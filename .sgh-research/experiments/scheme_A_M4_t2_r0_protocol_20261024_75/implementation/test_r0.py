#!/usr/bin/env python3
"""R0 offline validation (batch 75): named positive/negative suites.

Every retained 74th-batch counterexample must be rejected by its intended
named assertion; positive controls must genuinely pass. No ROS."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 't2_author_r0'))
import t2_action_contract as t2
import audit_t2

T2A_14_RUN = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/runs/T2A_14')
T2A_14_TABLE = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/T2A_table_v11.json')

V3 = t2.V3_CONTRACT_SHA


def table_t2a():
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'R0', 'case': 'T2A-clock-freeze',
            'contract_sha256': V3,
            'actions': [
                {'id': 'a1', 'action': 'clock_hold', 'parameters': {'mode': 'silent', 'duration_ms': 500},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 100}},
                {'id': 'a2', 'action': 'clock_resume', 'parameters': {'advance_ms': 0},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 800}}],
            'clauses': {'receipt_stale_ns': 100000000, 'pause_confirm_ns': 400000000,
                        'same_stamp_keeps_receipt_fresh': True, 'silent_exceeds_receipt_stale': True,
                        'old_candidate_must_not_revive': True, 'resume_requires_new_window': True}}


def table_t2c():
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'R0', 'case': 'T2C-driver-shutdown-interleave',
            'contract_sha256': V3,
            'actions': [{'id': 'a1', 'action': 'driver_shutdown_request',
                         'parameters': {'reason': 'R0 test'}, 'trigger': {'phase': 'ready_window', 'job_id': 2, 'delay_ms': 0}}],
            'clauses': {'ordering': 'ready_commit<request<=stopping_observed<=activation_guard',
                        'stop_must_precede_activation_guard': True, 'guard_rejects_target': True,
                        'full_exit_and_storage_required': True}}


def receipt(action_id, executed_ns, trigger, command_sha='c0', **extra):
    row = {'type': 't2_action_executed', 'action_id': action_id, 'command_sha256': command_sha,
           'executed_ns': executed_ns, 'trigger': trigger}
    row.update(extra)
    return row


def command_record(action_id, command, sha):
    return {'action_id': action_id, 'sequence': command['sequence'], 'command_sha256': sha, 'command': command}


def write_run(rows_by_file):
    root = Path(tempfile.mkdtemp())
    for rel, rows in rows_by_file.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    return root


class EvidenceConstructor(unittest.TestCase):
    def test_real_t2a14_job_received_row_builds_complete_evidence(self):
        """The nested job.job_id defect: the REAL row must yield full evidence."""
        rows = [json.loads(l) for l in (T2A_14_RUN / 'worker/source.jsonl').read_text().splitlines() if l.strip()]
        jr = next(r for r in rows if r.get('type') == 'job_received')
        job = jr['job']
        self.assertEqual(job['job_id'], 1)
        ev = t2.make_evidence('job_received', job, jr['receive_ns'], 'worker')
        self.assertEqual(set(ev), {'phase', 'job', 'observed_ns', 'source_role'})
        self.assertEqual(ev['observed_ns'], jr['receive_ns'])

    def test_phase_role_binding_enforced(self):
        with self.assertRaises(AssertionError):
            t2.make_evidence('job_received', {}, 5, 'driver')
        with self.assertRaises(AssertionError):
            t2.make_evidence('ready_window', {}, 5, 'worker')
        with self.assertRaises(AssertionError):
            t2.make_evidence('ready_window', {}, 0, 'regulator')  # no real event time


class ReceiptAccounting(unittest.TestCase):
    def commands(self, table, trigger1, trigger2=None):
        c1 = {'schema': t2.COMMAND_SCHEMA, 'run_id': table['run_id'], 'contract_sha256': V3,
              'action_id': 'a1', 'sequence': 1, 'trigger': trigger1}
        t2.validate_command(c1, table, [])
        records = [command_record('a1', c1, t2.digest(t2.encoded_json(c1)))]
        if trigger2:
            c2 = {'schema': t2.COMMAND_SCHEMA, 'run_id': table['run_id'], 'contract_sha256': V3,
                  'action_id': 'a2', 'sequence': 2, 'trigger': trigger2}
            t2.validate_command(c2, table, ['a1'])
            records.append(command_record('a2', c2, t2.digest(t2.encoded_json(c2))))
        return records

    def test_foreign_action_receipt_rejected(self):
        table = table_t2a()
        trig = {'phase': 'after_grant_ms', 'job': None, 'observed_ns': 5, 'source_role': 'driver'}
        receipts = [receipt('a1', 10, trig, 'x'), receipt('a2', 20, trig, 'y'), receipt('a9', 30, trig, 'z')]
        with self.assertRaises(AssertionError) as ctx:
            t2.check_receipts(table, receipts, [], None)
        self.assertIn('outside the frozen table', str(ctx.exception))

    def test_receipt_must_bind_exact_command_bytes(self):
        table = table_t2a()
        trig = {'phase': 'after_grant_ms', 'job': None, 'observed_ns': 5, 'source_role': 'driver'}
        records = self.commands(table, trig, trig)
        receipts = [receipt('a1', 10, trig, 'wrong-sha'), receipt('a2', 20, trig, records[1]['command_sha256'])]
        with self.assertRaises(AssertionError) as ctx:
            t2.check_receipts(table, receipts, [], records)
        self.assertIn('exact commanded bytes', str(ctx.exception))

    def test_command_set_must_equal_table(self):
        table = table_t2a()
        trig = {'phase': 'after_grant_ms', 'job': None, 'observed_ns': 5, 'source_role': 'driver'}
        records = self.commands(table, trig)  # only a1 commanded
        receipts = [receipt('a1', 10, trig, records[0]['command_sha256'])]
        with self.assertRaises(AssertionError) as ctx:
            t2.check_receipts(table, receipts, [], records)
        self.assertIn('command set must equal', str(ctx.exception))

    def test_incomplete_evidence_trigger_rejected_by_command_admission(self):
        """The 74 finding: B/C caches produced 3-field triggers; now rejected."""
        table = table_t2c()
        bad = {'phase': 'ready_window', 'job': {'job_id': 2}, 'observed_ns': 7}  # no source_role
        command = {'schema': t2.COMMAND_SCHEMA, 'run_id': table['run_id'], 'contract_sha256': V3,
                   'action_id': 'a1', 'sequence': 1, 'trigger': bad}
        with self.assertRaises(AssertionError) as ctx:
            t2.validate_command(command, table, [])
        self.assertIn('trigger evidence exact fields', str(ctx.exception))


def t2a_streams(stale_gap_ns=600000000, applied_count=13):
    """A complete positive T2A stream set with REAL evidence semantics."""
    t0 = 1000000000
    trig = {'phase': 'after_grant_ms', 'job': None, 'observed_ns': 500, 'source_role': 'driver'}
    receipts = [dict(receipt('a1', t0, trig, 'sha-a1'),
                     action='clock_hold', parameters={'mode': 'silent', 'duration_ms': 500}),
                dict(receipt('a2', t0 + 800000000, trig, 'sha-a2'), action='clock_resume',
                     parameters={'advance_ms': 0})]
    fixture = receipts
    clock = [{'type': 'clock', 'receive_ns': t0 - 200000000, 'sim_ns': 1, 'schedule_generation': 1},
             {'type': 'clock', 'receive_ns': t0 - 100000000, 'sim_ns': 2, 'schedule_generation': 1},
             {'type': 'clock', 'receive_ns': t0 + stale_gap_ns, 'sim_ns': 3, 'schedule_generation': 1},
             {'type': 'clock', 'receive_ns': t0 + stale_gap_ns + 20000000, 'sim_ns': 4, 'schedule_generation': 1},
             {'type': 'clock', 'receive_ns': t0 + 810000000, 'sim_ns': 5, 'schedule_generation': 2}]
    regs = [{'type': 'candidate_registration', 'accepted_registration': True, 'ready_commit_ns': t0 - 50000000,
             'job': {'job_id': 1, 'task_generation': 1, 'schedule_generation': 1}}]
    decisions = [{'type': 'decision', 'sequence': i + 1, 'accepted': i == 0, 'publish_success': [True, True] if i < applied_count else [False, False]}
                 for i in range(applied_count)]
    applied = [{'type': 'owned_applied_publication', 'sequence': i + 1} for i in range(applied_count)]
    regulator = clock + regs + decisions + applied
    witness = {'observation_complete': True}
    return fixture, regulator, witness


def t2a_run_dir(fixture, regulator, witness):
    return write_run({'fixture/nominal_steps.jsonl': fixture,
                      'regulator/source.jsonl': regulator,
                      'regulator/witness.json': [witness],
                      'driver_events.jsonl': []})


def driver_result_ok(table, receipts):
    trig = receipts[0]['trigger']
    records = []
    for index, row in enumerate(receipts, 1):
        command = {'schema': t2.COMMAND_SCHEMA, 'run_id': table['run_id'], 'contract_sha256': V3,
                   'action_id': row['action_id'], 'sequence': index, 'trigger': trig}
        records.append(command_record(row['action_id'], command, row['command_sha256']))
    closed = [{'role': role, 'returncode': 0, 'group_empty': True} for role in
              ('regulator', 'fixture', 'worker', 'recorder')]
    return {'closed_roles': closed, 't2_command_records': records}


class AuditFailClosed(unittest.TestCase):
    def test_t2a_positive_control_passes(self):
        table = table_t2a()
        fixture, regulator, witness = t2a_streams()
        root = t2a_run_dir(fixture, regulator, witness)
        result = audit_t2.audit_run(root, table, driver_result=driver_result_ok(table, fixture))
        self.assertEqual(result['failures'], [], result['failures'])
        self.assertTrue(result['passed'], result)

    def test_74_counterexample_sparse_stream_rejected(self):
        """Two real receipts + one arbitrary row only: must fail, not pass."""
        table = table_t2a()
        trig = {'phase': 'after_grant_ms', 'job': None, 'observed_ns': 500, 'source_role': 'driver'}
        fixture = [dict(receipt('a1', 1000, trig), action='clock_hold',
                         parameters={'mode': 'silent', 'duration_ms': 500}),
                   dict(receipt('a2', 800000000, trig), action='clock_resume', parameters={'advance_ms': 0})]
        root = t2a_run_dir(fixture, [{'type': 'arbitrary_row', 'processed_ns': 5}], {'observation_complete': True})
        result = audit_t2.audit_run(root, table, driver_result=driver_result_ok(table, fixture))
        self.assertFalse(result['passed'])
        self.assertTrue(any('Applied' in f or 'stale' in f or 'witness' in f or 'schedule' in f
                            for f in result['failures']), result['failures'])

    def test_74_counterexample_wrong_receipt_action_mode_duration_rejected(self):
        table = table_t2a()
        fixture, regulator, witness = t2a_streams()
        fixture = [dict(fixture[0], action='path_clear'),
                   dict(fixture[1], parameters={'advance_ms': 999})]
        root = t2a_run_dir(fixture, regulator, witness)
        result = audit_t2.audit_run(root, table, driver_result=driver_result_ok(table, fixture))
        self.assertFalse(result['passed'])
        self.assertTrue(any('differs from table' in f for f in result['failures']), result['failures'])

    def test_missing_files_rejected_not_crash(self):
        root = write_run({'fixture/nominal_steps.jsonl': []})
        result = audit_t2.audit_run(root, table_t2a())
        self.assertFalse(result['passed'])
        self.assertTrue(any('missing' in f for f in result['failures']))

    def test_corrupt_json_rejected(self):
        root = Path(tempfile.mkdtemp())
        (root / 'fixture').mkdir(parents=True)
        (root / 'fixture/nominal_steps.jsonl').write_text('{"type": broken\n')
        (root / 'regulator').mkdir()
        (root / 'regulator/source.jsonl').write_text('')
        (root / 'driver_events.jsonl').write_text('')
        result = audit_t2.audit_run(root, table_t2a())
        self.assertFalse(result['passed'])
        self.assertTrue(any('corrupt' in f for f in result['failures']))

    def test_witness_mismatch_with_declaration_rejected(self):
        """Declared healthy ending but the run shows observation incomplete."""
        table = table_t2a()
        fixture, regulator, _ = t2a_streams()
        root = t2a_run_dir(fixture, regulator, {'observation_complete': False})
        registration = {'expected_diagnostics': {'regulator_returncode': 0,
                                                 'witness_observation_complete': True}}
        result = audit_t2.audit_run(root, table, registration=registration,
                                    driver_result=driver_result_ok(table, fixture))
        self.assertFalse(result['passed'])
        self.assertTrue(any('witness observation_complete' in f for f in result['failures']))

    def test_declared_diagnostic_ending_accepted_only_when_exact(self):
        table = table_t2a()
        fixture, regulator, _ = t2a_streams()
        root = t2a_run_dir(fixture, regulator, {'observation_complete': False})
        result = driver_result_ok(table, fixture)
        result['closed_roles'][0]['returncode'] = 3
        registration = {'expected_diagnostics': {'regulator_returncode': 3,
                                                 'witness_observation_complete': False}}
        outcome = audit_t2.audit_run(root, table, registration=registration, driver_result=result)
        self.assertTrue(outcome['passed'], outcome)


class AuditT2CCounterexamples(unittest.TestCase):
    def streams(self, guard_ns, accepted_after=False, guard_present=True, order_guard_before_request=False):
        trig = {'phase': 'ready_window', 'job': {'job_id': 2, 'task_generation': 1},
                'observed_ns': 1000, 'source_role': 'regulator'}
        command = {'schema': t2.COMMAND_SCHEMA, 'run_id': 'R0', 'contract_sha256': V3,
                   'action_id': 'a1', 'sequence': 1, 'trigger': trig}
        sha = t2.digest(t2.encoded_json(command))
        driver_rows = [{'type': 't2_driver_action_executed', 'checked_ns': 2000, 'action_id': 'a1',
                        'command': command, 'executed_ns': 2000, 'command_sha256': sha,
                        'trigger': trig, 'executor': 'driver'}]
        regs = [{'type': 'candidate_registration', 'accepted_registration': True, 'ready_commit_ns': 1000,
                 'job': {'job_id': 2, 'task_generation': 1}}]
        decisions = [{'type': 'decision', 'sequence': 1, 'accepted': True, 'publish_success': [False, False],
                      'job_id': 0}]
        if guard_present:
            decisions.append({'type': 'decision', 'sequence': 2, 'accepted': False, 'job_id': 2,
                              'activation_commit_ns': guard_ns if not order_guard_before_request else 1500,
                              'publish_success': [False, False]})
        decisions.append({'type': 'decision', 'sequence': 3, 'accepted': False, 'reason': 'shutdown',
                          'end_ns': 2500, 'publish_success': [False, False]})
        if accepted_after:
            decisions.append({'type': 'decision', 'sequence': 4, 'accepted': True, 'job_id': 2,
                              'ready_commit_ns': 3000, 'publish_success': [False, False]})
        applied = [{'type': 'owned_applied_publication', 'sequence': 1}]
        regulator = regs + decisions + applied
        return driver_rows, regulator

    def run_case(self, **kwargs):
        table = table_t2c()
        driver_rows, regulator = self.streams(**kwargs)
        root = write_run({'fixture/nominal_steps.jsonl': [], 'driver_events.jsonl': driver_rows,
                          'regulator/source.jsonl': regulator, 'regulator/witness.json': [{'observation_complete': True}]})
        result = {'closed_roles': [{'role': r, 'returncode': 0, 'group_empty': True} for r in
                                    ('regulator', 'fixture', 'worker', 'recorder')]}
        record = command_record('a1', driver_rows[0]['command'], driver_rows[0]['command_sha256'])
        result['t2_command_records'] = [record]
        return audit_t2.audit_run(root, table, driver_result=result)

    def test_positive_control_passes(self):
        outcome = self.run_case(guard_ns=3000)
        self.assertEqual(outcome['failures'], [], outcome['failures'])
        self.assertTrue(outcome['passed'])

    def test_74_counterexample_no_guard_rejected(self):
        outcome = self.run_case(guard_ns=3000, guard_present=False)
        self.assertFalse(outcome['passed'])
        self.assertTrue(any('activation guard' in f for f in outcome['failures']))

    def test_74_counterexample_accepted_after_request_rejected(self):
        outcome = self.run_case(guard_ns=3000, accepted_after=True)
        self.assertFalse(outcome['passed'])
        self.assertTrue(any('accepted after the stop request' in f for f in outcome['failures']))

    def test_74_counterexample_guard_before_request_rejected(self):
        outcome = self.run_case(guard_ns=3000, order_guard_before_request=True)
        self.assertFalse(outcome['passed'])
        self.assertTrue(any('violated' in f for f in outcome['failures']))


class RealT2A14Regression(unittest.TestCase):
    def test_new_audit_rejects_t2a14_full_acceptance(self):
        """The preserved failing run must be rejected by the fail-closed audit."""
        if not T2A_14_RUN.is_dir():
            self.skipTest('preserved run not present')
        table = json.loads(T2A_14_TABLE.read_bytes())
        table['run_id'] = 'T2-T2A-14'
        result = audit_t2.audit_run(T2A_14_RUN, table,
                                    registration={'expected_diagnostics': {'regulator_returncode': 0,
                                                                            'witness_observation_complete': True}})
        self.assertFalse(result['passed'])
        self.assertTrue(result['failures'])


class DriverContractModuleSyntax(unittest.TestCase):
    def test_r0_modules_import(self):
        import importlib
        for name in ('t2_action_contract', 'audit_t2'):
            importlib.import_module(name)
        import py_compile
        py_compile.compile(str(HERE / 't2_author_r0/t2_scenario_driver_v1.py'), doraise=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
