# USV MPC 控制系统 (usv_mpc_ws)

面向 1.2 m / 14.2 kg 双推进器(差速)无人水面艇(USV)的 **ROS 2 Jazzy** 实船控制工作区:
运动学 MPC(方案 A, `usv_mpc`, acados SQP) + 动力学 NMPC(方案 B, `usv_nmpc`, acados SQP_RTI),
统一由 `usv_acados` 后端库驱动, 彻底消除对外部 CasADi 的运行时依赖。

> 注: 原开发机 VRX Gazebo / ArduPilot SITL 仿真入口及相关仿真资产已清理, 本仓库专注于树莓派 5 实机部署与控制器/规划/安全栈。

## 包结构

| 包 | 说明 |
|:---|:---|
| `usv_acados` | **共用 acados 后端**: 提供 `libusv_acados_backend.so` 与 vendored C 生成码, 封装方案 A (运动学 SQP+0.12s) 与方案 B (动力学 SQP_RTI) 独立 OCP |
| `usv_nmpc` | **动力学 NMPC(方案 B)**: Fossen 3-DOF 动力学 + `usv_acados` 后端; 输出 `rc_override` (左右推力分配) |
| `usv_mpc` | **运动学 MPC(方案 A)**: 运动学模型 + `usv_acados` 后端; 输出 `cmd_vel` (线速度 / 角速度指令) |
| `usv_planning` | 任务桥接(GPS→ENU)、圆弧倒角 + TOPP 速度剖面 |
| `usv_safety` | 模式管理 + 安全监控(围栏/电池/求解器/看门狗 failsafe → HOLD) |
| `usv_bringup` | Python (`ament_python`) launch(`real/mavros/ntrip/record`)、QoS 中继与全部 YAML 配置 |


## 两个控制方案

| | 方案 A(运动学 MPC) | 方案 B(动力学 NMPC) |
|:---|:---|:---|
| 状态 | `[x, y, ψ]` | `[x, y, ψ, u, v, r]` |
| 控制量 | `[u_surge, r_yaw]` | `[T_L, T_R]`(推力) |
| 实现 | `usv_mpc` (acados NONLINEAR_LS) | **`usv_nmpc`** (acados SQP_RTI) |
| 输出 | `cmd_vel`(GUIDED) | RC override(MANUAL) |
| 参数 | `mpc_params_A.yaml` + `usv_params_A.yaml` | `mpc_params_B.yaml` + `usv_params_B.yaml`(真船) |

## 构建

```bash
cd ~/usv_mpc_ws
colcon build --symlink-install
source install/setup.bash
```

控制/规划/安全包依赖:
- `sudo apt install libeigen3-dev nlohmann-json3-dev`
- **acados**: 源码编译到 `~/acados`(v0.5.4)。国内网络可走代理:
  ```bash
  git clone -b v0.5.4 --depth 1 https://ghfast.top/https://github.com/acados/acados.git ~/acados
  cd ~/acados && git config url."https://ghfast.top/https://github.com/".insteadOf "https://github.com/"
  git submodule update --init --recursive external/blasfeo external/hpipm external/jsonlab interfaces/acados_template/tera_renderer
  cmake -S . -B build -DACADOS_WITH_OPENMP=OFF -DACADOS_EXAMPLES=OFF -DACADOS_UNIT_TESTS=OFF
  cmake --build build -j $(nproc) && (cd build && make install)
  ```

## 实机运行

AET-H743-AIR-PRO / ArduRover,UART `/dev/ttyAMA10` @ 921600:

```bash
ros2 launch usv_bringup real.launch.py                # scheme:=B 默认(动力学 NMPC)
ros2 launch usv_bringup real.launch.py scheme:=A      # 运动学 MPC
```

完整部署/录包/RTK 注入说明见 `docs/pi5_deploy.md`、`docs/bag_recording.md`、`docs/pi_fcu_link_dataflow.md`。

## 测试

```bash
colcon build --symlink-install && source install/setup.bash
colcon test && colcon test-result --verbose           # pytest + gtest
```

运动学测试见 `src/usv_mpc/test/`。

## 配置

| 文件 | 内容 |
|:---|:---|
| `mpc_params_A.yaml` / `mpc_params_B.yaml` | 方案 A/B 实机参数(`scheme` 切换时由 `real.launch.py` 选择) |
| `usv_params_A.yaml` / `usv_params_B.yaml` | **真船**水动力学(14.2 kg / 1.2 m,2026-07-23 / 2026-09-03 辨识) |
| `path_config.yaml` | 圆弧倒角半径、TOPP 限制(规划可行域 ⊆ 控制可行域) |
| `safety_params.yaml` | 围栏/电池/求解器/看门狗阈值 |
| `power_monitor_params.yaml` | WeAct 功率计电池驱动 (串口/轮询/电池参数, 发布 `/usv/battery`) |
| `ntrip_params.yaml` | CORS 差分数据源(RTK,未入库;由 `ntrip_params.yaml.example` 复制) |
| `topic_contract.yaml` | 全系统话题契约(话题名/类型/QoS 与 path/profile 时间同步约定) |

## 工具脚本与文档

- `scripts/smoke_check_topics.sh real [A|B]` —— 实机话题冒烟检查
- `scripts/analyze_usv_bag.py` —— 离线 rosbag2 分析与绘图

## 仓库文档

- [docs/pi5_deploy.md](docs/pi5_deploy.md) —— Pi5 实机部署(acados 源码编译、依赖、构建)
- [docs/pi_fcu_link_dataflow.md](docs/pi_fcu_link_dataflow.md) —— 树莓派 ↔ 飞控链路与数据流解析
- [docs/bag_recording.md](docs/bag_recording.md) —— 实机 MCAP 录包与 MAVLink 帧录制
- [docs/mavlink_frame_recording_changes.md](docs/mavlink_frame_recording_changes.md) —— MAVLink 双向帧录制变更与排查总结
- [docs/runbook.md](docs/runbook.md) —— 运维手册
- [docs/topic_contract.md](docs/topic_contract.md) —— 话题契约说明
