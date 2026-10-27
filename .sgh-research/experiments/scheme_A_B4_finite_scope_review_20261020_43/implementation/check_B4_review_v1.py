"""Strict review artifact checker: source pinning, exact choices and no claim promotion."""
from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent.parent;P=D.parent/'scheme_A_post_lease_fresh_recovery_20261020_42'
META={
 'output_topics':{'output_publisher_creation','output_API_calls','shadow_entry_mode','shadow_publish_early_return'},
 'propagation_semantics':{'propagation_call','nominal_RK4_history','mixed_callbacks','activation_history_selection','causal_selection'},
 'source_age_semantics':{'source_age_comparison','source_eligibility','clock_window','clock_epoch_invalidation'},
 'worker_capability_lease_policy':{'worker_callback_authentication','capability_validation_and_renewal','capability_latch','terminal_transition'},
 'worker_capability_source_freshness_available':{'capability_wire_fields','worker_callback_authentication','capability_validation_and_renewal','capability_latch'}}
GROUP_FIELDS={
 'rho_n_s':{'rho_n_s','backend_rate_n_s','command_min_n','command_max_n','map_scale'},
 'hold_ns':{'hold_ns','rho_n_s','shutdown_grace_ns'},
 'activation_tolerance':{'activation_tolerance','activation_sensor_history_capacity','activation_validation_attempts','activation_state_policy'},
 'source ages':{'odom_age_ns','imu_age_ns','mixed_skew_ns','clock_age_ns','odom_sim_lag_ns','imu_sim_lag_ns','source_future_slack_ns','target_sim_slack_ns'},
 'RTF and pause':{'rtf_low','rtf_high','clock_age_ns','clock_pause_confirm_ns','target_sim_slack_ns'},
 'jitter/gap/publish':{'T_ns','deadline_ns','tick_jitter_ns','publish_gap_ns','publish_budget_ns'},
 'watchdog and cleanup':{'active_watchdog_ns','worker_grace_ns','term_grace_ns','kill_postcheck_ns','shutdown_grace_ns','recording_ready_timeout_ns'},
 'worker capability validated callback receipt lease; no source packet sequence/send time':{'worker_capability_receipt_timeout_ns','worker_capability_lease_policy','worker_capability_source_freshness_available'}}
