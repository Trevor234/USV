#!/usr/bin/env python3
"""Seal the local fixed-tail study and separately append exact MPC delivery.

Local QA does not verify unavailable historical network mirrors. Inventory
includes QA and all retained failures, excludes itself and any later successful
delivery receipt. Network copy refuses any different existing destination file.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,stat,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_causal_cold_start_20261018_v26'
M=Path('/home/trevor/MPC')/D.name
METADATA={'archive_inventory_v1.json','delivery_verification.json'}

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
 record=D/'postrun/intermediate_local_backup_v1.json';root=D/'intermediate_local_backup_v1'
 if record.exists():
  data=load(record)
  for r in data['files']:require(sha(r['snapshot'])==r['sha256'],'local_intermediate_backup_changed')
  return data
 root.mkdir(exist_ok=False);source=D/'CURRENT.md';target=root/'CURRENT.md';digest=copy_exact(source,target)
 data=dict(schema='first-control-initial-local-current-backup/v1',count=1,files=[dict(relative_path='CURRENT.md',original=str(source),snapshot=str(target),sha256=digest,bytes=source.stat().st_size)],remote_intermediate_not_available=True)
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
 write(D/'postrun/author_freeze_v1.json',{'schema':'causal-cold-start-author-freeze/v1','count':len(rows),'bytes':sum(r['bytes'] for r in rows),'files':rows,'directories':directories,'all_sources_runs_failed_attempts_and_raw_Storage_preserved':True})
 print(json.dumps({'author_files_frozen':len(rows),'author_bytes':sum(r['bytes'] for r in rows)}))

def qa():
 initial_path=D/'preflight/workspace_initial_local_v1.json';final_path=D/'preflight/workspace_final_local_v1.json';initial=load(initial_path);final=load(final_path)
 for result in [initial,final]:
  p=result['protection'];require(result['passed'] and p['full_local_current_byte_sha_recheck'] and p['MPC_mirror_current_bytes_verified'] is False,'local_scope_remote_deferred');require(p['unique_raw_files_reread']==35673 and p['logical_bytes_streamed']==4097643431 and p['local_D25_archive_files']==420,'complete_local_old_asset_scope')
 spec=importlib.util.spec_from_file_location('close_workspace26',D/'protection_local_v1.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);current=helper.workspace();require(helper.projection(current)==helper.projection(final['workspace_after']),'workspace_changed_after_final_stream')
 frozen=load(D/'postrun/author_freeze_v1.json');original,dirs=population(N);snap,snapdirs=population(D/'author_snapshot');require(frozen['count']==len(original)==8 and dirs==snapdirs==frozen['directories'],'eight_author_files');require({str(p) for p in original}=={r['original'] for r in frozen['files']} and {str(p) for p in snap}=={r['snapshot'] for r in frozen['files']},'exact_source_snapshot')
 for row in frozen['files']:require(sha(row['original'])==row['sha256']==sha(row['snapshot']),'author_byte_identity')
 build=load(D/'build/replay_attempt01/result.json');audit=load(D/'postrun/causal_cold_audit_v1.json');inv=load(D/'replay/offline_invocation_v1.json');lock=load(D/'preregister/offline_invocation_lock_v1.json');pre=load(D/'preregister/causal_cold_v1.json')
 require(build['passed'] and build['native_tests']==dict(tests=3,failures=0,errors=0,disabled=0),'three_prerequisite_native_checks');require(audit['passed'] and audit['candidate_component_gates_passed'] and audit['all_five_recorded_calls_independently_checked'] and audit['candidate_RTI_calls']==4 and audit['separate_restoration_probe_calls']==1 and audit['durable_journal_records']==9,'causal_candidate_and_separate_probe_scope')
 require(len(audit['negative_audit_boundaries'])==5 and all(r['rejected'] for r in audit['negative_audit_boundaries']),'independent_boundary_checks');require(audit['exact_one_final_warm_shift_verified'] and audit['withdrawal_preserves_warm_exactly'] and audit['actual_original_first_bounds_restored'],'one_shift_and_actual_bounds_restore')
 require(audit['native_file_open_trace']['validation_or_benchmark_open_attempts']==0 and audit['native_file_open_trace']['runtime_input_open_count']==3,'actual_no_oracle_file_opens');require(audit['refined_benchmark_errors']['X']<=pre['benchmark_final_X_U_abs_error'] and audit['refined_benchmark_errors']['U']<=pre['benchmark_final_X_U_abs_error'] and audit['refined_benchmark_errors']['feasible_cost']<=pre['benchmark_final_cost_abs_error'],'diagnostic_benchmark_component_gate')
 require(inv['passed'] and inv['input_closure_unchanged'] and inv['lock_sha256']==sha(D/'preregister/offline_invocation_lock_v1.json'),'pre_post_closure')
 for path,h in lock['files'].items():require(sha(path)==h,'selected_closure_changed:'+path)
 for path,target in lock['aliases'].items():require(str(Path(path).resolve(strict=True))==target,'selected_alias_changed:'+path)
 require(audit['input_sha256_before']==audit['input_sha256_after'],'audit_read_only')
 for path,h in audit['input_sha256_after'].items():require(sha(path)==h,'audit_input_changed:'+path)
 require(load(D/'preflight/strace_capability_v1.json')['passed'] is False and load(D/'preflight/strace_capability_host_v1.json')['passed'] is True,'sandbox_restriction_and_host_scope_recorded')
 require((D/'documents/方案A_因果冷启动候选_结果与下一步_2026-10-18.md').is_file() and (D/'documents/next_owned_worker_integration_plan_v1.md').is_file(),'result_and_next_plan')
 fixed={str(p):dict(sha256=sha(p),bytes=p.stat().st_size) for p in files(D)}
 q=dict(schema='causal-cold-start-local-QA/v1',passed=True,passed_semantics='local archive integrity and offline causal-candidate component validation only; no live Worker, closed-loop or remote-mirror qualification',archive_integrity_passed=True,offline_mechanism_complete=True,candidate_component_gates_passed=True,candidate_RTI_calls=4,separate_restoration_probe_RTI_calls=1,original_RMSE_failure_preserved=True,new_closed_loop_run=False,new_closed_loop_performance_qualified=False,legacy_actual_jobs=102,native_GTest_cases=3,negative_audit_boundaries=5,durable_journal_records=9,actual_oracle_open_attempts=0,mode_and_warm_restore_verified=True,author_frozen_files=8,author_freeze_sha256=sha(D/'postrun/author_freeze_v1.json'),local_old_asset_paths=35673,local_old_asset_bytes=4097643431,remote_MPC_mirrors_currently_verified=False,remote_MPC_expected_paths_deferred=len(final['protection']['remote_mirror_expectations_preserved_not_read']),MPC_delivery_verified_at_QA=False,MPC_destination_preparation_passed=load(D/'preflight/MPC_delivery_preparation_v1.json')['passed'],delivery_status_authority='delivery_verification.json if exact copy/readback later succeed',batch_status='offline_candidate_component_passed_MPC_delivery_pending',blocked_research_gate='parent_s005_RMSE',initial_local_protection_sha256=sha(initial_path),final_local_protection_sha256=sha(final_path),preregistration_sha256=sha(D/'preregister/causal_cold_v1.json'),native_result_sha256=sha(D/'replay/native_causal_cold_v1.json'),independent_audit_sha256=sha(D/'postrun/causal_cold_audit_v1.json'),candidate_metrics={k:audit[k] for k in ['candidate_feasible_cost','candidate_cost_reduction_fraction','candidate_surge_at_dt_m_s','surge_relative_gain','candidate_cost_premium_over_refined_free_fraction','refined_benchmark_errors','native_file_open_trace']},fixed_files=fixed,fixed_file_count=len(fixed),business_diff_sha256=current['business_diff_sha256'],original_real_launch_exception=final['protection']['explicit_live_original_path_exceptions'],stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False)
 write(D/'postrun/final_QA_v1.json',q);print(json.dumps({k:q[k] for k in ['archive_integrity_passed','candidate_component_gates_passed','MPC_delivery_verified_at_QA','fixed_file_count','batch_status']}))

def verify_fixed(q):
 for p,r in q['fixed_files'].items():require(sha(p)==r['sha256'] and Path(p).stat().st_size==r['bytes'],'fixed_local_QA_changed:'+p)

def verify_local_inventory():
 inv=load(D/'archive_inventory_v1.json');q=load(D/'postrun/final_QA_v1.json');verify_fixed(q)
 expected={r['relative_path'] for r in inv['files']}|{'archive_inventory_v1.json'}
 if (D/'delivery_verification.json').exists():expected.add('delivery_verification.json')
 population_now,dirs=population(D);require({str(p.relative_to(D)) for p in population_now}==expected and dirs==inv['directories'],'sealed_local_population')
 for row in inv['files']:require(sha(D/row['relative_path'])==row['sha256'] and (D/row['relative_path']).stat().st_size==row['bytes'],'sealed_local_byte_identity')
 return inv,q

def seal():
 q=load(D/'postrun/final_QA_v1.json');require(q['archive_integrity_passed'],'local_QA');verify_fixed(q)
 current,dirs=population(D);expected=set(q['fixed_files'])|{str(D/'postrun/final_QA_v1.json')}
 require({str(p) for p in current}==expected,'no_unreviewed_local_files')
 inv=dict(schema='causal-cold-start-archive-inventory/v1',files=[dict(relative_path=str(p.relative_to(D)),sha256=sha(p),bytes=p.stat().st_size) for p in current],directories=dirs,metadata_rule='inventory excludes itself and optional later successful delivery receipt; pending network state is not delivery',offline_mechanism_complete=True,MPC_delivery_verified_when_inventory_sealed=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 write(D/'archive_inventory_v1.json',inv);verify_local_inventory();print(json.dumps(dict(local_archive_sealed=True,local_regular_files=len(current)+1,bytes=sum(r['bytes'] for r in inv['files']),MPC_delivery_complete=False,inventory_sha256=sha(D/'archive_inventory_v1.json'))))

def deliver():
 inv,q=verify_local_inventory();receiptpath=D/'delivery_verification.json';M.mkdir(exist_ok=True)
 current,_=population(M);data_expected={r['relative_path'] for r in inv['files']}|{'archive_inventory_v1.json'}
 allowed=data_expected|{'delivery_verification.json'};require({str(p.relative_to(M)) for p in current}<=allowed,'unexpected_destination_file')
 for directory in inv['directories']:(M/directory).mkdir(parents=True,exist_ok=True)
 for rel in sorted(data_expected):
  src=D/rel;dst=M/rel
  if dst.exists():require(sha(src)==sha(dst),'existing_destination_differs:'+rel)
  else:copy_exact(src,dst)
 for rel in data_expected:require(sha(D/rel)==sha(M/rel),'complete_remote_readback:'+rel)
 receipt=dict(schema='causal-cold-start-MPC-delivery/v1',passed=True,source=str(D),destination=str(M),archive_inventory_sha256=sha(D/'archive_inventory_v1.json'),final_QA_sha256=sha(D/'postrun/final_QA_v1.json'),author_freeze_sha256=sha(D/'postrun/author_freeze_v1.json'),full_byte_readback=True,full_second_SHA_readback=True,complete_population_equal=True,final_regular_files_per_root=len(inv['files'])+2,current_batch_MPC_delivery_complete=True,historical_MPC_mirrors_revalidated=False,offline_mechanism_complete=True,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 if receiptpath.exists():require(load(receiptpath)==receipt,'existing_delivery_receipt_changed')
 else:write(receiptpath,receipt)
 if (M/receiptpath.name).exists():require(sha(M/receiptpath.name)==sha(receiptpath),'remote_receipt_differs')
 else:copy_exact(receiptpath,M/receiptpath.name)
 local,dirs=population(D);remote,remote_dirs=population(M);require({str(p.relative_to(D)) for p in local}=={str(p.relative_to(M)) for p in remote} and dirs==remote_dirs,'final_exact_population')
 for path in local:require(sha(path)==sha(M/path.relative_to(D)),'final_metadata_inclusive_readback')
 print(json.dumps(dict(passed=True,files=len(local),destination=str(M),receipt_sha256=sha(receiptpath))))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['freeze','qa','seal','verify','deliver']);a=parser.parse_args()
 try:{'freeze':freeze,'qa':qa,'seal':seal,'verify':verify_local_inventory,'deliver':deliver}[a.mode]()
 except (OSError,RuntimeError) as error:
  print(json.dumps(dict(passed=False,operation=a.mode,error=str(error),error_number=getattr(error,'errno',None),local_archive_preserved=True,MPC_delivery_complete=False),ensure_ascii=False));raise SystemExit(2)

