#!/usr/bin/env python3
"""New-scope read-only historical data/static-library probe, create-only outputs."""
from pathlib import Path
import hashlib,json,sqlite3,subprocess,sys,shlex,os
sys.dont_write_bytecode=True
S=Path(__file__).resolve().parent
E=S.parents[2];D=E/'scheme_A_reference_bias_20261016_20'
A=E/'p1_execution_architecture_20261005_01/authored_D1_longitudinal_20261016_v19'
U=Path('/home/trevor/USV/usv_mpc_ws');SRC=U/'src/usv_mpc_cpp';BUILD=U/'build/usv_mpc_cpp';LIB=U/'install/usv_mpc_cpp/lib/libmpc_core_lib.a'
B=D/'build/reference_probe_attempt01';B.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
 with Path(p).open('x') as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
pins={}
def pin(p):p=Path(p);pins[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size,'resolved_path':str(p.resolve())};return p
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict
samples=[]
for case,speed in [('s005',.05),('s010',.1),('s030',.3),('s060',.6)]:
 run=A/'runs'/('longitudinal_'+case+'_01');source=pin(run/'observer/source.jsonl');db=pin(run/'recorder/bag/bag_0.db3')
 rows=[json.loads(l) for l in source.read_text().splitlines()];con=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);paths={};profiles={}
 for topic,typ,raw in con.execute("select t.name,t.type,m.data from messages m join topics t on m.topic_id=t.id where t.name in ('/path/reference','/path/reference_profile') order by m.id"):
  m=dict(message_to_ordereddict(deserialize_message(raw,get_message(typ))))
  if topic=='/path/reference':stamp=m['header']['stamp'];key=stamp['sec']*1000000000+stamp['nanosec'];paths[key]=m
  else:dim=m['layout']['dim'];key=int(dim[0]['label'].split(':')[1])*1000000000+int(dim[1]['label'].split(':')[1]);profiles[key]=m
 con.close()
 for row in rows:
  if row.get('type')!='job':continue
  j=row['job'];p=row['input_provenance'];path=paths[p['path_stamp_ns']];prof=profiles[p['profile_stamp_ns']];data=list(prof['data']);stamp=path['header']['stamp']
  samples.append({'case':case,'speed':speed,'job_id':j['job_id'],'path':[[x['pose']['position']['x'],x['pose']['position']['y'],0.] for x in path['poses']],'profile':[data[k:k+4] for k in range(0,len(data),4)],'path_stamp':[stamp['sec'],stamp['nanosec']],'profile_stamp':[p['profile_stamp_ns']//1000000000,p['profile_stamp_ns']%1000000000],'path_sequence':p['path_sequence'],'profile_sequence':p['profile_sequence'],'target_state':j['target_state'],'frozen_state':j['frozen_state'],'reference':j['reference'],'source_metadata':{k:row[k] for k in ['nearest_index','start_index','profile_t0','reference_mode']},'target_ns':j['target_ns'],'freeze_ns':j['freeze_ns'],'anchor_n':j['anchor_n']})
inputs=S/'actual_inputs_v1.json';write(inputs,{'schema':'actual-recorded-reference-probe-input/v1','samples':samples,'read_inputs':pins,'all_inputs_from_closed_D19_source_and_actual_SQLite_Storage':True});pin(inputs)
for p in [S/'reference_probe.cpp',Path(__file__),LIB,SRC/'src/p1_input_core.cpp',SRC/'src/utils.cpp',SRC/'include/usv_mpc_cpp/p1_input_core.hpp',SRC/'include/usv_mpc_cpp/utils.hpp',SRC/'include/usv_mpc_cpp/usv_model_dynamic.hpp',BUILD/'CMakeFiles/mpc_core_lib.dir/flags.make',BUILD/'CMakeFiles/mpc_core_lib.dir/build.make',BUILD/'CMakeFiles/mpc_core_lib.dir/link.txt',BUILD/'CMakeFiles/mpc_core_lib.dir/src/p1_input_core.cpp.o',BUILD/'CMakeFiles/mpc_core_lib.dir/src/p1_input_core.cpp.o.d',U/'install/usv_mpc_cpp/share/usv_mpc_cpp/cmake/p1_core_targetsExport-release.cmake',E/'scheme_A_positive_chain_20261015_18/build/controlled_observer_attempt01/cmake_build/CMakeFiles/p1_regulator_shadow_observer_owned_v2.dir/link.txt',E/'scheme_A_positive_chain_20261015_18/build/controlled_observer_attempt01/cmake_build/p1_regulator_shadow_observer_owned_v2']:
 pin(p)
compiler=Path('/usr/bin/c++');pin(compiler)
flags=[str(compiler),'-std=c++17','-O2','-I'+str(SRC/'include'),'-isystem','/usr/include/eigen3']
dep=B/'precompile_dependencies.d';depcommand=flags+['-M','-MF',str(dep),str(S/'reference_probe.cpp')]
with (B/'preprocess.log').open('xb') as f:r=subprocess.run(depcommand,stdout=f,stderr=subprocess.STDOUT)
assert r.returncode==0
for path in shlex.split(dep.read_text().split(':',1)[1].replace('\\\n',' ')):pin(path)
archive_member=subprocess.run(['/usr/bin/ar','p',str(LIB),'p1_input_core.cpp.o'],capture_output=True,check=True).stdout
member=B/'installed_archive_p1_input_core.cpp.o';member.open('xb').write(archive_member)
object_path=BUILD/'CMakeFiles/mpc_core_lib.dir/src/p1_input_core.cpp.o'
write(B/'archive_member_comparison.json',{'current_archive_sha256':sha(LIB),'historical_archive_pin_sha256':'b4279533c459fcdd5026fd19f293da7063e3d1a54cfcfe11dccf9aa22e8c8020','current_archive_matches_historical_pin':sha(LIB)=='b4279533c459fcdd5026fd19f293da7063e3d1a54cfcfe11dccf9aa22e8c8020','member_sha256':sha(member),'workspace_object_sha256':sha(object_path),'current_archive_member_equals_workspace_object':member.read_bytes()==object_path.read_bytes(),'cpp_source_and_object_historically_pinned':False})
binary=B/'reference_probe';command=flags+[str(S/'reference_probe.cpp'),str(LIB),'-Wl,-Map='+str(B/'link.map'),'-o',str(binary)]
write(B/'preregister_source_and_link_v1.json',{'schema':'reference-probe-prebuild-pins/v1','all_inputs':pins,'compile_link_argv':command,'preprocessor_argv':depcommand,'before_compilation':True,'ROS_node_launch':False,'codegen':False,'install':False,'stage_qualified':False})
with (B/'build.log').open('xb') as f:r=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=90)
if r.returncode:write(B/'result.json',{'passed':False,'build_returncode':r.returncode,'failed_attempt_preserved':True});raise SystemExit(r.returncode)
result=B/'probe_result.json'
with result.open('xb') as out,(B/'probe_stderr.log').open('xb') as err:r=subprocess.run([str(binary),str(inputs)],stdout=out,stderr=err,timeout=30)
all_same=all(sha(p)==v['sha256'] for p,v in pins.items());x=json.loads(result.read_text()) if r.returncode==0 else {};matched=r.returncode==0 and all(v['actual_archive_all_126_doubles_equal'] for v in x['samples'])
write(B/'result.json',{'passed':matched and all_same,'run_returncode':r.returncode,'actual_library_reference_matches_all_recorded_jobs':matched,'sample_count':len(samples),'source_and_static_dependencies_unchanged':all_same,'binary':str(binary),'binary_sha256':sha(binary),'probe_result_sha256':sha(result),'no_ROS_node_started':True,'solver_invoked':False,'stage_qualified':False,'research_conclusion':False})
print(json.dumps({'passed':matched and all_same,'sample_count':len(samples),'binary_sha256':sha(binary),'results':str(result)}))
