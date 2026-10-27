#!/bin/bash
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONOPTIMIZE
unset ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
export ROS_DOMAIN_ID=120 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
W2_CASE_ROOT=/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66
export ROS_LOG_DIR="$W2_CASE_ROOT/evidence/ros_logs"
mkdir -p "$ROS_LOG_DIR"
exec /usr/bin/python3 -B "$W2_CASE_ROOT/implementation/launch_owned_once.py" --registration "$W2_CASE_ROOT/implementation/W2_registration_v1.json"
