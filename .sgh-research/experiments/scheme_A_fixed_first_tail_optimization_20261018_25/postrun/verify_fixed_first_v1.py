"""Independent audit of two feasible-seeded, unshifted RTI arms; no ROS."""
from pathlib import Path
import copy,json
from independent_model_v1 import np,math,sha,load,require,matrix,forward,objective
D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_fixed_first_tail_optimization_20261018_v25'
def write(p,v):
 with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def check_answer(r,fixed,inp):
 c=inp['contract'];j=inp['actual_job'];tol=inp['independent_abs_tolerance'];x=matrix(r['X'],(6,21));u=matrix(r['U'],(2,20));aug=matrix(r['augmented_X'],(8,21));state=matrix(j['target_state'],(6,));a=matrix(j['anchor_n'],(2,));ref=matrix(j['reference'],(6,21))
 require(r['native_status']==0 and r['actual_OCP_input_changed'] is fixed and r['additional_first_control_equality'] is fixed and r['tail_reoptimized'] is True,'status or changed feasible set misrepresented')
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
def check_seed(seed,fixed,inp):
 u=matrix(seed['U'],(2,20));expected=np.array(inp['refined_U']).reshape((2,20),order='F')
 if fixed:expected[:,0]=.5
 require(np.array_equal(u,expected),'seed differs from sole preregistered refined tail')
 x=matrix(seed['X_aug'],(8,21));job=inp['actual_job'];c=inp['contract'];a=matrix(job['anchor_n'],(2,));y=np.zeros((6,21));y[:,0]=matrix(job['target_state'],(6,))
 for k in range(20):y[:,k+1]=forward(y[:,k],u[:,k],c)
 error=float(np.max(np.abs(x[:6]-y)));require(error<=inp['independent_abs_tolerance'] and np.array_equal(x[6:],np.column_stack([a,u])),'feasible seed state or previous-control memory')
 return error
