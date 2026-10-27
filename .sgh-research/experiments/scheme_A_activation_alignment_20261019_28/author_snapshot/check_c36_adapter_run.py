#!/usr/bin/env python3
"""Closed-lifecycle checker for one preregistered C3.6 owned shadow adapter run.

This is an offline component check. It decodes every stored message and every
Applied callback typed reserialization, checks complete population joins, and
keeps preliminary component operations distinct from final business commits.
It never confers a phase or research qualification. No run input is modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / 'runtime')]
import check_owned_fixture as base
from check_p1_execution import exact, plain, projection, JOB_FIELDS, JOB_ALIASES
from owned_release import create_only_json
from owned_auth import parameter_digest

APPLIED = '/research/control/applied'
APPLIED_TYPE = 'usv_research_interfaces/msg/AppliedControl'
MAX_BYTES = 128 * 1024 * 1024
MAX_ROWS = 20000
MAX_CALLBACK_CDR = 1048576
T_NS = 200000000
READY_NS = 150000000
TAIL_NS = 2000000000
ROLES = {'publisher', 'observer', 'worker', 'synthetic_source', 'recorder'}
QUALIFICATIONS = {key: False for key in ('strict_full_chain', 'D1', 'B4', 'B5',
    'M0b', 'M4', 'F6', 'P1', 'execute', 'dynamic_20s_R5', 'mixed_turn',
    'research_conclusion')}
UNKNOWNS = {key: 'unknown' for key in ('owner_close_intent',
    'owner_endpoints_exited_at_adapter_close', 'continuous_DDS_uniqueness',
    'post_pin_exec_continuity', 'Worker_callback_GID_authentication',
    'MasterClock', 'plant_acceptance', 'WCET')}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON: '+x)))


def load(path):
    raw = Path(path).read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('missing/oversized JSON: ' + str(path))
    return strict(raw)


def lines(path):
    raw = Path(path).read_bytes()
    if not raw or len(raw) > MAX_BYTES or not raw.endswith(b'\n'):
        raise ValueError('source missing/unclosed/oversized: '+str(path))
    rows = raw.splitlines()
    if len(rows) > MAX_ROWS or any(not x for x in rows):
        raise ValueError('source row budget/blank line: '+str(path))
    result = [strict(x) for x in rows]
    if any(not isinstance(x, dict) for x in result):
        raise ValueError('source row is not object: '+str(path))
    return result


def integer(v, lower=0):
    return type(v) is int and lower <= v <= (1 << 63)-1


def vector(v, size):
    return isinstance(v, list) and len(v) == size and all(
        type(x) in (int, float) and math.isfinite(x) for x in v)


class Checks:
    def __init__(self):
        self.issues = []
        self.checked = Counter()

    def need(self, condition, code, **context):
        self.checked[code] += 1
        if not condition:
            self.issues.append({'code': code, **context})

    def index(self, rows, key, label):
        out = {}
        for row in rows:
            ident = key(row)
            self.need(ident not in out, 'duplicate_'+label, identity=ident)
            out[ident] = row
        return out

    def result(self, **extra):
        return {'passed': not self.issues, 'checks': dict(self.checked),
                'issues': self.issues, **extra}


def callback_population(observer, applied, publisher_manifest, close, checker):
    """Actual MessageInfo GID plus full typed CDR; no original wire-padding claim."""
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message
    cls = get_message(APPLIED_TYPE)
    callbacks = [r for r in observer if r['type'] == 'adapter_applied_callback']
    observed = [r for r in observer if r['type'] == 'adapter_applied_observed']
    anchors = [r for r in observer if r['type'] == 'legacy_anchor']
    publisher_endpoints = [r for r in publisher_manifest['endpoints']
        if r['kind'] == 'publisher' and r['topic'] == APPLIED and r['type'] == APPLIED_TYPE]
    checker.need(len(publisher_endpoints) == 1, 'unique_manifest_Applied_endpoint')
    expected_gid = publisher_endpoints[0]['gid'] if len(publisher_endpoints) == 1 else None
    count = len(applied)
    checker.need(count > 0, 'actual_Applied_nonempty')
    sequences = list(range(1, count+1))
    checker.need([r['message'].get('sequence') for r in applied] == sequences,
                 'entire_storage_Applied_sequence')
    for label, rows in (('callback', callbacks), ('component_observation', observed), ('legacy_anchor', anchors)):
        checker.need([r.get('sequence') for r in rows] == sequences,
                     'entire_Applied_'+label+'_population', count=len(rows), storage_count=count)
    storage_by_sequence = {r['message']['sequence']: r['message'] for r in applied}
    callback_messages = {}
    tail_count = 0
    later_alive_snapshot_false_count = 0
    for row in callbacks:
        seq = row.get('sequence')
        raw = row.get('raw_input')
        if not isinstance(raw, dict):
            checker.need(False, 'callback_full_raw_missing', sequence=seq)
            continue
        checker.need(raw.get('schema') == 'p1-input-callback-full-cdr-v1'
            and raw.get('topic') == APPLIED and raw.get('message_type') == APPLIED_TYPE
            and raw.get('rmw_implementation') == 'rmw_fastrtps_cpp'
            and raw.get('from_intra_process') is False,
            'callback_actual_interface', sequence=seq)
        checker.need(raw.get('publisher_gid') == expected_gid and row.get('expected_gid') == expected_gid,
                     'callback_owned_Applied_GID', sequence=seq)
        checker.need(integer(raw.get('callback_sequence'), 1)
            and integer(raw.get('entry_steady_ns'), 1)
            and integer(row.get('processed_ns'), 1)
            and raw['entry_steady_ns'] <= row['processed_ns'],
            'callback_time_order', sequence=seq)
        text = raw.get('cdr_hex')
        if not isinstance(text, str) or len(text) > 2*MAX_CALLBACK_CDR:
            checker.need(False, 'callback_CDR_domain', sequence=seq)
            continue
        try:
            blob = bytes.fromhex(text)
            checker.need(0 < len(blob) <= MAX_CALLBACK_CDR and raw.get('cdr_bytes') == len(blob)
                and raw.get('cdr_sha256') == hashlib.sha256(blob).hexdigest(),
                'callback_complete_CDR_sha', sequence=seq)
            message = plain(dict(message_to_ordereddict(deserialize_message(blob, cls))))
        except Exception as error:
            checker.need(False, 'callback_CDR_decode', sequence=seq, error=repr(error))
            continue
        callback_messages[seq] = message
        checker.need(exact(message, storage_by_sequence.get(seq)),
                     'callback_storage_full_typed_payload', sequence=seq)
        checker.need(message.get('plant_acceptance_observed') is False
            and message.get('force_measured') is False
            and message.get('execution_atomicity_proven') is False,
            'Applied_is_command_observation', sequence=seq)
        authentication = row.get('authentication_reason')
        tail = row.get('queued_terminal_tail')
        checker.need(type(tail) is bool, 'callback_tail_flag_typed', sequence=seq)
        if tail is True:
            tail_count += 1
            bound = close.get('requested_ns')
            observed_bound = close.get('observed_ns')
            checker.need(authentication == 'owner_process_exited'
                and row.get('owner_process_alive') is False
                and integer(bound,1) and integer(observed_bound,1)
                and bound <= observed_bound <= row['processed_ns'] <= bound+TAIL_NS
                and message.get('control_source')=='shutdown_zero'
                and message.get('final_n')==[0.,0.]
                and message.get('left_publish_success') is True
                and message.get('right_publish_success') is True
                and bound <= message['left_publish_start_steady_ns']
                    <= message['left_publish_end_steady_ns']
                    <= message['right_publish_start_steady_ns']
                    <= message['right_publish_end_steady_ns'] <= row['processed_ns'],
                'queued_terminal_tail_narrow_policy', sequence=seq)
        else:
            # callback_reason authenticates at its own zero-wait poll. The
            # later evidence poll can observe an exit between the two calls.
            checker.need(authentication=='' and type(row.get('owner_process_alive')) is bool,
                         'live_callback_owner_authentication_guard', sequence=seq)
            later_alive_snapshot_false_count += row.get('owner_process_alive') is False
    checker.need(len({r.get('raw_input', {}).get('callback_sequence') for r in callbacks
        if isinstance(r.get('raw_input'), dict)}) == len(callbacks), 'callback_sequence_uniqueness')
    for row in anchors:
        seq = row['sequence']
        message = callback_messages.get(seq)
        checker.need(exact(row.get('applied'), message) and row.get('applied_text_truncated') is False,
                     'legacy_anchor_full_callback_payload', sequence=seq)
        if message is not None:
            expected = {'command_n': message['final_n'], 'command_known': [True, True],
                'command_sequence': [seq, seq], 'command_publish_ns':
                [message['left_publish_start_steady_ns'], message['right_publish_start_steady_ns']]}
            components = [r for r in observed if r['sequence'] == seq]
            checker.need(len(components) == 1 and components[0].get('reason') == ''
                and all(exact(components[0].get('evidence', {}).get(k), v) for k,v in expected.items()),
                'component_anchor_actual_command_binding', sequence=seq)
    for kind in ('adapter_applied_auth_rejected', 'adapter_applied_resource_rejected',
                 'legacy_admission_rejected', 'legacy_history_reset', 'adapter_close_evidence_failed'):
        checker.need(not any(r['type'] == kind for r in observer), 'normal_run_no_'+kind)
    return {'storage': count, 'callbacks': len(callbacks), 'component_observations': len(observed),
        'legacy_anchors': len(anchors), 'queued_terminal_tail_count': tail_count,
        'expected_owned_gid': expected_gid,
        'later_alive_snapshot_false_after_live_guard_count':later_alive_snapshot_false_count,
        'callback_CDR_semantics': 'typed reserialization of received message; original network padding unclaimed'}


def component_population(observer, close, checker):
    events = [r for r in observer if r['type'].startswith('adapter_')]
    with_evidence = [r for r in events if isinstance(r.get('evidence'), dict)]
    required_evidence = {'adapter_applied_observed', 'adapter_job_import',
        'adapter_candidate_ready', 'adapter_final_commit', 'adapter_driver_close_observed',
        'adapter_closed_after_join'}
    anchor = {'command_n': [0.,0.], 'command_known': [False, False],
        'command_sequence': [0,0], 'command_publish_ns': [0,0]}
    closing = False
    for row in observer:
        kind = row['type']
        if kind not in required_evidence:
            continue
        evidence = row.get('evidence')
        checker.need(isinstance(evidence, dict), 'component_event_evidence_present', event=kind)
        if not isinstance(evidence, dict):
            continue
        if kind == 'adapter_applied_observed' and row.get('reason') == '':
            anchor = {k: evidence.get(k) for k in anchor}
        if kind == 'adapter_driver_close_observed':
            closing = True
        checker.need(evidence.get('profile') == 'C3.6-shadow-adapter'
            and evidence.get('active_publish_transaction') is False
            and evidence.get('actual_regulator_publish') is False
            and evidence.get('plant_acceptance_observed') is False
            and type(evidence.get('job_pending')) is bool,
            'component_observation_only_facts', event=kind)
        checker.need(all(exact(evidence.get(k), v) for k,v in anchor.items()),
                     'component_anchor_changes_only_from_Applied', event=kind)
        checker.need(evidence.get('closing_requested') is closing
            and (not closing or evidence.get('job_pending') is False),
            'component_closing_cancels_pending', event=kind)
        if kind == 'adapter_closed_after_join':
            checker.need(row.get('reason') == '' and evidence.get('component_lifecycle') == 4
                and evidence.get('job_pending') is False and row.get('owner_endpoints_exited') == 'unknown',
                'component_closed_after_join')
    checker.need(len([r for r in observer if r['type'] == 'adapter_closed_after_join']) == 1,
                 'component_closed_event_once')
    return {'event_counts': dict(Counter(r['type'] for r in events)),
        'evidence_population': len(with_evidence), 'active_publish_transaction_observed': False,
        'actual_regulator_publish_observed': False}


def business_population(observer, worker, close, cfg, checker):
    get = lambda kind: [r for r in observer if r['type'] == kind]
    jobs = checker.index(get('job'), lambda r:r['job']['job_id'], 'source_job')
    imports = checker.index(get('adapter_job_import'), lambda r:r['job_id'], 'adapter_import')
    candidates = checker.index([r for r in worker if r['type'] == 'candidate'], lambda r:r['job']['job_id'], 'worker_candidate')
    ready = checker.index(get('adapter_candidate_ready'), lambda r:r['job_id'], 'adapter_ready')
    registrations = checker.index(get('candidate_registration'), lambda r:r['job']['job_id'], 'candidate_registration')
    decisions = get('decision')
    finals = checker.index(get('adapter_final_commit'), lambda r:r['tick'], 'adapter_final_tick')
    checker.need(bool(jobs) and bool(candidates) and bool(decisions), 'actual_business_populations_nonempty')
    checker.need(set(candidates) == set(registrations), 'candidate_registration_entire_population')
    checker.need(set(jobs) == {k for k,r in imports.items() if r.get('reason') == ''},
                 'successful_adapter_import_entire_job_population')
    checker.need(set(jobs) == set(candidates), 'job_worker_candidate_entire_population')
    checker.need({r['tick'] for r in decisions} == set(finals), 'adapter_final_entire_decision_population')
    checker.need([r['sequence'] for r in decisions] == list(range(1,len(decisions)+1)),
                 'decision_complete_sequences')
    accepted_registrations = {k for k,r in registrations.items() if r.get('accepted_registration') is True}
    checker.need(accepted_registrations <= set(ready), 'accepted_registration_has_adapter_ready')
    anchors = get('legacy_anchor')
    def prefix(bound):
        receipts = [r for r in anchors if r['processed_ns'] <= bound]
        held = []
        for r in receipts:
            m = r['applied']
            for channel, side in enumerate(('left','right')):
                held.append((m[side+'_sim_time_ns'], channel, m['final_n'][channel]))
        expected = {'anchor_n':[0.,0.], 'anchor_sequence':[0,0],
            'anchor_publish_ns':[0,0], 'anchor_known':[False,False]}
        if receipts:
            r = receipts[-1]
            expected = {'anchor_n':r['final_n'],'anchor_sequence':[r['sequence']]*2,
                'anchor_publish_ns':r['publish_ns'],'anchor_known':r['known']}
        return expected, held[-cfg['history_capacity']:]
    # Frozen anchors and complete held history are independently reconstructed
    # from the actual admitted full Applied callback population.
    for ident, row in jobs.items():
        j = row['job']; canonical = projection(j, JOB_FIELDS, JOB_ALIASES)
        deadline = j['deadline_ns']; target = j['target_ns']; origin = j['tick_origin_ns']
        imp = imports.get(ident, {})
        checker.need(len(canonical) == len(JOB_FIELDS)
            and integer(ident,1) and j['target_tick'] > 0
            and deadline == origin+READY_NS and target == origin+T_NS
            and j['freeze_ns'] <= imp.get('submit_ns',0) <= row['submit_commit_ns'] <= deadline
            and imp.get('freeze_ns') == j['freeze_ns']
            and imp.get('import_linearization_ns') == imp.get('submit_ns')
            and row['submit_commit_ns'] < close['observed_ns'],
            'job_freeze_import_final_submit_time_contract', job_id=ident)
        frozen_anchor, history = prefix(j['freeze_ns'])
        checker.need(all(exact(j.get(k),v) for k,v in frozen_anchor.items())
            and exact([list(x) for x in zip(j['history_sim_ns'],j['history_channel'],j['history_n'])],[list(x) for x in history]),
            'job_frozen_anchor_and_entire_history_from_receipts', job_id=ident)
        candidate = candidates.get(ident, {})
        registration = registrations.get(ident, {})
        checker.need(exact(projection(candidate.get('job',{}), JOB_FIELDS, JOB_ALIASES),canonical)
            and exact(projection(registration.get('job',{}), JOB_FIELDS, JOB_ALIASES),canonical),
            'full_immutable_job_echoes', job_id=ident)
        checker.need(vector(j.get('target_state'),6)
            and vector(j.get('anchor_n'),2)
            and j.get('anchor_known') == [True,True]
            and len(j['history_sim_ns']) == len(j['history_channel']) == len(j['history_n']),
            'job_full_prediction_history_domain', job_id=ident)
        checker.need(candidate.get('solver_invoked') is True and candidate.get('success') is True
            and candidate.get('prediction_available') is True and candidate.get('backend') == 'acados'
            and vector(candidate.get('X'),6*(j['N']+1)) and vector(candidate.get('U'),2*j['N'])
            and vector(candidate.get('first_control'),2)
            and all(abs(a-b) <= 1e-7 for a,b in zip(candidate.get('X',[])[:6],j['target_state']))
            and all(abs(a-b) <= 1e-8 for a,b in zip(candidate.get('U',[])[:2],candidate.get('first_control',[]))),
            'candidate_complete_native_prediction_and_first_control', job_id=ident)
        if ident in ready:
            r = ready[ident]
            checker.need(r.get('preliminary_ready_ns') == r.get('commit_ns')
                and j['freeze_ns'] <= r['commit_ns'] <= registration['ready_commit_ns'],
                'adapter_ready_preliminary_before_completion', job_id=ident)
        if registration.get('accepted_registration') is True:
            r = ready.get(ident,{})
            checker.need(r.get('reason') == '' and candidate.get('success') is True
                and candidate['solve_end_ns'] <= registration['ready_commit_ns'] <= deadline
                and registration['ready_commit_ns'] < close['observed_ns']
                and registration.get('reason') == ''
                and exact(registration.get('first_control'), candidate.get('first_control')),
                'accepted_registration_final_completion_contract', job_id=ident)
    decision_histogram = Counter()
    accepted = []
    for d in decisions:
        f = finals.get(d['tick'], {})
        decision_histogram[d.get('reason')] += 1
        checker.need(d.get('mode') == 'shadow' and d.get('diagnostic_only') is True
            and d.get('publish_success') == [False, False]
            and d.get('publish_start_ns') == [0,0] and d.get('publish_end_ns') == [0,0]
            and d.get('plant_acceptance_observed') is False,
            'decision_has_no_regulator_publication', sequence=d['sequence'])
        checker.need(f.get('inspection_linearization_ns') == f.get('commit_ns')
            and integer(f.get('commit_ns'),1)
            and f['commit_ns'] <= d['activation_commit_ns'] <= d['end_ns']
            and f.get('job_id') == d['job_id'],
            'inspection_before_final_activation_completion', sequence=d['sequence'])
        if d['job_id']:
            jrow = jobs.get(d['job_id']); reg = registrations.get(d['job_id'])
            checker.need(jrow is not None and reg is not None, 'activation_refers_to_complete_job_registration', sequence=d['sequence'])
            if jrow is not None and reg is not None:
                j = jrow['job']
                checker.need(reg.get('accepted_registration') is True
                    and d['ready_commit_ns'] == reg['ready_commit_ns']
                    and d['tick'] == j['target_tick']
                    and d['activation_commit_ns'] >= j['target_ns'],
                    'activation_complete_job_ready_tick_binding', sequence=d['sequence'])
        if d.get('accepted') is True:
            accepted.append(d['sequence'])
            checker.need(d['job_id'] > 0 and d['activation_commit_ns'] < close['observed_ns']
                and d['activation_commit_ns']-d['planned_ns'] <= cfg['tick_jitter_ns']
                and f.get('reason') == '' and type(f.get('owner_process_alive')) is bool,
                'accepted_activation_final_completion_contract', sequence=d['sequence'])
        if d['activation_commit_ns'] >= close['observed_ns']:
            checker.need(d.get('accepted') is False, 'no_activation_after_observed_driver_close', sequence=d['sequence'])
    return {'jobs': len(jobs), 'candidates': len(candidates),
        'registrations': len(registrations), 'accepted_registrations': len(accepted_registrations),
        'decisions': len(decisions), 'accepted_decision_sequences': accepted,
        'decision_reason_counts': dict(decision_histogram),
        'acceptance_count_is_not_hard_coded': True,
        'preliminary_component_points_are_final_business_commits': False}


def close_population(run, inputs, result, peer, observer, publisher, checker):
    request = load(run/'adapter_driver_close_request.json')
    ack = load(run/'adapter_driver_close_ack.json')
    closes = [r for r in observer if r['type'] == 'adapter_driver_close_observed']
    checker.need(len(closes) == 1, 'observed_driver_close_once')
    if len(closes) != 1:
        raise ValueError('missing or duplicated adapter close observation')
    close = closes[0]
    checker.need(request.get('schema') == 'p1-C3.6-driver-close-request-v1'
        and request.get('run_id') == inputs['run_id']
        and request.get('boot_id') == publisher['boot_id']
        and request.get('driver_pid') == peer['driver']['pid']
        and request.get('driver_start_ticks') == peer['driver']['start_ticks']
        and request.get('driver_tool_sha256') == peer['driver_tool_sha256']
        and request.get('owner_manifest_sha256') == peer['publisher_peer']['manifest_sha256'],
        'driver_close_request_identity')
    checker.need(close.get('request_sha256') == sha(run/'adapter_driver_close_request.json')
        and close.get('requested_ns') == request.get('request_ns')
        and integer(request.get('request_ns'),1)
        and request['request_ns'] <= close['read_completed_ns'] <= close['observed_ns'],
        'driver_close_request_actual_observation')
    checker.need(close.get('cancel_reason') == '' and close.get('driver_close_request') is True
        and close.get('owner_process_alive') is True
        and close.get('owner_close_intent') == 'unknown'
        and close.get('owner_endpoints_exited') == 'unknown'
        and request.get('owner_close_intent') == 'unknown'
        and request.get('owner_endpoints_exited') == 'unknown', 'driver_intent_not_owner_exit_claim')
    checker.need(ack.get('schema') == 'p1-C3.6-driver-close-ack-v1'
        and exact(ack.get('observer'),close)
        and ack.get('request_sha256') == close.get('request_sha256')
        and ack.get('publisher_still_alive') is True
        and close['observed_ns'] <= ack['driver_checked_ns'] <= request['request_ns']+1000000000
        and ack.get('owner_endpoints_exited') == 'unknown'
        and ack.get('stage_qualified') is False,
        'driver_close_ack_before_publisher_stop')
    ledger = lines(run/'owned_process_ledger.jsonl')
    signals = [r for r in ledger if r['type']=='signal' and r.get('name')=='publisher']
    checker.need(len(signals)==1 and signals[0].get('signal')==2
        and ack['driver_checked_ns'] <= signals[0]['monotonic_ns']
        and signals[0].get('boot_id')==publisher['boot_id'],
        'actual_publisher_SIGINT_after_close_ack')
    tail = load(run/'close_tail_ack.json')
    checker.need(result.get('terminal_tail_ack_sha256') == sha(run/'close_tail_ack.json')
        and tail.get('publisher_session_sha256') == sha(run/'publisher/session_summary.json')
        and tail.get('receiver_roles_alive') is True
        and tail.get('observer_last_applied_sequence') == tail.get('publisher_last_applied_sequence')
        and tail.get('complete_observer_anchor_count') == tail.get('publisher_last_applied_sequence')
        and tail.get('stage_qualified') is False,
        'complete_publisher_terminal_tail_ack')
    return close


def analyze(run):
    run = Path(run).resolve()
    checker_inputs = load(run/'checker_inputs.json')
    inputs = load(run/'inputs.json'); result = load(run/'result.json')
    required = ('bag','topics_file','transport_source','synthetic_terminal','publisher_session',
        'startup_manifest','observer_source','worker_source','witness','expected_witness_header','owned_manifests')
    if set(required)-set(checker_inputs):
        raise ValueError('incomplete checker input declaration')
    checker = Checks()
    checker.need(set(checker_inputs['owned_manifests']) == ROLES, 'complete_owned_role_manifest_set')
    declarations = {k: run/rel for k,rel in {
        'bag':'recorder/bag','topics_file':'topics.json','transport_source':'synthetic_source/transport_source.jsonl',
        'synthetic_terminal':'synthetic_source/terminal.json','publisher_session':'publisher/session_summary.json',
        'startup_manifest':'publisher/startup_manifest.json','observer_source':'observer/source.jsonl',
        'worker_source':'worker/source.jsonl','witness':'observer/witness.json',
        'expected_witness_header':'expected_witness_header.json'}.items()}
    checker.need(all(Path(checker_inputs[k]).resolve() == p for k,p in declarations.items()),
                 'declared_checker_inputs_are_current_run')
    checker.need(all(Path(p).resolve() == run/role/'owned_manifest.json'
        for role,p in checker_inputs['owned_manifests'].items()), 'manifest_paths_are_current_run')
    allfiles = [p for p in run.rglob('*') if p.is_file() and p.name != 'check_c36_adapter_run.json']
    before = {str(p):sha(p) for p in allfiles}
    manifests = {k:load(v) for k,v in checker_inputs['owned_manifests'].items()}
    peer = load(run/'adapter_peer_pins.json'); publisher = manifests['publisher']; observer_manifest = manifests['observer']
    observer = lines(checker_inputs['observer_source']); worker = lines(checker_inputs['worker_source'])
    topics = load(checker_inputs['topics_file'])['topics']
    decoded, raw_rows, storage = base.read_actual_storage(checker_inputs['bag'], topics)
    transport = base.transport_join(raw_rows,lines(checker_inputs['transport_source']),manifests,topics)
    source = base.source_typed_join(observer,worker,decoded)
    publisher_join = base.publisher_join(load(checker_inputs['publisher_session']),decoded,
        load(checker_inputs['startup_manifest']),publisher)
    witness = base.witness_source_join(load(checker_inputs['witness']),load(checker_inputs['expected_witness_header']),observer)
    for name, report in (('transport_storage',transport),('source_typed_storage',source),
                         ('publisher_session',publisher_join),('source_fixed_witness',witness)):
        checker.need(report.get('passed') is True, name+'_passed', issues=report.get('issues'))
    checker.need(result.get('passed') is True and result.get('released') is True
        and result.get('mode') == 'positive' and inputs.get('mode') == 'positive'
        and inputs.get('measurement_seconds') == 4 and inputs.get('close_policy') == 'publisher-first'
        and result.get('cleanup_complete') is True and result.get('cleanup_within_budget') is True
        and result.get('evidence_qualification_clean') is True and result.get('close_errors') == []
        and result.get('ledger_failed') is False
        and set(result.get('cleanup',{})) == ROLES
        and all(r.get('cleanup_complete') is True and r.get('qualification_clean') is True
            and r.get('remaining_members') == [] for r in result.get('cleanup',{}).values())
        and result.get('owned_role_returncodes') == {r:0 for r in ROLES},
        'bounded_positive_driver_complete_and_clean')
    checker.need(peer['publisher_peer'].get('manifest_sha256') == sha(run/'publisher/owned_manifest.json')
        and peer['publisher_peer'].get('pid') == publisher['pid']
        and peer['publisher_peer'].get('process_start_ticks') == publisher['process_start_ticks']
        and peer['publisher_peer'].get('binary_sha256') == publisher['binary_sha256']
        and peer['publisher_peer'].get('effective_parameters_sha256') == publisher['effective_parameters_sha256']
        and peer['publisher_peer'].get('source_bundle_sha256') == publisher['source_bundle_sha256']
        and peer['publisher_peer'].get('topic') == APPLIED and peer['publisher_peer'].get('type') == APPLIED_TYPE,
        'adapter_peer_complete_publisher_pins')
    parameters = observer_manifest['effective_parameters']
    checker.need(parameters['mode']['value'] == 'shadow'
        and parameters['adapter_peer_pins_file']['value'] == str(run/'adapter_peer_pins.json')
        and parameters['adapter_peer_pins_sha256']['value'] == sha(run/'adapter_peer_pins.json')
        and parameters['adapter_driver_close_file']['value'] == str(run/'adapter_driver_close_request.json')
        and observer_manifest.get('adapter_pins_sha256') == sha(run/'adapter_peer_pins.json'),
        'effective_observer_adapter_configuration')
    binding = observer_manifest.get('adapter_peer_binding',{})
    checker.need(binding.get('schema')=='p1-owned-peer-C3_6-v1'
        and all(exact(binding.get(k),v) for k,v in peer['publisher_peer'].items()
            if k not in ('topic','type'))
        and binding.get('pidfd_alive_at_evidence_call') is True
        and binding.get('callback_policy')=='exact_DataWriter_GID_and_zero_wait_pidfd'
        and binding.get('continuous_DDS_uniqueness')=='unknown'
        and binding.get('post_pin_exec_continuity')=='unknown',
        'actual_observer_owned_peer_authentication_evidence')
    for role,m in manifests.items():
        expected_values = inputs['expected_parameters'][role]
        checker.need(m.get('effective_parameters_digest_encoding')=='p1-typed-ieee754-v1'
            and m.get('effective_parameters_immutable') is True
            and parameter_digest(m['effective_parameters'])==m['effective_parameters_sha256']
            and exact({k:v['value'] for k,v in m['effective_parameters'].items()},expected_values),
            'full_effective_configuration_source', role=role)
        checker.need(m.get('execute_qualified') is False and m.get('physical_release_qualified') is False,
            'owned_role_no_phase_qualification', role=role)
        if role != 'recorder':
            query = load(run/('live_parameters_'+role+'.json'))
            checker.need(exact(query,m['effective_parameters'])
                and result.get('live_parameter_queries',{}).get(role,{}).get('complete_name_set') is True
                and result.get('live_parameter_queries',{}).get(role,{}).get('mutation_rejected') is True,
                'external_full_live_configuration_receipt', role=role)
    wm = manifests['worker']
    capabilities = decoded.get('/p1/worker_capability',[])
    checker.need(bool(capabilities) and all(all(exact(row['message'].get(k),v) for k,v in {
        'run_id':wm['run_id'],'boot_id':wm['boot_id'],'contract_hash':wm['contract_sha256'],
        'nominal_hash':wm['nominal_hash'],'worker_instance':wm['worker_instance'],'pid':wm['pid']}.items())
        for row in capabilities), 'stored_Worker_capability_identity_entire_population')
    physical = {publisher['effective_parameters'][name]['value']
        for name in ('vrx_left_thrust_topic','vrx_right_thrust_topic')}
    checker.need(observer_manifest.get('physical_publisher_endpoints') == 0
        and not any(e['kind']=='publisher' and e['topic'] in physical for e in observer_manifest['endpoints']),
        'observer_has_no_physical_publisher_endpoint')
    checker.need(len([r for r in observer if r['type']=='legacy_ready']) == 1,
                 'existing_legacy_readiness_source_once')
    recorder = load(run/'recorder/terminal.json')
    checker.need(recorder.get('clean') is True and recorder.get('prepared') is True
        and recorder.get('Recorder_stop_completed') is True and recorder.get('metadata_exists') is True
        and recorder.get('metadata_sha256') == sha(run/'recorder/bag/metadata.yaml')
        and recorder.get('storage_id') == 'sqlite3'
        and recorder.get('manifest_sha256') == sha(run/'recorder/owned_manifest.json'),
        'actual_SQLite_recorder_terminal')
    terminal = load(checker_inputs['synthetic_terminal'])
    checker.need(terminal.get('normal_end') is True and terminal.get('failed') is False
        and terminal.get('run_id') == inputs['run_id']
        and terminal.get('transport_counts') == transport['counts']
        and terminal.get('transport_total') == sum(transport['counts'].values())
        and all(storage['actual_counts'].get(topic) == count
            for topic,count in terminal.get('published_counts',{}).items() if topic in topics),
        'synthetic_terminal_entire_population_counts')
    close = close_population(run,inputs,result,peer,observer,publisher,checker)
    callbacks = callback_population(observer,decoded.get(APPLIED,[]),publisher,close,checker)
    component = component_population(observer,close,checker)
    business = business_population(observer,worker,close,observer_manifest['contract_configuration'],checker)
    source_pins = {}; binary_pins = {}
    for role,bundle_pin in inputs['source_bundles'].items():
        path = Path(bundle_pin['path']); source_pins[str(path)] = sha(path)
        checker.need(source_pins[str(path)] == bundle_pin['sha256'], 'author_source_bundle_current_pin', role=role)
        bundle = load(path)
        for item in bundle['files'].values():
            p = Path(item['path']); source_pins[str(p)] = sha(p)
            checker.need(source_pins[str(p)] == item['sha256'], 'author_source_file_current_pin', role=role, path=str(p))
    for role,b in inputs['builds'].items():
        path = Path(b['binary']); binary_pins[str(path)] = sha(path)
        checker.need(binary_pins[str(path)] == b['binary_sha256'], 'role_binary_current_pin', role=role)
    after = {str(p):sha(p) for p in allfiles}
    checker.need(before == after, 'entire_run_inputs_unchanged')
    checker.need(all(sha(p)==value for p,value in {**source_pins,**binary_pins}.items()), 'author_assets_unchanged_during_check')
    dependency_paths = [HERE/'check_owned_fixture.py',HERE/'runtime/check_p1_execution.py',
        HERE/'runtime/check_p1_witness.py',HERE/'owned_release.py',HERE/'owned_auth.py']
    return checker.result(schema='p1-C3.6-owned-shadow-adapter-run-check-v1',
        scope='closed lifecycle of one normal bounded owned shadow adapter fixture; no phase qualification',
        run_dir=str(run),run_id=inputs['run_id'], qualifications=QUALIFICATIONS, unknowns=UNKNOWNS,
        storage=storage, transport_storage=transport, source_typed_storage=source,
        publisher_session=publisher_join, source_fixed_witness=witness,
        applied_callbacks=callbacks, component=component, business=business,
        driver_close={'request_ns':close['requested_ns'],'observed_ns':close['observed_ns'],
            'request_sha256':close['request_sha256'],'owner_process_alive_at_observation':close['owner_process_alive']},
        input_sha256_before=before,input_sha256_after=after,
        author_source_sha256=source_pins,author_binary_sha256=binary_pins,
        checker_dependencies={str(p):sha(p) for p in dependency_paths},
        complete_population_window_clipped=False, regulatory_physical_publication=False,
        Applied_runtime_partial_failure_adapter_verified=False,
        callback_authentication_scope='Applied callback GID only; existing Worker guards retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    try:
        report = analyze(args.run_dir)
    except Exception as error:
        report = {'schema':'p1-C3.6-owned-shadow-adapter-run-check-v1','passed':False,
            'run_dir':str(args.run_dir.resolve()),'reader_error':type(error).__name__+': '+str(error),
            'qualifications':QUALIFICATIONS,'unknowns':UNKNOWNS}
    report['checker_sha256'] = sha(__file__)
    if args.output:
        create_only_json(args.output,report)
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
