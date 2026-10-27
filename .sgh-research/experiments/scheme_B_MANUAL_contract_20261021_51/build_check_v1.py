#!/usr/bin/env python3
"""Isolated corrected binaries and affected tests; never install or start a FCU link."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

D = Path(__file__).resolve().parent
W = Path('/home/trevor/USV')


def pin(p):
    b = Path(p).read_bytes()
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def main():
    root = D / 'build/attempt01'
    root.mkdir()
    names = list(json.loads((D / 'preflight/workspace_and_source_before_v1.json').read_bytes())['files'])
    names += ['usv_mpc_ws/src/usv_safety_cpp/test/test_mode_manager_contract.cpp', 'docs/scheme_B_manual_rc_contract.md']
    before = {str(W / n): pin(W / n) for n in names}
    with (D / 'preflight/corrected_source_before_build_v1.json').open('x') as f:
        json.dump(before, f, indent=2, sort_keys=True);f.write('\n')
    helper = D.parent / 'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree = ast.parse(helper.read_bytes())
    setup = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SETUP' for t in n.targets))
    rows = []
    def run(name, argv, seconds):
        script = root / (name + '.sh')
        with script.open('x') as f:
            f.write('set -e\n' + setup + '\nexec timeout --signal=TERM --kill-after=5s ' + str(seconds) + 's ' + shlex.join(argv) + '\n')
        start = time.monotonic()
        with (root / (name + '.stdout.log')).open('xb') as out, (root / (name + '.stderr.log')).open('xb') as err:
            r = subprocess.run(['/bin/bash', str(script)], stdout=out, stderr=err, timeout=seconds + 10)
        row = {'name': name, 'returncode': r.returncode, 'elapsed_seconds': time.monotonic() - start, 'argv': argv}
        rows.append(row);print(json.dumps(row), flush=True)
        return r.returncode
    build = root / 'cmake_build'
    rc = run('configure', ['cmake', '-S', str(D / 'implementation'), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'], 120)
    targets = ['corrected_mpc_node', 'corrected_mode_manager_node', 'test_deadline_control', 'test_mode_manager_contract']
    completed = {}
    if rc == 0:
        for name in targets:
            rc = run('build_' + name, ['cmake', '--build', str(build), '--target', name, '-j1'], 180)
            if rc:
                break
            completed[name] = {'path': str(build / name), **pin(build / name)}
    after = {n: pin(n) for n in before}
    result = {'schema': 'SchemeB-MANUAL-contract-isolated-build/v1', 'passed': rc == 0 and len(completed) == 4 and before == after,
              'commands': rows, 'targets': completed, 'source_before': before, 'source_after': after,
              'production_install_changed': False, 'FCU_or_MAVROS_started': False, 'new_control_codegen': False,
              'scheme_A_M4_F6_P1_qualification_promoted': False}
    with (root / 'build_manifest_v1.json').open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True);f.write('\n')
    print(json.dumps({'passed': result['passed'], 'built_targets': len(completed)}))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
