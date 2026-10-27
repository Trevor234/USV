#!/usr/bin/env python3
"""20 s projected-reference nominal diagnostics; complete inherited source/wire/owner guards."""
from pathlib import Path
import argparse,hashlib,json,math,sys,bisect
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import check_c38_pair_wakeup_v1 as base
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
 inputs=c36.load(run/'inputs.json');case=inputs.get('ordered_stage');c.need(case=='C' and inputs.get('validation_recipe_revision')=='reference-pair-wakeup-20s-v1' and inputs.get('measurement_seconds')==20,'controlled_preregistered_scope')
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
 for dep in ['prepare_longitudinal_v1.py','check_longitudinal_v1.py','test_longitudinal_v1.py','check_c38_longitudinal_v1.py','prepare_controlled_v2.py','check_controlled_v2.py','test_controlled_v2.py','prepare_controlled_v1.py','check_controlled_v1.py','test_controlled_v1.py','check_controlled_owner_v1.py','test_controlled_owner_v1.py','check_positive_chain_v1.py','prepare_pair_wakeup_v1.py','check_pair_wakeup_v1.py','test_pair_wakeup_v1.py','check_c38_pair_wakeup_v1.py']:
  c.need(inputs['tool_sha256'].get(dep)==c36.sha(HERE/dep)==c36.sha(run/(dep+'.snapshot')),'controlled_exact_prerun_tool_binding',tool=dep)
 projection=projected_population(run,inputs,contract,observer,decoded,c)
 retries=reference_pair_retry_population(observer,c)
 from cold_start_policy_audit_v1 import analyze as audit_cold_policy
 cold_policy=audit_cold_policy(run,inputs,contract,observer,decoded,c)
 from check_activation_alignment_v1 import analyze as audit_alignment
 alignment=audit_alignment(run,observer,contract,decoded,c)
 performance=projected_performance(run,inputs,window,decoded,c)
 after={str(p):c36.sha(p) for p in files};c.need(before==after,'controlled_raw_inputs_unchanged')
 return c.result(schema='p1-task-time-reference-20s-check/v1',case=case,reference_speed_m_s=inputs.get('reference_speed_m_s'),measurement_seconds=20,window=window,task_time_reference=projection,reference_pair_retry=retries,cold_start_policy=cold_policy,activation_alignment=alignment,performance=performance,negative=negative,model=model,inherited=inherited,owner_evidence=owner_evidence,storage=storage,phase_recorded=len(phases),phase_received=phase_callback_count,phase_recorded_not_received=sorted(set(pi)-set(received)),jobs=len(jobs),qualifications=base.FLAGS,scope='finite_localhost_DDS_diagnostic_component',stage_qualified=False,execute_qualified=False,research_conclusion=False,input_sha256_before=before,input_sha256_after=after)
POLICY='first_target_task_time_profile_v1'
EPOCH_POLICY='first_successful_job_submit_completion_target_sim_v1'
REFERENCE_ABS_TOLERANCE=1e-12
PARENT_RMSE={.05:.014784991510502932,.1:.029260913386751467,.3:.08808870950703403,.6:.15508263209306208}
PARENT_METRICS=HERE.parents[1]/'scheme_A_longitudinal_20261016_19/postrun/ladder_metrics_v1.json'
PARENT_METRICS_SHA='612d3b84dd8065967bbeb6c6222f6ffb186c716624833d2add43afc6cead5831'
PARENT_CONTRACT=HERE.parent/'authored_D1_longitudinal_20261016_v19/controlled_contract_v1.json'
PARENT_CONTRACT_SHA='d3ad712ffa9b835186130917ebc3f8b2075b984e6d85b3424962bed69cca3664'
PROJECTED_CONTRACT_SHA='162741dfb9c1454f8e19fbad41c7b96315544819a688029609488c3778eb510f'
def real(v):return type(v) in (int,float) and math.isfinite(v)
def finite_vector(v,n):return type(v) is list and len(v)==n and all(real(x) for x in v)
def close_numeric(a,b,tol=REFERENCE_ABS_TOLERANCE):return real(a) and real(b) and abs(a-b)<=tol
def normalize(a):return math.atan2(math.sin(a),math.cos(a))
def reference_error(actual,expected):
 if not finite_vector(actual,126) or not finite_vector(expected,126):return None
 errors=[abs(a-b) for a,b in zip(actual,expected)]
 return max(errors) if all(math.isfinite(e) for e in errors) else None
