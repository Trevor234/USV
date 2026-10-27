"""Seal one current final V1 fault combination without stage promotion."""
import hashlib,json,time
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parent/'scheme_A_owned_business_start_20261020_39'
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def need(v,w):
    if not v:raise ValueError(w)
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def main():
    proofs=[load(D/'preflight'/name) for name in ['protection_initial_v1.json','protection_final_v1.json']]
    for p in proofs:
        need(p['passed'] and p['protection']['full_local_current_byte_sha_recheck'] and p['protection']['unique_raw_files_reread']==47191
            and p['protection']['logical_bytes_streamed']==5931009394,'full old byte protection')
        need(p['workspace_after']['staged_all_diff_bytes']==0 and p['protection']['business_diff_bytes']==151961
            and p['protection']['business_diff_sha256']=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5','original workspace preservation')
    b=load(P/'build/business_observer_attempt01/result.json');need(b['passed'] and b['Native_cases']==38,'parent current native evidence')
    for n in ['build_manifest_current.json','source_bundles_current.json','fault_self_close_v1.py','business_start_v1.py','runtime/owned_process_supervisor.py']:
        need((D/'author'/n).read_bytes()==(P/'author'/n).read_bytes(),'unchanged critical input:'+n)
    lock=load(D/'preflight/prerun_source_lock_v1.json');need(lock['count']==len(lock['files'])==2030,'source lock scope')
    for p,f in lock['files'].items():need(pin(p)==f,'locked input changed:'+p)
    a=load(D/'postrun/current_V1_actual_audit_v1.json');need(a['passed'] and a['actual_new_runs']==1 and a['new_driver_executed_live'],'independent current actual audit')
    need(a['input_sha256_before']==a['input_sha256_after'] and len(a['input_sha256_after'])==2145,'independent audit raw stability')
    for p,f in a['input_sha256_after'].items():need(pin(p)==f,'audited input changed:'+p)
    case=a['cases'][0];need(len(case['sections'])==3 and all(v['passed'] for v in case['sections'].values()),'all three independent sections')
    n=load(D/'verification/actual_V1_negatives_v1.json');need(n['passed'] and len(n['cases'])==14 and all(v['rejected'] for v in n['cases']) and n['actual_raw_unchanged'],'14 actual raw copy rejections')
    R=D/'author/runs/final_V1_01';r=load(R/'result.json');launch=load(D/'postrun/launch_final_V1_01_v1.json')
    need(launch['returncode']==0 and launch['inputs_unchanged'] and not launch['external_timeout_triggered'] and launch['elapsed_ns']<45000000000,'one finite launch')
    need(r['V1_fault_case_completed'] and r['V1_fault_observed'] and r['business_start_completed'] and r['Worker_normal_Source_qualified']
        and r['passed'] is False and r['normal_business_qualified'] is False and r['normal_close_qualified'] is False
        and not r.get('error') and not r['close_errors'] and not r['ledger_failed'],'fault profile remains separate')
    need(r['owned_role_returncodes']==dict(observer=2,worker=0,publisher=0,synthetic_source=0,recorder=0)
        and r['cleanup_complete'] and r['cleanup_within_budget'] and r['close_elapsed_ns']<15000000000,'finite exact cleanup')
    need(all(v['cleanup_complete'] and not v['remaining_members'] and not v['unexpected_descendants'] for v in r['cleanup'].values()),'five owned groups empty')
    need(not load(D/'postrun/final_process_observation_v1.json')['selected_research_processes'],'no selected readable residual role')
    ledger=[json.loads(line) for line in (R/'owned_process_ledger.jsonl').read_bytes().splitlines()]
    signals=[dict(name=x['name'],signal=x['signal']) for x in ledger if x['type']=='signal']
    need(signals==[dict(name=k,signal=2) for k in ['publisher','worker','synthetic_source','recorder']],'actual ordinary signals and natural Observer exit')
    src=[json.loads(line) for line in (R/'observer/source.jsonl').read_bytes().splitlines()];st=src[-1]
    need(st['type']=='source_summary' and st['normal_source_complete'] is False and st['dropped']==1
        and st['generated']==1170 and st['emitted']==1169,'actual intentional failed Source counters')
    gate=case['sections']['business_start_then_original_tick']['details'];strict=case['sections']['strict_actual_accepted_Applied_authenticated_ack_before_arm']['details'];close=case['sections']['current_fault_profile_owned_close_and_Stored_zero']['details']
    need(gate['prestart_decisions']==gate['prestart_jobs']==0 and gate['first_phase_publish_delay_ns']<150000000,'actual original gate budget')
    need(strict['actual_accepted_prefix_joins'] and all(j['Applied_before_arm_ns']>0 for j in strict['actual_accepted_prefix_joins']),'strict prefix ordering')
    need(close['zero_API_both_success'] and close['zero_Fixture_owner_GID_verified'] and close['zero_full_Stored_value_verified']
        and close['independent_SQL_metadata_verified'] and close['normal_close_qualified'] is False,'independent fault command closure')
    need(load(D/'evidence/protection_relative_path_rejection_v1.json')['passed'] is False,'invocation error retained')
    runs=list((D/'author/runs').iterdir());need(len(runs)==1 and runs[0]==R,'exact actual run population')
    files=[dict(relative_path=str(p.relative_to(R)),**pin(p)) for p in sorted(R.rglob('*')) if p.is_file()]
    dump(D/'postrun/raw_run_freeze_v1.json',dict(root=str(R),files=files,count=len(files),bytes=sum(f['bytes'] for f in files),directories=[str(p.relative_to(R)) for p in sorted(R.rglob('*')) if p.is_dir()],all_original_raw_retained=True))
    dump(D/'postrun/postrun_retro_v1.json',dict(primary_mechanism='insufficient_evidence resolved for one current gated V1 combination',
        selected_hypothesis_passed=True,same_V1_rerun_justified=False,next='ordinary receipt lease immediate stop and necessary current fresh-identity recovery then B4 closure',
        next_confidence='medium',next_impact='high',next_cost='low',next_risk='low',next_stop_condition='any trigger identity causal dispatch cleanup or storage failure',
        experiences=['prepare before business','strict actual Applied before arm','failed Source is not normal','raw failure retention','command evidence separate from plant'],
        EDA_route_STA_WNS_PPA='not applicable',stage_qualified=False,research_conclusion=False))
    qa=dict(schema='current-gated-V1-real-fault-final-QA/v1',passed=True,passed_scope='one current gated shadow V1 strict actual fault, owned fault-profile cleanup and independent Stored shutdown command',
        actual_ROS_runs=1,CXX_builds=0,all_five_parent39_registered_ELFs_reused=True,Native_cases_reused=38,Native_cases_executed_this_batch=0,
        actual_raw_copy_negatives=14,prerun_inputs_unchanged=2030,audit_inputs_unchanged=2145,
        audit_pin=pin(D/'postrun/current_V1_actual_audit_v1.json'),metrics=dict(gate=gate,strict=strict,close=close),
        exact_role_returncodes=r['owned_role_returncodes'],actual_signals=signals,Observer_natural_fault_exit=True,
        Observer_normal_Source_complete=False,Worker_normal_Source_complete=True,all_five_owned_groups_empty=True,
        old_local_paths_rechecked=47191,old_local_bytes_rechecked=5931009394,
        old_failures_preserved=True,protection_invocation_path_error_retained=True,Stored_messages=close['Stored_messages'],
        Recorder_builtin_stream_accounting_claim=False,independent_SQL_metadata_verified=True,
        current_selected_V1_case_passed=True,current_ordinary_lease_qualified=False,current_full_fresh_identity_recovery_qualified=False,
        all_terminal_causes_qualified=False,B4_all_eight_groups_qualified=False,normal_business_qualified=False,
        normal_close_qualified=False,stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False,
        MPC_delivery_pending_at_QA=True,delivery_authority='delivery_verification.json')
    dump(D/'postrun/final_QA_v1.json',qa)
    dump(D/'batch_status_final.json',dict(batch=40,status='current_gated_V1_strict_actual_fault_and_owned_self_close_completed',
        actual_ROS_runs=1,CXX_builds=0,Native_cases_reused=38,actual_raw_negatives=14,current_selected_V1_case_passed=True,
        all_owned_groups_empty=True,normal_business_qualified=False,stage_qualified=False,execute_qualified=False,research_conclusion=False,
        next='ordinary receipt lease immediate stop and necessary new-identity recovery then B4',MPC_delivery_authority='delivery_verification.json'))
    members=[];directories=[]
    for p in sorted(D.rglob('*')):
        need(not p.is_symlink(),'no archive symlinks');rel=str(p.relative_to(D))
        if p.is_dir():directories.append(rel)
        else:
            need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'already sealed');members.append(dict(relative_path=rel,**pin(p)))
    dump(D/'archive_inventory_v1.json',dict(schema='SchemeA-create-only-local-archive/v1',files=members,directories=directories,
        inventory_excludes_itself=True,optional_postseal_files=['delivery_verification.json'],created_monotonic_ns=time.monotonic_ns(),
        stage_qualified=False,execute_qualified=False,research_conclusion=False))
    print(json.dumps(dict(passed=True,sealed_files_including_inventory=len(members)+1,
        sealed_bytes_including_inventory=sum(m['bytes'] for m in members)+(D/'archive_inventory_v1.json').stat().st_size,
        inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],current_selected_V1_case_passed=True)))
if __name__=='__main__':main()
