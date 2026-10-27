#!/usr/bin/env python3
"""Finite affected native policy and source-linked activation verification."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import xml.etree.ElementTree as ET

D=Path(__file__).resolve().parent
B=D/'build/m4_attempt02'


def pin(p):
    raw=p.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def main():
    build=json.loads((B/'build_manifest_v1.json').read_bytes());assert build['passed']
    root=D/'verification/components_v2';root.mkdir()
    setup_file=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(setup_file.read_bytes());setup=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in n.targets))
    setup+='\nexport ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n'
    setup+='\nexport P1_PAIR_TEST_OUTPUT='+shlex.quote(str(root/'source_linked_cases'))+'\n'
    paths=[Path(__file__).resolve(),B/'build_manifest_v1.json']+[Path(r['path']) for r in build['targets'].values()]
    before={str(p):pin(p) for p in paths}
    def run(name,argv,budget=120):
        script=root/(name+'.sh');script.write_text('set -e\n'+setup+'\nexec timeout --signal=TERM --kill-after=5s '+str(budget)+'s '+shlex.join(argv)+'\n')
        with (root/(name+'.stdout.log')).open('xb') as out,(root/(name+'.stderr.log')).open('xb') as err:
            result=subprocess.run(['/bin/bash',str(script)],stdout=out,stderr=err,timeout=budget+10)
        return {'command':argv,'returncode':result.returncode,'stdout':str(root/(name+'.stdout.log')),'stderr':str(root/(name+'.stderr.log'))}
    contract=D.parent/'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
    policy=run('native_policy',[str(B/'cmake_build/test_m4_native_policy'),str(contract)])
    parsed=json.loads(Path(policy['stdout']).read_bytes());assert parsed['case_count']==len(parsed['cases'])
    activation=run('source_linked_activation',[str(B/'cmake_build/test_m4_activation_alignment'),'--gtest_output=xml:'+str(root/'activation_gtest.xml')])
    xml=ET.parse(root/'activation_gtest.xml').getroot()
    tests=int(xml.attrib.get('tests','0'));failures=int(xml.attrib.get('failures','0'));errors=int(xml.attrib.get('errors','0'));disabled=int(xml.attrib.get('disabled','0'))
    after={p:pin(Path(p)) for p in before}
    report={'schema':'M4-affected-native-component-verification/v1','passed':policy['returncode']==0 and parsed['passed'] and activation['returncode']==0 and tests>0 and failures==errors==disabled==0 and before==after,
      'native_policy':policy,'native_policy_cases':parsed['case_count'],'native_policy_expected_results':parsed,
      'source_linked_activation':activation,'GTest_XML':{'path':str(root/'activation_gtest.xml'),**pin(root/'activation_gtest.xml'),'tests':tests,'failures':failures,'errors':errors,'disabled':disabled},
      'input_sha256_before':before,'input_sha256_after':after,'pure_policy_ROS_initialized':False,
      'activation_component_ROS_session':True,'actuator_publishers_or_API_calls':0,'actual_M4_business_runs':0,
      'M4_qualified':False,'P1_qualified':False,'research_conclusion':False}
    with (D/'verification/component_verification_v2.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'passed':report['passed'],'native_policy_cases':parsed['case_count'],'actual_GTest_cases':tests,'failures':failures,'errors':errors}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
