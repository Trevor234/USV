#!/usr/bin/env python3
"""20 s longitudinal nominal diagnostics; complete inherited source/wire/owner guards."""
from pathlib import Path
import argparse,hashlib,json,math,sys,bisect
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import check_c38_longitudinal_v1 as base
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

class ExactPrefixReplay:
 """Independent canonical 2 ms RK4 grid, never seeded by Source state.

 Only full canonical steps and authenticated-event boundaries are reusable.
 Sensor-end partial steps remain ephemeral; their reuse would change the grid.
 Late actual input invalidates checkpoints at/after its first changed time.
 """
 def __init__(self,hydro):
  self.hydro=json.loads(json.dumps(hydro,allow_nan=False));self.origin=None
  self.history=();self.checkpoints=[];self.last_target=None
  self.rows=0;self.integration_steps=0;self.rollbacks=0;self.peak_checkpoints=0
 def _put(self,ns,x,held,index):
  point=(ns,tuple(x),tuple(held),index)
  if self.checkpoints and self.checkpoints[-1][0]==ns:self.checkpoints[-1]=point
  else:self.checkpoints.append(point)
  if len(self.checkpoints)>24050:raise ValueError('independent checkpoint bound')
  self.peak_checkpoints=max(self.peak_checkpoints,len(self.checkpoints))
 def replay(self,row):
  origin=row['origin_ns'];target=row['target_ns'];initial=row['initial_state']
  if (type(origin) is not int or type(target) is not int or origin<=0 or not origin<=target<=origin+40_000_000_000
      or type(initial) is not list or len(initial)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) or v!=0 for v in initial)
      or type(row['integration_substep_max_ns']) is not int or row['integration_substep_max_ns']!=2_000_000
      or type(row['rk4_substeps']) is not int or row['rk4_substeps']!=4):raise ValueError('canonical replay domain')
  if self.origin is None:
   self.origin=origin;self._put(origin,[0.]*6,[0.,0.],0)
  if origin!=self.origin or self.last_target is not None and target<self.last_target:raise ValueError('replay origin or sensor time reversal')
  events=[];identities=set()
  for e in row['held_events']:
   if (set(e)!=set(['publish_end_ns','channel','n','applied_sequence']) or type(e['publish_end_ns']) is not int or not 0<e['publish_end_ns']<=target
       or type(e['channel']) is not int or e['channel'] not in (0,1) or type(e['applied_sequence']) is not int or e['applied_sequence']<=0
       or type(e['n']) not in (int,float) or not math.isfinite(e['n']) or abs(e['n'])>25):raise ValueError('canonical event domain')
   identity=(e['applied_sequence'],e['channel'])
   if identity in identities:raise ValueError('duplicate received event')
   identities.add(identity);events.append((e['publish_end_ns'],e['channel'],float(e['n']),e['applied_sequence']))
  if len(events)>1024:raise ValueError('retained event bound')
  events=tuple(sorted(events,key=lambda e:(e[0],e[1])))
  previous={(e[3],e[1]):e for e in self.history};current={(e[3],e[1]):e for e in events}
  if any(current.get(k)!=v for k,v in previous.items()):raise ValueError('received event omitted or mutated')
  common=0
  while common<min(len(events),len(self.history)) and events[common]==self.history[common]:common+=1
  changed=min([e[0] for e in events[common:]]+[e[0] for e in self.history[common:]],default=None)
  if changed is not None and changed<=self.checkpoints[-1][0]:
   keep=bisect.bisect_left([p[0] for p in self.checkpoints],changed)
   self.checkpoints=self.checkpoints[:max(1,keep)];self.rollbacks+=1
   if changed<=origin:self.checkpoints=[];self._put(origin,[0.]*6,[0.,0.],0)
  cursor,x,held,index=self.checkpoints[-1];x=list(x);held=list(held)
  def advance(until,event_boundary):
   nonlocal cursor,x
   while cursor<until:
    delta=min(2_000_000,until-cursor);x=forward(x,held,delta/1e9,self.hydro);cursor+=delta;self.integration_steps+=1
    if delta==2_000_000 or event_boundary and cursor==until:self._put(cursor,x,held,index)
  while index<len(events) and events[index][0]<=target:
   when,ch,n,_=events[index]
   if when>cursor:advance(when,True)
   held[ch]=n;index+=1;self._put(cursor,x,held,index)
  advance(target,False)
  if any(not math.isfinite(v) for v in x):raise ValueError('nonfinite independent state')
  self.history=events;self.last_target=target;self.rows+=1;return x
 def stats(self):return dict(algorithm='independent_canonical_grid_exactprefix_checkpoints_v1',rows=self.rows,integration_steps=self.integration_steps,late_input_rollbacks=self.rollbacks,peak_checkpoints=self.peak_checkpoints,Source_state_used_as_seed=False,control_WCET_claimed=False)

