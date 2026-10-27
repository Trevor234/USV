"""Finite independent projection/profile reconstruction and preregistered gates."""
import copy,json,math,unittest
from pathlib import Path
import check_projected_v1 as p

def messages(points=None,times=None,speed=.1):
 if points is None:points=[(0.,0.,0.),(1.,0.,0.),(2.,0.,0.)]
 if times is None:times=[0.,10.,20.]
 h=dict(frame_id='map',stamp=dict(sec=100,nanosec=1234));poses=[]
 for x,y,yaw in points:poses.append(dict(header=copy.deepcopy(h),pose=dict(position=dict(x=x,y=y,z=0.),orientation=dict(x=0.,y=0.,z=math.sin(yaw/2),w=math.cos(yaw/2)))))
 path=dict(header=h,poses=poses);profile=dict(layout=dict(data_offset=0,dim=[dict(label='stamp_sec:100',size=len(points),stride=4*len(points)),dict(label='stamp_nanosec:1234',size=4,stride=4)]),data=[v for t in times for v in [speed,0.,0.,t]])
 return path,profile

def target(x=.37,y=.2,yaw=0.):return [x,y,yaw,.1,0.,0.]
def source_for(result):return dict(reference_mode=p.POLICY,reference_projection=copy.deepcopy(result['projection']),configured_start_offset=0,effective_start_offset=0,start_index=result['projection']['segment'],nearest_index=result['nearest_index'],profile_t0=result['projection']['profile_t0'])
def samples(speed=.1,start=1000000000):return [(start+k*200000000,speed) for k in range(100)]

class IndependentProjectionTests(unittest.TestCase):
 def test_interior_continuous_projection_has_no_discrete_carrot(self):
  r=p.independent_projection(target(),*messages());self.assertEqual(r['projection']['segment'],0);self.assertAlmostEqual(r['projection']['fraction'],.37);self.assertAlmostEqual(r['projection']['profile_t0'],3.7);self.assertAlmostEqual(r['reference'][0],.37);self.assertAlmostEqual(r['reference'][-6],.77);self.assertAlmostEqual(r['projection']['squared_distance'],.04)
 def test_off_path_point_clamps_to_first_segment_endpoint(self):
  r=p.independent_projection(target(-1.,.2),*messages());self.assertEqual(r['projection']['fraction'],0.);self.assertEqual(r['reference'][0],0.);self.assertAlmostEqual(r['projection']['squared_distance'],1.04)
 def test_shared_vertex_tie_uses_first_segment(self):
  r=p.independent_projection(target(1.,0.),*messages([(0.,0.,0.),(1.,0.,math.pi/2),(1.,1.,math.pi/2)]));self.assertEqual(r['projection']['segment'],0);self.assertEqual(r['projection']['fraction'],1.);self.assertAlmostEqual(r['reference'][-5],.4)
 def test_projection_uses_target_time_state_not_frozen_state(self):
  a=p.independent_projection(target(.37),*messages());b=p.independent_projection(target(.35),*messages());self.assertGreater(max(abs(x-y) for x,y in zip(a['reference'],b['reference'])),.019)
 def test_nonuniform_profile_time_is_interpolated_at_projected_fraction(self):
  r=p.independent_projection(target(.4),*messages([(0.,0.,0.),(1.,0.,0.),(3.,0.,0.)],[0.,5.,20.]));self.assertAlmostEqual(r['projection']['profile_t0'],2.);self.assertAlmostEqual(r['reference'][-6],1.+2./15)
 def test_heading_unwrap_crosses_pi_continuously(self):
  r=p.independent_projection(target(.5,0.,math.pi+.03),*messages([(0.,0.,math.pi-.05),(1.,0.,-math.pi+.05),(2.,0.,-math.pi+.1)]));headings=r['reference'][2::6];self.assertAlmostEqual(headings[0],math.pi);self.assertTrue(all(abs(b-a)<.01 for a,b in zip(headings,headings[1:])))
 def test_explicit_stationary_zero_path_is_valid(self):
  r=p.independent_projection(target(),*messages([(0.,0.,0.)]*3,[0.,1.,2.],0.));self.assertTrue(r['projection']['stationary']);self.assertEqual(r['projection']['segment'],-1);self.assertEqual(r['reference'],[0.]*126)
 def test_mixed_degenerate_segments_are_rejected(self):
  with self.assertRaises(ValueError):p.independent_projection(target(),*messages([(0.,0.,0.),(0.,0.,0.),(1.,0.,0.)]))
 def test_constant_geometry_with_nonzero_speed_is_not_stationary(self):
  with self.assertRaises(ValueError):p.independent_projection(target(),*messages([(0.,0.,0.)]*3))
 def test_unsynchronized_actual_pair_stamp_is_rejected(self):
  a,b=messages();b['layout']['dim'][1]['label']='stamp_nanosec:1235'
  with self.assertRaises(ValueError):p.independent_projection(target(),a,b)
 def test_repeated_or_reversed_profile_time_is_rejected(self):
  for times in ([0.,0.,20.],[0.,-1.,20.]):
   with self.assertRaises(ValueError):p.independent_projection(target(),*messages(times=times))
 def test_horizon_does_not_silently_clip_to_profile_end(self):
  with self.assertRaises(ValueError):p.independent_projection(target(1.95),*messages())
 def test_nonfinite_and_boolean_target_or_profile_fail(self):
  for bad in ([False,0.,0.,0.,0.,0.],[float('nan'),0.,0.,0.,0.,0.]):
   with self.assertRaises(ValueError):p.independent_projection(bad,*messages())
  a,b=messages();b['data'][0]=float('inf')
  with self.assertRaises(ValueError):p.independent_projection(target(),a,b)
 def test_fixed_horizon_and_dt_cannot_be_changed(self):
  for kw in [dict(N=21),dict(N=True),dict(dt=.1)]:
   with self.assertRaises(ValueError):p.independent_projection(target(),*messages(),**kw)
 def test_metadata_has_exact_seven_fields_and_zero_offsets(self):
  r=p.independent_projection(target(),*messages());source=source_for(r);self.assertTrue(p.projected_metadata_matches(source,r))
  for mutate in [lambda s:s['reference_projection'].update(extra=False),lambda s:s.update(effective_start_offset=True),lambda s:s.update(reference_mode='profile_time'),lambda s:s.update(start_index=2),lambda s:s.update(start_index=False),lambda s:s.update(nearest_index=False),lambda s:s['reference_projection'].update(fraction=.5)]:
   bad=copy.deepcopy(source);mutate(bad);self.assertFalse(p.projected_metadata_matches(bad,r))
 def test_reference_comparison_tolerance_is_finite_absolute(self):
  self.assertTrue(p.close_numeric(.1,.1+1e-13));self.assertFalse(p.close_numeric(.1,.1+1e-9));self.assertFalse(p.close_numeric(False,0.));self.assertFalse(p.close_numeric(float('nan'),0.))
 def test_bad_reference_shape_or_nonfinite_has_finite_failure_context(self):
  self.assertIsNone(p.reference_error([0.]*125,[0.]*126));self.assertIsNone(p.reference_error([False]*126,[0.]*126));self.assertIsNone(p.reference_error([float('nan')]*126,[0.]*126));self.assertEqual(p.reference_error([0.]*126,[0.]*126),0.)
 def test_actual_Job104_agrees_with_independent_single_x_shift_native_controlled_sample(self):
  root=p.HERE;inputs=json.loads((root/'reference_probe/actual_inputs_v1.json').read_text());sample=[s for s in inputs['samples'] if s['case']=='s010' and s['job_id']==104][0]
  path,profile=messages(sample['path'],[r[3] for r in sample['profile']],sample['speed']);stamp=sample['path_stamp'];path['header']['stamp']=dict(sec=stamp[0],nanosec=stamp[1]);profile['layout']['dim'][0]['label']='stamp_sec:'+str(stamp[0]);profile['layout']['dim'][1]['label']='stamp_nanosec:'+str(stamp[1]);profile['data']=[v for r in sample['profile'] for v in r]
  r=p.independent_projection(sample['target_state'],path,profile);native=json.loads((root.parents[1]/'scheme_A_reference_bias_20261016_20/replay/native_actual_backend_v1.json').read_text())
  expected=native['selected_reference_x_shift']['selected']['reference'];self.assertLess(max(abs(a-b) for a,b in zip(r['reference'],expected)),1e-12);self.assertAlmostEqual(r['reference'][0],sample['target_state'][0]);self.assertGreater(abs(r['reference'][0]-sample['reference'][0]),.03)

