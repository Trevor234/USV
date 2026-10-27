#!/usr/bin/env python3
"""Preregistered ordered 20s speed ladder; all control guards stay frozen."""
from pathlib import Path
import argparse,hashlib,json,re,shlex,subprocess,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_pair_wakeup_20261018_v22'
P=D.parent/'scheme_A_longitudinal_20261016_19'
sys.path.insert(0,str(N))
from build_c33_v9 import SETUP
CASES={'s005':(.05,198),'s010':(.1,199),'s030':(.3,200),'s060':(.6,189)}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,x):
 with Path(p).open('x') as f:json.dump(x,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def assets():
 pins=json.loads((N/'source_bundles_current.json').read_text());builds=json.loads((N/'build_manifest_current.json').read_text())
 assert {b['role'] for b in builds}==set(pins)=={'publisher','worker','observer','fixture','recorder'}
 out={}
 for b in builds:
  role=b['role'];p=pins[role];assert b['passed'] is True and p==b['source_bundle'];assert sha(p['path'])==p['sha256'];out[p['path']]=p['sha256']
  bundle=json.loads(Path(p['path']).read_text());assert bundle['role']==role and len(bundle['files'])==p['files']
  for x in bundle['files'].values():assert sha(x['path'])==x['sha256'] and Path(x['path']).stat().st_size==x['bytes'];out[x['path']]=x['sha256']
  assert sha(b['binary'])==b['binary_sha256'];out[b['binary']]=b['binary_sha256']
  leaf=bundle.get('static_link_inputs_before')
  if leaf:
   assert sha(leaf['path'])==leaf['sha256'];out[leaf['path']]=leaf['sha256'];m=json.loads(Path(leaf['path']).read_text())
   assert m['captured_after_configure_before_any_build'] is True and m['count']==leaf['archives']==len(m['files'])
   for r in m['files'].values():
    assert str(Path(r['path']).resolve(strict=True))==r['resolved_path'] and sha(r['path'])==r['sha256'] and Path(r['path']).stat().st_size==r['bytes']
    assert sha(r['snapshot']['path'])==r['sha256'];out[r['path']]=r['sha256'];out[r['snapshot']['path']]=r['sha256']
   for r in m['link_command_files'].values():assert sha(r['path'])==r['sha256'];out[r['path']]=r['sha256']
   after=Path(leaf['path']).parent/'static_link_inputs_after.json';a=json.loads(after.read_text());assert a['passed'] is True and a['same_before_after'] is True and a['before_sha256']==leaf['sha256'];out[str(after)]=sha(after)
   for key in ['generated_vendor_sources_before_build','generated_archive_tools_before_build']:
    for r in m.get(key,{}).values():assert sha(r['path'])==r['sha256'];out[r['path']]=r['sha256']
   for r in a.get('generated_archives_after_build',{}).values():assert sha(r['path'])==r['sha256'];out[r['path']]=r['sha256']

 return out
def command(out,name,args,budget,domain):
 script=out/(name+'.sh')
 with script.open('x') as f:f.write('set -e\n'+SETUP+'export ROS_DOMAIN_ID='+str(domain)+'\nexec timeout --signal=TERM --kill-after=5s '+str(budget)+'s '+shlex.join(args)+'\n')
 with (out/(name+'.log')).open('xb') as f:return subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=budget+10).returncode
