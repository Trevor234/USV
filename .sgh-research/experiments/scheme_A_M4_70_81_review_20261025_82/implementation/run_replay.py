#!/usr/bin/env python3
"""Bounded independent offline review commands; no role executable is launched."""
from pathlib import Path
import argparse
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
OUT = ROOT / 'evidence/replay01'
AUTHOR = BASE / 'scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3'
RUN = AUTHOR.parent / 'runs/T2B_P01'
sys.dont_write_bytecode = True


def run(directory, name, command, expected=0):
    with (directory / (name + '.stdout')).open('xb') as out, (directory / (name + '.stderr')).open('xb') as err:
        child = subprocess.run(command, stdout=out, stderr=err, timeout=60)
    record = {'command': command, 'returncode': child.returncode,
              'stdout': str((directory / (name + '.stdout')).relative_to(ROOT)),
              'stderr': str((directory / (name + '.stderr')).relative_to(ROOT))}
    assert child.returncode == expected, record
    return record


parser = argparse.ArgumentParser()
parser.add_argument('part', choices=['boundary', 'protocol', 'runtime', 'storage'])
args = parser.parse_args()
directory = OUT / ('protocol' if args.part == 'storage' else args.part)
records = []
if args.part == 'boundary':
    for name in ['extract_timeline', 'probe_audit', 'probe_driver_release']:
        records.append(run(directory, name, [sys.executable, '-B', str(directory / (name + '.py'))]))
    pinned = ROOT / 'evidence/recovered_P01_registered_sources/audit_t2.py'
    records.append(run(directory, 'pinned_audit_cli', [sys.executable, '-B', str(pinned), '--run', str(RUN)], expected=2))
    records.append(run(directory, 'current_audit_cli', [sys.executable, '-B', str(AUTHOR / 'audit_t2.py'), '--run', str(RUN)]))
    sys.path.insert(0, str(AUTHOR))
    import audit_t2
    failures = []
    accounting = audit_t2._api_accounting([
        {'type': 'decision', 'sequence': 1, 'publish_success': [True, True]},
        {'type': 'owned_applied_publication_failed', 'sequence': 1}], failures)
    assert not failures and accounting['applied_rows'] == 1
    with (directory / 'failed_applied_counted_as_success.json').open('x') as stream:
        stream.write(json.dumps({'scope': 'actual accounting helper only, no ROS or run mutation',
                                 'failures': failures, 'result': accounting,
                                 'publication_failure_counted_as_Applied_row': True}, indent=2) + '\n')
elif args.part == 'protocol':
    records.append(run(directory, 'r0_19_tests', [sys.executable, '-B', str(BASE / 'scheme_A_M4_t2_r0_protocol_20261024_75/implementation/test_r0.py')]))
    for name in ['probe', 'fixture_gate_probe', 'probe_t2a_predicates']:
        records.append(run(directory, name, [sys.executable, '-B', str(directory / (name + '.py'))]))
elif args.part == 'runtime':
    records.append(run(directory, 'pair_probe', [sys.executable, '-B', str(directory / 'probe_pair.py')]))
    binary = directory / 'replay_witness'
    records.append(run(directory, 'witness_build', ['c++', '-std=c++17', '-O0', '-pthread', str(directory / 'replay_witness.cpp'), '-o', str(binary)]))
    historical = BASE / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/runs/T2A_14/regulator/witness.json'
    records.append(run(directory, 'witness_original', [str(binary), str(historical)]))
    records.append(run(directory, 'witness_counterfactual', [str(binary), str(historical), 'counterfactual_tick_only']))
else:
    records.append(run(directory, 'generic_P01', [sys.executable, '-B', str(directory / 'validate_t2b_p01.py')]))
with (directory / (args.part + '_replay_result.json')).open('x') as stream:
    stream.write(json.dumps({'part': args.part, 'commands': records,
                             'owned_runs': 0, 'ROS_initialized': False,
                             'scope': 'reproduced review observations and counterexamples, not a family qualification'}, indent=2) + '\n')
print(json.dumps({'part': args.part, 'replay_complete': True, 'commands': len(records), 'owned_runs': 0}))
