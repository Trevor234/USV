set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:$LD_LIBRARY_PATH
export ROS_DOMAIN_ID=121 ROS_LOCALHOST_ONLY=1 PYTHONDONTWRITEBYTECODE=1
BUILD=/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r1_runtime_20261024_76/build/r1_harness
cmake -S /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r1_runtime_20261024_76/implementation/t2_author_r1/..//r1_harness -B $BUILD   -DT1_AUTHOR_DIR=/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r1_runtime_20261024_76/implementation/t2_author_r1   -DP1_FROZEN_CONTRACT=/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json   -DP1_OWNED_SOURCE_BUNDLE_SHA256=0000000000000000000000000000000000000000000000000000000000000000   -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS_DEBUG='-O0 -g0' > /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r1_runtime_20261024_76/evidence/harness_configure.log 2>&1
cmake --build $BUILD -j2 > /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r1_runtime_20261024_76/evidence/harness_build.log 2>&1
rm -rf /tmp/r1_cases && mkdir -p /tmp/r1_cases
P1_T1_TEST_OUTPUT=/tmp/r1_cases timeout --signal=TERM --kill-after=2s 60s $BUILD/test_current_candidate_reference_clock   --gtest_output=json:/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_r1_runtime_20261024_76/evidence/harness_gtest.json
