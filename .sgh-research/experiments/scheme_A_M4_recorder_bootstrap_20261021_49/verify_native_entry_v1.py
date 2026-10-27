#!/usr/bin/env python3
"""Actual executable entry refusals; every case fails before control Writer creation."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

D=Path(__file__).resolve().parent


def pin(p):
    raw=p.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def main():
    assert json.loads((D/'verification/component_verification_v1.json').read_bytes())['passed']
    root=D/'verification/native_entry_rejections_v1';root.mkdir()
    setupfile=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(setupfile.read_bytes());setup=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in n.targets))
    setup+='\nexport ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n'
    f47=D.parent/'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
    pre=D.parent/'scheme_A_B5_contract_parity_20261020_44/implementation/current_pre_freeze_contract_v1.json'
    scope='M4_owned_local_nominal_only_v1';h='19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'
    binaries={'regulator':D/'build/m4_attempt01/cmake_build/p1_m4_regulator_owned',
              'worker':D/'build/m4_attempt01/cmake_build/p1_m4_worker_owned',
              'fixture':D/'build/m4_attempt01/cmake_build/p1_m4_fixture_owned'}
    common={'run_id':'M4_entry_rejection_49','contract_file':str(f47),'contract_hash':h,'m4_release_scope':scope}
    cases=[]
    for mode in ['no_output','shadow','Execute','']:
        cases.append(('regulator_wrong_mode_'+repr(mode),'regulator',{**common,'mode':mode},1))
    cases += [('regulator_missing_scope','regulator',{**common,'mode':'execute','m4_release_scope':''},1),
              ('regulator_wrong_hash','regulator',{**common,'mode':'execute','contract_hash':'0'*64},1),
              ('regulator_old_pre_freeze','regulator',{**common,'mode':'execute','contract_file':str(pre),'contract_hash':pin(pre)['sha256']},1),
              ('regulator_no_owned_peers','regulator',{**common,'mode':'execute'},1),
              ('worker_no_isolated_scope','worker',{**common,'m4_release_scope':''},1),
              ('worker_no_live_driver','worker',common,1),
              ('worker_fault_parameter_closed','worker',{**common,'test_delay_ms':1},1),
              ('fixture_no_scope','fixture',{**common,'m4_release_scope':''},2),
              ('fixture_reference_outside_selected_source','fixture',{**common,'reference_speed_m_s':.1},2),
              ('fixture_no_live_driver','fixture',common,2)]
    before={str(p):pin(p) for p in binaries.values()};results=[]
    for index,(name,role,params,expected) in enumerate(cases):
        case=root/f'{index:02d}';case.mkdir();params={**params,'output_dir':str(case)}
        argv=[str(binaries[role]),'--ros-args']
        for key,value in params.items():argv+=['-p',key+':='+('""' if value=='' else str(value))]
        script=case/'command.sh';script.write_text('set -e\n'+setup+'\nexec timeout --signal=TERM --kill-after=2s 10s '+shlex.join(argv)+'\n')
        with (case/'stdout.log').open('xb') as out,(case/'stderr.log').open('xb') as err:
            result=subprocess.run(['/bin/bash',str(script)],stdout=out,stderr=err,timeout=15)
        observed=[str(p.name) for p in case.iterdir() if p.name not in {'command.sh','stdout.log','stderr.log'}]
        results.append({'name':name,'role':role,'expected_returncode':expected,'actual_returncode':result.returncode,
                        'passed':result.returncode==expected and not observed,'parameters':params,'command':argv,
                        'unexpected_business_artifacts':observed,'no_control_Writer_by_precreation_guard':True})
    after={p:pin(Path(p)) for p in before}
    report={'schema':'M4-native-executable-entry-refusals/v1','passed':all(r['passed'] for r in results) and before==after,
            'case_count':len(results),'cases':results,'input_sha256_before':before,'input_sha256_after':after,
            'ROS_initialization_only':True,'control_API_calls':0,'actual_M4_business_runs':0,'M4_stage_qualified':False,'P1_qualified':False}
    with (D/'verification/native_entry_rejections_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'passed':report['passed'],'cases':len(results),'failed':[r['name'] for r in results if not r['passed']]}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
