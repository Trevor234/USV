set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
export ROS_DOMAIN_ID=197
export P1_PAIR_TEST_OUTPUT=/home/trevor/USV/.sgh-research/experiments/scheme_A_reference_pair_wakeup_20261018_22/build/pair_wakeup_observer_attempt03/native_callback_output
export P1_PAIR_TEST_OUTPUT=/home/trevor/USV/.sgh-research/experiments/scheme_A_reference_pair_wakeup_20261018_22/component/native_crash_probe_v1
exec timeout --signal=TERM --kill-after=5s 30s gdb -q -batch -ex run -ex "thread apply all bt" --args /home/trevor/USV/.sgh-research/experiments/scheme_A_reference_pair_wakeup_20261018_22/build/pair_wakeup_observer_attempt03/cmake_build/test_reference_pair_callbacks --gtest_filter=PairCallbacks.ProfilePhasePathSubmitsActualJob
