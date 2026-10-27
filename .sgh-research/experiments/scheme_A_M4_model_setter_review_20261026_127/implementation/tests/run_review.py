#!/usr/bin/env python3
"""Finite review of isolated patches against freshly built current sources."""
from pathlib import Path
import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence'/sys.argv[1]
OUT.mkdir(parents=True,exist_ok=False)
BUILD=ROOT/'build'/sys.argv[1]
IMPL=ROOT/'implementation'
ENV={**os.environ,'LD_LIBRARY_PATH':'/home/trevor/acados/lib','PYTHONDONTWRITEBYTECODE':'1'}
checks=[];commands=[]
QUAL={k:False for k in ['M4','F6','P1','plant','hard_realtime']}
def pin(path):
 raw=Path(path).read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x')as f:f.write(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def check(name,ok,detail=None):
 if type(ok)is not bool:raise TypeError(name)
 checks.append({'name':name,'passed':ok,'detail':detail});print(('PASS 'if ok else'FAIL ')+name,flush=True)
 return ok
def command(name,argv,timeout=300):
 t=time.monotonic();r=subprocess.run(list(map(str,argv)),cwd=ROOT,env=ENV,capture_output=True,text=True,timeout=timeout)
 stem=f'{len(commands):02d}_{name}'
 (OUT/(stem+'.stdout')).write_text(r.stdout);(OUT/(stem+'.stderr')).write_text(r.stderr)
 commands.append({'name':name,'argv':list(map(str,argv)),'returncode':r.returncode,'elapsed_seconds':time.monotonic()-t,'timeout':timeout,'stdout':stem+'.stdout','stderr':stem+'.stderr'})
 return r
def demand(name,ok,detail=None):
 if not check(name,ok,detail):raise RuntimeError('mandatory check failed: '+name)
ROWS={'COLD':1,'WARM':8,'CUSTOM_MODEL':1,'APPLIED_ANCHOR':8,'RESET':5,'FAIL_COLD':1,
 'FAIL_WARM_EXHAUST':27,'NONFINITE_SOLUTION':3,'SOLVE_EXCEPTION':3,'APPLIED_INVALID':2,
 'BAD_N':0,'BAD_DT':0,'NEGATIVE_WEIGHT':0,'NAN_WEIGHT':0,'SETTER_ERROR':0,'NONFINITE_HYDRO':0}
COMMON=list(ROWS)[:-2]
EXPECTED_UNIT=['pack_all_30_distinct_slots','pack_preserves_IEEE_values_without_validation','apply_calls_adapter_once',
 'apply_exact_native_count_and_values','null_capsule_before_adapter','null_setter_rejected','nonfinite_before_adapter',
 'native_status_propagated','apply_input_unchanged','adapter_exception_propagates_to_owner']
F6=[f'F6-{i}'for i in range(1,7)]+['F6V-01-UNCOMMITTED','F6V-02-GEN-ZERO','F6V-03-STALE','F6V-04-NAN','F6V-05-IMMUTABLE','F6V-06-PREPARING','F6V-07-LEGAL','F6V-08-WRONG-THREAD','F6V-09-FAULTED-SET','F6V-10-FAULTED-RESET','F6V-11-ABORT-PREPARED','F6V-12-INPUT','F6V-13-API-EXCEPTION']
MUTATIONS={
 'pack_slot':('p_global_pack.hpp','pg[13] = h.Nr;','pg[13] = h.Nv;','pack_all_30_distinct_slots'),
 'argument_count':('p_global_apply.hpp','int(count));','int(count)-1);','apply_exact_native_count_and_values'),
 'input_alias':('p_global_apply.hpp','auto writable = values;','auto & writable = const_cast<Packed &>(values);','apply_input_unchanged'),
 'native_status':('p_global_apply.hpp','status == 0 ? ApplyCode::applied : ApplyCode::native_error','ApplyCode::applied','native_status_propagated')}
source_before={str(p):pin(p)for p in IMPL.rglob('*')if p.is_file()and'__pycache__'not in p.parts}
save(OUT/'registration.json',{'cases':ROWS,'ordinary_parity_cases':COMMON,'intentional_deltas':['SETTER_ERROR','NONFINITE_HYDRO'],
 'unit_assertions':EXPECTED_UNIT,'experimental_cases':F6,'mutations':MUTATIONS,'source_pins':source_before,'tolerance':1e-8,
 'timing_scope':'solve_time_ms excluded from parity; no timing qualification','case_timeout_seconds':60,'auto_retry':0,
 'implementation_scope':'isolated draft only','build_recipe':'generated C -O1; handwritten C++ -O2; functional comparison, not production release timing','qualification':QUAL})
