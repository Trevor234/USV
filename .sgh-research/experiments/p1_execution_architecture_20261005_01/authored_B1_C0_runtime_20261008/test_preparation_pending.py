import unittest
from check_preparation_pending import pending_proof

class PendingProof(unittest.TestCase):
    def setUp(self):
        self.reg=[{'type':'diagnostic_preparation_barrier_enter','target_tick':3,'start_ns':100,'maximum_ms':3000,'physical_output':False},
                  {'type':'diagnostic_preparation_pending_enqueued','target_tick':4,'enqueued_ns':200,'pending_count':1},
                  {'type':'worker_unusable_transition','check_ns':350,'processed_ns':360,'reason':'worker_process_exited','pending_before':True,'pending_after':False,'candidate_after':False,'cleared_pending_target_tick':4},
                  {'type':'diagnostic_preparation_barrier_release','target_tick':3,'released_ns':370,'cancelled':True,'worker_unusable':True,'pending_after':False},
                  {'type':'job_not_submitted','target_tick':3,'reason':'worker_unusable_after_preparation_barrier','processed_ns':380}]
        self.fault={'ns':300,'barrier_active_target_tick':3,'observed_preparation_pending_target_tick':4,'observed_preparation_pending_enqueue_ns':200,'active_job':0,'pending_count':0}
        self.fixture=[{'type':'post_fault_observation_end','ns':1_400_000_300}]
        self.jobs=[{'job':{'target_tick':1},'submit_commit_ns':80}]
        self.decisions=[{'activation_commit_ns':90,'accepted':True,'reason':''}]+[
            {'activation_commit_ns':400+i*200_000_000,'accepted':False,'reason':'worker_unusable'} for i in range(6)]
    def result(self):return pending_proof(self.reg,self.fixture,self.fault,self.jobs,self.decisions)
    def assert_fails(self):self.assertFalse(self.result()['mechanism_complete'])
    def test_complete(self):self.assertTrue(self.result()['mechanism_complete'])
    def test_empty_pending_before(self):self.reg[2]['pending_before']=False;self.assert_fails()
    def test_nonempty_after(self):self.reg[2]['pending_after']=True;self.assert_fails()
    def test_wrong_cleared_identity(self):self.reg[2]['cleared_pending_target_tick']=5;self.assert_fails()
    def test_queue_count_not_one(self):self.reg[1]['pending_count']=2;self.assert_fails()
    def test_active_pending_conflated(self):self.reg[1]['target_tick']=3;self.assert_fails()
    def test_missing_queue(self):self.reg.pop(1);self.assert_fails()
    def test_missing_release(self):self.reg.pop(3);self.assert_fails()
    def test_not_cancelled(self):self.reg[3]['cancelled']=False;self.assert_fails()
    def test_pending_on_release(self):self.reg[3]['pending_after']=True;self.assert_fails()
    def test_missing_discard(self):self.reg.pop(4);self.assert_fails()
    def test_active_submitted(self):self.jobs[0]['job']['target_tick']=3;self.assert_fails()
    def test_pending_submitted(self):self.jobs[0]['job']['target_tick']=4;self.assert_fails()
    def test_new_commit(self):self.jobs[0]['submit_commit_ns']=351;self.assert_fails()
    def test_new_acceptance(self):self.decisions[-1]['accepted']=True;self.assert_fails()
    def test_no_native_prefix(self):self.decisions[0]['accepted']=False;self.assert_fails()
    def test_unobserved_queue_premise(self):self.fault['observed_preparation_pending_enqueue_ns']=199;self.assert_fails()
    def test_queue_refill_after_exit(self):self.reg.append({'type':'diagnostic_preparation_pending_enqueued','target_tick':5,'pending_count':1,'enqueued_ns':355});self.assert_fails()
    def test_unbounded_release(self):self.reg[3]['released_ns']=3_100_000_101;self.assert_fails()
    def test_short_observation(self):self.fixture[0]['ns']=1_199_999_999;self.assert_fails()

if __name__=='__main__':unittest.main()
