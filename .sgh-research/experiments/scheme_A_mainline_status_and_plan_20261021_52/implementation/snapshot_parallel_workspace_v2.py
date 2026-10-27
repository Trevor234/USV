#!/usr/bin/env python3
"""Capture the user-confirmed parallel delta without granting untested code qualification."""
import datetime
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parents[1]
W = Path('/home/trevor/USV')
P51 = W / '.sgh-research/experiments/scheme_B_MANUAL_contract_20261021_51'


def git(*args):
    return subprocess.check_output(['git', '--no-optional-locks', *args], cwd=W)


def pin_bytes(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def emit(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True);f.write('\n')


def main():
    root = D / 'evidence/parallel_snapshot_v2';root.mkdir()
    base = json.loads((P51 / 'postrun/current_workspace_delta_v1.json').read_bytes())
    head = git('rev-parse', 'HEAD').decode().strip()
    status = git('status', '--porcelain=v1', '--branch', '--untracked-files=all').decode()
    patch = git('diff', '--binary')
    staged = git('diff', '--cached', '--binary')
    changed = git('diff', '--name-only').decode().splitlines()
    untracked = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
    selected = sorted(set(changed + untracked + list(base['files_after'])))
    rows = {};missing = []
    for name in selected:
        p = W / name
        if not p.exists():missing.append(name);continue
        if not p.is_file():continue  # Existing submodule status is recorded, not rewritten.
        assert not p.is_symlink(), name
        before = p.stat();raw = p.read_bytes();after = p.stat()
        assert (before.st_ino, before.st_mtime_ns, before.st_ctime_ns, before.st_size) == (after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size), name
        dest = root / 'files' / name;dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as f:f.write(raw)
        row = {**pin_bytes(raw), 'snapshot': str(dest.relative_to(D)),
               'mtime_UTC': datetime.datetime.fromtimestamp(after.st_mtime, datetime.timezone.utc).isoformat(),
               'in_51_verified_set': name in base['files_after']}
        if name in base['files_after']:
            row['same_as_51'] = pin_bytes(raw) == base['files_after'][name]
            old = (P51 / 'after' / name).read_bytes()
        elif name in changed:
            old = git('show', 'HEAD:' + name)
        else:
            old = None
        if old is not None and old != raw:
            diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), raw.decode().splitlines(True), fromfile='51_or_HEAD/' + name, tofile='parallel_snapshot/' + name))
            df = root / 'diffs' / (name + '.diff');df.parent.mkdir(parents=True, exist_ok=True)
            with df.open('x') as f:f.write(diff)
            row['difference_from_51_or_HEAD'] = str(df.relative_to(D))
        rows[name] = row
    assert git('rev-parse', 'HEAD').decode().strip() == head
    assert git('status', '--porcelain=v1', '--branch', '--untracked-files=all').decode() == status
    assert git('diff', '--binary') == patch and git('diff', '--cached', '--binary') == staged
    with (root / 'tracked_change.diff').open('xb') as f:f.write(patch)
    manifest = {'schema': 'user-confirmed-parallel-workspace-point-in-time-snapshot/v2',
                'captured_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'user_confirmed_other_task_is_modifying_workspace': True,
                'user_instruction': '有其他任务在修改，保留并标注',
                'HEAD': head, 'status': status, 'tracked_changed_files': changed, 'untracked_files': untracked,
                'tracked_patch': pin_bytes(patch), 'staged_patch': pin_bytes(staged), 'files': rows,
                '51_paths_currently_absent': missing,
                '51_verified_set_currently_identical': all(row.get('same_as_51', False) for name, row in rows.items() if name in base['files_after']) and not missing,
                'capture_consistent_during_read': True, 'parallel_changes_reverted_or_overwritten': False,
                'new_build_or_tests_run_for_parallel_changes': False,
                '51_checks_automatically_transferred_to_changed_code': False,
                'scope': 'snapshot at the recorded time; parallel work may continue afterwards'}
    emit(root / 'manifest.json', manifest)
    # Reuse only read-only archive/hash functions, never the old clean-workspace projection.
    spec = importlib.util.spec_from_file_location('mainline_asset_functions', D / 'implementation/adopt_mainline_baseline_v1.py')
    m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    archives = [m.archive(name, sha, count) for name, (sha, count) in m.EXPECTED.items()]
    index_path = m.E / 'scheme_A_formal_execute_profile_20261020_47/freeze/freeze_index_v1.json'
    assert m.pin(index_path)['sha256'] == '1d750a7eeb32f379f2be5dd516533f6f785e091c6b30082dda68e51b3f100081'
    index = json.loads(index_path.read_bytes());mismatches = []
    for row in index['artifacts']:
        actual = m.pin(Path(row['path']));expected = {k: row[k] for k in ['bytes', 'sha256']}
        if actual != expected:mismatches.append({'path': row['path'], 'expected': expected, 'actual': actual})
    install = m.installed()
    paths = {str((W / name).resolve(strict=False)) for name in rows}
    overlap = [row['path'] for row in index['artifacts'] if str(Path(row['path']).resolve()) in paths]
    out = {'schema': 'SchemeA-parallel-aware-mainline-evidence-checkpoint/v2',
           'passed': not mismatches, 'current_parallel_snapshot': str(root / 'manifest.json'),
           'snapshot_manifest_pin': m.pin(root / 'manifest.json'), 'sealed_archives': archives,
           'frozen47_actual_inputs_checked': len(index['artifacts']), 'frozen47_mismatches': mismatches,
           'workspace_changed_paths_overlap_frozen47': overlap, 'current_install': install,
           'old_strict51_workspace_guard_failure_retained': True,
           'unvalidated_parallel_changes_promoted_to_51_test_qualification': False,
           'whole_repository_clean_or_frozen': False, 'new_ROS_runs': 0, 'new_FCU_requests': 0,
           'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False}
    emit(D / 'evidence/parallel_aware_checkpoint_v2.json', out)
    print(json.dumps({'passed': out['passed'], 'snapshot_files': len(rows), 'tracked_changed': len(changed),
                      'missing_51_paths': missing, 'frozen47_mismatches': len(mismatches), 'frozen47_overlap': overlap,
                      'captured_UTC': manifest['captured_UTC']}, ensure_ascii=False))
    return 0 if out['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
