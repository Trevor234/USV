"""Change in-memory copies of closed actual evidence; never alter run data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(D))
from audit_ordinary_core_v1 import check
R=D/'author/runs/business_active_01'
def load(p):return json.loads(Path(p).read_bytes())
def rows(p):return [json.loads(x) for x in Path(p).read_bytes().splitlines()]
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
files=[R/'observer/source.jsonl',R/'worker/source.jsonl',R/'observer/witness.json',R/'ordinary_supervision.json',
       R/'owned_process_ledger.jsonl',R/'result.json',R/'preparation_evidence.json',D/'author/pair_wakeup_contract_v1.json']
before={str(p):pin(p) for p in files}
base=[rows(files[0]),rows(files[1]),load(files[2]),load(files[3]),rows(files[4]),
      {k:load(R/k/'owned_manifest.json') for k in ['observer','worker','publisher','synthetic_source','recorder']},
      load(files[5]),load(files[7]),0,load(files[6])]
positive=check(*base);results=[]
for name in load(D/'preflight/business_preregistration_v1.json')['checker_negative_cases']:
    args=deepcopy(base);source,worker,witness,report,ledger,manifests,result,contract,trailing,prepared=args
    terminal=next(r for r in source if r.get('type')=='worker_unusable_transition')
    cue=next(r for r in ledger if r['type']=='ordinary_notice_authenticated')
    if name=='unknown_cause':terminal['reason']='unexpected:active_watchdog'
    elif name=='duplicate_dispatch':ledger.append(deepcopy(next(r for r in ledger if r['type']=='ordinary_worker_stop_dispatched')))
    elif name=='foreign_signal_group':
        next(r for r in ledger if r['type']=='signal_call_result' and r['name']=='worker')['target_pgid']+=1
        report['signal_calls'][0]['target_pgid']+=1
    elif name=='injected_SIGSTOP':
        next(r for r in ledger if r['type']=='signal_call_result' and r['name']=='worker')['signal']=19
        report['signal_calls'][0]['signal']=19
    elif name=='notification_budget_exceeded':
        cue['authenticated_ns']=terminal['check_ns']+250_000_001;report['cue']['authenticated_ns']=cue['authenticated_ns']
    elif name=='inconsistent_wait_budget':report['declared_waits_ns']['worker_grace_ns']+=1
    elif name=='Worker_summary_missing':worker[:]=[r for r in worker if r.get('type')!='worker_summary']
    elif name=='new_submit_after_terminal':
        row=deepcopy(witness['submit'][-1]);row['commit_ns']=terminal['check_ns']+1;witness['submit'].append(row)
    elif name=='accepted_after_terminal':
        row=deepcopy(witness['activation'][-1]);row['commit_ns']=terminal['check_ns']+1;row['accepted']=True;witness['activation'].append(row)
    elif name=='Source_inode_mismatch':
        cue['Source_fd_identity']['inode']+=1;report['cue']['Source_fd_identity']['inode']+=1
    else:raise AssertionError('unselected mutation')
    reason=None
    try:check(*args)
    except ValueError as e:reason=str(e)
    results.append(dict(case=name,rejected=reason is not None,reason=reason))
after={p:pin(p) for p in before}
report=dict(passed=all(r['rejected'] for r in results) and before==after,positive_actual=positive,
    cases=results,negative_count=len(results),actual_raw_unchanged=before==after,
    input_sha256_before=before,input_sha256_after=after,stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'verification/actual_ordinary_negatives_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
print(json.dumps(dict(passed=report['passed'],negative_count=len(results),rejected=sum(r['rejected'] for r in results))))
raise SystemExit(0 if report['passed'] else 2)
