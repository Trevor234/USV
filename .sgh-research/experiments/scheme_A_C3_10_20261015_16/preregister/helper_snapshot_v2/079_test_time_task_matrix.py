import unittest
from check_time_task_matrix import mechanism
from p1_payload_digest import canonical_payload_digest

class TimeTaskEvidence(unittest.TestCase):
    def setUp(self):
        self.c={"clock_pause_confirm_ns":400_000_000,"odom_age_ns":100_000_000,
                "odom_sim_lag_ns":100_000_000,"source_future_slack_ns":20_000_000,"activation_tolerance":[.25]*6}
        self.candidates=[{"job":{"job_id":2},"success":True,"solver_invoked":True}]
        self.fault={"ns":155_000_000,"job_id":2,"deadline_ns":150_000_000,"target_ns":200_000_000,
                    "task_generation":2,"schedule_generation":1,"epoch":0,
                    "candidate_payload_sha256":canonical_payload_digest(self.candidates[0])}
        self.reg=[{"type":"candidate_registration","job":{"job_id":2},"accepted_registration":True,"ready_commit_ns":10_000_000},
                  {"type":"path_version","task_generation":3,"processed_ns":156_000_000}]
        self.dec=[dict(activation_commit_ns=i*200_000_000,job_id=0,accepted=False,reason="no_path",
                       task_generation=3,schedule_generation=1,epoch=0,anchor_known=[True,True]) for i in range(1,6)]
        self.dec.append(dict(activation_commit_ns=1_400_000_000,job_id=3,accepted=True,reason="",
                             task_generation=4,schedule_generation=1,epoch=0,anchor_known=[True,True]))
        self.fixture=[{"type":"fault_observation_end","ns":1_160_000_000},
                      {"type":"recovery_declared","recovery_ns":1_200_000_000}]
        self.jobs=[]
    def assess(self,scenario="path_clear"):
        return mechanism(scenario,self.fault,self.reg,self.dec,self.jobs,self.candidates,self.fixture,self.c)
    def test_clear_passes(self):self.assertTrue(self.assess()["mechanism_complete"])
    def test_missing_fault(self):self.fault=None;self.assertFalse(self.assess()["mechanism_complete"])
    def test_not_ready(self):self.reg[0]["accepted_registration"]=False;self.assertFalse(self.assess()["mechanism_complete"])
    def test_late_ready(self):self.reg[0]["ready_commit_ns"]=150_000_001;self.assertFalse(self.assess()["mechanism_complete"])
    def test_wrong_native(self):self.candidates[0]["solver_invoked"]=False;self.assertFalse(self.assess()["mechanism_complete"])
    def test_selected_digest(self):self.fault["candidate_payload_sha256"]="other";self.assertFalse(self.assess()["mechanism_complete"])
    def test_before_deadline(self):self.fault["ns"]=149_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_after_target(self):self.fault["ns"]=201_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_callback_after_target(self):self.reg[1]["processed_ns"]=201_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_callback_before_deadline(self):self.reg[1]["processed_ns"]=149_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_generation_not_changed(self):self.reg[1]["task_generation"]=2;self.assertFalse(self.assess()["mechanism_complete"])
    def test_old_activated(self):self.dec[0].update(accepted=True,job_id=2,task_generation=2);self.assertFalse(self.assess()["mechanism_complete"])
    def test_bad_reason(self):
        for d in self.dec[:-1]:d["reason"]="no_candidate"
        self.assertFalse(self.assess()["mechanism_complete"])
    def test_no_recovery(self):self.dec.pop();self.assertFalse(self.assess()["mechanism_complete"])
    def test_short_observation(self):self.fixture[0]["ns"]=900_000_000;self.assertFalse(self.assess()["mechanism_complete"])
    def test_too_few_decisions(self):self.dec=self.dec[:2]+self.dec[-1:];self.assertFalse(self.assess()["mechanism_complete"])
    def reset_fixture(self):
        self.fixture.pop()
        self.reg.append({"type":"clock","receive_ns":156_000_000,"epoch":1,"schedule_generation":2})
        self.dec.pop()
        for d in self.dec:d.update(reason="unknown_anchor",anchor_known=[False,False],epoch=1,schedule_generation=2)
    def test_reset_passes(self):self.reset_fixture();self.assertTrue(self.assess("clock_rollback")["mechanism_complete"])
    def test_reset_anchor_silently_recovered(self):self.reset_fixture();self.dec[1]["anchor_known"][0]=True;self.assertFalse(self.assess("clock_rollback")["mechanism_complete"])
    def test_reset_epoch_missing(self):self.reset_fixture();self.reg[-1]["epoch"]=0;self.assertFalse(self.assess("clock_jump")["mechanism_complete"])
    def test_reset_new_job(self):self.reset_fixture();self.jobs=[{"submit_commit_ns":300_000_000,"publish_start_ns":300_000_001}];self.assertFalse(self.assess("clock_jump")["mechanism_complete"])
    def test_physical_old_stamp_with_fresh_receipt(self):
        for d in self.dec[:-1]:d.update(reason="odom_sim_lag",odom_age_ns=10_000_000,activation_clock_sim_ns=1_000_000_000,
                                      activation_clock_receive_ns=d["activation_commit_ns"],activation_odom_stamp_ns=700_000_000)
        self.assertTrue(self.assess("source_lag")["mechanism_complete"])
    def test_old_stamp_not_relabelled_as_fresh(self):
        for d in self.dec[:-1]:d.update(reason="odom_sim_lag",odom_age_ns=200_000_000,activation_clock_sim_ns=1_000_000_000,
                                      activation_clock_receive_ns=d["activation_commit_ns"],activation_odom_stamp_ns=700_000_000)
        self.assertFalse(self.assess("source_lag")["mechanism_complete"])

if __name__=="__main__":unittest.main()
