#!/usr/bin/env python3
"""Independent W2 Source/Stored audit; no ROS init, signals, or new runs."""
from pathlib import Path
import argparse
import collections
import copy
import hashlib
import json
import sqlite3
import struct
import sys
import zlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import w2_audit_common as common


def require(value, message):
    if not value: raise AssertionError(message)


def w2_facts(reg, config, worker, regulator, driver):
    """Reconstruct target causality from raw rows, never Driver PASS flags."""
    wt, rt, dt = common.by_type(worker), common.by_type(regulator), common.by_type(driver)
    target, ordinal = reg['w2_release']['job_id'], reg['w2_release']['ordinal']
    entries = [x for x in wt['w2_boundary_entered'] if x['job_id'] == target]
    results = [x for x in wt['w2_boundary_result'] if x['job_id'] == target]
    writes = dt['w2_release_sent']
    jobs = {x['job']['job_id']: x['job'] for x in rt['job']}
    require(len(entries) == len(results) == len(writes) == 1, 'One target entry/result/release required')
    entry, result, write = entries[0], results[0], writes[0]
    b = result['boundary']; job = jobs[target]
    require(entry['ordinal'] == result['ordinal'] == b['ordinal'] == ordinal, 'Boundary ordinal mismatch')
    require(b['job_id'] == target and job['job_id'] == target, 'Boundary Job identity mismatch')
    require(b['released'] is True and b['gate_outcome'] == 'released', 'Release was not verified')
    require(result['disposition'] == b['disposition'] == 'expired', 'Target was not expired')
    deadline = job['tick_origin_ns'] + config['deadline_ns']
    require(deadline == job['deadline_ns'] == entry['job_deadline_ns'] == b['job_deadline_ns'], 'Original Job deadline changed')
    require(b['guard_ns'] > deadline and b['past_deadline_ns'] == b['guard_ns'] - deadline, 'Guard not past original deadline')
    require(result['actual_native_invoked'] is False and b['actual_native_invoked'] is False
            and b['ordinal_at_call'] == 0, 'Target entered C solve')
    require(b['entered_ns'] <= entry['entered_ns'] <= write['write_start_ns'] <= b['released_ns'] <= b['guard_ns'], 'Release/guard causality mismatch')
    require(write['write_end_ns'] >= write['write_start_ns'] and write['write_end_ns'] - b['entered_ns'] < config['active_watchdog_ns'], 'Release exceeded original watchdog window')
    raw = bytes.fromhex(write['frame_hex'])
    require(len(raw) == write['written_bytes'] == write['frame_len'] == 44, 'Release frame length/actual write mismatch')
    header = struct.unpack('<IHHQQIIQ', raw[:40])
    require(header == (0x4C523257, 1, 0, 1, target, ordinal, reg['w2_release']['nonce'], 1), 'Release frame identity mismatch')
    require(int.from_bytes(raw[40:], 'little') == zlib.crc32(raw[:40]) & 0xFFFFFFFF, 'Release CRC mismatch')
    require(hashlib.sha256(raw).hexdigest() == write['frame_sha256'], 'Release SHA mismatch')
    require(not rt['active_watchdog'], 'W2 took the watchdog path')
    for transition in rt['worker_unusable_transition']:
        require(transition['reason'] == reg['expected']['w2_isolation_reason']
                and transition['processed_ns'] >= b['guard_ns'], 'Unrelated/early isolation')
    terminals = [x for x in wt['terminal_exception'] if x['job_id'] == target]
    require(len(terminals) == 1 and terminals[0]['reason'] in reg['expected']['w2_terminal_reasons'], 'Wrong target terminal fact')
    policies = [x['metadata'] for x in wt['cold_start_policy_failure'] if x['job_id'] == target]
    require(len(policies) == 1 and policies[0]['terminal'] is True
            and policies[0]['actual_C_solve_calls_this_job'] == 0, 'Target native-policy count/terminal mismatch')
    require(policies[0]['w2_boundary'] == b, 'Policy and boundary facts differ')
    require(all(x['job']['job_id'] != target for x in wt['candidate']), 'Target generated a candidate')
    require(all(x['job_id'] != target for x in wt['candidate_publish_result']), 'Target attempted candidate publish')
    require(all(x['job']['job_id'] != target for x in rt['candidate_registration']), 'Target candidate registered')
    require(all(not(x.get('job_id') == target and x.get('accepted')) for x in rt['decision']), 'Target candidate activated')
    pairs = {x['tick']: x for x in rt['owned_API_pair'] if x['kind'] != 'shutdown'}
    ticks = []
    for decision in rt['decision']:
        pair = pairs.get(decision['tick'])
        if (pair and decision['reason'] != 'shutdown' and decision['start_ns'] >= entry['entered_ns']
                and decision['end_ns'] > decision['start_ns'] and pair['returned'] == [True, True]
                and pair['sequence'] == decision['sequence']
                and max(pair['ends']) <= write['write_start_ns']):
            ticks.append(decision['tick'])
    require(len(set(ticks)) >= reg['w2_release']['ticks_before_release'], 'Insufficient complete API ticks before release')
    cap = [x for x in rt['capability_admission'] if x.get('renewed') is True]
    held = [x for x in cap if entry['entered_ns'] <= x['lease_last_after_ns'] <= write['write_end_ns']
            and x['capability']['active_job'] == target and x['capability']['fatal'] is False]
    require(held, 'No actual capability renewal while held')
    prior = [x['lease_last_after_ns'] for x in cap if x['lease_last_after_ns'] <= entry['entered_ns']]
    require(prior, 'No valid capability lease before entry')
    chain = [max(prior)] + sorted({x['lease_last_after_ns'] for x in held}) + [write['write_end_ns']]
    require(all(0 <= later - earlier <= config['worker_capability_receipt_timeout_ns']
                for earlier, later in zip(chain, chain[1:])), 'Heartbeat lease gap during hold')
    attempts = wt['capability_publish_attempt']
    require(attempts and all(0 <= x['payload']['pending_count'] <= 1 for x in attempts), 'Pending mailbox bound violated')
    require(any(x['payload']['fatal'] is True and x['payload']['active_job'] == 0
                and x['payload']['pending_count'] == 0 for x in attempts), 'No final active/pending clear capability')
    ready = set(); max_ready = 0
    for row in regulator:
        if row['type'] == 'candidate_registration' and row.get('accepted_registration'):
            ready.add(row['job']['job_id']); max_ready = max(max_ready, len(ready))
        elif row['type'] == 'decision' and row.get('accepted'):
            ready.discard(row['job_id'])
        elif row['type'] == 'worker_unusable_transition':
            require(row.get('candidate_after') is False, 'Isolation did not clear ready candidate')
            ready.clear()
    require(max_ready <= 1, 'Ready candidate bound exceeded')
    ledger = {}
    received = [x['job']['job_id'] for x in wt['job_received']]
    require(len(received) == len(set(received)), 'Duplicate received Job')
    for jid in received:
        outcomes = []
        outcomes += ['delivered'] * sum(x['job_id'] == jid and x['success'] is True for x in wt['candidate_publish_result'])
        outcomes += ['replaced'] * sum(x['job_id'] == jid for x in wt['pending_replaced'])
        outcomes += ['expired_before_native'] * sum(x['job_id'] == jid for x in wt['pending_expired_before_native'])
        outcomes += ['discarded'] * sum(x['job_id'] == jid for x in wt['pending_discarded'])
        if jid == target: outcomes += ['expired_at_boundary']
        require(len(outcomes) == 1, 'Job %s has terminal outcomes %r' % (jid, outcomes))
        require(jid in jobs, 'Worker received an unissued Job')
        ledger[str(jid)] = outcomes[0]
    for jid in jobs:
        if str(jid) not in ledger:
            rejected = [x for x in wt['job_rejected'] if x['job_id'] == jid]
            require(len(rejected) == 1, 'Issued Job %s has no unique receive/reject terminal' % jid)
            ledger[str(jid)] = 'rejected:' + rejected[0]['reason']
    discarded = [x['job_id'] for x in wt['pending_discarded']]
    require(not reg['expected']['pending_discard_required'] or discarded, 'Required pending discard not observed')
    require(ledger.get('1') == 'delivered', 'No delivered normal Job1 prefix')
    prefix = [x for x in wt['cold_start_policy_result'] if x['job_id'] == 1]
    require(len(prefix) == 1 and prefix[0]['metadata']['successful'] is True, 'Normal native prefix absent')
    require(any(x['kind'] == 'accepted' and max(x['ends']) <= write['write_start_ns'] for x in rt['owned_API_pair']), 'No accepted pair before release')
    summary = wt['worker_summary']
    require(len(summary) == 1 and summary[0]['fatal'] is True and not summary[0]['source_io_failed'], 'Worker summary incomplete')
    require(summary[0]['capability_source']['capability_source_complete'] is True, 'Worker capability source incomplete')
    require(summary[0]['generated_candidates'] == summary[0]['published_candidates'] == 1
            and summary[0]['dropped_candidates'] == 0 and summary[0]['completed_jobs'] == 1, 'Worker completion/publication accounting mismatch')
    return {'target_job': target, 'target_C_calls': 0, 'complete_ticks': sorted(set(ticks)),
            'held_renewals': len(held), 'max_ready_candidates': max_ready,
            'ledger': ledger, 'pending_discarded': discarded,
            'guard_lateness_ns': b['guard_ns'] - deadline}


