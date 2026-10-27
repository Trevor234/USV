#!/usr/bin/env python3
"""Create-only current source/binary snapshot and owned raw copies; no old asset mutation."""
import hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parent
N=R.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 out=R/'final_frozen_snapshot';out.mkdir(exist_ok=False);paths={};builds=json.loads((N/'build_manifest_current.json').read_text())
 def add(p,kind):paths[str(Path(p).absolute())]=kind
 for b in builds:
  add(b['binary'],'binary')
  for item in b['native_binaries'].values():add(item['path'],'binary')
  for key in ['source_bundle','component_source_bundle']:
   if key not in b:continue
   bundle=Path(b[key]['path']);add(bundle,'source')
   for item in json.loads(bundle.read_text())['files'].values():add(item['path'],'source')
 for p in list(N.glob('*.py'))+list(N.glob('*.json'))+list((N/'runtime').rglob('*.py'))+list(R.glob('*.py')):add(p,'source')
 add('/opt/ros/jazzy/include/rmw/rmw/types.h','source')
 for p in R.glob('A_publication/reproductions/*'):
  if p.is_file():add(p,'source')
 for p in R.glob('D_IO/reproductions/*'):
  if p.is_file():add(p,'source')
 for p in R.glob('E_scope/differential01/*.cpp'):add(p,'source')
 for p in R.glob('A_publication/probe*'):
  if p.is_file() and p.suffix=='':add(p,'binary')
 for p in R.glob('D_IO/probe*'):
  if p.is_file() and p.suffix=='':add(p,'binary')
 for p in R.glob('E_scope/differential01/config_scope_probe_v1'):add(p,'binary')
 for p in (N/'publisher/build01').glob('libp1_frozen*.a'):add(p,'binary')
 rows=[]
 for i,(original,kind) in enumerate(sorted(paths.items()),1):
  p=Path(original);assert p.is_file() and not p.is_symlink();target=out/kind/(str(i).zfill(3)+'_'+p.name);target.parent.mkdir(exist_ok=True)
  before=sha(p)
  with p.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1048576)
  assert before==sha(p)==sha(target)
  rows.append({'original':str(p),'copy':str(target),'kind':kind,'sha256':before,'bytes':p.stat().st_size})
 raw=[];rawdir=R/'owned_raw';rawdir.mkdir(exist_ok=False)
 for run in sorted((N/'runs').iterdir()):
  for p in sorted(run.rglob('*')):
   if not p.is_file():continue
   assert not p.is_symlink();target=rawdir/p.relative_to(N/'runs');target.parent.mkdir(parents=True,exist_ok=True);before=sha(p)
   with p.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1048576)
   assert before==sha(p)==sha(target);raw.append({'original':str(p),'copy':str(target),'sha256':before,'bytes':p.stat().st_size})
 result={'schema':'p1-C3.4-current-source-binary-raw-freeze/v1','source_binary_count':len(rows),'owned_raw_count':len(raw),
         'bytes':sum(x['bytes'] for x in rows+raw),'all_pairs_verified':True,'files':rows,'owned_raw':raw,
         'scope':'current explicit component sources/binaries and three closed owned runs; failed prototypes/evidence retained separately in batch directory',
         'stage_qualified':False,'execute':False,'research_conclusion':False}
 with (out/'manifest.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('files','owned_raw')},sort_keys=True))
if __name__=='__main__':main()
