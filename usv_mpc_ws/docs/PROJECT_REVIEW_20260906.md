# USV MPC 项目 Review — 2026-09-06 全景文档

> 写作背景：2026-09-05 ~ 09-06 期间项目经历了密集修改（全栈审查修复、实船数字孪生、
> 控制器对齐整定），共 6 个提交。本文是重新定位文档——**项目是什么、哪些没变、
> 哪些变了、为什么改、怎么验证、怎么回退**。读完本文应能完全恢复对项目的掌控感。

---

## 1. 项目一句话

1.2 m / 14.2 kg 双推进器差动 USV 的 **ROS 2 Jazzy 控制栈**：CasADi/acados 动力学 NMPC
（方案 B）+ fillet/TOPP 路径规划 + 安全监控，VRX Gazebo 仿真已改造为
**实船数字孪生**（2026-09-03 实测辨识参数），实机为 MicoAir743 ArduRover。

## 2. 仓库与工作区布局

```
/home/trevor/USV/                     ← 根仓库 (github.com/Trevor234/USV, main)
├── usv_mpc_ws/                       ← 开发工作区（本 review 的主体, 9 个自研包）
│   ├── src/
│   │   ├── usv_bringup/              launch(7个) + config(13个YAML) — 全栈装配
│   │   ├── usv_mpc/                  运动学 MPC (Python, 方案 A, 开发/回退)
│   │   ├── usv_mpc_cpp/              动力学 NMPC (C++, 方案 B, acados SQP_RTI)
│   │   ├── usv_mpc_kinematic_cpp/    运动学 MPC C++ 版（实机方案 A 用）
│   │   ├── usv_planning(_cpp)/       航点→fillet 圆弧倒角→TOPP 速度剖面
│   │   ├── usv_safety(_cpp)/         mode_manager + safety_monitor (failsafe→RTL)
│   │   └── usv_simulation/           matplotlib 可视化 + VRX 单体船模型(urdf)
│   ├── scripts/analyze_usv_bag.py    ← 新增: rosbag 分析脚本
│   ├── docs/  (fix_log_20260905.md, 本文档, ...)
│   └── params_id/                    参数辨识管线 (脚本+解析数据)
├── vrx_ws/src/vrx_gz, wamv_gazebo... ← VRX 上游（第三方, 未改动*)
├── ardupilot/                        SITL (submodule)
├── install/                          ardupilot_sitl/ardupilot_msgs
└── data/                             (你 09-06 新建)
~/usv_vrx_logs/vrx_twin_circle_001~006 ← 本轮 6 个仿真 rosbag
~/acados/                             acados v0.5.4 (x86, 与 Pi5 同版本)
```

\* 唯一例外：`vrx_ws/.../sydney_regatta.sdf` 曾临时改波浪增益做对照实验，
**已恢复原样**（git 0 改动）。

**已消失的目录**：`usv_mpc_ws_B/`（Pi5 部署工作区）于 09-06 被你删除。
其内容此前已全部同步进本仓库（见 §4）；**车机 192.168.1.220 上的
`~/usv_mpc_ws_B` 仍在**，但其安全包之外的修复需要重新同步。

## 3. 哪些东西没有变（先安心）

| 层面 | 状态 |
|---|---|
| 话题契约（`docs/topic_contract.md`） | 未动 — 所有节点 pub/sub 名字、类型、QoS 与改动前一致 |
| 控制算法结构 | 未动 — Fossen 3-DOF NMPC、acados vendored codegen（N=20, dt=0.2）、CasADi fallback、状态机（STANDBY/ACTIVE/HOLD）全部原样 |
| launch 拓扑 | 未动 — real/sim/sitl/vrx 七个 launch 的节点组成、TimerAction 时序原样（vrx.launch 的参数传递链修过一个装配缺陷，见 §4.4） |
| 包划分 / 双语言架构 | 未动 — 9 包、Python/C++ 成对结构原样 |
| 实机链路 | 未动 — mavros UART 921600、ntrip RTK、record.launch 录包配置原样 |
| 飞控侧 | 未动 — ArduPilot 参数（mav.parm）、EKF3 配置原样 |

