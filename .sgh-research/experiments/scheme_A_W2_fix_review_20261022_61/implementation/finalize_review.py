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


def changed(records):
    return [name for name, value in records.items()
            if not Path(name).is_file() or pin(Path(name)) != value]


inputs = read(EVIDENCE / 'review_inputs_before_v1.json')['files']
prior = read(EVIDENCE / 'protected_prior_inputs_before_v1.json')
workspace = read(EVIDENCE / 'workspace_before_v1.json')
supporting = read(EVIDENCE / 'supporting_evidence_pins_v1.json')['files']
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-uall'],
                                 cwd='/home/trevor/USV', text=True)
input_changes = changed(inputs)
prior_changes = changed(prior['files'])
workspace_changes = changed(workspace['files'])
supporting_changes = changed(supporting)
assert not prior['changed_from_prior_pins']
assert not input_changes and not prior_changes and not workspace_changes and not supporting_changes
assert status == workspace['status_porcelain']

baseline = read(EVIDENCE / 'wiring_replay/wiring_verification_v2.json')
assert baseline['complete'] and baseline['sealed_tree_unchanged']
assert sum(row['passed'] for row in baseline['suites'].values()) == 25
assert len(baseline['mutations']) == 6
assert all(row['prepared'] and row['caught_by_test_suite'] for row in baseline['mutations'].values())
compile_result = read(EVIDENCE / 'application_compile_and_edges/verification_v1.json')
assert compile_result['probe_exit_code'] == 1
assert not compile_result['role_execution'] and not compile_result['formal_identity']
native_log = (EVIDENCE / 'application_compile_and_edges/review_backend_edges.stdout.txt').read_text()
assert '[  PASSED  ] 1 test.' in native_log and '3 FAILED TESTS' in native_log
facts = {}
for line in native_log.splitlines():
    if line.startswith('REVIEW_'):
        key, value = line.split(' ', 1)
        facts[key] = json.loads(value)
assert facts['REVIEW_NATIVE_ERROR_FACTS']['real_C_solve_calls'] == 1
assert facts['REVIEW_NATIVE_ERROR_FACTS']['boundary']['actual_native_invoked'] is False
assert facts['REVIEW_PREPARATION_STOP_FACTS']['real_C_solve_calls'] == 4
assert facts['REVIEW_PREPARATION_DEADLINE_FACTS']['real_C_solve_calls'] == 1
driver = read(EVIDENCE / 'driver_branch_probes_v2.json')
assert driver['final_predicate_false_positive']['actual_passed']
assert not driver['W2_summary_drops_observed_fields']['ramp_ok_present']
entry = read(EVIDENCE / 'entry_coverage_probe/verification_v1.json')
assert entry['passed_tests'] == 4 and not entry['mutant_rejected']

report = {
    'schema': 'scheme-A-W2-fix-independent-review-v1',
    'written_at': datetime.datetime.now().astimezone().isoformat(),
    'review_complete': True, 'implementation_accepted': False,
    'submitted_input_count': len(inputs), 'submitted_input_changes': input_changes,
    'protected_prior_input_count': len(prior['files']), 'protected_prior_input_changes': prior_changes,
    'protected_scope': prior['scope'],
    'ordinary_workspace_files': len(workspace['files']), 'ordinary_workspace_file_changes': workspace_changes,
    'git_status_unchanged': status == workspace['status_porcelain'],
    'supporting_prior_entry_failure_changes': supporting_changes,
    'submitted_source_modified_by_review': False,
    'private_probe_sources_created_and_modified': True,
    'fresh_submitted_tests_passed': 25, 'submitted_mutations_prepared_and_caught': 6,
    'delete_backend_wiring_caught_by_tests': baseline['mutations']['delete_backend_wiring']['failed_tests'],
    'roles_compiled_not_executed': compile_result['roles_compiled'],
    'private_compile_identities': 'x placeholders; no formal registry',
    'new_native_checks': {'passed': 1, 'failed': 3, 'exit_code': 1, 'facts': facts},
    'entry_mutant': {'old_worker_errors_restored': True, 'test_passed_count': 4, 'rejected': False},
    'driver_main_executed': False, 'driver_check_scope': 'Original AST branches only',
    'new_registry_created': False, 'owned_runs_started': 0, 'ROS_started': False,
    'hardware_control_started': False, 'offline_actual_acados_calls': True,
    'owned_W2_qualified': False, 'M4_stage_qualified': False, 'F6_qualified': False,
    'P1_qualified': False, 'plant_acceptance_qualified': False, 'hard_realtime_qualified': False,
    'validation_all_passed': False,
    'next': 'Finish existing Driver, C-entry facts/guards, entry helper, channel/terminal cleanup; then register final identities',
}
(EVIDENCE / 'review_verification_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
bad_links = []
link_count = 0
for path in [ROOT / 'CURRENT.md', *sorted((ROOT / 'documents').glob('*.md'))]:
    for target in re.findall(r'\]\((/[^)]+)\)', path.read_text()):
        link_count += 1
        file_path = re.sub(r':\d+$', '', target)
        if not Path(file_path).is_file():
            bad_links.append({'document': str(path), 'target': target})
assert not bad_links, bad_links
(EVIDENCE / 'document_link_verification_v1.json').write_text(json.dumps({
    'links_checked': link_count, 'bad_links': bad_links}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key: report[key] for key in [
    'review_complete', 'implementation_accepted', 'submitted_input_count',
    'submitted_input_changes', 'protected_prior_input_count', 'protected_prior_input_changes',
    'ordinary_workspace_file_changes', 'git_status_unchanged',
    'fresh_submitted_tests_passed', 'submitted_mutations_prepared_and_caught',
    'roles_compiled_not_executed', 'owned_runs_started']}, ensure_ascii=False))
