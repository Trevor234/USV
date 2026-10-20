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

默认记录：

- `/mavros/local_position/odom`
- `/mavros/imu/data`
- `/mavros/state`
- `/mavros/rc/override`
- `/mpc/status`
- `/path/reference`
- `/path/reference_profile`
- `/usv/mission/waypoints_local`
- `/mpc/predicted_trajectory`

话题列表位于 `config/bag_topics.yaml`，类型和语义以 `config/topic_contract.yaml` 为准。odom 和 IMU 发布端使用 SensorDataQoS，recorder 通过 `config/rosbag_qos_overrides.yaml` 以 best-effort 订阅，避免 QoS 不兼容导致静默漏录。

存储使用 MCAP 的 `zstd_fast` preset，即 MCAP 内部 Zstd chunk 压缩。不要额外添加 rosbag2 transport 的 `--compression-mode` 或 `--compression-format`，否则会双重压缩并增加 Pi5 负载。

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

建议在开发机上回放，不要在连接实船执行器的控制图中直接回放 `/mavros/rc/override`：

```bash
ros2 bag play /path/to/lake_test_20260817_153012
```

只回放分析所需话题：

```bash
ros2 bag play /path/to/lake_test_20260817_153012 \
  --topics /mavros/local_position/odom /mavros/imu/data /mpc/status
```

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
PPO_MODEL=/home/trevor/USV/usv_rl/models/v5/s4_dr/policy_physical_n.onnx
PPO_MANIFEST=/home/trevor/USV/usv_rl/models/v5/s4_dr/policy_physical_n.manifest.json
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