**一句话：所有改动集中在"安全链路加固、仿真保真度、控制器参数、工具链"四类，
控制算法本体与系统装配方式没有重构。**

## 4. 变更全景（6 个提交，按主题）

### 4.1 `b6c55eb` — 全栈审查 P0/P1/P2 修复（安全 + 健壮性）

动机：2026-09-05 全栈代码审查发现安全包存在 failsafe 失效的单点故障、
MPC 缺 NaN 防护等 20+ 项问题（分级 P0/P1/P2）。

| 文件 | 改动 |
|---|---|
| `usv_safety/usv_safety/safety_monitor.py` | 电池域与 odom 域解耦（`update_battery()`）；新增 `/mpc/status` 新鲜度看门狗；时间戳全部 `time.monotonic()` |
| `usv_safety/usv_safety/mode_manager_node.py` | JSON 载荷类型防御；armed 门控；服务结果确认回调；人工接管冷却 10 s；RTL 重发上限 |
| `usv_safety_cpp/`（hpp+cpp） | 上述全部的 C++ 镜像 |
| `usv_mpc_cpp/src/mpc_node.cpp` 等 | odom/imu NaN 门禁；三后端解有限性校验；STANDBY status 加锁；`on_shutdown` 安全停车；codegen N/dt 启动校验 |
| `usv_planning*/` | fillet 有限性门禁、航点过滤、mission bridge 拒绝 (0,0)、Python 定时器兜底 |
| `usv_mpc/`（Python 方案 A） | 同类加固（详见 `docs/fix_log_20260905.md`） |

验证：两工作区 `colcon build` + gtest 28 例 + pytest 全过；SIGINT 安全停车实测。
**回退**：`git revert b6c55eb`（安全行为回退会让 9-03 型故障重新可能，不建议）。

### 4.2 `32140ef` — RTL 指令洪水修复

动机：09-03 实测复盘（rosbag `usv_run_20260903_153938`）：mavros 未连 FCU 时
path 看门狗被空路径武装、规划器停发 184 s → FAILSAFE；且 RTL 到不了飞控、
mode 永不变 RTL → **0.5 s 一次无限重发**。

| 文件 | 改动 |
|---|---|
| `usv_safety*/mode_manager_node.*` | path 看门狗加 armed 门控（未解锁不监视）；`max_rtl_retries=10` 上限（超过即停止指令洪水，保持告警）；退出处理补 `ExternalShutdownException` |

验证：车机上实机冒烟（FCU 重连后）：零 FAILSAFE、零 RTL、干净退出。
**回退**：`git revert 32140ef`（不建议——洪水问题真实发生过）。

### 4.3 `6715be9` — VRX 仿真船 → 实船数字孪生 ⭐ 本轮最大变更

动机：旧仿真船标称 30 kg，实际因 WAM-V 吊舱（15 kg×2）总质量 **61 kg**，
且水动力/几何全是拍脑袋的初值——仿真调参无法迁移实机。
依据 `MPC/01_MPC_Project/02_水面试验与硬件/USVANSIS/2026-09-03/辨识产出/`。

| 文件 | 改动 |
|---|---|
| `config/usv_params_sim.yaml` | MPC 模型 30 kg → **实船 14.2 kg**（艏摇 Nr_dot −3.41 / Nr −3.105 / Nrr −0.71 为阶段 3 回归；纵向按阶段 2 决议维持 7-23 先验） |
| `usv_simulation/urdf/usv_mono.urdf.xacro` | 船体 1.2×0.6×0.3 m、质量预算 12.8 + 2×0.7 = 14.2 kg、桨位 ±0.25 m |
| `usv_simulation/urdf/usv_mono_thrusters.xacro` | **新增**轻量吊舱宏（替换 15 kg WAM-V 吊舱）；推进器系数按插件公式 `T=ρ·c·D⁴·ω²` 编码辨识 K（c=9.37e-5, D=0.2 → 25 N@3900 RPM） |
| `usv_simulation/urdf/usv_mono_dynamics.xacro` | 浮力圆柱 1.2 m/r0.25；水动力系数 = 辨识值；nDotR=3.53 使植物有效惯量 = 5.537 与 MPC 一致 |
| `config/mpc_params_vrx.yaml` | T_max 40→25、T_min −20→−25（实船界限） |
| `config/usv_params.yaml` / `usv_params_B.yaml` | 实船艏摇块应用阶段 3 结果（同上三值） |

