#!/usr/bin/env python3
"""Final offline QA and create-only seal. Delivery receipt is the only later file."""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent


def need(value, reason):
    if not value:
        raise ValueError(reason)


def load(path):
    return json.loads(path.read_bytes())


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, obj):
    with path.open('x') as stream:
        json.dump(obj, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    initial = load(D / 'preflight/workspace_initial_local_v1.json')
    final = load(D / 'preflight/workspace_final_local_v1.json')
    need(initial['passed'] and final['passed'], 'old_asset_preservation')
    for row in [initial, final]:
        need(row['protection']['unique_raw_files_reread'] == 43114
             and row['protection']['logical_bytes_streamed'] == 5382874541
             and row['protection']['full_local_current_byte_sha_recheck'] is True, 'complete_old_local_scope')
        need(row['workspace_after']['staged_all_diff_bytes'] == 0, 'staging_changed')
    checks = load(D / 'verification/targeted_offline_checks_v3.json')
    audit = load(D / 'verification/existing_runs_audit_v1.json')
    cli = load(D / 'verification/driver_import_and_CLI_v2.json')
    need(checks['passed'] and checks['targeted_rejected'] == 25 and checks['adapter_cases'] == 9
         and len(checks['unchanged_copied_parent_files']) == 199
         and checks['old_normal_close_branch_byte_identical'] and len(checks['finalization_cases']) == 8, 'final_targeted_checks')
    need(audit['passed'] and audit['inputs_unchanged'] and audit['input_sha256_before'] == audit['input_sha256_after']
         and len(audit['input_sha256_before']) == 223 and audit['actual_new_runs'] == 0, 'existing_raw_audit')
    for path, expected in audit['input_sha256_before'].items():
        need(pin(Path(path)) == expected, 'audit_input_changed:' + path)
    need(cli['passed'] and cli['ROS_context_initialized'] is False
         and pin(D / 'author/prepare_pair_wakeup_v1.py')['sha256'] == cli['driver_sha256']
         and pin(D / 'author/fault_self_close_v1.py')['sha256'] == cli['fault_helper_sha256'], 'current_driver_not_tested')
    sys.path.insert(0, str(D / 'implementation'))
    from check_fault_self_close_v1 import check
    reports = []
    for run, strict in [('v1_sink_01', False), ('v1_sink_ack_02', True)]:
        current = check(load(D / 'evidence' / (run + '_normalized_v1.json')))
        need(current == load(D / 'verification' / (run + '_fault_closure_v1.json'))
             and current['original_V1_strict_order_passed'] is strict
             and current['original_normal_status'] is False and current['normal_close_qualified'] is False
             and current['new_driver_executed_live'] is False, 'historical_scope_or_result_changed')
        reports.append(current)
    plan = load(D / 'preflight/V2_interface_scope_v1.json')
    need(plan['planned_not_executed'] and not plan['native_C_hang_injection_available'], 'V2_scope')
    for path, expected in plan['source_pins'].items():
        need(pin(Path(path)) == expected, 'V2_interface_input_changed')
    tested_paths = ['author/prepare_pair_wakeup_v1.py', 'author/fault_self_close_v1.py',
                    'implementation/check_fault_self_close_v1.py', 'audit_existing_runs_v1.py',
                    'test_fault_self_close_v1.py']
    tested = {p: pin(D / p) for p in tested_paths}
    for p in tested_paths:
        compile((D / p).read_text(), str(D / p), 'exec')
    final_qa = {'schema': 'SchemeA-batch34-final-offline-QA/v1', 'passed': True,
        'passed_scope': 'archive integrity, existing-raw fault closure audit and offline driver/component checks',
        'old_local_paths_rechecked': 43114, 'old_local_bytes_rechecked': 5382874541,
        'normal_close_qualified': False, 'original_normal_reports_both_false': True,
        'original_V1_first_gate': False, 'original_V1_repaired_gate': True,
        'actual_new_control_runs': 0, 'CXX_builds': 0, 'new_driver_executed_live': False,
        'retrospective_fault_close_cases': 2, 'targeted_rejected': 25, 'adapter_cases': 9, 'finalization_cases': 8,
        'unchanged_copied_parent_files': 199, 'original_normal_close_branch_byte_identical': True,
        'tested_source_pins': tested, 'V2_interface_plan_not_execution': True,
        'old_asset_initial_pin': pin(D / 'preflight/workspace_initial_local_v1.json'),
        'old_asset_final_pin': pin(D / 'preflight/workspace_final_local_v1.json'),
        'current_MPC_delivery_pending_at_QA': True, 'delivery_authority': 'delivery_verification.json',
        'stage_qualified': False, 'execute_qualified': False, 'true_plant_qualified': False,
        'research_conclusion': False}
    write(D / 'postrun/final_QA_v1.json', final_qa)
    write(D / 'postrun/retrospective_v1.json', {
        'actual_observation': 'Both archived shutdown_zero commands join successful per-side APIs, exact Fixture GID and full Stored values; old normal close failures retained.',
        'causal_limit': 'Witness closure does not timestamp process exit. Old r2 cleanup record order differs from the new driver.',
        'review_repair': 'Candidate metadata now reports actual explicit fault cleanup order; initial source/checks retained.',
        'next_experiment_scope': 'Separate pre-native work-thread block/active watchdog from capability callback receipt lease. No acados internal-hang claim.',
        'unnecessary_repeat_avoided': 'No new V1 live run, weight/RTI change or old base-component matrix.',
        'EDA_PPA_and_timing_signoff': 'not applicable to this local control research offline batch',
        'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False})
    write(D / 'batch_status_final.json', {
        'batch': 34, 'status': 'offline_fault_close_implementation_and_existing_raw_audit_complete',
        'component_verified': True, 'new_driver_executed_live': False, 'actual_new_control_runs': 0,
        'normal_close_qualified': False, 'original_failures_preserved': True,
        'next': 'V2 minimal implementation/preflight for separate active watchdog and receipt lease',
        'MPC_delivery_authority': 'delivery_verification.json',
        'stage_qualified': False, 'execute_qualified': False, 'true_plant_qualified': False, 'research_conclusion': False})
    directories, files = [], []
    for path in sorted(D.rglob('*')):
        need(not path.is_symlink(), 'archive_symlink')
        relative = str(path.relative_to(D))
        if path.is_dir():
            directories.append(relative)
        else:
            need(relative not in ['archive_inventory_v1.json', 'delivery_verification.json'], 'already_sealed')
            files.append({'relative_path': relative, **pin(path)})
    write(D / 'archive_inventory_v1.json', {
        'schema': 'SchemeA-create-only-local-archive/v1', 'created_monotonic_ns': time.monotonic_ns(),
        'files': files, 'directories': directories, 'inventory_excludes_itself': True,
        'optional_postseal_files': ['delivery_verification.json'], 'stage_qualified': False,
        'execute_qualified': False, 'research_conclusion': False})
    print(json.dumps({'passed': True, 'files_including_inventory': len(files) + 1,
                      'bytes_including_inventory': sum(r['bytes'] for r in files) + (D / 'archive_inventory_v1.json').stat().st_size,
                      'inventory_sha256': pin(D / 'archive_inventory_v1.json')['sha256'], 'actual_new_runs': 0}))


if __name__ == '__main__':
    main()
