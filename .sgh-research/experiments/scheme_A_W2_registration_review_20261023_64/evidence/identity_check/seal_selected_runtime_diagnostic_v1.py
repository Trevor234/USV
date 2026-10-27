#!/usr/bin/env python3
"""W1 diagnostic registry + registration. Create-only.

This package deliberately does NOT reuse the batch-53 seal: the Regulator and
Fixture sources changed (scope handling), and a new v4 contract and diagnostic
scope exist. The registry therefore records a fresh identity, and the audit
explains exactly which sources differ from the frozen parent.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
A = D / 'author'
BUILD = D / 'build/diagnostic_attempt18'
V4_CONTRACT = D / 'implementation/p1_execution_contract_v4.json'
SCOPE = 'M4_owned_diagnostic_worker_only_v1'
V4_SHA = '3a8451d5172423adbef955d78c8550d67bbeec4582a80bd9ba69028b867b9f06'
EVIDENCE = 'd1a9f0e2b7c4a8536e0f2b9d4c7a1e5836b0d9f2c4a7e1b8369d0c5f2a8e4b71'


def pin(p):
    b = Path(p).read_bytes()
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def emit(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def main():
    manifest = json.loads((BUILD / 'build_manifest_v1.json').read_bytes())
    assert manifest['passed'], 'build did not pass'
    assert len(manifest['targets']) == 7, 'expected seven built targets'

    # The v4 contract must be byte-identical to the one the build was configured
    # with, otherwise the binary and the registration describe different runs.
    assert pin(V4_CONTRACT)['sha256'] == V4_SHA, 'v4 contract bytes changed after the build'

    roles = {}
    for role, target in [('regulator', 'p1_m4_regulator_owned'),
                         ('worker', 'p1_m4_worker_owned'),
                         ('fixture', 'p1_m4_fixture_owned')]:
        row = manifest['targets'][target]
        roles[role] = {'binary': row['path'], 'binary_sha256': row['sha256'],
                       'source_bundle': {'path': manifest['source_bundle']['path'],
                                         'sha256': manifest['source_bundle']['sha256']}}

    # The Recorder is an external prebuilt ELF and is reused unchanged.
    recorder = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
    rec = recorder / 'recorder/build01/p1_owned_recorder'
    rec_bundle = recorder / 'recorder_source_bundle_C3_4_v1.json'
    assert pin(rec)['sha256'] == 'd1b91109081c84d4427510d752e926249a0779c44e84b36509bbfa1dac800002', \
        'Recorder binary changed'
    assert pin(rec_bundle)['sha256'] == '61da30907164a3e55ba3aa41e5609d9b80562982133c52cc6135d8283bb99c08', \
        'Recorder bundle changed'
    roles['recorder'] = {'binary': str(rec), 'binary_sha256': pin(rec)['sha256'],
                         'source_bundle': {'path': str(rec_bundle), 'sha256': pin(rec_bundle)['sha256']}}

    driver = A / 'owned_m4_diagnostic_driver_v1.py'
    assert pin(driver)['sha256'] == manifest['driver_tool_sha256'], \
        'driver changed after the build'

    # Topics come from the contract itself, plus the research/P1 streams.
    c = json.loads(V4_CONTRACT.read_bytes())
    topics = {
        'schema': 'p1-owned-recorder-topics/v1',
        'topics': {
            '/clock': 'rosgraph_msgs/msg/Clock',
            c['input_topics']['odom']: 'nav_msgs/msg/Odometry',
            c['input_topics']['imu']: 'sensor_msgs/msg/Imu',
            c['input_topics']['path']: 'nav_msgs/msg/Path',
            c['input_topics']['profile']: 'std_msgs/msg/Float64MultiArray',
            '/p1/solve_job': 'usv_research_interfaces/msg/SolveJob',
            '/p1/solve_candidate': 'usv_research_interfaces/msg/SolveCandidate',
            '/p1/execution_decision': 'usv_research_interfaces/msg/ExecutionDecision',
            '/p1/worker_capability': 'usv_research_interfaces/msg/WorkerCapability',
            '/research/control/applied': 'usv_research_interfaces/msg/AppliedControl',
            c['output_topics']['left']: 'std_msgs/msg/Float64',
            c['output_topics']['right']: 'std_msgs/msg/Float64',
        },
    }
    emit(D / 'implementation/m4_topics_v1.json', topics)

    registry = {
        'schema': 'M4-owned-diagnostic-registry/v1',
        'scope': SCOPE,
        'driver': str(driver),
        'driver_tool_sha256': pin(driver)['sha256'],
        'regulator_source': str(A / 'observer/src/shadow/regulator_owned_execute.cpp'),
        'regulator_source_sha256': pin(A / 'observer/src/shadow/regulator_owned_execute.cpp')['sha256'],
        'contract_sha256': V4_SHA,
        'evidence_marker': EVIDENCE,
        'roles': roles,
        'production_physical_release_enabled': False,
        'execute_qualified': False,
        'source_scope': ('W1 diagnostic: computation-thread stall only. '
                         'No native C hang, no plant acceptance, no ordinary release.'),
    }
    emit(D / 'implementation/selected_runtime_registry_v1.json', registry)

    topics_sha = pin(D / 'implementation/m4_topics_v1.json')['sha256']
    reg = {
        'schema': 'M4-owned-diagnostic-run-v1',
        'case': 'W1-work-stall-watchdog',
        'scope': SCOPE,
        'domain_id': 120,
        'production_physical_release_enabled': False,
        'fault_injection_enabled': True,
        'registry': str(D / 'implementation/selected_runtime_registry_v1.json'),
        'registry_sha256': pin(D / 'implementation/selected_runtime_registry_v1.json')['sha256'],
        'contract': str(V4_CONTRACT),
        'contract_sha256': V4_SHA,
        'index': str(D / 'implementation/p1_execution_contract_v4.json'),
        'index_sha256': EVIDENCE,
        'topics': str(D / 'implementation/m4_topics_v1.json'),
        'topics_sha256': topics_sha,
        'run_id': 'M4_diagnostic_W1_20261022_05',
        'output': str(D / 'runs/W1_05'),
        'max_seconds': 45,
        'automatic_retries': 0,
        'outer_timeout_seconds': 90,
        'boundary': 'Worker completes one job, then blocks its computation thread for 1700 ms '
                    'pre-native while the executor keeps publishing capability every 200 ms',
        'expected': {
            'transition_reason': 'active_watchdog',
            'capability_lease_stays_valid': True,
            'max_capability_age_while_stalled_ns': 600000000,
            'watchdog_ns': 1000000000,
            'stall_ns': 1700000000,
            'exit_codes': {'regulator': 0, 'worker': 0, 'fixture': 0, 'recorder': 0},
            'signals': {'regulator': [], 'worker': ['SIGINT'],
                        'fixture': ['SIGINT'], 'recorder': ['SIGINT']},
        },
        'declared_exceptions': [],
        'old_normal_or_fault_qualifications_transferred': False,
        'M4_stage_qualified': False,
        'F6_qualified': False,
        'P1_qualified': False,
    }
    emit(D / 'implementation/W1_registration_v1.json', reg)

    w3 = json.loads(json.dumps(reg))
    w3.update({
        'case': 'W3-result-delivery-delay',
        'run_id': 'M4_diagnostic_W3_20261022_05',
        'output': str(D / 'runs/W3_05'),
        'worker_delay_ms': 170,
        'boundary': ('Worker solves normally, then sleeps 170 ms before publishing the '
                     'candidate; solve_start/solve_end are NOT rewritten, so the candidate '
                     'arrives after the 150 ms deadline but inside the same 200 ms tick'),
        'expected': {
            'transition_reason': None,
            'active_watchdog_tripped': False,
            'late_candidates': '>=1',
            'exit_codes': {'regulator': 0, 'worker': 0, 'fixture': 0, 'recorder': 0},
            'signals': {'regulator': [], 'worker': ['SIGINT'],
                        'fixture': ['SIGINT'], 'recorder': ['SIGINT']},
        },
    })
    emit(D / 'implementation/W3_registration_v1.json', w3)

    w4 = json.loads(json.dumps(reg))
    w4.update({
        'case': 'W4-result-delivery-drop',
        'run_id': 'M4_diagnostic_W4_20261022_05',
        'output': str(D / 'runs/W4_05'),
        'drop_after_candidates': 2,
        'boundary': ('The Worker completes native solve, writes the Candidate row, and '
                     'deliberately does not publish it. The Regulator sees no candidate '
                     'for that job target tick, falls back under the frozen hold/ramp '
                     'policy, and the Worker still clears active_job and increments '
                     'completed_jobs before the next job arrives.'),
        'expected': {
            'transition_reason': None,
            'active_watchdog_tripped': False,
            'dropped_candidates': 1,
            'dropped_target_tick_decided_as': 'no_candidate',
            'dropped_candidate_must_not_be_registered': True,
            'fallback_source_must_match_hold_policy': True,
            'business_tick_after_dropped_tick': '>=1',
            'delivery_resumes_after_drop': True,
            'active_job_cleared_before_next_job': True,
            'candidate_accounting': 'generated == published + dropped',
            'exit_codes': {'regulator': 0, 'worker': 0, 'fixture': 0, 'recorder': 0},
            'signals': {'regulator': [], 'worker': ['SIGINT'],
                        'fixture': ['SIGINT'], 'recorder': ['SIGINT']},
        },
    })
    emit(D / 'implementation/W4_registration_v1.json', w4)

    # Source-lock: every tool input this run depends on.
    lock = {}
    for root in ('implementation', 'verification', 'preflight'):
        for f in (D / root).rglob('*'):
            if not f.is_file():
                continue
            # The launch wrapper and the run receipt do not exist until the run
            # itself starts; pinning them here would make the lock self-invalidating.
            if f.name.startswith('launch_registered_'):
                continue
            lock[str(f)] = pin(f)
    for role in roles.values():
        lock[role['binary']] = pin(Path(role['binary']))
        lock[role['source_bundle']['path']] = pin(Path(role['source_bundle']['path']))
    lock[str(driver)] = pin(driver)
    for key, row in manifest['compiler_dependencies'].items():
        lock[key] = row
    emit(D / 'preflight/prerun_source_lock_v1.json', {
        'schema': 'M4-owned-diagnostic-source-lock/v1',
        'files': lock, 'file_count': len(lock),
        'run_registrations': [str(D / 'implementation/W1_registration_v1.json'),
                              str(D / 'implementation/W3_registration_v1.json'),
                              str(D / 'implementation/W4_registration_v1.json')],
        'automatic_retries': 0,
    })

    print(json.dumps({'passed': True, 'roles': list(roles),
                      'locked_paths': len(lock), 'contract_sha256': V4_SHA[:16],
                      'run_registered_not_started': True}))


if __name__ == '__main__':
    main()