验证：隔离域下 `vrx_b_circle` 全任务闭环 ×2（ACTIVE → 全程跟踪 → 任务完成，
96 s，推力限幅正确，fail_count=0）。
**回退**：`git revert 6715be9 0a34531` + 重启仿真即回到 61 kg 旧船。
**注意**：`/tmp/usv_mono*.xacro.bak` 是临时备份，重启即失。

### 4.4 `0a34531` — 推进器编码落实（4.3 的修正）

发现 4.3 初版把辨识 K 直接填 `thrust_coefficient`，忽略了插件公式
`T = ρ·c·D⁴·ω²`（有效系数差 3600 倍）。修正为 c=9.37e-5（D=0.2），
并连续 2 次全任务验证。
**另修复**：`path_planner_node.py` 任务完成分支的 `info_once`（rclpy 无此 API，
曾致规划器每拍异常——被 4.2 加的兜底保护暴露）。

### 4.5 `518597a` — rosbag 分析脚本（新增工具）

`scripts/analyze_usv_bag.py`：仿真（wamv 话题）与实机（mavros 话题）包通用，
自动识别 odom 来源，输出轨迹/CTE/速度/推力四联图 + 文本报告。
**回退**：删除文件即可（纯新增）。

### 4.6 `3fe3c38` — 控制器对齐实机 + 参考整定

动机：002 包分析发现推力饱和 54.8%（MPC 一半时间贴 25 N 上限）。
两步整定，每步都有数据对照：

1. **Q/Qf_scale 对齐实机部署值**（`mpc_params_B.yaml`: Q=[20,20,50,8,1,8], Qf=8）
   —— 仿真与实机从此是**同一套控制器参数**。
2. **`reference_start_offset` 8→2、`cruise_speed` 0.8→0.6** —— 根因是参考点
   恒超前船 4-6 m，MPC 全程追赶（船速被顶到 1.45 m/s，直航阻力即 25 N）。

三轮对照（见 §5）。
**回退**：`git revert 3fe3c38` 后重新 `colcon build --packages-select usv_bringup`。

## 5. 仿真验证数据全景（6 个 bag, 域 42 隔离）

| bag | 配置 | CTE 均值/峰值 | 推力饱和 | 航速均值 | 结果 |
|---|---|---|---|---|---|
| 001 | 孪生 v1 | — | — | — | 闭环成功；predicted 轨迹 0 条（录包器发现竞争，非功能）|
| 002 | 孪生 v1 | 0.744 / 1.708 m | **54.8%** | 1.07 m/s | 完整任务；暴露推力饱和 |
| 003 | +权重对齐 | 0.896 / 1.674 m | 51.9% | 1.22 m/s | 饱和仍在 → 排除权重假说 |
| 004 | +参考整定 | **0.402** / 2.381 m | **10.4%** | **0.81 m/s** | ✅ 当前配置 |
| 005 | 复现验证 | 0.473 / 2.484 m | 9.7% | 0.82 m/s | ✅ 复现稳定 |
| 006 | 无波对照 | 0.523 / 2.507 m | 19.7% | 0.77 m/s | ✅ 波浪假设排除 |

每包同目录有 `analysis.png`（轨迹/CTE/速度/推力四联图）+ `analysis_report.txt`。

## 6. 已知问题与风险（按优先级）

1. **12 个提交未推送** —— `git log origin/main..HEAD` = 12。唯一权威副本在本机磁盘。
2. **DOMAIN_ID 隔离**：车机 220 与本机同域互相串扰（曾致"仿真 no_odom"假象、
   param/node 查询串台）。建议车机 `~/.bashrc` 加 `export ROS_DOMAIN_ID=7`。
3. **`ntrip_params.yaml` 含 CORS 明文凭据且已被 git 跟踪**（根仓库连着 GitHub）——
   文件头自己的注释就警告了这一点。建议移出版本库。
