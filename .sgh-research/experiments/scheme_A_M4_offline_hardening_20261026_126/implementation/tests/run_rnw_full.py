import copy,json,shutil,sys
from pathlib import Path
from offline_support import Evidence,ROOT,pin,save
sys.path.insert(0,str(ROOT/'implementation/audit'))
import rnw_audit_v3 as audit
import rnw_audit_v2 as old
e=Evidence('E02',sys.argv[1]);run=ROOT.parent/'scheme_A_M4_rnw_s4_owned_20261025_119/implementation/runs/T2A_RNW3'
save(e.out/'registration.json',{'family':'RNW','target_job':7,'sequence':18,'full_types':['SolveJob:44','SolveCandidate:14','ExecutionDecision:57','AppliedControl:39'],
 'positive':'actual RNW3 full control population','negative_controls':['missing Worker','missing witness','missing Stored','full Job reference mismatch','right API mismatch','actual C marker zero','Worker time reversal','duplicate API','Stored full Job mismatch'],
 'scope':'additional mandatory gates omitted by earlier v2; no legacy evidence edited'})
decoded=e.out/'stored_full.json'
r=e.command('read_Stored',['bash',ROOT/'implementation/setup_env.sh','/usr/bin/python3','-B',ROOT/'implementation/audit/stored_control_reader_v1.py',run,decoded],timeout=120)
e.check('full_native_CDR_decoder',r.returncode==0)
if r.returncode:
 result=e.finish();sys.exit(2)
stored=json.loads(decoded.read_text());src,bad=old.rows_of(run/'regulator/source.jsonl');worker,badw=old.rows_of(run/'worker/source.jsonl')
e.check('both_Source_streams_parse',bad==badw==0)
base=audit.audit(run,stored);save(e.out/'baseline.json',base)
e.check('RNW3_full_Source_Worker_Stored_accept',base['run_accepted']is True,base['gates'])
e.check('RNW3_exact_Job7_seq18_real_C',base['r4_observed']is not None and base['r4_observed']['job_id']==7 and base['r4_observed']['sequence']==18 and base['r4_observed']['actual_C_calls']==1)
results={}
def negative(name,mutate,gate,reason):
 s,w,st=copy.deepcopy(src),copy.deepcopy(worker),copy.deepcopy(stored);mutate(s,w,st)
 d=audit.audit(run,st,source_override=s,worker_override=w);results[name]=d
 g=next((g for g in d['gates']if g['gate']==gate),{})
 e.check(name,d['run_accepted']is False and g.get('passed')is False and g.get('reason')==reason,g)
def jobrow(rows,typ):return next(r for r in rows if r.get('type')==typ and r.get('job',{}).get('job_id')==7)
def seqrow(rows,typ):return next(r for r in rows if r.get('type')==typ and r.get('sequence')==18)
negative('full_Job_reference_echo',lambda s,w,st:jobrow(s,'candidate_registration')['job']['reference'].__setitem__(0,999.0),'R4.complete_identity_time_and_API','complete_job_echo')
negative('right_API_time',lambda s,w,st:seqrow(s,'owned_API_pair')['starts'].__setitem__(1,1),'R4.complete_identity_time_and_API','both_channel_API_times')
negative('actual_C_marker_zero',lambda s,w,st:next(r for r in w if r.get('type')=='cold_start_policy_result'and r.get('job_id')==7)['metadata'].__setitem__('actual_C_solve_calls_this_job',0),'R4.complete_identity_time_and_API','actual_C_entry')
negative('worker_time_reversal',lambda s,w,st:jobrow(w,'candidate').__setitem__('solve_end_ns',1),'R4.complete_identity_time_and_API','full_logical_time_order')
negative('duplicate_API',lambda s,w,st:s.append(copy.deepcopy(seqrow(s,'owned_API_pair'))),'R4.complete_identity_time_and_API','population.owned_API_pair')
negative('Stored_full_reference',lambda s,w,st:next(r for r in st['records']['SolveJob']if r['data']['job_id']==7)['data']['reference'].__setitem__(0,999.0),'Stored.full_control_streams','Stored_full_Job')
missing=audit.audit(run,None);e.check('missing_Stored_blocks_complete_accept',missing['run_accepted']is False and missing['r4_observed']is not None)
for name,excluded in [('missing_Worker','worker/source.jsonl'),('missing_witness','regulator/witness.json'),('missing_close','driver_result.json')]:
 private=e.out/'fixtures'/name
 for relative in ['regulator/source.jsonl','regulator/witness.json','worker/source.jsonl','driver_events.jsonl','driver_result.json','fixture/terminal.json','recorder/terminal.json']:
  if relative==excluded:continue
  target=private/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(run/relative,target)
 d=audit.audit(private,stored);results[name]=d
 e.check(name,d['run_accepted']is False and (d['r4_observed']is not None if name!='missing_Worker'else d['r4_observed']is None),d['gates'])
legal=list(reversed(src));d=audit.audit(run,stored,source_override=legal)
e.check('legal_Source_file_order_independent',d['run_accepted']is True,d['gates'])
old_failures={}
for name in ['T2A_RNW2','T2A_RNW2_attempt1']:
 path=ROOT.parent/'scheme_A_M4_t2a_rnw2_impl_20261025_112/implementation/runs'/name
 d=old.audit_rnw_run(path);old_failures[name]=d
 e.check('historical_no_open_'+name,d['r4_observed']['passed']is False and d['run_accepted']['accepted']is False)
save(e.out/'counterexamples.json',results);save(e.out/'historical_112.json',old_failures)
result=e.finish(full_field_counts={k:len(v)for k,v in stored['full_fields'].items()},stored_population={k:len(v)for k,v in stored['records'].items()},
 actual_RNW3_R4=base['r4_observed'],run_accepted=base['run_accepted'],type_support_files=stored['type_support_identity'],audit_source_pin=pin(ROOT/'implementation/audit/rnw_audit_v3.py'))
sys.exit(0 if result['status']=='PASS'else 2)
