# USV MPC 操作手册

本手册记录了所有支持的启动入口及确认话题/坐标系约定正常工作所需的最小检查步骤。
请保持本文档与 [`topic_contract.md`](topic_contract.md) 和
[`usv_bringup/config/topic_contract.yaml`](../src/usv_bringup/config/topic_contract.yaml) 同步更新。

## 编译与环境加载顺序

从一个干净的终端开始：

```bash
cd /home/trevor/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
export ACADOS_SOURCE_DIR=$HOME/acados
export LD_LIBRARY_PATH=$HOME/acados/lib:${LD_LIBRARY_PATH:-}
colcon build --symlink-install --packages-select \
  usv_bringup usv_planning usv_safety \
  usv_mpc usv_nmpc
source install/setup.bash
```

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

MAVROS 控制接口：

| 接口 | 默认值 |
| --- | --- |
| 里程计 | `/mavros/local_position/odom` |
| IMU | `/mavros/imu/data` |
| 飞控状态 | `/mavros/state` |
| 方案 A 速度指令 | `/mavros/setpoint_velocity/cmd_vel` |
| 方案 B RC 通道覆盖 | `/mavros/rc/override` |
| RC 输出 | `/mavros/rc/out` |

## 实机运行入口：通过 MAVROS 连接真实硬件

用于 AET-H743-AIR-PRO / 真实 USV 的部署路径：

```bash
cd /home/trevor/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 launch usv_bringup real.launch.py \
  scheme:=B \
  fcu_url:=/dev/ttyAMA10:921600
```

如需单独启动 MAVROS 并临时开启 GCS 转发（`real.launch.py` 默认不再提供 `gcs_url`）：

```bash
ros2 launch usv_bringup mavros.launch.py gcs_url:=udp://@<gcs-ip>:14550
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
- 方案 B 必须让飞控处于 **MANUAL**：RC 覆写只有在 MANUAL 下才经 ArduRover
  的 pilot 输入链成为舵/油主控制。GUIDED 下 MPC 仍会正常解算并发布覆写，
  但 CH1 转向被忽略、CH3 只作 speed nudge，且无 target 时 Stop/Loiter
  停车 —— 表现为船原地不动。`/mpc/status` 的 `allowed_fcu_modes` 应显示 `["MANUAL"]`，
  `standby_reason` 若为 `wrong_mode(...)` 说明模式没对上。
  因为 `auto_mode_switch` 默认关闭，必须由操作手切：遥控器模式开关打到
  **MODE1 位**（`MODE1=0`=MANUAL；MODE2/5=15=GUIDED，别停在那里），或用
  Mission Planner 的模式下拉框选 MANUAL。切好后 `/mpc/status` 从
  `STANDBY/wrong_mode` 变为 `ACTIVE`，`fcu_mode` 显示 `MANUAL`。
- 方案 B 的两条飞控侧前提（与方案 A 不同，务必知道）：
  1. **遥控器必须开机**。MPC 进 STANDBY 时会发全零 `OverrideRCIn`（=释放所有
     通道）。若此刻遥控器关机，`Rover::read_radio()` 拿不到有效 RC 帧，
     `RC_FS_TIMEOUT=1.0 s` 后触发 Radio Failsafe，`FS_ACTION=2`(Hold) 把船切进
     HOLD —— 也就是日志里 "FCU: Radio Failsafe / Cleared" 反复跳变的原因
     （2026-11-12 00:24–00:25 实测）。任何一次 odom/path 超时都会走这条路，
     而 `auto_mode_switch=false` 不会自己切回 MANUAL，必须人工重切。
     台架调试可临时 `FS_THR_ENABLE=0`，水上不要关。
  2. **人工接管按实机固件版本核对**。实机启动日志为
     `ArduRover V4.7.1 (dbe79216)`，该提交的 `RC_OPTIONS` 定义范围为 bit0–bit13。
     当前 `RC_OPTIONS=32` 对应 bit5（ARMING_CHECK_THROTTLE）。有效覆写期间，
     通道输入优先采用 MAVLink 覆写值，操作手推动摇杆后仍会使用覆写值。
     [对应固件的位定义](https://github.com/ArduPilot/ardupilot/blob/dbe79216/libraries/RC_Channel/RC_Channel.h#L623-L638)

     当前固件提供 `RCx_OPTION=46`（RC Override Enable）辅助开关机制，
     `x` 按遥控器实际接线选择独立可用通道。LOW 会清除现有覆写并关闭后续
     覆写接收，HIGH 重新允许覆写，MIDDLE 保持先前状态。在未解锁台架上核对
     开关实际高低位置、禁用覆写后的遥控输入，以及重新允许后的 MPC 恢复行为。
     [对应固件的开关处理](https://github.com/ArduPilot/ardupilot/blob/dbe79216/libraries/RC_Channel/RC_Channel.cpp#L1297-L1312)

     拨模式开关切到 HOLD 会使方案 B 进入待命并释放覆写。回到 MANUAL 后，
     MPC 在路径、里程计和解锁条件满足时会恢复输出，接管操作需结合覆写
     使能开关的实际配置。
- RTK 差分凭据：`ntrip.launch.py` 依赖
  `usv_bringup/config/ntrip_params.yaml`（含 CORS 账号密码，不入库）。
  仓库只提供 `ntrip_params.yaml.example` 模板；首次部署时先
  `cp ntrip_params.yaml.example ntrip_params.yaml` 并填写真实凭据，
  树莓派迁移时用 `scp` 单独传输该文件，不随源码提交。

## 脚本化冒烟检查

启动 `real.launch.py` 后，在另一个已 source 环境的终端中运行对应的检查：

```bash
cd /home/trevor/usv_mpc_ws

scripts/smoke_check_topics.sh real B
scripts/smoke_check_topics.sh real A
```

该脚本会检查指定方案对应的里程计/IMU/控制话题以及公共 MPC 约定话题。
如果任何必需话题缺失，或 `ros2 topic echo --once` 未收到消息，脚本将以非零状态退出。

启动较慢时可使用更长的超时时间：

```bash
SMOKE_TIMEOUT_S=10 scripts/smoke_check_topics.sh real B
```

## 通用诊断命令

```bash
ros2 topic list | grep -E 'mpc|path|mavros|usv'
ros2 node list
ros2 param dump /mpc_controller_node
ros2 topic echo /mpc/status --once
```

如果 MPC 未在控制船体，按以下顺序排查：

1. 传递给 `mpc_node` 的里程计话题是否有数据到达？
2. `/path/reference` 是否非空，且与里程计使用相同的坐标系？
3. `/mpc/status` 是否报告 `STANDBY`、`HOLD` 或求解器失败？
4. `/mavros/state` 是否已连接且处于允许的模式（方案 A 为 `GUIDED`，方案 B 为 `MANUAL`）？
