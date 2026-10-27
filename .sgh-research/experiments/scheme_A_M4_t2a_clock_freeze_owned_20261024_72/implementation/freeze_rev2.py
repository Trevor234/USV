#!/usr/bin/env python3
"""S2 freeze revision 2 (inside batch 72) + T2-A registration v5.

The first real bootstrap (T2A_04) exposed a frozen-driver defect: the T2
Driver passes diagnostic_case as an empty ROS parameter override, which rcl
cannot parse ('-p diagnostic_case:='). The roles' compiled cross-check
(formal_owned_runtime.hpp:140) pins the driver file to the ELF-baked SHA, so
the fix requires a freeze revision: derive t2_author_rev2 (single anchored
one-line fix, driver only), re-bundle, rebuild the three ELFs, re-issue the
registry (v2) and the three registrations (T2A v5 carries the corrected 850ms
resume delay; T2B/T2C v2 are repointed only). Regulator/Worker C++ stay
byte-identical. Offline validation gates everything before any execution."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
IMPL = ROOT / 'implementation'
B71 = BASE / 'scheme_A_M4_t2_action_freeze_20261024_71'
SOURCE_TREE = B71 / 'implementation/t2_author'
TREE = IMPL / 't2_author_rev2'
OUT = ROOT / 'evidence/freeze_rev2'
BUILD = ROOT / 'build/freeze_rev2/cmake_build'
RUNS = IMPL / 'runs'
CONTRACT_V3 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json')
CONTRACT_V4 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json')
REG66 = json.loads((BASE / 'scheme_A_W2_owned_takeover_20261023_66/implementation/selected_runtime_registry_w2_v1.json').read_bytes())
TOPICS = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/m4_topics_v1.json')
DRIVER_ANCHOR_OLD = "'diagnostic_case': ''}"
DRIVER_ANCHOR_NEW = "}"
SETUP = ('set -e; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; '
         'unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH; '
         'source /opt/ros/jazzy/setup.bash; source /home/trevor/USV/vrx_ws/install/local_setup.bash; '
         'source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash; '
         'export LD_LIBRARY_PATH=/home/trevor/acados/lib:$LD_LIBRARY_PATH; exec "$@"')


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def tree_manifest(root):
    return {str(p.relative_to(root)): {'path': str(p), **pin(p)}
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


# ---- 1. derive t2_author_rev2 with the single anchored driver fix ---------------
import shutil
driver = TREE / 't2_scenario_driver_v1.py'
if not TREE.exists():
    shutil.copytree(SOURCE_TREE, TREE)
    text = driver.read_text()
    assert text.count(DRIVER_ANCHOR_OLD) == 1, 'driver fix anchor not unique'
    driver.write_text(text.replace(DRIVER_ANCHOR_OLD, DRIVER_ANCHOR_NEW, 1))
else:
    assert driver.read_text().count(DRIVER_ANCHOR_OLD) == 0, 'existing rev2 tree still carries the defect'
before = tree_manifest(TREE)
assert before['observer/src/shadow/regulator_owned_execute.cpp']['sha256'] == \
    'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'
delta = [k for k in before if pin(SOURCE_TREE / k)['sha256'] != before[k]['sha256']]
assert delta == ['t2_scenario_driver_v1.py'], delta

OUT.mkdir(exist_ok=True)
if not (OUT / 'rev2_derivation_v1.json').exists():
  with (OUT / 'rev2_derivation_v1.json').open('x') as f:
    f.write(json.dumps({'schema': 'M4-T2-freeze-rev2-derivation-v72',
                        'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                        'source_tree': str(SOURCE_TREE), 'target_tree': str(TREE),
                        'delta_files': delta,
                        'fix': 'drop the empty diagnostic_case override; rcl cannot parse -p diagnostic_case:=',
                        'regulator_worker_sources_unchanged': True}, indent=2) + '\n')

# ---- 2. freeze rev2: bundle -> configure/build with real identities -------------
bundle = OUT / 'source_bundle.json'
bundle_doc = {'schema': 'M4-owned-source-bundle/v1', 'files': before, 'file_count': len(before),
              'physical_production_release': False, 'scope': 'M4_owned_local_nominal_only_v1'}
if not bundle.exists():
    with bundle.open('x') as f:
        f.write(json.dumps(bundle_doc, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']
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
assert tree_manifest(TREE) == before, 'a build step edited the rev2 tree'

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
registry_path = IMPL / 't2_registry_v2.json'
registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')

# ---- 3. tables + registrations v2 (T2A v5 timing) --------------------------------
sys.path.insert(0, str(TREE))
import t2_action_contract as t2
from w2_runtime_contract import registration_preflight_t2
RUNS.mkdir(exist_ok=True)
tables_dir = IMPL / 't2_tables_v2'
tables_dir.mkdir(exist_ok=True)
regs_dir = IMPL / 't2_registrations_v2'
regs_dir.mkdir(exist_ok=True)
audit = TREE / 'audit_t2.py'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
issued = {}
for tag in ('T2A', 'T2B', 'T2C'):
    table = json.loads((B71 / ('implementation/t2_action_tables/%s_v1.json' % tag)).read_bytes())
    table['run_id'] = 'T2-%s-05' % tag
    if tag == 'T2A':
        table['actions'][1]['trigger']['delay_ms'] = 850
    t2.validate_table(table, {'run_id': table['run_id'], 'case': table['case'],
                              'contract_sha256': t2.V3_CONTRACT_SHA})
    table_path = tables_dir / ('%s_v2.json' % tag)
    table_path.write_text(json.dumps(table, indent=2, sort_keys=True) + '\n')
    registration = {'schema': t2.REGISTRATION_SCHEMA, 'scope': t2.ORDINARY_SCOPE, 'case': table['case'],
                    'run_id': table['run_id'], 'production_physical_release_enabled': False,
                    'fault_injection_enabled': False, 'domain_id': 120, 'max_seconds': 45,
                    'automatic_retries': 0, 'contract': str(CONTRACT_V3),
                    'contract_sha256': t2.V3_CONTRACT_SHA,
                    'action_table': str(table_path), 'action_table_sha256': pin(table_path)['sha256'],
                    'registry': str(registry_path), 'registry_sha256': pin(registry_path)['sha256'],
                    'topics': str(TOPICS), 'topics_sha256': pin(TOPICS)['sha256'],
                    'output': str(RUNS / ('%s_05' % tag)),
                    'audit_tool': {'path': str(audit), 'sha256': pin(audit)['sha256']},
                    'freeze_revision': 'rev2 (batch 72): driver fix drop empty diagnostic_case; '
                                       'T2A resume delay 850ms; ELFs rebuilt, roles cross-check satisfied',
                    'executed': False}
    (regs_dir / ('%s_v2.json' % tag)).write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
    registration_preflight_t2(registration, driver, environment=ENV)
    issued[tag] = str(regs_dir / ('%s_v2.json' % tag))
if not (OUT / 'freeze_rev2_report_v1.json').exists():
  with (OUT / 'freeze_rev2_report_v1.json').open('x') as f:
    f.write(json.dumps({'schema': 'M4-T2-freeze-rev2-report-v72',
                       'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                       'bundle': {'path': str(bundle), 'sha256': bundle_sha, 'files': len(before)},
                       'driver_tool_sha256': driver_sha, 'delta_files': delta,
                       'roles': {r: v['binary_sha256'] for r, v in roles.items()},
                       'offline_preflight': issued}, indent=2) + '\n')
print(json.dumps({'bundle_sha256': bundle_sha[:16], 'driver': driver_sha[:12],
                  'roles': {r: v['binary_sha256'][:12] for r, v in roles.items()},
                  'registrations': sorted(issued)}))
