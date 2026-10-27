#!/usr/bin/env python3
"""Bounded A positive control; sealed F5/Worker/Observer/Recorder, new zero fixture."""
from pathlib import Path
import argparse, hashlib, json, re, shlex, subprocess, sys
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
N = D.parent/'p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18'
sys.path.insert(0, str(N))
from build_c33_v9 import SETUP

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def write(p,x):
 with Path(p).open('x') as f: json.dump(x,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n')
def verify_assets():
 pins=json.loads((N/'source_bundles_current.json').read_text())
 builds=json.loads((N/'build_manifest_current.json').read_text())
 assert {r['role'] for r in builds}==set(pins)=={'publisher','worker','fixture','observer','recorder'}
 hashes={}
 for r in builds:
  p=pins[r['role']]; assert r['passed'] is True and r['source_bundle']==p
  assert sha(p['path'])==p['sha256']; b=json.loads(Path(p['path']).read_text())
  assert len(b['files'])==p['files'] and b['role']==r['role']; hashes[p['path']]=p['sha256']
  for item in b['files'].values():
   assert sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes']
   hashes[item['path']]=item['sha256']
  assert sha(r['binary'])==r['binary_sha256']; hashes[r['binary']]=r['binary_sha256']
  assert r['install_performed'] is False and r['codegen_performed'] is False
 return hashes
def command(out,name,args,budget,domain):
 script=out/(name+'.sh')
 with script.open('x') as f:
  f.write('set -e\n'+SETUP+'export ROS_DOMAIN_ID='+str(domain)+'\nexec timeout --signal=TERM --kill-after=5s '+str(budget)+'s '+shlex.join(args)+'\n')
 with (out/(name+'.log')).open('xb') as log:
  return subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=budget+10).returncode
def preregister():
 before=verify_assets(); fixture=json.loads((D/'build/fixture_attempt02/result.json').read_text())
 assert fixture['passed'] and fixture['native_tests']=={'tests':6,'failures':0,'errors':0,'disabled':0}
 log=D/'component/checker_A_v1.log'
 with log.open('xb') as f:
  r=subprocess.run(['/usr/bin/python3','-B','-m','unittest','test_positive_chain_v1'],cwd=N,stdout=f,stderr=subprocess.STDOUT,timeout=30)
 count=int(re.search(r'Ran (\d+) tests',log.read_text()).group(1)); assert r.returncode==0 and count>=6
 assert before==verify_assets()
 files=[p for p in N.glob('*.py')]+list((N/'runtime').glob('*.py'))+[N/'source_bundles_current.json',N/'build_manifest_current.json',Path(__file__),D/'LOCKED_ORDER.md',D/'preflight/preflight_reflection_ordered_v1.md']
 snap=D/'preregister/A_helper_snapshots_v1'; snap.mkdir(exist_ok=False)
 hashes={}
 for i,p in enumerate(sorted(files)):
  target=snap/(str(i).zfill(3)+'_'+p.name); target.open('xb').write(p.read_bytes())
  hashes[str(p)]={'sha256':sha(p),'snapshot':str(target)}
 write(D/'preregister/A_preregistration_v1.json',{'schema':'ordered-A-preregister/v1','helper_files':hashes,'asset_sha256':before,'domain':171,'run_id':'ordered_A_zero_01','measurement_seconds':4,'minimum_consecutive_candidate_accepts':10,'actual_Applied_exact_zero_required':True,'owner_live_during_measurement_required':True,'actual_Source_Storage_Witness_join_required':True,'scope':'isolated_real_DDS_shadow_component','B_C_blocked_until_A_pass':True,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 write(D/'component/checker_A_v1.json',{'passed':True,'tests':count,'returncode':r.returncode,'log_sha256':sha(log),'fixture_native_evidence_sha256':sha(D/'build/fixture_attempt02/result.json'),'assets':before,'stage_qualified':False,'research_conclusion':False})
 print(json.dumps({'preregistered':True,'checker_tests':count}))
def actual():
 assert json.loads((D/'preflight/workspace_initial_v3.json').read_text())['passed']
 pre=json.loads((D/'preregister/A_preregistration_v1.json').read_text())
 for p,x in pre['helper_files'].items(): assert sha(p)==x['sha256'] and sha(x['snapshot'])==x['sha256'],p
 assert verify_assets()==pre['asset_sha256']
 out=D/'runs/A_zero_01'; out.mkdir(exist_ok=False); run=N/'runs'/pre['run_id']; domain=pre['domain']
 rc=command(out,'run_owned',['/usr/bin/python3','-B',str(N/'prepare_ordered_A_v1.py'),'--run-id',run.name,'--domain',str(domain),'--mode','positive','--c38-case','normal'],75,domain)
 write(out/'invocation.json',{'run_dir':str(run),'domain':domain,'driver_returncode':rc,'preregistration_sha256':sha(D/'preregister/A_preregistration_v1.json'),'stage_qualified':False})
 checkrc=command(out,'check_A',['/usr/bin/python3','-B',str(N/'check_positive_chain_v1.py'),'--run-dir',str(run),'--output',str(out/'check_result.json')],50,domain)
 x=json.loads((out/'check_result.json').read_text()); assert verify_assets()==pre['asset_sha256']
 print(json.dumps({'A_passed':x['passed'],'driver_returncode':rc,'checker_returncode':checkrc,'issues':x.get('issues'),'reader_error':x.get('reader_error')},ensure_ascii=False))
 return rc==0 and checkrc==0 and x['passed']
if __name__=='__main__':
 a=argparse.ArgumentParser(); a.add_argument('mode',choices=['preregister','actual']); opt=a.parse_args()
 if opt.mode=='preregister': preregister()
 else: raise SystemExit(0 if actual() else 2)
