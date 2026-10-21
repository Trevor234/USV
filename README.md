# USV MPC 控制系统 — 开发工作区 (usv_mpc_ws)

面向 1.2 m / 14.2 kg 双推进器(差速)无人水面艇(USV)的 **ROS 2 Jazzy** 工作区。

**算法栈与部署工作区 `usv_mpc_ws_B`(Pi5 实机)完全同源**(2026-09-04 以 B 为准同步):
运动学 MPC(方案 A,Python,CasADi/acados 双后端)+ 动力学 NMPC(方案 B,C++,acados SQP_RTI,
CasADi fallback)。本工作区在 B 的基础上额外保留并维护**开发专用能力**:VRX Gazebo 仿真、
ArduPilot SITL 联调、参数辨识工具链。

## 与 usv_mpc_ws_B(Pi5 部署)的关系

| 项 | 本工作区(开发) | usv_mpc_ws_B(Pi5 部署) |
|---|---|---|
| 算法(控制器/规划/安全) | **同源,以 B 为准** | 上游(source of truth) |
| VRX/Gazebo 仿真 | ✅ `sim/sitl/vrx.launch.py` | ❌(仅 matplotlib 可视化) |
| 仿真船参数 | `usv_params_sim.yaml`(30 kg 单体船) | — |
| 真船参数 | `usv_params*.yaml`(14.2 kg,2026-07-23 辨识) | 同左 |
| 参数辨识工具链 | ✅ `参数识别/` | ❌ |
| acados | x86 源码编译(`~/acados`) | aarch64 源码编译 |
| 部署文档 | 参考 B 的 `docs/pi5_deploy.md` | ✅ |

> 修改算法后若要部署实机,请把改动**回移**到 `usv_mpc_ws_B` 并在那边验证;本工作区只做开发与仿真验证。

## 包结构

| 包 | 语言 | 说明 |
|:---|:---|:---|
| `usv_mpc_cpp` | C++ | **动力学 NMPC(方案 B)**:Fossen 3-DOF + acados SQP_RTI(vendored codegen)+ CasADi fallback;输出后端 `rc_override`(实机)/`vrx_thrust`(VRX 仿真) |
| `usv_mpc_kinematic_cpp` | C++ | 运动学 MPC 的 C++ 版(方案 A 实机用) |
| `usv_planning_cpp` | C++ | 任务桥接(GPS→ENU)、圆弧倒角 + TOPP 速度剖面 |
| `usv_safety_cpp` | C++ | 模式管理 + 安全监控(围栏/电池/求解器/看门狗 failsafe → RTL) |
| `usv_simulation` | Python | matplotlib 实时可视化 + telemetry bridge(无 Gazebo 依赖) |
| `usv_bringup` | — | launch(`real/mavros/ntrip/record/sim/sitl/vrx`)+ 全部 YAML 配置 |

> 注: Python 版 `usv_planning` / `usv_safety` / `usv_mpc` 包已于 2026-09
> 删除, 现在全部为 C++ 实现 (`*_cpp`)。


## 两个控制方案

| | 方案 A(运动学) | 方案 B(动力学 NMPC) |
|:---|:---|:---|
| 状态 | `[x, y, ψ]` | `[x, y, ψ, u, v, r]` |
| 控制量 | `[u_surge, r_yaw]` | `[T_L, T_R]`(推力) |
| 实现 | C++ `usv_mpc_kinematic_cpp`(CasADi/IPOPT;2026-09-06 起 Python 版已删除, 方案 A 恒为 C++) | **C++ `usv_mpc_cpp`**(Python 动力学实现已删除) |
| 输出 | `cmd_vel`(GUIDED) | RC override(MANUAL)/ vrx_thrust(仿真) |
| 参数 | `mpc_params_A.yaml` | `mpc_params_B.yaml` + `usv_params_B.yaml`(真船) |

## 构建

```bash
cd ~/USV/usv_mpc_ws
colcon build --symlink-install
source install/setup.bash
```

C++ 包(`usv_mpc_cpp` 等)依赖:
- `sudo apt install libeigen3-dev nlohmann-json3-dev`
- **acados(x86)**:源码编译到 `~/acados`(与 Pi5 同为 v0.5.4)。国内网络可走代理:
  ```bash
  git clone -b v0.5.4 --depth 1 https://ghfast.top/https://github.com/acados/acados.git ~/acados
  cd ~/acados && git config url."https://ghfast.top/https://github.com/".insteadOf "https://github.com/"
  git submodule update --init --recursive external/blasfeo external/hpipm external/jsonlab interfaces/acados_template/tera_renderer
  cmake -S . -B build -DACADOS_WITH_OPENMP=OFF -DACADOS_EXAMPLES=OFF -DACADOS_UNIT_TESTS=OFF
  cmake --build build -j $(nproc) && (cd build && make install)
  ```
