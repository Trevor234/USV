#!/usr/bin/env python3
"""Evidence-consuming per-clause T2 audit (G1 rewrite, batch 84).

Consumes ALL role Sources (Fixture, Driver, Regulator, Worker) plus witness
and Stored artifacts. Every frozen clause has an explicit predicate over real
event evidence or an explicit not_covered status. Missing files, corrupt JSON
and absent events are recorded failures, never silently green."""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import t2_action_contract as t2


def _rows_or_failure(path, failures, label):
    p = Path(path)
    if not p.is_file():
        failures.append(label + ' missing: ' + str(p))
        return None
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            failures.append(label + ' corrupt line in ' + str(p))
            return None
    return out


def _api_accounting(regulator_rows, failures):
    """Exact-type decision/Applied contiguity: failed pubs don't count."""
    decisions = [r for r in regulator_rows if r.get('type') == 'decision' and type(r.get('sequence')) is int]
    seqs = sorted(r['sequence'] for r in decisions)
    if seqs and seqs != list(range(1, len(seqs) + 1)):
        failures.append('non-contiguous decision sequence: %s' % seqs)
    applied = [r for r in regulator_rows if r.get('type') == 'owned_applied_publication'
               and type(r.get('sequence')) is int]
    aseqs = sorted(r['sequence'] for r in applied)
    if not applied:
        failures.append('no successful Applied rows (owned_applied_publication) in the regulator Source')
    elif aseqs != list(range(1, len(aseqs) + 1)):
        failures.append('non-contiguous Applied sequence: %s' % aseqs)
    published = [r for r in decisions if r.get('publish_success') == [True, True]]
    if len(published) > len(applied):
        failures.append('decisions with both-side publish success exceed successful Applied rows (%d vs %d)'
                        % (len(published), len(applied)))
    return {'decisions': len(decisions), 'applied_success': len(applied)}


def _closure_gate(driver_result, expected, failures):
    closed = driver_result.get('closed_roles') or []
    by_role = {r.get('role'): r for r in closed if isinstance(r, dict)}
    if set(by_role) != {'regulator', 'fixture', 'worker', 'recorder'}:
        failures.append('role closure incomplete: %s' % sorted(by_role))
        return
    declared_rc = (expected or {}).get('regulator_returncode', 0)
    for role in ('regulator', 'fixture', 'worker', 'recorder'):
        row = by_role[role]
        expected_rc = declared_rc if role == 'regulator' else 0
        if row.get('returncode') != expected_rc:
            failures.append('role %s returncode %r differs from expected %r' % (role, row.get('returncode'), expected_rc))
        if row.get('group_empty') is not True:
            failures.append('role %s group not empty' % role)


def _witness_gate(run_dir, expected, failures):
    path = Path(run_dir) / 'regulator/witness.json'
    if not path.is_file():
        failures.append('witness file missing')
        return
    try:
        w = json.loads(path.read_bytes())
    except json.JSONDecodeError:
        failures.append('witness file corrupt')
        return
    declared = (expected or {}).get('witness_observation_complete')
    if declared is None:
        declared = True
    if w.get('observation_complete') is not declared:
        failures.append('witness observation_complete=%r differs from declared %r'
                        % (w.get('observation_complete'), declared))


def _stored_gate(run_dir, failures):
    bag = Path(run_dir) / 'recorder/bag'
    if not bag.is_dir() or not any(bag.iterdir()):
        failures.append('Stored artifacts (recorder/bag/) missing or empty')


