#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'evidence/reviewed_input_snapshot/implementation/w2_author'
OUT = ROOT / 'evidence/private_role_compile'
OUT.mkdir(exist_ok=False)
PRIVATE = OUT / 'author'
BUILD = OUT / 'build'
shutil.copytree(SOURCE, PRIVATE, ignore=shutil.ignore_patterns('__pycache__'))
scope = {'__file__': str(SOURCE / 'worker/run_wiring_verification.py'), '__name__': 'submitted_runner'}
exec(compile((SOURCE / 'worker/run_wiring_verification.py').read_text(), scope['__file__'], 'exec'), scope)


def shell(name, body):
    path = OUT / (name + '.sh')
    path.write_text(body)
    result = subprocess.run(['/bin/bash', str(path)], capture_output=True,
                            text=True, timeout=600)
    (OUT / (name + '.stdout.txt')).write_text(result.stdout)
    (OUT / (name + '.stderr.txt')).write_text(result.stderr)
    (OUT / (name + '.json')).write_text(json.dumps({
        'argv': ['/bin/bash', str(path)], 'returncode': result.returncode}, indent=2) + '\n')
    print(name, result.returncode, flush=True)
    return result


assert shell('configure', scope['CONFIGURE'].format(src=PRIVATE, build=BUILD)).returncode == 0
assert 'CMAKE_HOME_DIRECTORY:INTERNAL=' + str(PRIVATE) in (BUILD / 'CMakeCache.txt').read_text()
targets = ['p1_m4_worker_owned', 'p1_m4_regulator_owned', 'p1_m4_fixture_owned']
result = shell('build', scope['BUILD'].format(build=BUILD, targets=' '.join(targets)).replace('-j2', '-j1'))
if result.returncode:
    print(result.stderr[-3000:])
    raise SystemExit(result.returncode)
report = {'schema': 'W2-closeout-private-role-compile-v1', 'roles': targets,
          'all_built': True, 'role_execution': False, 'registry_created': False,
          'compile_identity_values': 'x placeholders, not a legal owned source',
          'source': str(PRIVATE),
          'binaries': {name: hashlib.sha256((BUILD / name).read_bytes()).hexdigest()
                       for name in targets}}
(OUT / 'verification_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False), flush=True)
