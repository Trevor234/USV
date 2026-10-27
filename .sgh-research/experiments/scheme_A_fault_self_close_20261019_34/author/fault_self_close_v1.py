"""Explicit shadow Sink-fault cleanup. This module grants no normal-close authority.

The caller supplies already authenticated owned-role records and supervisor stops.
No discovery, signal, ROS publish, close ACK or receiver callback lives here.
Resource cleanup continues when validation or evidence writing fails.
"""
import hashlib
import json
import struct
import time
from pathlib import Path

PROFILE = 'sink-fault-self-close-v1'
ROLES = ('observer', 'publisher', 'worker', 'synthetic_source', 'recorder')


def final_fault_case_completed(result, supervisor):
    """Call after supervisor.close and driver shutdown, not before final IO."""
    report = result.get('fault_self_close_driver', {})
    return bool(result.get('close_policy') == PROFILE and result.get('V1_fault_observed') is True
                and result.get('cleanup_complete') is True and result.get('cleanup_within_budget') is True
                and report.get('profile') == PROFILE and report.get('run_id') == result.get('run_id')
                and report.get('driver_sequence_completed') is True
                and not result.get('error') and not result.get('close_errors')
                and result.get('ledger_failed') is False and not supervisor.evidence_failed
                and not supervisor.cleanup_failed and not supervisor.unverified_children
                and not supervisor.unexpected_descendants)


def need(value, reason):
    if not value:
        raise ValueError(reason)


