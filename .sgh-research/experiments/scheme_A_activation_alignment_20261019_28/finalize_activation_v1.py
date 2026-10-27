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
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_activation_alignment_20261019_v28'
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
 data=dict(schema='activation-initial-local-current-backup/v1',count=1,files=[dict(relative_path='CURRENT.md',original=str(source),snapshot=str(target),sha256=digest,bytes=source.stat().st_size)],remote_intermediate_not_available=True)
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
 write(D/'postrun/author_freeze_v1.json',{'schema':'activation-alignment-author-freeze/v1','count':len(rows),'bytes':sum(r['bytes'] for r in rows),'files':rows,'directories':directories,'all_sources_runs_failed_attempts_and_raw_Storage_preserved':True})
 print(json.dumps({'author_files_frozen':len(rows),'author_bytes':sum(r['bytes'] for r in rows)}))

def qa():
 initial_path=D/'preflight/workspace_initial_local_v1.json';final_path=D/'preflight/workspace_final_local_v1.json';initial,final=load(initial_path),load(final_path)
 for result in [initial,final]:
  p=result['protection'];require(result['passed'] and p['full_local_current_byte_sha_recheck'] and p['MPC_mirror_current_bytes_verified'] is False,'local_protection_remote_deferred')
  require(p['unique_raw_files_reread']==37785 and p['logical_bytes_streamed']==4429713589 and p['local_D27_archive_files']==1558,'complete_historical_local_scope')
 spec=importlib.util.spec_from_file_location('close_workspace28',D/'protection_local_v1.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);current=helper.workspace()
 require(helper.projection(current)==helper.projection(final['workspace_after']),'workspace_changed_after_final_stream')
 frozen=load(D/'postrun/author_freeze_v1.json');original,dirs=population(N);snap,snapdirs=population(D/'author_snapshot')
 require(frozen['count']==len(original)==len(snap) and dirs==snapdirs==frozen['directories'],'complete_source_run_snapshot_population')
 require({str(p) for p in original}=={r['original'] for r in frozen['files']} and {str(p) for p in snap}=={r['snapshot'] for r in frozen['files']},'exact_author_paths')
 for r in frozen['files']:require(sha(r['original'])==r['sha256']==sha(r['snapshot']) and Path(r['original']).stat().st_size==r['bytes'],'author_byte_identity')
 pre=load(D/'preregister/activation_v1.json')
 for p,r in pre['helper_files'].items():require(sha(p)==r['sha256']==sha(r['snapshot']),'frozen_prerun_helper_changed:'+p)
 spec=importlib.util.spec_from_file_location('close_assets28',D/'verify_and_run_activation_v1.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver);require(driver.assets()==pre['asset_sha256'],'five_role_selected_assets_exact')
 observed={}
 def pin(r):
  p=r['path'];require(str(Path(p).resolve(strict=True))==r.get('resolved_path',str(Path(p).resolve(strict=True))),'dependency_alias_changed:'+p)
  if p not in observed:observed[p]=dict(sha256=sha(p),bytes=Path(p).stat().st_size)
  require(observed[p]['sha256']==r['sha256'] and observed[p]['bytes']==r['bytes'],'dependency_changed:'+p)
 components={}
 for role,gtests,plain in [('worker',9,103),('observer',39,346)]:
  root=D/('build/activation_'+role+'_attempt02');b=load(root/'result.json')
  require(b['passed'] and b['source_content_unchanged'] and b['compiled_source_bundle_pin_verified'],'current_role_build_passed')
  require(b['finite_native']['GTest_cases']==gtests and b['finite_native']['plain_checks']==plain and b['finite_native']['all_declared_native_targets_exercised'],'all_declared_components_exercised')
  require(sha(b['binary'])==b['binary_sha256'] and b['source_bundle']['sha256'].encode() in Path(b['binary']).read_bytes(),'binary_embedded_source_bundle_identity')
  for leaf in ['compiler_dependency_pins.json','runtime_library_pins.json']:
   m=load(root/leaf)
   for r in m['files'].values():pin(r)
   if 'compiler' in m:
    pin(m['compiler']);pin(m['compile_commands'])
    for r in m['compiler_dependency_files'].values():pin(r)
  for r in b['finite_native']['GTest_XML']:require(sha(r['path'])==r['sha256'] and not any(r[k] for k in ['failures','errors','disabled']),'GTest_XML_exact_and_successful')
  components[role]=dict(GTest_cases=gtests,plain_checks=plain,binary_sha256=b['binary_sha256'],compiler_dependencies=b['actual_compiler_dependencies'],loader_libraries=b['actual_loader_libraries'])
 py=load(D/'component/checker_finite_v1.json');require(py['passed'] and py['count']==76 and sha(D/'component/checker_finite_v1.log')==py['log_sha256'],'76_python_finite_checks')
 offline=load(D/'offline/parent_causal_feasibility_v1.json');require(offline['passed'] and offline['activation_prefixes']==100 and offline['older_raw_odom_selected']==7 and len(offline['negative_boundaries'])==6,'offline_causal_scope')
 for p,h in offline['input_sha256_after'].items():require(sha(p)==h,'offline_input_changed:'+p)
 require(offline['input_sha256_before']==offline['input_sha256_after'],'offline_read_only')
 R=N/'runs/activation_s005_01';report=load(D/'runs/s005_01/check_result.json');run=load(R/'result.json');audit=load(D/'postrun/activation_result_audit_v1.json')
 require(report['passed'] is False and len(report['issues'])==3 and audit['original_issues']==report['issues'],'original_three_issue_NoGo_preserved')
 require(run['passed'] and run['cleanup_complete'] and run['finite_prepare_and_measurement_passed'] and len(run['owned_role_returncodes'])==5 and all(v==0 for v in run['owned_role_returncodes'].values()),'real_five_role_case_completed_and_clean')
 for r in run['live_parameter_queries'].values():require(r['complete_name_set'] and r['mutation_rejected'] and r['typed_values_equal_expected'],'actual_effective_config_authenticated')
 require(audit['passed'] and audit['actual_case_passed'] is False and audit['original_report_not_rewritten'],'audit_not_experiment_qualification')
 require(audit['first_050_command_applied'] and audit['first_050_command_accepted'] and audit['actual_window_revalidations']==41 and audit['actual_window_rescued_revalidations']==31 and audit['rejection_counts']=={'activation_input_changed_during_validation':10},'actual_applied_progress_and_remaining_races')
 require(report['window']['accepted']==90 and report['window']['attempts']==100 and report['window']['consecutive_accepted']==18 and report['performance']['measured_surge_RMSE_m_s']==0.010475244990036596,'unchanged_failed_original_window')
 require(audit['contract_identity_bookkeeping']['strict_current_contract_validated'] and audit['no_negative_horizon_or_causal_selection_refusal'],'contract_bookkeeping_separate_from_actual_guard_failures')
 for p,h in audit['input_sha256_after'].items():require(sha(p)==h,'postrun_input_changed:'+p)
 require(audit['input_sha256_before']==audit['input_sha256_after'],'postrun_read_only')
 for role in ['worker','observer']:require(load(D/('build/activation_'+role+'_attempt01/result.json'))['passed'] is False,'initial_failed_build_preserved')
 for name in ['方案A_激活时刻对齐_实际结果与拒绝复盘_2026-10-19.md','next_deferred_observation_plan_v1.md']:require((D/'documents'/name).is_file(),'result_and_next_plan')
 status=load(D/'batch_status_final.json');require(status['actual_case_passed'] is False and status['first_050_command_applied'] and status['stage_qualified'] is False,'status_qualification_boundary')
 fixed={str(p):dict(sha256=sha(p),bytes=p.stat().st_size) for p in files(D)}
 q=dict(schema='activation-alignment-local-QA/v1',passed=True,passed_semantics='archive integrity, exact build/input preservation and component verification; real s005 remains NoGo',archive_integrity_passed=True,component_validation_complete=True,components=components,python_finite_cases=76,actual_case_passed=False,actual_five_roles_clean_exit=True,first_050_command_accepted=True,first_050_command_applied=True,accepted_candidates=90,measurement_attempts=100,maximum_consecutive_accepts=18,actual_revalidations=41,rescued_revalidations=31,rejection_counts=audit['rejection_counts'],negative_horizon_refusals=0,performance=report['performance'],original_checker_issues=report['issues'],checker_identity_constant_gap_preserved_and_independently_classified=True,author_frozen_files=frozen['count'],author_freeze_sha256=sha(D/'postrun/author_freeze_v1.json'),local_old_asset_paths=37785,local_old_asset_bytes=4429713589,current_unique_build_dependency_files_verified=len(observed),historical_MPC_mirrors_currently_verified=False,remote_MPC_expected_paths_deferred=len(final['protection']['remote_mirror_expectations_preserved_not_read']),MPC_delivery_verified_at_QA=False,MPC_destination_preparation_passed=load(D/'preflight/MPC_delivery_preparation_v1.json')['passed'],delivery_status_authority='delivery_verification.json only if exact copy and readback later succeed',batch_status='causal_selection_and_first050_Applied_proven_remaining_double_races_and_RMSE_NoGo',initial_local_protection_sha256=sha(initial_path),final_local_protection_sha256=sha(final_path),preregistration_sha256=sha(D/'preregister/activation_v1.json'),original_case_report_sha256=sha(D/'runs/s005_01/check_result.json'),postrun_audit_sha256=sha(D/'postrun/activation_result_audit_v1.json'),fixed_files=fixed,fixed_file_count=len(fixed),business_diff_sha256=current['business_diff_sha256'],original_real_launch_exception=final['protection']['explicit_live_original_path_exceptions'],stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False)
 write(D/'postrun/final_QA_v1.json',q);print(json.dumps({k:q[k] for k in ['archive_integrity_passed','component_validation_complete','actual_case_passed','first_050_command_applied','fixed_file_count','batch_status']}))

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
 inv=dict(schema='activation-alignment-archive-inventory/v1',files=[dict(relative_path=str(p.relative_to(D)),sha256=sha(p),bytes=p.stat().st_size) for p in current],directories=dirs,metadata_rule='inventory excludes itself and optional later successful delivery receipt; pending network state is not delivery',component_validation_complete=True,actual_case_passed=False,MPC_delivery_verified_when_inventory_sealed=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
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
 receipt=dict(schema='activation-alignment-MPC-delivery/v1',passed=True,source=str(D),destination=str(M),archive_inventory_sha256=sha(D/'archive_inventory_v1.json'),final_QA_sha256=sha(D/'postrun/final_QA_v1.json'),author_freeze_sha256=sha(D/'postrun/author_freeze_v1.json'),full_byte_readback=True,full_second_SHA_readback=True,complete_population_equal=True,final_regular_files_per_root=len(inv['files'])+2,current_batch_MPC_delivery_complete=True,historical_MPC_mirrors_revalidated=False,component_validation_complete=True,actual_case_passed=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
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

