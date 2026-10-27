import unittest
from check_controlled_v2 import phase_metadata_matches,base
class CaptureOrder(unittest.TestCase):
 def data(self):
  raw={k:0 for k in base.p.RAW_FIELDS};raw.update(schema='p1-input-callback-full-cdr-v1',topic='/p1/controlled_owner_phase',message_type='std_msgs/msg/String',callback_sequence=1,rmw_implementation='rmw_fastrtps_cpp',from_intra_process=False,entry_steady_ns=12)
  return raw,{'callback_sequence':1,'entry_ns':10,'observed_ns':15,'processed_ns':16},20
 def test_distinct_actual_capture_times(self):self.assertTrue(phase_metadata_matches(*self.data()))
 def test_capture_before_callback(self):
  raw,r,end=self.data();raw['entry_steady_ns']=9;self.assertFalse(phase_metadata_matches(raw,r,end))
 def test_capture_after_observation(self):
  raw,r,end=self.data();raw['entry_steady_ns']=16;self.assertFalse(phase_metadata_matches(raw,r,end))
 def test_processed_after_close(self):
  raw,r,end=self.data();r['processed_ns']=21;self.assertFalse(phase_metadata_matches(raw,r,end))
 def test_intra_process(self):
  raw,r,end=self.data();raw['from_intra_process']=True;self.assertFalse(phase_metadata_matches(raw,r,end))
 def test_wrong_receipt_sequence(self):
  raw,r,end=self.data();raw['callback_sequence']=2;self.assertFalse(phase_metadata_matches(raw,r,end))
if __name__=='__main__':unittest.main()
