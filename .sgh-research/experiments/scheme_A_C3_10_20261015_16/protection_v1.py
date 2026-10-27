#!/usr/bin/env python3
"""Once-recomputed parent semantics plus flat, full-byte preservation roster."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
P = D.parent / 'scheme_A_C3_9_20261014_15'
M = Path('/home/trevor/MPC') / P.name
PIN = {
    'archive_inventory_v1.json': '7fd313c1f567652869251b933fbd7df679e41a680a83e9ef07080bc2faa74da8',
    'postrun/final_QA_current.json': '63fa780b77a88c0d6ddd5bb22ec35b3c5aa12dd968c8878fac47a61b2039030d',
    'delivery_verification.json': 'bc10a49955e242ddb8534c7a1f049677442208bf54afe5646073404e63b9c110',
    'batch_status_final.json': 'fc32d46a542d25f0b2ee6c652ea8b740eb6c38ed0b8a1aa98e2aac6db81040c4',
    'archive_v1.py': '3e9a97187aeddcd17db5e21ac74e4fceb5c9bbaae2c0420d9f7ad997dc7a8604',
    'protection_v1.py': '6f9de8644fe8418a40d3d4fa5bdd3442752cdab5e1059001f8ecfb5230584773',
}
ROSTER = D / 'preflight/preservation_roster_v1.json'
ANCHOR = D / 'preflight/preservation_anchor_v1.json'
sys.path.insert(0, str(D.parent / 'p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11'))
import acceptance_core_v1 as C


def canon(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def write_new(path, value):
    raw = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode() + b'\n'
    with path.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    C.require(path.read_bytes() == raw, 'new_evidence_readback')


def workspace():
    spec = importlib.util.spec_from_file_location('c310_workspace_parent', P / 'protection_v1.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.workspace()


def stable_sha(path):
    """Component-wise O_NOFOLLOW stable FD streaming read; never caches file bytes."""
    p = Path(path)
    C.require(p.is_absolute() and '..' not in p.parts, 'absolute_normalized_path')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        for part in p.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(p.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(fd)
        C.require(stat.S_ISREG(before.st_mode), 'regular_input_required:' + str(p))
        h = hashlib.sha256()
        size = 0
        while True:
            raw = os.read(fd, 1024 * 1024)
            if not raw:
                break
            h.update(raw)
            size += len(raw)
        after = os.fstat(fd)
        named = os.stat(p.name, dir_fd=directory, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        C.require(identity(before) == identity(after) == identity(named) and size == before.st_size,
                  'input_changed_during_stream:' + str(p))
        return {'sha256': h.hexdigest(), 'bytes': size, 'mode': stat.S_IMODE(before.st_mode)}
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def directory_entries(path):
    p = Path(path)
    C.require(not any(x.is_symlink() for x in (p, *p.parents)), 'directory_symlink')
    rows = []
    with os.scandir(p) as entries:
        for entry in entries:
            s = entry.stat(follow_symlinks=False)
            C.require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode), 'sealed_population_special')
            rows.append([entry.name, 'file' if stat.S_ISREG(s.st_mode) else 'directory'])
    return sorted(rows)


def population(root):
    files, directories = set(), set()
    for base, ds, fs in os.walk(root, followlinks=False):
        for name in ds:
            p = Path(base) / name
            C.require(stat.S_ISDIR(p.lstat().st_mode), 'sealed_directory_special')
            directories.add(str(p.relative_to(root)))
        for name in fs:
            p = Path(base) / name
            C.require(stat.S_ISREG(p.lstat().st_mode), 'sealed_file_special')
            files.add(str(p.relative_to(root)))
    return files, directories


def parent_inventory():
    r = C.Reader(seconds=1800, max_bytes=3 * 1024**3, max_files=30000)
    for rel, digest in PIN.items():
        C.require(C.digest(r.raw(P / rel)) == digest, 'fixed_parent_metadata:' + rel)
    inv = r.json(P / 'archive_inventory_v1.json')
    delivery = r.json(P / 'delivery_verification.json')
    qa = r.json(P / 'postrun/final_QA_current.json')
    C.require(len(inv['files']) == 3161 and delivery['passed'] and delivery['full_second_SHA_readback']
              and delivery['final_regular_files_per_root'] == 3164, 'complete_parent_archive_scope')
    C.require(qa['passed'] and qa['native_count'] == 251 and qa['new_frozen_pairs'] == 2559
              and len(qa['fixed_source_header_input_hashes']) == 5119, 'parent_QA_scope')
    expected = {'archive_inventory_v1.json', 'delivery_verification.json', 'batch_status_final.json'}
    for pin in inv['files']:
        rel = Path(pin['relative_path'])
        C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in expected, 'parent_relative_unique')
        expected.add(str(rel))
        for root in (P, M):
            r.verify({'path': str(root / rel), 'sha256': pin['sha256'], 'bytes': pin['bytes']})
    for rel in ('archive_inventory_v1.json', 'delivery_verification.json', 'batch_status_final.json'):
        C.require(r.raw(P / rel) == r.raw(M / rel), 'parent_metadata_pair')
    for root in (P, M):
        C.require(population(root) == (expected, set(inv['directories'])), 'complete_parent_population')
    C.require(r.unchanged(), 'parent_changed_during_read')
    return inv, delivery, qa, r.hashes


def capture():
    """Run once before any test. Imported unchanged parent code decides semantic success."""
    C.require(not ROSTER.exists() and not ANCHOR.exists(), 'fresh_preservation_capture_required')
    before = workspace()
    for rel, digest in PIN.items():
        C.require(stable_sha(P / rel)['sha256'] == digest, 'fixed_parent_metadata:' + rel)
    trace = D / 'preflight/parent_read_trace_v1'
    trace.mkdir(exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(D / 'preservation_trace') + os.pathsep + str(Path(C.__file__).parent),
               C310_TRACE_DIRECTORY=str(trace))
    code = 'import sys,json;sys.dont_write_bytecode=True;sys.path.insert(0,' + repr(str(P)) + ');import archive_v1;print(json.dumps(archive_v1.protect(),sort_keys=True))'
    started = time.monotonic()
    run = subprocess.run([sys.executable, '-B', '-c', code], env=env, capture_output=True, timeout=2400)
    C.require(len(run.stdout) <= 32 * 1024 * 1024 and len(run.stderr) <= 4 * 1024 * 1024, 'finite_parent_output')
    (D / 'preflight/parent_recompute_stderr_v1.log').write_bytes(run.stderr)
    C.require(run.returncode == 0, 'parent_recompute_failed:' + run.stderr.decode(errors='replace')[-3000:])
    proof = C.strict_json(run.stdout)
    write_new(D / 'preflight/parent_recomputed_proof_v1.json', proof)
    inv, delivery, qa, parent_hashes = parent_inventory()
    C.require(proof == inv['protection'] == inv['protection_after_prepare']
              == delivery['protected_before'] == delivery['protected_after'], 'parent_semantic_proof_identity')
    files, directories, starts, ends, children = set(parent_hashes), set(), set(), set(), set()
    exact_read_pins = dict(parent_hashes)
    trace_files = sorted(trace.glob('*.jsonl'))
    C.require(bool(trace_files), 'parent_trace_required')
    for log in trace_files:
        for line in log.read_bytes().splitlines():
            row = C.strict_json(line)
            if row['event'] == 'file':
                files.add(row['path'])
            elif row['event'] == 'verified_read':
                files.add(row['path'])
                C.require(row['path'] not in exact_read_pins or exact_read_pins[row['path']] == row['sha256'],
                          'traced_Reader_bytes_differ_between_processes')
                exact_read_pins[row['path']] = row['sha256']
            elif row['event'] == 'directory':
                directories.add(row['path'])
            elif row['event'] == 'start':
                starts.add(row['pid'])
            elif row['event'] == 'end':
                ends.add(row['pid'])
            elif row['event'] == 'python_child':
                children.add(row['child_pid'])
    C.require(starts == ends and children <= starts and len(starts - children) == 1,
              'all_python_descendants_traced_to_exit')
    # Explicit additions bind the current parent all declared source/dependency paths and frozen originals/copies.
    files.update(qa['fixed_source_header_input_hashes'])
    frozen = C.Reader().json(P / 'final_frozen_snapshot/manifest.json')
    C.require(len(frozen['files']) == 2559, 'parent_frozen_population')
    for row in frozen['files']:
        files.update((row['original'], row['copy']))
    for root in (P, M):
        for base, ds, fs in os.walk(root, followlinks=False):
            directories.add(base)
            files.update(str(Path(base) / name) for name in fs)
    file_pins = {}
    for path in sorted(files):
        pin = stable_sha(path)
        if path in exact_read_pins:
            C.require(pin['sha256'] == exact_read_pins[path], 'captured_parent_bytes_changed')
        if path in qa['fixed_source_header_input_hashes']:
            C.require(pin['sha256'] == qa['fixed_source_header_input_hashes'][path], 'parent_fixed_bytes_changed')
        file_pins[path] = pin
    dir_pins = {path: directory_entries(path) for path in sorted(directories)}
    after = workspace()
    C.require(before == after, 'workspace_changed_during_capture')
    roster = {'schema': 'C3.10-flat-preservation-roster/v1', 'files': file_pins, 'directories': dir_pins,
              'parent_proof_sha256': C.digest(canon(proof)), 'parent_inventory_sha256': PIN['archive_inventory_v1.json'],
              'parent_QA_sha256': PIN['postrun/final_QA_current.json'], 'parent_archive_pairs': 3164,
              'parent_fixed_QA_paths': 5119, 'parent_frozen_pairs': 2559, 'initial_workspace': after,
              'capture_methods': ['CPython open audit', 'returned file descriptor', 'directory enumeration audit',
                                  'exact Reader returned bytes', 'explicit complete parent inventory', 'explicit parent QA/frozen lists'],
              'python_processes_traced': len(starts), 'python_children_traced': len(children),
              'parent_semantics_fully_recomputed_once': True, 'raw_byte_checks_replaced_with_metadata': False,
              'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}
    write_new(ROSTER, roster)
    write_new(ANCHOR, {'schema': 'C3.10-preservation-anchor/v1', 'roster_sha256': stable_sha(ROSTER)['sha256'],
                      'parent_proof_sha256': roster['parent_proof_sha256'], 'capture_seconds': time.monotonic() - started,
                      'trace_file_sha256': {str(p): stable_sha(p)['sha256'] for p in trace_files},
                      'helper_sha256': stable_sha(Path(__file__))['sha256'],
                      'tracer_sha256': stable_sha(D / 'preservation_trace/sitecustomize.py')['sha256'],
                      'stage_qualified': False, 'research_conclusion': False})
    return protect()


def protect():
    anchor = C.Reader().json(ANCHOR)
    C.require(stable_sha(ROSTER)['sha256'] == anchor['roster_sha256'], 'flat_roster_identity_changed')
    C.require(stable_sha(Path(__file__))['sha256'] == anchor['helper_sha256'], 'preservation_helper_changed')
    C.require(stable_sha(D / 'preservation_trace/sitecustomize.py')['sha256'] == anchor['tracer_sha256'], 'preservation_tracer_changed')
    roster = C.Reader().json(ROSTER)
    C.require(roster['parent_inventory_sha256'] == PIN['archive_inventory_v1.json']
              and roster['parent_QA_sha256'] == PIN['postrun/final_QA_current.json']
              and roster['parent_proof_sha256'] == anchor['parent_proof_sha256'], 'fixed_parent_anchor_identity')
    before = workspace()
    C.require(before == roster['initial_workspace'], 'workspace_changed_since_initial')
    for path, pin in roster['files'].items():
        C.require(stable_sha(path) == pin, 'flat_preservation_file_changed:' + path)
    for path, entries in roster['directories'].items():
        C.require(directory_entries(path) == entries, 'flat_preservation_population_changed:' + path)
    C.require(workspace() == before, 'workspace_changed_during_verification')
    return {'schema': 'C3.10-preservation/v1', 'passed': True,
            'parent_inventory_sha256': PIN['archive_inventory_v1.json'], 'parent_QA_sha256': PIN['postrun/final_QA_current.json'],
            'parent_archive_pairs': 3164, 'parent_fixed_QA_paths': 5119, 'parent_frozen_pairs': 2559,
            'parent_chain_proof_sha256': roster['parent_proof_sha256'], 'parent_chain_fully_recomputed_at_initial_capture': True,
            'flat_roster_sha256': anchor['roster_sha256'], 'unique_raw_files_reread': len(roster['files']),
            'directory_populations_rechecked': len(roster['directories']), 'full_raw_byte_sha_recheck': True,
            'HEAD': before['HEAD'], 'branch': before['branch'], 'boot_id': before['boot_id'],
            'business_tracked_count': 24, 'business_diff_bytes': 151961, 'business_diff_sha256': before['business_diff_sha256'],
            'actual_Witness_normal_business': False, 'normal_business_contract_qualified': False,
            'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['capture', 'verify'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    C.require(args.output.is_absolute() and args.output.parent == D / 'preflight', 'new_preflight_output_only')
    start = time.monotonic()
    try:
        b = workspace()
        proof = capture() if args.mode == 'capture' else protect()
        result = {'passed': True, 'protection': proof, 'workspace_before': b, 'workspace_after': workspace(),
                  'elapsed_seconds': time.monotonic() - start, 'endpoints_checked': False,
                  'stage_qualified': False, 'research_conclusion': False}
    except Exception as e:
        result = {'passed': False, 'error': repr(e), 'elapsed_seconds': time.monotonic() - start,
                  'stage_qualified': False, 'research_conclusion': False}
    write_new(args.output, result)
    print(json.dumps({'passed': result['passed'], 'error': result.get('error'), 'output': str(args.output),
                      'elapsed_seconds': result['elapsed_seconds']}, sort_keys=True))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
