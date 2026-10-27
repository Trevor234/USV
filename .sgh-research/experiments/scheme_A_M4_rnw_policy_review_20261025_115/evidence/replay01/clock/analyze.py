#!/usr/bin/env python3
"""Read-only forensic measurement. No ROS initialization or writes to historical assets."""
import json, pathlib, hashlib, struct, collections
BASE=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_rnw2_impl_20261025_112')
OUT=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_policy_review_20261025_115/evidence/replay01/clock')
def load(p):
 rows=[]
 for n,t in enumerate(p.read_text().splitlines(),1):
  if t.strip():rows.append((n,json.loads(t)))
 return rows

def brief(n,x):
 return dict(line=n,**{k:v for k,v in x.items() if k not in ('raw_input','d0_observation','activation_trace')})
result={'schema':'review114-clock-evidence-v1','historical_inputs':[], 'runs':{}}
for name in ['T2A_RNW2_attempt1','T2A_RNW2']:
 root=BASE/'implementation/runs'/name
 regpath=root/'regulator/source.jsonl';fxpath=root/'fixture/nominal_steps.jsonl'
 for p in [regpath,fxpath]:result['historical_inputs'].append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 reg=load(regpath);fx=load(fxpath)
 cl=[(n,x)for n,x in reg if x.get('type')=='clock']
 actions=[(n,x)for n,x in fx if x.get('type')=='t2_action_executed']
 hold=next((n,x)for n,x in actions if x['action']=='clock_hold')
 resume=next((n,x)for n,x in actions if x['action']=='clock_resume')
 pre=next((n,x)for n,x in reversed(cl) if x['receive_ns']<hold[1]['executed_ns'])
 post=next((n,x)for n,x in cl if x['receive_ns']>resume[1]['executed_ns'])
 decoded=[]
 for n,x in cl:
  b=bytes.fromhex(x['raw_input']['cdr_hex']); assert b[:4]==bytes.fromhex('00010000')
  sec,nsec=struct.unpack('<iI',b[4:12]);sim=sec*10**9+nsec
  assert sim==x['sim_ns'],(n,sim,x['sim_ns'])
  decoded.append(sim)
 pairs=[(n,x)for n,x in reg if x.get('type')=='owned_API_pair']
 regressions=[]
 for (pn,prev),(n,x) in zip(pairs,pairs[1:]):
  if x['sim_ns'][0]<prev['sim_ns'][1]:regressions.append({'previous_pair':brief(pn,prev),'pair':brief(n,x),'left_minus_prev_right_ns':x['sim_ns'][0]-prev['sim_ns'][1]})
 source_backsteps=[{'before':brief(pn,prev),'after':brief(n,x)}for (pn,prev),(n,x)in zip(cl,cl[1:])if x['sim_ns']<prev['sim_ns']]
 matches=[]
 for n,x in reg:
  if '102619942560' in json.dumps({k:v for k,v in x.items() if k!='raw_input'}):
   matches.append({'line':n,'type':x.get('type'),'stamp_ns':x.get('stamp_ns'),'sim_ns':x.get('sim_ns'),'receive_ns':x.get('receive_ns'),'relation_to_resume':'after' if x.get('receive_ns',0)>resume[1]['executed_ns'] else 'other'})
 result['runs'][name]={
  'run_id':next(x['run_id']for _,x in reg if 'run_id'in x),'clock_count':len(cl),'cdr_clock_stamp_verified':len(decoded),
  'source_clock_backsteps':source_backsteps,'clock_epochs':dict(collections.Counter(x['epoch']for _,x in cl)),
  'hold':brief(*hold),'resume':brief(*resume),'hold_actual_ns':resume[1]['executed_ns']-hold[1]['executed_ns'],
  'pre_hold_clock':brief(*pre),'first_resume_clock':brief(*post),'source_sim_delta_ns':post[1]['sim_ns']-pre[1]['sim_ns'],'source_receive_delta_ns':post[1]['receive_ns']-pre[1]['receive_ns'],
  'projection_regressions':regressions,'claimed_stamp_102619942560_matches':matches,
  'consistency_failures':[brief(n,x)for n,x in reg if x.get('type')=='owned_pair_consistency_failed'],
  'legacy_anchor_count':sum(x.get('type')=='legacy_anchor'for _,x in reg),'adapter_applied_callback_count':sum(x.get('type')=='adapter_applied_callback'for _,x in reg),
 }
result['findings']=[
 {'id':'C1','status':'refuted','claim':'attempt2 has received clock backward step of 31.91 ms','reason':'The two compared numbers are from different runs and different domains: attempt2 seq15 projected output left sim versus attempt1 second post-resume received clock stamp.'},
 {'id':'C2','status':'observed','claim':'attempt2 engineering output projection regressed','reason':'seq14 right to seq15 left regresses by 541809040 ns (left-to-left: 541761190 ns); received clocks remain increasing.'},
 {'id':'C3','status':'refuted','claim':'clock_epoch reset at L630 uniquely explains [false,true]','reason':'97 received clocks all epoch0 with no backward or >5s forward step. L844 synchronous push_history_locked reset, called after side0 apply and before side1 apply, explains signature without clock-thread interleave.'},
 {'id':'C4','status':'bounded','claim':'exact reset branch is directly observed','reason':'No dedicated held_history_time_regression reset row exists in this run. Source+code ordering strongly identifies the synchronous path under current code; report exact evidence and add branch instrumentation/source-linked deterministic test before promoting causal closure.'},
]
(OUT/'clock_evidence_v1.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:{q:v[q]for q in ['clock_count','source_clock_backsteps','clock_epochs','hold_actual_ns','source_sim_delta_ns','source_receive_delta_ns','claimed_stamp_102619942560_matches']}for k,v in result['runs'].items()},ensure_ascii=False,indent=2))
