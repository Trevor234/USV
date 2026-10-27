#!/usr/bin/env python3
"""Offline positive/negative validation of the frozen T2 interface (S2, batch 71).

No ROS initialisation. Covers: table admission (wrong case/hash/order/
multi-action/timeout/candidate forgery), command admission (duplicates,
order), receipt accounting (missing/duplicate/wrong order), normal-scope
rejection, the unrelaxed budgets, the W1-W4 preflight regression and the
audit clause consumption on synthetic streams."""
import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 't2_author'))
import t2_action_contract as t2
from w2_runtime_contract import require, registration_preflight_t2

V3 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json')
CONTEXT = {'run_id': 'T2-OFFLINE', 'case': None, 'contract_sha256': t2.V3_CONTRACT_SHA}


def table_t2a():
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'T2-OFFLINE', 'case': 'T2A-clock-freeze',
            'contract_sha256': t2.V3_CONTRACT_SHA,
            'actions': [
                {'id': 'a1', 'action': 'clock_hold', 'parameters': {'mode': 'silent', 'duration_ms': 600},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 100}},
                {'id': 'a2', 'action': 'clock_resume', 'parameters': {'advance_ms': 100},
                 'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 0}}],
            'clauses': {'receipt_stale_ns': 100000000, 'pause_confirm_ns': 400000000,
                        'same_stamp_keeps_receipt_fresh': True, 'silent_exceeds_receipt_stale': True,
                        'old_candidate_must_not_revive': True, 'resume_requires_new_window': True}}


def table_t2b(phase='solve_active'):
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'T2-OFFLINE', 'case': 'T2B-inflight-clear-replace',
            'contract_sha256': t2.V3_CONTRACT_SHA,
            'actions': [
                {'id': 'a1', 'action': 'path_replace', 'parameters': {'points': 101, 'speed_m_s': .05},
                 'trigger': {'phase': phase, 'job_id': 2, 'delay_ms': 0}}],
            'clauses': {'job_deadline_ns_after_origin': 150000000, 'deadline_must_not_extend': True,
                        'missed_window_is_registered_failure': True,
                        'stale_result_reject_reasons': ['version_mismatch', 'job_echo_mismatch'],
                        'expiry_or_worker_terminal_is_not_task_rejection': True}}


def table_t2c():
    return {'schema': 'M4-t2-action-table-v1', 'run_id': 'T2-OFFLINE', 'case': 'T2C-driver-shutdown-interleave',
            'contract_sha256': t2.V3_CONTRACT_SHA,
            'actions': [
                {'id': 'a1', 'action': 'driver_shutdown_request', 'parameters': {'reason': 'T2C registered stimulus'},
                 'trigger': {'phase': 'ready_window', 'job_id': 2, 'delay_ms': 0}}],
            'clauses': {'ordering': 'ready_commit<request<=stopping_observed<=activation_guard',
                        'stop_must_precede_activation_guard': True, 'guard_rejects_target': True,
                        'full_exit_and_storage_required': True}}


def valid(table):
    ctx = dict(CONTEXT, case=table['case'])
    return t2.validate_table(copy.deepcopy(table), ctx)


def rejects(table, fragment=None):
    try:
        valid(table)
    except AssertionError as error:
        if fragment:
            assert fragment in str(error), str(error)
        return str(error)
    raise AssertionError('table was accepted but should be rejected')


def command(table, action_id, sequence, trigger):
    return {'schema': 'M4-t2-action-command-v1', 'run_id': table['run_id'],
            'contract_sha256': table['contract_sha256'], 'action_id': action_id,
            'sequence': sequence, 'trigger': trigger}


TRIGGER_JOB = {'phase': 'solve_active', 'job': {'job_id': 2, 'task_generation': 3}, 'observed_ns': 1000, 'source_role': 'worker'}
TRIGGER_READY = {'phase': 'ready_window', 'job': {'job_id': 2, 'task_generation': 3}, 'observed_ns': 1000, 'source_role': 'regulator'}