def audit(regfile):
    reg = common.read(regfile); config = common.read(reg['contract']); registry = common.read(reg['registry'])
    root = Path(reg['output'])
    report = {'schema': 'W2-independent-owned-audit-v1', 'registration_sha256': common.pin(regfile)['sha256'],
              'audit_tool_sha256': common.pin(__file__)['sha256'], 'checks': {},
              'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
              'plant_acceptance': False, 'hard_realtime': False}
    def check(name, fn):
        try:
            value = fn(); report['checks'][name] = {'passed': True, 'evidence': value}
        except Exception as exc:
            report['checks'][name] = {'passed': False, 'error_type': type(exc).__name__, 'reason': str(exc)}
    def context():
        require(common.pin(reg['registry'])['sha256'] == reg['registry_sha256'], 'Registry changed')
        require(common.pin(reg['contract'])['sha256'] == reg['contract_sha256'], 'Contract changed')
        require(report['audit_tool_sha256'] == reg['audit_tool']['sha256'], 'Audit tool differs from registration')
        dm = common.read(root / 'driver_manifest.json')
        require(dm['registration_sha256'] == report['registration_sha256'], 'Launch registration pin mismatch')
        require(dm['registry_sha256'] == reg['registry_sha256'], 'Launch registry pin mismatch')
        return dm
    check('registration_identity', context)
    try:
        result = common.read(root / 'driver_result.json')
        worker, _ = common.lines(root / 'worker/source.jsonl')
        regulator, _ = common.lines(root / 'regulator/source.jsonl')
        driver, _ = common.lines(root / 'driver_events.jsonl')
        manifests = {role: common.read(root / role / ('owned_manifest.json' if role == 'fixture' else 'manifest.json'))
                     for role in ['worker', 'regulator', 'fixture', 'recorder']}
    except Exception as exc:
        report['checks']['complete_run_artifacts'] = {'passed': False, 'error_type': type(exc).__name__, 'reason': str(exc)}
        report['owned_W2_qualified'] = False
        return report
    r = common.by_type(regulator)
    def driver_integrity():
        require(result.get('error') is None, 'Driver execution error: ' + str(result.get('error')))
        require(result['run_id'] == reg['run_id'], 'Driver result run identity mismatch')
        return {'no_execution_error': True, 'driver_pass_claim_not_used_as_case_evidence': True}
    check('driver_execution_integrity', driver_integrity)
    check('roles_and_shutdown_signals', lambda: common.check_roles(result, reg, 'W2'))
    check('role_source_ELF_identity', lambda: common.check_role_identity(root, registry, manifests, reg, config))
    check('diagnostic_contract', lambda: common.check_contract_identity(root, config, registry, manifests, reg))
    check('W2_independent_raw_facts', lambda: w2_facts(reg, config, worker, regulator, driver))
    check('API_full_stream', lambda: common.check_pair_stream(r['owned_API_pair'], config))
    check('decision_contract', lambda: common.check_decisions(r['decision'], config))
    check('Job_original_deadline_and_anchors', lambda: common.check_jobs([x['job'] for x in r['job']], r['owned_API_pair'], config, manifests))
    check('bounded_shutdown', lambda: common.check_shutdown(regulator, config))
    check('source_and_witness', lambda: common.check_witness(root, regulator, 'W2'))
    def runtime():
        loaded = common.read(root / 'worker_loaded_libraries.json')
        grant = common.read(root / 'regulator/grant.json')
        require(loaded['checked'] is True and loaded['pid'] == manifests['worker']['pid']
                and loaded['process_start_ticks'] == manifests['worker']['process_start_ticks'], 'Loaded library process mismatch')
        require(loaded['checked_ns'] < grant['issued_ns'], 'Runtime maps were checked after grant')
        require({x['library'] for x in loaded['libraries']} == set(registry['acados_runtime']), 'Missing runtime library evidence')
        for row in loaded['libraries']:
            expected = registry['acados_runtime'][row['library']]
            require(row['sha256'] == expected['sha256'] and row['bytes'] == expected['bytes'], 'Mapped runtime bytes mismatch')
            require(Path(row['path']).resolve() == Path(expected['path']).resolve(), 'Mapped runtime path mismatch')
        return {'libraries': len(loaded['libraries']), 'checked_before_grant': True}
    check('live_runtime_identity', runtime)
    try:
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        bags = list((root / 'recorder/bag').glob('*.db3'))
        require(len(bags) == 1, 'One closed sqlite bag required')
        db = sqlite3.connect('file:' + str(bags[0]) + '?mode=ro', uri=True)
        topic_types = {i: (name, typ) for i, name, typ in db.execute('select id,name,type from topics')}
        classes = {typ: get_message(typ) for _, typ in topic_types.values()}
        decoded, wire = collections.defaultdict(list), collections.Counter()
        for topic_id, data in db.execute('select topic_id,data from messages order by id'):
            name, typ = topic_types[topic_id]
            decoded[name].append(common.norm(deserialize_message(data, classes[typ])))
            wire[(name, hashlib.sha256(data).hexdigest())] += 1
        db.close()
        report['stored_bag'] = common.pin(bags[0])
        check('capability_Source_Stored_multiset', lambda: common.check_capability_source_vs_stored(decoded, worker))
        check('typed_Source_Stored', lambda: common.check_typed_equality(decoded, regulator, worker, manifests, config))
        check('wire_GID_Stored', lambda: common.check_wire(root, decoded, wire, common.check_publishers(manifests, config)))
        check('recorder_and_fixture_complete', lambda: common.check_recorder_and_fixture(root, decoded, config, 'W2'))
    except Exception as exc:
        report['checks']['stored_decode'] = {'passed': False, 'error_type': type(exc).__name__, 'reason': str(exc)}
    report['driver_passed_claim'] = result.get('passed')
    report['owned_W2_qualified'] = bool(report['checks']) and all(x['passed'] for x in report['checks'].values())
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registration', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.registration)
    with args.output.open('x') as f: json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps({'owned_W2_qualified': report['owned_W2_qualified'],
                      'failed_checks': [k for k, v in report['checks'].items() if not v['passed']],
                      'output': str(args.output)}, ensure_ascii=False))
    return 0 if report['owned_W2_qualified'] else 2


if __name__ == '__main__': raise SystemExit(main())
