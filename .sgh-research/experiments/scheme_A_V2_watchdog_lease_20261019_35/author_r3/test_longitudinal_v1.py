"""Finite oracle, late-input, reference and coverage checks; no ROS participant."""
import copy,json,math,unittest
from pathlib import Path
import check_longitudinal_v1 as q
HYDRO=json.loads((Path(__file__).parent/'controlled_contract_v1.json').read_text())['hydro']
ORIGIN=1_000_000_000

def event(ns,ch,n,seq):return dict(publish_end_ns=ORIGIN+ns,channel=ch,n=n,applied_sequence=seq)
def row(target,events=()):return dict(origin_ns=ORIGIN,target_ns=ORIGIN+target,initial_state=[0.]*6,state=[0.]*6,integration_substep_max_ns=2_000_000,rk4_substeps=4,held_events=copy.deepcopy(list(events)))
def reference(speed):
 h=dict(frame_id='map',stamp=dict(sec=100,nanosec=1234));poses=[];data=[]
 for k in range(201):
  poses.append(dict(header=copy.deepcopy(h),pose=dict(position=dict(x=speed*(.2*k),y=0.,z=0.),orientation=dict(x=0.,y=0.,z=0.,w=1.))))
  data.extend([speed,0.,0.,.2*k])
 return dict(header=h,poses=poses),dict(layout=dict(data_offset=0,dim=[dict(label='stamp_sec:100',size=201,stride=804),dict(label='stamp_nanosec:1234',size=4,stride=4)]),data=data)
def window():
 start=ORIGIN;end=start+20_000_000_001;rows=[]
 for k in range(100):rows.append(dict(type='decision',activation_commit_ns=start+(k+1)*200_000_000,job_id=k+1,tick=k+1,accepted=True,reason='',control_source='candidate',skipped_ticks=0))
 return dict(start_ready_ns=start,end_driver_requested_ns=end,consecutive_accepted=100),rows

def workrow(target,previous,start,cpbefore,cpafter,steps,events=(),late=(),corrections=0,invalidated=0):
 r=row(target,events);r['integration_steps']=steps;r['work']=dict(schema='p1-nominal-checkpoint-work-v1',algorithm='checkpoint_cached_RK4_replay_v1',cache_before_ns=ORIGIN+previous,cache_after_ns=ORIGIN+target,last_requested_ns=ORIGIN+previous,requested_delta_ns=target-previous,integration_start_ns=ORIGIN+start,integration_target_ns=ORIGIN+target,integrated_ns=target-start,rollback_ns=previous-start,cache_rewound=bool(late),ordinary_incremental=not late,late_event_earliest_ns=ORIGIN+min(late) if late else None,late_channel_events_since_last_sensor=len(late),state_correction_count=corrections,integration_steps=steps,ODE_evaluations=16*steps,checkpoint_count_before=cpbefore,checkpoint_count_after=cpafter,invalidated_checkpoint_count=invalidated,event_element_visits=2*len(events),retained_channel_events=len(events),maximum_channel_events=1024,maximum_event_element_visits=2048,maximum_checkpoints=2048,maximum_integration_steps=512,maximum_full_run_2ms_steps=20000,maximum_run_duration_ns=40_000_000_000,event_retention_policy='retain every authenticated channel event; no clipping or eviction',WCET_qualified=False);return r

