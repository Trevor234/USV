#!/usr/bin/env python3
"""Fresh pinned five-role C3.4 build. No install, codegen, or node launch."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
from build_c33_v9 import SETUP

N = Path(__file__).resolve().parent
TARGETS = {'publisher':'p1_F5_held_publisher', 'observer':'p1_regulator_shadow_observer_owned_v2',
           'worker':'p1_solver_worker_owned_v2', 'fixture':'p1_synthetic_source', 'recorder':'p1_owned_recorder'}

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def dump(p,v):
    with Path(p).open('x') as f: json.dump(v,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n')

def verify(pin,role):
    assert sha(pin['path'])==pin['sha256']
    b=json.loads(Path(pin['path']).read_text()); assert b['role']==role and len(b['files'])==pin['files']
    for item in b['files'].values():
        assert Path(item['path']).is_absolute()
        assert Path(item['path']).stat().st_size==item['bytes'] and sha(item['path'])==item['sha256']
    return b

def parent_verify():
    pins=json.loads((N/'parent_N9_source_bundles_current.json').read_text())
    builds=json.loads((N/'parent_N9_build_manifest_current.json').read_text())
    for b in builds:
        verify(pins[b['role']],b['role']); assert b['passed'] is True and sha(b['binary'])==b['binary_sha256']

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--role',choices=TARGETS,required=True)
    ap.add_argument('--output',type=Path,required=True); ap.add_argument('--build-dir',type=Path,required=True)
    a=ap.parse_args(); assert a.output.is_absolute() and a.build_dir.is_relative_to(N/a.role)
    assert not a.build_dir.exists(); a.output.mkdir(parents=True,exist_ok=False)
    r={'schema':'p1-C3.4-build/v1','role':a.role,'author_directory':str(N),'passed':False,
       'node_launch_performed':False,'install_performed':False,'codegen_performed':False,
       'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    start=time.monotonic()
    try:
        pin=json.loads((N/'source_bundles_current.json').read_text())[a.role]; bundle=verify(pin,a.role)
        assert all(Path(x['path']).is_relative_to(N) for x in bundle['files'].values())
        parent_verify(); r['source_bundle']=pin
        for p in [Path(__file__),Path(pin['path']),N/'parent_N9_source_bundles_current.json',N/'parent_N9_build_manifest_current.json']:
            (a.output/(p.name+'.snapshot')).open('xb').write(p.read_bytes())
        configure=['cmake','-S',str(N/a.role),'-B',str(a.build_dir),'-DCMAKE_BUILD_TYPE=Release',
                   '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DPython3_EXECUTABLE=/usr/bin/python3']
        if a.role=='publisher':
            configure += ['-DP1_D1_SOURCE_BUNDLE_SHA256='+pin['sha256'],
              '-DP1_F5_SOURCE_PACKAGE=/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp',
              '-DP1_ACADOS_DIR=/home/trevor/acados','-DP1_CASADI_PACKAGE_DIR=/home/trevor/.local/lib/python3.12/site-packages/casadi','-DP1_CASADI_OLD_ABI=ON']
        else: configure += ['-DP1_OWNED_SOURCE_BUNDLE_SHA256='+pin['sha256']]
        commands=[('configure',configure,60),('runtime_build',['cmake','--build',str(a.build_dir),'--target',TARGETS[a.role],'-j2'],180)]
        if a.role=='publisher': tests=['test_publisher_startup']
        elif a.role=='observer':
            tests=['test_shadow_entry','test_enqueue_branch','test_d0_observation','test_atomic_observation','test_legacy_ready','test_c33_input_matrix']
            if (N/'observer/tests/test_c34_lease_matrix.cpp').exists(): tests.append('test_c34_lease_matrix')
            # The retained original wire prototype has a documented executor
            # API compile failure. Its corrected, separately pinned component
            # is built by scheme_A_C3_4_20261013_09/build_wire_revision.py.
        else: tests=[]
        for test in tests:
            commands.append(('native_build_'+test,['cmake','--build',str(a.build_dir),'--target',test,'-j2'],180))
        for name,cmd,budget in commands:
            script=a.output/(name+'.sh'); script.open('x').write('set -e\n'+SETUP+'exec timeout --signal=TERM --kill-after=10s '+str(budget)+'s '+shlex.join(cmd)+'\n')
            with (a.output/(name+'.log')).open('xb') as log:
                rc=subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=budget+15).returncode
            r[name+'_rc']=rc
            if rc: raise RuntimeError(name+' failed: '+str(rc))
        verify(pin,a.role); parent_verify()
        binary=a.build_dir/TARGETS[a.role]
        r.update(passed=True,configure_rc=0,build_rc=0,binary=str(binary),binary_sha256=sha(binary),parent_roles_verified_unchanged=True,
                 native_binaries={t:{'path':str(a.build_dir/t),'sha256':sha(a.build_dir/t)} for t in tests})
        if tests:
            r['native_binary']=str(a.build_dir/tests[0]); r['native_binary_sha256']=sha(a.build_dir/tests[0])
    except Exception as e: r['error']=repr(e)
    r['elapsed_seconds']=time.monotonic()-start; dump(a.output/'result.json',r); print(json.dumps(r,sort_keys=True))
    return 0 if r['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
