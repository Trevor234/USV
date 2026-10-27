#!/usr/bin/env python3
"""Scoped whole-population anchor audit; source-pinned native history predicate."""
import argparse,copy,hashlib,json,math,pathlib,subprocess,sys
N=pathlib.Path(__file__).resolve().parent.parent
D=N.parent.parent/'scheme_A_C3_6_20261013_11'
N10=N.parent/'authored_D1_C3_4_20261013_v10'
N11=N.parent/'authored_D1_C3_5_20261013_v11'
sys.path.insert(0,str(N11))
import acceptance_core_v1 as C

def need(value,reason):
 if not value:raise ValueError(reason)
def integer(x):need(type(x) is int and 0<=x<(1<<63),'exact_nonnegative_int64');return x
def boolean(x):need(type(x) is bool,'exact_boolean');return x
def numbers(x,length):
 need(type(x) is list and len(x)==length,'numeric_array_shape')
 for n in x:need(type(n) in (int,float) and math.isfinite(n) and -25<=n<=25,'finite_command_domain')
 return x
def anchor(x):
 numbers(x['n'],2)
 need(len(x['sequence'])==len(x['publish_ns'])==len(x['known'])==2,'anchor_shape')
 for n in x['sequence']+x['publish_ns']:integer(n)
 for n in x['known']:boolean(n)
 return x