def independent_projection(target,path_message,profile_message,N=20,dt=.2):
 if type(N) is not int or N!=20 or type(dt) not in (int,float) or dt!=.2 or not finite_vector(target,6):raise ValueError('fixed_horizon_or_target_domain')
 poses=path_message['poses'];data=profile_message['data'];dims=profile_message['layout']['dim'];stamp=path_message['header']['stamp']
 if type(poses) is not list or not 2<=len(poses)<=2048 or type(data) is not list or len(data)!=4*len(poses):raise ValueError('path_profile_population')
 if type(stamp.get('sec')) is not int or type(stamp.get('nanosec')) is not int or stamp['sec']<0 or not 0<=stamp['nanosec']<1000000000:raise ValueError('profile_not_synchronized')
 expected_dims=[dict(label='stamp_sec:'+str(stamp['sec']),size=len(poses),stride=4*len(poses)),dict(label='stamp_nanosec:'+str(stamp['nanosec']),size=4,stride=4)]
 if dims!=expected_dims or profile_message['layout'].get('data_offset')!=0:raise ValueError('profile_not_synchronized')
 path=[];profile=[]
 for k,pose in enumerate(poses):
  p=pose['pose']['position'];q=pose['pose']['orientation'];coordinates=[p['x'],p['y'],p['z'],q['x'],q['y'],q['z'],q['w']]
  if not finite_vector(coordinates,7):raise ValueError('path_nonfinite')
  yaw=math.atan2(2*(q['w']*q['z']+q['x']*q['y']),1-2*(q['y']*q['y']+q['z']*q['z']))
  path.append([p['x'],p['y'],yaw]);row=data[4*k:4*k+4]
  if not finite_vector(row,4):raise ValueError('profile_nonfinite')
  if k and row[3]<=profile[-1][3]:raise ValueError('profile_time_not_strictly_increasing')
  profile.append(row)
 stationary=all(p==path[0] and r[0]==0 and r[2]==0 for p,r in zip(path,profile))
 segment=-1;fraction=0.;times=[r[3] for r in profile]
 if stationary:
  px,py=path[0][:2];distance=(target[0]-px)**2+(target[1]-py)**2;t0=times[0]
 else:
  best=math.inf
  for k in range(len(path)-1):
   dx=path[k+1][0]-path[k][0];dy=path[k+1][1]-path[k][1];length2=dx*dx+dy*dy
   if not math.isfinite(length2) or length2<=0:raise ValueError('degenerate_segment_requires_explicit_policy')
   f=max(0.,min(1.,((target[0]-path[k][0])*dx+(target[1]-path[k][1])*dy)/length2))
   x=path[k][0]+f*dx;y=path[k][1]+f*dy;d=(target[0]-x)**2+(target[1]-y)**2
   if d<best:best=d;segment=k;fraction=f;px=x;py=y;distance=d;t0=times[k]+f*(times[k+1]-times[k])
  if segment<0 or not math.isfinite(best):raise ValueError('projection_not_finite')
  if t0+N*dt>times[-1]:raise ValueError('horizon_exceeds_profile')
 if not math.isfinite(distance):raise ValueError('projection_not_finite')
 reference=[];hint=max(0,segment)
 for k in range(N+1):
  tk=t0+k*dt
  while hint<len(path)-1 and times[hint+1]<tk:hint+=1
  if hint==len(path)-1:x,y,psi=path[-1];v=profile[-1][0];r=profile[-1][2]
  else:
   duration=times[hint+1]-times[hint];a=max(0.,min(1.,(tk-times[hint])/duration)) if duration>1e-9 else 0.
   x=path[hint][0]+a*(path[hint+1][0]-path[hint][0]);y=path[hint][1]+a*(path[hint+1][1]-path[hint][1])
   psi=normalize(path[hint][2]+a*normalize(path[hint+1][2]-path[hint][2]));v=profile[hint][0]+a*(profile[hint+1][0]-profile[hint][0]);r=profile[hint][2]+a*(profile[hint+1][2]-profile[hint][2])
  reference.extend([x,y,psi,v,0.,r])
 reference[2]=target[2]+normalize(reference[2]-target[2])
 for k in range(1,N+1):reference[6*k+2]=reference[6*(k-1)+2]+normalize(reference[6*k+2]-reference[6*(k-1)+2])
 if not finite_vector(reference,126):raise ValueError('reference_nonfinite')
 nearest=min(range(len(path)),key=lambda k:math.hypot(path[k][0]-target[0],path[k][1]-target[1]))
 return dict(reference=reference,projection=dict(segment=segment,fraction=fraction,profile_t0=t0,projection_x=px,projection_y=py,squared_distance=distance,stationary=stationary),nearest_index=nearest)
