# USV MPC 操作手册

本手册记录了所有支持的启动入口及确认话题/坐标系约定正常工作所需的最小检查步骤。
请保持本文档与 [`topic_contract.md`](topic_contract.md) 和
[`usv_bringup/config/topic_contract.yaml`](../src/usv_bringup/config/topic_contract.yaml) 同步更新。

## 编译与环境加载顺序

从一个干净的终端开始：

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select \
  usv_bringup usv_mpc usv_planning usv_safety usv_simulation
source install/setup.bash
```

如果需要使用 VRX Gazebo 仿真 / WAM-V 入口，需要先 source VRX 工作空间，再 source 本工作空间：

```bash
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/setup.bash
```

如果 `ros2 launch usv_bringup vrx.launch.py --show-args` 提示找不到
`wamv_gazebo` 或 `vrx_gz`，说明 VRX 工作空间未被正确 source。

## 话题与坐标系约定速查表

公共接口：

| 接口 | 默认值 |
| --- | --- |
| 参考路径 | `/path/reference` |
| 动态航点 | `/usv/mission/waypoints_local` |
| MPC 状态 | `/mpc/status` |
| MPC 预测轨迹 | `/mpc/predicted_trajectory` |
| 路径/地图坐标系 | `map` |
| 船体坐标系 | `base_link` |

纯仿真、SITL 和真机共用的 MAVROS 接口：

| 接口 | 默认值 |
| --- | --- |
| 里程计 | `/mavros/local_position/odom` |
| IMU | `/mavros/imu/data` |
| 飞控状态 | `/mavros/state` |
| 方案 A 速度指令 | `/mavros/setpoint_velocity/cmd_vel` |
| 方案 B RC 通道覆盖 | `/mavros/rc/override` |
| RC 输出 | `/mavros/rc/out` |

VRX WAM-V 专用接口：

| 接口 | 默认值 |
| --- | --- |
| 里程计 | `/wamv/sensors/position/ground_truth_odometry` |
| IMU | `/wamv/sensors/imu/imu/data` |
| 左推进器推力 | `/wamv/thrusters/left/thrust` |
| 右推进器推力 | `/wamv/thrusters/right/thrust` |

## 入口 1：VRX Gazebo 仿真 / WAM-V

用于方案 B (动力学) 的主要验证路径。

```bash
cd /home/trevor/USV
source /opt/ros/jazzy/setup.bash
source vrx_ws/install/setup.bash
source usv_mpc_ws/install/setup.bash

ros2 launch usv_bringup vrx.launch.py \
  waypoints_file:=/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/waypoints/vrx_b_circle.yaml \
  record_bag:=false
```

常用参数覆盖：

```bash
ros2 launch usv_bringup vrx.launch.py \
  world:=sydney_regatta \
  headless:=False \
  paused:=False \
  waypoints_file:=/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/waypoints/vrx_b_s_curve.yaml \
  record_bag:=true \
  bag_dir:=$HOME/usv_vrx_logs \
  run_id:=vrx_scheme_b_s_curve
```

在另一个终端中进行冒烟检查：

```bash
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/setup.bash

ros2 topic echo /wamv/sensors/position/ground_truth_odometry --once
ros2 topic echo /mpc/status --once
ros2 topic info /path/reference
ros2 topic info /mpc/predicted_trajectory
ros2 topic echo /wamv/thrusters/left/thrust --once
ros2 topic echo /wamv/thrusters/right/thrust --once
```

预期结果：

- `path_planner_node` 启动后，`/path/reference` 开始发布数据。
- `/mpc/status` 输出来自 `mpc_controller_node` 的 JSON 状态信息。
- 方案 B 状态中的 `tl_cmd_n/tr_cmd_n` 是计划推力，`tl_n/tr_n` 是映射后等效下发推力；
  `actuation_mapping_error_n` 较大时，应检查 RC 增益、PWM 限幅和推进器标定。
- MPC 正在求解时，`/mpc/predicted_trajectory` 存在并有数据。
- WAM-V 推力话题收到方案 B 的推力指令。

VRX 坐标系注意事项：航点 YAML 文件必须使用与 VRX 真值里程计相同的世界/地图坐标系。
`sydney_regatta` 世界中 WAM-V 的默认出生点大约在 `(-532, 162)`，因此以 `(0, 0)` 为中心的路径会离船很远。

## 入口 2：纯 Python 动力学仿真

当没有 VRX、Gazebo 或 MAVROS 硬件时使用此模式。模拟器会按照与约定相同的默认值发布
MAVROS 格式的话题。

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch usv_bringup sim.launch.py scheme:=B visualize:=false
```

查看或覆盖话题约定：

