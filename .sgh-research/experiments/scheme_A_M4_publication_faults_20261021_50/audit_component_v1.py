#!/usr/bin/env python3
"""Independently decode received wire and audit exact49 partial/close component facts."""
import copy
import hashlib
import json
from pathlib import Path
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

D = Path(__file__).resolve().parent
ROOT = D / 'verification/component_run01'


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def require(condition, why):
    if not condition:
        raise AssertionError(why)


def load_case(folder):
    return {'case': json.loads((folder / 'case.json').read_bytes()),
            'source': [json.loads(line) for line in (folder / 'source.jsonl').read_text().splitlines()]}


def verify_case(data):
    c = data['case']
    name = c['case']
    require(not c['case_failed'], name + ': GTest failure')
    require(c['exact_production_source_sha256'] == '94bbcb25c356c992111c1779d685bdb3da7dca2f5a0bf301d1f745ea4c2f9bf0', name + ': source')
    require(c['test_only_return_seam'] and c['seeded_owned_readiness_context'] and not c['production_owned_gate_exercised'], name + ': scope')
    require(c['actuator_topic_publishers'] == 0 and not c['observed_DDS_fault_claimed'] and not c['M4_stage_qualified'], name + ': scope promotion')
    source = data['source']
    pairs = [r for r in source if r.get('type') == 'owned_API_pair']
    applied = [r for r in source if r.get('type') == 'owned_applied_publication']
    applied_failed = [r for r in source if r.get('type') == 'owned_applied_publication_failed']
    require(len(pairs) == len(c['steps']) > 0, name + ': pair population')
    summaries = [r for r in source if r.get('type') == 'source_summary']
    require(len(summaries) == 1, name + ': summary population')
    summary = summaries[0]
    require(summary['dropped'] == 0 and summary['normal_source_complete'] and summary['generated'] == summary['emitted'], name + ': unexplained source loss')
    require(not any(r.get('type') == 'owned_pair_policy_failed' for r in source), name + ': policy exception')
    expected_wire = {0: [], 1: [], 2: []}
    control_entries = injected = delegated_control = delegated_applied = 0
    for index, (step, pair) in enumerate(zip(c['steps'], pairs)):
        d, before, after = step['decision'], step['before'], step['after']
        fail = step['injected_sides']
        calls = step['calls']
        require([r['side'] for r in calls] == [0, 1, 2], name + ': both calls/Applied attempted in order')
        require(d['sequence'] == index + 1 == pair['sequence'], name + ': sequence')
        require(pair['command_n'] == d['command'] and pair['starts'] == d['starts'] and pair['ends'] == d['ends'] and pair['returned'] == d['returned'], name + ': Source vs receipt')
        for flag in ['gap_exceeded', 'span_exceeded', 'rate_exceeded', 'bootstrap_late', 'command_invalid']:
            require(not pair[flag], name + ': undeclared ' + flag)
        require(d['ends'][1] - d['starts'][0] <= 5_000_000, name + ': full pair span')
        require(d['starts'][1] >= d['ends'][0], name + ': serial sides')
        require(after['known'] == after['authority_known'] and after['n'] == after['authority_n'] and after['start_ns'] == after['authority_start_ns'] and after['sequence'] == after['authority_sequence'], name + ': authority/history agreement')
        success_sides = 0
        for side, call in enumerate(calls):
            require(call['begin_ns'] <= call['end_ns'], name + ': native entry time')
            require(call['injected'] == fail[side] and call['delegated_to_actual_RCL'] == (not fail[side]), name + ': actual seam/delegation')
            require((call['rc'] == 0) == (not fail[side]), name + ': native return')
            injected += int(fail[side])
            if side < 2:
                control_entries += 1
                delegated_control += int(not fail[side])
                require(call['command'] == d['command'][side], name + ': native command')
                require(d['starts'][side] <= call['begin_ns'] <= call['end_ns'] <= d['ends'][side], name + ': call bounded by production API times')
                require(d['returned'][side] == (not fail[side]), name + ': production return fact')
                require(after['known'][side] == (not fail[side]), name + ': per-side known')
                if fail[side]:
                    require(all(after[key][side] == before[key][side] for key in ['n', 'start_ns', 'sequence']), name + ': failed-side receipt must not advance')
                else:
                    success_sides += 1
                    require(after['n'][side] == d['command'][side] and after['start_ns'][side] == d['starts'][side] and after['sequence'][side] == before['sequence'][side] + 1, name + ': successful-side receipt irreversible')
                    expected_wire[side].append(d['command'][side])
            else:
                delegated_applied += int(not fail[side])
                if not fail[side]:
                    expected_wire[2].append((step, pair))
        require(after['held_history_size'] == before['held_history_size'] + success_sides and after['publication_history_size'] == before['publication_history_size'] + success_sides, name + ': only successful calls append actual command history')
        if fail[0] or fail[1]:
            require(after['authority_terminal'] and not after['normal_complete'] and after['worker_unusable'] and after['stop_requested'] and not after['business_permitted'], name + ': partial must stay terminal/incomplete')
            require(not d['rho_available'] and not pair['rho_available'], name + ': partial rho unavailable')
            require(not after['candidate_present'] and not after['pending_present'], name + ': old candidate/pending survived partial')
        if fail[2]:
            require(not after['normal_complete'] and after['worker_unusable'] and after['stop_requested'], name + ': Applied failure must close normal execution')
        if index == 0:
            require(not any(before['known']) and d['command'] == [0.0, 0.0] and not d['rho_available'] and pair['initial_pair'], name + ': bootstrap facts')
        if before['authority_terminal']:
            require(after['authority_terminal'] and not after['business_permitted'] and not after['normal_complete'], name + ': terminal resurrection')
    require(len(applied) == len(expected_wire[2]), name + ': Source Applied population')
    require(len(applied_failed) == sum(step['injected_sides'][2] for step in c['steps']), name + ': Source Applied-failure population')
    actual_wire = {0: [], 1: [], 2: []}
    for row in c['wire']:
        side = row['side']
        require(side in actual_wire and row['topic'].startswith('/p1_m4_component_'), name + ': non-private topic')
        require(row['type'] == ('std_msgs/msg/Float64' if side < 2 else 'usv_research_interfaces/msg/AppliedControl'), name + ': wire type')
        raw = bytes.fromhex(row['cdr_hex'])
        require(len(raw) == row['bytes'], name + ': actual serialized capture length')
        actual_wire[side].append(deserialize_message(raw, get_message(row['type'])))
    for side in [0, 1]:
        require([m.data for m in actual_wire[side]] == expected_wire[side], name + ': independently received Float64 values/counts')
    require(len(actual_wire[2]) == len(expected_wire[2]), name + ': independently received Applied count')
    for m, (step, pair), source_applied in zip(actual_wire[2], expected_wire[2], applied):
        d, before = step['decision'], step['before']
        require(m.sequence == d['sequence'] == source_applied['sequence'], name + ': Applied sequence')
        require(list(m.final_n) == d['command'] == source_applied['n'], name + ': Applied actual request')
        require([m.left_publish_success, m.right_publish_success] == d['returned'] == source_applied['returned'], name + ': Applied per-side result')
        require([m.left_publish_start_steady_ns, m.right_publish_start_steady_ns] == d['starts'] and [m.left_publish_end_steady_ns, m.right_publish_end_steady_ns] == d['ends'], name + ': Applied actual time')
        require(m.previous_anchor_known == all(before['known']) and list(m.previous_final_n) == before['n'], name + ': Applied previous receipt')
        require(m.config_hash == '19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a' and m.producer_instance_id == source_applied['producer'] and m.baseline_id == source_applied['baseline'], name + ': typed Applied identity/config')
        require(m.event_semantics == 'actual_per_side_API_result', name + ': event semantics')
        require(m.publish_error == ('' if all(d['returned']) else 'partial_or_failed_API'), name + ': partial error label')
        require(not m.plant_acceptance_observed and not m.force_measured and not m.execution_atomicity_proven, name + ': plant/atomicity promotion')
    shutdown = [r for r in source if r.get('type') == 'regulator_shutdown']
    shutdown_expected = name.startswith('Shutdown') and 'Before' not in name
    require(len(shutdown) == int(shutdown_expected), name + ': exit population')
    if shutdown:
        row = shutdown[0]
        last = c['steps'][-1]['decision']
        zero = all(abs(v) < 1e-9 for v in last['command'])
        require(row['zero_requested'] == zero and row['zero_target_published'] == (zero and all(last['returned'])), name + ': requested zero vs actual dual success')
        require(row['shutdown_grace_exceeded'] == (not zero) and not row['plant_hold_end_known'], name + ': grace/plant facts')
        require(c['extra']['finish_exit_tick'], name + ': actual finish_tick result')
    if 'Grace' in name:
        delta = c['extra']['finish_now_ns'] - c['extra']['stop_start_ns']
        require(c['extra']['seeded_grace_time_boundary'] and delta == (2_500_000_000 - (1 if 'Before' in name else 0)), name + ': exact seeded grace boundary')
    if name.startswith('Clear'):
        require(c['extra']['real_clear_called'] and c['extra']['cleared_pending_target'] == 1, name + ': clear')
    return {'case': name, 'steps': len(c['steps']), 'actual_private_control_rcl_entries': control_entries,
            'delegated_control_calls': delegated_control, 'delegated_Applied_calls': delegated_applied,
            'injected_return_errors': injected, 'independently_decoded_wire_messages': len(c['wire']),
            'source_complete': True, 'component_passed': True, 'M4_stage_qualified': False}


