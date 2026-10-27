"""Independent numeric audit of fixed-Job offline results, without ROS initialization."""
from pathlib import Path
import copy,hashlib,json,math
import numpy as np

D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_startup_rti_mechanism_20261018_v23'
METHODS=('public_shift','raw_shift','raw_unshifted')
def require(v,m):
 if not v:raise ValueError(m)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def write(p,v):
 with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def matrix(v,shape):
 a=np.asarray(v,dtype=float);require(a.size==math.prod(shape) and np.isfinite(a).all(),'finite matrix and exact shape');return a.reshape(shape,order='F')
def forward(x,control,c):
 h=c['hydro'];step=c['dt']/4
 a=h['mass']-h['Xu_dot'];b=h['mass']-h['Yv_dot'];d=h['mass']*h['xg']-h['Yr_dot'];e=h['mass']*h['xg']-h['Nv_dot'];f=h['Iz']-h['Nr_dot'];det=b*f-d*e
 def ode(s):
  psi,u,v,r=s[2:];tl,tr=control;c13=-b*v-d*r;c23=a*u
  du=-h['Xu']-h['Xuu']*abs(u);dv=-h['Yv']-h['Yvv']*abs(v);dvr=-h['Yr']-h['Yrr']*abs(r);drv=-h['Nv']-h['Nvv']*abs(v);dr=-h['Nr']-h['Nrr']*abs(r)
  ru=tl+tr-c13*r-du*u;rv=-c23*r-dv*v-dvr*r;rr=h['d_thruster']*(tr-tl)+c13*u+c23*v-drv*v-dr*r
  return np.array([math.cos(psi)*u-math.sin(psi)*v,math.sin(psi)*u+math.cos(psi)*v,r,ru/a,(f*rv-d*rr)/det,(-e*rv+b*rr)/det])
 y=x.copy()
 for _ in range(4):
  k1=ode(y);k2=ode(y+.5*step*k1);k3=ode(y+.5*step*k2);k4=ode(y+step*k3);y=y+step/6*(k1+2*k2+2*k3+k4)
 y[2]=math.atan2(math.sin(y[2]),math.cos(y[2]));return y
def objective(x,u,reference,anchor,c):
 q=np.array(c['Q']);r=np.array(c['R']);rd=np.array(c['Rd']);dt=c['dt'];err=x-reference;du=u-np.column_stack([anchor,u[:,:-1]])
 parts={
 'stage_position_dt_scaled':float(dt*np.sum(q[:2,None]*err[:2,:-1]**2)),
 'stage_velocity_dt_scaled':float(dt*np.sum(q[3:,None]*err[3:,:-1]**2)),
 'stage_heading_dt_scaled':float(dt*np.sum(2*q[2]*(1-np.cos(err[2,:-1])))),
 'stage_absolute_control_dt_scaled':float(dt*np.sum(r[:,None]*u**2)),
 'stage_control_increment_dt_scaled':float(dt*np.sum(rd[:,None]*du**2)),
 'terminal_state_not_dt_scaled':float(c['Qf_scale']*(sum(q[i]*err[i,-1]**2 for i in [0,1,3,4,5])+2*q[2]*(1-math.cos(err[2,-1]))))}
 parts['total']=math.fsum(parts.values());return parts
