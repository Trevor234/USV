set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH

export ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp

exec /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/build/fault_attempt03/cmake_build/test_m4_recorder_process /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/verification/recorder_process_v3/case00.json 0335f309809eb9791d64079fa5cfef885f7c7979a0129aea04bc5d0ead0948e2
