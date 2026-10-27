#!/usr/bin/env bash
set -eu
python3 /tmp/review73_boundary_plan/measure.py
g++ -std=c++17 -O0 \
  -I/usr/include/eigen3 \
  -I/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/t2_author_rev8/observer/src/shadow \
  -I/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation/t2_author_rev8/common \
  -I/home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/include \
  /tmp/review73_boundary_plan/epoch_probe.cpp \
  /home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/src/utils.cpp \
  -o /tmp/review73_boundary_plan/epoch_probe
/tmp/review73_boundary_plan/epoch_probe > /tmp/review73_boundary_plan/epoch_probe.json
