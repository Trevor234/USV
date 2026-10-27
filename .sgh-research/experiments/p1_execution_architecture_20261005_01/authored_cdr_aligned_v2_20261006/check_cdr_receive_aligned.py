"""Account finite CDR attempts without attributing an independent reader to production.

validate() is a pure decoded-data proof. scan_bag() alone imports ROS packages.
The original mixed bag is never rewritten; the native contract view excludes
only exact declared injection blobs. All such samples have separate complete
accounting, including disagreement between local and production decode paths.
"""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

from check_p1_execution import (JOB_ALIASES, CANDIDATE_ALIASES, DECISION_ALIASES,
                                exact, job_projection, validate_decoded,
                                runtime_context, plain)

JOB = '/p1/solve_job'
CANDIDATE = '/p1/solve_candidate'
DECISION = '/p1/execution_decision'
RAW_TOPICS = (JOB, CANDIDATE)
STAGES = ('before', 'header4', 'tail_minus4', 'after')
BASE_KEYS = ('source_bag_contract_complete', 'logical_admission_contract_passed',
             'lifecycle_verified', 'raw_input_recording_complete',
             'activation_source_contract_complete')


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def raw_key(row):
    return row.get('topic'), row.get('bytes'), row.get('sha256')


def job_of(row):
    message = row['message']
    return message if row['topic'] == JOB else message['job']


