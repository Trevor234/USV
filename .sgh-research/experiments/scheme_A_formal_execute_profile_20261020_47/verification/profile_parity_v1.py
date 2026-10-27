#!/usr/bin/env python3
"""Independent expected raw corpus: preserved old 385 plus formal target cases."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent.parent
I = D / 'implementation'
sys.path.insert(0, str(I / 'python'))
import p1_full_contract as py


def enc(v):
    return (json.dumps(v, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def pin(p):
    raw = p.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def emit(p, value):
    with p.open('xb') as f:
        f.write(enc(value))


def main():
    root = D / 'verification/profile_corpus_v1'
    root.mkdir()
    old = D.parent / 'scheme_A_B5_contract_parity_20261020_44/verification'
    manifest = json.loads((old / 'corpus_manifest_v2.json').read_bytes())
    cases = []
    for row in manifest['cases']:
        p = old / 'corpus_v2' / f"{row['index']:04d}.json"
        assert pin(p) == row['raw']
        cases.append({k: row[k] for k in ['name', 'expected', 'action', 'mode']} | {'path': str(p), 'legacy': True})
    assert len(cases) == 385
    target = json.loads((I / 'owned_pre_freeze_contract_v1.json').read_bytes())
    shape = copy.deepcopy(target)
    shape.update(qualification='execution_frozen', execute_qualified=True,
                 parameters_are_diagnostic_only=False, pending_final_calibration=[],
                 freeze_evidence_sha256='e' * 64)
    emit(D / 'verification/owned_frozen_shape_only.json', shape)

    def add(name, obj, expected=False, action='fields', mode=''):
        p = root / f'{len(cases)-385:04d}.json'
        raw = obj if type(obj) is bytes else enc(obj)
        with p.open('xb') as f:
            f.write(raw)
        cases.append({'name': name, 'path': str(p), 'expected': expected, 'action': action, 'mode': mode, 'legacy': False})

    for label, c in [('owned_pre', target), ('owned_frozen_shape_only', shape)]:
        add(label + '_fields', c, True)
        allowed = {'no_output'} if label == 'owned_pre' else {'no_output', 'execute'}
        for mode in ['no_output', 'shadow', 'execute', '', 'NO_OUTPUT']:
            add(label + '_mode_' + repr(mode), c, mode in allowed, 'mode', mode)
            add(label + '_runtime_' + repr(mode), c, mode in allowed and mode != 'execute', 'runtime', mode)
        for key in c:
            bad = copy.deepcopy(c);bad.pop(key)
            add(label + '_missing_' + key, bad)
        for key in ['baseline_input', 'preparation_retry_policy', 'propagation_semantics', 'supported_parameter_profile']:
            bad = copy.deepcopy(c);bad[key] = json.loads((I / 'current_pre_freeze_contract_v1.json').read_bytes())[key]
            add(label + '_mixed_profile_' + key, bad)
        for key in ['N', 'hold_ns', 'publish_gap_ns', 'deadline_ns', 'worker_capability_receipt_timeout_ns']:
            for value in [float(c[key]), True, c[key] + 1]:
                bad = copy.deepcopy(c);bad[key] = value
                add(label + '_changed_or_wrong_type_' + key + '_' + repr(value), bad)
        for key, value in [('rho_n_s', 81), ('nominal_hash', 'a' * 64), ('fault_injection_enabled', True), ('resource_contract_revision', True)]:
            bad = copy.deepcopy(c);bad[key] = value
            add(label + '_changed_' + key, bad)
        for key, low, high in [('max_path_points', 1, 2048), ('max_job_bytes', 6460, 8192)]:
            for value, good in [(low, True), (high, True), (low - 1, False), (high + 1, False)]:
                bad = copy.deepcopy(c);bad[key] = value
                add(label + '_resource_' + key + '_' + str(value), bad, good)
    raw = enc(shape).rstrip()
    add('target_duplicate_top', raw[:-1] + b',"N":20}')
    add('target_duplicate_nested', raw.replace(b'"hydro":{', b'"hydro":{"Iz":2.13,', 1))
    add('target_NaN', raw.replace(b'"rho_n_s":80', b'"rho_n_s":NaN', 1))
    add('target_size_overflow', raw + b' ' * (65537 - len(raw)))
    requests = []
    rows = []
    binary = D / 'build/components_attempt01/contract_probe'
    paths = [Path(c['path']) for c in cases] + [binary, Path(__file__).resolve()]
    paths += list((I / 'python').glob('*.py')) + list((I / 'native').glob('*.hpp')) + [I / 'current_contract_spec_v1.json', I / 'python/p1_contract_spec_v1.json']
    before = {str(p): pin(p) for p in paths}
    for c in cases:
        requests.append({'path': c['path'], 'action': c['action'], 'mode': c['mode']})
        try:
            value = py.parse_contract_bytes(Path(c['path']).read_bytes())
            if c['action'] == 'fields':py.validate_fields(value)
            elif c['action'] == 'mode':py.validate_mode(value, c['mode'])
            else:py.require_runtime_mode(value, c['mode'])
            outcome = {'accepted': True}
        except (ValueError, TypeError, KeyError) as e:
            outcome = {'accepted': False, 'reason': str(e)}
        rows.append(c | {'Python': outcome})
    result = subprocess.run([str(binary)], input=b''.join(enc(r) for r in requests), capture_output=True, timeout=120)
    (D / 'verification/profile_native_stdout_v1.jsonl').write_bytes(result.stdout)
    (D / 'verification/profile_native_stderr_v1.log').write_bytes(result.stderr)
    outcomes = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 0 and len(outcomes) == len(rows)
    for row, native in zip(rows, outcomes):
        row['Native'] = native
        row['passed'] = row['Python']['accepted'] == native['accepted'] == row['expected'] and native['spec_sha256'] == py.SPEC_SHA256 and native['physical_execute_release_enabled'] is False
    after = {p: pin(Path(p)) for p in before}
    record = {'schema': 'P1-dual-profile-parity/v1', 'passed': all(r['passed'] for r in rows) and before == after,
              'legacy_cases': 385, 'new_cases': len(rows) - 385, 'cases': rows,
              'case_count': len(rows), 'expected_accept_count': sum(r['expected'] for r in rows),
              'failed_cases': [r['name'] for r in rows if not r['passed']],
              'input_sha256_before': before, 'input_sha256_after': after,
              'frozen_marker_cases_are_shape_tests_only': True, 'physical_execute_release_enabled': False,
              'ROS_runs': 0, 'stage_qualified': False, 'research_conclusion': False}
    emit(D / 'verification/profile_parity_v1.json', record)
    print(json.dumps({k: record[k] for k in ['passed', 'case_count', 'legacy_cases', 'new_cases', 'failed_cases']}))
    return 0 if record['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
