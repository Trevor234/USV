#!/usr/bin/env python3
"""Execute the two registered T2B-GEN owned runs once each and apply the
registered verdict checks. Assertions are computed here from primary evidence
(regulator/source.jsonl event stream, driver_result.json, driver_events.jsonl);
the driver's own passed flag is recorded, not trusted."""
import json, os, subprocess, sys, time
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
    out = []
    for line in Path(p).read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

checks = []
def check(name, ok, detail=None):
    checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + json.dumps(detail, default=str)[:220]) if detail else ''))
    return bool(ok)

def execute(tag, registration):
    reg = json.loads(Path(registration).read_bytes())
    out = Path(reg['output'])
    if out.exists():
        raise SystemExit(f'{tag}: output exists {out} (single finite execution)')
    begin = time.monotonic()
    proc = subprocess.run(['/bin/bash', str(SETUP), '/usr/bin/python3', '-B', str(DRIVER),
                           '--registration', str(Path(registration).resolve())],
                          capture_output=True, text=True, timeout=int(reg['max_seconds']) + 25)
    elapsed = round(time.monotonic() - begin, 3)
    return reg, out, proc, elapsed

def close_facts(tag, out, elapsed, proc=None):
    rp = out / 'driver_result.json'
    if not rp.is_file():
        check(f'{tag}.driver_result_written', False,
              {'stdout_tail': (proc.stdout or '')[-400:] if proc else None,
               'stderr_tail': (proc.stderr or '')[-1200:] if proc else None})
        raise SystemExit(f'{tag}: driver produced no result (see check record)')
    result = json.loads(rp.read_bytes())
    ev = rows_of(out / 'driver_events.jsonl')
    closed = result.get('closed_roles', [])
    by_role = {r.get('role'): r for r in closed}
    spawns = [e for e in ev if e['type'] == 'role_spawned']
    ok = check(f'{tag}.driver_completed', bool(closed) and elapsed <= 60, {'elapsed': elapsed, 'closed': len(closed)})
    ok &= check(f'{tag}.exactly_four_single_spawns', len(spawns) == 4 and len({s['role'] for s in spawns}) == 4,
                [s['role'] for s in spawns])
    ok &= check(f'{tag}.no_restart_events',
                not [e['type'] for e in ev if 'restart' in e['type'] or 'respawn' in e['type'] or 'retry' in e['type']])
    ok &= check(f'{tag}.roles_closed_clean',
                len(closed) == 4 and all(r.get('returncode') == 0 and r.get('group_empty') is True for r in closed),
                {r['role']: {'rc': r.get('returncode'), 'empty': r.get('group_empty')} for r in closed})
    return ok, result

def verify_pos(out, result):
    src = rows_of(out / 'regulator/source.jsonl')
    ok = True
    pv = [r for r in src if r.get('type') == 'path_version']
    fingerprints = {r.get('fingerprint') for r in pv}
    ok &= check('POS.path_fingerprint_changed', len(fingerprints) >= 2 and any(r.get('points') == 201 for r in pv),
                {'fingerprints': len(fingerprints), 'points': sorted({r.get('points') for r in pv})})
    versions = [r.get('task_generation') for r in pv]
    ok &= check('POS.task_generation_bumped', len(versions) >= 2 and versions[-1] > versions[0],
                {'generations_seen': versions})
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    ok &= check('POS.single_generation_opened',
                len(opened) == 1 and opened[0].get('generation') == 2
                and opened[0].get('previous_terminal_reason') == 'epoch_binding_changed'
                and opened[0].get('previous_first_job_id', 0) >= 1 and opened[0].get('previous_last_job_id', 0) >= 1,
                opened[0] if opened else None)
    committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
    gens = [c['reference_epoch'].get('generation') for c in committed]
    fps = [c['reference_epoch'].get('path_fingerprint') for c in committed]
    ok &= check('POS.two_epoch_commits_distinct_generations',
                len(committed) == 2 and gens == [1, 2] and fps[0] != fps[1],
                {'generations': gens})
    resubmitted = [r for r in src if r.get('type') == 'job_scoped_generation_resubmit']
    ok &= check('POS.scoped_resubmit_after_open',
                len(resubmitted) >= 1 and all(r.get('generation') == 2 for r in resubmitted),
                {'count': len(resubmitted)})
    prev_last = opened[0].get('previous_last_job_id') if opened else 0
    jobs_after = [r for r in src if r.get('type') == 'job' and isinstance(r.get('job'), dict)
                  and r['job'].get('job_id', 0) > prev_last]
    ok &= check('POS.jobs_submitted_in_generation_2', len(jobs_after) >= 1,
                {'job_ids_after_open': [r['job']['job_id'] for r in jobs_after][:5]})
    rejects_after = [r for r in src if r.get('type') == 'job_not_submitted'
                     and str(r.get('reason', '')).startswith('task_time_reference:')
                     and r.get('processed_ns', 0) > (opened[0].get('opened_ns') if opened else 0)]
    ok &= check('POS.no_epoch_unusable_after_open', not rejects_after, {'count': len(rejects_after)})
    return ok

def verify_neg(out, result):
    src = rows_of(out / 'regulator/source.jsonl')
    ok = True
    opened = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    ok &= check('NEG.no_generation_opened', not opened, {'count': len(opened)})
    committed = [r for r in src if r.get('type') == 'reference_epoch_committed']
    ok &= check('NEG.single_generation_one_commit',
                len(committed) <= 1 and all(c['reference_epoch'].get('generation') == 1 for c in committed),
                {'count': len(committed)})
    pv = [r for r in src if r.get('type') == 'path_version']
    ok &= check('NEG.no_fingerprint_change', len({r.get('fingerprint') for r in pv}) <= 1,
                {'fingerprints': len({r.get('fingerprint') for r in pv})})
    return ok

verdict = {'schema': 'T2B-GEN-owned-run-verdict/v1', 'batch': 104, 'cases': {}, 'passed': False}
all_ok = True
try:
    reg, out, proc, el = execute('POS', IMPL / 'T2BGEN_POS_registration.json')
    okc, result = close_facts('POS', out, el, proc)
    all_ok &= okc and verify_pos(out, result)
    verdict['cases']['T2BGEN_POS'] = {'ok': all_ok, 'elapsed_seconds': el, 'driver_rc': proc.returncode,
                                      'driver_passed': result.get('passed'), 'output': str(out),
                                      'stdout_tail': proc.stdout[-300:], 'stderr_tail': proc.stderr[-600:]}
    reg, out, proc, el = execute('NEG', IMPL / 'T2BGEN_NEG_registration.json')
    okc, result = close_facts('NEG', out, el, proc)
    all_ok &= okc and verify_neg(out, result)
    verdict['cases']['T2BGEN_NEG'] = {'ok': okc, 'elapsed_seconds': el, 'driver_rc': proc.returncode,
                                      'driver_passed': result.get('passed'), 'output': str(out),
                                      'stdout_tail': proc.stdout[-300:], 'stderr_tail': proc.stderr[-600:]}
    verdict['cases']['T2BGEN_POS']['ok'] = all_ok or verdict['cases']['T2BGEN_POS']['ok']
except Exception as error:
    verdict['error'] = repr(error)
    import traceback; verdict['traceback'] = traceback.format_exc()
    all_ok = False
verdict['checks'] = checks
verdict['passed'] = bool(all_ok)
(POSTRUN / 't2bgen_owned_verdict_v1.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
print('VERDICT passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
