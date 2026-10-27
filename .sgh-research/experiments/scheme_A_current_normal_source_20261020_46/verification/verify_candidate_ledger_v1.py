#!/usr/bin/env python3
"""Reject unsupported promotion or evidence drift in the new freeze candidate."""
import copy,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent.parent
def read(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def check(x):
    assert x['status']=='candidate_evidence_assembled_not_frozen'
    assert all(x[k] is False for k in ['physical_execute_release_enabled','B5_formal_freeze_qualified','M0b_qualified','M4_qualified','P1_qualified','stage_qualified','research_conclusion'])
    for p,row in x['input_sha256'].items():assert pin(p)==row
    audit=read(D/'postrun/current_normal_source20s_audit_v1.json');assert audit['passed']
    assert x['current_normal_source']==audit['sections']['continuous_current_nominal_source20s']['details']
    b4=read(x['source_review43_ref']);assert x['original_pending8']==b4['old_pending_array_preserved'] and len(x['original_pending8'])==8
    assert x['M0b_does_not_require_a_new_full_no_output_business_run'] is True
    assert not x['unrestricted_1_2_or_plant_or_turning_or_mixed_domain_claimed']
    assert {r['id'] for r in x['specific_freeze_actions_remaining']}=={'formal_execute_profile_policy','immutable_freeze_commit'}
    supplemental=read(D/'postrun/observed_domain_timing_supplement_v1.json');assert x['full_API_stream_observations']==supplemental['API_gap_population']
    return True
def main():
    x=read(D/'implementation/B5_candidate_evidence_ledger_v1.json');check(x);negative=[]
    def deny(name,edit):
        v=copy.deepcopy(x);edit(v)
        try:check(v);rejected=False
        except (AssertionError,ValueError,KeyError):rejected=True
        negative.append({'name':name,'rejected':rejected})
    deny('fake_frozen_status',lambda v:v.__setitem__('status','execution_frozen'))
    deny('execute_release_flag',lambda v:v.__setitem__('physical_execute_release_enabled',True))
    deny('P1_flag',lambda v:v.__setitem__('P1_qualified',True))
    deny('short_span_label',lambda v:v['current_normal_source'].__setitem__('source_span_ns',19_000_000_000))
    deny('missing_pending8',lambda v:v.__setitem__('original_pending8',[]))
    deny('new_no_output_stage',lambda v:v.__setitem__('M0b_does_not_require_a_new_full_no_output_business_run',False))
    deny('general_plant_domain',lambda v:v.__setitem__('unrestricted_1_2_or_plant_or_turning_or_mixed_domain_claimed',True))
    deny('bootstrap_gap_hidden',lambda v:v['full_API_stream_observations']['left'].__setitem__('full_stream_gap240ms_passed',True))
    assert all(r['rejected'] for r in negative)
    report={'schema':'B5-candidate-evidence-ledger-check-v1','passed':True,'altered_copy_cases':negative,'candidate_only':True,'stage_qualified':False}
    with (D/'verification/B5_candidate_ledger_checks_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'passed':True,'altered_copy_rejections':len(negative)}))
if __name__=='__main__':main()
