#!/usr/bin/env python3
"""Execute the single registered S4 owned run and adjudicate with the S1 pure
audit functions (rnw_audit_v1). The driver self-report is recorded, never
trusted; pass requires the R4 same-Job new-generation acceptance chain."""
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / 'implementation'
sys.path.insert(0, str(IMPL))
import rnw_audit_v1 as audit

DRIVER = (IMPL / 't2_author/t2b_gen_driver_v1.py').resolve()
SETUP = IMPL / 'setup_env.sh'
reg = json.loads((IMPL / 'T2A_RNW3_registration.json').read_bytes())
out = Path(reg['output'])
if out.exists():
    raise SystemExit(f'output exists {out} (single finite execution)')
begin = time.monotonic()
proc = subprocess.run(['/bin/bash', str(SETUP), '/usr/bin/python3', '-B', str(DRIVER),
                       '--registration', str((IMPL / 'T2A_RNW3_registration.json').resolve())],
                      capture_output=True, text=True, timeout=int(reg['max_seconds']) + 25)
elapsed = round(time.monotonic() - begin, 3)
verdict = {'schema': 'S4-owned-run-verdict/v1', 'batch': 119, 'output': str(out),
           'driver_rc': proc.returncode, 'elapsed_seconds': elapsed,
           'driver_stdout_tail': proc.stdout[-300:], 'driver_stderr_tail': proc.stderr[-600:]}
if not (out / 'driver_result.json').is_file():
    verdict['error'] = 'driver produced no result'
    verdict['passed'] = False
    (ROOT / 'postrun/s4_verdict_v1.json').write_text(json.dumps(verdict, indent=2) + '\n')
    print('VERDICT passed=False (no driver result)')
    sys.exit(2)
driver_result = json.loads((out / 'driver_result.json').read_bytes())
verdict['driver_selfreport_passed'] = driver_result.get('passed')  # evidence-only
audit_result = audit.audit_rnw_run(out)
verdict['audit'] = audit_result
verdict['passed'] = bool(audit_result.get('passed'))
(ROOT / 'postrun/s4_verdict_v1.json').write_text(json.dumps(verdict, indent=2, default=str) + '\n')
for c in audit_result.get('clauses', []):
    print(('PASS ' if c['passed'] else 'FAIL ') + c['name'] + ' [' + c['coverage'] + ']')
print('VERDICT passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
