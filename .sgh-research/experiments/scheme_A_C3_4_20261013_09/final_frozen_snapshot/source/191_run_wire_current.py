#!/usr/bin/env python3
"""Six serialized bounded DDS scenarios, explicit component producer, no plant."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent
N=R.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
sys.path.insert(0,str(N))
from build_c34_v10 import sha,verify,dump
def main():
 b=next(x for x in json.loads((N/'build_manifest_current.json').read_text()) if x['role']=='observer')
 pin=b['native_binaries']['c34_lease_wire_component'];verify(b['component_source_bundle'],'observer_wire_component');assert sha(pin['path'])==pin['sha256']
 out=R/'C_lease/wire_matrix01';out.mkdir(exist_ok=False)
 dump(out/'preregister.json',{'binary':pin,'source_bundle':b['component_source_bundle'],'cases':['invalid_foreign','fatal','instance','expired','duplicate','no_valid'],
    'domain':122,'wire_budget_seconds':25,'source_producer':'explicitly seeded original-callback component; no Production Worker/native solver qualification',
    'GID_bytes':16,'stage_qualified':False,'resource_oversize_and_exact_timeout_equality_wire_covered':False})
 (out/'runner.snapshot').open('xb').write(Path(__file__).read_bytes());reports=[]
 env=dict(os.environ,ROS_DOMAIN_ID='122',ROS_LOCALHOST_ONLY='1',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
 for case in ['invalid_foreign','fatal','instance','expired','duplicate','no_valid']:
  folder=out/case;report=out/(case+'_report.json');start=time.monotonic();cmd=['timeout','--signal=TERM','--kill-after=5s','25s',pin['path'],str(folder),case]
  with (out/(case+'.log')).open('xb') as log:rc=subprocess.run(cmd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=35).returncode
  item={'case':case,'argv':cmd,'returncode':rc,'elapsed_seconds':time.monotonic()-start,'passed':False}
  if rc==0:
   check=[sys.executable,'-B',str(N/'check_lease_wire_v1.py'),'--run',str(folder),'--output',str(report)]
   with (out/(case+'_checker.log')).open('xb') as log:crc=subprocess.run(check,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=30).returncode
   item['checker_returncode']=crc;item['checker_report']=str(report)
   if report.exists():item['passed']=crc==0 and json.loads(report.read_text())['passed'] is True
  reports.append(item);dump(out/(case+'_execution.json'),item)
 assert sha(pin['path'])==pin['sha256'];verify(b['component_source_bundle'],'observer_wire_component')
 result={'schema':'p1-C3.4-real-wire-matrix/v1','passed':all(x['passed'] for x in reports),'cases':reports,'component_verification_only':True,'stage_qualified':False,'execute':False,'research_conclusion':False}
 dump(out/'result.json',result);print(json.dumps(result,sort_keys=True));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
