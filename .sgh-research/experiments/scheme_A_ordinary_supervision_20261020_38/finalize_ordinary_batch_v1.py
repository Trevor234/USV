"""Seal component evidence and failed integrations; no ordinary feature promotion."""
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
        need(r['passed'] and r['protection']['unique_raw_files_reread']==45573
            and r['protection']['logical_bytes_streamed']==5737501500 and r['protection']['full_local_current_byte_sha_recheck'],
            'complete old asset byte protection')
        need(r['workspace_after']['staged_all_diff_bytes']==0,'staging unchanged')
    component=load(D/'verification/ordinary_components_v1.json')
    need(component['passed'] and component['negative_count']==44 and len(component['frozen_Source_positive_causes'])==2
         and len(component['real_owned_child_cases'])==2,'selected component checks')
    need(all(c['actual_signals']==[2] and c['returncode']==0 and c['Source_auth_context_seeded'] for c in component['real_owned_child_cases']),
         'real child scope not mistaken for ROS Source authorization')
    for p,expected in component['input_sha256_before'].items():need(pin(p)==expected,'component frozen input changed')
    audit_path=D/'postrun/failed_attempts_audit_v1.json';audit=load(audit_path)
    need(audit['audit_passed'] and audit['ordinary_supervision_actual_passed'] is False and len(audit['attempts'])==3,
         'failed integration outcomes remain false')
    need(audit['input_sha256_before']==audit['input_sha256_after'] and len(audit['input_sha256_before'])==2551,'failure audit source scope')
    for p,item in audit['input_sha256_before'].items():need(pin(p)==item,'audited failure input changed:'+p)
    locks=[]
    for suffix,count in [('',1841),('_r2',1843),('_r3',1845)]:
        lock=load(D/'preflight'/('prerun_source_lock'+suffix+'_v1.json'));need(len(lock['files'])==count,'versioned source population')
        for p,item in lock['files'].items():need(pin(p)==item,'locked source changed:'+p)
        locks.append(dict(suffix=suffix,count=count))
    review=load(D/'postrun/change_review_v1.json')
    need(review['passed'] and review['all_five_role_ELFs_reused'] and review['CXX_builds']==0,'reviewed unchanged role versions')
    need(not load(D/'postrun/final_process_observation_v1.json')['matching_research_role_processes'],'no owned research roles left')
    for attempt in audit['attempts']:
        need(attempt['all_owned_groups_empty'] and not attempt['ordinary_dispatch_executed']
             and attempt['Worker_job_rows']==0 and not attempt['positive_ordinary_supervision_qualified'],'no fabricated ordinary success')
    need(audit['attempts'][0]['first_phase_applied_delay_ns']==181627259
         and audit['attempts'][0]['release_call_ns']==152964292
         and audit['attempts'][0]['queued_decision_bound_rejections']==26,'actual initial phase failure evidence')
    write(D/'postrun/postrun_retro_v1.json',dict(primary_mechanism='startup and preparation policy does not isolate business tick start',
        component_policy_validation_passed=True,ordinary_actual_Worker_qualified=False,
        first_attempt_actual_stimulus_entered=False,second_attempt_incorrect_Recorder_dependency=True,
        third_attempt_early_parameter_service_unavailable=True,third_specific_discovery_or_constructor_cause_proven=False,
        all_three_attempts_retained=True,same_script_recursive_run_justified=False,
        next='review startup dependencies then implement authenticated Observer business start gate before new live work',
        next_confidence='medium',next_impact='high',EDA_route_STA_WNS_PPA='not applicable',
        stage_qualified=False,execute_qualified=False,research_conclusion=False))
    write(D/'postrun/final_QA_v1.json',dict(schema='ordinary-supervision-component-and-failure-archive-QA/v1',passed=True,
        passed_scope='component evidence, faithful failure audit, source/asset preservation and archive integrity only',
        ordinary_actual_Worker_case_passed=False,ordinary_supervision_qualified=False,
        component_validation_passed=True,frozen_Source_positive_causes=2,component_negative_checks=44,
        real_Linux_owned_child_cases=2,real_child_authorization_context_seeded=True,
        actual_ROS_attempts=3,actual_successful_ordinary_Worker_runs=0,actual_ordinary_dispatches=0,
        actual_success_audit_or_its_raw_negative_checks_executed=False,
        all_five_role_ELFs_reused=True,CXX_builds=0,source_locks_unchanged=locks,
        failure_audit_pin=pin(audit_path),failure_audit_inputs_unchanged=2551,
        old_local_paths_rechecked=45573,old_local_bytes_rechecked=5737501500,
        all_started_owned_groups_empty=True,old_failures_and_current_failures_retained=True,
        next_runtime_startup_interface_implementation_pending=True,
        normal_final_role_combination_qualified=False,stage_qualified=False,execute_qualified=False,
        true_plant_qualified=False,research_conclusion=False,current_MPC_delivery_pending_at_QA=True,
        delivery_authority='delivery_verification.json'))
    write(D/'batch_status_final.json',dict(batch=38,status='ordinary_policy_component_verified_live_startup_dependencies_unclosed',
        component_passed=True,ordinary_actual_case_passed=False,actual_ROS_attempts=3,
        no_additional_actual_run_after_r3=True,original_dirty_and_all_failures_preserved=True,
        next='authenticated business-start gate; component proof before one new live confirmation',
        stage_qualified=False,execute_qualified=False,research_conclusion=False,MPC_delivery_authority='delivery_verification.json'))
    files=[];directories=[]
    for p in sorted(D.rglob('*')):
        need(not p.is_symlink(),'archive links prohibited');rel=str(p.relative_to(D))
        if p.is_dir():directories.append(rel)
        else:
            need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'already sealed')
            files.append(dict(relative_path=rel,**pin(p)))
    write(D/'archive_inventory_v1.json',dict(schema='SchemeA-create-only-local-archive/v1',files=files,directories=directories,
        created_monotonic_ns=time.monotonic_ns(),inventory_excludes_itself=True,
        optional_postseal_files=['delivery_verification.json'],ordinary_actual_case_passed=False,
        stage_qualified=False,execute_qualified=False,research_conclusion=False))
    print(json.dumps(dict(archive_QA_passed=True,ordinary_actual_case_passed=False,
        sealed_files_including_inventory=len(files)+1,
        sealed_bytes_including_inventory=sum(x['bytes'] for x in files)+(D/'archive_inventory_v1.json').stat().st_size,
        inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'])))
if __name__=='__main__':main()
