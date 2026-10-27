#!/usr/bin/env python3
"""Independent final audit of submitted bytes, real results, and retained scope.

This recomputes qualifications from the actual contract, corpus outcomes,
artifact inventory, old calibration review, and preservation proofs. It does
not import the profile author, eligibility author, or freeze assembler.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D / 'implementation/python'))
import freeze_binding_v1 as binding
import p1_full_contract as full


def pin(p):
    return binding.stable_read(p.resolve(strict=True), binding.MAX_FILE_BYTES)


def main():
    paths = [D / name for name in ['freeze/freeze_submission_v1.json', 'freeze/freeze_index_v1.json',
             'freeze/p1_execution_contract_v1.json', 'freeze/freeze_conditions_v1.json', 'freeze/parameter_sources_v1.json',
             'freeze/owned_execution_policy_v1.json', 'freeze/M4_fault_matrix_v1.json',
             'verification/profile_parity_v1.json', 'verification/entry_policy_cases_v1.json',
             'verification/entry_policy_cases_v2.json', 'verification/freeze_binding_cases_v1.json',
             'verification/reproduce_generation_v1.json', 'preflight/workspace_initial_v1.json',
             'preflight/workspace_final_v1.json', 'preflight/component_input_lock_v1.json',
             'evidence/entry_policy_attempt01_failure_v1.json', 'postrun/frozen_package_verification_v1.json',
             'implementation/current_diag_contract_v1.json', 'implementation/current_pre_freeze_contract_v1.json',
             'implementation/owned_pre_freeze_contract_v1.json', 'implementation/profile_field_diff_v1.json']]
    paths += [Path(__file__).resolve(), D / 'implementation/python/freeze_binding_v1.py']
    before = {str(p): pin(p) for p in paths}
    values = {str(p.relative_to(D)): binding.parse(p.read_bytes()) for p in paths if p.suffix == '.json'}
    index = values['freeze/freeze_index_v1.json']
    c = values['freeze/p1_execution_contract_v1.json']
    pre = values['implementation/current_pre_freeze_contract_v1.json']
    target_pre = values['implementation/owned_pre_freeze_contract_v1.json']
    sub = values['freeze/freeze_submission_v1.json']
    # Independently trusted exact bytes are taken from this actual sealed
    # submission, then compared to its existing verified report and marker.
    package = binding.verify(D / 'freeze/p1_execution_contract_v1.json', D / 'freeze/freeze_index_v1.json', sub['freeze_index_sha256'], sub['contract_sha256'])
    artifact_pins = {r['path']: {'bytes': r['bytes'], 'sha256': r['sha256']} for r in index['artifacts']}
    for p, expected in artifact_pins.items():assert pin(Path(p)) == expected, p
    lock = values['preflight/component_input_lock_v1.json']['files']
    for p, expected in lock.items():assert pin(Path(p)) == expected, p
    parity = values['verification/profile_parity_v1.json']
    entry = values['verification/entry_policy_cases_v2.json']
    binder = values['verification/freeze_binding_cases_v1.json']
    policy = values['freeze/owned_execution_policy_v1.json']
    initial = values['preflight/workspace_initial_v1.json']
    final = values['preflight/workspace_final_v1.json']
    for p, expected in values['evidence/entry_policy_attempt01_failure_v1.json']['old_attempts_preserved'].items():assert pin(Path(p)) == expected
    original = D.parent / 'scheme_A_current_normal_source_20261020_46'
    old_normal_ledger = binding.parse((original / 'implementation/B5_candidate_evidence_ledger_v1.json').read_bytes())
    pre_freeze_delta = {k for k in pre if pre[k] != target_pre[k]}
    qualification = {'qualification', 'execute_qualified', 'parameters_are_diagnostic_only', 'pending_final_calibration', 'freeze_evidence_sha256'}
    semantic = {'baseline_input', 'preparation_retry_policy', 'propagation_semantics', 'supported_parameter_profile'}
    checks = {
        'actual_non_circular_index_and_contract_binding': package['passed'] and c['freeze_evidence_sha256'] == before[str(D / 'freeze/freeze_index_v1.json')]['sha256'] == sub['freeze_index_sha256'],
        'contract84_and_profile_exact': len(c) == 84 and c['supported_parameter_profile'] == full.SPEC['target_profile_id'],
        'pre_freeze_semantic_delta_exactly_four_strings': pre_freeze_delta == semantic and all(type(pre[k]) is str and type(target_pre[k]) is str for k in semantic),
        'final_delta_exactly_four_semantics_plus_five_qualification_fields': {k for k in pre if pre[k] != c[k]} == semantic | qualification,
        'all_other_fields_and_control_model_numbers_unchanged': all(pre[k] == c[k] for k in pre if k not in semantic | qualification) and len(c['hydro']) == 19,
        'only_new_frozen_pending_cleared_old8_retained': c['pending_final_calibration'] == [] and len(pre['pending_final_calibration']) == len(target_pre['pending_final_calibration']) == len(old_normal_ledger['original_pending8']) == 8,
        'old_pre_freeze_exact_source_bytes_retained': before[str(D / 'implementation/current_pre_freeze_contract_v1.json')]['sha256'] == '1faedd4bbf7338ffbd3bc1f9b049285e58d7c3605816d416ac2b83fbfd5365fb',
        'all_641_expected_results_not_merely_python_native_agreement': parity['passed'] and len(parity['cases']) == 641 and all(r['Python']['accepted'] == r['Native']['accepted'] == r['expected'] for r in parity['cases']),
        'old385_and_new256_expectations_separate': sum(r['legacy'] for r in parity['cases']) == 385 and sum(not r['legacy'] for r in parity['cases']) == 256,
        'selected92_entry_checks_all_passed': entry['passed'] and len(entry['cases']) == 92 and all(r['passed'] for r in entry['cases']),
        'actual_binding_and_21_negative_cases_passed': binder['passed'] and len(binder['cases']) == 24 and sum(not r['expected_accepted'] for r in binder['cases']) == 21,
        'generator_five_exact_outputs': values['verification/reproduce_generation_v1.json']['passed'] is True,
        'first_failure_not_erased': values['verification/entry_policy_cases_v1.json']['passed'] is False and values['verification/entry_policy_cases_v1.json']['failed_cases'] == ['partial_business_no_false_accept'],
        'all_index_metadata_stage_flags_are_actual_booleans': all(type(v) is bool for v in index['stage_status'].values()),
        'M4_full_matrix_future_unqualified': len(values['freeze/M4_fault_matrix_v1.json']['groups']) == 9 and all(x['current_M4_qualified'] is False for x in values['freeze/M4_fault_matrix_v1.json']['groups']),
        'finite_engineering_source_scope_retained': policy['domain']['full_1_2m_s_domain_proven'] is False and policy['domain']['plant_or_6DOF_proven'] is False and policy['domain']['WCET_proven'] is False,
        'startup1_54s_observation_not_promoted': policy['domain']['full_startup_gap240ms_in_calibration_passed'] is False and policy['domain']['current_full_startup_gap_max_ns'] == 1537738316,
        'no_new_ROS_runs_or_physical_output': entry['actual_ROS_or_output_calls'] == 0 and parity['ROS_runs'] == 0 and full.SPEC['physical_execute_release_enabled'] is False,
        'new_owner_and_bootstrap_have_concrete_code_pins': str(D / 'implementation/native/owned_execution_entry_v2.hpp') in artifact_pins and str(D / 'build/components_attempt02/entry_probe') in artifact_pins,
        'old_assets_before_and_after_passed': initial['passed'] is True and final['passed'] is True,
        'old_workspace_projection_same': initial['protection']['business_diff_bytes'] == final['protection']['business_diff_bytes'] == 151961 and initial['workspace_after']['HEAD'] == final['workspace_after']['HEAD'] == '78999cf380c0b0dd7f545e4dc8103b7c4c2f7b15',
        'same_boot_retained': initial['workspace_after']['boot_id'] == final['workspace_after']['boot_id'],
        'old_archive_path_population_equal': initial['protection']['raw_paths_equal_recorded_old_bytes'] == final['protection']['raw_paths_equal_recorded_old_bytes'] == 50790,
    }
    after = {p: pin(Path(p)) for p in before}
    report = {'schema': 'P1-M0b-independent-final-freeze-audit/v1', 'passed': all(checks.values()) and before == after,
              'checks': checks, 'check_count': len(checks), 'input_sha256_before': before, 'input_sha256_after': after,
              'frozen_artifact_sha256_rechecked': artifact_pins, 'frozen_artifact_count': len(artifact_pins),
              'package_verification': package, 'B5_contract_freeze_qualified': package['B5_contract_freeze_qualified'],
              'M0b_selected_engineering_freeze_qualified': package['M0b_selected_engineering_freeze_qualified'],
              'M4_qualified': False, 'F6_qualified': False, 'P1_qualified': False, 'physical_execute_release_enabled': False,
              'research_conclusion': False}
    with (D / 'postrun/independent_freeze_audit_v1.json').open('x') as f:json.dump(report, f, ensure_ascii=False, sort_keys=True, indent=2);f.write('\n')
    print(json.dumps({'passed': report['passed'], 'check_count': len(checks), 'artifact_count': len(artifact_pins), 'failed': [k for k, v in checks.items() if not v]}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
