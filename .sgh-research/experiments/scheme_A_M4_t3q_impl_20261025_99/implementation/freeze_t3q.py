#!/usr/bin/env python3
"""Self-contained freeze for batch 99 (T3-Q family): bundle -> native ELF -> registry -> registration.

Component-level by design: no ROS context, no ament, no actuator endpoints.
Registration is written BEFORE any case runs; assertion lists are fixed here.
"""
import hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / 'implementation/t2_author'
OUT = ROOT / 'evidence/freeze'
BUILD = ROOT / 'implementation/build_t3q'
TEST_SRC = TREE / 'observer/tests/test_t3_queue_pressure.cpp'
SINK_SRC = TREE / 'observer/src/shadow/p1_diag_sink.hpp'
WITNESS_SRC = TREE / 'observer/src/shadow/p1_witness.hpp'

# Must match the registration-fixed constants compiled into the test binary.
CAPACITY = 512
K = 2048
ATTEMPTS = CAPACITY + K
Q2_THREADS = 4
Q2_M = 768
DELAY_MS = 2
BUDGET_S = 60

OUT.mkdir(parents=True, exist_ok=True)
BUILD.mkdir(parents=True, exist_ok=True)

def pin(p):
    raw = Path(p).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

# 1. Bundle (pins the exact source set the test is compiled against)
files = {str(p.relative_to(TREE)): {'path': str(p), **pin(p)}
         for p in sorted(TREE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
bundle = OUT / 'source_bundle.json'
bundle.write_text(json.dumps({'schema': 'T3-queue-source-bundle/v1', 'scope': 'T3_queue_pressure_component_v1',
    'files': files, 'file_count': len(files), 'physical_production_release': False,
    'ros_context': False}, indent=2, sort_keys=True) + '\n')
bundle_sha = pin(bundle)['sha256']

# 2. Native build (g++ direct; no ROS context by design)
binary = BUILD / 'test_t3_queue_pressure'
cmd = ['g++', '-std=c++17', '-O2', '-DNDEBUG',
       '-I', str(TREE / 'observer/src/shadow'), '-I', str(TREE / 'common'),
       str(TEST_SRC), '-o', str(binary), '-pthread']
build = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
if build.returncode != 0:
    print(build.stderr[-4000:]); raise SystemExit(f'native build failed rc={build.returncode}')
cc = subprocess.run(['g++', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
binary_sha = pin(binary)['sha256']

# 3. Registry
registry = {'schema': 'T3-queue-native-registry/v1', 'scope': 'T3_queue_pressure_component_v1',
    'test_binary': str(binary), 'test_binary_sha256': binary_sha,
    'test_source': str(TEST_SRC), 'test_source_sha256': pin(TEST_SRC)['sha256'],
    'sink_source': str(SINK_SRC), 'sink_source_sha256': pin(SINK_SRC)['sha256'],
    'witness_source': str(WITNESS_SRC), 'witness_source_sha256': pin(WITNESS_SRC)['sha256'],
    'source_bundle': {'path': str(bundle), 'sha256': bundle_sha},
    'compiler': cc, 'ros_context': False, 'physical_production_release': False}
(ROOT / 'implementation/t3q_registry.json').write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')

# 4. Registration (pre-run, fail-closed: assertions fixed)
def qcase(case, stimulus, assertions):
    return {'case_id': case, 'family': 'queue_pressure_component', 'target': 'DiagSink add/loop/close',
            'harness': str(TEST_SRC), 'stimulus': stimulus, 'budget_seconds': BUDGET_S,
            'assertions': assertions, 'result_schema': 'T3-queue-pressure/v1',
            'qualification_flags': {'ROS_context_created': False, 'stage_qualified': False,
                                    'execute_qualified': False, 'research_conclusion': False}}
registration = {
    'schema': 'T3-case-registration/v1', 'batch_registered': 99, 'family_registered': 'T3-Q',
    'obligation_binding': {'register': 'experiments/scheme_A_M4_fixture_gap_20261024_67/postrun/case_applicability_v1.md',
        'row': 'actual_source_recording.03',
        'design': 'experiments/scheme_A_M4_t3_case_design_20261025_98/documents/方案A_第98批_T3场景设计_Sink压力与cleanup失败边界_2026-10-25.md'},
    'tree_base': {'source': str(TREE), 'bundle_sha256': bundle_sha, 'binary_sha256': binary_sha},
    'fixed_parameters': {'capacity': CAPACITY, 'K': K, 'single_producer_attempts': ATTEMPTS,
        'q2_threads': Q2_THREADS, 'q2_attempts_per_thread': Q2_M, 'delay_publish_ms': DELAY_MS,
        'contract_log_capacity_reference': 'common/p1_full_contract.hpp (log_capacity=512)'},
    'cases': [
        qcase('T3-Q1d', {'producer_threads': 1, 'attempts': ATTEMPTS + 1, 'publisher_mode': 'blocking_until_released',
                         'deterministic_seed': 'one event drained and provably blocked before flood'},
              ['terminal_add_rejects_while_full', 'blocked_publisher_delivered_nothing_yet',
               'accepted_capacity_plus_one', 'rejected_equals_K', 'overflow_and_failure_each_once',
               'publisher_delivered_exactly_accepted', 'file_rows_accepted_plus_summary',
               'generated_equals_attempts', 'balance_generated_equals_emitted_plus_dropped',
               'normal_source_complete_false', 'failed_terminal_after_close', 'peak_equals_capacity',
               'snapshot_dropped_matches', 'snapshot_generated_matches']),
        qcase('T3-Q1r', {'producer_threads': 1, 'attempts': ATTEMPTS, 'publisher_mode': 'delay', 'delay_ms': DELAY_MS},
              ['bounded_drain_out_completed', 'attempts_all_accounted', 'generated_equals_attempts',
               'dropped_equals_rejected', 'pressure_actually_applied', 'failed_flag_true',
               'peak_within_capacity', 'queue_overflow_phase_exactly_once',
               'source_failure_phase_exactly_once', 'publisher_delivered_exactly_accepted',
               'file_rows_accepted_plus_summary', 'balance_generated_equals_emitted_plus_dropped',
               'normal_source_complete_false']),
        qcase('T3-Q2', {'producer_threads': Q2_THREADS, 'attempts_per_thread': Q2_M,
                        'publisher_mode': 'delay', 'delay_ms': DELAY_MS},
              ['bounded_drain_out_completed', 'attempts_all_accounted', 'generated_equals_attempts',
               'dropped_equals_rejected', 'pressure_actually_applied', 'failed_flag_true',
               'peak_within_capacity', 'queue_overflow_phase_exactly_once',
               'source_failure_phase_exactly_once', 'publisher_delivered_exactly_accepted',
               'file_rows_accepted_plus_summary', 'balance_generated_equals_emitted_plus_dropped',
               'normal_source_complete_false']),
        qcase('T3-Q3', {'producer_threads': 1, 'attempts': ATTEMPTS, 'publisher_mode': 'delay',
                        'delay_ms': DELAY_MS, 'identity_check': True},
              ['bounded_drain_out_completed', 'attempts_all_accounted', 'generated_equals_attempts',
               'dropped_equals_rejected', 'pressure_actually_applied', 'failed_flag_true',
               'peak_within_capacity', 'queue_overflow_phase_exactly_once',
               'source_failure_phase_exactly_once', 'publisher_delivered_exactly_accepted',
               'file_rows_accepted_plus_summary', 'balance_generated_equals_emitted_plus_dropped',
               'normal_source_complete_false', 'each_accepted_event_exactly_once',
               'sequences_within_registered_ranges']),
        qcase('T3-Q4', {'producer_threads': 1, 'attempts': 100, 'publisher_mode': 'immediate'},
              ['bounded_drain_completed', 'no_pressure_no_rejection', 'failed_flag_false',
               'no_overflow_no_failure_phases', 'normal_source_complete_true', 'dropped_zero',
               'all_emitted', 'generated_equals_attempts']),
    ],
    'governance': {'pre_registration_required': True, 'single_finite_execution': True,
        'auto_retry': 0, 'failure_originals_preserved': True,
        'assertion_change_policy': 'changing any assertion after registration requires a new case_id'},
    'not_claimed': ['four-role Stored reconciliation (publisher seam stands in for delivery observation)',
                    'any stage qualification or research conclusion'],
}
(ROOT / 'implementation/T3Q_registration.json').write_text(json.dumps(registration, indent=2, sort_keys=True) + '\n')
print(f'bundle={bundle_sha[:16]}... binary={binary_sha[:16]}... files={len(files)} cc={cc}')
print('registry + registration written (pre-run)')
