#!/usr/bin/env python3
"""Create-only C3.9 default build and all registered native suites; no install/codegen."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

D = Path(__file__).resolve().parent
N = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_C3_9_20261014_v16'
sys.path.insert(0, str(N))
from build_c33_v9 import SETUP

RUNTIME = 'p1_regulator_shadow_observer_owned_v2'
TESTS = (
    'test_shadow_entry', 'test_enqueue_branch', 'test_d0_observation',
    'test_atomic_observation', 'test_legacy_ready', 'test_c33_input_matrix',
    'test_c34_lease_matrix', 'test_owned_peer_c36_v1',
    'test_c36_runtime_adapter', 'test_c36_completion',
    'test_owned_worker_peer_c37_v1', 'test_c37_worker_callbacks',
    'test_witness_v2_c37', 'test_c36_applied_boundaries',
    'test_c38_diagnostic_gate',
)
AUXILIARIES = ('c37_worker_child', 'witness_v2_c37_producer', 'c34_lease_wire_component')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    with Path(path).open('x') as output:
        json.dump(value, output, indent=2, sort_keys=True, allow_nan=False)
        output.write('\n')


def verify(pin):
    descriptor = Path(pin['path'])
    assert descriptor.is_absolute() and descriptor.is_relative_to(N)
    assert sha(descriptor) == pin['sha256'], 'source descriptor SHA changed'
    bundle = json.loads(descriptor.read_text())
    assert bundle['role'] == 'observer'
    assert len(bundle['files']) == pin['files']
    observed = {}
    for relative, item in bundle['files'].items():
        source = Path(item['path'])
        assert source.is_absolute() and source.is_relative_to(N), relative
        assert source == N / relative, relative
        assert source.is_file() and not source.is_symlink(), relative
        assert source.stat().st_size == item['bytes'], relative
        observed[relative] = sha(source)
        assert observed[relative] == item['sha256'], relative
    return bundle, observed


def registered_tests():
    text = (N / 'observer/CMakeLists.txt').read_text()
    explicit = set(re.findall(r'ament_add_gtest\(\s*(test_[A-Za-z0-9_]+)\s', text))
    for names in re.findall(r'foreach\(\s*name\s+([^)]*)\)', text):
        explicit.update('test_' + name for name in names.split())
    assert explicit == set(TESTS), ('registered GTest target population changed', sorted(explicit))
    return sorted(explicit)


def command(output, name, arguments, budget_s, domain, extra=''):
    script = output / (name + '.sh')
    with script.open('x') as stream:
        stream.write('set -e\n' + SETUP + 'export ROS_DOMAIN_ID=' + str(domain) + '\n' + extra
                     + 'exec timeout --signal=TERM --kill-after=5s ' + str(budget_s) + 's '
                     + shlex.join(arguments) + '\n')
    with (output / (name + '.log')).open('xb') as log:
        try:
            return subprocess.run(['bash', str(script)], stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  timeout=budget_s + 10).returncode
        except subprocess.TimeoutExpired:
            # The generated timeout command owns and signals the build/test
            # group. Preserve the outer timeout as a separate failed outcome.
            return 124


def binary_pin(path):
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def compiler_dependencies(build_dir, output):
    dependencies = {}
    depfiles = {}
    for depfile in sorted(build_dir.rglob('*.o.d')):
        depfiles[str(depfile)] = sha(depfile)
        body = depfile.read_text().replace('\\\n', ' ').split(':', 1)[1]
        for token in shlex.split(body):
            path = Path(token)
            if not path.is_absolute():
                path = build_dir / path
            if path.is_file():
                path = path.resolve()
                dependencies[str(path)] = sha(path)
    compiler = Path('/usr/bin/c++').resolve()
    commands = build_dir / 'compile_commands.json'
    proof = {
        'schema': 'p1-C3.9-compiler-dependencies/v1',
        'compiler': str(compiler), 'compiler_sha256': sha(compiler),
        'compile_commands_sha256': sha(commands),
        'dependency_count': len(dependencies), 'files': dependencies,
        'depfile_count': len(depfiles), 'depfile_sha256': depfiles,
        'scope': 'actual compiler-reported file contents; no full-machine or WCET qualification',
    }
    write(output / 'compiler_dependency_pins.json', proof)
    with (output / 'compile_commands.json').open('xb') as destination:
        destination.write(commands.read_bytes())
    return len(dependencies)


def build(domain):
    output = D / 'build/observer_attempt01'
    output.mkdir(parents=True, exist_ok=False)
    build_dir = N / 'observer/build01'
    started = time.monotonic()
    result = {
        'schema': 'p1-C3.9-observer-default-build/v1', 'role': 'observer',
        'author_directory': str(N), 'build_directory': str(build_dir),
        'passed': False, 'stage_qualified': False, 'execute_qualified': False,
        'research_conclusion': False, 'node_launch_performed': False,
        'install_performed': False, 'codegen_performed': False,
        'domain': domain, 'compile_concurrency': 2,
        'configure_budget_s': 90, 'gtest_budget_s': 90,
        'default_build_budget_s': 1200, 'default_build_has_target_override': False,
        'default_build_target_population': [RUNTIME, *TESTS, *AUXILIARIES],
    }
    pin = None
    before = None
    try:
        assert not build_dir.exists(), 'fresh build directory required'
        registry_path = N / 'source_bundles_current.json'
        registry_sha = sha(registry_path)
        pin = json.loads(registry_path.read_text())['observer']
        bundle, before = verify(pin)
        result['source_bundle'] = pin
        result['source_bundles_registry_sha256'] = registry_sha
        result['source_content_sha256_before'] = before
        result['registered_gtest_targets'] = registered_tests()
        snapshot = output / 'source_snapshot'
        snapshot.mkdir()
        for relative, item in bundle['files'].items():
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(Path(item['path']).read_bytes())
            assert sha(destination) == item['sha256'], relative
        write(output / 'source_snapshot_manifest.json', bundle)
        for path in (Path(__file__), N / 'build_c33_v9.py', registry_path, Path(pin['path'])):
            with (output / (path.name + '.snapshot')).open('xb') as stream:
                stream.write(path.read_bytes())
        result['recipe_sha256'] = sha(Path(__file__))
        result['setup_helper_sha256'] = sha(N / 'build_c33_v9.py')
        configure = ['cmake', '-S', str(N / 'observer'), '-B', str(build_dir),
                     '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                     '-DPython3_EXECUTABLE=/usr/bin/python3',
                     '-DP1_OWNED_SOURCE_BUNDLE_SHA256=' + pin['sha256']]
        result['configure_rc'] = command(output, 'configure', configure, 90, domain)
        assert result['configure_rc'] == 0, 'configure failed'
        result['gtest_build_rc'] = command(output, 'gtest_libs',
            ['cmake', '--build', str(build_dir), '--target', 'gtest', 'gtest_main', '-j2'], 90, domain)
        assert result['gtest_build_rc'] == 0, 'GTest libraries failed'
        # This command intentionally exercises the actual CMake default target.
        default_command = ['cmake', '--build', str(build_dir), '-j2']
        result['default_build_command'] = default_command
        result['default_build_rc'] = command(output, 'default_build', default_command, 1200, domain)
        assert result['default_build_rc'] == 0, 'default all-target build failed'
        result['binary'] = str(build_dir / RUNTIME)
        result['binary_sha256'] = sha(build_dir / RUNTIME)
        result['native_binaries'] = {name: binary_pin(build_dir / name) for name in TESTS}
        result['auxiliary_binaries'] = {name: binary_pin(build_dir / name) for name in AUXILIARIES}
        result.update(build_rc=0, runtime_build_rc=0, native_build_rc=0)
        assert sha(registry_path) == registry_sha, 'source registry changed during build'
        result['passed'] = True
    except BaseException as error:
        result['error'] = repr(error)
    finally:
        if pin is not None:
            try:
                _, after = verify(pin)
                result['source_content_sha256_after'] = after
                result['source_unchanged_before_after'] = before == after
                if before != after:
                    result['passed'] = False
                    result['source_verification_error'] = 'source population/content changed'
            except BaseException as error:
                result['passed'] = False
                result['source_verification_error'] = repr(error)
        if (build_dir / 'compile_commands.json').is_file():
            try:
                result['compiler_dependency_count'] = compiler_dependencies(build_dir, output)
            except BaseException as error:
                result['passed'] = False
                result['compiler_dependency_error'] = repr(error)
        # A failed default attempt retains whichever executables really exist;
        # their presence is never substituted for a successful default command.
        result['produced_target_pins'] = {
            name: binary_pin(build_dir / name) for name in (RUNTIME, *TESTS, *AUXILIARIES)
            if (build_dir / name).is_file()
        }
        result['elapsed_seconds'] = time.monotonic() - started
        write(output / 'result.json', result)
    print(json.dumps({'schema': result['schema'], 'passed': result['passed'],
                      'default_build_rc': result.get('default_build_rc'),
                      'native_targets': len(result.get('native_binaries', {})),
                      'error': result.get('error'), 'result': str(output / 'result.json')}, sort_keys=True))
    return result['passed']


def tests(domain):
    output = D / 'component/native_attempt01'
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {'schema': 'p1-C3.9-all-native/v1', 'passed': False, 'tests': {},
              'domain': domain, 'test_budget_s': 90, 'requested_filter': '*',
              'stage_qualified': False, 'execute_qualified': False,
              'research_conclusion': False, 'physical_publish_qualified': False}
    try:
        build_path = D / 'build/observer_attempt01/result.json'
        manifest_sha = sha(build_path)
        manifest = json.loads(build_path.read_text())
        assert manifest['passed'] and manifest['default_build_rc'] == 0
        assert manifest['default_build_has_target_override'] is False
        assert set(manifest['native_binaries']) == set(TESTS)
        assert registered_tests() == sorted(TESTS)
        _, before = verify(manifest['source_bundle'])
        result['build_result_sha256'] = manifest_sha
        result['source_content_sha256_before'] = before
        child = manifest['auxiliary_binaries']['c37_worker_child']
        assert sha(child['path']) == child['sha256']
        for name in TESTS:
            pin = manifest['native_binaries'][name]
            assert sha(pin['path']) == pin['sha256'], name
            folder = output / name
            folder.mkdir()
            branch = folder / 'branch'
            branch.mkdir()
            extra = ('unset GTEST_FILTER GTEST_TOTAL_SHARDS GTEST_SHARD_INDEX GTEST_SHARD_STATUS_FILE\n'
                     + 'export P1_C34_LEASE_NATIVE_DIR=' + shlex.quote(str(branch)) + '\n'
                     + 'export P1_BRANCH_TEST_OUTPUT=' + shlex.quote(str(branch)) + '\n'
                     + 'export C37_WORKER_CHILD_BIN=' + shlex.quote(child['path']) + '\n')
            xml_path = folder / 'gtest.xml'
            rc = command(folder, 'run', [pin['path'], '--gtest_filter=*',
                         '--gtest_output=xml:' + str(xml_path)], 90, domain, extra)
            row = {'returncode': rc, 'binary_sha256': pin['sha256'],
                   'count': 0, 'failed': 1, 'errors': 0, 'disabled': 0,
                   'test_output_directory': str(branch)}
            try:
                if xml_path.is_file():
                    xml = ET.parse(xml_path).getroot()
                    row.update(count=int(xml.attrib['tests']), failed=int(xml.attrib['failures']),
                               errors=int(xml.attrib.get('errors', 0)),
                               disabled=int(xml.attrib.get('disabled', 0)), xml_sha256=sha(xml_path))
            except BaseException as error:
                row['xml_error'] = repr(error)
            row['binary_unchanged_after'] = sha(pin['path']) == pin['sha256']
            row['passed'] = (rc == 0 and row['count'] > 0
                             and row['failed'] == row['errors'] == row['disabled'] == 0
                             and row['binary_unchanged_after'])
            result['tests'][name] = row
        _, after = verify(manifest['source_bundle'])
        result['source_content_sha256_after'] = after
        result['source_unchanged_before_after'] = before == after
        result['build_result_unchanged_after'] = sha(build_path) == manifest_sha
        result['child_binary_unchanged_after'] = sha(child['path']) == child['sha256']
        result['count'] = sum(row['count'] for row in result['tests'].values())
        result['suite_count'] = len(result['tests'])
        result['passed'] = (set(result['tests']) == set(TESTS)
                            and all(row['passed'] for row in result['tests'].values())
                            and result['source_unchanged_before_after']
                            and result['build_result_unchanged_after']
                            and result['child_binary_unchanged_after'])
    except BaseException as error:
        result['error'] = repr(error)
    result['elapsed_seconds'] = time.monotonic() - started
    write(output / 'result.json', result)
    print(json.dumps({'schema': result['schema'], 'passed': result['passed'],
                      'count': result.get('count', 0), 'suite_count': result.get('suite_count', 0),
                      'error': result.get('error'), 'result': str(output / 'result.json')}, sort_keys=True))
    return result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'tests'])
    parser.add_argument('--domain', type=int, default=151)
    arguments = parser.parse_args()
    assert 0 <= arguments.domain <= 232
    raise SystemExit(0 if (build(arguments.domain) if arguments.mode == 'build'
                          else tests(arguments.domain)) else 1)
