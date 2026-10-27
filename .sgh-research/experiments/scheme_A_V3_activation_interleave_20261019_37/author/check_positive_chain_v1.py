#!/usr/bin/env python3
"""A: whole owned evidence plus a finite, live-owner zero-equilibrium positive.

The inherited checker is executed without issue filtering or population clipping.
This is an independent shadow component result, never a phase qualification.
"""
from pathlib import Path
import argparse,json,math,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import check_c38_owned_close as base
c36=base.c36
FLAGS=base.FLAGS.copy()
MIN_CONSECUTIVE=10
ZERO_REFERENCE_KIND='stationary_zero_equilibrium'
def number(v):return type(v) in (int,float) and math.isfinite(v)
def zero_vector(v,size):return type(v) is list and len(v)==size and all(number(x) and x==0 for x in v)
def integer(v):return type(v) is int and 0<=v<2**63
def xyz_zero(v):return type(v) is dict and zero_vector([v.get(k) for k in ('x','y','z')],3)
def identity_quaternion(v):return type(v) is dict and xyz_zero(v) and number(v.get('w')) and v['w']==1
def odometry_zero(m):
 if type(m) is not dict:return False
 pose=m.get('pose',{}).get('pose',{});twist=m.get('twist',{}).get('twist',{})
 return (xyz_zero(pose.get('position')) and identity_quaternion(pose.get('orientation'))
         and xyz_zero(twist.get('linear')) and xyz_zero(twist.get('angular')))
def imu_zero(m):
 return (type(m) is dict and identity_quaternion(m.get('orientation'))
         and xyz_zero(m.get('angular_velocity')) and xyz_zero(m.get('linear_acceleration')))
def path_zero(m):
 if type(m) is not dict or m.get('header',{}).get('frame_id')!='map':return False
 h=m['header'];stamp=h.get('stamp',{})
 if not integer(stamp.get('sec')) or not integer(stamp.get('nanosec')) or stamp['nanosec']>=1_000_000_000:return False
 poses=m.get('poses')
 if type(poses) is not list or len(poses)!=61:return False
 for p in poses:
  if type(p) is not dict or p.get('header')!=h:return False
  pose=p.get('pose',{});v=pose.get('position',{});q=pose.get('orientation',{})
  if not zero_vector([v.get(k) for k in ('x','y','z')],3):return False
  if not zero_vector([q.get(k) for k in ('x','y','z')],3) or not number(q.get('w')) or q['w']!=1:return False
 return True
def profile_zero(m):
 if type(m) is not dict:return False
 layout=m.get('layout',{});dims=layout.get('dim');data=m.get('data')
 if type(layout.get('data_offset')) is not int or layout['data_offset']!=0 or type(dims) is not list or len(dims)!=2:return False
 for d,size,stride,prefix in zip(dims,(61,4),(244,4),('stamp_sec:','stamp_nanosec:')):
  if type(d) is not dict or type(d.get('size')) is not int or d['size']!=size or type(d.get('stride')) is not int or d['stride']!=stride:return False
  label=d.get('label')
  if type(label) is not str or not label.startswith(prefix):return False
  value=label[len(prefix):]
  if not value.isascii() or not value.isdecimal() or str(int(value))!=value:return False
  if prefix=='stamp_nanosec:' and int(value)>=1_000_000_000:return False
 if type(data) is not list or len(data)!=244:return False
 return all(zero_vector(data[4*k:4*k+3],3) and number(data[4*k+3]) and data[4*k+3]==0.2*k
            and (not k or data[4*k+3]>data[4*(k-1)+3]) for k in range(61))
def fixture_manifest_zero(m):
 return (m.get('role')=='synthetic_source' and m.get('synthetic') is True and m.get('plant_connected') is False
         and m.get('source_state')=='stationary_zero' and m.get('reference_kind')==ZERO_REFERENCE_KIND
         and number(m.get('reference_speed_m_s')) and m['reference_speed_m_s']==0)
def accepted(d):
 return (d.get('accepted') is True and d.get('reason')=='' and d.get('control_source')=='candidate'
         and type(d.get('job_id')) is int and d['job_id']>0 and d.get('skipped_ticks')==0)