def longitudinal_window(window,observer):
 try:
  start=window['start_ready_ns'];end=window['end_driver_requested_ns']
  rows=[d for d in observer if d.get('type')=='decision' and start<=d['activation_commit_ns']<end]
  candidates=[d for d in rows if d.get('job_id',0)>0]
  good=(end-start>=20_000_000_000 and len(candidates)>=90 and window['consecutive_accepted']>=90
        and bool(candidates) and all(positive.accepted(d) for d in candidates)
        and all(type(d.get('skipped_ticks')) is int and d['skipped_ticks']==0 for d in rows)
        and candidates[-1]['activation_commit_ns']-candidates[0]['activation_commit_ns']>=18_000_000_000
        and not any(r.get('type')=='legacy_ready_invalidated' and start<=r.get('check_ns',-1)<end for r in observer))
  return good
 except (KeyError,TypeError):return False

def longitudinal_reference(path,profile,speed):
 """Declared 201-point .2 s reference, with enough horizon beyond 20 s."""
 try:
  if type(speed) not in (int,float) or speed not in (.05,.1,.3,.6):return False
  h=path['header'];stamp=h['stamp'];poses=path['poses'];layout=profile['layout'];dims=layout['dim'];data=profile['data']
  if h['frame_id']!='map' or len(poses)!=201 or len(data)!=804 or layout['data_offset']!=0 or len(dims)!=2:return False
  if type(stamp['sec']) is not int or type(stamp['nanosec']) is not int or stamp['sec']<0 or not 0<=stamp['nanosec']<1_000_000_000:return False
  expected=[dict(label='stamp_sec:'+str(stamp['sec']),size=201,stride=804),dict(label='stamp_nanosec:'+str(stamp['nanosec']),size=4,stride=4)]
  if dims!=expected:return False
  for k,p in enumerate(poses):
   t=.2*k;pose=p['pose'];position=pose['position'];q=pose['orientation']
   if p['header']!=h or position!={'x':speed*(.2*k),'y':0.,'z':0.} or q!={'x':0.,'y':0.,'z':0.,'w':1.}:return False
   if data[4*k:4*k+4]!=[speed,0.,0.,t] or any(type(v) not in (int,float) or not math.isfinite(v) for v in data[4*k:4*k+4]):return False
  return data[-1]>=24 and poses[-1]['pose']['position']['x']>=speed*24
 except (KeyError,TypeError):return False

