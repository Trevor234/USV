import copy
import unittest
from check_regulator_fault_matrix import linkage

class LinkageEvidence(unittest.TestCase):
    def setUp(self):
        self.fault={"ns":1_000_000_000,"job_id":2,"active_job":0}
        self.jobs=[{"submit_commit_ns":950_000_000,"publish_start_ns":960_000_000}]
        self.reg=[{"job":{"job_id":2},"accepted_registration":False,"reason":"solver_failed"}]
        self.cand=[{"job":{"job_id":2},"solver_invoked":True,"success":False}]
        self.dec=[{"activation_commit_ns":1_100_000_000,"reason":"worker_unusable","accepted":False}]
        self.trans=[{"processed_ns":1_020_000_000,"reason":"fatal_capability","candidate_after":False,"pending_after":False}]
    def assess(self,scenario="numerical"):
        return linkage(scenario,self.fault,self.jobs,self.reg,self.cand,self.dec,self.trans,2_400_000_000)
    def test_complete(self):self.assertTrue(self.assess()["mechanism_complete"])
    def test_missing_fault(self):self.fault=None;self.assertFalse(self.assess()["mechanism_complete"])
    def test_native_call_required(self):self.cand[0]["solver_invoked"]=False;self.assertFalse(self.assess()["mechanism_complete"])
    def test_native_failure_required(self):self.cand[0]["success"]=True;self.assertFalse(self.assess()["mechanism_complete"])
    def test_failed_registration_missing(self):self.reg=[];self.assertFalse(self.assess()["mechanism_complete"])
    def test_failed_registration_accepted(self):self.reg[0]["accepted_registration"]=True;self.assertFalse(self.assess()["mechanism_complete"])
    def test_failed_registration_reason(self):self.reg[0]["reason"]="foreign";self.assertFalse(self.assess()["mechanism_complete"])
    def test_new_commit_after_terminal(self):self.jobs[0]["submit_commit_ns"]=1_020_000_001;self.assertFalse(self.assess()["mechanism_complete"])
    def test_precommitted_tail_allowed(self):
        self.jobs[0]["publish_start_ns"]=1_030_000_000
        r=self.assess();self.assertTrue(r["mechanism_complete"]);self.assertEqual(r["precommitted_publication_tail"],1)
    def test_activation_after_terminal(self):self.dec[0]["accepted"]=True;self.assertFalse(self.assess()["mechanism_complete"])
    def test_ready_invalidation(self):self.trans[0]["candidate_after"]=True;self.assertFalse(self.assess()["mechanism_complete"])
    def test_pending_invalidation(self):self.trans[0]["pending_after"]=True;self.assertFalse(self.assess()["mechanism_complete"])
    def test_no_unusable_decision(self):self.dec[0]["reason"]="no_candidate";self.assertFalse(self.assess()["mechanism_complete"])
    def test_insufficient_observation(self):
        r=linkage("numerical",self.fault,self.jobs,self.reg,self.cand,self.dec,self.trans,2_199_999_999)
        self.assertFalse(r["mechanism_complete"])
    def test_idle_state(self):self.fault["active_job"]=1;self.assertFalse(self.assess("idle_exit")["mechanism_complete"])
    def test_active_state(self):self.assertFalse(self.assess("active_exit")["mechanism_complete"])
    def test_delayed_death_observation(self):
        self.trans[0].update(processed_ns=1_220_000_001,reason="worker_process_exited")
        self.assertFalse(self.assess("idle_exit")["mechanism_complete"])
    def test_exit_cause(self):self.assertFalse(self.assess("idle_exit")["mechanism_complete"])
    def test_source_invalidation_unknown_without_event(self):
        self.trans=[];r=self.assess();self.assertTrue(r["mechanism_complete"]);self.assertFalse(r["terminal_source_invalidation_proven"])

if __name__=="__main__":unittest.main()
