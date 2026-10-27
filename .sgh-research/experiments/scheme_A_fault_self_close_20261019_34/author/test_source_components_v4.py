#!/usr/bin/env python3
"""Fresh-copy semantic negatives; originals and checker helpers stay untouched."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True
N=Path(__file__).resolve().parent
sys.path.insert(0,str(N))
import check_source_components_v4 as c


def hashes(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def event(rs,typ):return next(r for r in rs if r['type']==typ)
def write(p,rs):p.write_text(''.join(json.dumps(r,sort_keys=True,allow_nan=False)+'\n' for r in rs))
def normalize(rs,role):
    terminal=event(rs,'worker_summary' if role=='worker' else 'source_summary')
    if role=='worker':terminal['source_rows_before_terminal']=terminal['source_rows_emitted_before_terminal']=len(rs)-1
    else:terminal['generated']=terminal['emitted']=len(rs)-1
def edit(rs,typ,field,value):event(rs,typ)[field]=value


def cap_cdr(rs):
    from rclpy.serialization import deserialize_message,serialize_message
    from usv_research_interfaces.msg import WorkerCapability
    a=event(rs,'capability_publish_attempt');msg=deserialize_message(bytes.fromhex(a['cdr']['hex']),WorkerCapability)
    msg.completed_jobs+=1;a['payload']['completed_jobs']=msg.completed_jobs;blob=serialize_message(msg)
    a['cdr']['hex']=blob.hex();a['cdr']['bytes']=len(blob);a['cdr']['sha256']=c.sha(blob)
    a['payload_sha256']=c.typed_sha(a['payload']);event(rs,'capability_publish_result')['payload_sha256']=a['payload_sha256']


def cap_drop_tail(rs):
    seq=event(rs,'worker_summary')['capability_source']['capability_generated']
    rs[:]=[r for r in rs if not (r['type'] in ('capability_publish_attempt','capability_publish_result') and r['publish_seq']==seq)]
    terminal=event(rs,'worker_summary')['capability_source'];last=[r for r in rs if r['type']=='capability_publish_attempt'][-1];result=[r for r in rs if r['type']=='capability_publish_result'][-1]
    for key in ('capability_generated','capability_attempt_records','capability_publish_calls','capability_publish_returned','capability_result_records','capability_last_publish_seq'):terminal[key]=seq-1
    terminal['capability_last_payload_sha256']=last['payload_sha256'];terminal['capability_last_publish_end_ns']=result['publish_end_ns'];normalize(rs,'worker')


def raw_unused(rs,field):
    from rclpy.serialization import deserialize_message,serialize_message
    from nav_msgs.msg import Odometry
    r=event(rs,'odom_admission')['raw_input'];m=deserialize_message(bytes.fromhex(r['cdr_hex']),Odometry)
    if field=='covariance':m.pose.covariance[0]=7.
    else:m.pose.pose.position.z=7.
    raw=serialize_message(m);r['cdr_hex']=raw.hex();r['cdr_bytes']=len(raw);r['cdr_sha256']=c.sha(raw)


def unknown(rs,role):rs.insert(-1,{'type':'undeclared_source_event','value':0});normalize(rs,role)
def missing_raw(rs):event(rs,'odom_admission').pop('raw_input')
def cap_type(rs):
    a=event(rs,'capability_publish_attempt');a['payload']['horizon_steps']=True;a['payload_sha256']=c.typed_sha(a['payload']);event(rs,'capability_publish_result')['payload_sha256']=a['payload_sha256']


def header_late(rs):
    header=event(rs,'capability_source_header');rs.remove(header);rs.insert(2,header)


def result_early(rs):
    result=event(rs,'capability_publish_result');rs.remove(result);rs.insert(rs.index(event(rs,'capability_publish_attempt')),result)


CASES=[
 ('cap_drop_first_attempt','worker',lambda rs:rs.remove(event(rs,'capability_publish_attempt')),'cap_source_sequence'),
 ('cap_drop_tail_coherent_counters','worker',cap_drop_tail,'cap_full_publisher_storage_population'),
 ('cap_changed_payload_and_cdr','worker',cap_cdr,'cap_full_publisher_storage_population'),
 ('cap_payload_bool_horizon','worker',cap_type,'cap_exact_scalar_types'),
 ('cap_actual_call_time_reversed','worker',lambda rs:edit(rs,'capability_publish_result','publish_end_ns',0),'cap_actual_call_order'),
 ('cap_actual_call_not_returned','worker',lambda rs:edit(rs,'capability_publish_result','returned',False),'cap_actual_call_order'),
 ('cap_wrong_header_gid','worker',lambda rs:event(rs,'capability_source_header')['endpoint']['gid'].__setitem__(0,255),'cap_header_GID'),
 ('cap_wrong_author_binary','worker',lambda rs:edit(rs,'capability_source_header','binary_sha256','0'*64),'cap_header_author'),
 ('cap_terminal_count','worker',lambda rs:event(rs,'worker_summary')['capability_source'].__setitem__('capability_publish_calls',0),'cap_terminal_counters'),
 ('cap_terminal_io_failed','worker',lambda rs:event(rs,'worker_summary')['capability_source'].__setitem__('capability_source_io_failed',True),'cap_terminal_counters'),
 ('cap_attempt_hash','worker',lambda rs:edit(rs,'capability_publish_attempt','payload_sha256','0'*64),'cap_payload_SHA'),
 ('worker_unknown_event','worker',lambda rs:unknown(rs,'worker'),'unknown_positive_worker_source_event'),
 ('observer_unknown_event','observer',lambda rs:unknown(rs,'observer'),'unknown_positive_observer_source_event'),
 ('raw_missing_whole_input','observer',missing_raw,'raw_input_missing'),
 ('raw_unused_pose_z','observer',lambda rs:raw_unused(rs,'z'),'raw_full_fields_storage_subset'),
 ('raw_unused_covariance','observer',lambda rs:raw_unused(rs,'covariance'),'raw_full_fields_storage_subset'),
 ('raw_wrong_cdr_sha','observer',lambda rs:event(rs,'odom_admission')['raw_input'].__setitem__('cdr_sha256','0'*64),'raw_cdr_identity'),
 ('raw_wrong_gid','observer',lambda rs:event(rs,'odom_admission')['raw_input']['publisher_gid'].__setitem__(0,255),'raw_actual_GID'),
 ('raw_wrong_sequence','observer',lambda rs:event(rs,'odom_admission')['raw_input'].__setitem__('callback_sequence',2),'raw_schema_sequence'),
 ('raw_extra_field','observer',lambda rs:event(rs,'odom_admission')['raw_input'].__setitem__('unregistered',0),'raw_exact_field_set'),
 ('raw_bool_rmw_sequence','observer',lambda rs:event(rs,'clock')['raw_input'].__setitem__('publication_sequence_number',True),'raw_exact_integer_types'),
 ('RTF_changed_estimate','observer',lambda rs:edit(rs,'clock','rtf',0.01),'independent_clock_window'),
 ('RTF_changed_window','observer',lambda rs:edit(rs,'clock','rtf_window_span_ns',1),'independent_clock_window'),
 ('path_fingerprint','observer',lambda rs:edit(rs,'path_version','fingerprint','0'*64),'path_raw_fingerprint'),
 ('profile_fingerprint','observer',lambda rs:edit(rs,'profile_version','fingerprint','0'*64),'profile_raw_fingerprint'),
 ('raw_composed_state','observer',lambda rs:event(rs,'odom_admission')['state'].__setitem__(3,.2),'odom_raw_state'),
 ('job_nominal_target','observer',lambda rs:event(rs,'job')['job']['target_state'].__setitem__(0,.2),'independent_nominal_RK4'),
 ('job_reference126','observer',lambda rs:event(rs,'job')['job']['reference'].__setitem__(0,.2),'independent_frozen_reference126'),
 ('job_reference_selection','observer',lambda rs:event(rs,'job')['input_provenance'].__setitem__('profile_stamp_ns',0),'immutable_reference_selection'),
 ('job_target_sim_mapping','observer',lambda rs:event(rs,'job')['job'].__setitem__('target_sim_ns',event(rs,'job')['job']['target_sim_ns']+1000),'target_sim_mapping'),
 ('job_authenticated_history','observer',lambda rs:event(rs,'job')['job']['history_n'].__setitem__(0,0.),'job_history_authenticated_whole_prefix'),
 ('legacy_applied_full_projection','observer',lambda rs:event(rs,'legacy_anchor')['applied']['final_n'].__setitem__(0,0.),'complete_legacy_applied_full_fields'),
 ('cap_header_after_attempt','worker',header_late,'cap_header_first'),
 ('cap_result_before_attempt','worker',result_early,'cap_source_record_order'),
 ('cap_terminal_time_reversed','worker',lambda rs:edit(rs,'worker_summary','finished_ns',0),'cap_terminal_time'),
]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    root=Path(a.run);out=Path(a.output);out.mkdir();copies=N/'validation_copies'/out.name;copies.mkdir(parents=True)
    before=hashes(root);tool_before={p.name:c.sha(p.read_bytes()) for p in (N/'check_source_components_v4.py',Path(__file__))}
    (out/'prerun_identity.json').open('x').write(json.dumps({'tool_sha256':tool_before,'original_records':before,'cases':[{ 'name':n,'role':r,'expected_code':e} for n,r,_,e in CASES],'copied_originals_only':True,'stage_qualified':False},indent=2)+'\n')
    results=[]
    for name,role,mutator,expected in CASES:
        target=copies/name;shutil.copytree(root,target);source=target/role/'source.jsonl';rs=rows(source);mutator(rs);write(source,rs)
        s=None
        try:s=c.load(target);report=c.analyze(s)
        except Exception as e:report={'passed':False,'issues':[{'code':'bounded_input_or_checker_error','detail':type(e).__name__+': '+str(e)}]}
        codes=[i['code'] for i in report['issues']];matched=(not report['passed'] and expected in codes)
        report.update(expected_code=expected,expected_negative_matched=matched,copy_root=str(target),copy_hashes=hashes(target),no_stage_qualification=True)
        (out/(name+'.json')).open('x').write(json.dumps(report,indent=2,allow_nan=False)+'\n')
        results.append({'name':name,'expected_code':expected,'observed_codes':sorted(set(codes)),'expected_negative_matched':matched});print(name,matched,flush=True)
    summary={'schema':'p1-source-component-fresh-copy-negatives-v4','passed':all(x['expected_negative_matched'] for x in results),'cases':results,'count':len(results),'originals_unchanged':before==hashes(root),'tools_unchanged':tool_before=={p.name:c.sha(p.read_bytes()) for p in (N/'check_source_components_v4.py',Path(__file__))},'stage_qualified':False}
    summary['passed']=summary['passed'] and summary['originals_unchanged'] and summary['tools_unchanged']
    (out/'summary.json').open('x').write(json.dumps(summary,indent=2)+'\n');return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
