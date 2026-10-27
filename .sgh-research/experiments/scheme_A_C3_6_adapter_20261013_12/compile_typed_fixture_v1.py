#!/usr/bin/env python3
"""Compile separate corrected typed fixture without touching runtime bundle/CMake."""
from pathlib import Path
import json,shlex,subprocess,xml.etree.ElementTree as ET
import build_and_test_v2 as B
D,N=B.D,B.N
OUT=D/'component/atomic_typed_attempt01'
SOURCE=N/'component_fix/test_atomic_observation_typed_v1.cpp'
def main():
 OUT.mkdir(exist_ok=False);pin=json.loads((N/'source_bundles_current.json').read_text())['observer'];B.verify(pin)
 raw=SOURCE.read_bytes();(OUT/'test_atomic_observation_typed_v1.cpp.snapshot').write_bytes(raw)
 cmds=json.loads((N/'observer/build02/compile_commands.json').read_text());old=next(x for x in cmds if x['file'].endswith('/test_atomic_observation.cpp'))
 compiler=shlex.split(old['command']);obj=OUT/'fixture.o';binary=OUT/'test_atomic_observation_typed_v1'
 compiler[compiler.index('-o')+1]=str(obj);compiler[compiler.index('-c')+1]=str(SOURCE);compiler+=['-MMD','-MF',str(OUT/'fixture.d')]
 linker=shlex.split((N/'observer/build02/CMakeFiles/test_atomic_observation.dir/link.txt').read_text());linker[linker.index('-o')+1]=str(binary);linker=[str(obj) if x.endswith('test_atomic_observation.cpp.o') else x for x in linker]
 result={'schema':'C3.6-corrected-typed-native/v1','passed':False,'source':str(SOURCE),'source_sha256':B.sha(SOURCE),'runtime_bundle_unchanged':True,'runtime_source_bundle':pin,'preceding_failed_suite':str(D/'component/native_attempt01/test_atomic_observation/gtest.xml'),'source_compile_commands':str(N/'observer/build02/compile_commands.json'),'compiler_command':compiler,'linker_command':linker,'stage_qualified':False,'client_date':'2026-10-14'}
 try:
  def cmd(name,args,seconds):
   script=OUT/(name+'.sh');script.write_text('set -e\n'+B.SETUP+'cd '+shlex.quote(old['directory'])+'\nexec timeout --signal=TERM --kill-after=5s '+str(seconds)+'s '+shlex.join(args)+'\n')
   with (OUT/(name+'.log')).open('xb') as log:return subprocess.run(['bash',str(script)],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=seconds+10).returncode
  result['compile_returncode']=cmd('compile',compiler,180);assert result['compile_returncode']==0
  result['link_returncode']=cmd('link',linker,30);assert result['link_returncode']==0
  deps={}
  for x in shlex.split((OUT/'fixture.d').read_text().replace('\\\n',' ').split(':',1)[1]):
   p=Path(x)
   if p.is_absolute() and p.is_file():p=p.resolve();deps[str(p)]=B.sha(p)
  result['actual_dependency_pins']=deps;result['binary']=str(binary);result['binary_sha256']=B.sha(binary)
  branch=OUT/'branch';branch.mkdir()
  result['run_returncode']=B.command(OUT,'run',[str(binary),'--gtest_output=xml:'+str(OUT/'gtest.xml')],60,121,'export P1_BRANCH_TEST_OUTPUT='+shlex.quote(str(branch))+'\n')
  xml=ET.parse(OUT/'gtest.xml').getroot();result.update(count=int(xml.attrib['tests']),failed=int(xml.attrib['failures']),errors=int(xml.attrib.get('errors',0)))
  assert result['run_returncode']==0 and result['count']==12 and result['failed']==result['errors']==0
  B.verify(pin);assert B.sha(SOURCE)==result['source_sha256'];result['passed']=True
 except BaseException as e:result['error']=repr(e)
 B.write(OUT/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='actual_dependency_pins'}));return result['passed']
if __name__=='__main__':raise SystemExit(0 if main() else 1)
