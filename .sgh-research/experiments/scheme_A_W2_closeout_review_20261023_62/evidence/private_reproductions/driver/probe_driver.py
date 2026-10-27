import ast, copy, hashlib, json
from pathlib import Path
SRC=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_fix_review_20261022_61/implementation/w2_author/owned_m4_diagnostic_driver_v1.py')
src=SRC.read_text();tree=ast.parse(src);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');runtry=next(n for n in main.body if isinstance(n,ast.Try));final=runtry.finalbody
start=next(i for i,n in enumerate(final) if isinstance(n,ast.FunctionDef) and n.name=='rc_is')
branch=next(n for n in final if isinstance(n,ast.If) and getattr(n,'lineno',0)==716)
# Execute exact current helpers + common + W2 final branch; no main, spawn, signals or IO.
module=ast.Module(body=final[start:start+3]+[branch],type_ignores=[]);code=compile(module,str(SRC),'exec')
base_rows=[{'role':'regulator','returncode':0,'signals':[],'group_empty':True},{'role':'worker','returncode':2,'signals':[{'signal':'SIGINT'}],'group_empty':True},{'role':'fixture','returncode':0,'signals':[{'signal':'SIGINT'}],'group_empty':True},{'role':'recorder','returncode':0,'signals':[{'signal':'SIGINT'}],'group_empty':True}]
base_result={'W2_observed':True,'w2_boundary_entered':True,'w2_release_sent':True,'w2_entered_row':{'job_id':2,'ordinal':1,'entered_ns':1_000_000_000},'w2_ticks_after_enter':[3,4],'w2_result':{'disposition':'expired','actual_native_invoked':False,'job_id':2,'ordinal':1,'released':True,'guard_checked_ns':1_500_000_000},'ramp_ok':True,'transition_ns':None,'transition_reason':None,'watchdog_ns':None}
base_reg={'expected':{'w2_exit_codes':{'worker':2},'w2_isolation_reason':'fatal_capability'}}
cases={}
for name in ['baseline','worker_SIGTERM','worker_no_signal','transition_before_boundary_entry','watchdog_during_hold','recorded_error','bad_fixture_return','nonempty_worker_group']:
 rows=copy.deepcopy(base_rows);res=copy.deepcopy(base_result);reg=copy.deepcopy(base_reg)
 if name=='worker_SIGTERM':rows[1]['signals']=[{'signal':'SIGINT'},{'signal':'SIGTERM'}]
 if name=='worker_no_signal':rows[1]['signals']=[]
 if name=='transition_before_boundary_entry':res.update(transition_ns=900_000_000,transition_reason='fatal_capability')
 if name=='watchdog_during_hold':res.update(watchdog_ns=1_200_000_000)
 if name=='recorded_error':res['error']='existing failure'
 if name=='bad_fixture_return':rows[2]['returncode']=99
 if name=='nonempty_worker_group':rows[1]['group_empty']=False
 scope={'case':'W2-native-boundary-hold','reg':reg,'w2':{'job_id':2,'ordinal':1,'ticks_before_release':2},'result':res,'closed':rows,'by_role':{r['role']:r for r in rows}}
 exec(code,scope);cases[name]={'passed':res['passed'],'closed':rows,'result':res}
# Replay only exact FD cleanup nodes inside a local with the same try-local declaration:
# failure before line280 has assigned any values leaves the names unbound.
fdloop=next(n for n in final if isinstance(n,ast.For) and getattr(n,'lineno',0)==699)
assign=next(n for n in runtry.body if isinstance(n,ast.Assign) and getattr(n,'lineno',0)==280)
fn=ast.FunctionDef(name='early_failure_cleanup',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=[ast.Try(body=[ast.Raise(exc=ast.Call(func=ast.Name(id='RuntimeError',ctx=ast.Load()),args=[ast.Constant('fixture startup failure')],keywords=[]),cause=None),copy.deepcopy(assign)],handlers=[ast.ExceptHandler(type=ast.Name(id='Exception',ctx=ast.Load()),name=None,body=[ast.Pass()])],orelse=[],finalbody=[copy.deepcopy(fdloop)])],decorator_list=[])
m=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));scope={'os':__import__('os')};exec(compile(m,str(SRC),'exec'),scope)
try:scope['early_failure_cleanup']();early={'outcome':'completed'}
except Exception as e:early={'exception':type(e).__name__,'message':str(e)}
report={'source':str(SRC),'sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'cases':cases,'early_failure_fd_cleanup':early,'scope':'Exact source AST subsets; no main, ROS, spawn, signal or hardware calls.'}
Path('/tmp/w2_v62_driver_review/driver_probe_results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'case_acceptance':{k:v['passed'] for k,v in cases.items()},'early_failure_fd_cleanup':early},indent=2))
