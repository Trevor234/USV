# 2026-10-09 RTK 差分注入修复与联调记录

> - 日期：2026-10-09
> - 范围：`usv_bringup`（ntrip.launch.py / setup.py / 新增 fix_qos_relay.py）
> - 环境：树莓派 `~/usv_mpc_ws_B`（部署机）+ 本地 `usv_mpc_ws`（开发机，已同步）
> - 结果：**RTCM 注入链路全通，GPS 达到 RTK Float（fix_type=5）**

## 问题

1. **NTRIP 客户端未运行**：`usv-system.service` 启动时 `ntrip.launch.py` 有被拉起（TimerAction 5s），
   但旧 CORS 账号（<OLD_CORS_ACCOUNT>）已被服务商停用，caster 返回 HTTP 401，`ntrip_ros.py`
   exit code 1 退出，launch 无 respawn，之后无人重启 → `/mavros/gps_rtk/send_rtcm` 无发布者。
2. **QoS 不兼容（修复账号后暴露）**：新账号认证通过（ICY 200 OK）后仍无差分数据。
   根因：MAVROS `/mavros/global_position/raw/fix` 发布端是 **BEST_EFFORT**，
   `ntrip_client`(LORD 1.4.0) 的 `fix` 订阅是 **RELIABLE** 且未在代码里启用
   rclpy `qos_overriding_options` → 参数表（yaml `qos_overrides`）**无法覆盖**，
   GGA 上报被 DDS QoS 不兼容静默丢弃 → VRS 不生成差分流 → 空读 5 次反复重连。

## 修复

1. **凭据更新**：`config/ntrip_params.yaml` 换新账号（<CORS_PROVIDER>，有效期至 2026-10-10 00:00，
   到期前需续费或换号——改 yaml 后重启 ntrip 即可）。
2. **QoS 中继**：新增 `usv_bringup/fix_qos_relay.py`（BEST_EFFORT 订阅 raw/fix →
   RELIABLE 发布 `/fix_for_ntrip`），`ntrip.launch.py` 默认把 ntrip 的 `fix`
   remap 到中继话题，launch 自动拉起中继。setup.py 增加 entry_points
   `fix_qos_relay`。已在部署机 colcon build + 一键 launch 验证。
3. yaml 里保留的 `/**` 通配 `qos_overrides` 段对 rclpy 无效（仅 rclcpp 支持
   自动应用），不删但注释说明，真正生效的是中继。

## 验证证据（部署机实测）

- `/mavros/gps_rtk/send_rtcm` ≈ 5 Hz（30 秒 164 条 RTCM 消息）
- MAVROS→飞控方向抓到 **msgid 233（GPS_RTCM_DATA）**、len 182 字节帧
- `/mavros/gpsstatus/gps1/raw` 的 `fix_type` 从 3（单点）→ **5（RTK Float）**
- ArduPilot 侧参数：GPS1_TYPE=5、GPS1_COM_PORT=1（SERIAL1）、GPS_INJECT_TO=127、
  GPS_AUTO_CONFIG=1 —— 飞控消费 RTCM 的通路本来就在，只差数据进来

## 遗留

- **Float↔单点波动**：重启注入期间 fix_type 会回落到 3，恢复后 1-2 分钟内重回 5。
  实测尚未到 Fixed(6)：多路径/遮挡环境 + 11 颗可用星是主因（船在室内/棚区）。
  到开阔水域、天空视野良好时再看能否上 Fixed；到不了 Fixed 也可先用 Float
  （分米级）跑任务。
- `dgps_age` 恒 65535/4294967295：GPS 模块不上报差分龄期，属 ArduPilot/模块行为，不影响解算。
- **账号 2026-10-10 00:00 到期**，续费后只需改 `ntrip_params.yaml` 的
  username/password（install 是符号链，改 src 即生效），再重启 ntrip launch。
- 服务化后 `usv-system.service` 重启会自动带起 ntrip（real.launch.py 的
  use_ntrip 默认 true + TimerAction 5s），无需手工干预。

## 同步状态

- 部署机 `~/usv_mpc_ws_B/src/usv_bringup`：launch / setup.py / 新包目录 / 凭据 已改，已 build
- 开发机 `usv_mpc_ws/src/usv_bringup`：launch / setup.py / fix_qos_relay.py / 凭据 已同步，已 build
- 两侧均验证 `ros2 pkg executables usv_bringup` 输出 `fix_qos_relay`
