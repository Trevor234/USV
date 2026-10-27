"""Strict frozen-contract/package integrity gate. This never releases output.

The caller must supply independently pinned index AND contract hashes. A 64-hex
marker, self-written receipt, or a structurally frozen contract alone is not
authentication. M4 must recheck the package and live owned graph before startup;
this finite read does not lock the filesystem or prove future process identity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

import p1_full_contract as full

MAX_FILES = 10000
MAX_INDEX_BYTES = 16 * 1024**2
MAX_FILE_BYTES = 256 * 1024**2
MAX_TOTAL_BYTES = 8 * 1024**3
MAX_SECONDS = 180


class FreezeError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise FreezeError(reason)


def hash_shape(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def canonical(value):
    require(type(value) is str and 0 < len(value) <= 4096 and '\x00' not in value, 'bounded absolute path required')
    p = Path(value)
    require(p.is_absolute() and value == os.path.normpath(value), 'normalized absolute path required')
    require(str(p.resolve(strict=True)) == value, 'canonical path without symlink required')
    return p


def stable_read(path, limit, *, data=False, deadline=None):
    path = canonical(str(path))
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, 'bounded regular file required')
        sha = hashlib.sha256();chunks = [] if data else None;size = 0
        while True:
            require(deadline is None or time.monotonic() <= deadline, 'freeze verification time budget exceeded')
            chunk = os.read(fd, 512 * 1024)
            if not chunk:
                break
            size += len(chunk)
            require(size <= limit, 'file grew beyond read budget')
            sha.update(chunk)
            if data:chunks.append(chunk)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(all(getattr(before, k) == getattr(after, k) for k in fields) and size == before.st_size,
                'file changed during hash read')
        # Reject unlink/replacement while the original descriptor was read.
        current = os.stat(path, follow_symlinks=False)
        require(all(getattr(after, k) == getattr(current, k) for k in fields), 'file path identity changed during read')
        result = {'bytes': size, 'sha256': sha.hexdigest()}
        if data:result['data'] = b''.join(chunks)
        return result
    finally:
        os.close(fd)


def parse(raw):
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=full._unique_object,
                           parse_constant=full._reject_constant)
        full._domain(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise FreezeError('invalid freeze JSON') from error


def template_bytes(contract):
    value = dict(contract)
    value['freeze_evidence_sha256'] = ''
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def verify(contract_path, index_path, expected_index_sha256, expected_contract_sha256, *, mode='no_output'):
    require(hash_shape(expected_index_sha256) and hash_shape(expected_contract_sha256), 'independently pinned index and contract SHA required')
    started = time.monotonic();deadline = started + MAX_SECONDS
    index_pin = stable_read(index_path, MAX_INDEX_BYTES, data=True, deadline=deadline)
    require(index_pin['sha256'] == expected_index_sha256, 'freeze index SHA mismatch')
    index = parse(index_pin['data'])
    keys = {'schema', 'profile_id', 'qualification_scope', 'physical_execute_release_enabled',
            'contract_template_path', 'contract_template_sha256', 'policy_path', 'policy_sha256',
            'spec_sha256', 'parameter_sources_path', 'fault_matrix_path', 'fault_matrix_sha256',
            'conditions_path', 'evidence_ledger_path', 'artifacts', 'artifact_count', 'total_bytes',
            'M4_forward_obligations', 'limitations', 'stage_status', 'committed_before_M4'}
    require(type(index) is dict and set(index) == keys, 'exact freeze index fields required')
    require(index['schema'] == 'P1-M0b-engineering-freeze-index/v1' and index['profile_id'] == full.SPEC['target_profile_id'], 'unsupported freeze index/profile')
    require(index['physical_execute_release_enabled'] is False and index['committed_before_M4'] is True, 'physical release or wrong freeze order')
    require(index['spec_sha256'] == full.SPEC_SHA256 and index['policy_sha256'] == full.SPEC['target_policy_sha256'], 'spec/policy pin mismatch')
    require(index['stage_status'] == {'B5_contract_freeze': True, 'M0b_selected_engineering_freeze': True, 'M4': False, 'F6': False, 'P1': False, 'plant': False}, 'qualification scope mismatch')
    require(type(index['M4_forward_obligations']) is list and len(index['M4_forward_obligations']) == 9
            and all(type(x) is dict and x.get('current_qualified') is False for x in index['M4_forward_obligations']), 'M4 obligations must remain unqualified')
    contract_pin = stable_read(contract_path, full.MAX_CONTRACT_BYTES, data=True, deadline=deadline)
    require(contract_pin['sha256'] == expected_contract_sha256, 'frozen contract SHA mismatch')
    contract = full.parse_contract_bytes(contract_pin['data'])
    full.validate_fields(contract)
    require(contract['qualification'] == 'execution_frozen' and contract['supported_parameter_profile'] == full.SPEC['target_profile_id'], 'owned frozen profile required')
    full.require_runtime_mode(contract, mode)  # execute always rejects here
    require(mode == 'no_output', 'only offline/preflight verification is released')
    require(contract['freeze_evidence_sha256'] == expected_index_sha256, 'contract/index evidence binding mismatch')
    require(hashlib.sha256(template_bytes(contract)).hexdigest() == index['contract_template_sha256'], 'frozen contract template mismatch')
    artifacts = index['artifacts']
    require(type(artifacts) is list and 1 <= len(artifacts) <= MAX_FILES and type(index['artifact_count']) is int and len(artifacts) == index['artifact_count'], 'finite artifact population required')
    seen = set();total = 0;verified = {};required_roles = set()
    for row in artifacts:
        require(type(row) is dict and set(row) == {'path', 'sha256', 'bytes', 'roles'}, 'exact artifact fields')
        require(hash_shape(row['sha256']) and type(row['bytes']) is int and 0 <= row['bytes'] <= MAX_FILE_BYTES, 'artifact hash/size type')
        require(type(row['roles']) is list and 1 <= len(row['roles']) <= 32 and all(type(x) is str and 0 < len(x) <= 96 for x in row['roles']), 'artifact roles required')
        path = str(canonical(row['path']))
        require(path not in seen, 'duplicate artifact path')
        seen.add(path);total += row['bytes'];required_roles.update(row['roles'])
        require(total <= MAX_TOTAL_BYTES, 'total artifact byte budget')
        actual = stable_read(path, row['bytes'], deadline=deadline)
        require(actual == {'bytes': row['bytes'], 'sha256': row['sha256']}, 'artifact byte/hash mismatch: ' + path)
        verified[path] = actual
    require(type(index['total_bytes']) is int and total == index['total_bytes'], 'total bytes mismatch')
    require({'source', 'binary', 'model', 'config', 'tool', 'evidence', 'policy', 'fault_matrix', 'parameter_sources', 'freeze_conditions', 'contract_template'} <= required_roles, 'freeze artifact roles incomplete')
    for key in ['contract_template_path', 'policy_path', 'parameter_sources_path', 'fault_matrix_path', 'conditions_path', 'evidence_ledger_path']:
        require(index[key] in verified, 'required index artifact missing: ' + key)
    for path_key, hash_key in [('contract_template_path', 'contract_template_sha256'), ('policy_path', 'policy_sha256'), ('fault_matrix_path', 'fault_matrix_sha256')]:
        require(verified[index[path_key]]['sha256'] == index[hash_key], 'required artifact pin mismatch')
    template = stable_read(index['contract_template_path'], full.MAX_CONTRACT_BYTES, data=True, deadline=deadline)['data']
    require(template == template_bytes(contract), 'exact normalized contract template required')
    sources = parse(stable_read(index['parameter_sources_path'], MAX_INDEX_BYTES, data=True, deadline=deadline)['data'])
    require(sources.get('schema') == 'P1-M0b-parameter-source-table/v1' and sources.get('profile_id') == full.SPEC['target_profile_id'], 'parameter source profile mismatch')
    require(set(sources.get('pending8_selected', {})) == set(full.SPEC['legacy_baseline']['pending_final_calibration']), 'all pending8 require sources')
    require(all(x.get('selected_engineering_design_frozen') is True and x.get('physical_calibration_qualified') is False for x in sources['pending8_selected'].values()), 'source qualification scope')
    conditions = parse(stable_read(index['conditions_path'], MAX_INDEX_BYTES, data=True, deadline=deadline)['data'])
    require(conditions.get('passed') is True and conditions.get('physical_execute_release_enabled') is False and conditions.get('M4_qualified') is False,
            'freeze conditions not satisfied or scope inflated')
    require(type(conditions.get('checks')) is dict and len(conditions['checks']) >= 10 and all(type(x) is bool and x for x in conditions['checks'].values()), 'freeze condition checks incomplete')
    # Recheck the two top-level bindings after streaming all the artifacts.
    require(stable_read(index_path, MAX_INDEX_BYTES, deadline=deadline)['sha256'] == expected_index_sha256 and stable_read(contract_path, full.MAX_CONTRACT_BYTES, deadline=deadline)['sha256'] == expected_contract_sha256,
            'top-level binding changed while verifying artifacts')
    return {'schema': 'P1-M0b-frozen-package-verification/v1', 'passed': True,
            'index_sha256': expected_index_sha256, 'contract_sha256': expected_contract_sha256,
            'profile_id': full.SPEC['target_profile_id'], 'artifact_count': len(artifacts), 'artifact_bytes': total,
            'elapsed_seconds': time.monotonic() - started, 'physical_execute_release_enabled': False,
            'B5_contract_freeze_qualified': True, 'M0b_selected_engineering_freeze_qualified': True,
            'M4_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
            'plant_qualified': False, 'research_conclusion': False, 'filesystem_locked': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--expected-index', required=True)
    parser.add_argument('--expected-contract', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.contract, args.index, args.expected_index, args.expected_contract)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result = {'passed': False, 'error': str(error), 'physical_execute_release_enabled': False,
                  'B5_contract_freeze_qualified': False, 'M0b_selected_engineering_freeze_qualified': False,
                  'M4_qualified': False, 'P1_qualified': False}
    with args.report.open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True);f.write('\n')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
