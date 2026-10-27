"""Finite adversarial checks for the A predicate; no ROS participant is started."""
import copy,unittest
from check_positive_chain_v1 import (path_zero,profile_zero,fixture_manifest_zero,
    zero_vector,positive_window,c36,FLAGS,odometry_zero,imu_zero)
def path():
 h={'frame_id':'map','stamp':{'sec':100,'nanosec':1234}}
 p={'header':h,'pose':{'position':dict(x=0.0,y=0.0,z=0.0),'orientation':dict(x=0.0,y=0.0,z=0.0,w=1.0)}}
 return {'header':h,'poses':[copy.deepcopy(p) for _ in range(61)]}
def profile():
 return {'layout':{'data_offset':0,'dim':[dict(label='stamp_sec:100',size=61,stride=244),dict(label='stamp_nanosec:1234',size=4,stride=4)]},'data':[v for k in range(61) for v in (0.0,0.0,0.0,0.2*k)]}
def population():
 rows=[{'type':'legacy_ready','readiness':{'legacy_ready_ns':100}},
       {'type':'adapter_driver_close_observed','requested_ns':500,'observed_ns':600,'owner_process_alive':True},
       {'type':'adapter_applied_callback','processed_ns':150,'owner_process_alive':True,'authentication_reason':'','queued_terminal_tail':False}]
 for k in range(10):rows.append({'type':'decision','activation_commit_ns':200+k,'accepted':True,'reason':'','control_source':'candidate','job_id':1+k,'tick':1+k,'skipped_ticks':0,'schedule_generation':1,'task_generation':1,'model_generation':1,'config_generation':1,'epoch':0})
 return rows,{'proof_ns':700},[{'type':'signal','name':'publisher','monotonic_ns':650,'signal':2}]