def projected_metadata_matches(source,reconstructed):
 p=source.get('reference_projection');expected=reconstructed['projection']
 if type(p) is not dict or set(p)!=set(expected):return False
 if source.get('reference_mode')!=POLICY or type(source.get('configured_start_offset')) is not int or type(source.get('effective_start_offset')) is not int or source['configured_start_offset']!=0 or source['effective_start_offset']!=0:return False
 if type(p.get('segment')) is not int or p['segment']!=expected['segment'] or type(p.get('stationary')) is not bool or p['stationary']!=expected['stationary']:return False
 if type(source.get('start_index')) is not int or type(source.get('nearest_index')) is not int or source.get('start_index')!=expected['segment'] or source.get('nearest_index')!=reconstructed['nearest_index'] or not close_numeric(source.get('profile_t0'),expected['profile_t0']):return False
 return all(close_numeric(p[k],expected[k]) for k in ['fraction','profile_t0','projection_x','projection_y','squared_distance'])
def independent_task_time(target,path,profile,first_target,initial_t0,current_target):
 if any(type(t) is not int or t<=0 for t in [first_target,current_target]) or current_target<first_target or not real(initial_t0):raise ValueError('epoch_time_domain')
 geometric=independent_projection(target,path,profile)
 if current_target==first_target and not close_numeric(initial_t0,geometric['projection']['profile_t0']):raise ValueError('first_target_alignment')
 speed=profile['data'][0]
 if speed not in PARENT_RMSE or len(path['poses'])!=201 or len(profile['data'])!=804:raise ValueError('static_reference_population_or_speed')
 for k,pose in enumerate(path['poses']):
  position=pose['pose']['position'];orientation=pose['pose']['orientation']
  if [position['x'],position['y'],position['z']]!=[speed*(.2*k),0.,0.] or [orientation['x'],orientation['y'],orientation['z'],orientation['w']]!=[0.,0.,0.,1.] or profile['data'][4*k:4*k+4]!=[speed,0.,0.,.2*k]:raise ValueError('static_reference_content_domain')
 t0=initial_t0+(current_target-first_target)/1e9
 if not real(t0) or t0<0 or t0+4>40:raise ValueError('task_time_horizon_exceeds_profile')
 reference=[];hint=0;start_index=None
 for k in range(21):
  tk=t0+k*.2
  while hint<200 and .2*(hint+1)<tk:hint+=1
  if start_index is None:start_index=hint
  if hint==200:x=speed*40
  else:
   duration=.2*(hint+1)-.2*hint;alpha=max(0.,min(1.,(tk-.2*hint)/duration));x=speed*(.2*hint)+alpha*(speed*(.2*(hint+1))-speed*(.2*hint))
  reference.extend([x,0.,0.,speed,0.,0.])
 reference[2]=target[2]+normalize(reference[2]-target[2])
 for k in range(1,21):reference[6*k+2]=reference[6*(k-1)+2]+normalize(reference[6*k+2]-reference[6*(k-1)+2])
 if current_target==first_target:reference=geometric['reference'];start_index=geometric['projection']['segment']
 return dict(reference=reference,geometric=geometric,profile_t0=t0,start_index=start_index)

def expected_epoch(first,first_projection,current):
 a=first['job'];j=current['job'];binding=['task_generation','model_generation','config_generation','schedule_generation','clock_epoch','run_id','boot_id','contract_hash','nominal_hash']
 out={key:a[key] for key in binding}
 out.update(policy=POLICY,epoch_policy=EPOCH_POLICY,first_job_id=a['job_id'],first_target_sim_ns=a['target_sim_ns'],initial_profile_t0=first_projection['projection']['profile_t0'],epoch_submit_commit_ns=first['submit_commit_ns'],current_target_sim_ns=j['target_sim_ns'],profile_t0=first_projection['projection']['profile_t0']+(j['target_sim_ns']-a['target_sim_ns'])/1e9)
 for k in ['path','profile']:out[k+'_fingerprint']=first['input_provenance']['ref_selection'][k+'_fingerprint']
 return out