class ExactPrefixTests(unittest.TestCase):
 def test_every_short_prefix_matches_original_full_origin_oracle_exactly(self):
  cache=q.ExactPrefixReplay(HYDRO);events=[event(1_250_000,0,.1,1),event(1_270_000,1,.2,1)]
  for k in range(1,31):
   r=row(k*3_107_311,events);self.assertEqual(cache.replay(r),q.replay(r,HYDRO))
 def test_legal_late_input_rewinds_and_matches_full_origin_oracle(self):
  cache=q.ExactPrefixReplay(HYDRO);cache.replay(row(4_500_000))
  r=row(6_100_000,[event(1_250_000,0,.1,1),event(1_270_000,1,.1,1)])
  self.assertEqual(cache.replay(r),q.replay(r,HYDRO));self.assertEqual(cache.rollbacks,1)
 def test_late_event_at_existing_grid_boundary_is_replayed(self):
  cache=q.ExactPrefixReplay(HYDRO);cache.replay(row(8_000_000));r=row(10_000_000,[event(4_000_000,0,.2,1)])
  self.assertEqual(cache.replay(r),q.replay(r,HYDRO));self.assertEqual(cache.rollbacks,1)
 def test_second_late_event_in_earlier_prefix_is_inserted_safely(self):
  cache=q.ExactPrefixReplay(HYDRO);old=[event(1_000_000,0,.1,1)];cache.replay(row(12_000_000,old))
  r=row(14_000_000,old+[event(5_500_000,1,.3,2)])
  self.assertEqual(cache.replay(r),q.replay(r,HYDRO))
 def test_sensor_partial_is_not_a_reusable_canonical_checkpoint(self):
  cache=q.ExactPrefixReplay(HYDRO);events=[event(1_000_000,0,.1,1)];cache.replay(row(3_100_001,events))
  self.assertLess(cache.checkpoints[-1][0],ORIGIN+3_100_001)
  r=row(5_900_003,events);self.assertEqual(cache.replay(r),q.replay(r,HYDRO))
 def test_twenty_seconds_cache_work_is_linear_not_one_full_replay_per_row(self):
  cache=q.ExactPrefixReplay(HYDRO)
  for k in range(1,1001):cache.replay(row(k*20_000_000))
  self.assertEqual(cache.rows,1000);self.assertEqual(cache.integration_steps,10000);self.assertLess(cache.peak_checkpoints,11000)
 def test_self_described_state_never_seeds_independent_replay(self):
  cache=q.ExactPrefixReplay(HYDRO);r=row(20_000_000);r['state']=[99.]*6
  self.assertEqual(cache.replay(r),[0.]*6);self.assertFalse(cache.stats()['Source_state_used_as_seed'])
 def test_dropped_previously_received_event_rejected(self):
  cache=q.ExactPrefixReplay(HYDRO);cache.replay(row(5_000_000,[event(1_000_000,0,.1,1)]))
  with self.assertRaises(ValueError):cache.replay(row(10_000_000))
 def test_mutated_previously_received_event_rejected(self):
  cache=q.ExactPrefixReplay(HYDRO);cache.replay(row(5_000_000,[event(1_000_000,0,.1,1)]))
  with self.assertRaises(ValueError):cache.replay(row(10_000_000,[event(1_000_000,0,.2,1)]))
 def test_duplicate_event_cannot_count_as_new_actual_input(self):
  e=event(1_000_000,0,.1,1)
  with self.assertRaises(ValueError):q.ExactPrefixReplay(HYDRO).replay(row(10_000_000,[e,e]))
 def test_future_event_bool_channel_or_nonfinite_input_rejected(self):
  for e in [event(20_000_000,0,.1,1),event(1_000_000,False,.1,1),event(1_000_000,0,float('nan'),1)]:
   with self.assertRaises(ValueError):q.ExactPrefixReplay(HYDRO).replay(row(10_000_000,[e]))
 def test_nonzero_or_boolean_initial_state_cannot_be_trusted(self):
  for value in [1.,False,float('nan')]:
   r=row(1_000_000);r['initial_state'][0]=value
   with self.assertRaises(ValueError):q.ExactPrefixReplay(HYDRO).replay(r)
 def test_origin_change_or_sensor_time_reversal_rejected(self):
  for changed in ['origin','target']:
   cache=q.ExactPrefixReplay(HYDRO);cache.replay(row(20_000_000));r=row(30_000_000)
   if changed=='origin':r['origin_ns']+=1
   else:r['target_ns']=ORIGIN+19_000_000
   with self.assertRaises(ValueError):cache.replay(r)
 def test_missing_actual_received_prefix_or_mismatched_actual_sensor_rejected(self):
  e=event(1_000_000,0,.1,1);r=row(10_000_000);r.update(applied_received_watermark=1,applied_accepted_watermark=1)
  self.assertFalse(q.received_prefix_matches(r,[e],1,1))
  self.assertFalse(q.sensor_state_matches(r,{},{}))

