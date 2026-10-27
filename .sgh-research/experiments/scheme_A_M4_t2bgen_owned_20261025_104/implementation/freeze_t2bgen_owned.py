#!/usr/bin/env python3
"""Self-contained freeze for batch 104 (T2B-GEN Stage 2, owned): bundle ->
ELFs -> registry (scoped-wiring pins) -> two action tables -> two
registrations -> offline admission preflight. Static diffs are recorded as
evidence. Registration precedes any run."""
import difflib, hashlib, json, shlex, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / 'implementation/t2_author'
BUILD = ROOT / 'build/cmake'
RUNS = ROOT / 'implementation/runs'
OUT = ROOT / 'evidence/freeze'
SETUP_SH = ROOT / 'implementation/setup_env.sh'
V4 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
V3 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
REG66 = json.loads(Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66/implementation/selected_runtime_registry_w2_v1.json').read_bytes())
TOPICS = '/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/m4_topics_v1.json'
B91_TREE = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_g4c_fix_20261025_91/implementation/t2_author')
DRIVER = TREE / 't2b_gen_driver_v1.py'
T2_DRIVER = TREE / 't2_scenario_driver_v1.py'
REG_SRC = TREE / 'observer/src/shadow/regulator_owned_execute.cpp'

for d in (OUT, RUNS, BUILD):
    d.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(TREE))
