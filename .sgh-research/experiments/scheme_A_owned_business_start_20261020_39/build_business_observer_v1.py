#!/usr/bin/env python3
"""Freeze, build and test only the V3 Observer and source-linked activation target."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
A=D/'author'
P=D.parent/'scheme_A_activation_alignment_20261019_28'
spec=importlib.util.spec_from_file_location('sealed_activation_build_utilities',P/'build_activation_roles_v1.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
RUNTIME='p1_regulator_shadow_observer_owned_v2'
NATIVE='test_reference_activation_alignment'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=int,required=True);arg=ap.parse_args()
    B.require(1<=arg.attempt<=3,'initial build plus at most two repairs')
    out=D/'build'/('business_observer_attempt'+str(arg.attempt).zfill(2));out.mkdir()
    build=out/'cmake_build';(out/'native_callback_output').mkdir()
    result=dict(schema='owned-business-start-build/v1',passed=False,role='observer',new_runtime_ROS_run=False,
                native_local_rclcpp_context=True,native_seeded_ticket_RTF_lease_readiness=True,
                native_actuator_Writers=0,install=False,codegen=False,stage_qualified=False,
                execute_qualified=False,research_conclusion=False)
    start=time.monotonic();files={}
    try:
        inv=json.loads((P/'archive_inventory_v1.json').read_bytes())
        pin=next(x for x in inv['files'] if x['relative_path']=='build_activation_roles_v1.py')
        B.require(B.sha(P/'build_activation_roles_v1.py')==pin['sha256'],'sealed build utility')
        selected=[p for root in [A/'observer',A/'common'] for p in root.rglob('*') if p.is_file()]
        selected += [A/'phase_protocol.hpp',A/'pair_wakeup_contract_v1.json']
        files={str(p.relative_to(A)):B.pin(p) for p in sorted(selected)}
        for rel,row in files.items():B.snapshot(row['path'],out/'source_snapshot'/rel)
        descriptor=dict(schema='owned-business-start-source-bundle/v1',author_directory=str(A),files=files,
            frozen_before_configure=True,parent_registry=B.pin(D/'preregister/parent_build_manifest_current.json'),
            contract=B.pin(A/'pair_wakeup_contract_v1.json'),unused_parent_tests_not_claimed=True,
            stage_qualified=False,execute_qualified=False)
        B.write(out/'source_bundle_bootstrap.json',descriptor)
        configure=['cmake','-S',str(A/'observer'),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3',
            '-DP1_OWNED_SOURCE_BUNDLE_SHA256='+B.sha(out/'source_bundle_bootstrap.json')]
        result['bootstrap_configure_rc']=B.command(out,'bootstrap_configure',configure,30,files)
        B.require(result['bootstrap_configure_rc']==0,'bootstrap configure')
        static=B.static_link_inputs_before(build,out)
        descriptor['static_link_inputs_before']=B.pin(out/'static_link_inputs_before.json')
        B.write(out/'source_bundle.json',descriptor);identity=B.sha(out/'source_bundle.json')
        configure[-1]='-DP1_OWNED_SOURCE_BUNDLE_SHA256='+identity
        result['configure_rc']=B.command(out,'configure',configure,30,files)
        B.require(result['configure_rc']==0,'configure')
        B.verify_static_link_inputs(static)
        result['build_rc']=B.command(out,'build',['cmake','--build',str(build),'--parallel','2'],180,files)
        B.require(result['build_rc']==0,'two target build')
        result['Native_rc']=B.command(out,'native',[str(build/NATIVE),'--gtest_output=xml:'+str(out/'native_results.xml')],45,files)
        B.require(result['Native_rc']==0,'source-linked activation Native')
        import xml.etree.ElementTree as ET
        xml=ET.parse(out/'native_results.xml').getroot()
        B.require(int(xml.attrib['tests'])>=38 and int(xml.attrib['failures'])==int(xml.attrib['errors'])==0,'finite Native table')
        result['Native_cases']=int(xml.attrib['tests'])
        commands=json.loads((build/'compile_commands.json').read_bytes())
        runtime=build/RUNTIME
        B.require(identity.encode() in runtime.read_bytes() and len(commands)>=2,'runtime ELF identity and target closure')
        B.require(all(identity in c['command'] for c in commands if c['file'].endswith('regulator_shadow_observer.cpp')),'actual runtime compile identity')
        result['compiler_dependencies']=B.dependencies(build,out)
        result['runtime_libraries']=B.runtime_libraries(runtime,out,files)
        B.verify_static_link_inputs(static)
        B.write(out/'static_link_inputs_after.json',dict(passed=True,same_before_after=True,
            before_sha256=B.sha(out/'static_link_inputs_before.json'),files=static['files']))
        original=D.parent/'scheme_A_V2_supervisor_bridge_20261019_36/author/observer/src/shadow'
        for n in ['activation_sensor_history_v1.hpp','p1_admission.hpp','p1_full_contract.hpp','protocol.hpp','p1_shadow_entry.hpp']:
            B.require(B.sha(A/'observer/src/shadow'/n)==B.sha(original/n),'unchanged original activation gate:'+n)
        source=(A/'observer/src/shadow/regulator_shadow_observer.cpp').read_text()
        B.require('if(mode_!="execute")return;' in source,'execute publisher branch still unreachable')
        result.update(passed=True,source_bundle=dict(path=str(out/'source_bundle.json'),sha256=identity,files=len(files)),
            binary=str(runtime),binary_sha256=B.sha(runtime),native_binary=B.pin(build/NATIVE),
            runtime_target=RUNTIME,inherited_all_matrix_qualification=False)
    except BaseException as e:
        result.update(error=repr(e),traceback=__import__('traceback').format_exc())
    result['source_unchanged']=B.unchanged(files) if files else False
    result['elapsed_seconds']=time.monotonic()-start
    result['passed']=bool(result['passed'] and result['source_unchanged'])
    B.write(out/'result.json',result)
    print(json.dumps({k:result.get(k) for k in ['passed','error','Native_cases','elapsed_seconds','binary_sha256']}))
    return 0 if result['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
