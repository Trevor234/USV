import hashlib, json, os, pathlib, shutil, signal, subprocess, time

root=pathlib.Path('/home/trevor/USV').resolve()
exp=root/'.sgh-research/experiments/ppo_bag_actions_20261003_01'
case=exp/'results/new_actions'
case.mkdir(parents=True,exist_ok=False)
bag=root/'data/sim_bags/rl_c_actions_20261003_01'
assert not bag.exists(), 'bag output exists'
assert subprocess.run(['pgrep','-af','gz sim|ros2 launch|rl_policy_node|mpc_node|ros2 bag record'],capture_output=True).returncode==1
waypoints=exp/'straight_waypoints.yaml'
shutil.copy2(root/'.sgh-research/experiments/v5_scaling_fix_20261003/straight_waypoints.yaml',waypoints)
model=root/'usv_rl/models/v5/s4_dr/policy_physical_n.onnx'
manifest=model.with_suffix('.manifest.json')
contract=json.loads(manifest.read_text())
sha=hashlib.sha256(model.read_bytes()).hexdigest()
assert sha=='ff60e0f70a142dc0c76ac0e1b8e1d113bcff892d7999fad9ef41cf5a83147278'
assert contract['onnx_sha256']==sha and contract['output_unit']=='N'
env=os.environ.copy()
env.update(ROS_DOMAIN_ID='93',ROS_LOCALHOST_ONLY='1',GZ_PARTITION='ppo_bag_actions_20261003_01')
env['PYTHONPATH']=str(root/'usv_rl')+':'+env.get('PYTHONPATH','')
cmd='\n'.join([
    'set -e',
    'source /opt/ros/jazzy/setup.bash',
    'source /home/trevor/USV/vrx_ws/install/setup.bash',
    'source /home/trevor/USV/usv_mpc_ws/install/setup.bash',
    'exec ros2 launch usv_bringup vrx.launch.py scheme:=C headless:=true record_bag:=true'
    +' bag_dir:='+str(bag.parent)+' run_id:='+bag.name
    +' model_output_dir:='+str(case/'model')+' waypoints_file:='+str(waypoints)+' rl_model:='+str(model),
])
config_root=root/'usv_mpc_ws/install/usv_bringup/share/usv_bringup'
configs={}
for rel in ['launch/vrx.launch.py','config/path_config.yaml','config/usv_params_sim.yaml']:
    p=config_root/rel
    configs[rel]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),text=p.read_text())
context=dict(bag=str(bag),launch_command=cmd,model=str(model),model_sha256=sha,
    model_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),model_contract=contract,
    git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    git_status=subprocess.check_output(['git','status','--short'],cwd=root,text=True),
    git_diff_path=str(case/'git_diff.patch'),configs=configs,
    waypoints=dict(path=str(waypoints),sha256=hashlib.sha256(waypoints.read_bytes()).hexdigest(),text=waypoints.read_text()),
    control_rate_hz=5.0,d_t_max_n_per_s=80.0,
    recorder_use_sim_time=False,ros_domain_id=93,gazebo_partition=env['GZ_PARTITION'],
    topic_map=dict(left='/wamv/thrusters/left/thrust',right='/wamv/thrusters/right/thrust',
        status='/mpc/status',odom='/wamv/sensors/position/ground_truth_odometry',
        imu='/wamv/sensors/imu/imu/data',path='/path/reference',profile='/path/reference_profile',clock='/clock'),
    checker_parameters=dict(profile='ppo-actions-v1',match_window_ms=20.0,value_tolerance_n=1e-5,
        thrust_limit_n=25.0,min_active=10,require_nonzero_active=True),
    limitations=['Published commands, not measured realized force.',
        'No source sequence/stamp: common loss may remain undetected; exact GP labels unavailable.'])
(case/'git_diff.patch').write_bytes(subprocess.check_output(['git','diff'],cwd=root))
(case/'run_context.json').write_text(json.dumps(context,indent=2,ensure_ascii=False))
start=time.time()
signals=[]
with (case/'launch.log').open('w') as log:
    process=subprocess.Popen(['bash','-c',cmd],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (case/'process.json').write_text(json.dumps(dict(pid=process.pid,start_wall=start,
        command=cmd,bag=str(bag),env={k:env[k] for k in ['ROS_DOMAIN_ID','ROS_LOCALHOST_ONLY','GZ_PARTITION']}),indent=2))
    try:
        rc=process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        signals.append('SIGINT')
        os.killpg(process.pid,signal.SIGINT)
        try: rc=process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            signals.append('SIGTERM')
            os.killpg(process.pid,signal.SIGTERM)
            try: rc=process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                signals.append('SIGKILL')
                os.killpg(process.pid,signal.SIGKILL)
                rc=process.wait(timeout=5)
result=dict(returncode=rc,wall_elapsed=time.time()-start,stop_signals=signals,
    bag=str(bag),metadata_exists=(bag/'metadata.yaml').is_file())
(case/'complete.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
