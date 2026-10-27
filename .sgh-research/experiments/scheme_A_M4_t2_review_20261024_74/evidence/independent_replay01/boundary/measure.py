#!/usr/bin/env python3
"""Read-only reconstruction of batch73 measurements plus trigger admission."""
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
base = Path('/home/trevor/USV/.sgh-research/experiments')
p72 = base / 'scheme_A_M4_t2a_clock_freeze_owned_20261024_72' / 'implementation'
run = p72 / 'runs' / 'T2A_14'
author = p72 / 't2_author_rev8'
out = Path(__file__).resolve().parent
def rows(role):
    return [(n,json.loads(s)) for n,s in enumerate((run/role/'source.jsonl').read_text().splitlines(),1)]
w,r = rows('worker'),rows('regulator')
def keyed(data,kind):
    return {v.get('job_id',(v.get('job') or {}).get('job_id')):(n,v) for n,v in data if v.get('type')==kind}
recv,cands,sub,ready = (keyed(w,'job_received'),keyed(w,'candidate'),keyed(r,'job'),keyed(r,'candidate_registration'))
windows=[]
for jid in sorted(cands):
    wn,v=cands[jid]; rn,j=sub[jid]; an,a=ready[jid]; cn,c=recv[jid]
    windows.append({'job_id':jid,'worker_receive_line':cn,'worker_candidate_line':wn,
      'regulator_submit_line':rn,'regulator_ready_line':an,
      'receive_ns':c['receive_ns'],'candidate_event_publish_start_ns':v['publish_start_ns'],
      'receive_to_candidate_event_ns':v['publish_start_ns']-c['receive_ns'],
      'solve_start_to_end_ns':v['solve_end_ns']-v['solve_start_ns'],'backend_ms':v['backend_ms'],
      'submit_commit_ns':j['submit_commit_ns'],'ready_commit_ns':a['ready_commit_ns'],
      'submit_commit_to_ready_commit_ns':a['ready_commit_ns']-j['submit_commit_ns'],
      'accepted_registration':a['accepted_registration']})
caps=[(n,v) for n,v in w if v.get('type') in ('capability_publish_attempt','capability_publish_result')]
attempt=[(n,v) for n,v in caps if v['type']=='capability_publish_attempt']
result=[(n,v) for n,v in caps if v['type']=='capability_publish_result']
spec=importlib.util.spec_from_file_location('t2_readonly_probe',author/'t2_action_contract.py')
t2=importlib.util.module_from_spec(spec); spec.loader.exec_module(t2)
table=json.loads((p72/'t2_tables_v8/T2B_v8.json').read_text())
triggers=[]
for phase in ('solve_active','ready_window'):
    t=json.loads(json.dumps(table));t['actions'][0]['trigger']['phase']=phase
    # Exact shape the Driver caches at lines308-315 and331-332.
    evidence={'observed_ns':1,'job':sub[2][1]['job']}
    c={'schema':t2.COMMAND_SCHEMA,'run_id':t['run_id'],'contract_sha256':t2.V3_CONTRACT_SHA,
       'action_id':'a1','sequence':1,'trigger':evidence}
    try:
        t2.validate_command(c,t,[]);verdict='accepted'
    except AssertionError as ex:
        verdict=str(ex)
    triggers.append({'phase':phase,'actual_driver_evidence_keys':sorted(evidence),'validator_result':verdict})
files=[run/'worker/source.jsonl',run/'regulator/source.jsonl',author/'t2_action_contract.py',
       author/'t2_scenario_driver_v1.py',author/'observer/src/shadow/task_time_profile_v1.hpp',
       author/'observer/src/shadow/regulator_owned_execute.cpp']
data={'scope':'offline read-only original files; scripts/output only in /tmp; no ROS or owned run',
 'sources':[{ 'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
 'job_windows':windows,
 'capability':{'all_publish_rows':len(caps),'type_counts':dict(Counter(v['type'] for _,v in caps)),
   'attempt_payload_active_job_counts':dict(Counter(v['payload']['active_job'] for _,v in attempt)),
   'result_rows_with_payload':sum('payload' in v for _,v in result),
   'result_rows_with_top_level_active_job':sum('active_job' in v for _,v in result),
   'attempt_lines':[n for n,_ in attempt],'result_lines':[n for n,_ in result],
   'snapshot_intervals_ns':[b['snapshot_ns']-a['snapshot_ns'] for (_,a),(_,b) in zip(attempt,attempt[1:])]},
 'trigger_admission':triggers}
(out/'measurements.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':str(out/'measurements.json'),'job_count':len(windows),
 'receive_to_candidate_event_ns':[v['receive_to_candidate_event_ns'] for v in windows],
 'submit_commit_to_ready_commit_ns':[v['submit_commit_to_ready_commit_ns'] for v in windows],
 'capability_counts':data['capability']['type_counts'],'trigger_admission':triggers},ensure_ascii=False))
