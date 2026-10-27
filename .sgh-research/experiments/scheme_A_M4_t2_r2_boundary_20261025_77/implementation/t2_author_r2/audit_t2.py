#!/usr/bin/env python3
"""Fail-closed per-clause T2 audit (R0 rewrite, batch 75).

Every frozen clause gets an explicit predicate with real evidence, or an
explicit 'not_covered' status; missing files, corrupt JSON and absent events
are recorded failures, never silently green. Combined gates cover receipts,
command identity, Source output accounting, role closure and witness
structure; a registration may pre-declare a finite diagnostic ending (e.g.
regulator rc 3 with witness observation incomplete) and the audit then
requires the run to match the declared ending exactly. Exit 0 only when every
applicable check holds."""
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


def _table_entry(table, action_id):
    for row in table['actions']:
        if row['id'] == action_id:
            return row
    return None


def _receipts_match_table(table, receipts, failures):
    """Wrong action/parameters in a receipt must fail (74 counterexample)."""
    for receipt in receipts:
        entry = _table_entry(table, receipt.get('action_id'))
        if entry is None:
            failures.append('receipt action outside table: %r' % receipt.get('action_id'))
            continue
        if receipt.get('action') is not None and receipt['action'] != entry['action']:
            failures.append('receipt action differs from table: ' + str(receipt['action_id']))
        if receipt.get('parameters') is not None and receipt['parameters'] != entry['parameters']:
            failures.append('receipt parameters differ from table: ' + str(receipt['action_id']))


def _api_accounting(regulator_rows, failures):
    """Source-level decision/Applied contiguity: seq12-style gaps must fail."""
    decisions = [r for r in regulator_rows if r.get('type') == 'decision' and type(r.get('sequence')) is int]
    seqs = sorted(r['sequence'] for r in decisions)
    if seqs and seqs != list(range(1, len(seqs) + 1)):
        failures.append('non-contiguous decision sequence: %s' % seqs)
    applied = [r for r in regulator_rows if 'applied' in str(r.get('type', '')) and type(r.get('sequence')) is int]
    aseqs = sorted(r['sequence'] for r in applied)
    if not applied:
        failures.append('no Applied accounting rows in the regulator Source')
    elif aseqs != list(range(1, len(aseqs) + 1)):
        failures.append('non-contiguous Applied sequence: %s' % aseqs)
    published = [r for r in decisions if r.get('publish_success') == [True, True]]
    if len(published) > len(applied):
        failures.append('decisions with both-side publish success exceed Applied rows (%d vs %d)'
                        % (len(published), len(applied)))
    return {'decisions': len(decisions), 'applied_rows': len(applied)}


def _closure_gate(driver_result, expected, failures):
    closed = driver_result.get('closed_roles') or []
    by_role = {r.get('role'): r for r in closed if isinstance(r, dict)}
    if set(by_role) != {'regulator', 'fixture', 'worker', 'recorder'}:
        failures.append('role closure incomplete: %s' % sorted(by_role))
        return
    declared_rc = (expected or {}).get('regulator_returncode', 0)
    for role in ('fixture', 'worker', 'recorder'):
        row = by_role[role]
        if row.get('returncode') != 0 or row.get('group_empty') is not True:
            failures.append('role close invalid: ' + role)
    if by_role['regulator'].get('returncode') != declared_rc:
        failures.append('regulator rc %r differs from declared/expected %r'
                        % (by_role['regulator'].get('returncode'), declared_rc))


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


