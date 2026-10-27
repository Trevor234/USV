#!/usr/bin/env python3
"""T2-A owned execution (batch 72): corrected v2 registration, ONE finite run.

The 71st-batch T2A v1 table carries a registration-layer timing flaw found by
offline dry-check BEFORE any run (resume delay_ms=0 fires in the same sweep as
the hold, collapsing the 600 ms hold; the audit clause hold_minimum would
fail). v2 corrects only the registration layer (table delays); the frozen
bundle/driver/ELFs/registry from batch 71 are reused byte-identically and
re-asserted. Single execution, automatic retries 0; a failure is preserved,
never retried."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
IMPL = ROOT / 'implementation'
B71 = BASE / 'scheme_A_M4_t2_action_freeze_20261024_71'
AUTHOR = B71 / 'implementation/t2_author'
DRIVER = AUTHOR / 't2_scenario_driver_v1.py'
REGISTRY = B71 / 'implementation/t2_registry_v1.json'
RUNS = B71 / 'implementation/runs'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1',
       'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp', 'PYTHONDONTWRITEBYTECODE': '1'}
NOW = lambda: datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
sys.path.insert(0, str(AUTHOR))
import t2_action_contract as t2  # noqa: E402
from w2_runtime_contract import registration_preflight_t2  # noqa: E402

V1_TABLE = json.loads((B71 / 'implementation/t2_action_tables/T2A_v1.json').read_bytes())


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), 'create-only violated: ' + str(path)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


# ---- 1. freeze-identity re-assertion --------------------------------------------
registry = json.loads(REGISTRY.read_bytes())
freeze = json.loads((B71 / 'evidence/freeze_t2/freeze_report_v1.json').read_bytes())
assert pin(DRIVER)['sha256'] == registry['driver_tool_sha256'], 'frozen driver drifted'
for role in ('worker', 'regulator', 'fixture'):
    assert pin(registry['roles'][role]['binary'])['sha256'] == registry['roles'][role]['binary_sha256'], \
        role + ' frozen ELF drifted'
assert registry['regulator_source_sha256'] == 'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'

# ---- 2. corrected v2 table + registration (registration layer only) -------------
table_v2 = json.loads(json.dumps(V1_TABLE))
table_v2['run_id'] = 'T2-T2A-02'
table_v2['actions'][1]['trigger']['delay_ms'] = 850  # hold fires at grant+100ms; resume at +850ms -> >=750ms hold
t2.validate_table(table_v2, {'run_id': table_v2['run_id'], 'case': table_v2['case'],
                             'contract_sha256': table_v2['contract_sha256']})
table_path = IMPL / 'T2A_table_v2.json'
create(table_path, table_v2)
v1_reg = json.loads((B71 / 'implementation/t2_registrations/T2A_v1.json').read_bytes())
registration = json.loads(json.dumps(v1_reg))
registration['run_id'] = table_v2['run_id']
registration['action_table'] = str(table_path)
registration['action_table_sha256'] = pin(table_path)['sha256']
registration['output'] = str(RUNS / 'T2A_02')
registration['revision'] = 'v2: a2 trigger delay_ms 0->850; offline dry-check of v1 showed the resume firing in the same sweep as the hold, collapsing the registered 600ms hold (no run consumed)'
registration['executed'] = False
reg_path = IMPL / 'T2A_registration_v2.json'
create(reg_path, registration)
config, reg_registry, table = registration_preflight_t2(registration, DRIVER, environment=ENV)
assert table['actions'][1]['trigger']['delay_ms'] == 850

# ---- 3. ONE finite execution -----------------------------------------------------
run_dir = Path(registration['output'])
assert not run_dir.exists(), 'registered output already exists'
evidence = ROOT / 'evidence/owned_run01'
evidence.mkdir()
env = dict(os.environ)
env.update(ENV)
argv = [sys.executable, str(DRIVER), '--registration', str(reg_path)]
create(evidence / '01_driver_argv.json', argv)
with (evidence / '01_driver.stdout').open('xb') as out, (evidence / '01_driver.stderr').open('xb') as err:
    started = time.monotonic()
    proc = subprocess.run(argv, env=env, stdout=out, stderr=err, timeout=120)
    elapsed = time.monotonic() - started
driver_result = json.loads((run_dir / 'driver_result.json').read_bytes()) if (run_dir / 'driver_result.json').is_file() else None
create(evidence / 'driver_invocation_v1.json',
       {'schema': 'M4-T2A-owned-invocation-v72', 'ran_at': NOW(), 'argv': argv,
        'environment': ENV, 'returncode': proc.returncode, 'elapsed_seconds': elapsed,
        'single_execution': True, 'automatic_retries': 0})
print(json.dumps({'returncode': proc.returncode, 'elapsed': round(elapsed, 1),
                  'driver_passed': driver_result and driver_result.get('passed'),
                  'error': driver_result and driver_result.get('error'),
                  'output': str(run_dir)}))
