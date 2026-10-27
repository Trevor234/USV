#!/usr/bin/env python3
"""Fault-evidence risks exercised through the real decoded checker."""
import copy
import unittest
import check_p1_execution as checker
from test_check_p1_execution import fixture_v2, decision_update


def delay_fixture(delay=50, expired=False):
    f = fixture_v2()
    c = f[4]
    c.update(scenario="post_native_result_delay", fault_injection={"test_delay_ms": delay},
             _worker_owned_argv=["worker", "-p", "test_delay_ms:="+str(delay)],
             expected_mechanisms=["no_physical_publishers", "post_native_delay_observed", "original_deadline_respected"])
    if delay >= 150:
        c["expected_mechanisms"].append("late_candidate_rejected")
    f[2]["/p1/worker_capability"][0]["message"]["fault_injection_enabled"] = True
    f[1][0]["publish_start_ns"] = f[1][0]["solve_end_ns"] + delay*1000000
    if expired:
        r = next(e for e in f[0] if e.get("type") == "candidate_registration")
        r.update(accepted_registration=False, reason="wrong_tick", ready_commit_ns=1040000000+delay*1000000+1000000)
        decision_update(f, candidate_accepted=False, job_id=0, reason="no_candidate",
                        control_source="bootstrap_zero", candidate_ready_commit_ns=0)
    return f


def block_fixture():
    f = fixture_v2()
    f[3].update(active_watchdog_ns=1000000000, kill_postcheck_ns=1000000000)
    f[4].update(scenario="controlled_pre_native_barrier_watchdog", fault_injection={"test_native_block_ms": 60000},
        _worker_owned_argv=["worker", "-p", "test_native_block_ms:=60000"],
        expected_mechanisms=["no_physical_publishers", "watchdog_invalidated"],
        _watchdog_boundary_ns=2301000000, _worker_owned_signals_valid=True,
        _worker_owned_signals=[{"signal": x, "monotonic_ns": t} for x,t in [(2,2340000000),(15,2870000000),(9,3890000000)]],
        _worker_owned_cleanup={"returncode": -9, "cleanup_complete": True, "remaining_members": [], "monotonic_ns": 3990000000})
    f[4]["runner_summary_facts"].update(watchdog_seen=True, stop_reason="owned_worker_active_watchdog")
    f[4]["lifecycle"]["worker_source_flush_verified"] = False
    f[2]["/p1/worker_capability"][0]["message"]["fault_injection_enabled"] = True
    f[1][:] = [{"type": "controlled_pre_native_barrier", "start_ns": 1100000000,
               "duration_ms": 60000, "actual_native_invoked": False, "flush_requested": True, "job_id": 1}]
    f[2]["/p1/solve_candidate"] = []
    f[0][:] = [e for e in f[0] if e.get("type") != "candidate_registration"]
    decision_update(f, candidate_accepted=False, job_id=0, reason="no_candidate", control_source="bootstrap_zero", candidate_ready_commit_ns=0)
    source = next(e for e in f[0] if e.get("type") == "decision")
    d2 = copy.deepcopy(source)
    d2.update(sequence=2, tick=2, planned_ns=1400000000, start_ns=1400000000,
              activation_commit_ns=1400000000, end_ns=1400001000)
    f[0].insert(-2,d2)
    bd2 = copy.deepcopy(f[2]["/p1/execution_decision"][0])
    bd2["message"].update(sequence=2, tick=2, tick_planned_ns=1400000000, tick_start_ns=1400000000,
                          activation_commit_ns=1400000000, tick_end_ns=1400001000)
    f[2]["/p1/execution_decision"].append(bd2)
    f[0].insert(-1,{"type": "active_watchdog", "active_job": 1, "observed_ns": 2300000000})
    f[0][-1].update(generated=len(f[0])-1, emitted=len(f[0])-1)
    return f


