set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec timeout --signal=TERM --kill-after=5s 60s /usr/bin/strace -qq -f -e trace=open,openat,openat2 -o /home/trevor/USV/.sgh-research/experiments/scheme_A_causal_cold_start_20261018_26/replay/native_causal_cold_v1.opens.log /home/trevor/USV/.sgh-research/experiments/scheme_A_causal_cold_start_20261018_26/build/replay_attempt01/cmake_build/replay_causal_cold --input /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_causal_cold_start_20261018_v26/runtime_job_v1.json --output /home/trevor/USV/.sgh-research/experiments/scheme_A_causal_cold_start_20261018_26/replay/native_causal_cold_v1.json
