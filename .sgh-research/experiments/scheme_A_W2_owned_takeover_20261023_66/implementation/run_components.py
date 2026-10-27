#!/usr/bin/env python3
from pathlib import Path
import json
import subprocess
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
AUTHOR = ROOT / 'implementation/w2_author'
OUT = ROOT / 'evidence/component_attempt01'
OUT.mkdir(exist_ok=False)
BUILD = OUT / 'build'
runner = AUTHOR / 'worker/run_wiring_verification.py'
scope = {'__file__': str(runner), '__name__': 'configuration_only'}
exec(compile(runner.read_text(), str(runner), 'exec'), scope)
for name, body in [('configure', scope['CONFIGURE'].format(src=AUTHOR, build=BUILD)),
                   ('build', scope['BUILD'].format(build=BUILD, targets=' '.join(scope['SUITES'])))]:
    path = OUT / (name + '.sh'); path.write_text(body)
    with (OUT / (name + '.stdout.txt')).open('w') as stdout, (OUT / (name + '.stderr.txt')).open('w') as stderr:
        result = subprocess.run(['/bin/bash', str(path)], stdout=stdout, stderr=stderr, timeout=600)
    print(name, result.returncode, flush=True)
    if result.returncode: raise SystemExit(result.returncode)
env = {'PATH': '/usr/bin:/bin', 'LD_LIBRARY_PATH': '/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'}
report = {'schema': 'W2-takeover-components-v1', 'scope': 'C++ components, x identity, no ROS/owned run', 'suites': {}}
for name in scope['SUITES']:
    result = subprocess.run([str(BUILD / name)], capture_output=True, text=True, env=env, timeout=120)
    (OUT / (name + '.stdout.txt')).write_text(result.stdout)
    (OUT / (name + '.stderr.txt')).write_text(result.stderr)
    report['suites'][name] = {'returncode': result.returncode, **scope['summary'](result.stdout)}
    print(name, report['suites'][name], flush=True)
report['all_passed'] = all(row['returncode'] == 0 for row in report['suites'].values())
(OUT / 'verification_v1.json').write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(0 if report['all_passed'] else 1)
