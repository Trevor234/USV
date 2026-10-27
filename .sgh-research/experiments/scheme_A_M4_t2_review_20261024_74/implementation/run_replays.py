#!/usr/bin/env python3
"""Finite offline replays. Each raw output is created once; no ROS init."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
AUTHOR = ROOT.parent / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/t2_author_rev8'


def run(directory, name, command):
    with (directory / (name + '.stdout')).open('xb') as out, (directory / (name + '.stderr')).open('xb') as err:
        process = subprocess.run(command, stdout=out, stderr=err, timeout=60)
    record = {'command': command, 'returncode': process.returncode,
              'stdout': str((directory / (name + '.stdout')).relative_to(ROOT)),
              'stderr': str((directory / (name + '.stderr')).relative_to(ROOT))}
    assert process.returncode == 0, record
    return record


parser = argparse.ArgumentParser()
parser.add_argument('part', choices=['contract', 'clock', 'boundary'])
args = parser.parse_args()
directory = ROOT / 'evidence/independent_replay01' / args.part
records = []
if args.part == 'contract':
    records.append(run(directory, 'contract', [sys.executable, '-B', str(directory / 'review.py')]))
    # Confirm the actual frozen CLI (not just a helper) accepts the invalid flow.
    with (directory / 'bad_cli.stdout').open('xb') as out, (directory / 'bad_cli.stderr').open('xb') as err:
        command = [sys.executable, '-B', str(AUTHOR / 'audit_t2.py'), '--run',
                   str(directory / 'accepted_target_after_request')]
        child = subprocess.run(command, stdout=out, stderr=err, timeout=15)
    doc = json.loads((directory / 'bad_cli.stdout').read_bytes())
    assert child.returncode == 0 and doc['passed'] is True
    records.append({'command': command, 'returncode': child.returncode,
                    'invalid_flow_accepted_by_frozen_audit': True})
elif args.part == 'clock':
    build = directory / 'build'
    build.mkdir()
    binary = build / 'replay_anchor'
    records.append(run(directory, 'build', ['g++', '-std=c++17', '-O0',
                        str(directory / 'replay_anchor.cpp'), '-o', str(binary)]))
    records.append(run(directory, 'replay_anchor', [str(binary)]))
    # The Python replay reads this filename beside itself; preserve exact bytes.
    with (directory / 'replay_anchor.stdout.json').open('xb') as stream:
        stream.write((directory / 'replay_anchor.stdout').read_bytes())
    records.append(run(directory, 'validator', [sys.executable, '-B', str(directory / 'validate_t2a14.py')]))
else:
    records.append(run(directory, 'measure', [sys.executable, '-B', str(directory / 'measure.py')]))
    build = directory / 'build'
    build.mkdir()
    binary = build / 'epoch_probe'
    repo = ROOT.parents[2]
    records.append(run(directory, 'build', ['g++', '-std=c++17', '-O0', '-I/usr/include/eigen3',
                        '-I' + str(AUTHOR / 'observer/src/shadow'), '-I' + str(AUTHOR / 'common'),
                        '-I' + str(repo / 'usv_mpc_ws/src/usv_mpc_cpp/include'),
                        str(directory / 'epoch_probe.cpp'), str(repo / 'usv_mpc_ws/src/usv_mpc_cpp/src/utils.cpp'),
                        '-o', str(binary)]))
    records.append(run(directory, 'epoch_probe', [str(binary)]))
with (directory / 'replay_result.json').open('x') as stream:
    stream.write(json.dumps({'part': args.part, 'commands': records,
                             'owned_started': False, 'ROS_initialized': False}, indent=2) + '\n')
print(json.dumps({'part': args.part, 'replay_finished': True, 'commands': len(records),
                  'owned_started': False}))
