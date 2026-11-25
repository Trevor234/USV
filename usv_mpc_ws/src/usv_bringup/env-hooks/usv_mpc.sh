# acados 环境变量(供 ros2 launch 时使用)。
#
# 此文件可被 source,但 ROS2 ament_python 的 env-hook 自动 source 机制在不同版本
# 行为不一,建议同时在 ~/.bashrc 中写入以下两行以保证可靠:
#
#   export ACADOS_SOURCE_DIR=$HOME/acados
#   export LD_LIBRARY_PATH=$HOME/acados/lib:$LD_LIBRARY_PATH
#
# 详见 docs/pi5_deploy.md。

export ACADOS_SOURCE_DIR="${ACADOS_SOURCE_DIR:=$HOME/acados}"
export LD_LIBRARY_PATH="$HOME/acados/lib:${LD_LIBRARY_PATH}"
