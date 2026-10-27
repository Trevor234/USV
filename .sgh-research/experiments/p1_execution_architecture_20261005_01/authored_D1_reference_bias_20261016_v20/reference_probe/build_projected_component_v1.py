#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,subprocess,shlex,re,sys
sys.dont_write_bytecode=True
S=Path(__file__).resolve().parent;E=S.parents[2];B=E/'scheme_A_reference_bias_20261016_20/build/projected_reference_component_attempt01';B.mkdir(exist_ok=False)
SRC=Path('/home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/include');LIB=Path('/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/lib/libmpc_core_lib.a')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,x):
 with (B/name).open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
flags=['/usr/bin/c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(SRC),'-isystem','/usr/include/eigen3'];source=S/'test_projected_profile_time_v1.cpp'
dep=B/'precompile_dependencies.d'
with (B/'preprocess.log').open('xb') as f:subprocess.run(flags+['-M','-MF',str(dep),str(source)],stdout=f,stderr=subprocess.STDOUT,check=True)
paths=[Path(x) for x in shlex.split(dep.read_text().split(':',1)[1].replace('\\\n',' '))]+[LIB,Path('/usr/bin/c++'),Path(__file__)]
pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size,'resolved_path':str(p.resolve())} for p in paths}
binary=B/'test_projected_profile_time_v1';command=flags+[str(source),str(LIB),'-Wl,-Map='+str(B/'link.map'),'-o',str(binary)]
write('prebuild_pins.json',{'schema':'isolated-projected-reference-component-pins/v1','files':pins,'argv':command,'before_build':True,'old_business_source_modified':False,'production_Observer_or_Worker_changed':False,'no_ROS':True,'no_solver':True,'no_codegen':True,'no_install':True,'stage_qualified':False})
with (B/'build.log').open('xb') as out:r=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,timeout=90)
if r.returncode:write('result.json',{'passed':False,'build_rc':r.returncode,'failed_attempt_preserved':True});raise SystemExit(r.returncode)
with (B/'native.log').open('xb') as out:r=subprocess.run([str(binary)],stdout=out,stderr=subprocess.STDOUT,timeout=30)
text=(B/'native.log').read_text();m=re.search(r'checks=(\d+) passed',text)
unchanged=all(sha(p)==x['sha256'] for p,x in pins.items())
write('result.json',{'schema':'isolated-projected-reference-component-result/v1','passed':r.returncode==0 and m is not None and unchanged,'native_rc':r.returncode,'checks':int(m[1]) if m else None,'binary':str(binary),'binary_sha256':sha(binary),'native_log_sha256':sha(B/'native.log'),'all_prebuild_pins_unchanged':unchanged,'production_runtime_qualification':False,'solver_invoked':False,'stage_qualified':False})
print(json.dumps({'passed':r.returncode==0 and m is not None and unchanged,'checks':int(m[1]) if m else None,'result':str(B/'result.json')}))
