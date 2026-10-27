#!/usr/bin/env python3
"""One registered private-topic component process with exact inputs and finite cleanup."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

D = Path(__file__).resolve().parent
B = D / 'build/component_attempt01'


def pin(path):
    h = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as f:
        while b := f.read(1024 * 1024):
            h.update(b)
            size += len(b)
    return {'bytes': size, 'sha256': h.hexdigest()}


def emit(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')


def proc(pid):
    text = Path(f'/proc/{pid}/stat').read_text()
    rest = text[text.rfind(')') + 2:].split()
    return {'pid': pid, 'state': rest[0], 'pgid': int(rest[2]), 'start_ticks': int(rest[19]),
            'exe': str(Path(f'/proc/{pid}/exe').resolve(strict=True))}


def group_members(pgid):
    found = []
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            text = path.read_text()
            rest = text[text.rfind(')') + 2:].split()
            if int(rest[2]) == pgid:
                found.append({'pid': int(path.parent.name), 'state': rest[0]})
        except (OSError, ValueError):
            pass
    return found


def main():
    assert json.loads((D / 'preflight/workspace_initial_v1.json').read_bytes())['passed']
    build = json.loads((B / 'build_manifest_v1.json').read_bytes())
    assert build['passed'] and ' T rcl_publish' in build['test_only_rcl_publish_export']
    root = D / 'verification/component_run01'
    root.mkdir()
    cases_root = root / 'cases'
    cases_root.mkdir()
    case_names = re.findall(r'^TEST_F\(PublicationFault,([A-Za-z0-9_]+)\)', (D / 'author/test_m4_publication_faults.cpp').read_text(), re.M)
    assert len(case_names) == len(set(case_names)) == 16
    helper = D.parent / 'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree = ast.parse(helper.read_bytes())
    setup = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SETUP' for t in n.targets))
    setup += '\nexport ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n'
    setup += '\nexport P1_M4_COMPONENT_OUTPUT=' + shlex.quote(str(cases_root)) + '\n'
    target = Path(build['target']['path'])
    assert pin(target) == {k: build['target'][k] for k in ['bytes', 'sha256']}
    ldd_script = root / 'loader.sh'
    with ldd_script.open('x') as f:
        f.write('set -e\n' + setup + '\nexec ldd ' + shlex.quote(str(target)) + '\n')
    ldd = subprocess.run(['/bin/bash', str(ldd_script)], capture_output=True, text=True, timeout=30)
    assert ldd.returncode == 0 and 'not found' not in ldd.stdout
    with (root / 'loader.stdout.log').open('x') as f:
        f.write(ldd.stdout)
    libraries = {}
    for line in ldd.stdout.splitlines():
        value = line.strip().split('=>', 1)[-1].strip().split(' ', 1)[0]
        if value.startswith('/'):
            path = Path(value).resolve(strict=True)
            libraries[str(path)] = pin(path)
    assert libraries
    argv = [str(target), '--gtest_output=xml:' + str(root / 'gtest.xml')]
    run_script = root / 'run.sh'
    with run_script.open('x') as f:
        f.write('set -e\n' + setup + '\nexec ' + shlex.join(argv) + '\n')
    inputs = {**build['compiler_dependencies'], **libraries,
              **{str(p): pin(p) for p in [Path(__file__).resolve(), B / 'build_manifest_v1.json', target, helper, run_script,
                                         D / 'author/CMakeLists.txt', D / 'author/test_m4_publication_faults.cpp',
                                         D / 'preflight/preflight_reflection_v1.md', D / 'implementation/work_package_v1.json',
                                         D.parent / 'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json']}}
    for name, expected in inputs.items():
        assert pin(name) == expected, name
    emit(D / 'preflight/component_registration_v1.json', {
        'schema': 'M4-publication-fault-component-prerun-registration/v1',
        'registered_before_test': True, 'cases': case_names, 'inputs': inputs, 'argv': argv,
        'test_wall_seconds': 90, 'automatic_retries': 0,
        'cleanup_seconds': {'INT': 2.5, 'TERM': 1, 'KILL': 1},
        'test_only_error_return_interposition': True, 'success_delegates_to_actual_RCL': True,
        'production_source_modified': False, 'full_owned_entry_or_M4_run': False,
        'actuator_topic_publishers': 0, 'M4_stage_qualified': False, 'P1_qualified': False})
    start = time.monotonic()
    signals = []
    timed_out = False
    identity = None
    with (root / 'stdout.log').open('xb') as out, (root / 'stderr.log').open('xb') as err:
        child = subprocess.Popen(['/bin/bash', str(run_script)], stdout=out, stderr=err, start_new_session=True)
        launch_deadline = time.monotonic() + 5
        while child.poll() is None and time.monotonic() < launch_deadline:
            observed = proc(child.pid)
            if observed['exe'] == str(target.resolve()):
                identity = observed
                break
            time.sleep(.002)
        try:
            rc = child.wait(timeout=max(.001, 90 - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            timed_out = True
            for sig, grace in [(signal.SIGINT, 2.5), (signal.SIGTERM, 1), (signal.SIGKILL, 1)]:
                if child.poll() is not None:
                    break
                assert identity is not None, 'no authenticated test process identity for cleanup'
                current = proc(child.pid)
                assert all(current[k] == identity[k] for k in ['pid', 'pgid', 'start_ticks', 'exe']) and current['pgid'] == child.pid
                assert pin(target) == {k: build['target'][k] for k in ['bytes', 'sha256']}
                os.killpg(child.pid, sig)
                signals.append({'signal': sig.name, 'sent_ns': time.monotonic_ns(), 'grace_seconds': grace})
                try:
                    child.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    pass
            rc = child.poll()
    members = group_members(child.pid)
    after = {name: pin(name) for name in inputs}
    cases = sorted(p.parent.name for p in cases_root.glob('*/case.json'))
    xml_counts = None
    if (root / 'gtest.xml').exists():
        xml = ET.parse(root / 'gtest.xml').getroot()
        xml_counts = {key: int(xml.attrib.get(key, '0')) for key in ['tests', 'failures', 'errors', 'disabled']}
    passed = rc == 0 and not timed_out and not members and identity is not None and inputs == after
    passed = passed and cases == sorted(case_names) and xml_counts == {'tests': 16, 'failures': 0, 'errors': 0, 'disabled': 0}
    emit(D / 'verification/component_verification_v1.json', {
        'schema': 'M4-exact49-publication-fault-component-verification/v1', 'passed': passed,
        'returncode': rc, 'timed_out': timed_out, 'elapsed_seconds': time.monotonic() - start,
        'actual_process_identity': identity, 'signals': signals, 'group_members_after': members, 'group_empty': not members,
        'XML': xml_counts, 'completed_cases': cases, 'input_before': inputs, 'input_after': after,
        'production_source_modified': False, 'new_production_runtime_builds': 0,
        'full_owned_M4_runs': 0, 'actuator_topic_publishers': 0,
        'ordinary_production_release_enabled': False, 'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'research_conclusion': False})
    print(json.dumps({'passed': passed, 'returncode': rc, 'XML': xml_counts, 'group_empty': not members, 'elapsed_seconds': time.monotonic() - start}))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
