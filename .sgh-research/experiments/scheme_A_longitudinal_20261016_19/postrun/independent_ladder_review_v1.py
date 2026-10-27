from pathlib import Path
from collections import Counter,defaultdict
import json,hashlib,sqlite3,math,sys,xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
D=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_longitudinal_20261016_19')
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_longitudinal_20261016_v19'
issues=[];cache={}
def sha(p):
 p=Path(p);k=(str(p),p.stat().st_size,p.stat().st_mtime_ns)
 if k not in cache:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
  cache[k]=h.hexdigest()
 return cache[k]
def load(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(s) for s in Path(p).read_text().splitlines()]
def need(ok,code,**context):
 if not ok:issues.append(dict(code=code,**context))
def binding(p):p=Path(p);return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)
def plain(x):
 if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [plain(v) for v in x]
 if hasattr(x,'tolist'):return plain(x.tolist())
 return x
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict
classes={}
def decode(blob,typ):
 if typ not in classes:classes[typ]=get_message(typ)
 return plain(dict(message_to_ordereddict(deserialize_message(blob,classes[typ]))))
def canonical_geometry(rows):
 points=[];history=[];rollbacks=0;steps=0
 for row in rows:
  origin,target=row['origin_ns'],row['target_ns'];events=sorted(row['held_events'],key=lambda e:(e['publish_end_ns'],e['channel']))
  if not points:points=[(origin,0)]
  common=0
  while common<min(len(events),len(history)) and events[common]==history[common]:common+=1
  changed=min([e['publish_end_ns'] for e in events[common:]]+[e['publish_end_ns'] for e in history[common:]],default=None)
  if changed is not None and changed<=points[-1][0]:
   points=[p for p in points if p[0]<changed] or [(origin,0)];rollbacks+=1
   if changed<=origin:points=[(origin,0)]
  cursor,index=points[-1]
  def put(ns,index):
   if points and points[-1][0]==ns:points[-1]=(ns,index)
   else:points.append((ns,index))
  def advance(until,event_boundary):
   nonlocal cursor,steps
   while cursor<until:
    delta=min(2000000,until-cursor);cursor+=delta;steps+=1
    if delta==2000000 or event_boundary and cursor==until:put(cursor,index)
  while index<len(events) and events[index]['publish_end_ns']<=target:
   when=events[index]['publish_end_ns']
   if when>cursor:advance(when,True)
   index+=1;put(cursor,index)
  advance(target,False);history=events
 return dict(rollback_count=rollbacks,integration_step_count=steps,scope='timestamp/checkpoint geometry only; no numerical state seed or recomputation')
