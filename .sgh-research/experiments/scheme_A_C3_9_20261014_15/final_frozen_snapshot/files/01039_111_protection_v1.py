#!/usr/bin/env python3
"""Read-only entire parent archive and preservation chain, compact proof identity."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,stat,subprocess,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;P=D.parent/'scheme_A_C3_8_20261014_14';M=Path('/home/trevor/MPC')/P.name
sys.path.insert(0,str(D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11'))
import acceptance_core_v1 as C
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def parent_chain():
 code="import sys,json;sys.dont_write_bytecode=True;sys.path.insert(0,"+repr(str(P))+ ");import archive_v1;print(json.dumps(archive_v1.protect(),sort_keys=True))"
 x=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,timeout=1800)
 C.require(x.returncode==0,'parent_chain:'+x.stderr.decode(errors='replace')[-4000:]);C.require(len(x.stdout)<=16*1024*1024,'finite_parent_proof');return C.strict_json(x.stdout)
def workspace():
 spec=importlib.util.spec_from_file_location('c39_parent_workspace',P/'protection_v1.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod.workspace()
def population(root):
 files,dirs=set(),set()
 for base,ds,fs in os.walk(root,followlinks=False):
  for name in ds:
   p=Path(base)/name;C.require(stat.S_ISDIR(p.lstat().st_mode),'sealed_directory_special');dirs.add(str(p.relative_to(root)))
  for name in fs:
   p=Path(base)/name;C.require(stat.S_ISREG(p.lstat().st_mode),'sealed_file_special');files.add(str(p.relative_to(root)))
 return files,dirs
def protect():
 before=workspace();pins=C.Reader().json(D/'preregister/parent_pins_v1.json')['files'];r=C.Reader(seconds=1800,max_bytes=3*1024**3,max_files=30000)
 for rel,digest in pins.items():
  C.require(C.digest(r.raw(P/rel))==digest,'parent_metadata_changed:'+rel)
 for rel in ['archive_inventory_v1.json','delivery_verification.json','batch_status_final.json']:
  C.require(r.raw(P/rel)==r.raw(M/rel),'parent_metadata_pair:'+rel)
 inv=r.json(P/'archive_inventory_v1.json');delivery=r.json(P/'delivery_verification.json');qa=r.json(P/'postrun/final_QA_current.json')
 C.require(len(inv['files'])==2737 and delivery['passed'] and delivery['full_second_SHA_readback'] and delivery['final_regular_files_per_root']==2740,'complete_parent_archive_scope')
 C.require(qa['passed'] and qa['native_count']==102 and qa['new_frozen_pairs']==2411 and len(qa['fixed_source_header_input_hashes'])==4869,'parent_QA_scope')
 expected={'archive_inventory_v1.json','delivery_verification.json','batch_status_final.json'}
 for pin in inv['files']:
  rel=Path(pin['relative_path']);C.require(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in expected,'normalized_unique_parent_path');expected.add(str(rel))
  for root in [P,M]:r.verify({'path':str(root/rel),'sha256':pin['sha256'],'bytes':pin['bytes']})
 for root in [P,M]:C.require(population(root)==(expected,set(inv['directories'])),'complete_parent_population:'+str(root))
 C.require(r.json(P/'build/observer_attempt01/result.json')['passed'] is False,'original_Gate_compile_failure_retained')
 chain=parent_chain();C.require(chain==inv['protection']==inv['protection_after_prepare']==delivery['protected_before']==delivery['protected_after'],'complete_parent_chain_identity')
 C.require(r.unchanged(),'sealed_parent_changed_during_read');after=workspace()
 for key in ['HEAD','branch','boot_id','business_tracked_count','business_diff_bytes','business_diff_sha256','staged_business_diff_sha256']:C.require(before[key]==after[key],'workspace_changed:'+key)
 return {'schema':'C3.9-preservation/v1','passed':True,'parent_inventory_sha256':pins['archive_inventory_v1.json'],'parent_QA_sha256':pins['postrun/final_QA_current.json'],'parent_archive_pairs':2740,'parent_fixed_QA_paths':4869,'parent_frozen_pairs':2411,'parent_chain_proof_sha256':C.digest(canon(chain)),'parent_chain_fully_recomputed':True,'HEAD':after['HEAD'],'branch':after['branch'],'boot_id':after['boot_id'],'business_tracked_count':24,'business_diff_bytes':151961,'business_diff_sha256':after['business_diff_sha256'],'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();C.require(a.output.is_absolute() and a.output.parent==D/'preflight','new_preflight_only')
 try:
  b=workspace();proof=protect();z=workspace();x={'passed':True,'protection':proof,'workspace_before':b,'workspace_after':z,'endpoints_checked':False,'stage_qualified':False,'research_conclusion':False}
 except Exception as e:x={'passed':False,'error':repr(e),'stage_qualified':False,'research_conclusion':False}
 with a.output.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False,sort_keys=True);f.write('\n')
 print(json.dumps({'passed':x['passed'],'error':x.get('error'),'output':str(a.output)}));return 0 if x['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