class PerformanceGateTests(unittest.TestCase):
 def metric(self,s=None):return p.performance_metrics(samples() if s is None else s,1000000000,21000000000,.1)
 def test_exact_speed_passes_both_preregistered_gates(self):
  r=self.metric();self.assertTrue(r['passed']);self.assertEqual(r['measured_surge_RMSE_m_s'],0.);self.assertEqual(r['measurement_sensor_count'],100)
 def test_previous_twentyfive_percent_speed_bias_fails(self):
  r=self.metric(samples(.125));self.assertFalse(r['passed']);self.assertFalse(r['last5s_mean_passed']);self.assertFalse(r['RMSE_passed'])
 def test_good_last_five_seconds_does_not_hide_bad_whole_window(self):
  s=samples();s=[(t,.05 if k<60 else u) for k,(t,u) in enumerate(s)];r=self.metric(s);self.assertTrue(r['last5s_mean_passed']);self.assertFalse(r['RMSE_passed'])
 def test_small_RMSE_does_not_hide_last_five_seconds_bias(self):
  s=[(t,.106 if k>=75 else u) for k,(t,u) in enumerate(samples())];r=self.metric(s);self.assertTrue(r['RMSE_passed']);self.assertFalse(r['last5s_mean_passed'])
 def test_prepare_and_shutdown_tail_are_excluded_only_from_declared_metrics(self):
  r=self.metric([(0,9.)]+samples()+[(21000000000,0.),(22000000000,0.)]);self.assertTrue(r['passed']);self.assertEqual(r['measurement_sensor_count'],100);self.assertEqual(r['last5s_mean_surge_m_s'],.1)
 def test_missing_last_window_or_nonfinite_samples_fail(self):
  for s in [[],samples()[:50],[(1000000000,float('nan'))],[(True,.1)]]:
   with self.assertRaises(ValueError):self.metric(s)
 def test_duplicate_or_reordered_source_times_fail(self):
  s=samples();s[1]=s[0]
  with self.assertRaises(ValueError):self.metric(s)
 def test_parent_thresholds_are_fixed_and_no_qualification_is_granted(self):
  self.assertEqual(p.PARENT_RMSE[.1],.029260913386751467);self.assertEqual(p.c36.sha(p.PARENT_METRICS),p.PARENT_METRICS_SHA);self.assertTrue(all(v is False for v in p.base.FLAGS.values()))
if __name__=='__main__':unittest.main()