reports=[];all_raw_pins={};total_accepted=total_attempts=total_states=0
for tag,run_name,speed in [('s005_01','longitudinal_s005_01',.05),('s010_01','longitudinal_s010_01',.1),('s030_01','longitudinal_s030_01',.3),('s060_01','longitudinal_s060_01',.6)]:
 start_issues=len(issues);run=N/'runs'/run_name;rp=D/'runs'/tag/'check_result.json';report=load(rp);inputs=load(run/'inputs.json');result=load(run/'result.json')
 before=report['input_sha256_before'];need(before==report['input_sha256_after'],'locked_checker_input_maps_equal',run=run_name)
 for p,digest in before.items():need(sha(p)==digest,'locked_checker_input_current_SHA',run=run_name,path=p)
 for rel,digest in inputs['tool_sha256'].items():
  need(sha(N/rel)==digest==sha(run/(rel.replace('/','__')+'.snapshot')),'whole_prerun_checker_recipe_SHA',run=run_name,tool=rel)
 for role,pin in inputs['source_bundles'].items():
  need(sha(pin['path'])==pin['sha256'],'source_bundle_SHA',run=run_name,role=role)
  for item in load(pin['path'])['files'].values():need(sha(item['path'])==item['sha256'],'source_file_SHA',path=item['path'])
 for role,b in inputs['builds'].items():need(sha(b['binary'])==b['binary_sha256'],'actual_selected_binary_SHA',role=role)
 need(report['passed'] is True and report.get('issues')==[] and all(v is False for v in report['qualifications'].values()),'locked_full_checker_passed_without_qualifications',run=run_name)
 need(result['passed'] is True and result['cleanup_complete'] is True and result['cleanup_within_budget'] is True and all(v==0 for v in result['owned_role_returncodes'].values()),'all_five_roles_closed_returned_zero',run=run_name)
 need(set(result['cleanup'])=={'publisher','worker','observer','synthetic_source','recorder'} and all(v['remaining_members']==[] and v['cleanup_complete'] is True for v in result['cleanup'].values()),'closed_groups_empty',run=run_name)
 sources={k:run/k for k in ['observer/source.jsonl','worker/source.jsonl','publisher/controlled_source.jsonl','synthetic_source/nominal_steps.jsonl','synthetic_source/transport_source.jsonl','owned_process_ledger.jsonl']}
 obs=lines(sources['observer/source.jsonl']);owner=lines(sources['publisher/controlled_source.jsonl']);model=lines(sources['synthetic_source/nominal_steps.jsonl']);transport=lines(sources['synthetic_source/transport_source.jsonl']);steps=[r for r in model if r.get('schema')=='p1-controlled-nominal-model-step-v1']
 need(obs[-1]['type']=='source_summary' and owner[-1]['type']=='controlled_owner_source_closed' and model[-1]['type']=='nominal_source_closed','native_Source_populations_closed',run=run_name)
 for p in sources.values():all_raw_pins[str(p)]=sha(p)
 dbs=sorted((run/'recorder/bag').glob('*.db3'));need(bool(dbs),'SQLite_present',run=run_name)
 blobs=defaultdict(list);types={};dbfacts=[]
 for db in dbs:
  conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.execute('PRAGMA query_only=ON');integrity=conn.execute('PRAGMA quick_check').fetchall();need(integrity==[('ok',)],'SQLite_quick_check',run=run_name)
  topic_info={r[0]:(r[1],r[2]) for r in conn.execute('SELECT id,name,type FROM topics')}
  for topic_id,blob in conn.execute('SELECT topic_id,data FROM messages ORDER BY id'):
   name,typ=topic_info[topic_id];types[name]=typ;blobs[name].append(bytes(blob))
  dbfacts.append({**binding(db),'quick_check':'ok','rows':sum(conn.execute('SELECT count(*) FROM messages').fetchone())});conn.close()
 counts={t:len(v) for t,v in blobs.items()};expected=report['storage']['actual_counts']
 need(all(counts.get(t,0)==v for t,v in expected.items()) and not set(counts)-set(expected),'actual_SQLite_whole_topic_counts_equal_locked_report',run=run_name)
 need(sum(counts.values())==report['storage']['total_messages'],'actual_SQLite_total_count',run=run_name)
 transport_hashes=defaultdict(list)
 for r in transport:transport_hashes[r['topic']].append(r['payload_sha256'])
 need(all([hashlib.sha256(b).hexdigest() for b in data]==transport_hashes[t] for t,data in blobs.items()),'actual_SQLite_all_CDR_sequences_equal_independent_transport_Source',run=run_name)
 wanted=['/research/control/applied','/p1/execution_decision','/p1/controlled_owner_phase','/path/reference','/path/reference_profile','/wamv/sensors/position/ground_truth_odometry','/wamv/sensors/imu/imu/data','/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust']
 decoded={t:[decode(b,types[t]) for b in blobs[t]] for t in wanted}
 applied=decoded['/research/control/applied'];decisions=decoded['/p1/execution_decision'];phase_wires=[m['data'] for m in decoded['/p1/controlled_owner_phase']];phases=[json.loads(s) for s in phase_wires]
 ready=[r for r in obs if r['type']=='legacy_ready'];close=[r for r in obs if r['type']=='adapter_driver_close_observed'];need(len(ready)==len(close)==1,'single_native_ready_and_close',run=run_name);begin=ready[0]['readiness']['legacy_ready_ns'];end=close[0]['requested_ns']
 window=[d for d in decisions if begin<=d['activation_commit_ns']<end];attempts=[d for d in window if d['job_id']>0];accepted=[d for d in attempts if d['candidate_accepted'] is True];streak=longest=0;prev=None
 for d in window:
  if d['candidate_accepted'] and d['job_id']>0:
   ident=tuple(d[k] for k in ('task_generation','model_generation','config_generation','schedule_generation','clock_epoch'));streak=streak+1 if prev is not None and prev==(ident,d['tick']-1) else 1;prev=(ident,d['tick']);longest=max(longest,streak)
  else:streak=0;prev=None
 need(len(accepted)==len(attempts)==report['window']['accepted']==report['window']['attempts'] and longest==report['window']['consecutive_accepted']>=90 and all(d['skipped_ticks']==0 for d in window) and end-begin>=20_000_000_000 and accepted[-1]['activation_commit_ns']-accepted[0]['activation_commit_ns']>=18_000_000_000,'actual_SQLite_all_candidate_activations_accepted_in_live_window',run=run_name)
 need(close[0]['owner_process_alive'] is True and not any(d['candidate_accepted'] and d['activation_commit_ns']>close[0]['observed_ns'] for d in decisions),'live_owner_no_post_close_acceptance',run=run_name)
 for ch,topic in enumerate(['/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust']):need([m['data'] for m in decoded[topic]]==[a['final_n'][ch] for a in applied if a['left_publish_success' if ch==0 else 'right_publish_success']],'actual_physical_Float64_payloads_match_Applied',run=run_name,channel=ch)
 aevents={r['applied_sequence']:r for r in owner if r['type']=='controlled_Applied_emitted'};pevents=[r for r in owner if r['type']=='controlled_phase_emitted'];phase_map={p['decision_sequence']:p for p in phases};need(len(pevents)==len(phases)==len(phase_map),'whole_phase_Source_SQLite_population',run=run_name)
 for r in pevents:
  p=r['phase'];a=aevents[p['applied_sequence']];need(p==phase_map[p['decision_sequence']] and a['applied_publish_end_ns']<=p['emitted_ns']<=r['phase_publish_start_ns']<=r['phase_publish_end_ns'],'actual_Applied_DDS_completed_before_each_phase',run=run_name)
 need(len(steps)==len(decoded['/wamv/sensors/position/ground_truth_odometry'])==len(decoded['/wamv/sensors/imu/imu/data'])==model[-1]['model_steps'],'whole_sensor_Source_SQLite_population',run=run_name)
 for row,o,i in zip(steps,decoded['/wamv/sensors/position/ground_truth_odometry'],decoded['/wamv/sensors/imu/imu/data']):
  x=row['state'];p=o['pose']['pose'];t=o['twist']['twist'];s=o['header']['stamp'];q=dict(x=0.,y=0.,z=math.sin(x[2]/2),w=math.cos(x[2]/2))
  need([p['position']['x'],p['position']['y'],p['position']['z']]==[x[0],x[1],0.] and p['orientation']==q==i['orientation'] and [t['linear']['x'],t['linear']['y'],t['angular']['z']]==[x[3],x[4],x[5]] and i['angular_velocity']['z']==x[5] and s==i['header']['stamp'] and s['sec']*10**9+s['nanosec']==row['sim_stamp_ns'],'actual_SQLite_sensor_state_equals_model_Source',run=run_name,sensor=row['sensor_sequence'])
 fixture=load(run/'synthetic_source/owned_manifest.json');need(fixture['effective_parameters']['reference_speed_m_s']['value']==fixture['reference_speed_m_s']==inputs['reference_speed_m_s']==report['reference_speed_m_s']==speed and fixture['reference_points']==201 and fixture['reference_duration_s']==40.,'actual_speed_config_and_long_reference_manifest',run=run_name)
 paths=decoded['/path/reference'];profiles=decoded['/path/reference_profile'];need(len(paths)==len(profiles)>0,'full_reference_population',run=run_name)
 for p,f in zip(paths,profiles):
  need(len(p['poses'])==201 and len(f['data'])==804 and p['header']['stamp']['sec']==int(f['layout']['dim'][0]['label'].split(':')[1]) and p['header']['stamp']['nanosec']==int(f['layout']['dim'][1]['label'].split(':')[1]),'actual_201_reference_shape_stamp',run=run_name)
  need(all(p['poses'][k]['pose']['position']==dict(x=speed*(.2*k),y=0.,z=0.) and f['data'][4*k:4*k+4]==[speed,0.,0.,.2*k] for k in range(201)) and p['poses'][-1]['pose']['position']['x']>=speed*24,'actual_full_reference_payload_and_24second_coverage',run=run_name)
 rewound=[r for r in steps if r['work']['cache_rewound']];ordinary=[r for r in steps if r['work']['ordinary_incremental']];maxsteps=max(r['work']['integration_steps'] for r in steps);late_channels=sum(r['work']['late_channel_events_since_last_sensor'] for r in steps)
 need(len(rewound)==report['model']['native_work_audit']['late_event_rewinds']==steps[-1]['work']['state_correction_count'] and maxsteps==report['model']['native_work_audit']['maximum_native_query_integration_steps'] and all(r['work']['integration_steps']<=512 and r['work']['ODE_evaluations']==16*r['work']['integration_steps'] and r['work']['cache_after_ns']==r['target_ns'] and r['work']['integrated_ns']==r['target_ns']-r['work']['integration_start_ns'] and r['work']['rollback_ns']==r['work']['cache_before_ns']-r['work']['integration_start_ns'] and r['work']['WCET_qualified'] is False for r in steps),'actual_native_work_counters_and_budgets',run=run_name)
 geometry=canonical_geometry(steps);need(geometry['rollback_count']==report['model']['independent_replay']['late_input_rollbacks'] and geometry['integration_step_count']==report['model']['independent_replay']['integration_steps'],'independent_canonical_timestamp_geometry_reproduces_locked_counts',run=run_name)
 maximum=float(report['model']['maximum_absolute_replay_error']);need(0<=maximum<1e-9 and report['model']['states_recomputed']==len(steps) and report['model']['independent_replay']['Source_state_used_as_seed'] is False,'locked_full_numerical_replay_statistics',run=run_name)
 nonzero_applied=sum(any(abs(v)>1e-6 for v in a['final_n']) for a in applied);nonzero_states=sum(any(abs(v)>1e-6 for v in row['state']) for row in steps);need(nonzero_applied>0 and nonzero_states>0,'actual_nonzero_input_and_SQLite_bound_state',run=run_name)
 total_accepted+=len(accepted);total_attempts+=len(attempts);total_states+=len(steps)
 important=[run/'inputs.json',run/'result.json',run/'synthetic_source/owned_manifest.json',run/'publisher/owned_manifest.json',run/'observer/witness.json',run/'recorder/bag/metadata.yaml',*sources.values()]
 reports.append(dict(run_id=run_name,passed=len(issues)==start_issues,speed_m_s=speed,accepted=len(accepted),candidate_activations=len(attempts),longest_consecutive_accepted=longest,live_window_ns=end-begin,accepted_span_ns=accepted[-1]['activation_commit_ns']-accepted[0]['activation_commit_ns'],sensor_states=len(steps),actual_nonzero_Applied=nonzero_applied,actual_nonzero_states=nonzero_states,actual_max_abs_thrust_n=max(abs(v) for a in applied for v in a['final_n']),actual_final_state=steps[-1]['state'],phase_population=len(phases),all_five_roles_reaped=True,close_elapsed_ns=result['close_elapsed_ns'],native_work=dict(actual_rewound_samples=len(rewound),actual_late_channel_events=late_channels,ordinary_samples=len(ordinary),maximum_steps_per_query=maxsteps,final_state_correction_count=steps[-1]['work']['state_correction_count'],WCET_qualified=False),independent_timestamp_geometry=geometry,locked_numerical_checker_max_error=maximum,numerical_checker_error_recomputed_in_this_review=False,locked_numerical_checker_scope='existing exactprefix canonical-grid numerical report, all raw input and checker recipe SHA independently reverified; this review independently reproduces timestamp geometry and Source/SQLite joins',SQLite=dbfacts,SQLite_topic_counts=counts,locked_report=binding(rp),verified_locked_input_files=len(before),verified_checker_tools=len(inputs['tool_sha256']),raw_input_manifest_sha256=hashlib.sha256(json.dumps(before,sort_keys=True,separators=(',',':')).encode()).hexdigest(),evidence={str(p.relative_to(run)):binding(p) for p in important},actual_late_samples=[dict(sensor_sequence=r['sensor_sequence'],target_ns=r['target_ns'],earliest_late_event_ns=r['work']['late_event_earliest_ns'],rollback_ns=r['work']['rollback_ns'],integration_steps=r['work']['integration_steps']) for r in rewound]))
 for p,digest in before.items():need(sha(p)==digest,'raw_inputs_unchanged_after_independent_read',run=run_name,path=p)
 need(sha(rp)==reports[-1]['locked_report']['sha256'],'locked_report_unchanged',run=run_name)
