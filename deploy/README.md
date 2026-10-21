# 树莓派 5 部署配置

本目录存放**不在 ROS 包内、但实机运行必需**的配置。原先它们只存在于
Pi 的文件系统里（`/etc/systemd/system/` 与 `~/.ros/`），重装时必须靠人工
回忆重建。2026-10-21 审查后纳入版本控制。

## systemd/

| 文件 | 部署位置 | 说明 |
|---|---|---|
| `usv-system.service` | `/etc/systemd/system/` | 控制系统（方案 A/B 由 `/etc/default/usv-system` 的 `SCHEME` 切换） |
| `usv-record.service` | `/etc/systemd/system/` | rosbag2 录制，独立服务，**刻意不依赖** usv-system |
| `usv-system.default` | `/etc/default/usv-system` | `SCHEME=A` |

### 关键设计约束（改动前务必读）

**usv-record 不能加 `Requires=`/`BindsTo=` usv-system**
：录制属于旁挂功能，不能因为录制失败反过来拖死控制栈。

**usv-record 不能加 `RequiresMountsFor=/mnt/usv_bags`**
：会绕过 fstab 的 `x-systemd.automount` 惰性挂载，在开机时强制真实挂载，
与 USB 冷插枚举（实测 13~17s）竞速；而 `Restart=` 对 dependency 失败无效，
服务将永不启动（2026-10-06 定位）。挂载等待放在 `ExecStartPre` 里触发
automount，失败由 `Restart=always` 兜底。

**录制不通过 `real.launch.py record:=true` 启动**
：早期这样做会连带拉起第二套 mavros，与 usv-system 抢 `/dev/ttyAMA10`
串口，导致 MAVLink 帧损坏。

## ros/

| 文件 | 部署位置 | 说明 |
|---|---|---|
| `fastdds_lan.xml` | `~/.ros/` | DDS 只走 lo + eth0，排除 wwan0（5G）。否则 wwan0 的 10.x/8 地址会被 FastDDS 通告为回程单播定位符，数据发进蜂窝口黑洞 |
| `mcap_realtime.yaml` | `~/.ros/` | MCAP `noChunking` 实时落盘。默认 zstd_fast 有 768KB chunk 缓冲，700B/s 下要 18 分钟才 flush，断电丢数据 |

### 部署命令

```bash
sudo cp deploy/systemd/usv-system.service deploy/systemd/usv-record.service \
        /etc/systemd/system/
sudo cp deploy/systemd/usv-system.default /etc/default/usv-system
sudo systemctl daemon-reload

mkdir -p ~/.ros
cp deploy/ros/fastdds_lan.xml deploy/ros/mcap_realtime.yaml ~/.ros/
```

## 变更记录

- 2026-10-21：首次纳入版本控制（原仅存于 Pi 文件系统）
