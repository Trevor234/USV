#!/usr/bin/env python3
"""Create-only archive of this exact authorized research batch, with SHA readback."""
import argparse, hashlib, json, os, stat, subprocess
from pathlib import Path

D = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10')
M = Path('/home/trevor/MPC/scheme_A_C3_5_20261013_10')
W = Path('/home/trevor/USV')
P = D.parent / 'scheme_A_C3_4_20261013_09'
INVENTORY = D / 'archive_inventory_v1.json'

def require(value, message):
    if not value:
        raise ValueError(message)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def plain_parents(path):
    require(path.is_absolute() and '..' not in path.parts, 'normalized_absolute_path')
    for parent in path.parents:
        require(not parent.is_symlink(), 'symlink_parent:' + str(parent))

def raw_stable(path):
    path = Path(path)
    plain_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 128 * 1024 * 1024, 'bounded_regular_file')
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            require(size <= before.st_size, 'read_size_changed')
            chunks.append(chunk)
        after = os.fstat(fd)
        named = path.lstat()
        key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(key(before) == key(after) == key(named) and size == before.st_size, 'unstable_named_file')
        return b''.join(chunks), stat.S_IMODE(before.st_mode)
    finally:
        os.close(fd)

def new_bytes(path, raw, mode=0o644):
    plain_parents(path)
    with path.open('xb') as f:
        f.write(raw)
        os.fchmod(f.fileno(), mode & 0o777)
        f.flush()
        os.fsync(f.fileno())
    require(raw_stable(path)[0] == raw, 'new_file_readback')

def new_json(path, value):
    new_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode())

def protected():
    qa = json.loads(raw_stable(D / 'postrun/final_closure_QA.json')[0])
    for path, expected in qa['fixed_before_after_hashes'].items():
        require(digest(raw_stable(path)[0]) == expected, 'protected_final_input_changed:' + path)
    baseline = json.loads(raw_stable(P / 'postrun/preserved_assets.json')[0])
    for path, expected in baseline['pins'].items():
        # These are explicitly declared historical content paths, including
        # intended links. Their link identities are checked separately below.
        require(digest(Path(path).read_bytes()) == expected, 'declared_support_changed:' + path)
    support = json.loads((W / '.sgh-research/repairs/remaining_drift_20261010_01/SIM_SHARED_SUPPORT_20261010_01.json').read_text())
    for entry in support['assets']:
        path = Path(entry['path'])
        require(str(path.resolve()) == entry['resolved_path'], 'support_resolved_path_changed')
        require((os.readlink(path) if path.is_symlink() else None) == entry['link_target'], 'support_link_changed')
        if entry['sha256'] is None:
            require(path.is_dir(), 'support_directory_missing')
        else:
            require(digest(path.read_bytes()) == entry['sha256'], 'support_bytes_changed')
    diff = subprocess.check_output(['git', 'diff', '--binary', '--', ':(exclude).gitignore'], cwd=W)
    require(len(diff) == 151961 and digest(diff) == qa['original_business_diff_sha256'], 'original_business_diff_changed')
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=W, text=True).strip() == qa['HEAD'], 'HEAD_changed')
    require(subprocess.check_output(['git', 'branch', '--show-current'], cwd=W, text=True).strip() == qa['branch'], 'branch_changed')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == qa['boot_id'], 'boot_changed')
    frozen = json.loads(raw_stable(D / 'final_frozen_snapshot/manifest.json')[0])
    for pin in frozen['files']:
        for side in ('original', 'copy'):
            raw = raw_stable(pin[side])[0]
            require(digest(raw) == pin['sha256'] and len(raw) == pin['bytes'], 'new_frozen_pair_changed')
    return {'passed': True, 'N10_pairs': 355, 'declared_content_pins': len(baseline['pins']),
            'support_declarations': len(support['assets']), 'new_frozen_pairs': len(frozen['files']),
            'final_fixed_hash_paths': len(qa['fixed_before_after_hashes']),
            'business_diff_sha256': digest(diff), 'old_expected_updated': False,
            'scope': 'declared protected inputs only; no full-machine qualification'}

def prepare():
    require(Path(__file__).resolve() == D / 'archive_to_MPC_v1.py', 'archive_script_location')
    plain_parents(M)
    require(not M.exists() and not M.is_symlink(), 'fresh_MPC_batch_required')
    proof = protected()
    entries = []
    directories = []
    total = 0
    for root, dirs, files in os.walk(D, followlinks=False):
        for name in sorted(dirs):
            path = Path(root) / name
            require(stat.S_ISDIR(path.lstat().st_mode), 'archive_directory_link_or_special')
            directories.append(str(path.relative_to(D)))
        for name in sorted(files):
            path = Path(root) / name
            raw, mode = raw_stable(path)
            total += len(raw)
            entries.append({'relative_path': str(path.relative_to(D)), 'sha256': digest(raw), 'bytes': len(raw), 'mode': mode})
    entries.sort(key=lambda x: x['relative_path'])
    require(total < 512 * 1024 * 1024 and len(entries) < 5000, 'finite_archive_population')
    inventory = {'schema': 'scheme-A-C3.5-create-only-archive-inventory/v1', 'source_root': str(D),
                 'destination_root': str(M), 'entries': entries, 'directories': sorted(directories),
                 'regular_files': len(entries), 'bytes': total, 'symlinks': 0, 'special_files': 0,
                 'inventory_self_excluded': True, 'protected_before_prepare': proof,
                 'old_batches_overwritten': False}
    new_json(INVENTORY, inventory)
    print(json.dumps({'prepared': True, 'regular_files_excluding_inventory': len(entries), 'bytes': total,
                      'inventory_sha256': digest(raw_stable(INVENTORY)[0])}))

