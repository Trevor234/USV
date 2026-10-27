import copy, importlib.util, json, pathlib, sys
B=pathlib.Path('/home/trevor/USV/.sgh-research/experiments')
P=B/'scheme_A_M4_rnw_s4_owned_20261025_119/implementation'
sys.path.insert(0,str(P/'t2_author'))
spec=importlib.util.spec_from_file_location('actual_adm',P/'t2_author/t2b_gen_admission.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
spec=importlib.util.spec_from_file_location('pure_adm',B/'scheme_A_M4_rnw_s1_pure_20261025_117/implementation/rnw_admission_v2.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
base=json.loads((P/'T2A_RNW3_table.json').read_text());ctx={k:base[k] for k in ('run_id','case','contract_sha256')}
res=[]
for name,mutation in [('valid',lambda t:None),('clauses_all_false',lambda t:t.__setitem__('clauses',{k:False for k in t['clauses']})),('missing_hold',lambda t:t['actions'].pop(0)),('resume_before_hold',lambda t:t['actions'].__setitem__(slice(0,2),list(reversed(t['actions'][:2]))))]:
 t=copy.deepcopy(base);mutation(t)
 try:a.validate_table(t,ctx);status='accepted'
 except AssertionError as e:status='AssertionError: '+str(e)
 res.append({'case':name,'actual_owned_admission':status,'pure_S1_rejections':p.validate_table(t,ctx)})
print(json.dumps(res,indent=2));pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_session_code_review_20261026_124/evidence/replay01/rnw/admission_probe_results.json').write_text(json.dumps(res,indent=2))
