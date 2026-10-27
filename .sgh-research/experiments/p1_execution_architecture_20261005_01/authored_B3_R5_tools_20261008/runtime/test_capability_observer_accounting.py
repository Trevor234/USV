import copy,unittest
from p1_capability_observer_accounting import account_capability_receipts

class CapabilityObservation(unittest.TestCase):
    def setUp(self):
        idle={'active_job':0,'pending_count':0,'completed_jobs':0,'fatal':False}
        self.actual=[{'payload_sha256':'idle','bag_receive_wall_ns':10,'message':dict(idle)},
                     {'payload_sha256':'idle','bag_receive_wall_ns':20,'message':dict(idle)},
                     {'payload_sha256':'active','bag_receive_wall_ns':40,'message':dict(idle,active_job=1)}]
        self.observed=[{'payload_sha256':'idle'},{'payload_sha256':'active'}]
        self.first=30
    def result(self):return account_capability_receipts(self.observed,self.actual,self.first)
    def test_bounded_bootstrap(self):self.assertEqual(self.result()['issues'],[])
    def test_no_prefix_full_equal(self):
        self.actual=self.actual[1:];self.assertEqual(self.result()['issues'],[])
    def test_late_unobserved_prefix(self):
        self.actual[0]['bag_receive_wall_ns']=30;self.assertTrue(self.result()['issues'])
    def test_unobserved_active_prefix(self):
        self.actual[0]['message']['active_job']=1;self.assertTrue(self.result()['issues'])
    def test_unobserved_completed_prefix(self):
        self.actual[0]['message']['completed_jobs']=1;self.assertTrue(self.result()['issues'])
    def test_unobserved_pending_prefix(self):
        self.actual[0]['message']['pending_count']=1;self.assertTrue(self.result()['issues'])
    def test_unobserved_fatal_prefix(self):
        self.actual[0]['message']['fatal']=True;self.assertTrue(self.result()['issues'])
    def test_missing_clock(self):
        self.first=None;self.assertTrue(self.result()['issues'])
    def test_tail_missing(self):
        self.observed.pop();self.assertTrue(self.result()['issues'])
    def test_middle_payload_loss(self):
        self.observed[0]['payload_sha256']='other';self.assertTrue(self.result()['issues'])
    def test_extra_observer(self):
        self.observed*=2;self.assertTrue(self.result()['issues'])

if __name__=='__main__':unittest.main()
