"""Reject altered in-memory copies of this actual run; frozen raw never changes."""
import copy,hashlib,json
from pathlib import Path
from audit_fault_close_core_v1 import check as close
from audit_V1_strict_core_v1 import check as strict
from audit_business_start_v1 import check as start
D=Path(__file__).resolve().parent

def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def load(p):return json.loads(Path(p).read_bytes())
def main():
    audit=load(D/'postrun/current_V1_actual_audit_v1.json');assert audit['passed']
    pins=audit['input_sha256_after']
    for p,f in pins.items():assert pin(p)==f
    original=load(D/'evidence/final_V1_01_normalized_v1.json');root=Path(original['original_run_root'])
    def gate(b,cmd=None):
        return start(root,b['observer_source'],b['publisher_source'],b['witness'],cmd or load(root/'business_start_request.json'),load(root/'business_start_observation.json'),b['preparation'],b['inputs'],b['original_result'],b['manifests'])
    assert close(original)['passed'] and strict(original)['passed'] and gate(original)['passed']
    cases=[]
    def reject(name,edit,checker=close):
        b=copy.deepcopy(original);edit(b)
        try:checker(b)
        except Exception as e:cases.append(dict(name=name,rejected=True,error=repr(e)))
        else:cases.append(dict(name=name,rejected=False))
    reject('sink_depth_not_capacity',lambda b:b['fault']['sink'].__setitem__('depth_at_rejection',511))
    reject('not_first_actual_failure',lambda b:b['fault']['sink'].__setitem__('first_failure_at_this_decision',False))
    def later(b):
        at=next(p['ns'] for p in b['witness']['phase'] if p['event_code']==5 and p['observation_code']==3)
        row=copy.deepcopy(b['witness']['submit'][0]);row['commit_ns']=at+1;b['witness']['submit'].append(row)
    reject('new_submit_after_stopping',later)
    def invalid(b):
        next(r for r in b['witness']['phase'] if r['event_code']==8 and r['observation_code']==3)['admission_slots']=1
    reject('same_boundary_slots_not_cleared',invalid)
    reject('failed_Decision_Stored',lambda b:b['stored_decisions'].append(dict(sequence=b['fault']['decision_sequence'])))
    def nonzero(b):next(r for r in b['publisher_source'] if r.get('type')=='controlled_Applied_emitted' and r['control_source']=='shutdown_zero')['final_n']=[1.,0.]
    reject('shutdown_tail_not_zero',nonzero)
    def wrong_gid(b):
        for r in b['transport']:
            if r.get('topic')=='/research/control/applied':r['publisher_gid']='foreign'
    reject('Fixture_owner_GID_changed',wrong_gid)
    def cleanup_order(b):
        ids=[i for i,r in enumerate(b['ledger']) if r['type']=='cleanup_result'];i,j=ids[:2];b['ledger'][i],b['ledger'][j]=b['ledger'][j],b['ledger'][i]
    reject('actual_cleanup_order_reversed',cleanup_order)
    reject('accepted_prefix_missing',lambda b:b.__setitem__('stored_decisions',[r for r in b['stored_decisions'] if not r['candidate_accepted']]))
    def bad_auth(b):next(r for r in b['observer_source'] if r.get('type')=='controlled_phase_callback' and r.get('accepted') and r.get('phase',{}).get('decision_sequence')==next(x['decision_sequence'] for x in b['observer_source'] if x.get('type')=='diagnostic_v1_armed_after_ack'))['authentication_reason']='foreign'
    reject('authenticated_phase_reason_changed',bad_auth,strict)
    def bad_wire(b):
        ar=next(r for r in b['observer_source'] if r.get('type')=='diagnostic_v1_armed_after_ack')
        p=next(r for r in b['stored_phase'] if r['decoded']['decision_sequence']==ar['decision_sequence'] and r['decoded']['applied_sequence']==ar['applied_sequence'])
        p['wire_hex']='ff'+p['wire_hex'][2:]
    reject('Stored_phase_raw_bytes_changed',bad_wire,strict)
    def late(b):
        arm=next(r['ns'] for r in b['witness']['phase'] if r['event_code']==1)
        seq=next(r['applied_sequence'] for r in b['observer_source'] if r.get('type')=='diagnostic_v1_armed_after_ack')
        next(r for r in b['publisher_source'] if r.get('type')=='controlled_Applied_emitted' and r['applied_sequence']==seq)['applied_publish_end_ns']=arm+1
    reject('actual_Applied_after_arm',late,strict)
    def prestart(b):
        src=b['observer_source'];i=next(i for i,r in enumerate(src) if r.get('type')=='business_start_authorized');src.insert(i,copy.deepcopy(next(r for r in src if r.get('type')=='decision')))
    reject('business_Decision_before_gate',prestart,gate)
    def wrong_anchor(b):
        cmd=load(root/'business_start_request.json');cmd['initial_applied_sequence']+=1;return gate(b,cmd)
    reject('gate_initial_anchor_changed',lambda b:None,wrong_anchor)
    assert len(cases)==14
    for p,f in pins.items():assert pin(p)==f
    r=dict(passed=all(r['rejected'] for r in cases),cases=cases,actual_raw_unchanged=True,input_count=len(pins),normal_qualification=False,stage_qualified=False,research_conclusion=False)
    with (D/'verification/actual_V1_negatives_v1.json').open('x') as f:json.dump(r,f,indent=2)
    print(json.dumps(dict(passed=r['passed'],cases=cases)));assert r['passed']
if __name__=='__main__':main()
