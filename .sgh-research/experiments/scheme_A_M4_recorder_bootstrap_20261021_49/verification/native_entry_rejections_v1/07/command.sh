set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH

export ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp

exec timeout --signal=TERM --kill-after=2s 10s /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_recorder_bootstrap_20261021_49/build/m4_attempt01/cmake_build/p1_m4_regulator_owned --ros-args -p run_id:=M4_entry_rejection_49 -p contract_file:=/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json -p contract_hash:=19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a -p m4_release_scope:=M4_owned_local_nominal_only_v1 -p mode:=execute -p output_dir:=/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_recorder_bootstrap_20261021_49/verification/native_entry_rejections_v1/07
