#!/usr/bin/env python3
"""Assert expected review results; a reproduced defect is never a family pass."""
from pathlib import Path
from collections import Counter
import json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
OUT = ROOT / 'evidence/independent_replay01'
B72 = BASE / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72'


def read(path):
    return json.loads(Path(path).read_bytes())


def create(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


c = read(OUT / 'contract/results.json')
a = read(OUT / 'clock/validator.stdout')
m = read(OUT / 'boundary/measurements.json')
epoch = read(OUT / 'boundary/epoch_probe.stdout')
for part in ['contract', 'clock', 'boundary']:
    replay = read(OUT / part / 'replay_result.json')
    assert all(r['returncode'] == 0 for r in replay['commands'])
    assert replay['owned_started'] is False and replay['ROS_initialized'] is False
assert c['batch70']['strict_baseline_pass'] and c['batch70']['executed_tests'] == 32
assert len(c['batch70']['mutations']) == 3
assert all(r['returncode'] == 1 and r['named_assertions'] for r in c['batch70']['mutations'])
assert c['actual_ready_cache_shape'] == 'command trigger evidence exact fields'
assert all(r['all_boolean_checks_pass'] is True for r in c['t2c_audit_counterexamples'].values())
assert all(r['receipts_complete'] is True for r in c['receipt_counterexamples'].values())
assert all(r['all_audit_booleans'] is True for r in a['in_memory_false_positive_reproductions'].values())
assert all(a['input_identity'].values())
for key in ['API_full_stream', 'typed_Source_Stored']:
    assert a['independent_common_checks'][key]['passed'] is False
    assert a['independent_common_checks'][key]['error_type'] == 'AssertionError'
for key in ['role_source_ELF_identity', 'Source_flush', 'bounded_shutdown',
            'capability_Source_Stored', 'wire_GID_Stored']:
    assert a['independent_common_checks'][key]['passed'] is True
assert a['witness_structural_failure']['observation_complete'] is False
assert a['witness_structural_failure']['records_consistent_false_violation']
assert a['source_counts']['API_sequences'] == list(range(1, 12)) + [13]
assert a['Stored']['Applied_sequences'] == list(range(1, 12)) + [13]
assert a['Stored']['Decision_sequences'] == list(range(1, 14))
cpp = a['frozen_cpp_policy_offline_replay']
assert cpp['all_Source_anchors_reproduced'] and cpp['all_policy_ticks_pass']
assert [r['sequence'] for r in cpp['authority_history_mismatches']] == [12]
assert a['resume_history_authority_failure']['failed_job_id'] == 0
assert m['capability']['type_counts'] == {'capability_publish_attempt': 18, 'capability_publish_result': 18}
assert len(m['job_windows']) == 6
assert epoch['fresh_101']['reason'] == 'static_reference_population'
for name in ['changed_201_after_regulator_invalidation', 'changed_101_after_regulator_invalidation']:
    assert epoch[name]['reason'] == 'epoch_terminal'

# Record the actual nested Worker schema and historical launch/run populations.
worker = [json.loads(s) for s in (B72 / 'implementation/runs/T2A_14/worker/source.jsonl').read_text().splitlines()]
received = [r for r in worker if r.get('type') == 'job_received']
assert len(received) == 6 and all(r.get('job_id') is None for r in received)
assert [r['job']['job_id'] for r in received] == list(range(1, 7))
launches, runs = [], []
for batch in ['scheme_A_M4_t2_action_freeze_20261024_71', B72.name]:
    root = BASE / batch
    for path in sorted((root / 'implementation/runs').glob('*')):
        if not path.is_dir():
            continue
        events = path / 'driver_events.jsonl'
        values = [json.loads(s) for s in events.read_text().splitlines() if s.strip()] if events.exists() else []
        counts = Counter(r.get('type') for r in values)
        runs.append({'path': str(path), 'event_counts': dict(counts),
                     'role_spawned': counts['role_spawned'],
                     'roles': [r.get('role') for r in values if r.get('type') == 'role_spawned']})
    for path in sorted((root / 'evidence').glob('owned_run*')):
        launches.append(str(path))
create(ROOT / 'evidence/launch_population_v1.json', {
    'scope': 'directory/event population only; do not call every wrapper attempt a four-role owned run',
    'historical_launcher_directories': launches, 'historical_run_directories': runs,
    'current_batch_owned_started': 0})

findings = [
    {'id': 'R74-01', 'priority': 1, 'kind': 'runtime_output_accounting',
     'claim': 'T2A_14 seq12 successful per-side API calls are absent from API/Applied ledgers; anchor disagreement requests shutdown',
     'source': 'observer/src/shadow/regulator_owned_execute.cpp', 'lines': [843, 952, 963, 1221, 1224],
     'evidence': 'evidence/independent_replay01/clock/validator.stdout'},
    {'id': 'R74-02', 'priority': 1, 'kind': 'witness_structure',
     'claim': 'pause schedule generation is assigned to an old tick before the next iteration resets tick; same-generation witness tick9->0 fails',
     'source': 'observer/src/shadow/regulator_owned_execute.cpp', 'lines': [1094, 1101, 1104],
     'evidence': 'evidence/independent_replay01/clock/validator.stdout'},
    {'id': 'R74-03', 'priority': 1, 'kind': 'audit_false_accept',
     'claim': 'T2A audit accepts removal of scenario semantics; T2C accepts missing guard and post-request acceptance',
     'source': 'audit_t2.py', 'lines': [58, 75, 105, 113],
     'evidence': 'evidence/independent_replay01/contract/bad_cli.stdout'},
    {'id': 'R74-04', 'priority': 1, 'kind': 'driver_entry_failure',
     'claim': 'B/C trigger evidence lacks phase/source_role; command validation rejects it before execution',
     'source': 't2_scenario_driver_v1.py', 'lines': [308, 315, 328, 332, 365],
     'evidence': 'evidence/independent_replay01/contract/results.json'},
    {'id': 'R74-05', 'priority': 2, 'kind': 'command_receipt_binding',
     'claim': 'receipt verification accepts wrong command SHA, wrong target Job and foreign extra action; Fixture action-order validation differs from Python',
     'source': 't2_action_contract.py', 'lines': [223, 251],
     'fixture_source': 'fixture/synthetic_source_m4.cpp', 'fixture_lines': [133, 143],
     'evidence': 'evidence/independent_replay01/contract/results.json',
     'scope': 'receipt counterexamples executable; Fixture order discrepancy by source inspection'},
    {'id': 'R74-06', 'priority': 2, 'kind': 'measurement_and_inference',
     'claim': '18 snapshots plus 18 result records are not 36 active_job observations; measured windows and scheduling inference need narrower labels',
     'evidence': 'evidence/independent_replay01/boundary/measurements.json'},
    {'id': 'R74-07', 'priority': 2, 'kind': 'epoch_lifecycle',
     'claim': 'after active Epoch binding change, both 101- and 201-point references fail epoch_terminal before population checks',
     'evidence': 'evidence/independent_replay01/boundary/epoch_probe.stdout'},
    {'id': 'R74-08', 'priority': 2, 'kind': 'counter_scope',
     'claim': 'Fixture reports 154 model steps as clock publications although silent suppresses 39; actual transport and Stored both have 115',
     'source': 'fixture/synthetic_source_m4.cpp', 'lines': [82, 235, 240],
     'evidence': 'evidence/independent_replay01/clock/validator.stdout'},
]
create(ROOT / 'postrun/review_findings_v1.json', {
    'schema': 'M4-T2-review-v74', 'findings': findings,
    'review_reproductions_complete': True, 'production_fixes_implemented': False,
    'owned_runs_this_batch': 0,
    'status': {'S1_component_supplement': 'retained_finite_pass',
               'S2_rev8_identity': 'retained_hash_match_implementation_gaps_open',
               'T2A_14_observation': 'partial_valid_trace_runtime_and_audit_failures',
               'T2A_all_clauses_accepted': False,
               'T2B': 'design_and_protocol_repair_required',
               'T2C_rev8_executable': False,
               'M4': False, 'F6': False, 'P1': False, 'plant': False, 'hard_realtime': False},
    'production_B_mode': 'MANUAL+RC override'})
print(json.dumps({'review_reproductions_complete': True, 'findings': len(findings),
                  'production_fixes_implemented': False, 'owned_runs_this_batch': 0}))