def deliver(expected_sha):
    require(Path(__file__).resolve() == D / 'archive_to_MPC_v1.py', 'archive_script_location')
    plain_parents(M)
    require(M.parent.is_dir() and not M.exists() and not M.is_symlink(), 'fresh_MPC_batch_required')
    inventory_raw = raw_stable(INVENTORY)[0]
    require(digest(inventory_raw) == expected_sha, 'prepared_inventory_identity')
    inventory = json.loads(inventory_raw)
    require(inventory['source_root'] == str(D) and inventory['destination_root'] == str(M), 'fixed_archive_scope')
    before = protected()
    planned = {x['relative_path'] for x in inventory['entries']} | {'archive_inventory_v1.json'}
    actual = set()
    for root, dirs, files in os.walk(D, followlinks=False):
        for name in dirs:
            require(stat.S_ISDIR((Path(root) / name).lstat().st_mode), 'new_directory_link')
        for name in files:
            actual.add(str((Path(root) / name).relative_to(D)))
    require(actual == planned, 'source_population_changed_since_prepare')
    M.mkdir(exist_ok=False)
    for relative in sorted(inventory['directories'], key=lambda x: (len(Path(x).parts), x)):
        path = Path(relative)
        require(not path.is_absolute() and '..' not in path.parts, 'normalized_relative_directory')
        (M / path).mkdir(exist_ok=False)
    total = 0
    for pin in inventory['entries']:
        relative = Path(pin['relative_path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'normalized_relative_file')
        raw, mode = raw_stable(D / relative)
        require(digest(raw) == pin['sha256'] and len(raw) == pin['bytes'] and mode == pin['mode'], 'archive_source_pin')
        new_bytes(M / relative, raw, mode)
        total += len(raw)
    new_bytes(M / INVENTORY.name, inventory_raw)
    for pin in inventory['entries']:
        relative = Path(pin['relative_path'])
        source_raw = raw_stable(D / relative)[0]
        copy_raw = raw_stable(M / relative)[0]
        require(digest(source_raw) == digest(copy_raw) == pin['sha256'], 'full_archive_second_readback')
    require(raw_stable(INVENTORY)[0] == raw_stable(M / INVENTORY.name)[0] == inventory_raw, 'inventory_copy_changed')
    after = protected()
    require(before == after, 'protection_audit_changed')
    verification = {'schema': 'scheme-A-C3.5-archive-delivery-verification/v1', 'passed': True,
                    'source_root': str(D), 'destination_root': str(M), 'inventory_sha256': expected_sha,
                    'regular_files_copied': len(inventory['entries']) + 1,
                    'copied_bytes': total + len(inventory_raw), 'full_second_SHA_readback': True,
                    'source_population_unchanged_before_metadata': True,
                    'protected_before': before, 'protected_after': after,
                    'two_final_metadata_files_per_root': ['delivery_verification.json', 'batch_status_final.json'],
                    'final_regular_files_per_root': len(inventory['entries']) + 3,
                    'old_batches_overwritten': False, 'old_expected_updated': False, 'failure_evidence_deleted': False}
    prepared = json.loads(raw_stable(D / 'batch_status_final_prepared.json')[0])
    final = dict(prepared, state='component_complete_archive_verified', delivery_verified=True,
                 delivery_verification=str(M / 'delivery_verification.json'),
                 qualifications=prepared['qualifications'])
    for root in (D, M):
        new_json(root / 'delivery_verification.json', verification)
        new_json(root / 'batch_status_final.json', final)
    for name in ('delivery_verification.json', 'batch_status_final.json'):
        require(raw_stable(D / name)[0] == raw_stable(M / name)[0], 'final_metadata_pair_readback')
    require(sum(1 for p in D.rglob('*') if p.is_file()) == verification['final_regular_files_per_root'], 'final_source_count')
    require(sum(1 for p in M.rglob('*') if p.is_file()) == verification['final_regular_files_per_root'], 'final_destination_count')
    print(json.dumps(verification, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'deliver'])
    parser.add_argument('--inventory-sha')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare()
    else:
        require(type(args.inventory_sha) is str and len(args.inventory_sha) == 64, 'inventory_SHA_required')
        deliver(args.inventory_sha)
