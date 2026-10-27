"""Seal current ordinary lease evidence and exact recovery gap; no stage promotion."""
import hashlib,json,time
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parent/'scheme_A_owned_business_start_20261020_39'
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def need(v,w):
    if not v:raise ValueError(w)
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
    for n in ['protection_initial_v1.json','protection_final_v1.json']:
        x=load(D/'preflight'/n)
        need(x['passed'] and x['protection']['full_local_current_byte_sha_recheck'] and x['protection']['unique_raw_files_reread']==47556
            and x['protection']['logical_bytes_streamed']==5994754345,'full old local byte protection')
        need(x['workspace_after']['staged_all_diff_bytes']==0 and x['protection']['business_diff_bytes']==151961
            and x['protection']['business_diff_sha256']=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5','original dirty and staging protection')
    for n in ['ordinary_supervision_v1.py','supervision_bridge_v1.py','business_start_v1.py','worker_terminal_close_v1.py','owned_auth.py','owned_release.py','runtime/owned_process_supervisor.py','build_manifest_current.json','source_bundles_current.json']:
        need((D/'author'/n).read_bytes()==(P/'author'/n).read_bytes(),'critical original implementation:'+n)
    c=load(D/'verification/lease_entry_components_v1.json');need(c['passed'] and c['negative_count']==13 and c['helper_pin']==pin(D/'author/lease_stimulus_v1.py'),'new orchestration checks')
    need(load(P/'build/business_observer_attempt01/result.json')['Native_cases']==38,'original current Native evidence')
    need(load(D.parent/'scheme_A_ordinary_supervision_20261020_38/verification/ordinary_components_v1.json')['negative_count']==44,'original ordinary policy component scope')
    lock=load(D/'preflight/prerun_source_lock_v1.json');need(len(lock['files'])==lock['count']==2043,'actual source lock scope')
    for p,f in lock['files'].items():need(pin(p)==f,'locked input changed:'+p)
    need(load(D/'verification/driver_CLI_v1.json')['driver_sha256']==pin(D/'author/prepare_pair_wakeup_v1.py')['sha256'],'checked actual driver version')
    audit_path=D/'postrun/ordinary_lease_actual_audit_v1.json';a=load(audit_path)
    need(a['passed'] and a['component_passed'] and a['current_ordinary_lease_case_qualified']
        and len(a['sections'])==6 and all(v['passed'] for v in a['sections'].values()),'six independent actual sections')
    need(a['input_sha256_before']==a['input_sha256_after'] and len(a['input_sha256_after'])==2168,'audited input stability')
    for p,f in a['input_sha256_after'].items():need(pin(p)==f,'audited input changed:'+p)
    n=load(D/'verification/actual_ordinary_lease_negatives_v1.json')
    need(n['passed'] and n['actual_raw_unchanged'] and len(n['cases'])==14 and all(c['rejected'] for c in n['cases']),'14 actual raw copy negatives')
    R=D/'author/runs/ordinary_lease_01';r=load(R/'result.json');launch=load(D/'postrun/launch_ordinary_lease_01_v1.json')
    need(launch['returncode']==0 and not launch['external_timeout_triggered'] and launch['inputs_unchanged'] and launch['elapsed_ns']<45000000000,'single bounded launch')
    need(r['ordinary_supervision_case_completed'] and r['supervision_case_completed'] and r['business_start_completed'] and r['Worker_normal_Source_qualified']
        and r['evidence_qualification_clean'] and r['V2_case']=='lease' and r['V2_case_completed'] is False
        and r['passed'] is False and r['normal_business_qualified'] is False and not r.get('error') and not r['close_errors'],'selected component and business scope')
    need(r['owned_role_returncodes']=={k:0 for k in ['observer','worker','publisher','synthetic_source','recorder']}
        and r['cleanup_complete'] and r['cleanup_within_budget'] and r['close_elapsed_ns']<=15000000000 and not r['ledger_failed'],'all five finite normal resource exits')
    need(all(x['cleanup_complete'] and x['remaining_members']==[] and not x['unexpected_descendants'] for x in r['cleanup'].values()),'all exact owned groups empty')
    hostscan=load(D/'postrun/final_process_observation_host_v1.json');need(not hostscan['selected_research_processes'],'no readable selected host process remains')
    ledger=[json.loads(x) for x in (R/'owned_process_ledger.jsonl').read_bytes().splitlines()]
    signals=[dict(role=x['name'],signal=x['signal']) for x in ledger if x['type']=='signal'];need(signals and all(x['signal']==2 for x in signals),'only ordinary actual INTs')
    s=a['sections'];gate=s['business_start_then_original_tick']['details'];stop=s['supervisor_bridge_chain']['details'];lease=s['lease_stimulus_and_post_stop_queue']['details'];storage=s['Stored_Fixture_actual_command_chain']['details']
    need(stop['cause']=='worker_capability_expired' and stop['actual_signal_sequence']==[2] and stop['Worker_normal_Source_complete']
        and stop['notification_to_authenticated_ns']<=250000000 and stop['authenticated_to_SIGINT_start_ns']<=100000000,'current ordinary immediate receipt-lease stop')
    need(lease['receipt_age_at_expiry_ns']>600000000 and lease['Worker_stop_completed_before_resume']
        and lease['post_exit_capability_callbacks']>=1 and not lease['same_run_revival'],'actual trigger and queued peer rejection')
    recovery=load(D/'postrun/recovery_evidence_gap_v1.json')
    need(recovery['inventory_audit_passed'] and len(recovery['links'])==2 and recovery['exact_lease41_then_new_run_observed'] is False
        and recovery['selected_following_lease_recovery_qualified'] is False,'exact recovery scope')
    need(recovery['input_sha256_before']==recovery['input_sha256_after'],'recovery inventory stability')
    for p,f in recovery['input_sha256_after'].items():need(pin(p)==f,'recovery input changed:'+p)
    need(load(D/'evidence/automatic_approval_timeout_v1.json')['started'] is False,'review timeout retained as non-execution')
    need(list((D/'author/runs').iterdir())==[R],'exact one actual run population')
    files=[dict(relative_path=str(p.relative_to(R)),**pin(p)) for p in sorted(R.rglob('*')) if p.is_file()]
    dump(D/'postrun/raw_run_freeze_v1.json',dict(root=str(R),files=files,count=len(files),bytes=sum(f['bytes'] for f in files),directories=[str(p.relative_to(R)) for p in sorted(R.rglob('*')) if p.is_dir()],all_original_raw_retained=True))
    dump(D/'postrun/postrun_retro_v1.json',dict(primary_mechanism='flow_policy_mismatch resolved by immediate monitor after actual gate ACK',
        selected_hypothesis_passed=True,same_lease_active_V1_rerun_justified=False,next='one precise healthy fresh-identity start after lease41 then B4 source/domain/policy closure',
        next_confidence='medium',next_impact='high',next_cost='low',next_risk='low',
        stop_condition='any new identity gate healthy candidate or normal tail prerequisite missing',
        EDA_route_STA_WNS_PPA='not applicable',stage_qualified=False,research_conclusion=False))
    dump(D/'postrun/final_QA_v1.json',dict(schema='current-ordinary-receipt-lease-final-QA/v1',passed=True,
        passed_scope='one current shadow receipt-lease immediate ordinary owned stop, post-exit queued callback guard and independent command data closure',
        actual_ROS_runs=1,execution_authorization_requests=2,first_authorization_review_timed_out_before_start=True,
        CXX_builds=0,all_five_current_registered_ELFs_reused=True,Native_cases_reused=38,Native_cases_executed_this_batch=0,
        ordinary_policy_component_negatives_reused=44,new_orchestration_negative_cases=13,actual_raw_copy_negative_cases=14,
        prerun_inputs_unchanged=2043,audit_inputs_unchanged=2168,audit_pin=pin(audit_path),
        current_selected_ordinary_lease_case_passed=True,ordinary_policy_implementation_unchanged=True,
        current_active39_and_V1_40_parent_successes_retained=True,
        metrics=dict(gate=gate,stop=stop,lease=lease,storage=storage),actual_signals=signals,
        all_five_role_returncodes_zero=True,all_five_owned_groups_empty=True,Worker_normal_Source_complete=True,
        TERM_KILL_paths_exercised=False,SIGSTOP_used=False,
        host_unreadable_processes=len(hostscan['unreadable_process_ids']),host_global_process_absence_claimed=False,
        old_local_paths_rechecked=47556,old_local_bytes_rechecked=5994754345,all_old_failures_preserved=True,
        selected_exact_post_lease41_new_run_recovery_qualified=False,existing_same_ELF_identity_links_verified=2,
        source_packet_freshness_proven=False,queued_old_payload_full_CDR_identity_proven=False,native_C_hang_proven=False,
        Recorder_builtin_stream_accounting_claim=False,independent_SQL_metadata_verified=True,
        B4_all_eight_groups_qualified=False,normal_business_qualified=False,stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False,
        MPC_delivery_pending_at_QA=True,delivery_authority='delivery_verification.json'))
    dump(D/'batch_status_final.json',dict(batch=41,status='current_ordinary_receipt_lease_immediate_stop_and_queued_exit_guard_completed',
        actual_ROS_runs=1,CXX_builds=0,actual_raw_negatives=14,new_orchestration_negative_cases=13,current_selected_ordinary_lease_case_passed=True,
        all_five_roles_zero_and_groups_empty=True,stage_qualified=False,execute_qualified=False,research_conclusion=False,
        next='exact post-lease41 fresh healthy new run then B4 source/domain/policy closure',MPC_delivery_authority='delivery_verification.json'))
    members=[];directories=[]
    for p in sorted(D.rglob('*')):
        need(not p.is_symlink(),'no archive symlinks');rel=str(p.relative_to(D))
        if p.is_dir():directories.append(rel)
        else:
            need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'already sealed');members.append(dict(relative_path=rel,**pin(p)))
    dump(D/'archive_inventory_v1.json',dict(schema='SchemeA-create-only-local-archive/v1',files=members,directories=directories,inventory_excludes_itself=True,
        optional_postseal_files=['delivery_verification.json'],created_monotonic_ns=time.monotonic_ns(),stage_qualified=False,execute_qualified=False,research_conclusion=False))
    print(json.dumps(dict(passed=True,sealed_files_including_inventory=len(members)+1,
        sealed_bytes_including_inventory=sum(m['bytes'] for m in members)+(D/'archive_inventory_v1.json').stat().st_size,
        inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],current_selected_ordinary_lease_case_passed=True)))
if __name__=='__main__':main()
