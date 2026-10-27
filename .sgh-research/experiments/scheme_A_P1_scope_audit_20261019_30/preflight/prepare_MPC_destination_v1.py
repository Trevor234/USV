"""Prepare only this new batch's requested archive directory; never remount."""
from pathlib import Path
import json,subprocess,time
D=Path(__file__).resolve().parents[1]
M=Path('/home/trevor/MPC')/D.name
r=dict(schema='scheme-A-P1-scope-MPC-preparation/v1',requested_destination=str(M),checked_monotonic_ns=time.monotonic_ns(),passed=False,files_overwritten=False,mount_changed=False,stage_qualified=False)
try:
 try:M.mkdir();r['new_empty_directory_created']=True
 except FileExistsError:r['new_empty_directory_created']=False
 assert M.is_dir() and not M.is_symlink() and list(M.iterdir())==[],'new batch destination is not empty'
 r['passed']=True;r['empty_destination_ready']=True
except (OSError,AssertionError) as e:r.update(error=str(e),error_number=getattr(e,'errno',None),empty_destination_ready=False)
r['mount_observation']=subprocess.run(['findmnt','-T','/home/trevor/MPC','-o','TARGET,SOURCE,FSTYPE,OPTIONS'],capture_output=True,text=True,timeout=10).stdout
with (D/'preflight/MPC_delivery_preparation_v1.json').open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(r,ensure_ascii=False))
