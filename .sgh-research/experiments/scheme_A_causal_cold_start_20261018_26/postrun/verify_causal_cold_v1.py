"""Independent verification; validation/oracles are read after candidate generation."""
from pathlib import Path
import ast,copy,json,re
from independent_model_v1 import np,math,sha,load,require,matrix,forward,objective
D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_causal_cold_start_20261018_v26'
def write(p,v):
 with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def check_answer(r,fixed,inp):
 c=inp['contract'];j=inp['actual_job'];tol=inp['independent_abs_tolerance'];x=matrix(r['X'],(6,21));u=matrix(r['U'],(2,20));aug=matrix(r['augmented_X'],(8,21));state=matrix(j['target_state'],(6,));a=matrix(j['anchor_n'],(2,));ref=matrix(j['reference'],(6,21))
 require(r['native_status']==0 and r['actual_OCP_input_changed'] is fixed and r['additional_first_control_equality'] is fixed,'status or changed feasible set misrepresented')
 require(r['KKT_convergence_proven'] is False and r['solver_NLP_cost_readback'] is False,'unearned solver claim')
 require(list(u[:,0])==r['first_control'] and np.max(np.abs(aug[:6]-x))<=tol,'prediction/control shape binding')
 eq=float(np.max(np.abs(u[:,0]-.5))) if fixed else 0.;require(abs(r['first_control_equality_error_n']-eq)<=1e-15,'first equality diagnostic mismatch')
 require(not fixed or eq<=inp['fixed_first_equality_abs_tolerance_n'],'fixed first equality failed')
 rate=float(np.max(np.abs(u-np.column_stack([a,u[:,:-1]]))));bound=max(0.,float(np.max(c['command_min_n']-u)),float(np.max(u-c['command_max_n'])))
 require(bound<=1e-10 and rate<=c['backend_rate_n_s']*c['dt']+1e-10,'original input/rate constraint failed')
 y=np.zeros((6,21));y[:,0]=state
 for k in range(20):y[:,k+1]=forward(y[:,k],u[:,k],c)
 err=float(np.max(np.abs(y-matrix(r['feasible_rollout_X'],(6,21)))));require(err<=tol,'independent nonlinear rollout failed')
 maxcost=0.
 for key,states in [('objective_self_computed',x),('feasible_rollout_objective_self_computed',y)]:
  cost=objective(states,u,ref,a,c)
  for name,value in cost.items():
   delta=abs(value-r[key][name]);maxcost=max(maxcost,delta);require(delta<=tol,'independent objective failed')
 defect=max(float(np.max(np.abs(forward(x[:,k],u[:,k],c)-x[:,k+1]))) for k in range(20));initial=float(np.max(np.abs(x[:,0]-state)));memory=float(np.max(np.abs(aug[6:]-np.column_stack([a,u]))))
 for key,value in [('nonlinear_RK4_state_defect_max_abs',defect),('initial_state_max_abs_error',initial),('largest_control_increment_n',rate),('input_bound_violation_n',bound)]:require(abs(r[key]-value)<=tol,'diagnostic mismatch '+key)
 for key in ['kernel_solve_ms','wall_ms']:require(math.isfinite(r[key]) and r[key]>=0,'finite timing')
 return dict(rollout_max_abs_error=err,cost_max_abs_error=maxcost,defect=defect,initial_residual=initial,previous_control_memory_residual=memory,equality_error_n=eq,rate_n=rate)

def check_seed(seed,cold,runtime,v):
 expected=np.array(cold['U']).reshape((2,20),order='F').copy();expected[:,0]=.5;u=matrix(seed['U'],(2,20));require(np.array_equal(u,expected) and seed['source']=='current_job_preliminary_free_U_only','causal tail source mismatch')
 x=matrix(seed['X_aug'],(8,21));job=runtime['actual_job'];a=matrix(job['anchor_n'],(2,));y=np.zeros((6,21));y[:,0]=matrix(job['target_state'],(6,))
 for k in range(20):y[:,k+1]=forward(y[:,k],u[:,k],runtime['contract'])
 error=float(np.max(np.abs(x[:6]-y)));require(error<=v['independent_abs_tolerance'] and np.array_equal(x[6:],np.column_stack([a,u])),'causal feasible state or memory seed mismatch');return error

