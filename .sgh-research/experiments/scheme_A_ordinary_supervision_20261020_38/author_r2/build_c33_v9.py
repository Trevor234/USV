#!/usr/bin/env python3
"""Create-only isolated C3.3 build; no install or node launch."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

N = Path(__file__).resolve().parent
SETUP = '''export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
'''

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n')

def verify(pin, expected_role):
    path=Path(pin['path']); assert sha(path)==pin['sha256']
    bundle=json.loads(path.read_text()); assert bundle['role']==expected_role
    assert len(bundle['files'])==pin['files']
    for item in bundle['files'].values():
        source=Path(item['path']); assert source.is_absolute()
        assert source.stat().st_size==item['bytes'] and sha(source)==item['sha256']
    return bundle

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--role',choices=['publisher','observer'],required=True)
    ap.add_argument('--pin',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--build-dir',type=Path,required=True)
    a=ap.parse_args(); assert a.output.is_absolute() and a.build_dir.is_absolute()
    assert a.build_dir.is_relative_to(N/a.role)
    a.output.mkdir(parents=True,exist_ok=False)
    result={'schema':'p1-C3.3-build/v1','role':a.role,'author_directory':str(N),
            'passed':False,'node_launch_performed':False,'install_performed':False,
            'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    started=time.monotonic()
    try:
        pin=json.loads(a.pin.read_text()); bundle=verify(pin,a.role)
        assert all(Path(x['path']).is_relative_to(N) for x in bundle['files'].values())
        assert not a.build_dir.exists(),'fresh build directory required'
        parent=json.loads((N/'source_bundles_parent_v8.json').read_text())
        previous=json.loads((N/'build_manifest_parent_v8.json').read_text())
        parent_build_sha=sha(N/'build_manifest_parent_v8.json')
        for old in previous:
            verify(parent[old['role']],old['role'])
            assert old['passed'] and sha(old['binary'])==old['binary_sha256']
        for source in [Path(__file__),a.pin,Path(pin['path']),N/'source_bundles_parent_v8.json',N/'build_manifest_parent_v8.json']:
            with (a.output/(source.name+'.snapshot')).open('xb') as f:f.write(source.read_bytes())
        result['source_bundle']=pin; result['parent_build_manifest_sha256']=parent_build_sha
        target='p1_F5_held_publisher' if a.role=='publisher' else 'p1_regulator_shadow_observer_owned_v2'
        test='test_publisher_startup' if a.role=='publisher' else 'test_c33_input_matrix'
        configure=['cmake','-S',str(N/a.role),'-B',str(a.build_dir),
                   '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                   '-DPython3_EXECUTABLE=/usr/bin/python3']
        if a.role=='publisher':
            configure += ['-DP1_D1_SOURCE_BUNDLE_SHA256='+pin['sha256'],
                '-DP1_F5_SOURCE_PACKAGE=/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp',
                '-DP1_ACADOS_DIR=/home/trevor/acados',
                '-DP1_CASADI_PACKAGE_DIR=/home/trevor/.local/lib/python3.12/site-packages/casadi',
                '-DP1_CASADI_OLD_ABI=ON']
        else: configure += ['-DP1_OWNED_SOURCE_BUNDLE_SHA256='+pin['sha256']]
        commands=[('configure',configure,60),
                  ('runtime_build',['cmake','--build',str(a.build_dir),'--target',target,'-j2'],180),
                  ('native_build',['cmake','--build',str(a.build_dir),'--target',test,'-j2'],180)]
        for name,command,budget in commands:
            script=a.output/(name+'.sh')
            with script.open('x') as f:f.write('set -e\n'+SETUP+'exec timeout --signal=TERM --kill-after=10s '+str(budget)+'s '+shlex.join(command)+'\n')
            with (a.output/(name+'.log')).open('xb') as log:
                rc=subprocess.run(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=budget+15).returncode
            result[name+'_rc']=rc
            if rc: raise RuntimeError(name+' failed with code '+str(rc))
        verify(pin,a.role)
        for old in previous:
            verify(parent[old['role']],old['role']); assert sha(old['binary'])==old['binary_sha256']
        assert sha(N/'build_manifest_parent_v8.json')==parent_build_sha
        binary=a.build_dir/target; test_binary=a.build_dir/test
        result.update(binary=str(binary),binary_sha256=sha(binary),native_binary=str(test_binary),
                      native_binary_sha256=sha(test_binary),passed=True,
                      configure_rc=0,build_rc=0,parent_roles_verified_unchanged=True)
    except Exception as e: result['error']=repr(e)
    result['elapsed_seconds']=time.monotonic()-started
    write(a.output/'result.json',result)
    print(json.dumps(result,sort_keys=True))
    return 0 if result['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
