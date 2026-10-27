"""Tampering and missing-evidence boundaries for new retry observations."""
import copy,math,unittest
import check_pair_wakeup_v1 as p
from test_pair_wakeup_epoch_checker_v1 import reference_messages
def event():return dict(type='reference_pair_retry',policy=p.RETRY_POLICY,trigger='path',input_commit_ordinal=8,path_sequence=2,profile_sequence=2,path_stamp_ns=101000000000,profile_stamp_ns=101000000000,started_ns=20,completed_ns=30,phase_still_awaiting=False,froze=True,stage_qualified=False)
class PairRetryChecker(unittest.TestCase):
 def test_exact_retry_shape(self):self.assertTrue(p.retry_shape(event()))
 def test_all_fields_are_required_and_extras_fail(self):
  for k in event():
   e=event();del e[k];self.assertFalse(p.retry_shape(e),k)
  e=event();e['extra']=0;self.assertFalse(p.retry_shape(e))
 def test_wrong_policy_or_trigger_fails(self):
  for key,value in [('policy','timer_retry'),('trigger','clock'),('stage_qualified',True)]:
   e=event();e[key]=value;self.assertFalse(p.retry_shape(e))
 def test_boolean_identity_or_time_rejected(self):
  for k in ['input_commit_ordinal','path_sequence','profile_sequence','started_ns','completed_ns','path_stamp_ns','profile_stamp_ns']:
   e=event();e[k]=True;self.assertFalse(p.retry_shape(e),k)
 def test_failed_freeze_keeps_awaiting_and_does_not_pretend_success(self):
  e=event();e['phase_still_awaiting']=True;e['froze']=False;self.assertTrue(p.retry_shape(e));e['froze']=True;self.assertFalse(p.retry_shape(e))
 def test_negative_or_reordered_time_fails(self):
  e=event();e['completed_ns']=19;self.assertFalse(p.retry_shape(e));e=event();e['started_ns']=0;self.assertFalse(p.retry_shape(e))
 def test_temporal_heading_unwrap_preserves_target_turn_count(self):
  target=[0.,0.,2*math.pi+.3,0.,0.,0.];r=p.independent_task_time(target,*reference_messages(),100000000000,0.,101000000000)
  for yaw in r['reference'][2::6]:self.assertAlmostEqual(yaw,2*math.pi)
 def test_missing_actual_Job_is_not_accepted_as_freeze_proof(self):
  c=p.c36.Checks();e=event();observer=[dict(type='path_version',received_sequence=2,input_commit_ordinal=8,processed_ns=15,valid=True,resource_valid=True),dict(type='profile_version',received_sequence=2,input_commit_ordinal=7,processed_ns=14,valid=True,resource_valid=True),dict(type='controlled_phase_freeze',freeze_ns=20,deadline_ns=100,target_tick=3),e]
  p.reference_pair_retry_population(observer,c);self.assertTrue(any(r['code']=='pair_retry_same_stamp_original_deadline_and_actual_submitted_Job' for r in c.issues))
if __name__=='__main__':unittest.main()
