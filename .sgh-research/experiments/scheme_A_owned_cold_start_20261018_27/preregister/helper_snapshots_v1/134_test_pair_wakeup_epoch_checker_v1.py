"""Temporal Source reconstruction and tampering boundaries."""
import copy,unittest
import check_pair_wakeup_v1 as p
from test_pair_wakeup_v1 import messages
def reference_messages():return messages([(.05*(.2*k),0.,0.) for k in range(201)],[.2*k for k in range(201)],.05)
def target():return [0.,0.,0.,0.,0.,0.]
def records():
 j=dict(job_id=7,target_sim_ns=100000000000,task_generation=2,model_generation=1,config_generation=1,schedule_generation=1,clock_epoch=1,run_id='run',boot_id='boot',contract_hash='a'*64,nominal_hash='b'*64)
 first=dict(job=j,submit_commit_ns=10,input_provenance=dict(ref_selection=dict(path_fingerprint='c'*64,profile_fingerprint='d'*64)))
 geometric=p.independent_projection(target(),*reference_messages());r=p.independent_task_time(target(),*reference_messages(),j['target_sim_ns'],0.,j['target_sim_ns']);epoch=p.expected_epoch(first,geometric,first)
 source=dict(reference_mode=p.POLICY,reference_projection=r['geometric']['projection'],reference_epoch=epoch,configured_start_offset=0,effective_start_offset=0,nearest_index=r['geometric']['nearest_index'],start_index=r['start_index'],profile_t0=r['profile_t0'])
 return first,r,epoch,source
class TaskTimeEpochCheckerTests(unittest.TestCase):
 def test_first_reference_exact_G(self):
  _,r,_,_=records();self.assertEqual(r['reference'],r['geometric']['reference'])
 def test_advances_time_even_while_state_stays_still(self):
  r=p.independent_task_time(target(),*reference_messages(),100000000000,0.,101000000000);self.assertEqual(r['profile_t0'],1.);self.assertEqual(r['reference'][0],.05);self.assertEqual(r['geometric']['projection']['profile_t0'],0.)
 def test_exact_source_metadata_passes(self):
  _,r,e,s=records();self.assertTrue(p.task_time_metadata_matches(s,r,e))
 def test_each_epoch_field_is_required(self):
  _,r,e,s=records()
  for k in e:
   bad=copy.deepcopy(s);del bad['reference_epoch'][k];self.assertFalse(p.task_time_metadata_matches(bad,r,e),k)
 def test_epoch_tuple_and_binding_tampering_fails(self):
  _,r,e,s=records()
  for k,v in e.items():
   bad=copy.deepcopy(s);bad['reference_epoch'][k]=v+.001 if type(v) is float else v+1 if type(v) is int else v+'x';self.assertFalse(p.task_time_metadata_matches(bad,r,e),k)
 def test_boolean_identity_or_zero_offset_is_not_integer(self):
  _,r,e,s=records()
  for k in ['first_job_id','first_target_sim_ns','task_generation','clock_epoch']:
   bad=copy.deepcopy(s);bad['reference_epoch'][k]=True;self.assertFalse(p.task_time_metadata_matches(bad,r,e))
  bad=copy.deepcopy(s);bad['configured_start_offset']=False;self.assertFalse(p.task_time_metadata_matches(bad,r,e))
 def test_unknown_epoch_fields_and_foreign_policy_fail(self):
  _,r,e,s=records();bad=copy.deepcopy(s);bad['reference_epoch']['unknown']=0;self.assertFalse(p.task_time_metadata_matches(bad,r,e));bad=copy.deepcopy(s);bad['reference_mode']='projected_profile_time_v1';self.assertFalse(p.task_time_metadata_matches(bad,r,e))
 def test_wrong_clock_or_retroactive_initial_t0_fails(self):
  for first,initial,current in [(100,0.,99),(False,0.,100),(100,float('nan'),100),(100,.1,100)]:
   with self.assertRaises(ValueError):p.independent_task_time(target(),*reference_messages(),first,initial,current)
 def test_tiny_interval_and_changed_geometry_fail(self):
  for kind in ['profile','path']:
   path,profile=reference_messages()
   if kind=='profile':profile['data'][7]=1e-12
   else:path['poses'][4]['pose']['position']['x']+=.001
   with self.assertRaises(ValueError):p.independent_task_time(target(),path,profile,100,0.,200)
 def test_reference_coverage_is_not_clipped(self):
  with self.assertRaises(ValueError):p.independent_task_time(target(),*reference_messages(),1000000000,0.,38000000000)
 def test_epoch_is_derived_from_actual_first_submit(self):
  first,r,e,s=records();self.assertEqual(e['first_job_id'],7);self.assertEqual(e['epoch_submit_commit_ns'],10);self.assertEqual(e['first_target_sim_ns'],first['job']['target_sim_ns']);self.assertEqual(e['initial_profile_t0'],r['geometric']['projection']['profile_t0'])
if __name__=='__main__':unittest.main()
