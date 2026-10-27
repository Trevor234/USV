
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
exec cmake --build /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_action_freeze_20261024_71/build/freeze_t2/cmake_build --target p1_m4_worker_owned p1_m4_regulator_owned p1_m4_fixture_owned -j2
