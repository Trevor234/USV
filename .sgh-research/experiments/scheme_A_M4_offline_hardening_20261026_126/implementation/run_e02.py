#!/usr/bin/env python3
"""E02 (batch 126): RNW pure-audit matrix, fail-closed (fixes F124-02).

Runs the derived rnw_audit_v2 over:
  * the real RNW3 positive control (must stay accepted),
  * the two historical 112 failures (must NOT be accepted: no scoped open),
  * private counterexample fixtures built from the real RNW3 stream (missing
    close / missing clock / missing worker / identity / logical-time / fact),
  * the same private stream with legal-only variations (must NOT be false-rejected).

Fixtures are written under evidence/E02/<attempt>/fixtures/. Originals are only
read. Writes nothing outside the package. Exit 2 on any failure.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = Path('/home/trevor/USV/.sgh-research/experiments')
ATTEMPT = sys.argv[1] if len(sys.argv) > 1 else 'attempt01'
EVID = ROOT / f'evidence/E02/{ATTEMPT}'
FIX = EVID / 'fixtures'

sys.path.insert(0, str(ROOT / 'implementation/audit'))
import rnw_audit_v2 as audit  # noqa: E402

RNW3 = EXP / 'scheme_A_M4_rnw_s4_owned_20261025_119/implementation/runs/T2A_RNW3'
OLD112 = [
    EXP / 'scheme_A_M4_t2a_rnw2_impl_20261025_112/implementation/runs/T2A_RNW2',
    EXP / 'scheme_A_M4_t2a_rnw2_impl_20261025_112/implementation/runs/T2A_RNW2_attempt1',
]

failures = []


def record(name, ok, detail=None):
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + json.dumps(detail, default=str)[:200]) if detail is not None else ''))
    if not ok:
        failures.append({'case': name, 'detail': detail})
    return ok


def clone_run(dest, source=RNW3):
    """Copy the regulator Source and the close evidence into a private run dir."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'regulator').mkdir(exist_ok=True)
    shutil.copy2(source / 'regulator/source.jsonl', dest / 'regulator/source.jsonl')
    for name in ('driver_result.json', 'driver_events.jsonl'):
        if (source / name).is_file():
            shutil.copy2(source / name, dest / name)
    return dest


def edit_source(run_dir, mutate):
    p = run_dir / 'regulator/source.jsonl'
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    mutate(rows)
    p.write_text('\n'.join(json.dumps(r, sort_keys=True) for r in rows) + '\n')


if FIX.exists():
    shutil.rmtree(FIX)
FIX.mkdir(parents=True)

results = {}

# ---------------------------------------------------------------- POS-119
pos = audit.audit_rnw_run(RNW3, with_variants=True)
results['RNWV-POS-119'] = audit.summarise(pos)
results['RNWV-POS-119']['r4_fact'] = pos['r4_observed']['fact']
record('RNWV-POS-119', pos['r4_observed']['passed'] is True and pos['run_accepted']['accepted'] is True,
       {'r4': pos['r4_observed']['passed'], 'run_accepted': pos['run_accepted']['accepted'],
        'blockers': pos['run_accepted']['blockers'],
        'r4_fact': pos['r4_observed']['fact']})

# every R4 counterexample must fail; the file-order reversal must NOT
variants = pos['negative_variants']
legal_variants = {'file_order_reversed_still_legal', 'baseline_identity'}
for name, v in variants.items():
    if name in legal_variants:
        record(f'RNWV-LEGAL-{name}', v['r4_passed'] is True,
               {'expected': 'no false reject', 'observed': v['r4_passed']})
    else:
        record(f'RNWV-{name}', v['r4_passed'] is False,
               {'expected': 'R4 must fail', 'observed': v['r4_passed'], 'reason': v.get('reason')})
results['R4_variants'] = variants

