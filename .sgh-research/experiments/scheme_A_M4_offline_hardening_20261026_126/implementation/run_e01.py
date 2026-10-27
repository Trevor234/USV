#!/usr/bin/env python3
"""E01 (batch 126): run the registered Q-family matrix once each, fail-closed.

Each case runs exactly one finite invocation into a FRESH output directory.
Fail-closed verdict = rc == 0 AND result.passed is True AND the emitted assertion
name list exactly matches the registration AND every assertion passed.

Also audits the two retained batch-99 Q2 logs as negative controls (350 and 303
duplicated identities) without touching them, and records the mutation outcome
from the recorded mutation ledger.

Writes only under evidence/E01/. Exit 2 on any failure.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = Path('/home/trevor/USV/.sgh-research/experiments')
ATTEMPT = sys.argv[1] if len(sys.argv) > 1 else 'attempt01'
BUILD = ROOT / 'build/e01' / ATTEMPT
EVID = ROOT / f'evidence/E01/{ATTEMPT}'
RUNS = EVID / 'runs'
AUTHOR = ROOT / 'implementation/author'
SRC = ROOT / 'implementation/tests/test_t3_queue_pressure_v2.cpp'

sys.path.insert(0, str(ROOT / 'implementation/audit'))
import t3_identity_audit as ident  # noqa: E402

REGISTRATION = {
    'schema': 'plan126-E01-registration-v1',
    'case_family': 'Q2V',
    'harness': str(SRC),
    'binary_flavours': ['release', 'asan'],
    'budget_seconds': 60,
    'auto_retry': 0,
    'fresh_output_required': True,
    'cases': [
        {'case_id': 'Q2V-Q1d', 'assertions': [
            'terminal_add_rejects_while_full',
            'blocked_publisher_delivered_nothing_yet',
            'accepted_capacity_plus_one',
            'rejected_equals_K',
            'overflow_and_failure_each_once',
            'publisher_delivered_exactly_accepted',
            'file_rows_accepted_plus_summary',
            'generated_equals_attempts',
            'balance_generated_equals_emitted_plus_dropped',
            'normal_source_complete_false',
            'failed_terminal_after_close',
            'peak_equals_capacity',
            'snapshot_dropped_matches',
            'snapshot_generated_matches',
            'q1d_offered_identities_unique',
            'q1d_published_multiset_equals_accepted',
            'q1d_disk_multiset_equals_accepted',
        ]},
        {'case_id': 'Q2V-Q1r', 'assertions': [
            'bounded_drain_out_completed',
            'attempts_all_accounted',
            'generated_equals_attempts',
            'dropped_equals_rejected',
            'pressure_actually_applied',
            'failed_flag_true',
            'peak_within_capacity',
            'queue_overflow_phase_exactly_once',
            'source_failure_phase_exactly_once',
            'publisher_delivered_exactly_accepted',
            'file_rows_accepted_plus_summary',
            'generated_equals_attempts',
            'balance_generated_equals_emitted_plus_dropped',
            'normal_source_complete_false',
        ]},
        {'case_id': 'Q2V-Q2', 'assertions': [
            'bounded_drain_out_completed',
            'attempts_all_accounted',
            'generated_equals_attempts',
            'dropped_equals_rejected',
            'pressure_actually_applied',
            'failed_flag_true',
            'peak_within_capacity',
            'queue_overflow_phase_exactly_once',
            'source_failure_phase_exactly_once',
            'publisher_delivered_exactly_accepted',
            'file_rows_accepted_plus_summary',
            'generated_equals_attempts',
            'balance_generated_equals_emitted_plus_dropped',
            'normal_source_complete_false',
            'q2_offered_identities_unique',
            'q2_accepted_identities_unique',
            'q2_offered_eq_accepted_plus_rejected',
            'q2_published_multiset_equals_accepted',
            'q2_disk_multiset_equals_accepted',
            'q2_producer_local_sequence_consistent',
        ]},
        {'case_id': 'Q2V-Q3', 'assertions': [
            'bounded_drain_out_completed',
            'attempts_all_accounted',
            'generated_equals_attempts',
            'dropped_equals_rejected',
            'pressure_actually_applied',
            'failed_flag_true',
            'peak_within_capacity',
            'queue_overflow_phase_exactly_once',
            'source_failure_phase_exactly_once',
            'publisher_delivered_exactly_accepted',
            'file_rows_accepted_plus_summary',
            'generated_equals_attempts',
            'balance_generated_equals_emitted_plus_dropped',
            'normal_source_complete_false',
            'each_accepted_event_exactly_once',
            'published_multiset_equals_accepted',
            'sequences_within_registered_ranges',
        ]},
        {'case_id': 'Q2V-Q4', 'assertions': [
            'bounded_drain_completed',
            'no_pressure_no_rejection',
            'failed_flag_false',
            'no_overflow_no_failure_phases',
            'normal_source_complete_true',
            'dropped_zero',
            'all_emitted',
            'generated_equals_attempts',
            'q4_disk_multiset_equals_accepted',
        ]},
    ],
}

BUILDS = {
    'release': ['-std=c++17', '-O2', '-DNDEBUG'],
    'asan': ['-std=c++17', '-O1', '-g', '-fsanitize=address',
             '-fsanitize-address-use-after-scope', '-fno-omit-frame-pointer'],
}
INCLUDES = ['-I', str(AUTHOR / 'observer/src/shadow'), '-I', str(AUTHOR / 'common')]

failures = []


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def record(name, ok, detail=None):
    if not ok:
        failures.append({'clause': name, 'detail': detail})
    return ok


for d in (BUILD, RUNS, EVID / 'mutation'):
    d.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------- registration first
(EVID / 'registration.json').write_text(json.dumps(REGISTRATION, indent=2, sort_keys=True) + '\n')

# ------------------------------------------------------------- build both flavours
builds = {}
for flavour, flags in BUILDS.items():
    binary = BUILD / f'q2v_{flavour}'
    cmd = ['g++'] + flags + INCLUDES + [str(SRC), '-o', str(binary), '-pthread']
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    (EVID / (flavour + '_build.stdout')).write_text(r.stdout)
    (EVID / (flavour + '_build.stderr')).write_text(r.stderr)
    builds[flavour] = {
        'argv': cmd, 'exit_code': r.returncode,
        'elapsed_seconds': round(time.monotonic() - t0, 2),
        'stderr_tail': r.stderr[-2000:],
        'binary': str(binary),
        'binary_pin': pin(binary) if binary.is_file() else None,
    }
    record(f'build.{flavour}', r.returncode == 0, builds[flavour]['stderr_tail'][-400:])

# ------------------------------------------------------------- run the matrix
verdicts = []
for case in REGISTRATION['cases']:
    out = RUNS / case['case_id']
    if out.exists():
        raise SystemExit(f'output exists, single finite execution violated: {out}')
    t0 = time.monotonic()
    r = subprocess.run([str(BUILD / 'q2v_release'), case['case_id'], str(out)],
                       capture_output=True, text=True, timeout=REGISTRATION['budget_seconds'])
    elapsed = round(time.monotonic() - t0, 2)
    (EVID / (case['case_id'] + '.stdout')).write_text(r.stdout)
    (EVID / (case['case_id'] + '.stderr')).write_text(r.stderr)
    rp = out / 'result.json'
    result = json.loads(rp.read_bytes()) if rp.is_file() else None
    emitted = [a['name'] for a in result['assertions']] if isinstance(result, dict) and 'assertions' in result else []
    ok = (r.returncode == 0 and isinstance(result, dict)
          and result.get('passed') is True
          and emitted == case['assertions']
          and all(a['passed'] for a in result['assertions'])
          and elapsed <= REGISTRATION['budget_seconds'])
    verdicts.append({'case': case['case_id'], 'exit_code': r.returncode,
                     'elapsed_seconds': elapsed, 'passed': ok,
                     'assertion_count': len(emitted),
                     'registered_count': len(case['assertions']),
                     'assertions_exact': emitted == case['assertions'],
                     'result_path': str(rp),
                     'stdout_tail': r.stdout[-200:], 'stderr_tail': r.stderr[-300:]})
    record(f'case.{case["case_id"]}', ok, verdicts[-1])

# ------------------------------------------------- ASAN run of the fixed Q2 case
asan_out = RUNS / 'Q2V-Q2_asan'
if asan_out.exists():
    raise SystemExit('asan output exists')
env = {**os.environ, 'ASAN_OPTIONS': 'detect_stack_use_after_return=1:abort_on_error=0'}
ra = subprocess.run([str(BUILD / 'q2v_asan'), 'Q2V-Q2', str(asan_out)],
                    capture_output=True, text=True, timeout=180, env=env)
asan_reports = [ln for ln in ra.stderr.splitlines() if 'AddressSanitizer' in ln or 'LeakSanitizer' in ln]
(EVID / 'asan_fixed.stdout').write_text(ra.stdout)
(EVID / 'asan_fixed.stderr').write_text(ra.stderr)
asan_result = asan_out / 'result.json'
asan_passed = json.loads(asan_result.read_bytes())['passed'] if asan_result.is_file() else None
record('Q2V-LIFETIME.asan_clean',
       ra.returncode == 0 and not asan_reports and asan_passed is True,
       {'exit_code': ra.returncode, 'asan_reports': asan_reports[:2], 'result_passed': asan_passed})

# ------------------------------------------------------- mutate: restore ref capture
MUTANT = EVID / 'mutation/test_t3_queue_pressure_v2_refcapture.cpp'
mut_src = SRC.read_text()
MUT_OLD = "    ts.emplace_back([&,base,producer]{"
MUT_NEW = "    ts.emplace_back([&,producer]{  // MUTANT: base is a loop local captured by reference"
if mut_src.count(MUT_OLD) != 1:
    record('mutation.prepared', False, {'reason': 'capture site not unique', 'count': mut_src.count(MUT_OLD)})
else:
    MUTANT.write_text(mut_src.replace(MUT_OLD, MUT_NEW))
    record('mutation.prepared', True, {'target': 'by-value producer base capture',
                                       'diff_lines': 1})
mut_bin = BUILD / 'q2v_mutant'
mb = subprocess.run(['g++', '-std=c++17', '-O1', '-g', '-fsanitize=address',
                     '-fsanitize-address-use-after-scope', '-fno-omit-frame-pointer']
                    + INCLUDES + [str(MUTANT), '-o', str(mut_bin), '-pthread'],
                    capture_output=True, text=True, timeout=300)
mut_run_dir = RUNS / 'Q2V-MUT-CAPTURE_asan'
if mut_run_dir.exists():
    raise SystemExit('mutant output exists')
mr = subprocess.run([str(mut_bin), 'Q2V-Q2', str(mut_run_dir)],
                    capture_output=True, text=True, timeout=180, env=env) if mb.returncode == 0 else None
(EVID / 'mutation_build.stdout').write_text(mb.stdout)
(EVID / 'mutation_build.stderr').write_text(mb.stderr)
if mr is not None:
    (EVID / 'mutation_run.stdout').write_text(mr.stdout)
    (EVID / 'mutation_run.stderr').write_text(mr.stderr)
mut_caught = bool(mr and 'stack-use-after-scope' in mr.stderr)
record('Q2V-MUT-CAPTURE', mut_caught,
       {'build_exit': mb.returncode, 'run_exit': mr.returncode if mr else None,
        'asan_report_present': mut_caught,
        'note': 'a build failure would NOT count as a catch'})

# ------------------------------------------- retained negative controls (read-only)
OLD = {
    'T3-Q2': EXP / 'scheme_A_M4_t3q_impl_20261025_99/implementation/runs/T3-Q2/q2.jsonl',
    'T3-Q2_r2': EXP / 'scheme_A_M4_t3q_impl_20261025_99/implementation/runs/T3-Q2_r2/q2.jsonl',
}
old_audits, old_pins_before = {}, {}
for name, path in OLD.items():
    old_pins_before[name] = pin(path)
    old_audits[name] = ident.audit_event_file(path)
OLD_RESULT_PINS = {
    'T3-Q2': pin(EXP / 'scheme_A_M4_t3q_impl_20261025_99/implementation/runs/T3-Q2/result.json'),
    'T3-Q2_r2': pin(EXP / 'scheme_A_M4_t3q_impl_20261025_99/implementation/runs/T3-Q2_r2/result.json'),
}
q2_old = old_audits['T3-Q2']['identity_multiset']
q2r2_old = old_audits['T3-Q2_r2']['identity_multiset']
record('Q2V-RAW-OLD', q2r2_old['duplicated_entries'] == 350 and q2r2_old['unique'] == 163,
       {'T3-Q2_r2': q2r2_old})
record('Q2V-RAW-OLD2', q2_old['duplicated_entries'] == 303,
       {'T3-Q2': q2_old})
# the old verdicts must be untouched
for name, p in OLD.items():
    if pin(p) != old_pins_before[name]:
        record(f'Q2V-RAW-OLD.no_write.{name}', False, {'path': str(p)})

# ----------------------------------------------------------- new-case audits
new_audits = {}
for cid in ('Q2V-Q1d', 'Q2V-Q1r', 'Q2V-Q2', 'Q2V-Q3', 'Q2V-Q4'):
    log = RUNS / cid / {'Q2V-Q1d': 'q1d.jsonl', 'Q2V-Q1r': 'q1r.jsonl', 'Q2V-Q2': 'q2.jsonl',
                        'Q2V-Q3': 'q3.jsonl', 'Q2V-Q4': 'q4.jsonl'}[cid]
    new_audits[cid] = ident.audit_event_file(log)
    record(f'audit.{cid}.identity_unique',
           not new_audits[cid]['duplicates_present'], new_audits[cid]['identity_multiset'])
    record(f'audit.{cid}.producer_identity_recorded',
           new_audits[cid]['producer_identity_recorded'], None)
    record(f'audit.{cid}.summary_balance',
           new_audits[cid].get('summary_balance_ok') is True, None)

# --------------------------------------------------------------- write evidence
population = {
    'schema': 'plan126-E01-population-v1',
    'registration': str(EVID / 'registration.json'),
    'harness': {'path': str(SRC), **pin(SRC)},
    'builds': builds,
    'cases_run': len(verdicts),
    'cases_passed': sum(1 for v in verdicts if v['passed']),
    'counts_are_not_the_metric': 'each case must match its registered assertion list exactly',
}
(EVID / 'population.json').write_text(json.dumps(population, indent=2, sort_keys=True) + '\n')

(EVID / 'verdicts.json').write_text(json.dumps({
    'schema': 'plan126-E01-verdicts-v1', 'auto_retry': 0,
    'cases': verdicts, 'passed': all(v['passed'] for v in verdicts),
}, indent=2, sort_keys=True) + '\n')

(EVID / 'identity_audit.json').write_text(json.dumps({
    'schema': 'plan126-E01-identity-audit-v1',
    'new_cases': new_audits,
    'retained_originals': old_audits,
    'original_pins_before': old_pins_before,
    'original_pins_after': {n: pin(p) for n, p in OLD.items()},
    'original_result_pins': OLD_RESULT_PINS,
    'originals_are_read_only': True,
    'policy': 'the old 14/14 verdicts are NOT rewritten; the identity finding is recorded '
              'separately and the old files are byte-identical before and after',
}, indent=2, sort_keys=True) + '\n')

(EVID / 'asan.json').write_text(json.dumps({
    'schema': 'plan126-E01-asan-v1',
    'fixed_build': builds['asan']['argv'],
    'fixed_run': {'case': 'Q2V-Q2', 'exit_code': ra.returncode,
                  'reports': asan_reports, 'clean': ra.returncode == 0 and not asan_reports,
                  'stderr_tail': ra.stderr[-800:]},
    'mutation_build': {'exit_code': mb.returncode, 'stderr_tail': mb.stderr[-800:]},
    'mutation_run': {'exit_code': mr.returncode if mr else None,
                     'caught_stack_use_after_scope': mut_caught,
                     'stderr_head': (mr.stderr[:1500] if mr else '')},
}, indent=2, sort_keys=True) + '\n')

status = 'PASS' if not failures else 'FAIL_STOP'
(EVID / 'verification.json').write_text(json.dumps({
    'schema': 'plan126-E01-verification-v1', 'step_id': 'E01', 'status': status,
    'failures': failures,
    'observed_facts': {
        'cases_registered': len(REGISTRATION['cases']),
        'cases_passed': sum(1 for v in verdicts if v['passed']),
        'fixed_q2_identities_unique': not new_audits['Q2V-Q2']['duplicates_present'],
        'old_T3-Q2_r2_duplicates_detected': q2r2_old['duplicated_entries'],
        'old_T3-Q2_duplicates_detected': q2_old['duplicated_entries'],
        'asan_clean_on_fixed_build': ra.returncode == 0 and not asan_reports and asan_passed is True,
        'mutation_caught_by_asan': mut_caught,
        'q1d_capacity_plus_one_preserved': next(
            (a['passed'] for a in json.loads((RUNS / 'Q2V-Q1d/result.json').read_bytes())['assertions']
             if a['name'] == 'accepted_capacity_plus_one'), None),
    },
    'run_accepted': {'accepted': status == 'PASS'},
    'coverage': {
        'q2_dangling_capture': 'covered — fixed and proven by ASAN + mutation',
        'q2_identity_bookkeeping': 'covered — per-producer identity and multiset reconciliation',
        'old_q2_duplicate_ids': 'covered — 350/303 detected without touching originals',
        'q1d_regression': 'covered',
        'diag_sink_business_behaviour': 'not_changed',
        'fixed_acceptance_count_513': 'not required and not enforced — the new cases assert '
                                      'multiset identity, not a fixed accepted count',
    },
    'stage_qualified': False,
    'qualification': {'M4': False, 'F6': False, 'P1': False, 'plant': False,
                      'hard_realtime': False},
}, indent=2, sort_keys=True) + '\n')

print(f'E01 {status}: cases {sum(1 for v in verdicts if v["passed"])}/{len(verdicts)}, '
      f'failures {len(failures)}')
for f in failures:
    print('  FAIL', f['clause'], json.dumps(f['detail'], default=str)[:200])
sys.exit(0 if status == 'PASS' else 2)
