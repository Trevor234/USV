#!/usr/bin/env python3
"""C3.10 reuses sealed baseline binaries and tests only the new bounded changes."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess,sys,time
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_10_20261015_v17'
sys.path.insert(0,str(N));from build_c33_v9 import SETUP

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def write(p,x):
 with Path(p).open('x') as f:json.dump(x,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def verify_assets():
 pins=json.loads((N/'source_bundles_current.json').read_text());builds=json.loads((N/'build_manifest_current.json').read_text());assert {r['role'] for r in builds}==set(pins)=={'publisher','worker','fixture','observer','recorder','foreign'}
 hashes={}
 for row in builds:
  role=row['role'];pin=pins[role];assert row['passed'] is True and row['source_bundle']==pin
  assert sha(pin['path'])==pin['sha256'];bundle=json.loads(Path(pin['path']).read_text());assert len(bundle['files'])==pin['files'];hashes[pin['path']]=pin['sha256']
  for item in bundle['files'].values():assert sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes'];hashes[item['path']]=item['sha256']
  assert sha(row['binary'])==row['binary_sha256'];hashes[row['binary']]=row['binary_sha256']
  assert row['install_performed'] is False and row['codegen_performed'] is False
 return hashes

def command(out,name,args,budget,domain):
 script=out/(name+'.sh')
 with script.open('x') as f:f.write('set -e\n'+SETUP+'export ROS_DOMAIN_ID='+str(domain)+'\nexec timeout --signal=TERM --kill-after=5s '+str(budget)+'s '+shlex.join(args)+'\n')
 with (out/(name+'.log')).open('xb') as log:return subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=budget+10).returncode

def finite():
 before=verify_assets();out=D/'component';foreign=json.loads((D/'build/foreign_attempt03/result.json').read_text());assert foreign['passed'] and foreign['native_tests']['tests']>23 and all(foreign['native_tests'][k]==0 for k in ['failures','errors','disabled'])
 modules=['test_c38_owned_close','test_c39_worker_close','test_c310_foreign_close','test_c310_foreign_close_v2'];log=out/'checker_finite_v2.log'
 with log.open('xb') as f:r=subprocess.run(['/usr/bin/python3','-B','-m','unittest',*modules],cwd=N,stdout=f,stderr=subprocess.STDOUT,timeout=30)
 text=log.read_text();import re
 count=int(re.search(r'Ran (\d+) tests',text).group(1));assert count>=130
 old=D.parent/'scheme_A_C3_9_20261014_15/component/native_attempt01/result.json';base=json.loads(old.read_text());assert base['passed'] and base['count']==251
 result={'schema':'C3.10-component-verification/v1','passed':r.returncode==0 and before==verify_assets(),'new_native_count':foreign['native_tests']['tests'],'new_native_rerun_in_selected_producer_build':True,'finite_checker_count':count,'finite_checker_returncode':r.returncode,'finite_log_sha256':sha(log),'baseline_native_251_evidence_reused_sha256':sha(old),'baseline_native_251_rerun':False,'selected_assets_sha256':before,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 write(out/'result_v2.json',result);print(json.dumps({k:result[k] for k in ['passed','new_native_count','finite_checker_count','baseline_native_251_rerun']}));return result['passed']

def actual(case):
 assert json.loads((D/'preflight/workspace_resumed_v4.json').read_text())['passed']
 assert json.loads((D/'component/result_v2.json').read_text())['passed']
 helper=json.loads((D/'preregister/helper_pins_v4.json').read_text())
 for p,x in helper['files'].items():assert sha(p)==x['sha256'],p
 verify_assets();out=D/'runs'/(case+'_v3' if case=='foreign_after_close' else case+'_v2');out.mkdir(exist_ok=False)
 domain={'normal':161,'foreign_after_close':162}[case];run=N/'runs'/('owned_C310_'+case+('_03' if case=='foreign_after_close' else '_02'))
 rc=command(out,'run_owned',['/usr/bin/python3','-B',str(N/'prepare_fixture_v2.py'),'--run-id',run.name,'--domain',str(domain),'--mode','positive','--c38-case',case],75,domain)
 write(out/'invocation.json',{'schema':'C3.10-owned-invocation/v1','case':case,'domain':domain,'run_dir':str(run),'driver_returncode':rc,'stage_qualified':False})
 if (run/'result.json').is_file():
  with (out/'result.json').open('xb') as f:f.write((run/'result.json').read_bytes())
 checker='check_c38_owned_close.py' if case=='normal' else 'check_c310_foreign_close_v2.py'
 checkrc=command(out,'check_owned',['/usr/bin/python3','-B',str(N/checker),'--run-dir',str(run),'--output',str(out/'check_result.json')],45,domain)
 x=json.loads((out/'check_result.json').read_text());print(json.dumps({'case':case,'passed':x['passed'],'driver_returncode':rc,'check_returncode':checkrc,'issues':x.get('issues'),'reader_error':x.get('reader_error')},ensure_ascii=False));return checkrc==0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['finite','normal','foreign_after_close']);a=p.parse_args();raise SystemExit(0 if (finite() if a.mode=='finite' else actual(a.mode)) else 2)
