#!/usr/bin/env python3
"""Whole-evidence A2/B/C diagnostic checks. No stage or execution qualification."""
from pathlib import Path
import argparse,hashlib,json,math,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import check_c38_owned_close as base
import check_positive_chain_v1 as positive
import check_controlled_owner_v1 as owner_check
c36=base.c36
PHASE='/p1/controlled_owner_phase'
BASELINE='CONTROLLED_PHASE_20261015_DIAGNOSTIC_01'
def zero(v):return isinstance(v,list) and all(type(x) in (int,float) and math.isfinite(x) and x==0 for x in v)
def freeze_matches(g,j,a,p):
 try:
  starts=[a['left_publish_start_steady_ns'],a['right_publish_start_steady_ns']]
  ends=[a['left_publish_end_steady_ns'],a['right_publish_end_steady_ns']]
  return (g['freeze_ns']==j['freeze_ns'] and g['target_tick']==j['target_tick']==g['tick']+1
   and g['planned_ns']==j['tick_origin_ns'] and g['deadline_ns']==j['deadline_ns']==g['planned_ns']+150000000
   and g['target_ns']==j['target_ns']==g['planned_ns']+200000000 and g['held_until_ns']==j['target_ns']
   and g['command_n']==j['anchor_n']==a['final_n'] and j['anchor_sequence']==[a['sequence']]*2
   and g['applied_sequence']==a['sequence'] and g['phase_applied_sequence']==p['applied_sequence']
   and g['phase_applied_sequence']<=g['applied_sequence'] and p['command_n']==g['command_n']
   and p['held_until_ns']==g['held_until_ns'] and p['start_ns']==g['phase_start_ns'] and p['end_ns']==g['phase_end_ns'] and p['command_n']==g['phase_command_n']
   and p['decision_sequence']==g['decision_sequence'] and p['tick']==g['tick'] and p['planned_ns']==g['planned_ns']
   and p['emitted_ns']==g['phase_emitted_ns']<=g['freeze_ns']<=j['deadline_ns']
   and ends[1]<=g['freeze_ns'] and starts==[j['anchor_publish_ns'][0],j['anchor_publish_ns'][1]])
 except (KeyError,TypeError):return False
def phase_applied_matches(p,a):
 return (p.get('applied_sequence')==a.get('sequence') and p.get('command_n')==a.get('final_n')
  and p.get('start_ns')==[a.get('left_publish_start_steady_ns'),a.get('right_publish_start_steady_ns')]
  and p.get('end_ns')==[a.get('left_publish_end_steady_ns'),a.get('right_publish_end_steady_ns')]
  and a.get('left_publish_success') is True and a.get('right_publish_success') is True
  and p.get('emitted_ns',0)>=a.get('right_publish_end_steady_ns',1)
  and a.get('steady_clock_domain')==p.get('boot_id','')+':steady_clock'
  and all(p.get(k)==a.get(k) for k in ['run_id','baseline_id','producer_instance_id']))
def changed_window(j,d,applied):
 return [a for a in applied if j['freeze_ns']<a['left_publish_start_steady_ns']<=a['right_publish_end_steady_ns']<d['activation_commit_ns'] and a['final_n']!=j['anchor_n']]
def ode(x,n,p):
 _,_,yaw,u,v,r=x;tl,tr=n
 m11=p['mass']-p['Xu_dot'];m22=p['mass']-p['Yv_dot'];m23=p['mass']*p['xg']-p['Yr_dot'];m32=p['mass']*p['xg']-p['Nv_dot'];m33=p['Iz']-p['Nr_dot']
 c13=-m22*v-m23*r;c23=m11*u
 f0=tl+tr-c13*r-(-p['Xu']-p['Xuu']*abs(u))*u
 f1=-c23*r-(-p['Yv']-p['Yvv']*abs(v))*v-(-p['Yr']-p['Yrr']*abs(r))*r
 f2=p['d_thruster']*(tr-tl)+c13*u+c23*v-(-p['Nv']-p['Nvv']*abs(v))*v-(-p['Nr']-p['Nrr']*abs(r))*r
 det=m22*m33-m23*m32
 return [math.cos(yaw)*u-math.sin(yaw)*v,math.sin(yaw)*u+math.cos(yaw)*v,r,f0/m11,(m33*f1-m23*f2)/det,(-m32*f1+m22*f2)/det]