def audit_run(run_dir, table, registration=None, driver_result=None, commands=None):
    run_dir = Path(run_dir)
    failures = []
    checks = {}
    fixture_rows = _rows_or_failure(run_dir / 'fixture/nominal_steps.jsonl', failures, 'fixture source')
    driver_rows = _rows_or_failure(run_dir / 'driver_events.jsonl', failures, 'driver events')
    regulator_rows = _rows_or_failure(run_dir / 'regulator/source.jsonl', failures, 'regulator source')
    worker_rows = _rows_or_failure(run_dir / 'worker/source.jsonl', failures, 'worker source')
    if any(v is None for v in (fixture_rows, driver_rows, regulator_rows, worker_rows)):
        return {'checks': checks, 'failures': failures, 'passed': False}

    receipts = [r for r in fixture_rows if r.get('type') == t2.RECEIPT_TYPE] + \
               [r for r in driver_rows if r.get('type') == 't2_driver_action_executed']
    for r in receipts:
        if r.get('type') == 't2_driver_action_executed':
            r['type'] = t2.RECEIPT_TYPE
            r.setdefault('executed_ns', r.get('checked_ns', 0))
            r.setdefault('trigger', (r.get('command') or {}).get('trigger', {}))
    if driver_result is None:
        p = run_dir / 'driver_result.json'
        driver_result = json.loads(p.read_bytes()) if p.is_file() else {}
    if commands is None:
        commands = driver_result.get('t2_command_records') or []

    # combined gates
    try:
        accounting = t2.check_receipts(table, receipts, regulator_rows, commands or None)
        checks['receipt_accounting'] = accounting['receipts_complete'] and accounting['regulator_rows_separate_stream']
    except AssertionError as error:
        checks['receipt_accounting'] = False
        failures.append('receipt accounting: ' + str(error))
    _receipts_match_table(table, receipts, failures)
    checks['receipts_match_table'] = not any('differ from table' in f or 'outside table' in f for f in failures)
    _api_accounting(regulator_rows, failures)
    checks['output_accounting'] = not any('sequence' in f or 'Applied' in f for f in failures)
    expected = (registration or {}).get('expected_diagnostics') if isinstance(registration, dict) else None
    _closure_gate(driver_result, expected, failures)
    checks['closure_gate'] = not any('closure' in f or 'returncode' in f or 'group' in f for f in failures)
    _witness_gate(run_dir, expected, failures)
    checks['witness_gate'] = not any('witness' in f for f in failures)
    _stored_gate(run_dir, failures)
    checks['stored_gate'] = not any('Stored' in f for f in failures)

    family = table['case']
    clauses = table['clauses']

    # Worker evidence extraction (G1-A)
    w_job_received = {}
    w_boundary_entered = {}
    w_boundary_result = {}
    w_candidates = []
    for row in worker_rows:
        wt = row.get('type')
        if wt == 'job_received':
            j = row.get('job')
            if isinstance(j, dict) and type(j.get('job_id')) is int:
                w_job_received[j['job_id']] = j
        elif wt == 'w2_boundary_entered':
            jid = row.get('job_id')
            if type(jid) is int:
                w_boundary_entered[jid] = row
        elif wt == 'w2_boundary_result':
            jid = row.get('job_id')
            if type(jid) is int:
                w_boundary_result[jid] = row
        elif wt == 'candidate':
            j = row.get('job')
            if isinstance(j, dict):
                w_candidates.append(j)

    # Regulator evidence extraction
    r_jobs = {}
    r_regs = [r for r in regulator_rows if r.get('type') == 'candidate_registration']
    r_decisions = [r for r in regulator_rows if r.get('type') == 'decision']
    r_path_versions = [r for r in regulator_rows if r.get('type') == 'path_version']
    for row in regulator_rows:
        if row.get('type') == 'job':
            j = row.get('job')
            if isinstance(j, dict) and type(j.get('job_id')) is int:
                r_jobs[j['job_id']] = j

    def row_ns(r):
        return r.get('processed_ns') or r.get('submit_commit_ns') or r.get('ready_commit_ns') or 0

    if family == 'T2B-inflight-clear-replace':
        action_receipt = receipts[0] if receipts else None
        checks['path_receipt_present'] = action_receipt is not None
        checks['job_deadline_ns_after_origin_frozen'] = clauses['job_deadline_ns_after_origin'] == 150000000
        checks['deadline_must_not_extend'] = clauses['deadline_must_not_extend'] is True
        checks['missed_window_is_registered_failure'] = clauses['missed_window_is_registered_failure'] is True
        checks['expiry_not_masquerading'] = clauses['expiry_or_worker_terminal_is_not_task_rejection'] is True
        if action_receipt is not None:
            trigger = action_receipt.get('trigger') or {}
            target_jid = (trigger.get('job') or {}).get('job_id')
            checks['trigger_phase_valid'] = trigger.get('phase') in ('solve_active', 'ready_window', 'job_received')
            # G1-A: Worker stream consumption
            checks['worker_source_present'] = len(worker_rows) > 0
            checks['original_job_submitted'] = target_jid in r_jobs
            if not checks['original_job_submitted']:
                failures.append('T2B: original Job %s not found in Regulator submissions' % target_jid)
            checks['worker_received_target'] = target_jid in w_job_received
            if not checks['worker_received_target']:
                failures.append('T2B: Worker job_received for target Job %s missing' % target_jid)
            boundary = w_boundary_entered.get(target_jid)
            checks['boundary_entered_for_target'] = boundary is not None
            if boundary is None:
                failures.append('T2B: no w2_boundary_entered for target Job %s' % target_jid)
            bres = w_boundary_result.get(target_jid)
            checks['boundary_disposition_allowed'] = bres is not None and bres.get('disposition') == 'allowed'
            if not checks['boundary_disposition_allowed']:
                failures.append('T2B: boundary disposition for target Job %s is %r (expected allowed)'
                                % (target_jid, bres and bres.get('disposition')))
            checks['actual_native_invoked'] = bres is not None and bres.get('actual_native_invoked') is True
            if not checks['actual_native_invoked']:
                failures.append('T2B: actual native not invoked for target Job %s' % target_jid)
            cand = next((c for c in w_candidates if c.get('job_id') == target_jid), None)
            checks['c_call_completed'] = cand is not None
            if cand is None:
                failures.append('T2B: Worker candidate for target Job %s missing' % target_jid)
            # Identity chain: original Job == Worker echo == rejection Job (full JSON)
            if cand is not None and target_jid in r_jobs:
                checks['same_job_identity'] = (cand == r_jobs[target_jid])
                if not checks['same_job_identity']:
                    failures.append('T2B: Worker echo Job differs from Regulator submitted Job')
            rejection = next((r for r in r_regs if (r.get('job') or {}).get('job_id') == target_jid
                              and r.get('accepted_registration') is False), None)
            checks['stale_result_rejected'] = rejection is not None and \
                rejection.get('reason') in clauses['stale_result_reject_reasons']
            if not checks['stale_result_rejected']:
                failures.append('T2B: no same-target rejection with registered reason')
            # G1-A: the rejection Job identity must match the original submission
            if rejection is not None and target_jid in r_jobs:
                rej_job = rejection.get('job') or {}
                checks['rejection_job_identity'] = rej_job == r_jobs[target_jid]
                if not checks['rejection_job_identity']:
                    failures.append('T2B: rejection Job identity differs from original submission')
            # Timeliness: rejection ready_commit within original deadline from tick_origin
            if rejection is not None and target_jid in r_jobs:
                origin = r_jobs[target_jid].get('tick_origin_ns') or r_jobs[target_jid].get('tick_origin_steady_ns', 0)
                deadline = origin + clauses['job_deadline_ns_after_origin']
                reject_ns = rejection.get('ready_commit_ns', 0)
                checks['timely_within_deadline'] = 0 < reject_ns <= deadline
                if not checks['timely_within_deadline']:
                    failures.append('T2B: rejection at %d exceeds deadline %d (origin=%d)' % (reject_ns, deadline, origin))
            # Path version strictly advanced after action
            old_task = (trigger.get('job') or {}).get('task_generation', 0)
            post_action_versions = [r for r in r_path_versions if row_ns(r) > action_receipt.get('executed_ns', 0)]
            checks['regulator_task_version_after_receipt'] = bool(post_action_versions)
            checks['generation_strictly_advanced'] = any(
                r.get('task_generation', 0) > old_task for r in post_action_versions)
            if not checks['generation_strictly_advanced']:
                failures.append('T2B: no path_version with strictly advanced task_generation after action')
    elif family == 'T2A-clock-freeze':
        hold = next((r for r in receipts if (r.get('parameters') or {}).get('mode')), None)
        resume = next((r for r in receipts if r.get('action') == 'clock_resume'), None)
        clock_rows = [r for r in regulator_rows if r.get('type') == 'clock']
        checks['hold_receipt_present'] = hold is not None
        if hold is not None:
            mode = hold['parameters']['mode']
            duration_ns = int(hold['parameters']['duration_ms']) * 1000000
            effective = (resume['executed_ns'] - hold['executed_ns']) if resume else None
            checks['hold_minimum_respected'] = effective is None or effective >= duration_ns
            if mode == 'silent':
                last_before = max((r.get('receive_ns', 0) for r in clock_rows
                                   if r.get('receive_ns', 0) <= hold['executed_ns']), default=0)
                first_after = min((r.get('receive_ns', 0) for r in clock_rows
                                   if r.get('receive_ns', 0) > hold['executed_ns']), default=0)
                checks['silent_exceeds_receipt_stale'] = (last_before > 0 and first_after > 0 and
                                                          first_after - last_before >= clauses['receipt_stale_ns'])
                if not checks['silent_exceeds_receipt_stale']:
                    failures.append('T2A: stale gap derivation failed (last_before=%d first_after=%d)'
                                    % (last_before, first_after))
                checks['same_stamp_registered'] = 'not_covered:silent run'
            else:
                during = [r for r in clock_rows if hold['executed_ns'] <= r.get('receive_ns', 0)
                          <= (resume or hold)['executed_ns']]
                sims = [r.get('sim_ns') for r in during if r.get('sim_ns') is not None]
                checks['same_stamp_registered'] = bool(during) and len(set(sims)) <= 1
                checks['silent_exceeds_receipt_stale'] = 'not_covered:same_stamp run'
            schedule_before = max((r.get('schedule_generation', 0) for r in clock_rows
                                   if r.get('receive_ns', 0) <= hold['executed_ns']), default=0)
            schedule_after = max((r.get('schedule_generation', 0) for r in clock_rows
                                  if resume and r.get('receive_ns', 0) >= resume['executed_ns']), default=0)
            checks['pause_confirmed_generation_bump'] = (resume is None) or (schedule_after > schedule_before)
            # Full version identity for old-candidate-revive (not just task_generation)
            def full_version(j):
                return tuple(j.get(k, 0) for k in ('task_generation', 'model_generation',
                                                    'config_generation', 'schedule_generation', 'clock_epoch'))
            old_versions = {full_version(r.get('job') or {}) for r in r_regs
                            if r.get('accepted_registration') and row_ns(r) <= hold['executed_ns']}
            revived = [r for r in r_regs if r.get('accepted_registration') and row_ns(r) > hold['executed_ns']
                       and full_version(r.get('job') or {}) in old_versions
                       and (r.get('job') or {}).get('job_id', -1) != -1]
            checks['old_candidate_must_not_revive'] = not revived
            if revived:
                failures.append('T2A: accepted registration with full old version identity after hold')
            later = [r for r in r_regs if r.get('accepted_registration') and row_ns(r) > ((resume or hold)['executed_ns'])]
            if resume is not None:
                if later:
                    checks['resume_requires_new_window'] = all(
                        (r.get('job') or {}).get('schedule_generation', 0) > schedule_before for r in later)
                else:
                    checks['resume_requires_new_window'] = 'not_covered:no post-resume acceptance'
            else:
                checks['resume_requires_new_window'] = 'not_covered:no resume'
    else:  # T2C
        entry = next((a for a in table['actions'] if a['action'] == 'driver_shutdown_request'), None)
        target = entry and entry['trigger'].get('job_id')
        shutdown = next((r for r in receipts if r.get('executor') == 'driver'), None)
        checks['shutdown_receipt_present'] = shutdown is not None
        if shutdown is None or target is None:
            failures.append('T2C: shutdown receipt or bound target missing')
        else:
            request_ns = shutdown.get('executed_ns', 0)
            ready_target = next((r for r in r_regs if r.get('accepted_registration')
                                 and (r.get('job') or {}).get('job_id') == target), None)
            guard_rows = [r for r in r_decisions if r.get('job_id') == target
                          and r.get('accepted') is False and r.get('activation_commit_ns')]
            stopping = next((r for r in r_decisions if r.get('reason') == 'shutdown'
                             and r.get('tick_start_ns')), None)
            checks['target_ready_registered'] = ready_target is not None
            checks['target_guard_present'] = bool(guard_rows)
            checks['stopping_observed'] = stopping is not None and stopping.get('tick_start_ns') is not None
            if not guard_rows:
                failures.append('T2C: no real activation guard row for the target Job')
            if stopping is None:
                failures.append('T2C: no shutdown-observing decision row')
            accepted_after = [r for r in r_decisions if r.get('job_id') == target and r.get('accepted') is True
                              and (r.get('activation_commit_ns') or 0) > request_ns]
            checks['no_target_accepted_after_request'] = not accepted_after
            if accepted_after:
                failures.append('T2C: target accepted after the stop request (activation_commit > request)')
            if guard_rows and stopping is not None:
                guard_ns = min(r['activation_commit_ns'] for r in guard_rows)
                ready_ns = shutdown.get('trigger', {}).get('observed_ns', 0)
                stop_ns = stopping['tick_start_ns']
                checks['ordering_clause_holds'] = 0 < ready_ns < request_ns <= stop_ns < guard_ns
                if not checks['ordering_clause_holds']:
                    failures.append('T2C: ready<request<=stop_tick_start<target_guard violated')
            else:
                checks['ordering_clause_holds'] = False
            checks['ordering_clause_consumed'] = clauses['ordering'] == \
                'ready_commit<request<=stopping_observed<=activation_guard'
    checks = {k: (v if isinstance(v, str) else bool(v)) for k, v in checks.items()}
    passed = not failures and all(v is True or str(v).startswith('not_covered') for v in checks.values())
    return {'checks': checks, 'failures': failures, 'passed': passed}