def preregister():
 before=assets();fixture=next(x for x in json.loads((N/'build_manifest_current.json').read_text()) if x['role']=='fixture');assert fixture['source_content_unchanged']
 log=D/'component/checker_finite_v1.log'
 with log.open('xb') as f:r=subprocess.run(['/usr/bin/python3','-B','-m','unittest','test_pair_wakeup_v1','test_pair_wakeup_epoch_checker_v1','test_controlled_owner_v1','test_pair_retry_checker_v1'],cwd=N,stdout=f,stderr=subprocess.STDOUT,timeout=60)
 count=int(re.search(r'Ran (\d+) tests',log.read_text()).group(1));assert r.returncode==0 and count>=30
 assert before==assets();snap=D/'preregister/helper_snapshots_v1';snap.mkdir(exist_ok=False);pins={}
 sources=list(N.glob('*.py'))+list((N/'runtime').glob('*.py'))+[N/'source_bundles_current.json',N/'build_manifest_current.json',N/'pair_wakeup_contract_v1.json',Path(__file__),D/'preflight/preflight_reflection_pair_wakeup_v1.md',D/'postrun/compare_parent_v1.py',D/'build_pair_wakeup_roles_v1.py',D/'build_pair_wakeup_roles_v2.py']
 for i,p in enumerate(sorted(sources)):
  q=snap/(str(i).zfill(3)+'_'+p.name);q.open('xb').write(p.read_bytes());pins[str(p)]={'sha256':sha(p),'snapshot':str(q)}
 write(D/'preregister/pair_wakeup_v1.json',{'schema':'scheme-A-projected-preregister/v1','helper_files':pins,'asset_sha256':before,'cases':CASES,'order':list(CASES),'measurement_seconds':20,'minimum_consecutive_accepts':90,'minimum_activation_span_ns':18000000000,'all_measurement_candidate_activations_accepted':True,'prepare_budget_ns':25000000000,'overall_budget_ns':90000000000,'close_budget_ns':15000000000,'offline_check_budget_s':300,'output_budget_bytes':128*1024*1024,'reference_sampling_policy':'first_target_task_time_profile_v1','last5s_relative_mean_error_max':0.05,'RMSE_max_fraction_of_frozen_baseline':0.5,'frozen_baseline_RMSE':{'s005':0.014784991510502932,'s010':0.029260913386751467,'s030':0.08808870950703403,'s060':0.15508263209306208},'control_deadline_ns':150000000,'target_period_ns':200000000,'numerical_replay_tolerance':1e-9,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 write(D/'component/checker_finite_v1.json',{'passed':True,'count':count,'log_sha256':sha(log),'stage_qualified':False});print(json.dumps({'preregistered':True,'finite_tests':count}))
def actual(case):
 assert json.loads((D/'preflight/workspace_initial_v1.json').read_text())['passed']
 assert json.loads((P/'postrun/final_QA_v1.json').read_text())['passed']
 assert json.loads((D/'preflight/pair_wakeup_GoNoGo_v1.json').read_text())['Go'] is True
 pre=json.loads((D/'preregister/pair_wakeup_v1.json').read_text());order=pre['order'];idx=order.index(case)
 if idx:assert json.loads((D/'runs'/(order[idx-1]+'_01')/'check_result.json').read_text())['passed']
 for p,x in pre['helper_files'].items():assert sha(p)==x['sha256']==sha(x['snapshot']),p
 assert assets()==pre['asset_sha256'];speed,domain=pre['cases'][case]
 out=D/'runs'/(case+'_01');out.mkdir(exist_ok=False);run=N/'runs'/('pair_wakeup_'+case+'_01')
 rc=command(out,'run_owned',['/usr/bin/python3','-B',str(N/'prepare_pair_wakeup_v1.py'),'--run-id',run.name,'--domain',str(domain),'--mode','positive','--c38-case','normal','--controlled-case','C','--reference-speed',str(speed)],105,domain)
 write(out/'invocation.json',{'case':case,'reference_speed_m_s':speed,'domain':domain,'run_dir':str(run),'driver_returncode':rc,'preregistration_sha256':sha(D/'preregister/pair_wakeup_v1.json'),'stage_qualified':False})
 checkrc=command(out,'check_owned',['/usr/bin/python3','-B',str(N/'check_pair_wakeup_v1.py'),'--run-dir',str(run),'--output',str(out/'check_result.json')],300,domain)
 x=json.loads((out/'check_result.json').read_text());assert assets()==pre['asset_sha256']
 print(json.dumps({'case':case,'passed':x['passed'],'driver_rc':rc,'checker_rc':checkrc,'window':x.get('window'),'model':x.get('model'),'performance':x.get('performance'),'issues':x.get('issues'),'reader_error':x.get('reader_error')},ensure_ascii=False))
 return rc==0 and checkrc==0 and x['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['preregister',*CASES]);a=p.parse_args()
 if a.mode=='preregister':preregister()
 else:raise SystemExit(0 if actual(a.mode) else 2)
