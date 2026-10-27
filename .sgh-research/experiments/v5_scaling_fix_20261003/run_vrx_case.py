import argparse, json, os, pathlib, signal, subprocess, time
root=pathlib.Path('/home/trevor/USV')
exp=root/'.sgh-research/experiments/v5_scaling_fix_20261003'
parser=argparse.ArgumentParser()
parser.add_argument('case',choices=['old_diagnostic','new_physical_n'])
args=parser.parse_args()
case=exp/'results'/args.case
case.mkdir(parents=True,exist_ok=False)
waypoints=exp/'straight_waypoints.yaml'
if not waypoints.exists():
    waypoints.write_text('waypoints:\n  - {x: -532.0, y: 162.0}\n  - {x: -513.0894, y: 191.4515}\n  - {x: -494.1788, y: 220.9030}\n')
model=root/'usv_rl/models/v5/s4_dr'/('policy.onnx' if args.case=='old_diagnostic' else 'policy_physical_n.onnx')
env=os.environ.copy()
env.update(ROS_DOMAIN_ID='91',ROS_LOCALHOST_ONLY='1',
    GZ_PARTITION='v5_scaling_'+args.case+'_20261003')
env['PYTHONPATH']=str(root/'usv_rl')+':'+env.get('PYTHONPATH','')
cmd='\n'.join([
    'source /opt/ros/jazzy/setup.bash',
    'source /home/trevor/USV/vrx_ws/install/setup.bash',
    'source /home/trevor/USV/usv_mpc_ws/install/setup.bash',
    'exec ros2 launch usv_bringup vrx.launch.py scheme:=C headless:=True record_bag:=True'
    +' bag_dir:='+str(case)+' run_id:='+args.case+' model_output_dir:='+str(case/'model')
    +' waypoints_file:='+str(waypoints)+' rl_model:='+str(model),
])
start=time.time()
with (case/'launch.log').open('w') as log:
    p=subprocess.Popen(['bash','-c',cmd],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (case/'process.json').write_text(json.dumps(dict(pid=p.pid,start_wall=start,command=cmd,
        model=str(model),diagnostic_only=args.case=='old_diagnostic',
        env={k:env[k] for k in ['ROS_DOMAIN_ID','ROS_LOCALHOST_ONLY','GZ_PARTITION','PYTHONPATH']}),indent=2))
    bounded=False
    try: rc=p.wait(timeout=60)
    except subprocess.TimeoutExpired:
        bounded=True
        os.killpg(p.pid,signal.SIGINT)
        try: rc=p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try: rc=p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL)
                rc=p.wait(timeout=5)
(case/'complete.json').write_text(json.dumps(dict(returncode=rc,wall_elapsed=time.time()-start,
    bounded_stop=bounded),indent=2))
print(json.dumps(dict(case=args.case,returncode=rc,bounded_stop=bounded)))
