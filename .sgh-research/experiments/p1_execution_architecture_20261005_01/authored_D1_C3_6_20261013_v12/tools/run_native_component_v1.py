#!/usr/bin/env python3
"""Finite fresh-directory build/probe; no ROS launch and no overwrite of attempts."""
import argparse,hashlib,json,pathlib,shlex,shutil,subprocess,sys
N=pathlib.Path(__file__).resolve().parent.parent
D=N.parent.parent/'scheme_A_C3_6_20261013_11'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def new(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def main():
 a=argparse.ArgumentParser();a.add_argument('--attempt',required=True);args=a.parse_args()
 if not args.attempt.isascii() or not args.attempt.replace('_','').isalnum():raise ValueError('attempt_name')
 out=D/'component'/args.attempt;out.mkdir(exist_ok=False)
 sources=[N/'include/command_anchor_v1.hpp',N/'tests/test_command_anchor_v1.cpp',N/'vendor/p1_admission_N10.hpp',pathlib.Path(__file__).resolve(),D/'preregister/anchor_component_scope_v1.json']
 before={str(p):sha(p) for p in sources}
 (out/'source_snapshot').mkdir()
 for p in sources:
  with (out/'source_snapshot'/p.name).open('xb') as f:f.write(p.read_bytes())
 compiler=pathlib.Path(shutil.which('g++')).resolve()
 cmd=[str(compiler),'-std=c++17','-O2','-Wall','-Wextra','-Wpedantic','-pthread','-MD','-MF',str(out/'native.d'),'-I'+str(N/'include'),'-I'+str(N/'vendor'),str(N/'tests/test_command_anchor_v1.cpp'),'-o',str(out/'test_command_anchor_v1')]
 version=subprocess.check_output([str(compiler),'--version'],text=True)
 with (out/'build.log').open('xb') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=45).returncode
 build={'schema':'p1-C3.6-A-native-build/v1','argv':cmd,'returncode':rc,'compiler':str(compiler),'compiler_sha256':sha(compiler),'compiler_version':version,'sources_before':before,'optimization':'O2, tests use explicit throwing checks; no assert','new_ROS_nodes':False}
 if rc==0:
  dep=(out/'native.d').read_text().replace('\\\n',' ');paths=shlex.split(dep.split(':',1)[1]);deps={str(pathlib.Path(p).resolve()):sha(pathlib.Path(p).resolve()) for p in paths}
  build['actual_compile_dependency_pins']=deps;build['binary_sha256']=sha(out/'test_command_anchor_v1')
  build['dependency_scope']='compiler-reported headers plus compiler and frozen probe binary; not all toolchain/OS/WCET identity'
  with (out/'native_result.json').open('xb') as f, (out/'native_stderr.log').open('xb') as err:probe_rc=subprocess.run([str(out/'test_command_anchor_v1')],stdout=f,stderr=err,timeout=10).returncode
  build['probe_returncode']=probe_rc
  report=json.loads((out/'native_result.json').read_text());build['native_case_count']=report['count'];build['native_passed']=report['passed'] is True and probe_rc==0
  build['actual_compile_dependencies_unchanged']=all(sha(p)==h for p,h in deps.items())
 else:build['native_passed']=False
 build['sources_after']={str(p):sha(p) for p in sources};build['sources_unchanged']=build['sources_after']==before
 new(out/'build_result.json',build)
 print(json.dumps({k:v for k,v in build.items() if k not in ('actual_compile_dependency_pins','sources_before','sources_after','argv','compiler_version')}))
 return 0 if build['native_passed'] and build['sources_unchanged'] and build.get('actual_compile_dependencies_unchanged') else 1
if __name__=='__main__':raise SystemExit(main())
