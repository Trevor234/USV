#!/usr/bin/env python3
"""Final archive/integrity QA; explicit forced-supervision scope, no stage promotion."""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_bytes())
def pin(p):
 b=Path(p).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def need(v,w):
 if not v:raise ValueError(w)
def write(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False);f.write('\n')


def main():
 for leaf in ['workspace_initial_local_v1.json','workspace_final_local_v1.json']:
  p=load(D/'preflight'/leaf)
  need(p['passed'] and p['protection']['unique_raw_files_reread']==44388
       and p['protection']['logical_bytes_streamed']==5537587047
       and p['protection']['full_local_current_byte_sha_recheck'],'complete_old_local_protection')
  need(p['workspace_after']['staged_all_diff_bytes']==0,'staging_preserved')
 lock=load(D/'preflight/prerun_source_lock_v1.json')
 need(lock['count']==405,'prerun_input_population')
 for path,expected in lock['files'].items():need(pin(path)==expected,'prerun_source_changed:'+path)
 cli=load(D/'verification/driver_CLI_v2.json');need(cli['passed'] and cli['driver_sha256']==pin(D/'author/prepare_pair_wakeup_v1.py')['sha256'],'tested_driver_version')
 need(load(D/'verification/driver_CLI_v1.json')['passed'] is False,'precheck_failure_preserved')
 components=load(D/'verification/supervision_components_v1.json')
 need(components['passed'] and components['notice_and_cursor_rejected']==12
      and len(components['real_owned_child_cases'])==3,'component_checks')
 negatives=load(D/'verification/actual_supervision_negatives_v1.json')
 need(negatives['passed'] and negatives['rejected']==8,'actual_raw_negative_checks')
 audit_path=D/'postrun/supervision_actual_audit_v1.json';audit=load(audit_path)
 need(audit['passed'] and audit['component_passed'] and len(audit['sections'])==4
      and all(r['passed'] for r in audit['sections'].values()),'independent_actual_audit')
 need(audit['input_sha256_before']==audit['input_sha256_after'],'audit_input_stability')
 for name,expected in audit['input_sha256_before'].items():need(pin(name)==expected,'audited_raw_changed:'+name)
 R=D/'author/runs/v2_supervision_01';result=load(R/'result.json');launch=load(D/'postrun/v2_supervision_01_launch_v1.json')
 need(launch['returncode']==0 and not launch['external_timeout_triggered'] and launch['inputs_unchanged'],'one_bounded_run')
 need(result['passed'] is False and result['evidence_qualification_clean'] is False
      and result['V2_case_completed'] is False and result['supervision_case_completed'] is True,'normal_and_diagnostic_status_separate')
 need(result['owned_role_returncodes']=={'worker':-9,'publisher':0,'observer':0,'synthetic_source':0,'recorder':0}
      and result['cleanup_complete'] and result['cleanup_within_budget'] and not result['close_errors'] and not result.get('error'),'expected_forced_and_ordinary_exit_codes')
 need(not load(D/'postrun/final_process_observation_v1.json')['matching_research_role_processes'],'no_research_roles_left')
 metric=audit['sections']['supervisor_bridge_chain']['details']
 need(metric['contract_waits_ns']=={'worker_grace':500000000,'term_grace':1000000000,'kill_postcheck':1000000000}
      and metric['diagnostic_SIGSTOP_after_real_terminal'] and not metric['native_C_hang_proven'],'actual_scope_and_config')
 files=[{'relative_path':str(p.relative_to(R)),**pin(p)} for p in sorted(R.rglob('*')) if p.is_file()]
 write(D/'postrun/raw_run_freeze_v1.json',{'schema':'one-Source-supervision-run-freeze/v1','root':str(R),'files':files,
   'directories':[str(p.relative_to(R)) for p in sorted(R.rglob('*')) if p.is_dir()],
   'count':len(files),'bytes':sum(x['bytes'] for x in files),'Worker_forced_exit_and_incomplete_Source_retained':True})
 write(D/'postrun/postrun_retro_v1.json',{'observations':metric,
  'hypothesis_validation':{'Source_notification_measured_within_selected_domain':True,'immediate_supervision_replaces_wait_for_lifecycle_close':True,
  'real_contract_waits_verified':True,'normal_Worker_Source_qualified':False,'universal_Source_delay_bound_or_native_C_hang_proven':False},
  'mechanisms':['lifecycle_only_supervision_dispatch_repaired','notification_visibility_now_measured','contract_document_value_mismatch_corrected_without_mutating_old_documents'],
  'experience_used':['batch35 natural release/late cleanup is not an immediate stop chain','Source/normal business reception must be separated','signal intent is not the actual syscall time'],
  'recursive_same_case_run_justified':False,'scope_stop_condition_met':True,
  'next':{'objective':'V3 owned source/clock change versus bounded activation-history revalidation','confidence':'medium','impact':'high',
  'safe_first_action':'verify current native/runtime trigger interfaces and affected role versions before one scoped live interleaving',
  'stop_condition':'no fabricated observation edit or unbounded wait; no repeat without new mechanism evidence'},
  'EDA_route_WNS_PPA':'not applicable','stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 write(D/'postrun/final_QA_v1.json',{'schema':'Source-supervisor-final-QA/v1','passed':True,
  'passed_scope':'single Source-authenticated explicit diagnostic forced-escalation chain, associated data closure and archive integrity',
  'actual_ROS_runs':1,'real_supervisor_component_children':3,'CXX_builds':0,'all_five_role_ELFs_reused':True,
  'source_notice_and_inode_negative_checks':12,'actual_raw_negative_checks':8,'prerun_inputs_unchanged':405,
  'old_local_paths_rechecked':44388,'old_local_bytes_rechecked':5537587047,
  'actual_audit_pin':pin(audit_path),'metrics':metric,'forced_Worker_normal_Source_qualified':False,
  'ordinary_unpaused_supervision_profile_qualified':False,'all_terminal_cause_dispatch_qualified':False,
  'native_C_hang_qualified':False,'universal_notification_WCET_qualified':False,
  'normal_business_passed':False,'stage_qualified':False,'execute_qualified':False,'true_plant_qualified':False,'research_conclusion':False,
  'current_MPC_delivery_pending_at_QA':True,'delivery_authority':'delivery_verification.json'})
 write(D/'batch_status_final.json',{'batch':36,'status':'Source_to_owned_supervisor_forced_escalation_diagnostic_closed',
  'actual_ROS_runs':1,'component_validation_passed':True,'single_diagnostic_chain_passed':True,
  'forced_Worker_returncode':-9,'normal_Source_and_business_qualification_preserved_false':True,
  'old_failures_and_uncommitted_changes_preserved':True,'next':'V3 source/clock/history revalidation; assess ordinary supervision policy before final freeze',
  'MPC_delivery_authority':'delivery_verification.json','stage_qualified':False,'execute_qualified':False,'true_plant_qualified':False,'research_conclusion':False})
 archived=[];directories=[]
 for p in sorted(D.rglob('*')):
  need(not p.is_symlink(),'archive_symlink:'+str(p));rel=str(p.relative_to(D))
  if p.is_dir():directories.append(rel)
  else:
   need(rel not in ['archive_inventory_v1.json','delivery_verification.json'],'archive_already_sealed')
   archived.append({'relative_path':rel,**pin(p)})
 write(D/'archive_inventory_v1.json',{'schema':'SchemeA-create-only-local-archive/v1','created_monotonic_ns':time.monotonic_ns(),
   'files':archived,'directories':directories,'inventory_excludes_itself':True,'optional_postseal_files':['delivery_verification.json'],
   'stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 print(json.dumps({'passed':True,'sealed_files_including_inventory':len(archived)+1,
  'sealed_bytes_including_inventory':sum(x['bytes'] for x in archived)+(D/'archive_inventory_v1.json').stat().st_size,
  'inventory_sha256':pin(D/'archive_inventory_v1.json')['sha256'],'actual_ROS_runs':1}))


if __name__=='__main__':main()
