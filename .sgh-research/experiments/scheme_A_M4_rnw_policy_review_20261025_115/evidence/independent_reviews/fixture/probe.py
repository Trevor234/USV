#!/usr/bin/env python3
"""Read-only batch114 plan review. Does not import any runner or initialize ROS."""
import ast, copy, hashlib, json, sys
from pathlib import Path
BASE=Path('/home/trevor/USV/.sgh-research/experiments')
B112=BASE/'scheme_A_M4_t2a_rnw2_impl_20261025_112'
TREE=B112/'implementation/t2_author'
RUN=B112/'implementation/runs/T2A_RNW2'
OUT=Path('/tmp/review114_fixture_plan')
def rows(p):return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
src=rows(RUN/'regulator/source.jsonl'); fixture=rows(RUN/'fixture/nominal_steps.jsonl')
actions=[(i+1,x) for i,x in enumerate(fixture) if x.get('type')=='t2_action_executed']
clock=[(i+1,x) for i,x in enumerate(src) if x.get('type')=='clock']
hold=next(x for _,x in actions if x['action']=='clock_hold'); resume=next(x for _,x in actions if x['action']=='clock_resume')
preclock=next((i,x) for i,x in reversed(clock) if x['receive_ns']<hold['executed_ns'])
postclock=next((i,x) for i,x in clock if x['receive_ns']>resume['executed_ns'])
decisions={x['sequence']:(i+1,x) for i,x in enumerate(src) if x.get('type')=='decision'}
metrics={'run':str(RUN), 'raw_source_sha256':hashlib.sha256((RUN/'regulator/source.jsonl').read_bytes()).hexdigest(),
 'actions':[{'line':i,**{k:x[k] for k in ('action','executed_ns','stamp_ns','parameters')}} for i,x in actions],
 'actual_hold_ns':resume['executed_ns']-hold['executed_ns'],
 'clock_pre':{'line':preclock[0],**{k:preclock[1][k] for k in ('receive_ns','sim_ns','epoch','schedule_generation')}},
 'clock_post':{'line':postclock[0],**{k:postclock[1][k] for k in ('receive_ns','sim_ns','epoch','schedule_generation')}},
 'clock_receive_gap_ns':postclock[1]['receive_ns']-preclock[1]['receive_ns'],
 'clock_sim_advance_ns':postclock[1]['sim_ns']-preclock[1]['sim_ns'],
 'all_clock_epochs':sorted({x['epoch'] for _,x in clock}),
 'backward_clock_pairs':[{'before_line':i,'after_line':j,'before_sim':x['sim_ns'],'after_sim':y['sim_ns']} for (i,x),(j,y) in zip(clock,clock[1:]) if y['sim_ns']<x['sim_ns']],
 'seq14_15':[{ 'line':decisions[n][0],**{k:decisions[n][1][k] for k in ('sequence','epoch','schedule_generation','publish_sim_ns','activation_clock_sim_ns','reason')}} for n in (14,15)]}
# Replay only the actual check statements from the runner's AST. No imports,
# subprocesses, registration writes, or main/owned execution are evaluated.
script=B112/'implementation/run_t2a_rnw2.py'
code=script.read_text(); syntax=ast.parse(code)
start=next(i for i,n in enumerate(syntax.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='closed' for t in n.targets))
end=next(i for i,n in enumerate(syntax.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='verdict' for t in n.targets))
block=ast.Module(body=syntax.body[start:end],type_ignores=[])
fabricated=[{'type':'reference_epoch_committed','reference_epoch':{'generation':1,'clock_epoch':0}},
 {'type':'reference_epoch_committed','reference_epoch':{'generation':2,'clock_epoch':1}},
 {'type':'reference_epoch_generation_opened','generation':2,'previous_terminal_reason':'epoch_binding_changed','previous_first_job_id':1,'previous_last_job_id':1},
 {'type':'job','job':{'job_id':2}},
 {'type':'candidate_registration','accepted_registration':False,'reason':'solver_failed','job':{'job_id':2}},
 {'type':'owned_applied_publication','control_source':'ramp_zero','sequence':1},
 {'type':'job_scoped_generation_resubmit'}]