def validate_answer(answer,job,c):
 x=matrix(answer['X'],(6,21));u=matrix(answer['U'],(2,20));ref=matrix(job['reference'],(6,21));anchor=matrix(job['anchor_n'],(2,));state=matrix(job['target_state'],(6,))
 require(np.max(np.abs(matrix(answer['first_control'],(2,))-u[:,0]))<1e-14,'first control differs from U0')
 require(answer['actual_OCP_input_changed'] is False and answer['solver_NLP_cost_readback'] is False and answer['KKT_convergence_proven'] is False,'unearned solver claims')
 for key in ['wall_ms','kernel_solve_ms']:require(math.isfinite(answer[key]) and answer[key]>=0,'finite timing')
 rollout=np.zeros((6,21));rollout[:,0]=state
 for k in range(20):rollout[:,k+1]=forward(rollout[:,k],u[:,k],c)
 rollout_error=float(np.max(np.abs(rollout-matrix(answer['feasible_rollout_X'],(6,21)))))
 require(rollout_error<=1e-11,'independent nonlinear rollout mismatch')
 defect=max(float(np.max(np.abs(forward(x[:,k],u[:,k],c)-x[:,k+1]))) for k in range(20));initial=float(np.max(np.abs(x[:,0]-state)));rate=float(np.max(np.abs(u-np.column_stack([anchor,u[:,:-1]]))));bounds=max(0.,float(np.max(c['command_min_n']-u)),float(np.max(u-c['command_max_n'])))
 for key,value in [('nonlinear_RK4_state_defect_max_abs',defect),('initial_state_max_abs_error',initial),('largest_control_increment_n',rate),('input_bound_violation_n',bounds)]:require(abs(answer[key]-value)<=1e-11,'diagnostic differs: '+key)
 require(bounds<=1e-8 and rate<=c['backend_rate_n_s']*c['dt']+1e-8,'input constraints');require(math.isfinite(initial),'finite recorded initial residual')
 max_cost_error=0.
 for key,states in [('objective_self_computed',x),('feasible_rollout_objective_self_computed',rollout)]:
  expected=objective(states,u,ref,anchor,c)
  for name,val in expected.items():
   err=abs(answer[key][name]-val);max_cost_error=max(max_cost_error,err);require(err<=1e-10*max(1.,abs(val)),'independent cost mismatch: '+key+'/'+name)
 return dict(rollout_max_abs_error=rollout_error,cost_max_abs_error=max_cost_error,defect=defect,initial_state_max_abs_error=initial,input_bound_violation_n=bounds,largest_control_increment_n=rate)
def summary(answers,scope):
 first=answers[0];u0=np.array(first['first_control']);control_deltas=[float(np.max(np.abs(np.array(a['first_control'])-u0))) for a in answers]
 base=first['feasible_rollout_objective_self_computed']['total'];cost_deltas=[abs(a['feasible_rollout_objective_self_computed']['total']-base)/max(abs(base),1e-15) for a in answers]
 du=max(control_deltas);relative=du/max(float(np.max(np.abs(u0))),1e-15);dc=max(cost_deltas)
 return dict(first_control_iteration1_n=first['first_control'],first_control_iteration12_n=answers[-1]['first_control'],max_control_delta_from_iteration1_n=du,max_control_relative_delta=relative,max_feasible_cost_relative_delta=dc,feasible_cost_iteration1=base,feasible_cost_iteration12=answers[-1]['feasible_rollout_objective_self_computed']['total'],defect_iteration1=first['nonlinear_RK4_state_defect_max_abs'],defect_iteration12=answers[-1]['nonlinear_RK4_state_defect_max_abs'],nearly_unchanged=du<=scope['primary_small_change_control_abs_n'] and relative<=scope['primary_small_change_control_relative_fraction'] and dc<=scope['primary_small_change_feasible_cost_relative_fraction'],kernel_ms_min=min(a['kernel_solve_ms'] for a in answers),kernel_ms_max=max(a['kernel_solve_ms'] for a in answers))
