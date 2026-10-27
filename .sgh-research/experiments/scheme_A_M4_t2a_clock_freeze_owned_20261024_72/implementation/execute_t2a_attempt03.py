#!/usr/bin/env python3
"""T2-A attempt02: attempt01 (T2A_02) failed on an unsourced invocation
environment (librcl_yaml_param_parser.so not found, fixture rc 127) — a tool
preparation error, original preserved. This attempt sources the registered
environment and runs the same frozen scenario once (registration v3, output
T2A_03). Still a single execution with automatic retries 0."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
IMPL = ROOT / 'implementation'
B71 = BASE / 'scheme_A_M4_t2_action_freeze_20261024_71'
AUTHOR = B71 / 'implementation/t2_author'
DRIVER = AUTHOR / 't2_scenario_driver_v1.py'
RUNS = B71 / 'implementation/runs'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
SETUP = ('set -e; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; '
         'unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH; '
         'source /opt/ros/jazzy/setup.bash; source /home/trevor/USV/vrx_ws/install/local_setup.bash; '
         'source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash; '
         'export LD_LIBRARY_PATH=/home/trevor/acados/lib:$LD_LIBRARY_PATH; '
         'export ROS_DOMAIN_ID=120 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1; '
         'exec "$@"')
NOW = lambda: datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
sys.path.insert(0, str(AUTHOR))
from w2_runtime_contract import registration_preflight_t2  # noqa: E402


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), 'create-only violated: ' + str(path)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


v2 = json.loads((IMPL / 'T2A_registration_v2.json').read_bytes())
table_v3 = json.loads((B71 / 'implementation/t2_action_tables/T2A_v1.json').read_bytes())
table_v3['run_id'] = 'T2-T2A-03'
table_v3['actions'][1]['trigger']['delay_ms'] = 850
table_path = IMPL / 'T2A_table_v3.json'
if not table_path.is_file():
    create(table_path, table_v3)
registration = json.loads(json.dumps(v2))
registration['run_id'] = 'T2-T2A-03'
registration['action_table'] = str(table_path)
registration['action_table_sha256'] = pin(table_path)['sha256']
registration['output'] = str(RUNS / 'T2A_03')
registration['revision'] = ('v3: identical scenario to v2; attempt01 (T2A_02) failed on an unsourced '
                            'invocation environment (fixture rc 127, librcl_yaml_param_parser.so missing). '
                            'Tool preparation error, original preserved; this attempt sources the registered environment.')
registration['executed'] = False
reg_path = IMPL / 'T2A_registration_v3.json'
assert reg_path.is_file() and json.loads(reg_path.read_bytes())['run_id'] == 'T2-T2A-03', 'v3 registration missing'
registration_preflight_t2(json.loads(reg_path.read_bytes()), DRIVER, environment=ENV)

run_dir = Path(registration['output'])
assert not run_dir.exists(), 'registered output already exists'
evidence = ROOT / 'evidence/owned_run03'
evidence.mkdir()
argv = ['/bin/bash', '-c', SETUP, '/usr/bin/python3', str(DRIVER), '--registration', str(reg_path)]
create(evidence / '01_driver_argv.json', argv)
with (evidence / '01_driver.stdout').open('xb') as out, (evidence / '01_driver.stderr').open('xb') as err:
    started = time.monotonic()
    proc = subprocess.run(argv, stdout=out, stderr=err, timeout=120)
    elapsed = time.monotonic() - started
driver_result = json.loads((run_dir / 'driver_result.json').read_bytes()) if (run_dir / 'driver_result.json').is_file() else None
create(evidence / 'driver_invocation_v1.json',
       {'schema': 'M4-T2A-owned-invocation-v72', 'attempt': 3, 'ran_at': NOW(), 'argv': argv,
        'returncode': proc.returncode, 'elapsed_seconds': elapsed,
        'single_execution': True, 'automatic_retries': 0})
print(json.dumps({'returncode': proc.returncode, 'elapsed': round(elapsed, 1),
                  'driver_passed': driver_result and driver_result.get('passed'),
                  'error': driver_result and driver_result.get('error'),
                  'output': str(run_dir)}))
