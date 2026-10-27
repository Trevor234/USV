"""Mutate copies of actual closed evidence; original raw files remain read-only."""
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
from activation_interleave_audit_v1 import check
D=Path(__file__).resolve().parent;R=D/'author/runs/v3_odom_01'
def read(p):return json.loads(Path(p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
rawpath=R/'observer/source.jsonl';before={str(p):pin(p) for p in [rawpath,R/'synthetic_source/owned_manifest.json',D/'author/pair_wakeup_contract_v1.json',D/'activation_interleave_audit_v1.py']}
source=[json.loads(line) for line in rawpath.read_bytes().splitlines()]
fixture=read(R/'synthetic_source/owned_manifest.json');contract=read(D/'author/pair_wakeup_contract_v1.json')
positive=check(source,fixture,contract)
def target(rows):
    for d in rows:
        if d.get('type')!='decision':continue
        t=d['d0_observation']['activation_alignment']
        for a in t['attempts']:
            if 'diagnostic_interleave' in a:return d,t,a,a['diagnostic_interleave']
    raise ValueError('missing actual target')
def callback(rows):return next(r for r in rows if r.get('type')=='odom_admission' and r['accepted_sequence']==positive['callback_sequence'])
def mutate(rows,name):
    d,t,a,w=target(rows)
    if name=='unchanged_observed_sequence':w['observed_after']=w['captured_odom_sequence']
    elif name=='false_input_guard':a['input_change_gate_unchanged']=True
    elif name=='third_attempt':t['attempts'].append(copy.deepcopy(t['attempts'][-1]))
    elif name=='capacity33':a['frame_count']=33
    elif name=='wrong_owned_GID':callback(rows)['raw_input']['publisher_gid'][0]^=1
    elif name=='input_commit_before_snapshot':callback(rows)['diagnostic_v3_commit_ns']=a['sample_ns']-1
    elif name=='wait_budget_changed':w['wait_budget_ns']-=1
    elif name=='false_prior_healthy_activation':
        for r in rows:
            if r.get('type')=='decision' and r['activation_commit_ns']<a['sample_ns']:r['accepted']=False
    else:raise ValueError('unselected mutation')
names=read(D/'preflight/v3_preregistration_v1.json')['selected_checker_negative_cases'];results=[]
for name in names:
    changed=copy.deepcopy(source);mutate(changed,name);reason=None
    try:check(changed,fixture,contract)
    except ValueError as e:reason=str(e)
    results.append(dict(case=name,rejected=reason is not None,reason=reason))
after={p:pin(p) for p in before}
report=dict(passed=all(r['rejected'] for r in results) and before==after,positive_actual=positive,
    cases=results,actual_raw_unchanged=before==after,input_sha256_before=before,input_sha256_after=after,
    mutated_copies_only=True,stage_qualified=False,execute_qualified=False,research_conclusion=False)
with (D/'postrun/v3_checker_negative_actual_v1.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(dict(passed=report['passed'],negative_cases=len(results),rejected=sum(r['rejected'] for r in results))))
raise SystemExit(0 if report['passed'] else 2)
