"""Reconstruct the actual start boundary from Source, manifests and fixed Witness."""
import hashlib
import json
def need(v,w):
    if not v:raise ValueError(w)
def check(root,source,publisher,witness,command,proof,prepared,inputs,result,manifests):
    om,pm=manifests['observer'],manifests['publisher']
    waiting=[r for r in source if r.get('type')=='business_start_waiting']
    grants=[r for r in source if r.get('type')=='business_start_authorized']
    threads=[r for r in source if r.get('type')=='business_threads_started']
    need(len(waiting)==len(grants)==len(threads)==1,'unique waiting authorization and actual start records')
    need(not any(r.get('type') in ['business_start_closed_before_tick','business_tick_without_start_blocked'] for r in source),'no failed business start')
    grant,thread=grants[0],threads[0];at=grant['authorized_ns']
    before=source[:source.index(grant)]
    need(not any(r.get('type') in ['decision','job','controlled_phase_begin','controlled_phase_freeze'] for r in before),
         'no business decision phase or job before authenticated start')
    need(grant['decision_sequence_before']==grant['job_id_before']==0 and grant['physical_publisher_endpoints']==0,'native prestart zero business counters')
    need(any(r.get('type')=='odom_admission' for r in before) and any(r.get('type')=='capability_admission' and r['renewed'] for r in before),
         'actual receiver callbacks continue while gate waiting')
    need(command['schema']=='p1-owned-business-start-v1' and command['run_id']==om['run_id'] and command['boot_id']==om['boot_id']
         and command['contract_sha256']==om['contract_sha256']==pm['contract_sha256']
         and command['observer_manifest_sha256']==prepared['roles']['observer']['manifest_sha256']
         and command['publisher_manifest_sha256']==prepared['roles']['publisher']['manifest_sha256']
         and command['stage_qualified'] is False and command['execute_qualified'] is False,'actual command role bindings')
    driver=json.loads((root/'business_driver_identity.json').read_bytes())
    peer_driver=json.loads((root/'adapter_peer_pins.json').read_bytes())['driver']
    need(all(driver[k]==peer_driver[k] for k in ['pid','start_ticks','exe','exe_sha256','argv']),'business driver matches original authenticated peer pins')
    need(command['driver_pid']==driver['pid'] and command['driver_start_ticks']==driver['start_ticks']
         and command['driver_tool_sha256']==inputs['tool_sha256']['prepare_pair_wakeup_v1.py'],'actual driver PID-start and frozen tool')
    need(waiting[0]['gate']['created_ns']<=command['issued_ns']<=at<waiting[0]['gate']['deadline_ns']
         and at-command['issued_ns']<=2000000000,'gate wait and request TTL not extended')
    need(grant['version']==command['version'] and grant['actual_anchor_n']==[0.0,0.0]
         and grant['actual_anchor_sequence']==[command['initial_applied_sequence']]*2,'original zero anchor and version at start')
    bind=[r for r in publisher if r.get('type')=='controlled_observer_peer_bound']
    initial=[r for r in publisher if r.get('type')=='controlled_Applied_emitted' and r['control_source']=='controlled_initial_zero']
    ready=[r for r in before if r.get('type')=='legacy_ready']
    need(len(bind)==len(initial)==len(ready)==1 and initial[0]['final_n']==[0.,0.]
         and initial[0]['applied_sequence']==command['initial_applied_sequence'],'unique actual initial owner output and LegacyReady')
    need(bind[0]['source_written_ns']==command['publisher_bound_ns']==grant['driver_attested_Publisher_bound_ns']
         and bind[0]['source_written_ns']<=initial[0]['applied_publish_end_ns']<=ready[0]['readiness']['legacy_ready_ns']<=command['issued_ns'],
         'actual binding initial output joined ready before request')
    for key,topic in [('decision','/p1/execution_decision'),('job','/p1/solve_job')]:
        p=bind[0][key];need(p['pid']==om['pid'] and p['process_start_ticks']==om['process_start_ticks']
            and p['manifest_sha256']==command['observer_manifest_sha256'] and p['binary_sha256']==om['binary_sha256']
            and p['source_bundle_sha256']==om['source_bundle_sha256'] and p['endpoint']['topic']==topic,'actual native Publisher bound current Observer')
    digest=hashlib.sha256((root/'business_start_request.json').read_bytes()).hexdigest()
    need(proof['command_sha256']==grant['request_sha256']==digest and proof['Observer_authorized']==grant
         and proof['business_threads_started']==thread and proof['duplicate_create_rejected'] is True
         and proof['driver_live_parameters_completed_ns']==result['prebusiness_parameter_queries_completed_ns']<=command['issued_ns'],
         'typed parameter preparation and exact ACK proof')
    need(set(result['live_parameter_queries'])=={'publisher','worker','observer','synthetic_source'}
         and all(r['complete_name_set'] and r['typed_values_equal_expected'] and r['mutation_rejected'] for r in result['live_parameter_queries'].values()),
         'original complete live parameters checked before business start')
    decisions=[r for r in source if r.get('type')=='decision'];jobs=[r for r in source if r.get('type')=='job']
    need(decisions and jobs and decisions[0]['planned_ns']>=at+1000000000 and decisions[0]['start_ns']>=at+1000000000,'fresh original 1s tick origin after gate')
    need(thread['first_tick_lead_ns']==1000000000 and thread['job_deadline_ns']==150000000 and thread['period_ns']==200000000,
         'unchanged timing contract in actual start')
    need(all(r['planned_ns']>=at and r['activation_commit_ns']>=at for r in decisions)
         and all(r['commit_ns']>=at for r in witness['submit']),'no pre-gate authorization inherited')
    phase=[r for r in publisher if r.get('type')=='controlled_phase_emitted']
    need(phase and not any(r.get('type')=='controlled_phase_refused' for r in publisher),'first real phase meets original budget')
    first=phase[0];delta=first['phase_publish_end_ns']-first['phase']['planned_ns']
    need(0<=delta<150000000,'real first phase before unchanged150ms cutoff')
    need(om['physical_publisher_endpoints']==0 and om['effective_parameters']['business_start_policy']['value']=='owned-prepare-before-business-v1',
         'explicit gated shadow configuration only')
    return dict(passed=True,prestart_decisions=0,prestart_jobs=0,prestart_callbacks_live=True,
        parameter_queries_completed_ns=result['prebusiness_parameter_queries_completed_ns'],authorized_ns=at,
        first_tick_planned_ns=decisions[0]['planned_ns'],first_phase_publish_delay_ns=delta,
        first_phase_decision_sequence=first['phase']['decision_sequence'],duplicate_create_rejected=True,
        actual_gated_start_confirmed=True,stage_qualified=False,execute_qualified=False,research_conclusion=False)
