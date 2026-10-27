#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,json,os,re,shlex,stat,subprocess,sys,xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_8_20261014_v15'
sys.path.insert(0,str(D));import protection_v1 as P;import build_and_verify_v1 as B
sys.path.insert(0,str(N.parent/'authored_D1_C3_5_20261013_v11'));import acceptance_core_v1 as C
def write(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False);f.write('\n')
def main():
 before=P.protect();pre=json.loads((D/'preflight/workspace_initial.json').read_text());C.require(pre['passed'] and before==pre['protection'],'initial_protection_changed')
 r=C.Reader(seconds=900,max_bytes=3*1024*1024*1024,max_files=26000)
 build=r.json(D/'build/observer_attempt01_completion01/result.json');native=r.json(D/'component/native_attempt01/result.json');matrix=r.json(D/'postrun/matrix_current.json');pure=r.json(D/'component/checker_finite_v1.json')
 C.require(build['passed'] and native['passed'] and native['count']==102 and matrix['passed'] and matrix['actual_cases']==9 and pure['passed'] and pure['tests']==9,'current_components')
 failed=r.json(D/'build/observer_attempt01/result.json');C.require(failed['passed'] is False and failed['target_returncodes']['test_c38_diagnostic_gate']!=0,'original_build_failure_retained')
 fixed=r.json(D/'build/gate_corrected_attempt02/result.json');C.require(fixed['passed'] and fixed['production_source_changed'] is False,'separate_corrected_fixture')
 r.verify({'path':fixed['corrected_source'],'sha256':fixed['corrected_source_sha256']});r.verify({'path':fixed['binary'],'sha256':fixed['binary_sha256']})
 registry=r.json(N/'build_manifest_current.json');C.require(next(x for x in registry if x['role']=='observer')==build,'current_selected_manifest')
 source_registry=r.json(N/'source_bundles_current.json');C.require(source_registry['observer']==build['source_bundle'],'current_source_bundle')
 for entry in registry:
  r.verify({'path':entry['binary'],'sha256':entry['binary_sha256']});r.verify(entry['source_bundle'])
  for x in r.json(entry['source_bundle']['path'])['files'].values():r.verify(x)
 bundle=r.json(build['source_bundle']['path'])
 for rel,x in bundle['files'].items():r.verify({'path':str(D/'build/observer_attempt01/source_snapshot'/rel),'sha256':x['sha256'],'bytes':x['bytes']})
 for name,pin in build['native_binaries'].items():
  r.verify(pin);root=ET.fromstring(r.raw(D/'component/native_attempt01'/name/'gtest.xml'));C.require(int(root.attrib['tests'])==native['tests'][name]['count'] and int(root.attrib['failures'])==0,'native_XML')
 for path,pin in r.json(D/'preregister/helper_pins_v1.json')['files'].items():r.verify({'path':path,**pin})
 for row in matrix['rows']:
  checkpath=D/'runs'/row['case']/'check_result.json';C.require(C.digest(r.raw(checkpath))==row['check_sha256'],'selected_case_check')
  check=r.json(checkpath);C.require(check['passed'] and all(x is False for x in check['qualifications'].values()),'case_qualification_scope')
  C.require(check['input_sha256_before']==check['input_sha256_after'],'case_input_stability')
  for name in ['input_sha256_before','author_asset_sha256','checker_dependencies']:
   for path,digest in check[name].items():C.require(C.digest(r.raw(path))==digest,'case_input_changed:'+path)
 deps=r.json(D/'build/observer_attempt01_completion01/compiler_dependency_pins.json')
 for path,digest in deps['files'].items():C.require(C.digest(r.raw(path))==digest,'actual_compile_dependency')
 binaries={}
 for directory in [N/'observer/build01',N/'observer/build_gate_corrected02']:
  for p in directory.rglob('*'):
   if p.is_file():
    h=p.read_bytes()[:20]
    if len(h)>=20 and h[:4]==b'\x7fELF' and int.from_bytes(h[16:18],'little') in (2,3):binaries[str(p)]=C.digest(r.raw(p))
 libs={};ldddir=D/'postrun/runtime_ldd_v1';ldddir.mkdir()
 for i,path in enumerate(sorted(binaries)):
  proc=subprocess.run(['bash','-c','set -e\n'+B.SETUP+'exec '+shlex.join(['ldd',path])+'\n'],capture_output=True,text=True,timeout=20)
  with (ldddir/(str(i+1)+'_'+Path(path).name+'.log')).open('x') as f:f.write(proc.stdout+proc.stderr)
  C.require(proc.returncode==0 and 'not found' not in proc.stdout+proc.stderr,'runtime_environment_ldd')
  for name in re.findall(r'(?:=>\s+)?(/[^\s()]+)',proc.stdout):
   p=Path(name).resolve();libs[str(p)]=C.digest(r.raw(p))
 write(D/'postrun/runtime_shared_library_pins.json',{'passed':True,'within_build_SETUP':True,'files':libs,'scope':'linked file bytes; not WCET or whole machine'})
 root=D/'final_frozen_snapshot';root.mkdir();paths=[]
 for p in sorted(N.rglob('*')):
  if p.is_file() and not any(x.startswith('build') or x=='__pycache__' for x in p.relative_to(N).parts[:-1]):paths.append(('author_and_entire_raw_runs',p))
 paths += [('build_source_snapshot',p) for p in (D/'build/observer_attempt01/source_snapshot').rglob('*') if p.is_file()]
 paths += [('compile_dependency',Path(p)) for p in deps['files']]+[('compiler',Path(deps['compiler']))]+[('binary',Path(p)) for p in binaries]+[('runtime_link',Path(p)) for p in libs]
 paths += [('batch_helper_document_or_evidence',p) for p in D.glob('*.py')]+[('document',p) for p in D.glob('*.md')]+[('preregister',p) for p in (D/'preregister').glob('*') if p.is_file()]
 paths += [('case_selected_evidence',p) for p in (D/'runs').rglob('*') if p.is_file()]
 pairs=[];seen=set()
 for kind,p in paths:
  key=str(p.resolve())
  if key in seen:continue
  seen.add(key);raw=r.raw(p);copy=root/(f'{len(pairs)+1:04d}_'+p.name)
  with copy.open('xb') as f:f.write(raw)
  C.require(r.raw(copy)==raw,'frozen_pair_readback');pairs.append({'kind':kind,'original':str(p),'copy':str(copy),'sha256':C.digest(raw),'bytes':len(raw)})
 write(root/'manifest.json',{'passed':True,'all_pairs_verified':True,'files':pairs,'new_frozen_pairs':len(pairs),'stage_qualified':False,'research_conclusion':False})
 r.raw(root/'manifest.json');C.require(r.unchanged(),'fixed_inputs_changed');after=P.protect();C.require(before==after,'parent_assets_changed')
 qa={'schema':'C3.8-final-QA/v1','passed':True,'parent_before':before,'parent_after':after,'new_frozen_pairs':len(pairs),'native_count':102,'actual_owned_cases':9,'source_bundle_sha256':build['source_bundle']['sha256'],'runtime_binary_sha256':build['binary_sha256'],'runtime_env_within_BUILD_SETUP':True,'runtime_library_count':len(libs),'original_build_failure_retained':True,'original_target_still_failed':True,'corrected_fixture_independently_verified':True,'fixed_source_header_input_hashes':dict(r.hashes),'actual_Accepted':0,'normal_business':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 write(D/'postrun/final_QA_current.json',qa);print(json.dumps({k:v for k,v in qa.items() if k not in ('fixed_source_header_input_hashes','parent_before','parent_after')},ensure_ascii=False))
if __name__=='__main__':main()
