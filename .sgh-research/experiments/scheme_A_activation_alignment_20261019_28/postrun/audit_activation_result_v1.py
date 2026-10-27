#!/usr/bin/env python3
"""Preserve actual NoGo; separate causal selection, residual races and identity bookkeeping."""
from collections import Counter
from pathlib import Path
import hashlib, json, math, re, sys

D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_activation_alignment_20261019_v28'
P=D.parent/'scheme_A_owned_cold_start_20261018_27'
R=N/'runs/activation_s005_01'
def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def need(v,why):
 if not v:raise RuntimeError(why)
def percentiles(values):
 values=sorted(values)
 return dict(count=len(values),minimum=min(values),median=values[len(values)//2],p95=values[max(0,math.ceil(.95*len(values))-1)],maximum=max(values))

report=load(D/'runs/s005_01/check_result.json');run=load(R/'result.json');pre=load(D/'preregister/activation_v1.json')
inputs=dict(report['input_sha256_after']);need(inputs==report['input_sha256_before'],'original reader read-only')
inputs.update(load(P/'runs/s005_01/check_result.json')['input_sha256_after'])
for p in [D/'runs/s005_01/check_result.json',D/'preregister/activation_v1.json',N/'pair_wakeup_contract_v1.json',N/'check_pair_wakeup_v1.py',N/'cold_start_contract_v1.py',N/'cold_start_contract_spec_v1.json',N.parent/'authored_D1_owned_cold_start_20261018_v27/pair_wakeup_contract_v1.json',N/'observer/src/shadow/regulator_shadow_observer.cpp',P/'runs/s005_01/check_result.json']:
 inputs[str(p)]=sha(p)
need(all(sha(p)==h for p,h in inputs.items()),'original inputs current')
observer=[json.loads(l) for l in (R/'observer/source.jsonl').read_text().splitlines()]
window=report['window'];ds=[r for r in observer if r.get('type')=='decision' and r.get('job_id',0)>0 and window['start_ready_ns']<=r['activation_commit_ns']<window['end_driver_requested_ns']]
need(len(ds)==100 and sum(d['accepted'] for d in ds)==90,'complete actual window')
counts=Counter(d['reason'] for d in ds if not d['accepted']);need(counts=={'activation_input_changed_during_validation':10},'ten actual residual races only')
attempts=[a for d in ds for a in d['d0_observation']['activation_alignment']['attempts']]
retry_ds=[d for d in ds if len(d['d0_observation']['activation_alignment']['attempts'])==2]
rescued=[d for d in retry_ds if d['accepted']]
refusals=[]
for d in ds:
 if d['accepted']:continue
 aa=d['d0_observation']['activation_alignment']['attempts']
 need(len(aa)==2 and aa[0]['retry'] and not aa[1]['retry'],'bounded two passes')
 need(aa[0]['input_gate_reads']['input_imu_equal'] is False and aa[0]['input_gate_reads']['input_odom_equal'] is True and aa[1]['input_gate_reads']['input_odom_equal'] is False,'actual IMU then Odom burst')
 refusals.append(dict(job_id=d['job_id'],reason=d['reason'],attempts=[dict(attempt=a['attempt'],raw_odom_sequence=a['raw_snapshot']['odom_sequence'],raw_imu_sequence=a['raw_snapshot']['imu_sequence'],guard_odom_sequence=a['guard_snapshot']['odom_sequence'],guard_imu_sequence=a['guard_snapshot']['imu_sequence'],sample_ns=a['sample_ns'],copy_capture_ns=a['copy_capture_ns'],commit_check_ns=a['commit_check_ns'],unlocked_to_guard_ns=a['commit_check_ns']-a['copy_capture_ns'],held_history_count=a['raw_snapshot']['history_count']) for a in aa]))
first=report['cold_start_policy']['selected'];need(all(first[k] is not None for k in ['decision','owner_emit','stored_applied']),'first candidate actually applied')
need(first['decision']['accepted'] and first['owner_emit']['final_n']==first['stored_applied']['final_n']==[.5,.5] and first['stored_applied']['left_publish_success'] and first['stored_applied']['right_publish_success'],'actual complete first0.5N chain')
c=load(N/'pair_wakeup_contract_v1.json');old=load(N.parent/'authored_D1_owned_cold_start_20261018_v27/pair_wakeup_contract_v1.json');sys.path.insert(0,str(N));import cold_start_contract_v1 as strict
strict.validate(c);changes={k for k in set(c)|set(old) if c.get(k)!=old.get(k)}
need(changes=={'diagnostic_contract_revision','activation_state_policy','activation_sensor_history_capacity','activation_validation_attempts'},'only preregistered contract deltas')
text=(N/'check_pair_wakeup_v1.py').read_text();constant=re.search(r"PROJECTED_CONTRACT_SHA\s*=\s*['\"]([0-9a-f]{64})",text).group(1)
need(constant==sha(N.parent/'authored_D1_owned_cold_start_20261018_v27/pair_wakeup_contract_v1.json') and constant!=sha(N/'pair_wakeup_contract_v1.json'),'retained parent checker constant isolated')
frozen_contract_hash=pre['helper_files'][str(N/'pair_wakeup_contract_v1.json')]['sha256']
need(frozen_contract_hash==sha(N/'pair_wakeup_contract_v1.json')==load(R/'inputs.json')['contract_sha256'],'actual contract is preregistered current identity')
parent=load(P/'runs/s005_01/check_result.json');oldR=Path(load(P/'runs/s005_01/invocation.json')['run_dir']);old_observer=[json.loads(l) for l in (oldR/'observer/source.jsonl').read_text().splitlines()]
old_ds=[d for d in old_observer if d.get('type')=='decision' and d.get('job_id',0)>0 and parent['window']['start_ready_ns']<=d['activation_commit_ns']<parent['window']['end_driver_requested_ns']]
need(report['passed'] is False and {i['code'] for i in report['issues']}=={'longitudinal_20s_all_candidates_accepted_90_consecutive_18s_coverage','task_time_only_declared_sampling_and_cold_policy_fields_change_no_numeric_guard_or_objective_change','projected_preregistered_whole_measurement_RMSE_halved_parent'},'original three failures preserved')
source=(N/'observer/src/shadow/regulator_shadow_observer.cpp').read_text()
need(source.index('auto attempt_evidence=p1::Json')<source.index('auto reason=eligible(s,now);',source.index('void activate_candidate')),'new full snapshot JSON precedes guards in actual source')
need(run['cleanup_complete'] and all(v==0 for v in run['owned_role_returncodes'].values()),'five-role clean close')
need(all(sha(p)==h for p,h in inputs.items()),'read-only postrun')
out=dict(schema='activation-alignment-postrun/v1',passed=True,passed_semantics='read-only diagnosis, original NoGo remains',input_sha256_before=inputs,input_sha256_after=inputs,actual_case_passed=False,original_report_not_rewritten=True,original_issues=report['issues'],measurement_attempts=100,accepted=90,maximum_consecutive_accepts=18,rejection_counts=dict(counts),actual_window_revalidations=len(retry_ds),actual_window_rescued_revalidations=len(rescued),all_Source_revalidations=report['activation_alignment']['actual_revalidations'],all_Source_older_odom_selected=report['activation_alignment']['older_raw_odom_selected'],maximum_frames_scanned=report['activation_alignment']['maximum_frames_scanned'],all_ten_residual_failures_have_IMU_then_Odom_change=True,all_residual_failures=refusals,first_050_command_accepted=True,first_050_command_applied=True,first_native_entry_ms=first['native_entry_elapsed_ms'],first_native_kernel_ms=first['kernel_sum_ms'],first_actual_decision_sequence=first['decision']['sequence'],first_actual_Applied_sequence=first['owner_emit']['applied_sequence'],first_actual_StoredApplied=first['stored_applied'],Ready_to_first_control_api_ns=first['owner_emit']['left_start_ns']-window['start_ready_ns'],performance=report['performance'],model=report['model'],actual_alignment_audit=report['activation_alignment'],no_negative_horizon_or_causal_selection_refusal=True,contract_identity_bookkeeping=dict(stale_checker_constant=constant,actual_preregistered_contract=frozen_contract_hash,strict_current_contract_validated=True,only_declared_four_delta_keys=sorted(changes),original_NoGo_preserved=True),observation_work_diagnosis=dict(actual_new_full_snapshot_JSON_before_prediction_and_input_guard=True,new_unlocked_copy_to_guard_ns=percentiles([a['commit_check_ns']-a['copy_capture_ns'] for a in attempts]),parent_total_copy_to_final_commit_ns=percentiles([d['activation_commit_ns']-d['d0_observation']['validation_snapshot']['copy_capture_ns'] for d in old_ds]),cross_run_timing_is_not_controlled_causal_comparison=True,dominant_actual_refusal='two raw input changes across two validation attempts',next_minimal_change='defer new diagnostic JSON materialization until after final commit/publication; preserve two-pass policy and all guards before considering more synchronization changes'),stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False)
with (D/'postrun/activation_result_audit_v1.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps({k:out[k] for k in ['passed','actual_case_passed','first_050_command_applied','actual_window_revalidations','actual_window_rescued_revalidations','rejection_counts','observation_work_diagnosis']}))
