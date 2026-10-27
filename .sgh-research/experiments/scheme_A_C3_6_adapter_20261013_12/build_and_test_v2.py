#!/usr/bin/env python3
"""Fresh source-identified observer build and bounded local component tests."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess,time,xml.etree.ElementTree as ET
N=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13')
D=Path(__file__).resolve().parent
import sys
sys.path.insert(0,str(N))
from build_c33_v9 import SETUP
TARGETS=['p1_regulator_shadow_observer_owned_v2','test_owned_peer_c36_v1','test_c36_runtime_adapter','test_c36_completion','test_c36_applied_boundaries','test_shadow_entry','test_enqueue_branch','test_d0_observation','test_atomic_observation','test_legacy_ready','test_c33_input_matrix','test_c34_lease_matrix']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 with Path(p).open('x') as f:json.dump(x,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def verify(pin):
 assert sha(pin['path'])==pin['sha256']
 b=json.loads(Path(pin['path']).read_text())
 for rel,x in b['files'].items():assert sha(x['path'])==x['sha256'] and Path(x['path']).stat().st_size==x['bytes'],rel
 return b
def command(out,name,args,seconds,domain=120,extra=''):
 script=out/(name+'.sh')
 with script.open('x') as f:f.write('set -e\n'+SETUP+'export ROS_DOMAIN_ID='+str(domain)+'\n'+extra+'exec timeout --signal=TERM --kill-after=5s '+str(seconds)+'s '+shlex.join(args)+'\n')
 with (out/(name+'.log')).open('xb') as log:return subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=seconds+10).returncode
def build():
 out=D/'build/observer_attempt02';out.mkdir(exist_ok=False);bd=N/'observer/build02';assert not bd.exists()
 pin=json.loads((N/'source_bundles_current.json').read_text())['observer'];bundle=verify(pin)
 result={'schema':'C3.6-adapter-build/v2','role':'observer','author_directory':str(N),'source_bundle':pin,'passed':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False,'node_launch_performed':False,'install_performed':False,'codegen_performed':False}
 try:
  snap=out/'source_snapshot';snap.mkdir()
  for rel,x in bundle['files'].items():p=snap/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(Path(x['path']).read_bytes())
  args=['cmake','-S',str(N/'observer'),'-B',str(bd),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3','-DP1_OWNED_SOURCE_BUNDLE_SHA256='+pin['sha256']]
  result['configure_rc']=command(out,'configure',args,90);assert result['configure_rc']==0,'configure failed'
  result['build_rc']=command(out,'build',['cmake','--build',str(bd),'--target',*TARGETS,'-j2'],600);assert result['build_rc']==0,'build failed'
  verify(pin)
  binaries={t:{'path':str(bd/t),'sha256':sha(bd/t),'bytes':(bd/t).stat().st_size} for t in TARGETS}
  result.update(binary=str(bd/TARGETS[0]),binary_sha256=sha(bd/TARGETS[0]),native_binaries={k:v for k,v in binaries.items() if k.startswith('test_')},runtime_build_rc=0,native_build_rc=0)
  deps={}
  for f in bd.rglob('*.o.d'):
   raw=f.read_text().replace('\\\n',' ');tokens=shlex.split(raw.split(':',1)[1])
   for token in tokens:
    p=Path(token)
    if p.is_absolute() and p.is_file():deps[str(p)]=sha(p)
  write(out/'compiler_dependency_pins.json',{'compiler':str(Path('/usr/bin/c++').resolve()),'compiler_sha256':sha(Path('/usr/bin/c++').resolve()),'compile_commands_sha256':sha(bd/'compile_commands.json'),'dependency_count':len(deps),'files':deps,'scope':'compiler-reported file contents; no complete OS/toolchain/WCET qualification'})
  (out/'compile_commands.json').write_bytes((bd/'compile_commands.json').read_bytes())
  result['passed']=True
 except BaseException as e:result['error']=repr(e)
 write(out/'result.json',result);print(json.dumps(result));return result['passed']
def test(domain):
 out=D/'component/native_attempt01';out.mkdir(exist_ok=False)
 build=json.loads((D/'build/observer_attempt02/result.json').read_text());assert build['passed'];verify(build['source_bundle'])
 result={'schema':'C3.6-adapter-native/v1','passed':False,'domain':domain,'actual_DDS_same_payload_peer_test':True,'tests':{},'stage_qualified':False}
 for t,b in build['native_binaries'].items():
  assert sha(b['path'])==b['sha256'];folder=out/t;folder.mkdir();branch=folder/'branch';branch.mkdir()
  rc=command(folder,'run',[b['path'],'--gtest_output=xml:'+str(folder/'gtest.xml')],90,domain,'export P1_BRANCH_TEST_OUTPUT='+shlex.quote(str(branch))+'\n')
  counts={'count':0,'failed':1,'errors':0}
  if (folder/'gtest.xml').exists():
   xml=ET.parse(folder/'gtest.xml').getroot();counts={'count':int(xml.attrib['tests']),'failed':int(xml.attrib['failures']),'errors':int(xml.attrib.get('errors',0)),'disabled':int(xml.attrib.get('disabled',0))}
  result['tests'][t]={'returncode':rc,'binary_sha256':b['sha256'],**counts,'passed':rc==0 and counts['failed']==counts['errors']==0 and counts['count']>0}
 result['count']=sum(x['count'] for x in result['tests'].values());result['passed']=all(x['passed'] for x in result['tests'].values())
 verify(build['source_bundle']);write(out/'result.json',result);print(json.dumps(result));return result['passed']
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['build','test']);a.add_argument('--domain',type=int,default=121);x=a.parse_args();raise SystemExit(0 if (build() if x.mode=='build' else test(x.domain)) else 1)
