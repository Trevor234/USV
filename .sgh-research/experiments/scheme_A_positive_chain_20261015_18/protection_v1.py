#!/usr/bin/env python3
"""Read-only full-byte preservation for ordered positive-chain batch 18.

The historical semantic capture stays frozen. All captured input bytes and
directory populations, both complete later archives, and analysis inputs are
reread without running historical ROS processes or importing endpoint authority.
Only this batch's two new untracked roots are additionally excluded from the
existing workspace projection; old source, staging, submodules and failures stay
fixed. No recursive protection helper is invoked.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
P = D.parent / 'scheme_A_C3_10_20261015_16'
A = D.parent / 'scheme_A_rejection_analysis_20261015_17'
M = Path('/home/trevor/MPC')
NEW_ROOTS = (
    '.sgh-research/experiments/scheme_A_positive_chain_20261015_18/',
    '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18/',
)
OLD_ROOTS = (
    '.sgh-research/experiments/scheme_A_C3_10_20261015_16/',
    '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_10_20261015_v17/',
)
PIN16 = {
    'archive_inventory_v1.json': '8385def2158a9346ab38243ddb70f161a557d636c446b130a2b3a3f8b7886729',
    'postrun/final_QA_current.json': 'c55ebe389318e9d24941e0a6702dc40c2c8a36d4978b22d04d9e1cdd842bffe0',
    'delivery_verification.json': 'd761180125c2dd175eca57e76a30f7da236d0533589307158907f7daba2df761',
    'batch_status_final.json': '4d89572d606d016ae4c7383ba40498c5511c13957a9a4a891dd6efd1f8165b0d',
    'protection_v1.py': '7ea34af54149cd30ae455acbfffcbc5bbca9d5674989374a113e3ce91bd4c4c4',
    'protection_v3.py': '22c95d6512fccf2a83d1301882e621e382fe1cba1dade5dd845e5be335bd0b9c',
    'protection_v4.py': '2846776572d8237124c73c3c5469b0a22d95ca288b51d3efc76316e406d07f86',
    'preflight/preservation_anchor_v3.json': '770dcf7f3ffd12944a1117c1145a6e13ace825623b34fef8ee77e4539dd1aadb',
    'preflight/preservation_roster_v3.json': '4c9062d9033e2bd89ba34e3bf2c9490251b8bb0679a06018860fc74bc163583d',
    'preflight/boot_transition_v4.json': '0f188c835aff8c1070cb421406085fbce3dbb779bbbad3c9d6ccf5ce69c6e279',
}
PIN17 = {
    'archive_inventory_v1.json': '59ef7f3df168720079f1394536fec169b241b18bab818b6d2f6679a6a16f8ce2',
    'delivery_verification.json': '0864ec5b6d3879d99d405f32df6a6a22edad3ab21b31213e0412aeeb299d7a29',
    'evidence/analysis_QA_v1.json': 'b3918f644955d0921238f3d308daae9c7ed1e32c284e1e28d5e65102272fafed',
    'evidence/rejection_audit_v1.json': '3a0e9a95ceee10b2bc122a2a4f4282d07eb4d52822f41475a7f6d9896fc7d30a',
}

# Import only stable-stream/workspace utilities from the pinned original helper.
# Its protect/capture/parent-semantic subprocess functions are never invoked.
spec = importlib.util.spec_from_file_location('ordered_parent_preservation_utilities', P / 'protection_v1.py')
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
C = V.C


def projection(value):
    result = dict(value)
    rows = []
    for line in value['status_porcelain'].splitlines(keepends=True):
        path = line[3:]
        if path.startswith('"'):
            path = path[1:]
        if line.startswith('?? ') and any(path.startswith(prefix) for prefix in OLD_ROOTS + NEW_ROOTS):
            continue
        rows.append(line)
    result['status_porcelain'] = ''.join(rows)
    result['status_porcelain_sha256'] = C.digest(result['status_porcelain'].encode())
    return result


def without_boot(value):
    result = projection(value)
    result.pop('boot_id')
    return result


def add_pin(pins, path, sha, size=None, mode=None):
    path = str(path)
    row = {'sha256': sha}
    if size is not None:
        row['bytes'] = size
    if mode is not None:
        row['mode'] = mode
    if path in pins:
        for key in row.keys() & pins[path].keys():
            C.require(row[key] == pins[path][key], 'inconsistent_sealed_pin:' + path)
        pins[path].update(row)
    else:
        pins[path] = row


def add_archive(pins, root, inv, extra_pins, metadata_names):
    expected = set(metadata_names)
    directories = set(inv.get('directories', []))
    for row in inv['files']:
        rel = Path(row['relative_path'])
        C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in expected,
                  'unique_normalized_archive_member')
        expected.add(str(rel))
        for parent in rel.parents:
            if str(parent) != '.':
                directories.add(str(parent))
        for archive in (root, M / root.name):
            # Archive copying historically selected its own output mode. The
            # sealed archive byte/size identity, not original source mode, binds it.
            add_pin(pins, archive / rel, row['sha256'], row['bytes'])
    for archive in (root, M / root.name):
        C.require(V.population(archive) == (expected, directories), 'sealed_complete_population:' + str(archive))
        for name in metadata_names:
            add_pin(pins, archive / name, extra_pins[name])
    return (expected, directories)


def protect():
    before = V.workspace()
    reader = C.Reader(seconds=1200, max_bytes=512 * 1024**2, max_files=1000)
    for root, meta in ((P, PIN16), (A, PIN17)):
        for rel, sha in meta.items():
            C.require(C.digest(reader.raw(root / rel)) == sha, 'sealed_metadata_changed:' + str(root / rel))
    anchor = reader.json(P / 'preflight/preservation_anchor_v3.json')
    roster = reader.json(P / 'preflight/preservation_roster_v3.json')
    transition = reader.json(P / 'preflight/boot_transition_v4.json')
    C.require(anchor['roster_sha256'] == PIN16['preflight/preservation_roster_v3.json']
              and transition['original_anchor_sha256'] == PIN16['preflight/preservation_anchor_v3.json']
              and transition['original_roster_sha256'] == anchor['roster_sha256']
              and transition['helper_sha256'] == PIN16['protection_v4.py'], 'original_capture_transition_identity')
    C.require(roster['parent_inventory_sha256'] == V.PIN['archive_inventory_v1.json']
              and roster['parent_QA_sha256'] == V.PIN['postrun/final_QA_current.json']
              and roster['parent_proof_sha256'] == anchor['parent_proof_sha256'], 'historical_semantic_anchor_identity')
    C.require(len(roster['files']) == 34296 and len(roster['directories']) == 1344, 'historical_complete_capture_scope')
    C.require(before['boot_id'] == transition['resumed_boot_id'], 'new_boot_requires_explicit_transition')
    C.require(without_boot(before) == transition['preserved_workspace_projection_without_boot']
              == without_boot(roster['initial_workspace_projection']), 'old_workspace_projection_changed')
    C.require(before['business_tracked_count'] == 24 and before['business_diff_bytes'] == 151961
              and before['business_diff_sha256'] == 'd901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5',
              'original_24_business_changes_changed')
    pins = {path: dict(pin) for path, pin in roster['files'].items()}
    for path, sha in anchor['provenance_file_sha256'].items():
        add_pin(pins, path, sha)
    for root, meta in ((P, PIN16), (A, PIN17)):
        for rel, sha in meta.items():
            add_pin(pins, root / rel, sha)
    inv16 = reader.json(P / 'archive_inventory_v1.json')
    delivery16 = reader.json(P / 'delivery_verification.json')
    qa16 = reader.json(P / 'postrun/final_QA_current.json')
    C.require(len(inv16['files']) == 2432 and delivery16['passed']
              and delivery16['full_second_SHA_readback'] and delivery16['final_regular_files_per_root'] == 2435,
              'C310_complete_archive_scope')
    C.require(qa16['passed'] and qa16['stage_qualified'] is False and qa16['new_frozen_pairs'] == 2151
              and len(qa16['fixed_source_header_input_hashes']) == 4303, 'C310_current_QA_scope')
    C.require(qa16['parent_before'] == qa16['parent_after'] == inv16['protection']
              == inv16['protection_after_prepare'] == delivery16['protected_before']
              == delivery16['protected_after'], 'C310_archived_parent_proof_identity')
    old_proof = qa16['parent_after']
    C.require(old_proof['flat_roster_sha256'] == anchor['roster_sha256']
              and old_proof['parent_chain_proof_sha256'] == roster['parent_proof_sha256']
              and old_proof['boot_transition_record_sha256'] == PIN16['preflight/boot_transition_v4.json']
              and old_proof['old_run_or_endpoint_qualification_transferred'] is False
              and old_proof['current_asset_recheck_boot_id'] == before['boot_id'], 'C310_archived_proof_scope')
    archives16 = add_archive(pins, P, inv16, PIN16,
                             ('archive_inventory_v1.json', 'delivery_verification.json', 'batch_status_final.json'))
    for path, sha in qa16['fixed_source_header_input_hashes'].items():
        add_pin(pins, path, sha)
    frozen = reader.json(P / 'final_frozen_snapshot/manifest.json')
    C.require(len(frozen['files']) == 2151, 'C310_frozen_population')
    for row in frozen['files']:
        for field in ('original', 'copy'):
            add_pin(pins, row[field], row['sha256'], row['bytes'])
    inv17 = reader.json(A / 'archive_inventory_v1.json')
    delivery17 = reader.json(A / 'delivery_verification.json')
    qa17 = reader.json(A / 'evidence/analysis_QA_v1.json')
    audit17 = reader.json(A / 'evidence/rejection_audit_v1.json')
    C.require(len(inv17['files']) == 6 and delivery17['passed']
              and delivery17['full_second_SHA_readback'] and delivery17['final_files_per_root'] == 8
              and qa17['passed'] and qa17['raw_inputs_before_after_equal']
              and qa17['new_ROS_run'] is False and audit17['passed']
              and audit17['source_inputs_before_sha256'] == audit17['source_inputs_after_sha256'], 'analysis_preserved_scope')
    archives17 = add_archive(pins, A, inv17, PIN17, ('archive_inventory_v1.json', 'delivery_verification.json'))
    analysis_inputs = {**audit17['source_inputs_before_sha256'], **qa17['source_code_document_pins']}
    C.require(len(analysis_inputs) == 42, 'analysis_complete_input_scope')
    for path, sha in analysis_inputs.items():
        add_pin(pins, path, sha)
    for path, target in roster['legacy_symlink_targets'].items():
        C.require(Path(path).is_symlink() and os.readlink(path) == target, 'historical_symlink_changed:' + path)
    for path, target in roster['legacy_symlink_logical_aliases'].items():
        C.require(str(Path(path).resolve(strict=True)) == target, 'historical_alias_changed:' + path)
    total_bytes = 0
    for path, pin in sorted(pins.items()):
        actual = V.stable_sha(path)
        C.require(all(actual[key] == value for key, value in pin.items()), 'sealed_raw_file_changed:' + path)
        total_bytes += actual['bytes']
    for path, entries in roster['directories'].items():
        C.require(V.directory_entries(path) == entries, 'historical_population_changed:' + path)
    for root, expected in ((P, archives16), (M / P.name, archives16), (A, archives17), (M / A.name, archives17)):
        C.require(V.population(root) == expected, 'sealed_population_changed_during_read:' + str(root))
    C.require(reader.unchanged(), 'metadata_changed_during_stream_recheck')
    after = V.workspace()
    C.require(projection(before) == projection(after), 'old_workspace_changed_during_recheck')
    return {'schema': 'SchemeA-ordered-positive-preservation/v1', 'passed': True,
            'historical_flat_roster_sha256': anchor['roster_sha256'],
            'historical_raw_files_reread': len(roster['files']),
            'historical_directory_populations_rechecked': len(roster['directories']),
            'historical_capture_provenance_files_rechecked': len(anchor['provenance_file_sha256']),
            'historical_logical_aliases_rechecked': len(roster['legacy_symlink_logical_aliases']),
            'parent_C310_archive_pairs': 2435, 'parent_C310_fixed_QA_paths': 4303,
            'parent_C310_frozen_pairs': 2151, 'analysis_archive_pairs': 8,
            'analysis_inputs_reread': len(analysis_inputs), 'unique_raw_files_reread': len(pins),
            'logical_bytes_streamed': total_bytes, 'full_raw_byte_sha_recheck': True,
            'parent_inventory_sha256': PIN16['archive_inventory_v1.json'],
            'parent_QA_sha256': PIN16['postrun/final_QA_current.json'],
            'analysis_inventory_sha256': PIN17['archive_inventory_v1.json'],
            'archived_parent_proof_sha256': C.digest(V.canon(old_proof)),
            'historical_semantics_recomputed': False,
            'historical_semantic_capture_retained': True,
            'semantic_capture_boot_id': transition['original_capture_boot_id'],
            'current_asset_recheck_boot_id': before['boot_id'],
            'old_run_or_endpoint_qualification_transferred': False,
            'new_current_endpoints_verified': False,
            'workspace_status_excluded_untracked_roots_only': list(OLD_ROOTS + NEW_ROOTS),
            'initial_full_untracked_snapshot_unavailable': True,
            'initial_full_untracked_list_before_original_capture_retrospectively_proven': False,
            'HEAD': after['HEAD'], 'branch': after['branch'], 'boot_id': after['boot_id'],
            'business_tracked_count': 24, 'business_diff_bytes': 151961,
            'business_diff_sha256': after['business_diff_sha256'],
            'actual_Witness_normal_business': False, 'normal_business_contract_qualified': False,
            'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    C.require(args.output.is_absolute() and args.output.parent == D / 'preflight', 'new_preflight_output_only')
    started = time.monotonic()
    before = V.workspace()
    try:
        proof = protect()
        result = {'passed': True, 'protection': proof, 'workspace_before': before,
                  'workspace_after': V.workspace(), 'endpoints_checked': False,
                  'stage_qualified': False, 'research_conclusion': False}
    except Exception as error:
        result = {'passed': False, 'error': repr(error), 'workspace_before': before,
                  'workspace_after': V.workspace(), 'stage_qualified': False, 'research_conclusion': False}
    result['elapsed_seconds'] = time.monotonic() - started
    V.write_new(args.output, result)
    print(json.dumps({'passed': result['passed'], 'error': result.get('error'),
                      'elapsed_seconds': result['elapsed_seconds'], 'output': str(args.output)}, sort_keys=True))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
