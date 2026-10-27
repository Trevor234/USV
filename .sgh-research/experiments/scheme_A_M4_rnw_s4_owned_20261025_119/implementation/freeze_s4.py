#!/usr/bin/env python3
"""Self-contained freeze for batch 119 (S4): bundle -> ELFs -> registry (B2'
fixture variant pin) -> v3 table -> registration -> offline preflight
(driver admission layer + hardened rnw_admission_v2 layer). One finite run
follows; the verdict comes from the S1 pure audit functions."""
import hashlib, json, shlex, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / 'implementation'
TREE = IMPL / 't2_author'
BUILD = ROOT / 'build/cmake'
RUNS = IMPL / 'runs'
OUT = ROOT / 'evidence/freeze'
SETUP_SH = IMPL / 'setup_env.sh'
V3 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
V4 = '/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json'
REG66 = json.loads(Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66/implementation/selected_runtime_registry_w2_v1.json').read_bytes())
TOPICS = '/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/m4_topics_v1.json'
DRIVER = TREE / 't2b_gen_driver_v1.py'
for d in (OUT, RUNS, BUILD):
    d.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(TREE))
sys.path.insert(0, str(IMPL))
import t2b_gen_admission as gen
import rnw_admission_v2 as hard

def pin(p):
    raw = Path(p).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def run(cmd, timeout=300):
    r = subprocess.run(['/bin/bash', str(SETUP_SH), 'bash', '-c', ' '.join(shlex.quote(c) for c in cmd)],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print('STDERR:', r.stderr[-3000:])
        raise AssertionError(f'command failed rc={r.returncode}: {cmd[0]}')
    return r

files = {str(p.relative_to(TREE)): {'path': str(p), **pin(p)}
         for p in sorted(TREE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
bundle = OUT / 'source_bundle.json'
bundle.write_text(json.dumps({'schema': 'S4-B2-owned-source-bundle/v1', 'scope': gen.SCOPE,
    'files': files, 'file_count': len(files), 'physical_production_release': False,
    'basis': {'s0': 'batch 116', 's1': 'batch 117 (18/18)', 's2': 'batch 118 (16/16)',
              'review': 'batch 115'}}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']
driver_sha = pin(DRIVER)['sha256']
regulator_sha = pin(TREE / 'observer/src/shadow/regulator_owned_execute.cpp')['sha256']
assert regulator_sha == gen.REGULATOR_SOURCE_SHA, 'scoped regulator must stay unchanged from the 104-lineage'
fixture_sha = pin(TREE / 'fixture/synthetic_source_m4.cpp')['sha256']
assert fixture_sha == gen.FIXTURE_SOURCE_SHA, 'fixture pin mismatch'
assert pin(TREE / 'worker/solver_worker_m4.cpp')['sha256'] == gen.WORKER_SOURCE_SHA_B91
print(f'bundle={bundle_sha[:16]}... driver={driver_sha[:16]}... fixture={fixture_sha[:16]}...')

run(['cmake', '-S', str(TREE), '-B', str(BUILD), '-DCMAKE_BUILD_TYPE=Release',
     '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG',
     f'-DP1_OWNED_SOURCE_BUNDLE_SHA256={bundle_sha}',
     f'-DP1_DRIVER_TOOL_SHA256={driver_sha}',
     f'-DP1_V4_CONTRACT_FILE={V4}', f'-DP1_V3_CONTRACT_FILE={V3}'], timeout=300)
run(['cmake', '--build', str(BUILD), '--target', 'p1_m4_worker_owned', 'p1_m4_regulator_owned',
     'p1_m4_fixture_owned', '-j2'], timeout=1800)
print('ELFs built')

roles = {}
for name, role in [('p1_m4_worker_owned', 'worker'), ('p1_m4_regulator_owned', 'regulator'),
                   ('p1_m4_fixture_owned', 'fixture')]:
    binary = BUILD / name
    roles[role] = {'binary': str(binary), 'binary_sha256': pin(binary)['sha256'],
                   'source_bundle': {'path': str(bundle), 'sha256': bundle_sha}}
roles['recorder'] = REG66['roles']['recorder']
registry = {'schema': 'M4-owned-runtime-registry/v2', 'scope': gen.SCOPE,
            'driver': str(DRIVER), 'driver_tool_sha256': driver_sha,
            'regulator_source': str(TREE / 'observer/src/shadow/regulator_owned_execute.cpp'),
            'regulator_source_sha256': regulator_sha,
            'worker_source': str(TREE / 'worker/solver_worker_m4.cpp'),
            'worker_source_sha256': gen.WORKER_SOURCE_SHA_B91,
            'fixture_source': str(TREE / 'fixture/synthetic_source_m4.cpp'),
            'fixture_source_sha256': fixture_sha,
            'fixture_variant': 'B2 pairing mapping (batch 118 S2; declared)',
            'roles': roles, 'acados_runtime': REG66['acados_runtime']}
regp = IMPL / 's4_registry.json'
regp.write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')

table = {'schema': gen.TABLE_SCHEMA, 'run_id': 'T3-T2A-RNW3', 'case': 'T2A-gen-resume-new-window',
         'contract_sha256': gen.CONTRACT_SHA,
         'actions': [
            {'id': 'a1', 'action': 'clock_hold', 'parameters': {'mode': 'silent', 'duration_ms': 1200},
             'trigger': {'phase': 'after_grant_ms', 'delay_ms': 1200, 'job_id': 0}},
            {'id': 'a2', 'action': 'clock_resume', 'parameters': {},
             'trigger': {'phase': 'after_grant_ms', 'delay_ms': 2700, 'job_id': 0}},
            {'id': 'a3', 'action': 'driver_shutdown_request', 'parameters': {},
             'trigger': {'phase': 'after_grant_ms', 'delay_ms': 9000, 'job_id': 0}}],
         'clauses': {'resume_requires_new_window': True, 'old_candidate_must_not_revive': True,
                     'pause_confirm_ns': 400000000}}
tp = IMPL / 'T2A_RNW3_table.json'
tp.write_text(json.dumps(table, indent=2, sort_keys=True) + '\n')
ctx = {'run_id': table['run_id'], 'contract_sha256': table['contract_sha256']}
rejections = hard.validate_table(table, ctx)
assert rejections == [], f'hardened admission rejected the legal table: {rejections}'
print('hardened admission PASS')

audit_tool = IMPL / 'rnw_audit_v1.py'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
registration = {'schema': gen.REGISTRATION_SCHEMA, 'scope': gen.SCOPE, 'case': table['case'],
    'run_id': table['run_id'], 'output': str(RUNS / 'T2A_RNW3'),
    'registry': str(regp), 'registry_sha256': pin(regp)['sha256'],
    'contract': V3, 'contract_sha256': gen.CONTRACT_SHA,
    'topics': TOPICS, 'topics_sha256': pin(TOPICS)['sha256'],
    'action_table': str(tp), 'action_table_sha256': pin(tp)['sha256'],
    'audit_tool': {'path': str(audit_tool), 'sha256': pin(audit_tool)['sha256']},
    'max_seconds': 45, 'automatic_retries': 0, 'domain_id': 120,
    'fault_injection_enabled': False, 'executed': False,
    'production_physical_release_enabled': False,
    's4_note': 'B2 single-factor positive per batch 115 S4: pass requires genuine same-Job '
               'post-resume new-generation acceptance with actual output, adjudicated by the '
               'S1 pure audit (rnw_audit_v1); rc0/event-presence/generation-open alone never passes'}
rp = IMPL / 'T2A_RNW3_registration.json'
rp.write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
gen.registration_preflight_t2bgen(json.loads(rp.read_bytes()), DRIVER.resolve(), environment=ENV)
print('offline driver-admission preflight PASS')
