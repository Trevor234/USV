#!/usr/bin/env python3
"""Resume verified unchanged partial build; preserve aggregate-timeout attempt01."""
import json,subprocess,time,sys
from pathlib import Path
R=Path(__file__).resolve().parent
N=R.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
sys.path.insert(0,str(N))
from build_c34_v10 import sha,verify,parent_verify,SETUP,dump
import shlex
def main():
 old=json.loads((R/'build/observer01/result.json').read_text());assert old['runtime_build_rc']==0 and old['native_build_rc']==124
 out=R/'build/observer02';out.mkdir(exist_ok=False);start=time.monotonic();pin=old['source_bundle'];verify(pin,'observer');parent_verify()
 build=N/'observer/build01';binary=build/'p1_regulator_shadow_observer_owned_v2';binary_before=sha(binary)
 tests=['test_shadow_entry','test_enqueue_branch','test_d0_observation','test_atomic_observation','test_legacy_ready','test_c33_input_matrix','test_c34_lease_matrix','c34_lease_wire_component']
 result={**old,'schema':'p1-C3.4-verified-partial-build-completion/v1','passed':False,
         'previous_attempt':str(R/'build/observer01/result.json'),'previous_native_build_rc':124,
         'reuse':'unchanged source pin and actual successful runtime binary; cached incomplete native objects; no expected change',
         'native_commands':[]}
 try:
  for test in tests:
   if (build/test).exists():continue
   cmd=['cmake','--build',str(build),'--target',test,'-j2'];script=out/(test+'.sh')
   script.open('x').write('set -e\n'+SETUP+'exec timeout --signal=TERM --kill-after=10s 180s '+shlex.join(cmd)+'\n')
   with (out/(test+'.log')).open('xb') as log:rc=subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=195).returncode
   result['native_commands'].append({'target':test,'returncode':rc,'budget_seconds':180})
   if rc:raise RuntimeError(test+' failed: '+str(rc))
  verify(pin,'observer');parent_verify();assert sha(binary)==binary_before
  result.update(passed=True,error=None,build_rc=0,native_build_rc=0,binary=str(binary),binary_sha256=sha(binary),
                native_binaries={t:{'path':str(build/t),'sha256':sha(build/t)} for t in tests},
                native_binary=str(build/'test_c33_input_matrix'),native_binary_sha256=sha(build/'test_c33_input_matrix'),parent_roles_verified_unchanged=True)
 except Exception as e:result['error']=repr(e)
 result['elapsed_seconds']=time.monotonic()-start;dump(out/'result.json',result);print(json.dumps(result,sort_keys=True));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
