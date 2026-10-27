#!/usr/bin/env python3
"""Read-only preservation audit of declared N9/F5/support inputs, never update expected."""
import hashlib,json,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
W=Path('/home/trevor/USV')
N9=W/'.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9'
F5=W/'.sgh-research/baselines/F5_20261005_atomic_freeze_01'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main(label):
 issues=[];counts={};pins={}
 def check(p,expected,scope):
  try:
   actual=sha(p);pins[str(p)]=actual
   if actual!=expected:issues.append({'path':str(p),'scope':scope,'expected':expected,'actual':actual})
  except OSError as e:issues.append({'path':str(p),'scope':scope,'error':str(e)})
 manifest=N9/'final_frozen_snapshot_batch07/manifest.json'
 check(manifest,'9f21e8ea52560ff48e2297642a559f80c3dc39329c05fa2c32733a3b1133f1d1','N9 manifest')
 entries=json.loads(manifest.read_text())['files'];counts['N9_pairs']=len(entries)
 for x in entries:
  for key in ('original','copy'):check(x[key],x['sha256'],'N9 declared '+key)
 groups=[('source_snapshot',json.loads((F5/'source_hashes.json').read_text())),
         ('installed_snapshot',json.loads((F5/'installed_hashes.json').read_text())['files']),
         ('model_snapshot',json.loads((F5/'model_assets.json').read_text())['files'])]
 for scope,entries in groups:
  counts['F5_'+scope]=len(entries)
  for x in entries:check(F5/scope/x['path'],x['sha256'],'immutable F5 '+scope)
 dependency=W/'.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_startup_handshake_20261009_v1/scoped_dependency_lock.json'
 entries=json.loads(dependency.read_text())['files'];counts['scoped_dependencies']=len(entries)
 for path,x in entries.items():check(path,x['sha256'],'fixed scoped dependencies')
 support=W/'.sgh-research/repairs/remaining_drift_20261010_01/SIM_SHARED_SUPPORT_20261010_01.json'
 entries=json.loads(support.read_text())['assets'];counts['support']=len(entries)
 for x in entries:
  p=Path(x['path'])
  if x['sha256'] is None:
   if not p.is_dir():issues.append({'path':str(p),'scope':'declared support directory'})
  else:check(p,x['sha256'],'declared support')
  if str(p.resolve())!=x['resolved_path'] or (os.readlink(p) if p.is_symlink() else None)!=x['link_target']:
   issues.append({'path':str(p),'scope':'support link identity'})
 diff=subprocess.check_output(['git','diff','--binary','--',':(exclude).gitignore'],cwd=W)
 expected='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5'
 diffsha=hashlib.sha256(diff).hexdigest()
 if diffsha!=expected:issues.append({'scope':'business24 diff','expected':expected,'actual':diffsha})
 out={'schema':'scheme-A-C3.4-preservation/v1','counts':counts,'unique_reads':len(pins),'pins':pins,'issues':issues,
      'passed':not issues,'business_diff_bytes':len(diff),'business_diff_sha256':diffsha,
      'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip(),
      'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
      'scope':'declared N9 pairs, immutable F5 snapshots, current declared support and original business24 diff; not all historical or machine assets',
      'older3864_guard_requalified':False,'old_expected_updated':False}
 path=R/label/'preserved_assets.json'
 with path.open('x') as f:json.dump(out,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps({k:v for k,v in out.items() if k!='pins'},sort_keys=True))
 return 0 if out['passed'] else 1
if __name__=='__main__':
 import sys
 raise SystemExit(main(sys.argv[1]))
