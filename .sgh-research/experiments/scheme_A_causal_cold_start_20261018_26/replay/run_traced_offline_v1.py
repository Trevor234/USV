"""Execute the causal candidate with runtime input only; trace actual file opens."""
from pathlib import Path
import hashlib,json,os,shlex,subprocess,time
D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_causal_cold_start_20261018_v26'
B=D/'build/replay_attempt01'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def write(p,v):
 with Path(p).open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
def check():
 build=load(B/'result.json');pre=load(D/'preregister/causal_cold_v1.json');inp=load(pre['validation_input_path'])
 assert build['passed'] and build['native_tests']==dict(tests=3,failures=0,errors=0,disabled=0)
 assert sha(pre['runtime_input_path'])==pre['runtime_input_sha256'] and sha(pre['validation_input_path'])==pre['validation_input_sha256'];assert inp['candidate_calls']==4 and inp['post_candidate_free_probe_calls']==1
 expected={str(B/'result.json'):sha(B/'result.json'),str(D/'preregister/causal_cold_v1.json'):sha(D/'preregister/causal_cold_v1.json'),str(Path(__file__).resolve()):sha(__file__)}
 expected['/usr/bin/strace']=sha('/usr/bin/strace');expected.update(inp['source_pins']);expected.update(inp['static_libraries']);worker=inp['actual_worker'];expected[worker['binary']]=worker['binary_sha256'];expected[worker['link_recipe']]=worker['link_recipe_sha256']
 assert sha(build['source_bundle']['path'])==build['source_bundle']['sha256'];expected[build['source_bundle']['path']]=build['source_bundle']['sha256'];bundle=load(build['source_bundle']['path']);aliases={}
 for row in [*bundle['files'].values(),*bundle['pinned_external_inputs'].values(),*build['binaries'].values(),*load(B/'runtime_library_pins.json')['files'].values()]:
  p=Path(row['path']);target=p.resolve(strict=True);aliases[str(p)]=str(target)
  if row.get('resolved_path'):assert str(target)==row['resolved_path']
  assert target.stat().st_size==row['bytes'];h=row['sha256']
  if str(target) in expected:assert expected[str(target)]==h
  expected[str(target)]=h
 compiler=load(B/'compiler_dependency_pins.json');assert compiler['count']==len(compiler['files'])==build['compiler_dependencies']
 for p,h in compiler['files'].items():
  if p in expected:assert expected[p]==h
  expected[p]=h
 for name in ['runtime_library_pins.json','compiler_dependency_pins.json','native.gtest.xml','actual_link_recipe.txt','compile_commands.json']:expected[str(B/name)]=sha(B/name)
 assert sha(B/'compile_commands.json')==compiler['compile_commands_sha256']
 for p,h in expected.items():assert sha(p)==h,p
 for p,t in aliases.items():assert str(Path(p).resolve(strict=True))==t,p
 return dict(files=expected,aliases=aliases,runtime_input_sha256=pre['runtime_input_sha256'],validation_input_sha256=pre['validation_input_sha256'],source_bundle_sha256=build['source_bundle']['sha256'],binary=build['binaries']['replay_causal_cold'])
def main():
 proof=D/'preflight/workspace_initial_local_v1.json';initial=load(proof);assert initial['passed'] and initial['protection']['full_local_current_byte_sha_recheck']
 assert load(D/'preflight/strace_capability_host_v1.json')['passed'],'host file-open trace required'
 before=check();lock=D/'preregister/offline_invocation_lock_v1.json';write(lock,dict(schema='scheme-A-causal-cold-offline-lock/v1',**before,local_initial_proof_sha256=sha(proof),Go_offline_candidate_only=True,MPC_mirror_currently_verified=False,MPC_delivery_complete=False,default_102_job_and_mode_components_passed=True,captured_before_candidate_generation=True,candidate_RTI_calls=4,separate_restoration_probe_RTI_calls=1,ROS_nodes_started=False))
 script=D/'replay/native_causal_cold_v1.sh';setup=(B/'native.sh').read_text().split('exec timeout',1)[0];trace=D/'replay/native_causal_cold_v1.opens.log';command=['/usr/bin/strace','-qq','-f','-e','trace=open,openat,openat2','-o',str(trace),before['binary']['path'],'--input',str(N/'runtime_job_v1.json'),'--output',str(D/'replay/native_causal_cold_v1.json')];script.open('x').write(setup+'exec timeout --signal=TERM --kill-after=5s 60s '+shlex.join(command)+'\n')
 start=time.monotonic_ns()
 with (D/'replay/native_causal_cold_v1.log').open('xb') as f:rc=subprocess.run(['bash',str(script)],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=70).returncode
 after=check();out=dict(schema='scheme-A-causal-cold-offline-invocation/v1',passed=rc==0 and before==after,returncode=rc,start_monotonic_ns=start,end_monotonic_ns=time.monotonic_ns(),lock_sha256=sha(lock),script_sha256=sha(script),input_closure_unchanged=before==after,locked_paths=len(before['files']),file_open_trace_path=str(trace),file_open_trace_sha256=sha(trace),candidate_program_received_validation_argument=False,ROS_nodes_started=False,MPC_delivery_complete=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 result=D/'replay/native_causal_cold_v1.json'
 if result.exists():out['native_result_sha256']=sha(result)
 write(D/'replay/offline_invocation_v1.json',out);print(json.dumps(out));return 0 if out['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
