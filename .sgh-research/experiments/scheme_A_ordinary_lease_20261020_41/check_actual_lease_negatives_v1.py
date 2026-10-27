"""Current actual raw copy rejection tests; no historical or run files are edited."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
from audit_ordinary_core_v1 import check as check_stop
from audit_lease_gate_core_v1 import check as check_gate
D=Path(__file__).resolve().parent;R=D/'author/runs/ordinary_lease_01'
def load(p):return json.loads(Path(p).read_bytes())
def rows(p):return [json.loads(x) for x in Path(p).read_bytes().splitlines()]
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
    audit=load(D/'postrun/ordinary_lease_actual_audit_v1.json');assert audit['passed'];pins=audit['input_sha256_after']
    for p,f in pins.items():assert pin(p)==f
    source,worker=rows(R/'observer/source.jsonl'),rows(R/'worker/source.jsonl');witness=load(R/'observer/witness.json');report=load(R/'ordinary_supervision.json');ledger=rows(R/'owned_process_ledger.jsonl')
    manifests={k:load(R/k/'owned_manifest.json') for k in ['observer','worker','publisher','synthetic_source','recorder']};result=load(R/'result.json');contract=load(D/'author/pair_wakeup_contract_v1.json');prep=load(R/'preparation_evidence.json')
    base=[source,worker,witness,report,ledger,manifests,result,contract,0,prep]
    gate=[source,worker,witness,report,ledger,manifests,result,contract,load(R/'lease_stimulus.json'),load(R/'lease_resume_after_stop.json'),
        {a:dict(value=load(R/('c38_'+a+'_request.json')),sha256=pin(R/('c38_'+a+'_request.json'))['sha256']) for a in ['pause','resume']},load(R/'V2_prefix_observation.json'),prep]
    assert check_stop(*base)['passed'] and check_gate(*gate)['passed'];cases=[]
    names=['unknown_cause','duplicate_dispatch','foreign_signal_group','injected_SIGSTOP','notification_budget_exceeded','inconsistent_wait_budget','Worker_summary_missing','new_submit_after_terminal','accepted_after_terminal','Source_inode_mismatch']
    for name in names:
        args=deepcopy(base);source,worker,witness,report,ledger,manifests,result,contract,trailing,prepared=args
        terminal=next(r for r in source if r.get('type')=='worker_unusable_transition');cue=next(r for r in ledger if r['type']=='ordinary_notice_authenticated')
        if name=='unknown_cause':terminal['reason']='unexpected:worker_capability_expired'
        elif name=='duplicate_dispatch':ledger.append(deepcopy(next(r for r in ledger if r['type']=='ordinary_worker_stop_dispatched')))
        elif name=='foreign_signal_group':
            next(r for r in ledger if r['type']=='signal_call_result' and r['name']=='worker')['target_pgid']+=1;report['signal_calls'][0]['target_pgid']+=1
        elif name=='injected_SIGSTOP':
            next(r for r in ledger if r['type']=='signal_call_result' and r['name']=='worker')['signal']=19;report['signal_calls'][0]['signal']=19
        elif name=='notification_budget_exceeded':cue['authenticated_ns']=terminal['check_ns']+250000001;report['cue']['authenticated_ns']=cue['authenticated_ns']
        elif name=='inconsistent_wait_budget':report['declared_waits_ns']['worker_grace_ns']+=1
        elif name=='Worker_summary_missing':worker[:]=[r for r in worker if r.get('type')!='worker_summary']
        elif name=='new_submit_after_terminal':
            row=deepcopy(witness['submit'][-1]);row['commit_ns']=terminal['check_ns']+1;witness['submit'].append(row)
        elif name=='accepted_after_terminal':
            row=deepcopy(witness['activation'][-1]);row['commit_ns']=terminal['check_ns']+1;row['accepted']=True;witness['activation'].append(row)
        else:cue['Source_fd_identity']['inode']+=1;report['cue']['Source_fd_identity']['inode']+=1
        try:check_stop(*args)
        except ValueError as e:cases.append(dict(case=name,rejected=True,reason=str(e)))
        else:cases.append(dict(case=name,rejected=False))
    for name in ['monitor_after_terminal','resume_before_owned_cleanup','post_exit_semantic_callback','lease_not_expired']:
        args=deepcopy(gate);source,worker,witness,report,ledger,manifests,result,contract,stimulus,resumed,commands,prefix,prepared=args
        terminal=next(r for r in source if r.get('type')=='worker_unusable_transition')
        if name=='monitor_after_terminal':next(r for r in ledger if r['type']=='ordinary_lease_monitor_entered')['monotonic_ns']=terminal['check_ns']+1
        elif name=='resume_before_owned_cleanup':commands['resume']['value']['issued_ns']=next(r for r in ledger if r['type']=='cleanup_result' and r['name']=='worker')['cleanup_started_ns']
        elif name=='post_exit_semantic_callback':next(r for r in source if r.get('type')=='adapter_worker_callback' and r['entry_ns']>=resumed['resume']['ack']['gate']['resumed_ns'])['semantic_callback_invoked']=True
        else:terminal['capability_last_valid_commit_ns']=terminal['check_ns']-600000000
        try:check_gate(*args)
        except ValueError as e:cases.append(dict(case=name,rejected=True,reason=str(e)))
        else:cases.append(dict(case=name,rejected=False))
    assert len(cases)==14
    for p,f in pins.items():assert pin(p)==f
    r=dict(passed=all(c['rejected'] for c in cases),cases=cases,actual_raw_unchanged=True,input_count=len(pins),stage_qualified=False,execute_qualified=False,research_conclusion=False)
    with (D/'verification/actual_ordinary_lease_negatives_v1.json').open('x') as f:json.dump(r,f,indent=2)
    print(json.dumps(dict(passed=r['passed'],negative_count=len(cases),cases=cases)));assert r['passed']
if __name__=='__main__':main()
