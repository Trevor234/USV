#!/usr/bin/env python3
"""Create-only V2 final QA, raw freeze and archive seal; no qualification promotion."""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_bytes())
def pin(p):
 b=Path(p).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def need(v,w):
 if not v:raise ValueError(w)
def write(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def main():
 before=load(D/'preflight/workspace_initial_local_v1.json');after=load(D/'preflight/workspace_final_local_v1.json')
 for x in [before,after]:
  need(x['passed'] and x['protection']['unique_raw_files_reread']==43359
       and x['protection']['logical_bytes_streamed']==5440520275
       and x['protection']['full_local_current_byte_sha_recheck'], 'all_old_local_assets_preserved')
  need(x['workspace_after']['staged_all_diff_bytes']==0,'empty_staging_preserved')
 locks=[]
 for leaf in ['prerun_source_lock_v1.json','prerun_source_lock_r2_v1.json','prerun_source_lock_r3_v1.json']:
  path=D/'preflight'/leaf;lock=load(path)
  for name,expected in lock['files'].items():need(pin(name)==expected,'locked_input_changed:'+name)
  locks.append({'path':str(path),'files':len(lock['files']),**pin(path)})
 build=load(D/'build/v2_worker_attempt01/build_result_v1.json')
 need(build['passed'] and build['Native_assertions']==22 and not build['codegen_performed'] and not build['install_performed'],'selected_Worker_build')
 need(len(list((D/'build').glob('v2_worker_attempt*')))==1,'one_actual_CXX_build')
 for leaf,count in [('V2_time_boundaries_v1.json',12),('V2_causal_close_r3_v1.json',10)]:
  r=load(D/'verification'/leaf);need(r['passed'] and len(r['cases'])==count,'targeted_checks:'+leaf)
 r=load(D/'verification/actual_V2_suffix_negative_v1.json');need(r['passed'] and r['rejected']==8,'actual_terminal_negatives')
 audits=[]
 for leaf in ['v2_lease_r3_audit_v1.json','v2_active_r3_audit_v1.json']:
  audit=load(D/'postrun'/leaf)
  need(audit['passed'] and audit['component_passed'] and not audit['driver_normal_business_passed']
       and not audit['normal_final_unified_version_qualified'],'scoped_audit_passed')
  need(audit['input_sha256_before']==audit['input_sha256_after'],'audit_input_stability')
  for name,expected in audit['input_sha256_before'].items():need(pin(name)==expected,'audited_raw_changed:'+name)
  audits.append({'path':str(D/'postrun'/leaf),'sections':{k:v['passed'] for k,v in audit['sections'].items()},**pin(D/'postrun'/leaf)})
 cross=load(D/'postrun/cross_run_recovery_scope_v1.json')
 need(cross['passed'] and cross['V2_scoped_minimal_cases_complete'] and not cross['all_original_V2_stage_claims_complete']
      and not cross['watchdog_triggered_TERM_KILL_deadline_qualified'],'cross_run_scope')
 need(not load(D/'postrun/final_research_process_observation_v1.json')['matching_role_processes'],'no_owned_role_processes_left')
 frozen=[]
 for sub,run,kind in [('author','v2_lease_01','unreleased_library_failure'),('author','v2_lease_r2_02','literal_reason_and_normal_anchor_close_failure'),
                      ('author_r3','v2_lease_r3_04','final_scoped_profile_pass'),('author_r3','v2_active_r3_05','final_scoped_profile_pass')]:
  root=D/sub/'runs'/run;result=load(root/'result.json')
  need(result['cleanup_complete'] and result['cleanup_within_budget'],'all_attempt_resources_closed:'+run)
  files=[{'relative_path':str(p.relative_to(root)),**pin(p)} for p in sorted(root.rglob('*')) if p.is_file()]
  frozen.append({'root':str(root),'kind':kind,'files':files,'directories':[str(p.relative_to(root)) for p in sorted(root.rglob('*')) if p.is_dir()],
                 'count':len(files),'bytes':sum(r['bytes'] for r in files),'release_existed':(root/'release.json').exists(),
                 'normal_business_passed':result['passed'],'V2_case_completed':result.get('V2_case_completed',False)})
 need(len(frozen)==4 and sum(r['release_existed'] for r in frozen)==3
      and sum(r['V2_case_completed'] for r in frozen)==2,'actual_launch_release_pass_counts')
 write(D/'postrun/raw_run_freeze_v1.json',{'schema':'V2-all-actual-run-freeze/v1','runs':frozen,'all_failures_preserved':True})
 write(D/'postrun/final_QA_v1.json',{'schema':'SchemeA-V2-final-QA/v1','passed':True,
  'passed_scope':'two selected V2 fault-local/owned/Stored reception diagnostic chains plus archive integrity',
  'actual_launches':4,'released_runs':3,'final_profile_passed_runs':2,'CXX_builds':1,'Native_assertions':22,
  'time_boundary_checks':12,'causal_close_component_checks':10,'actual_suffix_negative_checks':8,
  'old_local_paths_rechecked':43359,'old_local_bytes_rechecked':5440520275,'source_locks':locks,'audits':audits,
  'selected_Worker_ELF_sha256':build['binary_sha256'],'new_run_prefix_recovery_observed':True,
  'old_normal_failures_and_source_versions_preserved':True,'normal_business_results_remain_false':True,
  'V2_scoped_minimal_cases_complete':True,'all_original_V2_stage_claims_complete':False,
  'native_C_hang_qualified':False,'watchdog_TERM_KILL_bound_qualified':False,'normal_final_unified_version_qualified':False,
  'current_MPC_delivery_pending_at_QA':True,'delivery_authority':'delivery_verification.json',
  'stage_qualified':False,'execute_qualified':False,'true_plant_qualified':False,'research_conclusion':False})
 write(D/'postrun/postrun_retro_v1.json',{'observations':{'lease_component':'655.887ms strict receipt expiry; live Worker publication while callbacks paused; no same-run revival',
  'active_component':'1189.326ms active expiry with 188.537ms receipt age; pre-native blocked job does not call native late',
  'recovery':'same ELF/new identity forms actual accepted prefix before its own separate barrier',
  'supervision_gap':'barrier released 505.910ms after terminal; Worker group empty 2180.917ms after terminal; no 500ms supervisory qualification'},
  'mechanisms':['launcher_environment_omission_before_release','diagnostic_literal_reason_mismatch','flow_policy_mismatch_between_business_anchors_and_terminal_reception'],
  'scope_stop_condition_met':True,'more_V2_local_same_case_runs_in_this_batch_justified':False,
  'next':{'objective':'bridge authenticated Observer terminal event to exact-owned Supervisor finite stop before V3',
  'confidence':'high','impact':'high','cost':'bounded implementation plus one affected confirmation','risk':'isolated localhost diagnostic only',
  'acceptance':'separately timestamp notification visibility, actual signals, waits and group empty; keep 500ms/1s/500ms contract values',
  'stop_condition':'no repeat without new mechanism evidence; preserve forced-exit and incomplete Source rather than normalizing them'},
  'EDA_route_WNS_PPA':'not applicable to this control experiment','stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 write(D/'batch_status_final.json',{'batch':35,'status':'V2_two_selected_actual_diagnostic_chains_closed',
  'V2_scoped_minimal_cases_complete':True,'original_entire_V2_and_P1_qualified':False,
  'actual_launches':4,'released_runs':3,'final_profile_passed_runs':2,'old_failures_retained':True,
  'next':'V2 terminal-to-Supervisor finite-stop bridge, then V3 source/clock/history revalidation interleaving',
  'MPC_delivery_authority':'delivery_verification.json','stage_qualified':False,'execute_qualified':False,'true_plant_qualified':False,'research_conclusion':False})
 files=[];directories=[]
 for p in sorted(D.rglob('*')):
  need(not p.is_symlink(),'no_archive_symlink:'+str(p))
  rel=str(p.relative_to(D))
  if p.is_dir():directories.append(rel)
  else:
   need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'new_archive_not_already_sealed')
   files.append({'relative_path':rel,**pin(p)})
 write(D/'archive_inventory_v1.json',{'schema':'SchemeA-create-only-local-archive/v1','created_monotonic_ns':time.monotonic_ns(),
  'files':files,'directories':directories,'inventory_excludes_itself':True,'optional_postseal_files':['delivery_verification.json'],
  'stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 print(json.dumps({'passed':True,'sealed_files_including_inventory':len(files)+1,
  'sealed_bytes_including_inventory':sum(r['bytes'] for r in files)+(D/'archive_inventory_v1.json').stat().st_size,
  'inventory_sha256':pin(D/'archive_inventory_v1.json')['sha256'],'actual_launches':4,'final_profile_passed_runs':2}))


if __name__=='__main__':main()
