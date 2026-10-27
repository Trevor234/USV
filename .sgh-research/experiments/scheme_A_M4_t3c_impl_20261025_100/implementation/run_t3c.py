#!/usr/bin/env python3
"""Execute the two registered T3-C runs once each (bounded, no retry) and
apply the registered close-boundary verdict checks in postrun.

C12 = T3-C1 + T3-C2 (same run: survivor fixture -> named cleanup_failed +
no-respawn evidence). C3 = negative control (original fixture, healthy close).
Driver exit code is NOT the verdict: C12 fails passed= by design and the T2
receipt-accounting artifact is out of T3-C scope; the verdict is computed
here from driver_result.json + driver_events.jsonl + bounded survivor death.
"""
import json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / 'implementation'
TREE = IMPL / 't2_author'
DRIVER = (TREE / 't3_cleanup_driver_v1.py').resolve()
SETUP = IMPL / 'setup_env.sh'
RUNS = IMPL / 'runs'
POSTRUN = ROOT / 'postrun'
POSTRUN.mkdir(exist_ok=True)

def pin(p):
    return __import__('hashlib').sha256(Path(p).read_bytes()).hexdigest()

def events_of(run_dir):
    out = []
    for line in (run_dir / 'driver_events.jsonl').read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

checks = []
def check(name, ok, detail=None):
    checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + json.dumps(detail)[:220] if detail else ''))
    return ok

def run_case(tag, registration):
    reg = json.loads(Path(registration).read_bytes())
    out = Path(reg['output'])
    if out.exists():
        raise SystemExit(f'{tag}: output exists {out} (single finite execution)')
    begin = time.monotonic()
    proc = subprocess.run(['/bin/bash', str(SETUP), '/usr/bin/python3', '-B', str(DRIVER),
                           '--registration', str(Path(registration).resolve())],
                          capture_output=True, text=True, timeout=int(reg['max_seconds']) + 25,
                          env={**os.environ})
    elapsed = round(time.monotonic() - begin, 3)
    return reg, out, proc, elapsed

