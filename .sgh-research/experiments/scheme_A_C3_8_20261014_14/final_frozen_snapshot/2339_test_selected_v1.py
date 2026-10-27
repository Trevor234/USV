#!/usr/bin/env python3
"""Fresh C3.7 source pin build, bounded targets; no install/codegen."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,shlex,subprocess,time,xml.etree.ElementTree as ET
import sys
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_8_20261014_v15'
sys.path.insert(0,str(N))
from build_c33_v9 import SETUP
TARGETS=['p1_regulator_shadow_observer_owned_v2','test_c38_diagnostic_gate','test_c36_applied_boundaries','test_c37_worker_callbacks','test_shadow_entry','test_legacy_ready','test_witness_v2_c37','c37_worker_child']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 with Path(p).open('x') as f:json.dump(x,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def verify(pin):
 assert sha(pin['path'])==pin['sha256'];b=json.loads(Path(pin['path']).read_text())
 for rel,x in b['files'].items():assert sha(x['path'])==x['sha256'] and Path(x['path']).stat().st_size==x['bytes'],rel
 return b
def command(out,name,args,seconds,domain=131,extra=''):
 script=out/(name+'.sh')
 with script.open('x') as f:f.write('set -e\n'+SETUP+'export ROS_DOMAIN_ID='+str(domain)+'\n'+extra+'exec timeout --signal=TERM --kill-after=5s '+str(seconds)+'s '+shlex.join(args)+'\n')
 with (out/(name+'.log')).open('xb') as log:return subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=seconds+10).returncode
def build():
 out=D/'build/observer_attempt01';out.mkdir(exist_ok=False);bd=N/'observer/build01';assert not bd.exists()
 pin=json.loads((N/'source_bundles_current.json').read_text())['observer'];bundle=verify(pin)
 result={'schema':'C3.7-observer-build/v1','role':'observer','author_directory':str(N),'source_bundle':pin,'passed':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False,'node_launch_performed':False,'install_performed':False,'codegen_performed':False,'target_budget_s':180,'compile_concurrency':2}
 try:
  snapshot=out/'source_snapshot';snapshot.mkdir()
  for rel,x in bundle['files'].items():p=snapshot/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(Path(x['path']).read_bytes())
  cfg=['cmake','-S',str(N/'observer'),'-B',str(bd),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3','-DP1_OWNED_SOURCE_BUNDLE_SHA256='+pin['sha256']]
  result['configure_rc']=command(out,'configure',cfg,90);assert result['configure_rc']==0
  result['gtest_build_rc']=command(out,'gtest_libs',['cmake','--build',str(bd),'--target','gtest','gtest_main','-j2'],90);assert result['gtest_build_rc']==0
  def one(t):
   rc=command(out,'build_'+t,['cmake','--build',str(bd),'--target',t,'-j1'],180);return t,rc
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:result['target_returncodes']=dict(pool.map(one,TARGETS))
  assert all(rc==0 for rc in result['target_returncodes'].values()),'target build failure'
  verify(pin);binaries={t:{'path':str(bd/t),'sha256':sha(bd/t),'bytes':(bd/t).stat().st_size} for t in TARGETS}
  result.update(binary=str(bd/TARGETS[0]),binary_sha256=sha(bd/TARGETS[0]),native_binaries={k:v for k,v in binaries.items() if k.startswith('test_')},auxiliary_binaries={k:v for k,v in binaries.items() if k in ['witness_v2_c37_producer','c37_worker_child']},configure_rc=0,build_rc=0,runtime_build_rc=0,native_build_rc=0)
  deps={}
  for f in bd.rglob('*.o.d'):
   for token in shlex.split(f.read_text().replace('\\\n',' ').split(':',1)[1]):
    p=Path(token)
    if p.is_absolute() and p.is_file():p=p.resolve();deps[str(p)]=sha(p)
  write(out/'compiler_dependency_pins.json',{'compiler':str(Path('/usr/bin/c++').resolve()),'compiler_sha256':sha(Path('/usr/bin/c++').resolve()),'compile_commands_sha256':sha(bd/'compile_commands.json'),'dependency_count':len(deps),'files':deps,'scope':'actual compiler-reported file contents; no full machine/WCET claim'})
  (out/'compile_commands.json').write_bytes((bd/'compile_commands.json').read_bytes());result['passed']=True
 except BaseException as e:result['error']=repr(e)
 write(out/'result.json',result);print(json.dumps(result));return result['passed']
def tests():
 out=D/'component/native_attempt01';out.mkdir(exist_ok=False);build=json.loads((D/'build/observer_attempt01_completion01/result.json').read_text());assert build['passed'];verify(build['source_bundle'])
 result={'schema':'C3.7-native/v1','passed':False,'tests':{},'domain':131,'stage_qualified':False}
 child=build['auxiliary_binaries']['c37_worker_child'];assert sha(child['path'])==child['sha256']
 for name,pin in build['native_binaries'].items():
  assert sha(pin['path'])==pin['sha256'];folder=out/name;folder.mkdir();branch=folder/'branch';branch.mkdir()
  env='export P1_C34_LEASE_NATIVE_DIR='+shlex.quote(str(branch))+'\nexport P1_BRANCH_TEST_OUTPUT='+shlex.quote(str(branch))+'\nexport C37_WORKER_CHILD_BIN='+shlex.quote(child['path'])+'\n'
  rc=command(folder,'run',[pin['path'],'--gtest_output=xml:'+str(folder/'gtest.xml')],90,131,env)
  row={'returncode':rc,'binary_sha256':pin['sha256'],'count':0,'failed':1,'errors':0}
  if (folder/'gtest.xml').exists():
   x=ET.parse(folder/'gtest.xml').getroot();row.update(count=int(x.attrib['tests']),failed=int(x.attrib['failures']),errors=int(x.attrib.get('errors',0)),disabled=int(x.attrib.get('disabled',0)))
  row['passed']=rc==0 and row['count']>0 and row['failed']==row['errors']==0;result['tests'][name]=row
 result['count']=sum(x['count'] for x in result['tests'].values());result['passed']=all(x['passed'] for x in result['tests'].values());verify(build['source_bundle']);write(out/'result.json',result);print(json.dumps(result));return result['passed']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','tests']);a=p.parse_args();raise SystemExit(0 if (build() if a.mode=='build' else tests()) else 1)
