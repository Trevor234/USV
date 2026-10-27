from pathlib import Path
import json,hashlib,sqlite3,math,bisect,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parents[1];E=D.parent/'p1_execution_architecture_20261005_01'
CASES=[('parent',E/'authored_D1_longitudinal_20261016_v19/runs/longitudinal_s005_01',D.parent/'scheme_A_longitudinal_20261016_19/runs/s005_01/check_result.json'),('projected',E/'authored_D1_reference_bias_20261016_v20/runs/projected_s005_01',D/'runs/s005_01/check_result.json')]
issues=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(s) for s in Path(p).read_text().splitlines()]
def bind(p):p=Path(p);return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def need(b,code,**context):
 if not b:issues.append(dict(code=code,**context))
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from rosidl_runtime_py.utilities import get_message
classes={}
def decode(data,typ):
 if typ not in classes:classes[typ]=get_message(typ)
 return dict(message_to_ordereddict(deserialize_message(data,classes[typ])))
def integrals(times,values,left,right,speed):
 # Piecewise-linear between pre-close observations; hold the last pre-close
 # value to the request boundary. Never read a post-request speed for metrics.
 def at(t):
  k=bisect.bisect_right(times,t)-1
  if k<0:return values[0]
  if k>=len(times)-1:return values[-1]
  f=(t-times[k])/(times[k+1]-times[k]);return values[k]+f*(values[k+1]-values[k])
 knots=[left]+[t for t in times if left<t<right]+[right];iae=ise=signed=0.
 for a,b in zip(knots,knots[1:]):
  e0=at(a)-speed;e1=at(b)-speed;dt=(b-a)/1e9
  signed+=dt*(e0+e1)/2;ise+=dt*(e0*e0+e0*e1+e1*e1)/3
  iae+=dt*(abs(e0)+abs(e1))/2 if e0*e1>=0 else dt*(e0*e0+e1*e1)/(2*(abs(e0)+abs(e1)))
 duration=(right-left)/1e9
 return dict(duration_s=duration,IAE_m=iae,ISE_m2_per_s=ise,time_weighted_MSE_m2_per_s2=ise/duration,time_weighted_RMSE_m_s=math.sqrt(ise/duration),signed_integrated_velocity_error_m=signed)
def settling(samples,start,end,speed,fraction):
 band=speed*fraction;inside=[abs(u-speed)<=band for t,u in samples];first=next((k for k,b in enumerate(inside) if b),None);lastoutside=max((k for k,b in enumerate(inside) if not b),default=-1);stable=lastoutside+1 if lastoutside+1<len(samples) else None
 return dict(relative_band=fraction,absolute_band_m_s=band,first_sampled_entry_s=(samples[first][0]-start)/1e9 if first is not None else None,entry_and_remain_until_close_request_s=(samples[stable][0]-start)/1e9 if stable is not None else None,remained_inside_through_end=stable is not None,observation_end_s=(end-start)/1e9,definition='sampled entry and all later pre-request samples within band; no infinite-time or inter-sample guarantee')
