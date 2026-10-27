"""Finite adversarial predicates for the controlled prototype; no ROS run."""
import copy
import json
import math
from pathlib import Path
import unittest
import check_controlled_v1 as q
from test_positive_chain_v1 import path, profile, population


def fixture():
 origin=1_000_000_000
 a=dict(run_id='owner',baseline_id=q.BASELINE,producer_instance_id='producer',
        steady_clock_domain='boot:steady_clock',sequence=5,final_n=[0.,0.],
        left_publish_success=True,right_publish_success=True,
        left_publish_start_steady_ns=origin+1_000,left_publish_end_steady_ns=origin+1_500,
        right_publish_start_steady_ns=origin+2_000,right_publish_end_steady_ns=origin+2_500)
 p=dict(schema='p1-controlled-owner-phase-v1',run_id='owner',boot_id='boot',contract_sha256='a'*64,
        baseline_id=q.BASELINE,producer_instance_id='producer',decision_sequence=3,tick=2,
        planned_ns=origin,applied_sequence=5,command_n=[0.,0.],
        start_ns=[origin+1_000,origin+2_000],end_ns=[origin+1_500,origin+2_500],
        held_until_ns=origin+200_000_000,emitted_ns=origin+3_000,
        stage_qualified=False,execute_qualified=False)
 g=dict(freeze_ns=origin+10_000,tick=2,target_tick=3,planned_ns=origin,
        deadline_ns=origin+150_000_000,target_ns=origin+200_000_000,
        held_until_ns=origin+200_000_000,command_n=[0.,0.],applied_sequence=5,
        phase_applied_sequence=5,decision_sequence=3,phase_emitted_ns=p['emitted_ns'],
        phase_command_n=p['command_n'],phase_start_ns=p['start_ns'],phase_end_ns=p['end_ns'])
 j=dict(job_id=7,freeze_ns=g['freeze_ns'],target_tick=3,tick_origin_ns=origin,
        deadline_ns=g['deadline_ns'],target_ns=g['target_ns'],anchor_n=[0.,0.],
        anchor_sequence=[5,5],anchor_publish_ns=p['start_ns'])
 return g,j,a,p