def main():
    registration = json.loads((D / 'preflight/component_registration_v1.json').read_bytes())
    verification = json.loads((D / 'verification/component_verification_v1.json').read_bytes())
    require(verification['passed'], 'component verification failed')
    paths = [Path(__file__).resolve(), D / 'preflight/component_registration_v1.json',
             D / 'verification/component_verification_v1.json', ROOT / 'gtest.xml']
    paths += sorted((ROOT / 'cases').glob('*/case.json')) + sorted((ROOT / 'cases').glob('*/source.jsonl'))
    before = {str(p): pin(p) for p in paths}
    results = []
    for name in registration['cases']:
        results.append(verify_case(load_case(ROOT / 'cases' / name)))
    parent = load_case(ROOT / 'cases/AcceptedLeftFailureClearsCandidateAndPending')
    negatives = []
    mutations = {
        'successful_side_not_delegated': lambda d: d['case']['steps'][-1]['calls'][1].update(delegated_to_actual_RCL=False),
        'partial_falsely_normal_complete': lambda d: d['case']['steps'][-1]['after'].update(normal_complete=True),
        'successful_anchor_rolled_back': lambda d: d['case']['steps'][-1]['after']['sequence'].__setitem__(1, 0),
        'actual_wire_message_missing': lambda d: d['case']['wire'].pop(),
    }
    for name, mutate in mutations.items():
        altered = copy.deepcopy(parent)
        mutate(altered)
        try:
            verify_case(altered)
        except AssertionError as e:
            negatives.append({'case': name, 'rejected': True, 'reason': str(e)})
        else:
            raise AssertionError('checker accepted mutation: ' + name)
    after = {str(p): pin(p) for p in paths}
    require(before == after, 'audit inputs changed')
    out = {'schema': 'M4-publication-fault-independent-wire-source-audit/v1', 'passed': True,
           'source_linked_publication_exit_component_passed': True, 'cases': results,
           'totals': {key: sum(row[key] for row in results) for key in ['steps', 'actual_private_control_rcl_entries', 'delegated_control_calls', 'delegated_Applied_calls', 'injected_return_errors', 'independently_decoded_wire_messages']},
           'checker_mutation_rejections': negatives, 'input_before': before, 'input_after': after,
           'SDK_deserializer_without_ROS_init': True, 'actual_M4_four_role_fault_runs': 0,
           'production_Regulator_source_modified': False, 'actuator_topic_publishers': 0,
           'ordinary_production_release_enabled': False, 'publication_exit_whole_group_qualified': False,
           'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False, 'research_conclusion': False}
    with (D / 'postrun/publication_fault_audit_v1.json').open('x') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({'passed': True, 'cases': len(results), 'totals': out['totals'], 'checker_mutation_rejections': len(negatives)}))


if __name__ == '__main__':
    main()
