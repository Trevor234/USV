#!/usr/bin/env python3
"""Read-only causal audit of recorded runs; no guard changes or replay qualification."""
from pathlib import Path
import collections,hashlib,json,math,statistics,subprocess
D=Path(__file__).resolve().parent
E=D.parent/'p1_execution_architecture_20261005_01'
SELECTED=[('authored_D1_C3_6_adapter_20261013_v13','owned_C36_adapter_positive_01'),('authored_D1_C3_7_20261014_v14','owned_C37_positive_01'),('authored_D1_C3_7_20261014_v14','owned_C37_positive_02'),('authored_D1_C3_8_20261014_v15','owned_C38_normal_01'),('authored_D1_C3_9_20261014_v16','owned_C39_normal_01'),('authored_D1_C3_10_20261015_v17','owned_C310_normal_01'),('authored_D1_C3_10_20261015_v17','owned_C310_normal_02')]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs={}
def lines(p):
 raw=p.read_bytes();inputs[str(p)]=hashlib.sha256(raw).hexdigest();return [json.loads(s) for s in raw.splitlines()]
def js(p):inputs[str(p)]=sha(p);return json.loads(p.read_text())
def rate_check(first,anchor,now):
 return all(anchor['known'][i] and now>anchor['publish_ns'][i] and -25<=first[i]<=25 and abs(first[i]-anchor['n'][i])<=80*(now-anchor['publish_ns'][i])/1e9+1e-9 for i in range(2))
contract=js(E/'authored_v13_resource_20261007/p1_shadow_contract_v5.json');tol=contract['activation_tolerance'];out=[];example={}
for author,name in SELECTED:
 r=E/author/'runs'/name;ob=lines(r/'observer/source.jsonl');worker=lines(r/'worker/source.jsonl');result=js(r/'result.json');conf=js(r/'inputs.json')
 close=next(x for x in ob if x['type']=='adapter_driver_close_observed')['observed_ns'];ready=next(x for x in ob if x['type']=='legacy_ready')['readiness']['legacy_ready_ns']
 dec=[x for x in ob if x['type']=='decision'];window=[x for x in dec if ready<=x['activation_commit_ns']<close];attempt=[x for x in window if x.get('job_id')];jobs={x['job']['job_id']:x for x in ob if x['type']=='job'};reg=[x for x in ob if x['type']=='candidate_registration'];cand=[x for x in worker if x['type']=='candidate'];anchors=[x for x in ob if x['type']=='anchor_validation'];state_exceed=0;full_errors=[];rate_ok=0
 for d in attempt:
  q=d['d0_observation'];err=q.get('full_error');assert q.get('full_error_available') is True and len(err)==6 and all(type(x)in(int,float) and math.isfinite(x) for x in err)
  full_errors.append(err);state_exceed+=any(abs(x)>t for x,t in zip(err,tol));rate_ok+=rate_check(q['candidate_capture']['first_control'],q['validation_snapshot']['anchor'],d['activation_commit_ns'])
 row={'author':author,'run_id':name,'run':str(r),'observer_sha256':inputs[str(r/'observer/source.jsonl')],'jobs':len(jobs),'candidates':len(cand),'solver_success':sum(c.get('success') is True for c in cand),'registered':len(reg),'registration_success':sum(c.get('accepted_registration') is True for c in reg),'ready_to_close_decisions':len(window),'ready_to_close_reasons':dict(collections.Counter(x['reason'] for x in window)),'activation_attempts':len(attempt),'activation_reasons':dict(collections.Counter(x['reason'] for x in attempt)),'activation_accepted':sum(x['accepted'] is True for x in attempt),'all_decision_reasons':dict(collections.Counter(x['reason'] for x in dec)),'latent_state_error_exceeded':state_exceed,'latent_state_error_is_not_reported_rejection':True,'command_check_independent_passed':rate_ok,'command_check_is_not_full_counterfactual_replay':True,'backend_ms_range':[min(c['backend_ms'] for c in cand),max(c['backend_ms'] for c in cand)],'freeze_to_activation_ms_range':[min((d['activation_commit_ns']-jobs[d['job_id']]['job']['freeze_ns'])/1e6 for d in attempt),max((d['activation_commit_ns']-jobs[d['job_id']]['job']['freeze_ns'])/1e6 for d in attempt)],'driver_passed':result['passed'],'fixture_source_role':conf['source_bundles']['fixture']}
 out.append(row)
 if name=='owned_C310_normal_02':
  first=attempt[0];job=jobs[first['job_id']]['job'];a=next(x for x in anchors if x['job_id']==first['job_id']);rr=next(x for x in reg if x['job']['job_id']==first['job_id']);origin=job['tick_origin_ns'];changes=[max(abs(x['actual_n'][i]-x['expected_n'][i]) for i in range(2)) for x in anchors]
  pubs=[x for x in ob if x['type']=='legacy_anchor'];pub_times=[x['applied']['left_publish_start_steady_ns'] for x in pubs if x['applied']['control_source']!='shutdown_zero'];intervals=[(b-a)/1e6 for a,b in zip(pub_times,pub_times[1:])]
  sample_names=['job','candidate_registration','anchor_validation','decision','adapter_driver_close_observed'];refs={}
  for n,event in enumerate(ob,1):
   if event['type'] in sample_names and (event.get('job_id')==1 or event.get('job',{}).get('job_id')==1 or event['type']=='adapter_driver_close_observed'):refs[event['type']]=n
  example={'run':str(r),'job_id':first['job_id'],'tick_origin_ns':origin,'freeze_after_origin_ms':(job['freeze_ns']-origin)/1e6,'ready_after_origin_ms':(rr['ready_commit_ns']-origin)/1e6,'legacy_update_after_origin_ms':(min(a['actual_publish_ns'])-origin)/1e6,'activation_after_origin_ms':(first['activation_commit_ns']-origin)/1e6,'deadline_after_origin_ms':(job['deadline_ns']-origin)/1e6,'frozen_anchor_n':a['expected_n'],'activation_anchor_n':a['actual_n'],'frozen_anchor_sequence':a['expected_sequence'],'activation_anchor_sequence':a['actual_sequence'],'anchor_n_change_range': [min(changes),max(changes)],'F5_published_interval_ms':{'median':statistics.median(intervals),'min':min(intervals),'max':max(intervals)},'max_abs_full_state_error_per_component':[max(abs(e[i]) for e in full_errors) for i in range(6)],'state_error_tolerance':tol,'raw_source_line_references':refs}