class LongitudinalReferenceTests(unittest.TestCase):
 def test_all_four_declared_speeds_have_true_40s_reference_coverage(self):
  for speed in [.05,.1,.3,.6]:self.assertTrue(q.longitudinal_reference(*reference(speed),speed))
 def test_old_61_point_reference_is_insufficient(self):
  p,f=reference(.6);p['poses']=p['poses'][:61];self.assertFalse(q.longitudinal_reference(p,f,.6))
 def test_profile_or_path_drop_and_wrong_last_point_rejected(self):
  for change in ['profile','point','last']:
   p,f=reference(.6)
   if change=='profile':f['data'].pop()
   elif change=='point':p['poses'].pop()
   else:p['poses'][-1]['pose']['position']['x']-=.01
   self.assertFalse(q.longitudinal_reference(p,f,.6))
 def test_velocity_yaw_or_time_forgery_rejected(self):
  for field in [0,2,3]:
   p,f=reference(.3);f['data'][4*150+field]+=.01;self.assertFalse(q.longitudinal_reference(p,f,.3))
 def test_wrong_frame_stamp_or_quaternion_rejected(self):
  for field in ['frame','stamp','quaternion']:
   p,f=reference(.1)
   if field=='frame':p['header']['frame_id']='odom'
   elif field=='stamp':p['poses'][-1]['header']['stamp']['nanosec']+=1
   else:p['poses'][-1]['pose']['orientation']['w']=.9
   self.assertFalse(q.longitudinal_reference(p,f,.1))
 def test_unregistered_speed_or_boolean_cannot_qualify(self):
  for speed in [0.,.2,True,float('nan')]:self.assertFalse(q.longitudinal_reference(*reference(.1),speed))

class LongWindowTests(unittest.TestCase):
 def test_twenty_second_hundred_candidate_window_passes(self):self.assertTrue(q.longitudinal_window(*window()))
 def test_twenty_second_claim_with_only_four_seconds_of_actual_window_fails(self):
  w,rows=window();w['end_driver_requested_ns']=ORIGIN+4_000_000_000;self.assertFalse(q.longitudinal_window(w,rows))
 def test_single_rejection_cannot_hide_inside_ninety_other_acceptances(self):
  w,rows=window();rows[50].update(accepted=False,reason='anchor_mismatch');self.assertFalse(q.longitudinal_window(w,rows))
 def test_skipped_tick_or_readiness_invalidation_fails(self):
  for change in ['skip','invalidated']:
   w,rows=window()
   if change=='skip':rows[50]['skipped_ticks']=1
   else:rows.append(dict(type='legacy_ready_invalidated',check_ns=ORIGIN+5_000_000_000))
   self.assertFalse(q.longitudinal_window(w,rows))
 def test_short_eighteen_second_activation_coverage_fails(self):
  w,rows=window()
  for k,d in enumerate(rows):d['activation_commit_ns']=ORIGIN+1_000+k*100_000_000
  self.assertFalse(q.longitudinal_window(w,rows))
 def test_tail_acceptance_cannot_fill_long_window(self):
  w,rows=window()
  for d in rows:d['activation_commit_ns']+=21_000_000_000
  self.assertFalse(q.longitudinal_window(w,rows))

class NativeWorkTests(unittest.TestCase):
 def test_ordinary_incremental_query_and_legal_late_rollback_pass(self):
  audit=q.NativeCheckpointAudit();self.assertTrue(audit.inspect(workrow(20_000_000,0,0,1,2,10)));self.assertTrue(audit.inspect(workrow(40_000_000,20_000_000,20_000_000,2,3,10)))
  events=[event(35_000_000,0,.1,1),event(35_010_000,1,.1,1)]
  self.assertTrue(audit.inspect(workrow(60_000_000,40_000_000,20_000_000,3,3,22,events,[35_000_000,35_010_000],1,1)))
  self.assertEqual(audit.stats()['late_event_rewinds'],1)
 def test_fake_full_origin_ordinary_work_is_rejected(self):
  audit=q.NativeCheckpointAudit();audit.inspect(workrow(20_000_000,0,0,1,2,10))
  self.assertFalse(audit.inspect(workrow(40_000_000,20_000_000,0,2,3,20)))
 def test_work_count_ODE_count_or_budget_forgery_rejected(self):
  for field,value in [('integration_steps',9),('ODE_evaluations',159),('maximum_integration_steps',513),('retained_channel_events',1),('WCET_qualified',True)]:
   r=workrow(20_000_000,0,0,1,2,10);r['work'][field]=value;self.assertFalse(q.NativeCheckpointAudit().inspect(r),field)
 def test_fake_no_rewind_after_late_event_rejected(self):
  audit=q.NativeCheckpointAudit();audit.inspect(workrow(20_000_000,0,0,1,2,10));e=event(10_000_000,0,.1,1)
  self.assertFalse(audit.inspect(workrow(40_000_000,20_000_000,20_000_000,2,3,10,[e])))
 def test_fake_checkpoint_or_clipped_event_visit_population_rejected(self):
  for field,value in [('checkpoint_count_after',1),('event_element_visits',2),('late_channel_events_since_last_sensor',False)]:
   r=workrow(20_000_000,0,0,1,2,10);r['work'][field]=value;self.assertFalse(q.NativeCheckpointAudit().inspect(r),field)

if __name__=='__main__':unittest.main()