def positive_window(observer,exitproof,ledger,checker):
 get=lambda kind:[r for r in observer if r.get('type')==kind]
 ready=get('legacy_ready');close=get('adapter_driver_close_observed')
 checker.need(len(ready)==len(close)==1,'A_single_ready_and_actual_close')
 if len(ready)!=1 or len(close)!=1:return {'consecutive_accepted':0,'accepted':0,'attempts':0}
 start=ready[0].get('readiness',{}).get('legacy_ready_ns');end=close[0].get('requested_ns');observed=close[0].get('observed_ns')
 valid=all(integer(v) and v>0 for v in (start,end,observed,exitproof.get('proof_ns'))) and start<end<=observed<exitproof['proof_ns']
 checker.need(valid,'A_ready_request_close_exit_order')
 checker.need(close[0].get('owner_process_alive') is True,'A_actual_owner_alive_at_native_close_observation')
 signals=[r for r in ledger if r.get('type')=='signal' and r.get('name')=='publisher']
 checker.need(bool(signals) and all(integer(r.get('monotonic_ns')) and r['monotonic_ns']>=observed for r in signals),'A_owner_no_driver_signal_before_measurement_close')
 if not valid:return {'consecutive_accepted':0,'accepted':0,'attempts':0}
 ds=[r for r in get('decision') if integer(r.get('activation_commit_ns')) and start<=r['activation_commit_ns']<end]
 checker.need(ds==sorted(ds,key=lambda r:r['activation_commit_ns']),'A_window_decision_Source_time_order')
 current=longest=count=0;previous=None;accepted_ids=[]
 for d in ds:
  identity=tuple(d.get(k) for k in ('schedule_generation','task_generation','model_generation','config_generation','epoch'))
  good=accepted(d)
  if good:
   count+=1;accepted_ids.append(d['job_id'])
   consecutive=previous is not None and previous[0]==identity and type(d.get('tick')) is int and d['tick']==previous[1]+1
   current=current+1 if consecutive else 1;longest=max(longest,current)
   previous=(identity,d.get('tick'))
  else:current=0;previous=None
 checker.need(longest>=MIN_CONSECUTIVE,'A_at_least_ten_consecutive_real_candidate_activations',longest=longest,required=MIN_CONSECUTIVE)
 checker.need(len(set(accepted_ids))==len(accepted_ids),'A_accepted_job_identity_unique')
 callbacks=[r for r in get('adapter_applied_callback') if integer(r.get('processed_ns')) and start<=r['processed_ns']<end]
 checker.need(bool(callbacks) and all(r.get('owner_process_alive') is True and r.get('authentication_reason')=='' and r.get('queued_terminal_tail') is False for r in callbacks),'A_live_original_owner_Applied_callbacks_in_measurement')
 checker.need(not [r for r in get('legacy_ready_invalidated') if integer(r.get('check_ns')) and start<=r['check_ns']<end],'A_no_readiness_invalidation_during_measurement')
 return {'start_ready_ns':start,'end_driver_requested_ns':end,'actual_close_observed_ns':observed,
         'owner_exit_proof_ns':exitproof['proof_ns'],'decisions':len(ds),'attempts':sum(d.get('job_id',0)>0 for d in ds),
         'accepted':count,'consecutive_accepted':longest,'accepted_job_ids':accepted_ids,'live_Applied_callbacks':len(callbacks),
         'acceptance_window_semantics':'legacy_ready <= activation < driver_close_requested; no tail acceptance counted'}
