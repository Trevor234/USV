"""Reject false gate evidence using copies of this actual run; no raw mutation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(D))
from audit_business_start_v1 import check
R=D/'author/runs/business_active_01'
def load(p):return json.loads(Path(p).read_bytes())
def rows(p):return [json.loads(v) for v in Path(p).read_bytes().splitlines()]
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
paths=[R/'observer/source.jsonl',R/'publisher/controlled_source.jsonl',R/'observer/witness.json',R/'business_start_request.json',
       R/'business_start_observation.json',R/'preparation_evidence.json',R/'inputs.json',R/'result.json']
before={str(p):pin(p) for p in paths}
base=[R,rows(paths[0]),rows(paths[1]),load(paths[2]),load(paths[3]),load(paths[4]),load(paths[5]),load(paths[6]),load(paths[7]),
      {name:load(R/name/'owned_manifest.json') for name in ['observer','publisher','worker','synthetic_source','recorder']}]
positive=check(*base);results=[]
for name in load(D/'preflight/business_preregistration_v1.json')['business_gate_negative_cases']:
    args=deepcopy(base);root,source,pub,witness,command,proof,prepared,inputs,result,manifests=args
    grant=next(r for r in source if r.get('type')=='business_start_authorized')
    if name=='pre_gate_decision':source.insert(0,deepcopy(next(r for r in source if r.get('type')=='decision')))
    elif name=='driver_start_mismatch':command['driver_start_ticks']+=1
    elif name=='early_first_tick':next(r for r in source if r.get('type')=='decision')['planned_ns']=grant['authorized_ns']+1
    elif name=='stale_gate_request':command['issued_ns']=grant['authorized_ns']-2_000_000_001
    elif name=='wrong_initial_anchor':grant['actual_anchor_n'][1]=.1
    elif name=='first_phase_late':
        first=next(r for r in pub if r.get('type')=='controlled_phase_emitted');first['phase_publish_end_ns']=first['phase']['planned_ns']+150000001
    else:raise AssertionError('unselected case')
    error=None
    try:check(*args)
    except ValueError as e:error=str(e)
    results.append(dict(case=name,rejected=error is not None,reason=error))
after={p:pin(p) for p in before}
report=dict(passed=all(r['rejected'] for r in results) and before==after,positive_actual=positive,cases=results,
    actual_raw_unchanged=before==after,input_sha256_before=before,input_sha256_after=after,
    stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'verification/actual_business_gate_negatives_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True)
print(json.dumps(dict(passed=report['passed'],cases=len(results),rejected=sum(r['rejected'] for r in results))))
raise SystemExit(0 if report['passed'] else 2)
