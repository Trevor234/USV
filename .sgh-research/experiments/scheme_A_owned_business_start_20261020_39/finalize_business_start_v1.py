"""Seal selected startup/ordinary stop evidence without promoting research stages."""
import hashlib
import json
from pathlib import Path
import time
D=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def need(v,w):
    if not v:raise ValueError(w)
def write(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
    for name in ['protection_initial_v1.json','protection_final_v1.json']:
        r=load(D/'preflight'/name)
        need(r['passed'] and r['protection']['unique_raw_files_reread']==46542
             and r['protection']['logical_bytes_streamed']==5821736387 and r['protection']['full_local_current_byte_sha_recheck'],'old asset full-byte protection')
        need(r['workspace_after']['staged_all_diff_bytes']==0,'staging empty')
    b=load(D/'build/business_observer_attempt01/result.json')
    need(b['passed'] and b['Native_cases']==38 and b['Native_rc']==0 and b['source_unchanged'],'selected build Native and source')
    need(b['binary_sha256']=='96fc74eb839367b6d420c6d698cc0302d242e1b57a879aaf39f4470d07aa7096','selected Observer ELF')
    lock=load(D/'preflight/prerun_source_lock_v1.json');need(len(lock['files'])==1805,'actual locked input scope')
    for p,r in lock['files'].items():need(pin(p)==r,'locked input changed:'+p)
    cli=load(D/'verification/driver_CLI_v2.json')
    need(cli['passed'] and cli['driver_sha256']==pin(D/'author/prepare_pair_wakeup_v1.py')['sha256'],'final CLI version')
    need(load(D/'verification/precheck_setup_failure_v1.json')['passed'] is False,'initial setup omission retained')
    audit_path=D/'postrun/business_ordinary_actual_audit_v1.json';a=load(audit_path)
    need(a['passed'] and a['component_passed'] and len(a['sections'])==5 and all(r['passed'] for r in a['sections'].values()),'five independent actual sections')
    need(a['input_sha256_before']==a['input_sha256_after'] and len(a['input_sha256_before'])==1924,'audit input stability')
    for p,r in a['input_sha256_before'].items():need(pin(p)==r,'audited input changed:'+p)
    for leaf,count in [('actual_business_gate_negatives_v1.json',6),('actual_ordinary_negatives_v1.json',10)]:
        n=load(D/'verification'/leaf)
        need(n['passed'] and len(n['cases'])==count and all(r['rejected'] for r in n['cases']) and n['actual_raw_unchanged'],'actual-copy rejection scope:'+leaf)
    R=D/'author/runs/business_active_01';r=load(R/'result.json');launch=load(D/'postrun/launch_business_active_01_v1.json')
    need(launch['returncode']==0 and launch['inputs_unchanged'] and not launch['external_timeout_triggered'] and launch['elapsed_ns']<45000000000,'one bounded actual run')
    need(r['ordinary_supervision_case_completed'] and r['business_start_completed'] and r['Worker_normal_Source_qualified']
         and r['passed'] is False and r['normal_business_qualified'] is False and r['V2_case_completed'] is False,'actual expected fault case separate from normal business')
    need(r['owned_role_returncodes']=={k:0 for k in ['observer','worker','publisher','synthetic_source','recorder']}
         and r['cleanup_complete'] and r['cleanup_within_budget'] and not r['close_errors'] and not r.get('error'),'five ordinary role exits and receiver close')
    need(not load(D/'postrun/final_process_observation_v1.json')['matching_research_role_processes'],'no residual roles')
    gate=a['sections']['business_start_then_original_tick']['details'];stop=a['sections']['supervisor_bridge_chain']['details']
    need(gate['prestart_jobs']==gate['prestart_decisions']==0 and gate['first_phase_publish_delay_ns']==3386393,'actual startup fix')
    need(stop['actual_signal_sequence']==[2] and stop['Worker_returncode']==0 and stop['Worker_normal_Source_complete']
         and stop['used_wait_stages']==['natural','worker_grace'] and not stop['diagnostic_SIGSTOP_injected'],'actual no-pause normal Worker stop')
    review=load(D/'preflight/source_change_review_v1.json')
    need(review['passed'] and all(r['byte_equal'] for r in review['unchanged_function_segments'].values()),'original hot-path behavior remains byte equal')
    files=[dict(relative_path=str(p.relative_to(R)),**pin(p)) for p in sorted(R.rglob('*')) if p.is_file()]
    write(D/'postrun/raw_run_freeze_v1.json',dict(root=str(R),files=files,count=len(files),bytes=sum(r['bytes'] for r in files),
        directories=[str(p.relative_to(R)) for p in sorted(R.rglob('*')) if p.is_dir()],all_original_raw_retained=True))
    write(D/'postrun/postrun_retro_v1.json',dict(primary_mechanism='explicit authenticated business start removes pre-release business scheduling',
        selected_start_and_ordinary_active_case_passed=True,observations=dict(gate=gate,stop=stop),
        same_active_or_V3_rerun_justified=False,experience_used=['retain actual readiness order','do not relax150ms','ordinary stop need not force KILL','scope flags remain separate'],
        next='necessary current-version V1, ordinary lease and explicit new-identity recovery then B4 policy/domain closure',
        next_confidence='medium',next_impact='high',EDA_route_STA_WNS_PPA='not applicable',stage_qualified=False,research_conclusion=False))
    storage=a['sections']['Stored_Fixture_actual_command_chain']['details']
    write(D/'postrun/final_QA_v1.json',dict(schema='owned-business-start-and-ordinary-active-final-QA/v1',passed=True,
        passed_scope='selected nominal shadow authenticated business start, ordinary actual active stop, data closure and archive integrity',
        actual_ROS_runs=1,CXX_build_attempts=1,Native_cases=38,actual_raw_copy_negatives=16,new_Observer_ELF=True,four_parent_ELFs_reused=True,
        business_start_actual_case_passed=True,ordinary_active_stop_actual_case_passed=True,
        normal_Worker_Source_complete=True,all_five_roles_return0=True,SIGSTOP_used=False,actual_signal_sequence=[2],
        TERM_KILL_paths_exercised_in_this_run=False,actual_lease_ordinary_stop_qualified=False,
        current_final_V1_and_full_recovery_qualified=False,all_terminal_causes_qualified=False,
        prerun_inputs_unchanged=1805,audit_inputs_unchanged=1924,audit_pin=pin(audit_path),metrics=dict(gate=gate,stop=stop),
        Stored_messages=storage['Stored_messages'],Recorder_builtin_stream_accounting_claim=False,independent_SQL_metadata_verified=True,
        old_local_paths_rechecked=46542,old_local_bytes_rechecked=5821736387,
        old_batch38_three_failures_not_reclassified=True,normal_business_qualified=False,stage_qualified=False,
        execute_qualified=False,true_plant_qualified=False,research_conclusion=False,
        current_MPC_delivery_pending_at_QA=True,delivery_authority='delivery_verification.json'))
    write(D/'batch_status_final.json',dict(batch=39,status='authenticated_business_start_and_selected_ordinary_active_stop_completed',
        actual_ROS_runs=1,Native_cases=38,actual_raw_negatives=16,all_owned_groups_empty=True,
        ordinary_selected_active_case_passed=True,stage_qualified=False,execute_qualified=False,research_conclusion=False,
        next='current-version necessary V1/lease/recovery, then B4 closure',MPC_delivery_authority='delivery_verification.json'))
    members=[];directories=[]
    for p in sorted(D.rglob('*')):
        need(not p.is_symlink(),'archive symlink prohibited');rel=str(p.relative_to(D))
        if p.is_dir():directories.append(rel)
        else:
            need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'already sealed')
            members.append(dict(relative_path=rel,**pin(p)))
    write(D/'archive_inventory_v1.json',dict(schema='SchemeA-create-only-local-archive/v1',files=members,directories=directories,
        inventory_excludes_itself=True,optional_postseal_files=['delivery_verification.json'],created_monotonic_ns=time.monotonic_ns(),
        stage_qualified=False,execute_qualified=False,research_conclusion=False))
    print(json.dumps(dict(passed=True,sealed_files_including_inventory=len(members)+1,
        sealed_bytes_including_inventory=sum(r['bytes'] for r in members)+(D/'archive_inventory_v1.json').stat().st_size,
        inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],ordinary_selected_active_case_passed=True)))
if __name__=='__main__':main()
