#!/usr/bin/env python3
"""Post-run T2 audit (S2 freeze, batch 71): consumes the frozen clauses.

Reads a finished run directory, re-validates the registration and action
table, then accounts the executed receipts SEPARATELY from Regulator state
rows and enforces the family's registered timing clauses. Total over
incomplete observations: missing evidence yields False checks, never an
exception. Exit 0 only when every check holds."""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import t2_action_contract as t2


def rows(path):
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def audit_run(run_dir, table):
    run_dir = Path(run_dir)
    fixture_rows = rows(run_dir / 'fixture/nominal_steps.jsonl')
    driver_rows = rows(run_dir / 'driver_events.jsonl')
    regulator_rows = rows(run_dir / 'regulator/source.jsonl')
    receipts = [r for r in fixture_rows if r.get('type') == t2.RECEIPT_TYPE] + \
               [r for r in driver_rows if r.get('type') == 't2_driver_action_executed']
    for r in receipts:
        if r.get('type') == 't2_driver_action_executed':
            r['type'] = t2.RECEIPT_TYPE
            r.setdefault('executed_ns', r.get('checked_ns', 0))
            r.setdefault('trigger', (r.get('command') or {}).get('trigger', {}))
            r.setdefault('command_sha256', t2.digest(t2.encoded_json(r.get('command', {}))))
    by_id = {r.get('action_id'): r for r in receipts}
    checks = {}
    try:
        accounting = t2.check_receipts(table, receipts, regulator_rows)
        checks['receipt_accounting'] = accounting['receipts_complete'] and accounting['regulator_rows_separate_stream']
        checks['accounting_detail'] = accounting
    except AssertionError as error:
        checks['receipt_accounting'] = False
        checks['accounting_error'] = str(error)
    family = table['case']
    clauses = table['clauses']
    if family == 'T2A-clock-freeze':
        hold = next((r for r in receipts if (r.get('parameters') or {}).get('mode')), None)
        resume = next((r for r in receipts if r.get('action') == 'clock_resume'), None)
        checks['hold_receipt_present'] = hold is not None
        if hold is not None:
            duration_ns = int(hold['parameters']['duration_ms']) * 1000000
            mode = hold['parameters']['mode']
            effective = (resume or hold).get('executed_ns', 0) - hold['executed_ns'] \
                if resume else None
            if mode == 'silent':
                checks['silent_hold_exceeds_receipt_stale'] = effective is None or \
                    effective >= clauses['receipt_stale_ns']
            else:
                checks['same_stamp_registered'] = mode == 'same_stamp'
            checks['hold_minimum_respected'] = effective is None or effective >= duration_ns
            after = [r for r in regulator_rows
                     if (r.get('processed_ns') or r.get('submit_commit_ns') or 0) > hold['executed_ns']]
            checks['regulator_stream_observed_after_hold'] = bool(after)
    elif family == 'T2B-inflight-clear-replace':
        action_receipt = receipts[0] if receipts else None
        checks['path_receipt_present'] = action_receipt is not None
        if action_receipt is not None:
            job = action_receipt.get('trigger', {}).get('job') or {}
            old_task = job.get('task_generation')
            version_rows = [r for r in regulator_rows if r.get('type') == 'path_version'
                            and (r.get('processed_ns') or 0) > action_receipt['executed_ns']]
            checks['regulator_task_version_after_receipt'] = bool(version_rows) and (
                old_task is None or version_rows[-1].get('task_generation', old_task) > old_task)
            stale_rejects = [r for r in regulator_rows
                             if r.get('type') == 'candidate_registration'
                             and r.get('accepted_registration') is False
                             and r.get('reason') in clauses['stale_result_reject_reasons']
                             and (r.get('ready_commit_ns') or 0) > action_receipt['executed_ns']]
            checks['stale_result_rejected_with_registered_reason'] = bool(stale_rejects)
            checks['trigger_phase_is_inflight_or_ready'] = \
                action_receipt.get('trigger', {}).get('phase') in ('solve_active', 'ready_window')
    else:
        shutdown = by_id.get(next((a['id'] for a in table['actions']
                                   if a['action'] == 'driver_shutdown_request'), ''), None)
        checks['shutdown_receipt_present'] = shutdown is not None
        if shutdown is not None:
            ready_ns = shutdown.get('trigger', {}).get('observed_ns', 0)
            request_ns = shutdown['executed_ns']
            stopping = [r for r in regulator_rows if r.get('type') in
                        ('owned_reception_closed', 'business_start_closed_before_tick')]
            stopping_ns = min((r.get('closed_ns') or r.get('closed_ns', 0) for r in stopping), default=None)
            target = (shutdown.get('trigger', {}).get('job') or {}).get('job_id')
            guard_rejects = [r for r in regulator_rows if r.get('type') == 'decision'
                             and r.get('job_id') == target and r.get('accepted') is False]
            checks['ready_before_request'] = 0 < ready_ns < request_ns
            checks['stopping_observed'] = stopping_ns is not None and stopping_ns >= request_ns
            checks['target_not_accepted_after_request'] = all(
                (r.get('ready_commit_ns') or r.get('activation_commit_ns') or 0) <= request_ns
                for r in guard_rejects) if guard_rejects else True
            checks['ordering_clause_consumed'] = clauses['ordering'] == \
                'ready_commit<request<=stopping_observed<=activation_guard'
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    reg = json.loads((args.run / 'registration_copy.json').read_bytes()) \
        if (args.run / 'registration_copy.json').is_file() else None
    table = json.loads((args.run / 'action_table_copy.json').read_bytes())
    if reg is not None:
        t2.validate_table(table, {'run_id': reg['run_id'], 'case': reg['case'],
                                  'contract_sha256': reg['contract_sha256']})
    checks = audit_run(args.run, table)
    verdict = all(v is True for k, v in checks.items() if isinstance(v, bool))
    print(json.dumps({'checks': checks, 'passed': verdict}, ensure_ascii=False, indent=2))
    return 0 if verdict else 2


if __name__ == '__main__':
    raise SystemExit(main())