def check_warm(candidate):
 final=candidate['candidate_final'];aug=matrix(final['augmented_X'],(8,21));u=matrix(final['U'],(2,20));w=candidate['warm_after_last_shift']
 require(w['warm'] is True and np.array_equal(matrix(w['X_aug'],(8,21)),np.column_stack([aug[:,1:],aug[:,-1]])) and np.array_equal(matrix(w['U'],(2,20)),np.column_stack([u[:,1:],u[:,-1]])),'one final warm shift mismatch')
 require(candidate['warm_after_withdrawal']==w,'mode withdrawal changed final warm cache')

def check_opens(opened,runtime_path,result_path,validation_path,source_pins):
 forbidden={str(Path(validation_path)),*source_pins.keys()};require(not any(p in forbidden for p in opened),'candidate attempted validation/benchmark file open')
 allowed={str(runtime_path),str(result_path),str(result_path)+'.journal.jsonl'}
 data=[p for p in opened if p.endswith(('.json','.jsonl','.yaml','.yml'))];require(set(data)<=allowed,'unregistered data file opened');require(str(runtime_path) in opened,'runtime input missing from file-open trace');return data

def main():
 paths=[N/'runtime_job_v1.json',N/'causal_validation_v1.json',D/'preregister/causal_cold_v1.json',D/'replay/native_causal_cold_v1.json',D/'replay/offline_invocation_v1.json',D/'preregister/offline_invocation_lock_v1.json',Path(__file__).resolve(),D/'postrun/independent_model_v1.py'];before={str(p):sha(p) for p in paths};runtime,v,pre,result,inv,lock=[load(p) for p in paths[:6]]
 require(inv['passed'] and inv['input_closure_unchanged'],'traced invocation failed');require(result['runtime_input_sha256']==pre['runtime_input_sha256']==v['runtime_input_sha256']==lock['runtime_input_sha256']==sha(paths[0]) and result['input_unchanged'],'runtime binding');require(sha(paths[1])==pre['validation_input_sha256']==lock['validation_input_sha256'],'separate validation binding');require(result['binary_sha256']==lock['binary']['sha256'] and result['source_bundle_sha256']==lock['source_bundle_sha256'],'source/binary binding')
 require(set(runtime)=={'schema','contract','contract_sha256','actual_job','policy','scope','runtime_code_changed','ROS_nodes_started'},'runtime input schema excludes oracles')
 for p,h in v['source_pins'].items():require(sha(p)==h,'sealed oracle input changed')
 legacy=load(v['actual_baseline_input_path']);require(runtime['actual_job']==legacy['ordered_native_jobs'][0]['job'] and runtime['contract']==legacy['contract'],'actual current Job/model/cost/reference binding')
 c=result['candidate'];require(c['actual_job']==runtime['actual_job'] and result['candidate_RTI_calls']==c['candidate_RTI_calls']==4 and result['separate_restoration_probe_RTI_calls']==1 and c['oracle_data_accepted_by_candidate'] is False and result['validation_input_argument_supported'] is False,'exact causal invocation scope')
 ctx={**v,'contract':runtime['contract'],'actual_job':runtime['actual_job']};cold=c['preliminary_free'];checks=[check_answer(cold,False,ctx)]
 for key,tol in [('first_control',v['baseline_max_control_abs_error_n']),('X',v['baseline_max_X_U_abs_error']),('U',v['baseline_max_X_U_abs_error'])]:require(np.max(np.abs(np.array(cold[key])-np.array(v['cold_expected'][key])))<=tol,'preliminary cold solve baseline')
 seederror=check_seed(c['causal_seed'],cold,runtime,v);require([r['iteration'] for r in c['restricted_iterations']]==[1,2,3],'exact three restricted calls')
 for row in c['restricted_iterations']:
  require(row['answer']['warm_shift_after_this_call'] is (row['iteration']==3),'warm must shift only after third restricted call');checks.append(check_answer(row['answer'],True,ctx))
 require(cold['warm_shift_after_this_call'] is False and c['candidate_final']==c['restricted_iterations'][-1]['answer'],'candidate final copy before separate probe');final=c['candidate_final'];require(final['nonlinear_RK4_state_defect_max_abs']<=v['final_dynamic_defect_abs_tolerance'],'final dynamic defect')
 benchmark=v['fixed_refined_benchmark'];xe=float(np.max(np.abs(np.array(final['X'])-np.array(benchmark['X']))));ue=float(np.max(np.abs(np.array(final['U'])-np.array(benchmark['U']))));ce=abs(final['feasible_rollout_objective_self_computed']['total']-benchmark['feasible_rollout_objective_self_computed']['total'])
 require(xe<=v['benchmark_final_X_U_abs_error'] and ue<=v['benchmark_final_X_U_abs_error'] and ce<=v['benchmark_final_cost_abs_error'],'bounded candidate fails preregistered refined benchmark gate')
 check_warm(c);off=c['restored_first_bounds'];require(off['read_from_actual_C_API'] and off['additional_first_equality'] is False and off['lbu']==[-25.,-25.] and off['ubu']==[25.,25.] and c['mode_withdrawn_before_return'],'actual first bounds not restored')
 on=c['enabled_first_bounds'];require(on['lbu']==[.5,.5] and on['ubu']==[.5,.5] and on['additional_first_equality'] and on['read_from_actual_C_API'],'added equality not recorded')
 probe=result['separate_restoration_probe'];require(probe['RTI_calls']==1 and probe['fed_back_into_candidate'] is False and probe['first_bounds_before']==off and probe['first_bounds_after']==off,'one separate free restoration probe');checks.append(check_answer(probe['answer'],False,ctx));distance=float(np.min(np.abs(np.array(probe['answer']['first_control'])-.5)));require(distance>v['restoration_probe_distance_from_050_min_n'],'free probe still locked to 0.5')
 journal=Path(result['journal_path']);require(sha(journal)==result['journal_sha256'],'durable journal digest');jr=[json.loads(l) for l in journal.read_text().splitlines()];phases=['identity','preliminary_free','fixed_mode_enabled','causal_seed','restricted_iteration','restricted_iteration','restricted_iteration','candidate_complete','restoration_probe'];require([r['phase'] for r in jr]==phases,'complete ordered journal')
 require(jr[1]['answer']==cold and jr[2]['bounds']==on and jr[3]['seed']==c['causal_seed'] and jr[7]['candidate']==c and jr[8]['probe']==probe,'journal full result identity')
 for i,row in enumerate(c['restricted_iterations']):require(jr[4+i]['iteration']==row['iteration'] and jr[4+i]['answer']==row['answer'],'restricted journal identity')
 trace=Path(inv['file_open_trace_path']);require(sha(trace)==inv['file_open_trace_sha256'],'actual open trace digest');opened=[ast.literal_eval(m.group(1)) for m in re.finditer(r'\b(?:open|openat|openat2)\([^\n"]*("(?:\\.|[^"\\])*")',trace.read_text())];dataopens=check_opens(opened,paths[0],paths[3],paths[1],v['source_pins'])
 require(opened and '+++ killed' not in trace.read_text(),'complete native trace')
 coldcost=cold['feasible_rollout_objective_self_computed']['total'];cost=final['feasible_rollout_objective_self_computed']['total'];dv=final['feasible_rollout_X'][9]-cold['feasible_rollout_X'][9];require(dv>v['surge_gain_tolerance_m_s'] and cost-coldcost<=v['cost_nonworsening_abs_tolerance'],'candidate response/cost gate versus current cold baseline')
 negative=[]
 for name,mutate in [('wrong_cost',lambda r:r['feasible_rollout_objective_self_computed'].__setitem__('total',cost+.01)),('hidden_constraint',lambda r:r.__setitem__('actual_OCP_input_changed',False)),('false_equality_diagnostic',lambda r:r.__setitem__('first_control_equality_error_n',.01))]:
  bad=copy.deepcopy(final);mutate(bad)
  try:check_answer(bad,True,ctx)
  except ValueError as e:negative.append(dict(name=name,rejected=True,reason=str(e)))
  else:raise ValueError('accepted corrupt answer '+name)
 bad=copy.deepcopy(c);bad['warm_after_withdrawal']['U'][0]+=.01
 try:check_warm(bad)
 except ValueError as e:negative.append(dict(name='mutated_restored_warm_cache',rejected=True,reason=str(e)))
 else:raise ValueError('accepted corrupt warm state')
 try:check_opens(opened+[str(paths[1])],paths[0],paths[3],paths[1],v['source_pins'])
 except ValueError as e:negative.append(dict(name='oracle_file_open_injected',rejected=True,reason=str(e)))
 else:raise ValueError('accepted forbidden oracle open')
 for p,h in v['source_pins'].items():require(sha(p)==h,'oracle changed during audit')
 after={str(p):sha(p) for p in paths};require(before==after,'audit input changed');require(all(result[k] is False for k in ['ROS_nodes_started','runtime_controller_changed','stage_qualified','execute_qualified','research_conclusion']),'scope/qualification')
 out=dict(schema='scheme-A-causal-cold-independent-audit/v1',passed=True,candidate_component_gates_passed=True,candidate_RTI_calls=4,separate_restoration_probe_calls=1,all_five_recorded_calls_independently_checked=True,cold_baseline_first_control_n=cold['first_control'],candidate_first_control_n=final['first_control'],cold_baseline_feasible_cost=coldcost,candidate_feasible_cost=cost,candidate_cost_reduction_fraction=(coldcost-cost)/coldcost,cold_surge_at_dt_m_s=cold['feasible_rollout_X'][9],candidate_surge_at_dt_m_s=final['feasible_rollout_X'][9],surge_gain_m_s=dv,surge_relative_gain=dv/cold['feasible_rollout_X'][9],candidate_cost_premium_over_refined_free_fraction=(cost-v['free_refined_benchmark']['feasible_rollout_objective_self_computed']['total'])/v['free_refined_benchmark']['feasible_rollout_objective_self_computed']['total'],refined_benchmark_errors=dict(X=xe,U=ue,feasible_cost=ce),final_dynamic_defect=final['nonlinear_RK4_state_defect_max_abs'],maximum_initial_residual=max(r['initial_residual'] for r in checks),maximum_previous_control_memory_residual=max(r['previous_control_memory_residual'] for r in checks),independent_rollout_max_abs_error=max(r['rollout_max_abs_error'] for r in checks),independent_cost_max_abs_error=max(r['cost_max_abs_error'] for r in checks),independent_seed_max_abs_error=seederror,exact_one_final_warm_shift_verified=True,withdrawal_preserves_warm_exactly=True,actual_original_first_bounds_restored=True,free_probe_first_control_n=probe['answer']['first_control'],free_probe_distance_from_050_n=distance,native_file_open_trace=dict(path=str(trace),sha256=sha(trace),total_open_attempts=len(opened),runtime_input_open_count=opened.count(str(paths[0])),data_open_paths=sorted(set(dataopens)),validation_or_benchmark_open_attempts=0),durable_journal_records=9,negative_audit_boundaries=negative,input_sha256_before=before,input_sha256_after=after,MPC_delivery_complete=False,new_closed_loop_performance_qualified=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 write(D/'postrun/causal_cold_audit_v1.json',out);print(json.dumps({k:v for k,v in out.items() if k not in ['input_sha256_before','input_sha256_after','negative_audit_boundaries']},allow_nan=False))
if __name__=='__main__':main()
