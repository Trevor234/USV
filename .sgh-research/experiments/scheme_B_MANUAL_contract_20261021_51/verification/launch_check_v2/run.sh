set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH

exec /usr/bin/python3 -B -m pytest -q /home/trevor/USV/usv_mpc_ws/src/usv_bringup/test/test_fcu_mode_contract.py --junitxml=/home/trevor/USV/.sgh-research/experiments/scheme_B_MANUAL_contract_20261021_51/verification/launch_check_v2/result.xml -o cache_dir=/home/trevor/USV/.sgh-research/experiments/scheme_B_MANUAL_contract_20261021_51/verification/launch_check_v2/cache