class FaultEvidenceRisks(unittest.TestCase):
    def check(self,f):
        return checker.validate_decoded(*f)

    def test_50ms_on_time_can_be_accepted_without_late_event(self):
        r=self.check(delay_fixture())
        self.assertEqual(r["issues"],[])
        self.assertTrue(r["fault_mechanism_passed"])
        self.assertEqual(r["fault_delay_observations"]["expired_registration_count"],0)
        self.assertFalse(r["diagnostic_complete"])
        self.assertFalse(r["normal_contract_complete"])

    def test_expired_wrong_tick_is_rejection_for_original_deadline(self):
        r=self.check(delay_fixture(250,True))
        self.assertEqual(r["issues"],[])
        self.assertTrue(r["fault_mechanism_passed"])
        self.assertEqual(r["fault_delay_observations"]["expired_registration_count"],1)

    def test_150ms_requires_actual_expired_rejection(self):
        f=delay_fixture(150)
        self.assertFalse(self.check(f)["fault_mechanism_passed"])

    def test_declared_delay_needs_owned_argv_capability_and_interval(self):
        for change in ("argv","capability","interval"):
            with self.subTest(change=change):
                f=delay_fixture()
                if change=="argv":f[4]["_worker_owned_argv"]=["worker","test_delay_ms:=0"]
                elif change=="capability":f[2]["/p1/worker_capability"][0]["message"]["fault_injection_enabled"]=False
                else:f[1][0]["publish_start_ns"]-=1
                self.assertFalse(self.check(f)["fault_mechanism_passed"])

    def test_missing_raw_data_cannot_pass_fault_mechanism(self):
        f=delay_fixture();f[4]["_actual_topic_counts"]["/odom"]-=1
        r=self.check(f)
        self.assertFalse(r["raw_input_recording_complete"])
        self.assertFalse(r["fault_mechanism_passed"])

    def test_killed_worker_can_prove_cleanup_but_source_stays_unknown(self):
        r=self.check(block_fixture())
        self.assertTrue(r["fault_mechanism_passed"],r["mechanism_assertions"])
        self.assertFalse(r["source_bag_contract_complete"])
        self.assertFalse(r["lifecycle_verified"])
        self.assertEqual(len(r["fault_expected_worker_source_gaps"]),3)
        self.assertFalse(r["normal_contract_complete"])

    def test_unknown_watchdog_boundary_is_not_vacuous_success(self):
        f=block_fixture();del f[4]["_watchdog_boundary_ns"]
        self.assertFalse(self.check(f)["fault_mechanism_passed"])

    def test_barrier_must_be_preserved_and_pre_native(self):
        for key,value in [("actual_native_invoked",True),("flush_requested",False),("job_id",999)]:
            with self.subTest(field=key):
                f=block_fixture();f[1][0][key]=value
                self.assertFalse(self.check(f)["fault_mechanism_passed"])

    def test_kill_needs_verified_sequence_and_finite_postcheck(self):
        for change in ("signals","identity","residual","postcheck"):
            with self.subTest(change=change):
                f=block_fixture()
                if change=="signals":f[4]["_worker_owned_signals"].pop(1)
                elif change=="identity":f[4]["_worker_owned_signals_valid"]=False
                elif change=="residual":f[4]["_worker_owned_cleanup"]["remaining_members"]=[42]
                else:f[4]["_worker_owned_cleanup"]["monotonic_ns"]=5000000000
                self.assertFalse(self.check(f)["fault_mechanism_passed"])

    def test_block_does_not_excuse_regulator_recording_gap(self):
        f=block_fixture();f[0][-1]["emitted"]-=1
        self.assertFalse(self.check(f)["fault_mechanism_passed"])

    def test_block_needs_independent_ticks_during_barrier(self):
        f=block_fixture()
        f[0][:]=[e for e in f[0] if not(e.get("type")=="decision" and e.get("sequence")==2)]
        f[2]["/p1/execution_decision"].pop()
        f[0][-1].update(generated=len(f[0])-1,emitted=len(f[0])-1)
        self.assertFalse(self.check(f)["fault_mechanism_passed"])


if __name__=="__main__":
    unittest.main()
