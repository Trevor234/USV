"""Audit all ten exact registered probes against independent nonlinear dynamics."""
from pathlib import Path
import copy,json
from independent_model_v1 import np,math,sha,load,require,matrix,forward,objective
D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_startup_first_control_20261018_v24'
def write(p,v):
 with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def validate_case(c,entry,inp):
 for key in ['case_id','tail_id','first_control_id','baseline_case_id']:require(c[key]==entry[key],'case identity or cross-tail baseline changed')
 require(c['tail_nodes_1_to_19_exactly_unchanged'] is True,'fixed-tail declaration')
 r=c['rollout'];u=matrix(r['U'],(2,20));job=inp['actual_job'];state=matrix(job['target_state'],(6,));anchor=matrix(job['anchor_n'],(2,));ref=matrix(job['reference'],(6,21));contract=inp['contract'];tol=inp['independent_abs_tolerance']
 require(list(u[:,0])==entry['first_control']==inp['first_controls'][entry['first_control_id']],'exact registered first control')
 original=inp['tail_sequences'][entry['tail_id']]['U'];require(r['U'][2:]==original[2:],'tail must remain bit-exact')
 require(r['first_control_n']==entry['first_control'],'recorded first control mismatch')
 increments=u-np.column_stack([anchor,u[:,:-1]]);largest=float(np.max(np.abs(increments)))
 require(float(u.min())>=contract['command_min_n'] and float(u.max())<=contract['command_max_n'] and largest<=contract['backend_rate_n_s']*contract['dt'],'unmodified input/rate constraints')
 x=np.zeros((6,21));x[:,0]=state
 for k in range(20):x[:,k+1]=forward(x[:,k],u[:,k],contract)
 err=float(np.max(np.abs(x-matrix(r['X'],(6,21)))));require(err<=tol,'independent full nonlinear rollout mismatch')
 expected=objective(x,u,ref,anchor,contract);costerr=max(abs(r['objective'][key]-v) for key,v in expected.items());require(costerr<=tol,'independent original cost mismatch')
 require(abs(r['first_interval_surge_m_s']-x[3,1])<=tol and np.max(np.abs(matrix(r['first_interval_position_m'],(2,))-x[:2,1]))<=tol,'first interval metrics')
 require(abs(r['largest_control_increment_n']-largest)<=tol and r['input_bound_violation_n']==0 and r['control_increment_limit_n']==contract['backend_rate_n_s']*contract['dt'],'constraint diagnostics')
 require(r['nonlinear_RK4_substeps']==4 and all(r[k] is False for k in ['optimizer_invoked','tail_reoptimized','solver_NLP_cost_readback']),'offline scope')
 return dict(X_max_abs_error=err,cost_max_abs_error=costerr)
