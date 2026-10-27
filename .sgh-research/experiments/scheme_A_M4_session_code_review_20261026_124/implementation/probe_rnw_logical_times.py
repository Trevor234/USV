#!/usr/bin/env python3
"""Check causal timestamps, independent of valid diagnostic append-order differences."""
from pathlib import Path
import copy
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
P119 = ROOT.parent / 'scheme_A_M4_rnw_s4_owned_20261025_119/implementation'
path = P119 / 'rnw_audit_v1.py'
spec = importlib.util.spec_from_file_location('review_rnw_times', path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
rows = [json.loads(s) for s in (P119 / 'runs/T2A_RNW3/regulator/source.jsonl').read_text().splitlines() if s.strip()]
selected = [r for r in rows if r.get('type') == 'reference_epoch_generation_opened'
            or (r.get('type') in ('job', 'candidate_registration') and r.get('job', {}).get('job_id') == 7)
            or (r.get('type') in ('decision', 'owned_API_pair', 'owned_applied_publication') and r.get('sequence') == 18)]
out = []
for name in ['baseline', 'ready_before_submit', 'activation_before_ready', 'API_before_activation']:
    stream = copy.deepcopy(selected)
    job = next(r for r in stream if r['type'] == 'job')
    cand = next(r for r in stream if r['type'] == 'candidate_registration')
    dec = next(r for r in stream if r['type'] == 'decision')
    pair = next(r for r in stream if r['type'] == 'owned_API_pair')
    if name == 'ready_before_submit':
        cand['ready_commit_ns'] = job['submit_commit_ns'] - 1
    elif name == 'activation_before_ready':
        dec['activation_commit_ns'] = cand['ready_commit_ns'] - 1
    elif name == 'API_before_activation':
        pair['starts'][0] = dec['activation_commit_ns'] - 2
        pair['ends'][0] = dec['activation_commit_ns'] - 1
    verdict = audit.audit_r4_acceptance_chain(stream)[0]
    assert verdict['passed'] is True
    out.append({'case': name, 'passed_by_current_R4': verdict['passed'],
                'logical_times': {'submit': job['submit_commit_ns'], 'ready': cand['ready_commit_ns'],
                                  'activation': dec['activation_commit_ns'], 'left_start': pair['starts'][0]}})
with (ROOT / 'evidence/replay01/rnw/logical_time_probe.json').open('x') as stream:
    stream.write(json.dumps({'scope': 'actual pure R4 function over private event copies; original files unchanged; no row-order rule invented', 'results': out}, indent=2) + '\n')
print(json.dumps({'cases': len(out), 'invalid_logical_time_cases_accepted': 3, 'owned_runs': 0}))