- CasADi C++ fallback 后端自动从 `pip install casadi` 的 wheel 中定位(`casadi/include/casadi.hpp`)。

## 仿真

### VRX Gazebo(方案 B,动力学 NMPC 直接推力)

```bash
ros2 launch usv_bringup sim.launch.py                      # 默认 sydney_regatta 世界
ros2 launch usv_bringup vrx.launch.py headless:=True       # 无头
ros2 launch usv_bringup vrx.launch.py record_bag:=True     # 顺带录 bag
```

- MPC 参数:`mpc_params_B.yaml` + `usv_params_sim.yaml`(30 kg 仿真船)+ `mpc_params_vrx.yaml`(overlay,
  `output_mode=vrx_thrust` 直接发布 `/wamv/thrusters/{left,right}/thrust`)。
- 需要本机装好 VRX(`vrx_gz`、`wamv_gazebo`)与 Gazebo;仿真船模型在 `src/usv_simulation/urdf/`。

### ArduPilot SITL(无 Gazebo)

```bash
# 先外部启动 SITL:
sim_vehicle.py -v Rover --map --console --out=tcpin:0.0.0.0:5760
# 方案 A(Python 运动学,GUIDED + cmd_vel):
ros2 launch usv_bringup sitl.launch.py
# 方案 B(C++ NMPC,MANUAL + RC override;需已编译 acados):
ros2 launch usv_bringup sitl.launch.py scheme:=B
```

## 实机运行

与 `usv_mpc_ws_B` 一致(MicoAir743 / ArduRover,UART `/dev/ttyAMA10` @ 921600):

```bash
ros2 launch usv_bringup real.launch.py                # scheme:=B 默认(动力学 NMPC)
ros2 launch usv_bringup real.launch.py scheme:=A      # 运动学 MPC
```

完整部署/录包/RTK 注入说明见 `docs/pi5_deploy.md`、`docs/bag_recording.md`(上游 B 维护)。

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
| `mpc_params_B.yaml` | NMPC 基础参数(真船 25 N 整定,方案 B) |
| `mpc_params_A.yaml` / `mpc_params_B.yaml` | 方案 A/B 实机参数(`scheme` 切换时由 `real.launch.py` 选择) |
| `mpc_params_vrx.yaml` | VRX 仿真 overlay(实船孪生 25 N + `vrx_thrust` 输出) |
| `usv_params_B.yaml` | **真船**水动力学(14.2 kg / 1.2 m,2026-07-23 辨识,sway-yaw 耦合项置零保证开环稳定) |
| `usv_params_A.yaml` / `usv_params_B.yaml` | 方案变体(真船) |
| `usv_params_sim.yaml` | **仿真船**水动力学(30 kg 单体,与 `usv_mono_dynamics.xacro` 一致) |
| `path_config.yaml` | 圆弧倒角半径、TOPP 限制(规划可行域 ⊆ 控制可行域) |
| `safety_params.yaml` | 围栏/电池/求解器/看门狗阈值 |
| `ntrip_params.yaml` | CORS 差分数据源(RTK) |
| `topic_contract.yaml` | 跨语言话题契约(C++/Python 节点混搭的 JSON/stamp 约定) |

> ⚠️ `waypoints/` 目录保留本工作区原有任务航点;`mpc_params_vrx_scheme_b.yaml`(Python 动力学时代的
> overlay)已被 `mpc_params_vrx.yaml` 取代并移除。

## 开发工具链(本工作区特有)

- `参数识别/` —— 2026-07-23 真船参数辨识脚本与结果(`usv_params_B.yaml` 数值的来源)
- `scripts/smoke_check_topics.sh` —— 实机/仿真话题冒烟检查
- `docs/runbook.md` —— 运维手册;`docs/topic_contract.md` —— 话题契约说明(以 `topic_contract.yaml` 为准)

## 仓库文档

- [docs/pi5_deploy.md](docs/pi5_deploy.md) —— Pi5 实机部署(acados 源码编译、依赖、构建)
- [docs/bag_recording.md](docs/bag_recording.md) —— 实机 MCAP 录包(SSD 挂载、话题、回放)
- [docs/runbook.md](docs/runbook.md) —— 运维手册
- [docs/topic_contract.md](docs/topic_contract.md) —— 话题契约说明
- [docs/usv_planning_cpp_tutorial.html](docs/usv_planning_cpp_tutorial.html) —— planning C++ 移植讲解
