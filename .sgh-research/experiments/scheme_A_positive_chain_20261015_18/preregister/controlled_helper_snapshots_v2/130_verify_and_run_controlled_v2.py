#!/usr/bin/env python3
"""Bounded A positive control; sealed F5/Worker/Observer/Recorder, new zero fixture."""
from pathlib import Path
import argparse, hashlib, json, re, shlex, subprocess, sys
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
N = D.parent/'p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18/controlled_phase'
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
 before=verify_assets()
 for role in ['observer','worker','publisher','fixture']:
  r=json.loads((N/'build_manifest_current.json').read_text()); row=next(x for x in r if x['role']==role)
  assert row['passed'] and row['source_content_unchanged']
 log=D/'component/checker_controlled_v2.log'
 with log.open('xb') as f:
  r=subprocess.run(['/usr/bin/python3','-B','-m','unittest','test_controlled_v1','test_controlled_owner_v1','test_controlled_v2'],cwd=N,stdout=f,stderr=subprocess.STDOUT,timeout=30)
 count=int(re.search(r'Ran (\d+) tests',log.read_text()).group(1));assert r.returncode==0 and count>=66
 assert before==verify_assets()
 files=list(N.glob('*.py'))+list((N/'runtime').glob('*.py'))+[N/'source_bundles_current.json',N/'build_manifest_current.json',N/'controlled_contract_v1.json',Path(__file__),D/'LOCKED_ORDER.md',D/'documents/controlled_design_v1.md']
 snap=D/'preregister/controlled_helper_snapshots_v2';snap.mkdir(exist_ok=False);hashes={}
 for i,p in enumerate(sorted(files)):
  target=snap/(str(i).zfill(3)+'_'+p.name);target.open('xb').write(p.read_bytes());hashes[str(p)]={'sha256':sha(p),'snapshot':str(target)}
 write(D/'preregister/controlled_preregistration_v2.json',{'schema':'ordered-controlled-preregister/v1','helper_files':hashes,'asset_sha256':before,'cases':{'A2':175,'B':176,'C':177},'measurement_seconds':4,'minimum_consecutive_candidate_accepts':10,'order':['A2','B','C'],'B_pulse_n':0.1,'B_pulse_offset_ns':100000000,'C_reference_speed_m_s':0.05,'scope':'isolated_real_DDS_diagnostic_nominal_model','stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 write(D/'component/checker_controlled_v2.json',{'passed':True,'tests':count,'log_sha256':sha(log),'stage_qualified':False})
 print(json.dumps({'controlled_preregistered':True,'checker_tests':count}))
def actual(case):
 assert json.loads((D/'runs/A_zero_01/check_result.json').read_text())['passed']
 assert json.loads((D/'preflight/workspace_resume_projection_v4.json').read_text())['passed']
 if case!='A2':
  prior='A2' if case=='B' else 'B';assert json.loads((D/'runs'/('controlled_'+prior+'_02')/'check_result.json').read_text())['passed']
 pre=json.loads((D/'preregister/controlled_preregistration_v2.json').read_text())
 for p,x in pre['helper_files'].items():assert sha(p)==x['sha256'] and sha(x['snapshot'])==x['sha256'],p
 assert verify_assets()==pre['asset_sha256']
 out=D/'runs'/('controlled_'+case+'_02');out.mkdir(exist_ok=False);run=N/'runs'/('ordered_'+case+'_02');domain=pre['cases'][case]
 rc=command(out,'run_owned',['/usr/bin/python3','-B',str(N/'prepare_controlled_v2.py'),'--run-id',run.name,'--domain',str(domain),'--mode','positive','--c38-case','normal','--controlled-case',case],75,domain)
 write(out/'invocation.json',{'run_dir':str(run),'domain':domain,'driver_returncode':rc,'preregistration_sha256':sha(D/'preregister/controlled_preregistration_v2.json'),'stage_qualified':False})
 checkrc=command(out,'check_controlled',['/usr/bin/python3','-B',str(N/'check_controlled_v2.py'),'--run-dir',str(run),'--output',str(out/'check_result.json')],90,domain)
 x=json.loads((out/'check_result.json').read_text());assert verify_assets()==pre['asset_sha256']
 print(json.dumps({'case':case,'passed':x['passed'],'driver_returncode':rc,'checker_returncode':checkrc,'window':x.get('window'),'negative':x.get('negative'),'model':x.get('model'),'issues':x.get('issues'),'reader_error':x.get('reader_error')},ensure_ascii=False))
 return rc==0 and checkrc==0 and x['passed']
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['preregister','A2','B','C']);opt=a.parse_args()
 if opt.mode=='preregister':preregister()
 else:raise SystemExit(0 if actual(opt.mode) else 2)
