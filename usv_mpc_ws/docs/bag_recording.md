# ROS 2 数据记录（rosbag2 + MCAP）

第 1–7 节描述 MAVROS 实机录包；VRX 仿真方案 C 的入口、话题与验收见第 8 节。两个入口的存储参数与话题清单分别生效。

本方案记录无人艇核心控制闭环，用于复盘定位、IMU、飞控状态、MPC 输出、参考轨迹和求解器状态。默认写入外接 SSD `/mnt/usv_bags`，不会在 SSD 缺失时回退到 Pi5 的 SD 卡。

## 1. 准备外接存储

将 SSD 挂载到 `/mnt/usv_bags`，并确保运行 ROS 2 的用户可进入和写入该目录：

```bash
findmnt /mnt/usv_bags
test -d /mnt/usv_bags
test -w /mnt/usv_bags
test -x /mnt/usv_bags
df -h /mnt/usv_bags
```

任一检查失败时先修复挂载或权限。录制 launch 会 fail-fast，不会自动创建挂载点，也不会改写到当前目录。

## 2. 录制方式

### 独立录制

适合单独调试 MAVROS 或控制节点：

```bash
source /opt/ros/jazzy/setup.bash
source ~/usv_mpc_ws_B/install/setup.bash
ros2 launch usv_bringup record.launch.py
```

### 随实机系统启动

```bash
ros2 launch usv_bringup real.launch.py record:=true
```

可覆盖输出位置和分片参数：

```bash
ros2 launch usv_bringup real.launch.py \
  record:=true \
  bag_output_dir:=/mnt/usv_bags \
  bag_prefix:=lake_test \
  bag_max_bag_size:=3221225472 \
  bag_max_bag_duration:=900
```

输出目录形如：

```text
/mnt/usv_bags/lake_test_20260817_153012/
```

默认每个 MCAP 文件达到 3 GiB 或 15 分钟时切分，以先达到者为准；切分不会停止整次录制。3 GiB 默认值低于 FAT32 的单文件上限，适用于当前 U 盘。写缓存默认 100 MiB。

## 3. 记录内容与 QoS

默认记录（与 `config/bag_topics.yaml` 一致，共 14 项）：

- `/mavros/local_position/odom`
- `/mavros/imu/data`
- `/mavros/state`
- `/mavros/rc/override`（方案 B 控制输出；方案 A 下 0 发布者）
- `/mavros/setpoint_velocity/cmd_vel`（方案 A 控制输出）
- `/mpc/status`
- `/path/reference`
- `/path/reference_profile`
- `/usv/mission/waypoints_local`
- `/mpc/predicted_trajectory`
- `/mavros/gpsstatus/gps1/raw`
- `/mavros/global_position/raw/fix`
- `/uas1/mavlink_source`（MAVLink 入站帧）
- `/uas1/mavlink_sink`（MAVLink 出站帧）

话题列表位于 `config/bag_topics.yaml`，类型和语义以 `config/topic_contract.yaml` 为准。odom、IMU、raw/fix 与两个 MAVLink 帧话题的发布端使用 BEST_EFFORT，recorder 通过 `config/rosbag_qos_overrides.yaml` 以 best-effort 订阅，避免 QoS 不兼容导致静默漏录。帧话题的覆盖深度为 1000。

存储使用 MCAP 的 `zstd_fast` preset，即 MCAP 内部 Zstd chunk 压缩。不要额外添加 rosbag2 transport 的 `--compression-mode` 或 `--compression-format`，否则会双重压缩并增加 Pi5 负载。

### 3.1 MAVLink 双向原始帧

| 话题 | 数据含义 | 时间戳含义 |
|---|---|---|
| `/uas1/mavlink_source` | 路由器交给 UAS 的入站帧；`header.frame_id=ep:<id>` 标识来源端点（实测 `ep:1000` = `/dev/ttyAMA10`） | 路由器解析后发布时的 ROS 时间，**不是** UART 首字节到达时间 |
| `/uas1/mavlink_sink` | UAS 封装后发出的报文，含控制/请求；仅表示**发送意图**，不证明串口已发出或飞控已执行 | UAS 发布前的 ROS 时间，**不是**实际线路发送时间 |

类型均为 `mavros_msgs/msg/Mavlink`。保留全部消息 ID 与 `framing_status`，不按插件/消息 ID 过滤，不另建桥接节点。

**记录边界（不得简化成“录到了飞控全部数据”）**：