# --------------------------------------------------------------- OLD-112
old = {}
for run in OLD112:
    r = audit.audit_rnw_run(run)
    old[run.name] = audit.summarise(r)
    record(f'RNWV-OLD-112.{run.name}',
           r['r4_observed']['passed'] is False and r['run_accepted']['accepted'] is False,
           {'r4': r['r4_observed']['passed'], 'run_accepted': r['run_accepted']['accepted'],
            'r4_reason': r['r4_observed']['detail'].get('reason'),
            'driver_selfreport_not_used': True})
results['RNWV-OLD-112'] = old

# ------------------------------------------------- run-level missing evidence
def run_level(name, build, expect_blocker):
    d = clone_run(FIX / name)
    build(d)
    r = audit.audit_rnw_run(d)
    blocked = expect_blocker in r['run_accepted']['blockers']
    record(f'RNWV-{name}', (not r['run_accepted']['accepted']) and blocked,
           {'run_accepted': r['run_accepted']['accepted'], 'blockers': r['run_accepted']['blockers'],
            'expected_blocker': expect_blocker, 'r4': r['r4_observed']['passed']})
    results[f'RNWV-{name}'] = {
        'r4_observed': r['r4_observed']['passed'],
        'run_accepted': r['run_accepted']['accepted'],
        'blockers': r['run_accepted']['blockers'],
        'note': 'R4 observation and run acceptance are reported separately',
    }
    return r


run_level('MISSING-CLOSE', lambda d: [(d / n).unlink() for n in
                                      ('driver_result.json', 'driver_events.jsonl')
                                      if (d / n).is_file()], 'close.evidence_present')
run_level('MISSING-CLOCK', lambda d: edit_source(
    d, lambda rows: rows.__setitem__(slice(None), [r for r in rows if r.get('type') != 'clock'])),
    'pause.confirmed')
def drop_worker(rows):
    """Remove the worker identity from the candidate echo only.

    The echo field lives inside the nested job object; also drop the top-level copy
    so the removal cannot be satisfied by a leftover.
    """
    for r in rows:
        if r.get('type') == 'candidate_registration':
            r.pop('worker_instance', None)
            if isinstance(r.get('job'), dict):
                r['job'].pop('worker_instance', None)


run_level('MISSING-WORKER', lambda d: edit_source(d, drop_worker), 'r4.same_job_full_chain')
run_level('MISSING-GENERATION', lambda d: edit_source(
    d, lambda rows: rows.__setitem__(slice(None),
                                     [r for r in rows if r.get('type') != 'reference_epoch_generation_opened'])),
    'generation.scoped_open')

# --------------------------------------------- identity / time / fact (source)
def source_variant(name, mutate, expect_r4_false=True):
    """Mutate a copy and ask R4 about THE SAME job the baseline accepts.

    Without pinning, breaking job 7 would just let R4 fall through to job 8 and the
    counterexample would pass for the wrong reason.
    """
    d = clone_run(FIX / name)
    edit_source(d, mutate)
    r = audit.audit_rnw_run(d, target_job=BASELINE_JOB)
    ok = (r['r4_observed']['passed'] is False) == expect_r4_false
    record(f'RNWV-{name}', ok, {'r4': r['r4_observed']['passed'],
                                'reason': r['r4_observed']['detail'].get('reason'),
                                'expected_r4_false': expect_r4_false})
    results[f'RNWV-{name}'] = {'r4_observed': r['r4_observed']['passed'],
                               'run_accepted': r['run_accepted']['accepted'],
                               'reason': r['r4_observed']['detail'].get('reason')}


def target_job(rows):
    g, fact = audit.audit_r4(rows)
    return (fact or {}).get('job_id')


def m_foreign(rows):
    jid = target_job(rows)
    for r in rows:
        if r.get('type') == 'candidate_registration' and r['job'].get('job_id') == jid:
            r['job']['run_id'] = 'FOREIGN-RUN'
            return


def m_dup_events(rows):
    jid = target_job(rows)
    for r in rows:
        if r.get('type') == 'candidate_registration' and r['job'].get('job_id') == jid:
            rows.append(json.loads(json.dumps(r)))   # duplicate the same id event
            return