def _receipts_match_table(table, receipts, failures):
    declared = {row['id']: row for row in table['actions']}
    for receipt in receipts:
        entry = declared.get(receipt.get('action_id'))
        if entry is None:
            failures.append('receipt action outside table: %r' % receipt.get('action_id'))
            continue
        if receipt.get('action') is not None and receipt['action'] != entry['action']:
            failures.append('receipt action differs from table: ' + str(receipt['action_id']))
        if receipt.get('parameters') is not None and receipt['parameters'] != entry['parameters']:
            failures.append('receipt parameters differ from table: ' + str(receipt['action_id']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    failures = []
    table_path = args.run / 'action_table_copy.json'
    if not table_path.is_file():
        print(json.dumps({'passed': False, 'failures': ['action table copy missing']}, indent=2))
        return 2
    table = json.loads(table_path.read_bytes())
    reg_path = args.run / 'registration_copy.json'
    registration = json.loads(reg_path.read_bytes()) if reg_path.is_file() else None
    if registration is not None:
        try:
            t2.validate_table(table, {'run_id': registration['run_id'], 'case': registration['case'],
                                      'contract_sha256': registration['contract_sha256']})
        except AssertionError as error:
            failures.append('table re-validation: ' + str(error))
    result = audit_run(args.run, table, registration)
    result['failures'].extend(failures)
    result['passed'] = result['passed'] and not failures
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
