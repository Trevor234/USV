#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
exec /usr/bin/python3 -B /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_70_81_review_20261025_82/implementation/replay_storage02.py
