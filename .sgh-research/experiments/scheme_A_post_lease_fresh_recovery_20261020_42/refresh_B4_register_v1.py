"""Reuse sealed B4 registry checker against current actual roles and source bundles; no ROS."""
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;W=D.parent
helper=W/'scheme_A_B4_applicability_20261019_31/implementation/b4_applicability_v1.py'
def pin(p):
 b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
assert json.loads((D/'postrun/fresh_recovery_actual_audit_v2.json').read_bytes())['passed']
(D/'implementation').mkdir(exist_ok=False)
manifest=json.loads((D/'author/build_manifest_current.json').read_bytes())
indices={'synthetic_source' if r['role']=='fixture' else r['role']:i for i,r in enumerate(manifest)}
helper_pin=pin(helper);wrapper_pin=pin(__file__)
results=[]
for mode in ['build','check']:
 spec=importlib.util.spec_from_file_location('sealed_current_B4_'+mode,helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.D=D;m.W=W;m.N=D/'author';m.R=D/'author/runs/fresh_after_lease_01';m.ROLE_INDEX=indices
 out=D/'verification'/('B4_register_'+mode+'_v1.json')
 argv=[str(helper),mode,'--output',str(out)]
 if mode=='check':
  path=D/'implementation/current_B4_applicability_v1.json';argv+=['--register',str(path),'--expected-sha256',pin(path)['sha256']]
 sys.argv=argv;m.main();report=json.loads(out.read_bytes());assert report['passed'] and report['only_register_integrity_checked_not_B4_phase'];results.append(dict(mode=mode,output=str(out),pin=pin(out)))
assert pin(helper)==helper_pin and pin(__file__)==wrapper_pin
register=json.loads((D/'implementation/current_B4_applicability_v1.json').read_bytes())
summary=dict(schema='B4-current-role-register-refresh/v1',passed=True,current_actual_run='fresh_after_lease_01',fields=81,hydro_fields=19,roles=5,
 sealed_batch31_checker_reused_unchanged=helper_pin,context_overrides=dict(author=str(D/'author'),run=str(D/'author/runs/fresh_after_lease_01'),role_index=indices),
 new_register=pin(D/'implementation/current_B4_applicability_v1.json'),results=results,
 original_targeted_register_negatives_reused=13,new_targeted_register_tests_executed=0,
 pending_original_groups=register['pending_original_groups'],literal_refs_are_not_automatic_runtime_domain_qualification=True,
 only_register_integrity_checked=True,new_ROS_runs=0,new_CXX_builds=0,B4_phase_qualified=False,formal_B5_freeze=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'postrun/B4_current_register_refresh_v1.json').open('x') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(dict(passed=True,current_fields=81,current_roles=5,build_and_SHA_check=True,B4_phase_qualified=False)))
