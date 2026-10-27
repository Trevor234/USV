#!/usr/bin/env python3
"""Produce explicit sources, timelines, fault criteria, and eligibility checks.

No execute observations are invented as prerequisites to original M0b. The new
entry is an offline policy core; actual owned execute wiring remains M4.
"""
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
B = D.parent
F = D / 'freeze'


def load(p):
    return json.loads(p.read_bytes())


def pin(p):
    data = p.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def emit(p, obj):
    with p.open('x') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False);f.write('\n')


def main():
    d43 = B / 'scheme_A_B4_finite_scope_review_20261020_43'
    d46 = B / 'scheme_A_current_normal_source_20261020_46'
    reviewed = load(d43 / 'implementation/B4_selected_policy_review_v1.json')
    ledger = load(d46 / 'implementation/B5_candidate_evidence_ledger_v1.json')
    spec = load(D / 'implementation/current_contract_spec_v1.json')
    pre = load(D / 'implementation/owned_pre_freeze_contract_v1.json')
    parity = load(D / 'verification/profile_parity_v1.json')
    entry = load(D / 'verification/entry_policy_cases_v2.json')
    reproduction = load(D / 'verification/reproduce_generation_v1.json')
    builds = [load(D / ('build/components_attempt0' + str(i) + '/build_manifest_v1.json')) for i in [1, 2]]
    groups = {g['id']: g for g in reviewed['groups']}
    sources = {'schema': 'P1-M0b-parameter-source-table/v1', 'profile_id': spec['target_profile_id'],
               'original_authority': str(B.parent / 'handoffs/scheme_A_20261010_01/source_docs/P1_时间与候选接纳契约及独立执行架构_最小实施计划_2026-10-05.md') + ':§6/§7 M0b',
               'complete_contract_fields': 84, 'nominal_hydro_parameters': 19,
               'all_non_flag_numeric_values': {k: v for k, v in pre.items() if type(v) in (int, float) or type(v) is list or k == 'hydro'},
               'pending8_selected': {k: dict(g, selected_engineering_design_frozen=True, physical_calibration_qualified=False) for k, g in groups.items()},
               'metadata_bindings': reviewed['metadata_bindings'],
               'current_normal_calibration': ledger['current_normal_source'],
               'assumptions': ledger['selected_engineering_assumptions'],
               'bootstrap_design_basis': {'origin': 'prepare grant, zero immediately then absolute T=200ms, first pair start <=T; values reused from existing T/gap/jitter/span design',
                                          'tests': str(D / 'verification/entry_policy_cases_v2.json'),
                                          'current_legacy_full_startup_gap240ms_passed': False,
                                          'actual_owned_bootstrap_M4_confirmation': False,
                                          'rate_before_first_actual_success': 'unknown; no plant-zero proof'},
               'numeric_tuning_performed': False, 'first_execute_observation_is_prerequisite': False,
               'complete_new_no_output_business_run_is_prerequisite': False,
               'general_1_2_or_turn_or_mixed_or_plant_or_WCET_proven': False}
    emit(F / 'parameter_sources_v1.json', sources)
    matrix_groups = [
        ('compatibility_input', ['F5 source/reference/mapping qualified old regression and logging off/on', 'new target-reference independent fixture, no implicit physical writer'], 'same reused core; exact declared future-reference semantics; no hidden writer'),
        ('time_boundaries', ['50/150/250/400ms; ready before/equal/after deadline', 'early ready, wrong target, delayed tick'], 'complete absolute 150ms cutoff equality allowed, strict-after cutoff; target remains origin+200ms; no deadline extension or late activation'),
        ('native_block_and_delivery', ['worker held at native boundary until independent release', 'separate result delivery delay/drop'], 'multiple complete regulator ticks while worker blocked; active/pending/ready bounded; one backend only; delivery delay not called native block'),
        ('candidate_identity_shape', ['failed, invalid shape, NaN, duplicate, old/reordered IDs', 'foreign producer/boot/version'], 'invalid selection or normal output count=0; each candidate consumed at most once; bounded slots and explicit reason'),
        ('task_reference', ['clear/single point before freeze, clear/replacement during solve', 'same content republish, path/profile mismatch, ordinary new odom'], 'semantic task generation only; old task rejected before activation; new odom does not unconditionally starve'),
        ('state_clock', ['source stale/future, mixed skew, activation mismatch', 'pause/resume/reset/jump and RTF band'], 'separate receipt/sim ages, IMU only if mixed; selected tolerances; epoch/schedule invalidation; no cross-domain subtraction or resurrection'),
        ('anchor_fallback', ['mid-interval change/same-value republish/different API intervals/missing history', 'five misses, HOLD equality/after, invalid bypass, unknown side'], 'actual per-side history; H=600ms from last accepted activation; rho80 each actual interval; missing anchor unavailable; no instant-zero rate fiction'),
        ('publication_exit', ['clear/shutdown before/after submit; left/right partial API outcomes', 'worker death, active watchdog, capability lease and cleanup failed'], 'sole new owner; both calls attempted; successful side irreversible; unknown failed side; finite cleanup attempt/no restart until old group empty; request/API/process/plant flags separate'),
        ('actual_source_recording', ['new isolated normal straight0.05 then controlled faults', 'log queue pressure, source/emit/bag counts and before/after assets'], 'normal source/Witness/raw/Stored accounting complete, full startup/business/fallback/shutdown API stream; fault flags follow declared exception, extra unexplained loss/error/overrun fails'),
    ]
    matrix = {'schema': 'P1-M4-predeclared-fault-matrix/v1', 'profile_id': spec['target_profile_id'],
              'derived_from_original_section8': True, 'registered_before_M4': True,
              'groups': [{'id': name, 'required_cases': cases, 'acceptance': acceptance, 'current_M4_qualified': False} for name, cases, acceptance in matrix_groups],
              'normal_limits_from_contract': {k: pre[k] for k in ['T_ns', 'deadline_ns', 'tick_jitter_ns', 'publish_gap_ns', 'publish_budget_ns', 'hold_ns', 'rho_n_s', 'activation_tolerance', 'odom_age_ns', 'imu_age_ns', 'mixed_skew_ns', 'clock_age_ns', 'clock_pause_confirm_ns', 'rtf_low', 'rtf_high', 'active_watchdog_ns', 'worker_capability_receipt_timeout_ns', 'worker_grace_ns', 'term_grace_ns', 'kill_postcheck_ns', 'shutdown_grace_ns']},
              'normal_criteria': {'full_stream_gap240ms': True, 'complete_source_and_recording': True, 'unexplained_drops': 0, 'invalid_normal_actions': 0, 'both_output_writers_same_owned_regulator': True},
              'fault_exception_policy': {'partial_output': ['normal_contract_complete=false', 'failed-side anchor unknown; successful side retained', 'rho_available reflects per-side facts'],
                                         'intentional_source_queue_drop': ['normal_contract_complete=false', 'drop count and reason exactly explained; extra loss fails'],
                                         'forced_worker_exit': ['worker_session_complete follows actual false/incomplete facts', 'cleanup_failed forbids restart'],
                                         'capability_receipt_timeout': ['terminal, no new job; current valid callback receipt only', 'no packet sequence/sendtime freshness claim']},
              'scope_controls': ['new run and old physical owner exited', 'sole regulator output only in isolated owned nominal fixture; no Gazebo/plant/hardware', 'normal first, then controlled fault cases', 'no threshold/RTI/cost/model tuning in a confirmation run', 'every new runtime/source/bin diff gets affected regression', 'physical production release remains closed'],
              'finite_next_normal_budget': {'normal_source_window_ns': 20000000000, 'whole_driver_wall_timeout_ns': 45000000000, 'cleanup_phase_bounds_from_contract': True, 'automatic_retries': 0},
              'future_fault_runs_require_case_specific_registration': True,
              'current_M4_runs': 0, 'P1_qualified': False}
    emit(F / 'M4_fault_matrix_v1.json', matrix)
    timelines = {'schema': 'P1-M0b-normal-late-clear-timelines/v1', 'units': 'CLOCK_MONOTONIC ns; sim uses separate source contract',
                 'normal': [{'event': 'freeze and submit origin', 'time_ns': 1000000000}, {'event': 'ready validation completed at equality, allowed', 'time_ns': 1150000000}, {'event': 'strictly after deadline cutoff', 'time_ns': 1150000001}, {'event': 'activation target with unchanged identity/state/anchor', 'time_ns': 1200000000}],
                 'late': [{'event': 'origin', 'time_ns': 1000000000}, {'event': 'ready completion after cutoff, rejected', 'time_ns': 1150000001}, {'event': 'no candidate; HOLD/ramp from actual side anchors, no deadline extension', 'time_ns': 1200000000}],
                 'clear': [{'event': 'old task ready before deadline', 'time_ns': 1140000000, 'task_generation': 7}, {'event': 'clear invalidates task before activation', 'time_ns': 1190000000, 'task_generation': 8}, {'event': 'old task rejected, invalid bypasses HOLD', 'time_ns': 1200000000, 'task_generation': 8}],
                 'truth_table': [{'condition': name, 'business_admission': result} for name, result in [('all identity/version/time/anchor/state/resource checks valid', True), ('at deadline and validation complete', True), ('ready completes after deadline', False), ('wrong target/old task/model/config/schedule/boot/producer', False), ('failed/invalid/nonfinite candidate', False), ('unknown/changed/incomplete per-side history', False), ('activation beyond tolerance/source stale/future/clock invalid', False), ('sole owner/bootstrap live gate incomplete', False)]],
                 'not_a_live_execute_observation': True}
    emit(F / 'timelines_and_truth_table_v1.json', timelines)
    checks = {
        'original_M0b_allows_shadow_calibration_without_first_execute': ledger['M0b_does_not_require_a_new_full_no_output_business_run'] is True,
        'current_normal20s_selected_component_complete': ledger['current_controlled_source_normal20s_component_passed'] is True and ledger['current_normal_source']['source_span_ns'] >= 20000000000 and ledger['current_normal_source']['jobs'] == 101,
        'selected_B4_eight_policy_sources_complete': len(groups) == 8 and all(g['review_status'] == 'complete_for_selected_engineering_design' for g in groups.values()),
        'all_pending8_parameter_source_ids_present': set(groups) == set(spec['legacy_baseline']['pending_final_calibration']),
        'all_84_fields_and_19_hydro_present': len(pre) == 84 and len(pre['hydro']) == 19,
        'new_profile_only_four_declared_string_fields_changed': set(load(D / 'implementation/profile_field_diff_v1.json')['changed_fields']) == {'baseline_input', 'preparation_retry_policy', 'propagation_semantics', 'supported_parameter_profile'},
        'old_385_raw_cases_retained_and_passed': parity['legacy_cases'] == 385 and all(r['passed'] for r in parity['cases'] if r['legacy']),
        'new_256_profile_cases_and_92_entry_cases_passed': parity['passed'] and parity['new_cases'] == 256 and entry['passed'] and entry['case_count'] == 92,
        'same_source_generation_five_exact_outputs': reproduction['passed'] and len(reproduction['outputs']) == 5,
        'both_offline_builds_and_selected_v2_entry_succeeded': all(x['passed'] for x in builds),
        'formal_prepare45_already_closed': load(B / 'scheme_A_owned_formal_prepare_20261020_45/postrun/final_QA_v1.json')['owned_formal_prepare_close_component_passed'] is True,
        'fault40_41_42_case_specific_evidence_retained': all(load(B / name / 'postrun/final_QA_v1.json')['passed'] for name in ['scheme_A_final_V1_gate_confirmation_20261020_40', 'scheme_A_ordinary_lease_20261020_41', 'scheme_A_post_lease_fresh_recovery_20261020_42']),
        'first_failed_entry_test_and_implementation_v1_retained': not load(D / 'verification/entry_policy_cases_v1.json')['passed'] and len(load(D / 'evidence/entry_policy_attempt01_failure_v1.json')['old_attempts_preserved']) == 6,
        'startup_gap_failure_not_relabelled': ledger['full_API_stream_observations']['left']['full_stream_gap240ms_passed'] is False,
        'M4_obligations_separate_and_unqualified': len(ledger['M4_forward_confirmation_stays_separate']) == 9 and all(x['current_qualified'] is False for x in ledger['M4_forward_confirmation_stays_separate']),
        'physical_release_stays_false': spec['physical_execute_release_enabled'] is False,
        'new_schema_or_control_numeric_tuning_absent': load(D / 'implementation/profile_field_diff_v1.json')['numeric_parameters_changed'] is False,
        'old_workspace_and_archives_preserved_before_work': load(D / 'preflight/workspace_initial_v1.json')['passed'] is True,
        'matrix_and_timelines_registered_before_M4': matrix['registered_before_M4'] is True and matrix['current_M4_runs'] == 0,
    }
    inputs = [D / 'verification/profile_parity_v1.json', D / 'verification/entry_policy_cases_v1.json', D / 'verification/entry_policy_cases_v2.json', D / 'verification/reproduce_generation_v1.json', d43 / 'implementation/B4_selected_policy_review_v1.json', d46 / 'implementation/B5_candidate_evidence_ledger_v1.json', Path(__file__).resolve()]
    conditions = {'schema': 'P1-M0b-selected-engineering-freeze-conditions/v1', 'passed': all(checks.values()), 'checks': checks,
                  'input_sha256': {str(p): pin(p) for p in inputs}, 'M4_qualified': False, 'physical_execute_release_enabled': False,
                  'scope': 'eligible for immutable engineering contract/policy submission; actual sealed index and package still require independent verification', 'research_conclusion': False}
    emit(F / 'freeze_conditions_v1.json', conditions)
    for source, dest in [(D / 'implementation/owned_execution_policy_v1.json', F / 'owned_execution_policy_v1.json'), (D / 'implementation/current_contract_spec_v1.json', F / 'p1_contract_spec_v1.json')]:
        with dest.open('xb') as f:f.write(source.read_bytes())
    print(json.dumps({'passed': conditions['passed'], 'checks': len(checks), 'M4_groups': len(matrix_groups), 'parameter_groups': len(groups)}))
    return 0 if conditions['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