results=[]
for name,run,rpath in CASES:
 first=len(issues);report=load(rpath);inputs=load(run/'inputs.json');result=load(run/'result.json');before=report['input_sha256_before'];need(before==report['input_sha256_after'],'parent_checker_input_maps_equal',case=name)
 for p,digest in before.items():need(sha(p)==digest,'all_locked_input_SHA_current',case=name,path=p)
 expected_issue=[] if name=='parent' else [{'code':'projected_preregistered_whole_measurement_RMSE_halved_parent','limit':.007392495755251466,'observed':.008758759754530695}]
 need(report['issues']==expected_issue and report['passed'] is (name=='parent'),'exact_original_component_gate_outcome_retained',case=name)
 need(result['passed'] is True and result['cleanup_complete'] is True and all(rc==0 for rc in result['owned_role_returncodes'].values()),'driver_and_cleanup_succeeded_distinct_from_performance',case=name)
 source=run/'synthetic_source/nominal_steps.jsonl';model=[r for r in rows(source) if r.get('schema')=='p1-controlled-nominal-model-step-v1'];obs=rows(run/'observer/source.jsonl');native_close=[r for r in obs if r['type']=='adapter_driver_close_observed'][0]
 start=report['window']['start_ready_ns'];end=report['window']['end_driver_requested_ns'];speed=.05
 dbs=sorted((run/'recorder/bag').glob('*.db3'));odoms=[];applied=[];dbbindings=[]
 for db in dbs:
  conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.execute('PRAGMA query_only=ON');need(conn.execute('PRAGMA quick_check').fetchall()==[('ok',)],'SQLite_quick_check',case=name)
  topics={i:(n,t) for i,n,t in conn.execute('SELECT id,name,type FROM topics')}
  for tid,blob in conn.execute('SELECT topic_id,data FROM messages ORDER BY id'):
   topic,typ=topics[tid]
   if topic=='/wamv/sensors/position/ground_truth_odometry':odoms.append(decode(blob,typ))
   if topic=='/research/control/applied':applied.append(decode(blob,typ))
  conn.close();dbbindings.append(bind(db))
 need(len(odoms)==len(model),'whole_actual_StoredOdom_Source_population',case=name)
 allsamples=[]
 for k,(row,odom) in enumerate(zip(model,odoms)):
  stamp=odom['header']['stamp'];u=float(odom['twist']['twist']['linear']['x']);need(row['sensor_sequence']==k+1 and row['sim_stamp_ns']==stamp['sec']*10**9+stamp['nanosec'] and u==row['state'][3],'every_actual_stored_surge_and_Source_time_binding',case=name,sensor_sequence=k+1)
  allsamples.append((row['target_ns'],u))
 need(all(b[0]>a[0] for a,b in zip(allsamples,allsamples[1:])),'all_sensor_times_strict',case=name)
 samples=[(t,u) for t,u in allsamples if start<=t<end];last=[u for t,u in samples if end-5_000_000_000<=t];sse=math.fsum((u-speed)**2 for t,u in samples);rmse=math.sqrt(sse/len(samples));mean=math.fsum(last)/len(last)
 metric=report.get('performance')
 if metric:need(rmse==metric['measured_surge_RMSE_m_s'] and mean==metric['last5s_mean_surge_m_s'],'exact_preregistered_metric_reproduction',case=name)
 integral_samples=[(t,u) for t,u in allsamples if t<end];times=[t for t,u in integral_samples];values=[u for t,u in integral_samples]
 whole=integrals(times,values,start,end,speed);cuts=[('0_to_1s',start,start+1_000_000_000),('1_to_2s',start+1_000_000_000,start+2_000_000_000),('2_to_5s',start+2_000_000_000,start+5_000_000_000),('5_to_10s',start+5_000_000_000,start+10_000_000_000),('10s_to_last5_start',start+10_000_000_000,end-5_000_000_000),('last5s',end-5_000_000_000,end)];parts=[]
 for label,a,b in cuts:
  selected=[u for t,u in samples if a<=t<b];part_sse=math.fsum((u-speed)**2 for u in selected);integral=integrals(times,values,a,b,speed)
  commands=[m for m in applied if a<=m['right_publish_end_steady_ns']<b];forces=[float(v) for m in commands for v in m['final_n']]
  parts.append(dict(segment=label,start_after_Ready_s=(a-start)/1e9,end_after_Ready_s=(b-start)/1e9,samples=len(selected),mean_surge_m_s=math.fsum(selected)/len(selected),mean_signed_error_m_s=math.fsum(u-speed for u in selected)/len(selected),sample_RMSE_m_s=math.sqrt(part_sse/len(selected)),sample_SSE_m2_per_s2=part_sse,sample_full_window_MSE_contribution_m2_per_s2=part_sse/len(samples),sample_SSE_fraction_of_whole=part_sse/sse,integral_ISAE_fraction_of_whole=integral['ISE_m2_per_s']/whole['ISE_m2_per_s'],actual_publisher_command_pairs=len(commands),mean_command_n_per_channel=math.fsum(forces)/len(forces) if forces else None,maximum_command_n=max(forces) if forces else None,**integral))
 need(abs(sum(p['sample_SSE_fraction_of_whole'] for p in parts)-1)<1e-12 and abs(sum(p['ISE_m2_per_s'] for p in parts)-whole['ISE_m2_per_s'])<1e-15,'disjoint_segments_conserve_full_error',case=name)
 # Command chronology is Publisher API observation, not measured actuator force.
 accepted_ids={d['sequence'] for d in obs if d.get('type')=='decision' and d.get('accepted') is True and start<=d['activation_commit_ns']<end};accepted_commands=[m for m in applied if m['cycle_sequence'] in accepted_ids and m['control_source']=='controlled_C_decision'];initial_commands=[m for m in accepted_commands if m['right_publish_end_steady_ns']<start+2_000_000_000]
 jobs=[r['job'] for r in obs if r.get('type')=='job' and start<=r['job']['freeze_ns']<end];leads=[j['reference'][0]-j['target_state'][0] for j in jobs]
 result_case=dict(case=name,audit_checks_passed=len(issues)==first,speed_reference_m_s=speed,measurement_window_s=(end-start)/1e9,measurement_sensor_count=len(samples),stored_total_model_sensor_count=len(model),sample_gate_metrics=dict(whole_RMSE_m_s=rmse,last5s_mean_surge_m_s=mean,last5s_relative_mean_error=abs(mean-speed)/speed),integral_method='piecewise-linear interpolation among pre-close samples; final pre-close value held to exact request boundary; no post-request sample used',whole_integrals=whole,segments=parts,first20s_supplement_not_used_as_gate=integrals(times,values,start,start+20_000_000_000,speed),settling={str(f):settling(samples,start,end,speed,f) for f in [.05,.1]},initial_state_observation=dict(first_sample_after_Ready_s=(samples[0][0]-start)/1e9,first_surge_m_s=samples[0][1]),first_accepted_actual_command=dict(after_Ready_s=(accepted_commands[0]['right_publish_end_steady_ns']-start)/1e9,thrust_n=list(accepted_commands[0]['final_n']),control_source=accepted_commands[0]['control_source'],command_is_force_measurement=False),first2s_accepted_commands=[dict(after_Ready_s=(m['right_publish_end_steady_ns']-start)/1e9,thrust_n=list(m['final_n'])) for m in initial_commands],actual_Job_reference_x_lead_m=dict(count=len(leads),mean=math.fsum(leads)/len(leads),minimum=min(leads),maximum=max(leads)),accepted=report['window']['accepted'],candidate_attempts=report['window']['attempts'],all_five_role_returncodes=result['owned_role_returncodes'],parent_full_checker_report=bind(rpath),locked_raw_file_count=len(before),raw_input_SHA_manifest_digest=hashlib.sha256(json.dumps(before,sort_keys=True,separators=(',',':')).encode()).hexdigest(),source_and_manifest_bindings={str(p.relative_to(run)):bind(p) for p in [source,run/'observer/source.jsonl',run/'worker/source.jsonl',run/'publisher/controlled_source.jsonl',run/'inputs.json',run/'result.json',run/'synthetic_source/owned_manifest.json',run/'observer/owned_manifest.json',run/'recorder/bag/metadata.yaml']},actual_SQLite=dbbindings)
 results.append(result_case)
 for p,digest in before.items():need(sha(p)==digest,'raw_file_SHA_unchanged_after_read_only_audit',case=name,path=p)