class TableAdmission(unittest.TestCase):
    def test_three_families_accepted(self):
        for table in (table_t2a(), table_t2b(), table_t2b('ready_window'), table_t2c()):
            self.assertTrue(valid(table))

    def test_unknown_case_rejected(self):
        bad = table_t2a()
        bad['case'] = 'T2D-not-registered'
        rejects(bad, 'unknown T2 scenario family')

    def test_wrong_contract_sha_rejected(self):
        bad = table_t2a()
        bad['contract_sha256'] = '0' * 64
        rejects(bad, 'frozen v3 contract')

    def test_wrong_run_binding_rejected(self):
        bad = table_t2a()
        bad['run_id'] = 'other-run'
        rejects(bad, 'table run binding')

    def test_candidate_forgery_rejected(self):
        bad = table_t2b()
        bad['actions'][0]['action'] = 'candidate_submit'
        rejects(bad, 'candidate forgery')

    def test_unknown_action_rejected(self):
        bad = table_t2b()
        bad['actions'][0]['action'] = 'clock_pause_hard'
        rejects(bad, 'unknown action')

    def test_family_action_separation(self):
        bad = table_t2b()
        bad['actions'][0]['action'] = 'clock_hold'
        rejects(bad, 'not admitted for')

    def test_job_received_trigger_rejected_for_t2b(self):
        rejects(table_t2b('job_received'), 'job_received proves queued only')

    def test_after_grant_with_job_rejected(self):
        bad = table_t2a()
        bad['actions'][0]['trigger']['job_id'] = 2
        rejects(bad, 'carries no Job binding')

    def test_resume_without_hold_rejected(self):
        bad = table_t2a()
        resume = dict(bad['actions'][1], id='a1')
        bad['actions'] = [resume]
        rejects(bad, 'clock_resume must follow a clock_hold')

    def test_duplicate_action_id_rejected(self):
        # Position-checked ids cannot duplicate; any duplicate-named table is
        # rejected by the id-order gate, which subsumes the duplicate guard.
        bad = table_t2a()
        bad['actions'][1]['id'] = 'a1'
        rejects(bad)

    def test_out_of_order_ids_rejected(self):
        bad = table_t2a()
        bad['actions'][0]['id'] = 'a2'
        rejects(bad, 'action ids are a1..aN')

    def test_multi_action_population_bounded(self):
        bad = table_t2a()
        row = copy.deepcopy(bad['actions'][0])
        row['id'] = 'a3'
        bad['actions'].insert(1, row)
        rejects(bad)  # two holds then resume is fine, but re-check ids
        bad['actions'] = bad['actions'] + [{**row, 'id': 'a%d' % i} for i in range(3, 8)]
        rejects(bad, 'finite action population')

    def test_shutdown_must_be_last(self):
        bad = table_t2c()
        bad['actions'].append({'id': 'a2', 'action': 'clock_hold',
                               'parameters': {'mode': 'silent', 'duration_ms': 100},
                               'trigger': {'phase': 'after_grant_ms', 'job_id': 0, 'delay_ms': 0}})
        rejects(bad, 'not admitted for')  # clock_hold is not a T2C action at all

    def test_timeout_bound_enforced(self):
        bad = table_t2a()
        bad['actions'][0]['parameters']['duration_ms'] = 5000
        rejects(bad, 'clock_hold duration outside finite bound')

    def test_clause_shape_enforced(self):
        bad = table_t2a()
        bad['clauses']['pause_confirm_ns'] = 100000000
        rejects(bad, 'pause confirm bound is 400 ms')
        bad = table_t2b()
        bad['clauses']['job_deadline_ns_after_origin'] = 200000000
        rejects(bad, 'Job deadline stays 150 ms')
        bad = table_t2c()
        bad['clauses']['ordering'] = 'request<ready'
        rejects(bad, 'T2C ordering clause is fixed')


