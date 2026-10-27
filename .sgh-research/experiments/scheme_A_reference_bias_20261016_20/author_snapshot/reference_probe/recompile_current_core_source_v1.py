#!/usr/bin/env python3
"""New current-time source/object equivalence proof; no historical source claim."""
from pathlib import Path
import hashlib,json,subprocess,shlex,os,sys
sys.dont_write_bytecode=True
S=Path(__file__).resolve().parent;E=S.parents[2];D=E/'scheme_A_reference_bias_20261016_20';B=D/'build/reference_source_recompile_attempt01';B.mkdir(exist_ok=False)
U=Path('/home/trevor/USV/usv_mpc_ws');src=U/'src/usv_mpc_cpp/src/p1_input_core.cpp';archive=U/'install/usv_mpc_cpp/lib/libmpc_core_lib.a';old=U/'build/usv_mpc_cpp/CMakeFiles/mpc_core_lib.dir/src/p1_input_core.cpp.o'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):
 with p.open('x') as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
command=['/usr/bin/c++','-I'+str(U/'src/usv_mpc_cpp/include'),'-isystem','/usr/include/eigen3','-O3','-DNDEBUG','-std=gnu++17','-Wall','-Wextra','-Wpedantic','-c',str(src),'-o',str(B/'p1_input_core.cpp.o')]
dep=old.with_suffix('.o.d');paths=[src,archive,old,dep,S/Path(__file__).name,U/'build/usv_mpc_cpp/CMakeFiles/mpc_core_lib.dir/flags.make',Path('/usr/bin/c++')]
paths+=list(map(Path,shlex.split(dep.read_text().split(':',1)[1].replace('\\\n',' '))))
pins={str(p):{'sha256':sha(p),'resolved_path':str(p.resolve()),'bytes':p.stat().st_size} for p in paths}
write(B/'prebuild_pins.json',{'schema':'current-core-source-recompile-pins/v1','current_time_capture_only':True,'argv':command,'files':pins,'historical_source_or_object_pin_claimed':False,'ROS_node_started':False,'codegen':False,'install':False})
env=dict(os.environ)
for k in ['CPATH','CPLUS_INCLUDE_PATH','C_INCLUDE_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH']:env.pop(k,None)
with (B/'compile.log').open('xb') as out:r=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,env=env,timeout=90)
member=subprocess.run(['/usr/bin/ar','p',str(archive),'p1_input_core.cpp.o'],capture_output=True,check=True).stdout
obj=B/'p1_input_core.cpp.o';same=r.returncode==0 and obj.read_bytes()==member
write(B/'result.json',{'schema':'current-core-source-recompile-result/v1','passed':r.returncode==0 and same,'compile_returncode':r.returncode,'current_source_sha256':sha(src),'actual_archive_sha256':sha(archive),'rebuilt_current_object_sha256':sha(obj) if obj.exists() else None,'actual_archive_member_sha256':hashlib.sha256(member).hexdigest(),'current_source_rebuild_equals_historically_pinned_archive_member':same,'inputs_unchanged':all(sha(p)==v['sha256'] for p,v in pins.items()),'historical_source_compile_provenance_claimed':False,'no_ROS_node_started':True,'stage_qualified':False})
print(json.dumps({'passed':r.returncode==0 and same,'same_object_bytes':same,'result':str(B/'result.json')}))
