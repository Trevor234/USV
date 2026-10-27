#!/usr/bin/env python3
"""New batch12 source/raw/binary freeze and scoped old-asset preservation proof."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,re
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13'
P=D.parent/'scheme_A_C3_6_20261013_11'
M=Path('/home/trevor/MPC/scheme_A_C3_6_20261013_11')
sys.path.insert(0,str(N.parent/'authored_D1_C3_5_20261013_v11'))
import acceptance_core_v1 as C
def write(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False);f.write('\n')
def parent():
 s=importlib.util.spec_from_file_location('parent_protection',P/'archive_v1.py');mod=importlib.util.module_from_spec(s);s.loader.exec_module(mod)
 return mod.protect()
def main():
 before=parent();r=C.Reader(seconds=600,max_bytes=1024*1024*1024,max_files=12000)
 inv=r.json(P/'archive_inventory_v1.json');C.require(C.digest(r.raw(P/'archive_inventory_v1.json'))=='d35ebd79bd5d79eb1765540fc6faec13b35fe2249a03188ae95b005d0269e34e','parent_inventory')
 for x in inv['files']:
  for root in (P,M):r.verify({'path':str(root/x['relative_path']),'sha256':x['sha256'],'bytes':x['bytes']})
 build=r.json(D/'build/observer_attempt02_completion01/final_build_manifest_entry.json');native=r.json(D/'component/native_current_assessment.json');run=r.json(D/'runs/positive01/result.json');check=r.json(D/'runs/positive01/check_result.json');observation=r.json(D/'runs/positive01/observation_population_result.json')
 C.require(build['passed'] and native['passed'] and run['passed'] and observation['component_observation_passed'],'current_component_or_run_not_passed')
 C.require(check['passed'] is False and observation['normal_witness_qualified'] is False,'normal_Witness_failure_must_remain')
 pin=build['source_bundle'];r.verify(pin);bundle=r.json(pin['path'])
 for x in bundle['files'].values():r.verify(x)
 deps=r.json(D/'build/observer_attempt02_completion01/compiler_dependency_pins.json')
 for p,sha in deps['files'].items():C.require(C.digest(r.raw(Path(p).resolve()))==sha,'compile_dependency_changed:'+p)
 for p,sha in check['input_sha256_before'].items():C.require(C.digest(r.raw(Path(p).resolve()))==sha,'checked_run_input_changed:'+p)
 C.require(check['checker_sha256']==C.digest(r.raw(N/'check_c36_adapter_run.py')),'current_checker_sha')
 binaries=[Path(build['binary'])]+[Path(x['path']) for x in build['native_binaries'].values()]
 typed=r.json(D/'component/atomic_typed_attempt01/result.json');C.require(typed['passed'] and typed['count']==12,'typed_suite')
 binaries.append(Path(typed['binary']))
 for p,sha in typed['actual_dependency_pins'].items():C.require(C.digest(r.raw(Path(p).resolve()))==sha,'typed_dependency_changed')
 runtime_links={}
 for binary in binaries:
  text=subprocess.check_output(['ldd',str(binary)],text=True)
  for item in re.findall(r'(?:=>\s+)?(/[^\s()]+)',text):
   p=Path(item).resolve();runtime_links[str(p)]=C.digest(r.raw(p))
 write(D/'postrun/runtime_shared_library_pins.json',{'files':runtime_links,'scope':'ldd resolved linked-file contents at finalization; no complete machine/runtime continuity or WCET qualification'})
 root=D/'final_frozen_snapshot';root.mkdir(exist_ok=False);pairs=[];seen=set()
 paths=[('author',p) for p in sorted(N.rglob('*')) if p.is_file() and not any(x.startswith('build') or x=='__pycache__' for x in p.relative_to(N).parts)]
 paths += [('binary',p) for p in binaries]
 reviewed=r.json(D/'build/observer_attempt01/result_before_review_repairs.json')
 for x in reviewed['built_targets'].values():
  C.require(C.digest(r.raw(Path(x['path']).resolve()))==x['sha256'],'reviewed_v1_binary_changed')
  paths.append(('reviewed_v1_binary',Path(x['path'])))
 paths += [('compile_dependency',Path(p)) for p in deps['files']]
 paths += [('typed_compile_dependency',Path(p)) for p in typed['actual_dependency_pins']]
 paths += [('runtime_link',Path(p)) for p in runtime_links]
 paths += [('compiler',Path(deps['compiler'])),('finalizer',Path(__file__).resolve())]
 for kind,p in paths:
  p=p.resolve()
  if str(p) in seen:continue
  seen.add(str(p));raw=r.raw(p);copy=root/(f'{len(pairs)+1:04d}_'+p.name)
  with copy.open('xb') as f:f.write(raw)
  C.require(r.raw(copy)==raw,'new_frozen_pair')
  pairs.append({'kind':kind,'original':str(p),'copy':str(copy),'sha256':C.digest(raw),'bytes':len(raw)})
 C.require(r.unchanged(),'inputs_changed_during_finalization');after=parent();C.require(before==after,'parent_protection_changed')
 manifest={'schema':'C3.6-adapter-final-freeze/v1','files':pairs,'all_pairs_verified':True,'new_frozen_pairs':len(pairs),'stage_qualified':False,'research_conclusion':False,'scope':'declared author/raw tools, binaries, actual compiler dependencies, ldd file pins; not complete OS/toolchain/plant/WCET'}
 write(root/'manifest.json',manifest)
 links=0
 for doc in D.glob('*.md'):
  for target in re.findall(r'\]\((/[^)]+)\)',doc.read_text()):
   links+=1;C.require(Path(re.sub(r':\d+$','',target)).exists(),'doc_link:'+target)
 qa={'schema':'C3.6-adapter-final-QA/v1','passed':True,'parent_before':before,'parent_after':after,'parent_batch11_pairs_checked':len(inv['files']),'source_bundle_sha256':pin['sha256'],'compiler_dependency_count':len(deps['files']),'runtime_shared_library_count':len(runtime_links),'new_frozen_pairs':len(pairs),'native_count':native['count'],'owned_driver_complete':True,'owned_shadow_observation_consistency_passed':True,'normal_Witness_qualified':False,'normal_Witness_status':'failed: BusinessReady absent, complete_flag_disagrees','failed_original_run_check_sha256':C.digest(r.raw(D/'runs/positive01/check_result.json')),'observation_population_result_sha256':C.digest(r.raw(D/'runs/positive01/observation_population_result.json')),'local_document_links_checked':links,'fixed_source_header_input_hashes':r.hashes,'business_diff_sha256':before['parent']['business_diff_sha256'],'old_expected_updated':False,'old_failure_deleted':False,'stage_qualified':False,'research_conclusion':False}
 write(D/'postrun/final_QA_current.json',qa)
 print(json.dumps({k:v for k,v in qa.items() if k!='fixed_source_header_input_hashes'},ensure_ascii=False))
if __name__=='__main__':main()
