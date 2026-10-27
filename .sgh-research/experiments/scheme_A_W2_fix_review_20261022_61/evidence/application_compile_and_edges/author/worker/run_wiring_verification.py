#!/usr/bin/env python3
"""Build and run the W2 wiring suites, then mutate each guard.

Hardening required by the 60 review (§R8):
  * every run uses a private copy of the author tree and a unique build
    directory, never the shared /tmp/w2build cache;
  * the actual CMAKE source root is asserted before trusting a build;
  * mutations are applied to the private copy, never to the sealed tree;
  * the sealed tree's hashes are verified unchanged before and after.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent          # implementation/w2_author/worker
TREE = HERE.parent                              # implementation/w2_author
PKG = TREE.parents[1]
OUT = PKG / 'evidence' / 'w2_wiring'

BOUNDARY_REL = 'worker/w2_native_boundary.hpp'
BACKEND_REL = 'worker/owned_cold_backend.hpp'

MUTATIONS = {
    'drop_expiry_guard': (
        BOUNDARY_REL,
        r'    if \(guard > config_\.job_deadline_ns\) \{\n'
        r'      record_\.disposition = Disposition::kExpired;\n'
        r'      return false;\n'
        r'    \}',
        '    if (false) {\n'
        '      record_.disposition = Disposition::kExpired;\n'
        '      return false;\n'
        '    }'),
    'expiry_off_by_one': (
        BOUNDARY_REL,
        r'if \(guard > config_\.job_deadline_ns\)',
        'if (guard >= config_.job_deadline_ns)'),
    'drop_post_gate_stop_guard': (
        BOUNDARY_REL,
        r'if \(record_\.stop_at_release \|\| \(stop_requested && stop_requested\(\)\)\) \{',
        'if (false) {'),
    'bind_on_ordinal_only': (
        BOUNDARY_REL,
        r'    return gate_ != nullptr && job_id == config_\.job_id &&\n'
        r'           ordinal == config_\.ordinal;',
        '    return gate_ != nullptr && ordinal == config_.ordinal;'),
    # The whole wiring block gone. This is the mutant the previous suite missed:
    # every original test still passed with the Backend blocking removed.
    #
    # Matched by explicit anchor text, not a lazy `(?:.*\n)*?` group: the lazy
    # form backtracks catastrophically on a file this size and hangs the runner.
    'delete_backend_wiring': (
        BACKEND_REL,
        r'   if\(boundary_&&boundary_->armed\(\)&&boundary_->matches\(ordinal,id\)\)\{\n'
        r'     const bool permitted=boundary_->enter\(ordinal,id,stop_\);\n'
        r'     if\(!permitted\)\{\n'
        r'       // Snapshot AFTER[^\n]*\n'
        r'       // policy JSON[^\n]*\n'
        r'       last_\["w2_boundary"\]=w2_boundary_json\(boundary_->record\(\)\);\n'
        r'       last_\["w2_actual_C_call_started"\]=false;\n'
        r'       throw std::runtime_error\(std::string\("w2_boundary_"\)\+\n'
        r'         w2_wire::disposition_name\(boundary_->record\(\)\.disposition\)\);\n'
        r'     \}\n'
        r'   \}\n'
        r'   last_\["backend_entries_started"\]',
        '   last_["backend_entries_started"]'),
    # The original seam silently dropped, which is the regression the review
    # reproduced with a throwing hook.
    'delete_before_call_hook': (
        BACKEND_REL,
        r'   if\(hook_\)hook_\(ordinal\);\n',
        ''),
}

SUITES = ['test_w2_native_boundary', 'test_w2_backend_wiring', 'test_w2_entry_contract']

CONFIGURE = '''
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec cmake -S "{src}" -B "{build}" -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG' -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DP1_OWNED_SOURCE_BUNDLE_SHA256=x -DP1_DRIVER_TOOL_SHA256=x \
  -DP1_V4_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json \
  -DP1_V3_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json
'''

BUILD = '''
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec cmake --build "{build}" --target {targets} -j2
'''


def sha_tree(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def run_script(body: str, timeout: int = 600) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as f:
        f.write(body)
        path = f.name
    try:
        return subprocess.run(['/bin/bash', path], capture_output=True,
                              text=True, timeout=timeout)
    finally:
        Path(path).unlink(missing_ok=True)


def configure_and_build(src: Path, build: Path) -> tuple[bool, str]:
    r = run_script(CONFIGURE.format(src=src, build=build))
    if r.returncode != 0:
        return False, (r.stdout + r.stderr)[-3000:]
    cache = build / 'CMakeCache.txt'
    if not cache.is_file() or f'CMAKE_HOME_DIRECTORY:INTERNAL={src}' not in cache.read_text():
        return False, 'build directory is not bound to the expected source root'
    r = run_script(BUILD.format(build=build, targets=' '.join(SUITES)))
    if r.returncode != 0:
        return False, (r.stdout + r.stderr)[-3000:]
    return True, ''


def summary(output: str) -> dict:
    passed = re.search(r'\[  PASSED  \] (\d+) tests?', output)
    failed = re.findall(r'\[  FAILED  \] (\w+\.\w+)', output)
    return {'passed': int(passed.group(1)) if passed else 0,
            'failed_tests': sorted(set(failed))}


def run_suite(build: Path, name: str) -> tuple[bool, str]:
    env = {
        'PATH': '/usr/local/bin:/usr/bin:/bin',
        'LD_LIBRARY_PATH': '/home/trevor/acados/lib:/home/trevor/.local/lib/'
                           'python3.12/site-packages/casadi',
    }
    r = subprocess.run([str(build / name)], capture_output=True, text=True,
                       env=env, timeout=300)
    return r.returncode == 0, r.stdout[-4000:]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sealed_before = sha_tree(TREE)
    report = {'schema': 'M4-diagnostic-w2-wiring-v2',
              'sealed_tree_hashes_before': len(sealed_before),
              'suites': {}, 'mutations': {}, 'private_copies': True}

    with tempfile.TemporaryDirectory(prefix='w2_wire_') as tmp:
        tmp = Path(tmp)
        private = tmp / 'author'
        shutil.copytree(TREE, private, ignore=shutil.ignore_patterns('__pycache__'))
        build = tmp / 'build'

        ok, log = configure_and_build(private, build)
        if not ok:
            print('BUILD FAILED')
            print(log)
            return 2
        for name in SUITES:
            passed, out = run_suite(build, name)
            report['suites'][name] = {'pass': passed, **summary(out)}
            print('suite %-26s %s %s' % (name, 'PASS' if passed else 'FAIL',
                                         report['suites'][name]))
            if not passed:
                print(out[-1200:])

        for mname, (rel, pattern, replacement) in MUTATIONS.items():
            target = private / rel
            original = target.read_text()
            mutated, count = re.subn(pattern, replacement, original, flags=re.S)
            if count != 1:
                report['mutations'][mname] = {
                    'prepared': False,
                    'reason': 'pattern matched %d times' % count}
                print('mutation %-28s NOT PREPARED (x%d)' % (mname, count))
                continue
            target.write_text(mutated)
            try:
                ok, log = configure_and_build(private, build)
                if not ok:
                    report['mutations'][mname] = {
                        'prepared': True, 'build_failed': True,
                        'caught_by_test_suite': False, 'detail': log[-400:]}
                    print('mutation %-28s BUILD FAILED (not counted)' % mname)
                    continue
                failed_tests = []
                for suite in SUITES:
                    s_ok, s_out = run_suite(build, suite)
                    if not s_ok:
                        failed_tests.extend(summary(s_out)['failed_tests'])
                caught = bool(failed_tests)
                report['mutations'][mname] = {
                    'prepared': True, 'caught_by_test_suite': caught,
                    'failed_tests': sorted(set(failed_tests))}
                print('mutation %-28s %s' % (
                    mname,
                    'caught by %s' % sorted(set(failed_tests)) if caught
                    else 'NOT CAUGHT (blind spot)'))
            finally:
                target.write_text(original)

    sealed_after = sha_tree(TREE)
    report['sealed_tree_unchanged'] = sealed_before == sealed_after
    suites_ok = all(v['pass'] for v in report['suites'].values())
    prepared = {k: v for k, v in report['mutations'].items() if v.get('prepared')}
    all_caught = all(v.get('caught_by_test_suite') for v in prepared.values())
    unpreparable = [k for k, v in report['mutations'].items()
                    if not v.get('prepared')]
    report['suites_pass'] = suites_ok
    report['all_prepared_mutations_caught'] = all_caught
    report['unprepared_mutations'] = unpreparable
    report['complete'] = (suites_ok and all_caught and not unpreparable
                          and report['sealed_tree_unchanged'])

    path = OUT / 'wiring_verification_v2.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print()
    print('suites pass:', suites_ok)
    print('every prepared mutation caught:', all_caught)
    print('sealed tree unchanged:', report['sealed_tree_unchanged'])
    if unpreparable:
        print('could not prepare:', unpreparable)
    print('written:', path)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