def _validate_base(data):
    """Return scoped gates; raw non-delivery may be explained but never called rejection."""
    issues = []
    def need(ok, code, scope='mechanism'):
        if not ok:
            issues.append({'scope': scope, 'code': code})
    plan, sends, raw, bag = (data[k] for k in ('plan', 'sends', 'raw', 'bag'))
    context, summary = data['context'], data['summary']
    reg, worker, ledger = data['reg'], data['worker'], data['ledger']
    run = context.get('run_id')
    cases = plan.get('cases', [])
    need(plan.get('schema') == 'p1-cdr-plan-aligned-v2' and plan.get('run_id') == run
         and plan.get('sample_count') == 8 and len(cases) == 8,
         'fixed_plan_identity_or_count', 'attempt')
    need(plan.get('observer_depth') == 64 and plan.get('production_reader_depth') == 1
         and plan.get('actual_plant') is False and plan.get('physical_endpoints') == 0,
         'fixed_plan_reader_or_output_scope', 'attempt')
    expected = [(topic, stage) for topic in RAW_TOPICS for stage in STAGES]
    need([(c.get('topic'), c.get('stage')) for c in cases] == expected
         and [c.get('case_index') for c in cases] == list(range(8)),
         'fixed_plan_case_order', 'attempt')
    ids = [c.get('job_id') for c in cases]
    need(len(set(ids)) == len(ids) and all(type(v) is int and v > 0 for v in ids),
         'injection_ids_not_unique_positive', 'attempt')
    facts = data.get('blob_facts', [])
    need(len(facts) == len(cases), 'injected_blob_fact_count', 'attempt')
    for i, c in enumerate(cases):
        f = facts[i] if i < len(facts) else {}
        need(all(f.get(k) == c.get(k) for k in ('blob', 'bytes', 'sha256'))
             and f.get('path_within_blob_directory') is True,
             'injected_blob_binding_' + str(i), 'attempt')
        need(c.get('valid_control') is (c.get('stage') in ('before', 'after')),
             'control_classification_' + str(i), 'attempt')
        need((c.get('stage') != 'empty' or c.get('bytes') == 0)
             and (c.get('stage') != 'header4' or c.get('bytes') == 4),
             'finite_stimulus_length_' + str(i), 'attempt')
    need(len(sends) == len(cases), 'send_ledger_attempt_count', 'attempt')
    previous_return = 0
    for i, c in enumerate(cases):
        s = sends[i] if i < len(sends) else {}
        need(all(s.get(k) == v for k, v in c.items()), 'send_plan_binding_' + str(i), 'attempt')
        at, returned = s.get('attempt_ns'), s.get('return_ns')
        need(type(at) is int and type(returned) is int and 0 < previous_return <= at <= returned
             if i else type(at) is int and type(returned) is int and 0 < at <= returned,
             'send_monotonic_order_' + str(i), 'attempt')
        previous_return = returned if type(returned) is int else previous_return
        target = 'p1_solver_worker' if c.get('topic') == JOB else 'p1_regulator'
        names = s.get('subscriber_names', [])
        need(type(s.get('matched_count')) is int and s['matched_count'] >= 3
             and target in names and 'p1_calibration_driver' in names
             and any('recorder' in v for v in names), 'writer_match_scope_' + str(i), 'attempt')
        need(type(s.get('api_returned')) is bool, 'api_result_unknown_' + str(i), 'attempt')
        if s.get('api_returned') is False:
            need(bool(s.get('exception_type')) and bool(s.get('exception')),
                 'api_error_not_recorded_' + str(i), 'attempt')
    observed = Counter(raw_key(r) for r in raw)
    stored = Counter(raw_key(r) for r in bag if r.get('topic') in RAW_TOPICS)
    need(observed == stored, 'raw_observer_storage_multiset_difference', 'raw')
    need([r.get('sequence') for r in raw] == list(range(1, len(raw) + 1)),
         'raw_observer_sequence_gap', 'raw')
    need(all(type(r.get('receive_ns')) is int and r['receive_ns'] > 0 for r in raw),
         'raw_observer_monotonic_time_unknown', 'raw')
    bykey = {}
    for b in bag:
        if b.get('topic') in RAW_TOPICS:
            bykey.setdefault(raw_key(b), []).append(b)
        if b.get('decoded') is False:
            need(bool(b.get('exception_type')) and bool(b.get('exception')),
                 'bag_decode_error_unrecorded', 'raw')
    discrepancies = []
    for r in raw:
        candidates = bykey.get(raw_key(r), [])
        need(bool(candidates), 'raw_storage_sample_missing', 'raw')
        if candidates and any(b.get('decoded') is not r.get('decoded') for b in candidates):
            discrepancies.append({'topic': r.get('topic'), 'bytes': r.get('bytes'),
                                  'sha256': r.get('sha256'), 'observer_decoded': r.get('decoded'),
                                  'bag_decoded': [b.get('decoded') for b in candidates]})
        if r.get('decoded') is False:
            need(bool(r.get('exception_type')) and bool(r.get('exception')),
                 'observer_decode_error_unrecorded', 'raw')
        elif r.get('decoded') is True:
            need(all((r.get('job_id'), r.get('run_id')) ==
                     (job_of(b).get('job_id'), job_of(b).get('run_id'))
                     for b in candidates if b.get('decoded') is True),
                 'observer_decoded_identity_difference', 'raw')
        else:
            need(False, 'observer_decode_status_unknown', 'raw')
    attempt_results = []
    controls = []
    declared_keys = {raw_key(c): c for c in cases}
    for i, c in enumerate(cases):
        s = sends[i] if i < len(sends) else {}
        nraw, nbag = observed[raw_key(c)], stored[raw_key(c)]
        need(nraw in (0, 1) and nbag in (0, 1), 'injection_duplicate_' + str(i), 'raw')
        if s.get('api_returned') is False:
            need(nraw == nbag == 0, 'api_reject_observed_bytes_' + str(i), 'attempt')
            classification = 'publisher_api_rejected'
        elif nraw == nbag == 1:
            classification = 'independent_raw_reader_and_recorder_observed'
        else:
            classification = 'raw_delivery_not_observed'
        entries = bykey.get(raw_key(c), [])
        local_entries = [r for r in raw if raw_key(r) == raw_key(c)]
        business = ([e for e in worker if e.get('type') == 'job_rejected'
                     and e.get('job_id') == c.get('job_id')] if c.get('topic') == JOB else
                    [e for e in reg if e.get('type') == 'candidate_registration'
                     and e.get('job', {}).get('job_id') == c.get('job_id')])
        business_observed = False
        if business:
            # Empty/header-only bytes carry no job identity. Their plan IDs are
            # labels, not wire content, and cannot attribute an unrelated event.
            need(c.get('stage') in ('before', 'after', 'tail_minus4'),
                 'unidentifiable_blob_business_id_' + str(i))
            need(len(business) == 1 and business[0].get('reason') == 'foreign',
                 'injected_business_rejection_count_or_reason_' + str(i))
            event = business[0]
            if c.get('topic') == JOB:
                need(type(event.get('receive_ns')) is int and event['receive_ns'] >= s.get('attempt_ns', 0),
                     'injected_job_business_time_' + str(i))
            else:
                need(event.get('accepted_registration') is False
                     and type(event.get('ready_commit_ns')) is int
                     and event['ready_commit_ns'] >= s.get('attempt_ns', 0),
                     'injected_candidate_business_time_' + str(i))
                # Even if the local decoder rejects the candidate suffix, its
                # entire embedded Job precedes that suffix. The independent
                # valid control is a field stencil, with only the reserved ID
                # differing. Never invent an independently decoded full result.
                before = next((p for p in cases if p.get('topic') == c.get('topic') and p.get('stage') == 'before'), {})
                stencil = bykey.get(raw_key(before), [])
                expected_job = dict(job_of(stencil[0])) if len(stencil) == 1 and stencil[0].get('decoded') is True else {}
                expected_job['job_id'] = c.get('job_id')
                need(bool(stencil) and exact(job_projection(event.get('job', {}), True), job_projection(expected_job)),
                     'injected_candidate_business_job_stencil_' + str(i))
            business_observed = len(business) == 1 and business[0].get('reason') == 'foreign'
        if c.get('valid_control'):
            controls.append(c)
            need(s.get('api_returned') is True and nraw == nbag == 1,
                 'foreign_control_raw_delivery_' + str(i))
            need(len(entries) == 1 and entries[0].get('decoded') is True
                 and job_of(entries[0]).get('run_id') == 'foreign_cdr_' + run
                 and job_of(entries[0]).get('job_id') == c.get('job_id'),
                 'foreign_control_decode_identity_' + str(i))
            need(len(local_entries) == 1 and local_entries[0].get('decoded') is True
                 and local_entries[0].get('run_id') == 'foreign_cdr_' + run
                 and local_entries[0].get('job_id') == c.get('job_id'),
                 'foreign_control_observer_identity_' + str(i))
            need(business_observed, 'foreign_control_business_source_' + str(i))
        if business_observed:
            classification = ('locally_decoded_and_production_business_rejected'
                              if local_entries and local_entries[0].get('decoded') is True else
                              'local_decoder_failed_but_production_business_rejected')
        elif entries:
            classification = ('independent_decoder_succeeded_target_path_unknown'
                              if local_entries and local_entries[0].get('decoded') is True else
                              'independent_decoder_failed_target_path_unknown')
        attempt_results.append({**c, 'api_returned': s.get('api_returned'),
                                'raw_observer_count': nraw, 'bag_count': nbag,
                                'classification': classification,
                                'observer_decoded': local_entries[0].get('decoded') if local_entries else None,
                                'bag_decoded': entries[0].get('decoded') if entries else None,
                                'production_business_rejection_observed': business_observed,
                                'target_reader_delivery': 'business_callback_observed' if business_observed else 'unknown',
                                'target_reader_rejection_layer': 'business_foreign_identity_gate' if business_observed else 'unknown',
                                'target_complete_decode_success': 'unknown'})
    need(len(controls) == 4, 'four_foreign_controls_missing')
    native_jobs = [b['message'] for b in bag if b.get('topic') == JOB
                   and b.get('decoded') is True and raw_key(b) not in declared_keys]
    native_candidates = [b['message'] for b in bag if b.get('topic') == CANDIDATE
                         and b.get('decoded') is True and raw_key(b) not in declared_keys]
    source_jobs = [e for e in reg if e.get('type') == 'job']
    source_candidates = [e for e in worker if e.get('type') == 'candidate']
    decisions = [e for e in reg if e.get('type') == 'decision']
    native_ids = [j.get('job_id') for j in native_jobs]
    need(len(set(native_ids)) == len(native_ids) and not (set(native_ids) & set(ids)),
         'injection_id_entered_native_namespace')
    need({e.get('job', {}).get('job_id') for e in source_jobs} == set(native_ids)
         and len(source_jobs) == len(native_jobs), 'native_job_source_identity_set')
    for j in native_jobs:
        need(j.get('run_id') == run and j.get('boot_id') == context.get('boot_id')
             and j.get('contract_hash') == context.get('contract_sha256'),
             'undeclared_decoded_job_identity')
        matching = [e for e in source_jobs if e.get('job', {}).get('job_id') == j.get('job_id')]
        need(len(matching) == 1 and exact(job_projection(matching[0]['job'], True), job_projection(j)),
             'native_job_full_source_echo')
    candidate_ids = [m.get('job', {}).get('job_id') for m in native_candidates]
    need(len(set(candidate_ids)) == len(candidate_ids) and not (set(candidate_ids) & set(ids))
         and {e.get('job', {}).get('job_id') for e in source_candidates} == set(candidate_ids)
         and len(source_candidates) == len(native_candidates), 'native_candidate_source_identity_set')
    for m in native_candidates:
        match = [e for e in source_candidates if e.get('job', {}).get('job_id') == m.get('job', {}).get('job_id')]
        need(len(match) == 1 and exact(job_projection(match[0].get('job', {}), True), job_projection(m.get('job', {})))
             and all(exact(match[0].get(CANDIDATE_ALIASES.get(k, k)), v)
                     for k, v in m.items() if k != 'job'), 'native_candidate_full_source_echo')
    stored_decisions = [b['message'] for b in bag if b.get('topic') == DECISION and b.get('decoded') is True]
    need(len(decisions) == len(stored_decisions), 'decision_source_storage_count')
    for e, m in zip(decisions, stored_decisions):
        need(all(exact(e.get(DECISION_ALIASES.get(k, k)), v) for k, v in m.items()),
             'decision_full_source_echo')
    need(bool(decisions) and all(e.get('publish_success') == [False, False]
         and e.get('normal_contract_complete') is False for e in decisions), 'physical_output_or_normal_promotion')
    need(not any(e.get('job_id') in ids and e.get('accepted') is True for e in decisions),
         'injected_id_activated')
    registrations = [e for e in reg if e.get('type') == 'candidate_registration' and e.get('accepted_registration') is True]
    submitted = {e['job']['job_id']: e for e in source_jobs}
    solved = {m['job']['job_id']: m for m in native_candidates}
    registered = {e['job']['job_id']: e for e in registrations}
    def genuine(e):
        jid = e.get('job_id'); m = solved.get(jid, {})
        return (e.get('accepted') is True and jid in submitted and jid in registered
                and m.get('solver_invoked') is True and m.get('success') is True
                and m.get('prediction_available') is True and m.get('backend') == 'acados'
                and submitted[jid]['job'].get('target_tick') == e.get('tick'))
    first = min((s.get('attempt_ns', 0) for s in sends), default=0)
    last = max((s.get('return_ns', 0) for s in sends), default=0)
    prefix = [e for e in decisions if genuine(e) and e.get('activation_commit_ns', 0) < first]
    recovered = [e for e in decisions if genuine(e) and e.get('activation_commit_ns', 0) > last
                 and submitted[e['job_id']].get('submit_commit_ns', 0) > last]
    need(len(prefix) >= 1, 'native_accepted_prefix_missing')
    need(len(recovered) >= 3, 'three_fresh_native_accepted_successors_missing')
    need(not any(e.get('type') in ('worker_unusable_transition', 'scheduler_skipped_ticks') for e in reg),
         'terminal_or_scheduler_skip')
    need(not any(e.get('type') == 'terminal_numerical_failure' for e in worker), 'native_terminal_failure')
    rs = [e for e in reg if e.get('type') == 'source_summary']
    ws = [e for e in worker if e.get('type') == 'worker_summary']
    need(len(rs) == 1 and reg[-1] is rs[0] and rs[0].get('generated') == rs[0].get('emitted') == len(reg) - 1
         and rs[0].get('dropped') == 0 and rs[0].get('normal_source_complete') is True,
         'regulator_source_close_count', 'evidence')
    need(len(ws) == 1 and worker[-1] is ws[0] and ws[0].get('generated_candidates') == ws[0].get('published_candidates') == len(source_candidates)
         and ws[0].get('fatal') is False and ws[0].get('normal_source_complete') is True,
         'worker_source_close_count', 'evidence')
    need(data.get('all_sources_closed') is True, 'source_file_unclosed', 'evidence')
    for name in ('regulator', 'worker'):
        text = data.get('consoles', {}).get(name, '')
        need(text.splitlines().count(name.upper() + '_CLOSE_FLUSH_SUCCESS=true') == 1
             and name.upper() + '_CLOSE_FLUSH_SUCCESS=false' not in text,
             name + '_flush_console_unknown', 'evidence')
    need(context.get('mode') == 'no_output' and context.get('declaration', {}).get('cdr_injection') is True
         and all(context.get('declaration', {}).get(k) == 0 for k in
                 ('test_delay_ms', 'test_native_block_ms', 'test_prepare_block_ms', 'test_tick_block_ms')),
         'actual_isolated_no_output_scope', 'evidence')
    need(summary.get('failure') is None and summary.get('cleanup_complete') is True
         and summary.get('cleanup_failed') is False and summary.get('supervision_evidence_complete') is True
         and summary.get('graph_no_physical_publishers') is True,
         'runner_cleanup_graph_or_evidence', 'evidence')
    for name in ('worker', 'regulator', 'fixture', 'recorder'):
        result = summary.get('cleanup', {}).get(name, {})
        spawn = [e for e in ledger if e.get('type') == 'spawn' and e.get('name') == name]
        cleanup = [e for e in ledger if e.get('type') == 'cleanup_result' and e.get('name') == name]
        need(len(spawn) == len(cleanup) == 1 and spawn[0].get('executable_verified') is True
             and result.get('cleanup_complete') is True and result.get('remaining_members') == []
             and result.get('returncode') == 0 and all(exact(cleanup[0].get(k), v) for k, v in result.items()),
             'owned_process_cleanup_binding_' + name, 'evidence')
    base = data.get('native_view_contract', {})
    need(base.get('issues') == [] and all(base.get(k) is True for k in BASE_KEYS),
         'native_view_contract_incomplete', 'evidence')
    complete_receiver = len(attempt_results) == 8 and all(v['raw_observer_count'] == v['bag_count'] == 1 for v in attempt_results)
    return {'schema': 'p1-cdr-receive-aligned-proof-v2', 'run_id': run, 'issues': issues,
            'selected_observation_gate_passed': not issues,
            'attempt_accounting_complete': not any(e['scope'] in ('attempt', 'raw') for e in issues),
            'evidence_accounting_complete': not any(e['scope'] in ('attempt', 'raw', 'evidence') for e in issues),
            'independent_reader_coverage_complete': complete_receiver and not any(e['scope'] in ('attempt', 'raw') for e in issues),
            'target_reader_fault_observation_complete': False,
            'target_reader_rejection_layer': 'unknown',
            'unknown': ['target_typed_reader_delivery_for_malformed_blobs',
                        'target_take_or_deserialization_rejection_layer',
                        'target_per_blob_error_observation'],
            'attempts': attempt_results, 'native_prefix_accepted': len(prefix),
            'decoder_discrepancies': discrepancies,
            'fresh_native_successors_accepted': len(recovered),
            'native_view_contract_passed': base.get('issues') == [] and all(base.get(k) is True for k in BASE_KEYS),
            'normal_contract_complete': False, 'execute_qualified': False,
            'zero_physical_endpoints': summary.get('graph_no_physical_publishers') is True,
            'physical_output_observed': any(any(v is True for v in e.get('publish_success', [])) for e in decisions),
            'plant_acceptance_observed': False}



