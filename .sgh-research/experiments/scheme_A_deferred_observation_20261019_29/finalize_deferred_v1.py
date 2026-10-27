#!/usr/bin/env python3
"""Seal the owned cold-start implementation and failed localhost case and separately append exact MPC delivery.

Local QA does not verify unavailable historical network mirrors. Inventory
includes QA and all retained failures, excludes itself and any later successful
delivery receipt. Network copy refuses any different existing destination file.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,stat,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_deferred_observation_20261019_v29'
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
 data=dict(schema='deferred-initial-local-current-backup/v1',count=1,files=[dict(relative_path='CURRENT.md',original=str(source),snapshot=str(target),sha256=digest,bytes=source.stat().st_size)],remote_intermediate_not_available=True)
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
 write(D/'postrun/author_freeze_v1.json',{'schema':'deferred-observation-author-freeze/v1','count':len(rows),'bytes':sum(r['bytes'] for r in rows),'files':rows,'directories':directories,'all_sources_runs_failed_attempts_and_raw_Storage_preserved':True})
 print(json.dumps({'author_files_frozen':len(rows),'author_bytes':sum(r['bytes'] for r in rows)}))

def qa():
 initial_path=D/'preflight/workspace_initial_local_v1.json';final_path=D/'preflight/workspace_final_local_v1.json';initial,final=load(initial_path),load(final_path)
 for result in [initial,final]:
  p=result['protection'];require(result['passed'] and p['full_local_current_byte_sha_recheck'] and p['MPC_mirror_current_bytes_verified'] is False,'local_old_asset_protection_only')
  require(p['unique_raw_files_reread']==39875 and p['logical_bytes_streamed']==4790609888 and p['local_D28_archive_files']==1765,'complete_old_local_scope')
 spec=importlib.util.spec_from_file_location('close_workspace29',D/'protection_local_v1.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);current=helper.workspace()
 require(helper.projection(current)==helper.projection(final['workspace_after']),'old_workspace_projection_changed')
 frozen=load(D/'postrun/author_freeze_v1.json');original,dirs=population(N);snap,snapdirs=population(D/'author_snapshot')
 require(frozen['count']==len(original)==len(snap) and dirs==snapdirs==frozen['directories'],'full_author_snapshot_population')
 require({str(p) for p in original}=={r['original'] for r in frozen['files']} and {str(p) for p in snap}=={r['snapshot'] for r in frozen['files']},'exact_author_paths')
 for r in frozen['files']:require(sha(r['original'])==r['sha256']==sha(r['snapshot']) and Path(r['original']).stat().st_size==r['bytes'],'author_byte_identity')
 pre=load(D/'preregister/deferred_v1.json')
 for p,r in pre['helper_files'].items():require(sha(p)==r['sha256']==sha(r['snapshot']),'prerun_helper_changed:'+p)
 spec=importlib.util.spec_from_file_location('close_assets29',D/'verify_and_run_deferred_v1.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
 require(driver.assets()==pre['asset_sha256'] and driver.verify_consumers(N,D/'verify_and_run_deferred_v1.py')['passed'],'actual_selected_assets_and_contract_consumers')
 require(sha(N/'pair_wakeup_contract_v1.json')=='89caaaf36783463a1e1d789bda41f7f90dc398981ddb4b3b8cd6037114333f72','exact_unchanged_C10_contract')
 root=D/'build/deferred_observer_attempt01';b=load(root/'result.json')
 require(b['passed'] and b['source_content_unchanged'] and b['parent_source_content_unchanged'] and b['compiled_source_bundle_pin_verified'],'new_Observer_build')
 require(b['finite_native']['GTest_cases']==44 and b['finite_native']['plain_checks']==346 and b['finite_native']['all_declared_native_targets_exercised'],'all_Observer_native_targets')
 require(sha(b['binary'])==b['binary_sha256'] and b['source_bundle']['sha256'].encode() in Path(b['binary']).read_bytes(),'new_Observer_binary_bundle')
 deps={}
 def pin(r):
  p=r['path'];require(str(Path(p).resolve(strict=True))==r.get('resolved_path',str(Path(p).resolve(strict=True))),'dependency_alias_changed:'+p)
  if p not in deps:deps[p]=dict(sha256=sha(p),bytes=Path(p).stat().st_size)
  require(deps[p]['sha256']==r['sha256'] and deps[p]['bytes']==r['bytes'],'dependency_changed:'+p)
 for leaf in ['compiler_dependency_pins.json','runtime_library_pins.json']:
  m=load(root/leaf)
  for r in m['files'].values():pin(r)
  if 'compiler' in m:
   pin(m['compiler']);pin(m['compile_commands'])
   for r in m['compiler_dependency_files'].values():pin(r)
 for r in b['finite_native']['GTest_XML']:require(sha(r['path'])==r['sha256'] and not any(r[k] for k in ['failures','errors','disabled']),'exact_successful_GTest_XML')
 worker=next(x for x in load(N/'build_manifest_current.json') if x['role']=='worker');reuse=load(D/'component/unchanged_worker_and_contract_v1.json')
 require(worker['binary_sha256']==reuse['worker_binary_sha256']=='1462e6be4ffec0079319cb6fb1aed8c3067df1065e9d167351092cd586e595f1' and worker['finite_native']==reuse['worker_native_evidence_reused_not_rerun'],'Worker_exact_reuse_not_new_tests')
 py=load(D/'component/checker_finite_v1.json');require(py['passed'] and py['count']==84 and sha(D/'component/checker_finite_v1.log')==py['log_sha256'],'84_Python_checks')
 R=N/'runs/deferred_s005_01';report=load(D/'runs/s005_01/check_result.json');run=load(R/'result.json');audit=load(D/'postrun/deferred_result_audit_v1.json')
 require(report['passed'] is False and len(report['issues'])==1 and report['issues'][0]['code']=='projected_preregistered_whole_measurement_RMSE_halved_parent','original_sole_RMSE_NoGo')
 require(run['passed'] and run['cleanup_complete'] and run['finite_prepare_and_measurement_passed'] and len(run['owned_role_returncodes'])==5 and all(v==0 for v in run['owned_role_returncodes'].values()),'actual_five_roles_closed_cleanly')
 for r in run['live_parameter_queries'].values():require(r['complete_name_set'] and r['mutation_rejected'] and r['typed_values_equal_expected'],'actual_effective_parameter_authentication')
 require(audit['passed'] and audit['actual_case_passed'] is False and audit['actual_acceptance_component_observed'] and audit['original_report_not_rewritten'],'audit_scope')
 require(audit['accepted']==audit['measurement_attempts']==audit['consecutive_accepted']==101 and audit['measurement_candidate_refusals']==0 and audit['first_050_command_applied'],'actual_acceptance_and_first_command')
 require(audit['actual_live_revalidations']==0 and audit['actual_live_older_point_selections']==0 and audit['unhit_live_branches_not_claimed_as_coverage'],'no_unhit_branch_qualification')
 require(audit['performance']['measured_surge_RMSE_m_s']==0.009195365993999232 and audit['performance']['RMSE_passed'] is False,'original_performance_failure')
 require(audit['error_budget']['prefixes'][1]['fraction_of_original_full_allowance']>1 and audit['error_budget']['no_tail_only_change_can_rescue_this_observed_prefix'],'observed_startup_error_budget')
 for path in [D/'postrun/deferred_result_audit_v1.json',D/'postrun/performance_gate_lineage_v1.json',D/'preflight/parent_prefix_error_budget_v1.json']:
  a=load(path);require(a['passed'] and a['input_sha256_before']==a['input_sha256_after'],'read_only_audit_scope')
  for p,h in a['input_sha256_after'].items():require(sha(p)==h,'audit_input_changed:'+p)
 for name in ['方案A_延后观测_连续接纳恢复与性能边界_2026-10-19.md','next_P1_scope_and_protocol_plan_v1.md']:require((D/'documents'/name).is_file(),'report_and_next_scope_plan')
 status=load(D/'batch_status_final.json');require(status['actual_case_passed'] is False and status['acceptance_component_observed'] and status['stage_qualified'] is False,'status_boundaries')
 fixed={str(p):dict(sha256=sha(p),bytes=p.stat().st_size) for p in files(D)}
 q=dict(schema='deferred-observation-local-QA/v1',passed=True,passed_semantics='archive integrity and exact component/current-input verification; actual acceptance observed, original performance case NoGo',archive_integrity_passed=True,component_validation_complete=True,new_Observer_GTest=44,new_Observer_plain_checks=346,Worker_native_evidence_reused_not_rerun=worker['finite_native'],Python_finite_cases=84,new_Observer_binary_sha256=b['binary_sha256'],compiler_dependency_files_verified=len(deps),actual_case_passed=False,acceptance_component_observed=True,actual_measurement_candidates=101,accepted_candidates=101,consecutive_accepted=101,measurement_candidate_refusals=0,first_050_command_applied=True,all_five_roles_cleanly_closed=True,original_only_failure=report['issues'],live_retry_and_older_point_branches_not_hit=True,performance=report['performance'],observed_prefix_error_budget=audit['error_budget'],author_frozen_files=frozen['count'],author_freeze_sha256=sha(D/'postrun/author_freeze_v1.json'),local_old_asset_paths=39875,local_old_asset_bytes=4790609888,historical_MPC_mirrors_currently_verified=False,remote_MPC_expected_paths_deferred=len(final['protection']['remote_mirror_expectations_preserved_not_read']),MPC_delivery_verified_at_QA=False,MPC_destination_preparation_passed=load(D/'preflight/MPC_delivery_preparation_v1.json')['passed'],delivery_status_authority='delivery_verification.json only after exact copy and readback succeed',batch_status='101_of_101_actual_acceptance_recovered_original_RMSE_NoGo_stop_startup_tuning',initial_local_protection_sha256=sha(initial_path),final_local_protection_sha256=sha(final_path),preregistration_sha256=sha(D/'preregister/deferred_v1.json'),original_case_report_sha256=sha(D/'runs/s005_01/check_result.json'),postrun_audit_sha256=sha(D/'postrun/deferred_result_audit_v1.json'),fixed_files=fixed,fixed_file_count=len(fixed),business_diff_sha256=current['business_diff_sha256'],original_real_launch_exception=final['protection']['explicit_live_original_path_exceptions'],stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False)
 write(D/'postrun/final_QA_v1.json',q);print(json.dumps({k:q[k] for k in ['archive_integrity_passed','actual_case_passed','acceptance_component_observed','accepted_candidates','fixed_file_count','batch_status']}))

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
 inv=dict(schema='deferred-observation-archive-inventory/v1',files=[dict(relative_path=str(p.relative_to(D)),sha256=sha(p),bytes=p.stat().st_size) for p in current],directories=dirs,metadata_rule='inventory excludes itself and optional later successful delivery receipt; pending network state is not delivery',component_validation_complete=True,actual_case_passed=False,MPC_delivery_verified_when_inventory_sealed=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
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
 receipt=dict(schema='deferred-observation-MPC-delivery/v1',passed=True,source=str(D),destination=str(M),archive_inventory_sha256=sha(D/'archive_inventory_v1.json'),final_QA_sha256=sha(D/'postrun/final_QA_v1.json'),author_freeze_sha256=sha(D/'postrun/author_freeze_v1.json'),full_byte_readback=True,full_second_SHA_readback=True,complete_population_equal=True,final_regular_files_per_root=len(inv['files'])+2,current_batch_MPC_delivery_complete=True,historical_MPC_mirrors_revalidated=False,component_validation_complete=True,actual_case_passed=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
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

