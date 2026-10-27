from pathlib import Path
import hashlib,json,subprocess,time,concurrent.futures
N=Path(__file__).resolve().parent
D=Path('/home/trevor/MPC/scheme_A_owned_20261010_01/S2/build_batch_v4');D.mkdir()
pins=json.loads((N/'source_bundles_v4.json').read_text())
bins={'publisher':'p1_mpc_publisher_startup','observer':'p1_regulator_shadow_observer_owned_v2','worker':'p1_solver_worker_owned_v2','recorder':'p1_owned_recorder','fixture':'p1_synthetic_source'}
setup='''export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=94
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
'''
def build(role):
 d=D/role;d.mkdir();t=time.monotonic();result={'role':role,'source_bundle':pins[role]}
 try:
  data=json.loads(Path(pins[role]['path']).read_text())
  for f in data['files'].values():
   if hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()!=f['sha256']:raise RuntimeError('source pin changed '+f['path'])
  flags=['-DCMAKE_BUILD_TYPE=Release','-DPython3_EXECUTABLE=/usr/bin/python3']
  macro='P1_D1_SOURCE_BUNDLE_SHA256' if role=='publisher' else 'P1_OWNED_SOURCE_BUNDLE_SHA256'
  flags+=['-D'+macro+'='+pins[role]['sha256']]
  if role=='publisher':flags+=['-DP1_F5_SOURCE_PACKAGE=/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp','-DP1_ACADOS_DIR=/home/trevor/acados','-DP1_CASADI_PACKAGE_DIR=/home/trevor/.local/lib/python3.12/site-packages/casadi','-DP1_CASADI_OLD_ABI=ON']
  import shlex
  commands=[['cmake','-S',str(N/role),'-B',str(N/role/'build'),*flags],['cmake','--build',str(N/role/'build'),'-j2']]
  for label,cmd,budget in zip(['configure','build'],commands,[60,180]):
   raw=setup+'exec timeout --signal=TERM --kill-after=10s '+str(budget)+'s '+shlex.join(cmd)+'\n'
   (d/(label+'.sh')).write_text(raw)
   with (d/(label+'.log')).open('xb') as out:
    rc=subprocess.run(['bash',str(d/(label+'.sh'))],stdout=out,stderr=subprocess.STDOUT,timeout=budget+15).returncode
   result[label+'_rc']=rc
   if rc:raise RuntimeError(label+' failed')
  for f in data['files'].values():
   if hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()!=f['sha256']:raise RuntimeError('source changed while building')
  p=N/role/'build'/bins[role]
  if not p.exists() and role=='publisher':
   found=[x for x in (N/role/'build').iterdir() if x.is_file() and x.stat().st_mode&0o111 and not x.name.startswith('test')];p=found[0]
  result.update(binary=str(p),binary_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),passed=True)
 except Exception as e:result.update(passed=False,error=str(e))
 result['elapsed_seconds']=time.monotonic()-t;(d/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:results=list(ex.map(build,bins))
(D/'result.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