def typed_digest(rows):
    encoded = {}
    for name, row in rows.items():
        value, kind = row['value'], row['type']
        canonical = (struct.pack('>d', value).hex() if kind == 3 else
                     [struct.pack('>d', x).hex() for x in value] if kind == 8 else value)
        need(type(canonical) is type(row['canonical_value']) and canonical == row['canonical_value'],
             'typed_parameter:' + name)
        encoded[name] = dict(type=kind, canonical_value=canonical)
    return hashlib.sha256(json.dumps(encoded, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def validate_entry(context, fault):
    """Validate a real first Sink failure before selecting diagnostic cleanup."""
    need(context['profile'] == PROFILE, 'explicit_fault_profile_required')
    need(context['released'] is True and context['diagnostic_shadow_only'] is True,
         'released_shadow_fixture_required')
    need(set(context['roles']) == set(ROLES), 'five_owned_roles_required')
    for role in ROLES:
        item = context['roles'][role]
        manifest, identity = item['manifest'], item['registered_identity']
        expected_run = context['run_id'] + '-publisher' if role == 'publisher' else context['run_id']
        need(manifest['role'] == role and manifest['run_id'] == expected_run
             and manifest['boot_id'] == context['boot_id']
             and manifest['contract_sha256'] == context['contract_sha256'], 'owned_run_identity:' + role)
        for mkey, ikey in [('pid', 'pid'), ('pgid', 'pgid'), ('sid', 'sid'),
                           ('process_start_ticks', 'start_ticks'), ('exe', 'exe'),
                           ('binary_sha256', 'exe_sha256')]:
            need(manifest[mkey] == identity[ikey], 'registered_identity:' + role + ':' + mkey)
        need(manifest['effective_parameters_immutable'] is True and manifest['execute_qualified'] is False,
             'immutable_shadow_role:' + role)
        need(typed_digest(manifest['effective_parameters']) == manifest['effective_parameters_sha256']
             == item['prepared_parameter_digest'], 'prepared_configuration:' + role)
        need(item['manifest_sha256'] == item['prepared_manifest_sha256'], 'prepared_manifest:' + role)
        need(manifest['source_bundle_sha256'] == item['prepared_source_bundle_sha256'], 'prepared_source_bundle:' + role)
    observer = context['roles']['observer']['manifest']
    params = observer['effective_parameters']
    need(params['diagnostic_v1_sink_policy']['value'] in
         ['decision_queue_saturation_v1', 'decision_queue_saturation_after_authenticated_phase_v2'],
         'explicit_sink_policy_required')
    need(params['witness_enabled']['value'] is True and observer['physical_publisher_endpoints'] == 0
         and params['mode']['value'] == 'shadow'
         and observer['physical_release_qualified'] is False, 'observer_shadow_boundary')
    need(all(params[k]['value'] == 0 for k in ['test_delay_ms', 'test_native_block_ms',
             'test_prepare_block_ms', 'test_sink_pause_ms', 'test_tick_block_ms']), 'legacy_hooks_remain_zero')
    for key, expected in [('run_id', context['run_id']), ('boot_id', context['boot_id']),
                          ('contract_hash', context['contract_sha256']),
                          ('binary_sha256', observer['binary_sha256']),
                          ('source_sha256', context['expected_header']['source_sha256'])]:
        need(fault[key] == expected, 'actual_fault_identity:' + key)
    need(fault['schema'] == 'V1-actual-queue-failure-observation/v1'
         and fault['stopping'] is True and fault['normal_complete'] is False
         and fault['stage_qualified'] is False and fault['execute_qualified'] is False
         and fault['observer_physical_publishers'] == 0,
         'actual_fault_stopping_required')
    sink = fault['sink']
    need(sink['enabled'] is True and sink['failed'] is True and sink['state'] == 3
         and sink['first_failure_at_this_decision'] is True and sink['capacity'] == 512
         and sink['depth_at_rejection'] == 512
         and sink['depth_before_fill'] + sink['filler_events'] == 512
         and 0 < sink['filler_events'] <= 512
         and sink['decision_sequence'] == fault['decision_sequence']
         and 0 < sink['rejection_ns'] <= fault['observation_ns'], 'real_queue_rejection_required')
    return {'entry_verified': True, 'profile': PROFILE,
            'fault_sequence': fault['decision_sequence'], 'normal_close_qualified': False}


def validate_observer_terminal(context, fault, source, witness):
    need(witness['header'] == context['expected_header'], 'Witness_exact_header')
    need(witness['closed'] is True and witness['observation_complete'] is True
         and witness['overflow'] is False and witness['incomplete'] is False, 'Witness_terminal')
    def phase(event, observation):
        found = [r for r in witness['phase'] if r['event_code'] == event and r['observation_code'] == observation]
        need(len(found) == 1, 'Witness_unique_boundary:' + str(event))
        return found[0]
    stopping, invalidation, closed = phase(5, 3), phase(8, 3), phase(7, 6)
    need(fault['sink']['rejection_ns'] <= stopping['ns'] <= invalidation['ns'] <= fault['observation_ns']
         <= closed['ns'] and closed['failed'] is True and closed['stopping'] is True,
         'fault_to_Witness_close_order')
    need(stopping['tick'] == invalidation['tick'] == fault['tick']
         and stopping['job_id'] == invalidation['job_id'] == fault['job_id']
         and invalidation['stopping'] is True and invalidation['admission_slots'] == 0
         and invalidation['candidate_present'] is False and invalidation['pending_present'] is False,
         'same_boundary_invalidation')
    need(not any(r['accepted'] and r['commit_ns'] > stopping['ns'] for r in witness['activation'])
         and not any(r['commit_ns'] > stopping['ns'] for r in witness['submit']), 'authorization_after_stopping')
    terminal = [r for r in source if r.get('type') == 'source_summary']
    need(len(terminal) == 1 and source[-1] == terminal[0], 'Source_unique_terminal')
    summary = terminal[0]
    need(summary['normal_source_complete'] is False and summary['dropped'] >= 1
         and summary['generated'] == summary['emitted'] + summary['dropped']
         and fault['observation_ns'] <= summary['finished_ns'] <= closed['ns'], 'Source_fault_accounting')
    need(len([r for r in source if r.get('type') == 'diagnostic_v1_queue_fill']) == fault['sink']['filler_events'],
         'Source_actual_fill_population')
    return {'Source_fault_terminal_verified': True, 'Witness_terminal_verified': True,
            'Witness_close_ns': closed['ns'], 'process_exit_proven_by_Witness': False,
            'normal_Source_complete': False}


def run_fault_close(context, fault, *, stop_role, observer_terminals, owner_exit_proof,
                    receivers_alive, supervision_health, now_ns, deadline_ns, record):
    """Run the distinct close branch; stop callbacks use the exact owned registry.

    Do not short-circuit remaining cleanup on validation/IO/stop failures. A false
    result still leaves the caller's unconditional owned-cleanup fallback active.
    This return value never represents terminal-tail/storage qualification.
    """
    events, errors, cleanup = [], [], {}
    def attempt(action, fn, bounded=True):
        try:
            if bounded:
                need(now_ns() < deadline_ns, 'fault_close_deadline')
            result = fn()
            events.append({'action': action, 'returned_ns': now_ns(), 'result': result})
            return result
        except Exception as error:
            errors.append({'action': action, 'error': repr(error)})
            return None
    entry = attempt('validate_fault_entry', lambda: validate_entry(context, fault))
    for role in ROLES:
        # Even an exhausted evidence budget must not skip owned resource cleanup.
        row = attempt('stop_' + role, lambda role=role: stop_role(role), bounded=False)
        if row is not None:
            cleanup[role] = row
        if role == 'observer' and entry:
            attempt('Observer_Source_Witness_terminal', observer_terminals)
        if role == 'publisher':
            attempt('Publisher_owned_exit', owner_exit_proof)
            attempt('Fixture_Recorder_still_alive', receivers_alive)
    attempt('supervision_health', supervision_health)
    finished = now_ns()
    expected_codes = {r: 2 if r == 'observer' else 0 for r in ROLES}
    resources = set(cleanup) == set(ROLES) and all(
        r.get('cleanup_complete') is True and r.get('remaining_members') == []
        and r.get('unexpected_descendants') == [] and r.get('returncode') == expected_codes[name]
        and r.get('qualification_clean') is (name != 'observer')
        for name, r in cleanup.items())
    report = {'schema': 'owned-Sink-fault-close-driver/v1', 'profile': PROFILE,
              'run_id': context['run_id'], 'events': events, 'errors': errors,
              'entry_verified': entry is not None, 'cleanup': cleanup,
              'driver_sequence_completed': bool(entry and resources and not errors and finished <= deadline_ns),
              'deadline_ns': deadline_ns, 'finished_ns': finished,
              'normal_close_qualified': False, 'Stored_zero_tail_verified': False,
              'stage_qualified': False, 'execute_qualified': False, 'research_conclusion': False}
    try:
        record(report)
    except Exception as error:
        report['errors'].append({'action': 'fault_close_report_write', 'error': repr(error)})
        report['driver_sequence_completed'] = False
    return report


def perform_driver_branch(directory, supervisor, owned, roles, *, expected_header,
                          contract_sha256, released, close_start_ns, overall_deadline_ns,
                          cleanup, owner_exit_proof):
    """Adapter used by the derived real driver; offline tests inject a supervisor.

    Existing ROS-facing ACK/normal tail code is deliberately outside this adapter.
    Budgets use the caller's monotonic deadline and the existing owned supervisor.
    """
    root = Path(directory)
    def load(relative):
        return json.loads((root / relative).read_bytes())
    prepared = load('preparation_evidence.json')
    context = {'profile': PROFILE, 'run_id': expected_header['run_id'],
               'boot_id': supervisor.boot, 'contract_sha256': contract_sha256,
               'released': released, 'diagnostic_shadow_only': True,
               'expected_header': expected_header, 'roles': {}}
    for name in ROLES:
        manifest_path = root / name / 'owned_manifest.json'
        manifest_bytes = manifest_path.read_bytes()
        need(hashlib.sha256(manifest_bytes).hexdigest() == roles[name]['sha256']
             and json.loads(manifest_bytes) == roles[name]['manifest'], 'live_manifest_changed:' + name)
        context['roles'][name] = {'manifest': roles[name]['manifest'],
            'registered_identity': owned[name].identity,
            'manifest_sha256': roles[name]['sha256'],
            'prepared_manifest_sha256': prepared['roles'][name]['manifest_sha256'],
            'prepared_source_bundle_sha256': prepared['roles'][name]['source_bundle_sha256'],
            'prepared_parameter_digest': prepared['roles'][name]['effective_parameters_sha256']}
    fault = load('observer/v1_fault.json')
    deadline = min(overall_deadline_ns, close_start_ns + 15_000_000_000)
    def stop(name):
        if name not in cleanup:
            # The first bounded wait permits fault-triggered natural Observer exit.
            # Emergency cleanup still runs with zero waits when time is exhausted;
            # the result then remains a failed diagnostic sequence.
            remaining = max(0., (deadline - time.monotonic_ns()) / 1e9)
            allocation = min(remaining, 4.0 if name == 'observer' else 2.5)
            natural = min(.5, allocation) if name == 'observer' else 0.
            terminal_wait = min(.25, max(0., allocation - natural))
            kill_wait = min(.25, max(0., allocation - natural - terminal_wait))
            grace = max(0., allocation - natural - terminal_wait - kill_wait)
            cleanup[name] = supervisor.stop(owned[name], grace, terminal_wait, kill_wait,
                                            natural_grace=natural)
        return cleanup[name]
    def terminals():
        raw = (root / 'observer/source.jsonl').read_bytes()
        need(raw.endswith(b'\n'), 'Source_unterminated_line')
        return validate_observer_terminal(context, fault, [json.loads(x) for x in raw.splitlines()],
                                          load('observer/witness.json'))
    def receivers():
        for name in ['synthetic_source', 'recorder']:
            need(owned[name].process.poll() is None and len(supervisor.members(owned[name])) == 1
                 and not supervisor.unexpected_descendants, 'receiver_exited_before_Publisher_cleanup:' + name)
        return {'Fixture_alive': True, 'Recorder_alive': True, 'DDS_delivery_proven': False}
    def record(report):
        with (root / 'fault_self_close_driver.json').open('x') as stream:
            json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
    def health():
        need(not supervisor.evidence_failed and not supervisor.unverified_children
             and not supervisor.unexpected_descendants and not supervisor.cleanup_failed, 'supervision_evidence_failed')
        need(not any(r['type'] == 'signal' and r['signal'] in [15, 9]
                     for r in supervisor.memory_tail), 'forced_cleanup_not_fault_qualified')
        return {'owned_ledger_clean': True, 'no_SIGTERM_or_SIGKILL': True}
    return run_fault_close(context, fault, stop_role=stop, observer_terminals=terminals,
        owner_exit_proof=owner_exit_proof, receivers_alive=receivers, supervision_health=health,
        now_ns=time.monotonic_ns, deadline_ns=deadline, record=record)
