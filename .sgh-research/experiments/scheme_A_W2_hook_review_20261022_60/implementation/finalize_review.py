#!/usr/bin/env python3
"""Read-only source/workspace verification; writes only this review package."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence'
PREVIOUS = ROOT.parent / 'scheme_A_W2_pre_wiring_review_20261022_59'


def read(path):
    return json.loads(path.read_text())


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def compare(records):
    return [name for name, value in records.items()
            if not Path(name).is_file() or pin(name) != value]


before = read(EVIDENCE / 'review_inputs_before_v1.json')
workspace = read(EVIDENCE / 'workspace_before_v1.json')
old = read(PREVIOUS / 'evidence/review_inputs_before_v1.json')['files']
source_changes = compare(before['files'])
workspace_changes = compare(workspace['files'])
historic_changes = compare(old)
status = subprocess.check_output(
    ['git', 'status', '--porcelain=v1', '-uall'], cwd='/home/trevor/USV', text=True)
snapshot_mismatch = []
for name, value in before['files'].items():
    path = EVIDENCE / 'reviewed_input_snapshot' / Path(name).relative_to(PREVIOUS)
    if not path.is_file() or pin(path) != value:
        snapshot_mismatch.append(name)

summary = read(EVIDENCE / 'reproduction_summary_v2.json')
assert summary['fresh_original_suites']['complete']
assert summary['fresh_original_suites']['total_passed'] == 20
assert summary['registered_mutations']['all_prepared']
assert summary['registered_mutations']['all_caught']
assert summary['registered_mutations']['originals_unchanged']
assert summary['deleted_boundary_block']['returncode'] == 0
assert summary['stop_after_gate']['released']
assert summary['stop_after_gate']['disposition'] == 'stopped'
backend_log = (EVIDENCE / 'private_reproductions/backend_facts/run_v2.log').read_text()
assert '[  PASSED  ] 1 test.' in backend_log
assert '2 FAILED TESTS' in backend_log

result = {
    'schema': 'scheme-A-W2-hook-code-review-v1',
    'written_at': datetime.datetime.now().astimezone().isoformat(),
    'review_complete': True,
    'implementation_accepted': False,
    'reviewed_inputs': len(before['files']),
    'reviewed_inputs_changed': source_changes,
    'reviewed_input_snapshot_mismatch': snapshot_mismatch,
    'selected_historic_assets': len(old),
    'selected_historic_assets_changed': historic_changes,
    'historic_scope': 'Original 59 review selected 56/57/58 inputs only; not a full archive scan',
    'ordinary_workspace_files': len(workspace['files']),
    'ordinary_workspace_files_changed': workspace_changes,
    'git_status_unchanged': status == workspace['status_porcelain'],
    'git_status_after': status,
    'source_code_modified_by_review': False,
    'new_registry_created': False,
    'ROS_started_by_review': False,
    'owned_runs_started_by_review': 0,
    'hardware_control_started': False,
    'offline_native_solver_was_invoked': True,
    'fresh_original_tests_passed': 20,
    'registered_mutations_prepared_and_caught': 5,
    'deleted_backend_wiring_mutant': 'NOT CAUGHT: existing 5 tests still pass',
    'new_backend_checks': {'passed': 1, 'failed': 2, 'exit_code': 1},
    'stop_after_gate_path': 'reachable and correctly rejected by existing Boundary',
    'owned_W2_qualified': False,
    'M4_stage_qualified': False,
    'F6_qualified': False,
    'P1_qualified': False,
    'plant_acceptance_qualified': False,
    'hard_realtime_qualified': False,
    'validation_all_passed': False,
    'next': 'Fix application wiring and regressions; targeted validation; then build and register final identities',
}
assert not source_changes and not workspace_changes and not historic_changes
assert not snapshot_mismatch and result['git_status_unchanged']
assert len(before['files']) == 96 and len(old) == 14 and len(workspace['files']) == 21
out = EVIDENCE / 'review_verification_v1.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')

bad_links = []
links_checked = 0
for document in [ROOT / 'CURRENT.md', *sorted((ROOT / 'documents').glob('*.md'))]:
    for target in re.findall(r'\]\((/[^)]+)\)', document.read_text()):
        path = re.sub(r':\d+$', '', target)
        links_checked += 1
        if not Path(path).is_file():
            bad_links.append({'document': str(document), 'target': target})
assert not bad_links, bad_links
(EVIDENCE / 'document_link_verification_v1.json').write_text(json.dumps({
    'links_checked': links_checked, 'bad_links': bad_links}, ensure_ascii=False, indent=2) + '\n')

print(json.dumps({key: result[key] for key in [
    'review_complete', 'implementation_accepted', 'reviewed_inputs',
    'reviewed_inputs_changed', 'selected_historic_assets_changed',
    'ordinary_workspace_files_changed', 'git_status_unchanged',
    'fresh_original_tests_passed', 'registered_mutations_prepared_and_caught',
    'new_backend_checks', 'owned_runs_started_by_review']}, ensure_ascii=False))
