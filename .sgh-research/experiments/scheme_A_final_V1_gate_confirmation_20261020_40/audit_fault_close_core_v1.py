"""Independent current closed-raw checker for Source-fault cleanup and command evidence.

No driver validation function is imported. Inputs are decoded from closed raw
files by audit_existing_runs_v1.py; this function can also reject altered inputs
in memory without modifying any frozen run. The current actual run is checked separately from historical records.
"""
import hashlib
import json
import math
import struct

ROLES = ['observer', 'publisher', 'worker', 'synthetic_source', 'recorder']


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest_parameters(rows):
    canonical = {}
    for name, row in rows.items():
        value, kind = row['value'], row['type']
        encoded = struct.pack('>d', value).hex() if kind == 3 else (
            [struct.pack('>d', x).hex() for x in value] if kind == 8 else value)
        require(type(encoded) is type(row['canonical_value']) and encoded == row['canonical_value'],
                'parameter_canonical:' + name)
        canonical[name] = {'type': kind, 'canonical_value': encoded}
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def check(bundle):
    require(bundle['requested_profile'] == 'sink-fault-self-close-v1', 'explicit_checker_profile')
    result, inputs = bundle['original_result'], bundle['inputs']
    run, boot, contract = bundle['run_id'], bundle['boot_id'], inputs['contract_sha256']
    require(result['run_id'] == run and result['passed'] is False and result['V1_fault_observed'] is True,
            'historical_normal_status_and_actual_fault')
    require(result['cleanup_complete'] is True and result['cleanup_within_budget'] is True
            and result['close_elapsed_ns'] <= 15_000_000_000 and result['overall_budget_ns'] == 45_000_000_000
            and result['elapsed_ns'] <= result['overall_budget_ns'],
            'historical_finite_budgets')
    require(result['ledger_failed'] is False, 'ledger_failure')
    ledger, manifests, prepared = bundle['ledger'], bundle['manifests'], bundle['preparation']
    require(all(r['boot_id'] == boot for r in ledger), 'ledger_boot')
    require(set(manifests) == set(ROLES), 'five_roles')
    spawns = [r for r in ledger if r['type'] == 'spawn']
    require(len(spawns) == 5 and {r['name'] for r in spawns} == set(ROLES), 'five_exact_spawns')
    cleanups = [r for r in ledger if r['type'] == 'cleanup_result']
    require(len(cleanups) == 5 and {r['name'] for r in cleanups} == set(ROLES), 'five_exact_cleanup_records')
    summary = [r for r in ledger if r['type'] == 'supervisor_summary']
    require(len(summary) == 1 and not summary[0]['cleanup_failed'] and not summary[0]['unverified_children']
            and not summary[0]['unexpected_descendants'], 'supervisor_terminal')
    for role, m in manifests.items():
        spawn = next(r for r in spawns if r['name'] == role)
        identity = spawn['identity']
        require(m['run_id'] == (run + '-publisher' if role == 'publisher' else run)
                and m['role'] == role and m['boot_id'] == boot and m['contract_sha256'] == contract, 'role_identity:' + role)
        for mk, ik in [('pid', 'pid'), ('pgid', 'pgid'), ('sid', 'sid'), ('process_start_ticks', 'start_ticks'),
                       ('exe', 'exe'), ('binary_sha256', 'exe_sha256')]:
            require(m[mk] == identity[ik] == prepared['roles'][role]['owned'][ik], 'spawn_prepared_identity:' + role + ':' + mk)
        require(spawn['executable_verified'] is True and spawn['expected_sha256'] == m['binary_sha256']
                == bundle['binary_hashes'][role] and spawn['expected_exe'] == m['exe'], 'selected_binary:' + role)
        require(m['effective_parameters_immutable'] is True and m['execute_qualified'] is False,
                'role_scope:' + role)
        require(bundle['manifest_hashes'][role] == prepared['roles'][role]['manifest_sha256']
                and digest_parameters(m['effective_parameters']) == m['effective_parameters_sha256']
                == prepared['roles'][role]['effective_parameters_sha256'], 'manifest_config_binding:' + role)
        bundle_role = 'fixture' if role == 'synthetic_source' else role
        require(m['source_bundle_sha256'] == prepared['roles'][role]['source_bundle_sha256']
                == inputs['source_bundles'][bundle_role]['sha256'], 'prepared_source_bundle:' + role)
        require({k: r['value'] for k, r in m['effective_parameters'].items()} == inputs['expected_parameters'][role],
                'full_config_expected:' + role)
        row = next(r for r in cleanups if r['name'] == role)
        expected_code = 2 if role == 'observer' else 0
        require(row['cleanup_complete'] is True and row['remaining_members'] == []
                and row['unexpected_descendants'] == [] and row['returncode'] == expected_code
                == result['owned_role_returncodes'][role], 'exact_owned_cleanup:' + role)
        require({k: v for k, v in row.items() if k not in ['monotonic_ns', 'boot_id', 'type']}
                == result['cleanup'][role] == summary[0]['children'][role], 'cleanup_record_binding:' + role)
        for signal in [r for r in ledger if r['type'] == 'signal' and r['name'] == role]:
            require(signal['signal'] == 2, 'escalated_cleanup_signal:' + role)
            require(len(signal['members']) == 1, 'signal_group_population:' + role)
            member = signal['members'][0]
            require(all(member[k] == identity[k] for k in ['pid', 'pgid', 'sid', 'start_ticks', 'exe']),
                    'signal_member_identity:' + role)
    observer = manifests['observer']
    require(observer['physical_publisher_endpoints'] == 0 and observer['physical_release_qualified'] is False
            and observer['effective_parameters']['mode']['value'] == 'shadow'
            and observer['effective_parameters']['witness_enabled']['value'] is True, 'shadow_only')
    require(observer['diagnostic_v1_sink_policy'] in
            ['decision_queue_saturation_v1', 'decision_queue_saturation_after_authenticated_phase_v2'], 'explicit_sink_policy')
    fault, witness, source = bundle['fault'], bundle['witness'], bundle['observer_source']
    require(witness['header'] == bundle['expected_header'], 'Witness_header')
    for key, expected in [('run_id', run), ('boot_id', boot), ('contract_hash', contract),
                          ('binary_sha256', observer['binary_sha256']), ('source_sha256', bundle['observer_source_sha256'])]:
        require(fault[key] == expected, 'fault_identity:' + key)
    require(witness['header']['binary_sha256'] == observer['binary_sha256']
            and witness['header']['source_sha256'] == bundle['observer_source_sha256'], 'Witness_binary_source')
    require(fault['stopping'] is True and fault['normal_complete'] is False and fault['stage_qualified'] is False
            and fault['execute_qualified'] is False,
            'real_fault_stopping')
    require(all(r['monotonic_ns'] >= fault['observation_ns'] for r in ledger
                if r['type'] == 'signal' and r['name'] == 'observer'), 'observer_signal_before_fault')
    sink = fault['sink']
    require(sink['enabled'] is True and sink['failed'] is True and sink['state'] == 3 and sink['first_failure_at_this_decision'] is True
            and sink['capacity'] == sink['depth_at_rejection'] == 512
            and sink['depth_before_fill'] + sink['filler_events'] == 512
            and 0 < sink['filler_events'] <= 512 and sink['decision_sequence'] == fault['decision_sequence'],
            'actual_Sink_rejection')
    require(witness['closed'] and witness['observation_complete'] and not witness['overflow'] and not witness['incomplete'],
            'Witness_terminal_complete')
    def phase(event, observation):
        rows = [r for r in witness['phase'] if r['event_code'] == event and r['observation_code'] == observation]
        require(len(rows) == 1, 'Witness_boundary:' + str(event))
        return rows[0]
    stopping, invalidation, closed = phase(5, 3), phase(8, 3), phase(7, 6)
    require(sink['rejection_ns'] <= phase(3, 5)['ns'] <= stopping['ns'] <= invalidation['ns']
            <= fault['observation_ns'] <= closed['ns'] and closed['failed'] is True and closed['stopping'] is True,
            'fault_Witness_causal_order')
    require(invalidation['tick'] == stopping['tick'] == fault['tick']
            and invalidation['job_id'] == stopping['job_id'] == fault['job_id']
            and invalidation['stopping'] is True and invalidation['admission_slots'] == 0
            and invalidation['candidate_present'] is False and invalidation['pending_present'] is False,
            'same_boundary_invalidation')
    require(not any(r['accepted'] and r['commit_ns'] > stopping['ns'] for r in witness['activation'])
            and not any(r['commit_ns'] > stopping['ns'] for r in witness['submit']), 'later_authorization')
    terminal = [r for r in source if r.get('type') == 'source_summary']
    require(len(terminal) == 1 and source[-1] == terminal[0], 'Source_terminal')
    st = terminal[0]
    require(st['normal_source_complete'] is False and st['dropped'] >= 1
            and st['generated'] == st['emitted'] + st['dropped']
            and fault['observation_ns'] <= st['finished_ns'] <= closed['ns'], 'Source_fault_accounting')
    require(len([r for r in source if r.get('type') == 'diagnostic_v1_queue_fill']) == sink['filler_events'],
            'Source_fill_count')
    require(not any(r.get('type') == 'decision' and r['sequence'] == fault['decision_sequence'] for r in source),
            'rejected_decision_logged_as_success')
    require(fault['decision_sequence'] not in [r['sequence'] for r in bundle['stored_decisions']], 'failed_decision_Stored')
    pubrows = bundle['publisher_source']
    require(not any(r.get('type') == 'controlled_decision_receipt' and r['decision_sequence'] == fault['decision_sequence']
                    for r in pubrows), 'failed_decision_owner_receipt')
    tail = [r for r in pubrows if r.get('type') == 'controlled_Applied_emitted' and r['control_source'] == 'shutdown_zero']
    require(len(tail) == 1, 'unique_actual_shutdown_zero')
    zero = tail[0]
    require(len(zero['final_n']) == 2 and all(math.isfinite(x) and abs(x) <= 1e-9 for x in zero['final_n']),
            'zero_command_value')
    require(closed['ns'] < zero['left_start_ns'] <= zero['left_end_ns'] <= zero['right_start_ns']
            <= zero['right_end_ns'] <= zero['applied_publish_start_ns'] <= zero['applied_publish_end_ns']
            <= zero['source_written_ns'], 'actual_zero_API_order')
    owner = manifests['publisher']
    gids = [e['gid'] for e in owner['endpoints'] if e['topic'] == '/research/control/applied' and e['kind'] == 'publisher']
    require(len(gids) == 1, 'unique_Applied_owner_GID')
    decoded = bundle['publisher_applied'][str(zero['applied_sequence'])]
    require(decoded['run_id'] == owner['run_id'] and decoded['producer_instance_id'] == owner['producer_instance_id']
            and decoded['config_hash'] == owner['config_hash'] and decoded['baseline_id'] == owner['baseline_id']
            and decoded['steady_clock_domain'] == boot + ':steady_clock', 'zero_Applied_identity')
    require(decoded['control_source'] == 'shutdown_zero' and decoded['event_semantics'] == 'publisher_command'
            and decoded['requested_known'] is True and decoded['left_publish_success'] is True
            and decoded['right_publish_success'] is True and decoded['publish_error'] == ''
            and decoded['final_n'] == zero['final_n'] and decoded['requested_n'] == zero['final_n'], 'successful_both_API_zero')
    for pk, dk in [('left_start_ns', 'left_publish_start_steady_ns'), ('left_end_ns', 'left_publish_end_steady_ns'),
                   ('right_start_ns', 'right_publish_start_steady_ns'), ('right_end_ns', 'right_publish_end_steady_ns')]:
        require(zero[pk] == decoded[dk], 'Source_CDR_API_binding:' + pk)
    require(not decoded['plant_acceptance_observed'] and not decoded['force_measured'] and not decoded['execution_atomicity_proven'],
            'command_only_evidence_scope')
    stored = [r for r in bundle['stored_applied'] if r['decoded']['run_id'] == owner['run_id']
              and r['decoded']['sequence'] == zero['applied_sequence']]
    require(len(stored) == 1 and stored[0]['decoded'] == decoded, 'Stored_full_Applied_value_binding')
    receipts = [r for r in bundle['transport'] if r.get('topic') == '/research/control/applied'
                and r['payload_sha256'] == stored[0]['wire_sha256'] and r['publisher_gid'] == gids[0]]
    require(len(receipts) == 1 and zero['applied_publish_start_ns'] <= receipts[0]['receive_ns'], 'Fixture_exact_wire_owner_GID')
    # DDS reception can overlap the API call; end-before-receive is not required.
    publisher_close = [r for r in pubrows if r.get('type') == 'controlled_owner_source_closed']
    require(len(publisher_close) == 1 and publisher_close[0] == pubrows[-1]
            and publisher_close[0]['closed_ns'] >= zero['applied_publish_end_ns'], 'Publisher_source_closed')
    ps = bundle['publisher_session']
    require(ps['run_id'] == owner['run_id'] and ps['normal_end'] is True and ps['flushed'] is True
            and ps['publish_errors'] == 0 and ps['queue_dropped_total'] == 0, 'Publisher_session_clean')
    aps = ps['streams']['applied']
    require(aps['generated'] == aps['emitted'] == publisher_close[0]['Applied_emitted'] and aps['dropped'] == 0,
            'Publisher_Applied_counts')
    fs, rt = bundle['fixture_terminal'], bundle['recorder_terminal']
    require(fs['run_id'] == run and fs['normal_end'] is True and fs['failed'] is False
            and fs['closed_steady_ns'] >= receipts[0]['receive_ns'] and fs['transport_total'] == len(bundle['transport']),
            'Fixture_closed_after_receipt')
    recorder = manifests['recorder']
    require(rt['run_id'] == run and rt['boot_id'] == boot and rt['contract_sha256'] == contract
            and rt['pid'] == recorder['pid'] and rt['process_start_ticks'] == recorder['process_start_ticks']
            and rt['manifest_sha256'] == bundle['manifest_hashes']['recorder']
            and rt['clean'] is True and rt['Recorder_stop_completed'] is True
            and rt['metadata_exists'] is True and rt['metadata_sha256'] == bundle['metadata_sha256'], 'Recorder_actual_clean_stop')
    require(bundle['db_integrity_check'] == 'ok' and bundle['storage_counts'] == bundle['metadata_counts']
            and sum(bundle['storage_counts'].values()) == bundle['metadata_total'], 'SQL_metadata_full_counts')
    end_by_role = {r['name']: r['monotonic_ns'] for r in cleanups}
    order = [r['name'] for r in cleanups]
    require(end_by_role['publisher'] < end_by_role['synthetic_source'] < end_by_role['recorder']
            and order[-1] == 'recorder', 'receiver_and_storage_cleanup_order')
    arm = phase(1, 5)['ns']
    accepted = [r for r in bundle['stored_decisions'] if r['candidate_accepted'] and r['sequence'] < fault['decision_sequence']]
    require(accepted, 'accepted_prefix_missing')
    prefix_before_arm = []
    for decision in accepted:
        returned = [r for r in pubrows if r.get('type') == 'controlled_decision_physical_return'
                    and r['decision_sequence'] == decision['sequence']]
        require(len(returned) == 1, 'accepted_prefix_owner_join')
        emissions = [r for r in pubrows if r.get('type') == 'controlled_Applied_emitted'
                     and r['applied_sequence'] == returned[0]['applied_sequence']]
        require(len(emissions) == 1, 'accepted_prefix_Applied_join')
        prefix_before_arm.append(emissions[0]['applied_publish_end_ns'] < arm)
    require(all(prefix_before_arm), 'strict_Applied_before_arm')
    require(result['V1_fault_case_completed'] is True and result['close_policy']=='sink-fault-self-close-v1'
            and result['normal_business_qualified'] is False and result['normal_close_qualified'] is False
            and not result.get('error') and not result['close_errors'], 'actual_explicit_fault_profile_completed')
    report=bundle['fault_close_driver']
    require(report==result['fault_self_close_driver'] and report['profile']=='sink-fault-self-close-v1'
            and report['driver_sequence_completed'] is True and report['entry_verified'] is True
            and report['errors']==[] and report['cleanup']==result['cleanup'], 'actual_driver_report_binding')
    require([e['action'] for e in report['events']]==['validate_fault_entry','stop_observer',
            'Observer_Source_Witness_terminal','stop_publisher','Publisher_owned_exit',
            'Fixture_Recorder_still_alive','stop_worker','stop_synthetic_source','stop_recorder','supervision_health'],
            'actual_fault_profile_event_order')
    require(order==ROLES, 'actual_five_role_cleanup_order')
    require(inputs['V2_case']=='none' and inputs['supervision_profile']=='none'
            and manifests['worker']['effective_parameters']['diagnostic_v2_policy']['value']=='none'
            and manifests['worker']['effective_parameters']['diagnostic_v2_block_ms']['value']==0,
            'Worker_V2_stimulus_disabled')
    return {'schema': 'current-owned-Sink-fault-close/v1', 'passed': True,
            'passed_scope': 'current gated Observer actual Sink fault cleanup and independently Stored shutdown-zero command',
            'run_id': run, 'zero_sequence': zero['applied_sequence'],
            'zero_API_both_success': True, 'zero_Fixture_owner_GID_verified': True,
            'zero_full_Stored_value_verified': True, 'Stored_messages': bundle['metadata_total'],
            'Witness_close_ns': closed['ns'], 'Observer_cleanup_observed_ns': end_by_role['observer'],
            'Observer_process_exit_time_from_Witness_known': False,
            'Observer_received_SIGINT_after_fault': any(r['type'] == 'signal' and r['name'] == 'observer' for r in ledger),
            'observed_cleanup_record_order': order, 'cleanup_order_matches_new_driver': order == ROLES,
            'new_driver_executed_live': True, 'current_explicit_fault_profile_run': True,
            'original_V1_strict_order_passed': all(prefix_before_arm),
            'original_normal_status': result['passed'], 'original_normal_close_errors': result['close_errors'],
            'Recorder_builtin_stream_accounting_claim': rt['storage_stream_accounting_verified'],
            'independent_SQL_metadata_verified': True, 'normal_close_qualified': False,
            'stage_qualified': False, 'execute_qualified': False, 'true_plant_qualified': False, 'research_conclusion': False}
