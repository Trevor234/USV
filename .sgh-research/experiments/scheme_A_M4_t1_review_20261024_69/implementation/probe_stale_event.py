#!/usr/bin/env python3
"""One private C++ counterexample: omit the new-Job call, keep old assertions."""
from pathlib import Path
import hashlib
import json
import os
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
B68 = ROOT.parent / 'scheme_A_M4_t1_component_wiring_20261024_68'
B67 = ROOT.parent / 'scheme_A_M4_fixture_gap_20261024_67'
B47 = ROOT.parent / 'scheme_A_formal_execute_profile_20261020_47'
OUT = ROOT / 'evidence/stale_event_probe'
SOURCE = ROOT / 'implementation/stale_event_probe'
BUILD = ROOT / 'build/stale_event_probe'
SETUP = 'source /opt/ros/jazzy/setup.bash; source /home/trevor/USV/usv_mpc_ws/install/setup.bash; exec "$@"'


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def command(label, argv, env=None, budget=180):
    create(OUT / (label + '_argv.json'), argv)
    with (OUT / (label + '.stdout')).open('xb') as out, (OUT / (label + '.stderr')).open('xb') as err:
        result = subprocess.run(['/bin/bash', '-c', 'set -e; ' + SETUP, 'bash', *argv],
                                stdout=out, stderr=err, timeout=budget, env=env)
    return result.returncode


OUT.mkdir()
(SOURCE / 'tests').mkdir(parents=True)
shutil.copy2(B68 / 'implementation/CMakeLists.txt', SOURCE / 'CMakeLists.txt')
test = B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'
text = test.read_text()
needle = 'seed_echo(r,j);r.candidate(c);flush_pad(r);'
assert text.count(needle) == 1
replacement = ('seed_echo(r,j);'
               'if(!(j.job_id==2 && j.task_generation>0))r.candidate(c);'
               'flush_pad(r);')
changed = SOURCE / 'tests/test_current_candidate_reference_clock.cpp'
changed.write_text(text.replace(needle, replacement, 1))
bundle = json.loads((B68 / 'evidence/init_inputs_v1.json').read_text())['current_author_bundle']['bundle_sha256']
configure = ['cmake', '-S', str(SOURCE), '-B', str(BUILD),
    '-DT1_AUTHOR_DIR=' + str(B67 / 'implementation/current_author'),
    '-DP1_FROZEN_CONTRACT=' + str(B47 / 'freeze/p1_execution_contract_v1.json'),
    '-DP1_OWNED_SOURCE_BUNDLE_SHA256=' + bundle,
    '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_CXX_FLAGS_DEBUG=-O0 -g0',
    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
assert command('configure', configure) == 0
assert command('build', ['cmake', '--build', str(BUILD), '-j2']) == 0
env = dict(os.environ)
env.update(ROS_DOMAIN_ID='121', ROS_LOCALHOST_ONLY='1',
           ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST', RMW_IMPLEMENTATION='rmw_fastrtps_cpp',
           ROS_LOG_DIR=str(OUT / 'ros_logs'), P1_T1_TEST_OUTPUT=str(OUT / 'cases'))
argv = ['timeout', '--signal=TERM', '--kill-after=2s', '20s',
        str(BUILD / 'test_current_candidate_reference_clock'),
        '--gtest_filter=T1Wiring.ReferenceReplaceDuringSolve',
        '--gtest_output=json:' + str(OUT / 'gtest.json')]
rc = command('run', argv, env, 25)
doc = json.loads((OUT / 'gtest.json').read_text())
assert rc == 0 and doc['tests'] == 1 and doc['failures'] == 0
source_file = OUT / 'cases/ReferenceReplaceDuringSolve/source.jsonl'
rows = [json.loads(line) for line in source_file.read_text().splitlines()]
registrations = [row for row in rows if row.get('type') == 'candidate_registration']
ids = [row['job']['job_id'] for row in registrations]
assert ids == [1], ids
create(OUT / 'counterexample_v1.json', {
    'schema': 'T1-stale-registration-real-CXX-counterexample-v69',
    'original_test': {'path': str(test), **pin(test)},
    'changed_test': {'path': str(changed), **pin(changed)},
    'change': 'Skip only the helper candidate() invocation for new-version Job2; retain every original test assertion',
    'source_under_test': {'path': str(B67 / 'implementation/current_author/observer/src/shadow/regulator_owned_execute.cpp'),
        **pin(B67 / 'implementation/current_author/observer/src/shadow/regulator_owned_execute.cpp')},
    'binary': pin(BUILD / 'test_current_candidate_reference_clock'),
    'process_returncode': rc, 'gtest_tests': 1, 'gtest_failures': 0,
    'actual_registered_Job_IDs': ids,
    'new_Job2_candidate_call_was_skipped': True,
    'original_assertions_still_passed': True,
    'counterexample_confirmed': True,
    'scope': 'Test-harness fault injection; original Regulator and batch68 are unchanged',
    'component_ROS_context_initialized': True,
    'test_publisher': '/p1_test/shadow_decision',
    'ROS_DOMAIN_ID': 121, 'ROS_LOCALHOST_ONLY': 1,
    'actuator_DataWriter_created': False, 'owned_runs': 0})
print(json.dumps({'counterexample_confirmed': True, 'gtest_passed': True,
                  'actual_registration_jobs': ids, 'missing_new_job': 2,
                  'owned_runs': 0}))
