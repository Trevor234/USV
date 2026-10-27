import subprocess,pathlib,json,time,os
p=pathlib.Path("/home/trevor/USV/.sgh-research/experiments/nmpc_timeout_fix_20261003/results/tests");p.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env.update(ROS_DOMAIN_ID="88",ROS_LOCALHOST_ONLY="1")
setup="source /opt/ros/jazzy/setup.bash && source /home/trevor/USV/usv_mpc_ws/install/setup.bash && cd /home/trevor/USV/usv_mpc_ws && "
start=time.time()
with (p/"test.log").open("w") as f:r=subprocess.run(["bash","-c",setup+"colcon test --packages-select usv_mpc_cpp --event-handlers console_direct+"],stdout=f,stderr=subprocess.STDOUT,env=env)
with (p/"test_result.log").open("w") as f:q=subprocess.run(["bash","-c",setup+"colcon test-result --test-result-base build/usv_mpc_cpp --verbose"],stdout=f,stderr=subprocess.STDOUT,env=env)
(p/"complete.json").write_text(json.dumps({"test_returncode":r.returncode,"result_returncode":q.returncode,"wall_elapsed":time.time()-start}))
