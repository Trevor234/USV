"""Bounded, synthetic localhost fixture. No execute/stage qualification.
Expected parameters come from F5's pinned dump plus preregistered overrides.
All application subscriptions are C++ owned; this Python node only queries graph/services.
"""
from pathlib import Path
import argparse,hashlib,json,os,signal,sys,time,traceback,struct
N=Path(__file__).resolve().parent
sys.path.insert(0,str(N/'runtime'))
from owned_process_supervisor import Supervisor
from owned_release import (actual_process,authenticate_startup,explicit_parameters,create_only_json,live_graph,require)
from owned_auth import authenticate_role,source_fd_matches,verify_owned_graph,authorize_fixture_release,parameter_digest
import rclpy
from rclpy.node import Node
from rcl_interfaces.srv import ListParameters,GetParameters,SetParameters
from rcl_interfaces.msg import Parameter,ParameterValue
from rclpy.parameter import Parameter as RosParameter

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,d):Path(p).open('x').write(json.dumps(d,sort_keys=True,indent=2,allow_nan=False)+'\n')
def flat(d,prefix=''):
 out={}
 for k,v in d.items():
  k=prefix+k
  if isinstance(v,dict):out.update(flat(v,k+'.'))
  else:out[k]=v
 return out

def rosval(v):
 # JSON scalar/array is also YAML; quote every string to avoid YAML implicit typing.
 return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def args_for(params):
 out=['--ros-args']
 for k,v in sorted(params.items()):out+=['-p',k+':='+rosval(v)]
 return out

