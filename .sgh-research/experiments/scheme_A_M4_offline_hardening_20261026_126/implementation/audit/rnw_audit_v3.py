"""Strict RNW Source/Worker/Stored audit. V2 gates are a subset, never final acceptance."""
import hashlib
import json
from pathlib import Path
import rnw_audit_v2 as legacy

JOB_ALIASES = {'schema_version': 'schema', 'tick_origin_steady_ns': 'tick_origin_ns',
               'freeze_steady_ns': 'freeze_ns', 'deadline_steady_ns': 'deadline_ns',
               'target_steady_ns': 'target_ns', 'horizon_steps': 'N', 'prediction_dt': 'dt'}
DECISION_ALIASES = {'schema_version': 'schema', 'clock_epoch': 'epoch', 'tick_planned_ns': 'planned_ns',
                    'tick_start_ns': 'start_ns', 'candidate_ready_commit_ns': 'ready_commit_ns',
                    'tick_end_ns': 'end_ns', 'candidate_accepted': 'accepted'}


class AuditViolation(Exception):
    pass


def demand(condition, reason):
    if not condition:
        raise AuditViolation(reason)


def equal(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def one(rows, typ, field, value):
    found = [r for r in rows if r.get('type') == typ and r.get(field) == value]
    demand(len(found) == 1, 'population.' + typ)
    return found[0]


def canonical_job(message):
    return {JOB_ALIASES.get(k, k): v for k, v in message.items()}


def strict_chain(src, worker, job_id=7):
    base_r4, _ = legacy.audit_r4(src, target_job=job_id)
    demand(base_r4['passed'] is True, 'reference_generation_or_decision_echo')
    jr = next((r for r in src if r.get('type') == 'job' and r.get('job', {}).get('job_id') == job_id), None)
    demand(jr is not None, 'target_job_missing')
    j = jr['job']
    c = [r for r in src if r.get('type') == 'candidate_registration' and r.get('job', {}).get('job_id') == job_id]
    w = [r for r in worker if r.get('type') == 'candidate' and r.get('job', {}).get('job_id') == job_id]
    received = [r for r in worker if r.get('type') == 'job_received' and r.get('job', {}).get('job_id') == job_id]
    demand(len(c) == len(w) == len(received) == 1, 'worker_or_registration_population')
    c, w, received = c[0], w[0], received[0]
    demand(equal(j, c['job']) and equal(j, w['job']) and equal(j, received['job']), 'complete_job_echo')
    demand(c['accepted_registration'] is True and w['success'] is True and w['solver_invoked'] is True, 'candidate_success')
    policy = one(worker, 'cold_start_policy_result', 'job_id', job_id)
    demand(policy['metadata']['actual_C_solve_calls_this_job'] > 0 and policy['metadata']['successful'] is True, 'actual_C_entry')
    published = one(worker, 'candidate_publish_result', 'job_id', job_id)
    demand(published.get('success', published.get('published')) is True, 'candidate_publish_failed')
    decisions = [r for r in src if r.get('type') == 'decision' and r.get('job_id') == job_id]
    demand(len(decisions) == 1, 'decision_population')
    d = decisions[0]
    demand(d['accepted'] is True and d['control_source'] == 'candidate', 'decision_not_candidate')
    seq = d['sequence']; pair = one(src, 'owned_API_pair', 'sequence', seq); applied = one(src, 'owned_applied_publication', 'sequence', seq)
    demand(pair['returned'] == [True, True] and d['publish_success'] == [True, True] and applied['returned'] == [True, True], 'partial_API')
    demand(equal(pair['starts'], d['publish_start_ns']) and equal(pair['ends'], d['publish_end_ns'])
           and pair['starts'] == [applied['left_start'], applied['right_start']]
           and pair['ends'] == [applied['left_end'], applied['right_end']], 'both_channel_API_times')
    demand(equal(d['final_n'], pair['command_n']) and equal(d['final_n'], applied['n']), 'API_command_mismatch')
    demand(applied['control_source'] == 'candidate' and applied['config_hash'] == j['contract_hash'], 'Applied_identity')
    times = [jr['submit_commit_ns'], received['receive_ns'], w['solve_start_ns'], w['solve_end_ns'],
             c['ready_commit_ns'], d['activation_commit_ns'], *[pair['starts'][0], pair['ends'][0], pair['starts'][1], pair['ends'][1]], applied['publish_start_ns'], applied['publish_end_ns']]
    demand(all(type(t) is int and t > 0 for t in times) and times == sorted(times), 'full_logical_time_order')
    return {'job_id': job_id, 'sequence': seq, 'actual_C_calls': policy['metadata']['actual_C_solve_calls_this_job'], 'times': times}


def stored_reconcile(src, worker, stored):
    records = stored['records']; fields = stored['full_fields']
    demand({k: len(v) for k, v in fields.items()} == {'SolveJob': 44, 'SolveCandidate': 14, 'ExecutionDecision': 57, 'AppliedControl': 39}, 'full_schema_population')
    jobs = [r for r in src if r.get('type') == 'job']
    candidates = [r for r in worker if r.get('type') == 'candidate']
    decisions = [r for r in src if r.get('type') == 'decision']
    applied = [r for r in src if r.get('type') == 'owned_applied_publication']
    for kind, rows in [('SolveJob', jobs), ('SolveCandidate', candidates), ('ExecutionDecision', decisions), ('AppliedControl', applied)]:
        demand(len(rows) == len(records[kind]) and bool(rows), 'Stored_population.' + kind)
    for jr in jobs:
        data = [r['data'] for r in records['SolveJob'] if r['data']['job_id'] == jr['job']['job_id']]
        demand(len(data) == 1 and equal(canonical_job(data[0]), jr['job']), 'Stored_full_Job')
    for candidate in candidates:
        matches = [r for r in records['SolveCandidate'] if r['data']['job']['job_id'] == candidate['job']['job_id']]
        demand(len(matches) == 1, 'Stored_Candidate_population')
        d = matches[0]['data']
        expected = {key: candidate[{'worker_receive_ns': 'receive_ns', 'x_prediction': 'X', 'u_prediction': 'U'}.get(key, key)] for key in fields['SolveCandidate'] if key != 'job'}
        expected['job'] = candidate['job']
        observed = {**d, 'job': canonical_job(d['job'])}
        demand(equal(expected, observed), 'Stored_full_Candidate')
    for source in decisions:
        matches = [r['data'] for r in records['ExecutionDecision'] if r['data']['sequence'] == source['sequence']]
        expected = {key: source[DECISION_ALIASES.get(key, key)] for key in fields['ExecutionDecision']}
        demand(len(matches) == 1 and equal(expected, matches[0]), 'Stored_full_Decision')
    equal_raw_digests = 0
    contract_path = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json')
    contract = json.loads(contract_path.read_text())
    for source in applied:
        matches = [r for r in records['AppliedControl'] if r['data']['sequence'] == source['sequence']]
        demand(len(matches) == 1, 'Stored_Applied_population')
        stored_row = matches[0]; d = stored_row['data']
        equal_raw_digests += stored_row['cdr_sha256'] == source['cdr']['sha256']
        demand(stored_row['typed_serialization_bytes'] == source['cdr']['bytes']
               and 0 <= stored_row['trailing_padding_bytes'] <= 3 and stored_row['trailing_padding_zero'] is True,
               'Stored_Applied_typed_size_and_padding')
        demand(d['final_n'] == source['n'] and d['producer_instance_id'] == source['producer']
               and d['config_hash'] == source['config_hash'] and d['control_source'] == source['control_source']
               and d['left_publish_start_steady_ns'] == source['left_start'] and d['right_publish_start_steady_ns'] == source['right_start']
               and d['left_publish_end_steady_ns'] == source['left_end'] and d['right_publish_end_steady_ns'] == source['right_end'], 'Stored_Applied_identity')
        dec = one(src, 'decision', 'sequence', source['sequence'])
        expected = {
            'schema_version': 'p0-contract-v1', 'run_id': dec['run_id'], 'producer_instance_id': source['producer'],
            'baseline_id': source['baseline'], 'config_hash': dec['contract_hash'], 'clock_status': 'engineering_1_to_1',
            'steady_clock_domain': dec['boot_id'] + ':steady_clock', 'sequence': dec['sequence'], 'cycle_sequence': dec['sequence'],
            'clock_epoch': dec['epoch'], 'sim_time_ns': dec['activation_clock_sim_ns'],
            'clock_receive_steady_ns': dec['activation_clock_receive_ns'], 'clock_age_ns': dec['clock_age_ns'],
            'control_source': source['control_source'], 'event_semantics': 'actual_per_side_API_result',
            'requested_known': True, 'requested_n': dec['requested_n'], 'final_n': dec['final_n'],
            'left_publish_success': dec['publish_success'][0], 'right_publish_success': dec['publish_success'][1],
            'left_publish_start_steady_ns': dec['publish_start_ns'][0], 'left_publish_end_steady_ns': dec['publish_end_ns'][0],
            'right_publish_start_steady_ns': dec['publish_start_ns'][1], 'right_publish_end_steady_ns': dec['publish_end_ns'][1],
            'left_sim_time_ns': dec['publish_sim_ns'][0], 'right_sim_time_ns': dec['publish_sim_ns'][1],
            'left_clock_epoch': dec['publish_epoch'][0], 'right_clock_epoch': dec['publish_epoch'][1],
            'left_clock_age_ns': dec['publish_clock_age_ns'][0], 'right_clock_age_ns': dec['publish_clock_age_ns'][1],
            'map_scale': float(contract['map_scale']), 'lower_n': float(contract['command_min_n']), 'upper_n': float(contract['command_max_n']),
            'previous_anchor_known': all(dec['previous_anchor_known']), 'previous_final_n': dec['previous_n'],
            'plant_acceptance_observed': False, 'force_measured': False, 'execution_atomicity_proven': False,
            'publish_error': '' if all(dec['publish_success']) else 'partial_or_failed_API',
        }
        demand(set(expected) == set(fields['AppliedControl']) and equal(expected, d), 'Stored_full_Applied_fields')
    return {'populations': {k: len(v) for k, v in records.items()},
            'Applied_source_vs_Stored_raw_digest_equal_count': equal_raw_digests,
            'digest_scope': 'Source digest is a typed reserialization; raw bytes are not asserted equal. All 39 fields are recomputed from frozen emitter semantics and Source.'}


def audit(run, stored=None, target_job=7, source_override=None, worker_override=None):
    run = Path(run); gates = []; facts = None
    def check(name, function):
        try:
            value = function(); gates.append({'gate': name, 'passed': True, 'detail': {'rows': len(value)} if isinstance(value, list) else value})
            return value
        except AuditViolation as exc:
            gates.append({'gate': name, 'passed': False, 'reason': str(exc), 'coverage': 'covered_rejection'})
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            gates.append({'gate': name, 'passed': False, 'reason': type(exc).__name__ + ': ' + str(exc), 'coverage': 'not_covered_or_parse_error'})
        return None
    src, errors = legacy.rows_of(run / 'regulator/source.jsonl')
    src = source_override if source_override is not None else src
    check('Source.parse', lambda: demand(errors == 0, 'regulator_parse_error'))
    clocks = sorted([r for r in src if r.get('type') == 'clock'], key=lambda r: r['receive_ns'])
    commits = sorted([r for r in src if r.get('type') == 'reference_epoch_committed'], key=lambda r: r['submit_commit_ns'])
    opens = [r for r in src if r.get('type') == 'reference_epoch_generation_opened']
    jobs = sorted([r for r in src if r.get('type') == 'job'], key=lambda r: r['submit_commit_ns'])
    base_gates = legacy.audit_close(run) + legacy.audit_pause(clocks) + legacy.audit_generation(commits + opens) + [legacy.audit_jobs_monotonic(jobs), legacy.audit_r4(src, target_job=target_job)[0]]
    by_name = {g['gate']: g for g in base_gates}
    blockers = [name for name in legacy.ACCEPTANCE_GATES if name != 'source.parse_clean' and (name not in by_name or not by_name[name]['passed'] or by_name[name]['coverage'] == 'not_covered')]
    check('legacy_mandatory_gates', lambda: demand(not blockers, ','.join(blockers)))
    worker_path = run / 'worker/source.jsonl'
    def read_worker():
        rows, bad = legacy.rows_of(worker_path)
        demand(bad == 0, 'worker_parse_error')
        return rows
    worker = check('Worker.Source', read_worker)
    worker = worker_override if worker_override is not None else worker
    if worker is not None:
        facts = check('R4.complete_identity_time_and_API', lambda: strict_chain(src, worker, target_job))
    def summaries():
        summary = one(src, 'source_summary', 'type', 'source_summary')
        demand(summary['normal_source_complete'] is True and summary['dropped'] == 0
               and summary['generated'] == summary['emitted'] == len(src) - 1, 'Source_summary_balance')
        ws = one(worker, 'worker_summary', 'type', 'worker_summary')
        demand(ws['normal_source_complete'] is True and ws['fatal'] is False and ws['source_io_failed'] is False
               and ws['source_rows_emitted_before_terminal'] == ws['source_rows_before_terminal'] == len(worker)-1, 'Worker_summary_balance')
        shutdown = one(src, 'regulator_shutdown', 'type', 'regulator_shutdown')
        demand(shutdown['normal_contract_complete'] is True and shutdown['shutdown_grace_exceeded'] is False
               and shutdown['zero_requested'] is True and shutdown['zero_target_published'] is True, 'shutdown_not_complete')
        witness = json.loads((run / 'regulator/witness.json').read_text())
        job = next(r['job'] for r in src if r.get('type') == 'job')
        demand(witness['closed'] is True and witness['observation_complete'] is True and witness['overflow'] is False
               and witness['incomplete'] is False and witness['header']['run_id'] == job['run_id']
               and witness['header']['boot_id'] == job['boot_id'] and witness['header']['worker_instance'] == job['worker_instance'], 'witness_not_complete')
        for key in ['tick', 'submit', 'activation', 'phase']:
            demand(witness['counters'][key]['published'] == len(witness[key]), 'witness_population')
        for role in ['fixture', 'recorder']:
            terminal = json.loads((run / role / 'terminal.json').read_text())
            demand(terminal.get('normal_end', terminal.get('clean')) is True and terminal['run_id'] == job['run_id'], role + '_terminal')
        return True
    if worker is not None:
        check('Source.Worker.witness.close', summaries)
    if stored is None:
        gates.append({'gate': 'Stored.full_control_streams', 'passed': False, 'reason': 'Stored_not_decoded', 'coverage': 'not_covered'})
    elif worker is not None:
        check('Stored.full_control_streams', lambda: stored_reconcile(src, worker, stored))
    required = {'Source.parse', 'legacy_mandatory_gates', 'Worker.Source', 'R4.complete_identity_time_and_API', 'Source.Worker.witness.close', 'Stored.full_control_streams'}
    missing = sorted(required - {g['gate'] for g in gates})
    return {'r4_observed': facts, 'run_accepted': not missing and all(g['passed'] for g in gates), 'gates': gates, 'required_gates_absent': missing,
            'stage_qualified': False, 'qualification': {k: False for k in ['M4', 'F6', 'P1', 'plant', 'hard_realtime']},
            'scope': 'RNW family Source+Worker+closed typed control streams; no plant qualification'}
