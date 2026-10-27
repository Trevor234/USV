import ast,copy,hashlib,json,pathlib
source_path=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_fix_review_20261022_61/implementation/w2_author/owned_m4_diagnostic_driver_v1.py')
source=source_path.read_text()
root=ast.parse(source)
branch=next(n for n in ast.walk(root) if isinstance(n,ast.If) and n.lineno==716)
code=compile(ast.Module(body=branch.body,type_ignores=[]),str(source_path),'exec')
w2={'job_id':2,'ordinal':1,'ticks_before_release':2}
base_result={'W2_observed':True,'w2_boundary_entered':True,'w2_release_sent':True,'w2_result':{'disposition':'expired','actual_native_invoked':False,'job_id':2,'ordinal':1},'w2_entered_row':{'job_id':2,'ordinal':1},'w2_ticks_after_enter':[3,4],'transition_ns':None,'ramp_ok':True}
base_closed=[{'role':role,'returncode':2 if role=='worker' else 0,'signals':[] if role=='regulator' else [{'signal':'SIGINT'}],'group_empty':True} for role in ['regulator','worker','fixture','recorder']]

def probe(name,change=None):
    result=copy.deepcopy(base_result);closed=copy.deepcopy(base_closed)
    reg={'expected':{'w2_exit_codes':{'worker':2},'w2_isolation_reason':'fatal_capability'}}
    if change:change(result,closed,reg)
    by_role={r['role']:r for r in closed}
    scope={'case':'W2-native-boundary-hold','reg':reg,'result':result,'closed':closed,'by_role':by_role,'w2':w2,'rc_is':lambda role,value:by_role.get(role,{}).get('returncode')==value,'only_int':lambda role:[s['signal'] for s in by_role.get(role,{}).get('signals',[])]==['SIGINT']}
    try:exec(code,scope);out={'passed':result.get('passed')}
    except Exception as exc:out={'exception':type(exc).__name__,'message':str(exc)}
    return {'name':name,**out,'closed':closed,'result':result,'reg':reg}
report={'source':str(source_path),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'extracted_lines':[branch.lineno,branch.body[-1].end_lineno], 'note':'Replay only the actual submitted final W2 predicate with supplied locals; no ROS/processes/owned run', 'cases':[]}
report['cases'].append(probe('baseline'))
report['cases'].append(probe('worker_SIGTERM',lambda r,c,g:c[1].update(signals=[{'signal':'SIGINT'},{'signal':'SIGTERM'}])))
report['cases'].append(probe('worker_no_SIGINT',lambda r,c,g:c[1].update(signals=[])))
report['cases'].append(probe('fixture_SIGTERM',lambda r,c,g:c[2].update(signals=[{'signal':'SIGTERM'}])))
report['cases'].append(probe('recorded_error',lambda r,c,g:r.update(error='failure')))
report['cases'].append(probe('worker_closing_error',lambda r,c,g:c[1].update(error='failure')))
report['cases'].append(probe('watchdog_row_without_transition',lambda r,c,g:r.update(watchdog_ns=123)))
report['cases'].append(probe('missing_expected_worker',lambda r,c,g:g['expected']['w2_exit_codes'].pop('worker')))
pathlib.Path('/tmp/w2_v62_tests_review/final_driver_probe_v1.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({c['name']:{k:v for k,v in c.items() if k in ['passed','exception','message']} for c in report['cases']},ensure_ascii=False,indent=2))
