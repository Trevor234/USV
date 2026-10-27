import subprocess,pathlib,json,time,os
p=pathlib.Path("/home/trevor/USV/.sgh-research/experiments/nmpc_timeout_fix_20261003/results/build");p.mkdir(parents=True,exist_ok=True)
cmd="source /opt/ros/jazzy/setup.bash && source /home/trevor/USV/vrx_ws/install/setup.bash && source /home/trevor/USV/usv_mpc_ws/install/setup.bash && cd /home/trevor/USV/usv_mpc_ws && colcon build --packages-select usv_mpc_cpp --symlink-install --event-handlers console_direct+"
start=time.time()
with (p/"build.log").open("w") as f:
 r=subprocess.run(["bash","-c",cmd],stdout=f,stderr=subprocess.STDOUT)
(p/"complete.json").write_text(json.dumps({"returncode":r.returncode,"wall_elapsed":time.time()-start}))
