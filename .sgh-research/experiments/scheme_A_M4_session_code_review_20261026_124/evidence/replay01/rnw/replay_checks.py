import pathlib, hashlib, json, subprocess, shutil, tempfile, os
B=pathlib.Path('/home/trevor/USV/.sgh-research/experiments');OUT=pathlib.Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_session_code_review_20261026_124/evidence/replay01/rnw')
def h(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
P117=B/'scheme_A_M4_rnw_s1_pure_20261025_117';P118=B/'scheme_A_M4_rnw_s2_b2_20261025_118';P119=B/'scheme_A_M4_rnw_s4_owned_20261025_119'
reg=json.loads((P119/'implementation/T2A_RNW3_registration.json').read_text());registry=json.loads((P119/'implementation/s4_registry.json').read_text())
pins=[]
for label,p,sha in [('registry',reg['registry'],reg['registry_sha256']),('audit',reg['audit_tool']['path'],reg['audit_tool']['sha256']),('table',reg['action_table'],reg['action_table_sha256']),('driver',registry['driver'],registry['driver_tool_sha256'])]:pins.append({'label':label,'path':p,'match':h(p)==sha})
for key in ('regulator','worker','fixture'):
 pins.append({'label':key+'_source','match':h(registry[key+'_source'])==registry[key+'_source_sha256']})
for role,r in registry['roles'].items():
 pins.append({'label':role+'_elf','match':h(r['binary'])==r['binary_sha256']})
 pins.append({'label':role+'_bundle','match':h(r['source_bundle']['path'])==r['source_bundle']['sha256']})
bundle=json.loads(pathlib.Path(registry['roles']['fixture']['source_bundle']['path']).read_text())
# Bundle shapes differ by lineage: inspect supported lists rather than guessing silent success.
print('BUNDLE_KEYS',list(bundle) if isinstance(bundle,dict) else type(bundle).__name__)
# S1 selftest in a private copy, preserving originals.
with tempfile.TemporaryDirectory(prefix='rnw_review_',dir='/tmp') as td:
 d=pathlib.Path(td);shutil.copytree(P117/'implementation',d/'implementation',ignore=shutil.ignore_patterns('__pycache__','fixtures'));(d/'postrun').mkdir()
 s1=subprocess.run(['python3','-B',str(d/'implementation/test_s1_pure.py')],cwd=d,capture_output=True,text=True,timeout=30)
 (OUT/'s1_replay_stdout.txt').write_text(s1.stdout);(OUT/'s1_replay_stderr.txt').write_text(s1.stderr)
 s1res=json.loads((d/'postrun/s1_acceptance_v1.json').read_text())
 (OUT/'s1_replay_result.json').write_text(json.dumps(s1res,indent=2))
# S2 native suite does not initialize ROS (test only helper).
s2reg=json.loads((P118/'implementation/s2_registry.json').read_text());out=OUT/'s2_native_result'
if out.exists():raise SystemExit('Fresh private S2 output required')
s2=subprocess.run([s2reg['test_binary'],str(out)],capture_output=True,text=True,timeout=30)
(OUT/'s2_replay_stdout.txt').write_text(s2.stdout);(OUT/'s2_replay_stderr.txt').write_text(s2.stderr)
summary={'pins':pins,'all_selected_pins_match':all(p['match'] for p in pins),'S1':{'rc':s1.returncode,'passed':s1res['passed'],'total':s1res['total']},'S2':{'rc':s2.returncode,'stdout':s2.stdout,'stderr':s2.stderr,'result':json.loads((out/'result.json').read_text())}}
(OUT/'replay_results.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({**summary,'S2':{'rc':s2.returncode,'assertion_count':summary['S2']['result']['assertion_count'],'passed':summary['S2']['result']['passed']}},indent=2))
