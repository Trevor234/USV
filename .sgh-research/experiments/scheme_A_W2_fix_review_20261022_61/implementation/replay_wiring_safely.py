#!/usr/bin/env python3
"""Replay the submitted runner without changing submitted source or evidence."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'scheme_A_W2_hook_review_20261022_60/implementation/w2_author'
OUT = ROOT / 'evidence/wiring_replay'
OUT.mkdir(exist_ok=False)
script = SOURCE / 'worker/run_wiring_verification.py'
scope = {'__file__': str(script), '__name__': 'submitted_wiring_runner'}
exec(compile(script.read_text(), str(script), 'exec'), scope)
scope['OUT'] = OUT
script_counter = 0
suite_counter = 0
stages = ['baseline', *scope['MUTATIONS']]


def run_script(body, timeout=600):
    global script_counter
    stage = OUT / ('command_%02d' % script_counter)
    script_counter += 1
    path = stage.with_suffix('.sh')
    path.write_text(body)
    result = subprocess.run(['/bin/bash', str(path)], capture_output=True,
                            text=True, timeout=timeout)
    stage.with_suffix('.stdout.txt').write_text(result.stdout)
    stage.with_suffix('.stderr.txt').write_text(result.stderr)
    stage.with_suffix('.json').write_text(json.dumps({
        'argv': ['/bin/bash', str(path)], 'returncode': result.returncode}, indent=2) + '\n')
    return result


def run_suite(build, name):
    global suite_counter
    stage = stages[suite_counter // len(scope['SUITES'])]
    suite_counter += 1
    folder = OUT / stage
    folder.mkdir(exist_ok=True)
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin',
           'LD_LIBRARY_PATH': '/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'}
    binary = build / name
    result = subprocess.run([str(binary)], capture_output=True, text=True,
                            env=env, timeout=300)
    (folder / (name + '.stdout.txt')).write_text(result.stdout)
    (folder / (name + '.stderr.txt')).write_text(result.stderr)
    (folder / (name + '.json')).write_text(json.dumps({
        'argv': [str(binary)], 'env': env, 'returncode': result.returncode,
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}, indent=2) + '\n')
    shutil.copy2(binary, folder / name)
    if name == scope['SUITES'][0]:
        cache = (build / 'CMakeCache.txt').read_text()
        src_line = next(line for line in cache.splitlines()
                        if line.startswith('CMAKE_HOME_DIRECTORY:INTERNAL='))
        author = Path(src_line.split('=', 1)[1])
        for rel in ['worker/w2_native_boundary.hpp', 'worker/owned_cold_backend.hpp',
                    'worker/raw_backend_v1.hpp', 'worker/test_w2_entry_contract.cpp']:
            target = folder / 'source' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(author / rel, target)
        (folder / 'cmake_source_root.txt').write_text(src_line + '\n')
        shutil.copy2(build / 'compile_commands.json', folder / 'compile_commands.json')
    return result.returncode == 0, result.stdout


scope['run_script'] = run_script
scope['run_suite'] = run_suite
code = scope['main']()
assert code == 0, code
print(json.dumps({'replay_exit_code': code, 'commands': script_counter,
                  'suite_runs': suite_counter, 'evidence': str(OUT)}))