checks=[]
def check(name,ok,detail=None):checks.append({'name':name,'passed':bool(ok),'detail':detail});return bool(ok)
namespace={'result':{'closed_roles':[{'role':r,'returncode':0,'group_empty':True} for r in ('fixture','worker','recorder','regulator')]},
 'ev':[{'type':'role_spawned','role':r} for r in ('fixture','worker','recorder','regulator')],
 'src':fabricated,'ok':True,'check':check}
exec(compile(ast.fix_missing_locations(block),str(script),'exec'),namespace)
runner_probe={'method':'AST-selected exact runner check block; subprocess/main never evaluated',
 'fabricated_no_pause_no_resume_no_accepted_candidate_no_candidate_activation':fabricated,
 'all_runner_checks_pass':namespace['ok'],'checks':checks}
# Import pure admission module; its imports do not initialize ROS.
sys.dont_write_bytecode=True;sys.path.insert(0,str(TREE))
import t2b_gen_admission as admission
original=json.loads((B112/'implementation/T2A_RNW2_table.json').read_text())
mutations={}
missing=copy.deepcopy(original);missing['actions']=missing['actions'][1:];mutations['missing_hold']=missing
reversed_=copy.deepcopy(original);reversed_['actions'][0],reversed_['actions'][1]=reversed_['actions'][1],reversed_['actions'][0];mutations['resume_before_hold_in_action_order']=reversed_
clauses=copy.deepcopy(original);clauses['clauses']={k:False for k in clauses['clauses']};mutations['all_clause_values_false']=clauses
admission_probes=[]
for name,table in mutations.items():
 try:admission.validate_table(table,original);outcome='ACCEPTED'
 except AssertionError as e:outcome='REJECTED: '+str(e)
 admission_probes.append({'mutation':name,'outcome':outcome})
# Exact edge arithmetic example: 20ms writer cadence, hold command 13ms
# after last actual clock, resume 1500ms later, next writer 13ms after last held writer.
# The shorthand last_stamp + (resume_action - hold_action) loses 13ms vs
# the last-published clock pair mapping unless all edge intervals are accounted.
arithmetic={'definition':'ms toy schedule, last published pair (S=100000,T=0), hold action T=13, resume action T=1513, next writer T=1520, last held writer T=1500',
 'shorthand_at_resume':100000+(1513-13),'existing_next_writer_add':1520-1500,
 'shorthand_next_stamp':100000+(1513-13)+(1520-1500),
 'paired_mapping_next_stamp':100000+(1520-0),
 'note':'This toy happens to align; changing action relative phase or timer cadence can leave either sign edge error. Store and use (S_last,T_last) directly.'}
# Non-aligned resume phase example establishes error: last held writer1500;
# resume1502, hold13. shorthandnext=151? same formula difference=-11.
arithmetic['nonaligned_example']={'hold_action_ms':13,'resume_action_ms':1502,'last_held_writer_ms':1500,'next_writer_ms':1520,'shorthand_next_stamp':100000+(1502-13)+(1520-1500),'paired_mapping_next_stamp':101520,'error_ms':(1502-13)+(1520-1500)-1520}
result={'metrics':metrics,'runner_probe':runner_probe,'admission_probes':admission_probes,'arithmetic':arithmetic}
(OUT/'findings.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'hold_ns':metrics['actual_hold_ns'],'clock_gap_ns':metrics['clock_receive_gap_ns'],'clock_sim_advance_ns':metrics['clock_sim_advance_ns'],'backward_clock_pairs':metrics['backward_clock_pairs'],'epochs':metrics['all_clock_epochs'],'runner_fake_pass':namespace['ok'],'admission':admission_probes},indent=2))
