from pathlib import Path
import argparse,hashlib,json,importlib.util,sys,time,xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;S=D/'wire_component_source';N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_pair_wakeup_20261018_v22'
spec=importlib.util.spec_from_file_location('pair_wire_build_helpers',D/'build_pair_wakeup_roles_v2.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=int,default=1);a=ap.parse_args();assert 1<=a.attempt<=3
 out=D/'build'/('wire_component_attempt%02d'%a.attempt);out.mkdir(exist_ok=False);(out/'native_callback_output').mkdir();build=out/'cmake_build';start=time.monotonic()
 files={str(p):H.pin(p) for p in [*S.glob('*'),Path(__file__),D/'build_pair_wakeup_roles_v2.py'] if p.is_file()}
 # Freeze complete actual runtime observer and common dependency source before compilation.
 for folder in [N/'observer',N/'common']:
  for p in folder.rglob('*'):
   if p.is_file():files[str(p)]=H.pin(p)
 for p in [N/'phase_protocol.hpp',N/'reference_contract_test.cpp',N/'pair_wakeup_contract_v1.json']:
  files[str(p)]=H.pin(p)
 static=[Path('/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/lib/libmpc_core_lib.a'),D/'build/pair_wakeup_observer_attempt04/cmake_build/gtest/libgtest.a',D/'build/pair_wakeup_observer_attempt04/cmake_build/gtest/libgtest_main.a']
 for p in static:files[str(p)]=H.pin(p)
 descriptor={'schema':'pair-wakeup-wire-component-source/v1','files':files,'worker_clock_odom_RTF_readiness_seeded':True,'all_changed_message_metadata_from_actual_DDS':True,'not_full_five_role_experiment':True,'stage_qualified':False}
 H.write(out/'source_bundle.json',descriptor);bundle={'path':str(out/'source_bundle.json'),'sha256':H.sha(out/'source_bundle.json')}
 for i,row in enumerate(files.values()):H.snapshot(row['path'],out/'source_snapshot'/('%04d_'%i+Path(row['path']).name))
 pre={'schema':'pair-wakeup-positive-wire-component-preregister/v1','source_bundle':bundle,'role':'source_including_component','ROS_DOMAIN_ID':197,'intended_order':['bootstrap actual Applied1','profile101 actual DDS receipt','actual Applied2 receipt','actual accepted phase while path100 remains','path101 actual DDS receipt','actual unchanged prepare/submit','exactly one actual DDS Job receipt'],'original_ready_deadline_ns':150000000,'original_target_period_ns':200000000,'expected_tests':1,'maximum_native_seconds':45,'performance_gate_replaced':False,'reference_speed_ladder_advanced':False,'worker_odom_clock_RTF_readiness_seeded':True,'stage_qualified':False}
 H.write(out/'preregister.json',pre)
 result={'schema':'pair-wakeup-real-wire-build-run/v1','passed':False,'source_bundle':bundle,'preregistration_sha256':H.sha(out/'preregister.json'),'actual_five_role_experiment':False,'stage_qualified':False,'execute_qualified':False,'recipe_sha256':H.sha(__file__)}
 try:
  result['configure_rc']=H.command(out,'configure',['cmake','-S',str(S),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3','-DP1_OWNED_SOURCE_BUNDLE_SHA256='+bundle['sha256']],90,files);assert result['configure_rc']==0
  link=build/'CMakeFiles/test_reference_pair_wire.dir/link.txt';result['link_sha256_before_build']=H.sha(link);assert all(str(p) in link.read_text() for p in static)
  result['build_rc']=H.command(out,'default_build',['cmake','--build',str(build),'-j1'],240,files);assert result['build_rc']==0
  binary=build/'test_reference_pair_wire';result['binary']={'path':str(binary),'sha256':H.sha(binary)}
  xml=out/'wire.gtest.xml';result['native_rc']=H.command(out,'native',[str(binary),'--gtest_output=xml:'+str(xml)],45,files);assert result['native_rc']==0
  root=ET.parse(xml).getroot();result['tests']={k:int(root.attrib.get(k,0)) for k in ['tests','failures','errors','disabled']};assert result['tests']==dict(tests=1,failures=0,errors=0,disabled=0)
  evidence=out/'native_callback_output/current/ActualDDSProfilePhasePathSubmitsExactlyOneJob/actual_wire_result.json';value=json.loads(evidence.read_text());assert value['actual_DDS_delivery'] and value['positive_reference_completion_retry']
  source=evidence.parent/'source.jsonl';rows=[json.loads(l) for l in source.read_text().splitlines()];positive=[r for r in rows if r.get('type')=='reference_pair_retry' and r.get('froze') is True];assert len(positive)==1 and positive[0]['trigger']=='path'
  phases=[r for r in rows if r.get('type')=='controlled_phase_callback' and r.get('accepted') is True];assert len(phases)==1
  for kind in ['path_version','profile_version']:
   observed=[r for r in rows if r.get('type')==kind and r.get('received_sequence')==2];assert len(observed)==1 and observed[0]['raw_input'] is not None and observed[0]['raw_input']['from_intra_process'] is False
  result['actual_positive_retry']=positive[0];result['actual_wire_result']={'path':str(evidence),'sha256':H.sha(evidence)};result['source']={'path':str(source),'sha256':H.sha(source)}
  result['compiler_dependencies']=H.dependencies(build,out);result['passed']=True
 except BaseException as e:result['error']=repr(e)
 result['source_inputs_unchanged']=H.unchanged(files);result['passed']=bool(result['passed'] and result['source_inputs_unchanged']);result['elapsed_seconds']=time.monotonic()-start;H.write(out/'result.json',result)
 print(json.dumps({k:result.get(k) for k in ['passed','error','tests','actual_positive_retry','elapsed_seconds']}));return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