def forward(x,n,seconds,p):
 x=list(x);h=seconds/4
 for _ in range(4):
  k1=ode(x,n,p);k2=ode([a+.5*h*b for a,b in zip(x,k1)],n,p);k3=ode([a+.5*h*b for a,b in zip(x,k2)],n,p);k4=ode([a+h*b for a,b in zip(x,k3)],n,p)
  x=[a+h*(b+2*c+2*d+e)/6 for a,b,c,d,e in zip(x,k1,k2,k3,k4)]
 x[2]=math.atan2(math.sin(x[2]),math.cos(x[2]));return x
def replay(row,p):
 x=list(row['initial_state']);now=row['origin_ns'];end=row['target_ns'];held=[0.,0.]
 assert len(x)==6 and now<=end and row['integration_substep_max_ns']==2000000 and row['rk4_substeps']==4
 events=sorted(row['held_events'],key=lambda e:(e['publish_end_ns'],e['channel']))
 def advance(until):
  nonlocal now,x
  while now<until:
   stop=min(until,now+2000000);x=forward(x,held,(stop-now)/1e9,p);now=stop
 for e in events:
  assert e['channel'] in (0,1) and type(e['n']) in (int,float) and math.isfinite(e['n'])
  when=e['publish_end_ns']
  if when>end:continue
  if when>now:advance(when)
  held[e['channel']]=e['n']
 advance(end);return x
def received_prefix_matches(row,events,received,accepted):
 try:
  expected=sorted([e for e in events if e['publish_end_ns']<=row['target_ns']],key=lambda e:(e['publish_end_ns'],e['channel']))
  return row['held_events']==expected and type(row['applied_received_watermark']) is int and type(row['applied_accepted_watermark']) is int and row['applied_received_watermark']==received and row['applied_accepted_watermark']==accepted
 except (KeyError,TypeError):return False

def sensor_state_matches(row,o,i):
 try:
  x=row['state'];pose=o['pose']['pose'];twist=o['twist']['twist'];stamp=o['header']['stamp']
  if len(x)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in x):return False
  q={'x':0.,'y':0.,'z':math.sin(x[2]/2),'w':math.cos(x[2]/2)}
  return (o['header']['frame_id']=='map' and o['child_frame_id']=='wamv/base_link' and i['header']['frame_id']=='wamv/wamv/base_link/imu_sensor'
   and stamp['sec']*1000000000+stamp['nanosec']==row['sim_stamp_ns']==100000000000+row['target_ns']-row['origin_ns'] and i['header']['stamp']==stamp
   and [pose['position']['x'],pose['position']['y'],pose['position']['z']]==[x[0],x[1],0.] and pose['orientation']==q and i['orientation']==q
   and [twist['linear']['x'],twist['linear']['y'],twist['linear']['z']]==[x[3],x[4],0.]
   and [twist['angular'][k] for k in ['x','y','z']]==[0.,0.,x[5]] and [i['angular_velocity'][k] for k in ['x','y','z']]==[0.,0.,x[5]])
 except (KeyError,TypeError,ValueError):return False

def phase_metadata_matches(raw,r,closed):
 try:return isinstance(raw,dict) and set(raw)==base.p.RAW_FIELDS and raw.get('schema')=='p1-input-callback-full-cdr-v1' and raw.get('topic')==PHASE and raw.get('message_type')=='std_msgs/msg/String' and raw.get('callback_sequence')==r['callback_sequence'] and raw.get('rmw_implementation')=='rmw_fastrtps_cpp' and raw.get('from_intra_process') is False and r['entry_ns']<=raw.get('entry_steady_ns',0)<=r['observed_ns']<=r['processed_ns']<=closed
 except (KeyError,TypeError):return False