class CommandAdmission(unittest.TestCase):
    def test_valid_command_sequence(self):
        table = valid(table_t2a())
        executed = []
        first = command(table, 'a1', 1, {'phase': 'after_grant_ms', 'job': None,
                                         'observed_ns': 500, 'source_role': 'driver'})
        t2.validate_command(first, table, executed)
        executed.append(first)
        second = command(table, 'a2', 2, {'phase': 'after_grant_ms', 'job': None,
                                          'observed_ns': 600, 'source_role': 'driver'})
        t2.validate_command(second, table, [c['action_id'] for c in executed])

    def test_duplicate_command_rejected(self):
        table = valid(table_t2a())
        executed = ['a1']
        dup = command(table, 'a1', 1, {'phase': 'after_grant_ms', 'job': None,
                                       'observed_ns': 500, 'source_role': 'driver'})
        with self.assertRaises(AssertionError):
            t2.validate_command(dup, table, executed)

    def test_out_of_order_command_rejected(self):
        table = valid(table_t2a())
        with self.assertRaises(AssertionError):
            t2.validate_command(command(table, 'a2', 1, {'phase': 'after_grant_ms', 'job': None,
                                                         'observed_ns': 500, 'source_role': 'driver'}),
                                table, [])

    def test_foreign_action_and_phase_rejected(self):
        table = valid(table_t2b())
        with self.assertRaises(AssertionError):
            t2.validate_command(command(table, 'a9', 1, TRIGGER_JOB), table, [])
        wrong_phase = dict(TRIGGER_JOB, phase='ready_window')
        with self.assertRaises(AssertionError):
            t2.validate_command(command(table, 'a1', 1, wrong_phase), table, [])
        wrong_job = dict(TRIGGER_JOB, job={'job_id': 9})
        with self.assertRaises(AssertionError):
            t2.validate_command(command(table, 'a1', 1, wrong_job), table, [])


def receipt(action_id, executed_ns, trigger, command_sha='c0ffee'):
    return {'type': 't2_action_executed', 'action_id': action_id, 'command_sha256': command_sha,
            'executed_ns': executed_ns, 'trigger': trigger}


class ReceiptAccounting(unittest.TestCase):
    def test_complete_ordered_receipts_accepted(self):
        table = valid(table_t2a())
        receipts = [receipt('a1', 1000, {'observed_ns': 500}), receipt('a2', 2000, {'observed_ns': 1500})]
        out = t2.check_receipts(table, receipts, [])
        self.assertTrue(out['receipts_complete'])
        self.assertTrue(out['regulator_rows_separate_stream'])

    def test_missing_receipt_detected(self):
        table = valid(table_t2a())
        with self.assertRaises(AssertionError):
            t2.check_receipts(table, [receipt('a1', 1000, {'observed_ns': 500})], [])

    def test_duplicate_receipt_detected(self):
        table = valid(table_t2a())
        dup = [receipt('a1', 1000, {'observed_ns': 500}), receipt('a1', 1100, {'observed_ns': 500})]
        with self.assertRaises(AssertionError):
            t2.check_receipts(table, dup + [receipt('a2', 2000, {'observed_ns': 1500})], [])

    def test_non_monotonic_receipts_detected(self):
        table = valid(table_t2a())
        bad = [receipt('a1', 2000, {'observed_ns': 500}), receipt('a2', 1000, {'observed_ns': 900})]
        with self.assertRaises(AssertionError):
            t2.check_receipts(table, bad, [])

    def test_execution_before_trigger_detected(self):
        table = valid(table_t2a())
        bad = [receipt('a1', 400, {'observed_ns': 500}), receipt('a2', 2000, {'observed_ns': 1500})]
        with self.assertRaises(AssertionError):
            t2.check_receipts(table, bad, [])

    def test_flush_pad_is_not_a_receipt(self):
        table = valid(table_t2a())
        with self.assertRaises(AssertionError):
            t2.check_receipts(table, [{'type': 't1_component_flush_pad', 'action_id': 'a1'}], [])


