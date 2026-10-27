import ast
import copy
import hashlib
import json
from pathlib import Path

P=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_registration_20261023_63/implementation/w2_author/owned_m4_diagnostic_driver_v1.py')
source=P.read_text();tree=ast.parse(source)
main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
attempt=next(n for n in main.body if isinstance(n,ast.Try))
target=next(n for n in attempt.finalbody if isinstance(n,ast.If) and n.lineno==779)
branch=ast.fix_missing_locations(ast.Module(body=target.body,type_ignores=[]))
program=compile(branch,str(P),'exec')
reg=json.loads((P.parent.parent/'W2_registration_v1.json').read_text())
closed=[{'role':r,'returncode':2 if r=='worker' else 0,'signals':([{'signal':'SIGINT'}] if r!='regulator' else []),'group_empty':True} for r in ('regulator','worker','fixture','recorder')]
baseline={'reg':reg,'w2':reg['w2_release'],'closed':closed,
 'by_role':{r['role']:r for r in closed},
 'registered_job_ids':set(),'published_job_ids':set(),
 'w2_terminal_evidence':{'backend_terminal':True,'active_cleared':True,'pending_discarded':True,
                         'terminal_events':[{'type':'terminal_exception','job_id':2,'reason':'w2_boundary_expired'}]},
 'result':{'W2_observed':True,'w2_boundary_entered':True,'w2_release_sent':True,
   'w2_entered_row':{'job_id':2,'ordinal':1},'w2_ticks_after_enter':[3,4],
   'w2_result':{'job_id':2,'ordinal':1,'disposition':'expired','actual_native_invoked':False,
     'boundary':{'released':True,'gate_outcome':'released','guard_ns':1200,'job_deadline_ns':1150,'entered_ns':1000}},
   'transition_ns':1300,'transition_reason':'fatal_capability','watchdog_ns':None,'ramp_ok':True}}

def run(scope):
    scope=copy.deepcopy(scope)
    scope['rc_is']=lambda role,value: scope['by_role'].get(role,{}).get('returncode')==value
    scope['only_int']=lambda role:[s['signal'] for s in scope['by_role'].get(role,{}).get('signals',[])]==['SIGINT']
    try:
        exec(program,scope)
        return {'passed':scope['result'].get('passed'),'outcome':'returned'}
    except Exception as e:
        return {'outcome':'exception','type':type(e).__name__,'message':str(e)}

report={'scope':'AST source-statement replay of actual final W2 predicate, no ROS, no process spawn',
 'driver':str(P),'driver_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),
 'source_lines':[target.lineno,target.end_lineno], 'cases':{}}
report['cases']['baseline']=run(baseline)
bad=copy.deepcopy(baseline);bad['result']['w2_result']['boundary']['released']=False;bad['result']['w2_result']['boundary']['gate_outcome']='timeout'
report['cases']['release_not_verified_but_label_expired']=run(bad)
bad=copy.deepcopy(baseline);bad['result']['w2_result']['boundary']['guard_ns']=1100
report['cases']['guard_precedes_deadline_but_label_expired']=run(bad)
bad=copy.deepcopy(baseline);bad['w2_terminal_evidence']['terminal_events'][0]['job_id']=999
report['cases']['terminal_event_wrong_job']=run(bad)
bad=copy.deepcopy(baseline)
for name in ('registered_job_ids','published_job_ids','w2_terminal_evidence'):bad.pop(name)
bad['result']={'passed':False,'error':"RuntimeError('fixture authentication failed')"}
report['cases']['bootstrap_error_before_observer_initialization']=run(bad)
local_mark=ast.If(test=ast.Constant(False),body=[ast.Assign(targets=[ast.Name(id=n,ctx=ast.Store())],value=ast.Constant(None)) for n in ('registered_job_ids','published_job_ids','w2_terminal_evidence')],orelse=[])
fn=ast.FunctionDef(name='actual_function_scope_replay',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=[local_mark]+target.body,decorator_list=[])
fnmodule=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
scope=copy.deepcopy(bad)
scope['rc_is']=lambda role,value:scope['by_role'].get(role,{}).get('returncode')==value
scope['only_int']=lambda role:[s['signal'] for s in scope['by_role'].get(role,{}).get('signals',[])]==['SIGINT']
exec(compile(fnmodule,str(P),'exec'),scope)
try:
    scope['actual_function_scope_replay']()
    report['cases']['bootstrap_error_actual_local_scope']={'outcome':'returned'}
except Exception as e:
    report['cases']['bootstrap_error_actual_local_scope']={'outcome':'exception','type':type(e).__name__,'message':str(e)}
report['note']='The rejection counterexamples are internally contradictory scripted evidence to test the verifier. They do not claim the current correct Worker spontaneously generates these rows. The bootstrap failure is a real reachable control-flow case.'
out=Path('/tmp/review_w2_driver_64/driver_final_predicate_review_v1.json');out.write_text(json.dumps(report,indent=2)+'\n');print(out.read_text())
