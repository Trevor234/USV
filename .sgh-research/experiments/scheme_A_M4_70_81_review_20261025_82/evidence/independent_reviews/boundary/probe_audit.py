#!/usr/bin/env python3
import sys,json,pathlib,tempfile,shutil,importlib.util
sys.dont_write_bytecode=True
base=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r2_driver_20261025_78')
run=base/'implementation/runs/T2B_P01'
author=base/'implementation/t2_author_r3'
sys.path.insert(0,str(author))
spec=importlib.util.spec_from_file_location('real_audit_t2',author/'audit_t2.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
table=json.loads((run/'action_table_copy.json').read_bytes())
reg=json.loads(pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2b_prepos_20261025_81/implementation/T2B_prepos_registration.json').read_bytes())
keep=['fixture/nominal_steps.jsonl','driver_events.jsonl','regulator/source.jsonl','regulator/witness.json','driver_result.json','worker/source.jsonl']
def read(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def write(p,r):p.write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in r))
results={}
for name in ['baseline','missing_worker_source','expired_zero_native_worker','missing_original_regulator_job','foreign_candidate_identity','no_task_commit_before_candidate']:
 with tempfile.TemporaryDirectory(prefix='review81_') as d:
  d=pathlib.Path(d)
  for x in keep:
   p=d/x;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(run/x,p)
  if name=='missing_worker_source':(d/'worker/source.jsonl').unlink()
  if name=='expired_zero_native_worker':
   rows=read(d/'worker/source.jsonl')
   for x in rows:
    if x.get('type')=='w2_boundary_result':
     x['actual_native_invoked']=False;x['disposition']='expired';x['boundary']['actual_native_invoked']=False;x['boundary']['disposition']='expired';x['boundary']['guard_ns']=x['boundary']['job_deadline_ns']+1000000
    if x.get('type')=='cold_start_policy_result' and x.get('job_id')==2:x['metadata']['actual_C_solve_calls_this_job']=0
   write(d/'worker/source.jsonl',rows)
  if name=='missing_original_regulator_job':
   write(d/'regulator/source.jsonl',[x for x in read(d/'regulator/source.jsonl') if x.get('type')!='job'])
  if name=='foreign_candidate_identity':
   rows=read(d/'regulator/source.jsonl')
   for x in rows:
    if x.get('type')=='candidate_registration' and x.get('job',{}).get('job_id')==2:x['job']['run_id']='foreign-run';x['job']['worker_instance']='foreign-worker';x['job']['task_generation']=999
   write(d/'regulator/source.jsonl',rows)
  if name=='no_task_commit_before_candidate':
   rows=read(d/'regulator/source.jsonl');cand=next(x for x in rows if x.get('type')=='candidate_registration' and x.get('job',{}).get('job_id')==2)
   # Retain only later unrelated version commits, all after candidate registration.
   write(d/'regulator/source.jsonl',[x for x in rows if not(x.get('type')=='path_version' and x.get('processed_ns',0)<=cand['ready_commit_ns'])])
  out=a.audit_run(d,table,reg)
  results[name]=out
pathlib.Path('/tmp/review81_boundary/audit_probe_results.json').write_text(json.dumps(results,indent=2))
print(json.dumps({k:{'passed':v['passed'],'checks':len(v['checks']),'failures':v['failures']} for k,v in results.items()},indent=2))