xml=D/'build/controlled_fixture_attempt01/cmake_build/test_results/p1_controlled_phase_fixture/test_controlled_dynamic_fixture.gtest.xml';tree=ET.parse(xml).getroot();native_late=[dict(name=r.attrib['name'],status=r.attrib.get('status'),failures=len(r.findall('failure'))) for r in tree.findall('.//testcase') if 'Late' in r.attrib['name'] or 'Checkpoint' in r.attrib['name'] or 'Budget' in r.attrib['name']]
need(all(r['failures']==0 for r in native_late) and len(native_late)>=4,'native_late_and_cap_component_tests_preserved')
need(total_accepted==total_attempts==408 and total_states==4865,'four_level_total_population')
out=dict(schema='p1-longitudinal-independent-ladder-review-v1',passed=not issues,issues=issues,case_count=4,actual_candidate_activations=total_attempts,actual_accepted=total_accepted,actual_SQLite_bound_sensor_states=total_states,cases=reports,native_late_tests=dict(evidence=binding(xml),cases=native_late,scope='finite native component tests; not actual DDS late input'),late_input_interpretation='First three runs have zero actual native rewind samples. The .6 m/s run has 69 actual native sensor-checkpoint rewinds and 69 state corrections; independent canonical 2 ms committed-checkpoint geometry has 44 invalidations. Different reusable checkpoint boundaries make these distinct valid counters; actual Source late events are separately bound above.',readonly=True,new_ROS_nodes_started=False,stage_qualified=False,execute_qualified=False,research_conclusion=False,true_Plant_acceptance_observed=False,review_recipe=binding(Path(__file__)))
path=D/'postrun/independent_ladder_review_v1.json'
with path.open('x') as f:json.dump(out,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps(dict(path=str(path),sha256=sha(path),passed=not issues,issues=issues,accepted=total_accepted,states=total_states,native_rewinds=[r['native_work']['actual_rewound_samples'] for r in reports],canonical_rollbacks=[r['independent_timestamp_geometry']['rollback_count'] for r in reports]),sort_keys=True))
