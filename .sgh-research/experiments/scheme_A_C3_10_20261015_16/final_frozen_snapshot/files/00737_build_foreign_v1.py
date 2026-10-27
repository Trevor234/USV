#!/usr/bin/env python3
"""Fresh independent native diagnostic producer build; never installs/launches."""
from pathlib import Path
import hashlib,json,shlex,subprocess,sys,time,xml.etree.ElementTree as ET
D=Path(__file__).resolve().parent
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_10_20261015_v17'
sys.path.insert(0,str(N))
from build_c33_v9 import SETUP
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
 with Path(p).open('x') as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
 out=D/'build/foreign_attempt01';out.mkdir(parents=True,exist_ok=False);b=N/'foreign/build01';assert not b.exists()
 files={str(p.relative_to(N)):{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted((N/'foreign').rglob('*')) if p.is_file()}
 descriptor=N/'foreign_source_bundle_C310_v1.json';write(descriptor,{'schema':'p1-C3.10-independent-source-bundle/v1','role':'foreign','files':files,'stage_qualified':False,'execute_qualified':False})
 pin={'path':str(descriptor),'sha256':sha(descriptor),'files':len(files)}
 result={'schema':'p1-C3.10-independent-foreign-build/v1','role':'foreign','author_directory':str(N),'build_directory':str(b),'source_bundle':pin,'passed':False,'node_launch_performed':False,'install_performed':False,'codegen_performed':False,'stage_qualified':False,'execute_qualified':False,'recipe_sha256':sha(__file__),'setup_helper_sha256':sha(N/'build_c33_v9.py')}
 snapshot=out/'source_snapshot';snapshot.mkdir()
 for rel,item in files.items():
  dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.open('xb').write(Path(item['path']).read_bytes());assert sha(dest)==item['sha256']
 for p in [Path(__file__),N/'build_c33_v9.py',descriptor]:(out/(p.name+'.snapshot')).open('xb').write(p.read_bytes())
 def run(name,argv,seconds):
  s=out/(name+'.sh');s.open('x').write('set -e\n'+SETUP+'exec timeout --signal=TERM --kill-after=5s '+str(seconds)+'s '+shlex.join(argv)+'\n')
  with (out/(name+'.log')).open('xb') as log:return subprocess.run(['bash',str(s)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=seconds+10).returncode
 started=time.monotonic()
 try:
  rc=run('configure',['cmake','-S',str(N/'foreign'),'-B',str(b),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3','-DP1_OWNED_SOURCE_BUNDLE_SHA256='+pin['sha256']],90);result['configure_rc']=rc;assert rc==0,'configure failed'
  rc=run('default_build',['cmake','--build',str(b),'-j2'],240);result['default_build_rc']=rc;assert rc==0,'default build failed'
  for target in ['p1_c310_foreign_applied','test_c310_foreign_protocol']:result[target]={'path':str(b/target),'sha256':sha(b/target),'bytes':(b/target).stat().st_size}
  xml=out/'gtest.xml';rc=run('finite_native',[str(b/'test_c310_foreign_protocol'),'--gtest_output=xml:'+str(xml)],60);result['finite_native_rc']=rc;assert rc==0,'finite protocol native tests failed'
  root=ET.parse(xml).getroot();result['native_tests']={k:int(root.attrib.get(k,0)) for k in ['tests','failures','disabled','errors']};assert result['native_tests']['tests']>0 and all(result['native_tests'][k]==0 for k in ['failures','errors','disabled'])
  deps={}
  for f in b.rglob('*.o.d'):
   for token in shlex.split(f.read_text().replace('\\\n',' ').split(':',1)[1]):
    p=Path(token);p=p if p.is_absolute() else b/p
    if p.is_file():deps[str(p.resolve())]=sha(p)
  write(out/'compiler_dependency_pins.json',{'schema':'p1-C3.10-actual-foreign-compiler-dependencies/v1','files':deps,'dependency_count':len(deps),'compile_commands_sha256':sha(b/'compile_commands.json'),'compiler_sha256':sha(Path('/usr/bin/c++').resolve())})
  (out/'compile_commands.json').open('xb').write((b/'compile_commands.json').read_bytes())
  result.update(binary=str(b/'p1_c310_foreign_applied'),binary_sha256=sha(b/'p1_c310_foreign_applied'),passed=True,actual_compiler_dependencies=len(deps))
 except BaseException as e:result['error']=repr(e)
 result['elapsed_seconds']=time.monotonic()-started
 result['source_content_unchanged']=all(sha(i['path'])==i['sha256'] for i in files.values());assert result['source_content_unchanged']
 write(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ['source_bundle']},sort_keys=True));return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
