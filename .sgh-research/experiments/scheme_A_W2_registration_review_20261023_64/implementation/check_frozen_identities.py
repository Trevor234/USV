#!/usr/bin/env python3
"""Read-only static identity and current loader resolution audit; no role runs."""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent / 'scheme_A_W2_registration_20261023_63'
IMPL = PKG / 'implementation'
AUTHOR = IMPL / 'w2_author'
OUT = ROOT / 'evidence/identity_check'
OUT.mkdir(exist_ok=False)


def read(path):
    return json.loads(Path(path).read_text())


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def constants(path):
    result = {}
    for node in ast.parse(Path(path).read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = node.value.value
    return result


reg = read(IMPL / 'W2_registration_v1.json')
registry = read(reg['registry'])
freeze = read(PKG / 'evidence/freeze_and_build/freeze_and_build_v1.json')
driver = Path(registry['driver'])
dc = constants(driver)
seal = ROOT.parent / 'scheme_A_M4_diagnostic_worker_20261021_56/seal_selected_runtime_diagnostic_v1.py'
sc = constants(seal)
assert reg['index_sha256'] == dc['INDEX_SHA'] == sc['EVIDENCE']
assert pin(reg['registry'])['sha256'] == reg['registry_sha256']
assert pin(driver)['sha256'] == registry['driver_tool_sha256'] == freeze['driver']['sha256']
assert pin(reg['contract'])['sha256'] == reg['contract_sha256'] == dc['CONTRACT_SHA']
assert pin(reg['topics'])['sha256'] == reg['topics_sha256']
assert pin(reg['index'])['sha256'] != reg['index_sha256']
roles = {}
for role, record in registry['roles'].items():
    bundle_path = Path(record['source_bundle']['path'])
    assert pin(bundle_path)['sha256'] == record['source_bundle']['sha256']
    bundle = read(bundle_path)
    rows = bundle['files']
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    mismatch = [row['path'] for row in rows if pin(row['path']) != {
        'bytes': row['bytes'], 'sha256': row['sha256']}]
    assert not mismatch, mismatch
    binary = Path(record['binary'])
    assert pin(binary)['sha256'] == record['binary_sha256']
    assert binary.read_bytes().startswith(b'\x7fELF')
    roles[role] = {'binary': str(binary), **pin(binary),
                   'bundle_sha256': pin(bundle_path)['sha256'], 'bundle_files': len(rows),
                   'bundle_file_mismatches': mismatch}
    if role != 'recorder':
        strings = subprocess.run(['strings', str(binary)], capture_output=True,
                                 text=True, timeout=30)
        assert strings.returncode == 0
        assert registry['source_bundle_sha256'] in strings.stdout
        assert registry['driver_tool_sha256'] in strings.stdout
        roles[role]['identity_literals_present'] = True

bundle = read(freeze['source_bundle']['path'])
assert len(bundle['files']) == bundle['file_count'] == 95
population = {str(p.relative_to(AUTHOR)) for p in AUTHOR.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
assert population == set(bundle['files'])
build = PKG / 'evidence/freeze_and_build/cmake_build'
cache = (build / 'CMakeCache.txt').read_text()
assert 'CMAKE_HOME_DIRECTORY:INTERNAL=' + str(AUTHOR) in cache
commands = read(build / 'compile_commands.json')
source_suffixes = ['worker/solver_worker_m4.cpp',
                   'observer/src/shadow/regulator_owned_execute.cpp',
                   'fixture/synthetic_source_m4.cpp']
compile_evidence = []
for suffix in source_suffixes:
    row = next(x for x in commands if x['file'] == str(AUTHOR / suffix))
    argv = row.get('arguments') or shlex.split(row['command'])
    defines = {}
    for arg in argv:
        if arg.startswith('-DP1_') and '=' in arg:
            name, value = arg[2:].split('=', 1)
            defines[name] = value.strip('"')
    assert defines['P1_OWNED_SOURCE_BUNDLE_SHA256'] == registry['source_bundle_sha256']
    assert defines['P1_DRIVER_TOOL_SHA256'] == registry['driver_tool_sha256']
    compile_evidence.append({'file': row['file'], 'defines': defines})

env = dict(os.environ)
env['LD_LIBRARY_PATH'] = '/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:/opt/ros/jazzy/lib:/home/trevor/USV/usv_mpc_ws/install/usv_research_interfaces/lib'
worker = Path(registry['roles']['worker']['binary'])
loader = subprocess.run(['ldd', str(worker)], capture_output=True, text=True,
                        env=env, timeout=30)
(OUT / 'worker_ldd.stdout.txt').write_text(loader.stdout)
(OUT / 'worker_ldd.stderr.txt').write_text(loader.stderr)
assert loader.returncode == 0
resolved = {}
for line in loader.stdout.splitlines():
    match = re.match(r'\s*(\S+)\s+=>\s+(/\S+)', line)
    if match:
        resolved[match.group(1)] = Path(match.group(2))
runtime = {}
for name, expected in registry['acados_runtime'].items():
    candidates = [value for key, value in resolved.items()
                  if key == name or key.startswith(name + '.')]
    assert len(candidates) == 1, (name, candidates)
    actual = candidates[0]
    current = pin(actual)
    assert current == expected, (name, current, expected)
    runtime[name] = {'loader_path': str(actual), 'resolved_real_path': str(actual.resolve()),
                     **current, 'matches_registry_now': True}
out = Path(reg['output'])
assert out.is_absolute() and out.parent == IMPL / 'runs' and out.parent.is_dir()
assert not out.exists(), 'The registered run output already exists; preserve it and do not reuse'
report = {
    'schema': 'W2-independent-static-registration-identity-v1',
    'source_bundle_sha256': pin(freeze['source_bundle']['path'])['sha256'],
    'source_bundle_file_count': len(bundle['files']),
    'driver_sha256': pin(driver)['sha256'], 'registry_sha256': pin(reg['registry'])['sha256'],
    'registration_sha256': pin(IMPL / 'W2_registration_v1.json')['sha256'],
    'roles': roles, 'compile_identity_defines': compile_evidence,
    'all_static_checks_passed': True,
    'index_marker': {'value': reg['index_sha256'], 'defined_by': str(seal),
                     'seal_script': pin(seal), 'meaning': 'Inherited EVIDENCE marker, not file SHA',
                     'index_file_actual_sha256': pin(reg['index'])['sha256']},
    'runtime_libraries_match_current_loader_resolution': runtime,
    'runtime_file_checks_performed_now': True,
    'registered_driver_checks_loaded_runtime_libraries': False,
    'worker_proc_maps_checked': False,
    'identity_chain_closed_at_owned_runtime': False,
    'registered_output_absent': True, 'roles_executed': False,
    'ROS_started': False, 'owned_run_performed': False,
    'limits': 'Strings plus recorded compiler definitions substantiate build identity; no claim of replayed build or runtime /proc maps authentication',
}
(OUT / 'verification_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key: report[key] for key in [
    'source_bundle_sha256', 'source_bundle_file_count', 'driver_sha256',
    'registry_sha256', 'registration_sha256', 'all_static_checks_passed',
    'registered_output_absent', 'identity_chain_closed_at_owned_runtime']}, ensure_ascii=False))
