#!/usr/bin/env python3
"""Seal exact-source component evidence and original-obligation coverage without promotion."""
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
P49 = D.parent / 'scheme_A_M4_recorder_bootstrap_20261021_49'
P47 = D.parent / 'scheme_A_formal_execute_profile_20261020_47'


def load(path):
    return json.loads(path.read_bytes())


def pin(path):
    h = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as f:
        while data := f.read(1024 * 1024):
            h.update(data)
            size += len(data)
    return {'bytes': size, 'sha256': h.hexdigest()}


def emit(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def main():
    assert not (D / 'archive_inventory_v1.json').exists()
    before = load(D / 'preflight/workspace_initial_v1.json')
    after = load(D / 'preflight/workspace_final_v1.json')
    b1 = load(D / 'build/component_attempt01/build_manifest_v1.json')
    b2 = load(D / 'build/component_attempt02/build_manifest_v1.json')
    v = load(D / 'verification/component_verification_v1.json')
    a = load(D / 'postrun/publication_fault_audit_v1.json')
    stderr = load(D / 'postrun/native_stderr_diagnostics_v1.json')
    reg = load(D / 'preflight/component_registration_v1.json')
    assert all(row['passed'] for row in [before, after, b2, v, a, stderr])
    assert not b1['passed']
    assert before['workspace_after'] == after['workspace_after'] and before['parent49'] == after['parent49']
    assert v['XML'] == {'tests': 16, 'failures': 0, 'errors': 0, 'disabled': 0}
    assert v['group_empty'] and v['signals'] == [] and v['returncode'] == 0 and not v['timed_out']
    assert v['input_before'] == v['input_after'] and len(v['input_after']) == 1540
    assert a['input_before'] == a['input_after'] and len(a['input_after']) == 36
    assert len(reg['cases']) == len(a['cases']) == 16 and reg['automatic_retries'] == 0
    assert a['totals'] == {'steps': 28, 'actual_private_control_rcl_entries': 56,
                           'delegated_control_calls': 43, 'delegated_Applied_calls': 27,
                           'injected_return_errors': 14, 'independently_decoded_wire_messages': 70}
    assert len(a['checker_mutation_rejections']) == 4 and all(row['rejected'] for row in a['checker_mutation_rejections'])
    assert stderr['unclassified_nonempty_stderr_lines'] == 0 and stderr['old_typesupport_error_state_overwrite_diagnostics'] == 8
    assert not stderr['original_stderr_modified_or_filtered'] and not stderr['original_stale_state_full_provenance_proven']
    for expected_map in [v['input_after'], a['input_after']]:
        for name, expected in expected_map.items():
            assert pin(name) == expected, name
    for name in ['CMakeLists.txt', 'test_m4_publication_faults.cpp']:
        assert (D / 'author' / name).read_bytes() == (D / 'build/component_attempt01/author_snapshot' / name).read_bytes()
        assert (D / 'author_v2' / name).read_bytes() == (D / 'build/component_attempt02/author_snapshot' / name).read_bytes()
    original = (D / 'author/test_m4_publication_faults.cpp').read_text()
    fixed = (D / 'author_v2/test_m4_publication_faults.cpp').read_text()
    assert original.replace('executor.add_node(r);', 'executor.add_node(r->get_node_base_interface());').replace('executor.remove_node(r);', 'executor.remove_node(r->get_node_base_interface());') == fixed
    source = P49 / 'author/observer/src/shadow/regulator_owned_execute.cpp'
    assert pin(source)['sha256'] == '94bbcb25c356c992111c1779d685bdb3da7dca2f5a0bf301d1f745ea4c2f9bf0'
    matrix_path = P47 / 'freeze/M4_fault_matrix_v1.json'
    matrix = load(matrix_path)
    matrix_groups = {row['id']: row for row in matrix['groups']}
    assert len(matrix_groups) == 9
    evidence = {
        'compatibility_input': ([str(P49 / 'evidence/F5_and_calibrated_nominal_scope_v1.json')], 'original F5 source/reference/mapping and logging applicability not closed'),
        'time_boundaries': ([str(P49 / 'verification/component_verification_v1.json'), str(P49 / 'postrun/actual_normal_audit_v1.json')], 'complete original timing cases require exact-case coverage; this batch only adds seeded shutdown grace boundary'),
        'native_block_and_delivery': ([], 'current owner true native block and distinct delivery delay/drop not covered by this batch'),
        'candidate_identity_shape': ([str(P49 / 'verification/source_core_reuse_v1.json'), str(P49 / 'verification/component_verification_v1.json')], 'same-source admission evidence retained; original full case matrix not jointly closed'),
        'task_reference': ([str(P49 / 'verification/source_core_reuse_v1.json')], 'clear pending component added; actual before/after committed-submit and reference replacement obligations remain'),
        'state_clock': ([str(P49 / 'verification/component_verification_v1.json'), str(P49 / 'postrun/actual_normal_audit_v1.json')], 'normal/selector components retained; current-runtime pause/reset/jump/RTF/mixed faults remain'),
        'anchor_fallback': ([str(P49 / 'postrun/actual_normal_audit_v1.json'), str(D / 'postrun/publication_fault_audit_v1.json')], 'actual nominal stream and exact-source partial histories covered; full HOLD/ramp/5-miss/interval cases remain'),
        'publication_exit': ([str(D / 'postrun/publication_fault_audit_v1.json')], 'partial/Applied/zero/grace/clear source-linked component passed; live owned pre-grant cancel, worker death/watchdog/lease/cleanup remain'),
        'actual_source_recording': ([str(P49 / 'postrun/actual_normal_audit_v1.json'), str(D / 'postrun/publication_fault_audit_v1.json')], '49 normal Stored and50 private wire/Source component complete; current four-role fault pressure/drop/Stored accounting remains')}
    groups = []
    for row in matrix['groups']:
        refs, remaining = evidence[row['id']]
        groups.append({**row, 'current_M4_qualified': False, 'current_scoped_evidence': refs,
                       'new_batch50_source_linked_subcomponent': row['id'] in ['publication_exit', 'anchor_fallback', 'task_reference', 'actual_source_recording'],
                       'remaining_obligation': remaining})
    emit(D / 'postrun/M4_current_fault_coverage_v1.json', {
        'schema': 'M4-after-publication-source-component-original-nine-group-coverage/v1',
        'parent_matrix': str(matrix_path), 'parent_matrix_pin': pin(matrix_path), 'groups': groups,
        'new_full_owned_fault_runs': 0, 'new_source_linked_publication_exit_cases_passed': 16,
        'all_nine_groups_require_new_long_ROS_runs': False,
        'publication_exit_whole_group_qualified': False, 'M4_stage_qualified': False,
        'F6_qualified': False, 'P1_qualified': False})
    emit(D / 'postrun/next_implementation_plan_v1.json', {
        'schema': 'M4-next-live-owned-cancel-and-worker-exit-then-F6-P1/v1',
        'closed_this_batch': 'exact49 partial publication/Applied/zero/grace/clear source-linked component',
        'runtime_source_changes_this_batch': 0, 'production_release_enabled': False,
        'automatic_next_ROS_run_registered': False,
        'steps': [
            {'order': 1, 'action': 'derive finite fault Driver and only actually required role source/bin bindings; preserve frozen contract/numbers and normal49 evidence'},
            {'order': 2, 'case': 'R1-owned-pre-grant-cancel', 'action': 'preregister exact preparation boundary, authenticate four actual roles and cancel before grant; verify API0, full-recorder vs process-only semantics and finite empty groups'},
            {'order': 3, 'case': 'R2-owned-worker-exit', 'action': 'preregister one authenticated Worker exit after actual accepted business, expected signal/RC/Source exception; verify no new submit/activation, actual per-side API/ramp history and finite cleanup without restart'},
            {'order': 4, 'action': 'close original remaining nine-group exact cases and F5/source/reference applicability with scoped reuse and necessary actual triggers; no blanket repeats'},
            {'order': 5, 'action': 'finite immutable numeric M0/M1 model+plan atomic transaction, fixed-tick activation, old/mixed rejection, saved-plan immutability and separate warmstart; then F6 freeze and original P1 joint review'}],
        'run_policy': {'case_specific_preregistration': True, 'automatic_retries': 0,
                       'driver_max_seconds': 45, 'outer_max_seconds': 90, 'normal_source_recalibration_added': False},
        'stop_conditions': ['identity/config/source/bin/GID mismatch', 'pre-grant API', 'invalid normal activation', 'undeclared loss/timeout/partial or successful-side rollback', 'cleanup_failed or old group nonempty'],
        'do_not_repeat': ['successful49 normal', 'closed45/46 preparation/source', 'old39-42 without affected code', 'same16 publication components without source change or new failure'],
        'new_full_no_output_business_stage': False, 'RTI_cost_model_threshold_tuning': False,
        'codegen_GP_PPO': False, 'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False, 'research_conclusion': False})
    proofs = ['preflight/workspace_initial_v1.json', 'preflight/workspace_final_v1.json',
              'preflight/preflight_reflection_v1.md', 'preflight/component_registration_v1.json',
              'build/component_attempt01/build_manifest_v1.json', 'build/component_attempt02/build_manifest_v1.json',
              'verification/component_verification_v1.json', 'postrun/publication_fault_audit_v1.json',
              'postrun/native_stderr_diagnostics_v1.json', 'evidence/test_executor_interface_fix_v1.json',
              'postrun/M4_current_fault_coverage_v1.json', 'postrun/next_implementation_plan_v1.json']
    emit(D / 'postrun/final_QA_v1.json', {
        'schema': 'SchemeA-M4-publication-fault-source-component-integrity-QA/v1', 'passed': True,
        'batch_deliverable_integrity_passed': True, 'source_linked_publication_exit_component_qualified': True,
        'qualification_scope': 'exact49 Regulator methods; seeded readiness; private-topic return seam and actual successful wire only',
        'source_linked_cases': 16, 'actual_component_ROS_processes': 1,
        'actual_test_returncode': 0, 'owned_test_group_empty': True, 'external_signals_sent': 0,
        'new_M4_four_role_fault_runs': 0, 'actuator_topic_publishers': 0,
        'private_API_and_wire_totals': a['totals'], 'evidence_checker_mutation_refusals': 4,
        'runtime_registered_inputs_unchanged': 1540, 'audit_inputs_unchanged': 36,
        'injected_returns_called_actual_DDS_failures': False,
        'normal49_component_preserved': True, 'parent49_archive_files': 533,
        'production_Regulator_source_modified': False, 'production_ELFs_rebuilt_or_modified': False,
        'first_test_build_failure_and_original_source_preserved': True,
        'source_v2_only_changes_Executor_NodeBaseInterface': True,
        'source_thresholds_model_RTI_cost_tuned': False, 'new_control_codegen_or_install': False,
        'ordinary_production_release_enabled': False, 'publication_exit_whole_group_qualified': False,
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'stage_qualified': False, 'research_conclusion': False, 'plant_qualified': False, 'WCET_qualified': False,
        'all_stderr_lines_classified': True, 'SDK_compatibility_warnings_retained': 2,
        'old_error_state_overwrite_diagnostics_retained': 8,
        'original_stale_error_state_provenance_fully_proven': False,
        'workspace_HEAD': after['workspace_after']['HEAD'], 'workspace_branch': after['workspace_after']['branch'],
        'workspace_status_porcelain_retained': after['workspace_after']['status_porcelain'],
        'all_historical_original_paths_unchanged': False,
        'preexisting_path_exceptions_and_untracked_submodule_state_retained': True,
        'proofs': {name: pin(D / name) for name in proofs}})
    files = []
    directories = []
    for path in sorted(D.rglob('*')):
        assert not path.is_symlink(), str(path)
        if path.is_dir():
            directories.append(str(path.relative_to(D)))
        else:
            assert path.is_file(), str(path)
            files.append({'relative_path': str(path.relative_to(D)), **pin(path)})
    emit(D / 'archive_inventory_v1.json', {
        'schema': 'SchemeA-M4-publication-fault-component-archive/v1', 'files': files, 'directories': directories,
        'file_count_before_inventory_receipt': len(files), 'bytes_before_inventory_receipt': sum(row['bytes'] for row in files),
        'source_linked_publication_exit_component_qualified': True, 'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False})
    print(json.dumps({'passed': True, 'files_before_inventory_receipt': len(files),
                      'bytes_before_inventory_receipt': sum(row['bytes'] for row in files),
                      'inventory': pin(D / 'archive_inventory_v1.json'), 'QA': pin(D / 'postrun/final_QA_v1.json')}))


if __name__ == '__main__':
    main()
