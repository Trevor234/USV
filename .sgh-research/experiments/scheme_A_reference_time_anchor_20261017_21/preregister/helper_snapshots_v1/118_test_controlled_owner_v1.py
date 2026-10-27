import copy,unittest
from check_controlled_owner_v1 import ordered_phase,pulse_matches
class OwnerEvidence(unittest.TestCase):
 def phase(self):
  a={'applied_sequence':4,'final_n':[0.,0.],'applied_publish_start_ns':10,'applied_publish_end_ns':20}
  r={'phase':{'applied_sequence':4,'command_n':[0.,0.],'emitted_ns':21,'end_ns':[8,9]},'applied_publish_start_ns':10,'applied_publish_end_ns':20,'phase_publish_start_ns':22,'phase_publish_end_ns':23}
  return r,a
 def test_actual_completed(self):self.assertTrue(ordered_phase(*self.phase()))
 def test_before_Applied_return(self):
  r,a=self.phase();r['phase']['emitted_ns']=19;self.assertFalse(ordered_phase(r,a))
 def test_phase_before_emit(self):
  r,a=self.phase();r['phase_publish_start_ns']=20;self.assertFalse(ordered_phase(r,a))
 def test_wrong_Applied(self):
  r,a=self.phase();r['phase']['applied_sequence']=5;self.assertFalse(ordered_phase(r,a))
 def test_wrong_command(self):
  r,a=self.phase();r['phase']['command_n']=[.1,0];self.assertFalse(ordered_phase(r,a))
 def test_physical_not_completed(self):
  r,a=self.phase();r['phase']['end_ns'][1]=11;self.assertFalse(ordered_phase(r,a))
 def pulse(self):
  j={'job_id':1,'freeze_ns':5,'tick_origin_ns':1,'deadline_ns':150000001}
  a={'sequence':4,'left_publish_start_steady_ns':100000002,'right_publish_end_steady_ns':100000003,'final_n':[.1,.1]}
  r={'job_id':1,'freeze_ns':5,'origin_ns':1,'due_ns':100000001,'physical_return_ns':100000004,'actual_command_n':[.1,.1],'applied_sequence':4}
  return r,j,a
 def test_pulse_actual(self):self.assertTrue(pulse_matches(*self.pulse()))
 def test_pulse_after_deadline(self):
  r,j,a=self.pulse();r['physical_return_ns']=150000001;self.assertFalse(pulse_matches(r,j,a))
 def test_pulse_before_due(self):
  r,j,a=self.pulse();a['left_publish_start_steady_ns']=99999999;self.assertFalse(pulse_matches(r,j,a))
 def test_pulse_wrong_amplitude(self):
  r,j,a=self.pulse();a['final_n']=[.2,.1];self.assertFalse(pulse_matches(r,j,a))
 def test_pulse_wrong_Job(self):
  r,j,a=self.pulse();r['job_id']=2;self.assertFalse(pulse_matches(r,j,a))
 def test_pulse_missing_completion(self):
  r,j,a=self.pulse();del a['right_publish_end_steady_ns'];self.assertFalse(pulse_matches(r,j,a))
if __name__=='__main__':unittest.main()
