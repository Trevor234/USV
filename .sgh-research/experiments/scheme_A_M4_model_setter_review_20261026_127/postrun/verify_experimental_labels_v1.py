from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/experimental_replay_v2';OUT.mkdir()
BUILD=ROOT/'build/attempt02'
registration=json.loads((ROOT/'evidence/attempt02/registration.json').read_text())
cases=registration['experimental_cases'];commands=[];results=[]
def execute(argv,timeout):
 r=subprocess.run(list(map(str,argv)),cwd=ROOT,env={**os.environ,'LD_LIBRARY_PATH':'/home/trevor/acados/lib'},capture_output=True,text=True,timeout=timeout)
 commands.append({'argv':list(map(str,argv)),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr});return r
r=execute(['cmake','--build',BUILD,'--target','experimental_f6','--parallel','2'],300)
if r.returncode==0:
 for case in cases:
  out=OUT/'runs'/case;r=execute([BUILD/'experimental_f6',case,out],60)
  p=out/'result.json';d=json.loads(p.read_text())if p.is_file()else{}
  ok=r.returncode==0 and d.get('passed')is True and all(x['passed']is True for x in d.get('assertions',[]))and'fresh'in d.get('comparison_scope','')
  results.append({'case':case,'passed':ok,'comparison_scope':d.get('comparison_scope')})
passed=len(results)==len(cases)and all(r['passed']for r in results)
sources={}
for p in (ROOT/'implementation/experiment_model').iterdir():
 if p.is_file():sources[str(p)]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
for name,data in [('commands.json',commands),('verification.json',{'passed':passed,'cases':results,'source_pins':sources,'old_label_correction_only':True,'algorithm_or_tolerance_changed':False,'qualification':{k:False for k in ['M4','F6','P1','plant','hard_realtime']}})]:
 with(OUT/name).open('x')as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'experimental_cases':len(results),'passed':passed}));sys.exit(0 if passed else 2)
