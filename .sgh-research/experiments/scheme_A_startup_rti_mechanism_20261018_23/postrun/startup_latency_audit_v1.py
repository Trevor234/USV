from pathlib import Path
import json,hashlib,math,sqlite3
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict
D=Path(__file__).resolve().parents[1];P=D.parent/'scheme_A_reference_pair_wakeup_20261018_22';R=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_pair_wakeup_20261018_v22/runs/pair_wakeup_s005_01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def main():
 report_path=P/'runs/s005_01/check_result.json';report=json.loads(report_path.read_text());pins=report['input_sha256_after'];assert pins==report['input_sha256_before']
 for p,h in pins.items():assert sha(p)==h,p
 observer=rows(R/'observer/source.jsonl');worker=rows(R/'worker/source.jsonl');publisher=rows(R/'publisher/controlled_source.jsonl');model=[r for r in rows(R/'synthetic_source/nominal_steps.jsonl') if r.get('schema')=='p1-controlled-nominal-model-step-v1'];start=report['window']['start_ready_ns'];end=report['window']['end_driver_requested_ns']
 decisions=[r for r in observer if r.get('type')=='decision' and r['accepted'] and start<=r['activation_commit_ns']<end];first=decisions[0];jid=first['job_id'];job=next(r for r in observer if r.get('type')=='job' and r['job']['job_id']==jid);native=next(r for r in worker if r.get('type')=='candidate' and r['job']['job_id']==jid);publish=next(r for r in publisher if r.get('type')=='controlled_Applied_emitted' and r['cycle_sequence']==first['sequence'] and r['control_source']=='controlled_C_decision')
 odom=[];applied=[];dbpins={};classes={}
 for db in sorted((R/'recorder/bag').glob('*.db3')):
  dbpins[str(db)]=sha(db);conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.execute('PRAGMA query_only=ON');assert conn.execute('PRAGMA quick_check').fetchall()==[('ok',)];topics={i:(n,t) for i,n,t in conn.execute('SELECT id,name,type FROM topics')}
  for tid,raw in conn.execute('SELECT topic_id,data FROM messages ORDER BY id'):
   name,typ=topics[tid]
   if name not in ['/wamv/sensors/position/ground_truth_odometry','/research/control/applied']:continue
   if typ not in classes:classes[typ]=get_message(typ)
   value=dict(message_to_ordereddict(deserialize_message(raw,classes[typ])));(odom if name.endswith('ground_truth_odometry') else applied).append(value)
  conn.close()
 assert len(odom)==len(model)
 for k,(m,o) in enumerate(zip(model,odom)):
  stamp=o['header']['stamp'];assert m['sensor_sequence']==k+1 and m['sim_stamp_ns']==stamp['sec']*10**9+stamp['nanosec'] and m['state'][3]==o['twist']['twist']['linear']['x'] and m['state'][0]==o['pose']['pose']['position']['x']
 stored=next(m for m in applied if m['sequence']==publish['applied_sequence']);assert stored['cycle_sequence']==first['sequence'] and stored['final_n']==publish['final_n']==native['first_control'];assert stored['left_publish_start_steady_ns']==publish['left_start_ns'] and stored['right_publish_end_steady_ns']==publish['right_end_ns']
 events=[('Ready',start),('freeze',job['job']['freeze_ns']),('submit_commit',job['submit_commit_ns']),('worker_received',native['receive_ns']),('solve_start',native['solve_start_ns']),('solve_end',native['solve_end_ns']),('observer_ready_commit',first['ready_commit_ns']),('planned_target',first['planned_ns']),('activation_commit',first['activation_commit_ns']),('first_left_call_start',publish['left_start_ns']),('both_calls_returned',publish['right_end_ns'])];assert all(b[1]>=a[1] for a,b in zip(events,events[1:]));segments=[dict(start_name=a[0],end_name=b[0],duration_ns=b[1]-a[1],duration_ms=(b[1]-a[1])/1e6) for a,b in zip(events,events[1:])];assert sum(x['duration_ns'] for x in segments)==events[-1][1]-start
 samples=[m for m in model if start<=m['target_ns']<end];sse=math.fsum((m['state'][3]-.05)**2 for m in samples);assert math.sqrt(sse/len(samples))==report['performance']['measured_surge_RMSE_m_s'];budget=len(samples)*report['performance']['RMSE_limit_m_s']**2
 first_control=publish['left_start_ns'];cuts=[('before_first_candidate_call',start,first_control),('first_call_to_1s',first_control,start+10**9),('1_to_2s',start+10**9,start+2*10**9),('2_to_5s',start+2*10**9,start+5*10**9),('after5s',start+5*10**9,end)];parts=[]
 for name,a,b in cuts:
  selected=[m for m in samples if a<=m['target_ns']<b];part=math.fsum((m['state'][3]-.05)**2 for m in selected);parts.append(dict(name=name,samples=len(selected),SSE=part,SSE_fraction_of_actual=part/sse,SSE_fraction_of_allowed_total=part/budget,RMSE_m_s=math.sqrt(part/len(selected)) if selected else None,maximum_abs_surge_m_s=max((abs(m['state'][3]) for m in selected),default=None)))
 assert sum(p['samples'] for p in parts)==len(samples) and abs(math.fsum(p['SSE'] for p in parts)-sse)<1e-15
 preceding=[m for m in applied if start<=m['right_publish_end_steady_ns']<first_control];assert all(m['final_n']==[0.,0.] for m in preceding) and parts[0]['maximum_abs_surge_m_s']==0.
 for p,h in pins.items():assert sha(p)==h,p
 out={'schema':'scheme-A-startup-latency-and-error-partition/v1','client_date':'2026-10-18','audit_passed':True,'job_id':jid,'event_timeline':[dict(name=n,monotonic_ns=t,after_Ready_ms=(t-start)/1e6) for n,t in events],'latency_segments':segments,'first_actual_pair_n':stored['final_n'],'actual_worker_kernel_solve_ms':native['backend_ms'],'native_call_elapsed_ms':(native['solve_end_ns']-native['solve_start_ns'])/1e6,'ready_commit_to_planned_target_ms':(first['planned_ns']-first['ready_commit_ns'])/1e6,'first_left_call_after_Ready_ms':(first_control-start)/1e6,'sample_error_partitions':parts,'whole_sample_SSE':sse,'allowed_total_sample_SSE':budget,'preregistered_RMSE_m_s':report['performance']['measured_surge_RMSE_m_s'],'RMSE_limit_m_s':report['performance']['RMSE_limit_m_s'],'exact_original_gate_reproduced':True,'preceding_stored_Applied_pairs_zero':True,'before_first_candidate_nominal_surge_zero':True,'input_locked_paths':len(pins),'actual_SQLite':dbpins,'original_check_sha256':sha(report_path),'latency_or_kernel_time_is_WCET_proof':False,'physical_actuator_latency_claimed':False,'frozen_RMSE_failure_changed':False,'ROS_nodes_started':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False,'recipe_sha256':sha(__file__)}
 p=D/'postrun/startup_latency_audit_v1.json';p.open('x').write(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps({'audit_passed':True,'native_call_elapsed_ms':out['native_call_elapsed_ms'],'ready_commit_to_target_ms':out['ready_commit_to_planned_target_ms'],'first_left_call_after_Ready_ms':out['first_left_call_after_Ready_ms'],'precontrol_samples':parts[0]['samples'],'precontrol_SSE_fraction_allowed':parts[0]['SSE_fraction_of_allowed_total']}))
if __name__=='__main__':main()