def validate(data):
    """Require a separately owned raw reader and exact bytes across the process boundary."""
    result = _validate_base(data)
    issues = result['issues']
    def need(ok, code, scope='evidence'):
        if not ok:
            issues.append({'scope': scope, 'code': code})
    context, summary, ledger = data['context'], data['summary'], data['ledger']
    external = data.get('external', [])
    starts = [e for e in external if e.get('type') == 'startup']
    endings = [e for e in external if e.get('type') == 'summary']
    inventories = [e for e in external if e.get('type') == 'endpoint_inventory']
    observed = [e for e in external if 'sequence' in e]
    need(len(starts) == len(endings) == len(inventories) == 1 and len(external) == len(observed) + 3
         and bool(external) and external[0] is starts[0] and external[-1] is endings[0],
         'external_source_start_or_terminal_missing')
    start = starts[0] if len(starts) == 1 else {}
    end = endings[0] if len(endings) == 1 else {}
    driver_pid = context.get('driver_pid')
    need(data['plan'].get('external_observer_required') is True,
         'external_observer_not_declared', 'attempt')
    need(type(driver_pid) is int and driver_pid > 0 and type(start.get('pid')) is int
         and start.get('pid') > 0 and start['pid'] != driver_pid,
         'external_observer_not_separate_process')
    need(start.get('schema') == end.get('schema') == 'p1-cdr-external-v1'
         and start.get('boot_id') == context.get('boot_id')
         and start.get('physical_publishers_created') == 0
         and end.get('pid') == start.get('pid') and end.get('error') is None
         and isinstance(start.get('node_name'), str) and bool(start.get('node_name')),
         'external_startup_identity_or_schema')
    spawn = [e for e in ledger if e.get('type') == 'spawn' and e.get('name') == 'raw_observer']
    identity = spawn[0].get('identity', {}) if len(spawn) == 1 else {}
    need(len(spawn) == 1 and spawn[0].get('executable_verified') is True
         and spawn[0].get('boot_id') == context.get('boot_id')
         and identity.get('pid') == start.get('pid')
         and identity.get('pid') == identity.get('pgid') == identity.get('sid')
         and type(identity.get('start_ticks')) is int and identity['start_ticks'] > 0
         and bool(identity.get('exe_sha256'))
         and identity.get('exe_sha256') == spawn[0].get('expected_sha256'),
         'external_owned_process_identity')
    clean = summary.get('cleanup', {}).get('raw_observer', {})
    clean_rows = [e for e in ledger if e.get('type') == 'cleanup_result' and e.get('name') == 'raw_observer']
    need(len(clean_rows) == 1 and clean.get('cleanup_complete') is True
         and clean.get('returncode') == 0 and clean.get('remaining_members') == []
         and all(exact(clean_rows[0].get(k), v) for k, v in clean.items()),
         'external_owned_cleanup_unverified')
    need(end.get('normal_source_complete') is True and end.get('received_count') == len(observed)
         and len(observed) > 0 and data.get('external_source_closed') is True
         and data.get('external_blob_directory_complete') is True,
         'external_source_close_count')
    need([e.get('sequence') for e in observed] == list(range(1, len(observed) + 1)),
         'external_source_sequence_gap', 'raw')
    need(all(e.get('topic') in RAW_TOPICS and type(e.get('receive_ns')) is int
         and e.get('receive_ns') > 0 for e in observed),
         'external_source_topic_or_clock', 'raw')
    facts = data.get('external_blob_facts', [])
    need(len(facts) == len(observed), 'external_blob_count', 'raw')
    for i, row in enumerate(observed):
        fact = facts[i] if i < len(facts) else {}
        need(fact.get('sequence') == row.get('sequence')
             and fact.get('blob') == f"{row.get('sequence', 0):06d}.cdr"
             and fact.get('bytes') == row.get('bytes') and fact.get('sha256') == row.get('sha256')
             and fact.get('path_within_blob_directory') is True,
             'external_blob_byte_binding_' + str(i), 'raw')
        need(type(row.get('decoded')) is bool, 'external_decode_status_unknown_' + str(i), 'raw')
        if row.get('decoded') is False:
            need(bool(row.get('exception_type')) and bool(row.get('exception')),
                 'external_decode_error_unrecorded_' + str(i), 'raw')
    actual = [b for b in data['bag'] if b.get('topic') in RAW_TOPICS]
    external_counter = Counter(raw_key(e) for e in observed)
    bag_counter = Counter(raw_key(b) for b in actual)
    driver_counter = Counter(raw_key(r) for r in data['raw'])
    need(external_counter == bag_counter, 'external_raw_storage_multiset_difference', 'raw')
    need(external_counter == driver_counter, 'driver_external_raw_multiset_difference', 'raw')
    cases = data['plan'].get('cases', [])
    for case in cases:
        need(type(case.get('bytes')) is int and case['bytes'] > 0 and case['bytes'] % 4 == 0,
             'declared_sample_not_four_byte_aligned_' + str(case.get('case_index')), 'attempt')
        need(external_counter[raw_key(case)] == bag_counter[raw_key(case)] == driver_counter[raw_key(case)] == 1,
             'aligned_injection_exact_bytes_missing_' + str(case.get('case_index')), 'raw')
    inventory = inventories[0] if len(inventories) == 1 else {}
    subscriptions = inventory.get('subscriptions', {})
    need(inventory.get('pid') == start.get('pid') and set(subscriptions) == set(RAW_TOPICS),
         'external_endpoint_inventory_identity')
    def valid_gid(gid):
        return (isinstance(gid, list) and len(gid) in (16, 24)
                and all(type(v) is int and 0 <= v <= 255 for v in gid)
                and any(gid[:12]))
    for topic in RAW_TOPICS:
        endpoints = subscriptions.get(topic, [])
        need(len(endpoints) == 1 and endpoints[0].get('node_name') == start.get('node_name')
             and valid_gid(endpoints[0].get('endpoint_gid')),
             'external_subscription_gid_' + topic)
        if len(endpoints) != 1 or not valid_gid(endpoints[0].get('endpoint_gid')):
            continue
        actual_gid = endpoints[0]['endpoint_gid']
        for send in data['sends']:
            if send.get('topic') != topic:
                continue
            readers = [e for e in send.get('subscriber_endpoints', [])
                       if e.get('node_name') == start.get('node_name')]
            writers = [e for e in send.get('publisher_endpoints', [])
                       if e.get('node_name') == 'p1_calibration_driver']
            need(len(readers) == 1 and readers[0].get('endpoint_gid') == actual_gid,
                 'external_send_subscription_gid_' + str(send.get('case_index')))
            need(bool(writers) and all(valid_gid(e.get('endpoint_gid')) for e in writers)
                 and all(e['endpoint_gid'][:12] != actual_gid[:12] for e in writers)
                 and len({tuple(e['endpoint_gid'][:12]) for e in writers if valid_gid(e.get('endpoint_gid'))}) == 1,
                 'external_driver_participant_prefix_' + str(send.get('case_index')))
    bykey = {}
    for row in actual:
        bykey.setdefault(raw_key(row), []).append(row)
    discrepancies = []
    for row in observed:
        matching = bykey.get(raw_key(row), [])
        if matching and any(b.get('decoded') is not row.get('decoded') for b in matching):
            discrepancies.append({'topic': row.get('topic'), 'bytes': row.get('bytes'),
                                  'sha256': row.get('sha256'), 'external_decoded': row.get('decoded'),
                                  'bag_decoded': [b.get('decoded') for b in matching]})
        if row.get('decoded') is True:
            need(all((row.get('job_id'), row.get('run_id')) ==
                     (job_of(b).get('job_id'), job_of(b).get('run_id'))
                     for b in matching if b.get('decoded') is True),
                 'external_decoded_identity_difference', 'raw')
    for attempt in result['attempts']:
        matching = [e for e in observed if raw_key(e) == raw_key(attempt)]
        attempt['external_observer_count'] = len(matching)
        attempt['external_decoded'] = matching[0].get('decoded') if len(matching) == 1 else None
        if attempt.get('valid_control'):
            need(len(matching) == 1 and matching[0].get('decoded') is True
                 and matching[0].get('job_id') == attempt.get('job_id')
                 and matching[0].get('run_id') == 'foreign_cdr_' + context['run_id'],
                 'external_valid_control_identity_' + str(attempt.get('case_index')))
    result.update(
        selected_observation_gate_passed=not issues,
        attempt_accounting_complete=not any(e['scope'] in ('attempt', 'raw') for e in issues),
        evidence_accounting_complete=not any(e['scope'] in ('attempt', 'raw', 'evidence') for e in issues),
        independent_reader_coverage_complete=(not issues and len(cases) == 8
            and all(external_counter[raw_key(c)] == bag_counter[raw_key(c)] == 1 for c in cases)),
        external_observer_pid=start.get('pid'), driver_pid=driver_pid,
        external_raw_received_count=len(observed),
        external_decoder_discrepancies=discrepancies,
        observer_scope='owned process distinct from producer; actual participant GID evidence retained',
        external_startup_evidence=start, external_close_evidence=end,
        normal_contract_complete=False, execute_qualified=False)
    return result


