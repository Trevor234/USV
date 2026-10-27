"""Read-only existing formal-contract compatibility probe; no ROS or compilation."""
from pathlib import Path
import copy,hashlib,importlib.util,json,re,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;W=D.parent;A=W/'scheme_A_owned_business_start_20261020_39/author'
PINS={}
def raw(p):
 p=Path(p);b=p.read_bytes();f=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());assert str(p) not in PINS or PINS[str(p)]==f;PINS[str(p)]=f;return b
def load(p):return json.loads(raw(p))
helper=A/'runtime/p1_full_contract.py';sys.path.insert(0,str(helper.parent));spec=importlib.util.spec_from_file_location('existing_frozen_formal_contract',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for p in [helper,helper.with_name('p1_contract_spec_v1.json'),helper.with_name('p1_resource_contract.py')]:
 if p.exists():raw(p)
c=load(W/'scheme_A_post_lease_fresh_recovery_20261020_42/author/pair_wakeup_contract_v1.json')
cpp=raw(A/'observer/src/shadow/p1_full_contract.hpp').decode();native=json.loads(re.search(r'R"P1BASE\((.*?)\)P1BASE"',cpp,re.S).group(1));assert native==c
pybase=m.SPEC['legacy_baseline'];old_ok=m.validate_fields(copy.deepcopy(pybase))==pybase
error=None
try:m.validate_fields(copy.deepcopy(c))
except m.ContractError as e:error=str(e)
assert old_ok and error is not None
changed={k:dict(python=pybase[k],current_native=c[k]) for k in pybase.keys()&c.keys() if type(pybase[k]) is not type(c[k]) or pybase[k]!=c[k]}
gate=raw(A/'common/business_start_gate_v1.hpp').decode();entry=raw(A/'observer/src/shadow/p1_shadow_entry.hpp').decode();ctor=raw(A/'observer/src/shadow/regulator_shadow_observer.cpp').decode()
assert 'ContractProfile::PreFreeze?mode=="no_output"' in cpp
assert 'require(mode=="shadow","only explicitly declared shadow mode is supported")' in entry
assert 'mode=="shadow"&&witnessed&&fault_enabled' in gate
assert 'p1::shadow::require_shadow_mode(mode_)' in ctor and 'p1::require_runtime_contract_mode(c_,mode_)' in ctor
before=dict(PINS)
for p in before:raw(p)
assert PINS==before
report=dict(schema='existing-formal-compatibility-probe/v1',probe_passed=True,new_ROS_runs=0,CXX_builds=0,
 formal_v3_schema_already_implemented=True,current_native_baseline_fields=len(native),old_python_baseline_fields=len(pybase),
 current_native_spec_sha256=re.search(r'full_contract_spec_sha256 = "([0-9a-f]+)"',cpp).group(1),
 old_python_spec_sha256=hashlib.sha256(raw(helper.with_name('p1_contract_spec_v1.json'))).hexdigest(),
 old_python_baseline_self_validates=True,current_diag10_rejected_by_old_python=True,actual_python_rejection=error,
 extra_current_fields=sorted(c.keys()-pybase.keys()),missing_current_fields=sorted(pybase.keys()-c.keys()),same_key_value_differences=changed,
 existing_formal_pre_freeze_modes=['no_output'],current_owned_Observer_modes=['shadow'],formal_pre_freeze_owned_Observer_mode_intersection=[],
 authenticated_business_gate_requires_fault_permission_true=True,formal_contract_requires_fault_permission_false=True,
 existing_frozen_shape_marker_is_not_runtime_release=True,physical_execute_release_enabled=False,
 next_implementation='reuse existing formal v3; synchronize current field/value spec and exact role/mode/owned-start matrices before formal freeze; no flag bypass',
 B5_formal_freeze_ready=False,stage_qualified=False,execute_qualified=False,research_conclusion=False,
 input_sha256_before=before,input_sha256_after=before)
with (D/'evidence/formal_compatibility_probe_v1.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:report[k] for k in ['probe_passed','formal_v3_schema_already_implemented','current_native_baseline_fields','old_python_baseline_fields','extra_current_fields','current_diag10_rejected_by_old_python','formal_pre_freeze_owned_Observer_mode_intersection','B5_formal_freeze_ready']},ensure_ascii=False))
