#!/usr/bin/env bash
# 编译 C++ 金标准轨迹导出工具（仅依赖 Eigen + usv_model_dynamic.cpp，无需 colcon）
set -euo pipefail
cd "$(dirname "$0")"

REPO_ROOT="$(cd ../../.. && pwd)"
EIGEN_INC="/usr/include/eigen3"
[ -d "$EIGEN_INC" ] || EIGEN_INC="$(pkg-config --variable=includedir eigen3 2>/dev/null || echo /usr/include/eigen3)"

g++ -O2 -std=c++17 \
  -I "$REPO_ROOT/usv_mpc_ws/src/usv_mpc_cpp/include" \
  -I "$EIGEN_INC" \
  dump_golden_trajectory.cpp \
  "$REPO_ROOT/usv_mpc_ws/src/usv_mpc_cpp/src/usv_model_dynamic.cpp" \
  -o dump_golden_trajectory

echo "built dump_golden_trajectory"