def execute(binary,case,directory):
 r=command(case,[binary,case,directory],60)
 path=directory/'result.json';d=json.loads(path.read_text())if path.is_file()else{}
 demand('executed.'+str(directory.relative_to(OUT)),r.returncode==0 and bool(d),{'exit':r.returncode})
 return d
def compare(a,b,path=''):
 diffs=[];worst=0.0
 if isinstance(a,dict)and isinstance(b,dict):
  if set(a)!=set(b):return [path+':fields'],0.0
  for k in a:
   dd,w=compare(a[k],b[k],path+'/'+k);diffs+=dd;worst=max(worst,w)
 elif isinstance(a,list)and isinstance(b,list):
  if len(a)!=len(b):return [path+':population'],0.0
  for i,(x,y)in enumerate(zip(a,b)):
   dd,w=compare(x,y,path+'/'+str(i));diffs+=dd;worst=max(worst,w)
 elif type(a)is float and type(b)is float:
  delta=abs(a-b);worst=delta
  if not(math.isfinite(a)and math.isfinite(b))or delta>1e-8:diffs.append(path)
 elif type(a)is not type(b)or a!=b:diffs.append(path)
 return diffs,worst

results={};summary={};error=None
try:
 r=command('configure',['cmake','-S',IMPL/'cmake','-B',BUILD,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_FLAGS_RELEASE=-O1 -DNDEBUG','-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG'])
 demand('cmake.configure',r.returncode==0)
 cache=(BUILD/'CMakeCache.txt').read_text()
 demand('cmake.unique_home','CMAKE_HOME_DIRECTORY:INTERNAL='+str(IMPL/'cmake')in cache)
 r=command('build',['cmake','--build',BUILD,'--parallel','2'],900)
 demand('fresh_current_source_build',r.returncode==0)
 r=command('shared_parameters',[BUILD/'shared_parameters',OUT/'shared_parameters'],60)
 unit=json.loads((OUT/'shared_parameters/result.json').read_text())
 demand('shared_parameters.exact_population',r.returncode==0 and unit['passed']is True
        and[a['name']for a in unit['assertions']]==EXPECTED_UNIT and all(a['passed']is True for a in unit['assertions']))
 for variant in ['baseline','packing_only','checked_init']:
  results[variant]={}
  for case,count in ROWS.items():
   d=execute(BUILD/('behavior_'+variant),case,OUT/'runs'/variant/case);results[variant][case]=d
   demand('population.'+variant+'.'+case,len(d['rows'])==count)
   demand('resources.'+variant+'.'+case,d['capsule_created']==d['capsule_freed']==d['graph_freed'])
   if case in ['BAD_N','BAD_DT','NEGATIVE_WEIGHT','NAN_WEIGHT']:
    demand('guard.'+variant+'.'+case,d['constructed']is False and d['solve_boundaries']==0 and d['exception_type']in ['runtime_error','invalid_argument'])
   elif case in COMMON:
    demand('constructor.'+variant+'.'+case,d['constructed']is True)
   for index,row in enumerate(d['rows']):
    expected=not(case=='FAIL_COLD'or(case=='FAIL_WARM_EXHAUST'and(index in range(3,25)or index==26))or(case in ['NONFINITE_SOLUTION','SOLVE_EXCEPTION']and index==1))
    demand('outcome.'+variant+'.'+case+'.'+str(index),row['success']is expected and len(row['u'])==2 and all(math.isfinite(x)and abs(x)<=25 for x in row['u']))
    if expected:demand('prediction.'+variant+'.'+case+'.'+str(index),row['X']['rows']==6 and row['X']['cols']==21 and row['U']['rows']==2 and row['U']['cols']==20)
  warm=results[variant]['FAIL_WARM_EXHAUST']['rows']
  demand('fallback_exhaust_recover_counter.'+variant,'fallback=shift_traj(fail=1)'in warm[3]['error']and'fallback=zero_thrust(fail=20)'in warm[22]['error']and warm[25]['success']is True and'fail=1)'in warm[26]['error'])
 for case in ROWS:
  diffs,worst=compare(results['baseline'][case],results['packing_only'][case])
  demand('pure_packing_parity.'+case,not diffs,{'worst_numeric_difference':worst,'differences':diffs[:5]})
  summary['pure.'+case]={'worst':worst,'diffs':diffs}
 for case in COMMON:
  diffs,worst=compare(results['baseline'][case],results['checked_init'][case])
  demand('checked_ordinary_parity.'+case,not diffs,{'worst_numeric_difference':worst,'differences':diffs[:5]})
  summary['checked.'+case]={'worst':worst,'diffs':diffs}
 failure=results['checked_init']['SETTER_ERROR'];baseline=results['baseline']['SETTER_ERROR']
 demand('intentional.setter_error_rejects_and_cleans',baseline['constructed']is True and failure['constructed']is False and'native_status=17'in failure['exception']and failure['solve_boundaries']==0)
 invalid=results['checked_init']['NONFINITE_HYDRO'];baseline=results['baseline']['NONFINITE_HYDRO']
 demand('intentional.nonfinite_refused_before_bad_payload',baseline['constructed']is True and any(r['finite']is False for r in baseline['setter_calls'])and invalid['constructed']is False and not any(r['finite']is False for r in invalid['setter_calls'])and invalid['solve_boundaries']==0)
 for case in F6:
  d=execute(BUILD/'experimental_f6',case,OUT/'experimental'/case)
  demand('experimental_shared.'+case,d['passed']is True and bool(d['assertions'])and all(a['passed']is True for a in d['assertions']))
 for name,(filename,pattern,replacement,assertion)in MUTATIONS.items():
  private=OUT/'mutations'/name/'include/usv_mpc_cpp';private.mkdir(parents=True)
  for header in ['p_global_pack.hpp','p_global_apply.hpp']:shutil.copy2(IMPL/'checked_init/include/usv_mpc_cpp'/header,private/header)
  p=private/filename;text=p.read_text();demand('mutation.prepared.'+name,text.count(pattern)==1);p.write_text(text.replace(pattern,replacement))
  binary=OUT/'mutations'/name/'unit'
  r=command('build_mut_'+name,['g++','-std=c++17','-O2','-I',private.parents[0],'-I',IMPL/'checked_init/include','-I',IMPL/'baseline/acados_generated','-I','/usr/include/eigen3','-I','/home/trevor/acados/include','-I','/home/trevor/acados/include/blasfeo/include','-I','/home/trevor/acados/include/hpipm/include',IMPL/'tests/test_shared_parameters.cpp','-L',BUILD,'-lgenerated_current','-L','/home/trevor/acados/lib','-lacados','-lhpipm','-lblasfeo','-lm','-o',binary])
  demand('mutation.compiled.'+name,r.returncode==0)
  r=command('mut_'+name,[binary,binary.parent/'run'],60)
  p=binary.parent/'run/result.json';d=json.loads(p.read_text())if p.is_file()else{}
  failed=[a['name']for a in d.get('assertions',[])if a['passed']is False]
  demand('mutation.caught.'+name,r.returncode==2 and assertion in failed,failed)
 demand('all_current_review_sources_unchanged',all(pin(p)==record for p,record in source_before.items()))
except Exception as exc:
 error=type(exc).__name__+': '+str(exc);print(error,flush=True)
save(OUT/'commands.json',commands)
save(OUT/'parity_summary.json',summary)
failures=[r for r in checks if not r['passed']]
ok=not failures and error is None
save(OUT/'verification.json',{'status':'PASS'if ok else'FAIL_STOP','checks':checks,'failures':failures,'unexpected_error':error,
 'behavior_cases_per_variant':len(ROWS),'ordinary_parity_cases':len(COMMON),'experimental_F6_cases':len(F6),
 'unit_assertions':len(EXPECTED_UNIT),'mutations':len(MUTATIONS),'fresh_codegen_sources':True,'no_installed_solver_archive_linked':True,
 'qualification':QUAL,'production_landing':False,'ROS_initialized':False,'new_owned_runs':0})
print(json.dumps({'status':'PASS'if ok else'FAIL_STOP','checks':len(checks),'failures':len(failures),'error':error}),flush=True)
sys.exit(0 if ok else 2)
