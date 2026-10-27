#!/usr/bin/env python3
"""Build and run the W2 release-gate component tests, plus mutation checks.

Two different things are reported, and they must not be confused:

  * the component suite passes;
  * each guard in the gate is *load-bearing* — removing it makes at least one
    test fail. A passing suite whose assertions would also pass against a
    gate with no identity check is not evidence of anything.

Read-only with respect to the 56 package. Writes only under `evidence/w2_gate/`.
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

HERE = Path(__file__).resolve().parent          # implementation/w2_gate
PKG = HERE.parents[1]
OUT = PKG / 'evidence' / 'w2_gate'

HEADER = HERE / 'w2_release_gate.hpp'
PIPE_HEADER = HERE / 'w2_pipe_reader.hpp'
TEST = HERE / 'test_w2_release_gate.cpp'
PIPE_TEST = HERE / 'test_w2_pipe_integration.cpp'

# name -> (header, regex, replacement) that removes one guard
MUTATIONS = {
    'drop_identity_comparison': (
        HEADER,
        r'if \(got\.run_seq != want\.run_seq \|\| got\.job_id != want\.job_id \|\|\n'
        r'      got\.ordinal != want\.ordinal \|\| got\.nonce != want\.nonce\) \{',
        'if (false) {'),
    'drop_crc_check': (
        HEADER,
        r'if \(get_u32\(in \+ 40\) != crc32\(in, 40\)\) return Outcome::kBadCrc;',
        'if (false) return Outcome::kBadCrc;'),
    'drop_stop_poll': (
        HEADER,
        r'if \(stop_requested && \*stop_requested\) \{',
        'if (false) {'),
    'drop_release_sequence_check': (
        HEADER,
        r'if \(release_seq != 1\) \{',
        'if (false) {'),
    'drop_partial_frame_distinction': (
        HEADER,
        r'outcome_ = got == 0 \? Outcome::kTimeout : Outcome::kPartialFrame;',
        'outcome_ = Outcome::kTimeout;'),
    # Pipe-level: treating an invalid fd as a timeout would burn the whole
    # budget instead of failing at once.
    'invalid_fd_waits_instead_of_failing': (
        PIPE_HEADER,
        r'if \(fd_ < 0 \|\| n == 0\) return 0;',
        'if (fd_ < 0 || n == 0) return -1;'),
    # Pipe-level: dropping the EINTR retry would report a signal as a timeout.
    'no_eintr_retry': (
        PIPE_HEADER,
        r'if \(errno == EINTR\) \{\n'
        r'          // A signal is not a protocol outcome\. Charge only the time actually\n'
        r'          // spent, then poll again with what remains of the budget\. Charging\n'
        r'          // the whole requested slice here would let a single signal consume\n'
        r'          // the entire budget and turn EINTR into a spurious timeout\.\n'
        r'          waited_ns \+= slice_elapsed_ns;\n'
        r'          if \(waited_ns >= budget_ns\) \{\n'
        r'            if \(elapsed_ns\) \*elapsed_ns = waited_ns;\n'
        r'            return -1;\n'
        r'          \}\n'
        r'          const int64_t left = budget_ns - waited_ns;\n'
        r'          timeout_ms = int\(\(left \+ 999999\) / 1000000\);\n'
        r'          if \(timeout_ms <= 0\) timeout_ms = 1;\n'
        r'          continue;\n'
        r'        \}',
        'if (errno == EINTR) { if (elapsed_ns) *elapsed_ns = waited_ns; return -1; }'),
}


def compile_and_run(header: Path, test: Path, out_bin: Path) -> tuple[bool, str]:
    build = subprocess.run(
        ['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-I', str(header.parent),
         str(test), '-lgtest', '-lgtest_main', '-pthread', '-o', str(out_bin)],
        capture_output=True, text=True)
    if build.returncode != 0:
        return False, 'BUILD FAILED:\n' + build.stderr[-2000:]
    run = subprocess.run([str(out_bin)], capture_output=True, text=True)
    return run.returncode == 0, run.stdout[-4000:]


def summarise(output: str) -> dict:
    passed = re.search(r'\[  PASSED  \] (\d+) tests?', output)
    failed = re.findall(r'\[  FAILED  \] (\w+\.\w+)', output)
    return {'passed': int(passed.group(1)) if passed else 0,
            'failed_tests': sorted(set(failed))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'schema': 'M4-diagnostic-w2-gate-component-v1',
              'header': str(HEADER), 'pipe_header': str(PIPE_HEADER),
              'test': str(TEST), 'pipe_test': str(PIPE_TEST),
              'component_suite': None, 'pipe_suite': None, 'mutations': {}}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ok, output = compile_and_run(HEADER, TEST, tmp / 'gate')
        report['component_suite'] = {'pass': ok, **summarise(output)}
        print('component suite:', 'PASS' if ok else 'FAIL',
              report['component_suite'])

        # The pipe suite links the pipe header through the same include dir, so
        # a mutation of either header must be visible to both suites.
        pipe_ok, pipe_out = compile_and_run(PIPE_HEADER, PIPE_TEST, tmp / 'pipe')
        report['pipe_suite'] = {'pass': pipe_ok, **summarise(pipe_out)}
        print('pipe suite:', 'PASS' if pipe_ok else 'FAIL',
              report['pipe_suite'])

        # Each mutation is applied to the copy of the tree its target suite
        # compiles, then BOTH suites are run: a guard that only the other suite
        # covers would otherwise look caught without the right test seeing it.
        for name, (target, pattern, replacement) in MUTATIONS.items():
            source_text = target.read_text()
            mutated, count = re.subn(pattern, replacement, source_text)
            if count != 1:
                report['mutations'][name] = {
                    'prepared': False,
                    'reason': 'pattern matched %d times' % count}
                print('mutation', name, 'NOT PREPARED (pattern x%d)' % count)
                continue
            d = tmp / name
            d.mkdir()
            # Copy both headers and both tests, so either suite can run.
            for h in (HEADER, PIPE_HEADER):
                shutil.copy(h, d / h.name)
            (d / target.name).write_text(mutated)
            for t in (TEST, PIPE_TEST):
                shutil.copy(t, d / t.name)
            suite_results = {}
            caught_by = []
            for suite_name, hdr, tst in (('component', d / HEADER.name, d / TEST.name),
                                         ('pipe', d / PIPE_HEADER.name, d / PIPE_TEST.name)):
                s_ok, s_out = compile_and_run(hdr, tst, d / (suite_name + '_bin'))
                suite_results[suite_name] = {'pass': s_ok, **summarise(s_out)}
                if not s_ok:
                    caught_by.extend(suite_results[suite_name]['failed_tests'])
            caught = bool(caught_by)
            report['mutations'][name] = {
                'prepared': True,
                'target': target.name,
                'caught_by_test_suite': caught,
                'failed_tests': sorted(set(caught_by)),
                'suites': suite_results}
            print('mutation', name, '->',
                  'caught by %s' % report['mutations'][name]['failed_tests']
                  if caught else 'NOT CAUGHT (blind spot)')

    suite_ok = report['component_suite']['pass'] and report['pipe_suite']['pass']
    all_caught = all(v.get('caught_by_test_suite') for k, v in report['mutations'].items()
                     if v.get('prepared'))
    unpreparable = [k for k, v in report['mutations'].items() if not v.get('prepared')]
    report['suites_pass'] = suite_ok
    report['suite_passes'] = suite_ok
    report['all_prepared_mutations_caught'] = all_caught
    report['unprepared_mutations'] = unpreparable
    report['complete'] = suite_ok and all_caught and not unpreparable

    path = OUT / 'component_verification_v1.json'
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    print()
    print('suite passes:', suite_ok)
    print('every prepared mutation caught:', all_caught)
    if unpreparable:
        print('mutations that could not be prepared:', unpreparable)
    print('written:', path)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