class NormalScopeAndBudgets(unittest.TestCase):
    def test_normal_scope_rejects_t2_capability(self):
        for key in ('action_table', 'action_table_sha256', 't2_case'):
            reg = {'schema': 'M4-owned-diagnostic-run-v1', 'case': 'W1-work-stall-watchdog'}
            reg[key] = 'x'
            with self.assertRaises(AssertionError):
                t2.require_normal_scope_unarmed(reg)

    def test_budgets_must_stay_frozen(self):
        config = json.loads(V3.read_bytes())
        t2.verify_budgets_unchanged(config)
        for key, value in [('deadline_ns', 200000000), ('hold_ns', 700000000),
                           ('active_watchdog_ns', 2000000000), ('clock_pause_confirm_ns', 300000000)]:
            relaxed = dict(config, **{key: value})
            with self.assertRaises(AssertionError):
                t2.verify_budgets_unchanged(relaxed)

    def test_w_registration_without_t2_keys_still_preflight_clean(self):
        """The W1-W4 entry path must not regress: the guard only fires on T2 keys."""
        reg = {'schema': 'M4-owned-diagnostic-run-v1', 'case': 'W1-work-stall-watchdog'}
        t2.require_normal_scope_unarmed(reg)

    def test_fixture_parameter_assembly(self):
        import tempfile
        table = table_t2b()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'table.json'
            path.write_text(json.dumps(table))
            reg = {'schema': t2.REGISTRATION_SCHEMA, 'run_id': 'T2-OFFLINE', 'case': table['case'],
                   'contract_sha256': t2.V3_CONTRACT_SHA, 'action_table_sha256': t2.pin(path)['sha256']}
            params = t2.fixture_action_parameters(reg, Path(tmp) / 'commands', path)
            self.assertEqual(params['t2_case'], table['case'])
            self.assertEqual(set(params), {'t2_case', 't2_action_table_file',
                                           't2_action_table_sha256', 't2_command_dir'})
            tampered = dict(reg, action_table_sha256='0' * 64)
            with self.assertRaises(AssertionError):
                t2.fixture_action_parameters(tampered, Path(tmp) / 'commands', path)


class PreflightT2Offline(unittest.TestCase):
    """registration_preflight_t2's schema/contract/case/table gates, offline."""

    def make_reg(self):
        return {'schema': t2.REGISTRATION_SCHEMA, 'scope': t2.ORDINARY_SCOPE,
                'case': 'T2B-inflight-clear-replace', 'run_id': 'T2-PREFLIGHT',
                'production_physical_release_enabled': False, 'fault_injection_enabled': False,
                'domain_id': 120, 'max_seconds': 45, 'automatic_retries': 0,
                'contract': str(V3), 'contract_sha256': t2.V3_CONTRACT_SHA,
                'action_table': None, 'action_table_sha256': None, 'output': None,
                'registry': None, 'registry_sha256': None, 'topics': None, 'topics_sha256': None,
                'audit_tool': None}

    def test_wrong_schema_rejected(self):
        reg = self.make_reg()
        reg['schema'] = 'M4-owned-diagnostic-run-v1'
        with self.assertRaises(AssertionError):
            registration_preflight_t2(reg, '/nonexistent/driver')

    def test_diagnostic_scope_rejected(self):
        reg = self.make_reg()
        reg['scope'] = 'M4_owned_diagnostic_worker_only_v1'
        with self.assertRaises(AssertionError):
            registration_preflight_t2(reg, '/nonexistent/driver')

    def test_fault_injection_must_stay_off(self):
        reg = self.make_reg()
        reg['fault_injection_enabled'] = True
        with self.assertRaises(AssertionError):
            registration_preflight_t2(reg, '/nonexistent/driver')

    def test_v4_contract_rejected(self):
        reg = self.make_reg()
        reg['contract'] = '/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json'
        with self.assertRaises(AssertionError):
            registration_preflight_t2(reg, '/nonexistent/driver')