- 只覆盖树莓派 UAS 端点实际收发的帧，不是全飞控物理通道的旁路抓包，也不等同于串口线抓取。解析器丢弃的串口噪声、残帧、不支持的 `incompat_flags` 不会出现。
- 独立数传/地面站之间不经过本 UAS 的交换无法记录；GCS↔FCU 端点直连转发也不保证出现在这两个话题中。
- `framing_status=1`（FRAMING_OK）**不等于**签名认证通过；本链路实测 `signature` 长度恒为 0。
- 帧封装不能补齐未下传的飞控内部高频量。只有原始帧不保证够辨识；未下传的内部量只能取自其他真实数据源（例如飞控 BIN 日志）。
- **RTCM 边界**：单独的 RTCM ROS 话题仍不录；但 MAVROS 经 UAS 发出的 `GPS_RTCM_DATA`（msgid 233）会自然出现在 `mavlink_sink` 内。不要把“RTCM 完全不在 bag 中”当成结论。
- 收/发两个话题**不是**一条单一有序线流。bag 接收时间、帧 ROS `header` 时间、载荷内 FCU boot/usec 时间是三条不同时间轴；不要用 ROS 时间差声称测出了串口延迟。
- 序号连续性必须按 `方向 + frame_id + sysid/compid` 跨全部 msgid 检查。按 msgid 分组会把正常的交错序号误报成丢包。


## 4. 正常停止与检查

使用 Ctrl-C 停止。看到 rosbag2 完成缓存刷新和 metadata 写入后，再断电或拔出 SSD；不要使用 `kill -9`。

```bash
ros2 bag info /mnt/usv_bags/lake_test_20260817_153012
```

重点检查：

- Storage id 为 `mcap`。
- odom、IMU 和 `/mpc/status` 的消息数大于 0。
- 录制起止时间符合实际运行。
- 目录中存在 `metadata.yaml` 和 `.mcap` 文件。

## 5. 回放

**禁止在连接真实飞控的 ROS 图上直接回放整个 bag。** `/uas1/mavlink_sink` 会把 MAVLink 报文注入 UAS 并送到串口，原有 `/mavros/rc/override` 与 `/mavros/setpoint_velocity/cmd_vel` 也会直接控制飞控——整包回放等于向实船重放历史控制量。分析一律使用离线 reader（`rosbag2_py.SequentialReader` + `rclpy.serialization.deserialize_message`）。确需回放只能在与实船完全隔离的环境，并显式使用安全话题白名单。

回放**必须同时满足**两个条件，缺一不可：①与实船完全隔离的环境（不同 ROS domain 且无任何到飞控的连接）；②显式安全话题白名单。不要提供或照抄不含白名单的整包 `ros2 bag play` 命令——那正是本节禁止的用法。

隔离环境 + 白名单的最小示例（`ROS_DOMAIN_ID` 必须与实船不同）：

```bash
export ROS_DOMAIN_ID=42        # 确认与船上 0 不同
ros2 bag play /path/to/bag \
  --topics /mavros/local_position/odom /mavros/imu/data /mpc/status
```

**任何时候都不要**把 `/uas1/mavlink_source`、`/uas1/mavlink_sink`、`/mavros/rc/override`、`/mavros/setpoint_velocity/cmd_vel` 放进白名单：它们会向 UAS/飞控注入控制量。

如分析节点使用 ROS 时钟，再按其设计决定是否加 `--clock` 和 `use_sim_time:=true`。


## 6. MPC 状态分析

`/mpc/status` 是 JSON 字符串，包含 `state`、`success`、`fail_count`、
`solve_time_ms`、`deadline_miss`、`hold`、`fcu_mode`、`armed`、
`path_received`、`profile_synced` 和后端信息。方案 B 还包含
`tl_cmd_n`/`tr_cmd_n`（求解器计划首拍）、`tl_n`/`tr_n`（执行层等效下发推力）、
`actuation_anchor_source` 和 `actuation_mapping_error_n`。离线分析时建议统计：

- `solve_time_ms` 的均值、P95、P99 和最大值。
- `deadline_miss` 次数。
- 连续失败和 HOLD 区间。
- `profile_synced=false` 与跟踪误差异常是否同时出现。
- `actuation_mapping_error_n` 的均值、P95 和峰值，确认 RC 增益或限幅是否让实际输入明显偏离计划。
- RC override 与 odom/IMU 响应的时延。

## 7. 未解锁 dry run

无需解锁飞控即可检查记录链路：

```bash
ros2 launch usv_bringup real.launch.py record:=true
```

保持 `armed=false`，运行约 30 秒后 Ctrl-C，再用 `ros2 bag info` 检查 MAVROS 和 MPC 状态消息。这样可在推进器不动作的情况下验证 SSD、QoS、MCAP 和 shutdown/finalize 流程。

## 8. VRX 方案 C：PPO 已发布动作录包与验收

VRX 使用 `usv_bringup vrx.launch.py`，必须显式指定 `scheme:=C record_bag:=true`。`record_bag` 默认仍为 `false`，录包输出位置由 `bag_dir` 和 `run_id` 决定。此入口保留原有 rosbag2 存储与记录时间选项；不能把第 3 节实机的 `config/bag_topics.yaml`、SSD 路径或 MCAP preset 当作 VRX 的有效配置。

