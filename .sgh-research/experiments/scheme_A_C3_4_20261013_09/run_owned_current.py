#!/usr/bin/env python3
"""New five-role synthetic owned runs with unchanged fixed runtime budgets."""
import json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent
N=R.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
sys.path.insert(0,str(N))
from build_c34_v10 import dump,sha,verify,parent_verify
def main():
 out=R/'runs/owned_matrix01';out.mkdir(exist_ok=False)
 pins=json.loads((N/'source_bundles_current.json').read_text());builds=json.loads((N/'build_manifest_current.json').read_text())
 for b in builds:verify(pins[b['role']],b['role']);assert b['passed'] and sha(b['binary'])==b['binary_sha256']
 parent_verify()
 dump(out/'preregister.json',{'before_first_run':True,'source_bundles':pins,'build_manifest_sha256':sha(N/'build_manifest_current.json'),
   'cases':['positive','expired_release','prepare_io_ambiguous'],'domain':123,'prepare_seconds':25,'overall_seconds':60,'close_seconds':15,
   'measurement_seconds':4,'release_validity_seconds':3,'normal_hook_values':0,'tool_sha256':{p.name:sha(p) for p in N.glob('*.py')},
   'qualification':'component evidence only; all research/stage flags false'})
 (out/'runner.snapshot').open('xb').write(Path(__file__).read_bytes());reports=[]
 env=dict(os.environ,ROS_DOMAIN_ID='123',ROS_LOCALHOST_ONLY='1',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
 for mode,label in [('positive','positive'),('expired_release','expired'),('prepare_io_ambiguous','ambiguous_preparation')]:
  run_id='owned_C3_4_'+label+'_01';run=N/'runs'/run_id;cmd=[sys.executable,'-B',str(N/'prepare_fixture.py'),'--run-id',run_id,'--domain','123','--mode',mode]
  start=time.monotonic()
  with (out/(label+'_driver.log')).open('xb') as log:rc=subprocess.run(['timeout','--signal=TERM','--kill-after=10s','80s',*cmd],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=95).returncode
  item={'mode':mode,'run':str(run),'driver_returncode':rc,'elapsed_seconds':time.monotonic()-start,'checks':{},'passed':False}
  if (run/'result.json').exists():
   result=json.loads((run/'result.json').read_text());item['normal_passed']=result['passed'];item['held_negative_passed']=result['held_negative_passed'];item['cleanup_complete']=result['cleanup_complete'];item['evidence_qualification_clean']=result['evidence_qualification_clean']
   if mode=='positive' and result['passed']:
    checks=[('owned',[sys.executable,'-B',str(N/'check_owned_fixture.py'),'--inputs',str(run/'checker_inputs.json'),'--output',str(out/(label+'_owned.json'))]),
            ('atomic',[sys.executable,'-B',str(N/'check_atomic_observation_v2.py'),'--run',str(run),'--output',str(out/(label+'_atomic.json'))]),
            ('release',[sys.executable,'-B',str(N/'check_release_observation_v1.py'),'--run',str(run),'--output',str(out/(label+'_release.json'))]),
            ('config_domain',[sys.executable,'-B',str(N/'config_scope_v1.py'),'--run',str(run),'--output',str(out/(label+'_config_domain.json'))])]
   elif mode=='expired_release' and result['held_negative_passed']:
    checks=[('release',[sys.executable,'-B',str(N/'check_release_observation_v1.py'),'--run',str(run),'--output',str(out/(label+'_release.json'))])]
   else:checks=[]
   for name,check in checks:
    with (out/(label+'_'+name+'.log')).open('xb') as log:crc=subprocess.run(check,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=45).returncode
    item['checks'][name]=crc
   if mode=='positive':item['passed']=rc==0 and result['passed'] and len(checks)==4 and all(v==0 for v in item['checks'].values())
   elif mode=='expired_release':item['passed']=rc==0 and result['held_negative_passed'] and result['passed'] is False and item['checks'].get('release')==0
   else:item['passed']=rc==0 and result.get('publication_ambiguous',{}).get('target_visible') is True and result['passed'] is False and result['cleanup_complete'] is True and result['evidence_qualification_clean'] is False and result['release_file_exists'] is False
  reports.append(item);dump(out/(label+'_execution.json'),item)
 parent_verify()
 for b in builds:verify(pins[b['role']],b['role']);assert sha(b['binary'])==b['binary_sha256']
 final={'schema':'p1-C3.4-current-owned-matrix/v1','passed':all(x['passed'] for x in reports),'cases':reports,'stage_qualified':False,'execute':False,'research_conclusion':False}
 dump(out/'result.json',final);print(json.dumps(final,sort_keys=True));return 0 if final['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