class AuditClauses(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(HERE / 't2_author'))
        import audit_t2
        self.audit = audit_t2

    def run_audit(self, table, fixture_rows=(), driver_rows=(), regulator_rows=()):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'fixture').mkdir()
            (root / 'regulator').mkdir()
            (root / 'fixture/nominal_steps.jsonl').write_text(
                '\n'.join(json.dumps(r) for r in fixture_rows) + '\n')
            (root / 'driver_events.jsonl').write_text(
                '\n'.join(json.dumps(r) for r in driver_rows) + '\n')
            (root / 'regulator/source.jsonl').write_text(
                '\n'.join(json.dumps(r) for r in regulator_rows) + '\n')
            return self.audit.audit_run(root, table)

    def test_t2a_clauses_consumed(self):
        table = table_t2a()
        trigger = {'observed_ns': 500, 'phase': 'after_grant_ms', 'job': None, 'source_role': 'driver'}
        fixture = [dict(receipt('a1', 1000, trigger, 'x'),
                        parameters={'mode': 'silent', 'duration_ms': 600}, action='clock_hold'),
                   dict(receipt('a2', 1000 + 700 * 1000000, trigger, 'y'),
                        action='clock_resume')]
        regulator = [{'type': 'path_version', 'processed_ns': 5000, 'task_generation': 1}]
        checks = self.run_audit(table, fixture_rows=fixture, regulator_rows=regulator)
        self.assertTrue(checks['receipt_accounting'])
        self.assertTrue(checks['hold_receipt_present'])
        self.assertTrue(checks['hold_minimum_respected'])
        self.assertTrue(checks['silent_hold_exceeds_receipt_stale'])
        self.assertTrue(checks['regulator_stream_observed_after_hold'])

    def test_t2b_clauses_consumed(self):
        table = table_t2b()
        fixture = [dict(receipt('a1', 2000, TRIGGER_JOB), parameters={'points': 101, 'speed_m_s': .05},
                        action='path_replace')]
        regulator = [{'type': 'path_version', 'processed_ns': 3000, 'task_generation': 4},
                     {'type': 'candidate_registration', 'accepted_registration': False,
                      'reason': 'version_mismatch', 'ready_commit_ns': 3500, 'job': {'job_id': 2}}]
        checks = self.run_audit(table, fixture_rows=fixture, regulator_rows=regulator)
        self.assertTrue(checks['receipt_accounting'])
        self.assertTrue(checks['regulator_task_version_after_receipt'])
        self.assertTrue(checks['stale_result_rejected_with_registered_reason'])
        self.assertTrue(checks['trigger_phase_is_inflight_or_ready'])

    def test_t2c_clauses_consumed(self):
        table = table_t2c()
        driver = [{'type': 't2_driver_action_executed', 'checked_ns': 2000, 'action_id': 'a1',
                   'command': {'trigger': TRIGGER_READY}, 'executed_ns': 2000}]
        regulator = [{'type': 'decision', 'job_id': 2, 'accepted': False,
                      'ready_commit_ns': 1500, 'activation_commit_ns': 1600, 'reason': 'shutdown'},
                     {'type': 'owned_reception_closed', 'closed_ns': 2500}]
        checks = self.run_audit(table, driver_rows=driver, regulator_rows=regulator)
        self.assertTrue(checks['receipt_accounting'])
        self.assertTrue(checks['shutdown_receipt_present'])
        self.assertTrue(checks['ready_before_request'])
        self.assertTrue(checks['stopping_observed'])
        self.assertTrue(checks['ordering_clause_consumed'])

    def test_missing_evidence_fails_not_crashes(self):
        checks = self.run_audit(table_t2c())
        self.assertFalse(checks['receipt_accounting'])
        self.assertFalse(checks.get('shutdown_receipt_present', False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
