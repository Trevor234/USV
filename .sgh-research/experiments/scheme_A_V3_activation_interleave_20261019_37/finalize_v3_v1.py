"""Verify the selected component evidence, freeze raw data and seal this batch."""
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
    proofs=[load(D/'preflight'/n) for n in ['protection_initial_v1.json','protection_final_v1.json']]
    for r in proofs:
        need(r['passed'] and r['protection']['unique_raw_files_reread']==44754
            and r['protection']['logical_bytes_streamed']==5598715826
            and r['protection']['full_local_current_byte_sha_recheck'],'old asset byte protection')
        need(r['workspace_after']['staged_all_diff_bytes']==0,'staging remains empty')
    lock=load(D/'preflight/prerun_source_lock_v1.json');need(len(lock['files'])==1799,'selected source count')
    for p,item in lock['files'].items():need(pin(p)==item,'prerun input changed:'+p)
    b1=load(D/'build/v3_observer_attempt01/result.json');b2=load(D/'build/v3_observer_attempt02/result.json')
    need(not b1['passed'] and b1['build_rc']!=0 and 'gtest_label_testthrow_' in (D/'build/v3_observer_attempt01/build.log').read_text(),'initial build error evidence retained')
    need(b2['passed'] and b2['Native_cases']==29 and b2['Native_rc']==0 and b2['source_unchanged'],'final build and selected Native')
    need(b2['binary_sha256']=='0ad364024f7ae4f452b280ed659db8239760397da8675c2846ffb1d370938043','actual selected Observer')
    audit_path=D/'postrun/v3_actual_audit_v1.json';audit=load(audit_path)
    need(audit['passed'] and audit['component_passed'] and len(audit['sections'])==4 and all(r['passed'] for r in audit['sections'].values()),'four actual independent sections')
    need(audit['input_sha256_before']==audit['input_sha256_after'] and len(audit['input_sha256_before'])==1909,'audit input scope and stability')
    for p,item in audit['input_sha256_before'].items():need(pin(p)==item,'raw audited input changed:'+p)
    neg=load(D/'postrun/v3_checker_negative_actual_v1.json')
    need(neg['passed'] and len(neg['cases'])==8 and all(c['rejected'] for c in neg['cases']) and neg['actual_raw_unchanged'],'eight actual-copy negatives')
    need(load(D/'postrun/change_review_v1.json')['passed'],'focused source review')
    R=D/'author/runs/v3_odom_01';run=load(R/'result.json');launch=load(D/'postrun/launch_v3_odom_01_v1.json')
    need(launch['returncode']==0 and launch['inputs_unchanged'] and not launch['external_timeout_triggered'] and launch['elapsed_ns']<45000000000,'one bounded launch')
    need(run['passed'] and run['cleanup_complete'] and run['cleanup_within_budget'] and not run['close_errors'] and not run.get('error'),'normal finite driver closure')
    need(all(c==0 for c in run['owned_role_returncodes'].values()) and len(run['owned_role_returncodes'])==5,'five normal role exits')
    need(not load(D/'postrun/final_process_observation_v1.json')['matching_research_role_processes'],'no remaining research roles')
    boundary=load(D/'postrun/qualification_boundaries_v1.json')
    need(boundary['Witness_observation_complete'] and boundary['Witness_business_ready_observed']
        and boundary['Decision_normal_contract_complete_all_false'] and not boundary['B4_B5_M4_F6_P1_stage_qualified'],'qualification boundaries retained')
    details=audit['sections']['Stored_Fixture_actual_command_chain']['details'];alignment=details['independent_activation_alignment']
    need(alignment['actual_revalidations']==1 and alignment['older_raw_odom_selected']==1 and alignment['maximum_frames_scanned']==3,'new actual branches hit')
    metric=audit['sections']['actual_source_interleave']['details']
    need(metric['attempts']==2 and metric['accepted_after_final_guard'] and metric['wait_ns']==8820274
        and metric['activation_jitter_ns']==8956596,'selected actual interleave result')
    rawfiles=[dict(relative_path=str(p.relative_to(R)),**pin(p)) for p in sorted(R.rglob('*')) if p.is_file()]
    write(D/'postrun/raw_run_freeze_v1.json',dict(root=str(R),files=rawfiles,
        directories=[str(p.relative_to(R)) for p in sorted(R.rglob('*')) if p.is_dir()],
        count=len(rawfiles),bytes=sum(r['bytes'] for r in rawfiles),all_original_raw_retained=True))
    write(D/'postrun/postrun_retro_v1.json',dict(primary_mechanism='actual concurrency evidence gap closed for selected finite source scope',
        hypotheses=dict(real_callback_during_wait=True,first_guard_invalidated=True,fresh_second_snapshot=True,
            older_causal_frame_selected=True,original_jitter_deadline_not_extended=True),
        observations=metric,experience_used=['snapshot freshness differs from target-time causal frame','driver/Witness scope differs from stage qualification'],
        repeated_same_V3_run_justified=False,next_objective='ordinary unpaused supervision and final role-combination necessary confirmation',
        next_confidence='medium',next_impact='high',next_risk='bounded',EDA_route_STA_WNS_PPA='not applicable',
        stage_qualified=False,execute_qualified=False,research_conclusion=False))
    write(D/'postrun/final_QA_v1.json',dict(schema='V3-selected-activation-source-final-QA/v1',passed=True,
        passed_scope='selected nominal owned-source input interleave, bounded causal revalidation, independent data closure and asset integrity',
        actual_ROS_runs=1,CXX_build_attempts=2,CXX_initial_failed_attempt_retained=True,selected_Native_cases=29,
        new_Observer_ELFs_selected=1,four_other_role_ELFs_reused=True,actual_raw_copy_negative_cases=8,
        prerun_source_inputs_unchanged=1799,actual_audit_inputs_unchanged=1909,
        old_local_paths_rechecked=44754,old_local_bytes_rechecked=5598715826,
        actual_audit_pin=pin(audit_path),metrics=metric,Stored_messages=details['Stored_messages'],
        independent_SQL_metadata_verified=True,Recorder_builtin_stream_accounting_claim=False,
        normal_owned_close=True,Worker_normal_Source_complete=True,selected_V3_actual_source_case_completed=True,
        actual_clock_or_reference_invalidation_covered=False,ordinary_unpaused_supervision_qualified=False,
        final_role_combination_whole_qualified=False,stage_qualified=False,execute_qualified=False,
        true_plant_qualified=False,research_conclusion=False,current_MPC_delivery_pending_at_QA=True,
        delivery_authority='delivery_verification.json'))
    write(D/'batch_status_final.json',dict(batch=37,status='selected_V3_actual_source_interleave_completed',
        actual_ROS_runs=1,Native_cases=29,raw_copy_negative_cases=8,all_owned_groups_empty=True,
        normal_shadow_driver_passed=True,all_prior_failures_and_dirty_preserved=True,
        next='ordinary unpaused supervision, final role combination then B4 policy/domain closure',
        stage_qualified=False,execute_qualified=False,research_conclusion=False,MPC_delivery_authority='delivery_verification.json'))
    files=[];dirs=[]
    for p in sorted(D.rglob('*')):
        need(not p.is_symlink(),'archive source links prohibited');rel=str(p.relative_to(D))
        if p.is_dir():dirs.append(rel)
        else:
            need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'already sealed')
            files.append(dict(relative_path=rel,**pin(p)))
    write(D/'archive_inventory_v1.json',dict(schema='SchemeA-create-only-local-archive/v1',files=files,
        directories=dirs,inventory_excludes_itself=True,optional_postseal_files=['delivery_verification.json'],
        created_monotonic_ns=time.monotonic_ns(),stage_qualified=False,execute_qualified=False,research_conclusion=False))
    print(json.dumps(dict(passed=True,sealed_files_including_inventory=len(files)+1,
        sealed_bytes_including_inventory=sum(x['bytes'] for x in files)+(D/'archive_inventory_v1.json').stat().st_size,
        inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'])))
if __name__=='__main__':main()
