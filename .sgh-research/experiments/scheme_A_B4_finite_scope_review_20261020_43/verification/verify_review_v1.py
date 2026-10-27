"""Check actual policy artifact plus adversarial in-memory promotion cases; no ROS."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;P=D.parent/'scheme_A_post_lease_fresh_recovery_20261020_42';sys.path.insert(0,str(D/'implementation'))
from check_B4_review_v1 import check
files=[D/'implementation/B4_selected_policy_review_v1.json',D/'evidence/current_source_facts_v1.json',P/'implementation/current_B4_applicability_v1.json',D/'evidence/formal_compatibility_probe_v1.json',D/'evidence/full_command_gap_scope_v1.json']
def pin(p):
 b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
before={str(p):pin(p) for p in files};base=[json.loads(p.read_bytes()) for p in files]
positive=check(*base);cases=[]
names=['missing_group','duplicate_group','wrong_rho','bool_as_numeric','source_freshness_promoted','RTF_as_hard_bound','mixed_general_promoted','twenty_seconds_from_short_runs','full_gap_qualified','Observer_physical_outlet_promoted','metadata_mapping_missing','wrong_source_line','erased_M4_bootstrap','M4_partial_qualified','cleared_original_pending','formal_freeze_ready','fake_current_contract_SHA','remove_environment_assumption']
for name in names:
 args=deepcopy(base);r,f,reg,probe,gap=args
 if name=='missing_group':r['groups'].pop()
 elif name=='duplicate_group':r['groups'][1]=deepcopy(r['groups'][0])
 elif name=='wrong_rho':r['groups'][0]['contract_values']['rho_n_s']=81
 elif name=='bool_as_numeric':r['unchanged_contract_values']['map_scale']=True
 elif name=='source_freshness_promoted':r['structured_non_claims']['source_packet_freshness_proven']=True
 elif name=='RTF_as_hard_bound':r['structured_non_claims']['RTF_average_is_instantaneous_hard_bound']=True
 elif name=='mixed_general_promoted':r['selected_domain']['qualified_general_mixed']=True
 elif name=='twenty_seconds_from_short_runs':r['selected_domain']['continuous_20s_trace_claimed']=True
 elif name=='full_gap_qualified':r['structured_non_claims']['full_command_stream_gap240ms_qualified']=True
 elif name=='Observer_physical_outlet_promoted':r['selected_domain']['current_Observer_physical_publishers']=2
 elif name=='metadata_mapping_missing':r['metadata_bindings'][0]['source_refs'].pop()
 elif name=='wrong_source_line':f['snippets']['source_age_comparison']['lines'][0]['sha256']='0'*64
 elif name=='erased_M4_bootstrap':r['M4_forward_obligations']=[x for x in r['M4_forward_obligations'] if x['id']!='M4-bootstrap-gap']
 elif name=='M4_partial_qualified':next(x for x in r['M4_forward_obligations'] if x['id']=='M4-partial-API')['current_qualified']=True
 elif name=='cleared_original_pending':r['old_pending_array_preserved']=[]
 elif name=='formal_freeze_ready':r['B5_current_assets_formal_freeze_ready']=True
 elif name=='fake_current_contract_SHA':r['contract_sha256']='0'*64
 else:r['assumptions'].pop()
 try:check(*args)
 except ValueError as e:cases.append(dict(case=name,rejected=True,reason=str(e)))
 else:cases.append(dict(case=name,rejected=False))
after={p:pin(p) for p in before};assert before==after
result=dict(passed=all(x['rejected'] for x in cases),positive_actual_artifact_check=positive,cases=cases,negative_count=len(cases),
 input_sha256_before=before,input_sha256_after=after,raw_or_runtime_changed=False,new_ROS_runs=0,new_CXX_builds=0,
 policy_artifact_rejection_is_not_runtime_branch_testing=True,stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'verification/review_artifact_checks_v1.json').open('x') as h:json.dump(result,h,ensure_ascii=False,indent=2)
print(json.dumps(dict(passed=result['passed'],groups=8,metadata_bindings=5,negative_cases=len(cases),rejected=sum(x['rejected'] for x in cases),new_ROS_runs=0)))
assert result['passed']