4. **ODE `aabbBound` 偶发崩溃**：孪生植物在 spawn 期偶发（twin2/3、final/2/3 共 5 次
   vs 干净 4 次），与吊舱质量/浮力/推进器参数的关联未完全定论（二分曾相互矛盾）。
   当前配置连续 3 次干净。若复现：重启 launch 即可；顽固时优先怀疑 /dev/shm 残留
   与 DDS 状态，其次回调吊舱质量。
5. **圆顶 excursion（CTE ~2.4 m, t≈95-105 s）**：已定性为"辨识出的低横漂阻尼
   (Yv −2.63) + 25 N 推力边界"下的真实可控性边界，非 bug（004/005/006 均复现、
   均恢复、均完成任务）。改善选项：进一步降速 / 调 Q_y / 接受现状。
6. **predicted_trajectory 偶发 0 条**（001 包）：录包器发现竞争，002 起正常。
7. **车机 B 工作区落后**：仅 safety 包同步过；数字孪生、planner 修复、艏摇参数
   均未上车。下次上船前建议整仓 rsync + `colcon build`。
8. **RPATH 烘焙 `$HOME/acados/lib`**：env-hook 与 real.launch 已兜底，改动需实机验证（有意保留）。

## 7. 常用命令速查

```bash
# 构建
cd ~/USV/usv_mpc_ws && colcon build --symlink-install
source /opt/ros/jazzy/setup.bash && source ~/USV/vrx_ws/install/setup.bash
source install/setup.bash
export LD_LIBRARY_PATH=$HOME/acados/lib:$LD_LIBRARY_PATH

# 仿真（带录包，域隔离）
export ROS_DOMAIN_ID=42
ros2 launch usv_bringup sim.launch.py headless:=False \
  waypoints_file:=$HOME/USV/usv_mpc_ws/src/usv_bringup/config/waypoints/vrx_b_circle.yaml \
  record_bag:=True run_id:=my_run

# 状态确认
ros2 topic echo /mpc/status --once --field data   # ACTIVE=闭环中

# 分析
python3 scripts/analyze_usv_bag.py ~/usv_vrx_logs/<run_id>

# 实机
ros2 launch usv_bringup real.launch.py            # 默认方案 B

# 测试
colcon test && colcon test-result --verbose
# (剩余失败均为存量 cpplint/uncrustify 风格项, 逻辑测试 0 失败)
```

## 8. 参数溯源表（数字孪生）

| 参数 | 值 | 来源 |
|---|---|---|
| mass | 14.2 kg | 09-03 锚定（surge_params.json）|
| Iz / Nr_dot | 2.13 / −3.41 | 阶段 3：Iz_eff=5.537 反解 |
| Nr / Nrr | −3.105 / −0.71 | 阶段 3 角加速度回归（R²=0.35, n=138k）|
| Xu / Xuu | −2.272 / −11.572 | 7-23 先验（阶段 2 决议维持）|
| Yv / Yvv | −2.629 / −0.05 | 7-23 辨识（横漂弱阻尼——excursion 根因）|
| Yr / Nv / Yrr / Nvv | 0 | 7-23（耦合项置零，开环稳定性论证见 usv_params.yaml 注释）|
| d_thruster | 0.25 m | 几何 |
| T_max / T_min | ±25 N | 7-23 假设（K=1.6437e-6 N/RPM² @ 3900 RPM）|
| 推进器插件 c | 9.37e-5 | 由 K 按 T=ρ·c·D⁴·ω² 反推（D=0.2）|
| Q / Qf_scale | [20,20,50,8,1,8] / 8 | 实机部署值（mpc_params_B.yaml）|
| reference_start_offset / cruise_speed | 2 / 0.6 | 09-06 整定（004 验证）|

## 9. 待办

- [ ] 推送 12 个提交；为车机 B 建远程仓库
- [ ] 车机 `ROS_DOMAIN_ID=7` 隔离
- [ ] 下次实跑（树莓派开机 + MPC）→ 用 `analyze_usv_bag.py` 出首份"孪生 vs 实船"对照
- [ ] `ntrip_params.yaml` 凭据移出 git（建议）
- [ ] 观察 004/005 的圆顶 excursion 是否持续；必要时降速或调 Q_y
- [ ] （可选）MPC 横漂阻尼补偿前馈
