#!/usr/bin/env python3
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'scheme_A_W2_fix_review_20261022_61/implementation/w2_author/worker/run_driver_branch_replay.py'
OUT = ROOT / 'evidence/driver_replay'
OUT.mkdir(exist_ok=False)
scope = {'__file__': str(SOURCE), '__name__': 'submitted_driver_replay'}
exec(compile(SOURCE.read_text(), str(SOURCE), 'exec'), scope)
scope['OUT'] = OUT
with (OUT / 'stdout.txt').open('w') as stdout, (OUT / 'stderr.txt').open('w') as stderr:
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = scope['main']()
assert code == 0, code
report = json.loads((OUT / 'driver_branch_replay_v1.json').read_text())
assert report['all_passed'] and len(report['cases']) == 5
print(json.dumps({'source': str(SOURCE), 'cases': 5, 'all_passed': True,
                  'scope': 'submitted observation-postconditions only; no Driver main or owned run'}))