OBLIGATIONS={'M4-own-outputs','M4-per-side-anchor','M4-partial-API','M4-hold-ramp-five-misses','M4-shutdown-accounting','M4-bootstrap-gap','M4-timing-API','M4-source-domain','M4-qualification-regression'}
NONCLAIMS={'source_packet_freshness_proven','RTF_average_is_instantaneous_hard_bound','receipt_and_source_age_are_equivalent','hold_lifetime_refreshed_by_republication','unknown_anchor_authorizes_rate_claim','full_command_stream_gap240ms_qualified','Observer_actual_publication_branch_exercised','mixed_general_domain_qualified','new_short_runs_form_one_20s_domain_trace','current_assets_formal_freeze_ready','current_physical_calibration_qualified'}
def need(v,w):
 if not v:raise ValueError(w)
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def pin(p):
 b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def check(review,facts,register,probe,gaps):
 need(review['schema']=='B4-selected-finite-engineering-policy-review/v1','review_schema')
 c=facts['contract_fields'];need(canon(review['unchanged_contract_values'])==canon(c) and len(c)==81,'all81_choices_unchanged_and_typed')
 need(review['contract_sha256']==register['contract_sha256'],'exact_current_contract_SHA')
 need(review['old_pending_array_preserved']==c['pending_final_calibration']==register['pending_original_groups'],'original_pending_not_silently_erased')
 domain=review['selected_domain'];need(domain['reference_speed_m_s']==.05 and type(domain['reference_speed_m_s']) in (float,int)
  and domain['current_modes']==['shadow'] and domain['plant_connected'] is False and domain['real_actuator_control'] is False
  and type(domain['current_Observer_physical_publishers']) is int and domain['current_Observer_physical_publishers']==0,'selected_domain_exact')
 for k in ['qualified_general_mixed','qualified_turning','full_velocity_gate_domain_0_to_1_2_m_s_proven','continuous_20s_trace_claimed','continuous_DDS_graph_exclusivity_proven','sensor_clock_hard_error_bound_proven','plant_input_or_safety_error_bound_proven']:
  need(domain[k] is False,'unsupported_domain_promotion:'+k)
 need(set(review['structured_non_claims'])==NONCLAIMS and all(v is False for v in review['structured_non_claims'].values()),'explicit_nonclaims_cannot_be_promoted')
 need({x['id'] for x in review['assumptions']}=={'trusted_source_graph','clock_1_to_1_engineering','nominal_point_model','bounded_local_scheduling'},'all_environment_assumptions_required')
 metadata=review['metadata_bindings'];need(len(metadata)==5 and {x['key'] for x in metadata}==set(META),'exact_five_metadata_bindings')
 for row in metadata:
  k=row['key'];need(canon(row['value'])==canon(c[k]),'metadata_value_or_type:'+k)
  need(set(row['source_refs'])==META[k] and row['resolved_for_selected_review'] is True
   and row['literal_key_read_required'] is False and row['explanation'] and row['limits'],'metadata_consumer_mapping:'+k)
 need(review['metadata_bindings'][-1]['key']=='worker_capability_source_freshness_available'
  and review['metadata_bindings'][-1]['value'] is False,'receipt_lease_not_source_freshness')
 groups=review['groups'];need(len(groups)==8 and [g['id'] for g in groups]==register['pending_original_groups'],'all_eight_original_groups_once_in_order')
 for g in groups:
  need(set(g['contract_values'])==GROUP_FIELDS[g['id']],'exact_group_field_population:'+g['id'])
  need(all(canon(v)==canon(c[k]) for k,v in g['contract_values'].items()),'exact_group_values:'+g['id'])
  need(g['review_status']=='complete_for_selected_engineering_design' and g['physical_calibration_claimed'] is False
   and g['whole_runtime_domain_proven'] is False,'group_scope:'+g['id'])
  need(g['selection_reason'] and g['boundary_semantics'] and g['selected_domain'] and g['evidence_basis']
   and g['out_of_domain_handling'] and g['M4_obligations'],'group_reason_domain_refusal_obligations:'+g['id'])
  need(set(g['M4_obligations']).issubset(OBLIGATIONS),'known_M4_obligation_ids')
 refs={x for row in metadata for x in row['source_refs']}|{x for g in groups for x in g['source_refs']}
 need(refs<=facts['snippets'].keys(),'all_sources_exist')
 for key in refs:
  s=facts['snippets'][key];need(pin(s['path'])==s['source_pin']==s['authority']['expected'],'current_compilation_source_pin:'+key)
  lines=Path(s['path']).read_text().splitlines();need(s['end_line']-s['start_line']+1==len(s['lines']),'source_excerpt_population')
  for row in s['lines']:
   actual=lines[row['line']-1];need(actual==row['text'] and hashlib.sha256(actual.encode()).hexdigest()==row['sha256'],'source_line_binding:'+key)
 o=review['M4_forward_obligations'];need(len(o)==9 and {x['id'] for x in o}==OBLIGATIONS
  and all(x['current_qualified'] is False and x['requirement'] for x in o),'M4_forward_obligations_not_erased_or_qualified')
 need(probe['probe_passed'] and probe['formal_v3_schema_already_implemented'] and probe['current_diag10_rejected_by_old_python']
  and probe['current_native_baseline_fields']==81 and probe['old_python_baseline_fields']==74
  and probe['formal_pre_freeze_owned_Observer_mode_intersection']==[]
  and probe['authenticated_business_gate_requires_fault_permission_true'] and probe['formal_contract_requires_fault_permission_false'],'real_formal_compatibility_gap_preserved')
 need(gaps['passed'] and gaps['M4_publish_gap_proven'] is False and all(x['claim_all_Applied_gap_qualified'] is False
  and min(x['first_to_second_gap_ns'].values())>240000000 for x in gaps['cases']),'full_startup_API_gap_limit_preserved')
 need(review['B4_selected_source_policy_review_complete'] is True and review['B4_selected_choices_adopted_for_B5_implementation'] is True
  and review['B5_compatibility_implementation_may_proceed'] is True,'selected_review_decision_explicit')
 for k in ['current_contract_promoted','B5_current_assets_formal_freeze_ready','B4_unrestricted_or_physical_calibration_qualified','stage_qualified','execute_qualified','research_conclusion']:
  need(review[k] is False,'review_cannot_grant_current_runtime_qualification:'+k)
 return dict(passed=True,source_metadata_bindings=5,original_groups_reviewed=8,pinned_source_bindings=len(refs),M4_forward_obligations=9,
  selected_source_policy_review_complete=True,B5_next='compatibility implementation',B5_current_assets_formal_freeze_ready=False,
  stage_qualified=False,execute_qualified=False,research_conclusion=False)