def main():
 paths=[N/'actual_startup_input_v1.json',D/'preregister/selected_solver_scope_v1.json',D/'replay/native_startup_v1.json',D/'replay/offline_invocation_v1.json',D/'preregister/offline_invocation_lock_v1.json',Path(__file__).resolve()]
 before={str(p):sha(p) for p in paths};inp,scope,result,invocation,lock=[load(p) for p in paths[:5]]
 require(invocation['passed'] and invocation['input_closure_unchanged'],'invocation success')
 require(result['input_sha256']==scope['input_sha256']==sha(paths[0]) and result['input_unchanged'],'input binding')
 require(result['source_bundle_sha256']==lock['source_bundle_sha256'] and result['binary_sha256']==lock['binary']['sha256'],'source/binary binding')
 for key in ['stage_qualified','execute_qualified','research_conclusion','actual_ROS_nodes_started','runtime_code_or_endpoint_policy_changed','generated_code_changed']:require(result[key] is False,'qualification scope '+key)
 require(result['baseline']['jobs']==102 and len(inp['ordered_native_jobs'])==102,'complete native order')
 for kind in ['public_vs_actual','raw_shift_vs_actual','public_vs_raw_shift']:
  row=result['baseline'][kind];require(row['control']<=1e-10 and row['X']<=1e-9 and row['U']<=1e-9,'baseline equivalence')
 # Bind extracted 102 Job/expected tuples to the sealed actual Worker source.
 workerpath=Path(inp['source_run_dir'])/'worker/source.jsonl';require(sha(workerpath)==inp['evidence'][str(workerpath)],'actual Worker evidence')
 actual=[r for r in map(json.loads,workerpath.read_text().splitlines()) if r.get('type')=='candidate'];require(len(actual)==102,'actual candidates')
 for extracted,raw in zip(inp['ordered_native_jobs'],actual):
  require(extracted['job']==raw['job'],'exact actual Job extraction')
  for key in ['first_control','X','U']:require(extracted['expected'][key]==raw[key],'exact actual output extraction')
 require([c['job_id'] for c in result['cases']]==scope['selected_job_ids']==[1,2,5,10],'selected scope unchanged')
 cases=[];audits=[]
 for case in result['cases']:
  jid=case['job_id'];job=inp['ordered_native_jobs'][jid-1]['job'];require(case['fixed_Job']==job and case['warm_prefix_jobs']==jid-1,'actual full-prefix selection')
  require(case['same_state_anchor_reference_params_every_repeat'] is True and case['repeated_closed_loop_claimed'] is False,'fixed Job scope')
  require([r['iteration'] for r in case['iterations']]==list(range(1,13)),'finite repeat count')
  for step in case['iterations']:
   for method in METHODS:audits.append(validate_answer(step[method],job,inp['contract']))
   for key in ['first_control','X','U']:require(np.max(np.abs(np.array(step['public_shift'][key])-np.array(step['raw_shift'][key])))<=1e-10,'raw/public same-shift equivalence')
  expected=inp['ordered_native_jobs'][jid-1]['expected']
  for method in METHODS:
   for key in ['first_control','X','U']:require(np.max(np.abs(np.array(case['iterations'][0][method][key])-np.array(expected[key])))<=1e-9,'selected first iteration equals actual')
  cases.append(dict(job_id=jid,warm_prefix_jobs=jid-1,methods={m:summary([r[m] for r in case['iterations']],scope) for m in METHODS}))
 # Verify the independent auditor rejects corruptions that would change claims.
 boundary=[];base=result['cases'][0]['iterations'][0]['public_shift'];job=inp['ordered_native_jobs'][0]['job']
 for name,mutate in [('nonfinite_prediction',lambda a:a['X'].__setitem__(0,float('nan'))),('wrong_first_control',lambda a:a['first_control'].__setitem__(0,a['first_control'][0]+.01)),('wrong_cost',lambda a:a['objective_self_computed'].__setitem__('total',a['objective_self_computed']['total']+.01)),('wrong_rollout',lambda a:a['feasible_rollout_X'].__setitem__(12,a['feasible_rollout_X'][12]+.01)),('unearned_KKT_claim',lambda a:a.__setitem__('KKT_convergence_proven',True))]:
  bad=copy.deepcopy(base);mutate(bad)
  try:validate_answer(bad,job,inp['contract'])
  except ValueError as e:boundary.append(dict(name=name,rejected=True,reason=str(e)))
  else:raise ValueError('boundary corruption accepted: '+name)
 after={str(p):sha(p) for p in paths};require(before==after,'audit input mutation')
 out=dict(schema='scheme-A-startup-RTI-independent-audit/v1',passed=True,baseline=result['baseline'],cases=cases,independently_checked_answers=len(audits),independent_rollout_max_abs_error=max(r['rollout_max_abs_error'] for r in audits),independent_cost_max_abs_error=max(r['cost_max_abs_error'] for r in audits),initial_state_max_abs_error=max(r['initial_state_max_abs_error'] for r in audits),initial_state_residual_exceeds_1e_10_count=sum(r['initial_state_max_abs_error']>1e-10 for r in audits),input_bound_violation_n=max(r['input_bound_violation_n'] for r in audits),largest_control_increment_n=max(r['largest_control_increment_n'] for r in audits),initial_state_exact_equality_claimed=False,negative_boundaries=boundary,all_actual_102_job_output_tuples_equal=True,input_sha256_before=before,input_sha256_after=after,primary_mechanism_nearly_unchanged=all(cases[0]['methods'][m]['nearly_unchanged'] for m in METHODS),new_closed_loop_performance_qualified=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 write(D/'postrun/startup_mechanism_audit_v2.json',out);print(json.dumps({k:v for k,v in out.items() if k not in ['input_sha256_before','input_sha256_after','negative_boundaries']},allow_nan=False))
if __name__=='__main__':main()
