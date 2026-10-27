#!/usr/bin/env python3
"""Finish one timed-out compiler target, retaining the original failure."""
from pathlib import Path
import argparse,json,shlex,subprocess,xml.etree.ElementTree as ET
import build_and_test_v2 as B
N,D=B.N,B.D
OUT=D/'build/observer_attempt02_completion01'
FINAL=OUT/'result.json'
def finish():
 OUT.mkdir(exist_ok=False)
 old=json.loads((D/'build/observer_attempt02/result.json').read_text());assert old['build_rc']==124 and not old['passed'];B.verify(old['source_bundle'])
 result={**old,'schema':'C3.6-adapter-build-completion/v1','passed':False,'preceding_failed_build':str(D/'build/observer_attempt02/result.json'),'preceding_build_returncode':124,'bounded_completion_budget_s':180}
 try:
  bd=N/'observer/build02';result['completion_build_rc']=B.command(OUT,'complete_last_target',['cmake','--build',str(bd),'--target','test_c34_lease_matrix','-j2'],180);assert result['completion_build_rc']==0
  B.verify(old['source_bundle'])
  binaries={t:{'path':str(bd/t),'sha256':B.sha(bd/t),'bytes':(bd/t).stat().st_size} for t in B.TARGETS}
  result.update(binary=str(bd/B.TARGETS[0]),binary_sha256=B.sha(bd/B.TARGETS[0]),native_binaries={k:v for k,v in binaries.items() if k.startswith('test_')},runtime_build_rc=0,native_build_rc=0,build_rc=0)
  deps={}
  for f in bd.rglob('*.o.d'):
   for token in shlex.split(f.read_text().replace('\\\n',' ').split(':',1)[1]):
    p=Path(token)
    if p.is_absolute() and p.is_file():p=p.resolve();deps[str(p)]=B.sha(p)
  B.write(OUT/'compiler_dependency_pins.json',{'compiler':str(Path('/usr/bin/c++').resolve()),'compiler_sha256':B.sha(Path('/usr/bin/c++').resolve()),'compile_commands_sha256':B.sha(bd/'compile_commands.json'),'dependency_count':len(deps),'files':deps,'scope':'compiler-reported file contents; no complete OS/toolchain/WCET qualification'})
  (OUT/'compile_commands.json').write_bytes((bd/'compile_commands.json').read_bytes());result['passed']=True
 except BaseException as e:result['error']=repr(e)
 B.write(FINAL,result);print(json.dumps(result));return result['passed']
def test(domain):
 out=D/'component/native_attempt01';out.mkdir(exist_ok=False)
 build=json.loads(FINAL.read_text());assert build['passed'];B.verify(build['source_bundle'])
 result={'schema':'C3.6-adapter-native/v1','passed':False,'domain':domain,'actual_DDS_same_payload_peer_test':True,'tests':{},'stage_qualified':False,'build_result':str(FINAL)}
 for t,b in build['native_binaries'].items():
  assert B.sha(b['path'])==b['sha256'];folder=out/t;folder.mkdir();branch=folder/'branch';branch.mkdir()
  rc=B.command(folder,'run',[b['path'],'--gtest_output=xml:'+str(folder/'gtest.xml')],90,domain,'export P1_BRANCH_TEST_OUTPUT='+shlex.quote(str(branch))+'\n')
  counts={'count':0,'failed':1,'errors':0}
  if (folder/'gtest.xml').exists():
   xml=ET.parse(folder/'gtest.xml').getroot();counts={'count':int(xml.attrib['tests']),'failed':int(xml.attrib['failures']),'errors':int(xml.attrib.get('errors',0)),'disabled':int(xml.attrib.get('disabled',0))}
  result['tests'][t]={'returncode':rc,'binary_sha256':b['sha256'],**counts,'passed':rc==0 and counts['failed']==counts['errors']==0 and counts['count']>0}
 result['count']=sum(x['count'] for x in result['tests'].values());result['passed']=all(x['passed'] for x in result['tests'].values());B.verify(build['source_bundle']);B.write(out/'result.json',result);print(json.dumps(result));return result['passed']
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['finish','test']);a.add_argument('--domain',type=int,default=121);x=a.parse_args();raise SystemExit(0 if (finish() if x.mode=='finish' else test(x.domain)) else 1)
