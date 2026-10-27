#!/usr/bin/env python3
"""Finite actual Worker post-exit queue diagnostic; no phase qualification.

Authenticated live callbacks retain complete typed received-CDR joins. Rejected
post-exit callbacks intentionally stop before reserialization: their actual
MessageInfo and unchanged six-field snapshots are checked, without inventing a
received payload or a unique Capability packet identity.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE/'runtime')]
import check_c37_owned_run_v2 as p
import check_c38_owned_close as c38
c36 = p.c36
exact = p.exact
SCHEMA = 'p1-C3.9-owned-Worker-post-exit-check-v1'
FLAGS = p.FLAGS.copy()
SNAPSHOT_FIELDS = {'worker_instance', 'worker_valid', 'worker_unusable',
                   'lease_last_valid_ns', 'candidate_present', 'admission_slots'}


def publication_before_close(publication, queued_checked_ns, close):
    """A real successful call already completed before the driver close request."""
    times = [publication.get('publish_start_ns'), publication.get('publish_end_ns'),
             queued_checked_ns, close.get('requested_ns'), close.get('read_completed_ns'),
             close.get('observed_ns')]
    return all(c36.integer(x, 1) for x in times) and times == sorted(times)


def current_adapter_bindings(run, observer, publisher, peer, peer_sha, publisher_sha):
    """Concrete current-run native parameters and complete publisher peer map."""
    run = Path(run)
    params = observer.get('effective_parameters', {})
    wanted = {'mode': 'shadow', 'adapter_peer_pins_file': str(run/'adapter_peer_pins.json'),
        'adapter_peer_pins_sha256': peer_sha,
        'adapter_driver_close_file': str(run/'adapter_driver_close_request.json'),
        'diagnostic_c38_mode': 'worker-gate',
        'diagnostic_c38_pause_file': str(run/'c38_pause_request.json'),
        'diagnostic_c38_resume_file': str(run/'c38_resume_request.json')}
    pins = {'manifest_path': str(run/'publisher/owned_manifest.json'),
        'manifest_sha256': publisher_sha, 'topic': c36.APPLIED, 'type': c36.APPLIED_TYPE}
    pins.update({k:publisher.get(k) for k in ('run_id', 'boot_id', 'contract_sha256',
        'producer_instance_id', 'config_hash', 'pid', 'process_start_ticks', 'exe',
        'binary_sha256', 'source_bundle_sha256', 'effective_parameters_sha256')})
    return (all(exact(params.get(k, {}).get('value'), value) for k, value in wanted.items())
        and observer.get('adapter_pins_sha256') == peer_sha
        and type(peer.get('publisher_peer')) is dict and set(peer['publisher_peer']) == set(pins)
        and all(exact(peer['publisher_peer'].get(k), value) for k, value in pins.items()))


def role_pin_population(run, inputs, result, manifests, preparation, ledger, checker):
    """Offline byte/process binding across assets, native manifests and live prep.

    The preparation row records the live authentication call; the ledger records
    supervisor-owned starts and reaps. These are historical same-run identity
    facts, and do not infer continuous exec or DDS endpoint uniqueness.
    """
    run = Path(run)
    checker.need(set(manifests) == c36.ROLES and set(preparation.get('roles', {})) == c36.ROLES,
                 'entire_live_authenticated_preparation_role_population')
    checker.need(preparation.get('schema_version') == 'p1-owned-fixture-preparation-v2'
        and preparation.get('fixture_only') is True and preparation.get('production_execute_qualified') is False
        and c36.integer(preparation.get('checked_ns'), 1), 'actual_preparation_diagnostic_scope')
    spawns = checker.index([r for r in ledger if r.get('type') == 'spawn'], lambda r:r.get('name'), 'supervisor_spawn')
    cleanups = checker.index([r for r in ledger if r.get('type') == 'cleanup_result'],
                             lambda r:r.get('name'), 'supervisor_cleanup')
    checker.need(set(spawns) == set(cleanups) == c36.ROLES, 'entire_supervisor_spawn_cleanup_role_population')
    for role, manifest in manifests.items():
        source_role = 'fixture' if role == 'synthetic_source' else role
        build = inputs.get('builds', {}).get(source_role, {})
        source = inputs.get('source_bundles', {}).get(source_role, {})
        checker.need(manifest.get('exe') == build.get('binary')
            and manifest.get('binary_sha256') == build.get('binary_sha256')
            and manifest.get('source_bundle_sha256') == source.get('sha256')
            and source.get('sha256') == build.get('source_bundle', {}).get('sha256')
            and c36.integer(manifest.get('pid'), 1) and c36.integer(manifest.get('process_start_ticks'), 1)
            and manifest.get('boot_id') == manifests['observer'].get('boot_id')
            and manifest.get('run_id') == inputs.get('run_id')+('-publisher' if role == 'publisher' else ''),
            'native_role_manifest_exact_current_asset_and_process_binding', role=role)
        auth = preparation.get('roles', {}).get(role, {}); owned = auth.get('owned', {})
        spawn = spawns.get(role, {}); ident = spawn.get('identity', {})
        checker.need(auth.get('manifest_sha256') == c36.sha(run/role/'owned_manifest.json')
            and auth.get('source_bundle_sha256') == manifest.get('source_bundle_sha256')
            and auth.get('effective_parameters_sha256') == manifest.get('effective_parameters_sha256')
            and owned.get('pid') == ident.get('pid') == manifest.get('pid')
            and owned.get('start_ticks') == ident.get('start_ticks') == manifest.get('process_start_ticks')
            and owned.get('exe') == ident.get('exe') == manifest.get('exe')
            and owned.get('exe_sha256') == ident.get('exe_sha256') == manifest.get('binary_sha256')
            and owned.get('boot_id') == spawn.get('boot_id') == manifest.get('boot_id')
            and owned.get('pgid') == ident.get('pgid') == manifest.get('pid')
            and owned.get('sid') == ident.get('sid') == manifest.get('pid')
            and exact(owned.get('argv'), spawn.get('argv'))
            and spawn.get('executable_verified') is True
            and spawn.get('expected_exe') == manifest.get('exe')
            and spawn.get('expected_sha256') == manifest.get('binary_sha256')
            and c36.integer(spawn.get('monotonic_ns'), 1)
            and spawn['monotonic_ns'] <= preparation.get('checked_ns', 0),
            'live_preparation_authentication_exact_supervisor_spawn_identity_and_argv', role=role)
        cleanup = cleanups.get(role, {}); expected_cleanup = result.get('cleanup', {}).get(role, {})
        checker.need(expected_cleanup.get('name') == role
            and cleanup.get('boot_id') == manifest.get('boot_id')
            and all(exact(cleanup.get(k), value) for k, value in expected_cleanup.items())
            and c36.integer(cleanup.get('monotonic_ns'), 1)
            and preparation.get('checked_ns', 0) <= cleanup.get('monotonic_ns', 0),
            'supervisor_cleanup_matches_complete_driver_cleanup_and_live_role', role=role)
        signals = [r for r in ledger if r.get('type') == 'signal' and r.get('name') == role]
        checker.need(len(signals) == 1 and signals[0].get('signal') == 2
            and signals[0].get('boot_id') == manifest.get('boot_id')
            and any(member.get('pid') == manifest.get('pid')
                    and member.get('start_ticks') == manifest.get('process_start_ticks')
                    and member.get('exe') == manifest.get('exe')
                    for member in signals[0].get('members', [])),
            'scoped_supervisor_signal_actual_native_role_pid_start_exe', role=role)
    summaries = [r for r in ledger if r.get('type') == 'supervisor_summary']
    checker.need(len(summaries) == 1 and ledger[-1] is summaries[0]
        and exact(summaries[0].get('children'), result.get('cleanup'))
        and summaries[0].get('cleanup_failed') is False and summaries[0].get('qualification_clean') is True
        and summaries[0].get('unexpected_descendants') == [] and summaries[0].get('unverified_children') == [],
        'entire_supervisor_terminal_population_and_cleanup_conservation')


def snapshot(value):
    return (type(value) is dict and set(value) == SNAPSHOT_FIELDS
        and type(value['worker_instance']) is str
        and all(type(value[k]) is bool for k in ('worker_valid', 'worker_unusable', 'candidate_present'))
        and c36.integer(value['lease_last_valid_ns'])
        and c36.integer(value['admission_slots']) and value['admission_slots'] <= 1)


def post_exit_rejection(row, expected_gid, proof_ns):
    """The exact early guard facts, deliberately no payload-identity predicate."""
    times = [row.get(k) for k in ('entry_ns', 'authentication_checked_ns',
                                 'callback_completed_ns', 'processed_ns')]
    return (c36.integer(proof_ns, 1) and all(c36.integer(x, 1) for x in times)
        and proof_ns < times[0] <= times[1] <= times[2] == times[3]
        and p.gid(expected_gid) and exact(row.get('expected_gid'), expected_gid)
        and exact(row.get('actual_gid'), expected_gid)
        and row.get('authentication_reason') == 'worker_process_exited'
        and row.get('worker_process_alive_at_guard') is False
        and row.get('later_worker_process_alive') is False
        and row.get('resource_valid') is True and row.get('resource_reason') == ''
        and row.get('rmw_implementation_matches_registered') is True
        and row.get('from_intra_process') is False
        and row.get('raw_input') is None and row.get('full_cdr_serialized') is False
        and row.get('semantic_callback_invoked') is False
        and snapshot(row.get('before')) and snapshot(row.get('after'))
        and exact(row['before'], row['after']))


def worker_population(observer, decoded, manifest, proof_ns, checker, *, decode=None):
    """All actual callbacks; separate live typed and early rejected populations."""
    if decode is None:
        decode = lambda raw, label: p.decode_callback(raw, checker, label)
    callbacks = [r for r in observer if r.get('type') == 'adapter_worker_callback']
    summaries = [r for r in observer if r.get('type') == 'source_summary']
    closures = [r for r in observer if r.get('type') == 'adapter_worker_reception_closed']
    checker.need(len(summaries) == len(closures) == 1, 'Worker_receiver_Source_unique_terminal')
    close = summaries[0].get('finished_ns') if len(summaries) == 1 else None
    receiver = closures[0] if len(closures) == 1 else {}
    receiver_ns = receiver.get('closed_ns')
    checker.need(receiver.get('schema') == 'p1-C3.7-worker-reception-close-v1'
        and receiver.get('executor_detached') is True and receiver.get('tick_joined') is True
        and receiver.get('prep_joined') is True and c36.integer(receiver_ns, 1)
        and c36.integer(close, 1) and proof_ns < receiver_ns <= close
        and receiver.get('worker_process_alive') is False
        and receiver.get('all_Worker_publications_received') is None
        and receiver.get('worker_endpoints_exited') == 'unknown',
        'Worker_actual_dead_peer_receiver_lifecycle_close_facts')
    endpoint = {}
    for kind, (topic, typ) in p.WORKER.items():
        es = [e for e in manifest['endpoints'] if e.get('kind') == 'publisher'
              and e.get('topic') == topic and e.get('type') == typ]
        checker.need(len(es) == 1 and p.gid(es[0].get('gid')),
                     'unique_Worker_manifest_endpoint', interface=kind)
        endpoint[kind] = es[0] if len(es) == 1 else {}
    report = {}; raw_by_interface = {}; admitted_by_interface = {}; events_by_interface = {}
    for kind, (topic, typ) in p.WORKER.items():
        received = [r for r in callbacks if r.get('interface') == kind]
        events_by_interface[kind] = {r.get('callback_sequence'): r for r in received}
        checker.need(bool(received), 'Worker_actual_received_nonempty', interface=kind)
        checker.need([r.get('callback_sequence') for r in received] == list(range(1, len(received)+1))
            and [r.get('received_count') for r in received] == list(range(1, len(received)+1)),
            'entire_Worker_callback_sequence_and_count', interface=kind)
        checker.need(type(receiver.get(kind+'_received')) is int
            and type(receiver.get(kind+'_callback_sequence')) is int
            and receiver.get(kind+'_received') == receiver.get(kind+'_callback_sequence') == len(received),
            'Worker_native_receiver_terminal_counter_conservation', interface=kind)
        recorded = [r['message'] for r in decoded.get(topic, [])]
        storage_count = Counter(p.canonical(m) for m in recorded)
        seen = Counter(); used = set(); raw_by_interface[kind] = {}; denied = []
        last_entry = 0; denial_started = False
        for r in received:
            seq = r.get('callback_sequence'); label = {'interface': kind, 'callback_sequence': seq}
            times = [r.get(k) for k in ('entry_ns', 'authentication_checked_ns', 'processed_ns')]
            checker.need(all(c36.integer(x, 1) for x in times)
                and last_entry <= times[0] <= times[1] <= times[2]
                and c36.integer(receiver_ns, 1) and times[2] <= receiver_ns <= close,
                'Worker_callback_finite_observation_time_order', **label)
            if c36.integer(r.get('entry_ns'), 1): last_entry = r['entry_ns']
            checker.need(p.gid(r.get('actual_gid')) and p.gid(r.get('expected_gid'))
                and exact(r.get('actual_gid'), endpoint[kind].get('gid'))
                and exact(r.get('expected_gid'), endpoint[kind].get('gid')),
                'Worker_callback_actual_owned_GID', **label)
            checker.need(r.get('topic') == topic and r.get('message_type') == typ
                and r.get('rmw_implementation_matches_registered') is True
                and r.get('from_intra_process') is False,
                'Worker_callback_actual_interface_metadata', **label)
            for phase in ('before', 'after'):
                checker.need(snapshot(r.get(phase)), 'Worker_callback_actual_snapshot_typed', phase=phase, **label)
            if r.get('authentication_reason'):
                denial_started = True
                checker.need(post_exit_rejection(r, endpoint[kind].get('gid'), proof_ns),
                             'actual_post_exit_Worker_early_guard_no_business_mutation', **label)
                denied.append({'callback_sequence': seq, 'entry_ns': r.get('entry_ns'),
                               'processed_ns': r.get('processed_ns'), 'auth': r.get('authentication_reason')})
                continue
            checker.need(not denial_started and r['entry_ns'] < proof_ns,
                         'no_live_semantic_receipt_after_dead_peer_proof', **label)
            checker.need(r.get('resource_valid') is True and r.get('resource_reason') == ''
                and r.get('worker_process_alive_at_guard') is True
                and type(r.get('later_worker_process_alive')) is bool
                and r.get('full_cdr_serialized') is True and r.get('semantic_callback_invoked') is True
                and r.get('callback_completed_ns') == r.get('processed_ns'),
                'live_Worker_callback_resource_and_identity_guard', **label)
            raw = r.get('raw_input')
            if not isinstance(raw, dict):
                checker.need(False, 'live_Worker_callback_raw_present', **label); continue
            checker.need(set(raw) == p.RAW_FIELDS and raw.get('schema') == 'p1-input-callback-full-cdr-v1'
                and raw.get('topic') == topic and raw.get('message_type') == typ
                and raw.get('callback_sequence') == seq
                and exact(raw.get('publisher_gid'), endpoint[kind].get('gid'))
                and raw.get('rmw_implementation') == 'rmw_fastrtps_cpp'
                and raw.get('from_intra_process') is False
                and c36.integer(raw.get('entry_steady_ns'), 1)
                and r['authentication_checked_ns'] <= raw['entry_steady_ns'] <= r['processed_ns'],
                'live_Worker_callback_actual_typed_interface', **label)
            m = decode(raw, label)
            if m is None: continue
            checker.need(type(m) is dict and ((kind == 'capability' and p.lease.exact_payload(m))
                or (kind == 'candidate' and set(m) == set(p.CANDIDATE_FIELDS)|{'job'}
                    and type(m.get('job')) is dict and set(m['job']) == set(p.JOB_FIELDS))),
                'live_Worker_callback_complete_typed_payload_field_domain', **label)
            raw_by_interface[kind][seq] = m
            key = p.canonical(m); seen[key] += 1
            checker.need(seen[key] <= storage_count[key], 'live_received_Worker_full_typed_occurrence_in_Storage', **label)
            index = next((i for i, x in enumerate(recorded) if i not in used and exact(x, m)), None)
            if index is not None: used.add(index)
            checker.need(exact(m.get('worker_instance'), manifest['worker_instance']), 'live_Worker_bound_instance', **label)
            if kind == 'capability':
                checker.need(all(exact(m.get(k), v) for k, v in {
                    'run_id': manifest['run_id'], 'boot_id': manifest['boot_id'],
                    'contract_hash': manifest['contract_sha256'], 'nominal_hash': manifest['nominal_hash'],
                    'pid': manifest['pid']}.items()), 'live_Worker_complete_capability_role_identity', **label)
        checker.need(bool(denied), 'actual_post_exit_callback_on_each_Worker_interface', interface=kind)
        checker.need(bool(raw_by_interface[kind]), 'actual_live_typed_callback_on_each_Worker_interface', interface=kind)
        checker.need(len(used)+len(denied) <= len(recorded),
                     'entire_Worker_received_count_bounded_by_Storage_without_denied_payload_assignment', interface=kind)
        admitted_by_interface[kind] = set(raw_by_interface[kind])
        report[kind] = {'recorded': len(recorded), 'received': len(received),
            'live_typed_received': len(raw_by_interface[kind]), 'live_typed_storage_matched': len(used),
            'post_exit_early_rejected': denied, 'complete_callback_counter_population': True,
            'complete_received_CDR_population': False, 'all_recorded_received': None,
            'rejected_payload_identity_available': False,
            'packet_identity_available': kind == 'candidate',
            'unassigned_Storage_ordinals': [i+1 for i in range(len(recorded)) if i not in used],
            'occurrence_assignment_semantics': 'Only live full typed occurrences matched. Rejected early guards have no received CDR; remaining Storage ordinals cannot be assigned to those callbacks.',
            'expected_owned_gid': endpoint[kind].get('gid'),
            'reception_window_close_monotonic_ns': receiver_ns, 'Source_flush_complete_monotonic_ns': close}
    checker.need(all(r.get('interface') in p.WORKER for r in callbacks), 'Worker_callback_known_interfaces')
    if len(closures) == 1:
        checker.need(all(observer.index(r) < observer.index(closures[0]) for r in callbacks),
                     'Worker_callback_events_before_native_receiver_close')
    for kind, event in (('capability', 'capability_admission'), ('candidate', 'candidate_registration')):
        semantic = checker.index([r for r in observer if r.get('type') == event],
                                 lambda r: r.get('callback_sequence'), 'Worker_'+event)
        checker.need(set(semantic) == admitted_by_interface[kind],
                     'exact_live_Worker_semantic_population_excludes_all_post_exit_callbacks', interface=kind)
        for seq, row in semantic.items():
            callback = events_by_interface[kind].get(seq, {})
            checker.need(row.get('received_count') == seq and exact(row.get('raw_input'), callback.get('raw_input')),
                         'live_Worker_semantic_exact_callback_raw_binding', interface=kind, callback_sequence=seq)
            m = raw_by_interface[kind].get(seq)
            if m is None: continue
            if kind == 'capability':
                checker.need(exact(row.get('capability'), m), 'live_Worker_semantic_full_capability_binding', callback_sequence=seq)
            else:
                checker.need(exact(p.projection(row.get('job', {}), p.JOB_FIELDS, p.JOB_ALIASES),
                                   p.projection(m.get('job', {}), p.JOB_FIELDS, {}))
                    and exact(row.get('first_control'), m.get('first_control')),
                    'live_Worker_semantic_full_candidate_Job_and_control_binding', callback_sequence=seq)
    return report, raw_by_interface


def analyze(run):
    run = Path(run).resolve(); c = c36.Checks()
    files = [f for f in run.rglob('*') if f.is_file()]
    before = {str(f): c36.sha(f) for f in files}
    inputs = c36.load(run/'inputs.json'); result = c36.load(run/'result.json')
    c.need(inputs.get('c38_case') == result.get('c38_case') == 'worker_post_exit', 'declared_C39_Worker_negative_case')
    c.need(inputs.get('mode') == 'positive' and inputs.get('measurement_seconds') == 4
        and inputs.get('witness_validation_profile') == p.PROFILE
        and result.get('finite_prepare_and_measurement_passed') is True and result.get('released') is True,
        'preregistered_prepare_measurement')
    c.need(result.get('diagnostic_case_completed') is True and result.get('cleanup_complete') is True
        and result.get('cleanup_within_budget') is True and c36.integer(result.get('close_elapsed_ns'), 1)
        and result['close_elapsed_ns'] <= 15_000_000_000, 'bounded_owned_cleanup_and_scenario')
    c.need(set(result.get('cleanup', {})) == c36.ROLES
        and all(v.get('remaining_members') == [] and v.get('cleanup_complete') is True
                for v in result.get('cleanup', {}).values()), 'all_registered_groups_reaped')
    c.need(result.get('owned_role_returncodes') == {role: 0 for role in c36.ROLES}
        and result.get('close_errors') == [] and result.get('ledger_failed') is False
        and result.get('evidence_qualification_clean') is True,
        'actual_all_roles_normal_reap_and_no_close_or_ledger_failure')
    manifests = {k: c36.load(run/k/'owned_manifest.json') for k in c36.ROLES}
    pub = manifests['publisher']; worker = manifests['worker']; obs = manifests['observer']
    peer = c36.load(run/'adapter_peer_pins.json')
    c.need(current_adapter_bindings(run, obs, pub, peer, c36.sha(run/'adapter_peer_pins.json'),
                                   c36.sha(run/'publisher/owned_manifest.json')),
           'concrete_current_run_Observer_adapter_configuration_and_full_publisher_peer_pins')
    c.need(peer.get('run_id') == inputs['run_id']
        and peer.get('driver_tool_sha256') == inputs.get('tool_sha256', {}).get('prepare_fixture.py')
        == c36.sha(HERE/'prepare_fixture.py') == c36.sha(run/'prepare_fixture.py.snapshot'),
        'actual_driver_tool_peer_input_and_prerun_snapshot_exact_binding')
    p.worker_binding(run, inputs, manifests, peer, c); p.configurations(run, inputs, result, manifests, c)
    p.worker_contract_configuration(inputs, worker, c)
    physical = {pub['effective_parameters'][n]['value'] for n in ('vrx_left_thrust_topic', 'vrx_right_thrust_topic')}
    c.need(obs['effective_parameters']['mode']['value'] == 'shadow' and obs.get('physical_publisher_endpoints') == 0
        and not any(e['kind'] == 'publisher' and e['topic'] in physical for e in obs['endpoints']),
        'actual_shadow_no_regulator_outputs')
    topics = c36.load(run/'topics.json')['topics']
    decoded, raw_rows, storage = p.base.read_actual_storage(run/'recorder/bag', topics)
    observer = c36.lines(run/'observer/source.jsonl'); ws = c36.lines(run/'worker/source.jsonl')
    transport = p.base.transport_join(raw_rows, c36.lines(run/'synthetic_source/transport_source.jsonl'), manifests, topics)
    source = p.base.source_typed_join(observer, ws, decoded)
    for name, report in (('whole_transport_storage', transport), ('whole_Job_Candidate_source_storage', source)):
        c.need(report.get('passed') is True, name, issues=report.get('issues'))
    pubs = p.worker_publication_population(run, inputs, ws, observer, decoded, worker, c)
    get = lambda kind: [r for r in observer if r.get('type') == kind]
    close = get('adapter_driver_close_observed'); rejected_close = get('adapter_close_evidence_failed')
    close_observation = c36.load(run/'c38_close_observation.json')
    c.need(len(close) == 1 and not rejected_close and close_observation.get('observer') == close[0]
        and close[0].get('request_sha256') == c36.sha(run/'adapter_driver_close_request.json'),
        'actual_driver_close_observed_and_ack_once')
    close_request = c36.load(run/'adapter_driver_close_request.json')
    c.need(close_request.get('schema') == 'p1-C3.6-driver-close-request-v1'
        and close_request.get('run_id') == inputs['run_id']
        and close_request.get('boot_id') == obs['boot_id']
        and close_request.get('driver_pid') == peer['driver']['pid']
        and close_request.get('driver_start_ticks') == peer['driver']['start_ticks']
        and close_request.get('driver_tool_sha256') == peer['driver_tool_sha256']
        and close_request.get('owner_manifest_sha256') == c36.sha(run/'publisher/owned_manifest.json')
        and close_request.get('stage_qualified') is False
        and c36.integer(close_request.get('request_ns'), 1)
        and close_request.get('request_ns') == (close[0]['requested_ns'] if len(close) == 1 else None),
        'actual_close_file_exact_current_driver_owner_and_Source_request_time')
    closing_ns = close[0]['observed_ns'] if len(close) == 1 else 0
    c.need(c36.integer(closing_ns, 1), 'actual_close_time_positive')
    c.need(not [r for r in get('job') if r['submit_commit_ns'] > closing_ns], 'no_new_Job_after_actual_close')
    c.need(not [r for r in get('decision') if r.get('accepted') is True
                and r['activation_commit_ns'] > closing_ns], 'no_new_Accepted_after_actual_close')
    proof = c36.load(run/'c39_worker_exit_proof.json'); proof_ns = proof.get('proof_ns')
    ledger = c36.lines(run/'owned_process_ledger.jsonl')
    role_pin_population(run, inputs, result, manifests, c36.load(run/'preparation_evidence.json'), ledger, c)
    signals = [r for r in ledger if r.get('type') == 'signal' and r.get('name') == 'worker']
    c.need(proof.get('schema') == 'p1-C3.9-worker-exit-proof-v1'
        and proof.get('run_id') == worker['run_id'] and proof.get('boot_id') == worker['boot_id']
        and proof.get('worker_pid') == worker['pid'] and proof.get('worker_start_ticks') == worker['process_start_ticks']
        and proof.get('worker_manifest_sha256') == c36.sha(run/'worker/owned_manifest.json')
        and c36.integer(proof_ns, 1) and proof.get('remaining_members') == []
        and proof.get('returncode') == result['owned_role_returncodes']['worker'] == 0
        and proof.get('cleanup', {}).get('cleanup_complete') is True
        and proof.get('cleanup', {}).get('remaining_members') == []
        and proof.get('endpoint_exit') == 'unknown' and proof.get('stage_qualified') is False,
        'actual_Worker_exit_reap_exact_manifest_process_identity')
    c.need(len(signals) == 1 and signals[0].get('signal') == 2
        and signals[0].get('boot_id') == worker['boot_id']
        and closing_ns <= signals[0]['monotonic_ns'] < proof_ns,
        'actual_close_ack_then_Worker_SIGINT_then_reap_proof')
    c.need(c36.integer(pubs.get('Worker_Source_finished_ns'), 1)
        and pubs['Worker_Source_finished_ns'] < proof_ns,
        'whole_Worker_Source_sender_terminal_before_scoped_exit_proof')
    paused = get('diagnostic_c38_gate_paused'); resumed = get('diagnostic_c38_gate_resumed')
    c.need(len(paused) == len(resumed) == 1 and not get('diagnostic_c38_gate_timeout')
        and not get('diagnostic_c38_gate_rejected'), 'actual_Worker_group_gate_finite')
    if len(paused) == len(resumed) == 1:
        c.need(paused[0].get('gate_interface') == resumed[0].get('gate_interface') == 'worker'
            and paused[0].get('group_registered') is False and resumed[0].get('group_registered') is True
            and paused[0]['checked_ns'] < closing_ns <= proof_ns <= resumed[0]['checked_ns'],
            'actual_worker_gate_pause_close_exit_resume_order')
        for action, event in [('pause', paused[0]), ('resume', resumed[0])]:
            request_path = run/('c38_'+action+'_request.json'); request = c36.load(request_path)
            c.need(event.get('request_sha256') == c36.sha(request_path)
                and request.get('schema') == 'p1-C3.8-applied-gate-v1'
                and request.get('action') == action and request.get('seq') == (1 if action == 'pause' else 2)
                and request.get('run_id') == inputs['run_id'] and request.get('boot_id') == worker['boot_id']
                and request.get('driver_pid') == peer['driver']['pid']
                and request.get('driver_start_ticks') == peer['driver']['start_ticks']
                and request.get('driver_tool_sha256') == peer['driver_tool_sha256']
                and request.get('owner_manifest_sha256') == c36.sha(run/'publisher/owned_manifest.json')
                and request.get('stage_qualified') is False,
                'actual_gate_request_complete_original_owner_driver_binding', action=action)
        queued = c36.load(run/'c39_queued_publication.json')
        publication = queued.get('candidate_publication', {})
        candidate_results = [r for r in ws if r.get('type') == 'candidate_publish_result']
        c.need(queued.get('schema') == 'p1-C3.9-queued-publications-v1'
            and queued.get('stage_qualified') is False and exact(queued.get('gate_paused'), paused[0])
            and any(exact(publication, r) for r in candidate_results)
            and publication.get('success') is True
            and c36.integer(publication.get('publish_start_ns'), 1)
            and paused[0]['checked_ns'] < publication['publish_start_ns']
            <= publication.get('publish_end_ns', 0) < signals[0]['monotonic_ns'] < proof_ns,
            'actual_successful_candidate_publication_while_worker_readers_paused_before_exit')
        c.need(publication_before_close(publication, queued.get('checked_ns'), close[0]),
               'queued_Candidate_call_completed_before_actual_driver_request_read_and_close')
        capability_publication = queued.get('capability_publication', {})
        capability_results = [r for r in ws if r.get('type') == 'capability_publish_result']
        c.need(any(exact(capability_publication, r) for r in capability_results)
            and capability_publication.get('returned') is True and capability_publication.get('threw') is False
            and c36.integer(capability_publication.get('publish_start_ns'), 1)
            and paused[0]['checked_ns'] < capability_publication['publish_start_ns']
            <= capability_publication.get('publish_end_ns', 0) < signals[0]['monotonic_ns'] < proof_ns,
            'actual_successful_capability_publication_while_worker_readers_paused_before_exit')
        c.need(publication_before_close(capability_publication, queued.get('checked_ns'), close[0]),
               'queued_Capability_call_completed_before_actual_driver_request_read_and_close')
        for kind in p.WORKER:
            c.need(c36.integer(paused[0].get(kind+'_received'))
                and c36.integer(paused[0].get(kind+'_callback_sequence'))
                and paused[0].get(kind+'_received') == paused[0].get(kind+'_callback_sequence')
                == resumed[0].get(kind+'_received') == resumed[0].get(kind+'_callback_sequence')
                and paused[0].get(kind+'_callback_sequence') == resumed[0].get(kind+'_callback_sequence'),
                'no_Worker_callback_dispatch_during_actual_group_pause', interface=kind)
    receipts, raw_worker = worker_population(observer, decoded, worker, proof_ns, c)
    expected = {k: worker[k] for k in ('run_id', 'boot_id')}
    expected.update(contract_hash=worker['contract_sha256'], nominal_hash=worker['nominal_hash'],
        pid=worker['pid'], fault_injection_enabled=p.worker_fault_permission(worker, c))
    lease = p.lease.replay(observer, expected, obs['contract_configuration']['worker_capability_receipt_timeout_ns'],
        c.need, decode_raw=lambda raw, index: raw_worker['capability'].get(raw['callback_sequence']), require_observation=True)
    c.need(lease['callbacks'] == receipts['capability']['live_typed_received'],
           'exact_lease_replay_population_excludes_all_post_exit_early_guards')
    witness = p.witness_source_population(c36.load(run/'observer/witness.json'),
        c36.load(run/'expected_witness_header.json'), observer, c)
    publisher = p.base.publisher_join(c36.load(run/'publisher/session_summary.json'), decoded,
        c36.load(run/'publisher/startup_manifest.json'), pub)
    c.need(publisher.get('passed') is True, 'whole_originalF5_session_storage', issues=publisher.get('issues'))
    owner_proof = c36.load(run/'c38_owner_exit_proof.json')
    c.need(owner_proof.get('publisher_pid') == pub['pid']
        and owner_proof.get('publisher_start_ticks') == pub['process_start_ticks']
        and owner_proof.get('owner_manifest_sha256') == c36.sha(run/'publisher/owned_manifest.json')
        and owner_proof.get('remaining_members') == []
        and owner_proof.get('returncode') == result['owned_role_returncodes']['publisher'] == 0
        and c36.integer(owner_proof.get('proof_ns'), 1) and proof_ns < owner_proof['proof_ns'],
        'actual_originalF5_scoped_exit_proof_after_Worker_exit')
    applied = applied_population(observer, decoded, pub, close, c)
    for row in get('adapter_closed_after_join'):
        c.need(row['evidence']['actual_regulator_publish'] is False
            and row['owner_endpoints_exited'] == 'unknown', 'no_physical_release_inference')
    recorder = c36.load(run/'recorder/terminal.json')
    c.need(recorder.get('clean') is True and recorder.get('prepared') is True
        and recorder.get('Recorder_stop_completed') is True and recorder.get('metadata_exists') is True
        and recorder.get('metadata_sha256') == c36.sha(run/'recorder/bag/metadata.yaml')
        and recorder.get('storage_id') == 'sqlite3'
        and recorder.get('manifest_sha256') == c36.sha(run/'recorder/owned_manifest.json'),
        'actual_SQLite_recorder_terminal')
    terminal = c36.load(run/'synthetic_source/terminal.json')
    c.need(terminal.get('normal_end') is True and terminal.get('failed') is False
        and terminal.get('run_id') == inputs['run_id'] and terminal.get('transport_counts') == transport['counts']
        and terminal.get('transport_total') == sum(transport['counts'].values()), 'whole_synthetic_transport_terminal_counts')
    assets = p.asset_pins(inputs, c)
    deps = [Path(__file__), HERE/'prepare_fixture.py', HERE/'runtime/owned_process_supervisor.py',
        HERE/'check_c38_owned_close.py', HERE/'check_c37_owned_run_v2.py',
        HERE/'check_c36_adapter_run.py', HERE/'check_owned_fixture.py', HERE/'runtime/check_p1_execution.py',
        HERE/'runtime/check_p1_witness_v2.py', HERE/'lease_replay_v1.py', HERE/'owned_auth.py', HERE/'owned_release.py']
    for dep in deps:
        rel = str(dep.relative_to(HERE)); snapshot_path = run/(rel.replace('/', '__')+'.snapshot')
        c.need(inputs.get('tool_sha256', {}).get(rel) == c36.sha(dep)
            and snapshot_path.is_file() and c36.sha(snapshot_path) == c36.sha(dep),
            'prerun_checker_dependency_exact', tool=rel)
    after = {str(f): c36.sha(f) for f in files}
    c.need(before == after, 'all_raw_run_files_unchanged')
    c.need(all(c36.sha(path) == value for path, value in assets.items()), 'author_assets_unchanged_during_check')
    return c.result(schema=SCHEMA, run_dir=str(run), case='worker_post_exit',
        diagnostic_case_predicate_passed=not c.issues, normal_driver_passed=result.get('passed'),
        diagnostic_only=True, qualifications=FLAGS, unknowns=p.UNKNOWNS,
        resource_cleanup_complete=result.get('cleanup_complete'), worker_callbacks=receipts,
        worker_publications=pubs, capability_receipt_lease={'callbacks': lease['callbacks'], 'final': lease['final']},
        witness_v2=witness, storage=storage, transport_storage=transport, source_typed_storage=source,
        applied_callbacks=applied, publisher_session=publisher,
        input_sha256_before=before, input_sha256_after=after, author_asset_sha256=assets,
        checker_dependencies={str(dep): c36.sha(dep) for dep in deps}, checker_sha256=c36.sha(__file__),
        all_published_received_claimed=False, window_clipped=False,
        rejected_received_CDR_proven=False, rejected_candidate_payload_identity_proven=False,
        rejected_Capability_packet_identity_proven=False, normal_business_contract_qualified=False)


def applied_population(observer, decoded, pub, close, checker):
    """C3.8 unchanged original owner/strict queued-zero policy, complete callbacks."""
    rows = [r for r in observer if r.get('type') == 'adapter_applied_callback']
    closure = [r for r in observer if r.get('type') == 'adapter_applied_reception_closed']
    checker.need(len(closure) == 1 and closure[0].get('executor_detached') is True
        and closure[0].get('legacy_received') == closure[0].get('raw_callback_sequence') == len(rows),
        'entire_actual_Applied_received_counter_closure')
    endpoints = [e for e in pub['endpoints'] if e.get('kind') == 'publisher' and e.get('topic') == c36.APPLIED]
    checker.need(len(endpoints) == 1, 'owner_manifest_unique_Applied_GID')
    gid = endpoints[0]['gid'] if len(endpoints) == 1 else None
    recorded = {r['message']['sequence']: r['message'] for r in decoded[c36.APPLIED]}
    checker.need(len(recorded) == len(decoded[c36.APPLIED]), 'stored_Applied_sequence_unique')
    checker.need([r.get('raw_input', {}).get('callback_sequence') for r in rows] == list(range(1, len(rows)+1)),
                 'all_Applied_callback_sequences')
    anchors = [r for r in observer if r.get('type') == 'legacy_anchor']
    rejections = [r for r in observer if r.get('type') == 'adapter_applied_auth_rejected']
    last_anchor = [0., 0.]
    for r in observer:
        if r.get('type') == 'legacy_anchor': last_anchor = r['final_n']
        elif r.get('type') == 'adapter_applied_auth_rejected':
            checker.need(exact(r['anchor_after'], last_anchor), 'denied_owner_receipt_keeps_anchor', sequence=r['sequence'])
    report = []
    for r in rows:
        raw = r['raw_input']; seq = r['sequence']; m = p.decode_callback(raw, checker, {'sequence': seq})
        checker.need(m is not None and seq in recorded and exact(m, recorded.get(seq)),
                     'whole_typed_Applied_received_CDR_Storage_binding', sequence=seq)
        checker.need(exact(raw.get('publisher_gid'), gid) and raw.get('rmw_implementation') == 'rmw_fastrtps_cpp'
            and raw['entry_steady_ns'] <= r['processed_ns'] <= closure[0]['closed_ns'],
            'actual_original_Applied_Writer_metadata_and_window', sequence=seq)
        if m is None: continue
        permitted = c38.tail_permitted(m, r['authentication_reason'], True,
            close[0]['requested_ns'] if len(close) == 1 else 0,
            close[0]['observed_ns'] if len(close) == 1 else 0, r['processed_ns'])
        checker.need(r.get('queued_terminal_tail') is permitted, 'original_post_exit_tail_predicate_exact', sequence=seq)
        if r['authentication_reason']:
            checker.need((any(a['sequence'] == seq for a in anchors) if permitted else
                any(a['sequence'] == seq for a in rejections) and not any(a['sequence'] == seq for a in anchors)),
                'original_Applied_post_exit_auth_admission_exact', sequence=seq)
        report.append({'sequence': seq, 'authentication_reason': r['authentication_reason'], 'queued_terminal_tail': permitted})
    return {'received': len(rows), 'recorded': len(recorded), 'population': report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try: report = analyze(args.run_dir)
    except Exception as error:
        report = {'schema': SCHEMA, 'passed': False, 'reader_error': repr(error),
                  'diagnostic_only': True, 'qualifications': FLAGS}
    size = c38.write(args.output, report)
    print(json.dumps({'passed': report['passed'], 'issues': report.get('issues'),
                      'reader_error': report.get('reader_error'), 'bytes': size}))
    return 0 if report['passed'] else 2


if __name__ == '__main__': raise SystemExit(main())
