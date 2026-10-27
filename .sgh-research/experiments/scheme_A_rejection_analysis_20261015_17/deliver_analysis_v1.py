#!/usr/bin/env python3
"""Create-only read-only-analysis archive, complete SHA readback."""
from pathlib import Path
import hashlib,json,os,stat
D=Path(__file__).resolve().parent;M=Path('/home/trevor/MPC')/D.name
sha=lambda b:hashlib.sha256(b).hexdigest()
def write(p,raw):
 assert not any(x.is_symlink() for x in p.parents)
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 assert p.read_bytes()==raw
def js(p,x):write(p,(json.dumps(x,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode())
q=json.loads((D/'evidence/analysis_QA_v1.json').read_text());assert q['passed']
a=json.loads((D/'evidence/rejection_audit_v1.json').read_text());pins={**a['source_inputs_before_sha256'],**q['source_code_document_pins']}
assert all(sha(Path(p).read_bytes())==v for p,v in pins.items())
assert not M.exists();files=sorted(p for p in D.rglob('*') if p.is_file());assert all(stat.S_ISREG(p.lstat().st_mode) for p in files)
rows=[{'relative_path':str(p.relative_to(D)),'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in files]
inv={'schema':'SchemeA-analysis-inventory/v1','source':str(D),'destination':str(M),'files':rows,'old_sources_unchanged':True,'new_ROS_run':False,'stage_qualified':False,'research_conclusion':False};js(D/'archive_inventory_v1.json',inv)
M.mkdir()
for p in sorted(D.rglob('*')):
 if p.is_dir():(M/p.relative_to(D)).mkdir(exist_ok=True)
for row in rows:
 rel=row['relative_path'];raw=(D/rel).read_bytes();assert sha(raw)==row['sha256'];write(M/rel,raw)
write(M/'archive_inventory_v1.json',(D/'archive_inventory_v1.json').read_bytes())
for row in rows:
 for root in [D,M]:assert sha((root/row['relative_path']).read_bytes())==row['sha256']
assert all(sha(Path(p).read_bytes())==v for p,v in pins.items())
result={'schema':'SchemeA-analysis-delivery/v1','passed':True,'full_second_SHA_readback':True,'final_files_per_root':len(rows)+2,'inventory_sha256':sha((D/'archive_inventory_v1.json').read_bytes()),'old_sources_before_after_unchanged':True,'source_inputs_count':len(pins),'read_only_analysis':True,'new_ROS_run':False,'stage_qualified':False,'research_conclusion':False}
for root in [D,M]:js(root/'delivery_verification.json',result)
assert (D/'delivery_verification.json').read_bytes()==(M/'delivery_verification.json').read_bytes()
assert sum(p.is_file() for p in M.rglob('*'))==result['final_files_per_root']
print(json.dumps(result,ensure_ascii=False))
