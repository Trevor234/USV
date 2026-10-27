#!/usr/bin/env python3
"""S2 freeze revision 3 + T2-A execution (batch 72).

rev2 bootstrap (T2A_05) exposed a Fixture defect: the Driver's atomic publish
writes a '.name.tmp' sidecar before the create-only rename, and the Fixture's
command poll does not skip dot-prefixed temp entries, so one command was
consumed twice and the second pass failed the declared-order check. rev3 adds
the one-line dot-file skip to the Fixture; driver keeps the rev2 fix; the
three ELFs are rebuilt (the compiled cross-checks demand it), registry and
registrations are reissued as v3, and T2-A runs ONCE on the frozen result."""
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
IMPL = ROOT / 'implementation'
SOURCE_TREE = IMPL / 't2_author_rev2'
TREE = IMPL / 't2_author_rev4'
OUT = ROOT / 'evidence/freeze_rev4'
BUILD = ROOT / 'build/freeze_rev4/cmake_build'
RUNS = IMPL / 'runs'
CONTRACT_V3 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json')
CONTRACT_V4 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json')
REG66 = json.loads((BASE / 'scheme_A_W2_owned_takeover_20261023_66/implementation/selected_runtime_registry_w2_v1.json').read_bytes())
TOPICS = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/m4_topics_v1.json')
FIX_OLD = """            if next_action >= len(actions):
                if all(r.get('action_id') in {a['id'] for a in actions} for r in receipts) or shutdown_fired:
                    break
                if time.monotonic() - grant_ns > 20:
                    break
                continue"""
FIX_NEW = """            if next_action >= len(actions):
                if shutdown_fired:
                    break
                if all(r.get('action_id') in {a['id'] for a in actions} for r in receipts):
                    global drain_deadline
                    if drain_deadline is None:
                        drain_deadline = time.monotonic() + 5.0
                    if time.monotonic() >= drain_deadline:
                        break
                    continue
                if time.monotonic() - grant_ns > 20:
                    break
                continue"""
