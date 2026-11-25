# USV MPC 操作手册

本手册记录了所有支持的启动入口及确认话题/坐标系约定正常工作所需的最小检查步骤。
请保持本文档与 [`topic_contract.md`](topic_contract.md) 和
[`usv_bringup/config/topic_contract.yaml`](../src/usv_bringup/config/topic_contract.yaml) 同步更新。

## 编译与环境加载顺序

### 1. 核心控制栈编译

从一个干净的终端开始：

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select \
  usv_bringup usv_acados usv_nmpc usv_mpc usv_planning usv_safety usv_simulation
source install/setup.bash
```

> [!NOTE]
> 如果直接全部编译，也可以简写为：`colcon build --symlink-install && source install/setup.bash`。

### 2. VRX 仿真环境加载顺序（关键！）

如果需要使用 VRX Gazebo 仿真 / WAM-V 入口，**必须先 source VRX 仿真工作空间，再 source MPC 控制工作空间**：

```bash
cd /home/trevor/USV
source /opt/ros/jazzy/setup.bash
source vrx_ws/install/setup.bash
source usv_mpc_ws/install/setup.bash
```

> [!WARNING]
> **常见错误排查**：
> 如果执行 `ros2 launch usv_bringup vrx.launch.py` 时报错：
> `PackageNotFoundError: package 'wamv_gazebo' not found` 或 `package 'vrx_gz' not found`，
> 说明当前终端**漏掉了 `source vrx_ws/install/setup.bash`**，请按上述三层顺序重新 source。

---

## 话题与坐标系约定速查表

公共接口：

| 接口 | 默认值 | 消息类型 / 坐标系 |
| --- | --- | --- |
| 参考路径 | `/path/reference` | `nav_msgs/msg/Path` (`map`) |
| 动态航点 | `/usv/mission/waypoints_local` | `nav_msgs/msg/Path` (`map`) |
| MPC 状态 | `/mpc/status` | `std_msgs/msg/String` (JSON 诊断) |
| MPC 预测轨迹 | `/mpc/predicted_trajectory` | `nav_msgs/msg/Path` (`map`) |
| 路径/地图坐标系 | `map` | 世界坐标系 |
| 船体坐标系 | `base_link` | 船体自身坐标系 |

纯仿真、SITL 和真机共用的 MAVROS 接口：

| 接口 | 默认值 | 说明 |
| --- | --- | --- |
| 里程计 | `/mavros/local_position/odom` | 状态反馈 |
| IMU | `/mavros/imu/data` | 姿态角速度反馈 |
| 飞控状态 | `/mavros/state` | 心跳/连接/模式状态 |
| 方案 A 速度指令 | `/mavros/setpoint_velocity/cmd_vel` | 运动学 MPC 输出 (GUIDED 模式) |
| 方案 B RC 通道覆盖 | `/mavros/rc/override` | 动力学 NMPC 输出 (MANUAL 模式) |
| RC 输出反馈 | `/mavros/rc/out` | 飞控舵机/电调实际输出通道 |

VRX WAM-V 专用接口：

| 接口 | 默认值 | 说明 |
| --- | --- | --- |
| 里程计 | `/wamv/sensors/position/ground_truth_odometry` | 仿真真值里程计 |
| IMU | `/wamv/sensors/imu/imu/data` | 仿真 IMU 数据 |
| 左推进器推力 | `/wamv/thrusters/left/thrust` | 方案 B 直驱推力指令 |
| 右推进器推力 | `/wamv/thrusters/right/thrust` | 方案 B 直驱推力指令 |

---

## 入口 1：VRX Gazebo 仿真 / WAM-V（双体船）

用于方案 B (动力学 NMPC) 的主要仿真验证路径。

```bash
cd /home/trevor/USV
source /opt/ros/jazzy/setup.bash
source vrx_ws/install/setup.bash
source usv_mpc_ws/install/setup.bash

ros2 launch usv_bringup vrx.launch.py \
  waypoints_file:=/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/waypoints/vrx_b_circle.yaml \
  visualize:=true \
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
  bag_dir:=/home/trevor/USV/data/sim_bags \
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
- 方案 B 状态中的 `tl_cmd_n/tr_cmd_n` 是计划推力，`tl_n/tr_n` 是映射后等效下发推力；`actuation_mapping_error_n` 较大时，应检查 RC 增益、PWM 限幅和推进器标定。
- MPC 正在求解时，`/mpc/predicted_trajectory` 存在并有预测数据。
- WAM-V 推力话题收到方案 B 的推力指令。

> [!NOTE]
> VRX 坐标系注意事项：航点 YAML 文件必须使用与 VRX 真值里程计相同的世界/地图坐标系。
> `sydney_regatta` 世界中 WAM-V 的默认出生点大约在 `(-532, 162)`，因此以 `(0, 0)` 为中心的路径会离船数百米远。

---

## 入口 2：纯 Python 动力学仿真（无外部依赖）

