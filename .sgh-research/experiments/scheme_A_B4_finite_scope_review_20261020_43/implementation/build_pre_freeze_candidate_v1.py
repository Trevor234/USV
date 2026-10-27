"""Prepare exact current v3 fields for later parity work; no runtime acceptance claim."""
from pathlib import Path
import copy,hashlib,json,re
D=Path(__file__).resolve().parent.parent;P=D.parent/'scheme_A_post_lease_fresh_recovery_20261020_42';H=D.parent/'scheme_A_owned_business_start_20261020_39/author/observer/src/shadow/p1_full_contract.hpp'
def pin(p):
 b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
c=json.loads((P/'author/pair_wakeup_contract_v1.json').read_bytes());old=copy.deepcopy(c);del c['diagnostic_contract_revision']
profile=re.search(r'contract_parameter_profile = "([^"]+)"',H.read_text()).group(1)
c.update(schema='p1-execution-contract-v3',qualification='execution_pre_freeze',execute_qualified=False,
 parameters_are_diagnostic_only=True,fault_injection_enabled=False,execution_contract_revision=1,resource_contract_revision=1,
 supported_parameter_profile=profile,freeze_evidence_sha256='')
assert len(c)==84 and c['pending_final_calibration']==old['pending_final_calibration']
for k,v in old.items():
 if k not in ['schema','qualification','execute_qualified','parameters_are_diagnostic_only','fault_injection_enabled','diagnostic_contract_revision']:assert c[k]==v
path=D/'implementation/current_pre_freeze_candidate_v1.json'
with path.open('x') as f:json.dump(c,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
r=dict(schema='current-formal-candidate-preparation/v1',passed=True,contract_candidate=dict(path=str(path),**pin(path)),
 source_current_contract=dict(path=str(P/'author/pair_wakeup_contract_v1.json'),**pin(P/'author/pair_wakeup_contract_v1.json')),
 CXX_field_rule_authority=dict(path=str(H),**pin(H)),candidate_fields=84,current_baseline_fields=81,kept_numeric_domain_model_cost_and_policies=True,
 intended_existing_formal_mode='no_output',old_pending_preserved=True,freeze_marker_empty=True,
 candidate_only=True,Native_validator_executed=False,Python_parity_repaired=False,current_owned_Observer_entry_accepts_candidate=False,
 runtime_executed=False,formal_freeze_completed=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'evidence/pre_freeze_candidate_preparation_v1.json').open('x') as f:json.dump(r,f,ensure_ascii=False,indent=2)
print(json.dumps(dict(candidate_prepared=True,fields=84,fault_permission=False,execute_permission=False,validator_or_runtime_run=False)))
