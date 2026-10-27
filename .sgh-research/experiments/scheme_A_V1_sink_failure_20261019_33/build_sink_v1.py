#!/usr/bin/env python3
"""Fresh source freeze, explicit link inputs, two targets and one pure Native test."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import time

D=Path(__file__).resolve().parent
P=D.parent/'scheme_A_deferred_observation_20261019_29'
A=D.parent/'p1_execution_architecture_20261005_01/authored_D1_V1_sink_failure_20261019_v33'
spec=importlib.util.spec_from_file_location('pinned_build_utilities',P/'build_deferred_observer_v1.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
RUNTIME='p1_regulator_shadow_observer_owned_v2'
NATIVE='test_v1_sink_queue'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=int,required=True);a=ap.parse_args()
    B.require(1<=a.attempt<=3,'initial build plus at most two repairs')
    out=D/'build'/('publication_attempt'+str(a.attempt).zfill(2));out.mkdir()
    build=out/'cmake_build';(out/'native_callback_output').mkdir()
    start=time.monotonic();result=dict(schema='publication-component-build/v1',passed=False,
        new_ROS_node_launch=False,Native_ROS_context_created=False,install=False,codegen=False,
        stage_qualified=False,execute_qualified=False,research_conclusion=False)
    files={}
    try:
        inventory=json.loads((P/'archive_inventory_v1.json').read_text())
        helper=next(r for r in inventory['files'] if r['relative_path']=='build_deferred_observer_v1.py')
        B.require(B.sha(P/'build_deferred_observer_v1.py')==helper['sha256'],'sealed_build_utility_changed')
        selected=[p for root in [A/'observer',A/'common'] for p in root.rglob('*') if p.is_file()]+[A/'phase_protocol.hpp',A/'pair_wakeup_contract_v1.json']
        files={str(p.relative_to(A)):B.pin(p) for p in sorted(selected)}
        B.require(all(not p.is_symlink() for p in A.rglob('*')),'no source links')
        for rel,row in files.items():B.snapshot(row['path'],out/'source_snapshot'/rel)
        descriptor=dict(schema='publication-component-source-bundle/v1',files=files,
                        author_directory=str(A),exact_parent_source=str(P),
                        no_publisher_or_Worker_rebuild=True,freeze_before_configure=True,
                        source_bundle_contains_unused_parent_tests_without_claiming_them_run=True,
                        execute_qualified=False)
        B.write(out/'source_bundle.json',descriptor);identity=B.sha(out/'source_bundle.json')
        configure=['cmake','-S',str(A/'observer'),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
                   '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3',
                   '-DP1_OWNED_SOURCE_BUNDLE_SHA256='+identity]
        result['configure_rc']=B.command(out,'configure',configure,30,files)
        B.require(result['configure_rc']==0,'configure failed')
        static=B.static_link_inputs_before(build,out)
        result['build_rc']=B.command(out,'build',['cmake','--build',str(build),'--parallel','2'],120,files)
        B.require(result['build_rc']==0,'explicit two-target build failed')
        test_output=out/'native_events'
        result['Native_rc']=B.command(out,'native',[str(build/NATIVE),str(test_output)],10,files)
        B.require(result['Native_rc']==0,'pure Native failed')
        native=json.loads((test_output/'result.json').read_text())
        B.require(native['passed'] and not native['ROS_context_created'] and not native['actuator_endpoints_created'],'Native scope')
        B.require(len(native['cases'])==native['case_count'] and native['case_count']==3,'required finite event table')
        B.require(all(c['passed'] for c in native['cases']),'event case failed')
        commands=json.loads((build/'compile_commands.json').read_text())
        B.require(len(commands)==2 and all(identity in c['command'] for c in commands if c['file'].endswith('regulator_shadow_observer.cpp')),'exact runtime identity and only two compile targets')
        runtime=build/RUNTIME;B.require(identity.encode() in runtime.read_bytes(),'actual ELF source identity')
        result['compiler_dependencies']=B.dependencies(build,out)
        result['runtime_libraries']=B.runtime_libraries(runtime,out,files)
        B.verify_static_link_inputs(static)
        B.write(out/'static_link_inputs_after.json',dict(passed=True,same_before_after=True,files=static['files'],before_sha256=B.sha(out/'static_link_inputs_before.json')))
        original=P.parent/'p1_execution_architecture_20261005_01/authored_D1_deferred_observation_20261019_v29/observer/src/shadow'
        for name in ['p1_admission.hpp','p1_full_contract.hpp','protocol.hpp','p1_shadow_entry.hpp']:
            B.require(B.sha(A/'observer/src/shadow'/name)==B.sha(original/name),'unchanged admission/contract/protocol:'+name)
        source=(A/'observer/src/shadow/regulator_shadow_observer.cpp').read_text()
        B.require('if(mode_!="execute")return;' in source and 'p1::publication::publish_pair' in source and 'p1::publication::apply_channel_result' in source and 'p1::publication::shutdown_result' in source,'source integration or execute guard')
        B.require('physical_execute_release_enabled=false' in (A/'observer/src/shadow/p1_full_contract.hpp').read_text().replace(' ',''),'physical release remains disabled')
        result.update(passed=True,source_bundle=dict(path=str(out/'source_bundle.json'),sha256=identity,files=len(files)),
                      binary=B.pin(runtime),Native_binary=B.pin(build/NATIVE),Native_event_report=B.pin(test_output/'result.json'),
                      cases=native['case_count'],assertions=native['assertions'],
                      runtime_publish_branch_executed=False,plain_component_injected_send_events_only=True,
                      inherited_old_native_tests_rerun=False)
    except Exception as e:
        result.update(error=repr(e),traceback=__import__('traceback').format_exc())
    result['source_unchanged']=B.unchanged(files) if files else False
    result['elapsed_seconds']=time.monotonic()-start
    result['passed']=bool(result['passed'] and result['source_unchanged'])
    B.write(out/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k in ['passed','error','cases','assertions','elapsed_seconds','compiler_dependencies','runtime_libraries']},ensure_ascii=False))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
