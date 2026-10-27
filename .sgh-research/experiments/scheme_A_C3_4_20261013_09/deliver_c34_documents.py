#!/usr/bin/env python3
"""Create-only authorized MPC batch archive with full byte readback and Markdown QA."""
import hashlib,json,os,re,shutil,stat,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
TARGET=Path('/home/trevor/MPC/scheme_A_C3_4_20261013_09')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def dump(p,v):
 with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,ensure_ascii=False);f.write('\n')
def pairs():
 main=json.loads((R/'final_frozen_snapshot/manifest.json').read_text());extra=json.loads((R/'final_frozen_snapshot/source_supplement.json').read_text())
 rows=main['files']+main['owned_raw']+extra['files']
 for x in rows:
  assert sha(x['original'])==sha(x['copy'])==x['sha256'],x['original']
 return len(rows)
def qa(root):
 issues=[];links=0
 for p in [root/'方案A_C3_4实现与有界验证报告_2026-10-13.md',root/'方案A_C3_5下一步实施计划_2026-10-13.md',root/'current-status.md']:
  for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)',p.read_text()):
   if not link.startswith('/'):continue
   path=Path(re.sub(r':\d+$','',link.split('#',1)[0]));links+=1
   if not path.exists():issues.append({'document':str(p),'target':str(path)})
 return {'passed':not issues,'local_links':links,'issues':issues}
def prepare():
 count=pairs();quality=qa(R);assert quality['passed'];dump(R/'postrun/staged_document_QA02.json',quality)
 assert not TARGET.exists()
 files=[];special=[]
 for p in sorted(R.rglob('*')):
  if '__pycache__' in p.parts:continue
  st=p.lstat()
  if stat.S_ISLNK(st.st_mode) or stat.S_ISFIFO(st.st_mode):
   special.append({'path':str(p),'relative':str(p.relative_to(R)),'type':'symlink' if stat.S_ISLNK(st.st_mode) else 'FIFO',
                   'link_target':os.readlink(p) if stat.S_ISLNK(st.st_mode) else None,'mode':st.st_mode,'nlink':st.st_nlink})
   continue
  if not stat.S_ISREG(st.st_mode):continue
  files.append({'path':str(p),'relative':str(p.relative_to(R)),'sha256':sha(p),'bytes':st.st_size})
 result={'schema':'p1-C3.4-authorized-MPC-delivery-plan/v1','source_root':str(R),'target_root':str(TARGET),
         'source_files':files,'special_entries':special,'bytes':sum(x['bytes'] for x in files),'frozen_pair_count_verified':count,'create_only':True,'old_MPC_files_modified':False,
         'special_entry_policy':'retain original special files in USV; archive exact metadata only, never dereference symlinks or read/recreate FIFOs'}
 dump(R/'postrun/delivery_source_manifest.json',result)
 print(json.dumps({'files':len(files),'bytes':result['bytes'],'frozen_pairs':count,'document_QA':quality},ensure_ascii=False))
def deliver():
 plan_path=R/'postrun/delivery_source_manifest.json';plan=json.loads(plan_path.read_text());assert plan['target_root']==str(TARGET)
 assert pairs()==plan['frozen_pair_count_verified'];TARGET.mkdir(exist_ok=False)
 for row in plan['special_entries']:
  p=Path(row['path']);st=p.lstat();assert st.st_mode==row['mode'] and st.st_nlink==row['nlink']
  if row['type']=='symlink':assert os.readlink(p)==row['link_target']
 dump(TARGET/'special_asset_metadata.json',{'entries':plan['special_entries'],'policy':plan['special_entry_policy']})
 rows=plan['source_files']+[{'path':str(plan_path),'relative':str(plan_path.relative_to(R)),'sha256':sha(plan_path),'bytes':plan_path.stat().st_size}]
 for row in rows:
  source=Path(row['path']);assert sha(source)==row['sha256'];dest=TARGET/row['relative'];dest.parent.mkdir(parents=True,exist_ok=True)
  with source.open('rb') as src,dest.open('xb') as dst:shutil.copyfileobj(src,dst,1048576)
  assert sha(dest)==sha(source)==row['sha256']
 quality=qa(TARGET);assert quality['passed']
 diff=subprocess.check_output(['git','diff','--binary','--',':(exclude).gitignore'],cwd='/home/trevor/USV')
 assert hashlib.sha256(diff).hexdigest()=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5'
 result={'schema':'p1-C3.4-MPC-byte-readback/v1','passed':True,'target_root':str(TARGET),'copied_files':len(rows),
         'frozen_pairs_verified_after':pairs(),'document_QA':quality,'regular_source_and_copy_bytes_verified':True,'business24_diff_unchanged':True,'old_MPC_files_modified':False,
         'special_entries_recorded_as_metadata':len(plan['special_entries']),'special_originals_preserved':True}
 dump(R/'postrun/delivery_readback.json',result);dump(TARGET/'postrun/delivery_readback.json',result)
 final=json.loads((R/'batch_status_final_prepared.json').read_text());final['MPC_archive_verified']=True;final['MPC_archive_path']=str(TARGET)
 dump(R/'batch_status_final.json',final);dump(TARGET/'batch_status_final.json',final)
 print(json.dumps(result,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':
 import sys
 {'prepare':prepare,'deliver':deliver}[sys.argv[1]]()
