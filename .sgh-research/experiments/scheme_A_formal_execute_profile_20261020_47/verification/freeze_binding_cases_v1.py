#!/usr/bin/env python3
"""Verify actual submitted package, then deterministic altered-copy refusals.

No frozen source/index/contract is edited. Rebound fixture hashes are explicitly
synthetic test trust roots, never a second stage submission.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(D / 'implementation/python'))
import freeze_binding_v1 as gate


def raw(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def put(p, value):
    data = value if type(value) is bytes else raw(value)
    with p.open('xb') as f:f.write(data)
    return hashlib.sha256(data).hexdigest()


def pin(p):
    data = p.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    root = D / 'verification/freeze_binding_copies_v1'
    root.mkdir()
    f = D / 'freeze'
    submitted = json.loads((f / 'freeze_submission_v1.json').read_bytes())
    index_path = f / 'freeze_index_v1.json'
    contract_path = f / 'p1_execution_contract_v1.json'
    original_index = json.loads(index_path.read_bytes())
    original_contract = json.loads(contract_path.read_bytes())
    before = {str(p): pin(p) for p in [index_path, contract_path, f / 'freeze_submission_v1.json', Path(__file__).resolve(), D / 'implementation/python/freeze_binding_v1.py']}
    rows = []

    def run(name, contract=contract_path, index=index_path, expected_index=submitted['freeze_index_sha256'], expected_contract=submitted['contract_sha256'], accepted=False, mode='no_output'):
        try:
            out = gate.verify(contract, index, expected_index, expected_contract, mode=mode)
            yes = True
        except (ValueError, OSError, KeyError, TypeError) as error:
            out = {'error': str(error)};yes = False
        rows.append({'name': name, 'expected_accepted': accepted, 'accepted': yes, 'passed': yes == accepted,
                     'contract': str(contract), 'index': str(index), 'expected_index': expected_index,
                     'expected_contract': expected_contract, 'output': out,
                     'input_kind': 'actual submitted package' if contract == contract_path and index == index_path else 'altered-copy component fixture; no stage submission'})

    run('actual_submitted_full_package', accepted=True)
    ccopy = root / 'exact_contract_copy.json';icopy = root / 'exact_index_copy.json'
    put(ccopy, contract_path.read_bytes());put(icopy, index_path.read_bytes())
    run('exact_byte_copies_keep_binding', ccopy, icopy, accepted=True)
    run('execute_still_refused', mode='execute')
    run('unknown_index_trust_pin', expected_index='0' * 64)
    run('unknown_contract_trust_pin', expected_contract='0' * 64)
    for name, key, value in [
        ('invented_hex_marker', 'freeze_evidence_sha256', 'e' * 64),
        ('retained_pending', 'pending_final_calibration', ['rho_n_s']),
        ('execute_bool_not_int', 'execute_qualified', 1),
        ('numeric_threshold_changed', 'rho_n_s', 81),
        ('resource_shape_valid_but_not_frozen_value', 'max_path_points', 1),
        ('wrong_target_profile', 'supported_parameter_profile', 'P1_activation_alignment_diagnostic_20261019_01'),
    ]:
        c = copy.deepcopy(original_contract);c[key] = value
        p = root / (name + '.json');h = put(p, c)
        run(name, p, expected_contract=h)
    c = copy.deepcopy(original_contract);c.pop('N')
    p = root / 'missing_required_field.json';h = put(p, c);run('missing_required_field', p, expected_contract=h)
    p = root / 'duplicate_contract_key.json'
    data = raw(original_contract).rstrip()[:-1] + b',"N":20}'
    h = put(p, data);run('duplicate_contract_key', p, expected_contract=h)
    p = root / 'old_pre_freeze.json';h = put(p, (D / 'implementation/owned_pre_freeze_contract_v1.json').read_bytes())
    run('old_pre_freeze_not_frozen', p, expected_contract=h)
    p = root / 'index_changed_whitespace.json';put(p, index_path.read_bytes() + b' ')
    run('index_bytes_are_exact', index=p)

    def rebound(name, change):
        index = copy.deepcopy(original_index);change(index)
        p = root / (name + '_index.json');h = put(p, index)
        contract = copy.deepcopy(original_contract);contract['freeze_evidence_sha256'] = h
        cp = root / (name + '_contract.json');ch = put(cp, contract)
        return cp, p, h, ch

    for name, change in [
        ('wrong_spec_pin', lambda v: v.update(spec_sha256='f' * 64)),
        ('wrong_policy_pin', lambda v: v.update(policy_sha256='f' * 64)),
        ('inflated_M4_scope', lambda v: v['stage_status'].update(M4=True)),
        ('inflated_M4_obligation', lambda v: v['M4_forward_obligations'][0].update(current_qualified=True)),
        ('physical_release_in_index', lambda v: v.update(physical_execute_release_enabled=True)),
        ('artifact_size_bool', lambda v: v['artifacts'][0].update(bytes=True)),
    ]:
        cp, ip, ih, ch = rebound(name, change)
        run(name, cp, ip, ih, ch)
    # Real file alteration under a rebound, otherwise equivalent copy. The
    # actual source is never touched, and the expected SHA is not relaxed.
    source = D / 'implementation/native/owned_execution_entry_v2.hpp'
    copy_path = root / 'actual_payload_copy.hpp'
    put(copy_path, source.read_bytes())

    def point_to_copy(index):
        row = next(r for r in index['artifacts'] if r['path'] == str(source))
        row['path'] = str(copy_path)

    cp, ip, ih, ch = rebound('payload_integrity', point_to_copy)
    run('rebound_payload_exact_bytes', cp, ip, ih, ch, accepted=True)
    data = copy_path.read_bytes();copy_path.write_bytes(b'!' + data[1:])
    run('actual_same_size_payload_tamper', cp, ip, ih, ch)
    # Existing symlink spelling must be refused as a manifest artifact path;
    # canonical resolved library/compiler paths remain supported.
    alias = Path('/usr/bin/python3')
    assert alias.is_symlink()
    cp, ip, ih, ch = rebound('noncanonical_alias', lambda v: v['artifacts'][0].update(path=str(alias)))
    run('noncanonical_symlink_path', cp, ip, ih, ch)
    after = {p: pin(Path(p)) for p in before}
    report = {'schema': 'P1-frozen-binding-actual-and-altered-copy-cases/v1',
              'passed': all(r['passed'] for r in rows) and before == after,
              'case_count': len(rows), 'actual_submitted_package_passed': rows[0]['passed'],
              'expected_accept_count': sum(r['expected_accepted'] for r in rows),
              'expected_reject_count': sum(not r['expected_accepted'] for r in rows),
              'failed_cases': [r['name'] for r in rows if not r['passed']], 'cases': rows,
              'input_sha256_before': before, 'input_sha256_after': after,
              'actual_frozen_assets_edited': False, 'M4_qualified': False,
              'physical_execute_release_enabled': False, 'research_conclusion': False}
    with (D / 'verification/freeze_binding_cases_v1.json').open('xb') as f:f.write(raw(report))
    print(json.dumps({k: report[k] for k in ['passed', 'case_count', 'expected_accept_count', 'expected_reject_count', 'failed_cases']}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
