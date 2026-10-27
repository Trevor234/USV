#!/usr/bin/env python3
"""Replay original independent policy expectations against the current headers."""
from pathlib import Path
import copy
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'scheme_A_formal_execute_profile_20261020_47'
AUTHOR = ROOT / 'implementation/current_author'
OUTPUT = ROOT / 'evidence/policy92_replay'


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, data):
    with path.open('x') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(data, (dict, list)) else data)


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


OUTPUT.mkdir()
old_report = OLD / 'verification/entry_policy_cases_v2.json'
old_probe = OLD / 'implementation/native/entry_probe_v2.cpp'
historical = json.loads(old_report.read_text())
assert historical['passed'] and historical['case_count'] == len(historical['cases']) == 92
source = old_probe.read_text()
assert source.count('#include "owned_execution_entry_v2.hpp"') == 1
source = source.replace('#include "owned_execution_entry_v2.hpp"',
                        '#include "owned_execution_policy_native_v1.hpp"')
probe = OUTPUT / 'current_entry_probe.cpp'
create(probe, source)
paths = [old_report, old_probe] + [p for p in AUTHOR.rglob('*') if p.is_file()]
before = {str(p): pin(p) for p in paths}
argv = ['g++', '-std=c++17', '-O1', '-I' + str(AUTHOR / 'observer/src/shadow'),
        '-I' + str(AUTHOR / 'common'), str(probe), '-o', str(OUTPUT / 'entry_probe')]
create(OUTPUT / 'compile_argv.json', argv)
compiled = subprocess.run(argv, capture_output=True, timeout=180)
(OUTPUT / 'compile.stdout').write_bytes(compiled.stdout)
(OUTPUT / 'compile.stderr').write_bytes(compiled.stderr)
assert compiled.returncode == 0, compiled.stderr.decode(errors='replace')[-3000:]
cases = copy.deepcopy(historical['cases'])
changes = []
for row in cases:
    request = row['request']
    for context in ('expected', 'actual'):
        gids = request[context].get('output_gids')
        if not isinstance(gids, list):
            continue
        for i, value in enumerate(gids):
            if isinstance(value, str) and re.fullmatch('[0-9a-f]{48}', value):
                request[context]['output_gids'][i] = value[:32]
                changes.append({'case': row['name'], 'context': context, 'index': i,
                                'from_hex_width': 48, 'to_hex_width': 32})
requests = b''.join(encode(row['request']) for row in cases)
(OUTPUT / 'requests.jsonl').write_bytes(requests)
result = subprocess.run([str(OUTPUT / 'entry_probe')], input=requests, capture_output=True, timeout=30)
(OUTPUT / 'stdout.jsonl').write_bytes(result.stdout)
(OUTPUT / 'stderr.log').write_bytes(result.stderr)
assert result.returncode == 0
outputs = [json.loads(line) for line in result.stdout.splitlines()]
assert len(outputs) == len(cases)
rows = []
for case, actual in zip(cases, outputs):
    passed = (actual['accepted'] == case['expected_accepted'] and
              actual['physical_execute_release_enabled'] is False and actual['physical_API_calls'] == 0)
    checks = []
    for check in case['checks']:
        try:
            observed = actual['events'][check['event']]
            for key in check['path'].split('.'):
                observed = observed[key]
            expected = check['value']
            if (type(observed) is list and type(expected) is list and
                    all(type(value) in (int, float) for value in expected)):
                good = len(observed) == len(expected) and all(abs(x - y) < 1e-8 for x, y in zip(observed, expected))
            else:
                good = type(observed) is type(expected) and observed == expected
        except (KeyError, IndexError, TypeError):
            good = False
            observed = None
        checks.append({**check, 'observed_current': observed, 'passed': good})
        passed = passed and good
    rows.append({'name': case['name'], 'expected_accepted': case['expected_accepted'],
                 'checks': checks, 'output': actual, 'passed': passed})
after = {path: pin(Path(path)) for path in before}
loader = subprocess.run(['ldd', str(OUTPUT / 'entry_probe')], capture_output=True, text=True, timeout=10)
create(OUTPUT / 'loader.log', loader.stdout + loader.stderr)
assert loader.returncode == 0 and not re.search('librcl|librmw|libacados', loader.stdout)
summary = {'schema': 'M4-current-policy-original92-replay-v67',
           'historical_report': {'path': str(old_report), **pin(old_report)},
           'current_header': {'path': str(AUTHOR / 'observer/src/shadow/owned_execution_policy_native_v1.hpp'),
                              **pin(AUTHOR / 'observer/src/shadow/owned_execution_policy_native_v1.hpp')},
           'probe': {'path': str(probe), **pin(probe)}, 'ELF': pin(OUTPUT / 'entry_probe'),
           'current_source_unchanged': before == after, 'compile_returncode': compiled.returncode,
           'case_count': len(rows), 'passed_cases': sum(row['passed'] for row in rows), 'cases': rows,
           'declared_request_adaptation': 'Only existing 48hex output GIDs become native 32hex; original accept/refuse and every expected policy fact retained',
           'GID_adaptations': changes, 'no_other_request_or_expectation_changes': True,
           'ROS_initialized': False, 'owned_runs': 0, 'actuator_API_calls': 0,
           'passed': all(row['passed'] for row in rows) and before == after,
           'scope': 'Current pure output policy and synthetic contexts/API facts; not a graph/Worker/Stored run',
           'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False}
create(OUTPUT / 'verification_v1.json', summary)
print(json.dumps({key: summary[key] for key in ('case_count', 'passed_cases', 'passed',
                                               'current_source_unchanged', 'ROS_initialized')}))
raise SystemExit(0 if summary['passed'] else 2)
