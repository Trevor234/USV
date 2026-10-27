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
    return json.loads(path.read_text())


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def changes(records):
    return [name for name, expected in records.items()
            if not Path(name).is_file() or pin(Path(name)) != expected]


inputs = read(EVIDENCE / 'review_inputs_before_v1.json')['files']
prior = read(EVIDENCE / 'protected_prior_inputs_before_v1.json')
workspace = read(EVIDENCE / 'workspace_before_v1.json')
input_changes = changes(inputs)
prior_changes = changes(prior['files'])
workspace_changes = changes(workspace['files'])
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-uall'],
                                 cwd='/home/trevor/USV', text=True)
assert not input_changes and not prior_changes and not workspace_changes
assert not prior['changed_from_prior_pins']
assert status == workspace['status_porcelain']

baseline = read(EVIDENCE / 'wiring_replay/wiring_verification_v2.json')
assert baseline['complete'] and baseline['sealed_tree_unchanged']
assert sum(row['passed'] for row in baseline['suites'].values()) == 36
assert len(baseline['mutations']) == 9
assert all(row['prepared'] and row['caught_by_test_suite'] for row in baseline['mutations'].values())
driver_replay = read(EVIDENCE / 'driver_replay/driver_branch_replay_v1.json')
assert driver_replay['all_passed'] and len(driver_replay['cases']) == 5
reproduction = read(EVIDENCE / 'reproduction_summary_v1.json')
native = reproduction['backend']['private_additional_tests']
assert native['passed'] == 4 and native['failed'] == 3 and native['exit_code'] == 1
assert reproduction['backend']['extra_mutation']['passed'] == 8
assert reproduction['backend']['extra_mutation']['mutation_caught'] is False
assert reproduction['driver']['worker_SIGTERM'] is True
assert reproduction['driver']['transition_before_boundary_entry'] is True
assert reproduction['driver']['recorded_error'] is False
assert reproduction['driver_early_failure']['exception'] == 'UnboundLocalError'
compiled = read(EVIDENCE / 'private_role_compile/verification_v1.json')
assert compiled['all_built'] and len(compiled['roles']) == 3
assert not compiled['role_execution'] and not compiled['registry_created']

report = {
    'schema': 'scheme-A-W2-closeout-independent-review-v1',
    'written_at': datetime.datetime.now().astimezone().isoformat(),
    'client_review_date': '2026-10-23',
    'review_complete': True,
    'registration_preparation_may_proceed': True,
    'current_source_ready_for_final_owned_seal': False,
    'limited_fixes_should_merge_into_registration_batch': True,
    'new_matrix_obligations_added': False,
    'submitted_inputs': len(inputs), 'submitted_input_changes': input_changes,
    'protected_prior_selected_inputs': len(prior['files']),
    'protected_prior_changes': prior_changes, 'protected_scope': prior['scope'],
    'ordinary_workspace_files': len(workspace['files']),
    'ordinary_workspace_changes': workspace_changes, 'git_status_unchanged': True,
    'submitted_source_modified_by_review': False,
    'private_probes_and_mutants_created': True,
    'submitted_baseline_tests_passed': 36,
    'submitted_mutations_prepared_and_caught': 9,
    'submitted_driver_observation_branch_cases_passed': 5,
    'driver_replay_scope': 'Observation postconditions only, not full event loop/finalization',
    'extra_native_tests': native,
    'extra_deleted_real_final_guard': reproduction['backend']['extra_mutation'],
    'D3_real_C_error_fact_fixed': True,
    'D4_matched_actual_preparation_guard_fixed': True,
    'D4_nonmatching_call_guard_fixed': False,
    'D5_production_tuple_fd_validate_shared': True,
    'D5_production_parameter_whitelist_shared': False,
    'D6_driver_pipe_manifest_binding_fixed': True,
    'private_roles_compiled_not_executed': compiled['roles'],
    'private_role_compile_identity': compiled['compile_identity_values'],
    'registry_created': False, 'owned_runs_started': 0,
    'ROS_started': False, 'hardware_control_started': False,
    'offline_actual_acados_calls': True,
    'owned_W2_qualified': False, 'M4_stage_qualified': False,
    'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance_qualified': False, 'hard_realtime_qualified': False,
    'all_implementation_checks_passed': False,
    'next': 'Merge bounded guard/finalization/coverage/terminal fixes into §6.3 preparation; freeze final source then register exact identities and run one finite owned W2',
}
(EVIDENCE / 'review_verification_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

bad_links = []
count = 0
for document in [ROOT / 'CURRENT.md', *sorted((ROOT / 'documents').glob('*.md'))]:
    for target in re.findall(r'\]\((/[^)]+)\)', document.read_text()):
        count += 1
        path = re.sub(r':\d+$', '', target)
        if not Path(path).is_file():
            bad_links.append({'document': str(document), 'target': target})
assert not bad_links, bad_links
(EVIDENCE / 'document_link_verification_v1.json').write_text(json.dumps({
    'links_checked': count, 'bad_links': bad_links}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key: report[key] for key in [
    'review_complete', 'registration_preparation_may_proceed',
    'current_source_ready_for_final_owned_seal', 'submitted_inputs',
    'submitted_input_changes', 'protected_prior_selected_inputs', 'protected_prior_changes',
    'ordinary_workspace_changes', 'submitted_baseline_tests_passed',
    'submitted_mutations_prepared_and_caught',
    'submitted_driver_observation_branch_cases_passed',
    'private_roles_compiled_not_executed', 'owned_runs_started']}, ensure_ascii=False))
