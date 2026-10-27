"""Seal one exact post-lease recovery, original normal tail and current registry evidence."""
from pathlib import Path
import hashlib,json,time
D=Path(__file__).resolve().parent;P=D.parent/'scheme_A_ordinary_lease_20261020_41'
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
 b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def need(v,w):
 if not v:raise ValueError(w)
def dump(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
 for n in ['protection_initial_v1.json','protection_final_v1.json']:
  x=load(D/'preflight'/n);need(x['passed'] and x['protection']['full_local_current_byte_sha_recheck']
   and x['protection']['unique_raw_files_reread']==47938 and x['protection']['logical_bytes_streamed']==6057276901,'full old local byte protection')
  need(x['workspace_after']['staged_all_diff_bytes']==0 and x['protection']['business_diff_bytes']==151961
   and x['protection']['business_diff_sha256']=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5','old dirty and staging protection')
 for n in ['build_manifest_current.json','source_bundles_current.json','business_start_v1.py','owned_auth.py','owned_release.py','runtime/owned_process_supervisor.py']:
  need((D/'author'/n).read_bytes()==(P/'author'/n).read_bytes(),'unchanged critical lineage:'+n)
 need(load(D/'preflight/source_change_review_v1.json')['original_normal_close_branch_byte_equal'],'original normal close branch')
 lock=load(D/'preflight/prerun_source_lock_v1.json');need(len(lock['files'])==lock['count']==2286,'actual source lock population')
 for p,f in lock['files'].items():need(pin(p)==f,'locked input changed:'+p)
 cli=load(D/'verification/driver_CLI_v1.json');need(cli['passed'] and cli['driver_sha256']==pin(D/'author/prepare_pair_wakeup_v1.py')['sha256'],'actual CLI driver version')
 entry=load(D/'verification/fresh_entry_components_v1.json');need(entry['passed'] and entry['negative_count']==8
  and entry['helper_pin']==pin(D/'author/fresh_recovery_v1.py') and entry['seeded_identity_context_only'],'entry seeded component scope')
 old=load(D/'postrun/fresh_recovery_actual_audit_v1.json');need(old['passed'] is False and old['sections']['two_healthy_distinct_jobs']['passed'] is False
  and old['sections']['two_healthy_distinct_jobs']['error']=="ValueError('unchanged_absolute150ms_ready_deadline')"
  and all(v['passed'] for k,v in old['sections'].items() if k!='two_healthy_distinct_jobs'),'original checker rejection preserved')
 fix=load(D/'verification/checker_correction_v1.json');need(fix['passed'] and fix['actual_ROS_reruns']==0 and fix['original_deadline_or_tolerance_changed'] is False
  and fix['original_failed_audit']==pin(D/'postrun/fresh_recovery_actual_audit_v1.json'),'versioned correction provenance')
 for name,f in fix['new_files'].items():need(pin(D/name)==f,'corrected checker version changed:'+name)
 need(load(D/'verification/deadline_registered_source_binding_v1.json')['passed'],'registered compiled source deadline binding')
 a_path=D/'postrun/fresh_recovery_actual_audit_v2.json';a=load(a_path)
 need(a['passed'] and a['component_passed'] and a['current_selected_post_lease_recovery_case_qualified']
  and len(a['sections'])==6 and all(r['passed'] for r in a['sections'].values()),'six final independent actual sections')
 for obj,count in [(old,2409),(a,2411)]:
  need(obj['input_sha256_before']==obj['input_sha256_after'] and len(obj['input_sha256_after'])==count,'both audit input sets stable')
  for p,f in obj['input_sha256_after'].items():need(pin(p)==f,'audited input changed:'+p)
 n=load(D/'verification/actual_fresh_negatives_v2.json');need(n['passed'] and n['actual_raw_unchanged'] and len(n['cases'])==14 and all(c['rejected'] for c in n['cases']),'14 actual raw rejection cases')
 R=D/'author/runs/fresh_after_lease_01';r=load(R/'result.json');launch=load(D/'postrun/launch_fresh_after_lease_01_v1.json')
 need(launch['returncode']==0 and launch['inputs_unchanged'] and not launch['external_timeout_triggered'] and launch['elapsed_ns']<45000000000,'exact finite actual launch')
 need(r['fresh_recovery_case_completed'] and r['passed'] and r['Worker_normal_Source_qualified'] and r['business_start_completed']
  and r['normal_business_qualified'] is False and r['V2_case']=='none' and not r.get('error') and not r['close_errors']
  and r['evidence_qualification_clean'] and not r['ledger_failed'],'healthy fixture and qualification scope')
 need(r['owned_role_returncodes']=={k:0 for k in ['observer','worker','publisher','synthetic_source','recorder']}
  and r['cleanup_complete'] and r['cleanup_within_budget'] and r['close_elapsed_ns']<=15000000000,'five finite clean resources')
 need(all(x['cleanup_complete'] and x['remaining_members']==[] and not x['unexpected_descendants'] for x in r['cleanup'].values()),'all owned groups empty')
 need(list((D/'author/runs').iterdir())==[R],'exact one actual run')
 scan=load(D/'postrun/final_process_observation_host_v1.json');need(not scan['selected_research_processes'],'no readable selected host processes')
 ledger=[json.loads(x) for x in (R/'owned_process_ledger.jsonl').read_bytes().splitlines()]
 signals=[dict(role=x['name'],signal=x['signal']) for x in ledger if x['type']=='signal']
 need(signals==[dict(role=k,signal=2) for k in ['publisher','observer','worker','synthetic_source','recorder']],'original ordinary signal order')
 s=a['sections'];identity=s['fresh_identity_after_exact_lease41']['details'];healthy=s['two_healthy_distinct_jobs']['details'];tail=s['original_normal_tail_and_resource_close']['details'];storage=s['Stored_Fixture_actual_command_chain']['details']
 need(identity['previous_run']=='ordinary_lease_01' and identity['old_all_groups_closed_before_new_prepare']
  and healthy['distinct_healthy_jobs']>=2 and tail['anchor_count']==tail['final_zero_Applied_sequence']==6,'exact recovery and original normal tail')
 need(storage['source_typed_join']['passed'] and storage['Witness_Source_join']['passed'] and storage['independent_SQL_metadata_verified'],'full Source Witness storage data joins')
 freeze=load(D/'postrun/selected_profile_evidence_freeze_v1.json')
 need(freeze['evidence_freeze_completed'] and len(freeze['current_role_pins'])==5 and len(freeze['diagnostic_profile_register'])==4
  and len(freeze['contract']['fields'])==81 and freeze['formal_B5_freeze'] is False,'selected evidence freeze scope')
 need(freeze['input_sha256_before']==freeze['input_sha256_after'],'profile evidence freeze input set')
 for p,f in freeze['input_sha256_before'].items():need(pin(p)==f,'profile evidence changed:'+p)
 reg=load(D/'postrun/B4_current_register_refresh_v1.json');need(reg['passed'] and reg['fields']==81 and reg['roles']==5 and reg['B4_phase_qualified'] is False,'current B4 registry refresh')
 for mode in ['build','check']:
  v=load(D/'verification'/('B4_register_'+mode+'_v1.json'));need(v['passed'] and v['all_inputs_unchanged'] and v['only_register_integrity_checked_not_B4_phase'],'current register integrity:'+mode)
  for p,f in v['input_pins'].items():need(pin(p)=={k:f[k] for k in ['bytes','sha256']},'B4 register input changed:'+p)
 need(pin(D/'implementation/current_B4_applicability_v1.json')==reg['new_register'],'B4 new register byte lock')
 files=[dict(relative_path=str(p.relative_to(R)),**pin(p)) for p in sorted(R.rglob('*')) if p.is_file()]
 dump(D/'postrun/raw_run_freeze_v1.json',dict(root=str(R),files=files,count=len(files),bytes=sum(f['bytes'] for f in files),directories=[str(p.relative_to(R)) for p in sorted(R.rglob('*')) if p.is_dir()],all_original_raw_retained=True))
 dump(D/'postrun/postrun_retro_v1.json',dict(primary_mechanism='insufficient_evidence resolved for exact post-lease41 fresh identity and original normal tail',
  secondary_mechanism='versioned postrun checker origin semantic error corrected from actual registered source without runtime changes',
  selected_hypothesis_passed=True,same_recovery_active_lease_V1_rerun_justified=False,next='B4 source domain and policy review on current81 field register then B5/M0b',
  next_confidence='high',next_impact='high',next_cost='low',next_risk='low',
  stop_condition='one specific consumer source or domain/unknown policy gap needs evidence; do not repeat already confirmed cases',
  EDA_route_STA_WNS_PPA='not applicable',stage_qualified=False,research_conclusion=False))
 dump(D/'postrun/final_QA_v1.json',dict(schema='exact-post-lease-fresh-identity-normal-tail-final-QA/v1',passed=True,
  passed_scope='one current synthetic nominal controlled shadow fresh cold start after lease41, two distinct healthy jobs, complete original normal tail and finite owned resource closure',
  actual_ROS_runs=1,actual_ROS_reruns=0,CXX_builds=0,all_five_registered_ELFs_reused=True,Native_cases_reused=38,Native_cases_executed_this_batch=0,
  new_seeded_identity_negative_cases=8,actual_raw_copy_negative_cases=14,
  prerun_inputs_unchanged=2286,first_audit_inputs_unchanged=2409,final_audit_inputs_unchanged=2411,
  initial_checker_semantic_rejection_retained=True,final_checker_version=2,contract_thresholds_unchanged=True,runtime_code_changed_by_audit_fix=False,
  audit_pin=pin(a_path),metrics=dict(gate=s['business_start_then_original_tick']['details'],identity=identity,healthy=healthy,tail=tail,storage=storage,timing=load(D/'postrun/observed_timing_v1.json')),
  current_selected_post_lease41_recovery_case_passed=True,original_normal_tail_component_verified=True,
  actual_signals=signals,all_five_returncodes_zero=True,all_five_owned_groups_empty=True,Worker_normal_Source_complete=True,
  Observer_normal_Source_complete=True,TERM_KILL_paths_exercised=False,SIGSTOP_used=False,
  host_unreadable_processes=len(scan['unreadable_process_ids']),host_global_process_absence_claimed=False,
  old_local_paths_rechecked=47938,old_local_bytes_rechecked=6057276901,all_old_failures_preserved=True,
  selected_profile_evidence_freeze_completed=True,diagnostic_profiles_registered=4,current_B4_81_field_register_refreshed=True,
  original_B4_register_negatives_reused=13,new_B4_register_negatives_executed=0,
  B4_all_eight_groups_qualified=False,formal_B5_freeze=False,M0b_formal_qualified=False,M4_qualified=False,
  normal_business_qualified=False,stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False,
  MPC_delivery_pending_at_QA=True,delivery_authority='delivery_verification.json'))
 dump(D/'batch_status_final.json',dict(batch=42,status='post_lease41_fresh_identity_healthy_recovery_original_normal_tail_and_current_register_update_completed',
  actual_ROS_runs=1,CXX_builds=0,actual_raw_negatives=14,new_seeded_identity_negatives=8,
  current_selected_recovery_passed=True,original_normal_tail_verified=True,selected_profile_evidence_frozen=True,current_B4_register_updated=True,
  stage_qualified=False,execute_qualified=False,research_conclusion=False,
  next='B4 eight group source finite-domain and policy review then B5/M0b',MPC_delivery_authority='delivery_verification.json'))
 members=[];directories=[]
 for p in sorted(D.rglob('*')):
  need(not p.is_symlink(),'no archive symlinks');rel=str(p.relative_to(D))
  if p.is_dir():directories.append(rel)
  else:
   need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'already sealed');members.append(dict(relative_path=rel,**pin(p)))
 dump(D/'archive_inventory_v1.json',dict(schema='SchemeA-create-only-local-archive/v1',files=members,directories=directories,inventory_excludes_itself=True,
  optional_postseal_files=['delivery_verification.json'],created_monotonic_ns=time.monotonic_ns(),stage_qualified=False,execute_qualified=False,research_conclusion=False))
 print(json.dumps(dict(passed=True,sealed_files_including_inventory=len(members)+1,sealed_bytes_including_inventory=sum(m['bytes'] for m in members)+(D/'archive_inventory_v1.json').stat().st_size,
  inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],selected_recovery_passed=True,current_B4_register_updated=True)))
if __name__=='__main__':main()
