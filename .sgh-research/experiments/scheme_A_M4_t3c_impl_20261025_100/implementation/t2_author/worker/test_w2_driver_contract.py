#!/usr/bin/env python3
"""Behavioral checks of the same helpers used by Driver, no ROS graph."""
from pathlib import Path
import copy
import json
import os
import select
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from w2_runtime_contract import validate_w2, w2_result_checks, complete_w2_ticks, verify_runtime_maps, process_start, pin


def registration():
    return {'w2_release': {'job_id': 2, 'ordinal': 1, 'nonce': 20261023,
                         'wait_budget_ns': 1500000000, 'ticks_before_release': 2},
        'expected': {'w2_exit_codes': {'worker': 2}, 'w2_worker_signals': ['SIGINT'],
            'w2_isolation_reason': 'fatal_capability', 'w2_terminal_reasons': ['w2_boundary_expired'],
            'exit_codes': {'worker': 2, 'regulator': 0, 'fixture': 0, 'recorder': 0},
            'signals': {'worker': ['SIGINT'], 'regulator': [], 'fixture': ['SIGINT'], 'recorder': ['SIGINT']},
            'target_job_native_calls': 0, 'target_job_candidate_published': False,
            'target_job_candidate_registered': False, 'backend_terminal': True,
            'active_job_cleared': True, 'pending_discard_required': True},
        'two_deadlines': {'gate_wait_budget_ns': 1500000000,
            'job_deadline_ns_after_origin': 150000000, 'gate_window_extends_job_deadline': False},
        'release_preconditions': {'required_complete_ticks_after_entry': 2,
            'capability_lease_ns': 600000000, 'active_watchdog_ns': 1000000000,
            'release_must_precede_active_watchdog': True},
        'channel': {'kind': 'private_pipe', 'driver_holds': 'write_end',
            'worker_inherits': 'read_end', 'siblings_inherit': 'none', 'static_registration_predicts_inode': False}}


CONFIG = {'deadline_ns': 150000000, 'worker_capability_receipt_timeout_ns': 600000000,
          'active_watchdog_ns': 1000000000}


def observations():
    reg = registration()
    b = {'job_id': 2, 'ordinal': 1, 'released': True, 'gate_outcome': 'released',
         'disposition': 'expired', 'actual_native_invoked': False, 'ordinal_at_call': 0,
         'entered_ns': 1000000000, 'released_ns': 1500000050, 'guard_ns': 1500000060,
         'job_deadline_ns': 1150000000, 'past_deadline_ns': 350000060}
    result = {'W2_observed': True, 'w2_boundary_entered': True, 'w2_release_sent': True,
              'w2_entered_row': {'job_id': 2, 'ordinal': 1, 'entered_ns': 1000000100,
                                  'job_deadline_ns': 1150000000},
              'w2_target_job': {'deadline_ns': 1150000000},
              'w2_result': {'job_id': 2, 'ordinal': 1, 'boundary': b,
                            'disposition': 'expired', 'actual_native_invoked': False},
              'w2_release_record': {'job_id': 2, 'ordinal': 1, 'nonce': 20261023,
                                     'write_start_ns': 1500000000, 'write_end_ns': 1500000100, 'written_bytes': 44},
              'w2_ticks_after_enter': [3, 4], 'w2_live_renewals': 1,
              'runtime_libraries_verified': True, 'ramp_ok': True, 'accepted_pairs': 1}
    closed = [{'role': role, 'returncode': reg['expected']['exit_codes'][role],
               'signals': [{'signal': v} for v in reg['expected']['signals'][role]], 'group_empty': True}
              for role in ['regulator', 'worker', 'fixture', 'recorder']]
    observed = {'terminal_events': [{'job_id': 2, 'reason': 'w2_boundary_expired'}],
                'registered_job_ids': {1}, 'worker_published_job_ids': {1},
                'candidate_rows': [1], 'active_cleared': True, 'pending_discarded_job_ids': [3],
                'target_policy': {'actual_C_solve_calls_this_job': 0, 'terminal': True}}
    return reg, result, closed, observed


class Preflight(unittest.TestCase):
    def test_valid(self): validate_w2(registration(), CONFIG)
    def test_nonce_zero(self):
        r = registration(); r['w2_release']['nonce'] = 0
        with self.assertRaises(AssertionError): validate_w2(r, CONFIG)
    def test_nonce_negative(self):
        r = registration(); r['w2_release']['nonce'] = -1
        with self.assertRaises(AssertionError): validate_w2(r, CONFIG)
    def test_nonce_bool(self):
        r = registration(); r['w2_release']['nonce'] = True
        with self.assertRaises(AssertionError): validate_w2(r, CONFIG)
    def test_budget_zero(self):
        r = registration(); r['w2_release']['wait_budget_ns'] = 0
        with self.assertRaises(AssertionError): validate_w2(r, CONFIG)
    def test_original_deadline_cannot_change(self):
        r = registration(); r['two_deadlines']['job_deadline_ns_after_origin'] += 1
        with self.assertRaises(AssertionError): validate_w2(r, CONFIG)
    def test_worker_signal_cannot_change(self):
        r = registration(); r['expected']['w2_worker_signals'] = ['SIGTERM']
        with self.assertRaises(AssertionError): validate_w2(r, CONFIG)
    def test_policy_cannot_extend_deadline(self):
        r = registration(); r['two_deadlines']['gate_window_extends_job_deadline'] = True
        with self.assertRaises(AssertionError): validate_w2(r, CONFIG)


