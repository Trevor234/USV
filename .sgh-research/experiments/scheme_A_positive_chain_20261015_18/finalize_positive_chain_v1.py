#!/usr/bin/env python3
"""Create-only author freeze, final QA and full MPC byte-readback delivery."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18'
M=Path('/home/trevor/MPC')/D.name
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def write(p,x):
 with Path(p).open('x') as f:json.dump(x,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def files(root):
 paths=list(root.rglob('*'));assert not any(p.is_symlink() for p in paths),'unexpected new archive symlink'
 return sorted(p for p in paths if p.is_file())
def freeze():
 root=D/'author_snapshot';root.mkdir(exist_ok=False);rows=[];original=files(N)
 for p in original:
  rel=p.relative_to(N);dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True);before=sha(p)
  with dst.open('xb') as f:
   with p.open('rb') as source:shutil.copyfileobj(source,f)
  assert sha(dst)==sha(p)==before
  rows.append({'original':str(p),'snapshot':str(dst),'relative_path':str(rel),'bytes':p.stat().st_size,'sha256':before})
 assert files(N)==original
 write(D/'postrun/author_freeze_v1.json',{'schema':'ordered-chain-author-freeze/v1','files':rows,'count':len(rows),'bytes':sum(r['bytes'] for r in rows),'all_source_and_failed_attempts_preserved':True})
 print(json.dumps({'author_files_frozen':len(rows)}))
def qa():
 proof=load(D/'preflight/workspace_final_v4.json');assert proof['passed']
 s=importlib.util.spec_from_file_location('final_controlled_harness',D/'verify_and_run_controlled_v2.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g);assets=g.verify_assets()
 for pre in ['A_preregistration_v1.json','controlled_preregistration_v1.json','controlled_preregistration_v2.json']:
  x=load(D/'preregister'/pre)
  for p,r in x['helper_files'].items():assert sha(p)==r['sha256']==sha(r['snapshot']),p
  for p,h in x['asset_sha256'].items():assert sha(p)==h,p
 selected={};cases={}
 for case,rel in [('A','A_zero_01'),('A2','controlled_A2_02'),('B','controlled_B_02'),('C','controlled_C_02')]:
  p=D/'runs'/rel/'check_result.json';x=load(p);assert x['passed'] and not x['issues'];cases[case]={'path':str(p),'sha256':sha(p),'window':x['window'],'negative':x.get('negative'),'model':x.get('model')}
  for source,h in x['input_sha256_after'].items():assert sha(source)==h,source
 assert load(D/'runs/controlled_A2_01/check_result.json')['passed'] is False
 assert load(D/'postrun/independent_sequence_review_v1.json')['passed'] is True
 for role,attempt in [('publisher','03'),('observer','01'),('worker','01'),('fixture','01')]:
  directory=D/'build'/('controlled_'+role+'_attempt'+attempt);x=load(directory/'result.json');assert x['passed']
  selected[role]={'result_sha256':sha(directory/'result.json'),'binary_sha256':x['binary_sha256'],'source_bundle':x['source_bundle']}
  for name in ['compiler_dependency_pins.json','runtime_library_pins.json']:
   for r in load(directory/name)['files'].values():
    assert sha(r['path'])==r['sha256'] and Path(r['path']).stat().st_size==r['bytes'],r['path']
 freeze=load(D/'postrun/author_freeze_v1.json')
 for r in freeze['files']:assert sha(r['original'])==r['sha256']==sha(r['snapshot'])
 fixed={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files(D)}
 result={'schema':'ordered-chain-final-QA/v1','passed':True,'component_sequence_completed':['A','A2','B','C'],'cases':cases,'selected_assets':assets,'selected_builds':selected,'fixed_files':fixed,'fixed_file_count':len(fixed),'author_frozen_files':freeze['count'],'final_old_protection_sha256':sha(D/'preflight/workspace_final_v4.json'),'old_original_paths_unchanged_except_one_explicit_live_delta':True,'all_historical_original_path_bytes_unchanged':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 write(D/'postrun/final_QA_v1.json',result);print(json.dumps({'QA_passed':True,'fixed_files':len(fixed),'author_files':freeze['count']}))
def deliver():
 q=load(D/'postrun/final_QA_v1.json');assert q['passed']
 for p,r in q['fixed_files'].items():assert sha(p)==r['sha256'],p
 # Preserve the intermediate delivered CURRENT before updating that document.
 old=M/'CURRENT.md';backup=D/'CURRENT_initial_delivery_v1.md'
 if old.exists() and sha(old)!=sha(D/'CURRENT.md'):
  assert old.read_bytes()==(D/'CURRENT_before_final_v1.md').read_bytes()
  if not backup.exists():backup.open('xb').write(old.read_bytes())
 inventory={'schema':'ordered-chain-archive-inventory/v1','files':[{'relative_path':str(p.relative_to(D)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files(D)],'directories':sorted(str(p.relative_to(D)) for p in D.rglob('*') if p.is_dir()),'stage_qualified':False,'research_conclusion':False}
 write(D/'archive_inventory_v1.json',inventory)
 for rel in inventory['directories']:(M/rel).mkdir(parents=True,exist_ok=True)
 for p in files(D):
  rel=p.relative_to(D);dst=M/rel;dst.parent.mkdir(parents=True,exist_ok=True)
  if dst.exists():
   if sha(dst)==sha(p):continue
   assert str(rel)=='CURRENT.md' and backup.read_bytes()==dst.read_bytes(),'unexpected previous delivery differs:'+str(rel)
   dst.write_bytes(p.read_bytes())
  else:
   with dst.open('xb') as f:
    with p.open('rb') as source:shutil.copyfileobj(source,f)
  assert sha(dst)==sha(p)
 assert {str(p.relative_to(M)) for p in files(M)}=={str(p.relative_to(D)) for p in files(D)}
 for p in files(D):assert sha(p)==sha(M/p.relative_to(D))
 verification={'schema':'ordered-chain-MPC-delivery/v1','passed':True,'source':str(D),'destination':str(M),'files_before_delivery_receipt':len(files(D)),'complete_population_equal':True,'full_byte_readback':True,'archive_inventory_sha256':sha(D/'archive_inventory_v1.json'),'final_QA_sha256':sha(D/'postrun/final_QA_v1.json'),'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 write(D/'delivery_verification.json',verification);write(M/'delivery_verification.json',verification)
 assert sha(D/'delivery_verification.json')==sha(M/'delivery_verification.json')
 print(json.dumps(verification,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','qa','deliver']);a=p.parse_args()
 {'freeze':freeze,'qa':qa,'deliver':deliver}[a.mode]()
