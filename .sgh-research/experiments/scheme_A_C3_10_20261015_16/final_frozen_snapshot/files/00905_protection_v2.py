#!/usr/bin/env python3
"""Create-only completion of the successful v1 parent semantic capture.

Only two new untracked roots are excluded from status comparison; all other
workspace data and every old asset's complete bytes remain required stable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
import protection_v1 as V
C = V.C
P, M = V.P, V.M
ROSTER = D / 'preflight/preservation_roster_v2.json'
ANCHOR = D / 'preflight/preservation_anchor_v2.json'
NEW_ROOTS = (
    '.sgh-research/experiments/scheme_A_C3_10_20261015_16/',
    '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_10_20261015_v17/',
)


def projection(value):
    result = dict(value)
    rows = []
    for line in value['status_porcelain'].splitlines(keepends=True):
        path = line[3:]
        if path.startswith('"'):
            path = path[1:]
        if line.startswith('?? ') and any(path.startswith(prefix) for prefix in NEW_ROOTS):
            continue
        rows.append(line)
    result['status_porcelain'] = ''.join(rows)
    result['status_porcelain_sha256'] = C.digest(result['status_porcelain'].encode())
    return result


def stable_sha(path, expected=None):
    # Existing no-follow stable FD algorithm; bound the named size before opening.
    if expected is not None:
        C.require(Path(path).lstat().st_size == expected['bytes'], 'anchored_size_changed:' + str(path))
    return V.stable_sha(path)


def add_pin(pins, path, sha, size=None, mode=None):
    path = str(path)
    pin = {'sha256': sha}
    if size is not None:
        pin['bytes'] = size
    if mode is not None:
        pin['mode'] = mode
    if path in pins:
        for key in pin.keys() & pins[path].keys():
            C.require(pin[key] == pins[path][key], 'inconsistent_declared_asset:' + path)
        pins[path].update(pin)
    else:
        pins[path] = pin


def complete():
    C.require(not ROSTER.exists() and not ANCHOR.exists(), 'fresh_v2_completion_required')
    before = V.workspace()
    calibration = C.Reader().json(D / 'preflight/calibration_preservation_v1.json')
    C.require(calibration['passed'] and stable_sha(D / 'protection_v1.py')['sha256'] == calibration['helper_sha256']
              and stable_sha(D / 'preservation_trace/sitecustomize.py')['sha256'] == calibration['tracer_sha256'],
              'unchanged_successfully_calibrated_v1_capture_code')
    pins, file_paths, directories = {}, set(), set()
    provenance = {
        str(D / 'protection_v1.py'): calibration['helper_sha256'],
        str(D / 'protection_v2.py'): stable_sha(Path(__file__))['sha256'],
        str(D / 'preservation_trace/sitecustomize.py'): calibration['tracer_sha256'],
        str(D / 'preflight/calibration_preservation_v1.json'): stable_sha(D / 'preflight/calibration_preservation_v1.json')['sha256'],
    }
    for path, sha in calibration['trace_sha256'].items():
        provenance[path] = sha
    for rel, sha in V.PIN.items():
        C.require(stable_sha(P / rel)['sha256'] == sha, 'fixed_parent_metadata:' + rel)
        add_pin(pins, P / rel, sha)
    r = C.Reader(seconds=1200, max_bytes=512 * 1024**2, max_files=100)
    inv = r.json(P / 'archive_inventory_v1.json')
    delivery = r.json(P / 'delivery_verification.json')
    qa = r.json(P / 'postrun/final_QA_current.json')
    proof_path = D / 'preflight/parent_recomputed_proof_v1.json'
    proof = r.json(proof_path)
    C.require(proof == inv['protection'] == inv['protection_after_prepare']
              == delivery['protected_before'] == delivery['protected_after'], 'successful_original_parent_semantics')
    C.require(len(inv['files']) == 3161 and delivery['passed'] and delivery['full_second_SHA_readback']
              and delivery['final_regular_files_per_root'] == 3164 and qa['passed']
              and qa['native_count'] == 251 and qa['new_frozen_pairs'] == 2559
              and len(qa['fixed_source_header_input_hashes']) == 5119, 'complete_parent_scope')
    provenance[str(proof_path)] = C.digest(r.raw(proof_path))
    stderr = D / 'preflight/parent_recompute_stderr_v1.log'
    C.require(stderr.read_bytes() == b'', 'original_parent_capture_stderr_not_empty')
    provenance[str(stderr)] = C.digest(b'')
    expected = {'archive_inventory_v1.json', 'delivery_verification.json', 'batch_status_final.json'}
    for row in inv['files']:
        rel = Path(row['relative_path'])
        C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in expected, 'unique_parent_inventory_path')
        expected.add(str(rel))
        for root in (P, M):
            add_pin(pins, root / rel, row['sha256'], row['bytes'], row['mode'])
    for root in (P, M):
        C.require(V.population(root) == (expected, set(inv['directories'])), 'complete_parent_population')
        for base, ds, fs in os.walk(root, followlinks=False):
            directories.add(base)
        for rel in ('archive_inventory_v1.json', 'delivery_verification.json', 'batch_status_final.json'):
            add_pin(pins, root / rel, V.PIN[rel])
    for path, sha in qa['fixed_source_header_input_hashes'].items():
        add_pin(pins, path, sha)
    frozen = r.json(P / 'final_frozen_snapshot/manifest.json')
    C.require(len(frozen['files']) == 2559, 'parent_frozen_population')
    for row in frozen['files']:
        for field in ('original', 'copy'):
            add_pin(pins, row[field], row['sha256'], row['bytes'])
    starts, ends, children = set(), set(), set()
    trace_files = sorted((D / 'preflight/parent_read_trace_v1').glob('*.jsonl'))
    C.require(bool(trace_files), 'successful_capture_trace_required')
    for path in trace_files:
        provenance[str(path)] = stable_sha(path)['sha256']
        for line in path.read_bytes().splitlines():
            row = C.strict_json(line)
            C.require(row['pid'] == int(path.stem), 'trace_pid_filename')
            event = row['event']
            if event == 'verified_read':
                add_pin(pins, row['path'], row['sha256'], row['bytes'])
            elif event == 'file':
                file_paths.add(row['path'])
            elif event == 'directory':
                directories.add(row['path'])
            elif event == 'start':
                C.require('acceptance_core.Reader.raw.actual_returned_bytes' in row['mechanisms'], 'exact_Reader_capture_enabled')
                starts.add(row['pid'])
            elif event == 'end':
                ends.add(row['pid'])
            elif event == 'python_child':
                children.add(row['child_pid'])
            else:
                raise ValueError('unknown_trace_event')
    C.require(starts == ends and children <= starts and len(starts - children) == 1,
              'all_original_python_processes_traced_to_exit')
    file_paths.update(pins)
    aliases, symlinks = {}, {}
    def canonical(path):
        p = Path(path)
        links = [q for q in (p, *p.parents) if q.is_symlink()]
        if not links:
            return str(p)
        resolved = str(p.resolve(strict=True))
        aliases[str(p)] = resolved
        for q in links:
            symlinks[str(q)] = os.readlink(q)
        return resolved
    normalized_pins, normalized_paths = {}, set()
    for path in sorted(file_paths):
        resolved = canonical(path)
        normalized_paths.add(resolved)
        if path in pins:
            pin = pins[path]
            add_pin(normalized_pins, resolved, pin['sha256'], pin.get('bytes'), pin.get('mode'))
    pins, file_paths = normalized_pins, normalized_paths
    directories = {canonical(path) for path in directories}
    actual = {}
    for path in sorted(file_paths):
        declared = pins.get(path)
        value = stable_sha(path, declared if declared and 'bytes' in declared else None)
        if declared:
            C.require(all(value[k] == v for k, v in declared.items()), 'original_raw_bytes_changed:' + path)
        actual[path] = value
    dir_pins = {path: V.directory_entries(path) for path in sorted(directories)}
    after = V.workspace()
    C.require(projection(before) == projection(after), 'non_new_root_workspace_changed_during_completion')
    for path, sha in provenance.items():
        C.require(stable_sha(path)['sha256'] == sha, 'capture_provenance_changed_during_completion')
    roster = {'schema': 'C3.10-flat-preservation-roster/v2', 'files': actual, 'directories': dir_pins,
              'legacy_symlink_logical_aliases': aliases, 'legacy_symlink_targets': symlinks,
              'initial_workspace_projection': projection(after), 'parent_proof_sha256': C.digest(V.canon(proof)),
              'parent_inventory_sha256': V.PIN['archive_inventory_v1.json'],
              'parent_QA_sha256': V.PIN['postrun/final_QA_current.json'], 'parent_archive_pairs': 3164,
              'parent_fixed_QA_paths': 5119, 'parent_frozen_pairs': 2559,
              'parent_semantics_fully_recomputed_once': True, 'python_processes_traced': len(starts),
              'workspace_status_excluded_untracked_roots_only': list(NEW_ROOTS),
              'initial_full_untracked_snapshot_unavailable': True,
              'initial_full_untracked_list_before_v1_capture_retrospectively_proven': False,
              'preservation_scope': 'declared frozen assets, original Reader inputs and archive inventories; other workspace state fixed from v2 full snapshot',
              'stage_qualified': False, 'research_conclusion': False}
    V.write_new(ROSTER, roster)
    V.write_new(ANCHOR, {'schema': 'C3.10-preservation-anchor/v2', 'roster_sha256': stable_sha(ROSTER)['sha256'],
                         'provenance_file_sha256': provenance, 'parent_proof_sha256': roster['parent_proof_sha256'],
                         'workspace_full_before': before, 'workspace_full_after': after,
                         'stage_qualified': False, 'research_conclusion': False})
    return protect()


def protect():
    anchor = C.Reader().json(ANCHOR)
    C.require(stable_sha(ROSTER)['sha256'] == anchor['roster_sha256'], 'flat_roster_identity_changed')
    for path, sha in anchor['provenance_file_sha256'].items():
        C.require(stable_sha(path)['sha256'] == sha, 'original_capture_provenance_changed:' + path)
    roster = C.Reader().json(ROSTER)
    C.require(roster['parent_inventory_sha256'] == V.PIN['archive_inventory_v1.json']
              and roster['parent_QA_sha256'] == V.PIN['postrun/final_QA_current.json']
              and roster['parent_proof_sha256'] == anchor['parent_proof_sha256'], 'parent_semantic_anchor_identity')
    before = V.workspace()
    C.require(projection(before) == roster['initial_workspace_projection'], 'preserved_workspace_changed')
    for path, target in roster['legacy_symlink_targets'].items():
        C.require(Path(path).is_symlink() and os.readlink(path) == target, 'preserved_legacy_symlink_changed:' + path)
    for path, target in roster['legacy_symlink_logical_aliases'].items():
        C.require(str(Path(path).resolve(strict=True)) == target, 'preserved_legacy_alias_resolution_changed:' + path)
    for path, pin in roster['files'].items():
        C.require(stable_sha(path, pin) == pin, 'preserved_raw_file_changed:' + path)
    for path, entries in roster['directories'].items():
        C.require(V.directory_entries(path) == entries, 'preserved_population_changed:' + path)
    C.require(projection(V.workspace()) == projection(before), 'workspace_changed_during_verification')
    return {'schema': 'C3.10-preservation/v2', 'passed': True,
            'parent_inventory_sha256': V.PIN['archive_inventory_v1.json'], 'parent_QA_sha256': V.PIN['postrun/final_QA_current.json'],
            'parent_archive_pairs': 3164, 'parent_fixed_QA_paths': 5119, 'parent_frozen_pairs': 2559,
            'parent_chain_proof_sha256': roster['parent_proof_sha256'], 'parent_chain_fully_recomputed_at_initial_capture': True,
            'flat_roster_sha256': anchor['roster_sha256'], 'unique_raw_files_reread': len(roster['files']),
            'directory_populations_rechecked': len(roster['directories']), 'full_raw_byte_sha_recheck': True,
            'legacy_logical_aliases_rechecked': len(roster['legacy_symlink_logical_aliases']),
            'capture_provenance_raw_files_rechecked': len(anchor['provenance_file_sha256']),
            'workspace_status_excluded_untracked_roots_only': list(NEW_ROOTS),
            'HEAD': before['HEAD'], 'branch': before['branch'], 'boot_id': before['boot_id'],
            'business_tracked_count': 24, 'business_diff_bytes': 151961, 'business_diff_sha256': before['business_diff_sha256'],
            'actual_Witness_normal_business': False, 'normal_business_contract_qualified': False,
            'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['complete', 'verify'])
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    C.require(a.output.is_absolute() and a.output.parent == D / 'preflight', 'new_preflight_output_only')
    started = time.monotonic()
    before = V.workspace()
    try:
        proof = complete() if a.mode == 'complete' else protect()
        result = {'passed': True, 'protection': proof, 'workspace_before': before, 'workspace_after': V.workspace(),
                  'endpoints_checked': False, 'stage_qualified': False, 'research_conclusion': False}
    except Exception as e:
        result = {'passed': False, 'error': repr(e), 'workspace_before': before, 'workspace_after': V.workspace(),
                  'stage_qualified': False, 'research_conclusion': False}
    result['elapsed_seconds'] = time.monotonic() - started
    V.write_new(a.output, result)
    print(json.dumps({'passed': result['passed'], 'error': result.get('error'), 'output': str(a.output),
                      'elapsed_seconds': result['elapsed_seconds']}, sort_keys=True))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
