#!/bin/bash
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONOPTIMIZE
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/local_setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
export LD_LIBRARY_PATH=/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:$LD_LIBRARY_PATH
export PYTHONDONTWRITEBYTECODE=1
W2_CASE_ROOT=/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66
exec /usr/bin/python3 -B "$W2_CASE_ROOT/implementation/w2_author/audit_w2.py" --registration "$W2_CASE_ROOT/implementation/W2_registration_v1.json" --output "$W2_CASE_ROOT/evidence/owned_audit_v1.json"
