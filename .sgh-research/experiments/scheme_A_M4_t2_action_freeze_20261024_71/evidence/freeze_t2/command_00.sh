
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec cmake -S /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_action_freeze_20261024_71/implementation/t2_author -B /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_action_freeze_20261024_71/build/freeze_t2/cmake_build -DCMAKE_BUILD_TYPE=Release '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG' -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DP1_OWNED_SOURCE_BUNDLE_SHA256=e88f6f26d49409cf1d00c58e195f73e57457481ad02efe717d79ac56441cd251 -DP1_DRIVER_TOOL_SHA256=8db9a511a168b6050a4c17663d74d7602e5f412e65bc23ed42e4161d5dc85bec -DP1_V4_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json -DP1_V3_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json
