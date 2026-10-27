#!/usr/bin/env python3
"""Bounded affected tests, with ROS restricted to isolated local mock peers."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET

D = Path(__file__).resolve().parent
W = Path('/home/trevor/USV')


def pin(p):
    b = Path(p).read_bytes()
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def main():
    build = json.loads((D / 'build/attempt01/build_manifest_v1.json').read_bytes())
    assert build['passed']
    root = D / 'verification/run01'
    root.mkdir()
    helper = D.parent / 'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree = ast.parse(helper.read_bytes())
    setup = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SETUP' for t in n.targets))
    setup += '\nexport ROS_DOMAIN_ID=122 ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1\n'
    inputs = {**build['source_after'], str(W / 'usv_mpc_ws/src/usv_bringup/test/test_fcu_mode_contract.py'): pin(W / 'usv_mpc_ws/src/usv_bringup/test/test_fcu_mode_contract.py'),
              **{row['path']: {k: row[k] for k in ['bytes', 'sha256']} for row in build['targets'].values()}}
    for name, expected in inputs.items():
        assert pin(name) == expected
    with (D / 'preflight/test_inputs_v1.json').open('x') as f:
        json.dump({'registered_before_launch': True, 'inputs': inputs, 'automatic_retries': 0,
                   'ROS_domain': 122, 'MAVROS_or_FCU_processes': 0, 'private_mock_mode_requests_only': True}, f, indent=2);f.write('\n')
    commands = []
    counts = {}
    for name, budget in [('test_deadline_control', 60), ('test_mode_manager_contract', 30), ('launch_parameters', 60)]:
        xml = root / (name + '.xml')
        if name == 'launch_parameters':
            argv = ['/usr/bin/python3', '-B', '-m', 'pytest', '-q', str(W / 'usv_mpc_ws/src/usv_bringup/test/test_fcu_mode_contract.py'),
                    '--junitxml=' + str(xml), '-o', 'cache_dir=' + str(root / 'pytest_cache')]
        else:
            argv = [build['targets'][name]['path'], '--gtest_output=xml:' + str(xml)]
        script = root / (name + '.sh')
        with script.open('x') as f:
            f.write('set -e\n' + setup + '\nexec timeout --signal=TERM --kill-after=5s ' + str(budget) + 's ' + shlex.join(argv) + '\n')
        start = time.monotonic()
        with (root / (name + '.stdout.log')).open('xb') as out, (root / (name + '.stderr.log')).open('xb') as err:
            result = subprocess.run(['/bin/bash', str(script)], stdout=out, stderr=err, timeout=budget + 10)
        tree = ET.parse(xml).getroot() if xml.exists() else None
        if tree is None:
            count = None
        elif 'tests' in tree.attrib:
            count = {k: int(tree.attrib.get(k, '0')) for k in ['tests', 'failures', 'errors', 'disabled', 'skipped']}
        else:
            count = {k: sum(int(row.attrib.get(k, '0')) for row in tree.findall('testsuite')) for k in ['tests', 'failures', 'errors', 'disabled', 'skipped']}
        counts[name] = count
        row = {'name': name, 'returncode': result.returncode, 'elapsed_seconds': time.monotonic() - start, 'counts': count, 'argv': argv}
        commands.append(row);print(json.dumps(row), flush=True)
    after = {name: pin(name) for name in inputs}
    passed = all(row['returncode'] == 0 and row['counts'] and row['counts']['tests'] > 0 and not any(row['counts'][k] for k in ['failures', 'errors', 'disabled', 'skipped']) for row in commands) and inputs == after
    report = {'schema': 'SchemeB-MANUAL-contract-affected-verification/v1', 'passed': passed,
              'commands': commands, 'counts': counts, 'input_before': inputs, 'input_after': after,
              'real_FCU_requests': 0, 'private_mock_mode_requests_only': True, 'production_install_replaced': False,
              'real_ship_acceptance': False, 'M4_F6_P1_qualified': False}
    with (D / 'verification/contract_checks_v1.json').open('x') as f:
        json.dump(report, f, indent=2, sort_keys=True);f.write('\n')
    print(json.dumps({'passed': passed, 'counts': counts}))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
