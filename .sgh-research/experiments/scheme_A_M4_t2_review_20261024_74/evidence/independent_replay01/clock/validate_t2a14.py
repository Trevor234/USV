#!/usr/bin/env python3
"""Read-only replay of already-finished T2A_14. Never initializes ROS.

Uses sqlite mode=ro. Optional ROS imports only deserialize stored CDR bytes.
Only --output may write, and it is restricted to /tmp/review72_clock_audit.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72')
TREE = ROOT / 'implementation/t2_author_rev8'
RUN = ROOT / 'implementation/runs/T2A_14'
sys.path.insert(0, str(TREE))
import audit_t2
import t2_action_contract as t2
import w2_audit_common as common


def read(path):
    return json.loads(Path(path).read_bytes())


def rows(path):
    return [(i, json.loads(s)) for i, s in enumerate(Path(path).read_text().splitlines(), 1) if s.strip()]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_check(fn):
    try:
        return {'passed': True, 'result': fn()}
    except Exception as exc:
        return {'passed': False, 'error_type': type(exc).__name__, 'reason': str(exc)}


def audit_bool(checks):
    return all(v is True for v in checks.values() if isinstance(v, bool))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    regpath = ROOT / 'implementation/T2A_registration_v11.json'
    reg, table = read(regpath), read(RUN / 'action_table_copy.json')
    registry, contract = read(reg['registry']), read(reg['contract'])
    rr, wr, fr = rows(RUN / 'regulator/source.jsonl'), rows(RUN / 'worker/source.jsonl'), rows(RUN / 'fixture/nominal_steps.jsonl')
    regulator = [x for _, x in rr]
    worker = [x for _, x in wr]
    types = common.by_type(regulator)
    ds = {x['sequence']: (i, x) for i, x in rr if x['type'] == 'decision'}
    receipts = [(i, x) for i, x in fr if x.get('type') == t2.RECEIPT_TYPE]
    hold, resume = receipts[0][1]['executed_ns'], receipts[1][1]['executed_ns']
    clocks = [(i, x) for i, x in rr if x['type'] == 'clock']
    before = [(i, x) for i, x in clocks if x['receive_ns'] < hold][-1]
    after = [(i, x) for i, x in clocks if x['receive_ns'] > resume][0]
    manifests = {role: read(RUN / role / ('owned_manifest.json' if role == 'fixture' else 'manifest.json'))
                 for role in ['worker', 'regulator', 'fixture', 'recorder']}
    witness, driver = read(RUN / 'regulator/witness.json'), read(RUN / 'driver_result.json')

    out = {'schema': 'private-read-only-T2A14-audit-v1', 'script': str(Path(__file__).resolve()),
           'root': str(ROOT), 'run_resolved_from_registration': reg['output'],
           'scope': 'finished artifacts only; no ROS init/spawn, signals, owned rerun, or input mutation',
           'input_identity': {'registration_sha256': digest(regpath),
                              'registration_pin_matches_driver': digest(regpath) == read(RUN / 'driver_manifest.json')['registration_sha256'],
                              'registration_copy_semantically_equal': reg == read(RUN / 'registration_copy.json'),
                              'action_table_pin_matches': digest(reg['action_table']) == reg['action_table_sha256'] == digest(RUN / 'action_table_copy.json'),
                              'registry_pin_matches': digest(reg['registry']) == reg['registry_sha256'],
                              'audit_tool_pin_matches': digest(reg['audit_tool']['path']) == reg['audit_tool']['sha256'],
                              'contract_pin_matches': digest(reg['contract']) == reg['contract_sha256']},
           'frozen_audit': audit_t2.audit_run(RUN, table)}

    # Reproduce false-positive audit paths entirely in memory.
    original_rows = audit_t2.rows
    receipt_rows = [x for _, x in receipts]
    minimal = [{'type': 'arbitrary_row', 'processed_ns': hold + 1}]
    try:
        audit_t2.rows = lambda p: receipt_rows if str(p).endswith('fixture/nominal_steps.jsonl') else minimal if str(p).endswith('regulator/source.jsonl') else []
        minimal_checks = audit_t2.audit_run(RUN, table)
        forged = json.loads(json.dumps(receipt_rows))
        forged[0].update(action='not_clock_hold', command_sha256='0' * 64,
                         parameters={'duration_ms': 50, 'mode': 'same_stamp'})
        audit_t2.rows = lambda p: forged if str(p).endswith('fixture/nominal_steps.jsonl') else minimal if str(p).endswith('regulator/source.jsonl') else []
        forged_checks = audit_t2.audit_run(RUN, table)
    finally:
        audit_t2.rows = original_rows
    out['in_memory_false_positive_reproductions'] = {
        'two_real_receipts_plus_one_arbitrary_regulator_row': {'all_audit_booleans': audit_bool(minimal_checks), 'checks': minimal_checks,
           'removed_evidence': ['decisions', 'clock', 'candidate', 'API', 'witness', 'identity', 'role closure', 'Source summary', 'Stored bag']},
        'wrong_action_digest_mode_duration_receipt': {'all_audit_booleans': audit_bool(forged_checks), 'checks': forged_checks}}

    wt = witness['tick']
    violations = []
    for p, n in zip(wt, wt[1:]):
        if n['schedule_generation'] == p['schedule_generation'] and n['tick'] != p['tick'] + 1 + n['skipped_ticks']:
            violations.append({'predicate': 'p1_witness.hpp:403-405', 'previous': p, 'next': n,
                               'expected_next_tick': p['tick'] + 1 + n['skipped_ticks']})
    out['witness_structural_failure'] = {'records_consistent_false_violation': violations,
         'observation_complete': witness['observation_complete'], 'normal_contract_qualified': witness['normal_contract_qualified'],
         'incomplete': witness['incomplete'], 'overflow': witness['overflow'], 'first_failure': witness['first_failure'],
         'reason_first_failure_zero': 'records_consistent() returns false without calling failure(); first_failure only records append/lifecycle/write failure paths',
         'return_code_path': ['p1_witness.hpp:314', 'regulator_owned_execute.cpp:316', 'regulator_owned_execute.cpp:1302']}

    out['clock_scenario_observed'] = {'hold_ns': resume - hold, 'hold_receipt_line': receipts[0][0], 'resume_receipt_line': receipts[1][0],
         'last_pre_hold_clock_line': before[0], 'first_resumed_clock_line': after[0],
         'last_clock_receive_ns': before[1]['receive_ns'], 'first_resumed_receive_ns': after[1]['receive_ns'],
         'receive_delta_ns': after[1]['receive_ns'] - before[1]['receive_ns'],
         'sim_delta_ns': after[1]['sim_ns'] - before[1]['sim_ns'],
         'uncompensated_first_ratio': (after[1]['sim_ns'] - before[1]['sim_ns']) / (after[1]['receive_ns'] - before[1]['receive_ns']),
         'clock_rows_during_hold': sum(hold <= x['receive_ns'] < resume for _, x in clocks),
         'accepted_pre_hold': [x['sequence'] for _, x in ds.values() if x['accepted'] and x['activation_commit_ns'] < hold],
         'accepted_post_hold': [x['sequence'] for _, x in ds.values() if x['accepted'] and x['activation_commit_ns'] >= hold],
         'late_decisions': [{'source_line': i, 'sequence': d['sequence'], 'tick': d['tick'], 'schedule_generation': d['schedule_generation'],
                            'reason': d['reason'], 'clock_age_ns': d['clock_age_ns'],
                            'paused_in_snapshot': d['d0_observation']['activation_alignment']['attempts'][0]['raw_snapshot']['paused']}
                           for i, d in ds.values() if d['sequence'] >= 8],
         'scope_limits': ['silent mode exercised; same_stamp freshness not exercised', 'no resumed new Job/window/accepted activation before shutdown',
                          'absence of old revival is observed; a successful recovery is not observed']}

    prior, failed = ds[11][1], ds[12][1]
    out['resume_history_authority_failure'] = {
        'source_failure_rows': [{'source_line': i, **x} for i, x in rr if x['type'] == 'owned_pair_policy_failed'],
        'previous_sequence': 11, 'previous_publish_sim_ns': prior['publish_sim_ns'],
        'failed_sequence': 12, 'failed_publish_sim_ns': failed['publish_sim_ns'],
        'failed_job_id': failed['job_id'], 'failed_candidate_capture': failed['d0_observation']['candidate_capture'],
        'left_vs_previous_right_regression_ns': prior['publish_sim_ns'][1] - failed['publish_sim_ns'][0],
        'failed_publish_success': failed['publish_success'], 'failed_publish_start_ns': failed['publish_start_ns'], 'failed_publish_end_ns': failed['publish_end_ns'],
        'history_anchor_known_after_seq12': failed['anchor_known'], 'history_anchor_sequence_after_seq12': failed['anchor_sequence'],
        'independent_authority_expected_known_after_two_successes': [True, True],
        'causal_code': ['regulator_owned_execute.cpp:952-958 extrapolates stale clock sim and appends successful per-side history',
                       'regulator_owned_execute.cpp:843 clears both anchor known flags on a backward history timestamp',
                       'right successful call restores right known flag after the left regression cleared both',
                       'owned_execution_policy_native_v1.hpp:115-125 independently records both successes as known',
                       'regulator_owned_execute.cpp:1221 throws before API/Applied emission at 1224-1230',
                       'regulator_owned_execute.cpp:963 catches and sets stop_requested=true',
                       'regulator_owned_execute.cpp:1096-1099 observes requested stop at sequence13'],
        'last_accepted_ns': ds[7][1]['activation_commit_ns'],
        'first_zero_sequence': 8,
        'first_zero_after_last_accepted_ns': ds[8][1]['activation_commit_ns'] - ds[7][1]['activation_commit_ns'],
        'first_zero_after_hold_ns': ds[8][1]['activation_commit_ns'] - hold,
        'meaning': 'actual successful zero calls and shutdown are supported; shutdown is caused by authority/history failure, not demonstrated as a 600ms hold-expiry transition',
        'limited_fix_entries': ['make time/history invalidation and physical output authority anchors consistent on resume mapping',
                                'emit unconditional actual API facts before optional policy consistency checks, and preserve Applied accounting on failure',
                                'make schedule-generation and tick-reset observation ordering satisfy the witness predicate',
                                'freeze/register an explicit resume mapping and separately test new-window recovery; advance_ms 0..1000 can express a 600ms catch-up']}

    out['independent_common_checks'] = {
        'role_source_ELF_identity': run_check(lambda: common.check_role_identity(RUN, registry, manifests, reg, contract)),
        'API_full_stream': run_check(lambda: common.check_pair_stream(types['owned_API_pair'], contract)),
        'Source_flush': run_check(lambda: common.check_witness(RUN, regulator, 'T2A')),
        'bounded_shutdown': run_check(lambda: common.check_shutdown(regulator, contract))}
    out['role_closure'] = driver['closed_roles']
    out['source_counts'] = {'regulator_summary': types['source_summary'][0],
                            'worker_summary': common.by_type(worker)['worker_summary'][0],
                            'decision_sequences': list(ds), 'API_sequences': [x['sequence'] for x in types['owned_API_pair']],
                            'Applied_sequences': [x['sequence'] for x in types['owned_applied_publication']]}
    connection = sqlite3.connect('file:' + str(RUN / 'recorder/bag/bag_0.db3') + '?mode=ro', uri=True)
    tt = {i: (name, typ) for i, name, typ in connection.execute('select id,name,type from topics')}
    counts, wire = collections.Counter(), collections.Counter()
    stored_rows = list(connection.execute('select id,topic_id,timestamp,data from messages order by id'))
    for _, tid, _, data in stored_rows:
        topic, _ = tt[tid]; counts[topic] += 1; wire[(topic, hashlib.sha256(data).hexdigest())] += 1
    out['Stored'] = {'integrity_check': connection.execute('pragma integrity_check').fetchone()[0], 'counts': dict(counts),
         'thrust_values': {side: [struct.unpack('<d', data[4:12])[0] for _, tid, _, data in stored_rows if tt[tid][0] == contract['output_topics'][side]]
                          for side in ['left', 'right']}}
    connection.close()
    try:
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        classes = {typ: get_message(typ) for _, typ in tt.values()}
        decoded = collections.defaultdict(list)
        for _, tid, _, data in stored_rows:
            name, typ = tt[tid]; decoded[name].append(common.norm(deserialize_message(data, classes[typ])))
        out['Stored']['Applied_sequences'] = [x['sequence'] for x in decoded['/research/control/applied']]
        out['Stored']['Decision_sequences'] = [x['sequence'] for x in decoded['/p1/execution_decision']]
        out['independent_common_checks'].update({
            'typed_Source_Stored': run_check(lambda: common.check_typed_equality(decoded, regulator, worker, manifests, contract)),
            'capability_Source_Stored': run_check(lambda: common.check_capability_source_vs_stored(decoded, worker)),
            'wire_GID_Stored': run_check(lambda: common.check_wire(RUN, decoded, wire, common.check_publishers(manifests, contract)))})
    except ImportError as exc:
        out['Stored']['decode_unavailable'] = str(exc)
    ft, rec = read(RUN / 'fixture/terminal.json'), read(RUN / 'recorder/terminal.json')
    out['recorder'] = rec
    out['fixture_clock_counter_scope'] = {'declared_clock_publications': ft['published_counts']['/clock'],
        'actual_transport_clock': ft['transport_counts']['/clock'], 'Stored_clock': counts['/clock'],
        'suppressed_clock_steps': ft['published_counts']['/clock'] - counts['/clock'],
        'interpretation': 'Fixture count_ counts all 154 sensor/model steps; silent suppresses clock publish on 39 steps. This is a misleading publication counter, not evidence of 39 dropped clock messages.',
        'code': ['synthetic_source_m4.cpp:82', 'synthetic_source_m4.cpp:235', 'synthetic_source_m4.cpp:240']}
    cpp_stdout = Path(__file__).resolve().parent / 'replay_anchor.stdout.json'
    if cpp_stdout.is_file():
        replay = read(cpp_stdout)
        out['frozen_cpp_policy_offline_replay'] = {
            'source': 'replay_anchor.cpp', 'stdout': cpp_stdout.name,
            'all_Source_anchors_reproduced': all(x['replayed_history_known'] == x['Source_history_known'] and
                x['replayed_history_seq'] == x['Source_history_seq'] for x in replay),
            'authority_history_mismatches': [x for x in replay if not x['authority_equals_history']],
            'all_policy_ticks_pass': all(x['tick_ok'] for x in replay)}
    if args.output:
        target = args.output.resolve()
        if not target.is_relative_to(Path('/tmp/review72_clock_audit')):
            raise ValueError('output restricted to private /tmp/review72_clock_audit directory')
        target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
