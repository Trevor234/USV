#!/usr/bin/env python3
"""Read-only P01 generic replay. sqlite mode=ro; CDR deserialization only; no ROS init."""
import collections,hashlib,json,sqlite3,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/home/trevor/USV/.sgh-research/experiments')
TREE=ROOT/'scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3'
RUN=TREE.parent/'runs/T2B_P01'
REGFILE=ROOT/'scheme_A_M4_t2b_prepos_20261025_81/implementation/T2B_prepos_registration.json'
OUT=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_70_81_review_20261025_82/evidence/replay01/protocol')
sys.path.insert(0,str(TREE))
sys.path.insert(0,str(ROOT/'p1_execution_architecture_20261005_01/v4_interfaces_snapshot/lib/python3.12/site-packages'))
import w2_audit_common as common

def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def lines(p):return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
def run_check(fn):
    try:return {'passed':True,'result':fn()}
    except Exception as e:return {'passed':False,'error_type':type(e).__name__,'reason':str(e)}
def run_hashes():return {str(p.relative_to(RUN)):sha(p) for p in sorted(RUN.rglob('*')) if p.is_file()}
before=run_hashes()
reg=read(REGFILE);registry=read(reg['registry']);c=read(reg['contract']);drv=read(RUN/'driver_result.json');dm=read(RUN/'driver_manifest.json')
rr=lines(RUN/'regulator/source.jsonl');wr=lines(RUN/'worker/source.jsonl');fr=lines(RUN/'fixture/nominal_steps.jsonl');rt=common.by_type(rr);wt=common.by_type(wr)
manifest={r:read(RUN/r/('owned_manifest.json' if r=='fixture' else 'manifest.json')) for r in ('regulator','worker','fixture','recorder')}
checks={}
identity={'registration_matches_Driver':sha(REGFILE)==dm['registration_sha256'], 'registry_matches_registration':sha(reg['registry'])==reg['registry_sha256'], 'contract_matches_registration':sha(reg['contract'])==reg['contract_sha256'], 'table_matches_registration':sha(reg['action_table'])==sha(RUN/'action_table_copy.json')==reg['action_table_sha256'], 'audit_tool_matches_registration':sha(reg['audit_tool']['path'])==reg['audit_tool']['sha256'], 'audit_tool_actual_sha256':sha(reg['audit_tool']['path']), 'audit_tool_registered_sha256':reg['audit_tool']['sha256']}
checks['role_source_ELF_identity']=run_check(lambda:common.check_role_identity(RUN,registry,manifest,reg,c.get('typed_configuration') or c))
for r in ('regulator','worker','fixture','recorder'):
    def role_identity(role=r):
        e=registry['roles'][role];m=manifest[role]
        assert sha(e['binary'])==e['binary_sha256']==m['binary_sha256'],'ELF pin differs'
        assert Path(m['exe']).resolve()==Path(e['binary']).resolve(),'ELF path differs'
        b=common.check_service_bundle(e,role)
        assert m['source_bundle_sha256']==b['bundle_sha256'],'bundle manifest differs'
        return {'binary_sha256':e['binary_sha256'],**b}
    checks[r+'_source_ELF_identity']=run_check(role_identity)
checks['publishers']=run_check(lambda:common.check_publishers(manifest,c))
checks['API_full_stream']=run_check(lambda:common.check_pair_stream(rt['owned_API_pair'],c))
checks['decisions']=run_check(lambda:common.check_decisions(rt['decision'],c))
checks['jobs']=run_check(lambda:common.check_jobs([x['job'] for x in rt['job']],rt['owned_API_pair'],c,manifest))
checks['fallback_policy']=run_check(lambda:common.check_fallback_policy(rt['decision'],c))
checks['Source_flush_witness_close']=run_check(lambda:common.check_witness(RUN,rr,'T2B'))
checks['bounded_shutdown']=run_check(lambda:common.check_shutdown(rr,c))
def close_raw():
    rows=drv.get('closed_roles',[])
    assert len(rows)==4,'not four close records'
    by={r['role']:r for r in rows};assert set(by)=={'regulator','worker','fixture','recorder'}
    for role,row in by.items():
        assert row['returncode']==0,role+' nonzero rc'
        assert row['group_empty'] is True,role+' group not empty'
        assert not row.get('error'),role+' has close error'
    return rows
