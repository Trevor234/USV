#!/usr/bin/env python3
"""Fresh bounded source-linked native component tests; loopback ROS only."""
import hashlib,json,os,subprocess,time
from pathlib import Path
import xml.etree.ElementTree as ET
R=Path(__file__).resolve().parent
N=R.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(role):
 attempt=role+'03' if role=='observer' else role+'01'
 b=json.loads((R/'build'/attempt/'result.json').read_text());assert b['passed'] is True
 out=R/'D_IO'/('native_'+role+'01');out.mkdir(exist_ok=False)
 (out/'runner.snapshot').open('xb').write(Path(__file__).read_bytes())
 reports=[]
 for name,pin in b['native_binaries'].items():
  if name=='c34_lease_wire_component':continue
  assert sha(pin['path'])==pin['sha256'];folder=out/name;folder.mkdir()
  env=dict(os.environ,P1_BRANCH_TEST_OUTPUT=str(folder),P1_C34_LEASE_NATIVE_DIR=str(folder/'lease_source'),ROS_DOMAIN_ID='121',ROS_LOCALHOST_ONLY='1',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
  xml=folder/'gtest.xml';start=time.monotonic()
  try:
   with (folder/'stdout.log').open('xb') as log:
    rc=subprocess.run(['timeout','--signal=TERM','--kill-after=5s','60s',pin['path'],'--gtest_output=xml:'+str(xml)],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=70).returncode
  except subprocess.TimeoutExpired:rc=124
  values={'name':name,'binary':pin,'returncode':rc,'elapsed_seconds':time.monotonic()-start,'xml_present':xml.exists(),'passed':False}
  if xml.exists():
   tree=ET.parse(xml).getroot();values.update(tests=int(tree.attrib['tests']),failures=int(tree.attrib['failures']),disabled=int(tree.attrib.get('disabled',0)),errors=int(tree.attrib.get('errors',0)))
   values['passed']=rc==0 and values['tests']>0 and values['failures']==0 and values['errors']==0
  assert sha(pin['path'])==pin['sha256'];reports.append(values)
 result={'schema':'scheme-A-C3.4-native-current/v1','role':role,'reports':reports,'passed':all(x['passed'] for x in reports),
         'tests':sum(x.get('tests',0) for x in reports),'scope':'source-linked native components; no owned whole graph/storage certification',
         'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 with (out/'result.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps(result,sort_keys=True));return 0 if result['passed'] else 1
if __name__=='__main__':
 import sys
 raise SystemExit(main(sys.argv[1]))
