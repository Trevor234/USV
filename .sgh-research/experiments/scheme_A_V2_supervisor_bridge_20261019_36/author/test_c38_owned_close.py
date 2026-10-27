import unittest
from copy import deepcopy
from check_c38_owned_close import tail_permitted
class TailTests(unittest.TestCase):
 def setUp(self):
  self.m={'control_source':'shutdown_zero','final_n':[0.,0.],'left_publish_success':True,'right_publish_success':True,'left_publish_start_steady_ns':1200,'left_publish_end_steady_ns':1300,'right_publish_start_steady_ns':1400,'right_publish_end_steady_ns':1500}
 def ok(self,m=None,auth='owner_process_exited',gid=True,request=1000,observed=1100,receipt=2000):return tail_permitted(self.m if m is None else m,auth,gid,request,observed,receipt)
 def test_exact_exit_zero(self):self.assertTrue(self.ok())
 def test_live_and_foreign_do_not_use_exception(self):
  self.assertFalse(self.ok(auth=''));self.assertFalse(self.ok(auth='callback_foreign_gid'));self.assertFalse(self.ok(gid=False))
 def test_exact_deadline(self):self.assertTrue(self.ok(receipt=2_000_001_000));self.assertFalse(self.ok(receipt=2_000_001_001))
 def test_before_request_call(self):self.assertFalse(self.ok(request=1250,observed=1300))
 def test_unobserved_future_and_bool_times(self):
  for kw in [{'request':0},{'observed':999},{'receipt':1099},{'request':True}]:self.assertFalse(self.ok(**kw))
 def test_nonzero_nonfinite_wrong_shape_and_boolean(self):
  for n in [[1.,0.],[0.,float('nan')],[0.,float('inf')],[False,0.],[0.],None]:
   m=deepcopy(self.m);m['final_n']=n;self.assertFalse(self.ok(m))
 def test_failed_or_unattempted_calls(self):
  for key in ['left_publish_success','right_publish_success']:
   for value in [False,1,None]:
    m=deepcopy(self.m);m[key]=value;self.assertFalse(self.ok(m))
 def test_unordered_and_missing_call_times(self):
  for key,val in [('left_publish_start_steady_ns',900),('left_publish_end_steady_ns',1199),('right_publish_start_steady_ns',1299),('right_publish_end_steady_ns',2001),('right_publish_end_steady_ns',None)]:
   m=deepcopy(self.m);m[key]=val;self.assertFalse(self.ok(m))
 def test_shutdown_tag_exact(self):
  m=deepcopy(self.m);m['control_source']='nmpc';self.assertFalse(self.ok(m))
if __name__=='__main__':unittest.main()
