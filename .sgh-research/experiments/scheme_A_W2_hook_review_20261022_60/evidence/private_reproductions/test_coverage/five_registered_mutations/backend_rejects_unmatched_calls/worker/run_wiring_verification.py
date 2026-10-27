#!/usr/bin/env python3
"""Build and run the W2 wiring tests, then mutate each guard.

Two separate claims, reported separately:
  * the wiring suites pass;
  * each guard in the boundary wiring is load-bearing — removing it makes at
    least one test fail.

The plan's §6.2 asks for exactly these targeted checks; a green suite whose
assertions would also pass against a boundary with no deadline guard is not
evidence of anything.
"""
from __future__ import annotations

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
BUILD = Path('/tmp/w2build')

BOUNDARY = HERE / 'w2_native_boundary.hpp'
BACKEND = HERE / 'owned_cold_backend.hpp'

MUTATIONS = {
    # The last guard is the whole point: a verified release must not grant
    # execution once the Job deadline has passed.
    'drop_expiry_guard': (
        BOUNDARY,
        r'    if \(guard > config_\.job_deadline_ns\) \{\n'
        r'      record_\.disposition = Disposition::kExpired;\n'
        r'      return false;\n'
        r'    \}',
        '    if (false) {\n'
        '      record_.disposition = Disposition::kExpired;\n'
        '      return false;\n'
        '    }'),
    # Off-by-one: `>=` would reject a release that lands exactly on the deadline.
    'expiry_off_by_one': (
        BOUNDARY,
        r'if \(guard > config_\.job_deadline_ns\)',
        'if (guard >= config_.job_deadline_ns)'),
    # NOTE: the boundary's own post-release stop check is deliberately NOT in
    # this list. The v2 Gate re-checks the predicate after assembly, so it
    # reports `stop_requested` before the boundary ever sees a `released`; the
    # boundary check is unreachable defense in depth for a different gate, not a
    # live guard. Claiming a mutation covers it would be claiming coverage of a
    # path nothing exercises.
    # Binding only on the ordinal would pause the first call of every Job.
    'bind_on_ordinal_only': (
        BOUNDARY,
        r'    return gate_ != nullptr && job_id == config_\.job_id &&\n'
        r'           ordinal == config_\.ordinal;',
        '    return gate_ != nullptr && ordinal == config_.ordinal;'),
    # Marking the call from the wrapper instead of from the C entry.
    'mark_call_before_guard': (
        BOUNDARY,
        r'    record_\.disposition = Disposition::kAllowed;\n'
        r'    return true;',
        '    record_.disposition = Disposition::kAllowed;\n'
        '    record_.actual_native_invoked = true;\n'
        '    return true;'),
    # The backend must not treat an unrelated call as a rejected one.
    'backend_rejects_unmatched_calls': (
        BACKEND,
        r'if\(boundary_&&boundary_->armed\(\)&&boundary_->matches\(ordinal,id\)\)\{',
        'if(boundary_&&boundary_->armed()){'),
}

SUITES = [('native_boundary', 'test_w2_native_boundary'),
          ('backend_wiring', 'test_w2_backend_wiring')]


def summary(output: str) -> dict:
    passed = re.search(r'\[  PASSED  \] (\d+) tests?', output)
    failed = re.findall(r'\[  FAILED  \] (\w+\.\w+)', output)
    return {'passed': int(passed.group(1)) if passed else 0,
            'failed_tests': sorted(set(failed))}


def build(targets: list[str]) -> tuple[bool, str]:
    cmd = ['cmake', '--build', str(BUILD), '--target', *targets, '-j2']
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stdout + r.stderr)[-3000:]
    return True, ''


def run(binary: Path) -> tuple[bool, str]:
    r = subprocess.run([str(binary)], capture_output=True, text=True,
                       env={'LD_LIBRARY_PATH':
                            '/home/trevor/acados/lib:/home/trevor/.local/lib/'
                            'python3.12/site-packages/casadi',
                            'PATH': '/usr/local/bin:/usr/bin:/bin'})
    return r.returncode == 0, r.stdout[-4000:]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'schema': 'M4-diagnostic-w2-wiring-v1', 'suites': {},
              'mutations': {}}

    ok, log = build([t for _, t in SUITES])
    if not ok:
        print('BUILD FAILED')
        print(log)
        return 2
    for name, target in SUITES:
        passed, out = run(BUILD / target)
        report['suites'][name] = {'pass': passed, **summary(out)}
        print('suite %-18s %s %s' % (name, 'PASS' if passed else 'FAIL',
                                     report['suites'][name]))
        if not passed:
            print(out[-1500:])

    originals = {p: p.read_text() for p in {BOUNDARY, BACKEND}}
    try:
        for name, (target, pattern, replacement) in MUTATIONS.items():
            mutated, count = re.subn(pattern, replacement, originals[target])
            if count != 1:
                report['mutations'][name] = {
                    'prepared': False,
                    'reason': 'pattern matched %d times' % count}
                print('mutation %-32s NOT PREPARED (x%d)' % (name, count))
                continue
            target.write_text(mutated)
            try:
                built, blog = build([t for _, t in SUITES])
                if not built:
                    report['mutations'][name] = {
                        'prepared': True, 'build_failed': True,
                        'caught_by_test_suite': False,
                        'detail': blog[-500:]}
                    print('mutation %-32s BUILD FAILED (not counted as caught)'
                          % name)
                    continue
                failed_tests = []
                for _, suite in SUITES:
                    s_ok, s_out = run(BUILD / suite)
                    if not s_ok:
                        failed_tests.extend(summary(s_out)['failed_tests'])
                caught = bool(failed_tests)
                report['mutations'][name] = {
                    'prepared': True,
                    'caught_by_test_suite': caught,
                    'failed_tests': sorted(set(failed_tests))}
                print('mutation %-32s %s' % (
                    name,
                    'caught by %s' % sorted(set(failed_tests)) if caught
                    else 'NOT CAUGHT (blind spot)'))
            finally:
                for p, text in originals.items():
                    p.write_text(text)
    finally:
        for p, text in originals.items():
            p.write_text(text)
        build([t for _, t in SUITES])  # restore the binaries

    suites_ok = all(v['pass'] for v in report['suites'].values())
    prepared = {k: v for k, v in report['mutations'].items() if v.get('prepared')}
    all_caught = all(v.get('caught_by_test_suite') for v in prepared.values())
    unpreparable = [k for k, v in report['mutations'].items() if not v.get('prepared')]
    report['suites_pass'] = suites_ok
    report['all_prepared_mutations_caught'] = all_caught
    report['unprepared_mutations'] = unpreparable
    report['complete'] = suites_ok and all_caught and not unpreparable

    path = OUT / 'wiring_verification_v1.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print()
    print('suites pass:', suites_ok)
    print('every prepared mutation caught:', all_caught)
    if unpreparable:
        print('could not prepare:', unpreparable)
    print('written:', path)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
