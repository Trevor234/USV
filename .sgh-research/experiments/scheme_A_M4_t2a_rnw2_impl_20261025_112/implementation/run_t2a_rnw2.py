#!/usr/bin/env python3
"""Execute the registered T2A-RNW2 owned run once and apply the batch-111
verdict checks, recomputed here from primary evidence (regulator source
stream, driver_result, driver_events). Driver self-report is recorded, not
trusted. Stream order (single-threaded append) defines 'after the open'."""
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / 'implementation'
TREE = IMPL / 't2_author'
DRIVER = (TREE / 't2b_gen_driver_v1.py').resolve()
SETUP = IMPL / 'setup_env.sh'
RUNS = IMPL / 'runs'
POSTRUN = ROOT / 'postrun'
POSTRUN.mkdir(exist_ok=True)

def rows_of(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]

checks = []
def check(name, ok, detail=None):
    checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + json.dumps(detail, default=str)[:220]) if detail else ''))
    return bool(ok)

reg = json.loads((IMPL / 'T2A_RNW2_registration.json').read_bytes())
out = Path(reg['output'])
if out.exists():
    raise SystemExit(f'output exists {out} (single finite execution)')
begin = time.monotonic()
proc = subprocess.run(['/bin/bash', str(SETUP), '/usr/bin/python3', '-B', str(DRIVER),
                       '--registration', str((IMPL / 'T2A_RNW2_registration.json').resolve())],
                      capture_output=True, text=True, timeout=int(reg['max_seconds']) + 25)
elapsed = round(time.monotonic() - begin, 3)
verdict = {'schema': 'T2A-RNW2-run-verdict/v1', 'batch': 112, 'passed': False,
           'driver_rc': proc.returncode, 'elapsed_seconds': elapsed, 'output': str(out),
           'driver_stdout_tail': proc.stdout[-300:], 'driver_stderr_tail': proc.stderr[-600:]}

ok = True
rp = out / 'driver_result.json'
if not rp.is_file():
    check('driver_result_written', False, {'stderr_tail': proc.stderr[-1200:]})
    verdict['checks'] = checks
    (POSTRUN / 't2a_rnw2_verdict_v1.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
    sys.exit(2)
result = json.loads(rp.read_bytes())
ev = rows_of(out / 'driver_events.jsonl')
src = rows_of(out / 'regulator/source.jsonl')

closed = result.get('closed_roles', [])
by_role = {r.get('role'): r for r in closed}
spawns = [e for e in ev if e['type'] == 'role_spawned']
ok &= check('healthy_close',
            len(closed) == 4 and all(r.get('returncode') == 0 and r.get('group_empty') is True for r in closed),
            {r['role']: {'rc': r.get('returncode'), 'empty': r.get('group_empty')} for r in closed})
ok &= check('exactly_four_single_spawns', len(spawns) == 4 and len({s['role'] for s in spawns}) == 4,
            [s['role'] for s in spawns])
ok &= check('no_restart_events',
            not [e['type'] for e in ev if 'restart' in e['type'] or 'respawn' in e['type'] or 'retry' in e['type']])

committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
gens = [c['reference_epoch'].get('generation') for c in committed]
clock_epochs = [c['reference_epoch'].get('clock_epoch') for c in committed]
ok &= check('two_generations_with_distinct_clock_epoch',
            len(committed) == 2 and gens == [1, 2] and clock_epochs[0] != clock_epochs[1],
            {'generations': gens, 'clock_epochs': clock_epochs})

opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
ok &= check('single_scoped_open_after_pause_terminal',
            len(opened) == 1 and opened[0].get('generation') == 2
            and opened[0].get('previous_terminal_reason') == 'epoch_binding_changed'
            and opened[0].get('previous_first_job_id', 0) >= 1
            and opened[0].get('previous_last_job_id', 0) >= 1,
            {k: opened[0].get(k) for k in ('generation', 'previous_terminal_reason',
                                           'previous_first_job_id', 'previous_last_job_id')} if opened else None)

open_index = src.index(opened[0]) if opened else len(src)
after = src[open_index + 1:]
jobs_after = [r['job']['job_id'] for r in after if r.get('type') == 'job' and isinstance(r.get('job'), dict)]
candidates_after = [r for r in after if r.get('type') == 'candidate_registration']
publications_after = [r for r in after if r.get('type') == 'owned_applied_publication']
ok &= check('resume_new_window_acceptance',
            len(jobs_after) >= 1 and len(candidates_after) >= 1 and len(publications_after) >= 1,
            {'jobs_after_open': jobs_after[:6], 'candidates_after_open': len(candidates_after),
             'publications_after_open': len(publications_after)})

all_jobs = [r['job']['job_id'] for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)]
ok &= check('job_ids_strictly_monotonic', all_jobs == sorted(all_jobs) and len(set(all_jobs)) == len(all_jobs),
            {'count': len(all_jobs)})
terminal_rejects_after = [r for r in after if r.get('type') == 'job_not_submitted'
                          and r.get('policy_reason') == 'epoch_terminal']
ok &= check('no_epoch_terminal_rejection_after_open', not terminal_rejects_after,
            {'count': len(terminal_rejects_after)})
resub = [r for r in after if r.get('type') == 'job_scoped_generation_resubmit']
ok &= check('scoped_resubmit_fired', len(resub) >= 1, {'count': len(resub)})

verdict['checks'] = checks
verdict['passed'] = bool(ok)
verdict['driver_passed'] = result.get('passed')
(POSTRUN / 't2a_rnw2_verdict_v1.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
print('VERDICT passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
