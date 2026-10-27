#!/usr/bin/env python3
import os
from pathlib import Path
import json
import shutil
import sys
from offline_support import Evidence, ROOT, pin, save

e=Evidence('E06',sys.argv[1])
model=ROOT/'implementation/standalone/model'
inc=Path('/home/trevor/USV/usv_mpc_ws/install/usv_mpc_cpp/include')
lib=inc.parent/'lib';acados=Path('/home/trevor/acados')
cases=[f'F6-{i}' for i in range(1,7)]+[
 'F6V-01-UNCOMMITTED','F6V-02-GEN-ZERO','F6V-03-STALE','F6V-04-NAN','F6V-05-IMMUTABLE',
 'F6V-06-PREPARING','F6V-07-LEGAL','F6V-08-WRONG-THREAD','F6V-09-FAULTED-SET',
 'F6V-10-FAULTED-RESET','F6V-11-ABORT-PREPARED','F6V-12-INPUT','F6V-13-API-EXCEPTION']
mutations={
 'uncommitted':('    if (!has_committed_) { out.reject = "model_not_committed"; return out; }\n','F6V-01-UNCOMMITTED','reject_model_not_committed'),
 'finite':('!std::all_of(p_global.begin(), p_global.end(), [](double x) { return std::isfinite(x); })','F6V-04-NAN','nan_model_refused'),
 'reset':('if (api_.reset(capsule_, 1) != 0) return false;','F6V-10-FAULTED-RESET','new_identity_not_published_after_failure'),
}
inputs={str(p):pin(p)for p in model.iterdir()if p.is_file()}
libraries={str(p):pin(p)for p in [lib/'libmpc_solver_lib.a',lib/'libcodegen_lib.a',lib/'libmpc_core_lib.a',acados/'lib/libacados.so',acados/'lib/libblasfeo.so',acados/'lib/libhpipm.so']}
save(e.out/'registration.json',{'cases':cases,'mutations':mutations,'source':inputs,'libraries':libraries,
 'tolerance':1e-8,'case_timeout_seconds':60,'auto_retry':0,'owner':'constructing thread',
 'adapter_limit':'nonzero adapter result tests policy; generated internal error propagation remains unverified'})

def build(directory,name):
 binary=e.out/name
 argv=['g++','-std=c++17','-O2','-I',directory,'-I',inc,'-I',inc/'usv_mpc_cpp/acados_generated',
 '-I',acados/'include','-I',acados/'include/blasfeo/include','-I',acados/'include/hpipm/include',
 '-I','/usr/include/eigen3',directory/'test_f6_state_v2.cpp','-o',binary,
 '-L',lib,'-lmpc_solver_lib','-lcodegen_lib','-lmpc_core_lib','-L',acados/'lib','-lacados','-lblasfeo','-lhpipm','-pthread',
 '-Wl,--wrap=usv_dyn_nmpc_acados_solve']
 r=e.command('build_'+name,argv);e.check('build.'+name,r.returncode==0)
 return binary if r.returncode==0 else None

env={**os.environ,'LD_LIBRARY_PATH':str(acados/'lib')}
def run(binary,case,out):
 r=e.command(case,[binary,case,out],timeout=60,env=env)
 p=out/'result.json';return r,json.loads(p.read_text())if p.is_file()else{}

binary=build(model,'model_states')
if binary:
 for case in cases:
  r,d=run(binary,case,e.out/'runs'/case)
  e.check(case,r.returncode==0 and d.get('passed')is True and bool(d.get('assertions'))and all(x['passed']is True for x in d['assertions']))
for name,(pattern,case,assertion)in mutations.items():
 directory=e.out/'mutations'/name;shutil.copytree(model,directory)
 p=directory/'model_transaction_v1.hpp';text=p.read_text();prepared=text.count(pattern)==1
 e.check('mutation.prepared.'+name,prepared)
 if not prepared:continue
 replacement={'finite':'false','reset':'(void)api_.reset(capsule_, 1);'}.get(name,'')
 p.write_text(text.replace(pattern,replacement))
 mutant=build(directory,'mut_'+name)
 if mutant:
  r,d=run(mutant,case,directory/'run')
  failed=[x['name']for x in d.get('assertions',[])if x['passed']is False]
  e.check('mutation.caught.'+name,r.returncode==2 and assertion in failed,failed)
e.check('pinned_installed_libraries_unchanged',all(pin(p)==v for p,v in libraries.items()))
result=e.finish(cases_registered=len(cases),libraries=libraries,source=inputs,real_C_entry_observer='linker --wrap',
               scope='single-owner finite model wrapper; current production source parity not claimed')
sys.exit(0 if result['status']=='PASS'else 2)