SETUP = ('set -e; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; '
         'unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH; '
         'source /opt/ros/jazzy/setup.bash; source /home/trevor/USV/vrx_ws/install/local_setup.bash; '
         'source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash; '
         'export LD_LIBRARY_PATH=/home/trevor/acados/lib:$LD_LIBRARY_PATH; '
         'export ROS_DOMAIN_ID=120 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1; '
         'exec "$@"')


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def tree_manifest(root):
    return {str(p.relative_to(root)): {'path': str(p), **pin(p)}
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


driver_file = TREE / 't2_scenario_driver_v1.py'
fixture = TREE / 'fixture/synthetic_source_m4.cpp'
if not TREE.exists():
    shutil.copytree(SOURCE_TREE, TREE)
    text = driver_file.read_text()
    assert text.count(FIX_OLD) == 1, 'driver drain anchor not unique'
    driver_file.write_text(text.replace(FIX_OLD, FIX_NEW, 1))
else:
    assert FIX_NEW.splitlines()[1].strip() in driver_file.read_text(), 'existing rev4 tree missing the fix'
before = tree_manifest(TREE)
assert before['observer/src/shadow/regulator_owned_execute.cpp']['sha256'] == \
    'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'
delta = sorted(k for k in before if pin(SOURCE_TREE / k)['sha256'] != before[k]['sha256'])
assert delta == ['t2_scenario_driver_v1.py'], delta
OUT.mkdir(exist_ok=True)
bundle = OUT / 'source_bundle.json'
if not bundle.exists():
    with bundle.open('x') as f:
        f.write(json.dumps({'schema': 'M4-owned-source-bundle/v1', 'files': before,
                            'file_count': len(before), 'physical_production_release': False,
                            'scope': 'M4_owned_local_nominal_only_v1'}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']
driver = TREE / 't2_scenario_driver_v1.py'
driver_sha = pin(driver)['sha256']
rc = subprocess.run(['/bin/bash', '-c', SETUP, 'bash', 'cmake', '-S', str(TREE), '-B', str(BUILD),
                     '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG',
                     '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                     '-DP1_OWNED_SOURCE_BUNDLE_SHA256=' + bundle_sha,
                     '-DP1_DRIVER_TOOL_SHA256=' + driver_sha,
                     '-DP1_V4_CONTRACT_FILE=' + shlex.quote(str(CONTRACT_V4)),
                     '-DP1_V3_CONTRACT_FILE=' + shlex.quote(str(CONTRACT_V3))],
                    capture_output=True, text=True, timeout=300).returncode
assert rc == 0, 'configure failed'
rc = subprocess.run(['/bin/bash', '-c', SETUP, 'bash', 'cmake', '--build', str(BUILD),
                     '--target', 'p1_m4_worker_owned', 'p1_m4_regulator_owned', 'p1_m4_fixture_owned', '-j2'],
                    capture_output=True, text=True, timeout=1800).returncode
assert rc == 0, 'build failed'
assert tree_manifest(TREE) == before, 'a build step edited the rev3 tree'
roles = {}
for name, role in (('p1_m4_worker_owned', 'worker'), ('p1_m4_regulator_owned', 'regulator'),
                   ('p1_m4_fixture_owned', 'fixture')):
    binary = BUILD / name
    roles[role] = {'binary': str(binary), 'binary_sha256': pin(binary)['sha256'],
                   'source_bundle': {'path': str(bundle), 'sha256': bundle_sha}}
roles['recorder'] = REG66['roles']['recorder']
registry = {'schema': 'M4-owned-runtime-registry/v2', 'scope': 'M4_owned_local_nominal_only_v1',
            'driver': str(driver), 'driver_tool_sha256': driver_sha,
            'regulator_source': str(TREE / 'observer/src/shadow/regulator_owned_execute.cpp'),
            'regulator_source_sha256': 'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5',
            'roles': roles, 'acados_runtime': REG66['acados_runtime']}
registry_path = IMPL / 't2_registry_v4.json'
registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')
sys.path.insert(0, str(TREE))
import t2_action_contract as t2
from w2_runtime_contract import registration_preflight_t2
RUNS.mkdir(exist_ok=True)
tables_dir = IMPL / 't2_tables_v4'
tables_dir.mkdir(exist_ok=True)
regs_dir = IMPL / 't2_registrations_v4'
regs_dir.mkdir(exist_ok=True)
audit = TREE / 'audit_t2.py'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
for tag in ('T2A', 'T2B', 'T2C'):
    table = json.loads((IMPL / ('t2_tables_v2/%s_v2.json' % tag)).read_bytes())
    table['run_id'] = 'T2-%s-07' % tag
    t2.validate_table(table, {'run_id': table['run_id'], 'case': table['case'],
                              'contract_sha256': t2.V3_CONTRACT_SHA})
    table_path = tables_dir / ('%s_v4.json' % tag)
    table_path.write_text(json.dumps(table, indent=2, sort_keys=True) + '\n')
    registration = {'schema': t2.REGISTRATION_SCHEMA, 'scope': t2.ORDINARY_SCOPE, 'case': table['case'],
                    'run_id': table['run_id'], 'production_physical_release_enabled': False,
                    'fault_injection_enabled': False, 'domain_id': 120, 'max_seconds': 45,
                    'automatic_retries': 0, 'contract': str(CONTRACT_V3),
                    'contract_sha256': t2.V3_CONTRACT_SHA,
                    'action_table': str(table_path), 'action_table_sha256': pin(table_path)['sha256'],
                    'registry': str(registry_path), 'registry_sha256': pin(registry_path)['sha256'],
                    'topics': str(TOPICS), 'topics_sha256': pin(TOPICS)['sha256'],
                    'output': str(RUNS / ('%s_07' % tag)),
                    'audit_tool': {'path': str(audit), 'sha256': pin(audit)['sha256']},
                    'freeze_revision': 'rev4 (batch 72): after all receipts arrive the Driver drains 5s of healthy '
                                       'business before closing (T2A_06 closed 5ms after resume; the only activation '
                                       'was the stale-clock rejection, so the witness BusinessReady binding and a clean '
                                       'regulator exit never had a chance); ELFs rebuilt',
                    'executed': False}
    (regs_dir / ('%s_v4.json' % tag)).write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
    registration_preflight_t2(registration, driver, environment=ENV)
with (OUT / 'freeze_rev4_report_v1.json').open('x') as f:
    f.write(json.dumps({'schema': 'M4-T2-freeze-rev4-report-v72',
                        'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                        'bundle': {'path': str(bundle), 'sha256': bundle_sha, 'files': len(before)},
                        'driver_tool_sha256': driver_sha, 'delta_vs_rev2': delta,
                        'roles': {r: v['binary_sha256'] for r, v in roles.items()}}, indent=2) + '\n')
print(json.dumps({'bundle_sha256': bundle_sha[:16], 'driver': driver_sha[:12],
                  'roles': {r: v['binary_sha256'][:12] for r, v in roles.items()}}))