class ControlledPredicateTests(unittest.TestCase):
 def test_valid_exact_freeze(self):self.assertTrue(q.freeze_matches(*fixture()))
 def test_same_value_heartbeat_latest_sequence_may_exceed_phase_sequence(self):
  g,j,a,p=fixture();a['sequence']=6;a['left_publish_start_steady_ns']+=4_000;a['left_publish_end_steady_ns']+=4_000;a['right_publish_start_steady_ns']+=4_000;a['right_publish_end_steady_ns']+=4_000
  g['applied_sequence']=6;j['anchor_sequence']=[6,6];j['anchor_publish_ns']=[a['left_publish_start_steady_ns'],a['right_publish_start_steady_ns']]
  self.assertTrue(q.freeze_matches(g,j,a,p))
 def test_changed_latest_value_cannot_borrow_old_phase(self):
  g,j,a,p=fixture();a['sequence']=6;a['final_n']=[.1,.1];g['applied_sequence']=6;g['command_n']=[.1,.1];j['anchor_sequence']=[6,6];j['anchor_n']=[.1,.1]
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_future_phase_sequence_rejected(self):
  g,j,a,p=fixture();g['phase_applied_sequence']=p['applied_sequence']=6
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_extended_ready_deadline_rejected(self):
  g,j,a,p=fixture();g['deadline_ns']=j['deadline_ns']=g['planned_ns']+160_000_000
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_shifted_target_rejected(self):
  g,j,a,p=fixture();g['target_ns']=j['target_ns']=g['held_until_ns']=g['planned_ns']+210_000_000
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_freeze_after_original_deadline_rejected(self):
  g,j,a,p=fixture();g['freeze_ns']=j['freeze_ns']=j['deadline_ns']+1
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_phase_emitted_after_freeze_rejected(self):
  g,j,a,p=fixture();p['emitted_ns']=g['phase_emitted_ns']=g['freeze_ns']+1
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_wrong_anchor_call_start_rejected(self):
  g,j,a,p=fixture();j['anchor_publish_ns'][1]+=1
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_missing_job_field_rejected(self):
  g,j,a,p=fixture();del j['anchor_sequence']
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_forged_shorter_wire_hold_cannot_borrow_Source_grant(self):
  g,j,a,p=fixture();p['held_until_ns']-=1
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_forged_Source_phase_call_end_rejected(self):
  g,j,a,p=fixture();g['phase_end_ns']=list(g['phase_end_ns']);g['phase_end_ns'][1]+=1
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_forged_Source_phase_command_rejected(self):
  g,j,a,p=fixture();g['phase_command_n']=[.1,.1]
  self.assertFalse(q.freeze_matches(g,j,a,p))
 def test_actual_Applied_has_domain_not_boot_id(self):
  _,_,a,p=fixture();self.assertNotIn('boot_id',a)
  self.assertTrue(q.phase_applied_matches(p,a))
 def test_wrong_phase_boot_domain_rejected(self):
  _,_,a,p=fixture();p['boot_id']='other-boot'
  self.assertFalse(q.phase_applied_matches(p,a))
 def test_phase_payload_cannot_change_real_command_or_call_times(self):
  for key,value in [('command_n',[1e-300,0.]),('start_ns',[1,2]),('end_ns',[3,4]),('applied_sequence',6)]:
   _,_,a,p=fixture();p[key]=value;self.assertFalse(q.phase_applied_matches(p,a),key)
 def test_partial_or_failed_pair_cannot_authorize_phase(self):
  for key in ['left_publish_success','right_publish_success']:
   _,_,a,p=fixture();a[key]=False;self.assertFalse(q.phase_applied_matches(p,a))
 def test_phase_cannot_precede_actual_call_completion(self):
  _,_,a,p=fixture();p['emitted_ns']=a['right_publish_end_steady_ns']-1
  self.assertFalse(q.phase_applied_matches(p,a))
 def test_B_changed_input_inside_window_is_located(self):
  g,j,a,p=fixture();a['final_n']=[.1,.1];d={'activation_commit_ns':j['target_ns']}
  for key in ['left_publish_start_steady_ns','left_publish_end_steady_ns','right_publish_start_steady_ns','right_publish_end_steady_ns']:a[key]+=100_000_000
  self.assertEqual(q.changed_window(j,d,[a]),[a])
 def test_B_same_value_heartbeat_is_not_changed_input(self):
  _,j,a,_=fixture();d={'activation_commit_ns':j['target_ns']}
  for key in ['left_publish_start_steady_ns','left_publish_end_steady_ns','right_publish_start_steady_ns','right_publish_end_steady_ns']:a[key]+=100_000_000
  self.assertEqual(q.changed_window(j,d,[a]),[])
 def test_B_change_after_activation_does_not_explain_prior_rejection(self):
  _,j,a,_=fixture();a['final_n']=[.1,.1];d={'activation_commit_ns':j['target_ns']}
  for key in ['left_publish_start_steady_ns','left_publish_end_steady_ns','right_publish_start_steady_ns','right_publish_end_steady_ns']:a[key]+=300_000_000
  self.assertEqual(q.changed_window(j,d,[a]),[])
 def test_zero_state_reference_predicates_are_exact(self):
  self.assertTrue(q.positive.path_zero(path()));self.assertTrue(q.positive.profile_zero(profile()))
  m=profile();m['data'][0]=.05;self.assertFalse(q.positive.profile_zero(m))
  m=path();m['poses'][-1]['pose']['position']['x']=1e-300;self.assertFalse(q.positive.path_zero(m))
 def test_rejected_or_dropped_activation_breaks_positive_streak(self):
  rows,proof,ledger=population();rows[7].update(accepted=False,reason='anchor_mismatch',control_source='ramp_zero')
  checks=q.c36.Checks();result=q.positive.positive_window(rows,proof,ledger,checks)
  self.assertLess(result['consecutive_accepted'],10);self.assertTrue(checks.issues)
 def test_real_Odometry_and_Imu_helpers_exist(self):
  self.assertTrue(callable(q.positive.odometry_zero));self.assertTrue(callable(q.positive.imu_zero))
 def test_zero_rejects_boolean_nonfinite_and_nonzero(self):
  for v in [[False,0.],[float('nan'),0.],[float('inf'),0.],[1e-300,0.]]:self.assertFalse(q.zero(v))


class NominalReplayTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.hydro=json.loads((Path(__file__).parent/'controlled_contract_v1.json').read_text())['hydro']
 def row(self):return dict(initial_state=[0.]*6,origin_ns=1_000_000_000,target_ns=1_010_000_000,integration_substep_max_ns=2_000_000,rk4_substeps=4,held_events=[])
 def test_zero_equilibrium_remains_exact_zero(self):self.assertEqual(q.replay(self.row(),self.hydro),[0.]*6)
 def test_actual_nonzero_history_generates_nonzero_surge(self):
  row=self.row();row['held_events']=[dict(publish_end_ns=row['origin_ns'],channel=ch,n=.1,applied_sequence=1) for ch in [0,1]]
  state=q.replay(row,self.hydro);self.assertGreater(state[0],0);self.assertGreater(state[3],0);self.assertEqual(state[1:3],[0.,0.]);self.assertEqual(state[4:],[0.,0.])
 def test_dropping_real_input_history_changes_recomputed_state(self):
  row=self.row();row['held_events']=[dict(publish_end_ns=row['origin_ns'],channel=ch,n=.1,applied_sequence=1) for ch in [0,1]]
  state=q.replay(row,self.hydro);row['held_events']=[];self.assertNotEqual(q.replay(row,self.hydro),state)
 def test_future_input_does_not_affect_earlier_state(self):
  row=self.row();row['held_events']=[dict(publish_end_ns=row['target_ns']+1,channel=0,n=.1,applied_sequence=1)]
  self.assertEqual(q.replay(row,self.hydro),[0.]*6)
 def test_invalid_integration_budget_rejected(self):
  for key,value in [('integration_substep_max_ns',2_000_001),('rk4_substeps',3),('initial_state',[0.]*5)]:
   row=self.row();row[key]=value
   with self.assertRaises((AssertionError,ValueError)):q.replay(row,self.hydro)
 def test_invalid_channel_and_nonfinite_input_rejected(self):
  for channel,n in [(2,.1),(0,float('nan')),(0,float('inf'))]:
   row=self.row();row['held_events']=[dict(publish_end_ns=row['origin_ns'],channel=channel,n=n,applied_sequence=1)]
   with self.assertRaises((AssertionError,ValueError)):q.replay(row,self.hydro)
 def test_ODE_satisfies_independent_mass_Coriolis_damping_balance(self):
  p=self.hydro;x=[.3,-.1,.4,.7,-.2,.15];n=[1.2,-.8];dx=q.ode(x,n,p);u,v,r=x[3:]
  m11=p['mass']-p['Xu_dot'];m22=p['mass']-p['Yv_dot'];m23=p['mass']*p['xg']-p['Yr_dot'];m32=p['mass']*p['xg']-p['Nv_dot'];m33=p['Iz']-p['Nr_dot']
  c13=-m22*v-m23*r;c23=m11*u
  lhs=[m11*dx[3]+c13*r+(-p['Xu']-p['Xuu']*abs(u))*u,
       m22*dx[4]+m23*dx[5]+c23*r+(-p['Yv']-p['Yvv']*abs(v))*v+(-p['Yr']-p['Yrr']*abs(r))*r,
       m32*dx[4]+m33*dx[5]-c13*u-c23*v+(-p['Nv']-p['Nvv']*abs(v))*v+(-p['Nr']-p['Nrr']*abs(r))*r]
  for actual,expected in zip(lhs,[sum(n),0.,p['d_thruster']*(n[1]-n[0])]):self.assertAlmostEqual(actual,expected,places=12)


