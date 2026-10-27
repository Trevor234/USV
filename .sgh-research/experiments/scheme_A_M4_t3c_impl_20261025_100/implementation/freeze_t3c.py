#!/usr/bin/env python3
"""Self-contained freeze for batch 100 (T3-C family): bundle -> ELFs -> two
registries (C12 survivor fixture / C3 original fixture) -> per-run action
tables -> registrations, plus an offline admission preflight and the static
driver-diff evidence. Registration precedes any run; assertions fixed."""
import difflib, hashlib, json, shlex, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / 'implementation/t2_author'
BUILD = ROOT / 'build/cmake'
RUNS = ROOT / 'implementation/runs'
OUT = ROOT / 'evidence/freeze'
SETUP_SH = ROOT / 'implementation/setup_env.sh'
V3 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
V4 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json'
REG66 = json.loads(Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66/implementation/selected_runtime_registry_w2_v1.json').read_bytes())
TOPICS = '/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/m4_topics_v1.json'
B91_TABLE = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_g4c_fix_20261025_91/implementation/T2C_table.json')
T3_DRIVER = TREE / 't3_cleanup_driver_v1.py'
T2_DRIVER = TREE / 't2_scenario_driver_v1.py'
SURVIVOR_HPP_GUARD = '225e975c56964c609657a433278519ec9903905027627b1231e538c490cf3300'  # regulator source must stay byte-identical

for d in (OUT, RUNS, BUILD):
    d.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(TREE))
import t2_action_contract as t2
from w2_runtime_contract import registration_preflight_t2

