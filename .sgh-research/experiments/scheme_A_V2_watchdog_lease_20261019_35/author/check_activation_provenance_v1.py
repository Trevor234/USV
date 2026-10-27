#!/usr/bin/python3
"""C3 independent offline reconstruction of the pinned fixed-callback run.

No stage qualification. D0 is the author's explicit selection observation;
raw CDR/storage authenticates its referents, not unobserved concurrent reads.
Gate functions below do not invoke the producer's admission implementation.
"""
import argparse
from collections import Counter, deque
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
N5 = Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_config_identity_20261011_v5')
D = Path('/home/trevor/MPC/scheme_A_activation_provenance_20261011_05')
PREREG_SHA = '0e5b16570557534b55e80d5f6c0e2af49af500d67d67a5b18fa07553f65b0659'
AMENDMENT_SHA = '3e38c7b824646350d882e7b107dbf485671e42821232b05f86cf8ac8bbce8c4b'
STAMP_AMENDMENT_SHA = '80f375900fa0d2166131eb374bbe9d79ebacc090922ffb807f41aaf279526490'
NATIVE_AMENDMENT_SHA = 'cd6693468c41bef708a4748ea0a3696d7539938c091928cdd18684800ed700f6'
sha = lambda b: hashlib.sha256(b).hexdigest()
VERSION_FIELDS = {'task':'task_generation', 'model':'model_generation', 'config':'config_generation', 'schedule':'schedule_generation', 'epoch':'clock_epoch'}
FLAGS = dict(strict_full_chain=False, C3_general=False, D1=False, B4=False,
             B5=False, M0b=False, M4=False, F6=False, P1=False, execute=False,
             dynamic_20s_R5=False, mixed_turn=False, true_master_clock=False,
             research_conclusion=False)


def imports():
    raw = (D/'preregister/c3_activation_contract_v1.json').read_bytes()
    if sha(raw) != PREREG_SHA:
        raise ValueError('C3 preregistration pin changed')
    c = json.loads(raw)
    amendment_raw = (D/'preregister/c3_binding_amendment_v1.json').read_bytes()
    if sha(amendment_raw) != AMENDMENT_SHA:
        raise ValueError('C3 binding amendment changed')
    amendment = json.loads(amendment_raw)
    if amendment['parent_sha256'] != PREREG_SHA: raise ValueError('C3 amendment parent changed')
    c['negative_cases'] += amendment['additional_negative_cases']
    stamp_raw = (D/'preregister/c3_stamp_pair_amendment_v1.json').read_bytes()
    if sha(stamp_raw) != STAMP_AMENDMENT_SHA: raise ValueError('C3 stamp-pair amendment changed')
    c['negative_cases'].append(json.loads(stamp_raw)['new_negative_case'])
    native_raw = (D/'preregister/c3_native_registration_amendment_v1.json').read_bytes()
    if sha(native_raw) != NATIVE_AMENDMENT_SHA: raise ValueError('C3 native registration amendment changed')
    c['negative_cases'] += json.loads(native_raw)['new_negative_cases']
    for p in list(c['source_pins'].values()) + [c['identity_contract'], c['formatter_contract'], c['parent_manifest']]:
        if sha(Path(p['path']).read_bytes()) != p['sha256']:
            raise ValueError('C3 dependency pin changed: '+p['path'])
    sys.path[:0] = [str(N5), str(N5/'runtime')]
    identity = importlib.import_module('check_config_identity_v1')
    if Path(identity.__file__).resolve() != N5/'check_config_identity_v1.py':
        raise ValueError('wrong sealed identity helper')
    return c, identity


def load(negative_copy=None):
    c, identity = imports()
    if negative_copy is None:
        for p in c['record_pins'].values():
            if sha(Path(p['path']).read_bytes()) != p['sha256']:
                raise ValueError('original C3 record changed: '+p['path'])
    s = identity.load_data(negative_copy)
    s['C3_contract'] = c
    s['identity'] = identity
    return s


def near(a, b, tolerance=1e-9):
    return (isinstance(a, (list, tuple)) and len(a) == len(b) and
            all(type(x) in (int, float) and type(y) in (int, float) and
                math.isfinite(x) and math.isfinite(y) and abs(x-y) <= tolerance
                for x, y in zip(a, b)))


def publication_gate(expected, actual, history):
    for ch in (0, 1):
        if not expected['known'][ch] or not actual['known'][ch]:
            return 'unknown_anchor'
        if not math.isfinite(expected['n'][ch]) or not math.isfinite(actual['n'][ch]):
            return 'unknown_anchor'
        if actual['n'][ch] != expected['n'][ch]:
            return 'anchor_mismatch'
        seq, time = expected['sequence'][ch], expected['publish_ns'][ch]
        endseq, endtime = actual['sequence'][ch], actual['publish_ns'][ch]
        if endseq < seq or endtime < time:
            return 'anchor_history_incomplete'
        if endseq == seq:
            if time != endtime:
                return 'anchor_history_incomplete'
            continue
        found = False
        for e in history:
            if e['channel'] != ch or not expected['sequence'][ch] <= e['sequence'] <= endseq:
                continue
            if not e['known'] or not math.isfinite(e['n']):
                return 'unknown_anchor'
            if e['n'] != expected['n'][ch]:
                return 'anchor_history_changed'
            if not found:
                if e['sequence'] != seq or e['publish_ns'] != time:
                    return 'anchor_history_incomplete'
                found = True
            else:
                if e['sequence'] != seq+1 or e['publish_ns'] <= time:
                    return 'anchor_history_incomplete'
                seq, time = e['sequence'], e['publish_ns']
        if not found or seq != endseq or time != endtime:
            return 'anchor_history_incomplete'
    return ''


def state_gate(target, actual, cfg, angle):
    errors = [0.0]*6
    for i in range(6):
        errors[i] = angle(actual[i]-target[i]) if i == 2 else actual[i]-target[i]
        if not math.isfinite(errors[i]):
            return 'nonfinite', errors
        if abs(errors[i]) > cfg['activation_tolerance'][i]:
            return 'activation_state_mismatch', errors
    return '', errors


