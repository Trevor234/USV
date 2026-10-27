#!/usr/bin/env python3
"""Read-only mainline baseline adoption; keep the user's exact MANUAL correction."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

D = Path(__file__).resolve().parents[1]
W = Path('/home/trevor/USV')
E = W / '.sgh-research/experiments'
P51 = E / 'scheme_B_MANUAL_contract_20261021_51'
EXPECTED = {
    'scheme_A_formal_execute_profile_20261020_47': ('668f89588e02de3ea1a0da8796982760ab1c9fc31e678dd65ce4093127b5b175', 396),
    'scheme_A_M4_recorder_bootstrap_20261021_49': ('7ca703b906bc95e154816ef591b9df6a8b5cadcdd4e2842b42ad3b254dbc87fc', 533),
    'scheme_A_M4_publication_faults_20261021_50': ('21aef89139f415b1aaad80c43ec74d34a6cb7123f4edd3bcff2255944b98a694', 262),
    'scheme_B_MANUAL_contract_20261021_51': ('77c5eb0f4dce18a04a455c647a3a7fbc8d9bc8c48d3fc25d4d6496dbd213d488', 282),
}


def pin(path):
    path = Path(path)
    before = path.stat()
    h = hashlib.sha256();size = 0
    with path.open('rb') as f:
        while raw := f.read(1024 * 1024):
            h.update(raw);size += len(raw)
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), str(path)
    return {'bytes': size, 'sha256': h.hexdigest()}


def git(args):
    return subprocess.check_output(['git', '--no-optional-locks', *args], cwd=W)


def workspace(delta):
    assert git(['rev-parse', 'HEAD']).decode().strip() == delta['HEAD']
    assert git(['status', '--porcelain=v1', '--branch', '--untracked-files=all']).decode() == delta['status_after']
    assert git(['diff', '--cached', '--binary']) == b''
    diff = git(['diff', '--binary'])
    assert {'bytes': len(diff), 'sha256': hashlib.sha256(diff).hexdigest()} == delta['tracked_patch']
    assert len(delta['tracked_changed_files']) == 11 and len(delta['new_files']) == 3
    for name, expected in delta['files_after'].items():
        assert pin(W / name) == expected, name
        assert pin(P51 / 'after' / name) == expected, name
    return {'HEAD': delta['HEAD'], 'branch': git(['branch', '--show-current']).decode().strip(),
            'status': delta['status_after'], 'tracked_patch': delta['tracked_patch'],
            'live_files': delta['files_after'], 'staging_empty': True,
            'whole_workspace_clean': False, 'old_untracked_and_submodule_state_retained': True}


def archive(name, expected_sha, count):
    root = E / name
    assert pin(root / 'archive_inventory_v1.json')['sha256'] == expected_sha
    inv = json.loads((root / 'archive_inventory_v1.json').read_bytes())
    for row in inv['files']:
        assert pin(root / row['relative_path']) == {k: row[k] for k in ['bytes', 'sha256']}, name + '/' + row['relative_path']
    files = set();dirs = set()
    for path in root.rglob('*'):
        assert not path.is_symlink(), str(path)
        (dirs if path.is_dir() else files).add(str(path.relative_to(root)))
    assert files == {row['relative_path'] for row in inv['files']} | {'archive_inventory_v1.json', 'delivery_verification.json'}
    assert dirs == set(inv['directories']) and len(files) == count
    receipt = json.loads((root / 'delivery_verification.json').read_bytes())
    assert receipt['passed'] and receipt['full_second_SHA_readback']
    return {'name': name, 'regular_files': count, 'inventory_sha256': expected_sha,
            'all_archived_members_checked': True, 'delivery_receipt': pin(root / 'delivery_verification.json')}


def installed():
    names = ['usv_mpc_ws/install/usv_bringup/share/usv_bringup/launch/real.launch.py',
             'usv_mpc_ws/install/usv_bringup/share/usv_bringup/config/mpc_params_B.yaml',
             'usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node',
             'usv_mpc_ws/install/usv_safety_cpp/lib/usv_safety_cpp/mode_manager_node']
    rows = []
    for name in names:
        path = W / name;target = path.resolve(strict=True);st = target.stat()
        row = {'path': str(path), 'resolved': str(target), 'is_symlink': path.is_symlink(),
               'link': os.readlink(path) if path.is_symlink() else None, **pin(target),
               'mtime_UTC': datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).isoformat()}
        if path.name == 'mpc_node':
            row['MANUAL_guard_marker_present'] = b'Scheme B rc_override requires allowed_fcu_modes=[MANUAL]' in target.read_bytes()
        if path.name == 'mode_manager_node':
            row['mode_target_marker_present'] = b'mpc_fcu_mode must be MANUAL (B) or GUIDED (kinematic A)' in target.read_bytes()
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser();ap.add_argument('--output', type=Path, required=True);args = ap.parse_args()
    assert args.output.is_absolute() and args.output.parent == D / 'evidence' and not args.output.exists()
    started = time.monotonic()
    out = {'schema': 'SchemeA-mainline-after-authorized-MANUAL-delta-baseline/v1', 'passed': False,
           'new_ROS_runs': 0, 'new_FCU_requests': 0, 'historical_archives_rewritten': False,
           'old_full_workspace_protection_invoked_or_falsely_projected_clean': False,
           'endpoint_qualification': False, 'real_ship_deployment_qualified': False,
           'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False}
    try:
        delta_path = P51 / 'postrun/current_workspace_delta_v1.json'
        assert pin(delta_path)['sha256'] == 'e9d5ca5b2bfe6b9fc53f62e8d3c4369864feb09e52824a03c70c35f64e00a74f'
        delta = json.loads(delta_path.read_bytes())
        before = workspace(delta)
        archives = [archive(name, sha, count) for name, (sha, count) in EXPECTED.items()]
        index_path = E / 'scheme_A_formal_execute_profile_20261020_47/freeze/freeze_index_v1.json'
        assert pin(index_path)['sha256'] == '1d750a7eeb32f379f2be5dd516533f6f785e091c6b30082dda68e51b3f100081'
        contract = E / 'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
        assert pin(contract)['sha256'] == '19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'
        index = json.loads(index_path.read_bytes())
        mismatches = []
        for row in index['artifacts']:
            actual = pin(Path(row['path']))
            expected = {k: row[k] for k in ['bytes', 'sha256']}
            if actual != expected:mismatches.append({'path': row['path'], 'expected': expected, 'actual': actual})
        current_install = installed()
        after = workspace(delta);assert before == after
        out.update(passed=not mismatches, workspace_before=before, workspace_after=after,
                   sealed_archives=archives, frozen47_actual_inputs_checked=len(index['artifacts']),
                   frozen47_mismatches=mismatches, current_install=current_install,
                   current_install_provenance_separate_from_51_historical_observation=True,
                   installation_markers_not_a_deployment_manifest=True)
    except Exception as e:
        out.update(error=repr(e), traceback=__import__('traceback').format_exc())
    out['elapsed_seconds'] = time.monotonic() - started
    with args.output.open('x') as f:json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True);f.write('\n')
    print(json.dumps({'passed': out['passed'], 'elapsed_seconds': out['elapsed_seconds'],
                      'frozen47_inputs': out.get('frozen47_actual_inputs_checked'),
                      'frozen47_mismatches': out.get('frozen47_mismatches'), 'error': out.get('error')}))
    return 0 if out['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