import t2b_gen_admission as gen

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
bundle.write_text(json.dumps({'schema': 'T2B-GEN-owned-source-bundle/v1', 'scope': gen.SCOPE,
    'files': files, 'file_count': len(files), 'physical_production_release': False}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']
driver_sha = pin(DRIVER)['sha256']
regulator_sha = pin(REG_SRC)['sha256']
assert regulator_sha == gen.REGULATOR_SOURCE_SHA, 'regulator source moved after admission was written'
worker_sha = pin(TREE / 'worker/solver_worker_m4.cpp')['sha256']
fixture_sha = pin(TREE / 'fixture/synthetic_source_m4.cpp')['sha256']
assert worker_sha == gen.WORKER_SOURCE_SHA_B91 and fixture_sha == gen.FIXTURE_SOURCE_SHA_B91
assert pin(V4)['sha256'] == gen.CONTRACT_SHA
print(f'bundle={bundle_sha[:16]}... gen_driver={driver_sha[:16]}... regulator={regulator_sha[:16]}... files={len(files)}')

# 2. Build
run(['cmake', '-S', str(TREE), '-B', str(BUILD),
     '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG',
     f'-DP1_OWNED_SOURCE_BUNDLE_SHA256={bundle_sha}',
     f'-DP1_DRIVER_TOOL_SHA256={driver_sha}',
     f'-DP1_V4_CONTRACT_FILE={V4}',
     f'-DP1_V3_CONTRACT_FILE={V3}'], timeout=300)
run(['cmake', '--build', str(BUILD), '--target',
     'p1_m4_worker_owned', 'p1_m4_regulator_owned', 'p1_m4_fixture_owned', '-j2'], timeout=1800)
print('ELFs built (3 targets, scoped-wiring regulator)')

# 3. Static diffs as evidence
driver_diff = ''.join(difflib.unified_diff(T2_DRIVER.read_text().splitlines(True), DRIVER.read_text().splitlines(True),
                                           fromfile='t2_scenario_driver_v1.py', tofile='t2b_gen_driver_v1.py'))
(OUT / 'driver_diff.txt').write_text(driver_diff)
assert 't2b_gen_admission' in DRIVER.read_text() and DRIVER.read_text().count('t2gen.') == 2
regulator_diff = ''.join(difflib.unified_diff(
    (B91_TREE / 'observer/src/shadow/regulator_owned_execute.cpp').read_text().splitlines(True),
    REG_SRC.read_text().splitlines(True), fromfile='regulator_owned_execute.cpp@batch91', tofile='regulator_owned_execute.cpp@batch104'))
(OUT / 'regulator_diff.txt').write_text(regulator_diff)
print(f'static diffs recorded (driver {len(driver_diff.splitlines())} lines, regulator {len(regulator_diff.splitlines())} lines)')

# 4. Registry
roles = {}
for name, role in [('p1_m4_worker_owned', 'worker'), ('p1_m4_regulator_owned', 'regulator'),
                   ('p1_m4_fixture_owned', 'fixture')]:
    binary = BUILD / name
    roles[role] = {'binary': str(binary), 'binary_sha256': pin(binary)['sha256'],
                   'source_bundle': {'path': str(bundle), 'sha256': bundle_sha}}
roles['recorder'] = REG66['roles']['recorder']
registry = {'schema': 'M4-owned-runtime-registry/v2', 'scope': gen.SCOPE,
            'driver': str(DRIVER), 'driver_tool_sha256': driver_sha,
            'regulator_source': str(REG_SRC), 'regulator_source_sha256': regulator_sha,
            'worker_source': str(TREE / 'worker/solver_worker_m4.cpp'), 'worker_source_sha256': worker_sha,
            'fixture_source': str(TREE / 'fixture/synthetic_source_m4.cpp'), 'fixture_source_sha256': fixture_sha,
            'roles': roles, 'acados_runtime': REG66['acados_runtime']}
regp = ROOT / 'implementation/t2bgen_registry.json'
regp.write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')

# 5. Action tables
pos_table = {'schema': gen.TABLE_SCHEMA, 'run_id': 'T3-T2BGEN-POS', 'case': 'T2B-gen-positive-control',
    'contract_sha256': gen.CONTRACT_SHA,
    'actions': [{'id': 'a1', 'action': 'path_replace',
                 'parameters': {'points': 201, 'speed_m_s': 0.1},
                 'trigger': {'delay_ms': 0, 'job_id': 2, 'phase': 'job_received'}}],
    'clauses': {'deadline_must_not_extend': True,
                'stale_result_reject_reasons': ['version_mismatch', 'job_echo_mismatch'],
                'old_generation_must_not_revive': True,
                'new_generation_first_job_must_commit': True}}
neg_table = {'schema': gen.TABLE_SCHEMA, 'run_id': 'T3-T2BGEN-NEG', 'case': 'T2B-gen-negative-control',
    'contract_sha256': gen.CONTRACT_SHA,
    'actions': [{'id': 'a1', 'action': 'driver_shutdown_request', 'parameters': {},
                 'trigger': {'delay_ms': 0, 'job_id': 2, 'phase': 'ready_window'}}],
    'clauses': {'no_generation_without_binding_change': True}}
tables = {}
for table, name in ((pos_table, 'T2BGEN_POS_table.json'), (neg_table, 'T2BGEN_NEG_table.json')):
    tp = ROOT / 'implementation' / name
    tp.write_text(json.dumps(table, indent=2, sort_keys=True) + '\n')
    tables[table['run_id']] = tp

# 6. Registrations (pre-run)
audit = TREE / 'audit_t2.py'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
def registration(run_id, table_path, output_name, note):
    return {'schema': gen.REGISTRATION_SCHEMA, 'scope': gen.SCOPE, 'case': json.loads(table_path.read_bytes())['case'],
            'run_id': run_id, 'output': str(RUNS / output_name),
            'registry': str(regp), 'registry_sha256': pin(regp)['sha256'],
            'contract': V4, 'contract_sha256': gen.CONTRACT_SHA,
            'topics': TOPICS, 'topics_sha256': pin(TOPICS)['sha256'],
            'action_table': str(table_path), 'action_table_sha256': pin(table_path)['sha256'],
            'audit_tool': {'path': str(audit), 'sha256': pin(audit)['sha256']},
            'max_seconds': 45, 'automatic_retries': 0, 'domain_id': 120,
            'fault_injection_enabled': False, 'executed': False,
            'production_physical_release_enabled': False,
            't2bgen_note': note}
reg_pos = registration('T3-T2BGEN-POS', tables['T3-T2BGEN-POS'], 'T2BGEN_POS',
    'positive control: path_replace 201pt/0.1 opens generation 2 in the same run')
reg_neg = registration('T3-T2BGEN-NEG', tables['T3-T2BGEN-NEG'], 'T2BGEN_NEG',
    'negative control: no binding change, single generation, healthy close')
p_pos = ROOT / 'implementation/T2BGEN_POS_registration.json'; p_pos.write_text(json.dumps(reg_pos, indent=2, sort_keys=True) + '\n')
p_neg = ROOT / 'implementation/T2BGEN_NEG_registration.json'; p_neg.write_text(json.dumps(reg_neg, indent=2, sort_keys=True) + '\n')

# 7. Offline admission preflight
for rp in (p_pos, p_neg):
    gen.registration_preflight_t2bgen(json.loads(rp.read_bytes()), DRIVER.resolve(), environment=ENV)
print('offline T2B-GEN admission preflight PASS for both registrations')
