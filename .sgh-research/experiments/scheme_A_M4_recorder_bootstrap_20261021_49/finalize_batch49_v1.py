#!/usr/bin/env python3
"""Create-only evidence QA and archive seal; component success is not stage release."""
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
P47 = D.parent / 'scheme_A_formal_execute_profile_20261020_47'


def load(path):
    return json.loads(path.read_bytes())


def pin(path):
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        while data := stream.read(1024 * 1024):
            h.update(data)
            size += len(data)
    return {'bytes': size, 'sha256': h.hexdigest()}


def emit(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(data)


def check_map(values):
    for name, expected in values.items():
        actual = pin(Path(name))
        assert actual == {k: expected[k] for k in actual}, name


def main():
    assert not (D / 'archive_inventory_v1.json').exists(), 'already sealed'
    assert not (D / 'delivery_verification.json').exists(), 'already delivered'
    for path in D.rglob('*'):
        assert not path.is_symlink(), str(path)
        assert path.is_dir() or path.is_file(), str(path)

    a = load(D / 'postrun/actual_normal_audit_v1.json')
    c = load(D / 'verification/component_verification_v1.json')
    n = load(D / 'verification/native_entry_rejections_v1.json')
    p = load(D / 'verification/recorder_process_verification_v1.json')
    b = load(D / 'build/m4_attempt01/build_manifest_v1.json')
    launch = load(D / 'evidence/normal_launch_v1.json')
    registration = load(D / 'implementation/normal_registration_v1.json')
    before = load(D / 'preflight/workspace_initial_v1.json')
    after = load(D / 'preflight/workspace_final_v2.json')
    f47 = load(D / 'preflight/frozen47_verification_v1.json')
    callback = load(D / 'postrun/callback_capture_scope_v1.json')
    source = load(D / 'verification/source_core_reuse_v1.json')
    loader = load(D / 'verification/actual_loader_closure_v1.json')

    assert all(j['passed'] for j in [a, c, n, p, b, launch, before, after, f47, source, loader])
    assert c['native_policy_cases'] == 52
    assert c['GTest_XML']['tests'] == 38 and c['GTest_XML']['failures'] == c['GTest_XML']['errors'] == 0
    assert n['case_count'] == p['case_count'] == 14
    assert p['Recorder_returncode'] == 2 and p['Recorder_signals'] == ['SIGINT'] and p['group_empty']
    assert not p['full_recording_ready_proven'] and p['control_API_calls'] == n['control_API_calls'] == 0
    assert len(b['targets']) == 6 and b['source_before_after_equal']
    assert not b['install_performed'] and not b['codegen_performed']
    assert a['normal_owned_outlet_component_qualified'] and a['actual_control_API_calls'] == 210 and a['physical_API_pairs'] == 105
    assert a['normal_window']['dynamic_jobs'] == 101 and a['normal_window']['accepted'] == a['normal_window']['decisions'] == 100
    assert a['normal_window']['source_span_ns'] >= registration['source_window_ns'] == 20_000_000_000
    assert a['startup_full_recorder_before_grant_before_API'] and not a['first_pair_rho_available']
    assert a['shutdown_zero_API_success'] and a['actual_roles'] == 4 and a['all_roles_RC0_INT_only_group_empty']
    assert max(a['full_stream_max_per_side_gap_ns']) <= 240_000_000
    assert a['full_stream_max_pair_span_ns'] <= 5_000_000 and a['max_tick_start_jitter_ns'] <= 20_000_000
    assert max(a['max_actual_per_side_rate_n_s']) <= 80
    assert a['stored_messages'] == 4053 and a['wire_transport_matched_messages'] == 4052
    assert a['external_storage_accounting_passed'] and a['typed_Source_and_actual_Stored_matched']
    assert a['one_capability_after_Fixture_close_explicitly_accounted'] and a['Recorder_internal_storage_accounting_flag_retained_false']
    assert a['Witness_observation_complete'] and a['Witness_profile_label'] == 'closed_shadow_observation'
    assert not callback['claim_all_DDS_publications_reached_Regulator'] and callback['unexplained_Stored_loss'] == 0
    assert callback['fixture_clock_publications'] == 1076 and callback['Regulator_clock_callbacks'] == 1061
    assert sum(callback['breakdown'].values()) == callback['not_received_by_Regulator_callbacks'] == 15
    assert all(not a[k] for k in ['M4_stage_qualified', 'F6_qualified', 'P1_qualified', 'ordinary_production_release_enabled', 'original_F5_plant_reference_identity_qualified', 'plant_zero_or_hold_end_proven', 'research_conclusion'])
    assert registration['automatic_retries'] == 0 and not registration['fault_injection_enabled']
    assert launch['driver_result']['elapsed_seconds'] <= registration['max_seconds'] == 45
    assert launch['elapsed_seconds'] <= registration['outer_timeout_seconds'] == 90
    assert not launch['driver_timed_out'] and launch['driver_returncode'] == 0
    assert all(not row['signals'] and row['group_empty'] for row in launch['emergency_cleanup'])
    assert len(a['prerun_input_sha256']) == 1840
    assert a['input_sha256_before'] == a['input_sha256_after'] and len(a['input_sha256_after']) == 41
    check_map(a['prerun_input_sha256'])
    check_map(a['input_sha256_after'])
    for target in b['targets'].values():
        assert pin(Path(target['path'])) == {k: target[k] for k in ['bytes', 'sha256']}
    assert f47['artifact_count'] == 4103 and f47['artifact_bytes'] == 373401307
    assert before['workspace_after'] == after['workspace_after']
    assert after['workspace_after']['live_tracked_diff_bytes'] == after['workspace_after']['staged_all_diff_bytes'] == 0
    assert after['workspace_after']['historical24_now_committed']

    matrix_path = P47 / 'freeze/M4_fault_matrix_v1.json'
    matrix = load(matrix_path)
    assert len(matrix['groups']) == 9
    groups = []
    for row in matrix['groups']:
        groups.append({**row, 'current_M4_qualified': False,
                       'batch49_status': 'normal-owned-outlet component passed; controlled recording faults pending' if row['id'] == 'actual_source_recording' else 'not fully qualified for this owned runtime',
                       'batch49_evidence': ['postrun/actual_normal_audit_v1.json'] if row['id'] == 'actual_source_recording' else []})
    emit(D / 'postrun/M4_current_fault_coverage_v1.json', {
        'schema': 'M4-current-owned-runtime-original-fault-coverage/v1',
        'parent_matrix': str(matrix_path), 'parent_matrix_pin': pin(matrix_path),
        'normal_owned_outlet_component_qualified': True, 'groups': groups,
        'new_controlled_fault_runs_this_batch': 0, 'M4_stage_qualified': False, 'P1_qualified': False,
        'existing_source_linked_tests_are_scoped_component_evidence_only': True,
        'all_groups_require_a_new_long_ROS_run': False,
        'first_next_focus': 'publication_exit and bootstrap/full-recorder-ready affected paths',
        'old39_42_identity_or_qualification_transferred_to_new_owner': False})
    emit(D / 'postrun/next_implementation_plan_v1.json', {
        'schema': 'M4-after-normal-current-faults-then-F6-P1/v1',
        'current_step_closed': 'isolated nominal normal sole owned outlet component',
        'normal_run': a['run_id'], 'normal_run_repeated': False,
        'parent_index_sha256': registration['index_sha256'],
        'parent_contract_sha256': registration['contract_sha256'],
        'automatic_next_ROS_run_registered': False,
        'steps': [
            {'order': 1, 'action': 'map original nine-group obligations to exact current source/bin and reused component evidence; register affected publication/exit and bootstrap/full-Recorder cases first',
             'gate': 'no parent archive edits; no fabricated middleware-failure claim from injected adapter returns'},
            {'order': 2, 'action': 'complete current-runtime fault cases and F5/current source/reference applicability obligations with appropriate deterministic tests or actual controlled triggers',
             'gate': 'case-specific source/bin/input hashes and finite budgets before launch; automatic retries0; exact fault exception flags; retain all failures'},
            {'order': 3, 'action': 'under sole execution chain prepare immutable finite numeric M0/M1, atomic model+plan commit at fixed tick, old/mixed rejection, saved-plan immutability and separate warmstart',
             'gate': 'existing NX8/NU2/N20/NP6/NP_GLOBAL30 numerical setters; no codegen/GP/PPO'},
            {'order': 4, 'action': 'bind final version/config/run/source/record and affected regressions; freeze F6 and perform original P1 joint review',
             'gate': 'normal component does not qualify faults, model transaction or P1; no half-RMSE or P2-certificate gate added'}],
        'do_not_repeat': ['successful batch49 normal run', 'closed45/46 preparation or source calibration', 'old39-42 faults without affected-code reason', 'new full no_output business stage'],
        'frozen_numbers_model_RTI_cost_thresholds_tuned': False,
        'ordinary_production_release_enabled': False,
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False, 'research_conclusion': False})

    proofs = ['postrun/actual_normal_audit_v1.json', 'postrun/callback_capture_scope_v1.json',
              'verification/component_verification_v1.json', 'verification/native_entry_rejections_v1.json',
              'verification/recorder_process_verification_v1.json', 'verification/source_core_reuse_v1.json',
              'verification/actual_loader_closure_v1.json', 'preflight/workspace_initial_v1.json',
              'preflight/workspace_final_v2.json', 'preflight/frozen47_verification_v1.json',
              'preflight/prerun_source_lock_v1.json', 'preflight/execution_tool_input_lock_v1.json',
              'build/m4_attempt01/build_manifest_v1.json', 'evidence/normal_launch_v1.json',
              'postrun/M4_current_fault_coverage_v1.json', 'postrun/next_implementation_plan_v1.json']
    emit(D / 'postrun/final_QA_v1.json', {
        'schema': 'SchemeA-M4-normal-owned-outlet-batch-integrity-QA/v1',
        'passed': True, 'batch_deliverable_integrity_passed': True,
        'qualification_layer': 'isolated nominal normal sole owned outlet component only',
        'normal_owned_outlet_component_qualified': True, 'actual_registered_normal_runs': 1,
        'actual_normal_run_passed': True, 'same_registration_retried': False,
        'normal_run_id': a['run_id'], 'actual_roles': 4, 'actual_control_API_calls': 210,
        'physical_API_pairs': 105, 'normal_window': a['normal_window'],
        'full_stream_max_per_side_gap_ns': a['full_stream_max_per_side_gap_ns'],
        'full_stream_max_pair_span_ns': a['full_stream_max_pair_span_ns'],
        'max_tick_start_jitter_ns': a['max_tick_start_jitter_ns'],
        'max_actual_per_side_rate_n_s': a['max_actual_per_side_rate_n_s'],
        'first_pair_rho_available': False, 'shutdown_zero_API_success': True,
        'all_roles_RC0_INT_only_group_empty': True, 'outer_emergency_signals_sent': 0,
        'native_policy_cases': 52, 'source_linked_GTest_cases': 38, 'native_entry_refusals': 14,
        'real_Recorder_process_pin_cases': 14, 'built_targets': 6,
        'real_Recorder_process_component_incomplete_RC2_retained': True,
        'external_storage_accounting_passed': True, 'stored_messages': 4053,
        'wire_transport_matched_messages': 4052, 'one_tail_capability_after_Fixture_close_accounted': True,
        'Recorder_internal_storage_accounting_flag_retained_false': True,
        'all_DDS_publications_received_by_Regulator_claimed': False,
        'Witness_qualification_scope': a['Witness_qualification_scope'],
        'registered_inputs_checked_unchanged': 1840, 'runtime_audit_inputs_checked_unchanged': 41,
        'frozen47_files_checked': 4103, 'B5_M0b_frozen_parent_preserved': True,
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'stage_qualified': False, 'ordinary_production_release_enabled': False,
        'original_F5_plant_reference_identity_qualified': False, 'plant_zero_or_hold_end_proven': False,
        'hard_realtime_or_WCET_qualified': False, 'GP_data_qualified': False, 'research_conclusion': False,
        'source_thresholds_model_RTI_cost_tuned': False,
        'workspace_resumed_HEAD': after['workspace_after']['HEAD'],
        'workspace_branch': after['workspace_after']['branch'],
        'main_repository_tracked_file_diff_and_staging_empty': True,
        'existing_status_porcelain_retained': after['workspace_after']['status_porcelain'],
        'existing_untracked_zcodeignore_and_submodule_status_retained': True,
        'whole_workspace_clean_claimed': False,
        'original24_now_committed_content_equal': True,
        'all_historical_original_paths_unchanged': False,
        'explicit_preexisting_path_changes': ['two pre_reference_prediction_v1 active backup headers absent; exact F5 bytes recovered in sealed48, active paths not restored', '.gitignore changed with resumed committed HEAD; old full bytes not reconstructed'],
        'old_failures_and_sealed_parents_retained': True,
        'final_preservation_interrupted_session_not_inferred_as_pass': True,
        'proofs': {name: pin(D / name) for name in proofs}})

    files = []
    directories = []
    for path in sorted(D.rglob('*')):
        assert not path.is_symlink(), str(path)
        if path.is_dir():
            directories.append(str(path.relative_to(D)))
        else:
            files.append({'relative_path': str(path.relative_to(D)), **pin(path)})
    emit(D / 'archive_inventory_v1.json', {
        'schema': 'SchemeA-M4-normal-owned-outlet-archive/v1', 'files': files,
        'directories': directories, 'file_count_before_inventory_receipt': len(files),
        'bytes_before_inventory_receipt': sum(row['bytes'] for row in files),
        'normal_owned_outlet_component_qualified': True,
        'actual_control_API_calls': 210, 'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False})
    print(json.dumps({'passed': True, 'files_before_inventory_receipt': len(files),
                      'bytes_before_inventory_receipt': sum(row['bytes'] for row in files),
                      'inventory': pin(D / 'archive_inventory_v1.json'),
                      'QA': pin(D / 'postrun/final_QA_v1.json'),
                      'normal_owned_outlet_component_qualified': True, 'M4_stage_qualified': False, 'P1_qualified': False}))


if __name__ == '__main__':
    main()
