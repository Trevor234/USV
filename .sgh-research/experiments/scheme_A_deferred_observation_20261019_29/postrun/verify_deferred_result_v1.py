#!/usr/bin/env python3
"""Read-only actual acceptance, deferred observation and startup error-budget audit."""
from pathlib import Path
import hashlib,json,math,sys

D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_deferred_observation_20261019_v29'
P=D.parent/'scheme_A_activation_alignment_20261019_28'
R=N/'runs/deferred_s005_01'
def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def need(v,why):
 if not v:raise RuntimeError(why)
def stats(values):
 s=sorted(values);return dict(count=len(s),minimum=min(s),median=s[len(s)//2],p95=s[max(0,math.ceil(.95*len(s))-1)],maximum=max(s))

report=load(D/'runs/s005_01/check_result.json');pre=load(D/'preregister/deferred_v1.json');run=load(R/'result.json')
inputs=dict(report['input_sha256_after']);need(inputs==report['input_sha256_before'],'original checker was read only')
for path in [D/'runs/s005_01/check_result.json',D/'preregister/deferred_v1.json',P/'postrun/activation_result_audit_v1.json',P/'runs/s005_01/check_result.json',N/'contract_identity_v1.py',D/'verify_and_run_deferred_v1.py']:
 inputs[str(path)]=sha(path)
need(all(sha(p)==h for p,h in inputs.items()),'current frozen inputs')
need(report['passed'] is False and len(report['issues'])==1 and report['issues'][0]['code']=='projected_preregistered_whole_measurement_RMSE_halved_parent','original sole performance failure retained')
sys.path.insert(0,str(N));from contract_identity_v1 import verify_consumers,EXPECTED_CONTRACT_SHA
identity=verify_consumers(N,D/'verify_and_run_deferred_v1.py')
need(load(R/'inputs.json')['contract_sha256']==pre['contract_sha256']==EXPECTED_CONTRACT_SHA,'actual preregistered C10 identity')
observer=[json.loads(l) for l in (R/'observer/source.jsonl').read_text().splitlines()]
w=report['window'];decisions=[r for r in observer if r.get('type')=='decision' and r.get('job_id',0)>0 and w['start_ready_ns']<=r['activation_commit_ns']<w['end_driver_requested_ns']]
need(len(decisions)==101 and all(d['accepted'] and d['reason']=='' for d in decisions) and w['consecutive_accepted']==101,'all actual measurement candidates accepted')
first=report['cold_start_policy']['selected'];need(all(first[k] is not None for k in ['decision','owner_emit','stored_applied']),'actual first command chain')
need(first['stored_applied']['final_n']==[.5,.5] and first['stored_applied']['left_publish_success'] and first['stored_applied']['right_publish_success'],'first0.5 successfully published command')
attempts=[a for d in decisions for a in d['d0_observation']['activation_alignment']['attempts']]
need(len(attempts)==101 and report['activation_alignment']['actual_revalidations']==0 and report['activation_alignment']['older_raw_odom_selected']==0,'actual run did not hit live recapture or older-point branch')
for d in [r for r in observer if r.get('type')=='decision']:
 t=d['d0_observation']['activation_alignment'];need(t['decision_commit_ns']==d['activation_commit_ns']<=t['observer_publish_return_ns']<=d['end_ns']<=t['materialized_start_ns']<=t['materialized_end_ns'],'all actual deferred materialization boundaries')
raw=[json.loads(l) for l in (R/'synthetic_source/nominal_steps.jsonl').read_text().splitlines()]
samples=[row for row in raw if row.get('schema')=='p1-controlled-nominal-model-step-v1' and w['start_ready_ns']<=row['target_ns']<w['end_driver_requested_ns']]
n=len(samples);speed=.05;errors=[(row['state'][3]-speed)**2 for row in samples];total=math.fsum(errors);rmse=math.sqrt(total/n);limit=report['performance']['RMSE_limit_m_s'];allowed=n*limit**2
need(n==1020 and n==report['performance']['measurement_sensor_count'] and abs(rmse-report['performance']['measured_surge_RMSE_m_s'])<=1e-12,'full original body-surge RMSE independently recomputed')
first_delay=first['owner_emit']['left_start_ns']-w['start_ready_ns'];prefix=[]
for duration in [first_delay,500000000,1000000000,2000000000,5000000000]:
 chosen=[row for row in samples if row['target_ns']<w['start_ready_ns']+duration];value=math.fsum((row['state'][3]-speed)**2 for row in chosen)
 prefix.append(dict(duration_ns=duration,samples=len(chosen),SSE=value,fraction_of_full_observed_SSE=value/total,fraction_of_original_full_allowance=value/allowed,full_RMSE_floor_if_remaining_errors_zero=math.sqrt(value/n)))
running=0.;crossing=None
for index,(row,error) in enumerate(zip(samples,errors),1):
 running+=error
 if crossing is None and running>allowed:crossing=dict(sensor_index=index,ready_offset_ns=row['target_ns']-w['start_ready_ns'],observed_surge_m_s=row['state'][3],cumulative_SSE=running)
need(crossing is not None,'actual startup eventually exhausts full allowance')
window_times=stats([a['commit_check_ns']-a['copy_capture_ns'] for a in attempts]);materialize_times=stats([d['d0_observation']['activation_alignment']['materialized_end_ns']-d['d0_observation']['activation_alignment']['materialized_start_ns'] for d in decisions])
need(run['passed'] and run['cleanup_complete'] and len(run['owned_role_returncodes'])==5 and all(v==0 for v in run['owned_role_returncodes'].values()),'five-role normal closure')
need(all(sha(p)==h for p,h in inputs.items()),'postrun read only')
out=dict(schema='deferred-observation-postrun/v1',passed=True,passed_semantics='independent read-only audit; original experiment remains performance NoGo',input_sha256_before=inputs,input_sha256_after=inputs,original_report_not_rewritten=True,actual_case_passed=False,original_issues=report['issues'],actual_acceptance_component_observed=True,measurement_attempts=101,accepted=101,consecutive_accepted=101,measurement_candidate_refusals=0,actual_live_revalidations=0,actual_live_older_point_selections=0,unhit_live_branches_not_claimed_as_coverage=True,all_deferred_materializations_verified=report['activation_alignment']['deferred_materializations_verified'],first_050_command_accepted=True,first_050_command_applied=True,actual_contract_consumers=identity,first_control_api_delay_ns=first_delay,first_native_worker_entry_ms=first['native_entry_elapsed_ms'],first_kernel_sum_ms=first['kernel_sum_ms'],critical_copy_to_guard_ns=window_times,deferred_materialization_ns=materialize_times,parent_critical_timing_context=load(P/'postrun/activation_result_audit_v1.json')['observation_work_diagnosis'],cross_run_phase_and_load_not_controlled_for_unique_causality=True,performance=report['performance'],model=report['model'],error_budget=dict(full_sample_count=n,full_observed_SSE=total,original_allowable_SSE=allowed,original_RMSE_limit=limit,prefixes=prefix,first_allowance_exhaustion=crossing,scope='observed trajectory prefixes and this fixed original sample population; no proof that all alternative controllers/protocols are infeasible',no_tail_only_change_can_rescue_this_observed_prefix=True,pre_control_samples_are_zero=all(abs(row['state'][3])<=1e-12 for row in samples if row['target_ns']<w['start_ready_ns']+first_delay)),no_additional_experiment_or_control_tuning=True,next_action='stop first-control/RTI tuning; audit performance target provenance, startup timing and original P1 stage dependencies before any new comparison protocol',stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False)
with (D/'postrun/deferred_result_audit_v1.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps({k:out[k] for k in ['passed','actual_acceptance_component_observed','accepted','measurement_candidate_refusals','critical_copy_to_guard_ns','first_control_api_delay_ns','error_budget']}))
