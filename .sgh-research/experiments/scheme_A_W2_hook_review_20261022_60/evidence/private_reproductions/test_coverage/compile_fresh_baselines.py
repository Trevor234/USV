from pathlib import Path
import subprocess,shlex,os,json,hashlib,re,datetime
src=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_pre_wiring_review_20261022_59/implementation/w2_author')
out=Path('/tmp/review_w2_tests_60/fresh_baselines')
out.mkdir(exist_ok=True)
report={'source_tree':str(src),'schema':'W2-fresh-baseline-replay-v1','suites':{},'source_files':[]}
env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'
for name in ['test_w2_native_boundary','test_w2_backend_wiring']:
 source=src/'worker'/f'{name}.cpp'
 flags={line.split(' = ',1)[0]:line.split(' = ',1)[1] for line in Path('/tmp/w2build/CMakeFiles/'+name+'.dir/flags.make').read_text().splitlines() if ' = ' in line}
 args=[]
 for k in ['CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS']:args+=shlex.split(flags[k])
 obj=out/f'{name}.o';binary=out/name
 compile_cmd=['/usr/bin/c++',*args,'-c',str(source),'-o',str(obj)]
 link=shlex.split(Path('/tmp/w2build/CMakeFiles/'+name+'.dir/link.txt').read_text())
 link=[str(obj) if item.endswith('.cpp.o') else str(binary) if item==name else str(Path('/tmp/w2build')/item) if item.startswith('gtest/') else item for item in link]
 commands={'compile':compile_cmd,'link':link,'run':[str(binary)],'run_env':{'LD_LIBRARY_PATH':env['LD_LIBRARY_PATH']}}
 (out/f'{name}.commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 stage={}
 for phase,cmd in [('compile',compile_cmd),('link',link),('run',[str(binary)])]:
  r=subprocess.run(cmd,capture_output=True,text=True,env=env)
  (out/f'{name}.{phase}.stdout.txt').write_text(r.stdout)
  (out/f'{name}.{phase}.stderr.txt').write_text(r.stderr)
  stage[phase]={'returncode':r.returncode,'stdout':str(out/f'{name}.{phase}.stdout.txt'),'stderr':str(out/f'{name}.{phase}.stderr.txt')}
  assert r.returncode==0,(phase,r.stderr[-4000:])
  if phase=='run':
   matched=re.search(r'\[  PASSED  \] (\d+) tests?',r.stdout)
   stage[phase]['passed_tests']=int(matched.group(1)) if matched else 0
 report['suites'][name]=stage
 report['source_files'].append({'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
 report['suites'][name]['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
 print(name,stage['run']['passed_tests'],flush=True)
for f in ['owned_cold_backend.hpp','w2_native_boundary.hpp','w2_release_gate.hpp','w2_pipe_reader.hpp']:
 p=src/'worker'/f
 report['source_files'].append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
report['complete']=all(v['compile']['returncode']==0 and v['link']['returncode']==0 and v['run']['returncode']==0 for v in report['suites'].values())
report['total_passed']=sum(v['run']['passed_tests'] for v in report['suites'].values())
(out/'fresh_baseline_verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'complete':report['complete'],'total_passed':report['total_passed'],'report':str(out/'fresh_baseline_verification.json')},indent=2))
