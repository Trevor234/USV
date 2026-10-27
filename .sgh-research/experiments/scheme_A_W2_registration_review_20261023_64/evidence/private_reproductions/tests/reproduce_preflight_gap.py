import ast,contextlib,copy,hashlib,io,json
from pathlib import Path
root=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_registration_20261023_63')
script=root/'implementation/replay_driver_preflight.py'
driver=root/'implementation/w2_author/owned_m4_diagnostic_driver_v1.py'
out=Path('/tmp/w2_review64_tests')
ns={'__name__':'review_only','__file__':str(script)}
exec(compile(script.read_text(),str(script),'exec'),ns)
real_read=ns['read']; reg=real_read(root/'implementation/W2_registration_v1.json')
mut=copy.deepcopy(reg);mut['w2_release']['nonce']=0
ns['OUT']=out/'hand_copied_replay'
ns['read']=lambda p:copy.deepcopy(mut) if Path(p)==root/'implementation/W2_registration_v1.json' else real_read(p)
stdout=io.StringIO()
with contextlib.redirect_stdout(stdout): rc=ns['main']()
(out/'hand_copied_preflight.stdout.txt').write_text(stdout.getvalue())
report=json.loads((ns['OUT']/'preflight_replay_v1.json').read_text())
tree=ast.parse(driver.read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
checks=next(n for n in main.body if isinstance(n,ast.If) and n.lineno==273)
exact=ast.Module(body=[checks],type_ignores=[])
try:
 exec(compile(exact,str(driver),'exec'),{'case':mut['case'],'reg':mut,'w2':mut['w2_release']})
 actual={'outcome':'accepted'}
except AssertionError as e: actual={'outcome':'assertion_rejected','message':str(e)}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
summary={'schema':'W2-preflight-replay-scope-counterexample-v1','mutation':'w2_release.nonce=0','hand_copied_replay':{'returncode':rc,'all_passed':report['all_passed'],'steps':len(report['steps'])},'actual_driver_w2_preflight':actual,'script_sha256':sha(script),'driver_sha256':sha(driver),'registration_sha256':sha(root/'implementation/W2_registration_v1.json'),'no_roles_started':True,'scope':'Executes only the actual Driver W2 registration precheck AST statement, plus the existing handwritten no-spawn replay with a read-only mutated registration object. Original files unchanged.'}
(out/'preflight_gap_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