“已执行动作”在这里指 PPO 节点经过幅值与变化率限制后，向 VRX 发布的左右推力命令，单位 N。记录不是推进器实际产生的力，也没有 Gazebo 接收确认。状态中的 `tl_cmd_n/tr_cmd_n` 是请求推力；`tl_n/tr_n` 才对应左右推力话题。做动作统计时应选择后者。

### 8.1 启动与正常停止

以下脚本使用当前默认参考任务。需要其他任务时，将已核验的用户参考文件作为 `waypoints_file:=/absolute/path/to/waypoints.yaml` 参数传给 launch，并在运行上下文中保存实际参数。不要依赖一次性实验目录中的参考文件长期存在。

```bash
#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/vrx_ws/install/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/setup.bash

# 93 是示例；先确认此 domain 没有其他实验进程。
export ROS_DOMAIN_ID=93
export ROS_LOCALHOST_ONLY=1
PPO_RUN_ID="rl_c_actions_$(date +%Y%m%d_%H%M%S)"
export GZ_PARTITION="$PPO_RUN_ID"
PPO_BAG_DIR=/home/trevor/USV/data/sim_bags
PPO_MODEL=/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx
PPO_MANIFEST=/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.manifest.json
PPO_EVIDENCE_DIR="/home/trevor/USV/.sgh-research/experiments/$PPO_RUN_ID"

test -f "$PPO_MODEL"
test -f "$PPO_MANIFEST"
test ! -e "$PPO_BAG_DIR/$PPO_RUN_ID"
test ! -e "$PPO_EVIDENCE_DIR"
mkdir -p "$PPO_BAG_DIR"
mkdir "$PPO_EVIDENCE_DIR"
printf '%s\n' "$PPO_BAG_DIR/$PPO_RUN_ID" > "$PPO_EVIDENCE_DIR/bag_path.txt"
sha256sum "$PPO_MODEL" "$PPO_MANIFEST" > "$PPO_EVIDENCE_DIR/model_sha256.txt"
printf 'run_id=%s\nevidence_dir=%s\n' "$PPO_RUN_ID" "$PPO_EVIDENCE_DIR"

ros2 launch usv_bringup vrx.launch.py \
  scheme:=C headless:=true record_bag:=true \
  bag_dir:="$PPO_BAG_DIR" run_id:="$PPO_RUN_ID" \
  rl_model:="$PPO_MODEL"
```

保存为 Bash 脚本执行，`set -e` 会在模型、清单或 run_id 检查失败时停止。`run_id` 目录存在即换新名字，不向旧 bag 写入。使用当前有效的物理 N 模型和单位清单；旧 `policy.onnx` 带有已知缺少物理缩放的问题，不能因为它也能生成推力话题就认作正确单位的基线。

先确认正在使用的 overlay：`ros2 pkg prefix usv_bringup` 应指向 `/home/trevor/USV/usv_mpc_ws/install/usv_bringup`。修改此 launch 后在 `/home/trevor/USV/usv_mpc_ws` 构建 `usv_bringup`，再 source 安装空间，检查安装侧 recorder 参数确有 `/clock`。

录制开始后确认 recorder 已订阅下表中的话题。控制器的 9 秒启动延迟不能保证 DDS 发现已完成；启动日志中的订阅结果与录后解码检查都需要保留。烟测运行约 60 秒墙钟，目标至少 10 个 ACTIVE 控制拍并有非零命令；墙钟时长不等于仿真时长。使用 Ctrl-C 正常停止，等待 recorder 刷新缓存并写完 `metadata.yaml` 后验收，不用 `kill -9`。独立实验全部进程应使用相同的 ROS domain 与 Gazebo partition，停止后确认该实验进程已退出。

### 8.2 必录话题

| 默认话题 | ROS 类型 | 用途 |
|---|---|---|
| `/wamv/thrusters/left/thrust` | `std_msgs/msg/Float64` | 已发布左推力命令，N |
| `/wamv/thrusters/right/thrust` | `std_msgs/msg/Float64` | 已发布右推力命令，N |
| `/mpc/status` | `std_msgs/msg/String` | JSON 状态、请求推力与限幅后推力、PPO 身份 |
| `/wamv/sensors/position/ground_truth_odometry` | `nav_msgs/msg/Odometry` | 观测状态及 Header 中的仿真时间 |
| `/wamv/sensors/imu/imu/data` | `sensor_msgs/msg/Imu` | IMU 观测 |
| `/path/reference` | `nav_msgs/msg/Path` | 采用的参考路径 |
| `/path/reference_profile` | `std_msgs/msg/Float64MultiArray` | 参考速度与调度剖面 |
| `/clock` | `rosgraph_msgs/msg/Clock` | 仿真时钟、暂停与重置诊断 |

现有 `/mpc/predicted_trajectory` 继续保留在 recorder 列表中，但方案 C 不要求产生此话题，缺失或为空不会使 PPO 动作验收失败。左右推力、status、odom、IMU、path 和 profile 仍使用 launch 中的可配置话题参数；`/clock` 为当前 VRX 固定时钟话题。

### 8.3 录后检查与两个 profile

