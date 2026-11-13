# acados 环境变量(供 ros2 launch 时使用)。
# 详见 docs/pi5_deploy.md。

export ACADOS_SOURCE_DIR="${ACADOS_SOURCE_DIR:=$HOME/acados}"
export LD_LIBRARY_PATH="$HOME/acados/lib:${LD_LIBRARY_PATH}"