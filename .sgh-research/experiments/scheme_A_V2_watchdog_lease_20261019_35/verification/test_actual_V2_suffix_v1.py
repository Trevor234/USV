from copy import deepcopy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(D/'implementation'))
from audit_v2_core_v2 import check
def load(p):return json.loads(p.read_bytes())
def rows(p):return [json.loads(x) for x in p.read_bytes().splitlines()]
tested=[]
for case,run in [('lease','v2_lease_r3_04'),('active','v2_active_r3_05')]:
 R=D/'author_r3/runs'/run
 source,worker,witness,obs=rows(R/'observer/source.jsonl'),rows(R/'worker/source.jsonl'),load(R/'observer/witness.json'),load(R/'V2_observation.json')
 assert check(case,source,worker,witness,obs)['V2_fault_local_gate_passed']
 t=next(r['check_ns'] for r in source if r['type']=='worker_unusable_transition')
 for name in ['new_submit_after_terminal','accepted_after_terminal','capability_revival','Witness_incomplete']:
  s,w=deepcopy(source),deepcopy(witness)
  if name=='new_submit_after_terminal':
   item=deepcopy(w['submit'][-1]);item['commit_ns']=t+1;w['submit'].append(item)
  elif name=='accepted_after_terminal':
   item=deepcopy(w['activation'][-1]);item['commit_ns']=t+1;item['accepted']=True;w['activation'].append(item)
  elif name=='capability_revival':
   next(r for r in s if r.get('type')=='capability_admission' and r['validation_commit_ns']>t)['renewed']=True
  else:w['incomplete']=True
  try:check(case,s,worker,w,obs)
  except ValueError as error:tested.append({'case':case,'mutation':name,'rejected':True,'reason':str(error)})
  else:raise AssertionError('terminal invariant violation admitted:'+case+':'+name)
with (D/'verification/actual_V2_suffix_negative_v1.json').open('x') as f:json.dump({'passed':True,'rejected':len(tested),'tests':tested,'raw_files_modified':False,'actual_new_runs':0},f,indent=2)
print(json.dumps({'passed':True,'rejected':len(tested)}))
