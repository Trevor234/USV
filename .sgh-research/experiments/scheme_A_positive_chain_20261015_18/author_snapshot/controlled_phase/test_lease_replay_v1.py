#!/usr/bin/python3
"""Finite lease semantics and coherent-forgery regressions, without ROS."""
import copy
import unittest
import lease_replay_v1 as L

EXPECTED=dict(run_id='run',boot_id='boot',contract_hash='a'*64,nominal_hash='b'*64,pid=41,fault_injection_enabled=False)
TIMEOUT=600_000_000
START=1_000_000_000

def valid():
    return dict(schema_version='p1-worker-capability-v1',run_id='run',boot_id='boot',contract_hash='a'*64,
        nominal_hash='b'*64,worker_instance='worker',clock_name='CLOCK_MONOTONIC',backend='acados',matrix_layout='column_major',
        horizon_steps=20,prediction_dt=.2,pid=41,startup_ns=1,completed_jobs=0,active_job=0,pending_count=0,
        fault_injection_enabled=False,fatal=False,reason='')

def observed(machine,cap,now):
    result=machine.callback(cap,now)
    out=dict(type='capability_admission',capability=copy.deepcopy(cap),receive_ns=now-1,validation_commit_ns=now,
        identity_valid=result['identity_valid'],valid=result['valid'],renewed=result['renewed'],terminal_run=result['terminal_run'],
        lease_last_before_ns=result['before']['last_valid_ns'],lease_last_after_ns=result['after']['last_valid_ns'],
        lease_timeout_ns=TIMEOUT,source_freshness_available=False,raw_input=None,
        lease_observation={phase:{k:result[phase][k] for k in ('worker_instance','worker_valid','worker_unusable')}
                           for phase in ('before','after')})
    transition=[]
    if not result['before']['worker_unusable'] and result['after']['worker_unusable']:
        transition=[dict(type='worker_unusable_transition',reason=result['after']['terminal_reason'],check_ns=now,
            capability_last_valid_commit_ns=result['after']['last_valid_ns'],capability_timeout_ns=TIMEOUT)]
    return transition+[out]

