#!/usr/bin/env python3
"""Attempt-2 runner for the three cases whose attempt-1 verdict failed on the
registration-count defect (see T3Q_registration.json revision 2). Runs each
affected case ONCE into a fresh <case>_r2 directory, then writes a merged
batch verdict v2 with full lineage. No retry beyond this single attempt."""
import hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT / 'implementation/T3Q_registration.json').read_bytes())
REGISTRY = json.loads((ROOT / 'implementation/t3q_registry.json').read_bytes())
BINARY = Path(REGISTRY['test_binary'])
RUNS = ROOT / 'implementation/runs'
AFFECTED = ['T3-Q1r', 'T3-Q2', 'T3-Q3']

def pin(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

if REG.get('revision') != 2:
    raise SystemExit('expected registration revision 2')
if pin(BINARY) != REGISTRY['test_binary_sha256']:
    raise SystemExit('binary SHA mismatch vs registry (re-run freeze_t3q.py)')
if REG['tree_base']['binary_sha256'] != REGISTRY['test_binary_sha256']:
    raise SystemExit('registration/registry binary SHA disagreement')

verdict = {'schema': 'T3-queue-run-verdict/v2', 'batch': 99, 'auto_retry': 0,
    'attempt': 2, 'attempt_scope': AFFECTED,
    'defect_record': REG['revision_note'], 'cases': [], 'passed': False}
for case in REG['cases']:
    cid = case['case_id']
    if cid not in AFFECTED:
        continue  # attempt-1 evidence reused unchanged; merged below
    out = RUNS / (cid + '_r2')
    if out.exists():
        raise SystemExit(f'output exists: {out} (single finite execution policy)')
    begin = time.monotonic()
    try:
        r = subprocess.run([str(BINARY), cid, str(out)], capture_output=True, text=True,
                           timeout=case['budget_seconds'])
        rc, timed_out, stdout, stderr = r.returncode, False, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        rc, timed_out = 124, True
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or '')
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or '')
    elapsed = round(time.monotonic() - begin, 3)
    result = None
    rp = out / 'result.json'
    if rp.is_file():
        try: result = json.loads(rp.read_bytes())
        except Exception as e: result = {'unparsable': repr(e)}
    ok = (not timed_out) and rc == 0 and isinstance(result, dict) \
         and result.get('passed') is True and elapsed <= case['budget_seconds'] \
         and result.get('assertion_count') == len(case['assertions'])
    verdict['cases'].append({'case': cid, 'attempt': 2, 'run_dir': str(out), 'rc': rc,
        'timed_out': timed_out, 'elapsed_seconds': elapsed, 'passed': ok,
        'result_path': str(rp), 'stdout_tail': (stdout or '')[-300:], 'stderr_tail': (stderr or '')[-600:]})
    print(f'{cid} (attempt2): rc={rc} elapsed={elapsed}s passed={ok}')

# merge attempt-1 evidence for the unaffected cases (originals untouched)
for cid in ['T3-Q1d', 'T3-Q4']:
    result = json.loads((RUNS / cid / 'result.json').read_bytes())
    verdict['cases'].append({'case': cid, 'attempt': 1, 'run_dir': str(RUNS / cid), 'rc': 0,
        'timed_out': False, 'passed': result.get('passed') is True,
        'result_path': str(RUNS / cid / 'result.json'),
        'note': 'attempt-1 evidence reused; registration count matched on first attempt'})
verdict['passed'] = len(verdict['cases']) == 5 and all(c['passed'] for c in verdict['cases'])
(ROOT / 'postrun/t3q_run_verdict_v2.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
print('VERDICT v2 passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
