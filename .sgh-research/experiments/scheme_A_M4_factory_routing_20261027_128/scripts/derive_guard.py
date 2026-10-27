from pathlib import Path
import difflib, json
from run_matrix import ROOT, pin, save

evidence=ROOT/'evidence/characterization03'
verified=json.loads((evidence/'verification.json').read_text())
assert verified['complete'] and verified['case_count']==52
examples={}
for id in ['NAN_HYDRO','INF_HYDRO','DIRECT_NAN_HYDRO','DIRECT_INF_HYDRO']:
    p=evidence/'cases/checked_init/on'/id/'result.json'
    r=json.loads(p.read_text())
    assert r['constructed'] and r['backend']=='casadi' and not r['rows'] and r['native_solves']==0
    examples[id]={'path':str(p),'pin':pin(p),'constructed':r['constructed'],'backend':r['backend'],
                  'allocation_attempts':r['allocation_attempts'],'created':r['created'],'freed':r['capsule_freed']}
save(ROOT/'evidence/reproduced_admission_bypass_v1.json',{
    'reproduced':True,'examples':examples,'invalid_model_solve_executed':False,
    'meaning':'checked Acados constructor rejection is bypassed by actual Casadi construction; direct Casadi factory has same admission gap',
    'authorized_minimal_fix':'Reject nonfinite 30-element shared packing before factory try and before direct Casadi factory; preserve finite backend fallback',
})
source=ROOT/'implementation/current/src/mpc_solver.cpp'
original=source.read_text()
guard='''namespace
{
void validate_model_parameters(const MpcParams & params)
{
  const auto values = p_global::pack(params);
  if (!std::all_of(values.begin(), values.end(), [](double x) { return std::isfinite(x); })) {
    throw std::invalid_argument("MPC p_global parameters must be finite");
  }
}
}  // namespace

'''
text=original.replace('#include <cstdio>','#include <cstdio>\n#include <algorithm>\n#include <cmath>\n#include "usv_mpc_cpp/p_global_pack.hpp"',1)
assert text.count('namespace usv_mpc\n{\n')==1
text=text.replace('namespace usv_mpc\n{\n','namespace usv_mpc\n{\n\n'+guard,1)
for name in ['make_dynamic_mpc','make_casadi_dynamic_mpc']:
    marker=f'{name}(const MpcParams & params)\n{{\n'
    assert text.count(marker)==1
    text=text.replace(marker,marker+'  validate_model_parameters(params);\n',1)
target=ROOT/'implementation/admission_guard/src/mpc_solver.cpp'
target.parent.mkdir(parents=True,exist_ok=True)
with target.open('x') as f:f.write(text)
patch=''.join(difflib.unified_diff(original.splitlines(keepends=True),text.splitlines(keepends=True),
         fromfile='a/src/mpc_solver.cpp',tofile='b/src/mpc_solver.cpp'))
with (ROOT/'patches/01_factory_shared_parameter_admission.patch').open('x') as f:f.write(patch)
save(ROOT/'postrun/patch_v1.json',{'base_factory':{'path':str(source),'pin':pin(source)},
    'candidate_factory':{'path':str(target),'pin':pin(target)},
    'patch':pin(ROOT/'patches/01_factory_shared_parameter_admission.patch'),
    'requires_batch127':'01 pure packing + 02 checked initialization; no production application',
    'finite_fallback_policy':'unchanged; reported status17 may choose Casadi when compiled in',
    'physical_parameter_validity':'not established by a finite check'})
print(json.dumps({'reproduced':True,'minimal_patch_created':True}))