def defaults(events=True,sim=False):
 d={'use_sim_time':sim,'start_type_description_service':True}
 if events:d.update({'qos_overrides./parameter_events.publisher.depth':1000,'qos_overrides./parameter_events.publisher.durability':'volatile','qos_overrides./parameter_events.publisher.history':'keep_last','qos_overrides./parameter_events.publisher.reliability':'reliable'})
 return d

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run-id',required=True);ap.add_argument('--domain',type=int,required=True);ap.add_argument('--mode',choices=['positive','foreign_same_name','foreign_wrong_type','wrong_config','wrong_hook'],default='positive');a=ap.parse_args()
 require(os.environ.get('ROS_DOMAIN_ID')==str(a.domain),'domain differs');require(os.environ.get('RMW_IMPLEMENTATION')=='rmw_fastrtps_cpp','RMW differs');require(os.environ.get('ROS_LOCALHOST_ONLY')=='1','localhost required')
 require(1<=a.domain<=200 and a.run_id.replace('_','').replace('-','').isalnum(),'invalid fixture identity')
 R=N/'runs'/a.run_id;R.mkdir(parents=True,exist_ok=False)
 for name in ['worker','observer','synthetic_source','recorder']:(R/name).mkdir()
 for source in ['prepare_fixture.py','owned_auth.py','owned_release.py','check_owned_fixture.py']:
  (R/(source+'.snapshot')).open('xb').write((N/source).read_bytes())
 prepare_start=time.monotonic_ns();prepare_budget=25_000_000_000;overall_deadline=prepare_start+60_000_000_000
 sup=Supervisor(R);node=None;released=False;roles={};expected={};owned={};last_graph=None;last_error=[None];result={'schema':'p1-owned-fixture-run-v1','run_id':a.run_id,'mode':a.mode,'fixture_only':True,'D1_dynamic_qualified':False,'execute_qualified':False,'physical_release_qualified':False,'prepare_start_ns':prepare_start,'prepare_budget_ns':prepare_budget,'overall_budget_ns':60_000_000_000,'passed':False}
 pins=load(N/'source_bundles_current.json');build=load(N/'build_manifest_current.json');build={b['role']:b for b in build}
 contract=N.parent/'authored_v13_resource_20261007/p1_shadow_contract_v5.json';ch=sha(contract);require(ch=='0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933','contract pin differs')
 C=load(contract);pubrun=a.run_id+'-publisher';manifest_paths={k:R/k/'owned_manifest.json' for k in ['publisher','worker','observer','synthetic_source','recorder']}
 release=R/'release.json';startfile=R/'synthetic_start.json'
 physical=['/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust']
 topics={'/clock':'rosgraph_msgs/msg/Clock','/wamv/sensors/position/ground_truth_odometry':'nav_msgs/msg/Odometry','/wamv/sensors/imu/imu/data':'sensor_msgs/msg/Imu','/path/reference':'nav_msgs/msg/Path','/path/reference_profile':'std_msgs/msg/Float64MultiArray','/research/control/applied':'usv_research_interfaces/msg/AppliedControl','/research/cycle_timing':'usv_research_interfaces/msg/CycleTiming','/research/reference_prediction':'usv_research_interfaces/msg/ReferencePrediction','/research/state_snapshot':'usv_research_interfaces/msg/StateSnapshot','/mavros/rc/override':'mavros_msgs/msg/OverrideRCIn','/mpc/predicted_trajectory':'nav_msgs/msg/Path','/mpc/status':'std_msgs/msg/String','/p1/solve_job':'usv_research_interfaces/msg/SolveJob','/p1/solve_candidate':'usv_research_interfaces/msg/SolveCandidate','/p1/worker_capability':'usv_research_interfaces/msg/WorkerCapability','/p1/execution_decision':'usv_research_interfaces/msg/ExecutionDecision',**{p:'std_msgs/msg/Float64' for p in physical}}
 topicfile=R/'topics.json';dump(topicfile,{'schema':'p1-owned-recorder-topics/v1','topics':topics});th=sha(topicfile)
 params=flat(load(N.parent/'vrx_shadow_fixed_f5_preflight_20261006_01.json')['f5_actual_parameters']);params.update(research_run_id=pubrun,research_output_dir=str(R/'publisher'),p1_release_file=str(release),p1_owned_contract_sha256=ch)
 expected['publisher']=dict(params)
 inputs={'run_id':a.run_id,'mode':a.mode,'domain':a.domain,'tool_sha256':{s:sha(N/s) for s in ['prepare_fixture.py','owned_auth.py','owned_release.py','check_owned_fixture.py','runtime/owned_process_supervisor.py']},'env':{k:os.environ.get(k) for k in ['RMW_IMPLEMENTATION','ROS_DOMAIN_ID','ROS_LOCALHOST_ONLY','ROS_AUTOMATIC_DISCOVERY_RANGE']},'contract':str(contract),'contract_sha256':ch,'topics_file':str(topicfile),'topics_sha256':th,'builds':build,'source_bundles':pins,'expected_parameters':expected,'measurement_seconds':4,'close_order':['publisher','observer','worker','synthetic_source','recorder'],'sensor_start_is_separate_create_only_gate':True}
 def bound():
  require(time.monotonic_ns()<overall_deadline,'overall deadline expired')
  for k,x in owned.items():
   require(x.process.poll() is None,'owned role exited early: '+k)
  require(sum(p.stat().st_size for p in R.rglob('*') if p.is_file())<=128*1024*1024,'output budget exceeded')
 def wait_for(predicate,label,seconds=5,preparing=True):
  until=min(overall_deadline,time.monotonic_ns()+int(seconds*1e9),prepare_start+prepare_budget if preparing else overall_deadline)
  while time.monotonic_ns()<until:
   bound()
   if predicate():return
   if node:rclpy.spin_once(node,timeout_sec=.01)
   else:time.sleep(.01)
  raise RuntimeError('deadline: '+label)
 def spawn(name,role,argv):
  b=build[role];require(b['passed'] is True,'unbuilt role '+role)
  bundle=load(pins[role]['path']);require(sha(pins[role]['path'])==pins[role]['sha256'],'bundle changed')
  for f in bundle['files'].values():require(sha(f['path'])==f['sha256'],'source differs '+f['path'])
  x=sup.spawn(name,[b['binary'],*argv],dict(os.environ),Path(b['binary']),b['binary_sha256']);owned[name]=x;return x
 def trusted(name):
  x=owned[name];actual=actual_process(x.process.pid)
  for k in ['pid','pgid','sid','start_ticks','exe','exe_sha256']:require(actual[k]==x.identity[k],'spawn identity differs '+name+':'+k)
  require(len(sup.members(x))==1,'unexpected child in owned role')
  return actual
 def authenticate(name):
  role='fixture' if name=='synthetic_source' else name
  return authenticate_role(manifest_paths[name],trusted(name),sup.boot,{'role':name,'run_id':pubrun if name=='publisher' else a.run_id,'contract_sha256':ch,'source_bundle_sha256':pins[role]['sha256'],'rmw_implementation':'rmw_fastrtps_cpp'},expected[name],prepare_start)
 def graph():
  alltopics=set(topics)
  for r in roles.values():alltopics.update(e['topic'] for e in r['manifest']['endpoints'])
  nonlocal last_graph
  last_graph=live_graph(node,physical,alltopics)
  return last_graph
 def rows(p):
  try:
   raw=Path(p).read_bytes();return [json.loads(line) for line in raw.splitlines(keepends=True) if line.endswith(b'\n')]
  except FileNotFoundError:return []
 def query_parameters(name):
  remote=roles[name]['manifest']['node'];deadline=min(time.monotonic_ns()+2_000_000_000,prepare_start+prepare_budget)
  def call(suffix,typ,req):
   client=node.create_client(typ,remote+'/'+suffix)
   try:
    require(client.wait_for_service(timeout_sec=max(0,(deadline-time.monotonic_ns())/1e9)),'parameter service absent '+remote)
    future=client.call_async(req)
    while not future.done() and time.monotonic_ns()<deadline:rclpy.spin_once(node,timeout_sec=.01)
    require(future.done(),'parameter query deadline '+remote);return future.result()
   finally:node.destroy_client(client)
  listed=call('list_parameters',ListParameters,ListParameters.Request(prefixes=[],depth=0)).result.names
  require(set(listed)==set(expected[name]),'external parameter name set differs '+name)
  reply=call('get_parameters',GetParameters,GetParameters.Request(names=listed))
  values={}
  typed={}
  for k,v in zip(listed,reply.values):
   value=RosParameter.from_parameter_msg(Parameter(name=k,value=v)).value
   if v.type>=5:value=list(value)
   values[k]=value
   canonical=struct.pack('>d',value).hex() if v.type==3 else [struct.pack('>d',x).hex() for x in value] if v.type==8 else value
   typed[k]={'type':v.type,'value':value,'canonical_value':canonical}
  dump(R/('live_parameters_'+name+'.json'),typed)
  require(parameter_digest(typed)==roles[name]['manifest']['effective_parameters_sha256'],'external live parameter digest differs '+name)
  require(values==expected[name],'live parameter values differ '+name)
  require([v.type for v in reply.values]==[roles[name]['manifest']['effective_parameters'][k]['type'] for k in listed],'live parameter types differ '+name)
  probe=Parameter(name='use_sim_time',value=ParameterValue(type=1,bool_value=not expected[name]['use_sim_time']))
  attempted=call('set_parameters',SetParameters,SetParameters.Request(parameters=[probe]))
  require(len(attempted.results)==1 and not attempted.results[0].successful,'poststartup parameter mutation accepted '+name)
  return {'complete_name_set':True,'typed_values_equal_expected':True,'mutation_rejected':True,'reason':attempted.results[0].reason}
 try:
  recorder_args={'--run-id':a.run_id,'--contract':str(contract),'--contract-sha256':ch,'--topics':str(topicfile),'--topics-sha256':th,'--manifest':str(manifest_paths['recorder']),'--terminal':str(R/'recorder/terminal.json'),'--bag':str(R/'recorder/bag'),'--storage-id':'sqlite3','--prepare-budget-ms':'15000'}
  expected['recorder']=defaults()
  spawn('recorder','recorder',[z for kv in recorder_args.items() for z in kv])
  actual_pub=dict(params)
  if a.mode=='wrong_config':actual_pub['dynamic.Rd']=[.3,.3]
  spawn('publisher','publisher',args_for(actual_pub));wait_for(lambda:(R/'publisher/startup_manifest.json').exists(),'publisher startup')
  startup=authenticate_startup(R/'publisher/startup_manifest.json',trusted('publisher'),sup.boot,{'run_id':pubrun,'contract_sha256':ch,'source_bundle_sha256':pins['publisher']['sha256']})
  roles['publisher']=authenticate('publisher');require(startup['manifest']['owned_manifest_sha256']==roles['publisher']['sha256'],'startup does not bind owned manifest')
  sp={'run_id':a.run_id,'contract_hash':ch,'output_dir':str(R/'synthetic_source'),'start_file':str(startfile),'topics_file':str(topicfile),'topics_sha256':th};expected['synthetic_source']={**defaults(),**sp}
  spawn('synthetic_source','fixture',args_for(sp));wait_for(lambda:manifest_paths['synthetic_source'].exists(),'synthetic endpoints')
  roles['synthetic_source']=authenticate('synthetic_source');source_fd_matches(roles['synthetic_source'],R/'synthetic_source/transport_source.jsonl')
  wp={'run_id':a.run_id,'contract_hash':ch,'contract_file':str(contract),'source_file':str(R/'worker/source.jsonl'),'owned_manifest_file':str(manifest_paths['worker']),'test_delay_ms':0,'test_native_block_ms':0};expected['worker']={**defaults(),**wp}
  actual_wp=dict(wp)
  if a.mode=='wrong_hook':actual_wp['test_delay_ms']=1
  spawn('worker','worker',args_for(actual_wp));wait_for(lambda:manifest_paths['worker'].exists(),'worker endpoints');roles['worker']=authenticate('worker');source_fd_matches(roles['worker'],R/'worker/source.jsonl')
  sm=startup['manifest'];omsrc=N/'observer/src/shadow/regulator_shadow_observer.cpp'
  op={'run_id':a.run_id,'contract_hash':ch,'contract_file':str(contract),'mode':'shadow','legacy_run_id':pubrun,'worker_pid':owned['worker'].process.pid,'witness_enabled':True,'witness_file':str(R/'observer/witness.json'),'source_file':str(R/'observer/source.jsonl'),'diagnostic_source_file':str(omsrc),'diagnostic_source_sha256':sha(omsrc),'diagnostic_binary_sha256':build['observer']['binary_sha256'],'worker_binary_sha256':build['worker']['binary_sha256'],'witness_worker_instance':roles['worker']['manifest']['worker_instance'],'legacy_schema_version':'p0-contract-v1','legacy_producer_instance_id':sm['producer_instance_id'],'legacy_config_hash':sm['config_hash'],'legacy_clock_domain':sm['steady_clock_domain'],'recording_observer_node':'p1_synthetic_source','legacy_ready_timeout_ms':12000,'owned_manifest_file':str(manifest_paths['observer']),**{k:0 for k in ['test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms','test_sink_pause_ms']}}
  expected['observer']={**defaults(),**op};spawn('observer','observer',args_for(op))
  wait_for(lambda:manifest_paths['observer'].exists() and manifest_paths['recorder'].exists(),'observer and Recorder owned endpoints',8)
  roles['observer']=authenticate('observer');roles['recorder']=authenticate('recorder');source_fd_matches(roles['observer'],R/'observer/source.jsonl')
  require(roles['worker']['manifest']['contract_configuration']==C and roles['observer']['manifest']['contract_configuration']==C,'effective contract configuration differs')
  for name,hooks in [('worker',['test_delay_ms','test_native_block_ms']),('observer',['test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms','test_sink_pause_ms'])]:
   # Explicit argv checks independently enforce zero integer hooks; JSON string values remain quoted.
   argv=roles[name]['actual']['argv'];explicit_parameters(argv,{k:rosval(v) for k,v in (wp if name=='worker' else op).items() if k not in hooks},hooks)
  rclpy.init(args=[]);node=Node('p1_owned_fixture_driver',enable_rosout=False,start_parameter_services=False)
  last_error=[None]
  def complete_graph():
   try:verify_owned_graph(graph(),roles,physical);last_error[0]=None;return True
   except (ValueError,KeyError) as e:last_error[0]=str(e);return False
  wait_for(complete_graph,'exact owned graph '+str(last_error[0]),6)
  if a.mode.startswith('foreign'):
   from std_msgs.msg import Float64,String
   foreign=Node(roles['publisher']['manifest']['node'].split('/')[-1],enable_rosout=False,start_parameter_services=False)
   fp=foreign.create_publisher(Float64 if a.mode=='foreign_same_name' else String,physical[0],10)
   end=time.monotonic()+1
   while time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.02)
   try:verify_owned_graph(graph(),roles,physical)
   except ValueError as e:result.update(expected_negative_rejection=True,rejection=str(e));raise RuntimeError('expected negative: '+str(e))
   finally:foreign.destroy_publisher(fp);foreign.destroy_node()
   raise RuntimeError('foreign endpoint was incorrectly admitted')
  ready_file=Path(str(manifest_paths['observer'])+'.reader_ready.json')
  wait_for(lambda:ready_file.exists(),'native Applied reader match',5)
  native=load(ready_file)
  require(native['owned_manifest_sha256']==roles['observer']['sha256'] and native['pid']==roles['observer']['actual']['pid'] and native['process_start_ticks']==roles['observer']['actual']['start_ticks'] and native['run_id']==a.run_id and native['boot_id']==sup.boot and native['contract_sha256']==ch and native['applied_matched_publishers']==1 and native['applied_endpoint'] in roles['observer']['manifest']['endpoints'],'native reader readiness differs')
  result['native_applied_reader_ready_sha256']=sha(ready_file)
  capability_ready_file=Path(str(manifest_paths['worker'])+'.capability_ready.json')
  wait_for(lambda:capability_ready_file.exists(),'native capability receivers match',5)
  result['live_parameter_queries']={k:query_parameters(k) for k in ['publisher','worker','observer','synthetic_source']}
  require(not (R/'publisher/release_receipt.json').exists() and not release.exists(),'publisher unexpectedly released')
  pre_rows=rows(R/'synthetic_source/transport_source.jsonl');require(not any(r['topic'] in physical or r['topic'] in ['/research/control/applied','/clock'] for r in pre_rows),'held output/sensor gate emitted')
  # Independent malformed GID / PID-start identity negatives on a copy never reach release.
  from copy import deepcopy
  bad=deepcopy(roles);bad['publisher']['manifest']['endpoints'][0]['gid'][0]^=1
  try:verify_owned_graph(graph(),bad,physical);raise RuntimeError('tampered GID admitted')
  except ValueError:result['tampered_gid_rejected']=True
  invalid=trusted('publisher');invalid['start_ticks']+=1
  from owned_release import authenticate_owned
  try:authenticate_owned(invalid,sup.boot);raise RuntimeError('PID start mismatch admitted')
  except ValueError:result['pid_start_mismatch_rejected']=True
  header={'run_id':a.run_id,'boot_id':sup.boot,'contract_sha256':ch,'source_sha256':sha(omsrc),'binary_sha256':build['observer']['binary_sha256'],'worker_binary_sha256':build['worker']['binary_sha256'],'worker_instance':roles['worker']['manifest']['worker_instance']};dump(R/'expected_witness_header.json',header)
  dump(R/'inputs.json',inputs)
  create_only_json(startfile,{'schema':'p1-synthetic-start-v1','run_id':a.run_id,'boot_id':sup.boot})
  warm=time.monotonic()+1.1
  while time.monotonic()<warm:bound();rclpy.spin_once(node,timeout_sec=.01)
  roles={k:authenticate(k) for k in roles}
  for k,p in [('worker',R/'worker/source.jsonl'),('observer',R/'observer/source.jsonl'),('synthetic_source',R/'synthetic_source/transport_source.jsonl')]:source_fd_matches(roles[k],p)
  result['release']=authorize_fixture_release(startup=startup,roles=roles,graph=graph(),physical_topics=physical,evidence_path=R/'preparation_evidence.json',release_path=release,native_reader_ready_path=ready_file,native_capability_ready_path=capability_ready_file,boot=sup.boot,prepare_start_ns=prepare_start,prepare_budget_ns=prepare_budget,driver_node='/p1_owned_fixture_driver');released=True
  wait_for(lambda:(R/'publisher/release_receipt.json').exists(),'publisher release receipt',3)
  wait_for(lambda:any(r['type']=='legacy_ready' for r in rows(R/'observer/source.jsonl')),'actual legacy_ready',8)
  end=time.monotonic()+4
  while time.monotonic()<end:
   bound();rclpy.spin_once(node,timeout_sec=.01)
   require(not any(r['type'] in ['legacy_ready_failed','legacy_ready_invalidated'] for r in rows(R/'observer/source.jsonl')),'legacy_ready invalidated in measurement')
  result['finite_prepare_and_measurement_passed']=True
 except BaseException as e:
  result['error']=str(e);result['traceback']=traceback.format_exc()
 finally:
  result['last_graph_rejection']=last_error[0]
  if last_graph:dump(R/'last_graph.json',last_graph)
  result['released']=released;result['release_file_exists']=release.exists();result['sensor_start_exists']=startfile.exists()
  # Keep sources and storage alive while publisher commits final Applied/session.
  close_start=time.monotonic_ns();cleanup={}
  def stop(name):
   if name in owned:cleanup[name]=sup.stop(owned[name],2,.5,.5)
  stop('publisher')
  if released and (R/'publisher/session_summary.json').exists():
   s=load(R/'publisher/session_summary.json');last=s.get('streams',{}).get('applied',{}).get('last_sequence')
   tail=time.monotonic()+.25
   while time.monotonic()<tail:
    if node and rclpy.ok():rclpy.spin_once(node,timeout_sec=.01)
    else:time.sleep(.01)
   result['final_publisher_applied_sequence']=last
  for name in ['observer','worker','synthetic_source','recorder']:stop(name)
  result['cleanup']=cleanup;result['close_elapsed_ns']=time.monotonic_ns()-close_start;result['cleanup_complete']=not sup.cleanup_failed and all(x['cleanup_complete'] for x in cleanup.values());result['cleanup_within_budget']=result['close_elapsed_ns']<=15_000_000_000
  result['owned_role_returncodes']={k:v.process.returncode for k,v in owned.items()};result['ledger_failed']=sup.evidence_failed;sup.close()
  if node:node.destroy_node()
  if rclpy.ok():rclpy.shutdown()
  if not (R/'inputs.json').exists():dump(R/'inputs.json',inputs)
  result['passed']=bool(result.get('finite_prepare_and_measurement_passed') and result['cleanup_complete'] and result['cleanup_within_budget'] and not result.get('error') and all(x==0 for x in result['owned_role_returncodes'].values()))
  result['elapsed_ns']=time.monotonic_ns()-prepare_start
  result['held_negative_passed']=bool(result.get('expected_negative_rejection') or (a.mode in ('wrong_config','wrong_hook') and not released and result.get('error','').startswith('full effective configuration differs')))
  dump(R/'result.json',result)
  if result['passed']:
   checker={'bag':str(R/'recorder/bag'),'topics_file':str(topicfile),'transport_source':str(R/'synthetic_source/transport_source.jsonl'),'synthetic_terminal':str(R/'synthetic_source/terminal.json'),'publisher_session':str(R/'publisher/session_summary.json'),'startup_manifest':str(R/'publisher/startup_manifest.json'),'observer_source':str(R/'observer/source.jsonl'),'worker_source':str(R/'worker/source.jsonl'),'witness':str(R/'observer/witness.json'),'expected_witness_header':str(R/'expected_witness_header.json'),'owned_manifests':{k:str(v) for k,v in manifest_paths.items()}}
   dump(R/'checker_inputs.json',checker)
 print(json.dumps({'run':str(R),'passed':result['passed'],'held_negative_passed':result['held_negative_passed'],'error':result.get('error'),'cleanup_complete':result['cleanup_complete'],'elapsed_s':result['elapsed_ns']/1e9},indent=2))
 return 0 if result['passed'] or result['held_negative_passed'] else 2
if __name__=='__main__':raise SystemExit(main())