class ActualModelMappingTests(unittest.TestCase):
 def prefix(self):
  events=[dict(publish_end_ns=100,channel=0,n=.1,applied_sequence=1),
          dict(publish_end_ns=101,channel=1,n=.1,applied_sequence=1),
          dict(publish_end_ns=250,channel=0,n=.2,applied_sequence=2)]
  row=dict(target_ns=200,held_events=copy.deepcopy(events[:2]),applied_received_watermark=2,applied_accepted_watermark=2)
  return row,events
 def sensors(self):
  x=[.1,.2,.3,.4,-.1,.05];z=dict(x=0.,y=0.,z=0.)
  stamp=dict(sec=100,nanosec=20_000_000);quat=dict(x=0.,y=0.,z=math.sin(x[2]/2),w=math.cos(x[2]/2))
  row=dict(state=x,origin_ns=1_000_000_000,target_ns=1_020_000_000,sim_stamp_ns=100_020_000_000)
  o=dict(header=dict(frame_id='map',stamp=copy.deepcopy(stamp)),child_frame_id='wamv/base_link',
         pose=dict(pose=dict(position=dict(x=x[0],y=x[1],z=0.),orientation=copy.deepcopy(quat))),
         twist=dict(twist=dict(linear=dict(x=x[3],y=x[4],z=0.),angular=dict(x=0.,y=0.,z=x[5]))))
  i=dict(header=dict(frame_id='wamv/wamv/base_link/imu_sensor',stamp=copy.deepcopy(stamp)),
         orientation=copy.deepcopy(quat),angular_velocity=dict(x=0.,y=0.,z=x[5]),linear_acceleration=z)
  return row,o,i
 def test_complete_received_prefix_passes_without_future_event(self):
  row,events=self.prefix();self.assertTrue(q.received_prefix_matches(row,events,2,2))
 def test_missing_already_received_channel_event_rejected(self):
  row,events=self.prefix();row['held_events'].pop();self.assertFalse(q.received_prefix_matches(row,events,2,2))
 def test_including_future_event_rejected(self):
  row,events=self.prefix();row['held_events'].append(events[-1]);self.assertFalse(q.received_prefix_matches(row,events,2,2))
 def test_forged_input_value_or_sequence_rejected(self):
  for key,value in [('n',.2),('applied_sequence',3),('publish_end_ns',99),('channel',1)]:
   row,events=self.prefix();row['held_events'][0][key]=value;self.assertFalse(q.received_prefix_matches(row,events,2,2),key)
 def test_duplicate_prefix_event_rejected(self):
  row,events=self.prefix();row['held_events'].append(copy.deepcopy(row['held_events'][0]));self.assertFalse(q.received_prefix_matches(row,events,2,2))
 def test_forged_received_or_accepted_watermark_rejected(self):
  for key,value in [('applied_received_watermark',1),('applied_accepted_watermark',1),('applied_received_watermark',False),('applied_accepted_watermark',2.)]:
   row,events=self.prefix();row[key]=value;self.assertFalse(q.received_prefix_matches(row,events,2,2),key)
 def test_complete_nonzero_actual_sensor_mapping_passes(self):self.assertTrue(q.sensor_state_matches(*self.sensors()))
 def test_wrong_StoredOdometry_stamp_rejected(self):
  row,o,i=self.sensors();o['header']['stamp']['nanosec']+=1;self.assertFalse(q.sensor_state_matches(row,o,i))
 def test_wrong_StoredImu_stamp_rejected(self):
  row,o,i=self.sensors();i['header']['stamp']['nanosec']+=1;self.assertFalse(q.sensor_state_matches(row,o,i))
 def test_forged_model_stamp_or_time_origin_rejected(self):
  for key in ['sim_stamp_ns','target_ns','origin_ns']:
   row,o,i=self.sensors();row[key]+=1;self.assertFalse(q.sensor_state_matches(row,o,i),key)
 def test_wrong_sensor_frame_or_child_frame_rejected(self):
  for which in ['odom','child','imu']:
   row,o,i=self.sensors()
   if which=='odom':o['header']['frame_id']='odom'
   elif which=='child':o['child_frame_id']='base_link'
   else:i['header']['frame_id']='imu'
   self.assertFalse(q.sensor_state_matches(row,o,i),which)
 def test_wrong_actual_position_velocity_or_yaw_rate_rejected(self):
  for which in ['position','surge','sway','yaw_rate','imu_rate']:
   row,o,i=self.sensors()
   target={'position':o['pose']['pose']['position'],'surge':o['twist']['twist']['linear'],
           'sway':o['twist']['twist']['linear'],'yaw_rate':o['twist']['twist']['angular'],'imu_rate':i['angular_velocity']}[which]
   key='y' if which=='sway' else ('z' if 'rate' in which else 'x');target[key]+=1e-6
   self.assertFalse(q.sensor_state_matches(row,o,i),which)
 def test_wrong_quaternion_in_either_actual_sensor_rejected(self):
  for which in ['odom','imu']:
   row,o,i=self.sensors();target=o['pose']['pose']['orientation'] if which=='odom' else i['orientation'];target['w']+=1e-6
   self.assertFalse(q.sensor_state_matches(row,o,i),which)
 def test_nonzero_unmodelled_heave_roll_or_pitch_rejected(self):
  for which in ['heave','linear_z','roll_rate','pitch_rate','imu_roll']:
   row,o,i=self.sensors()
   target,key={'heave':(o['pose']['pose']['position'],'z'),'linear_z':(o['twist']['twist']['linear'],'z'),
               'roll_rate':(o['twist']['twist']['angular'],'x'),'pitch_rate':(o['twist']['twist']['angular'],'y'),
               'imu_roll':(i['angular_velocity'],'x')}[which]
   target[key]=.01;self.assertFalse(q.sensor_state_matches(row,o,i),which)
 def test_model_nonfinite_boolean_or_missing_state_rejected(self):
  for value in [[False,0.,0.,0.,0.,0.],[float('nan'),0.,0.,0.,0.,0.],[0.]*5]:
   row,o,i=self.sensors();row['state']=value;self.assertFalse(q.sensor_state_matches(row,o,i))
 def test_missing_actual_sensor_payload_field_rejected(self):
  row,o,i=self.sensors();del i['angular_velocity'];self.assertFalse(q.sensor_state_matches(row,o,i))


if __name__=='__main__':unittest.main()
