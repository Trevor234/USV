#!/usr/bin/env python3
"""Independent actual API, lifecycle, typed Stored, Source and Witness audit.

Bag timestamps and CLOCK_MONOTONIC are never subtracted. Actual wire bytes are
matched to the independent generic transport receiver; typed Source CDR
reserialization is not assumed byte-identical to RMW padding.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
R=D/'runs/owned_normal20s_01'


def pin(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(p):return json.loads(p.read_bytes())
def lines(p):
    raw=p.read_bytes();assert len(raw)<=128*1024**2 and raw.endswith(b'\n')
    return [json.loads(x) for x in raw.splitlines()]
def norm(value):
    if type(value) in [str,bool,int,float,type(None)]:return value
    if hasattr(value,'get_fields_and_field_types'):return {k:norm(getattr(value,k)) for k in value.get_fields_and_field_types()}
    if hasattr(value,'tolist'):return norm(value.tolist())
    if hasattr(value,'item'):return norm(value.item())
    return [norm(x) for x in value]
def stamp(v):return v['sec']*1000000000+v['nanosec']
def rename_job(value):
    mapping={'schema_version':'schema','tick_origin_steady_ns':'tick_origin_ns','freeze_steady_ns':'freeze_ns',
             'deadline_steady_ns':'deadline_ns','target_steady_ns':'target_ns','horizon_steps':'N','prediction_dt':'dt'}
    return {mapping.get(k,k):v for k,v in value.items()}


def main():
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    src=lines(R/'regulator/source.jsonl');worker=lines(R/'worker/source.jsonl');nom=lines(R/'fixture/nominal_steps.jsonl');transport=lines(R/'fixture/transport_source.jsonl')
    source={k:[r for r in src if r['type']==k] for k in {r['type'] for r in src}}
    pairs=source['owned_API_pair'];decisions=source['decision'];jobs=[r['job'] for r in source['job']]
    manifests={role:read(R/role/('owned_manifest.json' if role=='fixture' else 'manifest.json')) for role in ['regulator','worker','fixture','recorder']}
    inputs=[p for p in R.rglob('*') if p.is_file()]+[Path(__file__).resolve(),D/'implementation/normal_registration_v1.json',D/'implementation/selected_runtime_registry_v1.json',D/'preflight/prerun_source_lock_v1.json',D/'evidence/normal_launch_v1.json']
    before={str(p):pin(p) for p in inputs}
    closure=read(D/'preflight/prerun_source_lock_v1.json')['files']
    closure.update(read(D/'preflight/execution_tool_input_lock_v1.json')['files'])
    for p,row in closure.items():assert pin(Path(p))==row,p
    result=read(R/'driver_result.json');outer=read(D/'evidence/normal_launch_v1.json');c=read(Path(read(D/'implementation/normal_registration_v1.json')['contract']))
    assert result['passed'] and outer['passed'] and len(result['closed_roles'])==4
    assert all(x['returncode']==0 and x['group_empty'] and [v['signal'] for v in x['signals']]==['SIGINT'] for x in result['closed_roles'])
    cm=manifests['regulator'];assert cm['role']=='p1_owned_execute_regulator' and cm['physical_publishers']==2 and cm['physical_API_calls_before_grant']==0
    output_topics={'/p1/solve_job','/p1/execution_decision','/research/control/applied',*c['output_topics'].values()}
    expected_gids={}
    for role,m in manifests.items():
        for ep in m['endpoints']:
            if ep['kind']=='publisher':
                assert ep['topic'] not in expected_gids;expected_gids[ep['topic']]=ep['gid']
                if ep['topic'] in output_topics:assert role=='regulator'
    ready=read(R/'regulator/ready.json');prepared=read(R/'regulator/prepared.json')
    assert ready['complete_recorder_pin']['manifest_sha256']==pin(R/'recorder/manifest.json')['sha256']
    full=source['owned_full_recorder_bound'][0];grant=source['owned_execute_grant_accepted'][0]
    assert full['physical_API_calls']==0 and full['bound_ns']<=grant['origin_ns']<=pairs[0]['starts'][0]
    assert ready['anchor_known']==[False,False] and ready['physical_API_calls']==0 and prepared['grant_sha256']==pin(R/'regulator/grant.json')['sha256']
    assert pairs[0]['initial_pair'] and pairs[0]['kind']=='bootstrap' and pairs[0]['previous_known']==[False,False] and pairs[0]['command_n']==[0,0] and pairs[0]['rho_available'] is False
    assert pairs[0]['starts'][0]-grant['origin_ns']<=c['T_ns']
    known=[False,False];previous=[0.,0.];last=[0,0];maxgap=[0,0];maxrate=[0.,0.];maxspan=0
    for i,row in enumerate(pairs):
        assert row['sequence']==i+1 and row['returned']==[True,True]
        assert row['previous_known']==known and row['previous_n']==previous and row['previous_start_ns']==last
        assert row['starts'][0]<=row['ends'][0]<=row['starts'][1]<=row['ends'][1]
        span=row['ends'][1]-row['starts'][0];maxspan=max(maxspan,span);assert span<=c['publish_budget_ns']
        for side in [0,1]:
            n=row['command_n'][side];assert math.isfinite(n) and c['command_min_n']<=n<=c['command_max_n']
            if known[side]:
                elapsed=row['starts'][side]-last[side];assert elapsed>0 and elapsed<=c['publish_gap_ns']
                rate=abs(n-previous[side])*1e9/elapsed;assert rate<=c['rho_n_s']+1e-8
                maxgap[side]=max(maxgap[side],elapsed);maxrate[side]=max(maxrate[side],rate)
            known[side]=True;previous[side]=n;last[side]=row['starts'][side]
        assert not any(row[k] for k in ['terminal','gap_exceeded','span_exceeded','rate_exceeded','command_invalid','bootstrap_late'])
    assert all(x['mode']=='execute' and not x['diagnostic_only'] and x['normal_contract_complete'] and x['skipped_ticks']==0 for x in decisions)
    maxjitter=max(x['start_ns']-x['planned_ns'] for x in decisions);assert 0<=maxjitter<=c['tick_jitter_ns']
    assert pairs[-1]['kind']=='shutdown' and pairs[-1]['command_n']==[0,0] and pairs[-1]['returned']==[True,True]
    shutdown=source['regulator_shutdown'][0];assert shutdown['zero_requested'] and shutdown['zero_target_published'] and not shutdown['shutdown_grace_exceeded'] and not shutdown['plant_hold_end_known']
    first,lastjob=result['first'],result['last'];window=[j for j in jobs if first['job_id']<=j['job_id']<=lastjob['job_id']]
    assert len(window)==101 and window[-1]['freeze_ns']-window[0]['freeze_ns']>=20000000000 and window[-1]['odom_stamp_ns']-window[0]['odom_stamp_ns']>=20000000000
    speed=[math.hypot(j['frozen_state'][3],j['frozen_state'][4]) for j in window]
    assert min(speed)>1e-6 and max(speed)<=1.2
    for job in jobs:
        assert job['anchor_source']=='regulator_publisher' and job['anchor_producer']==cm['producer_instance_id'] and job['anchor_run_id']==cm['run_id'] and job['anchor_known']==[True,True]
        assert job['deadline_ns']==job['tick_origin_ns']+150000000 and job['target_ns']==job['tick_origin_ns']+200000000
        assert job['tick_origin_ns']<=job['freeze_ns']<=job['deadline_ns']
        for side in [0,1]:
            seq=job['anchor_sequence'][side];actual=pairs[seq-1]
            assert actual['command_n'][side]==job['anchor_n'][side] and actual['starts'][side]==job['anchor_publish_ns'][side]<=job['freeze_ns']
        now=job['freeze_ns'];clock_now=job['frozen_clock_sim_ns']+now-job['frozen_clock_receive_ns']
        for key in ['odom']+(['imu'] if job['r_from_imu'] else []):
            assert 0<=now-job[key+'_receive_ns']<=c[key+'_age_ns']
            assert -c['source_future_slack_ns']<=clock_now-job[key+'_stamp_ns']<=c[key+'_sim_lag_ns']
    window_dec=[x for x in decisions if window[0]['freeze_ns']<=x['start_ns']<=window[-1]['freeze_ns']]
    assert len(window_dec)==100 and all(x['accepted'] for x in window_dec)
    assert source['source_summary'][0]['normal_source_complete'] and source['source_summary'][0]['dropped']==0
    ws=next(x for x in reversed(worker) if x['type']=='worker_summary');assert ws['normal_source_complete'] and not ws['fatal'] and ws['capability_source']['capability_source_complete']
    witness=read(R/'regulator/witness.json');assert witness['observation_complete'] and witness['business_ready_observed'] and not witness['overflow'] and not witness['incomplete']
    assert witness['counters']['tick']['published']==len(decisions) and witness['counters']['submit']['published']==len(jobs)
    # Decode the actual SQLite payload, not a reserialized diagnostic proxy.
    bag=next((R/'recorder/bag').glob('*.db3'));db=sqlite3.connect('file:'+str(bag)+'?mode=ro',uri=True)
    topics={i:(name,typ) for i,name,typ in db.execute('select id,name,type from topics')}
    decoded=collections.defaultdict(list);wire=collections.Counter();classes={typ:get_message(typ) for _,typ in topics.values()}
    for topic_id,data in db.execute('select topic_id,data from messages order by id'):
        name,typ=topics[topic_id];decoded[name].append(norm(deserialize_message(data,classes[typ])));wire[(name,hashlib.sha256(data).hexdigest())]+=1
    db.close();counts={k:len(v) for k,v in decoded.items()}
    assert counts['/p1/solve_job']==len(jobs)==103 and counts['/p1/solve_candidate']==ws['published_candidates']==103
    assert counts['/p1/execution_decision']==counts['/research/control/applied']==len(pairs)==105
    stored_jobs={j['job_id']:rename_job(j) for j in decoded['/p1/solve_job']}
    for job in jobs:assert stored_jobs[job['job_id']]==job
    worker_candidates={x['job']['job_id']:x for x in worker if x['type']=='candidate'}
    for candidate in decoded['/p1/solve_candidate']:
        row=worker_candidates[candidate['job']['job_id']]
        assert rename_job(candidate['job'])==row['job'] and candidate['first_control']==row['first_control'] and candidate['x_prediction']==row['X'] and candidate['u_prediction']==row['U']
        assert candidate['success']==row['success'] and candidate['prediction_available']==row['prediction_available']
    ds={x['sequence']:x for x in decisions}
    renames={'schema_version':'schema','clock_epoch':'epoch','tick_planned_ns':'planned_ns','tick_start_ns':'start_ns','tick_end_ns':'end_ns','candidate_accepted':'accepted','candidate_ready_commit_ns':'ready_commit_ns'}
    for decision in decoded['/p1/execution_decision']:
        row=ds[decision['sequence']]
        for key,value in decision.items():
            source_key=renames.get(key,key)
            if source_key in row:assert row[source_key]==value,('decision',key)
    for i,m in enumerate(decoded['/research/control/applied']):
        pair=pairs[i];d=ds[m['sequence']]
        assert m['sequence']==i+1 and m['run_id']==cm['run_id'] and m['config_hash']==cm['config_hash'] and m['producer_instance_id']==cm['producer_instance_id'] and m['baseline_id']==c['baseline_input']
        assert m['final_n']==pair['command_n'] and [m['left_publish_start_steady_ns'],m['right_publish_start_steady_ns']]==pair['starts'] and [m['left_publish_end_steady_ns'],m['right_publish_end_steady_ns']]==pair['ends']
        assert m['left_publish_success'] and m['right_publish_success'] and m['requested_n']==d['requested_n']
        assert not m['plant_acceptance_observed'] and not m['force_measured'] and not m['execution_atomicity_proven']
    assert decoded['/research/control/applied'][-1]['control_source']=='shutdown_zero'
    for side,key in enumerate(['left','right']):assert [m['data'] for m in decoded[c['output_topics'][key]]]==[p['command_n'][side] for p in pairs]
    ft=read(R/'fixture/terminal.json');assert ft['normal_end'] and not ft['failed']
    for topic,n in ft['published_counts'].items():assert counts[topic]==n
    steps={x['sim_stamp_ns']:x for x in nom if 'sim_stamp_ns' in x and 'sensor_sequence' in x}
    for m in decoded[c['input_topics']['odom']]:
        state=steps[stamp(m['header']['stamp'])]['state'];pose=m['pose']['pose'];twist=m['twist']['twist']
        assert pose['position']['x']==state[0] and pose['position']['y']==state[1] and twist['linear']['x']==state[3] and twist['linear']['y']==state[4] and twist['angular']['z']==state[5]
        assert abs(pose['orientation']['z']-math.sin(state[2]/2))<1e-12
    for m in decoded['/clock']:assert stamp(m['clock']) in steps
    cap_attempts=[x for x in worker if x['type']=='capability_publish_attempt']
    assert counts['/p1/worker_capability']==len(cap_attempts)==ws['capability_source']['capability_publish_returned']==111
    def capkey(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
    assert collections.Counter(capkey(m) for m in decoded['/p1/worker_capability'])==collections.Counter(capkey(x['payload']) for x in cap_attempts)
    observed=collections.Counter()
    for x in transport:
        assert x['publisher_gid']==expected_gids[x['topic']]
        observed[(x['topic'],x['payload_sha256'])]+=1
    extra=wire-observed;missing=observed-wire
    assert not missing and sum(extra.values())==1 and all(k[0]=='/p1/worker_capability' for k in extra)
    lastcap=next(x for x in reversed(worker) if x['type']=='capability_publish_result')
    assert lastcap['publish_start_ns']>ft['closed_steady_ns']
    rec=read(R/'recorder/terminal.json');assert rec['clean'] and rec['Recorder_stop_completed'] and rec['prepared'] and rec['storage_stream_accounting_verified'] is False
    after={p:pin(Path(p)) for p in before};assert before==after
    summary={'schema':'M4-owned-normal-independent-audit/v1','passed':True,'run_id':cm['run_id'],
      'actual_roles':4,'all_roles_RC0_INT_only_group_empty':True,'startup_full_recorder_before_grant_before_API':True,
      'physical_API_pairs':len(pairs),'actual_control_API_calls':2*len(pairs),'whole_Jobs':len(jobs),'whole_Candidates':103,'whole_Decisions':len(decisions),
      'whole_accepted_decisions':sum(x['accepted'] for x in decisions),'whole_decision_reasons':dict(collections.Counter(x['reason'] for x in decisions)),
      'normal_window':{'dynamic_jobs':len(window),'source_span_ns':window[-1]['freeze_ns']-window[0]['freeze_ns'],'odom_sim_span_ns':window[-1]['odom_stamp_ns']-window[0]['odom_stamp_ns'],
         'first_job_id':window[0]['job_id'],'last_job_id':window[-1]['job_id'],'decisions':len(window_dec),'accepted':sum(x['accepted'] for x in window_dec),
         'planar_speed_min_m_s':min(speed),'planar_speed_max_m_s':max(speed)},
      'first_pair_latency_from_grant_ns':pairs[0]['starts'][0]-grant['origin_ns'],'first_pair_rho_available':False,
      'full_stream_max_per_side_gap_ns':maxgap,'full_stream_max_pair_span_ns':maxspan,'max_tick_start_jitter_ns':maxjitter,'max_actual_per_side_rate_n_s':maxrate,
      'shutdown_zero_API_success':True,'plant_zero_or_hold_end_proven':False,'stored_messages':sum(counts.values()),'stored_counts':counts,
      'typed_Source_and_actual_Stored_matched':True,'wire_transport_matched_messages':sum(observed.values()),'one_capability_after_Fixture_close_explicitly_accounted':True,
      'Recorder_internal_storage_accounting_flag_retained_false':True,'external_storage_accounting_passed':True,
      'Regulator_callback_population_scope':'actual received callbacks only; best-effort/keep-last input reception is not all DDS publication delivery',
      'Regulator_received_callbacks':{k:len(source.get(k,[])) for k in ['clock','odom_admission','imu_admission','path_version','profile_version','capability_admission','candidate_registration']},
      'Witness_observation_complete':True,'Witness_profile_label':witness['profile'],'Witness_qualification_scope':witness['normal_contract_scope'],
      'normal_owned_outlet_component_qualified':True,'M4_stage_qualified':False,'F6_qualified':False,'P1_qualified':False,
      'original_F5_plant_reference_identity_qualified':False,'ordinary_production_release_enabled':False,'research_conclusion':False,
      'input_sha256_before':before,'input_sha256_after':after,'prerun_input_sha256':closure}
    with (D/'postrun/actual_normal_audit_v1.json').open('x') as f:json.dump(summary,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:summary[k] for k in ['passed','physical_API_pairs','whole_Jobs','whole_Candidates','whole_Decisions','stored_messages','full_stream_max_per_side_gap_ns','full_stream_max_pair_span_ns','max_tick_start_jitter_ns']}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        failure={'passed':False,'error':repr(error),'traceback':__import__('traceback').format_exc(),'stage_qualified':False}
        with (D/'postrun/actual_normal_audit_attempt01_failure_v1.json').open('x') as f:json.dump(failure,f,indent=2);f.write('\n')
        print(json.dumps({'passed':False,'error':repr(error)}));raise