def janchor(j):return anchor({'n':j['anchor_n'],'sequence':j['anchor_sequence'],'publish_ns':j['anchor_publish_ns'],'known':j['anchor_known']})
def same(a,b):return json.dumps(a,sort_keys=True,separators=(',',':'))==json.dumps(b,sort_keys=True,separators=(',',':'))
def write(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def pin(p):
 raw=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
def evaluate(lock):
 need(set(lock['records'])=={'source','witness','session','ledger'},'exact_record_roles')
 reader=C.Reader(seconds=60,max_bytes=128*1024*1024)
 for p in lock['sources']:reader.verify(p)
 raw={k:reader.verify(v) for k,v in lock['records'].items()}
 rows=[C.strict_json(l) for l in raw['source'].splitlines() if l]
 ledger=[C.strict_json(l) for l in raw['ledger'].splitlines() if l]
 w=C.strict_json(raw['witness']);session=C.strict_json(raw['session'])
 by=lambda t:[r for r in rows if r.get('type')==t]
 jobs=by('job');regs=by('candidate_registration');validations=by('anchor_validation');decisions=by('decision');legacy=by('legacy_anchor')
 need((len(jobs),len(regs),len(validations),len(decisions),len(legacy))==(23,23,22,47,23),'registered_record_population')
 jobmap={integer(r['job']['job_id']):r['job'] for r in jobs};regmap={integer(r['job']['job_id']):r for r in regs};dmap={integer(r['sequence']):r for r in decisions}
 need(sorted(jobmap)==sorted(regmap)==list(range(1,24)) and sorted(dmap)==list(range(1,48)),'unique_job_registration_decision_population')
 lmap={integer(r['sequence']):r for r in legacy};need(sorted(lmap)==list(range(1,24)),'complete_legacy_population')
 for r in legacy:
  a=r['applied'];need(a['event_semantics']=='publisher_command','command_semantics')
  need(a['run_id']==session['run_id'] and a['producer_instance_id']==session['producer_instance_id'] and a['config_hash']==session['config_hash'],'publisher_identity')
  need(integer(a['sequence'])==r['sequence'] and same(numbers(a['final_n'],2),numbers(r['final_n'],2)),'applied_source_join')
  need(a['left_publish_success'] is True and a['right_publish_success'] is True,'whole_local_pair')
  need(all(boolean(a[k]) is False for k in ('plant_acceptance_observed','force_measured','execution_atomicity_proven')),'no_plant_upgrade')
  need(same(r['known'],[True,True]),'known_pair')
  for ch,name in enumerate(('left','right')):
   start=integer(a[name+'_publish_start_steady_ns']);end=integer(a[name+'_publish_end_steady_ns'])
   need(0<start<=end<=integer(r['processed_ns']) and start==r['publish_ns'][ch],'local_call_receipt_join')
  need(a['left_publish_end_steady_ns']<=a['right_publish_start_steady_ns'],'sequential_calls')
 submit={integer(a['job_id']):a for a in w['submit']};activations={integer(a['job_id']):a for a in w['activation']}
 need(sorted(submit)==list(range(1,24)) and sorted(activations)==list(range(1,23)),'witness_population')
 for jid,j in jobmap.items():
  a=janchor(j);need(j['anchor_source']=='legacy_publisher' and j['anchor_run_id']==session['run_id'] and j['anchor_producer']==session['producer_instance_id'],'job_owner_source')
  need(j['boot_id']==w['header']['boot_id'] and j['contract_hash']==w['header']['contract_sha256'],'job_boot_contract')
  for field in ('job_id','target_tick','task_generation','model_generation','config_generation','schedule_generation','clock_epoch','tick_origin_ns','freeze_ns','deadline_ns','target_ns'):integer(j[field])
  need(j['deadline_ns']==j['tick_origin_ns']+150000000 and j['target_ns']==j['tick_origin_ns']+200000000 and j['tick_origin_ns']<=j['freeze_ns']<=j['deadline_ns'],'job_fixed_time_contract')
  available=[r for r in legacy if r['processed_ns']<=j['freeze_ns']]
  need(bool(available),'job_anchor_receipt_missing');last=available[-1]
  need(same(a,{'n':last['final_n'],'sequence':[last['sequence']]*2,'publish_ns':last['publish_ns'],'known':last['known']}),'job_anchor_not_from_last_source')
  reg=regmap[jid];need(same(reg['job'],j),'immutable_full_job_echo')
  numbers(reg['first_control'],2)
  need(reg['accepted_registration'] is True and j['freeze_ns']<=integer(reg['ready_commit_ns'])<=j['deadline_ns'],'ready_gate')
  source_job=next(r for r in jobs if r['job']['job_id']==jid)
  need(j['freeze_ns']<=integer(source_job['submit_commit_ns'])<=integer(submit[jid]['commit_ns'])<=integer(source_job['publish_start_ns'])<=reg['ready_commit_ns'],'submit_check_witness_publish_order')
 for d in decisions:
  need(d['mode']=='shadow' and d['diagnostic_only'] is True,'shadow_profile')
  need(same(d['publish_success'],[False,False]) and same(d['publish_start_ns'],[0,0]) and same(d['publish_end_ns'],[0,0]) and d['plant_acceptance_observed'] is False,'shadow_did_not_publish')
  need(same(d['previous_n'],[0.0,0.0]) and same(d['previous_anchor_known'],[False,False]) and same(d['previous_publish_ns'],[0,0]),'previous_fields_are_uncalled_defaults')
 native_inputs=[];details=[]
 for v in validations:
  jid=integer(v['job_id']);d=dmap[integer(v['sequence'])];j=jobmap[jid];wa=activations[jid]
  need(d['job_id']==jid and v['check_ns']==d['activation_commit_ns']==wa['commit_ns'] and d['tick']==j['target_tick']==wa['target_tick'],'activation_identity_time_join')
  need(integer(d['ready_commit_ns'])==integer(regmap[jid]['ready_commit_ns'])==integer(wa['ready_commit_ns']),'ready_decision_witness_join')
  expected=anchor({'n':v['expected_n'],'sequence':v['expected_sequence'],'publish_ns':v['expected_publish_ns'],'known':v['expected_known']})
  actual=anchor({'n':v['actual_n'],'sequence':v['actual_sequence'],'publish_ns':v['actual_publish_ns'],'known':v['actual_known']})
  snap=d['d0_observation']['final_snapshot'];need(same(expected,janchor(j)),'validation_expected_job_join');need(same(actual,anchor(snap['anchor'])),'validation_snapshot_join')
  need(v['producer']==snap['anchor_producer']==j['anchor_producer'] and v['run_id']==snap['anchor_run_id']==j['anchor_run_id'],'activation_owner_join')
  latest=[r for r in legacy if r['processed_ns']<=v['check_ns']][-1]
  need(same(actual,{'n':latest['final_n'],'sequence':[latest['sequence']]*2,'publish_ns':latest['publish_ns'],'known':latest['known']}),'activation_anchor_not_from_last_source')
  history=snap['publication_history'];need(len(history)==2*latest['sequence'],'full_history_population')
  for e in history:
   ch=integer(e['channel']);need(ch in (0,1),'history_channel');boolean(e['known']);integer(e['publish_ns']);numbers([e['n']],1)
   r=lmap[integer(e['sequence'])];need(e['n']==r['final_n'][ch] and e['known']==r['known'][ch] and e['publish_ns']==r['publish_ns'][ch],'history_source_join')
  selected=[e for e in history if expected['sequence'][e['channel']]<=e['sequence']<=actual['sequence'][e['channel']]]
  need(same(v['entries'],selected),'validation_history_subset_join')
  need(boolean(v['accepted'])==boolean(d['accepted'])==boolean(wa['accepted']),'activation_acceptance_witness_join')
  need(v['decision_reason']==d['reason'],'decision_reason_join')
  native_inputs.append({'job_id':jid,'expected':expected,'actual':actual,'history':v['entries']})
  details.append({'job_id':jid,'sequence':d['sequence'],'expected':expected,'actual':actual,'reason':v['history_reason'],'accepted':d['accepted'],'commit_ns':d['activation_commit_ns']})
 probe=pathlib.Path(lock['probe']['path']);reader.verify(lock['probe'])
 result=subprocess.run([str(probe),'--history'],input=json.dumps(native_inputs,allow_nan=False).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 need(result.returncode==0,'native_history_probe_failed');out=C.strict_json(result.stdout)
 need(len(out)==22,'native_history_population')
 for got,detail in zip(out,details):need(got['job_id']==detail['job_id'] and got['reason']==detail['reason'],'native_history_reason_differs')
 mismatches=[r for r in details if r['reason']=='anchor_mismatch'];accepted=[r for r in details if r['accepted']]
 need(len(mismatches)==21 and len(accepted)==1 and accepted[0]['job_id']==22,'registered_anchor_outcome_population')
 tail=accepted[0];j=jobmap[22];td=dmap[tail['sequence']];last=legacy[-1]
 signal=[r for r in ledger if r.get('name')=='publisher' and r['type']=='signal'];cleanup=[r for r in ledger if r.get('name')=='publisher' and r['type']=='cleanup_result']
 need(len(signal)==len(cleanup)==1,'publisher_lifecycle_population')
 lifecycle={'signal_ns':integer(signal[0]['monotonic_ns']),'last_zero_start_ns':last['publish_ns'],'session_end_ns':integer(session['end_steady_ns']),'tail_freeze_ns':j['freeze_ns'],'tail_activation_ns':tail['commit_ns'],'cleanup_ns':integer(cleanup[0]['monotonic_ns'])}
 need(last['applied']['control_source']=='shutdown_zero' and last['final_n']==[0.0,0.0],'last_shutdown_command')
 need(lifecycle['signal_ns']<=min(lifecycle['last_zero_start_ns'])<=max(lifecycle['last_zero_start_ns'])<=lifecycle['session_end_ns']<lifecycle['tail_freeze_ns']<lifecycle['tail_activation_ns']<lifecycle['cleanup_ns'],'tail_between_session_end_and_cleanup')
 need(cleanup[0]['cleanup_complete'] is True and cleanup[0]['remaining_members']==[],'eventual_cleanup')
 need(td['requested_n']==regmap[22]['first_control'] and any(n!=0 for n in td['requested_n']),'nonzero_shadow_proposal')
 need(reader.unchanged(),'input_changed')
 return {'schema':'p1-C3.6-A-historical-anchor-audit/v1','passed':True,'jobs':23,'registrations':23,'activations':22,'decisions':47,'legacy_pairs':23,'anchor_mismatches':21,'shadow_accepted':1,'details':details,'lifecycle':lifecycle,'tail_requested_n':td['requested_n'],'native_history_predicate_cases':22,'default_previous_fields_unusable_as_feedback':True,'input_before_after_unchanged':True,'scope':'anchor Source/Job/registration/Decision/Witness/lifecycle subset of frozen N10; CDR/GID already separately locked by parent, not newly reauthenticated','stage_qualified':False,'research_conclusion':False,'new_ROS_nodes':False}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
 need(args.attempt.isascii() and args.attempt.replace('_','').isalnum(),'attempt_name')
 out=D/'historical'/args.attempt;out.mkdir(exist_ok=False)
 R=N10/'runs/owned_C3_4_positive_01'
 roles={'source':R/'observer/source.jsonl','witness':R/'observer/witness.json','session':R/'publisher/session_summary.json','ledger':R/'owned_process_ledger.jsonl'}
 sources=[pathlib.Path(__file__).resolve(),N11/'acceptance_core_v1.py',N10/'observer/src/shadow/p1_admission.hpp',N10/'observer/src/shadow/regulator_shadow_observer.cpp',N10/'publisher/src/mpc_node.cpp',N10/'worker/solver_worker.cpp',pathlib.Path('/home/trevor/USV/usv_mpc_ws/src/usv_research_interfaces/msg/AppliedControl.msg'),N/'vendor/p1_admission_N10.hpp',N/'include/command_anchor_v1.hpp',N/'tests/test_command_anchor_v1.cpp']
 lock={'schema':'p1-C3.6-A-retrospective-input-lock/v1','records':{k:pin(p) for k,p in roles.items()},'sources':[pin(p) for p in sources],'probe':pin(D/'component/attempt03/test_command_anchor_v1'),'record_semantics':'retrospective original byte locks, not historical pre-run registration'}
 write(out/'input_lock_v1.json',lock);write(out/'result.json',evaluate(lock))
 originals={k:p.read_bytes() for k,p in roles.items()};cases=[]
 for name in ['job_anchor','actual_anchor','history_omission','publish_promotion','previous_promoted','session_end_shift','cleanup_shift','witness_accept','job_echo','typed_anchor_bool']:
  directory=D/'negatives'/args.attempt/name;directory.mkdir(parents=True,exist_ok=False)
  data={k:([C.strict_json(l) for l in raw.splitlines() if l] if k in ('source','ledger') else C.strict_json(raw)) for k,raw in originals.items()}
  rows=data['source'];v=next(r for r in rows if r['type']=='anchor_validation');dec=next(r for r in rows if r['type']=='decision' and r['sequence']==v['sequence'])
  if name=='job_anchor':
   for r in rows:
    if r['type'] in ('job','candidate_registration') and r['job']['job_id']==1:r['job']['anchor_n']=[0.,0.]
   v['expected_n']=[0.,0.]
  elif name=='actual_anchor':v['actual_n']=[0.,0.];dec['d0_observation']['final_snapshot']['anchor']['n']=[0.,0.]
  elif name=='history_omission':v['entries']=v['entries'][1:]
  elif name=='publish_promotion':next(r for r in rows if r['type']=='decision' and r['accepted'])['publish_success']=[True,False]
  elif name=='previous_promoted':dec['previous_n']=v['actual_n']
  elif name=='session_end_shift':data['session']['end_steady_ns']=next(r for r in rows if r['type']=='decision' and r['accepted'])['activation_commit_ns']+1
  elif name=='cleanup_shift':next(r for r in data['ledger'] if r['type']=='cleanup_result' and r.get('name')=='publisher')['monotonic_ns']=data['session']['end_steady_ns']+1
  elif name=='witness_accept':data['witness']['activation'][-1]['accepted']=False
  elif name=='job_echo':next(r for r in rows if r['type']=='candidate_registration')['job']['task_generation']+=1
  elif name=='typed_anchor_bool':v['actual_sequence'][0]=True;dec['d0_observation']['final_snapshot']['anchor']['sequence'][0]=True
  altered=copy.deepcopy(lock)
  for role,x in data.items():
   path=directory/(role+('.jsonl' if role in ('source','ledger') else '.json'))
   if role in ('source','ledger'):
    with path.open('x') as f:
     for row in x:f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
   else:write(path,x)
   altered['records'][role]=pin(path)
  write(directory/'rebound_input_lock.json',altered)
  try:evaluate(altered);case={'case':name,'passed':False,'reason':'accepted_corrupted_copy'}
  except ValueError as e:case={'case':name,'passed':True,'reason':str(e),'coherently_repinned_all_records':True}
  write(directory/'result.json',case);cases.append(case)
 need(all(c['passed'] for c in cases),'negative_copy_accepted')
 need(all(roles[k].read_bytes()==raw for k,raw in originals.items()),'original_records_changed')
 write(out/'negative_summary.json',{'passed':True,'count':len(cases),'cases':cases,'originals_unchanged':True,'stage_qualified':False})
 print(json.dumps({'passed':True,'historical_native_cases':22,'coherent_negative_copies':len(cases),'result':str(out/'result.json')}))
if __name__=='__main__':main()
