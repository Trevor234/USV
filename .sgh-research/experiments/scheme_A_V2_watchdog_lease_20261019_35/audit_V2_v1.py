#!/usr/bin/env python3
"""Independent closed-raw V2 audit. No ROS context or control publication is created."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import traceback

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D / 'implementation'))
from audit_v2_core_v1 import check as check_core
PINS = {}


def need(value, why):
    if not value:
        raise ValueError(why)


def raw(p):
    p = Path(p)
    data = p.read_bytes()
    item = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    need(str(p) not in PINS or PINS[str(p)] == item, 'input_changed:' + str(p))
    PINS[str(p)] = item
    return data


def load(p):
    return json.loads(raw(p))


def rows(p):
    data = raw(p)
    need(data.endswith(b'\n'), 'incomplete_final_JSONL:' + str(p))
    return [json.loads(x) for x in data.splitlines()]


def parameter_digest(rows):
    result = {}
    for key, row in rows.items():
        v, t = row['value'], row['type']
        c = struct.pack('>d', v).hex() if t == 3 else [struct.pack('>d', x).hex() for x in v] if t == 8 else v
        need(type(c) is type(row['canonical_value']) and c == row['canonical_value'], 'typed_parameter:' + key)
        result[key] = {'type': t, 'canonical_value': c}
    return hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    need(args.run.replace('_', '').isalnum(), 'bounded_run_name')
    root = D / 'author/runs' / args.run
    population = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())
    for name in population:
        raw(root / name)
    lock = load(D / 'preflight/prerun_source_lock_v1.json')
    for name, expected in lock['files'].items():
        need({'bytes': len(raw(name)), 'sha256': hashlib.sha256(raw(name)).hexdigest()} == expected, 'prerun_input_changed:' + name)
    inputs, result = load(root / 'inputs.json'), load(root / 'result.json')
    source, worker = rows(root / 'observer/source.jsonl'), rows(root / 'worker/source.jsonl')
    witness, observation = load(root / 'observer/witness.json'), load(root / 'V2_observation.json')
    case = inputs['V2_case']
    manifests = {r: load(root / r / 'owned_manifest.json') for r in ['publisher', 'observer', 'worker', 'synthetic_source', 'recorder']}
    prepared = load(root / 'preparation_evidence.json')
    ledger = rows(root / 'owned_process_ledger.jsonl')
    sections = {}
    def section(name, fn):
        try:
            sections[name] = {'passed': True, 'details': fn()}
        except Exception as error:
            sections[name] = {'passed': False, 'error': repr(error), 'traceback': traceback.format_exc()}
    section('fault_local_component', lambda: check_core(case, source, worker, witness, observation))
    def identity_and_cleanup():
        need(result['passed'] is False and result['normal_business_qualified'] is False and result['V2_case'] == case,
             'ordinary_business_status_must_not_be_promoted')
        need(result['cleanup_complete'] and result['cleanup_within_budget'] and result['close_elapsed_ns'] <= 15_000_000_000
             and result['elapsed_ns'] <= 45_000_000_000 and not result['ledger_failed'], 'finite_clean_resource_close')
        need(result['owned_role_returncodes'] == {r: 0 for r in manifests}, 'all_owned_exit_zero_without_Source_failure')
        need(not any(r['type'] == 'signal' and r['signal'] != 2 for r in ledger), 'no_TERM_KILL_or_unregistered_signal')
        for role, manifest in manifests.items():
            prep = prepared['roles'][role]
            spawn = [r for r in ledger if r['type'] == 'spawn' and r['name'] == role]
            cleanup = [r for r in ledger if r['type'] == 'cleanup_result' and r['name'] == role]
            need(len(spawn) == len(cleanup) == 1, 'one_owned_lifecycle:' + role)
            need(hashlib.sha256(raw(root / role / 'owned_manifest.json')).hexdigest() == prep['manifest_sha256'], 'prepared_manifest:' + role)
            need(manifest['role'] == role and manifest['run_id'] == args.run + ('-publisher' if role == 'publisher' else '')
                 and manifest['boot_id'] == witness['header']['boot_id'] and manifest['contract_sha256'] == inputs['contract_sha256'], 'role_identity:' + role)
            for mk, ik in [('pid','pid'), ('process_start_ticks','start_ticks'), ('exe','exe'), ('binary_sha256','exe_sha256')]:
                need(manifest[mk] == spawn[0]['identity'][ik] == prep['owned'][ik], 'exact_spawn_identity:' + role + ':' + mk)
            need(hashlib.sha256(raw(manifest['exe'])).hexdigest() == manifest['binary_sha256'], 'selected_ELF:' + role)
            need(parameter_digest(manifest['effective_parameters']) == manifest['effective_parameters_sha256'] == prep['effective_parameters_sha256'], 'typed_config_digest:' + role)
            need({k: v['value'] for k, v in manifest['effective_parameters'].items()} == inputs['expected_parameters'][role], 'whole_expected_configuration:' + role)
            need(manifest['effective_parameters_immutable'] and not manifest['execute_qualified'], 'immutable_shadow_role')
            need(cleanup[0]['cleanup_complete'] and not cleanup[0]['remaining_members'] and not cleanup[0]['unexpected_descendants']
                 and cleanup[0]['returncode'] == 0, 'exact_owned_group_empty:' + role)
        need(witness['header'] == load(root / 'expected_witness_header.json'), 'Witness_exact_source_binary_worker_identity')
        w = manifests['worker']
        need(w['binary_sha256'] == witness['header']['worker_binary_sha256'] == lock['worker_binary_sha256'], 'same_selected_Worker_version')
        need(w['runtime_hook_values'] == {'test_delay_ms': 0, 'test_native_block_ms': 0} and prepared['external_worker_zero_hooks'], 'legacy_zero_hooks_are_truthful')
        p = w['effective_parameters']
        need(p['diagnostic_v2_policy']['value'] == ('pre_native_once_after_completed_v1' if case == 'active' else 'none')
             and p['diagnostic_v2_block_ms']['value'] == (1700 if case == 'active' else 0), 'explicit_V2_Worker_configuration')
        op = manifests['observer']['effective_parameters']
        need(op['diagnostic_v1_sink_policy']['value'] == 'none' and op['diagnostic_v1_fault_file']['value'] == ''
             and manifests['observer']['physical_publisher_endpoints'] == 0 and not (root / 'observer/v1_fault.json').exists(), 'Sink_fault_disabled_Observer_has_no_physical_outlet')
        need(all(op[k]['value'] == 0 for k in ['test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms','test_sink_pause_ms']), 'Observer_legacy_hooks_zero')
        need(prepared['owned_dds_endpoint_binding_verified'] and prepared['unique_dual_channel_owner']
             and prepared['native_applied_reader_matched_verified'] and prepared['native_capability_receivers_matched_verified'], 'actual_native_interface_authentication')
        return {'five_owned_roles_and_typed_configs_verified': True, 'all_groups_empty': True,
                'legacy_zero_hooks': True, 'explicit_Worker_diagnostic_profile': p['diagnostic_v2_policy']['value']}
    section('identity_configuration_owned_cleanup', identity_and_cleanup)
    def ordinary_close_protocol():
        need(result['V2_case_completed'] and result['evidence_qualification_clean'] and not result['close_errors'] and not result.get('error'), 'driver_evidence_and_close_complete')
        request = raw(root / 'adapter_driver_close_request.json')
        ack = load(root / 'adapter_driver_close_ack.json')
        need(ack['request_sha256'] == hashlib.sha256(request).hexdigest(), 'ordinary_close_request_ACK')
        tail = load(root / 'close_tail_ack.json')
        need(tail['receiver_roles_alive'] and tail['observer_last_applied_sequence'] == tail['publisher_last_applied_sequence'], 'ordinary_receiver_tail_capture')
        return {'ordinary_ACK_and_tail_receiver_flow_verified': True, 'normal_business_qualified': False,
                'tail_sequence': tail['publisher_last_applied_sequence']}
    section('ordinary_close_protocol', ordinary_close_protocol)
    def storage_and_command_chain():
        import yaml
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.convert import message_to_ordereddict
        from usv_research_interfaces.msg import AppliedControl, ExecutionDecision, WorkerCapability
        def decode(data, cls):
            return json.loads(json.dumps(message_to_ordereddict(deserialize_message(data, cls))))
        dbs = list((root / 'recorder/bag').glob('*.db3'))
        need(len(dbs) == 1, 'one_actual_closed_SQLite')
        db = sqlite3.connect(dbs[0].resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            need(db.execute('pragma integrity_check').fetchone()[0] == 'ok', 'SQL_integrity')
            data = db.execute('select t.name,m.data from messages m join topics t on m.topic_id=t.id order by m.id').fetchall()
            counts = {name: 0 for name, in db.execute('select name from topics')}
        finally:
            db.close()
        metadata_bytes = raw(root / 'recorder/bag/metadata.yaml')
        md = yaml.safe_load(metadata_bytes)['rosbag2_bagfile_information']
        for topic, _ in data:
            counts[topic] += 1
        need(counts == {r['topic_metadata']['name']: r['message_count'] for r in md['topics_with_message_count']}
             and len(data) == md['message_count'], 'all_SQL_metadata_counts')
        rt = load(root / 'recorder/terminal.json')
        need(rt['clean'] and rt['Recorder_stop_completed'] and rt['metadata_sha256'] == hashlib.sha256(metadata_bytes).hexdigest()
             and rt['manifest_sha256'] == prepared['roles']['recorder']['manifest_sha256'], 'Recorder_clean_storage_stop')
        transport = rows(root / 'synthetic_source/transport_source.jsonl')
        pub = rows(root / 'publisher/controlled_source.jsonl')
        gids = {}
        for role, topic in [('publisher','/research/control/applied'),('observer','/p1/execution_decision'),('worker','/p1/worker_capability')]:
            selected = [e['gid'] for e in manifests[role]['endpoints'] if e['kind'] == 'publisher' and e['topic'] == topic]
            need(len(selected) == 1, 'one_actual_writer_GID')
            gids[topic] = selected[0]
        selected = {topic: [] for topic in gids}
        for topic, wire in data:
            if topic in selected:
                h = hashlib.sha256(wire).hexdigest()
                need(any(r['topic'] == topic and r['payload_sha256'] == h and r['publisher_gid'] == gids[topic] for r in transport), 'Stored_Fixture_exact_wire_GID:' + topic)
                cls = AppliedControl if topic == '/research/control/applied' else ExecutionDecision if topic == '/p1/execution_decision' else WorkerCapability
                selected[topic].append(decode(wire, cls))
        decisions = selected['/p1/execution_decision']
        source_decisions = [r for r in source if r.get('type') == 'decision']
        need(len(decisions) == len(source_decisions), 'all_Source_Decisions_Stored')
        for src, msg in zip(source_decisions, decisions):
            need(src['run_id'] == msg['run_id'] == args.run and src['sequence'] == msg['sequence'] and src['tick'] == msg['tick']
                 and src['accepted'] == msg['candidate_accepted'] and src['job_id'] == msg['job_id']
                 and src['activation_commit_ns'] == msg['activation_commit_ns'] and src['final_n'] == msg['final_n'], 'Source_Stored_Decision_semantics')
        applied = selected['/research/control/applied']
        emissions = [r for r in pub if r.get('type') == 'controlled_Applied_emitted']
        need(len(applied) == len(emissions) and len(applied) > 1, 'complete_Applied_population')
        previous = None
        for row in emissions:
            wire = bytes.fromhex(row['cdr_hex'])
            need(len(wire) == row['cdr_bytes'] and hashlib.sha256(wire).hexdigest() == row['cdr_sha256'], 'Publisher_CDR_integrity')
            msg = decode(wire, AppliedControl)
            matches = [m for m in applied if m['run_id'] == msg['run_id'] and m['sequence'] == msg['sequence']]
            need(len(matches) == 1 and matches[0] == msg, 'Publisher_full_Applied_Stored_value')
            need(msg['run_id'] == manifests['publisher']['run_id'] and msg['left_publish_success'] and msg['right_publish_success']
                 and not msg['plant_acceptance_observed'] and not msg['force_measured'] and not msg['execution_atomicity_proven'], 'command_API_scope')
            need(all(-25 <= n <= 25 for n in msg['final_n']), 'command_amplitude')
            if previous:
                for side, name in enumerate(['left','right']):
                    gap = msg[name+'_publish_start_steady_ns'] - previous[name+'_publish_start_steady_ns']
                    need(gap > 0 and abs(msg['final_n'][side] - previous['final_n'][side]) <= 80 * gap / 1e9 + 1e-9, 'actual_API_start_rate_limit')
            previous = msg
        need(previous['control_source'] == 'shutdown_zero' and all(abs(n) <= 1e-9 for n in previous['final_n']), 'last_actual_shutdown_zero_command')
        ps = load(root / 'publisher/session_summary.json')
        need(ps['normal_end'] and ps['flushed'] and ps['publish_errors'] == 0 and ps['streams']['applied']['emitted'] == len(applied), 'Publisher_clean_session')
        actual_caps = selected['/p1/worker_capability']
        attempts = [r['payload'] for r in worker if r.get('type') == 'capability_publish_attempt']
        need(actual_caps and all(m['run_id'] == args.run and m['worker_instance'] == manifests['worker']['worker_instance']
                                and any(m == p for p in attempts) for m in actual_caps), 'Stored_capability_actual_Worker_payload')
        if case == 'active':
            job = sections['fault_local_component'].get('details', {}).get('details', {}).get('blocked_job_id')
            need(job is not None and len([m for m in actual_caps if m['active_job'] == job]) >= 3, 'blocked_active_job_actual_DDS_capabilities')
        raw(yaml.__file__)
        return {'Stored_messages': len(data), 'Stored_Decisions': len(decisions), 'Stored_Applied': len(applied),
                'Stored_capabilities': len(actual_caps), 'actual_GID_and_full_value_binding_verified': True,
                'shutdown_zero_sequence': previous['sequence'], 'command_amplitude_and_API_start_rate_verified': True,
                'Recorder_builtin_stream_accounting_claim': rt['storage_stream_accounting_verified'],
                'independent_SQL_metadata_verified': True, 'plant_or_force_acknowledgement': False}
    section('Stored_Fixture_actual_command_chain', storage_and_command_chain)
    before = dict(PINS)
    for p in before:
        raw(p)
    need(PINS == before and population == sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()), 'final_raw_integrity')
    report = {'schema': 'V2-independent-closed-raw-audit/v1', 'run': args.run, 'case': case,
              'audit_completed': True, 'passed': all(r['passed'] for r in sections.values()), 'sections': sections,
              'component_passed': sections['fault_local_component']['passed'],
              'driver_normal_business_passed': result['passed'], 'original_driver_errors': result.get('error'),
              'original_driver_close_errors': result['close_errors'], 'input_sha256_before': before, 'input_sha256_after': PINS,
              'normal_final_unified_version_qualified': False, 'stage_qualified': False, 'execute_qualified': False,
              'true_plant_qualified': False, 'research_conclusion': False}
    out = Path(args.output)
    need(out.parent == D / 'postrun' and not out.exists(), 'new_batch_audit_output_only')
    with out.open('x') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')
    print(json.dumps({'run': args.run, 'passed': report['passed'], 'component_passed': report['component_passed'],
                      'sections': {k: {'passed': v['passed'], 'error': v.get('error')} for k,v in sections.items()}, 'input_count': len(PINS)}, ensure_ascii=False))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        output = Path(sys.argv[sys.argv.index('--output') + 1])
        if output.parent == D / 'postrun' and not output.exists():
            with output.open('x') as f:
                json.dump({'audit_completed': False, 'passed': False, 'component_passed': None,
                           'error': repr(error), 'traceback': traceback.format_exc(), 'read_input_pins': PINS,
                           'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}, f, indent=2)
        print(traceback.format_exc())
        raise SystemExit(2)
