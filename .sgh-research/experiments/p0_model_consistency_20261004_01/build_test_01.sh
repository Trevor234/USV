#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/setup.bash
cd /home/trevor/USV/usv_mpc_ws
colcon build --packages-select usv_mpc_cpp --symlink-install --event-handlers console_direct+
source install/setup.bash
colcon test --packages-select usv_mpc_cpp --return-code-on-test-failure --event-handlers console_direct+
colcon test-result --verbose
