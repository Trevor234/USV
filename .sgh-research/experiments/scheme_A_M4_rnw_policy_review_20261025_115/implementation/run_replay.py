#!/usr/bin/env python3
"""Finite artifact/header/AST review only; never import the live runner."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/replay01'
sys.dont_write_bytecode = True


def run(directory, name, command):
    with (directory / (name + '.stdout')).open('xb') as out, (directory / (name + '.stderr')).open('xb') as err:
        child = subprocess.run(command, stdout=out, stderr=err, timeout=60)
    record = {'command': command, 'returncode': child.returncode,
              'stdout': str((directory / (name + '.stdout')).relative_to(ROOT)),
              'stderr': str((directory / (name + '.stderr')).relative_to(ROOT))}
    assert child.returncode == 0, record
    return record


parser = argparse.ArgumentParser()
parser.add_argument('part', choices=['clock', 'policy', 'fixture'])
args = parser.parse_args()
directory = OUT / args.part
records = []
if args.part == 'clock':
    for name in ['analyze', 'replay_generate']:
        records.append(run(directory, name, [sys.executable, '-B', str(directory / (name + '.py'))]))
elif args.part == 'fixture':
    records.append(run(directory, 'fixture_probe', [sys.executable, '-B', str(directory / 'probe.py')]))
else:
    build = directory / 'build'
    build.mkdir()
    for name in ['probe', 'authority_interface']:
        executable = build / name
        records.append(run(directory, name + '_build', ['g++', '-std=c++17', '-pthread', str(directory / (name + '.cpp')), '-o', str(executable)]))
        records.append(run(directory, name, [str(executable)]))
with (directory / 'replay_result.json').open('x') as stream:
    stream.write(json.dumps({'part': args.part, 'commands': records, 'owned_runs': 0,
                             'ROS_initialized': False, 'new_policy_implemented': False,
                             'scope': 'review replay completion, not a resume policy qualification'}, indent=2) + '\n')
print(json.dumps({'part': args.part, 'review_replay_complete': True, 'commands': len(records), 'owned_runs': 0}))
