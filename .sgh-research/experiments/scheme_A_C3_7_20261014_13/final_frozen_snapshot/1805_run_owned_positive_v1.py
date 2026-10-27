#!/usr/bin/env python3
"""One preregistered fresh owned4s C3.7 shadow fixture, no execute."""
from pathlib import Path
import hashlib,json
import build_and_verify_v2 as B
D,N=B.D,B.N
OUT=D/'runs/positive01'
R=N/'runs/owned_C37_positive_01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 assert not R.exists() and not OUT.exists();OUT.mkdir()
 for p,x in json.loads((D/'preregister/helper_pins_v1.json').read_text())['files'].items():assert sha(p)==x['sha256'],p
 build=json.loads((N/'build_manifest_current.json').read_text());assert len(build)==5
 for x in build:assert x['passed'] and sha(x['binary'])==x['binary_sha256']
 B.verify(json.loads((N/'source_bundles_current.json').read_text())['observer'])
 native=json.loads((D/'component/native_current_assessment.json').read_text());assert native['passed']
 args=['/usr/bin/python3','-B',str(N/'prepare_fixture.py'),'--run-id',R.name,'--domain','132','--mode','positive']
 rc=B.command(OUT,'run_owned',args,75,132)
 B.write(OUT/'invocation.json',{'schema':'C3.7-owned-positive-invocation/v1','run_dir':str(R),'driver_returncode':rc,'command':args,'domain':132,'measurement_seconds':4,'client_date':'2026-10-14','normal_hooks':0,'witness_profile':'closed_shadow_observation','runtime_contract_changed':False,'stage_qualified':False})
 print(json.dumps({'driver_returncode':rc,'run_dir':str(R)}));return rc
if __name__=='__main__':raise SystemExit(main())