当没有 VRX、Gazebo 或 MAVROS 硬件时使用此模式。模拟器会按照与约定相同的默认值发布 MAVROS 格式的话题。

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
- `path_planner_node` 在拥有至少两个航点后发布 `/path/reference`；否则会发布空路径，MPC 保持待机/保持模式。
- `mpc_controller_node` 即使在等待有效路径或模式条件时也会发布 `/mpc/status`。

---

## 入口 3：ArduPilot SITL 软件在环仿真（虚拟飞控 + MAVROS）

用于在开发机上验证与真实 ArduRover 飞控协议（MAVLink / MAVROS）完全一致的闭环控制。

### 步骤 1：启动 ArduRover SITL 进程

在终端 1 中运行：

```bash
cd /home/trevor/USV/ardurover-argus/Tools/autotest
python3 sim_vehicle.py -v Rover -N --map --console --out=tcpin:0.0.0.0:5762
```

> [!TIP]
> - `-N`（或 `--no-rebuild`）表示跳过构建直接启动已编译好的 `ardurover` 固件，避免每次重复检查编译，秒级启动。
> - **端口注意**：请使用 `5762` 作为转发端口，**不要使用 `5760`**（因为 ArduRover 底层进程默认已占用了 `5760` 与 MAVProxy 内部通信，再次绑定会报 `[Errno 98] Address already in use`）。
> - 运行后会弹出地图（Map）和 MAVProxy 控制台（Console）图形界面。

### 步骤 2：启动 ROS 2 控制闭环

在终端 2 中运行：

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# 方案 A（运动学 MPC，GUIDED 模式下通过 cmd_vel 控速控向）
ros2 launch usv_bringup sitl.launch.py scheme:=A fcu_url:=tcp://127.0.0.1:5762

# 或 方案 B（动力学 NMPC，MANUAL 模式下通过 RC override 控制推力）
ros2 launch usv_bringup sitl.launch.py scheme:=B fcu_url:=tcp://127.0.0.1:5762
```

---

## 入口 4：通过 MAVROS 连接真实船艇硬件

用于 MicoAir743 / 真实 USV 的部署运行。

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch usv_bringup real.launch.py \
  scheme:=B \
  fcu_url:=/dev/ttyAMA10:921600 \
  gcs_url:=udp://@<GCS_IP>:14550 \
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
- 方案 A 使用 `/mavros/setpoint_velocity/cmd_vel`；方案 B 使用 `/mavros/rc/override`。
- **RTK 差分凭据**：`ntrip.launch.py` 依赖 `usv_bringup/config/ntrip_params.yaml`（含 CORS 账号密码，不入库）。首次部署时先 `cp ntrip_params.yaml.example ntrip_params.yaml` 并填写真实凭据。树莓派迁移时通过 `scp` 单独传输，不随源码提交。

---

## 脚本化快速冒烟检查

启动上述任一入口后，可在另一个终端中运行对应的自动化冒烟脚本：

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# 针对当前运行的环境进行校验
scripts/smoke_check_topics.sh vrx
scripts/smoke_check_topics.sh sim
scripts/smoke_check_topics.sh real
```

该脚本会检查对应场景的里程计、IMU、控制指令话题及 MPC 状态话题。启动较慢时可增加检测超时时间：

```bash
SMOKE_TIMEOUT_S=10 scripts/smoke_check_topics.sh vrx
```

---

## 离线工具：水动力与推进器参数辨识

实船采集到 `.bin` 日志后，可在开发机执行离线参数拟合与辨识：

```bash
# 1. 原始日志存放于统一数据目录：~/USV/data/flight_logs/<日期>/
# 2. 进入参数辨识独立工具箱
cd /home/trevor/USV/tools/params_id

# 3. 数据解析并执行 Stage 1/2/3 辨识
python3 scripts/parse_log.py ../../data/flight_logs/20260903/2026-09-03\ 14-46-08.bin data_parsed/0903_test.npz
python3 scripts/fit_thruster.py data_parsed results/20260903/
```

详细辨识流程与水试机动要求参见：[`参数辨识指南_换推进器版.md`](参数辨识指南_换推进器版.md)。

---

## 通用诊断与故障排查清单

```bash
ros2 topic list | grep -E 'mpc|path|wamv|mavros|usv'
ros2 node list
ros2 param dump /mpc_controller_node
ros2 topic echo /mpc/status --once
```

如果 MPC 未在控制船体，按以下顺序排查：
1. **里程计到达排查**：传递给 `mpc_node` 的里程计话题是否有数据到达？
2. **参考路径排查**：`/path/reference` 是否非空，且与里程计使用相同的坐标系（`map`）？
3. **求解器状态排查**：`/mpc/status` 是否报告 `STANDBY`、`HOLD` 或求解器失败（残差超标）？
4. **飞控模式排查**：对于 MAVROS 路径，`/mavros/state` 是否已连接且处于允许的模式（方案 A 需 GUIDED，方案 B 需 MANUAL）？
5. **VRX 推力排查**：对于 VRX，WAM-V 推力话题是否存在并正在接收数值？
