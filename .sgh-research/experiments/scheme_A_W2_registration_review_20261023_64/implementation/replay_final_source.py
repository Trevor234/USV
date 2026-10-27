#!/usr/bin/env python3
"""Replay frozen final source in a private island; no writes to batches62/63."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'evidence/input_snapshot/batch63/implementation/w2_author'
CLONE = ROOT / 'implementation/replay_author'
OUT = ROOT / 'evidence/final_source_replay'
ISLAND = ROOT / 'evidence/replay_workspace'
OUT.mkdir(exist_ok=False)
ISLAND.mkdir(exist_ok=False)
shutil.copytree(FROZEN, CLONE, ignore=shutil.ignore_patterns('__pycache__'))
script = CLONE / 'worker/run_wiring_verification.py'
scope = {'__file__': str(script), '__name__': 'submitted_runner'}
exec(compile(script.read_text(), str(script), 'exec'), scope)
scope['OUT'] = OUT
stages = ['baseline', *scope['MUTATIONS']]
stage_index = -1
command_index = 0
extra_index = 0


def run_script(body, timeout=600):
    global stage_index, command_index
    if 'exec cmake -S ' in body:
        stage_index += 1
    base = OUT / ('command_%02d' % command_index)
    command_index += 1
    path = base.with_suffix('.sh')
    path.write_text(body)
    result = subprocess.run(['/bin/bash', str(path)], capture_output=True,
                            text=True, timeout=timeout)
    base.with_suffix('.stdout.txt').write_text(result.stdout)
    base.with_suffix('.stderr.txt').write_text(result.stderr)
    base.with_suffix('.json').write_text(json.dumps({
        'argv': ['/bin/bash', str(path)], 'returncode': result.returncode}, indent=2) + '\n')
    return result


def run_suite(build, name):
    folder = OUT / stages[stage_index]
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
        source = next(line.split('=', 1)[1] for line in (build / 'CMakeCache.txt').read_text().splitlines()
                      if line.startswith('CMAKE_HOME_DIRECTORY:INTERNAL='))
        for rel in ['worker/w2_native_boundary.hpp', 'worker/owned_cold_backend.hpp',
                    'worker/raw_backend_v1.hpp', 'worker/w2_entry_contract.hpp',
                    'worker/solver_worker_m4.cpp']:
            target = folder / 'source' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(source) / rel, target)
        shutil.copy2(build / 'compile_commands.json', folder / 'compile_commands.json')
    return result.returncode == 0, result.stdout


def extra_run(argv, **kwargs):
    global extra_index
    name = ('extra_%02d_' % extra_index) + Path(argv[-1]).stem
    extra_index += 1
    result = subprocess.run(argv, **kwargs)
    (OUT / (name + '.stdout.txt')).write_text(result.stdout)
    (OUT / (name + '.stderr.txt')).write_text(result.stderr)
    (OUT / (name + '.json')).write_text(json.dumps({
        'argv': [str(x) for x in argv], 'returncode': result.returncode,
        'phase': stages[stage_index]}, indent=2) + '\n')
    if Path(argv[-1]).is_file():
        shutil.copy2(argv[-1], OUT / (name + '.py'))
    return result


scope['run_script'] = run_script
scope['run_suite'] = run_suite
scope['subprocess'] = types.SimpleNamespace(run=extra_run)
scope['tempfile'] = types.SimpleNamespace(
    TemporaryDirectory=lambda prefix: tempfile.TemporaryDirectory(prefix=prefix, dir=ISLAND))
code = scope['main']()
assert code == 0, code
assert all(a.read_bytes() == (FROZEN / a.relative_to(CLONE)).read_bytes()
           for a in CLONE.rglob('*') if a.is_file() and '__pycache__' not in a.parts)
print(json.dumps({'exit_code': code, 'shell_commands': command_index,
                  'nested_checks': extra_index, 'no_original_package_write': True}))
