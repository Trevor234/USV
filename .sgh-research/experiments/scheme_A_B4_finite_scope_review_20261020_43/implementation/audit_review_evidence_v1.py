"""Replay declared source/closed-raw pins and review integrity; no ROS/runtime tests."""
from pathlib import Path
import ast,hashlib,json,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;P=D.parent/'scheme_A_post_lease_fresh_recovery_20261020_42';sys.path.insert(0,str(D/'implementation'))
from check_B4_review_v1 import check
PINS={}
def need(v,w):
 if not v:raise ValueError(w)
def raw(p):
 p=Path(p);b=p.read_bytes();v=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());need(str(p) not in PINS or PINS[str(p)]==v,'changed:'+str(p));PINS[str(p)]=v;return b
def load(p):return json.loads(raw(p))
def pin(p):b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def merge(rows):
 for p,f in rows.items():need(pin(p)=={k:f[k] for k in ['bytes','sha256']},'referenced input changed:'+p)
def main():
 review=load(D/'implementation/B4_selected_policy_review_v1.json');facts=load(D/'evidence/current_source_facts_v1.json');reg=load(P/'implementation/current_B4_applicability_v1.json')
 probe=load(D/'evidence/formal_compatibility_probe_v1.json');gap=load(D/'evidence/full_command_gap_scope_v1.json')
 result=check(review,facts,reg,probe,gap)
 for obj in [facts,probe]:
  need(obj['input_sha256_before']==obj['input_sha256_after'],'producer input stability');merge(obj['input_sha256_after'])
 merge(gap['input_pins']);metric=load(D/'evidence/metric_scope_notes_v1.json');merge(metric['input_pins'])
 need(metric['failed_sequence'] in metric['Witness_sequences'] and metric['failed_sequence'] not in metric['Source_sequences'],'V1 Source gap interpretation')
 verification=load(D/'verification/review_artifact_checks_v1.json');need(verification['passed'] and verification['negative_count']==18 and all(r['rejected'] for r in verification['cases']),'18 review rejection cases')
 merge(verification['input_sha256_after'])
 freeze=load(P/'postrun/selected_profile_evidence_freeze_v1.json');merge(freeze['input_sha256_after'])
 current=load(P/'postrun/final_QA_v1.json');need(current['passed'] and current['current_selected_post_lease41_recovery_case_passed'],'sealed current case authority')
 candidate_meta=load(D/'evidence/pre_freeze_candidate_preparation_v1.json');candidate=load(D/'implementation/current_pre_freeze_candidate_v1.json')
 need(candidate_meta['candidate_only'] and candidate_meta['Native_validator_executed'] is False and candidate_meta['runtime_executed'] is False,'candidate cannot promote validation')
 need(candidate_meta['contract_candidate']['sha256']==pin(D/'implementation/current_pre_freeze_candidate_v1.json')['sha256'],'prepared candidate byte binding')
 baseline=review['unchanged_contract_values'];expected=set(baseline)-{'diagnostic_contract_revision'}|{'execution_contract_revision','resource_contract_revision','supported_parameter_profile','freeze_evidence_sha256'}
 need(len(candidate)==84 and set(candidate)==expected,'84 formal candidate field set')
 for k in set(baseline)-{'schema','qualification','execute_qualified','parameters_are_diagnostic_only','fault_injection_enabled','diagnostic_contract_revision'}:
  need(json.dumps(candidate[k],sort_keys=True)==json.dumps(baseline[k],sort_keys=True),'candidate fixed parameter drift:'+k)
 need(candidate['schema']=='p1-execution-contract-v3' and candidate['qualification']=='execution_pre_freeze' and candidate['fault_injection_enabled'] is False
  and candidate['execute_qualified'] is False and candidate['parameters_are_diagnostic_only'] is True and candidate['freeze_evidence_sha256']=='','existing pre-freeze permission shape')
 details=load(D/'evidence/formal_compatibility_details_v1.json');need(candidate['supported_parameter_profile']==details['native_supported_parameter_profile'],'candidate native profile id')
 plan=load(D/'implementation/B5_minimum_compatibility_plan_v1.json');need(plan['reuse_existing_formal_v3'] and plan['new_formal_schema_required'] is False and plan['formal_freeze_completed'] is False,'minimum B5 plan scope')
 for p in sorted(D.rglob('*.py')):ast.parse(raw(p))
 before=dict(PINS)
 for p in before:raw(p)
 need(PINS==before,'final evidence replay input stability')
 out=dict(schema='B4-source-policy-review-evidence-audit/v1',passed=True,positive_review=result,source_and_closed_raw_inputs_unchanged=True,
  input_sha256_before=before,input_sha256_after=PINS,input_count=len(before),
  metadata_bindings=5,groups_reviewed=8,review_artifact_negative_cases=18,formal_candidate_fields=84,
  B4_selected_source_policy_review_complete=True,B5_compatibility_implementation_next=True,B5_current_assets_formal_freeze_ready=False,
  new_ROS_runs=0,new_CXX_builds=0,new_Native_runs=0,current_runtime_or_contract_edited=False,
  stage_qualified=False,execute_qualified=False,research_conclusion=False)
 with (D/'postrun/review_evidence_audit_v1.json').open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2)
 print(json.dumps(dict(passed=True,input_count=len(before),groups=8,metadata_bindings=5,review_negatives=18,new_ROS_runs=0)))
if __name__=='__main__':main()
