#!/usr/bin/env python3
"""Create-only, finite owned runtime/component build; no node launch/install/codegen."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

D=Path(__file__).resolve().parent
A=D/'author_r2'


def pin(p):
    p=Path(p).resolve(strict=True);data=p.read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def emit(p,value):
    with p.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')


def main():
    assert json.loads((D/'preflight/workspace_initial_v3.json').read_bytes())['passed']
    assert json.loads((D/'preflight/frozen47_verification_v1.json').read_bytes())['passed']
    assert 'verdict=GO' in (D/'preflight/preflight_reflection_v1.md').read_text()
    root=D/'build/m4_attempt02';root.mkdir(parents=True)
    rows={str(p.relative_to(A)):{'path':str(p),**pin(p)} for p in A.rglob('*') if p.is_file()}
    bundle=root/'source_bundle.json';emit(bundle,{'schema':'M4-owned-source-bundle/v1','files':rows,'physical_production_release':False})
    bundle_sha=pin(bundle)['sha256'];driver_sha=pin(A/'owned_m4_driver_v1.py')['sha256']
    setup_file=D.parent/'scheme_A_owned_business_start_20261020_39/author/build_c33_v9.py'
    tree=ast.parse(setup_file.read_bytes());setup=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SETUP' for t in n.targets))
    setup+='\nexport ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n'
    results=[]
    def run(name,command,budget):
        script=root/(name+'.sh');script.write_text('set -e\n'+setup+'\nexec timeout --signal=TERM --kill-after=5s '+str(budget)+'s '+shlex.join(command)+'\n')
        started=time.monotonic()
        with (root/(name+'.stdout.log')).open('xb') as out,(root/(name+'.stderr.log')).open('xb') as err:
            result=subprocess.run(['/bin/bash',str(script)],stdout=out,stderr=err,timeout=budget+10)
        row={'name':name,'command':command,'returncode':result.returncode,'elapsed_seconds':time.monotonic()-started,'script_sha256':pin(script)['sha256']}
        results.append(row);print(json.dumps(row),flush=True);return result.returncode
    cmake=root/'cmake_build'
    rc=run('configure',['cmake','-S',str(A),'-B',str(cmake),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG',
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DP1_OWNED_SOURCE_BUNDLE_SHA256='+bundle_sha,'-DP1_DRIVER_TOOL_SHA256='+driver_sha],120)
    selected={}
    targets=['p1_m4_regulator_owned','p1_m4_worker_owned','p1_m4_fixture_owned','test_m4_native_policy','test_m4_activation_alignment']
    if rc==0:
        for name in targets:
            rc=run('build_'+name,['cmake','--build',str(cmake),'--target',name,'-j1'],180)
            if rc:break
            selected[name]={'path':str(cmake/name),**pin(cmake/name)}
    after={str(p.relative_to(A)):pin(p) for p in A.rglob('*') if p.is_file()}
    same=all(after[k]=={x:r[x] for x in ['bytes','sha256']} for k,r in rows.items()) and set(after)==set(rows)
    dependencies={}
    for dep in cmake.rglob('*.o.d'):
        paths=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        for name in paths:
            p=Path(name).resolve(strict=True);dependencies[str(p)]=pin(p)
    result={'schema':'M4-owned-runtime-build/v1','passed':rc==0 and len(selected)==len(targets) and same,
            'source_bundle':{'path':str(bundle),'sha256':bundle_sha,'files':len(rows)},'driver_tool_sha256':driver_sha,
            'targets':selected,'commands':results,'source_before_after_equal':same,'compiler_dependencies':dependencies,
            'setup_helper':{'path':str(setup_file),**pin(setup_file)},'ROS_runs':0,'install_performed':False,'codegen_performed':False,
            'ordinary_production_release_enabled':False,'M4_qualified':False,'P1_qualified':False}
    emit(root/'build_manifest_v1.json',result)
    print(json.dumps({'passed':result['passed'],'built_targets':len(selected),'output':str(root)}))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
