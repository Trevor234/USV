# ROS 2 数据记录（rosbag2 + MCAP）

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
