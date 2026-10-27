set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH

export ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_DOMAIN_ID=120 RMW_IMPLEMENTATION=rmw_fastrtps_cpp

exec /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/recorder/build01/p1_owned_recorder --run-id M4_recorder_process_component_49 --contract /home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json --contract-sha256 19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a --topics /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/verification/recorder_process_v1/topics.json --topics-sha256 3dc137d5fa18c61a09b08f0f6fb1026fc6708755186486280bec215557dd3d61 --manifest /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/verification/recorder_process_v1/manifest.json --terminal /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/verification/recorder_process_v1/terminal.json --bag /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/verification/recorder_process_v1/bag --storage-id sqlite3 --prepare-budget-ms 10000