class LeaseFiniteTests(unittest.TestCase):
    def machine(self):return L.LeaseReplay(EXPECTED,TIMEOUT)
    def replay(self,rows):
        issues=[]
        def need(ok,code,**detail):
            if not ok:issues.append(dict(code=code,**detail))
        result=L.replay(rows,EXPECTED,TIMEOUT,need)
        return result,issues
    def test_valid_then_invalid_keeps_last_valid(self):
        m=self.machine();a=m.callback(valid(),START);bad=valid();bad['backend']='other'
        b=m.callback(bad,START+10);self.assertTrue(a['renewed']);self.assertFalse(b['valid']);self.assertFalse(b['renewed'])
        self.assertEqual(m.last,START);self.assertTrue(m.worker_valid);self.assertFalse(m.terminal)
    def test_foreign_fatal_does_not_terminate(self):
        m=self.machine();m.callback(valid(),START);bad=valid();bad.update(run_id='foreign',fatal=True)
        b=m.callback(bad,START+10);self.assertFalse(b['identity_valid']);self.assertFalse(m.terminal);self.assertEqual(m.last,START)
    def test_resource_rejection_returns_before_timeout_check(self):
        m=self.machine();m.callback(valid(),START);bad=valid();bad['reason']='x'*257
        b=m.callback(bad,START+TIMEOUT+1);self.assertIsNotNone(b['resource']);self.assertFalse(m.terminal);self.assertEqual(m.last,START)
    def test_matching_fatal_is_terminal(self):
        m=self.machine();m.callback(valid(),START);bad=valid();bad['fatal']=True;m.callback(bad,START+1)
        self.assertTrue(m.terminal);self.assertFalse(m.worker_valid);self.assertEqual(m.reason,'fatal_capability')
    def test_changed_instance_invalid_still_terminal(self):
        m=self.machine();m.callback(valid(),START);bad=valid();bad.update(worker_instance='different',backend='other')
        m.callback(bad,START+1);self.assertEqual(m.reason,'worker_instance_changed');self.assertEqual(m.last,START)
    def test_timeout_equality_renews(self):
        m=self.machine();m.callback(valid(),START);b=m.callback(valid(),START+TIMEOUT)
        self.assertTrue(b['renewed']);self.assertFalse(m.terminal);self.assertEqual(m.last,START+TIMEOUT)
    def test_timeout_plus_one_cannot_renew(self):
        m=self.machine();m.callback(valid(),START);b=m.callback(valid(),START+TIMEOUT+1)
        self.assertTrue(b['valid']);self.assertFalse(b['renewed']);self.assertEqual(m.last,START);self.assertTrue(m.terminal)
    def test_duplicate_payload_can_renew(self):
        m=self.machine();cap=valid();m.callback(cap,START);self.assertTrue(m.callback(cap,START+1)['renewed'])
        self.assertEqual(m.last,START+1)
    def test_valid_after_expiry_cannot_resurrect(self):
        m=self.machine();m.callback(valid(),START);m.check(START+TIMEOUT+1)
        self.assertFalse(m.callback(valid(),START+TIMEOUT+2)['renewed']);self.assertFalse(m.worker_valid)
    def test_no_valid_renewal_worker_not_valid(self):
        m=self.machine();bad=valid();bad['backend']='other';m.callback(bad,START)
        self.assertEqual(m.last,0);self.assertFalse(m.worker_valid);self.assertFalse(m.terminal)
    def test_invalid_receipt_after_timeout_is_terminal(self):
        m=self.machine();m.callback(valid(),START);bad=valid();bad['run_id']='foreign';m.callback(bad,START+TIMEOUT+1)
        self.assertEqual(m.reason,'worker_capability_expired')
    def test_clock_backwards_terminal(self):
        m=self.machine();m.callback(valid(),START);m.callback(valid(),START-1)
        self.assertEqual(m.reason,'worker_capability_clock_invalid')
    def test_original_zero_startup_not_valid(self):
        m=self.machine();bad=valid();bad['startup_ns']=0;self.assertFalse(m.callback(bad,START)['valid'])
    def test_foreign_changed_instance_not_terminal(self):
        m=self.machine();m.callback(valid(),START);bad=valid();bad.update(pid=42,worker_instance='different')
        m.callback(bad,START+1);self.assertFalse(m.terminal)
    def test_replay_reconstructs_last_valid_across_invalid_receipt(self):
        m=self.machine();rows=observed(m,valid(),START);bad=valid();bad['backend']='other';rows+=observed(m,bad,START+5)
        out,issues=self.replay(rows);self.assertFalse(issues);self.assertEqual(L.state_at(out,START+6)['last_valid_ns'],START)
    def test_replay_terminal_then_valid_no_resurrection(self):
        m=self.machine();rows=observed(m,valid(),START);bad=valid();bad['fatal']=True;rows+=observed(m,bad,START+1);rows+=observed(m,valid(),START+2)
        out,issues=self.replay(rows);self.assertFalse(issues);self.assertTrue(out['final']['worker_unusable'])
    def test_coherent_invalid_receipt_renewal_forgery_rejected(self):
        m=self.machine();rows=observed(m,valid(),START);bad=valid();bad['backend']='other';rows+=observed(m,bad,START+2)
        rows[-1].update(valid=True,renewed=True,lease_last_after_ns=START+2)
        _,issues=self.replay(rows);self.assertIn('capability_independent_renewed',{x['code'] for x in issues})
    def test_coherent_last_receipt_before_after_forgery_rejected(self):
        m=self.machine();rows=observed(m,valid(),START);bad=valid();bad['run_id']='foreign';rows+=observed(m,bad,START+2);rows+=observed(m,valid(),START+3)
        rows[-2]['lease_last_after_ns']=START+2;rows[-1]['lease_last_before_ns']=START+2
        _,issues=self.replay(rows);self.assertIn('capability_independent_before_after',{x['code'] for x in issues})
    def test_coherent_terminal_worker_valid_forgery_rejected(self):
        m=self.machine();rows=observed(m,valid(),START);bad=valid();bad['fatal']=True;rows+=observed(m,bad,START+1)
        rows[-1]['terminal_run']=False;rows[-1]['lease_observation']['after'].update(worker_valid=True,worker_unusable=False)
        _,issues=self.replay(rows);codes={x['code'] for x in issues};self.assertIn('capability_independent_terminal_run',codes);self.assertIn('capability_independent_after_flags_instance',codes)
    def test_coherent_after_expiry_renewal_forgery_rejected(self):
        m=self.machine();rows=observed(m,valid(),START);rows+=observed(m,valid(),START+TIMEOUT+1)
        rows[-1].update(renewed=True,terminal_run=False,lease_last_after_ns=START+TIMEOUT+1)
        _,issues=self.replay(rows);self.assertIn('capability_independent_renewed',{x['code'] for x in issues})
    def test_exact_boolean_is_not_integer(self):
        cap=valid();cap['completed_jobs']=False;self.assertFalse(L.exact_payload(cap))
    def test_bad_gate_state_cannot_come_from_last_receipt(self):
        m=self.machine();rows=observed(m,valid(),START);bad=valid();bad['backend']='other';rows+=observed(m,bad,START+1)
        out,issues=self.replay(rows);self.assertFalse(issues);state=L.state_at(out,START+2)
        self.assertTrue(state['worker_valid']);self.assertEqual(state['last_capability']['backend'],'acados')

if __name__=='__main__':unittest.main()
