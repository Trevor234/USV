#!/usr/bin/env python3
"""Run one predeclared, locked localhost diagnostic. The driver owns all children."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', choices=['lease','active'], required=True)
    args = ap.parse_args()
    plan = json.loads((D / 'preflight/V2_preregistration_r3_v1.json').read_bytes())
    environment = json.loads((D / 'preflight/loader_environment_v2.json').read_bytes())
    assert environment['passed'] and plan['runner_sha256'] == pin(__file__)['sha256']
    assert plan['loader_environment_sha256'] == pin(D / 'preflight/loader_environment_v2.json')['sha256']
    lock = json.loads((D / 'preflight/prerun_source_lock_r3_v1.json').read_bytes())
    assert plan['verdict'] == 'GO' and plan['source_lock_sha256'] == pin(D / 'preflight/prerun_source_lock_r3_v1.json')['sha256']
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == plan['boot_id']
    for path, expected in lock['files'].items():
        assert pin(path) == expected, 'selected source/input changed: ' + path
    selected = next(r for r in plan['runs'] if r['case'] == args.case)
    run_id = selected['run_id']
    assert not (D / 'author_r3/runs' / run_id).exists(), 'never reuse a run directory'
    argv = ['/usr/bin/python3', str(D / 'author_r3/prepare_pair_wakeup_v1.py'), '--run-id', run_id,
            '--reference-speed', '0.05', '--controlled-case', 'C', '--domain', '196', '--v2-case', args.case,'--close-profile','worker-terminal-reception-v1']
    import importlib.util
    setup_file = D / 'author/build_c33_v9.py'
    spec = importlib.util.spec_from_file_location('pinned_complete_runtime_setup', setup_file)
    setup_module = importlib.util.module_from_spec(spec);spec.loader.exec_module(setup_module)
    setup = setup_module.SETUP
    assert hashlib.sha256(setup.encode()).hexdigest() == environment['complete_setup_sha256']
    command = setup + 'export PYTHONDONTWRITEBYTECODE=1 ROS_DOMAIN_ID=196 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n'
    command += 'exec timeout --signal=INT --kill-after=20s 55s ' + shlex.join(argv)
    started = time.monotonic_ns()
    with (D / 'evidence' / (run_id + '_driver.log')).open('xb') as log:
        rc = subprocess.run(['bash', '-c', command], stdout=log, stderr=subprocess.STDOUT, timeout=80).returncode
    finished = time.monotonic_ns()
    for path, expected in lock['files'].items():
        assert pin(path) == expected, 'selected source/input changed during run: ' + path
    report = {'run_id': run_id, 'case': args.case, 'returncode': rc, 'started_ns': started, 'finished_ns': finished,
              'elapsed_ns': finished-started, 'external_timeout_triggered': rc in [124, 137],
              'source_lock_sha256':plan['source_lock_sha256'],'launcher_sha256':pin(__file__)['sha256'],'complete_setup_sha256':environment['complete_setup_sha256'],'inputs_unchanged': True, 'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}
    with (D / 'postrun' / (run_id + '_launch_v1.json')).open('x') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
