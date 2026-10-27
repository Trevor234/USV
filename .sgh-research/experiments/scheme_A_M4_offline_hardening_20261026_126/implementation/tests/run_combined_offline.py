"""E09 fixed order; children use fresh evidence under E09, never historical paths."""
from pathlib import Path
import json,os,sys
from offline_support import Evidence,ROOT,pin,save
e=Evidence('E09',sys.argv[1]);out=e.out
inputs={str(p):pin(p)for p in sorted((ROOT/'implementation').rglob('*'))if p.is_file()and'__pycache__'not in p.parts and p.suffix in ['.py','.hpp','.h','.cpp','.sh']}
families=['Q','RNW','A105','Epoch','Model','B2','History']
save(out/'registration.json',{'fixed_order':families,'source_pins':inputs,'owned_runs':0,'auto_retry':0,
 'acceptance':'each current functional suite completes with no failures; historical process failure remains separately FAIL_STOP'})
steps=[
 ('Q',[sys.executable,'-B',ROOT/'implementation/run_e01.py',os.path.relpath(out/'Q',ROOT/'evidence/E01')],out/'Q/verification.json'),
 ('RNW',[sys.executable,'-B',ROOT/'implementation/tests/run_rnw_full.py',out/'RNW'],out/'RNW/verification.json'),
 ('RNW_entry',[sys.executable,'-B',ROOT/'implementation/tests/run_real_preflight.py',out/'RNW_entry'],out/'RNW_entry/verification.json'),
 ('A105',[sys.executable,'-B',ROOT/'implementation/run_e04.py',os.path.relpath(out/'A105',ROOT/'evidence/E04')],out/'A105/verification.json'),
 ('Epoch',[sys.executable,'-B',ROOT/'implementation/tests/run_e05_v2.py',out/'Epoch'],out/'Epoch/verification.json'),
 ('Model',[sys.executable,'-B',ROOT/'implementation/tests/run_e06.py',out/'Model'],out/'Model/verification.json'),
 ('B2',[sys.executable,'-B',ROOT/'implementation/tests/run_e07.py',out/'B2'],out/'B2/verification.json'),
 ('History',[sys.executable,'-B',ROOT/'implementation/tests/run_e08.py',out/'History'],out/'History/verification.json'),
]
completed=[]
for name,argv,verification in steps:
 print('START '+name,flush=True)
 r=e.command(name,argv,timeout=900,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
 d=json.loads(verification.read_text())if verification.is_file()else{}
 passed=r.returncode==0 and d.get('status')=='PASS'and d.get('failures')==[]
 e.check('suite.'+name,passed,{'exit':r.returncode,'verification':str(verification)})
 completed.append({'suite':name,'passed':passed,'verification':str(verification),'pin':pin(verification)if verification.is_file()else None})
 if not passed:
  print('STOP: child suite did not pass',flush=True);break
e.check('all_fixed_families_executed',len(completed)==len(steps))
e.check('same_current_source_before_after',all(pin(p)==v for p,v in inputs.items()))
save(out/'population.json',completed)
result=e.finish(fixed_order=families,child_suites=completed,source_files=len(inputs),historical_process_conformance=False)
sys.exit(0 if result['status']=='PASS'else 2)