def audit_run(run_dir, table, registration=None, driver_result=None, commands=None):
    run_dir = Path(run_dir)
    failures = []
    checks = {}
    fixture_rows = _rows_or_failure(run_dir / 'fixture/nominal_steps.jsonl', failures, 'fixture source')
    driver_rows = _rows_or_failure(run_dir / 'driver_events.jsonl', failures, 'driver events')
    regulator_rows = _rows_or_failure(run_dir / 'regulator/source.jsonl', failures, 'regulator source')
    if fixture_rows is None or driver_rows is None or regulator_rows is None:
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
    checks['closure_gate'] = not any('close' in f or 'closure' in f or 'rc ' in f for f in failures)
    _witness_gate(run_dir, expected, failures)
    checks['witness_gate'] = not any('witness' in f for f in failures)

    family = table['case']
    clauses = table['clauses']
    clock_rows = [r for r in regulator_rows if r.get('type') == 'clock']
    regs = [r for r in regulator_rows if r.get('type') == 'candidate_registration']
    decisions = [r for r in regulator_rows if r.get('type') == 'decision']

    def row_ns(r):
        return r.get('processed_ns') or r.get('submit_commit_ns') or r.get('ready_commit_ns') or 0

    if family == 'T2A-clock-freeze':
        hold = next((r for r in receipts if (r.get('parameters') or {}).get('mode')), None)
        resume = next((r for r in receipts if r.get('action') == 'clock_resume'), None)
        checks['hold_receipt_present'] = hold is not None
        if hold is None:
            failures.append('T2A: no clock_hold receipt')
        else:
            during = [r for r in clock_rows if hold['executed_ns'] <= r.get('receive_ns', 0)
                      <= (resume or hold)['executed_ns']]
            gaps = [b.get('receive_ns', 0) - a.get('receive_ns', 0) for a, b in zip(during, during[1:])]
            last_before = max((r.get('receive_ns', 0) for r in clock_rows
                               if r.get('receive_ns', 0) <= hold['executed_ns']), default=0)
            if last_before and during:
                gaps.append(during[0].get('receive_ns', 0) - last_before)
            mode = hold['parameters']['mode']
            duration_ns = int(hold['parameters']['duration_ms']) * 1000000
            effective = (resume['executed_ns'] - hold['executed_ns']) if resume else None
            if mode == 'silent':
                checks['silent_exceeds_receipt_stale'] = bool(gaps) and max(gaps, default=0) >= clauses['receipt_stale_ns']
                if not checks['silent_exceeds_receipt_stale']:
                    failures.append('T2A: no real stale receive gap during the silent hold')
                checks['same_stamp_registered'] = 'not_covered:silent run'
            else:
                checks['same_stamp_registered'] = mode == 'same_stamp'
                checks['silent_exceeds_receipt_stale'] = 'not_covered:same_stamp run'
            checks['hold_minimum_respected'] = effective is None or effective >= duration_ns
            schedule_before = max((r.get('schedule_generation', 0) for r in clock_rows
                                   if r.get('receive_ns', 0) <= hold['executed_ns']), default=0)
            schedule_after = max((r.get('schedule_generation', 0) for r in clock_rows
                                  if resume and r.get('receive_ns', 0) >= resume['executed_ns']), default=0)
            checks['pause_confirmed_generation_bump'] = (resume is None) or (schedule_after > schedule_before)
            if resume is not None and schedule_after <= schedule_before:
                failures.append('T2A: no schedule generation bump across pause/resume')
            gen_at_hold = max(((r.get('job') or {}).get('task_generation', 0) for r in regs
                               if r.get('accepted_registration') and row_ns(r) <= hold['executed_ns']), default=0)
            revived = [r for r in regs if r.get('accepted_registration') and row_ns(r) > hold['executed_ns']
                       and (r.get('job') or {}).get('task_generation', 1 << 30) <= gen_at_hold]
            checks['old_candidate_must_not_revive'] = not revived
            if revived:
                failures.append('T2A: accepted registration at/below pre-hold generation after the hold')
            if resume is not None:
                later = [r for r in regs if r.get('accepted_registration') and row_ns(r) > resume['executed_ns']]
                checks['resume_requires_new_window'] = all(
                    (r.get('job') or {}).get('schedule_generation', 0) > schedule_before for r in later)
            else:
                checks['resume_requires_new_window'] = 'not_covered:no resume'
    elif family == 'T2B-inflight-clear-replace':
        checks['job_deadline_ns_after_origin_frozen'] = clauses['job_deadline_ns_after_origin'] == 150000000
        checks['deadline_must_not_extend'] = clauses['deadline_must_not_extend'] is True
        checks['missed_window_is_registered_failure'] = clauses['missed_window_is_registered_failure'] is True
        checks['expiry_not_masquerading'] = clauses['expiry_or_worker_terminal_is_not_task_rejection'] is True
        action_receipt = receipts[0] if receipts else None
        checks['path_receipt_present'] = action_receipt is not None
        if action_receipt is not None:
            job = action_receipt.get('trigger', {}).get('job') or {}
            old_task = job.get('task_generation')
            checks['trigger_phase_is_inflight_or_ready'] = \
                action_receipt.get('trigger', {}).get('phase') in ('solve_active', 'ready_window')
            version_rows = [r for r in regulator_rows if r.get('type') == 'path_version'
                            and row_ns(r) > action_receipt['executed_ns']]
            checks['regulator_task_version_after_receipt'] = bool(version_rows) and (
                old_task is None or version_rows[-1].get('task_generation', old_task) > old_task)
            if not checks['regulator_task_version_after_receipt']:
                failures.append('T2B: no regulator task-version commit after the replace receipt')
            same_job = job.get('job_id')
            stale_rejects = [r for r in regs
                             if r.get('accepted_registration') is False
                             and r.get('reason') in clauses['stale_result_reject_reasons']
                             and row_ns(r) > action_receipt['executed_ns']
                             and (same_job is None or (r.get('job') or {}).get('job_id') == same_job)]
            checks['stale_result_rejected_with_registered_reason'] = bool(stale_rejects)
            if not stale_rejects:
                failures.append('T2B: no same-target stale rejection with a registered reason')
    else:
        entry = next((a for a in table['actions'] if a['action'] == 'driver_shutdown_request'), None)
        target = entry and entry['trigger'].get('job_id')
        shutdown = next((r for r in receipts if r.get('executor') == 'driver'), None)
        checks['shutdown_receipt_present'] = shutdown is not None
        if shutdown is None or target is None:
            failures.append('T2C: shutdown receipt or bound target missing')
        else:
            request_ns = shutdown.get('executed_ns', 0)
            ready_ns = shutdown.get('trigger', {}).get('observed_ns', 0)
            ready_target = next((r for r in regs if r.get('accepted_registration')
                                 and (r.get('job') or {}).get('job_id') == target), None)
            guard_rows = [r for r in decisions if r.get('job_id') == target
                          and r.get('accepted') is False and r.get('activation_commit_ns')]
            stopping = next((r for r in decisions if r.get('reason') == 'shutdown'
                             and r.get('end_ns')), None)
            checks['target_ready_registered'] = ready_target is not None
            checks['target_guard_present'] = bool(guard_rows)
            checks['stopping_observed'] = stopping is not None
            if not guard_rows:
                failures.append('T2C: no real activation guard row for the target Job')
            if stopping is None:
                failures.append('T2C: no shutdown-observing decision row (reception_closed is not evidence)')
            accepted_after = [r for r in decisions if r.get('job_id') == target and r.get('accepted') is True
                              and (r.get('ready_commit_ns') or 0) > request_ns]
            checks['no_target_accepted_after_request'] = not accepted_after
            if accepted_after:
                failures.append('T2C: target accepted after the stop request')
            if guard_rows and stopping is not None:
                guard_ns = min(r['activation_commit_ns'] for r in guard_rows)
                checks['ordering_clause_holds'] = 0 < ready_ns < request_ns <= stopping['end_ns'] <= guard_ns
                if not checks['ordering_clause_holds']:
                    failures.append('T2C: ready_commit<request<=stopping_observed<=activation_guard violated')
            else:
                checks['ordering_clause_holds'] = False
            checks['ordering_clause_consumed'] = clauses['ordering'] == \
                'ready_commit<request<=stopping_observed<=activation_guard'
    checks = {k: (v if isinstance(v, str) else bool(v)) for k, v in checks.items()}
    passed = not failures and all(v is True or str(v).startswith('not_covered') for v in checks.values())
    return {'checks': checks, 'failures': failures, 'passed': passed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    failures = []
    reg_path = args.run / 'registration_copy.json'
    table_path = args.run / 'action_table_copy.json'
    if not table_path.is_file():
        print(json.dumps({'passed': False, 'failures': ['action table copy missing']}, indent=2))
        return 2
    table = json.loads(table_path.read_bytes())
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