```bash
ros2 launch usv_bringup sim.launch.py --show-args

ros2 launch usv_bringup sim.launch.py \
  scheme:=B \
  odom_topic:=/mavros/local_position/odom \
  imu_topic:=/mavros/imu/data \
  path_topic:=/path/reference \
  mpc_status_topic:=/mpc/status \
  predicted_trajectory_topic:=/mpc/predicted_trajectory \
  visualize:=false
```

冒烟检查：

```bash
ros2 topic echo /mavros/local_position/odom --once
ros2 topic echo /mavros/imu/data --once
ros2 topic echo /mavros/state --once
ros2 topic info /path/reference
ros2 topic echo /mpc/status --once
ros2 topic info /mpc/predicted_trajectory
```

预期结果：

- `usv_sim_node` 发布里程计、IMU 和模拟的 MAVROS 状态。
- `path_planner_node` 在拥有至少两个航点后发布 `/path/reference`；
  否则会发布空路径，MPC 保持待机/保持模式。
- `mpc_controller_node` 即使在等待有效路径或模式条件时也会发布 `/mpc/status`。

## 入口 3：通过 MAVROS 连接真实硬件

用于 MicoAir743 / 真实 USV 的部署路径。默认值与 SITL 使用相同的 MAVROS 话题约定。

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch usv_bringup real.launch.py \
  scheme:=B \
  fcu_url:=/dev/ttyAMA10:921600 \
  gcs_url:=udp://@10.210.191.110:14550 \
  visualize:=false
```

当硬件/MAVROS 命名空间不同时的常用覆盖参数：

```bash
ros2 launch usv_bringup real.launch.py \
  mavros_odom_topic:=/mavros/local_position/odom \
  mavros_imu_topic:=/mavros/imu/data \
  mavros_state_topic:=/mavros/state \
  mavros_velocity_topic:=/mavros/setpoint_velocity/cmd_vel \
  mavros_rc_override_topic:=/mavros/rc/override
```

冒烟检查：

```bash
ros2 topic echo /mavros/state --once
ros2 topic echo /mavros/local_position/odom --once
ros2 topic echo /mavros/imu/data --once
ros2 topic info /path/reference
ros2 topic echo /mpc/status --once
```

真机安全注意事项：

- 在启用自动模式切换或推力输出之前，务必先确认手动遥控器接管和物理急停开关功能正常。
- `real.launch.py` 默认在模式管理器中禁用了 `auto_arm` 和自动模式切换。
- 方案 A 使用 `/mavros/setpoint_velocity/cmd_vel`；方案 B 使用
  `/mavros/rc/override`。
- RTK 差分凭据：`ntrip.launch.py` 依赖
  `usv_bringup/config/ntrip_params.yaml`（含 CORS 账号密码，不入库）。
  仓库只提供 `ntrip_params.yaml.example` 模板；首次部署时先
  `cp ntrip_params.yaml.example ntrip_params.yaml` 并填写真实凭据，
  树莓派迁移时用 `scp` 单独传输该文件，不随源码提交。

## 可选的备用启动文件

`usv_simulation` 包还保留了 Gazebo Sim / Gazebo Classic 全栈备用入口：

```bash
ros2 launch usv_simulation gz_sitl_full.launch.py --show-args
ros2 launch usv_simulation gazebo_sitl_full.launch.py --show-args
```

这些适用于旧版 SITL/Gazebo 集成工作。它们的 `bag_dir` 默认值为
`$HOME/usv_vrx_logs`；可通过覆盖 `bag_dir:=...` 和 `run_id:=...` 为验证运行命名。

## 脚本化冒烟检查

启动上述任一栈后，在另一个已 source 环境的终端中运行对应的配置文件检查：

```bash
cd /home/trevor/USV/usv_mpc_ws

scripts/smoke_check_topics.sh vrx
scripts/smoke_check_topics.sh sim
scripts/smoke_check_topics.sh real
```

该脚本会检查指定配置对应的里程计/IMU/控制话题以及公共 MPC 约定话题。
如果任何必需话题缺失，或 `ros2 topic echo --once` 未收到消息，脚本将以非零状态退出。

启动较慢时可使用更长的超时时间：

```bash
SMOKE_TIMEOUT_S=10 scripts/smoke_check_topics.sh vrx
```

## 通用诊断命令

```bash
ros2 topic list | grep -E 'mpc|path|wamv|mavros|usv'
ros2 node list
ros2 param dump /mpc_controller_node
ros2 topic echo /mpc/status --once
```

如果 MPC 未在控制船体，按以下顺序排查：

1. 传递给 `mpc_node` 的里程计话题是否有数据到达？
2. `/path/reference` 是否非空，且与里程计使用相同的坐标系？
3. `/mpc/status` 是否报告 `STANDBY`、`HOLD` 或求解器失败？
4. 对于 MAVROS 路径，`/mavros/state` 是否已连接且处于允许的模式？
5. 对于 VRX，WAM-V 推力话题是否存在并正在接收指令？