def command_gate(command, anchor, now, cfg):
    for ch in (0, 1):
        v = command[ch]
        if not math.isfinite(v): return 'nonfinite'
        if not cfg['command_min_n'] <= v <= cfg['command_max_n']: return 'command_limit'
        if not anchor['known'][ch]: return 'unknown_anchor'
        age = now-anchor['publish_ns'][ch]
        if age <= 0 or abs(v-anchor['n'][ch]) > cfg['rho_n_s']*age/1e9+1e-9:
            return 'command_rate'
    return ''


def source_time(now, sim, receive, stamp, source_receive, age, lag, slack):
    if age <= 0 or lag <= 0 or slack < 0: return 'limits_invalid'
    if now <= 0 or source_receive <= 0 or stamp < 0: return 'time_invalid'
    if source_receive > now: return 'receive_future'
    if now-source_receive > age: return 'receive_stale'
    if receive <= 0 or receive > now or sim < 0: return 'clock_anchor_invalid'
    elapsed = now-receive
    if sim > (1 << 63)-1-elapsed: return 'clock_extrapolation_overflow'
    current = sim+elapsed
    if stamp > current:
        if stamp-current > slack: return 'sim_future'
    elif current-stamp > lag: return 'sim_lag'
    return ''


def eligibility(snapshot, state, ref, anchor, now, cfg):
    if snapshot['odom_sequence'] <= 0: return 'no_odom'
    # Preserve the original double-seconds comparison, including its rounding.
    if cfg['odom_age_ns'] > 0 and now/1e9-snapshot['odom_receive_ns']/1e9 > cfg['odom_age_ns']/1e9:
        return 'odom_timeout'
    path, profile, ps, qs = ref
    if len(path) < 2: return 'no_path'
    if not all(math.isfinite(x) for x in state): return 'nonfinite'
    if snapshot['r_from_imu'] and (now-snapshot['imu_receive_ns'] > cfg['imu_age_ns'] or abs(snapshot['imu_stamp_ns']-snapshot['odom_stamp_ns']) > cfg['mixed_skew_ns']):
        return 'mixed_source_age_or_skew'
    if not snapshot['clock_receive_ns'] or now-snapshot['clock_receive_ns'] > cfg['clock_age_ns'] or snapshot['paused']:
        return 'clock_missing_stale_paused'
    if not snapshot['rtf_valid']: return 'rtf_unaligned'
    for side in ('odom', 'imu') if snapshot['r_from_imu'] else ('odom',):
        reason = source_time(now, snapshot['clock_sim_ns'], snapshot['clock_receive_ns'], snapshot[side+'_stamp_ns'], snapshot[side+'_receive_ns'], cfg[side+'_age_ns'], cfg[side+'_sim_lag_ns'], cfg['source_future_slack_ns'])
        if reason: return side+'_'+reason
    if not profile or len(profile) != len(path) or ps != qs: return 'profile_pair_incomplete'
    if not all(math.isfinite(v) for p in path for v in p): return 'invalid_path'
    if not all(anchor['known']): return 'unknown_anchor'
    return ''


