#!/usr/bin/env python3
"""Freeze the batch-71 T2 author tree and emit registry/tables/registrations.

Order matters and is asserted: hash the tree -> source bundle; hash the T2
Driver tool; configure with those real identities; build the three compiled
roles; re-hash the tree unchanged; write the registry (recorder stays the
frozen batch-01 binary, acados runtime pins copied from the 66th registry);
write the three frozen action tables and one registration per scenario family.
No run directory is created, no registration is executed."""
import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PKG = HERE.parent
AUTHOR = HERE / 't2_author'
OUT = PKG / 'evidence/freeze_t2'
BUILD = PKG / 'build/freeze_t2/cmake_build'
RUNS = HERE / 'runs'
B66 = PKG.parent / 'scheme_A_W2_owned_takeover_20261023_66'
REG66 = json.loads((B66 / 'implementation/selected_runtime_registry_w2_v1.json').read_bytes())
CONTRACT_V3 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json')
CONTRACT_V4 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json')
TOPICS = Path(json.loads((B66 / 'implementation/W2_registration_v1.json').read_bytes())['topics'])
REGULATOR_SHA = 'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'
TARGETS = ['p1_m4_worker_owned', 'p1_m4_regulator_owned', 'p1_m4_fixture_owned']

SETUP = '''
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
'''


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def tree_manifest(root):
    rows = {}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix == '.pyc':
            continue
        rows[str(p.relative_to(root))] = {'path': str(p), **pin(p)}
    return rows


_sequence = 0


def run_script(body, seconds):
    global _sequence
    prefix = OUT / ('command_%02d' % _sequence)
    _sequence += 1
    script = prefix.with_suffix('.sh')
    with script.open('x') as f:
        f.write(body)
    r = subprocess.run(['/bin/bash', str(script)], capture_output=True, text=True, timeout=seconds)
    prefix.with_suffix('.stdout.txt').write_text(r.stdout)
    prefix.with_suffix('.stderr.txt').write_text(r.stderr)
    prefix.with_suffix('.json').write_text(json.dumps(
        {'argv': ['/bin/bash', str(script)], 'returncode': r.returncode}, indent=2) + '\n')
    return r.returncode, r.stdout + r.stderr