old,new=results;ratio=new['sample_gate_metrics']['whole_RMSE_m_s']/old['sample_gate_metrics']['whole_RMSE_m_s'];new_0_2=sum(p['sample_SSE_fraction_of_whole'] for p in new['segments'][:2]);new_0_5=sum(p['sample_SSE_fraction_of_whole'] for p in new['segments'][:3])
node_runs=sorted(p.name for p in (E/'authored_D1_reference_bias_20261016_v20/runs').iterdir() if p.is_dir());need(node_runs==['projected_s005_01'],'projected_ladder_stopped_after_first_performance_NoGo',actual_runs=node_runs)
out=dict(schema='p1-startup-versus-steady-audit-v1',audit_client_date='2026-10-17',audit_passed=not issues,issues=issues,reference_speed_m_s=.05,comparison_scope='one closed projected run versus one closed D19 parent run; actual StoredOdom is an authenticated nominal-model sensor stream, not a real Plant measurement',cases=results,comparison=dict(RMSE_new_over_parent=ratio,RMSE_improvement_fraction=1-ratio,required_improvement_fraction=.5,required_RMSE_limit_m_s=.007392495755251466,observed_projected_RMSE_m_s=new['sample_gate_metrics']['whole_RMSE_m_s'],observed_projected_RMSE_passed=False,last5s_mean_relative_error_passed=True,new_error_sample_SSE_fraction_first2s=new_0_2,new_error_sample_SSE_fraction_first5s=new_0_5,projected_only_issue='projected_preregistered_whole_measurement_RMSE_halved_parent'),decision=dict(projected_overall_preregistered_performance_passed=False,mean_bias_component_observation_passed=True,next_reference_speeds_m_s=[.1,.3,.6],next_reference_speeds_status='NoGo; not executed',threshold_or_CPP_change_performed=False),interpretation=['The observed last-five-second mean bias is much smaller with projected reference, but the full preregistered RMSE improvement requirement failed.','Temporal decomposition distinguishes startup tracking error from the terminal observation window. It does not replace the predefined whole-window gate.','Changes in initial command and approach timing are observations for this pair of nominal diagnostic runs, not a physical acceleration limit or proof that cost weights must change.','No claim of true Plant performance, formal stage qualification, universal superiority or statistical significance is made.'],ROS_nodes_started=False,stage_qualified=False,execute_qualified=False,research_conclusion=False,review_recipe=bind(__file__))
old_startup_ISE=sum(p['ISE_m2_per_s'] for p in old['segments'][:2]);new_startup_ISE=sum(p['ISE_m2_per_s'] for p in new['segments'][:2])
out['comparison'].update(parent_first2s_ISE_m2_per_s=old_startup_ISE,projected_first2s_ISE_m2_per_s=new_startup_ISE,first2s_ISE_projected_over_parent=new_startup_ISE/old_startup_ISE,whole_sample_MSE_projected_over_parent=ratio*ratio,required_whole_sample_MSE_fraction=.25,startup_error_worsened_claim_supported=False,startup_timing_confound='The projected first accepted command is smaller but occurs earlier relative to Ready in this pair. This is an observed timing difference, not a matched-phase acceleration experiment.')
path=D/'postrun/startup_vs_steady_audit_v1.json'
with path.open('x') as f:json.dump(out,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def fmt(v,n=6):return '未在测量末端前持续留带' if v is None else f'{v:.{n}f}'
text=['# 投影参考首档：启动误差与末窗偏差审计','', '日期：2026-10-17。**末5秒均值门通过，整窗RMSE门未通过；后续0.1/0.3/0.6 m/s保持NoGo。** 未修改门槛、闭环代码或守卫。','', '审计直接读取新旧两次已闭合运行的实际SQLite Odometry，并逐条匹配模型Source的传感器序号、速度与时间戳；同时重新核验完整锁定输入SHA。这里的传感器来自标称模型，不能解释为真实Plant测量。','', '| 指标 | 父批离散前视 | 本批连续投影 |','|---|---:|---:|', f"| 测量窗/s | {old['measurement_window_s']:.6f} | {new['measurement_window_s']:.6f} |", f"| 整窗样本RMSE/(m/s) | {old['sample_gate_metrics']['whole_RMSE_m_s']:.12f} | {new['sample_gate_metrics']['whole_RMSE_m_s']:.12f} |", f"| 末5秒均值/(m/s) | {old['sample_gate_metrics']['last5s_mean_surge_m_s']:.12f} | {new['sample_gate_metrics']['last5s_mean_surge_m_s']:.12f} |", f"| 末5秒相对均值误差 | {100*old['sample_gate_metrics']['last5s_relative_mean_error']:.6f}% | {100*new['sample_gate_metrics']['last5s_relative_mean_error']:.6f}% |", f"| 样本持续留在±5%带内时间/s | {fmt(old['settling']['0.05']['entry_and_remain_until_close_request_s'])} | {fmt(new['settling']['0.05']['entry_and_remain_until_close_request_s'])} |", f"| 样本持续留在±10%带内时间/s | {fmt(old['settling']['0.1']['entry_and_remain_until_close_request_s'])} | {fmt(new['settling']['0.1']['entry_and_remain_until_close_request_s'])} |",'', f"整窗RMSE降低了{100*(1-ratio):.3f}%，预注册要求至少降低50%。门槛为0.007392495755251466 m/s，实测为{new['sample_gate_metrics']['whole_RMSE_m_s']:.12f} m/s，故总体性能判定仍为失败。",'', '## 按Ready相对时间分解','', '| 运行 | 区间 | 均速/(m/s) | 区间RMSE/(m/s) | 全窗样本SSE占比 | IAE/m | ISE/(m²/s) |','|---|---|---:|---:|---:|---:|---:|']
for case in results:
 for p in case['segments']:text.append(f"| {case['case']} | {p['segment']} | {p['mean_surge_m_s']:.9f} | {p['sample_RMSE_m_s']:.9f} | {100*p['sample_SSE_fraction_of_whole']:.4f}% | {p['IAE_m']:.9f} | {p['ISE_m2_per_s']:.12f} |")
text+=['', f"本批前2秒贡献全窗样本SSE的{100*new_0_2:.4f}%，前5秒贡献{100*new_0_5:.4f}%。这些分段与末5秒数据用于解释首个失败门，不替代整窗判定。",'', '## 本次可以解释到哪里','', f"父批首个已接受命令在Ready后{old['first_accepted_actual_command']['after_Ready_s']:.6f} s发布，双桨命令为{old['first_accepted_actual_command']['thrust_n']} N；投影策略对应时间为{new['first_accepted_actual_command']['after_Ready_s']:.6f} s，命令为{new['first_accepted_actual_command']['thrust_n']} N。这些是Publisher API命令观察，不是测得推力。",'', f"实际Job参考x原点平均超前量由{old['actual_Job_reference_x_lead_m']['mean']:.9f} m变为{new['actual_Job_reference_x_lead_m']['mean']:.12g} m。结合先前仅平移参考x的实际Acados重放，本次数据符合：离散前视带来的额外追赶需求消除后，末窗不再持续偏快；与此同时，本次启动过程的误差仍主导投影运行的整窗RMSE。",'', '这只是两次标称直线诊断的观测取舍。它没有证明物理加速极限，也不推出必须调权重。两次实际测量窗长度不同，JSON另存共同前20秒的补充积分，明确不将其替换预注册窗口。', '', 'IAE/ISE使用测量前及测量内样本线性插值，末个关闭请求前样本保持到请求边界；未使用关闭后速度代表稳态。持续留带时间只表示采样点直到本次窗口结束，不能外推无限时间。','', '新运行的101/101候选接纳、来源/存储/见证和正常回收，与总体预注册性能未通过是不同结论。后三档不推进。','', '[完整指标、分段与原始证据SHA](startup_vs_steady_audit_v1.json)']
qualification=f"0–2秒绝对ISE由{old_startup_ISE:.12f}降为{new_startup_ISE:.12f} m²/s（下降{100*(1-new_startup_ISE/old_startup_ISE):.3f}%）；两个启动分段RMSE也均略低。因此，本次数据不支持‘去carrot导致启动误差变坏’。首控更小但输出相位更早，是这对运行的联合观察，不能独归因为采样策略。更准确的失败解释是：去除持续偏快后，残余启动误差仍使全窗MSE为父批的{100*ratio*ratio:.3f}%，而RMSE减半要求MSE不超过父批25%。"
index=next(i for i,line in enumerate(text) if line.startswith('这只是两次标称直线诊断'))
text[index:index]=[qualification,'']
md=D/'postrun/startup_vs_steady_audit_v1.md';md.open('x').write('\n'.join(text)+'\n')
print(json.dumps(dict(audit_passed=not issues,issues=issues,json_path=str(path),json_sha256=sha(path),md_path=str(md),md_sha256=sha(md),RMSE_ratio=ratio,startup_SSE_fraction_0_2=new_0_2,startup_SSE_fraction_0_5=new_0_5,projected_settling_5percent_s=new['settling']['0.05']['entry_and_remain_until_close_request_s'],projected_settling_10percent_s=new['settling']['0.1']['entry_and_remain_until_close_request_s']),sort_keys=True))
