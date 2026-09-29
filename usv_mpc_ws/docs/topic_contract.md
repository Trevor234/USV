# USV MPC 话题与坐标系契约规范

本文档是 USV MPC 控制软件栈的权威接口映射规范。所有 Launch 启动文件、YAML 参数以及节点默认值均需与本契约保持严格对齐。

## 通用接口

| 接口名称 | 默认话题 / 坐标系 | 消息类型 / 说明 |
| --- | --- | --- |
| 参考路径 | `/path/reference` | `nav_msgs/msg/Path`，路径坐标系为 `map` |
| 动态航点 | `/usv/mission/waypoints_local` | `nav_msgs/msg/Path`，局部任务航点 |
| MPC 状态 | `/mpc/status` | `std_msgs/msg/String`，JSON 格式诊断信息 |
| MPC 预测轨迹 | `/mpc/predicted_trajectory` | `nav_msgs/msg/Path` |
| 地图/世界坐标系 | `map` | 全局/世界路径及里程计坐标系 |
| 机体坐标系 | `base_link` | 用于指令与诊断的 USV 船体自身坐标系 |

方案 A 在 `/mpc/status` 中发布候选解的可行性诊断信息：`initial_state_residual`（初始状态残差）、`max_dynamics_residual`（最大动力学残差）、`max_control_bound_violation`（最大控制量越界值）以及 `max_control_rate_violation`（最大控制率越界值）。仅当这四个值均在 `kinematic.solution_constraint_tol` 容差范围内时，恢复出的 IPOPT 迭代解才被认定为求解成功。

方案 B 将求解器规划的首步推力发布为 `tl_cmd_n`/`tr_cmd_n`，并将执行层用于下一个控制变化率锚定点的等效输入发布为 `tl_n`/`tr_n`。对于 RC 覆盖模式，`actuation_anchor_source` 为 `rc_linearized`；对于 VRX 直驱推力模式，则为 `vrx_published`。`actuation_mapping_error_n` 记录规划推力与锚定推力之间的最大绝对差值。

方案 C（`usv_rl_ros/rl_policy_node`，强化学习）复用方案 B 的全部公共话题：订阅相同的 odom/IMU/参考路径/速度剖面，在 VRX 模式发布相同的 `/wamv/thrusters/{left,right}/thrust` 推力话题，并发布与 `/mpc/status` 同构的 JSON（`control_mode` 为 `rl`，`backend` 为 `onnx_ppo`，`solve_time_ms` 为推理耗时）。安全节点的 `/mpc/status` 看门狗对方案 C 无需改动。方案 C 的动作侧约束与方案 B 一致：±25 N clamp + 80 N/s 速率限制。`real_mavros` 模式下的 `rc_override` 输出在部署阶段接入。

## 运行环境配置（Runtime Profiles）

### `vrx` — 真实 VRX Gazebo 仿真 / WAM-V 双体船

| 接口 | 对应话题 |
| --- | --- |
| 里程计 (Odometry) | `/wamv/sensors/position/ground_truth_odometry` |
| IMU 惯导 | `/wamv/sensors/imu/imu/data` |
| 左推进器推力指令 | `/wamv/thrusters/left/thrust` |
| 右推进器推力指令 | `/wamv/thrusters/right/thrust` |

注意事项：

- VRX 航点必须使用与 WAM-V 里程计完全相同的世界/地图坐标系（`map`），**不能**使用相对于船体生成点的局部坐标。
- VRX 里程计遵循 `nav_msgs/msg/Odometry` 坐标系契约：位姿（Pose）位于 `header.frame_id`（`map`），速度（Twist）位于 `child_frame_id`（`wamv/base_link`）。方案 A 的 `cmdvel_to_thrust` 直接消费 `twist.linear.x` 作为机体纵向速度（surge speed），**严禁再次根据航向角（yaw）进行旋转变换**。
- `sydney_regatta` 场景中 WAM-V 的默认生成位置大约在 `(-532, 162)` 附近，因此配置在 `(0, 0)` 附近的 YAML 航线实际相距数百米。
- VRX 推力话题使用 WAM-V 推进器指令尺度；`mpc_node` 会通过 `vrx_thrust_scale` 缩放内部左右推力值，并将其截断在配置的动态推力边界内，最后将实际发布的推力值写回，作为下一次 `delta_T` 的锚定点。

### `sitl_mavros` — ArduPilot SITL 软件在环仿真 + MAVROS

| 接口 | 对应话题 |
| --- | --- |
| 里程计 | `/mavros/local_position/odom` |
| IMU 惯导 | `/mavros/imu/data` |
| 飞控连接状态 (FCU) | `/mavros/state` |
| 方案 A 速度指令 | `/mavros/setpoint_velocity/cmd_vel` |
| 方案 B RC 覆盖输入 | `/mavros/rc/override` |
| RC 输出反馈 | `/mavros/rc/out` |

方案 B 的 RC 链路通过配置的 PWM 增益和正负号生成覆盖指令。在整型 PWM 量化后，节点会在 `tl_n`/`tr_n` 中上报线性化等效推力；在获取完整的 PWM、死区、推进系统及电池电压标定数据之前，该值属于指令侧估算值。

### `real_mavros` — 真实硬件船艇 + MAVROS

除非硬件 Launch 文件中显式重映射（remap）了相关话题，否则必须使用与 `sitl_mavros` 完全一致的 MAVROS 话题契约。任何改动均应在 Launch 文件中记录，并同步更新到本文档中。

### `fallback_gz` — 项目本地 Gazebo 仿真兜底方案

| 接口 | 对应话题 |
| --- | --- |
| Gazebo 模型里程计 | `/model/usv_2m/odometry` |
| 船体扳手（力和力矩）指令 | `/world/lake_gz/wrench` |
| 力指令桥接输入 | `/usv/cmd_force` |

### `classic_gazebo` — 旧版 Gazebo Classic（遗留/后备）

Gazebo Classic 的 Launch 文件依赖 `GAZEBO_*` 环境变量且可能依赖 `gazebo_ros`。在 ROS 2 Jazzy 环境下，这不是推荐的 VRX 验证路径。

## 调试排查清单（Debug checklist）

```bash
ros2 topic list | grep -E 'mpc|path|wamv|mavros|usv'
ros2 topic echo /mpc/status --once
ros2 topic info /path/reference
ros2 param dump /mpc_controller_node
```

在 VRX 仿真环境下，还需检查：

```bash
ros2 topic echo /wamv/sensors/position/ground_truth_odometry --once
ros2 topic echo /wamv/thrusters/left/thrust --once
ros2 topic echo /wamv/thrusters/right/thrust --once
```
