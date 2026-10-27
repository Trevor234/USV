#!/usr/bin/env python3
"""One registered attempt, bounded supervision, cleanup of authenticated own roles."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def snapshot(pid):
    p = Path('/proc') / str(pid)
    raw = (p / 'stat').read_text(); fields = raw[raw.rfind(')') + 1:].split()
    return {'start': int(fields[19]), 'pgid': int(fields[2]), 'sid': int(fields[3]),
            'state': fields[0], 'exe_sha256': pin(p / 'exe')['sha256']}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--registration', type=Path, required=True)
    args = parser.parse_args(); reg = json.loads(args.registration.read_text())
    assert reg['automatic_retries'] == 0 and reg['max_seconds'] == 45 and reg['outer_timeout_seconds'] == 90
    assert reg['production_physical_release_enabled'] is False
    assert reg['launch_tool']['sha256'] == pin(__file__)['sha256']
    registry = json.loads(Path(reg['registry']).read_text())
    assert pin(reg['registry'])['sha256'] == reg['registry_sha256']
    assert not Path(reg['output']).exists(), 'Never reuse a run output'
    out = ROOT / 'evidence/owned_launch'; out.mkdir(exist_ok=False)
    receipt = {'schema': 'W2-one-owned-launch-v1', 'registration': str(args.registration.resolve()),
        'registration_sha256': pin(args.registration)['sha256'], 'launch_tool_sha256': pin(__file__)['sha256'],
        'case': reg['case'], 'run_id': reg['run_id'], 'automatic_retries': 0,
        'started_ns': time.monotonic_ns(), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'environment': {k: os.environ.get(k) for k in ['ROS_DOMAIN_ID', 'ROS_LOCALHOST_ONLY', 'RMW_IMPLEMENTATION']}}
    with (out / 'attempt_started.json').open('x') as f: json.dump(receipt, f, indent=2); f.write('\n')
    # -B is part of the existing compiled Driver argv contract; don't insert -u
    # between it and the script. Unbuffered output is set through the environment.
    argv = [sys.executable, '-B', registry['driver'], '--registration', str(args.registration.resolve())]
    env = dict(os.environ); env['PYTHONUNBUFFERED'] = '1'; env['PYTHONDONTWRITEBYTECODE'] = '1'
    env.pop('PYTHONOPTIMIZE', None)
    with (out / 'driver.stdout.log').open('xb') as stdout, (out / 'driver.stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 start_new_session=True, env=env)
        identity = snapshot(child.pid); receipt.update(driver_pid=child.pid, driver_start=identity['start'], argv=argv)
        timeout = False
        try:
            child.wait(timeout=reg['outer_timeout_seconds'])
        except subprocess.TimeoutExpired:
            timeout = True
            for sig, budget in [(signal.SIGINT, 3), (signal.SIGTERM, 2), (signal.SIGKILL, 1)]:
                if child.poll() is not None: break
                actual = snapshot(child.pid)
                assert actual['start'] == identity['start'] and actual['pgid'] == actual['sid'] == child.pid
                os.killpg(child.pid, sig)
                try: child.wait(timeout=budget)
                except subprocess.TimeoutExpired: pass
        receipt.update(returncode=child.poll(), outer_timeout=timeout)
    fallback, groups = [], []
    for role, entry in registry['roles'].items():
        spawn = Path(reg['output']) / role / 'spawn.json'
        if not spawn.is_file(): continue
        own = json.loads(spawn.read_text()); pid = own['pid']
        if Path('/proc/%d' % pid).exists():
            actual = snapshot(pid)
            assert own['boot_id'] == receipt['boot_id'] and actual['start'] == own['process_start_ticks']
            assert actual['pgid'] == actual['sid'] == pid and actual['exe_sha256'] == entry['binary_sha256']
            for sig, budget in [(signal.SIGINT, .5 if role == 'worker' else 2.5),
                                (signal.SIGTERM, 1), (signal.SIGKILL, 1)]:
                if not Path('/proc/%d' % pid).exists(): break
                current = snapshot(pid)
                assert current['start'] == own['process_start_ticks'] and current['pgid'] == pid
                os.killpg(pid, sig); fallback.append({'role': role, 'signal': sig.name})
                until = time.monotonic() + budget
                while Path('/proc/%d' % pid).exists() and time.monotonic() < until: time.sleep(.02)
        try: os.killpg(pid, 0); empty = False
        except ProcessLookupError: empty = True
        groups.append({'role': role, 'pid': pid, 'group_empty_postcheck': empty})
    result_file = Path(reg['output']) / 'driver_result.json'
    result = json.loads(result_file.read_text()) if result_file.is_file() else None
    receipt.update(finished_ns=time.monotonic_ns(), cleanup_fallback=fallback,
                   owned_group_postchecks=groups, driver_result=result,
                   passed=bool(child.returncode == 0 and result and result.get('passed') is True
                               and not timeout and not fallback and all(x['group_empty_postcheck'] for x in groups)),
                   M4_stage_qualified=False, F6_qualified=False, P1_qualified=False)
    with (out / 'launch_receipt_v1.json').open('x') as f: json.dump(receipt, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps({'passed': receipt['passed'], 'driver_returncode': child.returncode,
                      'outer_timeout': timeout, 'receipt': str(out / 'launch_receipt_v1.json')}, ensure_ascii=False))
    return 0 if receipt['passed'] else 2


if __name__ == '__main__': raise SystemExit(main())
