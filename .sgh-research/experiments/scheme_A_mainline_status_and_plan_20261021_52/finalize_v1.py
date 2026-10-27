#!/usr/bin/env python3
"""Seal a reviewed, time-scoped mainline document; no runtime stage promotion."""
import hashlib
import json
from pathlib import Path
import re

D = Path(__file__).resolve().parent
REPORT = 'documents/方案A_主线进度_代码改动与后续实施详解_2026-10-21.md'


def load(p):return json.loads(p.read_bytes())
def pin(p):
    raw = p.read_bytes();return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
def emit(p, value):
    with p.open('x') as f:json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True);f.write('\n')


def main():
    assert not (D / 'archive_inventory_v1.json').exists()
    initial = load(D / 'evidence/current_baseline_adoption_v1.json')
    strict = load(D / 'evidence/final_baseline_adoption_v1.json')
    parallel = load(D / 'evidence/parallel_aware_checkpoint_v2.json')
    snapshot = load(D / 'evidence/parallel_snapshot_v2/manifest.json')
    assert initial['passed'] and not strict['passed'] and 'workspace' in strict['traceback']
    assert parallel['passed'] and parallel['frozen47_actual_inputs_checked'] == 4103
    assert parallel['frozen47_mismatches'] == parallel['workspace_changed_paths_overlap_frozen47'] == []
    assert snapshot['capture_consistent_during_read'] and snapshot['user_confirmed_other_task_is_modifying_workspace']
    assert len(snapshot['tracked_changed_files']) == 16 and len(snapshot['untracked_files']) == 4 and len(snapshot['files']) == 20
    assert snapshot['tracked_patch']['bytes'] == 24950
    assert not snapshot['51_verified_set_currently_identical']
    for name, row in snapshot['files'].items():
        assert pin(D / row['snapshot']) == {k: row[k] for k in ['bytes', 'sha256']}, name
    report = D / REPORT;text = report.read_text()
    assert len(text.splitlines()) >= 500 and text.count('```') % 2 == 0
    links = re.findall(r'\]\((/[^)]+)\)', text)
    missing = [target for target in links if not Path(re.sub(r':\d+$', '', target)).is_file()]
    assert not missing, missing
    for token in ['MANUAL', 'R1', 'R2', 'F6', 'model+plan', '20:34:29', '18,263', '24,950', '51批已验证']:
        assert token in text, token
    plan = load(D / 'postrun/next_implementation_plan_v2.json')
    assert plan['rebuild_required'] == ['p1_m4_regulator_owned', 'p1_m4_worker_owned', 'p1_m4_fixture_owned']
    assert plan['reuse_eligible'] == ['p1_owned_recorder'] and not plan['next_run_registered']
    assert not any(plan[k] for k in ['M4_stage_qualified', 'F6_qualified', 'P1_qualified', 'historical_51_test_qualification_transferred_to_parallel_source'])
    emit(D / 'evidence/independent_review_summary_v1.json', {
        'schema': 'SchemeA-read-only-document-and-plan-independent-review/v1',
        'reviewers': 3, 'new_ROS_runs_or_source_edits_by_reviewers': 0,
        'history_review': 'top-level CURRENT/documents13-46; distinguish offline work, real failures, diagnostic half-RMSE and actual stage obligations',
        'current_contract_review': 'MANUAL source/config and51 test versions checked; install marker/hash provenance and user-confirmed later parallel edits scoped separately',
        'next_plan_review': 'all3 native roles bind compiled Driver SHA; Recorder reusable; Worker death requires fallback observation then Driver shutdown; use actual unusable transition as commit boundary',
        'F6_review_note_applied': 'history reconciliation uses explicit base model; candidate defect uses selected performance model; record both identities',
        'review_is_not_new_controller_or_deployment_qualification': True})
    proofs = ['evidence/current_baseline_adoption_v1.json', 'evidence/final_baseline_adoption_v1.json',
              'evidence/parallel_aware_checkpoint_v2.json', 'evidence/parallel_snapshot_v2/manifest.json',
              'evidence/independent_review_summary_v1.json', 'postrun/next_implementation_plan_v2.json', REPORT, 'CURRENT.md']
    emit(D / 'postrun/final_QA_v1.json', {
        'schema': 'SchemeA-mainline-status-document-and-baseline-checkpoint-QA/v1', 'passed': True,
        'passed_scope': 'document consistency, exact point-in-time parallel snapshot and selected sealed asset verification only',
        'main_document': REPORT, 'document': pin(report), 'document_lines': len(text.splitlines()),
        'absolute_local_file_links_checked': len(links), 'missing_local_file_links': missing,
        'historical_51_baseline_initial_check_passed': True,
        'old_strict_workspace_final_check_passed': False,
        'strict_failure_preserved_and_explained_by_user_confirmed_parallel_work': True,
        'parallel_snapshot_captured_UTC': snapshot['captured_UTC'], 'parallel_snapshot_regular_source_files': 20,
        'snapshot_tracked_changes': 16, 'snapshot_untracked_files_including_preexisting_zcodeignore': 4,
        'snapshot_patch': snapshot['tracked_patch'],
        'parallel_aware_archive_and_frozen_input_check_passed': True,
        'frozen47_actual_files_checked': 4103, 'frozen47_mismatches': 0,
        'selected_sealed_archive_file_counts': {r['name']: r['regular_files'] for r in parallel['sealed_archives']},
        'live_parallel_sources_claimed_still_frozen_after_capture': False,
        'current_complete_parallel_source_build_regression_qualified': False,
        '51_old_test_qualification_transferred_to_new_source': False,
        'new_ROS_runs': 0, 'new_FCU_requests': 0, 'production_controller_source_changes_by_this_batch': 0,
        'R1_or_R2_implemented_or_run_this_batch': False,
        'ordinary_production_release_enabled_by_this_batch': False,
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False, 'research_conclusion': False,
        'old_records_failed_runs_and_user_changes_overwritten': False,
        'proofs': {name: pin(D / name) for name in proofs}})
    files = [];directories = []
    for path in sorted(D.rglob('*')):
        assert not path.is_symlink(), str(path)
        if path.is_dir():directories.append(str(path.relative_to(D)))
        else:files.append({'relative_path': str(path.relative_to(D)), **pin(path)})
    emit(D / 'archive_inventory_v1.json', {'schema': 'SchemeA-mainline-document-checkpoint-archive/v1',
         'files': files, 'directories': directories, 'file_count_before_inventory_receipt': len(files),
         'bytes_before_inventory_receipt': sum(r['bytes'] for r in files),
         'document_and_snapshot_integrity_passed': True, 'M4_F6_P1_qualified': False})
    print(json.dumps({'passed': True, 'report_bytes': pin(report)['bytes'], 'report_lines': len(text.splitlines()),
                      'files_before_inventory_receipt': len(files), 'inventory': pin(D / 'archive_inventory_v1.json'),
                      'QA': pin(D / 'postrun/final_QA_v1.json')}))


if __name__ == '__main__':main()
