"""Independent bounded causal sensor selection and forward prediction audit."""
from collections import deque
import math

POLICY = 'latest_causal_sensor_frame_then_one_revalidation_v1'
CAPACITY = 32


def source_reason(s, side, now, c):
    receive, stamp = s[side + '_receive_ns'], s[side + '_stamp_ns']
    clock_receive, clock_sim = s['clock_receive_ns'], s['clock_sim_ns']
    if receive <= 0 or stamp < 0 or now <= 0:
        return 'time_invalid'
    if receive > now:
        return 'receive_future'
    if now - receive > c[side + '_age_ns']:
        return 'receive_stale'
    if clock_receive <= 0 or clock_receive > now or clock_sim < 0:
        return 'clock_anchor_invalid'
    current = clock_sim + now - clock_receive
    if stamp > current and stamp - current > c['source_future_slack_ns']:
        return 'sim_future'
    if current - stamp > c[side + '_sim_lag_ns']:
        return 'sim_lag'
    return ''


def select_frame(frames, snapshot, target, c, generation):
    if len(frames) > CAPACITY:
        raise ValueError('history capacity')
    now = snapshot['sample_ns']
    for scanned, frame in enumerate(reversed(frames), 1):
        if (frame['history_generation'] != generation or frame['version'] != snapshot['version']
                or frame['input_commit_ordinal'] > snapshot['input_commit_ordinal']
                or frame['odom_sequence'] <= 0 or frame['odom_stamp_ns'] > target
                or frame['r_from_imu'] and frame['imu_stamp_ns'] > target
                or not 0 <= target - frame['odom_stamp_ns'] <= 1_000_000_000):
            continue
        if len(frame['state']) != 6 or any(not math.isfinite(x) for x in frame['state']):
            continue
        s = dict(snapshot, **frame)
        if source_reason(s, 'odom', now, c):
            continue
        if frame['r_from_imu'] and (frame['imu_sequence'] <= 0
                or abs(frame['imu_stamp_ns'] - frame['odom_stamp_ns']) > c['mixed_skew_ns']
                or source_reason(s, 'imu', now, c)):
            continue
        if {e['channel'] for e in snapshot['held_history']
                if e['sim_ns'] <= frame['odom_stamp_ns']} != {0, 1}:
            continue
        return frame, scanned
    return None, len(frames)


def reconstruct_frame_prefixes(observer):
    """Original raw callbacks determine state; reset events bound new histories.

    Legacy batch27 has no history events. Its version-changing input commits
    supply the explicit offline reset premise; this is not a runtime claim.
    """
    version = dict(task=0, model=1, config=1, schedule=1, epoch=0)
    generation = 1
    frames, prefixes = deque(maxlen=CAPACITY), {}
    state, odom, imu, have_odom = [0.] * 6, None, None, False
    has_explicit_resets = any(r.get('type') == 'activation_sensor_history_reset' for r in observer)
    for row in observer:
        kind = row.get('type')
        changed = False
        if kind in ['path_version', 'profile_version']:
            changed = version['task'] != row['task_generation']
            version['task'] = row['task_generation']
        elif kind == 'clock':
            changed = version['epoch'] != row['epoch'] or version['schedule'] != row['schedule_generation']
            version['epoch'], version['schedule'] = row['epoch'], row['schedule_generation']
        if kind == 'activation_sensor_history_reset':
            generation = row['history_generation']
            version = row['version']
            frames.clear()
            have_odom = False
        elif changed and not has_explicit_resets:
            generation += 1
            frames.clear()
            have_odom = False
        if kind not in ['odom_admission', 'imu_admission']:
            continue
        if row['valid']:
            if kind == 'odom_admission':
                odom, state, have_odom = row, list(row['state']), True
            else:
                imu = row
                state[5] = row['r_value']
            if have_odom:
                frame = dict(state=list(state), version=dict(version), history_generation=generation,
                             input_commit_ordinal=row['input_commit_ordinal'],
                             origin_kind='odom' if kind == 'odom_admission' else 'imu',
                             origin_sequence=row['sequence'], odom_sequence=odom['accepted_sequence'],
                             odom_stamp_ns=odom['stamp_ns'], odom_receive_ns=odom['receive_ns'],
                             imu_sequence=imu['accepted_sequence'] if imu else 0,
                             imu_stamp_ns=imu['stamp_ns'] if imu else 0,
                             imu_receive_ns=imu['receive_ns'] if imu else 0,
                             r_from_imu=kind == 'imu_admission')
                frames.append(frame)
        prefixes[row['input_commit_ordinal']] = (generation, list(frames))
    return prefixes


def propagate_frame(frame, snapshot, target, hydro):
    # Use the independent Fossen/RK4 implementation; no native selector or model
    # library is called here. Same held-input semantics as the original gate.
    from check_source_components_v4 import propagate
    events = [(e['sim_ns'], e['channel'], e['value']) for e in snapshot['held_history']]
    initial = list(snapshot['anchor']['n'])
    for when, channel, value in events:
        if when <= frame['odom_stamp_ns']:
            initial[channel] = value
    return propagate(frame['state'], frame['odom_stamp_ns'], target, initial, events, hydro)
