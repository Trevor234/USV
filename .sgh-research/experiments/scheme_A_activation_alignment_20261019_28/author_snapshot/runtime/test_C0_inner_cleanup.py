"""No ROS/process-spawn tests for C0 ledger-authorized group recovery."""
import copy
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import cleanup_C0_inner as c

BOOT = "12345678-1234-1234-1234-123456789abc"
SHA = "a" * 64


class FakeBackend:
    def __init__(self, processes=None):
        self.processes = copy.deepcopy(processes or {})
        self.boot = BOOT
        self.now = 0.
        self.signals = []
        self.remove_at = signal.SIGINT
        self.on_sleep = None
        self.on_signal = None

    def boot_id(self):
        return self.boot

    def proc_identity(self, pid, hash_exe=True):
        return copy.deepcopy(self.processes.get(pid))

    def proc_table(self):
        return copy.deepcopy(list(self.processes.values()))

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.on_sleep:
            self.on_sleep()

    def killpg(self, group, sig):
        self.signals.append((group, sig))
        if self.on_signal:
            self.on_signal(group, sig)
        if self.remove_at is not None and sig == self.remove_at:
            self.processes = {pid:r for pid,r in self.processes.items() if r['pgid'] != group}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned_process_ledger.jsonl'
        self.expected = {r:{'exe':'/bin/'+r, 'sha256':SHA} for r in c.ROLES}
        self.identities = {r:{'pid':100+i,'ppid':90,'pgid':100+i,'sid':100+i,
                              'start_ticks':1000+i,'exe':'/bin/'+r,
                              'exe_sha256':SHA,'state':'S'} for i,r in enumerate(c.ROLES)}
        self.rows = [{'type':'spawn','monotonic_ns':20+i,'boot_id':BOOT,'name':r,
                      'identity':copy.deepcopy(self.identities[r]),'expected_exe':'/bin/'+r,
                      'expected_sha256':SHA,'executable_verified':True}
                     for i,r in enumerate(c.ROLES)]
        self.backend = FakeBackend({v['pid']:v for v in self.identities.values()})
        self.events = []
        self.write()

    def write(self, raw=None):
        self.path.write_bytes(raw if raw is not None else ''.join(json.dumps(r)+'\n' for r in self.rows).encode())

    def event(self, kind, **details):
        self.events.append((kind,details))
        return True

    def recover(self, **kwargs):
        return c.recover(self.path,self.expected,BOOT,runner_pid=90,event=self.event,
                         backend=self.backend,**kwargs)

    def blocked(self):
        report = self.recover()
        self.assertFalse(report['cleanup_complete'])
        self.assertEqual(self.backend.signals, [])
        return report

    def test_all_four_roles_recovered_without_waitpid(self):
        report=self.recover()
        self.assertTrue(report['cleanup_complete'])
        self.assertTrue(report['evidence_complete'])
        self.assertTrue(report['group_cleanup_complete'])
        self.assertEqual(self.backend.signals,[(100+i,signal.SIGINT) for i in range(4)])
        self.assertEqual(len(report['roles']),4)
        self.assertFalse(report['execute_qualified'])

    def test_already_empty_is_complete_without_signals(self):
        self.backend.processes={}
        self.assertTrue(self.recover()['cleanup_complete'])
        self.assertEqual(self.backend.signals,[])

    def test_missing_role_safe_subset_never_claims_full_complete(self):
        self.rows.pop();self.write()
        report=self.recover()
        self.assertFalse(report['cleanup_complete'])
        self.assertFalse(report['evidence_complete'])
        self.assertTrue(report['group_cleanup_complete'])
        self.assertEqual(report['missing_roles'],['recorder'])
        self.assertEqual([p for p,s in self.backend.signals],[100,101,102])
        self.assertIn(103,self.backend.processes)

    def test_no_spawns_no_signal_and_unknown_roles(self):
        self.rows=[{'type':'supervisor_summary','monotonic_ns':1,'boot_id':BOOT}];self.write()
        report=self.blocked()
        self.assertFalse(report['group_cleanup_complete'])
        self.assertEqual(set(report['missing_roles']),set(c.ROLES))

    def test_missing_ledger(self):
        self.path.unlink();self.blocked()

    def test_malformed_ledger(self):
        self.write(b'{broken}\n');self.blocked()

    def test_duplicate_json_key(self):
        self.write(b'{"type":"x","type":"spawn"}\n');self.blocked()

    def test_unclosed_concurrent_tail(self):
        self.write(self.path.read_bytes()+b'{"type":');self.blocked()

    def test_snapshot_concurrent_write_aborts_without_signals(self):
        original=Path.read_bytes
        def changed(path):
            raw=original(path)
            if path==self.path:
                with path.open('ab') as f:f.write(b'{}\n')
            return raw
        with patch.object(Path,'read_bytes',changed):self.blocked()

    def test_numeric_overflow_in_unused_json_field_is_malformed(self):
        raw=self.path.read_bytes().replace(b'"type": "spawn"',b'"extra": 1e9999, "type": "spawn"',1)
        self.write(raw);self.blocked()

    def test_duplicate_role(self):
        self.rows.append(copy.deepcopy(self.rows[0]));self.write();self.blocked()

    def test_ledger_boot_mismatch(self):
        self.rows[1]['boot_id']='f'*36;self.write();self.blocked()

    def test_live_boot_mismatch(self):
        self.backend.boot='f'*36;self.blocked()

    def test_spawn_wrong_parent(self):
        self.rows[0]['identity']['ppid']=91;self.write();self.blocked()

    def test_spawn_foreign_session(self):
        self.rows[0]['identity']['sid']=101;self.write();self.blocked()

    def test_spawn_expected_executable_mismatch(self):
        self.rows[0]['expected_exe']='/bin/foreign';self.write();self.blocked()

    def test_spawn_hash_mismatch(self):
        self.rows[0]['identity']['exe_sha256']='b'*64;self.write();self.blocked()

    def test_live_leader_pid_reuse_aborts_all_roles(self):
        self.backend.processes[103]['start_ticks']+=100;self.blocked()

    def test_live_leader_executable_hash_changed(self):
        self.backend.processes[102]['exe_sha256']='b'*64;self.blocked()

    def test_foreign_member_sid_aborts_all_roles(self):
        row=copy.deepcopy(self.identities['recorder']);row.update(pid=200,pgid=103,sid=200,start_ticks=2000)
        self.backend.processes[200]=row;self.blocked()

    def test_known_descendant_pid_reuse_aborts_all_roles(self):
        row=copy.deepcopy(self.identities['recorder']);row.update(pid=200,start_ticks=2000)
        self.rows.append({'type':'owned_descendant_observed','name':'recorder','identity':row,'monotonic_ns':30,'boot_id':BOOT})
        self.write();row['start_ticks']=2001;self.backend.processes[200]=row;self.blocked()

    def recorded_descendant(self):
        row=copy.deepcopy(self.identities['recorder']);row.update(pid=200,start_ticks=2000)
        self.rows.append({'type':'owned_descendant_observed','name':'recorder','identity':copy.deepcopy(row),'monotonic_ns':30,'boot_id':BOOT})
        self.write()
        self.backend.processes.pop(103)
        self.backend.processes[200]=row
        return row

    def test_known_descendant_escaped_pgid_original_group_empty(self):
        row=self.recorded_descendant();row['pgid']=200
        self.blocked()

    def test_known_descendant_escaped_sid_original_group_empty(self):
        row=self.recorded_descendant();row.update(pgid=200,sid=200)
        self.blocked()

    def test_known_pid_reused_outside_original_group(self):
        row=self.recorded_descendant();row.update(pgid=200,sid=200,start_ticks=2001)
        self.blocked()

    def test_absent_leader_with_owned_descendant(self):
        self.backend.processes.pop(100)
        row=copy.deepcopy(self.identities['regulator']);row.update(pid=200,ppid=1,start_ticks=2000)
        self.backend.processes[200]=row
        report=self.recover()
        self.assertTrue(report['cleanup_complete'])
        observed=[v for k,v in self.events if k=='C0_recovery_member_observed']
        self.assertEqual(observed[0]['identity']['pid'],200)

    def test_evidence_write_failure_before_signal(self):
        self.event=lambda *a,**k:False;self.blocked()

    def test_new_member_evidence_failure_before_any_signal(self):
        row=copy.deepcopy(self.identities['recorder']);row.update(pid=200,start_ticks=2000)
        self.backend.processes[200]=row
        self.event=lambda kind,**details:kind!='C0_recovery_member_observed'
        self.blocked()

    def test_signal_evidence_write_failure_before_touch(self):
        self.event=lambda kind,**details:kind!='C0_recovery_signal';self.blocked()

    def test_pid_reuse_during_signal_evidence_is_rechecked(self):
        original=self.event
        def callback(kind,**details):
            if kind=='C0_recovery_signal':self.backend.processes[100]['start_ticks']+=1
            return original(kind,**details)
        self.event=callback;self.blocked()

    def test_leader_changed_during_member_evidence_is_rechecked(self):
        row=copy.deepcopy(self.identities['regulator']);row.update(pid=200,start_ticks=2000)
        self.backend.processes[200]=row
        original=self.event
        def callback(kind,**details):
            if kind=='C0_recovery_member_observed':self.backend.processes[100]['exe_sha256']='b'*64
            return original(kind,**details)
        self.event=callback;self.blocked()

    def test_final_signal_member_event_escape_rechecked_before_killpg(self):
        original=self.event
        def callback(kind,**details):
            if kind=='C0_recovery_signal' and details['role']=='regulator':
                row=copy.deepcopy(self.identities['regulator']);row.update(pid=200,start_ticks=2000)
                self.backend.processes[200]=row
            if kind=='C0_recovery_member_observed':
                self.backend.processes[200].update(pgid=200,sid=200)
            return original(kind,**details)
        self.event=callback;self.blocked()

    def test_boot_change_during_wait_stops_further_signals(self):
        self.backend.remove_at=None
        self.backend.on_sleep=lambda:setattr(self.backend,'boot','f'*36)
        report=self.recover()
        self.assertFalse(report['cleanup_complete'])
        self.assertEqual(self.backend.signals,[(100,signal.SIGINT)])

    def test_finite_term_kill_escalation(self):
        self.backend.remove_at=c.SIGKILL
        report=self.recover()
        self.assertTrue(report['cleanup_complete'])
        self.assertEqual(self.backend.signals[:3],[(100,signal.SIGINT),(100,signal.SIGTERM),(100,c.SIGKILL)])
        self.assertLessEqual(self.backend.now,6.1)

    def test_unresponsive_group_finite_and_not_complete(self):
        self.backend.remove_at=None
        report=self.recover()
        self.assertFalse(report['cleanup_complete'])
        self.assertEqual(len(self.backend.signals),12)
        self.assertLessEqual(self.backend.now,10.1)

    def test_zombie_is_exited_but_not_group_empty(self):
        for row in self.backend.processes.values():row['state']='Z'
        report=self.recover()
        self.assertFalse(report['cleanup_complete'])
        self.assertEqual(self.backend.signals,[])
        self.assertTrue(all(r['leader_status']=='exited_zombie' for r in report['roles'].values()))

    def test_ledger_append_during_recovery_invalidates_full_evidence(self):
        def append(group,sig):
            if group==100:
                with self.path.open('ab') as f:f.write(json.dumps({'type':'cleanup_result','monotonic_ns':40,'boot_id':BOOT}).encode()+b'\n')
        self.backend.on_signal=append
        report=self.recover()
        self.assertTrue(report['group_cleanup_complete'])
        self.assertFalse(report['cleanup_complete'])
        self.assertFalse(report['ledger_snapshot_unchanged'])

    def test_bool_identity_rejected(self):
        self.rows[0]['identity']['pid']=True;self.write();self.blocked()

    def test_invalid_wait_rejected_before_signal(self):
        for value in (True,float('nan'),float('inf'),-1,61):
            with self.subTest(value=value):
                report=self.recover(grace=value)
                self.assertFalse(report['cleanup_complete'])
                self.assertEqual(self.backend.signals,[])

    def test_unverified_owned_launch_aborts_global(self):
        self.rows.append({'type':'launch_identity_missing','monotonic_ns':40,'boot_id':BOOT});self.write();self.blocked()


if __name__=='__main__':
    unittest.main()
