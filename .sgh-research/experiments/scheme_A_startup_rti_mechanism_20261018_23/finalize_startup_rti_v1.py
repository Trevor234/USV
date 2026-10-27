#!/usr/bin/env python3
"""Create-only offline author freeze, semantic QA and full MPC delivery.

`passed` in final_QA means archive integrity; cases_complete and blocked_gate
state the experimental outcome separately. No ROS node, test or goal is started.
Inventory includes final_QA but excludes itself and the delivery receipt. Receipt
pins inventory/QA; it never claims a self hash. Nothing is overwritten except the
previously backed-up intermediate MPC CURRENT.md, with exact-byte precondition.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,stat,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_startup_rti_mechanism_20261018_v23'
M=Path('/home/trevor/MPC')/D.name
METADATA={'archive_inventory_v1.json','delivery_verification.json'}
INTERMEDIATE={'CURRENT.md','preflight/preflight_reflection_startup_rti_v1.md','protection_v1.py'}

def require(value,reason):
 if not value:raise RuntimeError(reason)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(path):return json.loads(Path(path).read_text())
def write(path,value):
 raw=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
 with Path(path).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(Path(path).read_bytes()==raw,'metadata_readback:'+str(path))
def population(root):
 require(root.is_dir() and not root.is_symlink(),'regular_root:'+str(root))
 paths=list(root.rglob('*'));require(not any(p.is_symlink() for p in paths),'archive_symlink:'+str(root))
 require(all(p.is_file() or p.is_dir() for p in paths),'archive_special_file:'+str(root))
 return sorted(p for p in paths if p.is_file()),sorted(str(p.relative_to(root)) for p in paths if p.is_dir())
def files(root):return population(root)[0]
def copy_exact(source,destination):
 source=Path(source);destination=Path(destination);before=sha(source);mode=stat.S_IMODE(source.stat().st_mode)
 destination.parent.mkdir(parents=True,exist_ok=True)
 with destination.open('xb') as target:
  with source.open('rb') as original:shutil.copyfileobj(original,target,1024*1024)
  target.flush();os.fsync(target.fileno())
 os.chmod(destination,mode&0o777)
 require(sha(source)==before==sha(destination),'copy_changed:'+str(source));return before

def preserve_intermediate():
 record=D/'postrun/intermediate_MPC_backup_v1.json';root=D/'intermediate_MPC_backup_v1'
 if record.exists():
  data=load(record)
  for r in data['files']:require(sha(r['snapshot'])==r['sha256'],'intermediate_backup_changed')
  return data
 original,_=population(M);require({str(p.relative_to(M)) for p in original}==INTERMEDIATE,'unexpected_intermediate_MPC_population')
 root.mkdir(exist_ok=False);rows=[]
 for source in original:
  rel=source.relative_to(M);target=root/rel;digest=copy_exact(source,target)
  rows.append({'relative_path':str(rel),'original':str(source),'snapshot':str(target),'sha256':digest,'bytes':source.stat().st_size})
 data={'schema':'startup-rti-mechanism-intermediate-MPC-backup/v1','files':rows,'count':len(rows),'all_three_intermediate_files_preserved':True}
 write(record,data);return data

def freeze():
 preserve_intermediate();root=D/'author_snapshot';root.mkdir(exist_ok=False);original,directories=population(N);rows=[]
 for rel in directories:(root/rel).mkdir(parents=True,exist_ok=True)
 for source in original:
  rel=source.relative_to(N);target=root/rel;digest=copy_exact(source,target)
  rows.append({'relative_path':str(rel),'original':str(source),'snapshot':str(target),'sha256':digest,'bytes':source.stat().st_size})
 after,afterdirs=population(N);snap,snapdirs=population(root)
 require(after==original and afterdirs==directories,'author_population_changed_during_freeze')
 require({str(p.relative_to(root)) for p in snap}=={r['relative_path'] for r in rows} and snapdirs==directories,'author_snapshot_population')
 write(D/'postrun/author_freeze_v1.json',{'schema':'startup-rti-mechanism-author-freeze/v1','count':len(rows),'bytes':sum(r['bytes'] for r in rows),'files':rows,'directories':directories,'all_sources_runs_failed_attempts_and_raw_Storage_preserved':True})
 print(json.dumps({'author_files_frozen':len(rows),'author_bytes':sum(r['bytes'] for r in rows)}))

def qa():
 initial_path=D/'preflight/workspace_initial_v3.json';final_path=D/'preflight/workspace_final_v3.json'
 initial=load(initial_path);final=load(final_path)
 require(initial['passed'] and final['passed'],'initial_and_final_full_preservation')
 close=load(D/'postrun/workspace_close_check_v1.json');require(close['passed'] and close['workspace_projection_matches_full_final_proof'] and close['declared_real_launch_delta_still_exact'] and close['full_final_proof_sha256']==sha(final_path),'closing_workspace_projection_and_declared_exception')
 require(initial['protection']['unique_raw_files_reread']==final['protection']['unique_raw_files_reread']==58148 and initial['protection']['logical_bytes_streamed']==final['protection']['logical_bytes_streamed']==6366146238,'same_initial_final_full_asset_scope')
 require(final['protection']['parent_D22_RMSE_failure_preserved'] and final['protection']['parent_D22_archive_pairs']==1885,'frozen_parent_failure_required')
 frozen=load(D/'postrun/author_freeze_v1.json');original,dirs=population(N);copied,copydirs=population(D/'author_snapshot')
 require(len(original)==frozen['count']==6 and dirs==frozen['directories']==copydirs,'offline_author_population')
 require({str(p) for p in original}=={r['original'] for r in frozen['files']} and {str(p) for p in copied}=={r['snapshot'] for r in frozen['files']},'author_complete_snapshot')
 for row in frozen['files']:require(sha(row['original'])==row['sha256']==sha(row['snapshot']),'author_bytes')
 build=load(D/'build/replay_attempt02/result.json');audit=load(D/'postrun/startup_mechanism_audit_v2.json');latency=load(D/'postrun/startup_latency_audit_v1.json');invocation=load(D/'replay/offline_invocation_v1.json');lock=load(D/'preregister/offline_invocation_lock_v1.json')
 require(build['passed'] and build['native_tests']==dict(tests=10,failures=0,errors=0,disabled=0),'ten_native_component_checks')
 require(audit['passed'] and audit['all_actual_102_job_output_tuples_equal'] and audit['independently_checked_answers']==144 and len(audit['negative_boundaries'])==5 and all(r['rejected'] for r in audit['negative_boundaries']),'independent_mechanism_numeric_audit')
 require(latency['audit_passed'] and latency['exact_original_gate_reproduced'] and latency['frozen_RMSE_failure_changed'] is False,'read_only_latency_and_error_budget')
 require(invocation['passed'] and invocation['input_closure_unchanged'] and invocation['lock_sha256']==sha(D/'preregister/offline_invocation_lock_v1.json'),'pre_execution_closure_lock')
 for path,digest in lock['files'].items():require(sha(path)==digest,'locked_input_changed:'+path)
 for path,target in lock['aliases'].items():require(str(Path(path).resolve(strict=True))==target,'locked_alias_changed:'+path)
 for path,digest in audit['input_sha256_after'].items():require(sha(path)==digest,'audit_input_changed:'+path)
 require(audit['input_sha256_before']==audit['input_sha256_after'],'read_only_audit')
 require(audit['initial_state_exact_equality_claimed'] is False and audit['initial_state_max_abs_error']==2.2526709664294486e-10 and audit['initial_state_residual_exceeds_1e_10_count']==36,'approximate_initial_residual_honestly_reported')
 native=load(D/'replay/native_startup_v1.json');interp=load(D/'postrun/startup_interpretation_v1.json');first=native['cases'][0]['iterations'][0]['raw_unshifted'];last=native['cases'][0]['iterations'][-1]['raw_unshifted']
 require(interp['native_result_sha256']==sha(D/'replay/native_startup_v1.json') and interp['primary_nearly_unchanged'] is audit['primary_mechanism_nearly_unchanged'] is False,'derived_mechanism_binding')
 require(interp['first_hold_nominal_surge_delta_m_s']==last['feasible_rollout_X'][9]-first['feasible_rollout_X'][9],'derived_first_interval_delta')
 require(interp['full_control_horizon_max_delta_n']==max(abs(a-b) for a,b in zip(last['U'],first['U'])),'derived_full_horizon_delta')
 require(interp['feasible_cost_relative_decrease']==(first['feasible_rollout_objective_self_computed']['total']-last['feasible_rollout_objective_self_computed']['total'])/first['feasible_rollout_objective_self_computed']['total'],'derived_cost_decrease')
 require(load(D/'build/replay_attempt01/result.json')['passed'] is False and load(D/'preflight/workspace_initial_v1.json')['passed'] is False,'failed_attempts_retained')
 require(sha(D/'postrun/startup_latency_audit_v1.py')==latency['recipe_sha256'],'latency_recipe_identity')
 require((D/'documents/方案A_启动RTI机制对照_结果与下一步_2026-10-18.md').is_file() and (D/'documents/next_objective_mechanism_plan_v1.md').is_file(),'result_and_next_plan_documents')
 fixed={str(p):dict(sha256=sha(p),bytes=p.stat().st_size) for p in files(D)}
 result=dict(schema='startup-rti-mechanism-final-QA/v1',passed=True,passed_semantics='archive integrity and the stated offline numeric audit only; no new closed-loop qualification',archive_integrity_passed=True,offline_mechanism_complete=True,new_closed_loop_run=False,new_closed_loop_performance_qualified=False,parent_first_RMSE_gate_failure_preserved=True,speed_ladder_advanced=False,cases_complete=False,all_planned_cases_passed=False,batch_status='offline_mechanism_complete_parent_gate_still_failed',blocked_gate='parent_s005_RMSE',baseline=audit['baseline'],primary_mechanism_nearly_unchanged=audit['primary_mechanism_nearly_unchanged'],selected_jobs=[r['job_id'] for r in audit['cases']],native_GTest_cases=10,independent_checked_answers=144,auditor_negative_boundaries=5,initial_protection_sha256=sha(initial_path),final_protection_sha256=sha(final_path),selected_build_result_sha256=sha(D/'build/replay_attempt02/result.json'),native_result_sha256=sha(D/'replay/native_startup_v1.json'),independent_audit_sha256=sha(D/'postrun/startup_mechanism_audit_v2.json'),latency_audit_sha256=sha(D/'postrun/startup_latency_audit_v1.json'),preregistration_sha256=sha(D/'preregister/selected_solver_scope_v1.json'),fixed_files=fixed,fixed_file_count=len(fixed),author_frozen_files=frozen['count'],author_freeze_sha256=sha(D/'postrun/author_freeze_v1.json'),historical_original_path_statement=dict(all_historical_original_path_bytes_unchanged=final['protection'].get('all_historical_original_path_bytes_unchanged'),explicit_live_original_path_exceptions=final['protection'].get('explicit_live_original_path_exceptions',[])),stage_qualified=False,execute_qualified=False,research_conclusion=False)
 write(D/'postrun/final_QA_v1.json',result);print(json.dumps({k:result[k] for k in ['archive_integrity_passed','offline_mechanism_complete','new_closed_loop_performance_qualified','fixed_file_count','author_frozen_files','batch_status']}))

def verify_fixed(q):
 for path,row in q['fixed_files'].items():require(sha(path)==row['sha256'],'fixed_QA_input_changed:'+path)
def deliver():
 qpath=D/'postrun/final_QA_v1.json';q=load(qpath);require(q['archive_integrity_passed'] is True,'archive_QA_integrity');verify_fixed(q)
 backup=load(D/'postrun/intermediate_MPC_backup_v1.json');backup_rows={r['relative_path']:r for r in backup['files']}
 for r in backup_rows.values():require(sha(r['snapshot'])==r['sha256'],'intermediate_MPC_backup_identity')
 invpath=D/'archive_inventory_v1.json';receiptpath=D/'delivery_verification.json'
 source,directories=population(D);datafiles=[p for p in source if str(p.relative_to(D)) not in METADATA]
 inventory={'schema':'startup-rti-mechanism-archive-inventory/v1','files':[{'relative_path':str(p.relative_to(D)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in datafiles],'directories':directories,'metadata_rule':'inventory excludes itself and receipt; final population adds exactly these two metadata files','cases_complete':q['cases_complete'],'batch_status':q['batch_status'],'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 if invpath.exists():require(load(invpath)==inventory,'existing_inventory_changed')
 else:write(invpath,inventory)
 expected={r['relative_path'] for r in inventory['files']}|{'archive_inventory_v1.json'}
 if receiptpath.exists():expected.add('delivery_verification.json')
 require({str(p.relative_to(D)) for p in files(D)}==expected,'source_archive_population_changed')
 if not M.exists():M.mkdir(parents=True)
 current,_=population(M)
 require({str(p.relative_to(M)) for p in current}<=expected,'unexpected_MPC_files')
 for rel in directories:(M/rel).mkdir(parents=True,exist_ok=True)
 for rel in sorted(expected):
  source=D/rel;target=M/rel
  if target.exists():
   if sha(target)==sha(source):continue
   require(rel=='CURRENT.md' and rel in backup_rows and sha(target)==backup_rows[rel]['sha256'],'unexpected_previous_delivery_differs:'+rel)
   temporary=M/'CURRENT.md.final-copy.tmp'
   copy_exact(source,temporary);os.replace(temporary,target)
  else:copy_exact(source,target)
  require(sha(source)==sha(target),'MPC_copy_readback:'+rel)
 require({str(p.relative_to(M)) for p in files(M)}==expected,'MPC_complete_population')
 for rel in expected:require(sha(D/rel)==sha(M/rel),'full_second_SHA_readback:'+rel)
 verification={'schema':'startup-rti-mechanism-MPC-delivery/v1','passed':True,'source':str(D),'destination':str(M),'files_before_delivery_receipt':len(inventory['files'])+1,'final_regular_files_per_root':len(inventory['files'])+2,'inventory_declared_data_files':len(inventory['files']),'complete_population_equal':True,'full_byte_readback':True,'full_second_SHA_readback':True,'archive_inventory_sha256':sha(invpath),'final_QA_sha256':sha(qpath),'author_freeze_sha256':sha(D/'postrun/author_freeze_v1.json'),'intermediate_files_backed_up':len(backup_rows),'cases_complete':q['cases_complete'],'batch_status':q['batch_status'],'blocked_gate':q['blocked_gate'],'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 if receiptpath.exists():require(load(receiptpath)==verification,'existing_receipt_changed')
 else:write(receiptpath,verification)
 if (M/receiptpath.name).exists():require((M/receiptpath.name).read_bytes()==receiptpath.read_bytes(),'MPC_receipt_differs')
 else:copy_exact(receiptpath,M/receiptpath.name)
 require({str(p.relative_to(D)) for p in files(D)}=={str(p.relative_to(M)) for p in files(M)},'final_full_population')
 for p in files(D):require(sha(p)==sha(M/p.relative_to(D)),'final_metadata_inclusive_readback:'+str(p))
 print(json.dumps({'passed':True,'destination':str(M),'files':verification['final_regular_files_per_root'],'cases_complete':q['cases_complete'],'batch_status':q['batch_status'],'receipt_sha256':sha(receiptpath)},ensure_ascii=False))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['freeze','qa','deliver']);args=parser.parse_args();{'freeze':freeze,'qa':qa,'deliver':deliver}[args.mode]()
