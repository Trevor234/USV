set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec cmake -S /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_action_freeze_20261024_71/implementation/t2_author \
  -B /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_action_freeze_20261024_71/evidence/compile_gate/build \
  -DCMAKE_BUILD_TYPE=Release '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG' \
  -DP1_OWNED_SOURCE_BUNDLE_SHA256=0000000000000000000000000000000000000000000000000000000000000000 \
  -DP1_DRIVER_TOOL_SHA256=1111111111111111111111111111111111111111111111111111111111111111 \
  -DP1_V4_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json \
  -DP1_V3_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json
