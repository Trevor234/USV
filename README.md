# USV MPC 控制系统 (usv_mpc_ws)

面向 1.2 m / 14.2 kg 双推进器(差速)无人水面艇(USV)的 **ROS 2 Jazzy** 实船控制工作区:
运动学 MPC(方案 A,C++ `usv_mpc_kinematic_cpp`,CasADi/IPOPT)+ 动力学 NMPC(方案 B,C++ `usv_mpc_cpp`,
acados SQP_RTI + CasADi fallback)。

> 注: 原开发机 VRX Gazebo / ArduPilot SITL 仿真入口及相关仿真资产已清理, 本仓库专注于树莓派 5 实机部署与控制器/规划/安全栈。

## 包结构

| 包 | 语言 | 说明 |
|:---|:---|:---|
| `usv_mpc_cpp` | C++ | **动力学 NMPC(方案 B)**:Fossen 3-DOF + acados SQP_RTI(vendored codegen)+ CasADi fallback;输出后端 `rc_override` |
| `usv_mpc_kinematic_cpp` | C++ | 运动学 MPC 的 C++ 版(方案 A 实机用) |
| `usv_planning_cpp` | C++ | 任务桥接(GPS→ENU)、圆弧倒角 + TOPP 速度剖面 |
| `usv_safety_cpp` | C++ | 模式管理 + 安全监控(围栏/电池/求解器/看门狗 failsafe → HOLD) |
| `usv_bringup` | Python | launch(`real/mavros/ntrip/record`)、QoS 中继与全部 YAML 配置 |

> 注: Python 版 `usv_planning` / `usv_safety` / `usv_mpc` 包已于 2026-09
> 删除, 现在全部为 C++ 实现 (`*_cpp`)。


## 两个控制方案

| | 方案 A(运动学) | 方案 B(动力学 NMPC) |
|:---|:---|:---|
| 状态 | `[x, y, ψ]` | `[x, y, ψ, u, v, r]` |
| 控制量 | `[u_surge, r_yaw]` | `[T_L, T_R]`(推力) |
| 实现 | C++ `usv_mpc_kinematic_cpp`(CasADi/IPOPT) | **C++ `usv_mpc_cpp`**(acados SQP_RTI + CasADi fallback) |
| 输出 | `cmd_vel`(GUIDED) | RC override(MANUAL) |
| 参数 | `mpc_params_A.yaml` + `usv_params_A.yaml` | `mpc_params_B.yaml` + `usv_params_B.yaml`(真船) |

## 构建

```bash
cd ~/usv_mpc_ws
colcon build --symlink-install
source install/setup.bash
```

C++ 包(`usv_mpc_cpp` 等)依赖:
- `sudo apt install libeigen3-dev nlohmann-json3-dev`
- **acados**:源码编译到 `~/acados`(v0.5.4)。国内网络可走代理:
  ```bash
  git clone -b v0.5.4 --depth 1 https://ghfast.top/https://github.com/acados/acados.git ~/acados
  cd ~/acados && git config url."https://ghfast.top/https://github.com/".insteadOf "https://github.com/"
  git submodule update --init --recursive external/blasfeo external/hpipm external/jsonlab interfaces/acados_template/tera_renderer
  cmake -S . -B build -DACADOS_WITH_OPENMP=OFF -DACADOS_EXAMPLES=OFF -DACADOS_UNIT_TESTS=OFF
  cmake --build build -j $(nproc) && (cd build && make install)
  ```
- CasADi C++ fallback 后端自动从 `pip install casadi` 的 wheel 中定位(`casadi/include/casadi.hpp`)。

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
colcon test && colcon test-result --verbose           # pytest + gtest(C++ 包需构建成功)
```

> 注: Python 方案 A 包 `usv_mpc` 已删除(2026-09-06), 其独立 CasADi 脚本随之移除;
> C++ 运动学测试见 `src/usv_mpc_kinematic_cpp/test/`。

## 配置

| 文件 | 内容 |
|:---|:---|
| `mpc_params_A.yaml` / `mpc_params_B.yaml` | 方案 A/B 实机参数(`scheme` 切换时由 `real.launch.py` 选择) |
| `usv_params_A.yaml` / `usv_params_B.yaml` | **真船**水动力学(14.2 kg / 1.2 m,2026-07-23 / 2026-09-03 辨识) |
| `path_config.yaml` | 圆弧倒角半径、TOPP 限制(规划可行域 ⊆ 控制可行域) |
| `safety_params.yaml` | 围栏/电池/求解器/看门狗阈值 |
| `ntrip_params.yaml` | CORS 差分数据源(RTK,未入库;由 `ntrip_params.yaml.example` 复制) |
| `topic_contract.yaml` | 跨语言话题契约(C++/Python 节点混搭的 JSON/stamp 约定) |

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