def scan_bag(bag, expected_topics):
    """Scan all actual rows; preserve malformed rows rather than silently skipping them."""
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    meta = yaml.safe_load((bag / 'metadata.yaml').read_text())['rosbag2_bagfile_information']
    if meta['storage_identifier'] != 'mcap':
        raise ValueError('unexpected actual storage')
    expected_counts = {r['topic_metadata']['name']: r['message_count'] for r in meta['topics_with_message_count']}
    types = {r['topic_metadata']['name']: r['topic_metadata']['type'] for r in meta['topics_with_message_count']}
    if types != expected_topics:
        raise ValueError('metadata topic/type scope differs')
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id='mcap'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    if {v.name: v.type for v in reader.get_all_topics_and_types()} != types:
        raise ValueError('actual storage topic types differ')
    classes = {k: get_message(v) for k, v in types.items()}
    rows = []
    counts = Counter()
    while reader.has_next():
        topic, blob, timestamp = reader.read_next()
        blob = bytes(blob); counts[topic] += 1
        row = {'topic': topic, 'bytes': len(blob), 'sha256': digest(blob), 'bag_receive_ns': int(timestamp)}
        try:
            message = deserialize_message(blob, classes[topic])
            row.update(decoded=True, message=plain(dict(message_to_ordereddict(message))))
        except Exception as error:
            row.update(decoded=False, exception_type=type(error).__name__, exception=str(error)[:1024])
        rows.append(row)
    if dict(counts) != expected_counts or sum(counts.values()) != meta['message_count']:
        raise ValueError('actual storage counts differ from metadata')
    return rows, {'actual_topic_counts': dict(counts), 'topic_types': types,
                  'timestamp_semantics': 'bag wall timestamp; never compared to CLOCK_MONOTONIC'}


