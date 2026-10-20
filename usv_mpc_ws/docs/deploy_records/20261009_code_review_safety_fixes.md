# 2026-10-09 代码审查安全修复（方案 A 四项移植 + failsafe HOLD + RL 防护 + 遥测修复）

> - 日期：2026-10-09
> - 范围：`usv_mpc_kinematic_cpp`（方案 A，Pi 部署机主控节点）、`usv_safety_cpp` 配置、
>   `usv_rl_ros`（方案 C 节点）、`usv_simulation`（遥测）、`usv_bringup`（配置/契约/测试）
> - 背景：全项目代码审查发现方案 A 缺失方案 B 已有的四项安全修复（A/B 代码 80% 重复且分叉），
>   以及若干实船安全隐患。本次修复全部为"移植 B 已验证实现"或小范围防护加固。
> - 状态：**本地 + Pi 均构建通过、全部测试绿、已部署重启验证**

## 修复清单

### 1. 方案 A `usv_mpc_kinematic_cpp` — 移植 B 的四项安全修复

| # | 缺陷 | 修复 | 对齐 B 的位置 |
|---|------|------|--------------|
| C1 | **TOCTOU**：`can_solve_()` 检查后锁释放，path 回调在窗口内清空路径 → `build_reference_` 返回全零参考 → **船被命令驶向地图原点**（每次任务结束时窗口打开） | `run_kinematic_mpc_()` 在 state_lock_ 内重查 `can_solve_()`，失败解锁→standby→return | mpc_node.cpp:749-759 |
| C2 | **关机竞争**：`safe_shutdown()` 在信号线程与在途 solve() 并发操作 CasADi 后端（UB） | 新增 `shutting_down_` atomic + `control_output_mutex_`；`enter_standby_`/发布段/`safe_shutdown` 加锁+检查；shutdown 不再触碰求解器 | mpc_node.hpp:177-180, mpc_node.cpp:1169-1177 |
| M1 | **四元数退化穿透**：全零四元数 `quaternion_to_yaw=0`（有限值），isfinite 拦不住 → 静默 ψ=0（最大 180° 航向错误） | odom 门禁增加范数检查 `|q|²<1e-12` 丢弃 | p1_input_core.hpp:61-75 `admit_odom` |
| M2 | **deadline 只查后端时间**：Pi 抢占下 wall 远超 IPOPT 内部时间 → 发布过期解；且拒绝后未重置热启动 | 墙钟+后端双计时+有限性检查；拒绝时 `reset_warmstart()` + repeat-last（新增 `last_commanded_velocity_`/`has_last_command_`） | mpc_node.cpp:716-738, 838-846 |

顺手修复：`mpc_node_main.cpp` on_shutdown lambda 补 try/catch（防信号线程异常逃逸 → terminate）；
周期日志改用 `current_pose` 局部拷贝（原实现锁外读共享成员，技术性 UB）；补 `#include <algorithm>`。

### 2. 新增 `test/test_deadline_control.cpp`（方案 A 回归测试，8 用例）

移植 B 的测试模式：注入式构造函数 `MpcControllerNode(std::unique_ptr<KinematicMpc>)` +
`friend MpcControllerNodeTestAccess`，`FakeKinematicMpc` 故障注入。覆盖：

- 及时成功 → 发布候选 + 轨迹
- **墙钟超限**（后端计时正常）→ 拒绝 + warmstart 重置 + 零速度（无历史时）
- 拒绝后**重放上一条指令**（repeat-last，非过期候选）
- 后端计时超限 → 拒绝
- **空路径 recheck** → STANDBY 不调求解器（C1 核心回归）
- 全零四元数 odom → 丢弃（M1 回归）
- 计时无效（NaN/负）→ 拒绝
- 关机后 standby 不再发布（C2）

构建坑记录：注入式构造必须创建 timer 再 cancel（timer_ 为空指针直接 cancel → segfault，
本地和 Pi 各踩一次）；节点实现不在库里，测试目标需直接编入 `src/mpc_node.cpp`。

### 3. `safety_params.yaml`: `failsafe_mode: "report"` → `"HOLD"`

审查发现 C3：代码注释自己记载"MPC 死亡时 FCU 锁存最后一条速度指令（GUIDED 无 setpoint
超时）"，而 report 模式只打日志——MPC 崩溃/OOM = 船保持最后速度持续行驶。
实船正式任务默认改为 HOLD（配置注释本就推荐）；码头调试可临时改回 report。

### 4. `rl_policy_node.py` 防护（方案 C，VRX/开发机侧）

