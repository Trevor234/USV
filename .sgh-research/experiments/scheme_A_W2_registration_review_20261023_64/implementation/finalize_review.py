#!/usr/bin/env python3
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence'


def read(path):
    return json.loads(Path(path).read_text())


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def changed(records):
    return [name for name, value in records.items()
            if not Path(name).is_file() or pin(name) != value]


inputs = read(EVIDENCE / 'review_inputs_before_v1.json')
prior = read(EVIDENCE / 'protected_prior_inputs_before_v1.json')
workspace = read(EVIDENCE / 'workspace_before_v1.json')
auxiliary = read(EVIDENCE / 'identity_check/auxiliary_input_pins_v1.json')
input_changes = changed(inputs['files'])
prior_changes = changed(prior['files'])
workspace_changes = changed(workspace['files'])
auxiliary_changes = changed(auxiliary['files'])
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-uall'],
                                 cwd='/home/trevor/USV', text=True)
assert not input_changes and not prior_changes and not workspace_changes and not auxiliary_changes
assert not prior['changed_from_prior_pins'] and status == workspace['status_porcelain']

identity = read(EVIDENCE / 'identity_check/verification_v1.json')
assert identity['all_static_checks_passed'] and identity['source_bundle_file_count'] == 95
assert identity['registered_output_absent'] and not identity['owned_run_performed']
assert not Path(ROOT.parent / 'scheme_A_W2_registration_20261023_63/implementation/runs/W2_01').exists()
baseline = read(EVIDENCE / 'final_source_replay/wiring_verification_v2.json')
assert baseline['complete'] and baseline['sealed_tree_unchanged']
assert sum(value['passed'] for value in baseline['suites'].values()) == 39
assert len(baseline['mutations']) == 12
assert all(value['prepared'] and value['caught_by_test_suite'] for value in baseline['mutations'].values())
source_contract = read(EVIDENCE / 'w2_source_contract/source_contract_v1.json')
driver_replay = read(EVIDENCE / 'w2_driver_replay/driver_branch_replay_v1.json')
assert source_contract['all_passed'] and len(source_contract['checks']) == 10
assert driver_replay['all_passed'] and len(driver_replay['cases']) == 5
policy = read(EVIDENCE / 'policy_consistency_v1.json')
assert policy['all_consistent_now'] and len(policy['checks']) == 14
backend = read(EVIDENCE / 'private_reproductions/backend/probe_assertions.json')
assert backend['regression_assertions_passed'] == 1 and backend['regression_assertions_failed'] == 2
assert all(case['native_call_count'] == 0 for case in backend['cases'])
driver = read(EVIDENCE / 'private_reproductions/driver/driver_final_predicate_review_v1.json')
assert driver['cases']['baseline']['passed'] is True
assert driver['cases']['release_not_verified_but_label_expired']['passed'] is True
assert driver['cases']['bootstrap_error_actual_local_scope']['type'] == 'UnboundLocalError'
preflight = read(EVIDENCE / 'private_reproductions/tests/preflight_gap_summary.json')
assert preflight['hand_copied_replay']['all_passed'] is True
assert preflight['actual_driver_w2_preflight']['outcome'] == 'assertion_rejected'

report = {
    'schema': 'scheme-A-W2-two-round-registration-review-v1',
    'written_at': datetime.datetime.now().astimezone().isoformat(),
    'client_review_date': '2026-10-23', 'timeline': inputs['timeline'],
    'review_complete': True, 'static_build_and_registration_verified': True,
    'current_driver_PASS_sufficient_for_owned_W2_qualification': False,
    'owned_trial_preparation_may_proceed': True,
    'limited_prerun_fixes_and_identity_refresh_recommended': True,
    'new_matrix_obligations_added': False,
    'submitted_inputs': len(inputs['files']), 'submitted_input_changes': input_changes,
    'protected_prior_selected_inputs': len(prior['files']), 'protected_prior_changes': prior_changes,
    'protected_scope': prior['scope'], 'ordinary_workspace_files': len(workspace['files']),
    'ordinary_workspace_changes': workspace_changes, 'git_status_unchanged': True,
    'auxiliary_identity_input_changes': auxiliary_changes,
    'submitted_packages_modified_by_review': False,
    'source_bundle_sha256': identity['source_bundle_sha256'],
    'driver_sha256': identity['driver_sha256'],
    'registry_sha256': identity['registry_sha256'],
    'registration_sha256': identity['registration_sha256'],
    'frozen_source_files': 95, 'current_runtime_files_match_registry': True,
    'registered_driver_enforces_runtime_maps_identity': False,
    'static_source_identity_is_not_runtime_maps_authentication': True,
    'final_source_tests_passed': 39, 'registered_mutations_prepared_and_caught': 12,
    'source_contract_checks_passed': 10, 'driver_observation_branch_cases_passed': 5,
    'static_policy_consistency_checks_passed': 14,
    'extra_backend_fact_assertions': {'positive_control_passed': 1, 'consistency_assertions_failed': 2,
                                      'probe_process_returncode': backend['probe_execution_returncode'],
                                      'actual_C_solve_calls_each_case': 0},
    'early_bootstrap_finalization_bug_reproduced': True,
    'handwritten_preflight_scope_gap_reproduced': True,
    'new_registry_created': False, 'owned_runs_started': 0,
    'registered_run_output_created': False, 'roles_executed': False,
    'ROS_started': False, 'hardware_control_started': False,
    'offline_actual_acados_calls': True,
    'owned_W2_qualified': False, 'M4_stage_qualified': False, 'F6_qualified': False,
    'P1_qualified': False, 'plant_acceptance_qualified': False, 'hard_realtime_qualified': False,
    'all_implementation_checks_passed': False,
    'next': 'Bounded failure-finalization, factual audit, target-record and runtime-library fixes; refresh affected identities; then one finite owned W2 with independent audit',
}
(EVIDENCE / 'review_verification_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
bad_links = []
count = 0
for document in [ROOT / 'CURRENT.md', *sorted((ROOT / 'documents').glob('*.md'))]:
    for target in re.findall(r'\]\((/[^)]+)\)', document.read_text()):
        count += 1
        if not Path(re.sub(r':\d+$', '', target)).is_file():
            bad_links.append({'document': str(document), 'target': target})
assert not bad_links, bad_links
(EVIDENCE / 'document_link_verification_v1.json').write_text(json.dumps({
    'links_checked': count, 'bad_links': bad_links}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key: report[key] for key in [
    'review_complete', 'static_build_and_registration_verified', 'submitted_inputs',
    'submitted_input_changes', 'protected_prior_selected_inputs', 'protected_prior_changes',
    'ordinary_workspace_changes', 'final_source_tests_passed',
    'registered_mutations_prepared_and_caught', 'source_contract_checks_passed',
    'driver_observation_branch_cases_passed', 'owned_runs_started']}, ensure_ascii=False))