`scripts/check_ppo_bag.py` 按 metadata 中的 storage id 读取实际记录并反序列化。它不修改 bag 或 metadata；报告必须写在 bag 之外，不能用 `ros2 bag info` 的非零计数替代动作完整性检查。

录制脚本会输出实际 `run_id` 和证据目录。脚本退出后其局部变量不会传回父终端；在验收终端按刚才打印的 run_id 设置变量，source 相同 ROS 环境，然后运行：

```bash
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/setup.bash
PPO_RUN_ID=替换为刚才输出的实际run_id
PPO_BAG_DIR=/home/trevor/USV/data/sim_bags
PPO_EVIDENCE_DIR="/home/trevor/USV/.sgh-research/experiments/$PPO_RUN_ID"

ros2 bag info "$PPO_BAG_DIR/$PPO_RUN_ID"

python3 /home/trevor/USV/usv_mpc_ws/scripts/check_ppo_bag.py \
  "$PPO_BAG_DIR/$PPO_RUN_ID" \
  --profile ppo-actions-v1 \
  --match-window-ms 20 --value-tolerance-n 1e-5 \
  --thrust-limit-n 25.0 \
  --min-active 10 --require-nonzero-active \
  --report "$PPO_EVIDENCE_DIR/acceptance.json"
```

- `ppo-actions-v1` 用于新 bag 正式验收：要求上表 8 个话题有实际可解码记录，验证方案 C 身份、左右发布与 status 一对一匹配，并检查 clock 与 odom 对控制区间的覆盖和可见时序空洞。
- `legacy-actions` 用于历史 bag 的已发布动作流检查：允许缺 `/clock`，但会标明 `timing_incomplete`。此模式不能替代新 bag 正式验收，也不能弥补历史缺失动作。

检查器先按 bag 接收时间和顺序逐路配对，匹配窗默认严格小于 20 ms，并必须小于半个名义控制周期；当前 `dynamic_dt=0.2 s`，因此该上界为 100 ms。匹配后再比较数值，默认允许误差 `1e-5 N`。它不会搜索相同数值补齐缺帧或重复使用相邻命令；未匹配、窗口内歧义、坏 JSON、缺字段、错误类型、NaN/Inf、发布值与 `tl_n/tr_n` 不一致都明确失败。待机零命令和开始/结束残帧也纳入检查，不能静默删除残帧后声明整包完整。

`--thrust-limit-n` 依据本次有效执行配置与模型单位清单设置，示例为当前 v5 的 ±25 N；更换配置后应明确更新该参数。量程通过本身不能证明 ONNX 已正确缩放，验收仍需绑定模型和 manifest 的 SHA256。`--min-active 10 --require-nonzero-active` 是本次烟测的附加条件，避免一直 STANDBY 或全零运行被视为 PPO 动作链烟测成功；其他研究任务可以合法地产生全零动作，不应普遍禁止。

历史正例的检查命令：

```bash
python3 /home/trevor/USV/usv_mpc_ws/scripts/check_ppo_bag.py \
  /home/trevor/USV/.sgh-research/experiments/v5_scaling_fix_20261003/results/new_physical_n/new_physical_n \
  --profile legacy-actions --thrust-limit-n 25.0 \
  --report /home/trevor/USV/.sgh-research/experiments/ppo_bag_history_new_physical_n.json
```

退出码 `0` 表示所选 profile 通过；`2` 表示可读取但数据合同不合格；`1` 表示无法读取、依赖缺失或配置错误。新研究 bag 只有正式验收通过才纳入数据集。失败 bag 保留为诊断，修复原因后使用新 run_id 重新录制。

### 8.4 话题重映射

launch 与检查器必须使用同一组实际话题名。例如录制时传入 `left_thrust_topic:=/experiment/left_thrust right_thrust_topic:=/experiment/right_thrust mpc_status_topic:=/experiment/rl_status`，验收时相应传入：

```bash
python3 /home/trevor/USV/usv_mpc_ws/scripts/check_ppo_bag.py \
  /absolute/path/to/bag --profile ppo-actions-v1 \
  --left-topic /experiment/left_thrust \
  --right-topic /experiment/right_thrust \
  --status-topic /experiment/rl_status \
  --thrust-limit-n 25.0 \
  --report /absolute/path/outside_bag/acceptance.json
```

其余参数对应关系为 `odom_topic` → `--odom-topic`、`imu_topic` → `--imu-topic`、`path_topic` → `--path-topic`、`profile_topic` → `--profile-topic`。`--clock-topic` 默认 `/clock`；若外部记录入口更改时钟名，必须同步设置。不能因检查器仍使用默认值而把正确的重映射 bag 误判为漏录，也不能使用重复的话题名让左右命令共用一条流。

### 8.5 时间与结论边界

