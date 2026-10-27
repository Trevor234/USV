import os,json,pathlib,subprocess,time,signal
b=pathlib.Path("/home/trevor/USV/.sgh-research/experiments/nmpc_timeout_fix_20261003/results/postpatch");b.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env.update(ROS_DOMAIN_ID="89",ROS_LOCALHOST_ONLY="1",GZ_PARTITION="nmpc_timeout_postpatch_20261003")
cmd="source /opt/ros/jazzy/setup.bash && source /home/trevor/USV/vrx_ws/install/setup.bash && source /home/trevor/USV/usv_mpc_ws/install/setup.bash && exec ros2 launch usv_bringup vrx.launch.py scheme:=B headless:=True record_bag:=True bag_dir:="+str(b)+" run_id:=postpatch model_output_dir:="+str(b/"model")
start=time.time()
with (b/"launch.log").open("w") as log:
 p=subprocess.Popen(["bash","-c",cmd],stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
 (b/"process.json").write_text(json.dumps({"pid":p.pid,"start_wall":start,"env":{k:env[k] for k in ["ROS_DOMAIN_ID","ROS_LOCALHOST_ONLY","GZ_PARTITION"]}}))
 timed_out=False
 try: rc=p.wait(timeout=60)
 except subprocess.TimeoutExpired:
  timed_out=True;os.killpg(p.pid,signal.SIGINT)
  try:rc=p.wait(timeout=20)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=15)
 (b/"complete.json").write_text(json.dumps({"returncode":rc,"wall_elapsed":time.time()-start,"bounded_stop":timed_out}))
