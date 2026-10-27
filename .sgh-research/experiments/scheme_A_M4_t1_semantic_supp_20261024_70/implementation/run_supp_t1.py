#!/usr/bin/env python3
"""Create-only bounded S1 runner (batch 70): 25 reviewed + 7 supplementary tests,
strict shared failure/identity gates, unchanged 67th-batch Regulator source."""
from pathlib import Path
import ast
import datetime
import hashlib
import json
import os
import subprocess
import traceback
from runner_verdict_v2 import baseline_verdict, mutation_verdict, complete_verdict

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
B67 = BASE / 'scheme_A_M4_fixture_gap_20261024_67'
B68 = BASE / 'scheme_A_M4_t1_component_wiring_20261024_68'
AUTHOR = B67 / 'implementation/current_author'
REGULATOR = AUTHOR / 'observer/src/shadow/regulator_owned_execute.cpp'
PROJECT = ROOT / 'implementation/supp_harness'
SETUP = 'set -e; source /opt/ros/jazzy/setup.bash; source /home/trevor/USV/usv_mpc_ws/install/setup.bash; exec "$@"'

# The seven S1 supplementary cases (batch 70), appended to the 25 reviewed ones.
SUPP_TESTS = [
    'T1Wiring.CandidateSuccessFalseAloneRejected',
    'T1Wiring.CandidateSolverNotInvokedAloneRejected',
    'T1Wiring.NativePredictionShapeFixedByConstruction',
    'T1Wiring.RealPrepareLoopSubmitsJob',
    'T1Wiring.RealSubmitBlockedByShutdownBeforeSubmit',
    'T1Wiring.RealSubmitBlockedByVersionChangeBeforeSubmit',
    'T1Wiring.ReferenceOrdinaryNewOdomActivation',
]


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def allocate(parent, prefix):
    parent.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        path = parent / f'{prefix}{index:02d}'
        try:
            path.mkdir()
            return path
        except FileExistsError:
            index += 1


def specification():
    path = ROOT / 'evidence/spec68/scripts/run_t1.py'
    tree = ast.parse(path.read_text())
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('ATOM_MAP', 'COMPANIONS', 'MUTATIONS'):
                    values[target.id] = ast.literal_eval(node.value)
    assert set(values) == {'ATOM_MAP', 'COMPANIONS', 'MUTATIONS'}
    return values