checks['observed_four_role_rc0_group_empty_no_errors']=run_check(close_raw)
# Registered exact signal expectations are not present in this T2 registration.
# Report signals as observations without inventing an expected block.
conn=sqlite3.connect('file:'+str(RUN/'recorder/bag/bag_0.db3')+'?mode=ro',uri=True)
topics={i:(n,t) for i,n,t in conn.execute('select id,name,type from topics')}
stored=list(conn.execute('select id,topic_id,timestamp,data from messages order by id'))
counts=collections.Counter();wire=collections.Counter()
for _,tid,_,data in stored:
    name,_=topics[tid];counts[name]+=1;wire[(name,hashlib.sha256(data).hexdigest())]+=1
storage={'sqlite_integrity':conn.execute('pragma integrity_check').fetchone()[0], 'counts':dict(counts),'rows':len(stored)}
conn.close()
try:
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    classes={t:get_message(t) for _,t in topics.values()}
    decoded=collections.defaultdict(list)
    for _,tid,_,data in stored:
        name,typ=topics[tid];decoded[name].append(common.norm(deserialize_message(data,classes[typ])))
    storage['CDR_decoded']=True
    for key,fn in [('typed_Source_Stored',lambda:common.check_typed_equality(decoded,rr,wr,manifest,c)),('capability_Source_Stored',lambda:common.check_capability_source_vs_stored(decoded,wr)),('wire_GID_Stored',lambda:common.check_wire(RUN,decoded,wire,common.check_publishers(manifest,c))),('recorder_fixture_counts',lambda:common.check_recorder_and_fixture(RUN,decoded,c,'T2B'))]:checks[key]=run_check(fn)
    storage['Applied_sequences']=[x['sequence'] for x in decoded['/research/control/applied']]
    storage['Decision_sequences']=[x['sequence'] for x in decoded['/p1/execution_decision']]
except Exception as e:
    storage['CDR_decoded']=False;storage['decode_error_type']=type(e).__name__;storage['decode_reason']=str(e);storage['traceback']=traceback.format_exc()
# Count actual frozen facts; do not derive an overall qualification from local pass bits.
out={'schema':'private-read-only-P01-generic-checks-v1','run':str(RUN),'registration':str(REGFILE),'script':str(Path(__file__).resolve()),'mode':'artifact-only; sqlite mode=ro; no rclpy.init or ROS process; no role spawn/signals; common pure functions separately caught','identity':identity,'common_checks':checks,'source_counts':{'decisions':len(rt['decision']),'API_pairs':len(rt['owned_API_pair']),'Applied':len(rt['owned_applied_publication']),'jobs':len(rt['job']),'candidates_generated':len(wt['candidate']),'candidates_published':len(wt['candidate_publish_result']),'capability_attempts':len(wt['capability_publish_attempt'])},'Source_sequences':{k:[r['sequence'] for r in rt[k]] for k in ('decision','owned_API_pair','owned_applied_publication')},'Source_summary':rt.get('source_summary',[]),'Worker_summary':wt.get('worker_summary',[]),'witness':{k:read(RUN/'regulator/witness.json').get(k) for k in ('closed','overflow','incomplete','observation_complete','normal_contract_qualified','records_inconsistency','first_failure')},'Stored':storage,'check_applicability':{'fallback_policy':'The reused W generic function assumes hold solely by last accepted age and does not model the invalid argument. P01 tick4 reason=worker_unusable follows task_time_reference:epoch_terminal. Production p1_admission.hpp:131-135 permits hold only when !invalid, and regulator_owned_execute.cpp:1071 forces invalid for worker_unusable. Retain raw W failure, but do not classify it as a T2 runtime defect without a T2-aware predicate.'},'inspection_limits':['Generic checks do not certify T2 in-flight semantics or deadline boundary release; those require same-Job event ordering review.','T2 exact expected signals are absent; rc0/group-empty checked from recorded closure, without claiming current process-group OS observation.','Original audit omits these generic checks; successful private replay would repair evidence only, not frozen registration identity.'],'protected_run_files_unchanged':before==run_hashes(),'protected_run_files':len(before)}
(OUT/'validate_t2b_p01_result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