def task_time_metadata_matches(source,reconstructed,expected):
 actual=source.get('reference_epoch')
 if type(actual) is not dict or set(actual)!=set(expected):return False
 for key,value in expected.items():
  if key in ['profile_t0','initial_profile_t0']:
   if not close_numeric(actual[key],value):return False
  elif type(actual[key]) is not type(value) or actual[key]!=value:return False
 geom=reconstructed['geometric'];projection=source.get('reference_projection')
 if type(projection) is not dict or set(projection)!=set(geom['projection']):return False
 for key,value in geom['projection'].items():
  if type(value) in (int,bool):
   if type(projection[key]) is not type(value) or projection[key]!=value:return False
  elif not close_numeric(projection[key],value):return False
 if source.get('reference_mode')!=POLICY:return False
 for key,value in [('configured_start_offset',0),('effective_start_offset',0),('nearest_index',geom['nearest_index']),('start_index',reconstructed['start_index'])]:
  if type(source.get(key)) is not int or source[key]!=value:return False
 return close_numeric(source.get('profile_t0'),reconstructed['profile_t0'])

def projected_population(run,inputs,contract,observer,decoded,c):
 c.need(c36.sha(PARENT_CONTRACT)==PARENT_CONTRACT_SHA,'projected_parent_contract_exact_pin')
 expected=c36.load(PARENT_CONTRACT);expected.update(reference_start_offset=0,reference_sampling_policy=POLICY,diagnostic_contract_revision=10,activation_state_policy="latest_causal_sensor_frame_then_one_revalidation_v1",activation_sensor_history_capacity=32,activation_validation_attempts=2,cold_start_policy="current_job_free_once_then_fixed050_three_rti_v1",reference_epoch_policy=EPOCH_POLICY,preparation_retry_policy="authenticated_phase_reference_pair_completion_v1")
 c.need(base.exact(contract,expected) and inputs['contract_sha256']==PROJECTED_CONTRACT_SHA,'task_time_only_declared_sampling_and_cold_policy_fields_change_no_numeric_guard_or_objective_change')
 fixture=c36.load(run/'synthetic_source/owned_manifest.json');endpoints=fixture['endpoints']
 versions={kind:c.index([r for r in observer if r.get('type')==kind+'_version'],lambda r:r['received_sequence'],'projected_'+kind+'_Source_version') for kind in ['path','profile']}
 cache={};maximum=0.;summaries=[];jobs=[r for r in observer if r.get('type')=='job'];first_projection=None
 epochs=[r for r in observer if r.get('type')=='reference_epoch_committed'];c.need(len(epochs)==1,'task_time_exactly_one_epoch_commit')
 if jobs and len(epochs)==1:c.need(epochs[0].get('job_id')==jobs[0]['job']['job_id'] and epochs[0].get('submit_commit_ns')==jobs[0]['submit_commit_ns'] and epochs[0].get('first_job_G_T_reference_bit_identical') is True and epochs[0].get('reference_epoch')==jobs[0].get('reference_epoch'),'task_time_epoch_at_first_actual_submit_completion')
 for source in jobs:
  j=source['job'];provenance=source['input_provenance'];selected={}
  for kind,topic,typ in [('path','/path/reference','nav_msgs/msg/Path'),('profile','/path/reference_profile','std_msgs/msg/Float64MultiArray')]:
   sequence=provenance[kind+'_sequence'];event=versions[kind].get(sequence);key=(kind,sequence)
   c.need(event is not None,'projected_selected_reference_received_Source_exists',job_id=j['job_id'],interface=kind,sequence=sequence)
   if event is None:continue
   if key not in cache:
    raw=event.get('raw_input');message=base.p.decode_callback(raw,c,{'projected_interface':kind,'sequence':sequence});gid=[e['gid'] for e in endpoints if e['kind']=='publisher' and e['topic']==topic and e['type']==typ]
    c.need(isinstance(raw,dict) and set(raw)==base.p.RAW_FIELDS and raw.get('topic')==topic and raw.get('message_type')==typ and raw.get('callback_sequence')==sequence and raw.get('rmw_implementation')=='rmw_fastrtps_cpp' and raw.get('from_intra_process') is False and len(gid)==1 and raw.get('publisher_gid')==gid[0],'projected_selected_reference_actual_full_CDR_GID',interface=kind,sequence=sequence)
    c.need(message is not None and any(base.exact(message,r['message']) for r in decoded[topic]),'projected_selected_reference_full_typed_Storage_subset',interface=kind,sequence=sequence)
    c.need(event.get('valid') is True and event.get('resource_valid') is True,'projected_selected_reference_native_input_admitted',interface=kind,sequence=sequence)
    cache[key]=message
   selected[kind]=cache[key]
   c.need(event['input_commit_ordinal']<=provenance['input_commit_ordinal'] and event['processed_ns']<=j['freeze_ns'] and provenance['ref_selection'][kind+'_sequence']==sequence,'projected_selected_reference_frozen_provenance',job_id=j['job_id'],interface=kind)
  if any(selected.get(k) is None for k in ['path','profile']):continue
  stamp=selected['path']['header']['stamp'];stamp_ns=stamp['sec']*1000000000+stamp['nanosec']
  c.need(provenance['path_stamp_ns']==provenance['profile_stamp_ns']==stamp_ns and provenance['ref_selection']['path_stamp']==provenance['ref_selection']['profile_stamp']==stamp,'projected_selected_actual_pair_stamp_exact',job_id=j['job_id'])
  try:
   if first_projection is None:first_projection=independent_projection(j['target_state'],selected['path'],selected['profile'],j['N'],j['dt'])
   reconstructed=independent_task_time(j['target_state'],selected['path'],selected['profile'],jobs[0]['job']['target_sim_ns'],first_projection['projection']['profile_t0'],j['target_sim_ns'])
   expected=expected_epoch(jobs[0],first_projection,source)
   for key in ['task_generation','model_generation','config_generation','schedule_generation','clock_epoch','run_id','boot_id','contract_hash','nominal_hash']:c.need(type(j[key]) is type(expected[key]) and j[key]==expected[key],'task_time_immutable_actual_Job_lifecycle_binding',job_id=j['job_id'],key=key)
   for kind in ['path','profile']:c.need(provenance['ref_selection'][kind+'_fingerprint']==expected[kind+'_fingerprint']==versions[kind][provenance[kind+'_sequence']]['fingerprint'],'task_time_fixed_actual_reference_content_fingerprint',job_id=j['job_id'],interface=kind)
   if source is jobs[0]:c.need(reference_error(j['reference'],first_projection['reference'])==0.,'task_time_first_actual_Job_G_T_reference_exact')
   if summaries:c.need(j['target_sim_ns']>summaries[-1]['target_sim_ns'],'task_time_strict_actual_target_sim_progression',job_id=j['job_id'])
  except Exception as e:c.need(False,'projected_independent_reconstruction_domain',job_id=j['job_id'],error=repr(e));continue
  error=reference_error(j.get('reference'),reconstructed['reference'])
  if error is not None:maximum=max(maximum,error)
  c.need(error is not None and error<=REFERENCE_ABS_TOLERANCE,'projected_all_126_actual_Job_reference_fields_independently_reconstructed',job_id=j['job_id'],maximum_absolute_error=error,actual_shape=len(j['reference']) if isinstance(j.get('reference'),list) else None,absolute_tolerance=REFERENCE_ABS_TOLERANCE)
  c.need(task_time_metadata_matches(source,reconstructed,expected),'projected_actual_Source_metadata_matches_independent_projection',job_id=j['job_id'])
  summaries.append(dict(job_id=j['job_id'],path_received_sequence=provenance['path_sequence'],profile_received_sequence=provenance['profile_sequence'],target_sim_ns=j['target_sim_ns'],segment=reconstructed['geometric']['projection']['segment'],fraction=reconstructed['geometric']['projection']['fraction'],profile_t0=reconstructed['profile_t0'],geometric_profile_t0=reconstructed['geometric']['projection']['profile_t0'],reference_x_minus_target_m=j['reference'][0]-j['target_state'][0],maximum_absolute_reference_error=error))
 c.need(bool(jobs) and len(summaries)==len(jobs),'projected_entire_Job_population_reconstructed_without_clipping')
 return dict(policy=POLICY,actual_jobs=len(jobs),reconstructed_jobs=len(summaries),selected_received_reference_messages=len(cache),maximum_absolute_reference_error=maximum,reference_absolute_tolerance=REFERENCE_ABS_TOLERANCE,epoch_policy=EPOCH_POLICY,epoch_commits=len(epochs),first_epoch=expected_epoch(jobs[0],first_projection,jobs[0]) if jobs and first_projection else None,built_from='first actual Job.target_sim plus its independently reconstructed geometric t0; every actual selected CDR and Storage pair; no per-tick reanchor',metadata_interface='seven Result fields plus separate zero offsets/nearest/start/profile_t0',all_published_reference_packets_received_claimed=False,jobs=summaries)
