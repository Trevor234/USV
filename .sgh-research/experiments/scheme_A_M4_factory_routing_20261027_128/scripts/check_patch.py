import json, shutil
from run_matrix import ROOT, command, pin, save

out=ROOT/'evidence/patch_replay01';out.mkdir(exist_ok=False)
private=out/'private_root';(private/'src').mkdir(parents=True)
source=ROOT/'implementation/current/src/mpc_solver.cpp'
candidate=ROOT/'implementation/admission_guard/src/mpc_solver.cpp'
shutil.copy2(source,private/'src/mpc_solver.cpp')
patch=ROOT/'patches/01_factory_shared_parameter_admission.patch'
dry=command(['patch','--batch','--forward','-p1','-d',private,'--dry-run','-i',patch],out/'dry_run')
assert dry['returncode']==0,'dry_run_failed'
applied=command(['patch','--batch','--forward','-p1','-d',private,'-i',patch],out/'apply')
assert applied['returncode']==0,'apply_failed'
assert (private/'src/mpc_solver.cpp').read_bytes()==candidate.read_bytes(),'candidate_differs'
save(out/'verification.json',{'complete':True,'target':'private_root_only','production_application':False,
                            'patch':pin(patch),'candidate':pin(candidate),'dry_run':dry,'apply':applied})
print(json.dumps({'complete':True,'production_application':False}))
