#!/usr/bin/env python3
"""Preregister and execute actual source-linked constructors in isolated DDS198."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

D=Path(__file__).resolve().parent.parent


def pin(path):
    b=Path(path).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def create(path,value):
    with path.open('x') as f:json.dump(value,f,sort_keys=True,indent=2);f.write('\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);a=p.parse_args()
    build=json.loads((a.build/'build_result_v1.json').read_text());assert build['passed']
    assert os.environ['ROS_DOMAIN_ID']=='198'
    source_bundle=json.loads(Path(build['source_bundle']['path']).read_text())
    for r in source_bundle['files'].values():assert pin(r['path'])['sha256']==r['sha256']
    root=D/'verification/constructor_cases_v2';root.mkdir()
    pre=json.loads((D/'author/formal_pre_freeze_contract_v1.json').read_text());profiles={}
    def profile(label,value):
        q=root/(label+'.json');create(q,value);profiles[label]=q;return q
    profile('pre',pre)
    old=D.parent/'scheme_A_B5_contract_parity_20261020_44/implementation/current_diag_contract_v1.json'
    profile('diagnostic',json.loads(old.read_text()))
    frozen=dict(pre);frozen.update(qualification='execution_frozen',execute_qualified=True,parameters_are_diagnostic_only=False,
        pending_final_calibration=[],freeze_evidence_sha256='a'*64);profile('Frozen',frozen)
    x=dict(pre);x['fault_injection_enabled']=True;profile('fault_true',x)
    x=dict(pre);x['execute_qualified']=True;profile('execute_flag',x)
    x=dict(pre);x.pop('N');profile('missing_field',x)
    specs=[('wrong_mode_shadow','pre','shadow',[],None,'only no_output entry permitted'),
           ('wrong_mode_execute','pre','execute',[],None,'only no_output entry permitted'),
           ('diagnostic_cannot_promote','diagnostic','no_output',[],None,'pre-freeze only'),
           ('Frozen_cannot_promote','Frozen','no_output',[],None,'pre-freeze only'),
           ('fault_permission_prohibited','fault_true','no_output',[],None,'formal fault injection prohibited'),
           ('execute_flag_prohibited','execute_flag','no_output',[],None,'pre-freeze qualification flags'),
           ('exact_fields_required','missing_field','no_output',[],None,'missing or unknown'),
           ('bad_input_SHA','pre','no_output',[],'b'*64,'formal contract SHA mismatch'),
           ('no_ready_override','pre','no_output',['-p','fake_ready:=true'],None,'unknown formal startup override'),
           ('no_topic_remapping','pre','no_output',['-r','/clock:=/wamv/thrusters/left/thrust'],None,'formal remapping forbidden'),
           ('good_contract_needs_actual_pins','pre','no_output',[],None,'manifest_path')]
    commands=[]
    for role in ['fixture','preparer']:
        binary=build['roles'][role]['binary'];assert pin(binary)['sha256']==build['roles'][role]['binary_sha256']
        for label,which,mode,extra,override,error in specs:
            case=root/(role+'_'+label);case.mkdir()
            argv=[binary,'--ros-args','-p','run_id:=ctor45','-p','contract_file:='+str(profiles[which]),
                  '-p','contract_hash:='+(override or pin(profiles[which])['sha256']),'-p','mode:='+mode,
                  '-p','output_dir:='+str(case),*extra]
            commands.append({'role':role,'name':label,'argv':argv,'expected_returncode':2,'expected_error':error,'output':str(case)})
    registration={'schema':'formal-constructor-registration-v1','registered_ns':time.monotonic_ns(),'DDS_domain':198,
      'source_bundle':build['source_bundle'],'cases':commands,'new_control_publishers_permitted':0,
      'role_ROS_contexts':len(commands),'full_four_role_sessions':0,'stage_qualified':False,'execute_qualified':False}
    create(D/'preflight/constructor_registration_v2.json',registration)
    rows=[];started=time.monotonic()
    for case in commands:
        assert time.monotonic()-started<60
        result=subprocess.run(case['argv'],capture_output=True,timeout=4)
        (Path(case['output'])/'stdout.log').write_bytes(result.stdout)
        (Path(case['output'])/'stderr.log').write_bytes(result.stderr)
        rows.append({**case,'returncode':result.returncode,'stderr':result.stderr.decode(errors='replace'),
            'passed':result.returncode==case['expected_returncode'] and case['expected_error'] in result.stderr.decode(errors='replace')
                     and not (Path(case['output'])/'manifest.json').exists() and not (Path(case['output'])/'source.jsonl').exists()})
    report={'schema':'formal-actual-constructor-checks-v1','passed':all(r['passed'] for r in rows),'case_count':len(rows),
            'cases':rows,'elapsed_seconds':time.monotonic()-started,'full_ROS_sessions':0,'constructors_initialized_ROS_context':True,
            'stage_qualified':False,'execute_qualified':False}
    create(D/'verification/constructor_checks_v2.json',report)
    print(json.dumps({'passed':report['passed'],'cases':len(rows),'failed':[r['role']+':'+r['name'] for r in rows if not r['passed']],'elapsed_seconds':report['elapsed_seconds']}))
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
