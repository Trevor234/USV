#!/usr/bin/env python3
"""Offline all-rejected activation component; no normal/D1/execute qualification."""
import argparse
import array
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
import sys

sys.dont_write_bytecode = True
CONTRACT = Path('/home/trevor/MPC/scheme_A_strict_source_20261011_03/audits/witness_policy/contract_v1.json')
CONTRACT_SHA = 'a835191f587a4ad03dd57258789bd58bded0696cb52a3344ce56bd7010b7d5f7'
LOCK_SHA = 'bac477029e589a0336cdcd71c583cbcdf3b945ade06516c446f3179b8a64928a'
SCHEMA = 'p1-all-rejected-activation-audit-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    out = {}
    for k, v in items:
        if k in out:
            raise ValueError('duplicate JSON key: ' + k)
        out[k] = v
    return out


def parse(raw):
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON ' + x)))


def read_json(path):
    return parse(Path(path).read_bytes())


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)


def same(a, b):
    return canonical(a) == canonical(b)


def finite(v):
    return type(v) in (float, int) and math.isfinite(v)


def exact_vector(a, n):
    return type(a) is list and len(a) == n and all(finite(v) for v in a)


def load_contract():
    raw = CONTRACT.read_bytes()
    if digest(raw) != CONTRACT_SHA:
        raise ValueError('frozen component contract changed')
    c = parse(raw)
    for item in [c['helper'], *c['policy_source_pins'].values()]:
        if digest(Path(item['path']).read_bytes()) != item['sha256']:
            raise ValueError('frozen helper/policy source changed: ' + item['path'])
    lockraw = Path(c['original_lock']['path']).read_bytes()
    if digest(lockraw) != LOCK_SHA:
        raise ValueError('original lock changed')
    lock = parse(lockraw)
    for item in lock['offline_serializer_python_pins'].values():
        if digest(Path(item['path']).read_bytes()) != item['sha256']:
            raise ValueError('offline serializer Python pin changed')
    return c, lock


def plain(value):
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if hasattr(value, 'tolist'):
        return plain(value.tolist())
    if isinstance(value, (array.array, list, tuple)):
        return [plain(v) for v in value]
    return value


def raw_bag(root):
    from rclpy.serialization import deserialize_message
    from nav_msgs.msg import Path as RosPath
    from std_msgs.msg import Float64MultiArray
    from usv_research_interfaces.msg import AppliedControl
    types = {'/path/reference': RosPath, '/path/reference_profile': Float64MultiArray,
             '/research/control/applied': AppliedControl}
    out = {k: [] for k in types}
    db = Path(root) / 'recorder/bag/bag_0.db3'
    connection = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
    try:
        for topic, stamp, blob in connection.execute(
                'SELECT t.name,m.timestamp,m.data FROM messages m JOIN topics t ON m.topic_id=t.id ORDER BY m.id'):
            if topic not in types:
                continue
            msg = deserialize_message(blob, types[topic])
            if topic == '/path/reference':
                item = {'stamp': [msg.header.stamp.sec, msg.header.stamp.nanosec],
                        'frame': msg.header.frame_id,
                        'points': [[x.pose.position.x, x.pose.position.y, x.pose.position.z,
                                    x.pose.orientation.x, x.pose.orientation.y,
                                    x.pose.orientation.z, x.pose.orientation.w] for x in msg.poses]}
            elif topic == '/path/reference_profile':
                labels = [x.label for x in msg.layout.dim]
                if len(labels) != 2 or not labels[0].startswith('stamp_sec:') or not labels[1].startswith('stamp_nanosec:'):
                    raise ValueError('profile stamp labels invalid')
                item = {'stamp': [int(labels[0].split(':')[1]), int(labels[1].split(':')[1])],
                        'data': plain(msg.data), 'dims': [x.size for x in msg.layout.dim]}
            else:
                item = {k: plain(getattr(msg, k)) for k in msg.get_fields_and_field_types()}
            out[topic].append(item)
    finally:
        connection.close()
    return out


