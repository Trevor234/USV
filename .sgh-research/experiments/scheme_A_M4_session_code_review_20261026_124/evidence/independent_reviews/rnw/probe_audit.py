import copy, hashlib, importlib.util, json, pathlib, tempfile
B=pathlib.Path('/home/trevor/USV/.sgh-research/experiments')
P=B/'scheme_A_M4_rnw_s4_owned_20261025_119/implementation'
S=P/'runs/T2A_RNW3'; A=P/'rnw_audit_v1.py'
spec=importlib.util.spec_from_file_location('rnw_review',A);a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
rows=[json.loads(l) for l in (S/'regulator/source.jsonl').read_text().splitlines() if l.strip()]
closed=json.loads((S/'driver_result.json').read_text());events=(S/'driver_events.jsonl').read_text()
res=[]
def run(name, mutate, close=closed,ev=events):
 s=copy.deepcopy(rows);mutate(s)
 with tempfile.TemporaryDirectory() as td:
  d=pathlib.Path(td);(d/'regulator').mkdir()
  (d/'regulator/source.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in s))
  if close is not None:(d/'driver_result.json').write_text(json.dumps(close))
  if ev is not None:(d/'driver_events.jsonl').write_text(ev)
  v=a.audit_rnw_run(d)
  res.append({'case':name,'passed':v['passed'],'failed_clauses':[c['name'] for c in v.get('clauses',[]) if not c['passed']]})
run('actual_RNW3',lambda s:None)
run('missing_close_and_spawn_evidence',lambda s:None,close=None,ev=None)
run('no_clock_events',lambda s:s.__setitem__(slice(None),[r for r in s if r.get('type')!='clock']))
def wrong_open(s):
 for r in s:
  if r.get('type')=='reference_epoch_generation_opened':r['generation']=99;r['previous_terminal_reason']='invented'
run('wrong_generation_open',wrong_open)
def reorder(s):
 # Actual Source emits API/Applied before final Decision diagnostic row; causal times must be used.
 chain=[r for r in s if r.get('type') in ('job','candidate_registration') and r.get('job',{}).get('job_id')==7]
 chain += [r for r in s if r.get('sequence')==18 and r.get('type') in ('decision','owned_API_pair','owned_applied_publication')]
 for r in chain:s.remove(r)
 oi=next(i for i,r in enumerate(s) if r.get('type')=='reference_epoch_generation_opened')
 s[oi+1:oi+1]=list(reversed(chain))
run('reversed_R4_chain_still_present',reorder)
def identity(s):
 for r in s:
  if r.get('type')=='candidate_registration' and r.get('job',{}).get('job_id')==7:
   r['job']['run_id']='foreign-run';r['job']['schedule_generation']=1;r['job']['target_tick']=999
run('candidate_echo_same_id_foreign_run_and_old_binding',identity)
# Isolated R4 probe prevents later good Jobs hiding mutations.
opened=next(r for r in rows if r.get('type')=='reference_epoch_generation_opened')
j=next(r for r in rows if r.get('type')=='job' and r.get('job',{}).get('job_id')==7)
c=next(r for r in rows if r.get('type')=='candidate_registration' and r.get('job',{}).get('job_id')==7)
d=next(r for r in rows if r.get('type')=='decision' and r.get('job_id')==7)
p=next(r for r in rows if r.get('type')=='owned_API_pair' and r.get('sequence')==18)
ap=next(r for r in rows if r.get('type')=='owned_applied_publication' and r.get('sequence')==18)
for name, seq in [('isolated_actual',[opened,j,c,d,p,ap]),('isolated_reverse',[opened,ap,p,d,c,j])]:
 res.append({'case':name,'passed':a.audit_r4_acceptance_chain(seq)[0]['passed']})
cf=copy.deepcopy(c);cf['job']['run_id']='foreign';cf['job']['schedule_generation']=1
res.append({'case':'isolated_foreign_candidate','passed':a.audit_r4_acceptance_chain([opened,j,cf,d,p,ap])[0]['passed']})
# Actual evidence fields condensed, including logical times rather than sink append order.
summary=[]
for i,r in enumerate(rows,1):
 typ=r.get('type')
 if (typ in ('job','candidate_registration') and r.get('job',{}).get('job_id')==7) or (typ=='decision' and r.get('job_id')==7) or (typ in ('owned_API_pair','owned_applied_publication') and r.get('sequence')==18) or typ in ('reference_epoch_generation_opened',):
  summary.append({'line':i,'type':typ,**{k:r[k] for k in ('generation','sequence','accepted','accepted_registration','control_source','returned','submit_commit_ns','ready_commit_ns','start_ns','end_ns','publish_start_ns','publish_end_ns','processed_ns','opened_ns') if k in r},'job':{k:r.get('job',{}).get(k) for k in ('job_id','run_id','boot_id','schedule_generation','target_tick')} if 'job' in r else None})
out={'schema':'review123-rnw-probe/v1','auditor_path':str(A),'auditor_sha256':hashlib.sha256(A.read_bytes()).hexdigest(),'results':res,'actual_R4_condensed':summary}
pathlib.Path('/tmp/review123_rnw/audit_probe_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
