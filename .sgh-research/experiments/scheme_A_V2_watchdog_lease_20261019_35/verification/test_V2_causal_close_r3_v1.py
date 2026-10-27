"""Offline new-profile checks against frozen failed-r2 facts. No live receiver proof."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(D/'implementation'),str(D/'author_r3')]
from audit_v2_core_v2 import terminal_source_cause
from v2_observe_v1 import actual_cause
from worker_terminal_close_v1 import capture
R=D/'author/runs/v2_lease_r2_02'
def rows(path):return [json.loads(x) for x in Path(path).read_bytes().splitlines()]
source=rows(R/'observer/source.jsonl')
terminal=next(r for r in source if r['type']=='worker_unusable_transition')
assert terminal_source_cause(terminal,source)==actual_cause(terminal,source)=='worker_capability_expired'
assert terminal['reason']=='legacy_ready_invalidated:worker_unusable:worker_capability_expired'
cases=[{'case':'actual_composite_reason_and_matching_Source_link','passed':True}]
for name,mutation in [
 ('missing_link',lambda s:[r for r in s if r.get('type')!='legacy_ready_invalidated']),
 ('duplicate_link',lambda s:s+[deepcopy(next(r for r in s if r.get('type')=='legacy_ready_invalidated'))]),
 ('wrong_link_time',lambda s:[{**r,'check_ns':1} if r.get('type')=='legacy_ready_invalidated' else r for r in s]),
 ('wrong_cause',lambda s:[{**r,'reason':'worker_unusable:active_watchdog'} if r.get('type')=='legacy_ready_invalidated' else r for r in s]),
]:
 for check in [terminal_source_cause,actual_cause]:
  try:check(terminal,mutation(deepcopy(source)))
  except ValueError:pass
  else:raise AssertionError('causal mismatch admitted:'+name)
 cases.append({'case':name,'passed':True,'both_independent_interpreters_rejected':True})
roles={r:{'manifest':json.loads((R/r/'owned_manifest.json').read_bytes())} for r in ['publisher','observer']}
def component(which):
 source_copy=deepcopy(source);transport=rows(R/'synthetic_source/transport_source.jsonl')
 if which=='foreign_callback_gid':
  next(r for r in source_copy if r.get('type')=='adapter_applied_callback')['raw_input']['publisher_gid'][0]^=1
 if which=='corrupt_CDR_hash':
  next(r for r in source_copy if r.get('type')=='adapter_applied_callback')['raw_input']['cdr_sha256']='0'*64
 if which=='missing_tail':
  source_copy=[r for r in source_copy if not(r.get('type')=='adapter_applied_callback' and r['sequence']==11)]
 if which=='foreign_transport_gid':
  next(r for r in transport if r['topic']=='/wamv/thrusters/left/thrust')['publisher_gid'][0]^=1
 written=[]
 def read(p):
  return source_copy if str(p).endswith('observer/source.jsonl') else transport
 now=time.monotonic_ns()
 try:
  result=capture(R,roles,rows=read,spin=lambda _:None,bound=lambda:None,close_start_ns=now,
                 deadline_ns=now+30_000_000,create_only_json=lambda p,v:written.append(v))
 except (ValueError,RuntimeError):
  assert which!='positive'
  return {'case':which,'passed':True,'rejected':True,'offline_test_double':True}
 assert which=='positive' and len(written)==1 and result['authenticated_receiver_count']==11
 assert result['business_anchor_count']==6 and result['business_anchor_chain_complete'] is False
 assert result['normal_close_qualified'] is False
 return {'case':which,'passed':True,'offline_test_double':True,'actual_receiver_liveness_proven':False,
         'authenticated_receiver_count':11,'business_anchor_count':6,'normal_close_qualified':False}
for case in ['positive','foreign_callback_gid','corrupt_CDR_hash','missing_tail','foreign_transport_gid']:
 cases.append(component(case))
parent=(D/'author/prepare_pair_wakeup_v1.py').read_text();new=(D/'author_r3/prepare_pair_wakeup_v1.py').read_text()
start="  elif released and a.close_order=='publisher-first' and 'observer' in owned:\n"
end="  for name in ['foreign','publisher','observer','worker','synthetic_source','recorder']:stop(name)\n"
assert parent[parent.index(start):parent.index(end)]==new[new.index(start):new.index(end)]
with (D/'verification/V2_causal_close_r3_v1.json').open('x') as f:json.dump({'passed':True,'cases':cases,'old_normal_close_body_unchanged':True,'actual_new_runs':0},f,indent=2)
print(json.dumps({'passed':True,'cases':len(cases),'old_normal_close_body_unchanged':True}))
