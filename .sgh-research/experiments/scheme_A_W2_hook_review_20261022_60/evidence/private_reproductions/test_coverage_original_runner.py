from pathlib import Path
import subprocess,shutil,shlex,os,json,hashlib
src=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_pre_wiring_review_20261022_59/implementation/w2_author')
out=Path('/tmp/review_w2_tests_60')
out.mkdir(exist_ok=True)
for sub in ['worker','common']:
 shutil.copytree(src/sub,out/sub,dirs_exist_ok=True)
report={}
env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi'
for target in ['test_w2_native_boundary','test_w2_backend_wiring']:
 r=subprocess.run(['/tmp/w2build/'+target],capture_output=True,text=True,env=env)
 report[target]={'returncode':r.returncode,'output':r.stdout[-3000:]}
header=out/'worker/owned_cold_backend.hpp';text=header.read_text()
a=text.index('   if(boundary_&&boundary_->armed()&&boundary_->matches(ordinal,id)){')
b=text.index('   last_["backend_entries_started"]',a)
header.write_text(text[:a]+'   // REVIEW MUTATION: completely omit the Backend boundary check\n'+text[b:])
target='test_w2_backend_wiring'
flags={line.split(' = ',1)[0]:line.split(' = ',1)[1] for line in Path('/tmp/w2build/CMakeFiles/'+target+'.dir/flags.make').read_text().splitlines() if ' = ' in line}
args=[]
for k in ['CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS']: args+=shlex.split(flags[k].replace(str(src),str(out)))
obj=out/'mutant.o'
r=subprocess.run(['/usr/bin/c++',*args,'-c',str(out/'worker/test_w2_backend_wiring.cpp'),'-o',str(obj)],capture_output=True,text=True)
assert r.returncode==0,r.stderr
link=shlex.split(Path('/tmp/w2build/CMakeFiles/'+target+'.dir/link.txt').read_text())
link=[str(obj) if item.endswith('.cpp.o') else str(out/'mutant_backend') if item==target else str(Path('/tmp/w2build')/item) if item.startswith('gtest/') else item for item in link]
r=subprocess.run(link,capture_output=True,text=True)
assert r.returncode==0,r.stderr
r=subprocess.run([str(out/'mutant_backend')],capture_output=True,text=True,env=env)
report['all_backend_boundary_checks_deleted']={'returncode':r.returncode,'output':r.stdout[-4000:]}
report['original_header_sha']=hashlib.sha256((src/'worker/owned_cold_backend.hpp').read_bytes()).hexdigest()
(out/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