def performance_metrics(samples,start,end,speed):
 if type(start) is not int or type(end) is not int or end-start<20000000000 or type(speed) not in (int,float) or speed not in PARENT_RMSE:raise ValueError('performance_window_or_speed_domain')
 if type(samples) is not list or not samples or any(type(t) is not int or not real(u) for t,u in samples):raise ValueError('performance_samples_domain')
 if any(samples[k][0]<=samples[k-1][0] for k in range(1,len(samples))):raise ValueError('performance_sample_time_order')
 window=[(t,u) for t,u in samples if start<=t<end];last=[u for t,u in window if end-5000000000<=t]
 if not window or not last:raise ValueError('empty_preregistered_performance_window')
 mean=math.fsum(last)/len(last);rmse=math.sqrt(math.fsum((u-speed)**2 for _,u in window)/len(window));relative=abs(mean-speed)/speed;limit=.5*PARENT_RMSE[speed]
 return dict(measurement_sensor_count=len(window),last5s_sensor_count=len(last),start_ready_ns=start,end_driver_requested_ns=end,last5s_start_ns=end-5000000000,last5s_mean_surge_m_s=mean,last5s_relative_mean_error=relative,last5s_relative_mean_error_limit=.05,measured_surge_RMSE_m_s=rmse,parent_fixed_RMSE_m_s=PARENT_RMSE[speed],RMSE_limit_m_s=limit,last5s_mean_passed=relative<=.05,RMSE_passed=rmse<=limit,passed=relative<=.05 and rmse<=limit,window_semantics='Source target time, actual Odom-body surge; Ready inclusive to driver close request exclusive; shutdown tail excluded')