class NativeCheckpointAudit:
 """Verify claimed incremental/rollback work against actual event chronology."""
 def __init__(self):self.checkpoints=[];self.events={};self.last=None;self.corrections=0;self.ordinary=0;self.rewinds=0;self.maximum_steps=0
 def inspect(self,row):
  try:
   w=row['work'];origin=row['origin_ns'];target=row['target_ns'];previous=origin if self.last is None else self.last
   if not self.checkpoints:self.checkpoints=[origin]
   events={(e['applied_sequence'],e['channel']):e for e in row['held_events']}
   if any(events.get(k)!=v for k,v in self.events.items()):return False
   late=[e['publish_end_ns'] for k,e in events.items() if self.last is not None and k not in self.events and e['publish_end_ns']<=previous]
   dirty=min(late) if late else None;rewound=bool(late);before=len(self.checkpoints);chosen=before-1
   if rewound:
    chosen=0
    for k,ns in enumerate(self.checkpoints):
     if ns<dirty:chosen=k
     else:break
   start=self.checkpoints[chosen];invalidated=before-chosen-1
   expected_corrections=self.corrections+int(rewound)
   integer_fields=['cache_before_ns','cache_after_ns','last_requested_ns','requested_delta_ns','integration_start_ns','integration_target_ns','integrated_ns','rollback_ns','late_channel_events_since_last_sensor','state_correction_count','integration_steps','ODE_evaluations','checkpoint_count_before','checkpoint_count_after','invalidated_checkpoint_count','event_element_visits','retained_channel_events']
   if any(type(w.get(k)) is not int or w[k]<0 for k in integer_fields):return False
   if (w.get('schema')!='p1-nominal-checkpoint-work-v1' or w.get('algorithm')!='checkpoint_cached_RK4_replay_v1'
       or type(w.get('cache_rewound')) is not bool or w['cache_rewound']!=rewound or w.get('ordinary_incremental') is not (not rewound)
       or w.get('WCET_qualified') is not False or w.get('late_event_earliest_ns')!=dirty
       or w['cache_before_ns']!=previous or w['cache_after_ns']!=target or w['last_requested_ns']!=previous
       or w['requested_delta_ns']!=target-previous or w['integration_start_ns']!=start or w['integration_target_ns']!=target
       or w['integrated_ns']!=target-start or w['rollback_ns']!=previous-start
       or w['state_correction_count']!=expected_corrections or w['late_channel_events_since_last_sensor']!=len(late)
       or w['checkpoint_count_before']!=before or w['invalidated_checkpoint_count']!=invalidated
       or w['retained_channel_events']!=len(events) or w['event_element_visits']!=2*len(events)
       or w['integration_steps']!=row['integration_steps'] or w['ODE_evaluations']!=16*w['integration_steps']):return False
   limits={'maximum_channel_events':1024,'maximum_event_element_visits':2048,'maximum_checkpoints':2048,'maximum_integration_steps':512,'maximum_full_run_2ms_steps':20000,'maximum_run_duration_ns':40_000_000_000}
   if any(type(w.get(k)) is not int or w[k]!=v for k,v in limits.items()):return False
   if w.get('event_retention_policy')!='retain every authenticated channel event; no clipping or eviction':return False
   cursor=start;expected_steps=0
   for stop in sorted(set(e['publish_end_ns'] for e in events.values() if start<e['publish_end_ns']<=target))+[target]:
    expected_steps+=(stop-cursor+1_999_999)//2_000_000;cursor=stop
   if w['integration_steps']!=expected_steps or expected_steps>512 or len(events)>1024 or target-origin>40_000_000_000:return False
   after=self.checkpoints[:chosen+1]
   if after[-1]<target:after.append(target)
   if w['checkpoint_count_after']!=len(after) or len(after)>2048:return False
   self.checkpoints=after;self.events=events;self.last=target;self.corrections=expected_corrections
   self.ordinary+=int(not rewound);self.rewinds+=int(rewound);self.maximum_steps=max(self.maximum_steps,w['integration_steps']);return True
  except (KeyError,TypeError,ValueError):return False
 def stats(self):return dict(ordinary_queries=self.ordinary,late_event_rewinds=self.rewinds,state_corrections=self.corrections,maximum_native_query_integration_steps=self.maximum_steps,work_is_source_observation_not_WCET_qualification=True)

def phase_metadata_matches(raw,r,closed):
 try:return isinstance(raw,dict) and set(raw)==base.p.RAW_FIELDS and raw.get('schema')=='p1-input-callback-full-cdr-v1' and raw.get('topic')==PHASE and raw.get('message_type')=='std_msgs/msg/String' and raw.get('callback_sequence')==r['callback_sequence'] and raw.get('rmw_implementation')=='rmw_fastrtps_cpp' and raw.get('from_intra_process') is False and r['entry_ns']<=raw.get('entry_steady_ns',0)<=r['observed_ns']<=r['processed_ns']<=closed
 except (KeyError,TypeError):return False

