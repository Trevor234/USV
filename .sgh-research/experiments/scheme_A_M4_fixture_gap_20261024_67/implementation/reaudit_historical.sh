#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/setup.bash
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 -B /home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/implementation/reaudit_historical.py
