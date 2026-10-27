"""Seal selected B4 engineering review; current formal/runtime permissions remain closed."""
from pathlib import Path
import hashlib,json,time
D=Path(__file__).resolve().parent.parent if Path(__file__).parent.name=='implementation' else Path(__file__).resolve().parent
P=D.parent/'scheme_A_post_lease_fresh_recovery_20261020_42'
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
   and x['protection']['unique_raw_files_reread']==48330 and x['protection']['logical_bytes_streamed']==6121689813,'full old byte protection')
  need(x['workspace_after']['staged_all_diff_bytes']==0 and x['protection']['business_diff_bytes']==151961
   and x['protection']['business_diff_sha256']=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5','original dirty and staging preserved')
 a=load(D/'postrun/review_evidence_audit_v1.json');need(a['passed'] and a['input_count']==187 and a['input_sha256_before']==a['input_sha256_after'],'review evidence audit')
 for p,f in a['input_sha256_after'].items():need(pin(p)==f,'audited input changed:'+p)
 tests=load(D/'verification/review_artifact_checks_v1.json');need(tests['passed'] and tests['negative_count']==18 and all(c['rejected'] for c in tests['cases']),'18 review artifact negatives')
 policy=load(D/'implementation/B4_selected_policy_review_v1.json');need(len(policy['groups'])==8 and len(policy['metadata_bindings'])==5
  and policy['B4_selected_source_policy_review_complete'] and policy['B5_compatibility_implementation_may_proceed']
  and policy['B5_current_assets_formal_freeze_ready'] is False,'selected review decision')
 c=load(P/'author/pair_wakeup_contract_v1.json');need(policy['unchanged_contract_values']==c and policy['old_pending_array_preserved']==c['pending_final_calibration'],'original contract and pending unchanged')
 need(pin(P/'author/pair_wakeup_contract_v1.json')['sha256']=='89caaaf36783463a1e1d789bda41f7f90dc398981ddb4b3b8cd6037114333f72','unchanged actual diagnostic contract')
 facts=load(D/'evidence/current_source_facts_v1.json');need(facts['passed'] and len(facts['snippets'])==26 and len(facts['finite_observations'])==4
  and len(facts['selected_current_Native_test_names'])==38,'actual finite source evidence scope')
 need(facts['input_sha256_before']==facts['input_sha256_after'],'source facts pin stability')
 probe=load(D/'evidence/formal_compatibility_probe_v1.json');need(probe['probe_passed'] and probe['formal_v3_schema_already_implemented']
  and probe['current_diag10_rejected_by_old_python'] and probe['current_native_baseline_fields']==81 and probe['old_python_baseline_fields']==74
  and probe['formal_pre_freeze_owned_Observer_mode_intersection']==[] and probe['B5_formal_freeze_ready'] is False,'reproduced compatibility gaps')
 details=load(D/'evidence/formal_compatibility_details_v1.json');need(len(details['extra_native_fields'])==7 and len(details['changed_shared_baseline_fields'])==3
  and details['native_supported_parameter_profile']!=details['Python_supported_parameter_profile'],'exact spec drift scope')
 gaps=load(D/'evidence/full_command_gap_scope_v1.json');need(gaps['passed'] and gaps['M4_publish_gap_proven'] is False
  and all(min(c['first_to_second_gap_ns'].values())>240000000 for c in gaps['cases']),'startup API gap limitation retained')
 note=load(D/'evidence/metric_scope_notes_v1.json');need(note['passed'] and note['Source_sequences']==[1,2,4] and note['Witness_sequences']==[1,2,3,4]
  and note['Witness_max_adjacent_tick_start_gap_ns']<240000000,'V1 incomplete Source interpretation')
 candidate=load(D/'implementation/current_pre_freeze_candidate_v1.json');meta=load(D/'evidence/pre_freeze_candidate_preparation_v1.json')
 need(len(candidate)==84 and candidate['fault_injection_enabled'] is False and candidate['execute_qualified'] is False
  and candidate['qualification']=='execution_pre_freeze' and candidate['pending_final_calibration']==c['pending_final_calibration']
  and candidate['freeze_evidence_sha256']=='' and meta['candidate_only'] and meta['Native_validator_executed'] is False
  and meta['runtime_executed'] is False,'concrete candidate without qualification promotion')
 need(not any((D/n).exists() for n in ['author','runs','build']),'no runtime author build or run created')
 decision=load(D/'postrun/theory_review_decision_v1.json');need(decision['verdict']=='CONDITIONAL' and decision['B4_selected_source_policy_review_complete']
  and decision['B5_current_assets_formal_freeze_ready'] is False,'scope of conditional next step')
 dump(D/'postrun/final_QA_v1.json',dict(schema='B4-selected-source-domain-policy-review-final-QA/v1',passed=True,
  passed_scope='eight original groups and five metadata semantics in explicitly limited current engineering design; source/evidence/artifact integrity only',
  B4_selected_source_policy_review_complete=True,B4_selected_choices_adopted_for_B5_implementation=True,
  current_runtime_or_contract_modified=False,current_contract_promoted=False,original_pending_array_preserved=True,
  metadata_fields_bound=5,original_groups_reviewed=8,registered_source_excerpts=26,M4_forward_obligations=9,
  review_artifact_negative_cases=18,evidence_inputs_unchanged=187,audit_pin=pin(D/'postrun/review_evidence_audit_v1.json'),
  actual_ROS_runs=0,CXX_builds=0,Native_runs=0,prior_Native_cases_reused=38,prior_actual_profiles_reused=[39,40,41,42],
  old_Python_contract_rejection_preserved=True,Python_baseline_fields=74,Native_baseline_fields=81,native_extra_fields=7,shared_baseline_value_changes=3,
  formal_v3_schema_already_exists=True,current_owned_formal_pre_freeze_mode_intersection_empty=True,business_gate_permission_compatibility_unresolved=True,
  prepared_formal_candidate_fields=84,formal_candidate_only=True,formal_candidate_Native_or_runtime_validation_claimed=False,
  full_command_stream_publish_gap240ms_proven=False,V1_incomplete_Source_not_mislabeled_scheduler_skip=True,
  old_local_paths_rechecked=48330,old_local_bytes_rechecked=6121689813,old_dirty_and_sealed_failures_preserved=True,
  B5_next='synchronized current spec and explicit formal no_output owned entry/prepare matrices',
  B5_current_assets_formal_freeze_ready=False,formal_B5_freeze_completed=False,M0b_formal_qualified=False,M4_qualified=False,
  unrestricted_or_physical_calibration_qualified=False,source_packet_freshness_proven=False,WCET_proven=False,
  stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False,
  MPC_delivery_pending_at_QA=True,delivery_authority='delivery_verification.json'))
 dump(D/'batch_status_final.json',dict(batch=43,status='B4_selected_finite_engineering_source_policy_review_completed_B5_compatibility_gap_identified',
  B4_selected_review_complete=True,metadata_bindings=5,groups_reviewed=8,artifact_rejection_cases=18,
  actual_ROS_runs=0,CXX_builds=0,Native_runs=0,
  next='B5 synchronized spec and explicit formal no_output owned entry/prepare compatibility implementation',
  current_assets_formal_freeze_ready=False,stage_qualified=False,execute_qualified=False,research_conclusion=False,
  MPC_delivery_authority='delivery_verification.json'))
 members=[];directories=[]
 for p in sorted(D.rglob('*')):
  need(not p.is_symlink(),'no archive symlinks');rel=str(p.relative_to(D))
  if p.is_dir():directories.append(rel)
  else:
   need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'already sealed');members.append(dict(relative_path=rel,**pin(p)))
 dump(D/'archive_inventory_v1.json',dict(schema='SchemeA-create-only-local-archive/v1',files=members,directories=directories,inventory_excludes_itself=True,
  optional_postseal_files=['delivery_verification.json'],created_monotonic_ns=time.monotonic_ns(),stage_qualified=False,execute_qualified=False,research_conclusion=False))
 print(json.dumps(dict(passed=True,sealed_files_including_inventory=len(members)+1,sealed_bytes_including_inventory=sum(x['bytes'] for x in members)+(D/'archive_inventory_v1.json').stat().st_size,
  inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],B4_selected_review_complete=True,B5_current_assets_formal_freeze_ready=False)))
if __name__=='__main__':main()
