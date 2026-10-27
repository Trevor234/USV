#!/usr/bin/env python3
"""Freeze C3.10 new source, all raw case files, actual build and selected role pins."""
from pathlib import Path
import json,os,re,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D));import verify_and_run_v1 as B
import protection_v2 as P
N=B.N

def main():
 component=json.loads((D/'component/result.json').read_text());assert component['passed'] and component['new_native_count']==23 and component['finite_checker_count']==80
 pre=json.loads((D/'preflight/workspace_initial_v2.json').read_text());assert pre['passed']
 cases={k:json.loads((D/'runs'/k/'check_result.json').read_text()) for k in ['normal','foreign_after_close']};assert all(x['passed'] for x in cases.values())
 after=P.protect();assert after==pre['protection'];assets=B.verify_assets()
 matrix={'schema':'C3.10-matrix/v1','passed':True,'new_native_count':23,'finite_checker_count':80,'baseline_native251_rerun':False,'cases':{},'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 for case,x in cases.items():
  run=N/'runs'/('owned_C310_'+case+'_01');w=json.loads((run/'observer/witness.json').read_text());r=json.loads((run/'result.json').read_text());assert w['observation_complete'] and w['business_ready_observed'] is False and w['normal_contract_qualified'] is False and w['counters']['accepted_activations']==0
  matrix['cases'][case]={'component_passed':x['passed'],'driver_passed':r['passed'],'resource_cleanup_complete':r['cleanup_complete'],'cleanup_roles':len(r['cleanup']),'Witness_observation_complete':True,'Witness_BusinessReady':False,'Accepted':0,'full_check_result_sha256':B.sha(D/'runs'/case/'check_result.json')}
 B.write(D/'postrun/matrix_current.json',matrix)
 out=D/'postrun/ldd';out.mkdir();producer=json.loads((D/'build/foreign_attempt02/result.json').read_text());libs={}
 for i,field in enumerate(['p1_c310_foreign_applied','test_c310_foreign_protocol']):
  binary=producer[field]['path'];assert B.sha(binary)==producer[field]['sha256'];assert B.command(out,'binary_'+str(i),['ldd',binary],10,161)==0
  text=(out/('binary_'+str(i)+'.log')).read_text();assert 'not found' not in text
  for word in re.findall(r'(/[^\s()]+)',text):
   p=Path(word)
   if p.is_file():libs[str(p.resolve())]=B.sha(p.resolve())
 B.write(D/'postrun/actual_foreign_library_pins.json',{'files':libs,'count':len(libs),'scope':'actual producer build ldd under pinned setup; no OS or WCET qualification'})
 paths={Path(p).resolve() for p in assets};paths.update(Path(p).resolve() for p in libs)
 for root in [N,D]:
  for p in root.rglob('*'):
   if p.is_file() and not any(s=='__pycache__' or s.startswith('build') for s in p.relative_to(root).parts[:-1]) and 'final_frozen_snapshot' not in p.parts:paths.add(p.resolve())
 # D/build is evidence (source snapshots/logs), not the large author object tree.
 paths.update(p.resolve() for p in (D/'build').rglob('*') if p.is_file())
 for attempt in ['01','02']:
  build=json.loads((D/f'build/foreign_attempt{attempt}/result.json').read_text());bd=Path(build['build_directory'])
  paths.update((bd/t).resolve() for t in ['p1_c310_foreign_applied','test_c310_foreign_protocol'])
  dp=json.loads((D/f'build/foreign_attempt{attempt}/compiler_dependency_pins.json').read_text())
  paths.update(Path(p).resolve() for p in dp['files'])
  paths.update(p.resolve() for p in bd.rglob('*.o.d'));paths.update(p.resolve() for p in bd.rglob('link.txt'))
  paths.update(p.resolve() for p in [bd/'CMakeCache.txt',bd/'compile_commands.json'] if p.is_file())
  paths.update(p.resolve() for p in bd.rglob('*.a') if p.name in ['libgtest.a','libgtest_main.a'])
 frozen=D/'final_frozen_snapshot';frozen.mkdir();records=[];fixed={}
 for i,p in enumerate(sorted(paths)):
  assert p.is_file() and not p.is_symlink();raw=p.read_bytes();dst=frozen/'files'/f'{i:05d}_{p.name}';dst.parent.mkdir(exist_ok=True)
  with dst.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  sha=B.sha(p);assert B.sha(dst)==sha;fixed[str(p)]=sha;fixed[str(dst)]=sha;records.append({'original':str(p),'copy':str(dst),'sha256':sha,'bytes':len(raw)})
 B.write(frozen/'manifest.json',{'schema':'C3.10-final-freeze/v1','files':records,'count':len(records),'stage_qualified':False});fixed[str(frozen/'manifest.json')]=B.sha(frozen/'manifest.json')
 assert all(B.sha(p)==sha for p,sha in fixed.items())
 qa={'schema':'C3.10-final-QA/v1','passed':True,'new_native_count':23,'finite_checker_count':80,'baseline_native251_rerun':False,'actual_owned_cases':2,'actual_Accepted':0,'new_frozen_pairs':len(records),'fixed_source_header_input_hashes':fixed,'actual_foreign_libraries':len(libs),'parent_before':pre['protection'],'parent_after':after,'actual_Witness_normal_business':False,'normal_business_contract_qualified':False,'identical_Storage_row_writer_unique_assignment':False,'same_owner_nonzero_qualification':False,'initial_full_untracked_snapshot_unavailable':True,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 B.write(D/'postrun/final_QA_current.json',qa);print(json.dumps({'passed':True,'frozen_pairs':len(records),'fixed_paths':len(fixed),'libraries':len(libs),'QA_sha256':B.sha(D/'postrun/final_QA_current.json')}))
if __name__=='__main__':main()
