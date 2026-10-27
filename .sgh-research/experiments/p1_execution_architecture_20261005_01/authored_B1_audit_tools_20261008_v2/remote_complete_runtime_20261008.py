from pathlib import Path
import sys,os,hashlib,json,shutil,subprocess
E=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01');R=E/'authored_runtime_v30_contract_20261007';P=E/'authored_B1_runtime_20261008_final';A=E/'authored_B1_C0_runtime_20261008';G=E/'B1_closed_assets_20261008.json'
sys.path.insert(0,str(R))
from run_worker_fault_matrix import verify_assets
from run_formal_no_output_validation import host_preflight
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
host=host_preflight();guard=verify_assets(G);assert not A.exists()
files={p.name:p for p in R.iterdir() if p.is_file() and p.suffix in ('.py','.json')};assert len(files)==45
assert not set(files)&{p.name for p in P.glob('*.py')}
files.update({p.name:p for p in P.glob('*.py')});assert len(files)==49;A.mkdir()
manifest={}
for n,p in files.items():
    raw=p.read_bytes()
    with (A/n).open('xb') as f:f.write(raw)
    manifest[n]={'sha256':sha(A/n),'bytes':len(raw),'copied_from':str(p)};assert manifest[n]['sha256']==sha(p)
env={**os.environ,'PYTHONPATH':str(A)+':'+os.environ.get('PYTHONPATH','')}
with (A/'new_tool_tests.log').open('xb') as f:q=subprocess.run(['/usr/bin/python3','-B','-m','unittest','-v','test_p1_witness','test_r5_diag_runner'],cwd=A,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=30)
log=(A/'new_tool_tests.log').read_text();assert 'Ran 63 tests' in log
result={'schema':'p1-B1-complete-runtime-v1','runtime_root':str(A),'files':manifest,'file_count':len(files),'returncode':q.returncode,'tests_discovered':63,'log_sha256':sha(A/'new_tool_tests.log'),'passed':q.returncode==0,'old_runtime_copied_byte_identical':True,'same_directory_dependencies_present':True,'host_before':host,'host_after':host_preflight(),'guard_before':guard,'guard_after':verify_assets(G),'C0_run':False,'R5_run':False,'physical_release':False}
with (A/'result.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
