#!/usr/bin/env python3
"""Read-only fault-specific audit. Original normal status and close errors stay frozen."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import yaml
from rclpy.serialization import deserialize_message
from usv_research_interfaces.msg import ExecutionDecision,AppliedControl
from std_msgs.msg import String

D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_V1_sink_failure_20261019_v33r2'
R=N/'runs/v1_sink_ack_02'
PINS={}


def need(v,why):
    if not v:raise ValueError(why)


def read(p):
    p=Path(p);b=p.read_bytes();v=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
    need(str(p) not in PINS or PINS[str(p)]==v,'input changed:'+str(p));PINS[str(p)]=v;return b


def load(p):return json.loads(read(p))
def lines(p):return [json.loads(x) for x in read(p).splitlines() if x.strip()]


def parameter_digest(rows):
    result={}
    for k,r in rows.items():
        v=r['value'];t=r['type'];c=struct.pack('>d',v).hex() if t==3 else [struct.pack('>d',x).hex() for x in v] if t==8 else v
        need(type(c)==type(r['canonical_value']) and c==r['canonical_value'],'typed canonical value:'+k)
        result[k]=dict(type=t,canonical_value=c)
    return hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def main():
    for p in sorted(R.rglob('*')):
        if p.is_file():read(p)
    prereg=load(D/'preflight/V1_preregistration_r2_v1.json');lock=load(D/'preflight/prerun_author_lock_r2_v1.json')
    for p,expected in lock['files'].items():need(dict(bytes=len(read(p)),sha256=hashlib.sha256(read(p)).hexdigest())==expected,'prerun source changed:'+p)
    inp=load(R/'inputs.json');result=load(R/'result.json');fault=load(R/'observer/v1_fault.json');w=load(R/'observer/witness.json');prep=load(R/'preparation_evidence.json')
    need(result['passed'] is False and result['V1_fault_observed'] and result['V1_fault_case_completed'],'normal status or fault declaration')
    need(result['elapsed_ns']<=prereg['overall_observation_budget_ns'],'actual run budget')
    need(result['cleanup_complete'] and result['cleanup_within_budget'],'owned finite cleanup')
    need(result['owned_role_returncodes']==dict(observer=2,publisher=0,recorder=0,synthetic_source=0,worker=0),'expected returncodes')
    need(all(not x['remaining_members'] and x['cleanup_complete'] and not x['unexpected_descendants'] for x in result['cleanup'].values()),'owned group remains')
    for key in ['owned_dds_endpoint_binding_verified','native_applied_reader_matched_verified','native_capability_receivers_matched_verified','unique_dual_channel_owner','subscriptions_verified']:
        need(prep[key] is True,'actual prepare evidence:'+key)
    roles={role:load(R/role/'owned_manifest.json') for role in ['observer','publisher','worker','synthetic_source','recorder']}
    for role,m in roles.items():
        need(prep['roles'][role]['manifest_sha256']==hashlib.sha256(read(R/role/'owned_manifest.json')).hexdigest(),'prepare manifest binding:'+role)
        need(parameter_digest(m['effective_parameters'])==m['effective_parameters_sha256']==prep['roles'][role]['effective_parameters_sha256'],'effective parameters:'+role)
        need(m['effective_parameters_immutable'] is True and not m['execute_qualified'],'role scope:'+role)
        need(hashlib.sha256(read(m['exe'])).hexdigest()==m['binary_sha256'],'actual selected ELF:'+role)
        expected=inp['expected_parameters'][role];values={k:x['value'] for k,x in m['effective_parameters'].items()}
        need(values==expected,'full configured values:'+role)
    need(not any(e['topic'] in ['/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust'] and e['kind']=='publisher' for e in roles['observer']['endpoints']),'Observer acquired physical endpoint')
    need(roles['observer']['effective_parameters']['diagnostic_v1_sink_policy']['value']=='decision_queue_saturation_after_authenticated_phase_v2','explicit fault profile absent')
    need(w['header']==load(R/'expected_witness_header.json'),'Witness identity')
    need(w['observation_complete'] and w['closed'] and not w['overflow'] and not w['incomplete'],'Witness completeness')
    need(w['header']['binary_sha256']==fault['binary_sha256']==roles['observer']['binary_sha256']==prereg['observer_binary']['sha256'],'fault exact binary')
    need(w['header']['source_sha256']==fault['source_sha256']==hashlib.sha256(read(N/'observer/src/shadow/regulator_shadow_observer.cpp')).hexdigest(),'actual source')
    s=fault['sink'];need(s['capacity']==512 and s['depth_at_rejection']==512 and s['depth_before_fill']+s['filler_events']==512,'actual bounded queue saturation')
    need(s['first_failure_at_this_decision'] is True and s['state']==3 and s['failed'] and 0<s['filler_events']<=512,'first actual source failure')
    need(fault['stopping'] and not fault['normal_complete'] and fault['admission_slots']==0 and not fault['candidate_present'] and not fault['pending_present'],'failure business state')
    def phase(event,observation=None):
        rows=[x for x in w['phase'] if x['event_code']==event and (observation is None or x['observation_code']==observation)]
        need(len(rows)==1,'unique Witness phase:'+str(event));return rows[0]
    arm,begin,overflow,source_failure,end,stop,invalid=phase(1),phase(2),phase(3),phase(4),phase(6),phase(5,3),phase(8,3)
    need(arm['ns']<=begin['ns']<=s['rejection_ns']<=overflow['ns']<=source_failure['ns']<=end['ns']<=stop['ns']<=invalid['ns']<=fault['observation_ns'],'causal first failure order')
    need(stop['tick']==invalid['tick']==fault['tick'] and stop['job_id']==invalid['job_id']==fault['job_id'],'same actual DecisionEnqueue boundary')
    need(stop['stopping'] and invalid['stopping'] and invalid['admission_slots']==0 and invalid['candidate_present'] is False and invalid['pending_present'] is False,'same-boundary invalidation facts')
    need(not any(a['accepted'] and a['commit_ns']>stop['ns'] for a in w['activation']),'later accepted activation')
    need(not any(a['commit_ns']>stop['ns'] for a in w['submit']),'later submit authorization')
    observer=lines(R/'observer/source.jsonl');publisher=lines(R/'publisher/controlled_source.jsonl');transport=lines(R/'synthetic_source/transport_source.jsonl')
    summaries=[r for r in observer if r.get('type')=='source_summary'];need(len(summaries)==1,'Source terminal');summary=summaries[0]
    fills=[r for r in observer if r.get('type')=='diagnostic_v1_queue_fill'];need(len(fills)==s['filler_events'],'real fill rows drained')
    need(not summary['normal_source_complete'] and summary['dropped']>=1 and summary['generated']==summary['emitted']+summary['dropped'],'actual Source failure accounting retained')
    terminals=load(R/'recorder/terminal.json');need(terminals['clean'] and terminals['Recorder_stop_completed'],'Recorder normal drain')
    dbs=list((R/'recorder/bag').glob('*.db3'));need(len(dbs)==1,'one actual closed sqlite storage')
    db=sqlite3.connect(dbs[0].resolve().as_uri()+'?mode=ro',uri=True)
    data=db.execute('select t.name,m.data from messages m join topics t on m.topic_id=t.id order by m.id').fetchall();db.close()
    metadata=yaml.safe_load(read(R/'recorder/bag/metadata.yaml'))['rosbag2_bagfile_information']
    need(metadata['message_count']==len(data),'full Stored/metadata population count')
    actual_counts={}
    for topic,_ in data:actual_counts[topic]=actual_counts.get(topic,0)+1
    for row in metadata['topics_with_message_count']:
        need(actual_counts.get(row['topic_metadata']['name'],0)==row['message_count'],'Stored per-topic metadata count')
    read(yaml.__file__)
    stored=[];stored_applied=[];stored_phase=[];decision_hashes=[]
    gid=next(e['gid'] for e in roles['observer']['endpoints'] if e['topic']=='/p1/execution_decision' and e['kind']=='publisher')
    for topic,raw in data:
        if topic=='/p1/execution_decision':
            msg=deserialize_message(raw,ExecutionDecision);stored.append(msg);h=hashlib.sha256(raw).hexdigest();decision_hashes.append(h)
            need(any(r['topic']==topic and r['payload_sha256']==h and r['publisher_gid']==gid for r in transport),'Stored decision CDR exact source/GID')
            need(msg.run_id==fault['run_id'] and msg.contract_hash==fault['contract_hash'],'Stored decision identity')
        if topic=='/p1/controlled_owner_phase':
            phase_gid=next(e['gid'] for e in roles['publisher']['endpoints'] if e['topic']==topic and e['kind']=='publisher')
            h=hashlib.sha256(raw).hexdigest();need(any(r['topic']==topic and r['payload_sha256']==h and r['publisher_gid']==phase_gid for r in transport),'Stored phase actual owner/GID')
            stored_phase.append((json.loads(deserialize_message(raw,String).data),h,bytes(raw)))
        if topic=='/research/control/applied':stored_applied.append(deserialize_message(raw,AppliedControl))
    need(stored,'no Stored Decision')
    failed_sequence=fault['decision_sequence'];need(failed_sequence not in {m.sequence for m in stored},'failed Decision appeared in Storage')
    need(not any(r.get('type')=='decision' and r['sequence']==failed_sequence for r in observer),'failed Decision falsely present in Source')
    need(not any(r.get('type')=='controlled_decision_receipt' and r['decision_sequence']==failed_sequence for r in publisher),'failed Decision received by owner')
    accepted=[m for m in stored if m.candidate_accepted and m.sequence<failed_sequence];need(accepted,'no actual accepted prefix')
    joins=[]
    for m in accepted:
        source=[r for r in observer if r.get('type')=='decision' and r['sequence']==m.sequence and r['accepted']]
        physical=[r for r in publisher if r.get('type')=='controlled_decision_physical_return' and r['decision_sequence']==m.sequence]
        need(len(source)==len(physical)==1,'accepted Source/owner join')
        emission=[r for r in publisher if r.get('type')=='controlled_Applied_emitted' and r['applied_sequence']==physical[0]['applied_sequence']]
        need(len(emission)==1,'actual owner API report');e=emission[0]
        need(any(a.sequence==e['applied_sequence'] and list(a.final_n)==e['final_n'] for a in stored_applied),'Stored Applied prefix')
        before_arm=e['applied_publish_end_ns']<arm['ns']
        joins.append(dict(decision=m.sequence,job=m.job_id,command=list(m.final_n),applied_sequence=e['applied_sequence'],actual_Applied_before_arm=before_arm,Applied_minus_arm_ns=e['applied_publish_end_ns']-arm['ns']))
    arm_rows=[r for r in observer if r.get('type')=='diagnostic_v1_armed_after_ack']
    need(len(arm_rows)==1 and arm_rows[0]['armed'],'one actual authenticated arming event')
    ar=arm_rows[0];joined=next((j for j in joins if j['decision']==ar['decision_sequence'] and j['applied_sequence']==ar['applied_sequence']),None)
    need(joined is not None,'arm matched first accepted actual Applied')
    matching=[(c,h,raw) for c,h,raw in stored_phase if c['decision_sequence']==ar['decision_sequence'] and c['applied_sequence']==ar['applied_sequence']]
    need(len(matching)==1,'arm phase Stored exactly once');c,h,phase_wire=matching[0]
    callbacks=[r for r in observer if r.get('type')=='controlled_phase_callback' and r.get('accepted') and r.get('phase',{}).get('decision_sequence')==ar['decision_sequence']]
    need(len(callbacks)==1 and callbacks[0]['authentication_reason']=='','actual authenticated phase callback')
    receipt=callbacks[0]['raw_input'];typed=bytes.fromhex(receipt['cdr_hex'])
    need(hashlib.sha256(typed).hexdigest()==receipt['cdr_sha256'] and len(typed)==receipt['cdr_bytes'],'callback CDR self-integrity')
    need(receipt['publisher_gid']==phase_gid and receipt['topic']=='/p1/controlled_owner_phase','callback exact owner GID')
    need(typed[:4]==phase_wire[:4]==b'\x00\x01\x00\x00','supported CDR1 String header')
    payload_end=8+int.from_bytes(typed[4:8],'little')
    need(payload_end>8 and typed[payload_end-1]==0 and 0<=len(typed)-payload_end<=3 and 0<=len(phase_wire)-payload_end<=3,'bounded String CDR declared extent')
    need(typed[:payload_end]==phase_wire[:payload_end] and callbacks[0]['phase']==c,'complete declared String payload equality')
    phase_cdr_binding=dict(callback_serialized_bytes=len(typed),Stored_wire_bytes=len(phase_wire),declared_extent=payload_end,callback_sha256=receipt['cdr_sha256'],Stored_wire_sha256=h,trailing_bytes_preserved_not_rewritten=True)

    need(c['emitted_ns']<=arm['ns'] and c['emitted_ns']==ar['phase_emitted_ns'],'phase completion precedes arm')
    need(all(j['actual_Applied_before_arm'] for j in joins),'strict Applied-before-arm remains mandatory')
    zero_tail=[r for r in publisher if r.get('type')=='controlled_Applied_emitted' and r['left_start_ns']>phase(7,6)['ns'] and all(abs(x)<1e-9 for x in r['final_n'])]
    need(zero_tail,'no actual zero command tail after Observer close')
    need(all(any(a.sequence==e['applied_sequence'] and list(a.final_n)==e['final_n'] for a in stored_applied) for e in zero_tail),'zero command tail not Stored')
    current=dict(PINS)
    for p in current:read(p)
    need(current==PINS,'final input SHA changed')
    out=dict(schema='V1-actual-queue-fault-audit/v1',passed=True,passed_semantics='preregistered fault-local Source/Witness/Stored prefix and owned cleanup only',
      V1_preregistered_case_passed=all(j['actual_Applied_before_arm'] for j in joins),failed_preregistered_ordering=[j for j in joins if not j['actual_Applied_before_arm']],actual_authenticated_arm_binding=ar,phase_CDR_binding=phase_cdr_binding,first_actual_queue_failure=dict(decision=failed_sequence,job=fault['job_id'],tick=fault['tick'],depth_before_fill=s['depth_before_fill'],filler_events=s['filler_events'],depth_rejected=s['depth_at_rejection']),
      actual_Source_summary=summary,Witness_observation_complete=True,actual_accepted_prefix_joins=joins,
      failed_decision_not_Stored_or_owner_received=True,no_later_accepted_or_submit_authorization=True,
      slots_observed_empty_at_failure=True,nonempty_pre_failure_slot_interleaving_proven=False,
      stopping_after_overflow_ns=stop['ns']-overflow['ns'],invalidation_after_overflow_ns=invalid['ns']-overflow['ns'],timing_is_observation_not_WCET=True,
      Stored_messages=len(data),Stored_decisions=len(stored),Stored_applied=len(stored_applied),five_actual_owned_parameter_digests_verified=True,
      actual_owned_groups_all_empty=True,actual_role_returncodes=result['owned_role_returncodes'],Recorder_clean_drain=True,Recorder_builtin_stream_accounting_claim=terminals['storage_stream_accounting_verified'],independent_SQL_metadata_counts_matched=True,
      zero_command_tail_stored_after_Observer_close=[e['applied_sequence'] for e in zero_tail],Observer_normal_tail_receiver_qualified=False,
      original_normal_status=result['passed'],original_normal_close_errors=result['close_errors'],normal_final_version_close_qualified=False,
      original_failures_reclassified=False,elapsed_ns=result['elapsed_ns'],Source_extra_dropped_payload_identity='not reconstructed',
      input_sha256_before=current,input_sha256_after=PINS,stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False)
    with (D/'postrun/V1_actual_fault_audit_r2_v1.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:v for k,v in out.items() if k not in ['input_sha256_before','input_sha256_after']},ensure_ascii=False))


if __name__=='__main__':main()
