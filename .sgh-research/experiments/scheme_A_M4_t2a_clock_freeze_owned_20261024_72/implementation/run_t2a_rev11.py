#!/usr/bin/env python3
"""T2-A owned execution on freeze rev2 (single run) + audit + family verdicts."""
from pathlib import Path
import datetime
import json
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / 'implementation'
TREE = IMPL / 't2_author_rev8'
DRIVER = TREE / 't2_scenario_driver_v1.py'
REG = IMPL / 'T2A_registration_v11.json'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
SETUP = ('set -e; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; '
         'unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH; '
         'source /opt/ros/jazzy/setup.bash; source /home/trevor/USV/vrx_ws/install/local_setup.bash; '
         'source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash; '
         'export LD_LIBRARY_PATH=/home/trevor/acados/lib:$LD_LIBRARY_PATH; '
         'export ROS_DOMAIN_ID=120 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1; '
         'exec "$@"')
NOW = lambda: datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), 'create-only violated: ' + str(path)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


registration = json.loads(REG.read_bytes())
run_dir = Path(registration['output'])
assert not run_dir.exists(), 'registered output already exists'
evidence = ROOT / 'evidence/owned_run16'
evidence.mkdir()
argv = ['/bin/bash', '-c', SETUP, 'bash', '/usr/bin/python3', '-B', str(DRIVER), '--registration', str(REG)]
create(evidence / '01_driver_argv.json', argv)
with (evidence / '01_driver.stdout').open('xb') as out, (evidence / '01_driver.stderr').open('xb') as err:
    started = time.monotonic()
    proc = subprocess.run(argv, stdout=out, stderr=err, timeout=120)
    elapsed = time.monotonic() - started
driver_result = json.loads((run_dir / 'driver_result.json').read_bytes()) if (run_dir / 'driver_result.json').is_file() else None
create(evidence / 'driver_invocation_v1.json',
       {'schema': 'M4-T2A-owned-invocation-rev2-v72', 'ran_at': NOW(), 'argv': argv,
        'returncode': proc.returncode, 'elapsed_seconds': elapsed,
        'single_execution': True, 'automatic_retries': 0})
print(json.dumps({'returncode': proc.returncode, 'elapsed': round(elapsed, 1),
                  'driver_passed': driver_result and driver_result.get('passed'),
                  'error': driver_result and driver_result.get('error'),
                  'output': str(run_dir)}))
