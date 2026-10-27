#!/bin/bash
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:$LD_LIBRARY_PATH
export ROS_DOMAIN_ID=120
export ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export PYTHONDONTWRITEBYTECODE=1
exec "$@"
