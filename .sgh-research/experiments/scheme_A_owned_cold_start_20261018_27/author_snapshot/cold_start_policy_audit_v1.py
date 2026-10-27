"""Independent native-policy source audit; no change to inherited control/performance gates."""
from pathlib import Path
import json,math
POLICY='current_job_free_once_then_fixed050_three_rti_v1'
def load(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(s) for s in Path(p).read_text().splitlines()]
def close(a,b,tol=1e-9):return type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol
def vector(v,n):return type(v) is list and len(v)==n and all(type(x) in (int,float) and math.isfinite(x) for x in v)
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

def causal_seed_valid(j,preliminary,seed,hydro):
 try:
  u=seed['U'];a=seed['X_aug']
  if not vector(u,40) or not vector(a,168) or u[:2]!=[.5,.5] or u[2:]!=preliminary['U'][2:]:return False
  x=list(j['target_state'])
  for k in range(21):
   expected=x+(j['anchor_n'] if k==0 else u[2*(k-1):2*k])
   if any(not close(p,q,1e-11) for p,q in zip(a[8*k:8*k+8],expected)):return False
   if k<20:x=forward(x,u[2*k:2*k+2],.2,hydro)
  return True
 except (KeyError,TypeError,ValueError,IndexError):return False

def warm_restore_valid(last,before,after,bounds):
 try:
  return (before==after and before['warm'] is True and before['X_aug']==last['augmented_X'][8:]+last['augmented_X'][-8:]
   and before['U']==last['U'][2:]+last['U'][-2:] and bounds['lbu']==[-25.,-25.] and bounds['ubu']==[25.,25.]
   and bounds['additional_first_equality'] is False and bounds['read_from_actual_C_API'] is True)
 except (KeyError,TypeError):return False

def objective(x,u,ref,anchor,c):
 q=c['Q'];r=c['R'];rd=c['Rd'];dt=c['dt'];position=velocity=heading=effort=increment=terminal=0.;previous=anchor
 for k in range(20):
  for i in [0,1]:position+=dt*q[i]*(x[6*k+i]-ref[6*k+i])**2
  for i in [3,4,5]:velocity+=dt*q[i]*(x[6*k+i]-ref[6*k+i])**2
  heading+=dt*2*q[2]*(1-math.cos(x[6*k+2]-ref[6*k+2]))
  for i in [0,1]:effort+=dt*r[i]*u[2*k+i]**2;increment+=dt*rd[i]*(u[2*k+i]-previous[i])**2
  previous=u[2*k:2*k+2]
 for i in [0,1,3,4,5]:terminal+=c['Qf_scale']*q[i]*(x[120+i]-ref[120+i])**2
 terminal+=c['Qf_scale']*2*q[2]*(1-math.cos(x[122]-ref[122]))
 return dict(position=position,velocity=velocity,heading=heading,effort=effort,increment=increment,terminal=terminal,total=position+velocity+heading+effort+increment+terminal)