class FinalVerdict(unittest.TestCase):
    def test_positive(self): self.assertTrue(all(w2_result_checks(*observations()).values()))
    def rejected(self, fn):
        data = observations(); fn(*data)
        self.assertFalse(all(w2_result_checks(*data).values()))
    def test_no_verified_release(self):
        self.rejected(lambda reg, result, closed, obs: result['w2_result']['boundary'].update(released=False))
    def test_not_past_deadline(self):
        self.rejected(lambda reg, result, closed, obs: result['w2_result']['boundary'].update(guard_ns=1100000000))
    def test_wrong_terminal_Job(self):
        self.rejected(lambda reg, result, closed, obs: obs['terminal_events'][0].update(job_id=999))
    def test_publication_is_worker_fact(self):
        self.rejected(lambda reg, result, closed, obs: obs['worker_published_job_ids'].add(2))
    def test_worker_signal_exact(self):
        self.rejected(lambda reg, result, closed, obs: closed[1]['signals'].append({'signal': 'SIGTERM'}))
    def test_early_isolation(self):
        self.rejected(lambda reg, result, closed, obs: result.update(transition_ns=999999999, transition_reason='fatal_capability'))
    def test_bootstrap_error_finalizes(self):
        checks = w2_result_checks(registration(), {'error': 'fixture authentication failed'}, [], {})
        self.assertFalse(all(checks.values()))
        self.assertFalse(checks['no_driver_error'])
    def test_no_runtime_evidence(self):
        self.rejected(lambda reg, result, closed, obs: result.update(runtime_libraries_verified=False))
    def test_no_heartbeat(self):
        self.rejected(lambda reg, result, closed, obs: result.update(w2_live_renewals=0))


class CompleteTicks(unittest.TestCase):
    def test_requires_real_successful_pair_and_real_time(self):
        decisions = {3: {'sequence': 5, 'start_ns': 110, 'end_ns': 130, 'reason': 'no_candidate'}}
        pair = {'sequence': 5, 'starts': [115, 120], 'ends': [118, 125], 'returned': [True, True], 'kind': 'fallback'}
        self.assertEqual(complete_w2_ticks(100, decisions, {3: pair}), [3])
        self.assertEqual(complete_w2_ticks(120, decisions, {3: pair}), [])
        self.assertEqual(complete_w2_ticks(100, decisions, {}), [])
        pair['returned'][1] = False
        self.assertEqual(complete_w2_ticks(100, decisions, {3: pair}), [])


class LoadedLibraries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = [Path('/home/trevor/acados/lib') / name for name in ['libblasfeo.so', 'libhpipm.so', 'libacados.so']]
        cls.records = {p.name: {'path': str(p.resolve()), **pin(p)} for p in paths}
        code = 'import ctypes,sys\nfor p in sys.argv[1:]: ctypes.CDLL(p,mode=ctypes.RTLD_GLOBAL)\nprint("READY",flush=True)\nsys.stdin.readline()\n'
        env = dict(os.environ); env['LD_LIBRARY_PATH'] = '/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'
        cls.child = subprocess.Popen([sys.executable, '-u', '-c', code, *[str(p) for p in paths]],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        if not select.select([cls.child.stdout], [], [], 10)[0] or cls.child.stdout.readline().strip() != 'READY':
            cls.child.kill(); out, err = cls.child.communicate(timeout=5)
            raise AssertionError('Library component child not ready: ' + err)
        cls.start = process_start(cls.child.pid)
    @classmethod
    def tearDownClass(cls):
        cls.child.communicate('exit\n', timeout=5)
        if cls.child.returncode != 0: raise AssertionError('Library child did not close')
    def test_live_objects_match(self):
        self.assertEqual(len(verify_runtime_maps(self.child.pid, self.records, self.start)['libraries']), 3)
    def test_wrong_hash_rejected(self):
        records = copy.deepcopy(self.records); next(iter(records.values()))['sha256'] = '0' * 64
        with self.assertRaises(AssertionError): verify_runtime_maps(self.child.pid, records, self.start)
    def test_wrong_process_start_rejected(self):
        with self.assertRaises(AssertionError): verify_runtime_maps(self.child.pid, self.records, self.start + 1)
    def test_wrong_path_rejected(self):
        records = copy.deepcopy(self.records); next(iter(records.values()))['path'] = '/bin/true'
        with self.assertRaises(AssertionError): verify_runtime_maps(self.child.pid, records, self.start)


if __name__ == '__main__': unittest.main()