def main():
    spec = specification()
    expected_tests = sorted({name for names in spec['ATOM_MAP'].values() for name in names}
                            | set(spec['COMPANIONS']) | set(SUPP_TESTS))
    assert len(expected_tests) == 32 and len(spec['MUTATIONS']) == 3
    attempt = allocate(ROOT / 'evidence/supp_t1', 'attempt')
    build_root = allocate(ROOT / 'build/supp_t1', 'attempt')
    paths = [p for p in AUTHOR.rglob('*') if p.is_file()]
    paths += [PROJECT / 'CMakeLists.txt', PROJECT / 'tests/test_current_candidate_reference_clock.cpp',
              PROJECT / 's1_helpers_insert.cpp', PROJECT / 's1_tests_append.cpp',
              Path(__file__).resolve(), ROOT / 'implementation/runner_verdict_v2.py']
    before = {str(p): pin(p) for p in paths}
    report = {'schema': 'T1-S1-create-only-runner-v70',
        'started_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'attempt': str(attempt), 'build_root': str(build_root), 'expected_tests': expected_tests,
        'reviewed_tests': sorted({name for names in spec['ATOM_MAP'].values() for name in names}
                                 | set(spec['COMPANIONS'])), 'supp_tests': sorted(SUPP_TESTS),
        'source_pins_before': before, 'nominal': None, 'mutations': [], 'complete': False,
        'component_ROS_context_initialized': True, 'owned_runs': 0,
        'test_job_publisher_created': True,
        'control_DataWriter_created': False, 'ROS_DOMAIN_ID': 121, 'ROS_LOCALHOST_ONLY': 1,
        'automatic_retries': 0, 'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False}
    env = dict(os.environ)
    env.update(ROS_DOMAIN_ID='121', ROS_LOCALHOST_ONLY='1', ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
               RMW_IMPLEMENTATION='rmw_fastrtps_cpp', PYTHONDONTWRITEBYTECODE='1')
    bundle = json.loads((B68 / 'evidence/init_inputs_v1.json').read_text())['current_author_bundle']['bundle_sha256']
    ordinal = 0

    def command(folder, label, argv, seconds):
        nonlocal ordinal
        folder.mkdir(parents=True, exist_ok=True)
        ordinal += 1
        create(folder / f'{ordinal:02d}_{label}_argv.json', argv)
        specific_env = dict(env)
        specific_env['ROS_LOG_DIR'] = str(folder / 'ros_logs')
        specific_env['P1_T1_TEST_OUTPUT'] = str(folder / 'cases')
        with (folder / f'{ordinal:02d}_{label}.stdout').open('xb') as out, (folder / f'{ordinal:02d}_{label}.stderr').open('xb') as err:
            result = subprocess.run(['/bin/bash', '-c', SETUP, 'bash', *argv], env=specific_env,
                                    stdout=out, stderr=err, timeout=seconds)
        return result.returncode

    def build(folder, evidence, mutated=None):
        folder.mkdir()
        argv = ['cmake', '-S', str(PROJECT), '-B', str(folder),
            '-DT1_AUTHOR_DIR=' + str(AUTHOR),
            '-DP1_FROZEN_CONTRACT=' + str(BASE / 'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'),
            '-DP1_OWNED_SOURCE_BUNDLE_SHA256=' + bundle,
            '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_CXX_FLAGS_DEBUG=-O0 -g0', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
        if mutated:
            argv += ['-DT1_MUTATED_SOURCE=' + str(mutated)]
        assert command(evidence, 'configure', argv, 60) == 0, 'configure failed'
        cache = (folder / 'CMakeCache.txt').read_text()
        assert 'CMAKE_HOME_DIRECTORY:INTERNAL=' + str(PROJECT) + '\n' in cache
        rc = command(evidence, 'build', ['cmake', '--build', str(folder), '-j2'], 180)
        assert rc == 0, 'build failed'
        return folder / 'test_current_candidate_reference_clock'

    def run(binary, folder):
        folder.mkdir()
        doc_path = folder / 'gtest.json'
        rc = command(folder, 'gtest', ['timeout', '--signal=TERM', '--kill-after=2s', '40s',
            str(binary), '--gtest_output=json:' + str(doc_path)], 45)
        doc = json.loads(doc_path.read_text()) if doc_path.exists() else None
        return rc, doc

    try:
        binary = build(build_root / 'baseline', attempt / 'baseline_build')
        rc, doc = run(binary, attempt / 'nominal_run01')
        rows = baseline_verdict(doc, rc, expected_tests)
        report['nominal'] = {'returncode': rc, 'doc': str(attempt / 'nominal_run01/gtest.json'),
            'test_count': len(rows), 'all_passed': True, 'rows': rows,
            'binary': {'path': str(binary), **pin(binary)}}
        for mutation in spec['MUTATIONS']:
            name = mutation['name']
            record = {'name': name, 'prepared': False, 'assertion_caught': False}
            report['mutations'].append(record)
            text = REGULATOR.read_text()
            count = text.count(mutation['find'])
            record['pattern_count'] = count
            if count != 1:
                record['error'] = 'mutation was not prepared'
                continue
            target = attempt / 'mutated_sources' / name / 'regulator_owned_execute.cpp'
            target.parent.mkdir(parents=True)
            with target.open('x') as stream:
                stream.write(text.replace(mutation['find'], mutation['replace'], 1))
            record.update(prepared=True, source={'path': str(target), **pin(target)})
            binary = build(build_root / name, attempt / (name + '_build'), target)
            rc, doc = run(binary, attempt / (name + '_run01'))
            assertions = mutation_verdict(doc, rc, expected_tests, mutation['expect_caught_by'], True, 0)
            record.update(assertion_caught=True, returncode=rc, named_assertions=assertions,
                          binary={'path': str(binary), **pin(binary)})
        after = {filename: pin(Path(filename)) for filename in before}
        report['source_pins_after'] = after
        report['identities_unchanged'] = before == after
        report['complete'] = complete_verdict(True, report['mutations'],
            [row['name'] for row in spec['MUTATIONS']], before == after)
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
    create(attempt / 'verification_v1.json', report)
    print(json.dumps({'complete': report['complete'], 'attempt': str(attempt),
                      'nominal_tests': report['nominal']['test_count'] if report['nominal'] else 0,
                      'mutations_caught': [row['name'] for row in report['mutations'] if row['assertion_caught']],
                      'error': report.get('error')}))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