def analyze(run,inputs,contract,observer,decoded,c):
 run=Path(run);workers=lines(run/'worker/source.jsonl');candidates={r['job']['job_id']:r for r in workers if r.get('type')=='candidate'};events=[r for r in workers if r.get('type')=='cold_start_policy_result'];failures=[r for r in workers if r.get('type')=='cold_start_policy_failure']
 c.need(contract.get('diagnostic_contract_revision')==9 and contract.get('cold_start_policy')==POLICY,'cold_exact_authenticated_policy')
 c.need(not failures,'cold_no_failed_native_policy_in_normal_case',failures=len(failures));c.need(len(events)==len(candidates) and {r['job_id'] for r in events}==set(candidates),'cold_complete_policy_candidate_population')
 applied=[r for r in events if r['metadata'].get('candidate_applied') is True];c.need(len(applied)==1 and applied[0]['job_id']==1,'cold_exactly_one_actual_first_job_policy',count=len(applied))
 summaries=[];selected=None
 for event in events:
  candidate=candidates[event['job_id']];j=candidate['job'];m=event['metadata'];active=m['candidate_applied'];calls=m['subcalls'];expected=4 if active else 1
  context={k:j[k] for k in ['run_id','boot_id','contract_hash','config_generation','model_generation','task_generation','schedule_generation','clock_epoch']}
  c.need(m['schema']=='owned-cold-start-native-policy-v1' and m['policy']==POLICY and m['context']==context and event['worker_instance']==candidate['worker_instance'],'cold_current_native_context_binding',job_id=j['job_id'])
  c.need(m['successful'] is True and m['terminal'] is False and m['backend_entries_started']==m['backend_entries_completed']==len(calls)==expected and [r['ordinal'] for r in calls]==list(range(1,expected+1)),'cold_bounded_actual_backend_entry_counts',job_id=j['job_id'])
  c.need(event['solve_start_ns']==candidate['solve_start_ns'] and event['solve_end_ns']==candidate['solve_end_ns'] and all(candidate['solve_start_ns']<=r['start_ns']<=r['end_ns']<=candidate['solve_end_ns'] and r['native_returned_success'] is True for r in calls),'cold_actual_native_entry_time_window',job_id=j['job_id'])
  c.need(m['final_first_control']==candidate['first_control'] and close(sum(r['kernel_ms'] for r in calls),candidate['backend_ms'],1e-9),'cold_final_control_and_complete_kernel_sum',job_id=j['job_id'])
  c.need(m['policy_consumed_for_run'] is True,'cold_not_rearmed_after_first_job',job_id=j['job_id'])
  if not active:
   c.need(calls[0]['additional_first_equality'] is False and calls[0]['warm_shift_after'] is True,'cold_later_jobs_original_free_shift_semantics',job_id=j['job_id']);continue
  c.need(m['applied_context']==context and m['eligibility'] is True and [r['additional_first_equality'] for r in calls]==[False,True,True,True] and [r['warm_shift_after'] for r in calls]==[False,False,False,True],'cold_first_one_plus_three_exact_semantics')
  c.need(causal_seed_valid(j,calls[0],m['causal_seed'],contract['hydro']),'cold_seed_only_current_preliminary_tail')
  c.need(warm_restore_valid(calls[-1],m['warm_after_last_shift'],m['warm_after_withdrawal'],m['restored_first_bounds']),'cold_actual_one_warm_shift_and_withdrawal')
  c.need(m['enabled_first_bounds']['lbu']==m['enabled_first_bounds']['ubu']==[.5,.5] and m['enabled_first_bounds']['additional_first_equality'] is True,'cold_actual_first_equality_enabled')
  for row in calls:
   u=row['U'];x=row['X'];c.need(vector(x,126) and vector(u,40) and vector(row['augmented_X'],168),'cold_finite_complete_native_prediction')
   c.need(row['first_control']==u[:2] and all(-25<=v<=25 for v in u),'cold_original_input_bounds')
   prior=j['anchor_n'];rate=0
   for k in range(20):rate=max(rate,max(abs(u[2*k+i]-prior[i]) for i in [0,1]));prior=u[2*k:2*k+2]
   c.need(rate<=16+1e-10,'cold_original_every_step_rate_bounds')
   if row['additional_first_equality']:c.need(max(abs(v-.5) for v in u[:2])<=1e-10,'cold_fixed_first_equality_residual')
   y=list(j['target_state']);rollout=list(y);defect=0.
   for k in range(20):
    yn=forward(y,u[2*k:2*k+2],.2,contract['hydro']);rollout+=yn;y=yn;pred=forward(x[6*k:6*k+6],u[2*k:2*k+2],.2,contract['hydro']);defect=max(defect,max(abs(a-b) for a,b in zip(pred,x[6*k+6:6*k+12])))
   summaries.append(dict(ordinal=row['ordinal'],first_control=row['first_control'],feasible_cost=objective(rollout,u,j['reference'],j['anchor_n'],contract),surge_at_dt_m_s=rollout[9],dynamic_defect=defect,largest_control_increment_n=rate))
  c.need(calls[-1]['X']==candidate['X'] and calls[-1]['U']==candidate['U'] and calls[-1]['first_control']==candidate['first_control']==[.5,.5],'cold_published_candidate_is_final_fourth_entry')
  c.need(summaries[-1]['dynamic_defect']<=1e-8,'cold_final_actual_dynamic_defect')
  decisions=[r for r in observer if r.get('type')=='decision' and r.get('job_id')==j['job_id']];accepted=[r for r in decisions if r.get('accepted') is True];c.need(len(accepted)==1,'cold_actual_first_candidate_accepted')
  pub=lines(run/'publisher/controlled_source.jsonl');emitted=[r for r in pub if r.get('type')=='controlled_Applied_emitted' and accepted and r.get('cycle_sequence')==accepted[0]['sequence'] and r.get('control_source')=='controlled_C_decision'];c.need(len(emitted)==1 and emitted[0]['final_n']==[.5,.5],'cold_actual_owner_published_candidate_command')
  stored=[r['message'] for r in decoded['/research/control/applied'] if emitted and r['message']['sequence']==emitted[0]['applied_sequence']];c.need(len(stored)==1 and stored[0]['final_n']==[.5,.5] and stored[0]['left_publish_success'] and stored[0]['right_publish_success'],'cold_StoredApplied_successful_first_command')
  selected=dict(job_id=j['job_id'],native_entry_elapsed_ms=(candidate['solve_end_ns']-candidate['solve_start_ns'])/1e6,kernel_sum_ms=candidate['backend_ms'],metadata=m,actual_job=j,actual_candidate=candidate,decision=accepted[0] if accepted else None,owner_emit=emitted[0] if emitted else None,stored_applied=stored[0] if stored else None)
 return dict(policy=POLICY,policy_events=len(events),candidate_events=len(candidates),actual_policy_applied_count=len(applied),first_job_native_call_count=4 if selected else None,selected=selected,independent_first_job_subcalls=summaries,physical_actuator_response_proven=False,new_stage_qualification=False)
