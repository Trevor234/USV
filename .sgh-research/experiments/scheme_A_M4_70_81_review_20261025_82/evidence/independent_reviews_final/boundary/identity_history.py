#!/usr/bin/env python3
"""Read-only hashes/existence in batches 77-81; no ownership/time inference."""
import pathlib,json,hashlib,collections
base=pathlib.Path('/home/trevor/USV/.sgh-research/experiments')
B={n:next(base.glob('*_'+str(n))) for n in range(77,82)}
b78=B[78];rundir=b78/'implementation/runs';author=b78/'implementation/t2_author_r3';r4=B[80]/'implementation/t2_author_r4'
cache={}
def sha(p):
 p=pathlib.Path(p)
 if not p.is_file():return None
 k=str(p)
 if k not in cache:cache[k]=hashlib.sha256(p.read_bytes()).hexdigest()
 return cache[k]
def load(p):return json.loads(pathlib.Path(p).read_bytes())
def cmp(p,expected):return {'path':str(p),'exists':pathlib.Path(p).is_file(),'expected_sha256':expected,'actual_sha256':sha(p),'matches':sha(p)==expected if expected else None}
registry_path=b78/'implementation/t2_registry_v11.json';registry=load(registry_path)
bundle_path=pathlib.Path(registry['roles']['worker']['source_bundle']['path']);bundle=load(bundle_path)
freeze_path=b78/'evidence/freeze_rev11/freeze_rev11_report_v1.json';freeze=load(freeze_path)
# Search exact matches only in declared bounded scope: nonbuild ordinary files in 77-81,
# plus current registered ELFs. This is not a global search for recoverable files.
index=collections.defaultdict(list);file_count=0
for b in B.values():
 for p in b.rglob('*'):
  if not p.is_file() or any(x in {'build','CMakeFiles','cmake_build','__pycache__'} or x.startswith('build_') for x in p.relative_to(b).parts):continue
  h=sha(p);index[h].append(str(p));file_count+=1
for role,row in registry['roles'].items():
 p=pathlib.Path(row['binary']);h=sha(p)
 if h:index[h].append(str(p))
def matches(h):return index.get(h,[])
actual={'registry':cmp(registry_path,sha(registry_path)),'bundle':cmp(bundle_path,registry['roles']['worker']['source_bundle']['sha256']),'driver':cmp(registry['driver'],registry['driver_tool_sha256']),'roles':{k:cmp(v['binary'],v['binary_sha256']) for k,v in registry['roles'].items()},'bundle_files':[]}
for rel,row in bundle['files'].items():actual['bundle_files'].append({'relative':rel,**cmp(row['path'],row['sha256']),'exact_copy_in_r4':cmp(r4/rel,row['sha256'])})
report={'report_path':str(freeze_path),'report_bundle':cmp(freeze['bundle']['path'],freeze['bundle']['sha256']),'report_driver':cmp(registry['driver'],freeze['driver_tool_sha256']),'report_roles':{k:cmp(registry['roles'][k]['binary'],v) for k,v in freeze['roles'].items()}}
registrations=[]
for n,b in B.items():
 for p in b.rglob('*registration*.json'):
  if '/runs/' in str(p) or '/build/' in str(p):continue
  try:x=load(p)
  except:continue
  if not isinstance(x,dict) or 'registry_sha256' not in x:continue
  rawp=pathlib.Path(x['registry']);resolved=rawp if rawp.is_absolute() else b/rawp
  audit=x.get('audit_tool',{});ap=pathlib.Path(audit['path']) if audit.get('path') else None
  if ap and not ap.is_absolute():ap=b/ap
  registrations.append({'batch':n,'path':str(p),'sha256':sha(p),'run_id':x.get('run_id'),'output':x.get('output'),'registry':cmp(resolved,x['registry_sha256']),'audit':cmp(ap,audit.get('sha256')) if ap else None})
reg_by_sha={x['sha256']:x for x in registrations}
runs=[]
for r in sorted(rundir.iterdir()):
 if not r.is_dir():continue
 p=r/'driver_manifest.json'
 if not p.exists():runs.append({'run':r.name,'driver_manifest_exists':False});continue
 x=load(p)
 roles={}
 for role,rel in [('fixture','fixture/owned_manifest.json'),('worker','worker/manifest.json'),('regulator','regulator/manifest.json'),('recorder','recorder/manifest.json')]:
  mp=r/rel
  if not mp.is_file():roles[role]={'manifest_exists':False};continue
  m=load(mp);bs=m.get('source_bundle_sha256')
  roles[role]={'manifest_exists':True,'manifest_path':str(mp),'binary':cmp(m['exe'],m.get('binary_sha256')),'source_bundle_sha256':bs,'matches_current_registered_role_bundle':bs==registry['roles'][role]['source_bundle']['sha256'],'exact_bundle_files_in_bounded_search':matches(bs)}
 runs.append({'run':r.name,'driver_manifest_exists':True,'manifest_path':str(p),'contract_sha256':x.get('contract_sha256'),'registration_sha256':x.get('registration_sha256'),'registration_exact_file_in_inventory':reg_by_sha.get(x.get('registration_sha256'),{}).get('path'),'registry_sha256':x.get('registry_sha256'),'registry_matches_current':x.get('registry_sha256')==sha(registry_path),'exact_registry_files_in_bounded_search':matches(x.get('registry_sha256')),'driver':cmp(x['tool_path'],x.get('tool_sha256')),'driver_exact_files_in_r4':[z for z in matches(x.get('tool_sha256')) if z.startswith(str(r4))],'roles':roles})
out={'scope':{'batch_directories':{str(k):str(v) for k,v in B.items()},'hash_search_nonbuild_file_count':file_count,'search_limits':'nonbuild ordinary files under batches77-81 plus current registry ELFs; not a global restoration search','interpretation':'only exact SHA/existence comparisons; no actor/intent attribution'},'current':actual,'freeze_report_vs_current':report,'registrations':registrations,'runs':runs}
pathlib.Path('/tmp/review81_boundary/identity_history_v1.json').write_text(json.dumps(out,indent=2))
summary={'freeze_report_bundle_matches_current':report['report_bundle']['matches'],'freeze_report_driver_matches_current':report['report_driver']['matches'],'freeze_report_roles_match':{k:v['matches'] for k,v in report['report_roles'].items()},'current_bundle_bad_files':[x['relative'] for x in actual['bundle_files'] if not x['matches']],'r4_copies_matching_current_bundle_file_count':sum(x['exact_copy_in_r4']['matches'] is True for x in actual['bundle_files']),'run_matrix':[{'run':x['run'],'registry_current':x.get('registry_matches_current'),'registration_exact_file':x.get('registration_exact_file_in_inventory'),'driver_current':x.get('driver',{}).get('matches'),'role_ELF_current':{k:v.get('binary',{}).get('matches') for k,v in x.get('roles',{}).items()},'role_bundles_current':{k:v.get('matches_current_registered_role_bundle') for k,v in x.get('roles',{}).items()}} for x in runs]}
pathlib.Path('/tmp/review81_boundary/identity_history_summary_v1.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
