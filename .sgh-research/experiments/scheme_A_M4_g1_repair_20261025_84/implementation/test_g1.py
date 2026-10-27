#!/usr/bin/env python3
"""G1 offline validation (batch 84): named positive/negative suites.

Every 82nd-batch retained counterexample must be rejected by its intended
named assertion; positive controls must genuinely pass. No ROS."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 't2_author_g1'))
import t2_action_contract as t2
import audit_t2

V3 = t2.V3_CONTRACT_SHA
V4 = '3a8451d5172423adbef955d78c8550d67bbeec4582a80bd9ba69028b867b9f06'
T2A_14_RUN = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/runs/T2A_14')


def table_t2b():
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'G1', 'case': 'T2B-inflight-clear-replace',
            'contract_sha256': V4,
            'actions': [{'id': 'a1', 'action': 'path_replace',
                         'parameters': {'points': 101, 'speed_m_s': .05},
                         'trigger': {'phase': 'job_received', 'job_id': 2, 'delay_ms': 0}}],
            'clauses': {'job_deadline_ns_after_origin': 150000000, 'deadline_must_not_extend': True,
                        'missed_window_is_registered_failure': True,
                        'stale_result_reject_reasons': ['version_mismatch', 'job_echo_mismatch'],
                        'expiry_or_worker_terminal_is_not_task_rejection': True}}


def table_t2c():
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'G1', 'case': 'T2C-driver-shutdown-interleave',
            'contract_sha256': V3,
            'actions': [{'id': 'a1', 'action': 'driver_shutdown_request',
                         'parameters': {'reason': 'G1 test'}, 'trigger': {'phase': 'ready_window', 'job_id': 2, 'delay_ms': 0}}],
            'clauses': {'ordering': 'ready_commit<request<=stopping_observed<=activation_guard',
                        'stop_must_precede_activation_guard': True, 'guard_rejects_target': True,
                        'full_exit_and_storage_required': True}}


def table_t2a():
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'G1', 'case': 'T2A-clock-freeze',
            'contract_sha256': V3,
            'actions': [
                {'id': 'a1', 'action': 'clock_hold', 'parameters': {'mode': 'silent', 'duration_ms': 500},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 100}},
                {'id': 'a2', 'action': 'clock_resume', 'parameters': {'advance_ms': 0},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 800}}],
            'clauses': {'receipt_stale_ns': 100000000, 'pause_confirm_ns': 400000000,
                        'same_stamp_keeps_receipt_fresh': True, 'silent_exceeds_receipt_stale': True,
                        'old_candidate_must_not_revive': True, 'resume_requires_new_window': True}}


def make_job(jid=2, task=2, origin=1000000):
    return {'job_id': jid, 'task_generation': task, 'model_generation': 1, 'config_generation': 1,
            'schedule_generation': 1, 'clock_epoch': 0, 'tick_origin_ns': origin}


def receipt(action_id, executed_ns, trigger, command_sha='c0', **extra):
    row = {'type': 't2_action_executed', 'action_id': action_id, 'command_sha256': command_sha,
           'executed_ns': executed_ns, 'trigger': trigger}
    row.update(extra)
    return row


def command_record(action_id, command, sha):
    return {'action_id': action_id, 'sequence': command['sequence'], 'command_sha256': sha, 'command': command}


def write_run(files):
    root = Path(tempfile.mkdtemp())
    for rel, rows in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(rows, list):
            path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        else:
            path.write_text(json.dumps(rows, indent=2) + '\n')
    return root


def full_t2b_run(boundary_disposition='allowed', native_invoked=True, target_job=2,
                 worker_present=True, original_job_present=True, rejection_reason='version_mismatch',
                 rejection_identity=None, task_advance=True):
    """A complete T2B boundary run with real Worker/Regulator evidence."""
    origin = 1000000000
    j2 = make_job(2, 2, origin)
    trigger = {'phase': 'job_received', 'job': j2, 'observed_ns': origin + 1000000, 'source_role': 'worker'}
    command = {'schema': t2.COMMAND_SCHEMA, 'run_id': 'G1', 'contract_sha256': V4,
               'action_id': 'a1', 'sequence': 1, 'trigger': trigger}
    sha = t2.digest(t2.encoded_json(command))
    receipts = [dict(receipt('a1', origin + 50000000, trigger, sha),
                     action='path_replace', parameters={'points': 101, 'speed_m_s': .05})]
    worker = []
    if worker_present:
        worker = [{'type': 'job_received', 'job': j2, 'receive_ns': origin + 1000000, 'commit_ns': origin + 900000},
                  {'type': 'w2_boundary_entered', 'job_id': 2, 'ordinal': 1,
                   'entered_ns': origin + 1500000, 'job_deadline_ns': origin + 150000000},
                  {'type': 'w2_boundary_result', 'job_id': 2, 'disposition': boundary_disposition,
                   'actual_native_invoked': native_invoked, 'ordinal': 1},
                  {'type': 'candidate', 'job': j2, 'publish_start_ns': origin + 65000000}]
    regulator = []
    if original_job_present:
        regulator.append({'type': 'job', 'job': j2, 'submit_commit_ns': origin + 500000})
    new_task = 3 if task_advance else 2
    regulator += [
        {'type': 'path_version', 'processed_ns': origin + 51000000, 'task_generation': new_task},
        {'type': 'candidate_registration', 'accepted_registration': True, 'ready_commit_ns': origin + 2000000,
         'job': make_job(1, 2, origin - 200000000)},
    ]
    rej_job = rejection_identity or j2
    regulator.append({'type': 'candidate_registration', 'accepted_registration': False,
                      'reason': rejection_reason, 'ready_commit_ns': origin + 66000000, 'job': rej_job})
    regulator += [{'type': 'decision', 'sequence': i + 1, 'accepted': True, 'publish_success': [True, True]}
                  for i in range(5)]
    regulator += [{'type': 'owned_applied_publication', 'sequence': i + 1} for i in range(5)]
    closed = [{'role': r, 'returncode': 0, 'group_empty': True} for r in
              ('regulator', 'fixture', 'worker', 'recorder')]
    return write_run({
        'fixture/nominal_steps.jsonl': receipts,
        'worker/source.jsonl': worker,
        'regulator/source.jsonl': regulator,
        'regulator/witness.json': {'observation_complete': True},
        'driver_events.jsonl': [],
        'recorder/bag/.keep': [{'placeholder': True}],
        'driver_result.json': {'closed_roles': closed, 't2_command_records': [
            command_record('a1', command, sha)]}})


class T2BBoundaryWorkerConsumption(unittest.TestCase):
    def run_audit(self, **kwargs):
        root = full_t2b_run(**kwargs)
        table = table_t2b()
        return audit_t2.audit_run(root, table, driver_result=json.loads((root / 'driver_result.json').read_bytes()))

    def test_positive_control_passes(self):
        result = self.run_audit()
        self.assertEqual(result['failures'], [], result['failures'])
        self.assertTrue(result['passed'], result)

    def test_82_missing_worker_rejected(self):
        result = self.run_audit(worker_present=False)
        self.assertFalse(result['passed'])
        self.assertTrue(any('job_received for target Job' in f for f in result['failures']), result['failures'])

    def test_82_expired_disposition_rejected(self):
        result = self.run_audit(boundary_disposition='expired')
        self.assertFalse(result['passed'])
        self.assertTrue(any('disposition' in f and 'expired' in f for f in result['failures']), result['failures'])

    def test_82_native_false_rejected(self):
        result = self.run_audit(native_invoked=False)
        self.assertFalse(result['passed'])
        self.assertTrue(any('native not invoked' in f for f in result['failures']), result['failures'])

    def test_82_missing_original_job_rejected(self):
        result = self.run_audit(original_job_present=False)
        self.assertFalse(result['passed'])
        self.assertTrue(any('original Job' in f and 'not found' in f for f in result['failures']), result['failures'])

    def test_82_foreign_identity_rejected(self):
        foreign = make_job(2, 99)
        result = self.run_audit(rejection_identity=foreign)
        self.assertFalse(result['passed'])
        self.assertTrue(any('rejection Job identity differs' in f for f in result['failures']), result['failures'])

    def test_82_no_generation_advance_rejected(self):
        result = self.run_audit(task_advance=False)
        self.assertFalse(result['passed'])
        self.assertTrue(any('strictly advanced' in f for f in result['failures']), result['failures'])

    def test_82_timeliness_checked(self):
        """Rejection beyond the 150ms deadline must fail."""
        root = full_t2b_run()
        # Rewrite rejection to be past deadline
        lines = (root / 'regulator/source.jsonl').read_text().splitlines()
        new_lines = []
        for line in lines:
            row = json.loads(line)
            if row.get('type') == 'candidate_registration' and row.get('accepted_registration') is False:
                row['ready_commit_ns'] = 1000000000 + 200000000  # > deadline
            new_lines.append(json.dumps(row))
        (root / 'regulator/source.jsonl').write_text('\n'.join(new_lines) + '\n')
        result = audit_t2.audit_run(root, table_t2b(),
                                    driver_result=json.loads((root / 'driver_result.json').read_bytes()))
        self.assertFalse(result['passed'])
        self.assertTrue(any('exceeds deadline' in f for f in result['failures']), result['failures'])


class T2BAuditPredicates(unittest.TestCase):
    def test_resume_no_acceptance_is_not_covered(self):
        """82: no resume acceptance should be not_covered, not true."""
        t0 = 1000000000
        trig = {'phase': 'after_grant_ms', 'job': None, 'observed_ns': 500, 'source_role': 'driver'}
        receipts = [dict(receipt('a1', t0, trig, 'x'), action='clock_hold',
                         parameters={'mode': 'silent', 'duration_ms': 500}),
                    dict(receipt('a2', t0 + 800000000, trig, 'y'), action='clock_resume',
                         parameters={'advance_ms': 0})]
        clock = [{'type': 'clock', 'receive_ns': t0 - 200000000, 'sim_ns': 1, 'schedule_generation': 1},
                 {'type': 'clock', 'receive_ns': t0 - 100000000, 'sim_ns': 2, 'schedule_generation': 1},
                 {'type': 'clock', 'receive_ns': t0 + 700000000, 'sim_ns': 3, 'schedule_generation': 2}]
        # NO resume clock row → first_after comes from resume boundary
        clock.append({'type': 'clock', 'receive_ns': t0 + 810000000, 'sim_ns': 4, 'schedule_generation': 2})
        regulator = clock + [
            {'type': 'decision', 'sequence': 1, 'accepted': False, 'publish_success': [True, True]},
            {'type': 'owned_applied_publication', 'sequence': 1}]
        closed = [{'role': r, 'returncode': 0, 'group_empty': True} for r in
                  ('regulator', 'fixture', 'worker', 'recorder')]
        root = write_run({'fixture/nominal_steps.jsonl': receipts, 'worker/source.jsonl': [],
                          'regulator/source.jsonl': regulator,
                          'regulator/witness.json': {'observation_complete': True},
                          'driver_events.jsonl': [], 'recorder/bag/.keep': [{}],
                          'driver_result.json': {'closed_roles': closed}})
        result = audit_t2.audit_run(root, table_t2a(),
                                    driver_result={'closed_roles': closed})
        self.assertEqual(str(result['checks'].get('resume_requires_new_window')), 'not_covered:no post-resume acceptance',
                         result['checks'])

    def test_silent_zero_clock_in_hold_valid(self):
        """82: legal silent hold with zero clock rows during hold should not be rejected."""
        t0 = 1000000000
        trig = {'phase': 'after_grant_ms', 'job': None, 'observed_ns': 500, 'source_role': 'driver'}
        receipts = [dict(receipt('a1', t0, trig, 'x'), action='clock_hold',
                         parameters={'mode': 'silent', 'duration_ms': 500}),
                    dict(receipt('a2', t0 + 800000000, trig, 'y'), action='clock_resume',
                         parameters={'advance_ms': 0})]
        # Last clock before hold, then first after resume (no rows during hold)
        clock = [{'type': 'clock', 'receive_ns': t0 - 1000000, 'sim_ns': 2, 'schedule_generation': 1},
                 {'type': 'clock', 'receive_ns': t0 + 810000000, 'sim_ns': 3, 'schedule_generation': 2}]
        regulator = clock + [
            {'type': 'decision', 'sequence': 1, 'accepted': False, 'publish_success': [True, True]},
            {'type': 'owned_applied_publication', 'sequence': 1}]
        closed = [{'role': r, 'returncode': 0, 'group_empty': True} for r in
                  ('regulator', 'fixture', 'worker', 'recorder')]
        root = write_run({'fixture/nominal_steps.jsonl': receipts, 'worker/source.jsonl': [],
                          'regulator/source.jsonl': regulator,
                          'regulator/witness.json': {'observation_complete': True},
                          'driver_events.jsonl': [], 'recorder/bag/.keep': [{}],
                          'driver_result.json': {'closed_roles': closed}})
        result = audit_t2.audit_run(root, table_t2a(), driver_result={'closed_roles': closed})
        self.assertTrue(result['checks'].get('silent_exceeds_receipt_stale'),
                        'legal silent hold wrongly rejected: %s' % result['failures'])


class CommandBytesSHA(unittest.TestCase):
    def test_sha_recomputed_from_fixed_bytes(self):
        table = table_t2b()
        trig = {'phase': 'job_received', 'job': make_job(), 'observed_ns': 1000, 'source_role': 'worker'}
        cmd = {'schema': t2.COMMAND_SCHEMA, 'run_id': 'G1', 'contract_sha256': V4,
               'action_id': 'a1', 'sequence': 1, 'trigger': trig}
        good_sha = t2.digest(t2.encoded_json(cmd))
        records = [command_record('a1', cmd, good_sha)]
        receipts = [receipt('a1', 2000, trig, 'wrong-sha')]
        with self.assertRaises(AssertionError) as ctx:
            t2.check_receipts(table, receipts, [], records)
        self.assertIn('recomputed', str(ctx.exception))

    def test_trigger_binding_checked(self):
        table = table_t2b()
        trig = {'phase': 'job_received', 'job': make_job(), 'observed_ns': 1000, 'source_role': 'worker'}
        cmd = {'schema': t2.COMMAND_SCHEMA, 'run_id': 'G1', 'contract_sha256': V4,
               'action_id': 'a1', 'sequence': 1, 'trigger': trig}
        records = [command_record('a1', cmd, t2.digest(t2.encoded_json(cmd)))]
        bad_trig = dict(trig, source_role='driver')  # wrong role
        receipts = [receipt('a1', 2000, bad_trig, records[0]['command_sha256'])]
        with self.assertRaises(AssertionError) as ctx:
            t2.check_receipts(table, receipts, [], records)
        self.assertIn('source_role differs', str(ctx.exception))


class T2CTiming(unittest.TestCase):
    def test_activation_not_ready_for_accepted_after(self):
        """82: activation time (not ready) determines post-request acceptance."""
        table = table_t2c()
        trig = {'phase': 'ready_window', 'job': make_job(), 'observed_ns': 1000, 'source_role': 'regulator'}
        cmd = {'schema': t2.COMMAND_SCHEMA, 'run_id': 'G1', 'contract_sha256': V3,
               'action_id': 'a1', 'sequence': 1, 'trigger': trig}
        sha = t2.digest(t2.encoded_json(cmd))
        driver = [{'type': 't2_driver_action_executed', 'checked_ns': 2000, 'action_id': 'a1',
                   'command': cmd, 'executed_ns': 2000, 'command_sha256': sha,
                   'trigger': trig, 'executor': 'driver'}]
        regs = [{'type': 'candidate_registration', 'accepted_registration': True, 'ready_commit_ns': 1000,
                 'job': make_job()}]
        # ready=1000 < request=2000 BUT activation=4000 > request → must reject
        decisions = [{'type': 'decision', 'sequence': 1, 'accepted': True, 'job_id': 2,
                      'ready_commit_ns': 1500, 'activation_commit_ns': 4000, 'publish_success': [False, False]},
                     {'type': 'decision', 'sequence': 2, 'accepted': False, 'job_id': 2,
                      'activation_commit_ns': 5000, 'publish_success': [False, False]},
                     {'type': 'decision', 'sequence': 3, 'accepted': False, 'reason': 'shutdown',
                      'tick_start_ns': 2500, 'end_ns': 2800, 'publish_success': [False, False]}]
        applied = [{'type': 'owned_applied_publication', 'sequence': 1}]
        root = write_run({'fixture/nominal_steps.jsonl': [], 'driver_events.jsonl': driver,
                          'regulator/source.jsonl': regs + decisions + applied,
                          'regulator/witness.json': {'observation_complete': True},
                          'worker/source.jsonl': [], 'recorder/bag/.keep': [{}],
                          'driver_result.json': {'closed_roles': [
                              {'role': r, 'returncode': 0, 'group_empty': True} for r in
                              ('regulator', 'fixture', 'worker', 'recorder')],
                              't2_command_records': [command_record('a1', cmd, sha)]}})
        result = audit_t2.audit_run(root, table)
        self.assertFalse(result['passed'])
        self.assertTrue(any('activation_commit > request' in f for f in result['failures']), result['failures'])


class StoredGateAndClosure(unittest.TestCase):
    def test_synthetic_no_stored_rejected(self):
        table = table_t2c()
        root = full_t2b_run()  # T2B run has Stored
        # Create a copy without Stored
        root2 = Path(tempfile.mkdtemp())
        for f in root.rglob('*'):
            if f.is_file() and 'recorder' not in f.parts:
                dest = root2 / f.relative_to(root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(f.read_bytes())
        result = audit_t2.audit_run(root2, table_t2b(),
                                    driver_result=json.loads((root2 / 'driver_result.json').read_bytes()))
        self.assertFalse(result['passed'])
        self.assertTrue(any('Stored' in f for f in result['failures']))

    def test_group_not_empty_rejected(self):
        root = full_t2b_run()
        dr = json.loads((root / 'driver_result.json').read_bytes())
        dr['closed_roles'][0]['group_empty'] = False
        result = audit_t2.audit_run(root, table_t2b(), driver_result=dr)
        self.assertFalse(result['passed'])
        self.assertTrue(any('group not empty' in f for f in result['failures']))


class RealT2A14Regression(unittest.TestCase):
    def test_new_audit_rejects_t2a14(self):
        if not T2A_14_RUN.is_dir():
            self.skipTest('preserved run not present')
        table = json.loads(Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/T2A_table_v11.json').read_bytes())
        table['run_id'] = 'T2-T2A-14'
        result = audit_t2.audit_run(T2A_14_RUN, table,
                                    registration={'expected_diagnostics': {'regulator_returncode': 0,
                                                                            'witness_observation_complete': True}})
        self.assertFalse(result['passed'])


class ModuleSyntax(unittest.TestCase):
    def test_g1_modules_import(self):
        import importlib
        importlib.import_module('t2_action_contract')
        importlib.import_module('audit_t2')
        import py_compile
        py_compile.compile(str(HERE / 't2_author_g1/t2_scenario_driver_v1.py'), doraise=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