def projected_performance(run,inputs,window,decoded,c):
 c.need(c36.sha(PARENT_METRICS)==PARENT_METRICS_SHA,'projected_parent_performance_frozen_SHA')
 metrics=c36.load(PARENT_METRICS);c.need({r['reference_speed_m_s']:r['measured_surge_RMSE_m_s'] for r in metrics['cases']}==PARENT_RMSE,'projected_preregistered_parent_RMSE_constants_exact')
 rows=[r for r in c36.lines(run/'synthetic_source/nominal_steps.jsonl') if r.get('schema')=='p1-controlled-nominal-model-step-v1'];odoms=decoded['/wamv/sensors/position/ground_truth_odometry']
 c.need(len(rows)==len(odoms),'projected_performance_complete_actual_Odom_Source_population')
 samples=[]
 for k,(row,record) in enumerate(zip(rows,odoms)):
  m=record['message'];stamp=m['header']['stamp'];u=m['twist']['twist']['linear']['x']
  c.need(row['sensor_sequence']==k+1 and row['sim_stamp_ns']==stamp['sec']*1000000000+stamp['nanosec'] and row['state'][3]==u,'projected_performance_actual_stored_body_surge_binding',sensor_sequence=k+1)
  samples.append((row['target_ns'],u))
 try:result=performance_metrics(samples,window['start_ready_ns'],window['end_driver_requested_ns'],inputs['reference_speed_m_s'])
 except Exception as e:c.need(False,'projected_performance_numeric_domain',error=repr(e));return {'passed':False,'reader_error':repr(e)}
 c.need(result['last5s_mean_passed'],'projected_preregistered_last5s_mean_surge_relative_error_5percent',observed=result['last5s_relative_mean_error'],limit=.05)
 c.need(result['RMSE_passed'],'projected_preregistered_whole_measurement_RMSE_halved_parent',observed=result['measured_surge_RMSE_m_s'],limit=result['RMSE_limit_m_s'])
 result.update(parent_metrics_path=str(PARENT_METRICS),parent_metrics_sha256=PARENT_METRICS_SHA,all_evidence_populations_checked_before_windowed_metrics=True,shutdown_tail_used_for_performance=False,stage_qualified=False,research_conclusion=False)
 return result