def load_run(root, contract, *, original=True):
    root = Path(root)
    files = ['observer/source.jsonl', 'worker/source.jsonl', 'observer/witness.json',
             'expected_witness_header.json', 'inputs.json', 'result.json',
             'full_stream_check_01.json', 'recorder/bag/bag_0.db3',
             'recorder/bag/metadata.yaml', 'observer/owned_manifest.json',
             'worker/owned_manifest.json', 'publisher/owned_manifest.json',
             'publisher/startup_manifest.json']
    before = {n: digest((root / n).read_bytes()) for n in files}
    data = {'root': str(root), 'input_sha256': before, 'original': original}
    for key, name in [('observer', 'observer/source.jsonl'), ('worker', 'worker/source.jsonl')]:
        data[key] = [parse(x) for x in (root / name).read_bytes().splitlines() if x.strip()]
    for key, name in [('witness', 'observer/witness.json'), ('header', 'expected_witness_header.json'),
                      ('inputs', 'inputs.json'), ('result', 'result.json'),
                      ('worker_manifest', 'worker/owned_manifest.json')]:
        data[key] = read_json(root / name)
    data['configuration'] = read_json(data['inputs']['contract'])
    if digest(Path(data['inputs']['contract']).read_bytes()) != data['inputs']['contract_sha256']:
        raise ValueError('diagnostic contract identity mismatch')
    data['raw'] = raw_bag(root)
    data['inputs_unchanged'] = before == {n: digest((root / n).read_bytes()) for n in files}
    return data


def history_reason(expected, actual, entries):
    for channel in (0, 1):
        if expected['known'][channel] is not True or actual['known'][channel] is not True:
            return 'unknown_anchor'
        if not finite(expected['n'][channel]) or not finite(actual['n'][channel]):
            return 'unknown_anchor'
        if actual['n'][channel] != expected['n'][channel]:
            return 'anchor_mismatch'
        if actual['sequence'][channel] < expected['sequence'][channel] or actual['publish_ns'][channel] < expected['publish_ns'][channel]:
            return 'anchor_history_incomplete'
        if actual['sequence'][channel] == expected['sequence'][channel]:
            if actual['publish_ns'][channel] != expected['publish_ns'][channel]:
                return 'anchor_history_incomplete'
            continue
        relevant = [e for e in entries if e['channel'] == channel and
                    expected['sequence'][channel] <= e['sequence'] <= actual['sequence'][channel]]
        if not relevant:
            return 'anchor_history_incomplete'
        prev = None
        for seq, e in enumerate(relevant, expected['sequence'][channel]):
            if e['known'] is not True or not finite(e['n']):
                return 'unknown_anchor'
            if e['n'] != expected['n'][channel]:
                return 'anchor_history_changed'
            if e['sequence'] != seq or prev is not None and e['publish_ns'] <= prev:
                return 'anchor_history_incomplete'
            prev = e['publish_ns']
        if (relevant[0]['publish_ns'] != expected['publish_ns'][channel]
                or relevant[-1]['publish_ns'] != actual['publish_ns'][channel]
                or relevant[-1]['sequence'] != actual['sequence'][channel]):
            return 'anchor_history_incomplete'
    return ''


def anchor(row):
    return {'known': row['known'], 'n': row['final_n'],
            'sequence': [row['sequence']] * 2, 'publish_ns': row['publish_ns']}


def version_job(j):
    return {k: j[k + '_generation'] for k in ('task', 'model', 'config', 'schedule')} | {'epoch': j['clock_epoch']}


