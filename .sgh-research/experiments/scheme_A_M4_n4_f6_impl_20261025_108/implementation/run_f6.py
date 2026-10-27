#!/usr/bin/env python3
"""Run the 6 registered F6 cases once each: bounded, fresh output, no retry.
Fail-closed: rc==0 AND passed AND assertion list exactly matches registration."""
import hashlib, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT / 'implementation/F6_registration.json').read_bytes())
REGISTRY = json.loads((ROOT / 'implementation/f6_registry.json').read_bytes())
BINARY = Path(REGISTRY['test_binary'])
RUNS = ROOT / 'implementation/runs'
POSTRUN = ROOT / 'postrun'
RUNS.mkdir(parents=True, exist_ok=True); POSTRUN.mkdir(parents=True, exist_ok=True)

def pin(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

if pin(BINARY) != REGISTRY['test_binary_sha256']:
    raise SystemExit('binary SHA mismatch vs registry (re-run freeze_f6.py)')

env = {**os.environ, 'LD_LIBRARY_PATH': '/home/trevor/acados/lib'}
verdict = {'schema': 'F6-run-verdict/v1', 'batch': 108, 'cases': [], 'auto_retry': 0, 'passed': False}
for case in REG['cases']:
    out = RUNS / case['case_id']
    if out.exists():
        raise SystemExit(f'output exists: {out} (single finite execution policy)')
    begin = time.monotonic()
    try:
        r = subprocess.run([str(BINARY), case['case_id'], str(out)], capture_output=True,
                           text=True, timeout=case['budget_seconds'], env=env)
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
    emitted = [a['name'] for a in result['assertions']] if isinstance(result, dict) and 'assertions' in result else []
    ok = (not timed_out) and rc == 0 and isinstance(result, dict) \
         and result.get('passed') is True and elapsed <= case['budget_seconds'] \
         and emitted == case['assertions'] and all(a['passed'] for a in result['assertions'])
    verdict['cases'].append({'case': case['case_id'], 'rc': rc, 'timed_out': timed_out,
        'elapsed_seconds': elapsed, 'passed': ok, 'result_path': str(rp),
        'assertion_count': len(emitted), 'registered_count': len(case['assertions']),
        'stdout_tail': (stdout or '')[-200:], 'stderr_tail': (stderr or '')[-400:]})
    print(f'{case["case_id"]}: rc={rc} elapsed={elapsed}s assertions={len(emitted)}/{len(case["assertions"])} passed={ok}')

verdict['passed'] = len(verdict['cases']) == len(REG['cases']) and all(c['passed'] for c in verdict['cases'])
(POSTRUN / 'f6_run_verdict_v1.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
print('VERDICT passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
