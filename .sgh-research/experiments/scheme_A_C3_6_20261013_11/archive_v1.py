#!/usr/bin/env python3
"""Fresh batch11 archive only; pinned inventory and complete SHA readback."""
import argparse,importlib.util,json,os,pathlib,stat,sys
D=pathlib.Path(__file__).resolve().parent
M=pathlib.Path('/home/trevor/MPC/scheme_A_C3_6_20261013_11')
P=D.parent/'scheme_A_C3_5_20261013_10'
sys.path.insert(0,str(D.parent/'p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11'))
import acceptance_core_v1 as C
def write_new(path,raw,mode=0o644):
 C.require(not any(p.is_symlink() for p in path.parents),'archive_symlink_parent')
 with path.open('xb') as f:f.write(raw);os.fchmod(f.fileno(),mode&0o777);f.flush();os.fsync(f.fileno())
 C.require(C.Reader().raw(path)==raw,'create_only_readback')
def write_json(path,x):write_new(path,(json.dumps(x,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode())
def protect():
 q=C.Reader().json(D/'postrun/final_QA_current.json')
 r=C.Reader(seconds=300,max_bytes=768*1024*1024,max_files=6000)
 for path,sha in q['fixed_source_header_input_hashes'].items():C.require(C.digest(r.raw(path))==sha,'protected_input_changed:'+path)
 s=importlib.util.spec_from_file_location('parent_protection',P/'archive_to_MPC_v1.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 proof=m.protected();C.require(proof==q['parent_after'],'parent_protection_changed')
 return {'passed':True,'parent':proof,'current_fixed_paths':len(q['fixed_source_header_input_hashes']),'new_frozen_pairs':q['new_frozen_pairs'],'current_QA_sha256':C.digest(C.Reader().raw(D/'postrun/final_QA_current.json'))}
def population():
 files=[];directories=[]
 for root,dirs,names in os.walk(D,followlinks=False):
  for name in dirs:
   p=pathlib.Path(root)/name;C.require(stat.S_ISDIR(p.lstat().st_mode),'directory_link_or_special');directories.append(str(p.relative_to(D)))
  for name in names:
   p=pathlib.Path(root)/name;C.require(stat.S_ISREG(p.lstat().st_mode),'archive_regular_only');files.append(p)
 return sorted(files),sorted(directories,key=lambda x:(len(pathlib.Path(x).parts),x))
def prepare():
 C.require(not M.exists() and not M.is_symlink(),'fresh_MPC_batch_required');proof=protect()
 files,dirs=population();r=C.Reader(seconds=120,max_bytes=256*1024*1024,max_files=2000)
 pins=[]
 for p in files:
  raw=r.raw(p);pins.append({'relative_path':str(p.relative_to(D)),'sha256':C.digest(raw),'bytes':len(raw),'mode':stat.S_IMODE(p.lstat().st_mode)})
 C.require(r.unchanged(),'prepare_sources_changed')
 inventory={'schema':'p1-C3.6-A-archive-inventory/v1','source':str(D),'destination':str(M),'files':pins,'directories':dirs,'inventory_self_excluded':True,'protection':proof,'old_batches_overwritten':False}
 write_json(D/'archive_inventory_v1.json',inventory)
 print(json.dumps({'prepared':True,'files_excluding_inventory':len(pins),'bytes':sum(p['bytes'] for p in pins),'inventory_sha256':C.digest(C.Reader().raw(D/'archive_inventory_v1.json'))}))
def deliver(sha):
 C.require(D.name=='scheme_A_C3_6_20261013_11' and not M.exists() and not M.is_symlink() and M.parent.is_dir(),'fixed_fresh_destination')
 C.require(not any(p.is_symlink() for p in M.parents),'MPC_parent_link')
 raw=C.Reader().raw(D/'archive_inventory_v1.json');C.require(C.digest(raw)==sha,'archive_inventory_identity');x=C.strict_json(raw)
 C.require(x['source']==str(D) and x['destination']==str(M),'fixed_archive_scope')
 before=protect();files,_=population();C.require({str(p.relative_to(D)) for p in files}=={p['relative_path'] for p in x['files']}|{'archive_inventory_v1.json'},'source_population_changed')
 M.mkdir(exist_ok=False)
 for directory in x['directories']:
  p=pathlib.Path(directory);C.require(not p.is_absolute() and '..' not in p.parts,'relative_directory');(M/p).mkdir(exist_ok=False)
 reader=C.Reader(seconds=300,max_bytes=256*1024*1024,max_files=2000)
 for pin in x['files']:
  p=pathlib.Path(pin['relative_path']);C.require(not p.is_absolute() and '..' not in p.parts,'relative_file')
  b=reader.verify({'path':str(D/p),'sha256':pin['sha256'],'bytes':pin['bytes']});write_new(M/p,b,pin['mode'])
 write_new(M/'archive_inventory_v1.json',raw)
 for pin in x['files']:
  for root in (D,M):reader.verify({'path':str(root/pin['relative_path']),'sha256':pin['sha256'],'bytes':pin['bytes']})
 C.require(C.Reader().raw(D/'archive_inventory_v1.json')==C.Reader().raw(M/'archive_inventory_v1.json')==raw,'inventory_copy')
 after=protect();C.require(before==after,'protection_before_after')
 verification={'schema':'p1-C3.6-A-delivery-verification/v1','passed':True,'source':str(D),'destination':str(M),'inventory_sha256':sha,'copied_regular_files':len(x['files'])+1,'copied_bytes':sum(p['bytes'] for p in x['files'])+len(raw),'full_second_SHA_readback':True,'protected_before':before,'protected_after':after,'metadata_supplements':['delivery_verification.json','batch_status_final.json'],'final_regular_files_per_root':len(x['files'])+3,'old_batches_overwritten':False,'old_expected_updated':False,'old_failure_deleted':False}
 status=C.Reader().json(D/'batch_status_prepared.json');status.update(delivery_verified=True,state='finite_component_complete_archive_verified',delivery_verification=str(M/'delivery_verification.json'))
 for root in (D,M):write_json(root/'delivery_verification.json',verification);write_json(root/'batch_status_final.json',status)
 for name in verification['metadata_supplements']:C.require(C.Reader().raw(D/name)==C.Reader().raw(M/name),'metadata_pair_readback')
 C.require(len(population()[0])==verification['final_regular_files_per_root'] and sum(p.is_file() for p in M.rglob('*'))==verification['final_regular_files_per_root'],'final_population')
 print(json.dumps(verification,ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=('prepare','deliver'));a.add_argument('--sha');args=a.parse_args()
 if args.mode=='prepare':prepare()
 else:C.require(type(args.sha) is str and len(args.sha)==64,'inventory_SHA_required');deliver(args.sha)