def analyze(data, contract):
    issues, joined = [], []
    def check(ok, code, **detail):
        if not ok:
            issues.append({'code': code, **detail})
        return bool(ok)
    def index(rows, typ, get):
        selected = [r for r in rows if r['type'] == typ]
        result = {get(r): r for r in selected}
        check(len(result) == len(selected), 'duplicate_' + typ)
        return result
    obs, worker, w, cfg = data['observer'], data['worker'], data['witness'], data['configuration']
    inp, raw = data['inputs'], data['raw']
    jobs = index(obs, 'job', lambda r: r['job']['job_id'])
    registrations = index(obs, 'candidate_registration', lambda r: r['job']['job_id'])
    receives = index(worker, 'job_received', lambda r: r['job']['job_id'])
    candidates = index(worker, 'candidate', lambda r: r['job']['job_id'])
    decisions = {r['job_id']: r for r in obs if r['type'] == 'decision' and r['job_id']}
    proofs = index(obs, 'anchor_validation', lambda r: r['job_id'])
    legacy = [r for r in obs if r['type'] == 'legacy_anchor']
    raw_applied = {r['sequence']: r for r in raw['/research/control/applied']}
    check(len(raw_applied) == len(raw['/research/control/applied']), 'duplicate_raw_applied')
    check([r['sequence'] for r in legacy] == list(range(1, len(legacy) + 1)), 'legacy_sequence_gap')
    for r in legacy:
        check(r['sequence'] in raw_applied and same(r['applied'], raw_applied[r['sequence']]),
              'raw_applied_projection', sequence=r['sequence'])
        a = r['applied']
        check(same(r['final_n'], a['final_n']) and same(r['known'], [a['left_publish_success'], a['right_publish_success']])
              and r['publish_ns'] == [a['left_publish_start_steady_ns'], a['right_publish_start_steady_ns']],
              'legacy_anchor_projection', sequence=r['sequence'])
    for collection in (registrations, receives, candidates):
        check(set(collection) == set(jobs), 'job_set_coverage')
        for jid in jobs.keys() & collection.keys():
            check(same(jobs[jid]['job'], collection[jid]['job']), 'immutable_job_echo', job_id=jid)
    helper = contract['helper']
    spec = importlib.util.spec_from_file_location('frozen_witness_helper', helper['path'])
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    old_gate = mod.analyze(w, data['header'])
    check(data['header']['run_id'] == inp['run_id']
          and data['header']['contract_sha256'] == inp['contract_sha256']
          and data['header']['binary_sha256'] == inp['builds']['observer']['binary_sha256']
          and data['header']['worker_binary_sha256'] == inp['builds']['worker']['binary_sha256']
          and data['header']['worker_instance'] == data['worker_manifest']['worker_instance'], 'independent_header_pins')
    expected_wids = set()
    for stream in ('activation', 'tick', 'submit'):
        rows = w[stream]
        check([r['sequence'] for r in rows] == list(range(1, len(rows) + 1)), 'witness_stream_sequence', stream=stream)
    wa = {r['job_id']: r for r in w['activation']}
    wt = {r['job_id']: r for r in w['tick'] if r['candidate_present']}
    ws = {r['job_id']: r for r in w['submit']}
    check(len(wa) == len(w['activation']), 'duplicate_witness_activation')
    check(set(proofs) == set(decisions) == set(wa) == set(wt), 'activation_attempt_sets')
    check(set(ws) == set(jobs), 'witness_submit_sets')
    ready = [r for r in obs if r['type'] == 'legacy_ready']
    check(len(ready) == 1, 'legacy_readiness_once')
    check(not any(r['type'] in ('legacy_ready_failed', 'legacy_ready_invalidated', 'scheduler_skipped_ticks') for r in obs), 'run_readiness_or_schedule_invalidated')
    for jid, d in sorted(decisions.items()):
        if jid not in jobs or jid not in proofs or jid not in wa or jid not in wt or jid not in ws:
            continue
        before_count = len(issues)
        jr, p, a, tick, submit = jobs[jid], proofs[jid], wa[jid], wt[jid], ws[jid]
        j, reg, wc, wr = jr['job'], registrations[jid], candidates[jid], receives[jid]
        v, f = d['d0_observation']['validation_snapshot'], d['d0_observation']['final_snapshot']
        def latest(rows, field, cutoff):
            eligible = [r for r in rows if r[field] <= cutoff]
            if not eligible:
                raise ValueError('missing current provenance: ' + field)
            return max(eligible, key=lambda r: r[field])
        frozen_anchor_row = latest(legacy, 'processed_ns', j['freeze_ns'])
        validation_anchor_row = latest(legacy, 'processed_ns', v['copy_capture_ns'])
        actual_anchor_row = latest(legacy, 'processed_ns', d['activation_commit_ns'])
        expected, validation, actual = anchor(frozen_anchor_row), anchor(validation_anchor_row), anchor(actual_anchor_row)
        job_anchor = {'known': j['anchor_known'], 'n': j['anchor_n'], 'sequence': j['anchor_sequence'], 'publish_ns': j['anchor_publish_ns']}
        proof_expected = {k: p['expected_' + k] for k in ('known', 'n', 'sequence', 'publish_ns')}
        proof_actual = {k: p['actual_' + k] for k in ('known', 'n', 'sequence', 'publish_ns')}
        check(same(expected, job_anchor) and same(expected, proof_expected), 'expected_anchor_actual_applied_join', job_id=jid)
        check(same(validation, v['anchor']), 'validation_anchor_actual_applied_join', job_id=jid)
        check(same(actual, proof_actual), 'final_anchor_actual_applied_join', job_id=jid)
        entries, validation_entries = [], []
        for r in legacy:
            for ch in (0, 1):
                e = {'channel': ch, 'sequence': r['sequence'], 'publish_ns': r['publish_ns'][ch], 'n': r['final_n'][ch], 'known': r['known'][ch]}
                if expected['sequence'][ch] <= e['sequence'] <= actual['sequence'][ch]: entries.append(e)
                if expected['sequence'][ch] <= e['sequence'] <= validation['sequence'][ch]: validation_entries.append(e)
        check(same(entries, p['entries']), 'complete_publication_entry_join', job_id=jid)
        independently_reconstructed_history = history_reason(expected, actual, entries)
        validation_history = history_reason(expected, validation, validation_entries)
        check(p['history_reason'] == independently_reconstructed_history, 'history_reason_semantics', job_id=jid)
        for k in ('task', 'model', 'config', 'schedule', 'epoch'):
            dk = k + '_generation' if k != 'epoch' else 'epoch'
            check(j[k + '_generation' if k != 'epoch' else 'clock_epoch'] == d[dk]
                  and j[k + '_generation' if k != 'epoch' else 'clock_epoch'] == a[k + '_generation' if k != 'epoch' else 'clock_epoch'], 'identity_version_join', job_id=jid, field=k)
        check(same(version_job(j), v['version']) and same(v['version'], f['version']), 'snapshot_version_join', job_id=jid)
        check(j['nominal_hash'] == cfg['nominal_hash'] == data['worker_manifest']['nominal_hash']
              and j['contract_hash'] == inp['contract_sha256'] and j['run_id'] == inp['run_id']
              and j['worker_instance'] == data['header']['worker_instance']
              and j['N'] == 20 and j['dt'] == 0.2 and exact_vector(j['reference'], 126), 'job_configuration_identity', job_id=jid)
        check(a['tick'] == d['tick'] == j['target_tick'] == tick['tick']
              and submit['target_tick'] == j['target_tick'] and submit['tick'] + 1 == j['target_tick']
              and a['commit_ns'] == p['check_ns'] == d['activation_commit_ns']
              and a['ready_commit_ns'] == d['ready_commit_ns'] == reg['ready_commit_ns']
              and jr['submit_commit_ns'] <= submit['commit_ns'] <= jr['publish_start_ns'], 'witness_time_identity_join', job_id=jid)
        ordering = [j['freeze_ns'], jr['submit_commit_ns'], wr['receive_ns'], wc['solve_start_ns'], wc['solve_end_ns'], reg['ready_commit_ns'], j['deadline_ns'], j['target_ns'], d['activation_commit_ns'], tick['end_ns']]
        check(ordering == sorted(ordering), 'native_deadline_activation_order', job_id=jid)
        check(a['accepted'] is d['accepted'] and a['reason_code'] == (0 if d['accepted'] else 1 if d['reason'] == 'shutdown' else 2 if d['reason'] == 'run_unusable_at_commit' else 3), 'witness_activation_reason_join', job_id=jid)
        check(p['decision_reason'] == d['reason'] and p['accepted'] is d['accepted'], 'proof_decision_join', job_id=jid)
        # Reconstruct predecessor observations, rather than trusting reason text.
        now = d['start_ns']
        od = latest([r for r in obs if r['type'] == 'odom_admission' and r['valid']], 'receive_ns', v['copy_capture_ns'])
        clock = latest([r for r in obs if r['type'] == 'clock'], 'receive_ns', v['copy_capture_ns'])
        path = latest([r for r in obs if r['type'] == 'path_version'], 'processed_ns', v['copy_capture_ns'])
        profile = latest([r for r in obs if r['type'] == 'profile_version'], 'processed_ns', v['copy_capture_ns'])
        rp = raw['/path/reference'][path['received_sequence'] - 1]
        rf = raw['/path/reference_profile'][profile['received_sequence'] - 1]
        check(v['odom_sequence'] == od['accepted_sequence'] and v['odom_stamp_ns'] == od['stamp_ns']
              and v['odom_receive_ns'] == od['receive_ns'] and same(v['state'], od['state'])
              and v['clock_sim_ns'] == clock['sim_ns'] and v['clock_receive_ns'] == clock['receive_ns'], 'validation_source_provenance', job_id=jid)
        pre = []
        def gate(ok, why):
            pre.append({'gate': why, 'passed': bool(ok)})
            return bool(ok)
        gate(v['odom_sequence'] > 0 and 0 <= now - v['odom_receive_ns'] <= cfg['odom_age_ns'], 'odom_input_age')
        gate(path['valid'] is True and path['points'] > 0 and path['resource_valid'] is True
             and all(all(finite(x) for x in point) for point in rp['points']), 'path_input_valid')
        gate(exact_vector(v['state'], 6), 'finite_state')
        if v['r_from_imu']:
            gate(0 <= now - v['imu_receive_ns'] <= cfg['imu_age_ns'] and abs(v['imu_stamp_ns'] - v['odom_stamp_ns']) <= cfg['mixed_skew_ns'], 'mixed_source_age_or_skew')
        gate(v['clock_receive_ns'] > 0 and 0 <= now - v['clock_receive_ns'] <= cfg['clock_age_ns'] and not v['paused'], 'clock_missing_stale_paused')
        gate(v['rtf_valid'] is True, 'rtf_unaligned')
        extrapolated = v['clock_sim_ns'] + now - v['clock_receive_ns']
        lag = extrapolated - v['odom_stamp_ns']
        gate(0 <= now - v['odom_receive_ns'] <= cfg['odom_age_ns'] and -cfg['source_future_slack_ns'] <= lag <= cfg['odom_sim_lag_ns'], 'odom_source_physical_age')
        if v['r_from_imu']:
            ilag = extrapolated - v['imu_stamp_ns']
            gate(0 <= now - v['imu_receive_ns'] <= cfg['imu_age_ns'] and -cfg['source_future_slack_ns'] <= ilag <= cfg['imu_sim_lag_ns'], 'imu_source_physical_age')
        gate(profile['valid'] is True and profile['rows'] == len(rp['points']) and rf['stamp'] == rp['stamp'] and rf['dims'] == [len(rp['points']), 4], 'profile_pair_incomplete')
        gate(all(validation['known']), 'unknown_anchor')
        gate(len(ready) == 1 and ready[0]['readiness']['legacy_ready_ns'] <= now, 'legacy_not_ready')
        gate(now - d['planned_ns'] <= cfg['tick_jitter_ns'], 'tick_jitter')
        gate(same(version_job(j), v['version']), 'version_mismatch')
        pre_failed = next((r['gate'] for r in pre if not r['passed']), None)
        if pre_failed:
            independent_first_reason = 'predecessor:' + pre_failed
        elif validation_history:
            independent_first_reason = validation_history
        elif not d['d0_observation']['predict_success']:
            independent_first_reason = 'activation_history_or_time'
        else:
            independent_first_reason = ''
        # A current anchor changed at commit could also be an earlier guard.
        if not independent_first_reason and independently_reconstructed_history:
            independent_first_reason = independently_reconstructed_history
        check(independent_first_reason == d['reason'], 'first_rejection_order', job_id=jid,
              independent=independent_first_reason, recorded=d['reason'])
        ob = d['d0_observation']
        if ob['full_error_available']:
            error = [ob['predicted_state'][k] - j['target_state'][k] for k in range(6)]
            error[2] = math.atan2(math.sin(error[2]), math.cos(error[2]))
            check(all(abs(x - y) <= 1e-12 for x, y in zip(error, ob['full_error'])), 'observed_full_error_arithmetic', job_id=jid)
        check(ob['input_change_gate_ran'] is (not bool(independent_first_reason)), 'downstream_input_gate_order', job_id=jid)
        joined.append({'job_id': jid, 'tick': d['tick'], 'decision_sequence': d['sequence'],
                       'expected_anchor': expected, 'validation_anchor': validation, 'actual_anchor': actual,
                       'publication_entries': entries, 'validation_publication_entries': validation_entries,
                       'true_n_changed': [actual['n'][k] != expected['n'][k] for k in (0, 1)],
                       'sequence_advances': [actual['sequence'][k] - expected['sequence'][k] for k in (0, 1)],
                       'freeze_ns': j['freeze_ns'], 'candidate_ready_ns': reg['ready_commit_ns'],
                       'deadline_ns': j['deadline_ns'], 'target_ns': j['target_ns'],
                       'activation_commit_ns': d['activation_commit_ns'],
                       'actual_publication_minus_freeze_ns': [actual['publish_ns'][k] - j['freeze_ns'] for k in (0, 1)],
                       'candidate_deadline_margin_ns': j['deadline_ns'] - reg['ready_commit_ns'],
                       'activation_minus_target_ns': d['activation_commit_ns'] - j['target_ns'],
                       'version': version_job(j), 'nominal_hash': j['nominal_hash'],
                       'reference_sha256_canonical_json': digest(canonical(j['reference']).encode()),
                       'reference': j['reference'], 'target_state': j['target_state'],
                       'full_error_observed': ob['full_error'], 'prediction_status_observed': ob['predict_status'],
                       'predecessor_gates': pre, 'validation_history_reason': validation_history,
                       'final_history_reason': independently_reconstructed_history,
                       'independent_first_reason': independent_first_reason,
                       'recorded_reason': d['reason'], 'accepted': d['accepted'],
                       'witness_activation': a, 'row_checks_passed': len(issues) == before_count})
    accepted = sum(r['accepted'] is True for r in w['activation'])
    all_rejected = bool(w['activation']) and accepted == 0
    semantic_allowed = {'business_ready_count', 'complete_flag_disagrees'} if all_rejected else set()
    residual = [i for i in old_gate['issues'] if i['code'] not in semantic_allowed]
    check(not residual, 'fixed_ring_integrity_residual', residual=residual)
    business = [p for p in w['phase'] if p['event_code'] == 9]
    if all_rejected:
        check(len(business) == 0, 'all_rejected_business_ready_must_be_absent')
        check([i['code'] for i in old_gate['issues']] == ['business_ready_count', 'complete_flag_disagrees'], 'legacy_semantic_disagreement_exact')
    check(w['audit_complete'] is True and w['closed'] is True and w['overflow'] is False and w['incomplete'] is False, 'fixed_storage_integrity_flags')
    check(data['inputs_unchanged'], 'input_changed_during_read')
    unattempted = sorted(set(jobs) - set(decisions))
    for jid in unattempted:
        check(any(p['event_code'] == 5 and p['candidate_present'] is True for p in w['phase']), 'unattempted_candidate_requires_stopping_phase', job_id=jid)
    return {'schema': SCHEMA, 'scope': 'offline_all_rejected_activation_policy_component',
            'run_id': inp['run_id'], 'original_locked_artifact': data['original'],
            'copied_evidence': not data['original'], 'inputs_unchanged': data['inputs_unchanged'],
            'input_sha256': data['input_sha256'], 'joins_passed': not issues,
            'all_rejected_scope_matched': all_rejected,
            'protocol_component_passed': all_rejected and not issues,
            'scope_rejection': None if all_rejected else 'accepted_activation_present_comparison_case',
            'issues': issues, 'joined_activations': joined,
            'counts': {'jobs': len(jobs), 'decisions': len([r for r in obs if r['type'] == 'decision']),
                       'activation_attempts': len(w['activation']), 'accepted': accepted,
                       'BusinessReady': len(business), 'unattempted_terminal_jobs': unattempted},
            'legacy_checker_result_unchanged': old_gate,
            'storage_integrity_semantics': 'audit_complete is closed committed slots without overflow/incomplete; never implies BusinessReady/accepted business coverage',
            'normal_contract_qualified': False, 'shared_v2_full_chain_qualified': False,
            'independent_nominal_qualified': False, 'D1_dynamic_qualified': False,
            'B4_qualified': False, 'M0b_qualified': False, 'execute_qualified': False}


def write_create_only(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        contract, lock = load_contract()
        root = Path(args.run)
        entry = next(v for v in lock['cases'].values() if v['root'] == str(root))
        for n, pin in entry['files'].items():
            if digest((root / n).read_bytes()) != pin['sha256']:
                raise ValueError('original artifact pin mismatch: ' + n)
        report = analyze(load_run(root, contract), contract)
        for n, pin in entry['files'].items():
            if digest((root / n).read_bytes()) != pin['sha256']:
                raise ValueError('original artifact changed after audit: ' + n)
    except Exception as error:
        report = {'schema': SCHEMA, 'protocol_component_passed': False, 'joins_passed': False,
                  'issues': [{'code': 'audit_input_or_join_error', 'detail': type(error).__name__ + ': ' + str(error)}],
                  'normal_contract_qualified': False, 'execute_qualified': False}
    write_create_only(args.output, report)
    print(json.dumps({k: report.get(k) for k in ('run_id', 'protocol_component_passed', 'joins_passed', 'scope_rejection', 'issues')}))
    return 0 if report.get('joins_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
