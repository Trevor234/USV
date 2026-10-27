#!/usr/bin/env python3
"""Create-only author freeze, honest complete/partial QA, exact MPC delivery.

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
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_pair_wakeup_20261018_v22'
M=Path('/home/trevor/MPC')/D.name
ORDER=('s005','s010','s030','s060')
METADATA={'archive_inventory_v1.json','delivery_verification.json'}
INTERMEDIATE={'CURRENT.md','preflight/preflight_reflection_pair_wakeup_v1.md','protection_v1.py'}

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
 data={'schema':'reference-pair-wakeup-intermediate-MPC-backup/v1','files':rows,'count':len(rows),'all_three_intermediate_files_preserved':True}
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
 write(D/'postrun/author_freeze_v1.json',{'schema':'reference-pair-wakeup-author-freeze/v1','count':len(rows),'bytes':sum(r['bytes'] for r in rows),'files':rows,'directories':directories,'all_sources_runs_failed_attempts_and_raw_Storage_preserved':True})
 print(json.dumps({'author_files_frozen':len(rows),'author_bytes':sum(r['bytes'] for r in rows)}))

# Dependencies/loader pins may intentionally name an old symlink alias. Resolve
# that alias, prove inode identity, and hash the regular target; never forbid the
# old alias merely because it is a link, and never manufacture a prebuild pin.
HASH_CACHE={}
def verify_pin(row):
 path=Path(row['path']);resolved=path.resolve(strict=True);before=resolved.stat()
 require(stat.S_ISREG(before.st_mode),'dependency_regular_target:'+str(path))
 signature=(str(resolved),before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
 digest=HASH_CACHE.get(signature)
 if digest is None:digest=sha(resolved);HASH_CACHE[signature]=digest
 require(path.resolve(strict=True)==resolved and os.path.samefile(path,resolved),'dependency_alias_changed:'+str(path))
 after=resolved.stat();require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'dependency_changed:'+str(path))
 require(digest==row['sha256'] and ('bytes' not in row or before.st_size==row['bytes']),'dependency_digest:'+str(path))
 if row.get('resolved_path'):
  declared=Path(row['resolved_path']).resolve(strict=True);require(os.path.samefile(declared,resolved),'declared_resolution_differs:'+str(path))
 return {'path':str(path),'resolved_path':str(resolved),'sha256':digest,'bytes':before.st_size,'alias_present':str(path)!=str(resolved)}
def selected_builds(registry):
 selected={}
 for b in registry:
  role=b['role'];require(b['passed'] is True,'unpassed_selected_build:'+role);runtime=verify_pin({'path':b['binary'],'sha256':b['binary_sha256']})
  for row in b.get('native_binaries',{}).values():verify_pin(row)
  for row in b.get('produced_target_pins',{}).values():verify_pin(row)
  out=b.get('output_directory');evidence={'runtime':runtime,'source_bundle':b['source_bundle'],'reused_from_parent':role not in ('worker','observer'),'compiler_and_loader_manifests':{}}
  if out:
   out=Path(out);record=out/'result.json';require(load(record)==b,'selected_build_registry_result_differs:'+role)
   evidence['result_path']=str(record);evidence['result_sha256']=sha(record)
   for name in ['compiler_dependency_pins.json','runtime_library_pins.json']:
    path=out/name;data=load(path);pins=list(data['files'].values());resolved=[verify_pin(r) for r in pins]
    # Also verify the compiler, compile recipe and actual .o.d artifacts when
    # the producer recorded them outside its flattened `files` population.
    for key in ['compiler','compile_commands']:
     if isinstance(data.get(key),dict) and 'path' in data[key]:verify_pin(data[key])
    for r in data.get('compiler_dependency_files',{}).values():verify_pin(r)
    evidence['compiler_and_loader_manifests'][name]={'path':str(path),'sha256':sha(path),'verified_files':len(pins),'resolved_aliases':[r for r in resolved if r['alias_present']]}
   for x in b.get('finite_native',{}).get('GTest_XML',[]):verify_pin(x)
   evidence['finite_native']=b.get('finite_native')
  else:
   require(role=='recorder','missing_selected_build_dependency_record:'+role)
   evidence['recorded_dependency_scope']='Recorder source/binary are reused from sealed N10; no new recorder compilation/dependency observation claimed. Historical dependency lineage remains in the full parent protection proof.'
  leaf=load(b['source_bundle']['path']).get('static_link_inputs_before')
  if leaf:
   require(sha(leaf['path'])==leaf['sha256'],'selected_static_leaf_bundle_pin:'+role);before=load(leaf['path'])
   require(before['captured_after_configure_before_any_build'] is True,'static_pins_before_build')
   for row in before['files'].values():verify_pin(row);verify_pin(row['snapshot'])
   for row in before['link_command_files'].values():verify_pin(row)
   after=load(Path(leaf['path']).parent/'static_link_inputs_after.json');require(after['passed'] is True and after['same_before_after'] is True and after['before_sha256']==leaf['sha256'],'selected_static_link_unchanged')
   for key in ['generated_vendor_sources_before_build','generated_archive_tools_before_build']:
    for row in before.get(key,{}).values():verify_pin(row)
   for row in after.get('generated_archives_after_build',{}).values():verify_pin(row)
   evidence['generated_test_archives_after_build']=after.get('generated_archives_after_build',{})
   evidence['generated_vendor_source_count']=len(before.get('generated_vendor_sources_before_build',{}))
   evidence['static_link_inputs_before']=leaf
  selected[role]=evidence
 require(set(selected)=={'publisher','worker','observer','fixture','recorder'},'selected_role_population');return selected

def collect_cases(pre):
 cases={};blocked=None;ordered=True;previous_start=None
 for key in ORDER:
  out=D/'runs'/(key+'_01');report=out/'check_result.json';invocation=out/'invocation.json';entry={'status':'not_run','reference_speed_m_s':pre['cases'][key][0]}
  if out.exists():
   entry['directory']=str(out);entry['status']='incomplete'
   if blocked is not None:ordered=False
   if invocation.exists():
    inv=load(invocation);entry['invocation_sha256']=sha(invocation)
    require(inv['case']==key and inv['preregistration_sha256']==sha(D/'preregister/pair_wakeup_v1.json'),'case_preregistration_binding:'+key)
    require(inv['reference_speed_m_s']==entry['reference_speed_m_s'],'case_speed:'+key)
    run=Path(inv['run_dir']);require(run.is_relative_to(N/'runs'),'owned_run_root:'+key)
    if (run/'inputs.json').exists():
     inputs=load(run/'inputs.json');require(inputs['measurement_seconds']==20 and inputs['reference_speed_m_s']==entry['reference_speed_m_s'],'run_actual_scope:'+key)
    if (run/'result.json').exists():
     actual=load(run/'result.json');start=actual['prepare_start_ns'];entry['driver_passed']=actual.get('passed');entry['resource_cleanup_complete']=actual.get('resource_cleanup_complete',actual.get('cleanup_complete'))
     if previous_start is not None and start<=previous_start:ordered=False
     previous_start=start
   if report.exists():
    result=load(report);entry.update(status='passed' if result.get('passed') is True and not result.get('issues') and not result.get('reader_error') else 'failed',path=str(report),sha256=sha(report),window=result.get('window'),model=result.get('model'),performance=result.get('performance'),issues=result.get('issues'),reader_error=result.get('reader_error'))
    for source,digest in result.get('input_sha256_after',{}).items():require(sha(source)==digest,'raw_case_input_changed:'+source)
    if result.get('input_sha256_before') is not None:require(result['input_sha256_before']==result.get('input_sha256_after'),'case_read_only_proof:'+key)
    if entry['status']=='passed':require(entry.get('driver_passed') is True and entry.get('resource_cleanup_complete') is True,'passed_checker_with_failed_driver:'+key)
  if entry['status']!='passed' and blocked is None:blocked=key
  cases[key]=entry
 return cases,blocked,ordered

def qa():
 initial_path=D/'preflight/workspace_initial_v1.json';final_path=D/'preflight/workspace_final_v1.json';initial=load(initial_path);final=load(final_path)
 require(initial['passed'] is True and final['passed'] is True,'complete_old_asset_protection_required')
 for key in ['HEAD','branch','boot_id','business_diff_sha256','business_diff_bytes','business_tracked_count']:
  require(initial['protection'].get(key)==final['protection'].get(key),'protected_workspace_identity_changed:'+key)
 spec=importlib.util.spec_from_file_location('longitudinal_verify_readonly',D/'verify_and_run_pair_wakeup_v1.py');harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
 assets=harness.assets();pre_path=D/'preregister/pair_wakeup_v1.json';pre=load(pre_path);require(tuple(pre['order'])==ORDER and pre['measurement_seconds']==20,'longitudinal_preregistration_scope')
 for path,row in pre['helper_files'].items():require(sha(path)==row['sha256']==sha(row['snapshot']),'preregistered_helper_changed:'+path)
 require(assets==pre['asset_sha256'],'preregistered_selected_assets_changed')
 finite=load(D/'component/checker_finite_v1.json');require(finite['passed'] is True and finite['count']==57 and finite['log_sha256']==sha(D/'component/checker_finite_v1.log'),'finite_component_proof')
 selected=selected_builds(load(N/'build_manifest_current.json'));require(selected['fixture']['finite_native']['GTest_cases']==16,'actual_new_fixture_sixteen_native_cases')
 require(selected['worker']['result_path']==str(D/'build/pair_wakeup_worker_attempt01/result.json') and selected['observer']['result_path']==str(D/'build/pair_wakeup_observer_attempt04/result.json'),'new_projected_two_roles_selected')
 frozen=load(D/'postrun/author_freeze_v1.json');original,dirs=population(N);copied,copydirs=population(D/'author_snapshot')
 require({str(p) for p in original}=={r['original'] for r in frozen['files']} and dirs==frozen['directories'],'author_complete_current_population')
 require({str(p) for p in copied}=={r['snapshot'] for r in frozen['files']} and copydirs==dirs,'author_complete_snapshot_population')
 for row in frozen['files']:require(sha(row['original'])==row['sha256']==sha(row['snapshot']),'author_frozen_bytes_changed:'+row['original'])
 callback_build=load(D/'build/pair_wakeup_observer_attempt04/result.json')
 require(callback_build['finite_native']['GTest_cases']==19,'parent_counterexample_and_eighteen_current_source_callback_cases')
 comparison=load(D/'postrun/comparison_parent_v1.json');require(comparison['audit_passed'] is True and comparison['performance_gate_replaced'] is False,'read_only_parent_comparison_required')
 wire=load(D/'build/wire_component_attempt01/result.json');wire_audit=load(D/'postrun/wire_component_audit_v1.json');require(wire['passed'] is True and wire_audit['audit_passed'] is True,'separately_preregistered_actual_DDS_positive_retry_component')
 cases,blocked,ordered=collect_cases(pre);complete=blocked is None and ordered
 fixed={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files(D)}
 result={'schema':'reference-pair-wakeup-final-QA/v1','passed':True,'passed_semantics':'archive integrity only; actual ordered component outcomes remain separate','archive_integrity_passed':True,'cases_complete':complete,'all_planned_cases_passed':complete,'batch_status':'complete' if complete else 'blocked_gate' if any(v['status'] in ('failed','incomplete') for v in cases.values()) else 'partial','blocked_gate':blocked,'ordered_execution_valid':ordered,'cases':cases,'finite_checks':finite['count'],'selected_assets':assets,'selected_builds':selected,'fixed_files':fixed,'fixed_file_count':len(fixed),'author_frozen_files':frozen['count'],'author_freeze_sha256':sha(D/'postrun/author_freeze_v1.json'),'preregistration_sha256':sha(pre_path),'initial_protection_v1_sha256':sha(initial_path),'final_protection_v1_sha256':sha(final_path),'source_callback_GTest_cases':19,'actual_DDS_wire_component_cases':1,'actual_DDS_wire_component_audit_sha256':sha(D/'postrun/wire_component_audit_v1.json'),'reference_pair_retry_comparison_sha256':sha(D/'postrun/comparison_parent_v1.json'),'first_RMSE_gate_failure_preserved':any(r.get('code')=='projected_preregistered_whole_measurement_RMSE_halved_parent' for r in cases['s005'].get('issues',[])),'historical_original_path_statement':{'all_historical_original_path_bytes_unchanged':final['protection'].get('all_historical_original_path_bytes_unchanged'),'explicit_live_original_path_exceptions':final['protection'].get('explicit_live_original_path_exceptions',[])},'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 write(D/'postrun/final_QA_v1.json',result);print(json.dumps({'archive_integrity_passed':True,'cases_complete':complete,'batch_status':result['batch_status'],'blocked_gate':blocked,'fixed_files':len(fixed),'author_files':frozen['count']}))

def verify_fixed(q):
 for path,row in q['fixed_files'].items():require(sha(path)==row['sha256'],'fixed_QA_input_changed:'+path)
def deliver():
 qpath=D/'postrun/final_QA_v1.json';q=load(qpath);require(q['archive_integrity_passed'] is True,'archive_QA_integrity');verify_fixed(q)
 backup=load(D/'postrun/intermediate_MPC_backup_v1.json');backup_rows={r['relative_path']:r for r in backup['files']}
 for r in backup_rows.values():require(sha(r['snapshot'])==r['sha256'],'intermediate_MPC_backup_identity')
 invpath=D/'archive_inventory_v1.json';receiptpath=D/'delivery_verification.json'
 source,directories=population(D);datafiles=[p for p in source if str(p.relative_to(D)) not in METADATA]
 inventory={'schema':'reference-pair-wakeup-archive-inventory/v1','files':[{'relative_path':str(p.relative_to(D)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in datafiles],'directories':directories,'metadata_rule':'inventory excludes itself and receipt; final population adds exactly these two metadata files','cases_complete':q['cases_complete'],'batch_status':q['batch_status'],'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
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
 verification={'schema':'reference-pair-wakeup-MPC-delivery/v1','passed':True,'source':str(D),'destination':str(M),'files_before_delivery_receipt':len(inventory['files'])+1,'final_regular_files_per_root':len(inventory['files'])+2,'inventory_declared_data_files':len(inventory['files']),'complete_population_equal':True,'full_byte_readback':True,'full_second_SHA_readback':True,'archive_inventory_sha256':sha(invpath),'final_QA_sha256':sha(qpath),'author_freeze_sha256':sha(D/'postrun/author_freeze_v1.json'),'intermediate_files_backed_up':len(backup_rows),'cases_complete':q['cases_complete'],'batch_status':q['batch_status'],'blocked_gate':q['blocked_gate'],'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 if receiptpath.exists():require(load(receiptpath)==verification,'existing_receipt_changed')
 else:write(receiptpath,verification)
 if (M/receiptpath.name).exists():require((M/receiptpath.name).read_bytes()==receiptpath.read_bytes(),'MPC_receipt_differs')
 else:copy_exact(receiptpath,M/receiptpath.name)
 require({str(p.relative_to(D)) for p in files(D)}=={str(p.relative_to(M)) for p in files(M)},'final_full_population')
 for p in files(D):require(sha(p)==sha(M/p.relative_to(D)),'final_metadata_inclusive_readback:'+str(p))
 print(json.dumps({'passed':True,'destination':str(M),'files':verification['final_regular_files_per_root'],'cases_complete':q['cases_complete'],'batch_status':q['batch_status'],'receipt_sha256':sha(receiptpath)},ensure_ascii=False))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['freeze','qa','deliver']);args=parser.parse_args();{'freeze':freeze,'qa':qa,'deliver':deliver}[args.mode]()