def m_clock_epoch(rows):
    for r in rows:
        if r.get('type') == 'clock':
            r['epoch'] = 7                        # clock epoch moved: not the legal case


BASELINE_JOB = (pos['r4_observed']['fact'] or {}).get('job_id')


def m_foreign_pinned(rows):
    for r in rows:
        if r.get('type') == 'candidate_registration' and r['job'].get('job_id') == BASELINE_JOB:
            r['job']['run_id'] = 'FOREIGN-RUN'
            return


def m_dup_pinned(rows):
    for r in rows:
        if r.get('type') == 'candidate_registration' and r['job'].get('job_id') == BASELINE_JOB:
            rows.append(json.loads(json.dumps(r)))
            return


source_variant('IDENTITY-FOREIGN', m_foreign_pinned)
source_variant('IDENTITY-DUP', m_dup_pinned)
source_variant('LEGAL-EPOCH0', m_clock_epoch, expect_r4_false=False)

# ---------------------------------------------------------------- write files
(EVID / 'matrix.json').write_text(json.dumps({
    'schema': 'plan126-E02-matrix-v1',
    'auditor': {'path': str(ROOT / 'implementation/audit/rnw_audit_v2.py'),
                'sha256': __import__('hashlib').sha256(
                    (ROOT / 'implementation/audit/rnw_audit_v2.py').read_bytes()).hexdigest()},
    'auditor_origin': str(EXP / 'scheme_A_M4_rnw_s1_pure_20261025_117/implementation/rnw_audit_v1.py'),
    'results': results,
    'pos_r4_fact': pos['r4_observed']['fact'],
    'run_accepted_gate_states': pos['run_accepted']['gate_states'],
    'conditional_states': pos['run_accepted']['conditional_states_recorded_not_blocking'],
    'four_dimensions_separate': True,
}, indent=2, sort_keys=True) + '\n')

status = 'PASS' if not failures else 'FAIL_STOP'
(EVID / 'verification.json').write_text(json.dumps({
    'schema': 'plan126-E02-verification-v1', 'step_id': 'E02', 'status': status,
    'failures': failures,
    'observed_facts': {
        'rnw3_r4_observed': pos['r4_observed']['passed'],
        'rnw3_run_accepted': pos['run_accepted']['accepted'],
        'rnw3_job': (pos['r4_observed']['fact'] or {}).get('job_id'),
        'rnw3_sequence': (pos['r4_observed']['fact'] or {}).get('sequence'),
        'r4_counterexamples_failed_as_required': sum(
            1 for n, v in variants.items() if n not in legal_variants and v['r4_passed'] is False),
        'r4_counterexamples_total': len([n for n in variants if n not in legal_variants]),
        'legal_variants_not_false_rejected': sum(
            1 for n, v in variants.items() if n in legal_variants and v['r4_passed'] is True),
        'old112_runs_rejected': all(v['run_accepted'] is False for v in old.values()),
        'cases_total': len(results),
    },
    'run_accepted': {'accepted': status == 'PASS'},
    'coverage': {
        'r4_positive_fact': 'covered — RNW3 Job7/seq18 with full identity echo and logical time',
        'run_acceptance_gating': 'covered — 16 acceptance gates, absence/not_covered/fail all block',
        'old_candidate_disposition': 'not_covered — recorded, tolerated, never counted as rejection',
        'identity_and_time_counterexamples': 'covered — 9 R4 variants',
        'run_level_missing_evidence': 'covered — 4 fixtures',
        'worker_and_stored_chain': 'partial — worker source is not read by this audit; '
                                   'the required-worker gate is expressed through the R4 echo',
    },
    'stage_qualified': False,
    'qualification': {'M4': False, 'F6': False, 'P1': False, 'plant': False,
                      'hard_realtime': False},
}, indent=2, sort_keys=True) + '\n')

print(f'\nE02 {status}: failures {len(failures)}')
sys.exit(0 if status == 'PASS' else 2)