def pin(p):
    raw = Path(p).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def run(cmd, timeout=300):
    result = subprocess.run(['/bin/bash', str(SETUP_SH), 'bash', '-c', ' '.join(shlex.quote(c) for c in cmd)],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print('STDERR:', result.stderr[-3000:])
        raise AssertionError(f'command failed rc={result.returncode}: {cmd[0]}')
    return result

# 1. Bundle
files = {str(p.relative_to(TREE)): {'path': str(p), **pin(p)}
         for p in sorted(TREE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
bundle = OUT / 'source_bundle.json'
bundle.write_text(json.dumps({'schema': 'T3-cleanup-source-bundle/v1', 'scope': 'M4_owned_local_nominal_only_v1',
    'files': files, 'file_count': len(files), 'physical_production_release': False}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']
driver_sha = pin(T3_DRIVER)['sha256']
regulator_sha = pin(TREE / 'observer/src/shadow/regulator_owned_execute.cpp')['sha256']
assert regulator_sha == SURVIVOR_HPP_GUARD, 'regulator source changed; T2 admission forbids this'
print(f'bundle={bundle_sha[:16]}... t3_driver={driver_sha[:16]}... files={len(files)}')

# 2. Build (original three roles + T3 survivor fixture variant)
run(['cmake', '-S', str(TREE), '-B', str(BUILD),
     '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG',
     f'-DP1_OWNED_SOURCE_BUNDLE_SHA256={bundle_sha}',
     f'-DP1_DRIVER_TOOL_SHA256={driver_sha}',
     f'-DP1_V4_CONTRACT_FILE={V4}',
     f'-DP1_V3_CONTRACT_FILE={V3}'], timeout=300)
run(['cmake', '--build', str(BUILD), '--target',
     'p1_m4_worker_owned', 'p1_m4_regulator_owned', 'p1_m4_fixture_owned', 'p1_m4_fixture_t3_survivor', '-j2'],
    timeout=1800)
print('ELFs built (4 targets)')

# 3. Static driver-diff evidence: only the two cleanup_failed insertions differ
diff = ''.join(difflib.unified_diff(T2_DRIVER.read_text().splitlines(True), T3_DRIVER.read_text().splitlines(True),
                                    fromfile='t2_scenario_driver_v1.py', tofile='t3_cleanup_driver_v1.py'))
(OUT / 'driver_diff.txt').write_text(diff)
assert 'cleanup_failed' in diff and diff.count('+') >= 2
t2_spawn_lines = [l for l in T2_DRIVER.read_text().splitlines() if 'spawn(' in l and 'def spawn' not in l]
t3_spawn_lines = [l for l in T3_DRIVER.read_text().splitlines() if 'spawn(' in l and 'def spawn' not in l]
assert t2_spawn_lines == t3_spawn_lines, 'spawn call sites changed'
print(f'driver diff recorded ({len(diff.splitlines())} lines); spawn call sites identical ({len(t2_spawn_lines)})')

# 4. Registries: identical except roles.fixture binary
def make_registry(fixture_target):
    roles = {}
    for name, role in [('p1_m4_worker_owned', 'worker'), ('p1_m4_regulator_owned', 'regulator'),
                       (fixture_target, 'fixture')]:
        binary = BUILD / name
        roles[role] = {'binary': str(binary), 'binary_sha256': pin(binary)['sha256'],
                       'source_bundle': {'path': str(bundle), 'sha256': bundle_sha}}
    roles['recorder'] = REG66['roles']['recorder']
    return {'schema': 'M4-owned-runtime-registry/v2', 'scope': 'M4_owned_local_nominal_only_v1',
            'driver': str(T3_DRIVER), 'driver_tool_sha256': driver_sha,
            'regulator_source': str(TREE / 'observer/src/shadow/regulator_owned_execute.cpp'),
            'regulator_source_sha256': regulator_sha,
            'roles': roles, 'acados_runtime': REG66['acados_runtime']}
reg_c12 = make_registry('p1_m4_fixture_t3_survivor')
reg_c3 = make_registry('p1_m4_fixture_owned')
assert reg_c12['roles']['fixture']['binary_sha256'] != reg_c3['roles']['fixture']['binary_sha256']
p_c12 = ROOT / 'implementation/t3c_registry_c12.json'; p_c12.write_text(json.dumps(reg_c12, indent=2, sort_keys=True) + '\n')
p_c3 = ROOT / 'implementation/t3c_registry_c3.json'; p_c3.write_text(json.dumps(reg_c3, indent=2, sort_keys=True) + '\n')

# 5. Per-run action tables (same frozen action; run_id binding changes)
base_table = json.loads(B91_TABLE.read_bytes())
def make_table(run_id):
    table = {k: v for k, v in base_table.items() if k != 'run_id'}
    table['run_id'] = run_id
    return table
tables = {}
for run_id, name in [('T3-T3C-C12', 'T3C_C12_table.json'), ('T3-T3C-C3', 'T3C_C3_table.json')]:
    tp = ROOT / 'implementation' / name
    tp.write_text(json.dumps(make_table(run_id), indent=2, sort_keys=True) + '\n')
    tables[run_id] = tp
    t2.validate_table(json.loads(tp.read_bytes()), {'run_id': run_id, 'case': base_table['case'],
                                                    'contract_sha256': base_table['contract_sha256']})
print('action tables validated')

# 6. Registrations (pre-run)
audit = TREE / 'audit_t2.py'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
def make_registration(run_id, registry_path, table_path, output_name, injection):
    reg = {'schema': 'M4-owned-t2-scenario-run-v1', 'scope': 'M4_owned_local_nominal_only_v1',
           'case': base_table['case'], 'run_id': run_id,
           'output': str(RUNS / output_name),
           'registry': str(registry_path), 'registry_sha256': pin(registry_path)['sha256'],
           'contract': V3, 'contract_sha256': t2.V3_CONTRACT_SHA,
           'topics': TOPICS, 'topics_sha256': pin(TOPICS)['sha256'],
           'action_table': str(table_path), 'action_table_sha256': pin(table_path)['sha256'],
           'audit_tool': {'path': str(audit), 'sha256': pin(audit)['sha256']},
           'max_seconds': 45, 'automatic_retries': 0, 'domain_id': 120,
           'fault_injection_enabled': False, 'executed': False,
           'production_physical_release_enabled': False,
           't3_close_injection': injection}
    return reg
inj_c12 = {'mechanism': 'role_side_survivor', 'role': 'fixture',
           'binary_variant': 'p1_m4_fixture_t3_survivor_owned',
           'survivor_self_deadline_ms': 3000, 'killable': True,
           'no_ptrace_no_sigstop_no_dstate': True,
           'obligation': 'publication_exit.09/.10 (batch 67 register)'}
inj_c3 = {'mechanism': 'none', 'obligation': 'negative control for T3-C1/C2'}
reg12 = make_registration('T3-T3C-C12', p_c12, tables['T3-T3C-C12'], 'T3C_C12', inj_c12)
reg3 = make_registration('T3-T3C-C3', p_c3, tables['T3-T3C-C3'], 'T3C_C3', inj_c3)
rp12 = ROOT / 'implementation/T3C12_registration.json'; rp12.write_text(json.dumps(reg12, indent=2, sort_keys=True) + '\n')
rp3 = ROOT / 'implementation/T3C3_registration.json'; rp3.write_text(json.dumps(reg3, indent=2, sort_keys=True) + '\n')

# 7. Offline admission preflight for both registrations against the T3 driver
for rp in (rp12, rp3):
    registration_preflight_t2(json.loads(rp.read_bytes()), T3_DRIVER.resolve(), environment=ENV)
print('offline preflight PASS for both registrations')
print(f'survivor_fixture={reg_c12["roles"]["fixture"]["binary_sha256"][:16]}... original_fixture={reg_c3["roles"]["fixture"]["binary_sha256"][:16]}...')
