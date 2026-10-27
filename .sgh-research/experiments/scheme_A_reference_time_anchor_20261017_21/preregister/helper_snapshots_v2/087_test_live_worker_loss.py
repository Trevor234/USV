import unittest
from check_live_worker_loss import mechanism

class LiveLossProof(unittest.TestCase):
    def setUp(self):
        self.context={'scenario':'idle_stop','policy_mode':'enforce_lease'}
        self.fault={'ns':1_000_000_000,'pid':99,'active_job':0,'pending_count':0,'process_identity':{'start_ticks':10}}
        self.summary={'fault':self.fault}
        self.fixture=[{'type':'stopped_live_sample','identity':{'pid':99,'start_ticks':10,'state':'T'}} for _ in range(18)]+[
            {'type':'stopped_observation_end','ns':2_800_000_001},
            {'type':'declared_owned_continue','ns':2_900_000_000},
            {'type':'resume_observation_end','ns':3_700_000_001}]
        self.reg=[{'type':'capability_admission','validation_commit_ns':800_000_000,'renewed':True,'valid':True,'terminal_run':False},
                  {'type':'capability_admission','validation_commit_ns':900_000_000,'renewed':True,'valid':True,'terminal_run':False},
                  {'type':'worker_unusable_transition','check_ns':1_600_000_000,'processed_ns':1_600_000_001,'capability_last_valid_commit_ns':900_000_000,'capability_timeout_ns':600_000_000,'reason':'worker_capability_expired','candidate_after':False,'pending_after':False},
                  {'type':'capability_admission','validation_commit_ns':3_000_000_000,'renewed':False,'valid':True,'terminal_run':True}]
        self.jobs=[{'submit_commit_ns':950_000_000}]
        self.dec=[{'activation_commit_ns':950_000_000,'accepted':True,'reason':''}]+[
            {'activation_commit_ns':1_000_000_000+i*200_000_000,'accepted':False,'reason':'worker_unusable'} for i in range(10)]+[
            {'activation_commit_ns':3_000_000_000+i*200_000_000,'accepted':False,'reason':'worker_unusable'} for i in range(4)]
    def result(self):return mechanism(self.context,self.summary,self.reg,self.fixture,self.dec,self.jobs,[])
    def fails(self):self.assertFalse(self.result()['mechanism_complete'])
    def test_complete(self):self.assertTrue(self.result()['mechanism_complete'])
    def test_not_live_stopped(self):self.fixture[0]['identity']['state']='R';self.fails()
    def test_pid_recycled(self):self.fixture[0]['identity']['start_ticks']=11;self.fails()
    def test_short_stop_window(self):self.fixture[-3]['ns']=2_799_999_999;self.fails()
    def test_short_resume_window(self):self.fixture[-1]['ns']=3_699_999_999;self.fails()
    def test_missing_terminal(self):self.reg.pop(2);self.fails()
    def test_wrong_terminal_cause(self):self.reg[2]['reason']='active_watchdog';self.fails()
    def test_expiration_equality_not_expired(self):self.reg[2]['check_ns']=1_500_000_000;self.fails()
    def test_too_late_detection(self):self.reg[2]['check_ns']=1_720_000_001;self.fails()
    def test_wrong_last_valid(self):self.reg[2]['capability_last_valid_commit_ns']=899_999_999;self.fails()
    def test_invalid_renewal(self):self.reg[1]['valid']=False;self.fails()
    def test_renewal_after_terminal(self):self.reg[-1]['renewed']=True;self.fails()
    def test_no_resume_capability(self):self.reg.pop();self.fails()
    def test_resume_not_terminal(self):self.reg[-1]['terminal_run']=False;self.fails()
    def test_new_submit(self):self.jobs.append({'submit_commit_ns':1_600_000_001});self.fails()
    def test_new_activation(self):self.dec[-1]['accepted']=True;self.fails()
    def test_pending_not_cleared(self):self.reg[2]['pending_after']=True;self.fails()
    def test_old_gap_observation(self):
        self.context['policy_mode']='observe_old';self.reg=[]
        self.jobs.append({'submit_commit_ns':2_500_000_000})
        r=self.result();self.assertTrue(r['gap_reproduced']);self.assertFalse(r['mechanism_complete']);self.assertEqual(r['issues'],[])
    def test_old_gap_not_reproduced(self):
        self.context['policy_mode']='observe_old';self.reg=[]
        self.assertFalse(self.result()['gap_reproduced'])

if __name__=='__main__':unittest.main()
