"""Finite offline invocation; source, actual inputs and loader closure checked twice."""
from pathlib import Path
import hashlib,json,os,shlex,subprocess,time

D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_startup_rti_mechanism_20261018_v23'
B=D/'build/replay_attempt02'

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
def load(path):return json.loads(Path(path).read_text())
def write(path,value):
 with Path(path).open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
def check():
 build=load(B/'result.json');assert build['passed'] and build['native_tests']==dict(tests=10,failures=0,errors=0,disabled=0)
 scope=load(D/'preregister/selected_solver_scope_v1.json');inp=load(scope['input_path']);assert sha(scope['input_path'])==scope['input_sha256']
 assert scope['selected_job_ids']==inp['selected_job_ids']==[1,2,5,10] and scope['repeat_count']==inp['repeat_count']==12
 assert len(inp['ordered_native_jobs'])==scope['jobs']==102
 expected={str(B/'result.json'):sha(B/'result.json'),str(D/'preregister/selected_solver_scope_v1.json'):sha(D/'preregister/selected_solver_scope_v1.json'),str(Path(__file__).resolve()):sha(__file__)}
 expected.update(inp['evidence']);expected.update(inp['static_libraries'])
 expected[inp['actual_worker']['binary']]=inp['actual_worker']['binary_sha256'];expected[inp['actual_worker']['link_recipe']]=inp['actual_worker']['link_recipe_sha256']
 bundle=load(build['source_bundle']['path']);assert sha(build['source_bundle']['path'])==build['source_bundle']['sha256']
 expected[build['source_bundle']['path']]=build['source_bundle']['sha256']
 aliases={}
 for row in [*bundle['files'].values(),*bundle['pinned_external_inputs'].values(),*build['binaries'].values(),*load(B/'runtime_library_pins.json')['files'].values()]:
  p=Path(row['path']);target=p.resolve(strict=True)
  if row.get('resolved_path'):assert str(target)==row['resolved_path']
  aliases[str(p)]=str(target);expected[str(target)]=row['sha256'];assert target.stat().st_size==row['bytes']
 for name in ['runtime_library_pins.json','compiler_dependency_pins.json','native.gtest.xml','actual_link_recipe.txt','compile_commands.json']:
  path=B/name;expected[str(path)]=sha(path)
 compiler=load(B/'compiler_dependency_pins.json');assert compiler['count']==len(compiler['files'])==770
 expected.update(compiler['files']);assert sha(B/'compile_commands.json')==compiler['compile_commands_sha256']
 for p,h in sorted(expected.items()):assert sha(p)==h,p
 for p,t in aliases.items():assert str(Path(p).resolve(strict=True))==t,p
 return dict(files=expected,aliases=aliases,source_bundle_sha256=build['source_bundle']['sha256'],binary=build['binaries']['replay_startup_rti'],input_sha256=scope['input_sha256'])

def main():
 proof=D/'preflight/workspace_initial_v3.json';assert load(proof)['passed'] is True,'full initial preservation required'
 before=check();write(D/'preregister/offline_invocation_lock_v1.json',dict(schema='scheme-A-startup-offline-lock/v1',**before,initial_proof_path=str(proof),initial_proof_sha256=sha(proof),captured_before_selected_repeat_execution=True,ROS_nodes_started=False))
 script=D/'replay/native_startup_v1.sh';setup=(B/'native.sh').read_text().split('exec timeout',1)[0]
 command=[before['binary']['path'],'--input',str(N/'actual_startup_input_v1.json'),'--output',str(D/'replay/native_startup_v1.json')]
 script.open('x').write(setup+'exec timeout --signal=TERM --kill-after=5s 60s '+shlex.join(command)+'\n')
 start=time.monotonic_ns()
 with (D/'replay/native_startup_v1.log').open('xb') as f:rc=subprocess.run(['bash',str(script)],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=70).returncode
 after=check();result=dict(schema='scheme-A-startup-offline-invocation/v1',passed=rc==0 and before==after,returncode=rc,start_monotonic_ns=start,end_monotonic_ns=time.monotonic_ns(),lock_sha256=sha(D/'preregister/offline_invocation_lock_v1.json'),script_sha256=sha(script),input_closure_unchanged=before==after,locked_paths=len(before['files']),ROS_nodes_started=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 if (D/'replay/native_startup_v1.json').exists():result['native_result_sha256']=sha(D/'replay/native_startup_v1.json')
 write(D/'replay/offline_invocation_v1.json',result);print(json.dumps(result));return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
