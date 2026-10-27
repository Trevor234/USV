
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec cmake -S "/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_fix_review_20261022_61/evidence/application_compile_and_edges/author" -B "/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_fix_review_20261022_61/evidence/application_compile_and_edges/build" -DCMAKE_BUILD_TYPE=Release   '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG' -DCMAKE_EXPORT_COMPILE_COMMANDS=ON   -DP1_OWNED_SOURCE_BUNDLE_SHA256=x -DP1_DRIVER_TOOL_SHA256=x   -DP1_V4_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json   -DP1_V3_CONTRACT_FILE=/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json