def analyze(run):
 run=Path(run).resolve();files=[p for p in run.rglob('*') if p.is_file()];before={str(p):c36.sha(p) for p in files}
 inherited=base.analyze(run);c=c36.Checks();c.need(inherited.get('passed') is True,'controlled_entire_inherited_evidence',issues=inherited.get('issues'))
 c.need(inherited.get('normal_driver_passed') is True,'controlled_driver_clean')
 inputs=c36.load(run/'inputs.json');case=inputs.get('ordered_stage');c.need(case in ['A2','B','C'] and inputs.get('validation_recipe_revision')=='ordered-controlled-v2','controlled_preregistered_scope')
 contract=c36.load(inputs['contract']);c.need(contract['baseline_input']==BASELINE and contract['execute_qualified'] is False,'new_diagnostic_baseline')
 decoded,_,storage=base.p.base.read_actual_storage(run/'recorder/bag',c36.load(run/'topics.json')['topics'])
 observer=c36.lines(run/'observer/source.jsonl');get=lambda kind:[r for r in observer if r.get('type')==kind]
 applied=[r['message'] for r in decoded[c36.APPLIED]];am=c.index(applied,lambda a:a['sequence'],'controlled_Applied')
 pm=c36.load(run/'publisher/owned_manifest.json');params=pm['effective_parameters']
 for ch,key in enumerate(['vrx_left_thrust_topic','vrx_right_thrust_topic']):
  topic=params[key]['value'];actual=[r['message']['data'] for r in decoded[topic]]
  expected=[a['final_n'][ch] for a in applied if a['left_publish_success' if ch==0 else 'right_publish_success'] is True]
  c.need(actual==expected,'actual_physical_Float64_full_payload_join',channel=ch)
 phases=[c36.strict(r['message']['data']) for r in decoded[PHASE]];pi=c.index(phases,lambda p:p['decision_sequence'],'controlled_phase')
 expected_gid=[e['gid'] for e in pm['endpoints'] if e['kind']=='publisher' and e['topic']==PHASE];c.need(len(expected_gid)==1,'owned_phase_writer_unique')
 callbacks=get('controlled_phase_callback');closure=get('controlled_phase_reception_closed')
 c.need(len(closure)==1 and closure[0].get('executor_detached') is True and closure[0].get('received')==len(callbacks),'whole_phase_callback_closed_population')
 c.need([r['callback_sequence'] for r in callbacks]==list(range(1,len(callbacks)+1)),'whole_phase_callback_sequences')
 received=[]
 for r in callbacks:
  raw=r.get('raw_input');m=base.p.decode_callback(raw,c,{'phase_callback':r['callback_sequence']})
  p=c36.strict(m['data']) if m else None
  c.need(phase_metadata_matches(raw,r,closure[0]['closed_ns']),'whole_phase_actual_callback_metadata')
  c.need(p in phases and r.get('phase')==p and r.get('authentication_reason')=='' and raw.get('publisher_gid')==expected_gid[0],'actual_received_phase_CDR_GID_Storage_binding',sequence=r['callback_sequence'])
  if p is not None:received.append(p['decision_sequence'])
 c.need(len(set(received))==len(received),'phase_received_once')
 for p in phases:
  a=am.get(p['applied_sequence']);c.need(a is not None and phase_applied_matches(p,a),'phase_actual_successful_Applied_binding',decision=p['decision_sequence'])
  c.need(p['contract_sha256']==inputs['contract_sha256'] and p['baseline_id']==BASELINE and p['stage_qualified'] is False and p['execute_qualified'] is False,'phase_exact_new_identity_and_qualification')
 grants=get('controlled_phase_freeze');jobs=[r['job'] for r in get('job')];gm=c.index(grants,lambda g:g['freeze_ns'],'controlled_freeze');jm=c.index(jobs,lambda j:j['job_id'],'controlled_job')
 for j in jobs:
  g=gm.get(j['freeze_ns']);a=am.get(g['applied_sequence']) if g else None;p=pi.get(g['decision_sequence']) if g else None
  c.need(g is not None and a is not None and p is not None and freeze_matches(g,j,a,p),'actual_Job_Applied_phase_freeze_binding',job_id=j['job_id'])
  matching=[r for r in callbacks if r.get('accepted') is True and r.get('phase',{}).get('decision_sequence')==(g or {}).get('decision_sequence')]
  c.need(len(matching)==1 and matching[0]['observed_ns']<=j['freeze_ns'],'phase_native_acceptance_before_freeze',job_id=j['job_id'])
 # The inherited window predicate also enforces owner-live measurement and excludes shutdown tail.
 window=positive.positive_window(observer,c36.load(run/'c38_owner_exit_proof.json'),c36.lines(run/'owned_process_ledger.jsonl'),c)
 owner_evidence=owner_check.analyze(run,decoded,c)
 negative=[];model={};phase_callback_count=len(callbacks)
 if case in ['A2','B']:
  for topic,predicate in [('/path/reference',positive.path_zero),('/path/reference_profile',positive.profile_zero),('/wamv/sensors/position/ground_truth_odometry',positive.odometry_zero),('/wamv/sensors/imu/imu/data',positive.imu_zero)]:
   rows=decoded[topic];c.need(bool(rows) and all(predicate(r['message']) for r in rows),'controlled_entire_zero_state_reference',topic=topic)
 if case=='A2':c.need(bool(applied) and all(zero(a['final_n']) for a in applied),'A2_actual_Applied_zero')
 if case in ['A2','C']:
  for d in get('decision'):
   j=jm.get(d['job_id'])
   if j and window['start_ready_ns']<=d['activation_commit_ns']<window['end_driver_requested_ns']:c.need(not changed_window(j,d,applied),'actual_held_input_entire_freeze_activation_window',job_id=j['job_id'])
 if case=='B':
  for d in get('decision'):
   j=jm.get(d['job_id'])
   if not j:continue
   changed=changed_window(j,d,applied)
   if changed:
    c.need(d['accepted'] is False and d['reason'] in ['anchor_mismatch','anchor_history_changed'],'B_changed_actual_input_rejected_by_original_history',job_id=j['job_id'],reason=d['reason'])
    registrations=[r for r in get('candidate_registration') if r.get('job',{}).get('job_id')==j['job_id']]
    c.need(bool(registrations) and all(r.get('accepted_registration') is True and r.get('reason')=='' for r in registrations),'B_candidate_was_otherwise_ready',job_id=j['job_id'])
    negative.append({'job_id':j['job_id'],'freeze_ns':j['freeze_ns'],'activation_ns':d['activation_commit_ns'],'reason':d['reason'],'actual_Applied_sequences':[a['sequence'] for a in changed]})
  c.need(len(negative)==1,'B_single_preregistered_input_negative',matched=len(negative))
 if case=='C':
  rows=c36.lines(run/'synthetic_source/nominal_steps.jsonl');steps=[r for r in rows if r.get('schema')=='p1-controlled-nominal-model-step-v1'];hydro=contract['hydro'];errors=[]
  c.need(bool(steps),'C_actual_model_state_Source_population')
  fixture=c36.load(run/'synthetic_source/owned_manifest.json')
  c.need(fixture.get('model_contract_sha256')==inputs['contract_sha256'] and fixture.get('contract_hydro')==hydro and fixture.get('plant_connected') is False and fixture.get('diagnostic_nominal_model_connected') is True,'C_actual_model_uses_complete_normative_hydro')
  close=[r for r in rows if r.get('type')=='nominal_source_closed'];callbacks=[r for r in rows if r.get('type')=='nominal_applied_callback']
  c.need(len(close)==1 and rows[-1] is close[0] and close[0]['model_steps']==len(steps) and close[0]['Applied_received']==len(callbacks),'C_full_nominal_Source_terminal_counts')
  c.need(len(steps)==len(decoded['/wamv/sensors/position/ground_truth_odometry'])==len(decoded['/wamv/sensors/imu/imu/data']),'C_entire_sensor_and_model_Source_population')
  odoms=[r['message'] for r in decoded['/wamv/sensors/position/ground_truth_odometry']];imus=[r['message'] for r in decoded['/wamv/sensors/imu/imu/data']]
  received_count=accepted_count=0;events=[];model_index=0
  owner_gid=[e['gid'] for e in pm['endpoints'] if e['kind']=='publisher' and e['topic']==c36.APPLIED][0]
  for r in rows:
   if r.get('type')=='nominal_applied_callback':
    received_count+=1;m=base.p.decode_callback(r.get('raw_input'),c,{'nominal_callback':received_count});raw=r.get('raw_input')
    c.need(isinstance(raw,dict) and set(raw)==base.p.RAW_FIELDS and raw.get('schema')=='p1-controlled-full-cdr-receipt-v1' and raw.get('topic')==c36.APPLIED and raw.get('message_type')==c36.APPLIED_TYPE and raw.get('callback_sequence')==received_count and raw.get('rmw_implementation')=='rmw_fastrtps_cpp' and raw.get('from_intra_process') is False and raw.get('entry_steady_ns',0)<=r['processed_ns']<=close[0]['closed_ns'],'C_full_actual_model_callback_metadata')
    c.need(m is not None and m==am.get(r['sequence']) and r.get('raw_input',{}).get('publisher_gid')==owner_gid,'C_model_callback_actual_CDR_GID_Applied_Storage_binding')
    if r.get('accepted') is True and m is not None:
     c.need(r.get('authentication_reason')=='','C_only_authenticated_Applied_enters_model');accepted_count+=1
     for ch,key in enumerate(['left_publish_end_steady_ns','right_publish_end_steady_ns']):events.append({'publish_end_ns':m[key],'channel':ch,'n':m['final_n'][ch],'applied_sequence':m['sequence']})
    else:
     c.need(m is not None and m.get('control_source')=='shutdown_zero' and r['processed_ns']>=window['end_driver_requested_ns'],'C_unmodelled_callback_only_declared_terminal_tail')
   if r.get('schema')=='p1-controlled-nominal-model-step-v1':
    c.need(received_prefix_matches(r,events,received_count,accepted_count),'C_complete_received_Applied_prefix_no_event_omission',sensor_sequence=r['sensor_sequence'])
    c.need(r['sensor_sequence']==model_index+1 and r.get('contract_hydro')==hydro and r.get('model_contract_sha256')==inputs['contract_sha256'],'C_model_row_contract_and_sequence')
    if model_index<len(odoms) and model_index<len(imus):
     c.need(sensor_state_matches(r,odoms[model_index],imus[model_index]),'C_entire_actual_sensor_stamp_state_payload_binding',sensor_sequence=r['sensor_sequence'])
    model_index+=1
  for row in steps:
   x=replay(row,hydro);errors.append(max(abs(a-b) for a,b in zip(x,row['state'])))
   for e in row['held_events']:
    a=am.get(e['applied_sequence']);ch=e['channel'];key='left_publish_end_steady_ns' if ch==0 else 'right_publish_end_steady_ns'
    c.need(a is not None and a[key]==e['publish_end_ns'] and a['final_n'][ch]==e['n'],'C_held_event_actual_Applied_binding')
  c.need(bool(errors) and max(errors)<1e-9,'C_independent_Python_Fossen_RK4_full_replay',max_error=max(errors) if errors else None)
  c.need(any(any(abs(v)>1e-6 for v in a['final_n']) for a in applied),'C_actual_nonzero_input')
  c.need(any(any(abs(v)>1e-6 for v in row['state']) for row in steps),'C_actual_nonzero_model_state')
  model={'states_recomputed':len(steps),'maximum_absolute_replay_error':max(errors) if errors else None,'true_physical_plant_acceptance':False}
 for dep in ['prepare_controlled_v2.py','check_controlled_v2.py','test_controlled_v2.py','prepare_controlled_v1.py','check_controlled_v1.py','test_controlled_v1.py','check_controlled_owner_v1.py','test_controlled_owner_v1.py','check_positive_chain_v1.py']:
  c.need(inputs['tool_sha256'].get(dep)==c36.sha(HERE/dep)==c36.sha(run/(dep+'.snapshot')),'controlled_exact_prerun_tool_binding',tool=dep)
 after={str(p):c36.sha(p) for p in files};c.need(before==after,'controlled_raw_inputs_unchanged')
 return c.result(schema='ordered-controlled-check/v1',case=case,window=window,negative=negative,model=model,inherited=inherited,owner_evidence=owner_evidence,storage=storage,phase_recorded=len(phases),phase_received=phase_callback_count,phase_recorded_not_received=sorted(set(pi)-set(received)),jobs=len(jobs),qualifications=base.FLAGS,scope='finite_localhost_DDS_diagnostic_component',stage_qualified=False,execute_qualified=False,research_conclusion=False,input_sha256_before=before,input_sha256_after=after)
def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 try:r=analyze(a.run_dir)
 except Exception as e:r={'schema':'ordered-controlled-check/v1','passed':False,'reader_error':repr(e),'stage_qualified':False}
 base.write(a.output,r);print(json.dumps({k:r.get(k) for k in ['passed','case','window','negative','model','issues','reader_error']},ensure_ascii=False));return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
