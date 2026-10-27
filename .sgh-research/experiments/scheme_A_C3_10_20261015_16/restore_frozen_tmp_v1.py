#!/usr/bin/env python3
"""Restore missing reboot-cleared temporary historical artifacts from sealed exact copies."""
from pathlib import Path
import hashlib,json,os,stat,sys
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;R=D/'preflight/preservation_roster_v3.json';P=D.parent/'scheme_A_C3_7_20261014_13/final_frozen_snapshot/manifest.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads(R.read_text());assert sha(P)==r['files'][str(P)]['sha256'];m=json.loads(P.read_text());missing=[p for p in r['files'] if not Path(p).is_file()]
assert len(missing)==10 and all(Path(p).parent==Path('/tmp/p1-C34-lease-native') for p in missing)
records=[]
for name in missing:
 matches=[x for x in m['files'] if x['original']==name];assert len(matches)==1
 item=matches[0];source=Path(item['copy']);expected=r['files'][name];assert sha(source)==item['sha256']==expected['sha256'] and source.stat().st_size==item['bytes']==expected['bytes']
 target=Path(name);assert not target.exists() and not target.is_symlink() and not any(p.is_symlink() for p in target.parents)
 target.parent.mkdir(exist_ok=True);raw=source.read_bytes();fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,expected['mode'])
 with os.fdopen(fd,'wb') as f:f.write(raw);os.fchmod(f.fileno(),expected['mode']);f.flush();os.fsync(f.fileno())
 assert sha(target)==expected['sha256'] and target.stat().st_size==expected['bytes'] and stat.S_IMODE(target.stat().st_mode)==expected['mode']
 records.append({'original_missing':name,'restored_from':str(source),'sha256':expected['sha256'],'bytes':expected['bytes'],'mode':expected['mode']})
x={'schema':'C3.10-frozen-tmp-restoration/v1','passed':True,'restored_files':records,'source_manifest':str(P),'source_manifest_sha256':sha(P),'source_manifest_anchored_in_old_roster':True,'create_only':True,'old_archive_changed':False,'old_results_recomputed':False,'old_live_endpoint_authority_transferred':False,'stage_qualified':False,'research_conclusion':False}
with (D/'preflight/restored_frozen_tmp_v1.json').open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'passed':True,'restored_missing_files':len(records),'old_archive_changed':False}))
