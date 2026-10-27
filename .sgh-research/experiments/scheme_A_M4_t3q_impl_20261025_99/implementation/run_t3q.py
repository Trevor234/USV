#!/usr/bin/env python3
"""Run the 5 registered T3-Q cases once each: bounded, fresh output, zero retry.

Verdict is fail-closed: rc==0 AND result.json passed==true AND elapsed<=budget.
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT / 'implementation/T3Q_registration.json').read_bytes())
REGISTRY = json.loads((ROOT / 'implementation/t3q_registry.json').read_bytes())
BINARY = Path(REGISTRY['test_binary'])
RUNS = ROOT / 'implementation/runs'
POSTRUN = ROOT / 'postrun'
RUNS.mkdir(parents=True, exist_ok=True); POSTRUN.mkdir(parents=True, exist_ok=True)

def pin(p):
    raw = Path(p).read_bytes()
    return hashlib.sha256(raw).hexdigest()

# Fail-closed identity check before any run.
actual = pin(BINARY)
if actual != REGISTRY['test_binary_sha256']:
    raise SystemExit(f'binary SHA mismatch: registry={REGISTRY["test_binary_sha256"][:16]} actual={actual[:16]} (re-run freeze_t3q.py)')
if REG['tree_base']['binary_sha256'] != REGISTRY['test_binary_sha256']:
    raise SystemExit('registration/registry binary SHA disagreement')

verdict = {'schema': 'T3-queue-run-verdict/v1', 'batch': 99, 'cases': [], 'auto_retry': 0, 'passed': False}
for case in REG['cases']:
    out = RUNS / case['case_id']
    if out.exists():
        raise SystemExit(f'output exists: {out} (single finite execution policy; no overwrite, no retry)')
    begin = time.monotonic()
    try:
        r = subprocess.run([str(BINARY), case['case_id'], str(out)],
                           capture_output=True, text=True, timeout=case['budget_seconds'])
        rc, timed_out = r.returncode, False
        stdout, stderr = r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        rc, timed_out, stdout, stderr = 124, True, (e.stdout or b'').decode() if isinstance(e.stdout, bytes) else (e.stdout or ''), (e.stderr or b'').decode() if isinstance(e.stderr, bytes) else (e.stderr or '')
    elapsed = round(time.monotonic() - begin, 3)
    result = None
    rp = out / 'result.json'
    if rp.is_file():
        try: result = json.loads(rp.read_bytes())
        except Exception as e: result = {'unparsable': repr(e)}
    ok = (not timed_out) and rc == 0 and isinstance(result, dict) \
         and result.get('passed') is True and elapsed <= case['budget_seconds'] \
         and result.get('assertion_count') == len(case['assertions'])
    verdict['cases'].append({'case': case['case_id'], 'rc': rc, 'timed_out': timed_out,
        'elapsed_seconds': elapsed, 'budget_seconds': case['budget_seconds'], 'passed': ok,
        'result_path': str(rp), 'stdout_tail': (stdout or '')[-300:], 'stderr_tail': (stderr or '')[-600:]})
    print(f'{case["case_id"]}: rc={rc} timed_out={timed_out} elapsed={elapsed}s passed={ok}')

verdict['passed'] = len(verdict['cases']) == len(REG['cases']) and all(c['passed'] for c in verdict['cases'])
(POSTRUN / 't3q_run_verdict_v1.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
print('VERDICT passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