def analyze(s):
    src = s['source']; safe = s['safe']; typed = s['typed']; cfg = typed['configuration']
    obs = s['records']['observer_source']; worker = s['records']['worker_source']
    source_order = {id(row):i for i,row in enumerate(obs)}
    witness = s['records']['witness']; issues = []; groups = {}; proofs = []
    def need(ok, code, **detail):
        if not ok: issues.append({'code':code, **detail})
        return bool(ok)
    def rows(typ): return src.fields(obs, typ)
    def group(name, start, **detail):
        groups[name] = {'passed':len(issues) == start, **detail}

    start = len(issues)
    formatter = json.loads(Path(s['C3_contract']['formatter_contract']['path']).read_bytes())
    config_report = s['identity'].analyze(s, formatter)
    for g in config_report['components'].values(): issues.extend(g['issues'])
    source_join = typed['reader'].source_typed_join(obs, worker, typed['decoded'])
    issues.extend(source_join['issues'])
    witness_join = typed['reader'].witness_source_join(witness,s['records']['expected_witness_header'],obs)
    need(witness_join['passed'], 'complete_original_Witness_integrity')
    issues.extend(witness_join['issues'])
    allowed = set('clock imu_admission odom_admission capability_admission decision legacy_anchor job job_publish_result candidate_registration anchor_validation profile_version path_version recording_ready startup legacy_ready regulator_shutdown source_summary'.split())
    need(all(x['type'] in allowed for x in obs), 'fixed_valid_event_scope')
    terminal = rows('source_summary')
    need(len(terminal) == 1 and obs[-1] is terminal[0] and terminal[0]['generated'] == terminal[0]['emitted'] == len(obs)-1 and terminal[0]['dropped'] == 0 and terminal[0]['normal_source_complete'] is True, 'whole_source_terminal_conservation')
    transport = typed['reader'].transport_join(typed['cdr'], s['records']['transport_source'],
        {role:s['records']['owned_'+role] for role in ('publisher','worker','observer','synthetic_source','recorder')}, s['records']['topics_file']['topics'])
    issues.extend(transport['issues'] if isinstance(transport, dict) else transport)
    anchors = rows('legacy_anchor')
    applied = [x['message'] for x in typed['decoded'][safe.APPLIED_TOPIC]]
    need(len(anchors) == len(applied) == 23 and [x['sequence'] for x in anchors] == list(range(1,24)), 'whole_Applied_population')
    need(all(safe.equal(x['applied'], y) for x,y in zip(anchors, applied)), 'whole_Applied_full_typed_fields')
    group('pinned_configuration_and_whole_typed_storage', start, configuration_components=len(config_report['components']), storage=typed['storage'])

    start = len(issues); sensors = {}; clock_by_receive = {}; paths = {}; profiles = {}; window = deque(); last_receive = last_sim = 0
    for typ, (topic, ros_type) in src.SENSORS.items():
        mapping = {}; cursor = 0; previous = 0
        gid = next(e['gid'] for e in s['records']['owned_synthetic_source']['endpoints'] if e['kind'] == 'publisher' and e['topic'] == topic)
        for seq, row in enumerate(rows(typ), 1):
            raw = row['raw_input']; blob = bytes.fromhex(raw['cdr_hex'])
            need(raw['callback_sequence'] == seq and raw['schema'] == 'p1-input-callback-full-cdr-v1' and raw['topic'] == topic and raw['message_type'] == ros_type and safe.equal(raw['publisher_gid'], gid), 'raw_callback_identity', event=typ, sequence=seq)
            when = row.get('receive_ns', row.get('processed_ns'))
            need(previous < raw['entry_steady_ns'] <= when and len(blob) == raw['cdr_bytes'] and sha(blob) == raw['cdr_sha256'], 'raw_callback_CDR_identity', event=typ, sequence=seq); previous = raw['entry_steady_ns']
            m = typed['decode'](blob, ros_type)
            stored = typed['decoded'][topic]
            while cursor < len(stored) and not safe.equal(m, stored[cursor]['message']): cursor += 1
            need(cursor < len(stored), 'raw_callback_full_storage_binding', event=typ, sequence=seq)
            if cursor < len(stored): cursor += 1
            need(row.get('sequence', row.get('received_sequence', seq)) == seq, 'raw_callback_semantic_sequence')
            mapping[seq] = (row, m)
            if typ == 'clock':
                receive = row['receive_ns']; sim = src.stamp(m['clock'])
                if last_receive and (receive <= last_receive or sim < last_sim or sim-last_sim > 5_000_000_000): window.clear()
                last_receive, last_sim = receive, sim
                while window and receive-window[0][0] > 600_000_000: window.popleft()
                if not window or receive-window[-1][0] >= 10_000_000: window.append((receive, sim))
                while len(window) > 100: window.popleft()
                span = receive-window[0][0]; rtf = 0.0 if span < 400_000_000 else (sim-window[0][1])/span
                valid = span >= 400_000_000 and cfg['rtf_low'] <= rtf <= cfg['rtf_high']
                need(row['sim_ns'] == sim and row['rtf_window_span_ns'] == span and row['rtf_stored_samples'] == len(window) and abs(row['rtf']-rtf) <= 1e-12 and row['rtf_valid'] == valid, 'whole_independent_RTF_window', sequence=seq)
                clock_by_receive[receive] = {'sim':sim, 'rtf':rtf, 'valid':valid, 'row':row}
            elif typ == 'path_version':
                points = [[p['pose']['position']['x'], p['pose']['position']['y'], src.yaw(p['pose']['orientation'])] for p in m['poses']]
                paths[seq] = (points, (m['header']['stamp']['sec'],m['header']['stamp']['nanosec']), row)
            elif typ == 'profile_version':
                stamps = {'sec':-1,'nanosec':-1}
                for d in m['layout']['dim']:
                    for unit in ('sec','nanosec'):
                        prefix = 'stamp_'+unit+':'
                        if d['label'].startswith(prefix): stamps[unit] = int(re.match(r'^[+-]?\d+', d['label'][len(prefix):]).group())
                profiles[seq] = ([m['data'][i:i+4] for i in range(0,len(m['data']),4)], (stamps['sec'],stamps['nanosec']), row)
        sensors[typ] = mapping
        need(bool(mapping) and all(row.get('valid', True) is True for row,_ in mapping.values()), 'fixed_valid_callback_scope', event=typ)
    need(len(paths) == len(profiles) == 13 and len({x[2]['fingerprint'] for x in paths.values()}) == len({x[2]['fingerprint'] for x in profiles.values()}) == 1, 'stable_reference_content_scope')
    need(all(x['epoch'] == 0 and x['schedule_generation'] == 1 and not x['paused'] for x,_ in sensors['clock'].values()), 'no_clock_reset_pause_scope')
    group('whole_raw_callback_CDR_and_independent_RTF', start, counts={k:len(v) for k,v in sensors.items()}, general_formatter_qualified=False)

    def selected(snapshot, bound, decision, which):
        seq = snapshot['odom_sequence']; odom, m = sensors['odom_admission'][seq]
        need(snapshot['odom_receive_ns'] == odom['receive_ns'] and snapshot['odom_stamp_ns'] == odom['stamp_ns'] == src.stamp(m['header']['stamp']), 'selected_odom_binding', decision=decision, snapshot=which)
        p = m['pose']['pose']['position']; q = m['pose']['pose']['orientation']; t = m['twist']['twist']
        state = [p['x'],p['y'],src.yaw(q),t['linear']['x'],t['linear']['y'],t['angular']['z']]
        need(sum(q[k]**2 for k in ('x','y','z','w')) >= 1e-12 and m['header']['frame_id'] == cfg['expected_pose_frame'] and m['child_frame_id'] == cfg['expected_child_frame'] and near(odom['state'], state), 'selected_odom_raw_admission')
        imu, im = sensors['imu_admission'][snapshot['imu_sequence']]
        need(snapshot['imu_receive_ns'] == imu['receive_ns'] and snapshot['imu_stamp_ns'] == imu['stamp_ns'] == src.stamp(im['header']['stamp']) and abs(imu['r_value']-im['angular_velocity']['z']) <= 1e-9 and im['header']['frame_id'] == cfg['expected_imu_frame'], 'selected_raw_IMU_binding', decision=decision, snapshot=which)
        # Both callbacks share the state mutex. A selected later odom resets mixed.
        # Callback source rows enqueue inside the same state mutex. Receive times
        # are sampled before that lock, so their numeric order is not an oracle.
        need(snapshot['r_from_imu'] == (source_order[id(imu)] > source_order[id(odom)]), 'selected_mixed_flag_binding', decision=decision)
        if snapshot['r_from_imu']: state[5] = im['angular_velocity']['z']
        clock = clock_by_receive.get(snapshot['clock_receive_ns'])
        need(clock is not None and snapshot['clock_sim_ns'] == clock['sim'], 'selected_clock_binding', decision=decision, snapshot=which)
        if clock is not None:
            need(abs(snapshot['rtf']-clock['rtf']) <= 1e-12 and snapshot['rtf_valid'] == clock['valid'] and snapshot['paused'] == clock['row']['paused'], 'selected_RTF_binding', decision=decision, snapshot=which)
        need(all(0 < snapshot[k] <= bound for k in ('odom_receive_ns','imu_receive_ns','clock_receive_ns')), 'snapshot_capture_order', decision=decision, snapshot=which)
        # Recorded version is cross-bound to constant authenticated ref content and raw clock version.
        need(snapshot['version'] == {'task':2,'model':1,'config':1,'schedule':1,'epoch':0}, 'snapshot_version_binding', decision=decision, snapshot=which)
        return state

    def prefix(bound, sequence=None):
        population = [a for a in anchors if a['processed_ns'] <= bound]
        if sequence is not None: population = [a for a in population if a['sequence'] <= sequence]
        history = []; pub = []
        for a in population:
            m = a['applied']
            for ch, side in enumerate(('left','right')):
                history.append({'sim_ns':m[side+'_sim_time_ns'],'channel':ch,'value':m['final_n'][ch]})
                pub.append({'channel':ch,'sequence':m['sequence'],'publish_ns':m[side+'_publish_start_steady_ns'],'n':m['final_n'][ch],'known':m[side+'_publish_success']})
        anchor = {'n':[0.,0.], 'sequence':[0,0], 'publish_ns':[0,0], 'known':[False,False]}
        if population:
            a = population[-1]; anchor = {'n':a['applied']['final_n'],'sequence':[a['sequence']]*2,'publish_ns':a['publish_ns'],'known':a['known']}
        return anchor, history[-cfg['history_capacity']:], pub[-cfg['history_capacity']:], len(population)

    def ref_at(bound):
        pa = [x for x in paths.values() if x[2]['processed_ns'] <= bound]; pr = [x for x in profiles.values() if x[2]['processed_ns'] <= bound]
        if not pa or not pr: return [], [], -1, -1
        p, q = pa[-1], pr[-1]
        return p[0], q[0], p[1], q[1]

    decisions = rows('decision'); jobs = rows('job'); registrations = rows('candidate_registration')
    jobmap = {x['job']['job_id']:x for x in jobs}; regmap = {x['job']['job_id']:x for x in registrations}
    candidates = src.fields(worker,'candidate'); candidate_map = {x['job']['job_id']:x for x in candidates}
    received = src.fields(worker,'job_received'); received_map = {x['job']['job_id']:x for x in received}
    start = len(issues); jobproof = []
    for row in jobs:
        j = row['job']; p = row['input_provenance']
        snap = {k:p[k] for k in ('r_from_imu','clock_receive_ns','clock_sim_ns','rtf','rtf_valid','paused')}
        snap.update({k:j[k] for k in ('odom_sequence','odom_receive_ns','odom_stamp_ns')})
        imu, _ = sensors['imu_admission'][p['imu_sequence_raw']]
        snap.update(imu_sequence=p['imu_sequence_raw'], imu_receive_ns=imu['receive_ns'], imu_stamp_ns=imu['stamp_ns'], version={k:j[v] for k,v in VERSION_FIELDS.items()})
        frozen = selected(snap, j['freeze_ns'], 'job'+str(j['job_id']), 'job')
        need(p['freeze_ns'] == j['freeze_ns'] and p['clock_receive_ns'] == j['frozen_clock_receive_ns'] and p['clock_sim_ns'] == j['frozen_clock_sim_ns'], 'job_explicit_clock_freeze_binding', job=j['job_id'])
        need(near(j['frozen_state'], frozen), 'job_selected_raw_state', job=j['job_id'])
        anchor, hist, _, _ = prefix(j['freeze_ns'])
        actual_hist = [{'sim_ns':a,'channel':b,'value':v} for a,b,v in zip(j['history_sim_ns'],j['history_channel'],j['history_n'])]
        need(len(j['history_sim_ns']) == len(j['history_channel']) == len(j['history_n']) and safe.equal(actual_hist,hist) and safe.equal(anchor, {'n':j['anchor_n'],'sequence':j['anchor_sequence'],'publish_ns':j['anchor_publish_ns'],'known':j['anchor_known']}), 'job_full_history_and_anchor', job=j['job_id'])
        target = p['clock_sim_ns']+j['target_ns']-p['clock_receive_ns']
        need(j['target_sim_ns'] == target and j['assumed_rtf'] == 1.0, 'job_original_target_mapping', job=j['job_id'])
        nominal = src.propagate(frozen,j['odom_stamp_ns'],target,anchor['n'],[(x['sim_ns'],x['channel'],x['value']) for x in hist],cfg['hydro'])
        need(near(j['target_state'], nominal), 'independent_job_RK4', job=j['job_id'])
        path, ps, pathrow = paths[p['path_sequence']]; profile, qs, profilerow = profiles[p['profile_sequence']]
        need(ps[0]*1_000_000_000+ps[1] == p['path_stamp_ns'] and qs[0]*1_000_000_000+qs[1] == p['profile_stamp_ns'] and pathrow['processed_ns'] <= j['freeze_ns'] and profilerow['processed_ns'] <= j['freeze_ns'], 'immutable_job_reference_selection', job=j['job_id'])
        # Actual C++ mutates s.state in predict, then builds reference from it.
        ref, meta = src.reference(nominal,path,profile,ps,qs,cfg)
        need(near(j['reference'],ref) and all(row[k] == v for k,v in meta.items()), 'reference_from_nominal_target126', job=j['job_id'])
        need(j['reset_warmstart'] == (abs(src.angle(nominal[2]-ref[2])) > math.pi*.75), 'original_reference_warmstart', job=j['job_id'])
        jobproof.append({'job_id':j['job_id'],'odom_sequence':j['odom_sequence'],'path_sequence':p['path_sequence'],'profile_sequence':p['profile_sequence'],'max_nominal_error':max(abs(x-y) for x,y in zip(j['target_state'],nominal)),'max_reference_error':max(abs(x-y) for x,y in zip(j['reference'],ref)),'reference_state':'independent nominal target'})
    need(len(jobproof) == 23, 'whole_Job_population')
    group('immutable_Job_raw_nominal_target_and_reference126', start, jobs=jobproof, general_moving_reference_qualified=False)

    start = len(issues)
    submit = witness['submit']; acts = witness['activation']; ticks = witness['tick']
    pair_decisions = [d for d in decisions if d['d0_observation']['candidate_pair_available']]
    need(len(decisions) == len(ticks) == 31 and [d['sequence'] for d in decisions] == list(range(1,32)), 'whole_Decision_tick_population')
    need(len(jobs) == len(registrations) == len(submit) == 23 and set(jobmap) == set(regmap) == set(x['job_id'] for x in submit), 'whole_Job_registration_submit_population')
    need(len(candidates) == len(received) == 23 and set(candidate_map) == set(received_map) == set(jobmap), 'whole_actual_Worker_Candidate_population')
    need(len(acts) == len(pair_decisions) == 22 and [(x['job_id'],x['tick']) for x in acts] == [(d['job_id'],d['tick']) for d in pair_decisions], 'whole_actual_activation_population')
    need(witness['enabled'] and witness['closed'] and witness['audit_complete'] and not witness['overflow'] and not witness['incomplete'], 'witness_integrity_without_normal_policy_relaxation')
    for row in registrations:
        j = row['job']; original = jobmap[j['job_id']]['job']
        candidate = candidate_map[j['job_id']]
        receipt = received_map[j['job_id']]
        worker_instance = s['records']['owned_worker']['worker_instance']
        need(safe.equal(candidate['job'],j) and safe.equal(receipt['job'],j) and candidate['receive_ns'] == receipt['receive_ns'] and receipt['worker_instance'] == candidate['worker_instance'] == j['worker_instance'] == worker_instance and candidate['backend'] == 'acados' and all(safe.equal(row[k],candidate[k]) for k in ('first_control','solve_start_ns','solve_end_ns','worker_instance')) and candidate['success'] and candidate['prediction_available'] and candidate['solver_invoked'] and candidate['reason'] == '' and len(candidate['X']) == 126 and len(candidate['U']) == 40 and all(math.isfinite(x) for x in candidate['X']+candidate['U']+candidate['first_control']) and math.isfinite(candidate['backend_ms']) and candidate['backend_ms'] >= 0 and j['freeze_ns'] <= candidate['receive_ns'] <= candidate['solve_start_ns'] <= candidate['solve_end_ns'] <= row['ready_commit_ns'] and near(candidate['first_control'],candidate['U'][:2],1e-8) and near(candidate['X'][:6],j['target_state'],1e-7), 'actual_Worker_Candidate_registration_binding', job=j['job_id'])
        need(safe.equal(j,original) and row['accepted_registration'] and row['reason'] == '', 'original_immutable_registration', job=j['job_id'])
        need(j['deadline_ns'] == j['tick_origin_ns']+150_000_000 and j['target_ns'] == j['tick_origin_ns']+200_000_000 and j['freeze_ns'] <= row['solve_start_ns'] <= row['solve_end_ns'] <= row['ready_commit_ns'] <= j['deadline_ns'], 'original_registration_time', job=j['job_id'])
        w = next(x for x in submit if x['job_id'] == j['job_id'])
        need(w['tick']+1 == j['target_tick'] == w['target_tick'] and all(w[field] == j[field] for field in VERSION_FIELDS.values()) and jobmap[j['job_id']]['submit_commit_ns'] <= w['commit_ns'] <= jobmap[j['job_id']]['publish_start_ns'] and not w['failed'] and not w['stopping'], 'original_submit_tick_identity', job=j['job_id'])
    group('whole_registration_cutoff_Witness_populations', start, decisions=len(decisions), pairs=len(pair_decisions), registrations=len(registrations), normal_Witness_policy_changed=False)

    start = len(issues); selectedproof = {}; anchorproof = {}; predictionproof = {}
    for d in decisions:
        seq = d['sequence']; ob = d['d0_observation']; v = ob['validation_snapshot']; f = ob['final_snapshot']; pair = ob['candidate_pair_available']
        need(ob['schema'] == 'p1-d0-observation-v1' and v['capture_semantics'] == 'mutex_copy_end' and v['sample_ns'] == d['start_ns'] and v['sample_ns'] <= v['copy_capture_ns'] <= f['commit_ns'] == d['activation_commit_ns'] <= d['end_ns'], 'snapshot_capture_order', decision=seq)
        state = selected(v, v['copy_capture_ns'], seq, 'validation'); finalstate = selected(f, f['commit_ns'], seq, 'final')
        need(near(v['state'],state), 'raw_selected_state', decision=seq)
        expected_version = {k:d['epoch'] if k == 'epoch' else d[field] for k,field in VERSION_FIELDS.items()}
        need(v['version'] == expected_version, 'snapshot_Decision_version_binding', decision=seq)
        need(all(d['activation_'+k] == f[k] for k in ('clock_receive_ns','clock_sim_ns','odom_receive_ns','odom_stamp_ns','odom_sequence','r_from_imu')) and abs(d['activation_rtf']-f['rtf']) <= 1e-12 and all(d['activation_'+k] == (f[k] if f['r_from_imu'] else 0) for k in ('imu_receive_ns','imu_stamp_ns','imu_sequence')), 'canonical_final_input_binding', decision=seq)
        need(d['odom_age_ns'] == f['commit_ns']-f['odom_receive_ns'] and d['clock_age_ns'] == f['commit_ns']-f['clock_receive_ns'] and d['imu_age_ns'] == (f['commit_ns']-f['imu_receive_ns'] if f['r_from_imu'] else 0), 'final_actual_source_ages', decision=seq)
        a, hist, pub, count = prefix(v['copy_capture_ns']); finalanchor, finalhist, finalpub, finalcount = prefix(f['commit_ns'])
        need(safe.equal(v['anchor'],a), 'validation_actual_anchor', decision=seq)
        need(v['history_count'] == len(hist) and safe.equal(v['held_history'],hist), 'validation_full_held_history', decision=seq)
        selectedproof[seq] = {'validation_state':state,'final_state':finalstate,'validation_anchor':a,'final_anchor':finalanchor,'validation_pub':pub,'final_pub':finalpub}
        if pair:
            j = jobmap[d['job_id']]['job']; reg = regmap[d['job_id']]
            need(ob['candidate_job_id'] == d['job_id'] and ob['candidate_target_tick'] == d['tick'] == j['target_tick'] and near(d['target_state'], j['target_state']), 'candidate_ticket_binding', decision=seq)
            need(ob['prediction_target_sim_ns'] == j['target_sim_ns'], 'pair_target_binding', decision=seq)
            need(d['ready_commit_ns'] == reg['ready_commit_ns'] and reg['ready_commit_ns'] <= j['deadline_ns'] < d['cutoff_commit_ns'] <= d['start_ns'] and j['target_ns'] == d['planned_ns'] <= d['start_ns'], 'original_cutoff_take', decision=seq)
            expected = {'n':j['anchor_n'],'sequence':j['anchor_sequence'],'publish_ns':j['anchor_publish_ns'],'known':j['anchor_known']}
            anchor_rows = [x for x in rows('anchor_validation') if x['sequence'] == seq]
            need(len(anchor_rows) == 1, 'commit_anchor_evidence_population', decision=seq)
            ar = anchor_rows[0]
            actual = {'n':ar['actual_n'],'sequence':ar['actual_sequence'],'publish_ns':ar['actual_publish_ns'],'known':ar['actual_known']}
            expected_claim = {'n':ar['expected_n'],'sequence':ar['expected_sequence'],'publish_ns':ar['expected_publish_ns'],'known':ar['expected_known']}
            need(safe.equal(actual, finalanchor) and safe.equal(expected_claim,expected) and ar['check_ns'] == f['commit_ns'] and ar['job_id'] == j['job_id'], 'commit_actual_anchor', decision=seq)
            scoped_pub = [e for e in finalpub if expected['sequence'][e['channel']] <= e['sequence'] <= finalanchor['sequence'][e['channel']]]
            need(safe.equal(ar['entries'], scoped_pub), 'commit_full_publication_history', decision=seq)
            validation_reason = publication_gate(expected,a,pub); final_reason = publication_gate(expected,finalanchor,finalpub)
            need(ar['history_reason'] == final_reason and ar['decision_reason'] == d['reason'] and ar['accepted'] == d['accepted'], 'independent_publication_history_reason', decision=seq)
            history = [(x['sim_ns'],x['channel'],x['value']) for x in hist]
            initial = list(a['n']); found = [False,False]
            for when,ch,value in history:
                if when <= v['odom_stamp_ns']: initial[ch] = value; found[ch] = True
            predicted_ok = all(found) and 0 <= j['target_sim_ns']-v['odom_stamp_ns'] <= 1_000_000_000
            predicted = src.propagate(state,v['odom_stamp_ns'],j['target_sim_ns'],initial,history,cfg['hydro']) if predicted_ok else [0.]*6
            need(ob['predict_invoked'] and ob['predict_success'] == predicted_ok and ob['predict_status'] == ('success' if predicted_ok else 'history_or_time_failed') and ob['predicted_state_available'] == predicted_ok and ob['full_error_available'] == predicted_ok and (predicted_ok or (ob['predicted_state'] is None and ob['full_error'] is None)), 'pair_prediction_lifecycle', decision=seq)
            need(near(d['activation_state'],predicted) and (not predicted_ok or near(ob['predicted_state'],predicted)), 'independent_activation_RK4', decision=seq)
            full = [src.angle(predicted[i]-j['target_state'][i]) if i == 2 else predicted[i]-j['target_state'][i] for i in range(6)]
            state_reason, errors = state_gate(j['target_state'],predicted,cfg,src.angle) if predicted_ok else (None,[0.]*6)
            need(not predicted_ok or near(ob['full_error'],full), 'independent_full_error', decision=seq)
            need(near(d['state_error'],errors if predicted_ok else [0.]*6), 'original_state_check_prefix', decision=seq)
            anchorproof[seq] = (validation_reason,final_reason)
            predictionproof[seq] = (predicted_ok,state_reason)
        else:
            need(ob['candidate_job_id'] is None and ob['candidate_target_tick'] is None and ob['prediction_target_sim_ns'] is None and not ob['predict_invoked'] and ob['predict_status'] == 'not_attempted' and not ob['predict_success'] and not ob['predicted_state_available'] and not ob['full_error_available'] and ob['predicted_state'] is None and ob['full_error'] is None and d['job_id'] == 0, 'nonpair_prediction_lifecycle', decision=seq)
        proofs.append({'decision':seq,'pair':pair,'job_id':d['job_id'],'validation_odom_sequence':v['odom_sequence'],'final_odom_sequence':f['odom_sequence'],'raw_imu_sequence':v['imu_sequence'],'r_from_imu':v['r_from_imu'],'job_odom_sequence':jobmap[d['job_id']]['job']['odom_sequence'] if pair else None,'validation_Applied_prefix':count,'final_Applied_prefix':finalcount,'held_events':len(hist),'state_check_reason':predictionproof[seq][1] if pair else None,'full_error_vs_prefix_differs':pair and not near(ob['full_error'],d['state_error'])})
    group('actual_selected_raw_state_history_and_activation_numerics', start, snapshots=2*len(decisions), predictions=len(pair_decisions), accepted_predictions=sum(d['accepted'] for d in pair_decisions), source_selection_claim_authenticated=True, independently_observed_mutex_mutation_serial=False)

    start = len(issues); ready = rows('legacy_ready')
    need(len(ready) == 1 and ready[0]['readiness']['measurement_eligible'] is True, 'stable_legacy_ready_scope')
    ready_ns = ready[0]['readiness']['legacy_ready_ns']
    cap = rows('capability_admission')
    need(bool(cap) and all(x['valid'] and x['identity_valid'] and x['renewed'] and not x['terminal_run'] and not x['capability']['fatal'] for x in cap), 'normal_worker_lease_scope')
    forbidden = {'legacy_ready_invalidated','legacy_ready_failed','worker_unusable_transition','worker_capability_lease_expired','worker_invalid','source_failure','scheduler_skipped_ticks','active_watchdog'}
    need(not (set(x['type'] for x in obs) & forbidden), 'no_unobserved_policy_transition_scope')
    stopping_phases = [x for x in witness['phase'] if x['event_code'] == 5]
    need(len(stopping_phases) == 1 and stopping_phases[0]['observation_code'] == 1 and stopping_phases[0]['tick'] == decisions[-1]['tick'], 'actual_shutdown_phase')
    last_accepted = 0; reason_counts = Counter(); ran_counts = Counter(); skipped_counts = Counter()
    for d, proof in zip(decisions,proofs):
        seq = d['sequence']; v = d['d0_observation']['validation_snapshot']; f = d['d0_observation']['final_snapshot']; ob = d['d0_observation']; pair = ob['candidate_pair_available']; selected_data = selectedproof[seq]
        wt = next(x for x in ticks if x['tick'] == d['tick'])
        need(wt['job_id'] == d['job_id'] and wt['target_tick'] == (d['tick'] if pair else 0) and all(wt[field] == (d['epoch'] if key == 'epoch' else d[field]) for key,field in VERSION_FIELDS.items()) and wt['sequence'] == seq and wt['planned_ns'] == d['planned_ns'] and wt['start_ns'] == d['start_ns'] and d['end_ns'] <= wt['end_ns'] and wt['candidate_present'] == pair and not wt['failed_start'] and not wt['failed_end'] and wt['skipped_ticks'] == 0, 'whole_tick_identity_and_policy_scope', decision=seq)
        stop = wt['stopping_start']; final_stop = wt['stopping_end']
        need(stop == final_stop == (d['tick'] == stopping_phases[0]['tick']), 'shutdown_flags_phase_binding', decision=seq)
        need(all(0 <= d['start_ns']-d['planned_ns'] <= cfg['tick_jitter_ns'] for _ in (0,)), 'fixed_no_jitter_scope', decision=seq)
        lease = [x for x in cap if x['validation_commit_ns'] <= v['sample_ns']]
        need(bool(lease) and f['commit_ns']-lease[-1]['validation_commit_ns'] <= cfg['worker_capability_receipt_timeout_ns'], 'actual_worker_receipt_lease', decision=seq)
        trace = []
        def gate(name, value=None, ran=True, overwrite=False):
            nonlocal reason
            before = reason
            if ran and (overwrite or not reason): reason = value or ''
            trace.append({'gate':name,'ran':ran,'evaluated_reason':value if ran else None,'reason_before':before,'reason_after':reason,'overwrites':overwrite and ran and before != reason})
            (ran_counts if ran else skipped_counts)[name] += 1
        reason = ''
        eligible_reason = eligibility(v,selected_data['validation_state'],ref_at(v['copy_capture_ns']),selected_data['validation_anchor'],v['sample_ns'],cfg)
        gate('validation_eligibility',eligible_reason)
        legacy = ready_ns <= v['sample_ns']
        gate('legacy_not_ready_override','legacy_not_ready',ran=not legacy,overwrite=True)
        gate('shutdown_start_override','shutdown',ran=stop,overwrite=True)
        gate('worker_unusable_override','worker_unusable',ran=False,overwrite=True)
        gate('tick_jitter_override','tick_jitter',ran=d['start_ns']-d['planned_ns'] > cfg['tick_jitter_ns'],overwrite=True)
        requested = [0.,0.]; final = [0.,0.]
        if pair:
            j = jobmap[d['job_id']]['job']; reg = regmap[d['job_id']]
            job_version = {k:j[field] for k,field in VERSION_FIELDS.items()}
            gate('candidate_version','' if job_version == v['version'] else 'version_mismatch',ran=not reason)
            gate('publication_history_validation',anchorproof[seq][0],ran=not reason)
            predicted_ok, state_reason = predictionproof[seq]
            gate('prediction_status','' if predicted_ok else 'activation_history_or_time',ran=True)
            # State check actually executes despite previous reason, without replacing it.
            gate('state_check',state_reason,ran=predicted_ok)
            map_ran = not reason
            if map_ran:
                requested = list(candidate_map[d['job_id']]['first_control']); lo = max(cfg['command_min_n'],-cfg['publisher_max_n']); hi = min(cfg['command_max_n'],cfg['publisher_max_n'])
                final = [min(hi,max(lo,x*cfg['map_scale'])) for x in requested]
                command_reason = command_gate(final,selected_data['validation_anchor'],v['sample_ns'],cfg)
                gate('command_validation',command_reason)
                gate('mapping_changed_override','candidate_mapping_changed',ran=math.hypot(*(a-b for a,b in zip(final,requested))) > 1e-9,overwrite=True)
            else:
                gate('command_validation',ran=False); gate('mapping_changed_override',ran=False,overwrite=True)
        else: gate('no_candidate','no_candidate',ran=not reason)
        input_ran = not reason
        unchanged = v['version'] == f['version'] and v['odom_sequence'] == f['odom_sequence'] and v['imu_sequence'] == f['imu_sequence']
        need(ob['input_change_gate_ran'] == input_ran and ob['input_change_gate_unchanged'] == (unchanged if input_ran else None), 'original_input_change_gate', decision=seq)
        gate('input_change','' if unchanged else 'activation_input_changed_during_validation',ran=input_ran)
        gate('publication_history_commit',anchorproof[seq][1] if pair else None,ran=not reason and pair)
        gate('commit_eligibility',eligibility(f,selected_data['final_state'],ref_at(f['commit_ns']),selected_data['final_anchor'],f['commit_ns'],cfg),ran=not reason)
        gate('legacy_commit','' if ready_ns <= f['commit_ns'] else 'legacy_not_ready_at_commit',ran=not reason)
        gate('run_usable_commit','',ran=not reason)
        gate('jitter_commit','tick_jitter_at_commit' if f['commit_ns']-d['planned_ns'] > cfg['tick_jitter_ns'] else '',ran=not reason)
        target_reason = ''
        if pair and abs(f['clock_sim_ns']+f['commit_ns']-f['clock_receive_ns']-j['target_sim_ns']) > cfg['target_sim_slack_ns']: target_reason = 'target_sim_mismatch'
        gate('target_sim_commit',target_reason,ran=not reason and pair)
        gate('command_commit',command_gate(final,selected_data['final_anchor'],f['commit_ns'],cfg),ran=not reason)
        gate('shutdown_final_override','shutdown',ran=final_stop,overwrite=True)
        accepted = not reason
        need(d['reason'] == reason and d['accepted'] == accepted, 'original_reason_flow', decision=seq, expected_reason=reason, observed_reason=d['reason'])
        if accepted:
            last_accepted = f['commit_ns']; source = 'candidate'
        else:
            invalid = final_stop or reason != 'no_candidate'
            hold = not invalid and last_accepted > 0 and f['commit_ns']-last_accepted <= cfg['hold_ns']
            a = selected_data['final_anchor']; final = []
            for ch in (0,1):
                if not a['known'][ch]: val = 0.
                elif hold: val = a['n'][ch]
                else: val = math.copysign(max(0.,abs(a['n'][ch])-cfg['rho_n_s']*max(0,f['commit_ns']-a['publish_ns'][ch])/1e9),a['n'][ch])
                final.append(val)
            requested = final[:]; source = 'hold' if hold else 'ramp_zero'
        need(near(d['final_n'],final) and near(d['requested_n'],requested) and d['control_source'] == source, 'original_output_command', decision=seq)
        need(d['mode'] == 'shadow' and d['diagnostic_only'] and not any(d['publish_success']) and d['publish_start_ns'] == d['publish_end_ns'] == [0,0] and not d['plant_acceptance_observed'], 'no_physical_Observer_output', decision=seq)
        if pair:
            matching = [x for x in acts if x['job_id'] == d['job_id']]
            need(len(matching) == 1, 'whole_actual_activation_population', decision=seq)
            if len(matching) == 1:
                wa = matching[0]
                need(wa['target_tick'] == d['tick'] and all(wa[field] == (d['epoch'] if key == 'epoch' else d[field]) for key,field in VERSION_FIELDS.items()) and wa['commit_ns'] == f['commit_ns'] and wa['ready_commit_ns'] == d['ready_commit_ns'] and wa['accepted'] == accepted and wa['reason_code'] == (0 if accepted else 1 if reason == 'shutdown' else 2 if reason == 'run_unusable_at_commit' else 3) and not wa['failed'] and wa['stopping'] == final_stop, 'whole_activation_Witness_binding', decision=seq)
        proof.update(validation_eligibility_reason=eligible_reason, final_reason=reason, accepted=accepted, gate_trace=trace, final_command=final, atomic_policy_read_values_observed=False)
        reason_counts[reason or 'accepted'] += 1
    group('original_ordered_reason_overrides_and_fallback',start, reason_counts=dict(reason_counts), gates_ran=dict(ran_counts), gates_skipped=dict(skipped_counts), independently_atomic_flags_observed=False)
    return {'schema':'p1-C3-activation-components-v1','passed':not issues,'components':groups,'issues':issues,'proofs':proofs,'run_id':typed['records']['inputs.json']['run_id'],'original_authenticity_qualified':s['negative_copy'] is None,'negative_copy':s['negative_copy'],'scope':s['C3_contract']['scope'],'preregister_sha256':PREREG_SHA,'input_sha256':s['hashes'],'typed_input_sha256':typed['hashes'],'component_verification_only':True,'selected_reference_content_equivalence':True,'selected_reference_identity_general_qualified':False,'all_rejected_full_raw_run_qualified':False,'qualification_limits':s['C3_contract']['remaining_observation_gaps'],**FLAGS}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); a = p.parse_args()
    try:
        s = load(); report = analyze(s)
        after = {k:sha(s['safe'].read_regular(path)) for k,path in s['paths'].items()}
        typed_after = {p:sha(s['safe'].read_regular(Path(s['typed']['root'])/p)) for p in s['typed']['paths']}
        unchanged = after == s['hashes'] and typed_after == s['typed']['hashes']
        report['original_inputs_unchanged'] = unchanged
        if not unchanged: report['issues'].append({'code':'input_changed_during_read'}); report['passed'] = False
        # Recheck contract, sources and full bag pins after the read.
        c,_ = imports()
        for pin in c['record_pins'].values():
            if sha(Path(pin['path']).read_bytes()) != pin['sha256']: raise ValueError('original record changed after check')
    except Exception as e:
        report = {'schema':'p1-C3-activation-components-v1','passed':False,'issues':[{'code':'bounded_input_or_checker_error','detail':type(e).__name__+': '+str(e)}],**FLAGS}
    with a.output.open('x') as f: json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')
    print(json.dumps({'passed':report['passed'],'issues':report['issues'][:20],'components':{k:v['passed'] for k,v in report.get('components',{}).items()}},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