def analyze(run):
 run=Path(run).resolve();files=[p for p in run.rglob('*') if p.is_file()];before={str(p):c36.sha(p) for p in files}
 inherited=base.analyze(run);c=c36.Checks()
 c.need(inherited.get('passed') is True,'A_whole_inherited_Source_Storage_Witness_peer_cleanup_evidence',issues=inherited.get('issues'),reader_error=inherited.get('reader_error'))
 c.need(inherited.get('normal_driver_passed') is True,'A_normal_owned_driver_passed')
 inputs=c36.load(run/'inputs.json')
 c.need(inputs.get('c38_case')=='normal' and inputs.get('ordered_stage')=='A' and inputs.get('validation_recipe_revision')=='ordered-positive-A-v1','A_preregistered_stage_and_normal_case')
 fixture=c36.load(run/'synthetic_source/owned_manifest.json');c.need(fixture_manifest_zero(fixture),'A_explicit_new_stationary_zero_fixture_manifest')
 pin=inputs['source_bundles']['fixture'];descriptor=c36.load(pin['path'])
 c.need(descriptor.get('reference_kind')==ZERO_REFERENCE_KIND and number(descriptor.get('reference_speed_m_s')) and descriptor['reference_speed_m_s']==0 and pin['sha256']==fixture['source_bundle_sha256'],'A_new_fixture_manifest_source_descriptor_binding')
 decoded,_,storage=base.p.base.read_actual_storage(run/'recorder/bag',c36.load(run/'topics.json')['topics'])
 paths=decoded.get('/path/reference',[]);profiles=decoded.get('/path/reference_profile',[])
 odoms=decoded.get('/wamv/sensors/position/ground_truth_odometry',[]);imus=decoded.get('/wamv/sensors/imu/imu/data',[])
 c.need(bool(odoms) and all(odometry_zero(r['message']) for r in odoms),'A_entire_actual_stored_stationary_zero_Odometry_population',count=len(odoms))
 c.need(bool(imus) and all(imu_zero(r['message']) for r in imus),'A_entire_actual_stored_stationary_zero_Imu_population',count=len(imus))
 c.need(bool(paths) and all(path_zero(r['message']) for r in paths),'A_entire_actual_stored_zero_Path_population',count=len(paths))
 c.need(bool(profiles) and all(profile_zero(r['message']) for r in profiles),'A_entire_actual_stored_zero_profile_population',count=len(profiles))
 path_stamps=[(r['message']['header']['stamp']['sec'],r['message']['header']['stamp']['nanosec']) for r in paths]
 profile_stamps=[tuple(int(d['label'].split(':',1)[1]) for d in r['message']['layout']['dim']) for r in profiles if profile_zero(r['message'])]
 c.need(path_stamps==profile_stamps,'A_entire_actual_Path_profile_same_stamp_population')
 applied=decoded.get(c36.APPLIED,[])
 c.need(bool(applied) and all(zero_vector(r['message'].get('final_n'),2) and r['message'].get('left_publish_success') is True and r['message'].get('right_publish_success') is True for r in applied),'A_entire_actual_Applied_exact_zero_successful_calls',count=len(applied))
 observer=c36.lines(run/'observer/source.jsonl');window=positive_window(observer,c36.load(run/'c38_owner_exit_proof.json'),c36.lines(run/'owned_process_ledger.jsonl'),c)
 jobs=[r['job'] for r in observer if r.get('type')=='job']
 c.need(bool(jobs) and all(zero_vector(j.get('anchor_n'),2) and zero_vector(j.get('frozen_state'),6) and zero_vector(j.get('reference'),6*(j.get('N',-1)+1)) for j in jobs),'A_all_frozen_jobs_zero_anchor_state_and_reference',count=len(jobs))
 for dep in (Path(__file__),HERE/'test_positive_chain_v1.py'):
  rel=dep.name;c.need(inputs.get('tool_sha256',{}).get(rel)==c36.sha(dep) and c36.sha(run/(rel+'.snapshot'))==c36.sha(dep),'A_checker_exact_prerun_snapshot',tool=rel)
 after={str(p):c36.sha(p) for p in files};c.need(before==after,'A_all_raw_files_read_only')
 return c.result(schema='p1-positive-chain-A-check/v1',run_dir=str(run),positive_component_passed=not c.issues,
        stage='A',profile='zero_equilibrium_owned_shadow',normal_business_contract_qualified=False,
        inherited=inherited,window=window,storage=storage,qualifications=FLAGS,unknowns=base.p.UNKNOWNS,
        actual_reference_paths=len(paths),actual_reference_profiles=len(profiles),actual_Applied=len(applied),actual_zero_Odometry=len(odoms),actual_zero_Imu=len(imus),
        no_tail_acceptance_counted=True,window_clipped=False,input_sha256_before=before,input_sha256_after=after,
        checker_sha256=c36.sha(__file__))
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 try:r=analyze(args.run_dir)
 except Exception as e:r={'schema':'p1-positive-chain-A-check/v1','passed':False,'positive_component_passed':False,'reader_error':repr(e),'qualifications':FLAGS}
 size=base.write(args.output,r);print(json.dumps({'passed':r['passed'],'issues':r.get('issues'),'reader_error':r.get('reader_error'),'window':r.get('window'),'bytes':size}));return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