def main():
    OUT.mkdir(parents=True)
    assert (AUTHOR / 't2_scenario_driver_v1.py').is_file() and (AUTHOR / 't2_action_contract.py').is_file()
    before = tree_manifest(AUTHOR)
    assert before['observer/src/shadow/regulator_owned_execute.cpp']['sha256'] == REGULATOR_SHA
    bundle = OUT / 'source_bundle.json'
    bundle_doc = {'schema': 'M4-owned-source-bundle/v1', 'files': before, 'file_count': len(before),
                  'physical_production_release': False, 'scope': 'M4_owned_local_nominal_only_v1'}
    with bundle.open('x') as f:
        f.write(json.dumps(bundle_doc, indent=2, sort_keys=True) + '\n')
    bundle_sha = pin(bundle)['sha256']
    driver = AUTHOR / 't2_scenario_driver_v1.py'
    driver_sha = pin(driver)['sha256']
    configure = SETUP + 'exec cmake -S %s -B %s -DCMAKE_BUILD_TYPE=Release ' \
        "'-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG' -DCMAKE_EXPORT_COMPILE_COMMANDS=ON " \
        '-DP1_OWNED_SOURCE_BUNDLE_SHA256=%s -DP1_DRIVER_TOOL_SHA256=%s ' \
        '-DP1_V4_CONTRACT_FILE=%s -DP1_V3_CONTRACT_FILE=%s\n' % (
            shlex.quote(str(AUTHOR)), shlex.quote(str(BUILD)), bundle_sha, driver_sha,
            shlex.quote(str(CONTRACT_V4)), shlex.quote(str(CONTRACT_V3)))
    rc, log = run_script(configure, 300)
    assert rc == 0, 'configure failed: ' + log[-2000:]
    cache = (BUILD / 'CMakeCache.txt').read_text()
    assert 'CMAKE_HOME_DIRECTORY:INTERNAL=%s' % AUTHOR in cache
    rc, log = run_script(SETUP + 'exec cmake --build %s --target %s -j2\n'
                         % (shlex.quote(str(BUILD)), ' '.join(TARGETS)), 1800)
    assert rc == 0, 'build failed: ' + log[-2000:]
    after = tree_manifest(AUTHOR)
    assert before == after, 'a build step edited the frozen tree'
    roles = {}
    for name, role in (('p1_m4_worker_owned', 'worker'), ('p1_m4_regulator_owned', 'regulator'),
                       ('p1_m4_fixture_owned', 'fixture')):
        binary = BUILD / name
        roles[role] = {'binary': str(binary), 'binary_sha256': pin(binary)['sha256'],
                       'source_bundle': {'path': str(bundle), 'sha256': bundle_sha}}
    roles['recorder'] = REG66['roles']['recorder']
    registry = {'schema': 'M4-owned-runtime-registry/v2', 'scope': 'M4_owned_local_nominal_only_v1',
                'driver': str(driver), 'driver_tool_sha256': driver_sha,
                'regulator_source': str(AUTHOR / 'observer/src/shadow/regulator_owned_execute.cpp'),
                'regulator_source_sha256': REGULATOR_SHA,
                'roles': roles, 'acados_runtime': REG66['acados_runtime']}
    registry_path = HERE / 't2_registry_v1.json'
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')
    audit = AUTHOR / 'audit_t2.py'
    RUNS.mkdir(exist_ok=True)
    tables = HERE / 't2_action_tables'
    tables.mkdir()
    regs = HERE / 't2_registrations'
    regs.mkdir()
    frozen = {}
    families = {
        'T2A-clock-freeze': {
            'actions': [
                {'id': 'a1', 'action': 'clock_hold', 'parameters': {'mode': 'silent', 'duration_ms': 600},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 100}},
                {'id': 'a2', 'action': 'clock_resume', 'parameters': {'advance_ms': 100},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 0}}],
            'clauses': {'receipt_stale_ns': 100000000, 'pause_confirm_ns': 400000000,
                        'same_stamp_keeps_receipt_fresh': True, 'silent_exceeds_receipt_stale': True,
                        'old_candidate_must_not_revive': True, 'resume_requires_new_window': True}},
        'T2B-inflight-clear-replace': {
            'actions': [
                {'id': 'a1', 'action': 'path_replace', 'parameters': {'points': 101, 'speed_m_s': .05},
                 'trigger': {'phase': 'solve_active', 'job_id': 2, 'delay_ms': 0}}],
            'clauses': {'job_deadline_ns_after_origin': 150000000, 'deadline_must_not_extend': True,
                        'missed_window_is_registered_failure': True,
                        'stale_result_reject_reasons': ['version_mismatch', 'job_echo_mismatch'],
                        'expiry_or_worker_terminal_is_not_task_rejection': True}},
        'T2C-driver-shutdown-interleave': {
            'actions': [
                {'id': 'a1', 'action': 'driver_shutdown_request', 'parameters': {'reason': 'T2C registered stimulus'},
                 'trigger': {'phase': 'ready_window', 'job_id': 2, 'delay_ms': 0}}],
            'clauses': {'ordering': 'ready_commit<request<=stopping_observed<=activation_guard',
                        'stop_must_precede_activation_guard': True, 'guard_rejects_target': True,
                        'full_exit_and_storage_required': True}}}
    sys.path.insert(0, str(AUTHOR))
    import t2_action_contract as t2
    for family, spec in families.items():
        tag = family.split('-')[0]
        table_doc = {'schema': 'M4-t2-action-table-v1', 'run_id': 'T2-%s-01' % tag, 'case': family,
                     'contract_sha256': t2.V3_CONTRACT_SHA, **spec}
        t2.validate_table(json.loads(json.dumps(table_doc)),
                          {'run_id': table_doc['run_id'], 'case': family, 'contract_sha256': t2.V3_CONTRACT_SHA})
        table_path = tables / ('%s_v1.json' % tag)
        table_path.write_text(json.dumps(table_doc, indent=2, sort_keys=True) + '\n')
        registration = {'schema': t2.REGISTRATION_SCHEMA, 'scope': t2.ORDINARY_SCOPE, 'case': family,
                        'run_id': table_doc['run_id'],
                        'production_physical_release_enabled': False, 'fault_injection_enabled': False,
                        'domain_id': 120, 'max_seconds': 45, 'automatic_retries': 0,
                        'contract': str(CONTRACT_V3), 'contract_sha256': t2.V3_CONTRACT_SHA,
                        'action_table': str(table_path), 'action_table_sha256': pin(table_path)['sha256'],
                        'registry': str(registry_path), 'registry_sha256': pin(registry_path)['sha256'],
                        'topics': str(TOPICS), 'topics_sha256': pin(TOPICS)['sha256'],
                        'output': str(RUNS / ('%s_01' % tag)),
                        'audit_tool': {'path': str(audit), 'sha256': pin(audit)['sha256']},
                        'executed': False}
        (regs / ('%s_v1.json' % tag)).write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
        frozen[tag] = {'table': str(table_path), 'registration': str(regs / ('%s_v1.json' % tag))}
    report = {'schema': 'M4-T2-freeze-report-v71', 'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'bundle': {'path': str(bundle), 'sha256': bundle_sha, 'files': len(before)},
              'driver_tool_sha256': driver_sha,
              'roles': {role: {'binary': row['binary'], 'sha256': row['binary_sha256']} for role, row in roles.items()},
              'regulator_source_sha256_unchanged': True,
              'tree_unchanged_after_build': True,
              'frozen': frozen,
              'executed_any_registration': False}
    with (OUT / 'freeze_report_v1.json').open('x') as f:
        f.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'bundle_sha256': bundle_sha, 'files': len(before),
                      'roles': {r: v['binary_sha256'][:12] for r, v in roles.items()},
                      'tables': sorted(frozen)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
