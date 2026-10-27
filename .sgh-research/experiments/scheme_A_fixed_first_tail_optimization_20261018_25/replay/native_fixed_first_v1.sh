set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec timeout --signal=TERM --kill-after=5s 60s /home/trevor/USV/.sgh-research/experiments/scheme_A_fixed_first_tail_optimization_20261018_25/build/replay_attempt01/cmake_build/replay_fixed_first --input /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_fixed_first_tail_optimization_20261018_v25/actual_fixed_first_input_v1.json --output /home/trevor/USV/.sgh-research/experiments/scheme_A_fixed_first_tail_optimization_20261018_25/replay/native_fixed_first_v1.json