当前 Float64 没有 Header，status 也没有源序号或源时间戳。检查通过证明已记录发布流满足配对与数值合同；它不能证明每一个计划控制拍都被 recorder 录下。如果同一拍的左右推力与 status 三路共同缺失，配对仍可能通过。严格 profile 使用同一 clock 分段内最近的 clock 辅助检查连续 ACTIVE 间隔，大于 `1.5 × dynamic_dt` 的可见空洞会失败；当前周期对应 0.3 s。这仍不能保证识别所有共同掉拍，或区分控制器漏拍与 recorder 漏录。

补录 `/clock` 可帮助诊断暂停、回退、重置与时序覆盖，但不能消除跨话题传输和接收延迟。严格 profile 对 clock 回退或控制区间无覆盖明确失败，不跨重置拼接样本。bag 的墙钟接收时间不能直接用作仿真动力学 Δt。本入口继续保留现有 recorder 时间模式，没有增加 `--use-sim-time`；该参数会改为使用最近收到的 clock 作为记录时间，并在首条 clock 前不写消息，属于不同时间合同，参见 [rosbag2 Jazzy 官方说明](https://github.com/ros2/rosbag2/tree/jazzy#simulation-time)。

报告保留 `common_drop_identifiable=false`、`exact_execution_timing_available=false` 和 `gp_labels_ready=false`。通过动作验收不自动意味着精确 GP 标签可用、执行延迟已测得或控制性能已经改善。首选 A 后续如需精确持有输入与状态对齐，应另行建立联合动作事件及源时间/序号合同。

### 8.6 历史 bag 分类与运行上下文

- `data/sim_bags/rl_c_001` 只有参考路径、剖面、odom 和 IMU，缺少左右推力、status 和 clock；两种 profile 均应拒绝。保留原文件，外部报告标记 `action_recording_complete=false`、`gp_labels_ready=false`。它仍可做有边界的轨迹与观测分析，不能直接计算可靠的动作统计、限幅、控制努力或动力学残差标签。
- 前次 `new_physical_n` bag 有已验证的动作记录，但未录 clock；`legacy-actions` 可以检查已记录流，正式 `ppo-actions-v1` 应因时钟缺失拒绝。
- 前次 `old_diagnostic` 虽有动作记录，仍带已知物理缩放缺陷；只能保留为诊断对照。

缺失的历史动作不能补零，不能把动力学逆算或重新运行策略得到的动作当成原实验的真实发布动作写回 bag。需要已发布输入的研究样本必须重新录制。

在 bag 外的实验目录保存 `run_context.json` 或等效上下文文件，包括实际启动命令、解析后的话题名、模型与 manifest SHA256、Git HEAD 和未提交差异、有效车辆/控制参数与参考任务、ROS domain、Gazebo partition、recorder 时间模式、停止方式和检查器参数。建议同时保存 `ros2 pkg prefix usv_bringup`、recorder 订阅日志及验收 JSON，便于核验实际运行的 overlay。当前配置不能冒充历史训练配置；上下文中不要保存登录凭据。

## 9. 实机 systemd 录制服务（usv-record.service）与挂载时序

实机 Pi 上由 `usv-record.service` 常开录制（旁挂 usv-system，不写 Requires/BindsTo）。该 unit 只存在于部署机 `/etc/systemd/system/`，无 git 源；修改前按部署惯例先备份到 `~/usv_backups/<部署号>/`。

SSD 挂载采用 fstab 惰性方案：`x-systemd.automount` + `x-systemd.device-timeout=30s` + `nofail`。unit 与挂载的契约如下，改动前先理解：

- **禁止在 unit 中加 `RequiresMountsFor=/mnt/usv_bags`**。它会绕过 automount 的惰性语义，在开机时对真实 `.mount` 单元建立硬依赖并立即挂载；USB 冷插枚举（实测 13~17 s）慢于 device-timeout 时设备 job 超时，mount 单元以 `dependency` 失败，并连带录制服务一起失败。`Restart=` 只对服务自身失败生效，对 `dependency` 失败无效，于是服务从开机起永久死亡，只能手动 start。2026-09 起每次冷启动必现，表现为"出海没录上"。
- 正确机制是让 unit 内的 fail-fast 检查真正起作用：`ExecStartPre` 先触碰挂载点触发 automount（设备未就绪时阻塞至 device-timeout），随后 `mountpoint -q` 与 `test -w` 确认真实挂载与可写；失败交给 `Restart=always` 重试。盘未插时服务以约 40 s 周期持续重试，中途插盘即可自动开始录制，无需重启服务。
- `TimeoutStartSec=120` 为首次触发等待留余量；`KillSignal=SIGINT`、`TimeoutStopSec=90` 保证停服务时 mcap 正常 finalize。

2026-10-06 修复记录：删除 `RequiresMountsFor`、新增触发用 `ExecStartPre`、device-timeout 5 s→30 s。验证为冷启动 `reboot` 后不做任何手动挂载，服务 `active` 且 `NRestarts=0`，新 `usv_run_*` 目录自动生成。改动前后文件备份于 `~/usv_backups/20261006_record_mount_fix_01/`。排查时注意：树莓派无 RTC，冷启动后时钟未同步前 journal 时间戳沿用上次关机时间，日志日期不可直接当真。

## 10. MAVLink 帧录制实测验收（2026-11-11）

本节记录本方案实际入包结果。计划期的只读发现不是录制成功证据，以下数据均来自封口 MCAP 的离线反序列化。

### 10.1 部署入口与维护窗口改动

| 项目 | 现状 |
|---|---|
| 录制入口 | `usv-record.service` → `record.launch.py`，单一 recorder，实时 MCAP，`cache=0`、不分卷，输出 `/mnt/usv_bags` |
| 话题资源 | `install/usv_bringup/share/usv_bringup/config/` 三份 YAML 与 `src/` 同步修改 |
| DDS 修复 | `~/.ros/fastdds_lan.xml` 白名单由 `lo,eth0` 改为 `eth0,enx889e96164bd0`；备份 `~/.ros/fastdds_lan.xml.bak_20261111-2240` |
| MAVROS | `plugin_denylist` 追加 `sys_time`（见 10.4）；备份在 `~/usv_bringup_config_backup_20261111-223334/` |

`lo` 必须从白名单移除：FastDDS 在同时列入 `lo` 与任一物理网卡时，新建 reader 会报 `No unicast locators to create unique flows` 并拿不到数据；实测 `eth0+enx889e96164bd0` 组合正常。切换后 MAVROS 的 DDS socket 才会从已消失的 `<PI_DIRECT_IP>` 重新绑定到当前活动网卡。

### 10.2 封口验收包

`/mnt/usv_bags/usv_run_20261111_225441`

| 指标 | 值 |
|---|---|
| 时长 | 128.6 s |
| 消息总数 | 6386 |
| bag 大小 | 1.5 MiB |
| 方向 | 入站 3376 帧，出站 1460 帧（**含两个入站发布端，总速率不可直接当作采样率**，见 10.3） |
| `framing_status` | 全部为 1 (FRAMING_OK) |
| 帧长度自洽 | 4836/4836（v1 `8+len`，v2 `12+len+sig`） |
| 载荷长度 | 截断感知校验 0 违规：`len ≤ 规范全长` 且被截掉的尾部字节全为 0（MAVLink 合法的尾零截断） |
| 签名 | `signature` 长度恒为 0（未启用签名，FRAMING_OK 不代表已认证） |

验收后已恢复同一服务持续录制，当前活动包：`/mnt/usv_bags/usv_run_20261111_225756`。

### 10.3 发布端、方向与序号

必须按完整键 `(frame_id, sysid, compid)` 分组统计。合并统计会把两个入站发布端混成一个速率，是错误做法。

| 方向 | 完整键 | 帧数 | 总速率 | HEARTBEAT | `magic` |
|---|---|---|---|---|---|
| source | `('ep:1000', 1, 1)` 飞控 | 3166 | 24.67 Hz | **1.01 Hz** | 254 为主，另有 253 |
| source | `('ep:1000', 255, 190)` **来源未确认** | 210 | 1.64 Hz | 1.00 Hz | — |
| sink | `('mavros', 255, 191)` MAVROS UAS | 1460 | 11.49 Hz | 1.01 Hz | 253 |

**序号观测（仅陈述统计，不推断成因）**：

| 键 | 序号步长直方图 | 说明 |
|---|---|---|
| source `1.1` | `{1: 3165}` | 本包内 3165 次转移全部 +1 |
| source `255.190` | `{1: 197, 3: 9, 5: 2, 8: 1}` | 15 次非 +1 转移 |
| sink `255.191` | `{1: 1444, 2: 10, 255: 5}` | 15 次非 +1 转移 |

`1.1` 在本包内步长全为 +1 是**观测事实**；它**不构成零丢失保证**——本链路是 BEST_EFFORT，且只覆盖树莓派 UAS 端点看到的帧，不能排除端点之前/之后的丢失。sink 的 `{2,255}` 步长与 source `255.190` 的 `{3,5,8}` 步长的**成因未在本任务中确定**，不要归因为"按速率抽取"。

**发布端身份**：实测 sink 只有一个身份 `255.191`；`255.190` **只出现在 source**，本任务没有证据说明它是什么（不要写成"MAVROS 回环"或自造 TIMESYNC 自回声机制）。分析时必须单独分组；把两者合并会得出错误的总速率与 HEARTBEAT 计数。

**时间覆盖**：按各自 FCU boot 时间字段检查，各消息 128 个样本、标称间隔 1001.7 ms、最大 1022.0 ms，**超过 2× 标称的间隔为 0 次**。据此只能说本包内没有观测到该量级的采集空档，不足以推出"真实下传速率"或"没有丢帧"。

### 10.4 已知阻塞：飞控 SYSTEM_TIME 触发 MAVROS abort

飞控重启后会发出 `SYSTEM_TIME.time_unix_usec = 3155760742730791`（≈2070 年）。该值通过 MAVROS 的“时间有效”判断（`> 1234567890 s`），但 `sec = 3155760742 > INT32_MAX`，被转成负 `int32` 后 `rclcpp::Time` 抛出 `cannot store a negative time point in rclcpp::Time`，`abort()`。MAVROS 启动约 5 s 即死，`/uas1/mavlink_*` 永远没有发布端。

- 该崩溃在改动前已存在（2026-11-11 22:37:28 首次复现），不是本次配置引入。
- `timesync_mode` **无法**规避：`SystemTimePlugin::get_subscriptions()` 无条件注册 `SYSTEM_TIME` handler。
- 现采用 `plugin_denylist` 追加 `sys_time` 规避。本工作区没有订阅 `/mavros/time_reference` 或 `/mavros/timesync_status`，停用该插件不影响其他功能；副作用是不再做飞控时间同步。
- **根治应在飞控侧**（GPS 时间/`SYSTEM_TIME` 来源），或在上游给 `rclcpp::Time` 加范围检查。恢复 `sys_time` 前必须先确认飞控不再发出越界时间。

### 10.5 参数辨识覆盖与实测频率（按实测消息 ID）

速率均为飞控发布端 `('ep:1000', 1, 1)` 单独统计，不与其他发布端合并。

| 辨识要素 | 实测消息 | 采样率 | 实测值样例 | 覆盖判定 |
|---|---|---|---|---|
| 姿态 | `ATTITUDE`(30) | 1 Hz | roll=0.0060 pitch=0.0037 yaw=−0.0004 rad | 有；`ATTITUDE_QUATERNION`(31) **本次完全未出现** |
| 姿态扩展 | `AHRS`(163) / `AHRS2`(178) | 1 Hz | — | 有 |
| 位置/速度 | `LOCAL_POSITION_NED`(32) | 1 Hz | x=−0.00 y=0.00 z=−0.03 m，vx=vy=vz≈0 | 有 |
| 全局位置 | `GLOBAL_POSITION_INT`(33) | 1 Hz | lat=30.8877999 lon=121.8954999 alt=4030 mm | 有；`hdg` 是 `uint16` cdeg，实测 35998 → 359.98°（按 `int16` 解会误得 −295.38°） |
| GPS 质量 | `GPS_RAW_INT`(24) | 1 Hz | fix_type=**5 (RTK Float)**, sats=24, eph=0.60 m | 有 |
| IMU | `RAW_IMU`(27) / `SCALED_IMU2`(116) | 1 Hz | xacc=−4 yacc=3 zacc=−1000 mG | 有，频率低 |
| 舵机输出 | `SERVO_OUTPUT_RAW`(36) | 1 Hz | servo1=1500 servo2=0 servo3=1500 servo4=0 µs | 有，静止中立位 |
| RC 输入 | `RC_CHANNELS`(65) / `RC_CHANNELS_RAW`(35) | 1 Hz | ch1..4 全 0，rssi=0 | 有；**无遥控输入**（未接/未开） |
| 电池 | `SYS_STATUS`(1) | 1 Hz | 12.130 V, 0.22 A, load 0% | 有 |
| 电池(扩展) | `POWER_STATUS`(125) / `BATTERY_STATUS`(147) | 1 Hz | 147 的 `voltages` 全为 65535（无效哨兵）；pct=86 | 147 电压字段不可用，改用 SYS_STATUS |
| 压力 | `SCALED_PRESSURE`(29) | 1 Hz | — | 有 |
| 振动 | `VIBRATION`(241) | 1 Hz | — | 有 |
| RTCM | `GPS_RTCM_DATA`(233) 在 sink | 7.46 Hz | 载荷 27–182 B 可变；`fragment_id=(flags>>1)&3` 实测仅 0/1，`sequence_id=(flags>>3)&0x1F` 覆盖 0–31 | 有；**帧在 sink，不是串口抓包** |
| 飞控时间 | `SYSTEM_TIME`(2) | 1 Hz | `boot_time_ms` 9598005→9725005，单调 | 仅取 boot 时间可用；`time_unix_usec` 为 ≈2070 年，不可用 |
| 方案 A 控制指令 | `/mavros/setpoint_velocity/cmd_vel` | 0 Hz | — | 本次 `disarmed`+STANDBY，**无数据** |
| 方案 B 控制指令 | `/mavros/rc/override` | 0 Hz | — | 方案 B 未发 override，**无数据** |

`MISSION_ITEM_INT`(73) 2 Hz、`MISSION_REQUEST_INT`(51) 2 Hz、`GPS_RTCM_DATA` 7.46 Hz，其余均为 1 Hz。

**时间字段一致性**：`ATTITUDE`/`LOCAL_POSITION_NED`/`GLOBAL_POSITION_INT`/`RC_CHANNELS`/`SYSTEM_TIME.boot_time_ms` 以及 `GPS_RAW_INT`/`RAW_IMU.time_usec` 属**同一 FCU 上电纪元**（9598005→9725005 ms），单调无回退，可直接互相对齐。

**`SERVO_OUTPUT_RAW` 的 `time_usec` 是 u32 µs，本包已回绕 2 次**：`1008070695 + 2×2³² = 9598005287 µs = 9598005.287 ms`，与 `ATTITUDE` 的 `9598005 ms` 相差 **+0.287 ms**；回绕后单调。不减回绕直接比较会得出约 **−2.4 h** 的假偏移（若再错减一次得到 1193 h，是双错误）。对齐前必须展开，且 `k` 要按 µs/ms 单位一致推导。

**结论边界**：1 Hz 的 `ATTITUDE`/`LOCAL_POSITION_NED` 不足以做高频参数辨识；本次未进入 ACTIVE，两个控制指令话题均无数据，因此**本次数据不能建立控制输入—输出关系**。`RC_CHANNELS` 无输入、`BATTERY_STATUS.voltages` 无效，相关辨识也缺输入。要提高辨识质量需在飞控侧调整 SRx 流率（本任务未做），或改用飞控 BIN 日志补齐未下传的高频内部量。

### 10.6 时间与存储

| 检查 | 结果 |
|---|---|
| 帧 `header` vs bag 接收时间 | 中位 −0.1 ms / −0.2 ms，最大 −6.4/−8.8 ms（header 略早，属正常发布路径） |
| source `header` 回拨 | 0 次 |
| sink `header` 回拨 | **5 次**（偏移 −148 ns ~ −175 908 ns，成因未确定） |
| 同消息内采样间隔 | 标称 1001.7 ms，最大 1022.0 ms，>2× 间隔 **0 次** |
| 跨消息 FCU 纪元 | 6 类消息同为 9598005→9725005 ms，单调无回退 |
| FCU 与机载时钟关系 | 飞控 `SYSTEM_TIME.time_unix_usec` ≈2070 年，**不能用它对齐机载时间**；只能用 boot 相对量 |
| 写盘速率 | 1 513 342 B / 128.5997 s ≈ **0.67 MiB/min** |
| SSD 剩余 | 25 GiB（`/dev/sda1`，17% 已用） |
| 粗估可录时长 | ≈ **26 天**（25 GiB ÷ 0.67 MiB/min ≈ 26.4 天） |

三条时间轴必须分开使用：**bag 接收时间**（ROS 墙钟，用于跨话题对齐）、**帧 `header` 时间**（发布时刻，略早于接收）、**载荷内 FCU boot/usec**（设备侧，唯一可与飞控内部量对齐的轴）。不要用 ROS 时间差声称测出了串口延迟，也不要假定飞控墙钟可用。

该估算**仅在该实测工况下成立**（静止、1 Hz 消息流、无 ACTIVE 控制段）。出海时消息率与控制频率上升会线性增加写入量；不要沿用旧的“数百天”估算，也不要把 26 天当作恒定值。

### 10.7 复测命令

```bash
source /opt/ros/jazzy/setup.bash
ros2 bag info /mnt/usv_bags/<run>
```

`ros2 bag info` 只读元数据。消息内容必须用 `rosbag2_py.SequentialReader` 反序列化后再判定，不能只看 topic 清单。离线验收至少覆盖：

1. **按完整键分组**统计 `(frame_id, sysid, compid)` 的速率与消息 ID 分布，禁止把多个发布端合并；不要把 sink 的发送速率当作采样率。
2. **载荷长度截断感知校验**：`len ≤ 规范全长` 且被截断的尾部字节全为 0；`GPS_RTCM_DATA`(233) 为变长，不能套用固定长度。
   所有字段类型/偏移**必须取自生成头文件**（`/opt/ros/jazzy/include/mavlink/*/mavlink_msg_*.h` 的 `MAVLINK_TYPE_*` 与 offset），不要凭印象：本轮已因此错过三处 —— `hdg` 是 `uint16`（当 `int16` 会解出 −295.38° 这种假值）、`GPS_RTCM_DATA.fragment_id=(flags>>1)&3`（写成 `>>5` 会得出 0–27 的假范围）、`SERVO_OUTPUT_RAW.time_usec` 回绕次数按 µs/ms 混算会多算一次。
3. **载荷值抽样**：确认 `ATTITUDE`/`LOCAL_POSITION_NED`/`GPS_RAW_INT`/`SERVO_OUTPUT_RAW` 等字段能解出合理量纲，而不是只看计数。
4. **时间轴**：分别检查 bag 接收时间、帧 `header` 时间、载荷内 FCU boot/usec 三轴，报告回拨与异常段。
5. **u32 时间回绕**：`SERVO_OUTPUT_RAW.time_usec` 是 u32 µs，本包已回绕 2 次（+2×2³² µs 后与 `ATTITUDE` 纪元差 0.287 ms）；直接用会得到约 −2.4 h 的假偏移，对齐前必须展开。

未覆盖的方向或消息必须如实报告为“未实测”，不能用 `FRAMING_OK` 或“话题在清单里”代替。
