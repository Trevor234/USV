#!/usr/bin/env python3
"""Create-only controlled-role source freeze, default build and finite checks.

No source edits, install, code generation, ROS node launch or registry mutation.
Every attempt owns its bundle, source snapshots, build tree and failure evidence.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
N = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18'
C = N / 'controlled_phase'
BASELINE = Path('/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01')
F5 = BASELINE / 'source_snapshot/usv_mpc_ws/src/usv_mpc_cpp'
sys.path.insert(0, str(N))
from build_c33_v9 import SETUP


def require(condition, why):
    if not condition:
        raise ValueError(why)


def pin(path):
    logical = Path(path)
    resolved = logical.resolve(strict=True)
    require(resolved.is_absolute(), 'absolute_input_required')
    with resolved.open('rb') as handle:
        before = os.fstat(handle.fileno())
        require(stat.S_ISREG(before.st_mode), 'regular_input_required:' + str(path))
        h = hashlib.sha256()
        size = 0
        for raw in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(raw)
            size += len(raw)
        after = os.fstat(handle.fileno())
    named = resolved.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after) == identity(named) and size == before.st_size,
            'input_changed_during_read:' + str(path))
    return {'path': str(logical), 'resolved_path': str(resolved), 'bytes': size, 'sha256': h.hexdigest()}


def sha(path):
    return pin(path)['sha256']


def write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with Path(path).open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    require(Path(path).read_bytes() == raw, 'create_only_evidence_readback')


def snapshot(source, destination):
    require(not destination.exists(), 'fresh_snapshot_required')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as output:
        output.write(Path(source).read_bytes())
    require(sha(source) == sha(destination), 'snapshot_byte_identity')


def unchanged(files):
    return all(sha(row['path']) == row['sha256'] and Path(row['path']).stat().st_size == row['bytes']
               for row in files.values())


def source_files(role):
    selected = []
    for root in (C / role, C / ('common' if role in ('observer', 'worker') else 'owner_common')):
        require(root.is_dir(), 'role_source_not_ready:' + str(root))
        for path in sorted(root.rglob('*')):
            require(not path.is_symlink(), 'local_source_link_not_allowed')
            if path.is_file() and not any(part.startswith('build') or part == '__pycache__'
                                         for part in path.relative_to(root).parts):
                selected.append(path)
    if role in ('observer', 'worker'):
        selected += [p for p in sorted(C.glob('phase_protocol*')) if p.suffix in ('.hpp', '.cpp')]
        selected += [p for p in sorted(C.glob('controlled_contract_test*')) if p.suffix in ('.hpp', '.cpp')]
    selected.append(C / 'controlled_contract_v1.json')
    require(all(p.is_file() for p in selected), 'complete_local_source_required')
    return {str(path.relative_to(C)): pin(path) for path in sorted(set(selected))}


def parent_role(role):
    source = json.loads((N / 'source_bundles_current.json').read_text())[role]
    rows = json.loads((N / 'build_manifest_current.json').read_text())
    build = next(row for row in rows if row['role'] == role)
    require(build['passed'] is True and build['source_bundle'] == source, 'parent_role_registry')
    require(sha(source['path']) == source['sha256'], 'parent_bundle_identity')
    bundle = json.loads(Path(source['path']).read_text())
    require(len(bundle['files']) == source['files'] and unchanged(bundle['files']), 'parent_source_preserved')
    require(sha(build['binary']) == build['binary_sha256'], 'parent_binary_preserved')
    return source, build, bundle['files']


def frozen_f5_inputs():
    require(sha(BASELINE / 'baseline_manifest.json') == '77737a5924f1bcd97996dee3c08e204a4a4c8fbf2f3716ff65d41fbc4bad6762', 'frozen_F5_manifest')
    require(sha(BASELINE / 'source_hashes.json') == 'f7709365308f856669caf7c1d7e9971857214d9ec6d5d5f8d7bf24f6bef4d9e8', 'frozen_F5_source_inventory')
    declared = json.loads((BASELINE / 'source_hashes.json').read_text())
    rows = [row for row in declared if row['path'].startswith('usv_mpc_ws/src/usv_mpc_cpp/')]
    require(len(rows) == 45, 'frozen_F5_complete_source_scope')
    values = {}
    for row in rows:
        path = BASELINE / 'source_snapshot' / row['path']
        actual = pin(path)
        require(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'], 'frozen_F5_source_changed:' + str(path))
        values[str(path)] = actual
    require(set(str(p) for p in F5.rglob('*') if p.is_file()) == set(values), 'frozen_F5_source_population')
    return values


def command(out, name, argv, budget, files, cwd=None):
    require(unchanged(files), 'frozen_source_changed_before:' + name)
    script = out / (name + '.sh')
    with script.open('x') as handle:
        handle.write('set -e\n' + SETUP + 'exec timeout --signal=TERM --kill-after=5s '
                     + str(budget) + 's ' + shlex.join(argv) + '\n')
    with (out / (name + '.log')).open('xb') as log:
        rc = subprocess.run(['bash', str(script)], cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, timeout=budget + 10).returncode
    require(unchanged(files), 'frozen_source_changed_after:' + name)
    return rc


def dependencies(build, out):
    manifests = sorted(build.rglob('*.o.d'))
    require(manifests, 'actual_compiler_dependency_files_required')
    values = {}
    depfiles = {}
    for source in manifests:
        depfiles[str(source)] = pin(source)
        tokens = shlex.split(source.read_text().replace('\\\n', ' ').split(':', 1)[1])
        for token in tokens:
            path = Path(token)
            if not path.is_absolute():
                path = build / path
            require(path.is_file(), 'actual_compiler_dependency_missing:' + str(path))
            resolved = path.resolve(strict=True)
            if str(resolved) not in values:
                values[str(resolved)] = pin(resolved)
    require(values, 'nonempty_actual_compiler_dependencies')
    record = {'schema': 'ordered-controlled-actual-compiler-inputs/v1', 'files': values,
              'dependency_count': len(values), 'compiler_dependency_files': depfiles,
              'compile_commands': pin(build / 'compile_commands.json'), 'compiler': pin('/usr/bin/c++'),
              'collection_after_build': True, 'prebuild_source_bundle_frozen': True,
              'compiler_internal_builtin_state_replayed': False}
    write(out / 'compiler_dependency_pins.json', record)
    snapshot(build / 'compile_commands.json', out / 'compile_commands.json')
    return len(values)


def runtime_libraries(binary, out, files):
    rc = command(out, 'loader_dependencies', ['ldd', str(binary)], 30, files)
    require(rc == 0, 'runtime_loader_dependencies_failed')
    text = (out / 'loader_dependencies.log').read_text()
    require('not found' not in text, 'runtime_library_unresolved')
    selected = {}
    for line in text.splitlines():
        match = re.search(r'(?:=>\s*)?(/[^\s]+)\s+\(', line)
        if match:
            row = pin(match.group(1))
            selected[row['resolved_path']] = row
    require(selected, 'actual_loader_library_population')
    write(out / 'runtime_library_pins.json', {'schema': 'ordered-controlled-loader-libraries/v1',
          'files': selected, 'count': len(selected), 'no_ROS_node_started': True,
          'scope': 'ldd resolves the freshly built ELF; actual future process mapped-library validation remains separate'})
    return len(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=['observer', 'worker', 'publisher', 'fixture'], required=True)
    parser.add_argument('--attempt', type=int, default=1)
    args = parser.parse_args()
    require(1 <= args.attempt <= 99, 'finite_attempt_domain')
    role = args.role
    out = D / 'build' / ('controlled_' + role + '_attempt' + str(args.attempt).zfill(2))
    out.mkdir(parents=True, exist_ok=False)
    build = out / 'cmake_build'
    require(not build.exists(), 'fresh_build_directory_required')
    started = time.monotonic()
    result = {'schema': 'ordered-controlled-role-build/v1', 'role': role, 'author_directory': str(C),
              'output_directory': str(out), 'build_directory': str(build), 'passed': False,
              'node_launch_performed': False, 'install_performed': False, 'codegen_performed': False,
              'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False,
              'recipe_sha256': sha(__file__), 'setup_helper_sha256': sha(N / 'build_c33_v9.py')}
    files = {}
    parents = {}
    try:
        parent, previous, parents = parent_role(role)
        files = source_files(role)
        descriptor = {'schema': 'ordered-controlled-role-source/v1', 'role': role, 'files': files,
                      'author_directory': str(C), 'parent_source_bundle': parent,
                      'controlled_contract': pin(C / 'controlled_contract_v1.json'),
                      'baseline_is_new_controlled_scope': True, 'frozen_before_configure': True,
                      'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}
        write(out / 'source_bundle.json', descriptor)
        bundle = {'path': str(out / 'source_bundle.json'), 'sha256': sha(out / 'source_bundle.json'), 'files': len(files)}
        result['source_bundle'] = bundle
        result['parent_source_bundle'] = parent
        result['parent_binary_sha256'] = previous['binary_sha256']
        result['source_content_sha256_before'] = {key: row['sha256'] for key, row in files.items()}
        for key, row in files.items():
            snapshot(row['path'], out / 'source_snapshot' / key)
        for source in (Path(__file__), N / 'build_c33_v9.py', N / 'source_bundles_current.json', N / 'build_manifest_current.json'):
            snapshot(source, out / (source.name + '.snapshot'))
        external = frozen_f5_inputs() if role == 'publisher' else {}
        write(out / 'frozen_external_before.json', {'files': external, 'file_count': len(external)})
        cmake_text = (C / role / 'CMakeLists.txt').read_text()
        declared = re.findall(r'\b(add_executable|ament_add_gtest)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)', cmake_text)
        runtimes = [name for kind, name in declared if kind == 'add_executable' and name.startswith('p1_')]
        tests = [name for kind, name in declared if name.startswith('test_')]
        require(len(runtimes) == 1 and tests and all(name.startswith('test_controlled_') for name in tests),
                'one_runtime_and_explicit_controlled_native_targets_required')
        runtime = runtimes[0]
        result['runtime_target'] = runtime
        result['declared_native_targets'] = tests
        configure = ['cmake', '-S', str(C / role), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
                     '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DPython3_EXECUTABLE=/usr/bin/python3']
        if role == 'publisher':
            configure += ['-DP1_D1_SOURCE_BUNDLE_SHA256=' + bundle['sha256'], '-DP1_F5_SOURCE_PACKAGE=' + str(F5),
                          '-DP1_ACADOS_DIR=/home/trevor/acados',
                          '-DP1_CASADI_PACKAGE_DIR=/home/trevor/.local/lib/python3.12/site-packages/casadi', '-DP1_CASADI_OLD_ABI=ON']
            macro = 'P1_D1_SOURCE_BUNDLE_SHA256'
        else:
            configure += ['-DP1_OWNED_SOURCE_BUNDLE_SHA256=' + bundle['sha256']]
            macro = 'P1_OWNED_SOURCE_BUNDLE_SHA256'
        result['configure_rc'] = command(out, 'configure', configure, 90, files)
        require(result['configure_rc'] == 0, 'configure_failed')
        result['default_build_rc'] = command(out, 'default_build', ['cmake', '--build', str(build), '-j2'], 600, files)
        require(result['default_build_rc'] == 0, 'default_build_failed')
        result['produced_target_pins'] = {name: pin(build / name) for name in [runtime, *tests]}
        binary = build / runtime
        commands = json.loads((build / 'compile_commands.json').read_text())
        runtime_commands = [row for row in commands if 'CMakeFiles/' + runtime + '.dir/' in row['command']]
        require(runtime_commands and all(macro in row['command'] and bundle['sha256'] in row['command'] for row in runtime_commands),
                'actual_runtime_compile_source_bundle_pin')
        require(bundle['sha256'].encode() in binary.read_bytes(), 'runtime_ELF_contains_exact_bundle_identity')
        result['compiled_source_bundle_pin_verified'] = True
        rc = command(out, 'ctest_plan', ['ctest', '--test-dir', str(build), '--show-only=json-v1'], 30, files)
        require(rc == 0, 'ctest_plan_failed')
        plan = json.loads((out / 'ctest_plan.log').read_text())
        registered = [row['name'] for row in plan['tests']]
        require(set(registered) <= set(tests), 'only_declared_controlled_finite_tests_registered')
        result['ctest_registered_tests'] = registered
        result['ctest_rc'] = None
        if registered:
            result['ctest_rc'] = command(out, 'ctest', ['ctest', '--test-dir', str(build), '--output-on-failure',
                        '-j1', '--timeout', '45', '--output-junit', str(out / 'ctest.junit.xml')], 90, files)
            require(result['ctest_rc'] == 0, 'ctest_failed')
        plain = {}
        for name in tests:
            if name not in registered:
                rc = command(out, 'native_' + name, [str(build / name)], 45, files)
                require(rc == 0, 'finite_native_failed:' + name)
                log = (out / ('native_' + name + '.log')).read_text()
                checks = re.search(r'(?:checks|assertions)\s*[=:]\s*(\d+)\s+passed', log)
                plain[name] = {'returncode': rc, 'reported_checks': int(checks.group(1)) if checks else None,
                               'log_sha256': sha(out / ('native_' + name + '.log'))}
        xml_results = []
        for path in sorted((build / 'test_results').rglob('*.xml')):
            root = ET.parse(path).getroot()
            if 'tests' in root.attrib:
                row = {key: int(root.attrib.get(key, 0)) for key in ('tests', 'failures', 'disabled', 'errors')}
                require(row['tests'] > 0 and all(row[key] == 0 for key in ('failures', 'disabled', 'errors')), 'native_GTest_XML_failed')
                xml_results.append({'path': str(path), 'sha256': sha(path), **row})
        require(len(plain) + len(registered) == len(tests), 'every_declared_native_target_exercised')
        require(not registered or xml_results, 'registered_GTest_case_evidence_required')
        result['finite_native'] = {'plain_targets': plain, 'GTest_XML': xml_results,
                                  'GTest_cases': sum(x['tests'] for x in xml_results),
                                  'plain_checks': sum(x['reported_checks'] or 0 for x in plain.values()),
                                  'all_declared_native_targets_exercised': True}
        result['actual_compiler_dependencies'] = dependencies(build, out)
        result['actual_loader_libraries'] = runtime_libraries(binary, out, files)
        require(unchanged(external), 'frozen_F5_changed_during_build')
        require(unchanged(parents) and sha(previous['binary']) == previous['binary_sha256'], 'parent_role_changed_during_build')
        require(sha(out / 'source_bundle.json') == bundle['sha256'], 'frozen_role_bundle_changed')
        result.update(binary=str(binary), binary_sha256=sha(binary), native_binaries={name: pin(build / name) for name in tests},
                      build_rc=0, runtime_build_rc=0, native_build_rc=0, parent_roles_verified_unchanged=True, passed=True)
    except BaseException as error:
        result['error'] = repr(error)
    result['source_content_unchanged'] = unchanged(files) if files else False
    result['parent_source_content_unchanged'] = unchanged(parents) if parents else False
    result['source_content_sha256_after'] = {key: sha(row['path']) for key, row in files.items()}
    result['passed'] = bool(result['passed'] and result['source_content_unchanged'] and result['parent_source_content_unchanged'])
    result['elapsed_seconds'] = time.monotonic() - started
    write(out / 'result.json', result)
    print(json.dumps({key: result.get(key) for key in ('role', 'passed', 'error', 'runtime_target', 'binary_sha256',
                     'actual_compiler_dependencies', 'actual_loader_libraries', 'elapsed_seconds')}, sort_keys=True))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