- `_control_loop` 主体包 try/except → 异常时零推力 + STANDBY(`control_loop_error`)
  + 节流日志，**定时器存活**（原实现任何 ORT 异常直接崩节点；VRX 下无 mode_manager
  兜底 → Gazebo 推力锁存 = 失控船）
- 三道 NaN 门禁：状态 (`nonfinite_state`)、观测 (`nonfinite_obs`)、推理输出
  (`nonfinite_action`)——NaN 经 `np.clip` 仍是 NaN 直发执行器
- `_odom_cb` 补四元数范数+NaN 门禁（对齐 MPC 节点）；`_imu_cb` 补 isfinite
- `_publish_status` 全字段有限性清洗（防 NaN 进 JSON 打崩严格解析器）
- 删除 `self.schedule_rebase_m = 2.0` 死赋值（原第 204 行，覆盖了 ROS 参数）；
  `import time` 移到模块顶部（原在热路径内）

### 5. `visualizer.py` 轨迹冻结修复

根因：`_history` 是 `deque(maxlen=10000)`，环绕后遥测桥的绝对游标 `last_track`
恒大于 deque 长度 → `hist[track_since:]` 永远为空 → **GCS 轨迹显示约 200-330 秒后
永久停止更新**。修复：`_history_total` 绝对计数 + `snapshot()` 内换算
`evicted = total - len(hist)`，游标 clamp。桥接协议不变，重连全量回放保留。

### 6. `topic_contract.yaml` 补录 GPS 话题

`gpsstatus/gps1/raw`（fix_type/eph/卫星数）与 `raw/fix`（经纬度原值），与当天早些时候
`bag_topics.yaml` 的录制清单对齐；同步更新 `test_config_smoke.py` 的传感器话题集合断言。

## 验证证据

| 验证项 | 结果 |
|---|---|
| 本地 colcon build | 4 包全过（kinematic/simulation/rl_ros/bringup） |
| 本地 colcon test | kinematic 8+13、bringup 5、simulation 9 全绿 |
| 本地 pytest（RL 单元） | 28 passed |
| **Pi 回归测试** | **8 tests PASSED**（含四元数退化实测日志 `|q|²=0.000e+00, 丢弃`） |
| Pi 构建 | 3 包过，二进制 19:20 更新 |
| 部署前置检查 | Pi 源码 vs 本地 HEAD 完全去空白后仅 38 个大括号差异（格式差异，语义一致）；船 disarmed/HOLD/STANDBY |
| 部署后 | usv-system + usv-record active；6 控制节点 + ntrip + relay 在线；MPC STANDBY(no_path) fail=0；RTCM 6.8 Hz；fix_type=5 (RTK Float)；bag 正常增长；failsafe_mode=HOLD 生效 |

## 审查发现但未修的 backlog（按优先级）

1. **B 包 CMake `find_package(Python3)` 顺序 bug**（M3）：CasADi 探测用了未定义的
   `Python3_EXECUTABLE`，fallback 后端静默不可用（A 的顺序是对的）
2. **A/B 头文件目录冲突**（M4）：两包都装 `<usv_mpc_cpp/*.hpp>` 且同名类
   `usv_mpc::MpcControllerNode`（ODR 隐患）；根治需 A 改 include 目录 + 抽公共库
3. **mode_manager 自动切换新鲜度**（M5）：`mpc_ok_` 默认 true，MPC 死亡时仍可把
   MANUAL 切 GUIDED；GUIDED 路径无重试上限
4. **mission_bridge 进度重置**（M6）：is_current 签名变化导致规划器航点进度反复清零
5. **cmdvel_to_thrust 前馈 10 倍单位错误**（M4-py，休眠中）：0.2s 除数 vs 0.02s 周期
6. `collect_repair_baseline.py` 基线冻结缺 `observation.py`/`usv_tracking_env.py`（M5-py）
7. 仓库卫生：`.sgh-research/`(3.8GB) 未 ignore、10 个 `.pre_*` 备份在源码目录、
   README/runbook 过时（无方案 C）、`sim.launch.py` 不转发 scheme 参数
8. git 历史含旧 CORS 凭据（已确认暂不重写；push main 前需决策）

## 文件清单

本地 + Pi（`~/usv_mpc_ws_B`）双侧同步：
- `src/usv_mpc_kinematic_cpp/{src/mpc_node.cpp, src/mpc_node_main.cpp, include/usv_mpc_cpp/mpc_node.hpp, CMakeLists.txt, test/test_deadline_control.cpp(新)}`
- `src/usv_bringup/{config/safety_params.yaml, config/topic_contract.yaml, test/test_config_smoke.py}`
- `src/usv_simulation/usv_simulation/visualizer.py`
- `src/usv_rl_ros/usv_rl_ros/rl_policy_node.py`（仅本地——Pi 未部署方案 C）
