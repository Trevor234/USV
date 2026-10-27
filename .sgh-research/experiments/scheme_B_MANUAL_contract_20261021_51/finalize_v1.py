#!/usr/bin/env python3
"""Preserve the user-authorized live delta and seal its corrected-contract evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

D = Path(__file__).resolve().parent
W = Path('/home/trevor/USV')


def pin(p):
    h = hashlib.sha256()
    size = 0
    with Path(p).open('rb') as f:
        while b := f.read(1048576):
            h.update(b);size += len(b)
    return {'bytes': size, 'sha256': h.hexdigest()}


def emit(p, v):
    with p.open('x') as f:
        json.dump(v, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')


def git(args):
    return subprocess.check_output(['git', '--no-optional-locks', *args], cwd=W)


def main():
    assert not (D / 'archive_inventory_v1.json').exists()
    baseline = json.loads((D / 'preflight/workspace_and_source_before_v1.json').read_bytes())
    checks = json.loads((D / 'verification/contract_checks_v1.json').read_bytes())
    launch = json.loads((D / 'verification/launch_checks_v4.json').read_bytes())
    build = json.loads((D / 'build/attempt01/build_manifest_v1.json').read_bytes())
    assets = json.loads((D / 'evidence/SchemeA_asset_impact_v1.json').read_bytes())
    assert build['passed'] and launch['passed'] and assets['passed']
    assert checks['counts']['test_deadline_control']['tests'] == 18
    assert checks['counts']['test_mode_manager_contract']['tests'] == 6
    for row in checks['commands'][:2]:
        assert row['returncode'] == 0 and not any(row['counts'][k] for k in ['failures', 'errors', 'disabled', 'skipped'])
    assert launch['counts'] == {'tests': 6, 'failures': 0, 'errors': 0, 'skipped': 0}
    assert not checks['passed']  # First launch failure remains a failure.
    for name, row in build['source_after'].items():
        if Path(name).suffix in ['.cpp', '.hpp'] or name.endswith('usv_safety_cpp/CMakeLists.txt'):
            assert pin(name) == row, name
    for row in build['targets'].values():
        assert pin(row['path']) == {k: row[k] for k in ['bytes', 'sha256']}
    py = W / 'usv_mpc_ws/src/usv_bringup/test/test_fcu_mode_contract.py'
    assert pin(py)['sha256'] == launch['source_sha256']
    added = ['docs/scheme_B_manual_rc_contract.md',
             'usv_mpc_ws/src/usv_bringup/test/test_fcu_mode_contract.py',
             'usv_mpc_ws/src/usv_safety_cpp/test/test_mode_manager_contract.cpp']
    names = sorted(list(baseline['files']) + added)
    assert set(git(['diff', '--name-only']).decode().splitlines()) == set(baseline['files'])
    assert git(['diff', '--cached', '--binary']) == b''
    assert git(['rev-parse', 'HEAD']).decode().strip() == baseline['HEAD']
    status = git(['status', '--porcelain=v1', '--branch', '--untracked-files=all']).decode()
    old_lines = baseline['status_porcelain'].splitlines()
    assert all(line in status.splitlines() for line in old_lines)
    extras = [line for line in status.splitlines() if line not in old_lines]
    assert {line[3:] for line in extras} == set(names)
    after = {}
    for name in names:
        src = W / name;dest = D / 'after' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        after[name] = pin(src)
        assert pin(dest) == after[name]
    patch = git(['diff', '--binary'])
    with (D / 'evidence/authorized_mode_contract_change.diff').open('xb') as f:
        f.write(patch)
    emit(D / 'postrun/current_workspace_delta_v1.json', {
        'schema': 'user-authorized-SchemeB-MANUAL-live-workspace-delta/v1',
        'HEAD': baseline['HEAD'], 'status_before': baseline['status_porcelain'], 'status_after': status,
        'tracked_changed_files': sorted(baseline['files']), 'new_files': added, 'files_after': after,
        'tracked_patch': pin(D / 'evidence/authorized_mode_contract_change.diff'),
        'staging_unchanged_empty': True, 'commit_reset_stash_or_firmware_change': False,
        'existing_untracked_and_submodule_status_retained': True,
        'old_clean_projection_must_not_discard_this_user_authorized_delta': True})
    emit(D / 'evidence/launch_resolution_root_causes_v1.json', {
        'initial_failed_launch_evidence_preserved': True,
        'causes': ['launch evaluator returns tuple; test initially assumed list',
                   'disabled SITL Node condition was initially not filtered by the test',
                   'test default ROS log directory read-only in sandbox; fixture uses task temp',
                   'new real.launch mode override initially normalized as scalar string; fixed with explicit ParameterValue List[str]'],
        'corrected_configuration_array_type_and_exact_values_required': True,
        'CXX_tests_repeated': False, 'final_launch_checks_v4_passed': True,
        'FCU_started_or_requested': False})
    # Pytest creates convenience "current" aliases inside its own temp tree.
    # Preserve their mapping and dereferenced contents for the regular-file copier.
    links = []
    for p in sorted(D.rglob('*')):
        if p.is_symlink():
            target = p.resolve(strict=True)
            assert target.is_relative_to(D) and not p.is_relative_to(target)
            links.append({'path': str(p.relative_to(D)), 'original_link': os.readlink(p), 'target': str(target.relative_to(D))})
            p.unlink()
            if target.is_dir():
                shutil.copytree(target, p)
            else:
                shutil.copy2(target, p)
    emit(D / 'evidence/test_tmp_alias_preservation_v1.json', {'aliases': links, 'target_data_preserved': True, 'scope': 'new batch pytest-owned temp aliases only; old assets untouched'})
    proofs = ['verification/contract_checks_v1.json', 'verification/launch_checks_v4.json',
              'build/attempt01/build_manifest_v1.json', 'evidence/original_user_MANUAL_contract_v1.json',
              'evidence/firmware_control_flow_v1.json', 'evidence/SchemeA_asset_impact_v1.json',
              'postrun/current_workspace_delta_v1.json', 'evidence/launch_resolution_root_causes_v1.json']
    emit(D / 'postrun/final_QA_v1.json', {
        'schema': 'SchemeB-MANUAL-RC-contract-correction-QA/v1', 'passed': True,
        'original_contract_MANUAL_RC_confirmed': True, 'live_source_and_config_corrected': True,
        'dynamic_controller_tests': 18, 'mode_manager_private_service_tests': 6,
        'effective_launch_and_yaml_tests': 6, 'total_current_passing_checks': 30,
        'built_corrected_nodes': 2, 'built_test_targets': 2,
        'launch_first_failures_preserved': True, 'wrong_scalar_override_caught_and_fixed_before_deployment': True,
        'real_FCU_requests': 0, 'real_ship_deployment_or_acceptance': False,
        'existing_install_binaries_replaced': False, 'new_binaries_isolated': True,
        'source_symlinked_launch_and_yaml_changes_visible_to_install': True,
        'frozen47_inputs_verified': 4103, 'frozen49_and50_archives_preserved': True,
        'research_M4_F6_P1_promoted': False, 'old_real_B_firmware_mode_qualified': False,
        'tracked_files_changed': 11, 'new_files': 3, 'authorized_live_delta_preserved': True,
        'models_cost_weights_RTI_mapping_or_firmware_tuned': False,
        'proofs': {name: pin(D / name) for name in proofs}})
    files = [];directories = []
    for p in sorted(D.rglob('*')):
        assert not p.is_symlink(), str(p)
        if p.is_dir():directories.append(str(p.relative_to(D)))
        else:files.append({'relative_path': str(p.relative_to(D)), **pin(p)})
    emit(D / 'archive_inventory_v1.json', {
        'schema': 'SchemeB-MANUAL-correction-archive/v1', 'files': files, 'directories': directories,
        'file_count_before_inventory_receipt': len(files), 'bytes_before_inventory_receipt': sum(r['bytes'] for r in files),
        'source_contract_corrected_and_verified': True, 'real_ship_deployed': False,
        'M4_F6_P1_qualified': False})
    print(json.dumps({'passed': True, 'files_before_inventory_receipt': len(files), 'inventory': pin(D / 'archive_inventory_v1.json'), 'QA': pin(D / 'postrun/final_QA_v1.json')}))


if __name__ == '__main__':
    main()