def read_lines(path):
    blob = path.read_bytes()
    if not blob.endswith(b'\n'):
        raise ValueError('unclosed source: ' + str(path))
    return [json.loads(row) for row in blob.decode().splitlines()]


def check(directory):
    from check_p1_execution import TOPICS
    directory = directory.resolve()
    output = directory / 'verification_cdr_aligned_v2'
    if output.exists():
        raise FileExistsError('create-only CDR verification already exists')
    context = json.loads((directory / 'run_context.json').read_text())
    normalized, binding_files = runtime_context(directory, context)
    contract_file = Path(context['contract_file'])
    contract = json.loads(contract_file.read_text())
    files = [p for p in directory.rglob('*') if p.is_file()] + binding_files + [contract_file]
    locked = {str(p): digest(p.read_bytes()) for p in set(files)}
    if locked[str(contract_file)] != context['contract_sha256']:
        raise ValueError('contract bytes differ from frozen context')
    plan = json.loads((directory / 'cdr_injection_plan.json').read_text())
    blob_root = (directory / 'cdr_injected_blobs').resolve()
    blob_facts = []
    for case in plan['cases']:
        path = (blob_root / case['blob']).resolve()
        inside = path.parent == blob_root and path.name == case['blob']
        if not inside:
            raise ValueError('injected blob escaped fixed directory')
        blob = path.read_bytes()
        blob_facts.append({'blob': case['blob'], 'bytes': len(blob), 'sha256': digest(blob),
                           'path_within_blob_directory': inside})
    topics = {**{v: {'clock':'rosgraph_msgs/msg/Clock', 'odom':'nav_msgs/msg/Odometry',
                      'imu':'sensor_msgs/msg/Imu', 'path':'nav_msgs/msg/Path',
                      'profile':'std_msgs/msg/Float64MultiArray'}[k]
                  for k, v in context['topics']['inputs'].items()}, **TOPICS,
              context['topics']['p1']['stop']: 'std_msgs/msg/Bool'}
    bag, storage = scan_bag(directory / context['bag_relative_path'], topics)
    reg, worker = read_lines(directory / 'regulator_source.jsonl'), read_lines(directory / 'worker_source.jsonl')
    fixture = read_lines(directory / 'fixture_source.jsonl')
    if len(fixture) != 1 or fixture[0].get('type') != 'fixture_summary':
        raise ValueError('fixture source completion differs')
    normalized['_fixture_summary'] = fixture[0]
    normalized['_actual_topic_counts'] = storage['actual_topic_counts']
    declared = {raw_key(c) for c in plan['cases']}
    view = {k: [] for k in TOPICS}
    for row in bag:
        if row['topic'] in view and row['decoded'] and not (row['topic'] in RAW_TOPICS and raw_key(row) in declared):
            view[row['topic']].append({'message': row['message'], 'bag_receive_ns': row['bag_receive_ns']})
    base = validate_decoded(reg, worker, view, contract, normalized, context['contract_sha256'])
    data = {'plan': plan, 'sends': read_lines(directory / 'cdr_send_ledger.jsonl'),
            'raw': read_lines(directory / 'cdr_raw_observer.jsonl'), 'bag': bag,
            'reg': reg, 'worker': worker, 'ledger': read_lines(directory / 'owned_process_ledger.jsonl'),
            'context': context, 'summary': json.loads((directory / 'runner_summary.json').read_text()),
            'blob_facts': blob_facts, 'all_sources_closed': True,
            'consoles': {n: (directory / (n + '.console.log')).read_text(errors='replace') for n in ('worker', 'regulator')},
            'native_view_contract': base}
    external = read_lines(directory / 'cdr_external_observer.jsonl')
    external_root = (directory / 'cdr_external_blobs').resolve()
    external_facts = []
    for row in external:
        if 'sequence' not in row:
            continue
        if type(row['sequence']) is not int or row['sequence'] <= 0:
            raise ValueError('invalid external blob sequence')
        name = f"{row['sequence']:06d}.cdr"
        path = (external_root / name).resolve()
        if path.parent != external_root:
            raise ValueError('external blob escaped fixed directory')
        blob = path.read_bytes()
        external_facts.append({'sequence': row['sequence'], 'blob': name,
                               'bytes': len(blob), 'sha256': digest(blob),
                               'path_within_blob_directory': True})
    names = {f['blob'] for f in external_facts}
    directory_complete = {p.name for p in external_root.iterdir() if p.is_file()} == names
    data.update(external=external, external_blob_facts=external_facts, external_source_closed=True,
                external_blob_directory_complete=directory_complete)
    result = validate(data)
    if any(digest(Path(p).read_bytes()) != value for p, value in locked.items()):
        raise RuntimeError('raw evidence changed during verification')
    result.update(storage=storage, raw_evidence_sha256=locked,
                  native_view_contract_issues=base['issues'],
                  native_view_contract_scope='derived native-only view; original mixed bag accounted separately')
    output.mkdir()
    with (output / 'cdr_receive_check.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'raw_evidence_sha256'}, sort_keys=True))
    return 0 if result['selected_observation_gate_passed'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    raise SystemExit(check(parser.parse_args().directory))