class PositivePredicateTests(unittest.TestCase):
 def test_actual_Odometry_predicate_rejects_nonzero_pose_velocity_or_bad_orientation(self):
  xyz=dict(x=0.0,y=0.0,z=0.0);q=dict(x=0.0,y=0.0,z=0.0,w=1.0)
  good={'pose':{'pose':{'position':xyz,'orientation':q}},'twist':{'twist':{'linear':xyz,'angular':xyz}}}
  self.assertTrue(odometry_zero(good))
  for section,key in [('pose','position'),('pose','orientation'),('twist','linear'),('twist','angular')]:
   bad=copy.deepcopy(good);bad[section][section][key]['x']=1e-300;self.assertFalse(odometry_zero(bad))
 def test_actual_Imu_predicate_rejects_nonzero_rates_or_acceleration(self):
  good={'orientation':dict(x=0.0,y=0.0,z=0.0,w=1.0),'angular_velocity':dict(x=0.0,y=0.0,z=0.0),'linear_acceleration':dict(x=0.0,y=0.0,z=0.0)}
  self.assertTrue(imu_zero(good))
  for key,value in [('orientation',1.0),('angular_velocity',float('nan')),('linear_acceleration',True)]:
   bad=copy.deepcopy(good);bad[key]['x']=value;self.assertFalse(imu_zero(bad))
 def check_window(self,rows=None,proof=None,ledger=None):
  original=population();c=c36.Checks();r=positive_window(original[0] if rows is None else rows,original[1] if proof is None else proof,original[2] if ledger is None else ledger,c);return r,c
 def test_valid_zero_Path_and_profile(self):self.assertTrue(path_zero(path()));self.assertTrue(profile_zero(profile()))
 def test_nonzero_Path_at_last_point_fails(self):
  m=path();m['poses'][-1]['pose']['position']['x']=1e-300;self.assertFalse(path_zero(m))
 def test_bad_quaternion_stamp_or_frame_fails(self):
  for key,value in [('w',0.0),('x',float('nan'))]:
   m=path();m['poses'][0]['pose']['orientation'][key]=value;self.assertFalse(path_zero(m))
  m=path();m['header']['frame_id']='odom';self.assertFalse(path_zero(m))
  m=path();m['poses'][0]['header']['stamp']['nanosec']=False;self.assertFalse(path_zero(m))
 def test_nonzero_profile_velocity_yaw_or_acceleration_fails(self):
  for field in range(3):
   m=profile();m['data'][4*60+field]=1e-300;self.assertFalse(profile_zero(m))
 def test_repeated_reversed_nonfinite_profile_time_fails(self):
  for value in (0.0,-1.0,float('nan'),float('inf'),True):
   m=profile();m['data'][7]=value;self.assertFalse(profile_zero(m))
 def test_profile_malformed_layout_fails(self):
  for key,value in [('size',60),('stride',243),('label','stamp_sec:0100')]:
   m=profile();m['layout']['dim'][0][key]=value;self.assertFalse(profile_zero(m))
  m=profile();m['data'].pop();self.assertFalse(profile_zero(m))
 def test_zero_does_not_accept_boolean_nonfinite_or_wrong_size(self):
  for value in ([False,0.0],[0.0,float('nan')],[0.0,float('inf')],[0.0],[1e-300,0.0]):self.assertFalse(zero_vector(value,2))
 def test_manifest_needs_explicit_new_fixture_kind(self):
  m=dict(role='synthetic_source',synthetic=True,plant_connected=False,source_state='stationary_zero',reference_kind='stationary_zero_equilibrium',reference_speed_m_s=0.0)
  self.assertTrue(fixture_manifest_zero(m))
  for key,value in [('reference_kind','moving'),('reference_speed_m_s',0.6),('reference_speed_m_s',False),('plant_connected',True),('synthetic',1)]:
   bad=dict(m);bad[key]=value;self.assertFalse(fixture_manifest_zero(bad))
 def test_ten_continuous_live_owner_activations_pass(self):
  result,c=self.check_window();self.assertFalse(c.issues);self.assertEqual(result['consecutive_accepted'],10)
 def test_nine_is_insufficient(self):
  rows,_,_=population();rows.pop();r,c=self.check_window(rows);self.assertEqual(r['consecutive_accepted'],9);self.assertTrue(c.issues)
 def test_all_rejected_does_not_pass_base_observation_as_positive(self):
  rows,_,_=population()
  for d in rows[3:]:d.update(accepted=False,reason='anchor_mismatch',control_source='ramp_zero')
  r,c=self.check_window(rows);self.assertEqual(r['accepted'],0);self.assertTrue(c.issues)
 def test_accepted_after_close_request_never_counted(self):
  rows,_,_=population()
  for d in rows[3:]:d['activation_commit_ns']+=500
  r,c=self.check_window(rows);self.assertEqual(r['accepted'],0);self.assertTrue(c.issues)
 def test_tick_gap_generation_change_rejection_break_streak(self):
  for kind in ('tick','generation','rejected','skipped'):
   rows,_,_=population();d=rows[7]
   if kind=='tick':d['tick']+=2
   elif kind=='generation':d['schedule_generation']+=1
   elif kind=='rejected':d.update(accepted=False,reason='anchor_mismatch')
   else:d['skipped_ticks']=1
   r,c=self.check_window(rows);self.assertLess(r['consecutive_accepted'],10);self.assertTrue(c.issues)
 def test_duplicate_accepted_job_identity_fails(self):
  rows,_,_=population();rows[-1]['job_id']=1;_,c=self.check_window(rows);self.assertTrue(any(x['code']=='A_accepted_job_identity_unique' for x in c.issues))
 def test_owner_dead_early_signal_or_tail_receipt_fails(self):
  rows,proof,ledger=population();rows[1]['owner_process_alive']=False;self.assertTrue(self.check_window(rows)[1].issues)
  rows,proof,ledger=population();ledger[0]['monotonic_ns']=450;self.assertTrue(self.check_window(rows,proof,ledger)[1].issues)
  rows,_,_=population();rows[2].update(owner_process_alive=False,queued_terminal_tail=True);self.assertTrue(self.check_window(rows)[1].issues)
 def test_invalidated_readiness_and_early_exit_fail(self):
  rows,_,_=population();rows.append({'type':'legacy_ready_invalidated','check_ns':250});self.assertTrue(self.check_window(rows)[1].issues)
  self.assertTrue(self.check_window(proof={'proof_ns':550})[1].issues)
 def test_missing_or_duplicate_ready_and_close_fail(self):
  rows,_,_=population();rows.pop(0);self.assertTrue(self.check_window(rows)[1].issues)
  rows,_,_=population();rows.append(copy.deepcopy(rows[1]));self.assertTrue(self.check_window(rows)[1].issues)
 def test_no_phase_or_research_qualification(self):self.assertTrue(FLAGS);self.assertTrue(all(v is False for v in FLAGS.values()))
if __name__=='__main__':unittest.main()
