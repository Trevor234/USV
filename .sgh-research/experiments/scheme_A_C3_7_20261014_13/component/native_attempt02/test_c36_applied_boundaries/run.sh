set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
export ROS_DOMAIN_ID=131
export P1_C34_LEASE_NATIVE_DIR=/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_7_20261014_13/component/native_attempt02/test_c36_applied_boundaries/branch
export P1_BRANCH_TEST_OUTPUT=/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_7_20261014_13/component/native_attempt02/test_c36_applied_boundaries/branch
export C37_WORKER_CHILD_BIN=/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_7_20261014_v14/observer/build02/c37_worker_child
exec timeout --signal=TERM --kill-after=5s 90s /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_7_20261014_v14/observer/build02/test_c36_applied_boundaries --gtest_output=xml:/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_7_20261014_13/component/native_attempt02/test_c36_applied_boundaries/gtest.xml
