from pathlib import Path
import importlib.util,sys,shlex,subprocess,os,json,re,shutil,concurrent.futures,hashlib,time
src=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_pre_wiring_review_20261022_59/implementation/w2_author')
out=Path('/tmp/review_w2_tests_60/five_registered_mutations');out.mkdir(exist_ok=True)
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('registered_wiring_verifier',src/'worker/run_wiring_verification.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'
original_pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [src/'worker/w2_native_boundary.hpp',src/'worker/owned_cold_backend.hpp']}
def one(entry):
 name,(target,pattern,replacement)=entry
 work=out/name;work.mkdir(exist_ok=True)
 for sub in ['worker','common']:shutil.copytree(src/sub,work/sub,dirs_exist_ok=True)
 original=target.read_text();mutated,count=re.subn(pattern,replacement,original)
 report={'name':name,'prepared':count==1,'matches':count,'suites':{}}
 if count!=1:return report
 private_target=work/target.relative_to(src);private_target.write_text(mutated)
 report['mutated_file']=str(private_target);report['original_sha256']=hashlib.sha256(original.encode()).hexdigest();report['mutant_sha256']=hashlib.sha256(mutated.encode()).hexdigest()
 for suite in ['test_w2_native_boundary','test_w2_backend_wiring']:
  flags={line.split(' = ',1)[0]:line.split(' = ',1)[1] for line in Path('/tmp/w2build/CMakeFiles/'+suite+'.dir/flags.make').read_text().splitlines() if ' = ' in line}
  args=[]
  for k in ['CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS']:args+=shlex.split(flags[k].replace(str(src),str(work)))
  obj=work/f'{suite}.o';binary=work/suite
  cc=['/usr/bin/c++',*args,'-c',str(work/'worker'/f'{suite}.cpp'),'-o',str(obj)]
  link=shlex.split(Path('/tmp/w2build/CMakeFiles/'+suite+'.dir/link.txt').read_text())
  link=[str(obj) if item.endswith('.cpp.o') else str(binary) if item==suite else str(Path('/tmp/w2build')/item) if item.startswith('gtest/') else item for item in link]
  commands={'compile':cc,'link':link,'run':[str(binary)],'run_env':{'LD_LIBRARY_PATH':env['LD_LIBRARY_PATH']}}
  (work/f'{suite}.commands.json').write_text(json.dumps(commands,indent=2)+'\n')
  rec={}
  for phase,cmd in [('compile',cc),('link',link),('run',[str(binary)])]:
   r=subprocess.run(cmd,capture_output=True,text=True,env=env)
   (work/f'{suite}.{phase}.stdout.txt').write_text(r.stdout);(work/f'{suite}.{phase}.stderr.txt').write_text(r.stderr)
   rec[phase]={'returncode':r.returncode}
   if phase=='run':
    rec[phase]['failed_tests']=sorted(set(re.findall(r'\[  FAILED  \] (\w+\.\w+)',r.stdout)))
    matched=re.search(r'\[  PASSED  \] (\d+) tests?',r.stdout);rec[phase]['passed_tests']=int(matched.group(1)) if matched else 0
   if phase!='run' and r.returncode!=0:break
  report['suites'][suite]=rec
 report['caught_by_test_suite']=any(rec.get('run',{}).get('failed_tests') for rec in report['suites'].values())
 (work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(name,report['caught_by_test_suite'],[t for s in report['suites'].values() for t in s.get('run',{}).get('failed_tests',[])],flush=True)
 return report
start=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,m.MUTATIONS.items()))
final={'schema':'W2-private-five-registered-mutations-v1','results':results,'all_prepared':all(r['prepared'] for r in results),'all_caught':all(r.get('caught_by_test_suite') for r in results),'elapsed_s':time.monotonic()-start,'original_pins':original_pins,'originals_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in original_pins.items())}
(out/'five_registered_mutations_verification.json').write_text(json.dumps(final,indent=2)+'\n')
print(json.dumps({k:final[k] for k in ['all_prepared','all_caught','originals_unchanged','elapsed_s']},indent=2))