def analyze(run):
 run=Path(run).resolve();files=[p for p in run.rglob('*') if p.is_file()];before={str(p):c36.sha(p) for p in files}
 inherited=base.analyze(run);c=c36.Checks();c.need(inherited.get('passed') is True,'controlled_entire_inherited_evidence',issues=inherited.get('issues'))
 c.need(inherited.get('normal_driver_passed') is True,'controlled_driver_clean')
 inputs=c36.load(run/'inputs.json');case=inputs.get('ordered_stage');c.need(case=='C' and inputs.get('validation_recipe_revision')=='longitudinal-20s-v1' and inputs.get('measurement_seconds')==20,'controlled_preregistered_scope')
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
 c.need(longitudinal_window(window,observer),'longitudinal_20s_all_candidates_accepted_90_consecutive_18s_coverage')
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
  speed=inputs.get('reference_speed_m_s')
  c.need(type(speed) in (int,float) and speed in (.05,.1,.3,.6),'longitudinal_declared_speed')
  rows=c36.lines(run/'synthetic_source/nominal_steps.jsonl');steps=[r for r in rows if r.get('schema')=='p1-controlled-nominal-model-step-v1'];hydro=contract['hydro'];errors=[]
  c.need(bool(steps),'C_actual_model_state_Source_population')
  fixture=c36.load(run/'synthetic_source/owned_manifest.json')
  live=c36.load(run/'live_parameters_synthetic_source.json');parameter=fixture.get('effective_parameters',{}).get('reference_speed_m_s',{})
  c.need(fixture.get('reference_speed_m_s')==speed and parameter.get('type')==3 and parameter.get('value')==speed and live.get('reference_speed_m_s')==parameter,'longitudinal_actual_live_immutable_reference_speed')
  paths=decoded['/path/reference'];profiles=decoded['/path/reference_profile']
  c.need(bool(paths) and len(paths)==len(profiles) and all(longitudinal_reference(a['message'],b['message'],speed) for a,b in zip(paths,profiles)),'longitudinal_entire_201point_reference_40s_and_24s_coverage')
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
  independent=ExactPrefixReplay(hydro);work_audit=NativeCheckpointAudit()
  for row in steps:
   c.need(work_audit.inspect(row),'longitudinal_native_incremental_and_late_rollback_work',sensor_sequence=row['sensor_sequence'])
   x=independent.replay(row);errors.append(max(abs(a-b) for a,b in zip(x,row['state'])))
   for e in row['held_events']:
    a=am.get(e['applied_sequence']);ch=e['channel'];key='left_publish_end_steady_ns' if ch==0 else 'right_publish_end_steady_ns'
    c.need(a is not None and a[key]==e['publish_end_ns'] and a['final_n'][ch]==e['n'],'C_held_event_actual_Applied_binding')
  c.need(bool(errors) and all(math.isfinite(e) for e in errors) and max(errors)<1e-9,'C_independent_Python_Fossen_RK4_full_replay',max_error=max(errors) if errors else None)
  c.need(any(any(abs(v)>1e-6 for v in a['final_n']) for a in applied),'C_actual_nonzero_input')
  c.need(any(any(abs(v)>1e-6 for v in row['state']) for row in steps),'C_actual_nonzero_model_state')
  model={'states_recomputed':len(steps),'maximum_absolute_replay_error':max(errors) if errors else None,'independent_replay':independent.stats(),'native_work_audit':work_audit.stats(),'true_physical_plant_acceptance':False}
 for dep in ['prepare_longitudinal_v1.py','check_longitudinal_v1.py','test_longitudinal_v1.py','check_c38_longitudinal_v1.py','prepare_controlled_v2.py','check_controlled_v2.py','test_controlled_v2.py','prepare_controlled_v1.py','check_controlled_v1.py','test_controlled_v1.py','check_controlled_owner_v1.py','test_controlled_owner_v1.py','check_positive_chain_v1.py']:
  c.need(inputs['tool_sha256'].get(dep)==c36.sha(HERE/dep)==c36.sha(run/(dep+'.snapshot')),'controlled_exact_prerun_tool_binding',tool=dep)
 after={str(p):c36.sha(p) for p in files};c.need(before==after,'controlled_raw_inputs_unchanged')
 return c.result(schema='p1-longitudinal-20s-check/v1',case=case,reference_speed_m_s=inputs.get('reference_speed_m_s'),measurement_seconds=20,window=window,negative=negative,model=model,inherited=inherited,owner_evidence=owner_evidence,storage=storage,phase_recorded=len(phases),phase_received=phase_callback_count,phase_recorded_not_received=sorted(set(pi)-set(received)),jobs=len(jobs),qualifications=base.FLAGS,scope='finite_localhost_DDS_diagnostic_component',stage_qualified=False,execute_qualified=False,research_conclusion=False,input_sha256_before=before,input_sha256_after=after)
def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 try:r=analyze(a.run_dir)
 except Exception as e:r={'schema':'p1-longitudinal-20s-check/v1','passed':False,'reader_error':repr(e),'stage_qualified':False}
 base.write(a.output,r);print(json.dumps({k:r.get(k) for k in ['passed','case','window','negative','model','issues','reader_error']},ensure_ascii=False));return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