def verify(tag, out, proc, elapsed, expect_cleanup_failure):
    result = json.loads((out / 'driver_result.json').read_bytes()) if (out / 'driver_result.json').is_file() else {}
    ev = events_of(out)
    kinds = [e['type'] for e in ev]
    spawns = [e for e in ev if e['type'] == 'role_spawned']
    closed = result.get('closed_roles', [])
    by_role = {r.get('role'): r for r in closed}
    ok = True
    ok &= check(f'{tag}.driver_completed_within_budget', elapsed <= 60 and bool(closed), {'elapsed': elapsed, 'closed': len(closed)})
    ok &= check(f'{tag}.exactly_four_single_spawns', len(spawns) == 4 and len({s['role'] for s in spawns}) == 4,
                {'spawns': [s['role'] for s in spawns]})
    ok &= check(f'{tag}.no_restart_events', not [k for k in kinds if 'restart' in k or 'respawn' in k or 'retry' in k],
                sorted(set(kinds)))
    cleanup = [e for e in ev if e['type'] == 'cleanup_failed']
    if expect_cleanup_failure:
        ok &= check(f'{tag}.cleanup_failed_event_present_for_fixture',
                    len(cleanup) == 1 and cleanup[0].get('role') == 'fixture'
                    and cleanup[0].get('group_empty') is False
                    and cleanup[0].get('check_deadline_ns') == 1000000000
                    and cleanup[0].get('returncode') == 0,
                    cleanup[0] if cleanup else None)
        ok &= check(f'{tag}.cleanup_failed_roles_field', result.get('cleanup_failed_roles') == ['fixture'],
                    result.get('cleanup_failed_roles'))
        ok &= check(f'{tag}.fixture_ladder_int_term_no_kill',
                    [s['signal'] for s in by_role.get('fixture', {}).get('signals', [])] == ['SIGINT', 'SIGTERM'],
                    by_role.get('fixture', {}).get('signals'))
        ok &= check(f'{tag}.other_roles_healthy',
                    all(by_role.get(r, {}).get('returncode') == 0 and by_role.get(r, {}).get('group_empty') is True
                        for r in ('regulator', 'worker', 'recorder')),
                    {r: {'rc': by_role.get(r, {}).get('returncode'), 'empty': by_role.get(r, {}).get('group_empty')}
                     for r in ('regulator', 'worker', 'recorder')})
        # bounded, killable survivor: dies on its own within deadline + margin
        sv_path = out / 'fixture' / 't3_survivor.json'
        sv = json.loads(sv_path.read_bytes()) if sv_path.is_file() else None
        ok &= check(f'{tag}.survivor_recorded', sv is not None and sv.get('policy') == 't3_close_survivor_v1', sv)
        fixture_pgid = json.loads((out / 'fixture' / 'spawn.json').read_bytes())['pid']
        deadline = time.monotonic() + 6.0
        while group_alive(fixture_pgid) and time.monotonic() < deadline:
            time.sleep(0.2)
        ok &= check(f'{tag}.survivor_self_terminated_bounded', not group_alive(fixture_pgid),
                    {'pgid': fixture_pgid, 'waited_s': round(6.0 - (deadline - time.monotonic()), 1)})
        ok &= check(f'{tag}.run_declared_failed', result.get('passed') is False, {'passed': result.get('passed')})
    else:
        ok &= check(f'{tag}.no_cleanup_failed', not cleanup and result.get('cleanup_failed_roles') == [],
                    {'events': cleanup, 'field': result.get('cleanup_failed_roles')})
        ok &= check(f'{tag}.all_roles_healthy_close',
                    len(closed) == 4 and all(r.get('returncode') == 0 and r.get('group_empty') is True for r in closed)
                    and [s['signal'] for s in by_role.get('regulator', {}).get('signals', [])] in ([], ['SIGINT'])
                    and all([s['signal'] for s in by_role.get(r, {}).get('signals', [])] == ['SIGINT']
                            for r in ('fixture', 'worker', 'recorder')),
                    {r: {'rc': by_role.get(r, {}).get('returncode'), 'empty': by_role.get(r, {}).get('group_empty'),
                         'ladder': [s['signal'] for s in by_role.get(r, {}).get('signals', [])]}
                     for r in ('regulator', 'fixture', 'worker', 'recorder')})
    return ok, checks

verdict = {'schema': 'T3-cleanup-run-verdict/v1', 'batch': 100, 'cases': {}, 'passed': False}
all_ok = True
try:
    reg12, out12, proc12, el12 = run_case('C12', IMPL / 'T3C12_registration.json')
    ok12, _ = verify('C12', out12, proc12, el12, expect_cleanup_failure=True)
    verdict['cases']['T3C_C12'] = {'ok': ok12, 'elapsed_seconds': el12, 'driver_rc': proc12.returncode,
                                   'output': str(out12), 'driver_stdout_tail': proc12.stdout[-300:],
                                   'driver_stderr_tail': proc12.stderr[-500:]}
    all_ok &= ok12
    reg3, out3, proc3, el3 = run_case('C3', IMPL / 'T3C3_registration.json')
    ok3, _ = verify('C3', out3, proc3, el3, expect_cleanup_failure=False)
    verdict['cases']['T3C_C3'] = {'ok': ok3, 'elapsed_seconds': el3, 'driver_rc': proc3.returncode,
                                  'output': str(out3), 'driver_stdout_tail': proc3.stdout[-300:],
                                  'driver_stderr_tail': proc3.stderr[-500:]}
    all_ok &= ok3
except Exception as error:
    verdict['error'] = repr(error)
    all_ok = False
verdict['checks'] = checks
verdict['passed'] = bool(all_ok)
(POSTRUN / 't3c_run_verdict_v1.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
print('VERDICT passed=' + str(verdict['passed']))
sys.exit(0 if verdict['passed'] else 2)
