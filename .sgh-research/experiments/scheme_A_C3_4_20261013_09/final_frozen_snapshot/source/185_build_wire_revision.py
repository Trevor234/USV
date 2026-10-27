#!/usr/bin/env python3
"""Build explicit corrected wire component derivative, preserve role bundle v1."""
import hashlib,json,shlex,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent
N=R.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10'
sys.path.insert(0,str(N))
from build_c34_v10 import sha,verify,parent_verify,dump
def main():
 out=R/'C_lease/build_wire_v3';out.mkdir(exist_ok=False);start=time.monotonic()
 old=json.loads((R/'build/observer02/result.json').read_text());assert old['runtime_build_rc']==0
 pin=old['source_bundle'];bundle=verify(pin,'observer');parent_verify()
 original=N/'observer/tests/c34_lease_wire.cpp';source=out/'c34_lease_wire_v2.cpp'
 text=original.read_text().replace('executor.add_node(regulator);','executor.add_node(regulator->get_node_base_interface());').replace('executor.remove_node(regulator);','executor.remove_node(regulator->get_node_base_interface());')
 assert text!=original.read_text();source.open('x').write(text)
 files=dict(bundle['files']);files['corrected_wire_v2.cpp']={'path':str(source),'bytes':source.stat().st_size,'sha256':sha(source)}
 component_bundle=out/'component_source_bundle_v2.json'
 dump(component_bundle,{'schema':'p1-C3.4-corrected-wire-component-source/v2','role':'observer_wire_component','parent_role_bundle':pin,'files':files,
                       'change':'executor add/remove uses actual NodeBaseInterface shared pointer; component fixture only','stage_qualified':False})
 cpin={'path':str(component_bundle),'sha256':sha(component_bundle),'files':len(files)}
 dump(out/'preregister.json',{'before_compile':True,'source_bundle':cpin,'failed_parent_attempt':str(R/'build/observer02/result.json'),
                           'role_source_changed':False,'normal_runtime_changed':False,'execute_qualified':False})
 build=N/'observer/build01';commands=json.loads((build/'compile_commands.json').read_text())
 entry=next(x for x in commands if x['file']==str(original));compile_cmd=shlex.split(entry['command'])
 compile_cmd=[x for x in compile_cmd if not x.startswith('-DP1_OWNED_SOURCE_BUNDLE_SHA256=')]
 compile_cmd.insert(1,'-DP1_OWNED_SOURCE_BUNDLE_SHA256="'+cpin['sha256']+'"')
 compile_cmd.insert(1,'-I'+str(original.parent))
 obj=out/'wire_v2.o';compile_cmd[compile_cmd.index('-o')+1]=str(obj);compile_cmd[compile_cmd.index('-c')+1]=str(source)
 link=shlex.split((build/'CMakeFiles/c34_lease_wire_component.dir/link.txt').read_text());link=[str(obj) if x.endswith('c34_lease_wire.cpp.o') else x for x in link]
 binary=out/'c34_lease_wire_component_v2';link[link.index('-o')+1]=str(binary)
 result={'schema':'p1-C3.4-wire-component-build/v2','passed':False,'component_source_bundle':cpin,'role_source_bundle':pin,
         'normal_runtime_changed':False,'stage_qualified':False,'execute_qualified':False,'commands':[]}
 try:
  for name,cmd in [('compile',compile_cmd),('link',link)]:
   dump(out/(name+'_command.json'),{'cwd':str(build),'argv':cmd,'budget_seconds':180})
   with (out/(name+'.log')).open('xb') as log:rc=subprocess.run(['timeout','--signal=TERM','--kill-after=10s','180s',*cmd],cwd=build,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=195).returncode
   result['commands'].append({'name':name,'returncode':rc})
   if rc:raise RuntimeError(name+' failed:'+str(rc))
  verify(pin,'observer');verify(cpin,'observer_wire_component');parent_verify()
  result.update(passed=True,binary=str(binary),binary_sha256=sha(binary))
 except Exception as e:result['error']=repr(e)
 result['elapsed_seconds']=time.monotonic()-start;dump(out/'result.json',result);print(json.dumps(result,sort_keys=True));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
