"""Read-only, predefined startup and task-position diagnostics; never a gate replacement."""
from pathlib import Path
import argparse,hashlib,json,math,sqlite3
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict
D=Path(__file__).resolve().parents[1]
E=D.parent/'p1_execution_architecture_20261005_01'
CASES=[('G',E/'authored_D1_reference_bias_20261016_v20/runs/projected_s005_01',D.parent/'scheme_A_reference_bias_20261016_20/runs/s005_01/check_result.json'),('T',E/'authored_D1_reference_time_anchor_20261018_v21r2/runs/task_time_r02_s005_01',D/'runs/s005_02/check_result.json')]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(s) for s in Path(p).read_text().splitlines()]
def need(b,why):
 if not b:raise ValueError(why)
def metrics(values):
 need(bool(values),'empty diagnostic population')
 return dict(samples=len(values),mean=math.fsum(values)/len(values),RMSE=math.sqrt(math.fsum(x*x for x in values)/len(values)),minimum=min(values),maximum=max(values),last=values[-1])
def analyze(name,run,report_path):
 report=load(report_path);before=report['input_sha256_before'];need(before==report['input_sha256_after'],'read-only parent report maps')
 for p,digest in before.items():need(sha(p)==digest,'actual raw input changed: '+p)
 actual=load(run/'result.json');need(actual['passed'] and actual['cleanup_complete'] and all(c==0 for c in actual['owned_role_returncodes'].values()),'actual driver and normal closure required')
 model=[r for r in rows(run/'synthetic_source/nominal_steps.jsonl') if r.get('schema')=='p1-controlled-nominal-model-step-v1']
 observer=rows(run/'observer/source.jsonl');jobs=[r for r in observer if r.get('type')=='job'];need(bool(jobs),'actual jobs required')
 start=report['window']['start_ready_ns'];end=report['window']['end_driver_requested_ns'];odoms=[];applied=[];dbpins={};classes={}
 for db in sorted((run/'recorder/bag').glob('*.db3')):
  dbpins[str(db)]=sha(db);conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.execute('PRAGMA query_only=ON');need(conn.execute('PRAGMA quick_check').fetchall()==[('ok',)],'SQLite quick check')
  topics={i:(n,t) for i,n,t in conn.execute('SELECT id,name,type FROM topics')}
  for tid,blob in conn.execute('SELECT topic_id,data FROM messages ORDER BY id'):
   topic,typ=topics[tid]
   if topic not in ['/wamv/sensors/position/ground_truth_odometry','/research/control/applied']:continue
   if typ not in classes:classes[typ]=get_message(typ)
   value=dict(message_to_ordereddict(deserialize_message(blob,classes[typ])))
   (odoms if topic.endswith('ground_truth_odometry') else applied).append(value)
  conn.close()
 need(len(odoms)==len(model),'entire actual StoredOdom/Source population')
 for i,(m,o) in enumerate(zip(model,odoms)):
  stamp=o['header']['stamp'];need(m['sensor_sequence']==i+1 and m['sim_stamp_ns']==stamp['sec']*10**9+stamp['nanosec'] and m['state'][0]==o['pose']['pose']['position']['x'] and m['state'][1]==o['pose']['pose']['position']['y'] and m['state'][3]==o['twist']['twist']['linear']['x'],'every stored state position/surge/stamp matches model Source')
 samples=[r for r in model if start<=r['target_ns']<end];need(bool(samples),'pre-request measurement window')
 speed=.05;errors=[r['state'][3]-speed for r in samples];sse=math.fsum(x*x for x in errors);rmse=math.sqrt(sse/len(errors));last=[r['state'][3] for r in samples if r['target_ns']>=end-5*10**9];mean=math.fsum(last)/len(last)
 need(rmse==report['performance']['measured_surge_RMSE_m_s'] and mean==report['performance']['last5s_mean_surge_m_s'],'exact frozen gate reproduction')
 cuts=[('0_to_1s',start,start+10**9),('1_to_2s',start+10**9,start+2*10**9),('2_to_5s',start+2*10**9,start+5*10**9),('5_to_10s',start+5*10**9,start+10*10**9),('10s_to_last5',start+10*10**9,end-5*10**9),('last5',end-5*10**9,end)]
 segments=[]
 for label,a,b in cuts:
  values=[r['state'][3]-speed for r in samples if a<=r['target_ns']<b];part=metrics(values);part.update(label=label,sample_SSE_fraction=math.fsum(x*x for x in values)/sse);segments.append(part)
 need(abs(math.fsum(r['sample_SSE_fraction'] for r in segments)-1)<1e-12,'disjoint diagnostics conserve whole SSE')
 first=jobs[0];epoch=first['job']['target_sim_ns'];t0=first['profile_t0'];position=[r for r in samples if r['sim_stamp_ns']>=epoch];gap=[speed*(t0+(r['sim_stamp_ns']-epoch)/1e9)-r['state'][0] for r in position];position_last=[e for r,e in zip(position,gap) if r['target_ns']>=end-5*10**9]
 accepted_ids={r['sequence'] for r in observer if r.get('type')=='decision' and r.get('accepted') is True and start<=r['activation_commit_ns']<end};commands=[m for m in applied if m['cycle_sequence'] in accepted_ids and m['control_source']=='controlled_C_decision'];need(bool(commands),'accepted actual command publications')
 inside=[abs(e)<=speed*.05 for e in errors];last_bad=max((i for i,b in enumerate(inside) if not b),default=-1);settled=last_bad+1 if last_bad+1<len(samples) else None
 result=dict(case=name,report_path=str(report_path),report_sha256=sha(report_path),overall_case_passed=report['passed'],original_issues=report['issues'],measurement_seconds=(end-start)/1e9,gate_metrics=report['performance'],segments=segments,whole_SSE=sse,SSE_fraction_first2s=sum(r['sample_SSE_fraction'] for r in segments[:2]),SSE_fraction_first5s=sum(r['sample_SSE_fraction'] for r in segments[:3]),maximum_surge_m_s=max(r['state'][3] for r in samples),settled_5percent_until_close_s=(samples[settled]['target_ns']-start)/1e9 if settled is not None else None,first_actual_accepted_command_after_Ready_s=(commands[0]['right_publish_end_steady_ns']-start)/1e9,first_actual_accepted_command_n=commands[0]['final_n'],command_is_force_measurement=False,position_error=dict(epoch_semantics='diagnostic first-target task-time line for G; declared actual first-submit epoch for T',first_job_id=first['job']['job_id'],first_target_sim_ns=epoch,initial_profile_t0=t0,excluded_pre_epoch_samples=len(samples)-len(position),signed_target_minus_actual_x_m=metrics(gap),last5s_signed_target_minus_actual_x_m=metrics(position_last)),accepted=report['window']['accepted'],attempts=report['window']['attempts'],actual_jobs=len(jobs),all_stored_sensor_rows_checked=len(model),role_returncodes=actual['owned_role_returncodes'],locked_raw_paths=len(before),raw_SHA_map_digest=hashlib.sha256(json.dumps(before,sort_keys=True,separators=(',',':')).encode()).hexdigest(),actual_SQLite=dbpins)
 for p,digest in before.items():need(sha(p)==digest,'audit mutated raw input: '+p)
 return result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();results=[analyze(*case) for case in CASES]
 g,t=results;result=dict(schema='scheme-A-G-T-task-time-comparison/v1',client_date='2026-10-18',audit_passed=True,cases=results,RMSE_T_over_G=t['gate_metrics']['measured_surge_RMSE_m_s']/g['gate_metrics']['measured_surge_RMSE_m_s'],last_position_gap_T_over_G=t['position_error']['signed_target_minus_actual_x_m']['last']/g['position_error']['signed_target_minus_actual_x_m']['last'],diagnostic_windows='Ready inclusive to actual driver close request exclusive; exact same six startup/terminal segments as parent audit; position only post first target; no shutdown tail',paired_or_same_latency_trial=False,scope='one frozen G run and one fresh T run; identical .05m/s static nominal diagnostic model, separate startup/runtime phases; finite observation only',performance_gate_replaced=False,ROS_nodes_started=False,stage_qualified=False,execute_qualified=False,research_conclusion=False,recipe_sha256=sha(__file__))
 with a.output.open('x') as f:json.dump(result,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({k:result[k] for k in ['audit_passed','RMSE_T_over_G','last_position_gap_T_over_G']}))
if __name__=='__main__':main()
