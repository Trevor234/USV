#!/usr/bin/env python3
"""Create-only bounded current-batch evidence freeze and final QA."""
from pathlib import Path
import hashlib,json,os,re,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D));import build_and_verify_v2 as B;import protection_v1 as P
N=B.N
def pin(p):return {'path':str(p),'sha256':B.sha(p),'bytes':p.stat().st_size}
def main():
 native=json.loads((D/'component/native_attempt01/result.json').read_text());finite=json.loads((D/'component/checker_finite_v2.json').read_text());build=json.loads((D/'build/observer_attempt02/result.json').read_text())
 assert native['passed'] and native['count']==251 and finite['passed'] and finite['test_count']==40 and build['passed'] and build['default_build_rc']==0
 failure=json.loads((D/'runs/worker_early_exit/check_result.json').read_text());assert failure['passed'] and failure['driver_returncode']==2 and len(failure['cleanup'])==5
 cases={k:json.loads((D/'runs'/k/'check_result.json').read_text()) for k in ['normal','worker_post_exit']};assert all(x['passed'] for x in cases.values())
 before=json.loads((D/'preflight/workspace_initial.json').read_text())['protection'];after=P.protect();assert before==after
 matrix={'schema':'C3.9-actual-matrix/v1','passed':True,'native_count':native['count'],'finite_checker_count':40,'default_build_rc':0,'build_attempt01_retained_failed':json.loads((D/'build/observer_attempt01/result.json').read_text())['passed'] is False,'actual_cases':{},'qualifications':{'B4':'unknown','M0b':'unknown','B5':'unknown','M4':'unknown','F6':'unknown','P1':'unknown'},'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 for kind,x in cases.items():
  row={'component_passed':x['passed'],'normal_driver_passed':x.get('normal_driver_passed'),'resource_cleanup_complete':x.get('resource_cleanup_complete'),'Witness_observation_complete':x['witness_v2']['basis']['observation_complete'],'Witness_v2':x['witness_v2'],'Worker_publications':x['worker_publications'],'Worker_callbacks':x['worker_callbacks'],'issues':x['issues']}
  matrix['actual_cases'][kind]=row
  witness=json.loads((N/'runs'/('owned_C39_'+kind+'_01')/'observer/witness.json').read_text());assert witness['observation_complete'] is True and witness['business_ready_observed'] is False and witness['normal_contract_qualified'] is False and witness['counters']['accepted_activations']==0
  assert x['witness_v2']['basis']['normal_business'] is False
 matrix['cleanup_failure_case']={k:failure[k] for k in ['passed','driver_returncode','component_scope','error','close_errors','Witness_observation_complete','actual_Accepted','stage_qualified']}
 B.write(D/'postrun/matrix_current.json',matrix)
 out=D/'postrun/ldd';out.mkdir()
 bins={str(Path(x['path'])) for x in build['produced_target_pins'].values()};libs={}
 for i,binary in enumerate(sorted(bins)):
  rc=B.command(out,'binary_'+str(i),['ldd',binary],10,151);assert rc==0
  text=(out/('binary_'+str(i)+'.log')).read_text();assert 'not found' not in text
  for word in re.findall(r'(/[^\s()]+)',text):
   p=Path(word)
   if p.is_file():libs[str(p.resolve())]=B.sha(p.resolve())
 B.write(D/'postrun/actual_shared_library_pins.json',{'schema':'C3.9-actual-build-library-pins/v1','files':libs,'count':len(libs),'scope':'ldd under actual build SETUP; not complete OS/WCET/plant proof'})
 paths=set()
 for p in N.rglob('*'):
  if p.is_file() and not any(part=='__pycache__' or part.startswith('build') for part in p.relative_to(N).parts[:-1]):paths.add(p.resolve())
 for p in D.rglob('*'):
  if p.is_file() and 'final_frozen_snapshot' not in p.parts:paths.add(p.resolve())
 for attempt in ['observer_attempt01','observer_attempt02']:
  x=json.loads((D/'build'/attempt/'result.json').read_text());paths.update(Path(v['path']).resolve() for v in x['produced_target_pins'].values())
  dp=json.loads((D/'build'/attempt/'compiler_dependency_pins.json').read_text());paths.update(Path(p).resolve() for p in dp['files']);paths.update(Path(p).resolve() for p in dp['depfile_sha256'])
  bd=Path(x['build_directory']);paths.update(p.resolve() for p in [bd/'CMakeCache.txt',bd/'compile_commands.json'] if p.is_file());paths.update(p.resolve() for p in bd.rglob('link.txt'))
  paths.update(p.resolve() for p in bd.rglob('*.a') if p.name in ['libgtest.a','libgtest_main.a'])
 paths.update(Path(p) for p in libs)
 frozen=D/'final_frozen_snapshot';frozen.mkdir();records=[];fixed={}
 for i,p in enumerate(sorted(paths)):
  assert p.is_file() and not p.is_symlink();raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest();dst=frozen/'files'/f'{i:05d}_{p.name}';dst.parent.mkdir(exist_ok=True)
  with dst.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  assert B.sha(dst)==sha;fixed[str(p)]=sha;fixed[str(dst)]=sha;records.append({'original':str(p),'copy':str(dst),'sha256':sha,'bytes':len(raw)})
 B.write(frozen/'manifest.json',{'schema':'C3.9-final-freeze/v1','files':records,'count':len(records),'old_assets_modified':False,'stage_qualified':False})
 fixed[str(frozen/'manifest.json')]=B.sha(frozen/'manifest.json')
 assert all(B.sha(p)==sha for p,sha in fixed.items())
 q={'schema':'C3.9-final-QA/v1','passed':True,'native_count':native['count'],'finite_checker_count':40,'actual_owned_cases':2,'actual_driver_failure_cleanup_cases':1,'default_build_rc':0,'failed_build_attempt01_retained':True,'new_frozen_pairs':len(records),'fixed_source_header_input_hashes':fixed,'actual_build_shared_libraries':len(libs),'parent_before':before,'parent_after':after,'old_24_business_diff_sha256':after['business_diff_sha256'],'actual_Witness_normal_business':False,'normal_business_contract_qualified':False,'actual_Accepted':0,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False,'unqualified_claims':['all rejected received payload identity','MasterClock','plant acceptance','WCET','continuous DDS integrity','endpoint disappearance','postpin-exec immunity']}
 B.write(D/'postrun/final_QA_current.json',q);print(json.dumps({'passed':True,'frozen_pairs':len(records),'fixed_paths':len(fixed),'actual_build_libraries':len(libs),'QA_sha256':B.sha(D/'postrun/final_QA_current.json')}))
if __name__=='__main__':main()