history=[]
for name in ['p1_C0_diag5_normal_20261008_01','p1_D0_observation_normal_20261009_01','p1_capability_regression_normal_20261006_01','p1_capability_regression_shadow_20261006_01']:
 p=E/name/'regulator_source.jsonl';rs=lines(p);dec=[r for r in rs if r.get('type')=='decision'];history.append({'run':name,'path':str(p),'decisions':len(dec),'accepted':sum(r.get('accepted') is True for r in dec),'mode_counts':dict(collections.Counter(r.get('mode') for r in dec)),'reason_counts':dict(collections.Counter(r.get('reason') for r in dec)),'current_version_or_plant_qualification_granted':False})
for author,name in [('authored_D1_C3_3_20261012_v9','owned_C3_3_positive_01'),('authored_D1_C3_4_20261013_v10','owned_C3_4_positive_01')]:
 r=E/author/'runs'/name;rs=lines(r/'observer/source.jsonl');session=js(r/'publisher/session_summary.json');end=session['end_steady_ns'];jobs={x['job']['job_id']:x['job'] for x in rs if x['type']=='job'};acc=[x for x in rs if x['type']=='decision' and x.get('accepted') is True]
 history.append({'run':name,'accepted':len(acc),'normal_live_owner_acceptance_claimed':False,'accepted_tail_details':[{'job_id':d['job_id'],'freeze_after_publisher_end_ms':(jobs[d['job_id']]['freeze_ns']-end)/1e6,'activation_after_publisher_end_ms':(d['activation_commit_ns']-end)/1e6,'anchor':jobs[d['job_id']]['anchor_n'],'publish_success':d['publish_success'],'mode':d['mode']} for d in acc]})
assert all(sha(p)==v for p,v in inputs.items())
summary={'schema':'SchemeA-rejection-readonly-audit/v1','passed':True,'normal_runs':out,'latest_normal_example':example,'historical_contexts':history,'totals':{k:sum(row[k] for row in out) for k in ['jobs','candidates','solver_success','registered','registration_success','activation_attempts','activation_accepted','latent_state_error_exceeded']},'source_inputs_before_sha256':inputs,'source_inputs_after_sha256':dict(inputs),'new_ROS_run_performed':False,'production_code_modified':False,'guards_modified':False,'counterfactual_activation_run_performed':False,'stage_qualified':False,'research_conclusion':False}
with (D/'evidence/rejection_audit_v1.json').open('x') as f:json.dump(summary,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'passed':True,'totals':summary['totals'],'latest':example,'source_inputs':len(inputs)},ensure_ascii=False))
