"""Reject only in-memory alterations of the new closed run; preserve every actual byte."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
from audit_fresh_core_v1 import identity,healthy,normal_tail
D=Path(__file__).resolve().parent;R=D/'author/runs/fresh_after_lease_01'
def load(p):return json.loads(Path(p).read_bytes())
def rows(p):return [json.loads(x) for x in Path(p).read_bytes().splitlines()]
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
    audit=load(D/'postrun/fresh_recovery_actual_audit_v1.json');assert audit['passed'];pins=audit['input_sha256_after']
    for p,f in pins.items():assert pin(p)==f
    b=dict(previous=load(D/'author/previous_lease_close_proof_v1.json'),source=rows(R/'observer/source.jsonl'),worker=rows(R/'worker/source.jsonl'),
        publisher=rows(R/'publisher/controlled_source.jsonl'),witness=load(R/'observer/witness.json'),ledger=rows(R/'owned_process_ledger.jsonl'),
        manifests={k:load(R/k/'owned_manifest.json') for k in ['observer','worker','publisher','synthetic_source','recorder']},
        prepared=load(R/'preparation_evidence.json'),result=load(R/'result.json'),inputs=load(R/'inputs.json'),
        identity=load(R/'recovery_identity_before_business.json'),healthy=load(R/'recovery_healthy_observation.json'),
        close_ack=load(R/'adapter_driver_close_ack.json'),tail=load(R/'close_tail_ack.json'),
        close_command=load(R/'adapter_driver_close_request.json'),close_command_sha256=pin(R/'adapter_driver_close_request.json')['sha256'],
        publisher_session=load(R/'publisher/session_summary.json'),publisher_session_sha256=pin(R/'publisher/session_summary.json')['sha256'])
    assert identity(b)['passed'] and healthy(b)['passed'] and normal_tail(b)['passed'];cases=[]
    def reject(name,change,check):
        bad=deepcopy(b);change(bad)
        try:check(bad)
        except (ValueError,KeyError) as e:cases.append(dict(case=name,rejected=True,reason=str(e)))
        else:cases.append(dict(case=name,rejected=False))
    reject('old_Worker_instance',lambda b:b['manifests']['worker'].__setitem__('worker_instance',b['previous']['old_role_manifests']['worker']['worker_instance']),identity)
    reject('old_Worker_run',lambda b:b['manifests']['worker'].__setitem__('run_id',b['previous']['run_id']),identity)
    def old_pid(b):
        m=b['manifests']['observer'];old=b['previous']['old_role_manifests']['observer'];m['pid']=old['pid'];m['process_start_ticks']=old['process_start_ticks']
    reject('old_Observer_PID_start',old_pid,identity)
    reject('old_group_not_closed',lambda b:b['previous']['old_cleanup']['worker'].__setitem__('remaining_members',[dict(pid=1)]),identity)
    reject('new_prepare_before_old_close',lambda b:b['result'].__setitem__('prepare_start_ns',b['previous']['old_all_groups_cleanup_observed_ns']),identity)
    reject('duplicate_job_as_two_cycles',lambda b:b['healthy']['pairs'][-1].__setitem__('job_id',b['healthy']['pairs'][0]['job_id']),healthy)
    def late(b):
        jid=b['healthy']['pairs'][0]['job_id'];deadline=next(r['job']['deadline_ns'] for r in b['source'] if r.get('type')=='job' and r['job']['job_id']==jid)
        next(r for r in b['source'] if r.get('type')=='decision' and r.get('accepted') and r['job_id']==jid)['ready_commit_ns']=deadline+1
    reject('ready_after_absolute_deadline',late,healthy)
    def missing_applied(b):
        seq=b['healthy']['pairs'][0]['Applied_sequence'];b['publisher'][:]=[r for r in b['publisher'] if not(r.get('type')=='controlled_Applied_emitted' and r['applied_sequence']==seq)]
    reject('missing_actual_healthy_Applied',missing_applied,healthy)
    reject('Worker_unusable_during_recovery',lambda b:b['source'].append(dict(type='worker_unusable_transition')),healthy)
    def missing_anchor(b):
        i=next(i for i in range(len(b['source'])-1,-1,-1) if b['source'][i].get('type')=='legacy_anchor');b['source'].pop(i)
    reject('normal_tail_anchor_missing',missing_anchor,normal_tail)
    def nonzero(b):next(r for r in b['publisher'] if r.get('type')=='controlled_Applied_emitted' and r['control_source']=='shutdown_zero')['final_n']=[1.,0.]
    reject('normal_tail_not_zero',nonzero,normal_tail)
    def later_submit(b):
        j=deepcopy(next(r for r in b['source'] if r.get('type')=='job'));j['submit_commit_ns']=b['close_ack']['observer']['observed_ns']+1;b['source'].append(j)
    reject('submit_after_normal_close_ACK',later_submit,normal_tail)
    def later_accepted(b):
        r=deepcopy(next(r for r in b['source'] if r.get('type')=='decision' and r.get('accepted')));r['activation_commit_ns']=b['close_ack']['observer']['observed_ns']+1;b['source'].append(r)
    reject('accepted_after_normal_close_ACK',later_accepted,normal_tail)
    reject('normal_close_ACK_wrong_request',lambda b:b['close_ack'].__setitem__('request_sha256','0'*64),normal_tail)
    assert len(cases)==14
    for p,f in pins.items():assert pin(p)==f
    report=dict(passed=all(r['rejected'] for r in cases),cases=cases,actual_raw_unchanged=True,input_count=len(pins),stage_qualified=False,execute_qualified=False,research_conclusion=False)
    with (D/'verification/actual_fresh_negatives_v1.json').open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(passed=report['passed'],cases=cases)));assert report['passed']
if __name__=='__main__':main()
