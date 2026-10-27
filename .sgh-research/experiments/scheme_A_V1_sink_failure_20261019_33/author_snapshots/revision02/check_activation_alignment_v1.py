"""Actual received sensors -> bounded causal frame -> original state gate.

Source observations authenticate the author's capture/guard reads. This does
not claim external observation of mutex mutation order, WCET or plant response.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import activation_alignment_audit_v1 as independent


def near(a, b, tolerance=1e-9):
    return (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b)
            and all(type(x) in (int, float) and math.isfinite(x) and abs(x-y) <= tolerance for x, y in zip(a, b)))


def selection_valid(attempt, frames, target, contract):
    raw = dict(attempt['raw_snapshot'], sample_ns=attempt['sample_ns'])
    selected, scanned = independent.select_frame(frames, raw, target, contract, attempt['history_generation'])
    return (attempt['frame_count'] == len(frames) <= 32 and attempt['selected_frame'] == selected
            and attempt['frames_scanned'] == scanned), selected, raw


def guard_reads_valid(attempt):
    reads = attempt['input_gate_reads']
    expected = dict(input_version_equal=None, input_odom_equal=None, input_imu_equal=None)
    result = None
    if attempt['input_change_gate_ran']:
        raw, current = attempt['raw_snapshot'], attempt['guard_snapshot']
        expected['input_version_equal'] = raw['version'] == current['version']
        result = expected['input_version_equal']
        if result:
            expected['input_odom_equal'] = raw['odom_sequence'] == current['odom_sequence']
            result = expected['input_odom_equal']
        if result:
            expected['input_imu_equal'] = raw['imu_sequence'] == current['imu_sequence']
            result = expected['input_imu_equal']
    return all(reads[k] is v for k, v in expected.items()) and attempt['input_change_gate_unchanged'] is result


def materialization_valid(trace, decision):
    keys=['decision_commit_ns','observer_publish_return_ns','materialized_start_ns','materialized_end_ns']
    return (trace.get('observation_policy')=='bounded_values_then_JSON_after_observer_publish_return_v1'
            and all(type(trace.get(k)) is int and trace[k]>0 for k in keys)
            and trace['decision_commit_ns']==decision['activation_commit_ns']
            and trace['decision_commit_ns']<=trace['observer_publish_return_ns']<=decision['end_ns']
            <=trace['materialized_start_ns']<=trace['materialized_end_ns'])


def analyze(run, observer, contract, decoded, c):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message
    from check_owned_fixture import plain
    c.need(contract['diagnostic_contract_revision'] == 10 and contract['activation_state_policy'] == independent.POLICY
           and type(contract['activation_sensor_history_capacity']) is int and contract['activation_sensor_history_capacity'] == 32
           and type(contract['activation_validation_attempts']) is int and contract['activation_validation_attempts'] == 2,
           'alignment_exact_authenticated_policy_and_bounds')
    sensors = [r for r in observer if r.get('type') in ['odom_admission', 'imu_admission']]
    topics = dict(odom_admission='/wamv/sensors/position/ground_truth_odometry', imu_admission='/wamv/sensors/imu/imu/data')
    canonical = lambda m: json.dumps(m, sort_keys=True, separators=(',', ':'), allow_nan=False)
    stored = {topic: Counter(canonical(r['message']) for r in decoded[topic]) for topic in topics.values()}
    manifest = json.loads((Path(run) / 'synthetic_source/owned_manifest.json').read_text())
    gids = {e['topic']: e['gid'] for e in manifest['endpoints'] if e['kind'] == 'publisher'}
    classes = {topic: get_message('nav_msgs/msg/Odometry' if 'odometry' in topic else 'sensor_msgs/msg/Imu') for topic in topics.values()}
    for row in sensors:
        raw = row['raw_input']; blob = bytes.fromhex(raw['cdr_hex']); topic = topics[row['type']]
        c.need(len(blob) == raw['cdr_bytes'] and hashlib.sha256(blob).hexdigest() == raw['cdr_sha256']
               and raw['publisher_gid'] == gids[topic] and raw['topic'] == topic,
               'alignment_sensor_actual_full_CDR_and_owned_GID', ordinal=row['input_commit_ordinal'])
        message = plain(dict(message_to_ordereddict(deserialize_message(blob, classes[topic]))))
        key = canonical(message)
        c.need(stored[topic][key] > 0, 'alignment_received_sensor_typed_Storage_subset', ordinal=row['input_commit_ordinal'])
        stored[topic][key] -= 1
        ns = message['header']['stamp']['sec'] * 1_000_000_000 + message['header']['stamp']['nanosec']
        c.need(ns == row['stamp_ns'], 'alignment_sensor_stamp_exact')
        if row['valid'] and row['type'] == 'odom_admission':
            pose, twist = message['pose']['pose'], message['twist']['twist']; q = pose['orientation']
            norm = sum(q[k] ** 2 for k in ['x', 'y', 'z', 'w'])
            yaw = math.atan2(2 * (q['w']*q['z']+q['x']*q['y']) / norm, 1-2*(q['y']**2+q['z']**2) / norm)
            state = [pose['position']['x'], pose['position']['y'], yaw, twist['linear']['x'], twist['linear']['y'], twist['angular']['z']]
            c.need(message['header']['frame_id'] == contract['expected_pose_frame']
                   and message['child_frame_id'] == contract['expected_child_frame'] and near(row['state'], state, 1e-12),
                   'alignment_admitted_Odom_state_from_received_CDR')
        if row['valid'] and row['type'] == 'imu_admission':
            c.need(message['header']['frame_id'] == contract['expected_imu_frame']
                   and row['r_value'] == message['angular_velocity']['z'], 'alignment_admitted_IMU_from_received_CDR')

    prefixes = independent.reconstruct_frame_prefixes(observer)
    frames = []; generation = 1
    for row in observer:
        if row.get('type') == 'activation_sensor_history_reset':
            c.need(row['history_generation'] == generation + 1, 'alignment_history_reset_monotonic')
            generation = row['history_generation']
        if row.get('type') not in topics:
            continue
        gen, prefix = prefixes[row['input_commit_ordinal']]
        expected = prefix[-1] if prefix and prefix[-1]['input_commit_ordinal'] == row['input_commit_ordinal'] else None
        c.need(row.get('activation_sensor_frame') == expected, 'alignment_actual_callback_composite_frame', ordinal=row['input_commit_ordinal'])
        if expected is not None:
            frames.append(expected)
    jobs = {r['job']['job_id']: r['job'] for r in observer if r.get('type') == 'job'}
    odom = {r['accepted_sequence']: r for r in sensors if r['valid'] and r['type'] == 'odom_admission'}
    imu = {r['accepted_sequence']: r for r in sensors if r['valid'] and r['type'] == 'imu_admission'}
    proofs = []; total_retries = older = maximum_scan = 0
    for d in [r for r in observer if r.get('type') == 'decision']:
        observation = d['d0_observation']; evidence = observation['activation_alignment']; attempts = evidence['attempts']
        c.need(materialization_valid(evidence,d),'deferred_JSON_after_actual_commit_and_observer_publish_return',decision=d['sequence'])
        c.need(evidence['policy'] == independent.POLICY and evidence['capacity'] == 32 and evidence['maximum_attempts'] == 2
               and 1 <= len(attempts) <= 2, 'alignment_actual_bounded_attempt_population', decision=d['sequence'])
        selected = None; last_raw = None; predicted = None
        for number, attempt in enumerate(attempts, 1):
            raw = dict(attempt['raw_snapshot'], sample_ns=attempt['sample_ns'])
            c.need(attempt['attempt'] == number and attempt['sample_ns'] <= attempt['copy_capture_ns'] <= attempt['commit_check_ns'] <= d['activation_commit_ns'],
                   'alignment_actual_capture_guard_order', decision=d['sequence'], attempt=number)
            c.need(guard_reads_valid(attempt), 'alignment_original_version_Odom_IMU_short_circuit_guards', decision=d['sequence'], attempt=number)
            # Check raw capture keeps the latest actual valid callback identities.
            os = [r for r in odom.values() if r['input_commit_ordinal'] <= raw['input_commit_ordinal']]
            ims = [r for r in imu.values() if r['input_commit_ordinal'] <= raw['input_commit_ordinal']]
            o = max(os, key=lambda r: r['input_commit_ordinal']) if os else None
            i = max(ims, key=lambda r: r['input_commit_ordinal']) if ims else None
            mixed = bool(i and (not o or i['input_commit_ordinal'] > o['input_commit_ordinal']))
            state = list(o['state']) if o else [0.] * 6
            if mixed: state[5] = i['r_value']
            c.need(raw['odom_sequence'] == (o['accepted_sequence'] if o else 0)
                   and raw['imu_sequence'] == (i['accepted_sequence'] if i else 0)
                   and raw['r_from_imu'] is mixed and near(raw['state'], state, 1e-12),
                   'alignment_raw_capture_preserves_latest_callback_state', decision=d['sequence'], attempt=number)
            if d['job_id']:
                eligible = [f for f in frames if f['history_generation'] == attempt['history_generation']
                            and f['input_commit_ordinal'] <= raw['input_commit_ordinal']][-32:]
                valid, selected, selected_raw = selection_valid(attempt, eligible, jobs[d['job_id']]['target_sim_ns'], contract)
                c.need(valid, 'alignment_independent_latest_causal_eligible_frame', decision=d['sequence'], attempt=number)
                maximum_scan = max(maximum_scan, attempt['frames_scanned'])
                if selected:
                    predicted = independent.propagate_frame(selected, selected_raw, jobs[d['job_id']]['target_sim_ns'], contract['hydro'])
            else:
                c.need(attempt['selected_frame'] is None and attempt['frames_scanned'] == 0, 'alignment_non_candidate_no_prediction')
            if attempt['retry']:
                total_retries += 1
                c.need(number == 1 and len(attempts) == 2 and attempt['reason'] == 'activation_input_changed_during_validation'
                       and attempt['input_change_gate_ran'] is True and attempt['input_change_gate_unchanged'] is False
                       and attempt['commit_check_ns'] - d['planned_ns'] <= contract['tick_jitter_ns'],
                       'alignment_one_retry_only_for_actual_input_race')
            else:
                c.need(number == len(attempts) and attempt['reason'] == d['reason'] and attempt['final_commit_ns'] == d['activation_commit_ns'],
                       'alignment_one_terminal_commit_per_decision')
            last_raw = raw
        final_attempt = attempts[-1]
        c.need(last_raw['input_commit_ordinal'] == observation['validation_snapshot']['input_commit_ordinal']
               and near(last_raw['state'], observation['validation_snapshot']['state'], 1e-12)
               and final_attempt['sample_ns'] == observation['validation_snapshot']['sample_ns'],
               'alignment_final_attempt_matches_D0_raw_capture')
        if d['job_id'] and selected:
            older += selected['odom_sequence'] != last_raw['odom_sequence']
            c.need(observation['predict_success'] is True and near(predicted, d['activation_state'])
                   and near(predicted, observation['predicted_state']), 'alignment_independent_full_forward_RK4', decision=d['sequence'])
            error = [math.atan2(math.sin(x-y), math.cos(x-y)) if j == 2 else x-y
                     for j, (x, y) in enumerate(zip(predicted, jobs[d['job_id']]['target_state']))]
            c.need(near(error, observation['full_error']), 'alignment_independent_full_state_error')
            if d['accepted']:
                c.need(all(abs(e) <= contract['activation_tolerance'][j] for j, e in enumerate(error))
                       and final_attempt['input_change_gate_unchanged'] is True,
                       'alignment_accepted_candidate_original_state_and_input_gates')
                current = observation['final_snapshot']
                for side in ['odom', 'imu'] if selected['r_from_imu'] else ['odom']:
                    selected_current = dict(current, **selected)
                    c.need(not independent.source_reason(selected_current, side, d['activation_commit_ns'], contract),
                           'alignment_selected_sensor_age_at_actual_final_commit', interface=side)
        proofs.append(dict(decision=d['sequence'], job_id=d['job_id'], attempts=len(attempts), accepted=d['accepted'],
                           selected_odom_sequence=selected['odom_sequence'] if selected else None,
                           raw_odom_sequence=last_raw['odom_sequence'], frames_scanned=final_attempt['frames_scanned']))
    return dict(policy=independent.POLICY, actual_received_sensor_CDRs=len(sensors), actual_frames=len(frames),
                actual_decisions=len(proofs), deferred_materializations_verified=len(proofs), observation_policy='bounded_values_then_JSON_after_observer_publish_return_v1', actual_revalidations=total_retries, older_raw_odom_selected=older,
                maximum_frames_scanned=maximum_scan, proofs=proofs, stage_qualified=False,
                execute_qualified=False, physical_plant_response_proven=False)
