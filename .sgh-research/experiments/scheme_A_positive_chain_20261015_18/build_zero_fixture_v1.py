#!/usr/bin/env python3
"""Build the explicitly new zero-reference fixture; never launch/install/codegen."""
from pathlib import Path
import hashlib,json,shlex,subprocess,sys,time,xml.etree.ElementTree as ET
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_positive_chain_20261015_v18'
P=N.parent/'authored_D1_C3_4_20261013_v10'
sys.path.insert(0,str(N))
from build_c33_v9 import SETUP
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
 with Path(p).open('x') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def main():
 out=D/'build/fixture_attempt01';out.mkdir(parents=True,exist_ok=False)
 b=N/'fixture/build01';assert not b.exists()
 old_path=P/'fixture_source_bundle_C3_4_v1.json'
 assert sha(old_path)=='f092c4205f4fbf69cfba48fb4c8ebc4a5fe5882a74372ef18dd15cb1e707be71'
 old=json.loads(old_path.read_text())
 assert all(sha(item['path'])==item['sha256'] for item in old['files'].values())
 paths=[N/'common/p1_create_only_atomic.hpp',N/'common/p1_owned_identity.hpp']
 paths += [p for p in sorted((N/'fixture').rglob('*')) if p.is_file() and not any(part.startswith('build') for part in p.relative_to(N/'fixture').parts)]
 files={str(p.relative_to(N)):{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths}
 descriptor=N/'fixture_source_bundle_positive_chain_v1.json'
 write(descriptor,{'schema':'p1-positive-chain-fixture-source/v1','role':'fixture','files':files,
       'parent_source_bundle':{'path':str(old_path),'sha256':sha(old_path),'files':len(old['files'])},
       'reference_kind':'stationary_zero_equilibrium','reference_speed_m_s':0.0,
       'stage_qualified':False,'execute_qualified':False,'research_conclusion':False})
 pin={'path':str(descriptor),'sha256':sha(descriptor),'files':len(files)}
 result={'schema':'p1-positive-chain-zero-fixture-build/v1','role':'fixture','author_directory':str(N),
         'build_directory':str(b),'source_bundle':pin,'passed':False,'node_launch_performed':False,
         'install_performed':False,'codegen_performed':False,'stage_qualified':False,'execute_qualified':False,
         'research_conclusion':False,'reference_kind':'stationary_zero_equilibrium','reference_speed_m_s':0.0,
         'recipe_sha256':sha(__file__),'setup_helper_sha256':sha(N/'build_c33_v9.py')}
 snapshot=out/'source_snapshot';snapshot.mkdir()
 for rel,item in files.items():
  dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  dest.open('xb').write(Path(item['path']).read_bytes());assert sha(dest)==item['sha256']
 for p in [Path(__file__),N/'build_c33_v9.py',descriptor]:(out/(p.name+'.snapshot')).open('xb').write(p.read_bytes())
 def run(name,argv,budget):
  script=out/(name+'.sh');script.open('x').write('set -e\n'+SETUP+'exec timeout --signal=TERM --kill-after=5s '+str(budget)+'s '+shlex.join(argv)+'\n')
  with (out/(name+'.log')).open('xb') as log:
   return subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=budget+10).returncode
 started=time.monotonic()
 try:
  result['configure_rc']=run('configure',['cmake','-S',str(N/'fixture'),'-B',str(b),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3','-DP1_OWNED_SOURCE_BUNDLE_SHA256='+pin['sha256']],90)
  assert result['configure_rc']==0,'configure failed'
  result['default_build_rc']=run('default_build',['cmake','--build',str(b),'-j2'],240)
  assert result['default_build_rc']==0,'default build failed'
  targets={target:{'path':str(b/target),'sha256':sha(b/target),'bytes':(b/target).stat().st_size} for target in ['p1_synthetic_source','test_zero_reference']}
  result['produced_target_pins']=targets
  xml=out/'gtest.xml'
  result['finite_native_rc']=run('finite_native',[str(b/'test_zero_reference'),'--gtest_output=xml:'+str(xml)],30)
  assert result['finite_native_rc']==0,'finite native failed'
  root=ET.parse(xml).getroot();result['native_tests']={k:int(root.attrib.get(k,0)) for k in ['tests','failures','disabled','errors']}
  assert result['native_tests']['tests']==6 and all(result['native_tests'][k]==0 for k in ['failures','disabled','errors'])
  deps={}
  for f in b.rglob('*.o.d'):
   for token in shlex.split(f.read_text().replace('\\\n',' ').split(':',1)[1]):
    p=Path(token);p=p if p.is_absolute() else b/p
    if p.is_file():deps[str(p.resolve())]=sha(p)
  assert len(deps)>0
  write(out/'compiler_dependency_pins.json',{'schema':'p1-positive-chain-actual-fixture-compiler-dependencies/v1','files':deps,'dependency_count':len(deps),'compile_commands_sha256':sha(b/'compile_commands.json'),'compiler_sha256':sha(Path('/usr/bin/c++').resolve())})
  (out/'compile_commands.json').open('xb').write((b/'compile_commands.json').read_bytes())
  result.update(binary=targets['p1_synthetic_source']['path'],binary_sha256=targets['p1_synthetic_source']['sha256'],
                native_binary=targets['test_zero_reference']['path'],native_binary_sha256=targets['test_zero_reference']['sha256'],
                native_binaries={'test_zero_reference':targets['test_zero_reference']},build_rc=0,runtime_build_rc=0,
                native_build_rc=0,passed=True,actual_compiler_dependencies=len(deps))
 except BaseException as e:result['error']=repr(e)
 result['elapsed_seconds']=time.monotonic()-started
 result['source_content_unchanged']=all(sha(item['path'])==item['sha256'] for item in files.values())
 result['parent_source_content_unchanged']=all(sha(item['path'])==item['sha256'] for item in old['files'].values()) and sha(old_path)=='f092c4205f4fbf69cfba48fb4c8ebc4a5fe5882a74372ef18dd15cb1e707be71'
 assert result['source_content_unchanged'] and result['parent_source_content_unchanged']
 write(out/'result.json',result)
 print(json.dumps({k:v for k,v in result.items() if k!='produced_target_pins'},sort_keys=True))
 return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
