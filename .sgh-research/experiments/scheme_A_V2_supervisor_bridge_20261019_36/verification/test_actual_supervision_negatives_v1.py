from copy import deepcopy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(D/'implementation'))
from audit_bridge_core_v1 import check
R=D/'author/runs/v2_supervision_01'
def load(p):return json.loads(p.read_bytes())
def rows(p):return [json.loads(x) for x in p.read_bytes().splitlines() if x.endswith(b'}')]
source=rows(R/'observer/source.jsonl');worker=rows(R/'worker/source.jsonl');witness=load(R/'observer/witness.json')
report=load(R/'supervision_bridge.json');ledger=rows(R/'owned_process_ledger.jsonl')
manifests={r:load(R/r/'owned_manifest.json') for r in ['observer','worker','publisher','synthetic_source','recorder']}
result=load(R/'result.json');contract=load(D/'author/pair_wakeup_contract_v1.json');prepared=load(R/'preparation_evidence.json')
assert check(source,worker,witness,report,ledger,manifests,result,contract,0,prepared)['passed']
tested=[]
for case in ['foreign_signal_group','missing_TERM','shortened_kill_postcheck','signal_before_authentication',
             'false_normal_Worker_Source','new_submit_after_terminal','new_activation_after_terminal','false_clean_forced_exit']:
 s,w,wi,le=deepcopy(source),deepcopy(worker),deepcopy(witness),deepcopy(ledger)
 if case=='foreign_signal_group':next(r for r in le if r['type']=='signal_call_result' and r['name']=='worker')['target_pgid']=1
 elif case=='missing_TERM':le=[r for r in le if not(r['type']=='signal_call_result' and r['name']=='worker' and r['signal']==15)]
 elif case=='shortened_kill_postcheck':next(r for r in le if r['type']=='wait_result' and r['name']=='worker' and r['stage']=='kill_postcheck')['budget_ns']=500000000
 elif case=='signal_before_authentication':next(r for r in le if r['type']=='signal_call_result' and r['name']=='worker' and r['signal']==2)['call_start_ns']=1
 elif case=='false_normal_Worker_Source':w.append({'type':'worker_summary','normal_source_complete':True})
 elif case=='new_submit_after_terminal':
  entry=deepcopy(wi['submit'][-1]);entry['commit_ns']=report['cue']['notice']['terminal']['check_ns']+1;wi['submit'].append(entry)
 elif case=='new_activation_after_terminal':
  entry=deepcopy(wi['activation'][-1]);entry['commit_ns']=report['cue']['notice']['terminal']['check_ns']+1;entry['accepted']=True;wi['activation'].append(entry)
 else:next(r for r in le if r['type']=='cleanup_result' and r['name']=='worker')['qualification_clean']=True
 try:check(s,w,wi,report,le,manifests,result,contract,0,prepared)
 except ValueError as error:tested.append({'case':case,'rejected':True,'reason':str(error)})
 else:raise AssertionError('accepted modified supervision evidence:'+case)
with (D/'verification/actual_supervision_negatives_v1.json').open('x') as f:json.dump({'passed':True,'rejected':len(tested),'cases':tested,'raw_files_modified':False,'new_actual_runs':0},f,indent=2)
print(json.dumps({'passed':True,'rejected':len(tested)}))