RETRY_POLICY='authenticated_phase_reference_pair_completion_v1'
RETRY_FIELDS={'type','policy','trigger','input_commit_ordinal','path_sequence','profile_sequence','path_stamp_ns','profile_stamp_ns','started_ns','completed_ns','phase_still_awaiting','froze','stage_qualified'}
def retry_shape(row):
 if type(row) is not dict or set(row)!=RETRY_FIELDS or row['type']!='reference_pair_retry' or row['policy']!=RETRY_POLICY or row['trigger'] not in ['path','profile'] or row['stage_qualified'] is not False:return False
 if any(type(row[k]) is not int or row[k]<=0 for k in ['input_commit_ordinal','started_ns','completed_ns']):return False
 if any(type(row[k]) is not int or row[k]<0 for k in ['path_sequence','profile_sequence']):return False
 if any(type(row[k]) is not int for k in ['path_stamp_ns','profile_stamp_ns']):return False
 trigger=row['trigger'];other='path' if trigger=='profile' else 'profile'
 if row[trigger+'_sequence']<=0:return False
 if row[other+'_sequence']==0 and (row[other+'_stamp_ns']!=-1000000001 or row['froze'] is not False or row['phase_still_awaiting'] is not True):return False
 return row['completed_ns']>=row['started_ns'] and type(row['froze']) is bool and type(row['phase_still_awaiting']) is bool and row['froze'] is (not row['phase_still_awaiting'])
def reference_pair_retry_population(observer,c):
 retries=[r for r in observer if r.get('type')=='reference_pair_retry'];freezes=[r for r in observer if r.get('type')=='controlled_phase_freeze'];jobs=[r for r in observer if r.get('type')=='job'];versions={kind:{r['received_sequence']:r for r in observer if r.get('type')==kind+'_version'} for kind in ['path','profile']};successful=[];missing_opposite=0
 for row in retries:
  c.need(retry_shape(row),'pair_retry_exact_Source_domain')
  if not retry_shape(row):continue
  matches=[f for f in freezes if row['started_ns']<=f['freeze_ns']<=row['completed_ns']]
  c.need(len(matches)==(1 if row['froze'] else 0),'pair_retry_actual_freeze_population_exact')
  for kind in ['path','profile']:
   if row[kind+'_sequence']==0:
    absent=not any(r['input_commit_ordinal']<=row['input_commit_ordinal'] for r in versions[kind].values())
    c.need(absent and kind!=row['trigger'] and row['froze'] is False and row['phase_still_awaiting'] is True,'pair_retry_missing_opposite_actual_prefix',interface=kind);missing_opposite+=1;continue
   source=versions[kind].get(row[kind+'_sequence']);c.need(source is not None and source['input_commit_ordinal']<=row['input_commit_ordinal'] and source['processed_ns']<=row['started_ns'],'pair_retry_actual_committed_reference_Source',interface=kind)
  trigger=versions[row['trigger']].get(row[row['trigger']+'_sequence']);c.need(trigger is not None and trigger['valid'] is True and trigger['resource_valid'] is True and trigger['input_commit_ordinal']==row['input_commit_ordinal'],'pair_retry_only_after_valid_trigger_commit')
  if row['froze'] and len(matches)==1:
   f=matches[0];bound=[j for j in jobs if j['job']['target_tick']==f['target_tick'] and j['job']['freeze_ns']==f['freeze_ns']]
   c.need(row['path_stamp_ns']==row['profile_stamp_ns'] and f['freeze_ns']<=f['deadline_ns'] and len(bound)==1,'pair_retry_same_stamp_original_deadline_and_actual_submitted_Job')
   successful.append(dict(trigger=row['trigger'],target_tick=f['target_tick'],job_id=bound[0]['job']['job_id'] if len(bound)==1 else None,remaining_deadline_ns=f['deadline_ns']-f['freeze_ns']))
 return dict(policy=RETRY_POLICY,actual_retry_events=len(retries),missing_opposite_startup_records=missing_opposite,successful_reference_completion_freezes=len(successful),successful=successful,all_events_checked=True,zero_retries_does_not_prove_interleaving_coverage=True,stage_qualified=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 try:r=analyze(a.run_dir)
 except Exception as e:r={'schema':'p1-task-time-reference-20s-check/v1','passed':False,'reader_error':repr(e),'stage_qualified':False}
 base.write(a.output,r);print(json.dumps({k:r.get(k) for k in ['passed','case','window','negative','model','issues','reader_error']},ensure_ascii=False));return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
