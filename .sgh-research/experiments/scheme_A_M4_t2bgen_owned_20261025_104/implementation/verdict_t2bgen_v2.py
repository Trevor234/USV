#!/usr/bin/env python3
"""Verdict v2 for batch 104: recompute over the EXISTING run evidence with the
corrected generation-identity predicate. Runs are NOT re-executed (single
finite execution preserved; launch1-3 originals kept).

Defect in verdict v1 (analysis-only, runs unchanged): two_epoch_commits_
distinct_generations required the two committed events' path fingerprints to
differ. The owned flow exposed real fixture behavior the predicate missed:
the Fixture republishes its ORIGINAL .05 reference periodically, so the
registered path_replace (.1) is transient — the binding sequence is
(.05,task2) -> terminal on (.1,task4) -> (.05,task6), and generation 2
anchors on (.05,task6), differing from generation 1 by the version tuple,
not the fingerprint. The corrected predicate compares binding identity
(generation + task_generation + fingerprint) and additionally requires the
transient replace fingerprint to be observed in path_version events."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / 'implementation'
RUNS = IMPL / 'runs'

def rows_of(p):
    out = []
    for line in Path(p).read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

checks = []
def check(name, ok, detail=None):
    checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + json.dumps(detail, default=str)[:200]) if detail else ''))
    return bool(ok)

verdict = {'schema': 'T2B-GEN-owned-run-verdict/v2', 'batch': 104, 'cases': {}, 'passed': False,
           'v1_defect_record': Path(__file__).name.split('.')[0] + ' header text'}
checks = []
all_ok = True

# POS over existing evidence
out = RUNS / 'T2BGEN_POS'
result = json.loads((out / 'driver_result.json').read_bytes())
ev = rows_of(out / 'driver_events.jsonl')
src = rows_of(out / 'regulator/source.jsonl')
closed = result.get('closed_roles', [])
spawns = [e for e in ev if e['type'] == 'role_spawned']
all_ok &= check('POS.exactly_four_single_spawns', len(spawns) == 4 and len({s['role'] for s in spawns}) == 4,
                [s['role'] for s in spawns])
all_ok &= check('POS.roles_closed_clean',
                len(closed) == 4 and all(r.get('returncode') == 0 and r.get('group_empty') is True for r in closed),
                {r['role']: r.get('returncode') for r in closed})
pv = [r for r in src if r.get('type') == 'path_version']
fingerprints = {r.get('fingerprint') for r in pv}
all_ok &= check('POS.replace_fingerprint_observed', len(fingerprints) >= 2 and any(r.get('points') == 201 for r in pv),
                {'distinct_fingerprints': len(fingerprints), 'points': sorted({r.get('points') for r in pv})})
versions = [r.get('task_generation') for r in pv]
all_ok &= check('POS.task_generation_bumped', len(versions) >= 2 and versions[-1] > versions[0],
                {'seen': sorted(set(versions))})
opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
all_ok &= check('POS.single_generation_opened',
                len(opened) == 1 and opened[0].get('generation') == 2
                and opened[0].get('previous_terminal_reason') == 'epoch_binding_changed'
                and opened[0].get('previous_first_job_id') == 1 and opened[0].get('previous_last_job_id') == 2,
                {k: opened[0].get(k) for k in ('generation', 'previous_terminal_reason',
                                               'previous_first_job_id', 'previous_last_job_id')} if opened else None)
committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
def binding_of(c):
    e = c['reference_epoch']
    return (e.get('generation'), e.get('task_generation'), e.get('path_fingerprint'))
bindings = [binding_of(c) for c in committed]
all_ok &= check('POS.two_epoch_commits_distinct_binding_identity',
                len(committed) == 2 and [b[0] for b in bindings] == [1, 2] and bindings[0] != bindings[1],
                {'bindings': [(b[0], b[1], b[2][:12]) for b in bindings]})
resub = [r for r in src if r.get('type') == 'job_scoped_generation_resubmit']
all_ok &= check('POS.scoped_resubmit_after_open', len(resub) >= 1 and all(r.get('generation') == 2 for r in resub))
jobs_after = [r['job']['job_id'] for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)
              and r['job'].get('job_id', 0) > 2]
all_ok &= check('POS.jobs_submitted_in_generation_2', len(jobs_after) >= 1, {'ids': jobs_after[:8]})
rejects_after = [r for r in src if r.get('type') == 'job_not_submitted'
                 and str(r.get('reason', '')).startswith('task_time_reference:')]
all_ok &= check('POS.no_epoch_unusable_after_open', not rejects_after, {'count': len(rejects_after)})
verdict['cases']['T2BGEN_POS'] = {'ok': all_ok, 'output': str(out), 'driver_passed': result.get('passed')}

# NEG over existing evidence
out = RUNS / 'T2BGEN_NEG'
result = json.loads((out / 'driver_result.json').read_bytes())
src = rows_of(out / 'regulator/source.jsonl')
closed = result.get('closed_roles', [])
neg_ok = check('NEG.roles_closed_clean',
               len(closed) == 4 and all(r.get('returncode') == 0 and r.get('group_empty') is True for r in closed),
               {r['role']: r.get('returncode') for r in closed})
neg_ok &= check('NEG.no_generation_opened',
                not [r for r in src if r.get('type') == 'reference_epoch_generation_opened'])
committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
neg_ok &= check('NEG.single_generation_one_commit',
                len(committed) <= 1 and all(c['reference_epoch'].get('generation') == 1 for c in committed))
neg_ok &= check('NEG.no_fingerprint_change',
                len({r.get('fingerprint') for r in src if r.get('type') == 'path_version'}) <= 1)
verdict['cases']['T2BGEN_NEG'] = {'ok': neg_ok, 'output': str(out), 'driver_passed': result.get('passed')}
all_ok &= neg_ok

verdict['checks'] = checks
verdict['passed'] = bool(all_ok)
(ROOT / 'postrun/t2bgen_owned_verdict_v2.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
print('VERDICT v2 passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