def main():
 paths=[N/'actual_first_control_input_v1.json',D/'preregister/first_control_v1.json',D/'replay/native_first_control_v1.json',D/'replay/offline_invocation_v1.json',D/'preregister/offline_invocation_lock_v1.json',Path(__file__).resolve(),D/'postrun/independent_model_v1.py'];before={str(p):sha(p) for p in paths};inp,pre,result,inv,lock=[load(p) for p in paths[:5]]
 require(inv['passed'] and inv['input_closure_unchanged'],'invocation passed')
 require(result['input_sha256']==pre['input_sha256']==lock['input_sha256']==sha(paths[0]) and result['input_unchanged'],'fixed actual input binding')
 require(result['source_bundle_sha256']==lock['source_bundle_sha256'] and result['binary_sha256']==lock['binary']['sha256'],'source and executable binding')
 require(pre['ordered_cases']==inp['ordered_cases'] and len(result['cases'])==pre['cases']==10 and result['all_10_cases_complete'] and result['optimizer_calls']==0,'finite registered scope')
 require(all(result[k] is False for k in ['stage_qualified','execute_qualified','research_conclusion','ROS_nodes_started','runtime_code_changed','new_closed_loop_performance_qualified']),'qualification unchanged')
 for p,h in inp['source_pins'].items():require(sha(p)==h,'sealed parent input changed')
 parent=load(next(p for p in inp['source_pins'] if p.endswith('/replay/native_startup_v1.json')))
 require(inp['actual_job']==parent['cases'][0]['fixed_Job'],'actual Job1 binding')
 for tail,iteration in [('once',0),('refined',11)]:
  expected=parent['cases'][0]['iterations'][iteration]['raw_unshifted'];stored=inp['tail_sequences'][tail]
  require(stored['U']==expected['U'] and stored['expected_rollout_X']==expected['feasible_rollout_X'] and stored['expected_objective']==expected['feasible_rollout_objective_self_computed'],'exact sealed tail and baseline')
 entries=inp['ordered_cases'];audits=[validate_case(c,e,inp) for c,e in zip(result['cases'],entries)]
 cases_by_id={c['case_id']:c for c in result['cases']};require(len(cases_by_id)==10,'unique exact cases')
 for tail in ['once','refined']:
  base=result['baselines'][tail];expected=inp['tail_sequences'][tail];require(base['max_X_abs_error']<=pre['baseline_abs_tolerance'] and base['max_cost_part_abs_error']<=pre['baseline_abs_tolerance'],'native baseline gate')
  b=cases_by_id[tail+'__'+expected['baseline_choice']]['rollout'];require(b==base['rollout'],'baseline case is identical to independently checked baseline')
  require(np.max(np.abs(np.array(b['X'])-np.array(expected['expected_rollout_X'])))<=pre['baseline_abs_tolerance'],'sealed complete baseline X')
  for key,value in expected['expected_objective'].items():
   if key!='solver_NLP_cost_readback':require(abs(b['objective'][key]-value)<=pre['baseline_abs_tolerance'],'sealed baseline cost decomposition')
 summaries=[]
 for c in result['cases']:
  r=c['rollout'];base=cases_by_id[c['baseline_case_id']]['rollout'];speed=r['first_interval_surge_m_s']-base['first_interval_surge_m_s'];cost=r['objective']['total']-base['objective']['total'];relative=cost/base['objective']['total']
  gain=speed>pre['first_interval_speed_gain_tolerance_m_s'];nonworse=cost<=pre['cost_nonworsening_abs_tolerance']
  summaries.append(dict(case_id=c['case_id'],tail_id=c['tail_id'],first_control_id=c['first_control_id'],first_control_n=r['first_control_n'],baseline_case_id=c['baseline_case_id'],first_interval_surge_m_s=r['first_interval_surge_m_s'],first_interval_position_m=r['first_interval_position_m'],first_interval_surge_gain_m_s=speed,cost_total=r['objective']['total'],cost_delta_from_own_baseline=cost,cost_relative_delta_from_own_baseline=relative,cost_component_deltas={k:r['objective'][k]-v for k,v in base['objective'].items() if k!='solver_NLP_cost_readback'},first_interval_speed_improved=gain,original_objective_nonworsening=nonworse,material_cost_worsening=relative>pre['cost_material_worsening_relative_fraction'],faster_and_original_objective_nonworsening=gain and nonworse,maximum_control_increment_n=r['largest_control_increment_n']))
 # These mutations test the audit boundary, not additional controller probes.
 base=result['cases'][0];entry=entries[0];negative=[]
 for name,mutate in [('changed_tail',lambda c:c['rollout']['U'].__setitem__(4,c['rollout']['U'][4]+.01)),('wrong_cost',lambda c:c['rollout']['objective'].__setitem__('total',c['rollout']['objective']['total']+.01)),('wrong_rollout',lambda c:c['rollout']['X'].__setitem__(9,c['rollout']['X'][9]+.001)),('cross_tail_baseline',lambda c:c.__setitem__('baseline_case_id','refined__first_refined')),('nonfinite_control',lambda c:c['rollout']['U'].__setitem__(0,float('nan')))]:
  bad=copy.deepcopy(base);mutate(bad)
  try:validate_case(bad,entry,inp)
  except ValueError as e:negative.append(dict(name=name,rejected=True,reason=str(e)))
  else:raise ValueError('audit accepted corruption '+name)
 for p,h in inp['source_pins'].items():require(sha(p)==h,'parent changed during audit')
 after={str(p):sha(p) for p in paths};require(before==after,'read-only audit inputs')
 out=dict(schema='scheme-A-first-control-independent-audit/v1',passed=True,cases=summaries,native_baselines={k:{n:v for n,v in b.items() if n!='rollout'} for k,b in result['baselines'].items()},all_ten_exact_registered_cases_checked=True,independent_rollout_max_abs_error=max(r['X_max_abs_error'] for r in audits),independent_cost_max_abs_error=max(r['cost_max_abs_error'] for r in audits),negative_audit_boundaries=negative,source_pins=inp['source_pins'],input_sha256_before=before,input_sha256_after=after,material_pulses=[r['case_id'] for r in summaries if r['first_control_id'] in ['n050','n100','n200']],all_material_pulses_faster_and_cost_worse=all(r['first_interval_speed_improved'] and r['material_cost_worsening'] for r in summaries if r['first_control_id'] in ['n050','n100','n200']),all_faster_nonworsening_cases=[r['case_id'] for r in summaries if r['faster_and_original_objective_nonworsening']],MPC_delivery_complete=False,new_closed_loop_performance_qualified=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 write(D/'postrun/first_control_audit_v1.json',out);print(json.dumps({k:v for k,v in out.items() if k not in ['input_sha256_before','input_sha256_after','source_pins','negative_audit_boundaries']},allow_nan=False))
if __name__=='__main__':main()