def main():
 paths=[N/'actual_fixed_first_input_v1.json',D/'preregister/fixed_first_v1.json',D/'replay/native_fixed_first_v1.json',D/'replay/offline_invocation_v1.json',D/'preregister/offline_invocation_lock_v1.json',Path(__file__).resolve(),D/'postrun/independent_model_v1.py'];before={str(p):sha(p) for p in paths};inp,pre,result,inv,lock=[load(p) for p in paths[:5]]
 require(inv['passed'] and inv['input_closure_unchanged'],'invocation closure')
 require(result['input_sha256']==pre['input_sha256']==lock['input_sha256']==sha(paths[0]) and result['input_unchanged'],'fixed input identity')
 require(result['binary_sha256']==lock['binary']['sha256'] and result['source_bundle_sha256']==lock['source_bundle_sha256'],'source/binary identity')
 for p,h in inp['source_pins'].items():require(sha(p)==h,'sealed parent changed')
 parent=load(next(p for p in inp['source_pins'] if p.endswith('/replay/native_startup_v1.json')));require(inp['actual_job']==parent['cases'][0]['fixed_Job'] and inp['refined_answer']==parent['cases'][0]['iterations'][11]['raw_unshifted'] and inp['refined_U']==inp['refined_answer']['U'],'actual Job and sole refined seed binding')
 require(result['legacy_baseline']['jobs']==102,'all actual legacy Jobs')
 for kind in ['public_vs_actual','raw_shift_vs_actual','public_vs_raw_shift']:
  r=result['legacy_baseline'][kind];require(r['control']<=1e-10 and r['X']<=1e-9 and r['U']<=1e-9,'legacy baseline failed')
 baseline=result['seeded_free_baseline'];require(baseline['X_max_abs_error']<=pre['baseline_max_U_X_abs_error'] and baseline['U_max_abs_error']<=pre['baseline_max_U_X_abs_error'] and baseline['feasible_cost_abs_error']<=pre['baseline_max_feasible_cost_abs_error'],'seeded free component gate')
 require([a['arm_id'] for a in result['arms']]==pre['ordered_arms']==['free_first','fixed_first_050'] and result['all_24_iterations_complete'] and result['mechanism_RTI_calls']==24,'exact finite mechanism scope')
 journal=Path(result['journal_path']);require(sha(journal)==result['journal_sha256'],'durable journal binding');records=[json.loads(l) for l in journal.read_text().splitlines()];require(len(records)==28 and records[0]['type']=='identity' and records[1]['type']=='baselines_passed','complete journal phases')
 jr=[r for r in records if r['type']=='iteration'];require(len(jr)==24,'complete durable iteration records')
 checks=[];seederrors=[];summaries=[];offset=0
 for arm in result['arms']:
  fixed=arm['arm_id']=='fixed_first_050';require(arm['additional_first_equality'] is fixed and arm['fixed_Job']==inp['actual_job'] and arm['warm_cache_shifted'] is False and arm['original_model_cost_reference_unchanged'] is True,'fixed Job/model/reference and unshifted seed')
  require([r['iteration'] for r in arm['iterations']]==list(range(1,13)),'exact twelve iterations')
  seederrors.append(check_seed(arm['seed'],fixed,inp))
  for row in arm['iterations']:
   require(jr[offset]['arm_id']==arm['arm_id'] and jr[offset]['record']==row,'journal/result equality');offset+=1;checks.append(check_answer(row['answer'],fixed,inp))
  final=arm['iterations'][-1]['answer'];prior=arm['iterations'][-2]['answer'];require(final['nonlinear_RK4_state_defect_max_abs']<=pre['final_dynamic_defect_abs_tolerance'],'final nonlinear defect gate')
  du=float(np.max(np.abs(np.array(final['U'])-np.array(prior['U']))));dc=abs(final['feasible_rollout_objective_self_computed']['total']-prior['feasible_rollout_objective_self_computed']['total'])
  summaries.append(dict(arm_id=arm['arm_id'],additional_first_equality=fixed,first_control_n=final['first_control'],cost_final=final['feasible_rollout_objective_self_computed']['total'],cost_components_final=final['feasible_rollout_objective_self_computed'],surge_at_dt_m_s=final['feasible_rollout_X'][9],position_at_dt_m=final['feasible_rollout_X'][6:8],final_dynamic_defect=final['nonlinear_RK4_state_defect_max_abs'],final_initial_residual=final['initial_state_max_abs_error'],last_iteration_all_U_max_delta_n=du,last_iteration_feasible_cost_delta=dc,last_iteration_stable=du<=pre['last_iteration_stability_control_abs_n'] and dc<=pre['last_iteration_stability_cost_abs'],maximum_first_equality_error_n=max(r['answer']['first_control_equality_error_n'] for r in arm['iterations'])))
 a,b=summaries;premium=(b['cost_final']-a['cost_final'])/a['cost_final'];parent24=load(next(p for p in inp['source_pins'] if p.endswith('/replay/native_first_control_v1.json')));oldfixed=next(c['rollout'] for c in parent24['cases'] if c['case_id']=='refined__n050');oldcost=oldfixed['objective']['total'];oldpremium=oldcost-a['cost_final'];newpremium=b['cost_final']-a['cost_final']
 comparison=dict(free_cost=a['cost_final'],fixed_first_reoptimized_cost=b['cost_final'],cost_premium=newpremium,cost_premium_relative_fraction=premium,material_cost_premium=premium>pre['material_cost_premium_relative_fraction'],fixed_tail_parent24_cost=oldcost,premium_reduction_fraction_from_tail_reoptimization=(oldpremium-newpremium)/oldpremium,surge_at_dt_gain_m_s=b['surge_at_dt_m_s']-a['surge_at_dt_m_s'],surge_at_dt_relative_gain=(b['surge_at_dt_m_s']-a['surge_at_dt_m_s'])/a['surge_at_dt_m_s'],cost_component_deltas={k:b['cost_components_final'][k]-v for k,v in a['cost_components_final'].items() if k!='solver_NLP_cost_readback'})
 negative=[];base=result['arms'][1]['iterations'][0]['answer']
 for name,mutate in [('wrong_cost',lambda r:r['feasible_rollout_objective_self_computed'].__setitem__('total',r['feasible_rollout_objective_self_computed']['total']+.01)),('wrong_rollout',lambda r:r['feasible_rollout_X'].__setitem__(9,r['feasible_rollout_X'][9]+.01)),('hidden_changed_feasible_set',lambda r:r.__setitem__('actual_OCP_input_changed',False)),('false_equality_diagnostic',lambda r:r.__setitem__('first_control_equality_error_n',.001)),('unearned_KKT_claim',lambda r:r.__setitem__('KKT_convergence_proven',True))]:
  bad=copy.deepcopy(base);mutate(bad)
  try:check_answer(bad,True,inp)
  except ValueError as e:negative.append(dict(name=name,rejected=True,reason=str(e)))
  else:raise ValueError('auditor accepted corruption '+name)
 for p,h in inp['source_pins'].items():require(sha(p)==h,'sealed parent changed during audit')
 after={str(p):sha(p) for p in paths};require(before==after,'audit input mutation');require(all(result[k] is False for k in ['ROS_nodes_started','runtime_code_changed','original_objective_changed','stage_qualified','execute_qualified','research_conclusion']),'scope/qualification')
 out=dict(schema='scheme-A-fixed-first-tail-independent-audit/v1',passed=True,all_24_iterations_checked=True,legacy_baseline=result['legacy_baseline'],seeded_free_baseline_errors={k:v for k,v in baseline.items() if k not in ['seed','answer']},arms=summaries,comparison=comparison,independent_rollout_max_abs_error=max(c['rollout_max_abs_error'] for c in checks),independent_cost_max_abs_error=max(c['cost_max_abs_error'] for c in checks),independent_seed_max_abs_error=max(seederrors),maximum_previous_control_memory_residual=max(c['previous_control_memory_residual'] for c in checks),maximum_initial_residual=max(c['initial_residual'] for c in checks),maximum_control_increment_n=max(c['rate_n'] for c in checks),negative_audit_boundaries=negative,journal_records=28,journal_sha256=sha(journal),input_sha256_before=before,input_sha256_after=after,MPC_delivery_complete=False,new_closed_loop_performance_qualified=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 write(D/'postrun/fixed_first_audit_v1.json',out);print(json.dumps({k:v for k,v in out.items() if k not in ['input_sha256_before','input_sha256_after','negative_audit_boundaries']},allow_nan=False))
if __name__=='__main__':main()
