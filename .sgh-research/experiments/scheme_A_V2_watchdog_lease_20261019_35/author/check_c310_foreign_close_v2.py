#!/usr/bin/env python3
"""Whole actual multiwriter post-close diagnostic; no phase qualification.

Source and MessageInfo identify each independently received occurrence. SQLite
CDR occurrences are conserved without claiming a unique writer for byte-identical
bag rows. Applied.sequence is intentionally nonunique across writers.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
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
import check_c39_worker_close as c39
c36 = p.c36
exact = p.exact
SCHEMA = 'p1-C3.10-actual-foreign-after-close-check-v2'
ROLES = c36.ROLES | {'foreign'}
LABELS = ['clone_zero_first', 'clone_nonzero', 'clone_zero_repeat']
FLAGS = p.FLAGS.copy()
DEPENDENCIES = ('check_c310_foreign_close_v2.py', 'test_c310_foreign_close_v2.py',
    'prepare_fixture_v2.py', 'check_c39_worker_close.py', 'check_c38_owned_close.py',
    'check_c37_owned_run_v2.py', 'check_c36_adapter_run.py', 'check_owned_fixture.py',
    'runtime/owned_process_supervisor.py', 'runtime/check_p1_execution.py',
    'runtime/check_p1_witness_v2.py', 'lease_replay_v1.py', 'owned_auth.py', 'owned_release.py')


def endpoint(manifest, checker, role):
    es = [e for e in manifest.get('endpoints', []) if e.get('kind') == 'publisher'
          and e.get('topic') == c36.APPLIED and e.get('type') == c36.APPLIED_TYPE]
    checker.need(len(es) == 1 and p.gid(es[0].get('gid')), 'unique_actual_Applied_endpoint', role=role)
    return es[0].get('gid') if len(es) == 1 else None


def multiwriter_transport(raw_rows, transport, manifests, topics, checker):
    """Exact full wire SHA sequences plus actual allowed GID populations.

    Matching two ordered SHA streams is a population consistency check. With
    copied CDR it cannot identify the writer of an individual bag occurrence.
    """
    before = len(checker.issues)
    allowed = {topic: [] for topic in topics}
    for role, manifest in manifests.items():
        for e in manifest.get('endpoints', []):
            if e.get('kind') == 'publisher' and e.get('topic') in topics:
                checker.need(e.get('type') == topics[e['topic']] and p.gid(e.get('gid')),
                             'declared_transport_publisher_actual_type_gid', role=role, topic=e['topic'])
                allowed[e['topic']].append((role, e.get('gid')))
    checker.need(len(allowed.get(c36.APPLIED, [])) == 2
        and {role for role, gid in allowed[c36.APPLIED]} == {'publisher', 'foreign'}
        and not exact(allowed[c36.APPLIED][0][1], allowed[c36.APPLIED][1][1]),
        'exact_two_independent_Applied_DataWriters')
    checker.need(all(len(rows) == (2 if topic == c36.APPLIED else 1) for topic, rows in allowed.items()),
                 'complete_application_publisher_endpoint_population')
    seen = {topic: [] for topic in topics}; by_role = {role: [] for role in manifests}
    checker.need(all(c36.integer(r.get('ordinal'),1) for r in transport)
        and [r.get('ordinal') for r in transport] == list(range(1, len(transport)+1)),
                 'entire_transport_Source_ordinal_population')
    last_ns = 0
    for row in transport:
        topic = row.get('topic')
        checker.need(row.get('type') == 'transport_message' and topic in seen,
                     'known_actual_transport_message_topic')
        if topic not in seen: continue
        candidates = [role for role, gid in allowed[topic] if exact(gid, row.get('publisher_gid'))]
        checker.need(len(candidates) == 1 and row.get('ros_type') == topics[topic]
            and row.get('serialization') == 'cdr' and c36.integer(row.get('serialized_bytes'), 1)
            and type(row.get('payload_sha256')) is str and len(row['payload_sha256']) == 64
            and c36.integer(row.get('receive_ns'), 1) and row['receive_ns'] >= last_ns,
            'actual_transport_type_GID_CDR_and_monotonic_observation', topic=topic)
        if c36.integer(row.get('receive_ns'), 1): last_ns = row['receive_ns']
        seen[topic].append(row.get('payload_sha256'))
        if len(candidates) == 1: by_role[candidates[0]].append(row)
    for topic in topics:
        checker.need(exact(seen[topic], raw_rows.get(topic)),
            'entire_multiwriter_transport_Storage_CDR_SHA_sequence', topic=topic,
            transport_count=len(seen[topic]), storage_count=len(raw_rows.get(topic, [])))
    return {'passed': len(checker.issues) == before, 'counts': {t:len(v) for t,v in seen.items()},
        'role_counts': {role:Counter(r['topic'] for r in rows) for role, rows in by_role.items()},
        'actual_Applied_writer_count': 2, 'unique_bag_row_writer_identity_proven': False,
        'copied_CDR_ambiguity_preserved': True, 'window_clipped': False}, by_role


def foreign_rejection(row, rejection, original_gid, foreign_gid, proof_ns, close_ns):
    raw = row.get('raw_input', {})
    return (p.gid(original_gid) and p.gid(foreign_gid) and not exact(original_gid, foreign_gid)
        and exact(row.get('expected_gid'), original_gid) and exact(raw.get('publisher_gid'), foreign_gid)
        and row.get('authentication_reason') == rejection.get('reason') == 'callback_foreign_gid'
        and row.get('queued_terminal_tail') is False and row.get('owner_process_alive') is False
        and c36.integer(proof_ns, 1) and c36.integer(close_ns, 1)
        and c36.integer(raw.get('entry_steady_ns'), 1) and c36.integer(row.get('processed_ns'), 1)
        and close_ns < proof_ns < raw['entry_steady_ns'] <= row['processed_ns']
        and rejection.get('sequence') == row.get('sequence')
        and rejection.get('processed_ns') == row.get('processed_ns'))


def applied_population(observer, decoded, pub, foreign, close, proof_ns, checker, *, decode=None):
    if decode is None: decode = lambda raw, label:p.decode_callback(raw, checker, label)
    rows = [r for r in observer if r.get('type') == 'adapter_applied_callback']
    receiver = [r for r in observer if r.get('type') == 'adapter_applied_reception_closed']
    checker.need(len(receiver) == 1, 'actual_Applied_receiver_terminal_once')
    receiver = receiver[0] if len(receiver) == 1 else {}
    checker.need(receiver.get('executor_detached') is True and c36.integer(receiver.get('closed_ns'), 1)
        and type(receiver.get('legacy_received')) is int and type(receiver.get('raw_callback_sequence')) is int
        and receiver.get('legacy_received') == receiver.get('raw_callback_sequence') == len(rows),
        'entire_Applied_callback_counter_conservation')
    original_gid = endpoint(pub, checker, 'publisher'); foreign_gid = endpoint(foreign, checker, 'foreign')
    checker.need(not exact(original_gid, foreign_gid), 'independent_foreign_GID_not_original_owner')
    checker.need(all(c36.integer(r.get('raw_input',{}).get('callback_sequence'),1) and c36.integer(r.get('sequence'),1) for r in rows)
        and [r.get('raw_input', {}).get('callback_sequence') for r in rows] == list(range(1, len(rows)+1)),
        'entire_Applied_callback_sequence_not_payload_sequence')
    anchors = [r for r in observer if r.get('type') == 'legacy_anchor']
    rejects = [r for r in observer if r.get('type') == 'adapter_applied_auth_rejected']
    observed = [r for r in observer if r.get('type') == 'adapter_applied_observed']
    key = lambda row:(row.get('sequence'), row.get('processed_ns'))
    anchors_by = checker.index(anchors, key, 'actual_Applied_anchor_commit')
    rejects_by = checker.index(rejects, key, 'actual_Applied_auth_rejection_commit')
    observed_by = checker.index(observed, key, 'actual_Applied_component_observation_commit')
    checker.need(len({key(r) for r in rows}) == len(rows), 'unique_callback_commit_key_despite_payload_collision')
    stored = Counter(p.canonical(r['message']) for r in decoded.get(c36.APPLIED, []))
    received = Counter(); owned_messages=[]; foreign_messages=[]; foreign_rows=[]; previous_ns=0
    admitted_keys=set(); rejection_keys=set(); population=[]
    for row in rows:
        raw = row.get('raw_input', {}); cbseq = raw.get('callback_sequence'); label={'callback_sequence':cbseq}
        checker.need(type(raw) is dict and set(raw) == p.RAW_FIELDS
            and raw.get('schema') == 'p1-input-callback-full-cdr-v1'
            and raw.get('topic') == c36.APPLIED and raw.get('message_type') == c36.APPLIED_TYPE
            and raw.get('rmw_implementation') == 'rmw_fastrtps_cpp' and raw.get('from_intra_process') is False
            and p.gid(raw.get('publisher_gid')) and exact(row.get('expected_gid'), original_gid),
            'actual_Applied_full_received_CDR_interface_and_original_owner_pin', **label)
        checker.need(c36.integer(raw.get('entry_steady_ns'), 1) and c36.integer(row.get('processed_ns'), 1)
            and c36.integer(receiver.get('closed_ns'), 1)
            and previous_ns <= raw.get('entry_steady_ns', 0) <= row.get('processed_ns', 0) <= receiver.get('closed_ns', 0),
            'whole_Applied_actual_received_time_window', **label)
        if c36.integer(row.get('processed_ns'), 1): previous_ns=row['processed_ns']
        message = decode(raw, label)
        if message is None: continue
        checker.need(message.get('sequence') == row.get('sequence')
            and all(message.get(k) is False for k in ('plant_acceptance_observed','force_measured','execution_atomicity_proven')),
            'received_Applied_complete_payload_command_observation', **label)
        canonical = p.canonical(message); received[canonical]+=1
        checker.need(received[canonical] <= stored[canonical], 'received_full_typed_Applied_occurrence_bounded_by_Storage', **label)
        commit=key(row); auth=row.get('authentication_reason'); actual_gid=raw.get('publisher_gid')
        if exact(actual_gid, foreign_gid):
            foreign_rows.append(row); foreign_messages.append(message); rejection_keys.add(commit)
            checker.need(foreign_rejection(row, rejects_by.get(commit, {}), original_gid, foreign_gid,
                proof_ns, close.get('observed_ns')), 'actual_post_close_foreign_DataWriter_denied_at_auth_guard', **label)
            checker.need(commit not in anchors_by and commit not in observed_by,
                'foreign_sequence_collision_never_creates_semantic_anchor_or_component_observation', **label)
        elif exact(actual_gid, original_gid):
            owned_messages.append(message)
            permitted=c38.tail_permitted(message, auth, True, close.get('requested_ns'),close.get('observed_ns'),row.get('processed_ns'))
            checker.need(row.get('queued_terminal_tail') is permitted, 'original_owner_tail_predicate_unchanged', **label)
            checker.need(auth == '' or permitted, 'complete_original_owner_receipts_admitted', **label)
            admitted_keys.add(commit)
            anchor=anchors_by.get(commit, {}); component=observed_by.get(commit, {})
            checker.need(exact(anchor.get('applied'), message) and anchor.get('applied_text_truncated') is False
                and exact(anchor.get('final_n'), message.get('final_n')) and anchor.get('received_count') == cbseq
                and component.get('reason') == '' and exact(component.get('evidence',{}).get('command_n'),message.get('final_n')),
                'original_owner_full_typed_callback_anchor_component_binding', **label)
        else: checker.need(False, 'unregistered_Applied_DataWriter_actual_receipt', **label)
        population.append({'callback_sequence':cbseq, 'sequence':row.get('sequence'),
            'processed_ns':row.get('processed_ns'), 'publisher_gid':actual_gid, 'authentication_reason':auth,
            'queued_terminal_tail':row.get('queued_terminal_tail'), 'cdr_sha256':raw.get('cdr_sha256'),
            'final_n':message.get('final_n')})
    checker.need(received == stored, 'entire_Storage_Applied_full_typed_occurrence_population_received')
    checker.need(set(anchors_by) == set(observed_by) == admitted_keys and set(rejects_by) == rejection_keys,
        'complete_Applied_auth_semantic_anchor_population_by_commit_not_colliding_sequence')
    checker.need(receiver.get('legacy_admitted') == len(anchors), 'native_Applied_admission_counter_conservation')
    checker.need(len(foreign_rows) == 3 and len(owned_messages)>0
        and [m.get('sequence') for m in owned_messages] == list(range(1,len(owned_messages)+1))
        and [m.get('sequence') for m in foreign_messages] == [len(owned_messages)]*3,
        'three_actual_foreign_callbacks_collide_original_terminal_sequence')
    # Source order establishes the before-anchor for every denial. No rejection
    # may silently create a new anchor, even when all payload sequences collide.
    anchor_n=[0.,0.]; component_state=None
    for row in observer:
        if row.get('type')=='legacy_anchor': anchor_n=row['final_n']
        if row.get('type') in ('adapter_applied_observed','adapter_driver_close_observed'):
            component_state=row.get('evidence')
        if row.get('type')=='adapter_applied_auth_rejected':
            checker.need(exact(row.get('anchor_after'),anchor_n), 'foreign_denial_anchor_before_after_exactly_unchanged')
            state=row.get('component',{})
            checker.need(component_state is not None and all(exact(state.get(k),component_state.get(k))
                for k in ('command_n','command_known','command_sequence','command_publish_ns')),
                'foreign_denial_component_command_anchor_unchanged')
    for kind in ('adapter_applied_resource_rejected','legacy_admission_rejected','legacy_history_reset','adapter_close_evidence_failed'):
        checker.need(not [r for r in observer if r.get('type')==kind], 'no_unexplained_'+kind)
    return {'received':len(rows),'recorded':sum(stored.values()),'original_received':len(owned_messages),
        'foreign_received':len(foreign_rows),'population':population,'payload_sequence_unique':False,
        'complete_typed_received_population':True,'unique_bag_row_writer_identity_proven':False}, owned_messages, foreign_messages, foreign_rows


def cdr_record_valid(value):
    if type(value) is not dict or set(value) != {'hex','bytes','sha256'}:return False
    text=value.get('hex')
    return (type(text) is str and 0<len(text)<=16384 and len(text)%2==0
        and all(c in '0123456789abcdef' for c in text)
        and type(value.get('bytes')) is int and 1<=value['bytes']<=8192
        and len(text)==2*value['bytes'] and type(value.get('sha256')) is str
        and hashlib.sha256(bytes.fromhex(text)).hexdigest()==value['sha256'])


def explicit_submission_relation(application, submitted, padding_bytes):
    """Exact producer-controlled bytes; no inferred middleware normalization."""
    if not (cdr_record_valid(application) and cdr_record_valid(submitted)
        and type(padding_bytes) is int and 0<=padding_bytes<=3):return False
    app,submission=bytes.fromhex(application['hex']),bytes.fromhex(submitted['hex'])
    return padding_bytes==(-len(app))%4 and submission==app+b'\0'*padding_bytes and len(submission)%4==0


def foreign_contract_configuration(contract, checker):
    expected={'schema':'p1-C3.10-foreign-Applied-contract-v2', 'topic':c36.APPLIED,
        'ros_type':c36.APPLIED_TYPE, 'packet_labels':LABELS, 'max_packets':3,
        'max_cdr_bytes':8192, 'nonzero_final_n':[1.,-1.], 'physical_publisher_endpoints':0,
        'stage_qualified':False, 'execute_qualified':False, 'submission_alignment_bytes':4,
        'submission_padding_policy':'explicit-zero-fill-before-native-publish'}
    checker.need(type(contract) is dict and exact(contract,expected)
        and all(type(contract.get(key)) is int for key in
            ('max_packets','max_cdr_bytes','physical_publisher_endpoints','submission_alignment_bytes'))
        and type(contract.get('nonzero_final_n')) is list
        and all(type(value) is float for value in contract['nonzero_final_n']),
        'foreign_explicit_submission_contract_configuration')


def checker_dependency_population(run, inputs, checker, *, here=None):
    here=HERE if here is None else Path(here)
    deps=[here/rel for rel in DEPENDENCIES]
    for rel,dep in zip(DEPENDENCIES,deps):
        snap=run/(rel.replace('/','__')+'.snapshot')
        exists=dep.is_file() and snap.is_file()
        checker.need(exists and inputs.get('tool_sha256',{}).get(rel)==c36.sha(dep)
            and c36.sha(snap)==c36.sha(dep), 'executed_checker_dependency_exact_prerun_snapshot',tool=rel)
    return deps


def foreign_source_population(run, inputs, manifest, command, emit, source, terminal, typed_messages,
                              callback_rows, transport_rows, proof_ns, close, checker, *, decode=None):
    if decode is None:
        def decode(raw, label):
            callback={'cdr_hex':raw['cdr_hex'],'cdr_bytes':raw['cdr_bytes'],
                'cdr_sha256':raw['payload_sha256'],'message_type':c36.APPLIED_TYPE}
            return p.decode_callback(callback,checker,label)
    checker.need(all(c36.integer(r.get('source_ordinal'),1) for r in source)
        and [r.get('source_ordinal') for r in source] == list(range(1,10))
        and [r.get('type') for r in source] == ['foreign_ready','foreign_emit_observed',
            'foreign_publish_start','foreign_publish_result','foreign_publish_start','foreign_publish_result',
            'foreign_publish_start','foreign_publish_result','foreign_summary'], 'entire_foreign_Source_fixed_packet_population')
    ready=[r for r in source if r.get('type')=='foreign_ready']; observed=[r for r in source if r.get('type')=='foreign_emit_observed']
    starts=[r for r in source if r.get('type')=='foreign_publish_start']; results=[r for r in source if r.get('type')=='foreign_publish_result']
    summaries=[r for r in source if r.get('type')=='foreign_summary']
    checker.need(len(ready)==len(observed)==len(summaries)==1 and len(starts)==len(results)==3,
                 'unique_foreign_Source_boundaries')
    if not (len(ready)==len(observed)==len(summaries)==1 and len(starts)==len(results)==3):return {}
    ready=ready[0]; observed=observed[0]; summary=summaries[0]
    gid=endpoint(manifest,checker,'foreign'); mh=c36.sha(run/'foreign/owned_manifest.json'); ch=c36.sha(run/'foreign/command.json')
    checker.need(ready.get('manifest_sha256')==observed.get('manifest_sha256')==mh
        and ready.get('command_sha256')==observed.get('command_sha256')==ch
        and exact(ready.get('publisher_gid'),gid) and ready.get('execute_qualified') is False
        and ready.get('stage_qualified') is False, 'foreign_Source_header_native_manifest_command_GID_binding')
    times=[proof_ns,manifest.get('created_steady_ns'),ready.get('prepared_ns'),emit.get('issued_ns'),observed.get('observed_ns')]
    checker.need(all(c36.integer(x,1) for x in times) and times==sorted(times)
        and observed.get('issued_ns')==emit.get('issued_ns') and observed['observed_ns']-emit['issued_ns']<=3_500_000_000
        and observed.get('emit_sha256')==c36.sha(run/'foreign/emit.json')
        and c36.integer(observed.get('matched_subscriptions'),3), 'actual_foreign_emit_after_owner_reap_and_finite_native_discovery')
    previous_end=observed['observed_ns']; decoded=[]; application_decoded=[]
    for index,(start,result) in enumerate(zip(starts,results),1):
        fields=set(('packet_index label topic ros_type sequence publisher_gid serialization cdr_hex cdr_bytes '
            'payload_sha256 publish_start_ns final_n application_cdr_hex application_cdr_bytes '
            'application_cdr_sha256 padding_bytes physical_publish_attempted stage_qualified execute_qualified').split())
        checker.need(set(start)==fields|{'type','source_ordinal'}
            and set(result)==fields|{'type','source_ordinal','publish_end_ns','returned','error'}
            and c36.integer(start.get('packet_index'),1) and c36.integer(result.get('packet_index'),1)
            and start.get('packet_index')==result.get('packet_index')==index
            and start.get('label')==result.get('label')==LABELS[index-1]
            and exact({k:v for k,v in start.items() if k not in ('type','source_ordinal')},
                {k:v for k,v in result.items() if k not in ('type','source_ordinal','publish_end_ns','returned','error')})
            and start.get('topic')==c36.APPLIED and start.get('ros_type')==c36.APPLIED_TYPE
            and exact(start.get('publisher_gid'),gid) and start.get('serialization')=='cdr'
            and start.get('physical_publish_attempted') is False and start.get('stage_qualified') is False
            and start.get('execute_qualified') is False and result.get('returned') is True and result.get('error')=='',
            'actual_foreign_full_Source_start_result_packet_binding', packet_index=index)
        checker.need(c36.integer(start.get('publish_start_ns'),1) and c36.integer(result.get('publish_end_ns'),1)
            and previous_end<=start.get('publish_start_ns',0)<=result.get('publish_end_ns',0),
            'actual_foreign_publication_call_monotonic_order',packet_index=index)
        previous_end=result.get('publish_end_ns',0)
        submitted={'hex':start.get('cdr_hex'),'bytes':start.get('cdr_bytes'),'sha256':start.get('payload_sha256')}
        application={'hex':start.get('application_cdr_hex'),'bytes':start.get('application_cdr_bytes'),
            'sha256':start.get('application_cdr_sha256')}
        wire_valid=cdr_record_valid(submitted);app_valid=cdr_record_valid(application)
        checker.need(wire_valid,'foreign_Source_wire_CDR_SHA_binding',packet_index=index)
        checker.need(app_valid,'foreign_Source_application_CDR_SHA_binding',packet_index=index)
        checker.need(explicit_submission_relation(application,submitted,start.get('padding_bytes')),
            'foreign_Source_explicit_zero_padding_before_submission_exact_bytes',packet_index=index)
        if not (wire_valid and app_valid):continue
        message=decode(start,{'packet_index':index});decoded.append(message)
        application_raw={'cdr_hex':application['hex'],'cdr_bytes':application['bytes'],
            'payload_sha256':application['sha256']}
        application_message=decode(application_raw,{'packet_index':index});application_decoded.append(application_message)
        checker.need(message is not None and application_message is not None and exact(message,application_message),
            'foreign_Source_application_and_submission_full_typed_equal',packet_index=index)
        checker.need(message is not None and exact(start.get('final_n'),message.get('final_n'))
            and start.get('sequence')==message.get('sequence'), 'foreign_Source_typed_full_CDR_projection',packet_index=index)
    checker.need(len(decoded)==3 and len(typed_messages)==3 and all(exact(a,b) for a,b in zip(decoded,typed_messages)),
                 'entire_foreign_Source_received_full_typed_population')
    if len(decoded)==3 and all(type(message) is dict for message in decoded):
        original=deepcopy(decoded[0]); mutated=deepcopy(original);mutated['final_n']=[1.,-1.]
        checker.need(exact(decoded[2],original) and exact(decoded[1],mutated)
            and original.get('control_source')=='shutdown_zero' and exact(original.get('final_n'),[0.,0.])
            and starts[0].get('application_cdr_hex')==starts[2].get('application_cdr_hex')==command.get('original_applied_cdr_hex')
            and starts[0].get('application_cdr_sha256')==starts[2].get('application_cdr_sha256')==command.get('original_applied_cdr_sha256')
            and starts[0].get('cdr_hex')==starts[2].get('cdr_hex')
            and starts[0].get('payload_sha256')==starts[2].get('payload_sha256'),
            'exact_copied_terminal_zero_nonzero_only_final_n_and_repeat')
    checker.need(len(transport_rows)==3 and [r.get('payload_sha256') for r in transport_rows]
        ==[r.get('payload_sha256') for r in starts]
        and all(exact(r.get('publisher_gid'),gid) and r.get('topic')==c36.APPLIED
            and result['publish_start_ns']<=r.get('receive_ns',0) for r,result in zip(transport_rows,results)),
        'entire_foreign_Source_actual_GID_transport_wire_CDR_occurrence_population')
    checker.need(len(callback_rows)==3 and all(result['publish_start_ns']<=callback['raw_input']['entry_steady_ns']
        for result,callback in zip(results,callback_rows)), 'actual_foreign_Source_calls_precede_actual_callbacks')
    checker.need(summary.get('generated')==summary.get('returned')==summary.get('expected_packets')==3
        and summary.get('normal_source_complete') is True and summary.get('physical_publish_attempted') is False
        and summary.get('execute_qualified') is False and summary.get('stage_qualified') is False
        and c36.integer(summary.get('finished_ns'),1) and previous_end<=summary['finished_ns'],
        'foreign_Source_terminal_complete_call_count_conservation')
    checker.need(terminal.get('schema')=='p1-C3.10-foreign-Applied-terminal-v1'
        and terminal.get('run_id')==inputs['run_id'] and terminal.get('boot_id')==manifest['boot_id']
        and terminal.get('manifest_sha256')==mh and terminal.get('command_sha256')==ch
        and terminal.get('source_sha256')==c36.sha(run/'foreign/source.jsonl')
        and terminal.get('generated')==terminal.get('returned')==3 and terminal.get('normal_end') is True
        and terminal.get('physical_publisher_endpoints')==0 and terminal.get('execute_qualified') is False
        and terminal.get('stage_qualified') is False and c36.integer(terminal.get('closed_ns'),1)
        and summary['finished_ns']<=terminal['closed_ns'], 'foreign_native_terminal_complete_Source_manifest_command_binding')
    return {'published':len(starts),'received':len(callback_rows),'transport':len(transport_rows),
        'diagnostic_only':True,'cloned_zero_application_SHA':command.get('original_applied_cdr_sha256'),
        'cloned_zero_submitted_SHA':starts[0].get('payload_sha256'),
        'application_sha256':[r.get('application_cdr_sha256') for r in starts],
        'submitted_sha256':[r.get('payload_sha256') for r in starts],
        'explicit_padding_bytes':[r.get('padding_bytes') for r in starts],
        'foreign_gid':gid,'unique_bag_row_writer_identity_proven':False,'terminal':terminal}


def role_pin_population(run, inputs, result, manifests, initial, late, ledger, checker):
    checker.need(set(initial.get('roles',{}))==c36.ROLES and set(late.get('roles',{}))=={'foreign'},
                 'initial_five_and_late_foreign_live_preparation_role_population')
    for prep in (initial,late):
        checker.need(prep.get('schema_version')=='p1-owned-fixture-preparation-v2'
            and prep.get('fixture_only') is True and prep.get('production_execute_qualified') is False
            and c36.integer(prep.get('checked_ns'),1), 'actual_preparation_diagnostic_scope')
    spawns=checker.index([r for r in ledger if r.get('type')=='spawn'],lambda r:r.get('name'),'supervisor_spawn')
    cleanups=checker.index([r for r in ledger if r.get('type')=='cleanup_result'],lambda r:r.get('name'),'supervisor_cleanup')
    checker.need(set(spawns)==set(cleanups)==ROLES,'entire_six_role_supervisor_spawn_cleanup_population')
    for role,m in manifests.items():
        prep=late if role=='foreign' else initial;auth=prep.get('roles',{}).get(role,{}); owned=auth.get('owned',{})
        source_role='fixture' if role=='synthetic_source' else role;build=inputs['builds'].get(source_role,{});source=inputs['source_bundles'].get(source_role,{})
        spawn=spawns.get(role,{});ident=spawn.get('identity',{})
        checker.need(m.get('role')==role and m.get('run_id')==inputs['run_id']+('-publisher' if role=='publisher' else '')
            and m.get('exe')==build.get('binary') and m.get('binary_sha256')==build.get('binary_sha256')
            and m.get('source_bundle_sha256')==source.get('sha256')==build.get('source_bundle',{}).get('sha256')
            and m.get('boot_id')==manifests['observer'].get('boot_id'), 'native_six_role_asset_and_run_binding',role=role)
        checker.need(auth.get('manifest_sha256')==c36.sha(run/role/'owned_manifest.json')
            and auth.get('source_bundle_sha256')==m.get('source_bundle_sha256')
            and auth.get('effective_parameters_sha256')==m.get('effective_parameters_sha256')
            and c36.integer(m.get('pid'),1) and c36.integer(m.get('process_start_ticks'),1)
            and owned.get('pid')==ident.get('pid')==m.get('pid')
            and owned.get('start_ticks')==ident.get('start_ticks')==m.get('process_start_ticks')
            and owned.get('exe')==ident.get('exe')==m.get('exe')
            and owned.get('exe_sha256')==ident.get('exe_sha256')==m.get('binary_sha256')
            and owned.get('boot_id')==spawn.get('boot_id')==m.get('boot_id')
            and owned.get('pgid')==ident.get('pgid')==m.get('pid')
            and owned.get('sid')==ident.get('sid')==m.get('pid')
            and exact(owned.get('argv'),spawn.get('argv')) and exact(m.get('argv'),spawn.get('argv'))
            and spawn.get('executable_verified') is True and spawn.get('expected_exe')==m.get('exe')
            and spawn.get('expected_sha256')==m.get('binary_sha256')
            and c36.integer(spawn.get('monotonic_ns'),1) and spawn['monotonic_ns']<=prep['checked_ns'],
            'actual_live_preparation_exact_supervisor_native_process_argv_asset',role=role)
        cleanup=cleanups.get(role,{});wanted=result['cleanup'].get(role,{})
        checker.need(wanted.get('name')==role and cleanup.get('boot_id')==m.get('boot_id')
            and all(exact(cleanup.get(k),v) for k,v in wanted.items())
            and c36.integer(cleanup.get('monotonic_ns'),1) and prep['checked_ns']<=cleanup['monotonic_ns'],
            'actual_supervisor_cleanup_exact_driver_population',role=role)
        signals=[r for r in ledger if r.get('type')=='signal' and r.get('name')==role]
        checker.need(len(signals)==1 and signals[0].get('signal')==2
            and signals[0].get('boot_id')==m.get('boot_id') and any(x.get('pid')==m.get('pid')
                and x.get('start_ticks')==m.get('process_start_ticks') and x.get('exe')==m.get('exe') for x in signals[0].get('members',[])),
            'scoped_six_role_SIGINT_native_process_identity',role=role)
    terminal=[r for r in ledger if r.get('type')=='supervisor_summary']
    checker.need(len(terminal)==1 and ledger[-1] is terminal[0] and exact(terminal[0].get('children'),result['cleanup'])
        and terminal[0].get('cleanup_failed') is False and terminal[0].get('qualification_clean') is True
        and terminal[0].get('unexpected_descendants')==[] and terminal[0].get('unverified_children')==[],
        'entire_six_role_supervisor_terminal_population')
    return spawns


def late_graph_population(graph, manifests, topics, late, emit, proof_ns, checker):
    """One actual graph observation; departed original endpoints may be stale."""
    times=[proof_ns,late.get('checked_ns'),graph.get('observed_ns'),emit.get('issued_ns')]
    checker.need(all(c36.integer(x,1) for x in times) and times==sorted(times)
        and times[-1]-times[-2]<=1_000_000_000 and set(graph.get('topics',{}))==set(topics),
        'late_graph_actual_post_reap_authenticated_pre_emit_finite_observation')
    expected={topic:{'publishers':[],'subscriptions':[]} for topic in topics}
    for role,m in manifests.items():
        for e in m.get('endpoints',[]):
            if e.get('topic') not in topics:continue
            kind={'publisher':'publishers','subscription':'subscriptions'}.get(e.get('kind'))
            if kind is None:continue
            expected[e['topic']][kind].append((role,{'node':m.get('node'),'type':e.get('type'),'gid':e.get('gid')}))
    for topic in topics:
        actual=graph.get('topics',{}).get(topic,{})
        for kind in ('publishers','subscriptions'):
            rows=actual.get(kind,[]);allowed=expected[topic][kind]
            checker.need(type(rows) is list and all(type(row) is dict and set(row)=={'node','type','gid'}
                and p.gid(row.get('gid')) and row.get('type')==topics[topic]
                and any(exact(row,known) for role,known in allowed) for row in rows)
                and len({p.canonical(row) for row in rows})==len(rows),
                'late_graph_entire_actual_endpoint_population_registered_and_typed',topic=topic,kind=kind)
            for role,known in allowed:
                # A departed endpoint may remain in this discovery snapshot. No
                # endpoint-exit claim is derived from either presence or absence.
                if role=='publisher':continue
                checker.need(sum(exact(row,known) for row in rows)==1,
                    'late_graph_actual_live_native_endpoint_present_once',topic=topic,kind=kind,role=role)
    return {'observed_ns':graph.get('observed_ns'),'complete_declared_topic_population':True,
        'original_owner_endpoint_exit':'unknown','continuous_DDS_uniqueness':'unknown'}


def command_binding(run, inputs, peer, pub, foreign, command, emit, proof, close, checker):
    expected={'schema':'p1-C3.10-foreign-Applied-command-v1','run_id':inputs['run_id'],'boot_id':pub['boot_id'],
        'original_owner_manifest_sha256':c36.sha(run/'publisher/owned_manifest.json'),
        'driver_pid':peer['driver']['pid'],'driver_start_ticks':peer['driver']['start_ticks'],
        'driver_tool_sha256':peer['driver_tool_sha256'],'close_request_sha256':c36.sha(run/'adapter_driver_close_request.json'),
        'close_observed_ns':close['observed_ns'],'owner_exit_proof_sha256':c36.sha(run/'c38_owner_exit_proof.json')}
    checker.need(all(c36.integer(command.get(k),1) for k in ('driver_pid','driver_start_ticks','close_observed_ns'))
        and set(command)==set(expected)|{'original_applied_cdr_hex','original_applied_cdr_sha256'}
        and all(exact(command.get(k),v) for k,v in expected.items()), 'foreign_command_exact_original_owner_actual_close_exit_driver_binding')
    expected_emit={'schema':'p1-C3.10-foreign-Applied-emit-v1','run_id':inputs['run_id'],'boot_id':pub['boot_id'],
        'driver_pid':peer['driver']['pid'],'driver_start_ticks':peer['driver']['start_ticks'],
        'driver_tool_sha256':peer['driver_tool_sha256'],'command_sha256':c36.sha(run/'foreign/command.json'),
        'foreign_manifest_sha256':c36.sha(run/'foreign/owned_manifest.json')}
    checker.need(all(c36.integer(emit.get(k),1) for k in ('driver_pid','driver_start_ticks'))
        and set(emit)==set(expected_emit)|{'issued_ns'} and all(exact(emit.get(k),v) for k,v in expected_emit.items())
        and c36.integer(emit.get('issued_ns'),1) and proof['proof_ns']<emit.get('issued_ns',0),
        'foreign_emit_exact_independent_manifest_current_driver_command_binding')
    params=foreign.get('effective_parameters',{})
    concrete={'run_id':inputs['run_id'],'contract_file':str(HERE/'foreign/foreign_contract_v2.json'),
        'contract_sha256':c36.sha(HERE/'foreign/foreign_contract_v2.json'),'output_dir':str(run/'foreign'),
        'command_file':str(run/'foreign/command.json'),'command_sha256':c36.sha(run/'foreign/command.json'),
        'emit_file':str(run/'foreign/emit.json')}
    checker.need(all(exact(params.get(k,{}).get('value'),v) for k,v in concrete.items())
        and foreign.get('contract_sha256')==concrete['contract_sha256']!=pub.get('contract_sha256')
        and foreign.get('command_file')==concrete['command_file'] and foreign.get('command_sha256')==concrete['command_sha256']
        and foreign.get('independent_contract_file')==concrete['contract_file']
        and foreign.get('diagnostic_only') is True and foreign.get('physical_publisher_endpoints')==0,
        'foreign_separate_diagnostic_contract_concrete_effective_input_sources')


def analyze(run):
    run=Path(run).resolve();c=c36.Checks();files=[f for f in run.rglob('*') if f.is_file()]
    before={str(f):c36.sha(f) for f in files};inputs=c36.load(run/'inputs.json');result=c36.load(run/'result.json')
    c.need(inputs.get('c38_case')==result.get('c38_case')=='foreign_after_close'
        and inputs.get('mode')=='positive' and inputs.get('measurement_seconds')==4
        and inputs.get('witness_validation_profile')==p.PROFILE and result.get('released') is True
        and result.get('finite_prepare_and_measurement_passed') is True, 'declared_finite_C310_shadow_diagnostic_scope')
    c.need(result.get('diagnostic_case_completed') is True and result.get('cleanup_complete') is True
        and result.get('cleanup_within_budget') is True and c36.integer(result.get('close_elapsed_ns'),1)
        and result['close_elapsed_ns']<=15_000_000_000 and set(result.get('cleanup',{}))==ROLES
        and all(v.get('remaining_members')==[] and v.get('cleanup_complete') is True for v in result['cleanup'].values())
        and result.get('owned_role_returncodes')=={r:0 for r in ROLES} and result.get('close_errors')==[]
        and result.get('ledger_failed') is False and result.get('evidence_qualification_clean') is True,
        'actual_six_role_bounded_cleanup_and_clean_diagnostic_completion')
    manifests={r:c36.load(run/r/'owned_manifest.json') for r in ROLES};pub=manifests['publisher'];obs=manifests['observer'];worker=manifests['worker'];foreign=manifests['foreign']
    peer=c36.load(run/'adapter_peer_pins.json'); params=obs.get('effective_parameters',{})
    wanted={'mode':'shadow','adapter_peer_pins_file':str(run/'adapter_peer_pins.json'),
        'adapter_peer_pins_sha256':c36.sha(run/'adapter_peer_pins.json'),
        'adapter_driver_close_file':str(run/'adapter_driver_close_request.json'),
        'diagnostic_c38_mode':'none','diagnostic_c38_pause_file':'','diagnostic_c38_resume_file':''}
    c.need(all(exact(params.get(k,{}).get('value'),v) for k,v in wanted.items())
        and obs.get('adapter_pins_sha256')==wanted['adapter_peer_pins_sha256'], 'concrete_current_shadow_adapter_configuration_no_gate')
    pinmap={k:pub[k] for k in ('run_id','boot_id','contract_sha256','producer_instance_id','config_hash','pid','process_start_ticks','exe','binary_sha256','source_bundle_sha256','effective_parameters_sha256')}
    pinmap.update(manifest_path=str(run/'publisher/owned_manifest.json'),manifest_sha256=c36.sha(run/'publisher/owned_manifest.json'),topic=c36.APPLIED,type=c36.APPLIED_TYPE)
    c.need(set(peer.get('publisher_peer',{}))==set(pinmap) and all(exact(peer['publisher_peer'].get(k),v) for k,v in pinmap.items()), 'original_owner_complete_peer_pins_not_rebound_to_foreign')
    c.need(inputs.get('driver_tool_name')=='prepare_fixture_v2.py'
        and inputs.get('validation_recipe_revision')=='C3.10-foreign-close-v2'
        and peer.get('run_id')==inputs['run_id'] and peer.get('driver_tool_sha256')==inputs['tool_sha256'].get('prepare_fixture_v2.py')==c36.sha(HERE/'prepare_fixture_v2.py'), 'actual_current_driver_identity_and_executed_tool_SHA')
    p.worker_binding(run,inputs,manifests,peer,c);p.worker_contract_configuration(inputs,worker,c);p.configurations(run,inputs,result,manifests,c)
    ledger=c36.lines(run/'owned_process_ledger.jsonl');initial=c36.load(run/'preparation_evidence.json');late=c36.load(run/'foreign_preparation_evidence.json')
    spawns=role_pin_population(run,inputs,result,manifests,initial,late,ledger,c)
    pre=c36.load(run/'inputs_pre_foreign.json');c.need(all(exact(v,inputs.get(k)) for k,v in pre.items() if k!='expected_parameters')
        and set(pre.get('expected_parameters',{}))==c36.ROLES and all(exact(v,inputs['expected_parameters'].get(k)) for k,v in pre['expected_parameters'].items()), 'before_release_asset_input_pins_preserved_when_late_foreign_config_added')
    c.need(exact(c36.load(run/'foreign/expected_parameters.json'),inputs['expected_parameters']['foreign'])
        and late.get('expected_parameters_sha256')==c36.sha(run/'foreign/expected_parameters.json')
        and c36.integer(late.get('expected_parameters_written_ns'),1)
        and late['expected_parameters_written_ns']<=spawns.get('foreign',{}).get('monotonic_ns',0)
        and late.get('original_publisher_already_exited') is True and late.get('diagnostic_only') is True
        and late.get('original_owner_exit_proof_sha256')==c36.sha(run/'c38_owner_exit_proof.json'),
        'foreign_complete_expected_configuration_preregistered_before_spawn')
    topics=c36.load(run/'topics.json')['topics'];decoded,raw,storage=p.base.read_actual_storage(run/'recorder/bag',topics)
    observer=c36.lines(run/'observer/source.jsonl');ws=c36.lines(run/'worker/source.jsonl');tr=c36.lines(run/'synthetic_source/transport_source.jsonl')
    transport,by_role=multiwriter_transport(raw,tr,manifests,topics,c)
    source=p.base.source_typed_join(observer,ws,decoded);c.need(source.get('passed') is True,'whole_non_Applied_Source_typed_Storage',issues=source.get('issues'))
    close=c36.close_population(run,inputs,result,peer,observer,pub,c)
    c.need(c36.load(run/'c38_close_observation.json').get('observer')==close
        and not [r for r in observer if r.get('type')=='adapter_close_evidence_failed'], 'actual_Source_close_observation_unchanged')
    c.need(not [r for r in observer if r.get('type')=='job' and r.get('submit_commit_ns',0)>close['observed_ns']], 'no_new_Job_after_actual_close')
    c.need(not [r for r in observer if r.get('type')=='decision' and r.get('accepted') is True], 'actual_Accepted_zero_whole_population')
    proof=c36.load(run/'c38_owner_exit_proof.json')
    c.need(proof.get('schema')=='p1-C3.8-owner-exit-proof-v1' and proof.get('run_id')==inputs['run_id']
        and proof.get('boot_id')==pub['boot_id'] and proof.get('publisher_pid')==pub['pid']
        and proof.get('publisher_start_ticks')==pub['process_start_ticks']
        and proof.get('owner_manifest_sha256')==c36.sha(run/'publisher/owned_manifest.json')
        and proof.get('remaining_members')==[] and proof.get('returncode')==0
        and proof.get('cleanup',{}).get('cleanup_complete') is True and proof.get('stage_qualified') is False
        and c36.integer(proof.get('proof_ns'),1) and close['observed_ns']<proof['proof_ns']
        and proof['proof_ns']<spawns.get('foreign',{}).get('monotonic_ns',0)<=late.get('checked_ns',0),
        'actual_original_owner_reaped_before_distinct_foreign_process_spawn_and_authentication')
    applied,owned_messages,foreign_messages,foreign_rows=applied_population(observer,decoded,pub,foreign,close,proof['proof_ns'],c)
    original_callbacks=[r for r in observer if r.get('type')=='adapter_applied_callback' and exact(r.get('raw_input',{}).get('publisher_gid'),endpoint(pub,c,'publisher'))]
    command=c36.load(run/'foreign/command.json');emit=c36.load(run/'foreign/emit.json')
    command_binding(run,inputs,peer,pub,foreign,command,emit,proof,close,c)
    foreign_contract_configuration(c36.load(HERE/'foreign/foreign_contract_v2.json'),c)
    late_graph=late_graph_population(c36.load(run/'foreign_graph.json'),manifests,topics,late,emit,proof['proof_ns'],c)
    ack=c36.load(run/'c310_foreign_population_ack.json')
    c.need(ack.get('foreign_graph_sha256')==c36.sha(run/'foreign_graph.json')
        and exact(ack.get('foreign_gid'),endpoint(foreign,c,'foreign'))
        and ack.get('published')==ack.get('transport_received')==ack.get('observer_received')==3
        and c36.integer(ack.get('checked_ns'),1) and ack['checked_ns']>=emit['issued_ns']
        and all(ack['checked_ns']>=row['processed_ns'] for row in foreign_rows)
        and ack.get('stage_qualified') is False, 'whole_actual_foreign_population_ack_after_all_native_receipts')
    c.need(bool(original_callbacks) and original_callbacks[-1]['raw_input'].get('cdr_hex')==command.get('original_applied_cdr_hex')
        and original_callbacks[-1]['raw_input'].get('cdr_sha256')==command.get('original_applied_cdr_sha256')
        and original_callbacks[-1]['processed_ns']<spawns.get('foreign',{}).get('monotonic_ns',0), 'foreign_command_exact_actual_original_terminal_callback_CDR_before_spawn')
    foreign_report=foreign_source_population(run,inputs,foreign,command,emit,c36.lines(run/'foreign/source.jsonl'),c36.load(run/'foreign/terminal.json'),foreign_messages,foreign_rows,by_role['foreign'],proof['proof_ns'],close,c)
    # The original publisher's session is checked against independently received
    # original-GID typed occurrences, each conserved in complete Storage above.
    # This intentionally does not assign copied SQLite rows to a specific writer.
    original_decoded=dict(decoded);original_decoded[c36.APPLIED]=[{'message':m} for m in owned_messages]
    publisher=p.base.publisher_join(c36.load(run/'publisher/session_summary.json'),original_decoded,c36.load(run/'publisher/startup_manifest.json'),pub)
    c.need(publisher.get('passed') is True,'whole_original_F5_session_received_occurrences_and_Storage_conservation',issues=publisher.get('issues'))
    original_transport=[r for r in by_role['publisher'] if r.get('topic')==c36.APPLIED]
    c.need(len(original_transport)==len(owned_messages) and len(decoded[c36.APPLIED])==len(original_transport)+3,
        'entire_original_and_foreign_Applied_transport_received_Storage_count_conservation')
    receipts,raw_worker=p.worker_population(observer,decoded,worker,peer,c);pubs=p.worker_publication_population(run,inputs,ws,observer,decoded,worker,c)
    expected={k:worker[k] for k in ('run_id','boot_id')};expected.update(contract_hash=worker['contract_sha256'],nominal_hash=worker['nominal_hash'],pid=worker['pid'],fault_injection_enabled=p.worker_fault_permission(worker,c))
    lease=p.lease.replay(observer,expected,obs['contract_configuration']['worker_capability_receipt_timeout_ns'],c.need,decode_raw=lambda raw,index:raw_worker['capability'].get(raw['callback_sequence']),require_observation=True)
    witness=p.witness_source_population(c36.load(run/'observer/witness.json'),c36.load(run/'expected_witness_header.json'),observer,c)
    physical={pub['effective_parameters'][k]['value'] for k in ('vrx_left_thrust_topic','vrx_right_thrust_topic')}
    for role in ('observer','foreign'):
        c.need(manifests[role].get('physical_publisher_endpoints')==0 and not any(e.get('kind')=='publisher' and e.get('topic') in physical for e in manifests[role]['endpoints']), 'actual_no_diagnostic_role_physical_publisher_endpoint',role=role)
    recorder=c36.load(run/'recorder/terminal.json');c.need(recorder.get('clean') is True and recorder.get('prepared') is True
        and recorder.get('Recorder_stop_completed') is True and recorder.get('metadata_exists') is True
        and recorder.get('metadata_sha256')==c36.sha(run/'recorder/bag/metadata.yaml') and recorder.get('storage_id')=='sqlite3'
        and recorder.get('manifest_sha256')==c36.sha(run/'recorder/owned_manifest.json'),'actual_SQLite_recorder_terminal')
    terminal=c36.load(run/'synthetic_source/terminal.json');c.need(terminal.get('normal_end') is True and terminal.get('failed') is False
        and terminal.get('run_id')==inputs['run_id'] and terminal.get('transport_counts')==transport['counts']
        and terminal.get('transport_total')==sum(transport['counts'].values()), 'whole_synthetic_transport_terminal_counter_conservation')
    c.need(exact(inputs.get('source_bundles'),c36.load(HERE/'source_bundles_current.json'))
        and exact(inputs.get('builds'),{row['role']:row for row in c36.load(HERE/'build_manifest_current.json')}),
        'input_assets_exact_current_selected_source_and_build_registries')
    pins=p.asset_pins(inputs,c)
    deps=checker_dependency_population(run,inputs,c)
    after={str(f):c36.sha(f) for f in files};c.need(before==after,'entire_raw_run_files_unchanged')
    c.need(all(c36.sha(path)==value for path,value in pins.items()),'all_author_assets_unchanged_during_check')
    return c.result(schema=SCHEMA,run_dir=str(run),case='foreign_after_close',diagnostic_case_predicate_passed=not c.issues,
        diagnostic_only=True,normal_driver_passed=result.get('passed'),resource_cleanup_complete=result.get('cleanup_complete'),
        qualifications=FLAGS,unknowns=p.UNKNOWNS,storage=storage,transport_storage=transport,source_typed_storage=source,
        applied_callbacks=applied,foreign_publications=foreign_report,late_graph=late_graph,publisher_session=publisher,worker_callbacks=receipts,
        worker_publications=pubs,capability_receipt_lease={'callbacks':lease['callbacks'],'final':lease['final']},witness_v2=witness,
        input_sha256_before=before,input_sha256_after=after,author_asset_sha256=pins,
        checker_dependencies={str(dep):c36.sha(dep) for dep in deps},checker_sha256=c36.sha(__file__),
        all_published_received_claimed=False,window_clipped=False,unique_bag_row_writer_identity_proven=False,
        normal_business_contract_qualified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:report=analyze(args.run_dir)
    except Exception as error:report={'schema':SCHEMA,'passed':False,'reader_error':repr(error),'diagnostic_only':True,'qualifications':FLAGS}
    size=c38.write(args.output,report);print(json.dumps({'passed':report['passed'],'issues':report.get('issues'),'reader_error':report.get('reader_error'),'bytes':size}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
