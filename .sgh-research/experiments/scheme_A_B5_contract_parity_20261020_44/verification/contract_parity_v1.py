#!/usr/bin/env python3
"""Independent expected corpus against current Python and actual C++ process.

Expectations are declared by category before either validator is called. This
does not infer correctness merely because two implementations agree.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent.parent
I = D / 'implementation'
sys.path.insert(0, str(I / 'python'))
import p1_full_contract as py


def sha(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def encoded(value):
    return (json.dumps(value, separators=(',', ':'), ensure_ascii=True, allow_nan=False) + '\n').encode()


def create(path, value):
    with path.open('xb') as f:
        f.write(encoded(value))


def corpus():
    diag = json.loads((I / 'current_diag_contract_v1.json').read_bytes())
    pre = json.loads((I / 'current_pre_freeze_contract_v1.json').read_bytes())
    frozen = copy.deepcopy(pre)
    frozen.update(qualification='execution_frozen', execute_qualified=True,
                  parameters_are_diagnostic_only=False, pending_final_calibration=[],
                  freeze_evidence_sha256='a' * 64)
    cases = []

    def add(name, obj, expected=False, action='fields', mode=''):
        cases.append({'name': name, 'raw': obj if type(obj) is bytes else encoded(obj),
                      'expected': expected, 'action': action, 'mode': mode})

    for label, profile in [('diagnostic', diag), ('pre_freeze', pre), ('frozen_shape', frozen)]:
        add(label + '_fields', profile, True)
        allowed = {'diagnostic': {'no_output', 'shadow'}, 'pre_freeze': {'no_output'},
                   'frozen_shape': {'no_output', 'execute'}}[label]
        for mode in ['no_output', 'shadow', 'execute', '', 'NO_OUTPUT', 'no-output']:
            add(label + '_mode_' + repr(mode), profile, mode in allowed, 'mode', mode)
            add(label + '_runtime_' + repr(mode), profile,
                mode in allowed and mode != 'execute', 'runtime', mode)
    # Each non-resource diagnostic value is fixed, including policy strings,
    # nested hydro, all flags, revisions and complete topic identities.
    resource = set(py.SPEC['resource_keys'])
    for key, value in diag.items():
        if key in resource:
            continue
        bad = copy.deepcopy(diag)
        if type(value) is bool:
            bad[key] = not value
        elif type(value) in (int, float):
            bad[key] = value + 1
        elif type(value) is str:
            bad[key] = value + '_unregistered'
        elif type(value) is list:
            bad[key] = value[:-1]
        elif type(value) is dict:
            bad[key] = dict(value)
            bad[key].pop(next(iter(value)))
        add('fixed_value_' + key, bad)
    for key in diag:
        bad = dict(diag);bad.pop(key)
        add('missing_' + key, bad)
    bad = dict(diag);bad['invented_qualification'] = True
    add('unknown_key', bad)
    for key in py.SPEC['integer_keys']:
        for label, transform in [('float', float), ('bool', bool)]:
            bad = dict(diag);bad[key] = transform(diag[key])
            add('strict_integer_' + key + '_' + label, bad)
    # Independently declared typed-resource boundaries; preserve ranges rather
    # than accidentally freezing every resource to the nominal maximum.
    bounded = {'max_path_points': (1, 2048), 'max_profile_rows': (1, 2048),
               'log_capacity': (1, 512), 'history_capacity': (1, 256),
               'max_job_bytes': (6460, 8192), 'max_candidate_bytes': (8204, 16384)}
    fixed = {'max_profile_dims': 4, 'max_profile_label_bytes': 64,
             'max_path_frame_bytes': 128, 'job_cdr_max_bytes': 6460,
             'candidate_cdr_max_bytes': 8204, 'dds_depth': 1}
    for label, profile in [('diag', diag), ('pre', pre)]:
        for key, (low, high) in bounded.items():
            for value, expected in [(low, True), (high, True), (low - 1, False), (high + 1, False)]:
                bad = dict(profile);bad[key] = value
                add(f'resource_{label}_{key}_{value}', bad, expected)
        for key, value in fixed.items():
            bad = dict(profile);bad[key] = value + 1
            add(f'resource_{label}_{key}_fixed_mismatch', bad)
    for label, profile in [('pre', pre), ('frozen', frozen)]:
        alterations = {
            'fault': ('fault_injection_enabled', True),
            'revision_bool': ('execution_contract_revision', True),
            'revision_float': ('execution_contract_revision', 1.0),
            'revision_unknown': ('resource_contract_revision', 2),
            'profile_old': ('supported_parameter_profile', 'F5_P1_candidate_20261007_01'),
            'profile_unknown': ('supported_parameter_profile', 'unregistered'),
            'legacy_revision': ('diagnostic_contract_revision', 10),
            'schema_unknown': ('schema', 'p1-execution-contract-v4'),
            'qualification_unknown': ('qualification', 'approved'),
            'execute_bool_type': ('execute_qualified', 1 if label == 'frozen' else 0),
            'diagnostic_bool_type': ('parameters_are_diagnostic_only', 0 if label == 'frozen' else 1),
            'marker_type': ('freeze_evidence_sha256', None),
            'pending_type': ('pending_final_calibration', 'none'),
            'execute_flag': ('execute_qualified', label != 'frozen'),
            'diag_flag': ('parameters_are_diagnostic_only', label == 'frozen'),
        }
        for name, (key, value) in alterations.items():
            bad = dict(profile);bad[key] = value
            add('formal_' + label + '_' + name, bad)
    for value in ['a' * 64, 'approved', 0]:
        bad = dict(pre);bad['freeze_evidence_sha256'] = value
        add('pre_marker_must_be_empty_' + str(value), bad)
    bad = dict(pre);bad['pending_final_calibration'] = []
    add('pre_cannot_drop_pending', bad)
    for value in ['', 'a' * 63, 'a' * 65, 'A' * 64, 'g' * 64]:
        bad = dict(frozen);bad['freeze_evidence_sha256'] = value
        add('frozen_marker_shape_' + value, bad)
    bad = dict(frozen);bad['pending_final_calibration'] = diag['pending_final_calibration']
    add('frozen_pending_remains', bad)
    semantic = copy.deepcopy(diag)
    semantic['Q'] = [float(v) for v in semantic['Q']]
    semantic['command_max_n'] = 25.0
    add('non_integer_key_numeric_semantics', semantic, True)
    raw = encoded(diag).rstrip()
    add('duplicate_top', raw[:-1] + b',"N":20}')
    add('duplicate_nested', raw.replace(b'"hydro":{', b'"hydro":{"Iz":2.13,', 1))
    for label, value in [('nan', b'NaN'), ('infinity', b'Infinity'),
                         ('minus_infinity', b'-Infinity'), ('overflow_float', b'1e999'),
                         ('uint64_overflow', b'18446744073709551616'),
                         ('int64_overflow', b'9223372036854775808')]:
        add('raw_' + label, raw.replace(b'"N":20', b'"N":' + value, 1))
    for label, value in [('empty', b''), ('truncated', raw[:-1]),
                         ('trailing', raw + b' trailing'), ('invalid_utf8', b'{"bad":"\xff"}'),
                         ('null', b'null'), ('array', b'[]'), ('scalar', b'3'),
                         ('size_overflow', raw + b' ' * (65537 - len(raw)))]:
        add('raw_' + label, value)
    add('exact_64KiB_valid_whitespace', raw + b' ' * (65536 - len(raw)), True)
    old_spec = D.parent / 'scheme_A_owned_business_start_20261020_39/author/runtime/p1_contract_spec_v1.json'
    add('old74_is_not_current81', json.loads(old_spec.read_bytes())['legacy_baseline'])
    return cases


def main():
    binary = D / 'build/contract_probe_attempt01/contract_probe'
    root = D / 'verification/corpus_v1';root.mkdir()
    inputs = [I/'current_contract_spec_v1.json', I/'current_diag_contract_v1.json',
              I/'current_pre_freeze_contract_v1.json', I/'python/p1_full_contract.py',
              I/'python/p1_resource_contract.py', I/'python/p1_contract_spec_v1.json',
              I/'native/p1_full_contract.hpp', I/'native/p1_resources.hpp',
              I/'native/contract_probe.cpp', Path(__file__).resolve(), binary]
    before = {str(p): sha(p) for p in inputs}
    expected_spec = before[str(I/'current_contract_spec_v1.json')]['sha256']
    assert expected_spec == py.SPEC_SHA256 == '317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798'
    cases = corpus();requests=[];rows=[]
    for index, case in enumerate(cases):
        path = root / f'{index:04d}.json'
        with path.open('xb') as f:f.write(case['raw'])
        before[str(path)] = sha(path)
        requests.append({'path': str(path), 'action': case['action'], 'mode': case['mode']})
        try:
            value = py.parse_contract_bytes(case['raw'])
            if case['action'] == 'fields':py.validate_fields(value)
            elif case['action'] == 'mode':py.validate_mode(value, case['mode'])
            else:py.require_runtime_mode(value, case['mode'])
            outcome={'accepted':True}
        except (ValueError, TypeError, KeyError) as error:
            outcome={'accepted':False,'reason':str(error)}
        rows.append({'index':index, 'name':case['name'], 'expected':case['expected'],
                     'action':case['action'], 'mode':case['mode'],
                     'raw':before[str(path)], 'Python':outcome})
    create(D/'verification/corpus_manifest_v1.json',
           {'schema':'B5-independent-contract-corpus/v1','cases':
            [{k:v for k,v in row.items() if k!='Python'} for row in rows]})
    started=time.monotonic()
    result=subprocess.run([str(binary)],input=b''.join(encoded(r) for r in requests),
                          capture_output=True,timeout=60)
    with (D/'verification/native_parity_stdout_v1.jsonl').open('xb') as f:f.write(result.stdout)
    with (D/'verification/native_parity_stderr_v1.log').open('xb') as f:f.write(result.stderr)
    outcomes=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(outcomes)==len(rows) and result.returncode==0
    for row,native in zip(rows,outcomes):
        row['Native']=native
        row['passed']=(row['Python']['accepted']==native['accepted']==row['expected']
                       and native['spec_sha256']==expected_spec
                       and native['profile_id']==py.SPEC['profile_id']
                       and native['physical_execute_release_enabled'] is False)
    after={path:sha(Path(path)) for path in before}
    passed=all(row['passed'] for row in rows) and before==after
    report={'schema':'B5-current-Python-Native-contract-parity/v1','passed':passed,
            'cases':rows,'case_count':len(rows),'expected_accept_count':sum(r['expected'] for r in rows),
            'expected_reject_count':sum(not r['expected'] for r in rows),
            'failed_cases':[r['name'] for r in rows if not r['passed']],
            'native_elapsed_seconds':time.monotonic()-started,
            'spec_sha256':expected_spec,'input_sha256_before':before,'input_sha256_after':after,
            'old74_rejection_preserved':True,'frozen_shape_does_not_authorize_execute':True,
            'physical_execute_release_enabled':False,'runtime_ROS_runs':0,
            'stage_qualified':False,'research_conclusion':False}
    create(D/'verification/contract_parity_v1.json',report)
    print(json.dumps({k:report[k] for k in ['passed','case_count','expected_accept_count',
                                          'expected_reject_count','failed_cases','native_elapsed_seconds']}))
    return 0 if passed else 2


if __name__=='__main__':
    raise SystemExit(main())
