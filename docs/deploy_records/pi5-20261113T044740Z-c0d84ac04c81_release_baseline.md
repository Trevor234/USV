# RELEASE_ID pi5-20261113T044740Z-c0d84ac04c81 运行版本对齐与 Release 生产验收

- 执行时间: 2026-11-13 (UTC 04:47 冻结 / 12:47–13:02 构建 / 13:07–13:41 离线基线与迁移测量 / 14:07 烟测 / 18:27 CST NoOpt 在线取证 / 19:46 CST Release 在线取证)
- 宿主: `trevor-desktop` (Raspberry Pi 5, aarch64, 4 核, 8 GiB)
- **最终部署: 本候选的 `install_release` (Release 优化版, -O3 -DNDEBUG), 生产环境正式生效并完成只读取证闭环。**
- 上一候选 `pi5-20261112T150424Z-5cf562ed290b` (NoOpt 回退状态) 已完整由本候选替代。

---

## 1. 架构重构与演进

本次重构解决了长期困扰系统的“包名混杂”与“方案 A (CasADi) CPU 预算硬超限导致失败拍”两大核心问题：

1. **包名规范化（去除 `_cpp` 后缀）**：
   - `usv_mpc_cpp` → `usv_nmpc`（动力学 NMPC，专职输出左右推力）
   - `usv_mpc_kinematic_cpp` → `usv_mpc`（运动学 MPC，专职输出线速度/角速度指令）
   - `usv_planning_cpp` → `usv_planning`（路径规划与任务桥接）
   - `usv_safety_cpp` → `usv_safety`（状态机与安全监控）
   - 头文件全部移至规范目录 `include/<pkg_name>/...`，同步更新全工作空间 CMake、package.xml 与 launch 文件。

2. **求解器专职化与全新 `usv_acados` 后端库**：
   - 新增 `src/usv_acados`，提供独立的 `libusv_acados_backend.so`，实现无 ROS 依赖的纯 C++ acados 封装。
   - **方案 A（运动学 MPC）彻底迁移至 acados**：从 CasADi/IPOPT 迁移到非线性最小二乘 (NONLINEAR_LS) SQP+0.12s 预算控制，包含 8 维 `p_global` 动态注入、独立四项残差审计与 status 严格门禁。
   - **方案 B（动力学 NMPC）剥离 CasADi fallback**：专一绑定 acados SQP_RTI，剔除全部 CasADi 探针与运行时代码。
   - 彻底解除整个工作空间对 Python pip `libcasadi.so` 的 C++ 运行时依赖。

3. **DDS 环回配置修复**：
   - 修复 `~/.ros/fastdds_lan.xml` 白名单中缺少 `127.0.0.1` 的问题，确保生产服务在使用 FastDDS 时本地 ROS 2 CLI 诊断工具能够瞬时互通。

---

## 2. 离线基线与算法迁移验收 (`ACCEPTANCE.md`)

| 评估维度 | 验收指标与门禁要求 | 实际测试结果 | 结论 |
| :--- | :--- | :--- | :--- |
| **功能测试** | 全工作区 `colcon test` 无功能故障 | 68/68 全部 PASS，既有 lint 债务不增 (106 项，原 127 项) | **通过** |
| **部署工具门禁** | `deploy/tests` 单元测试 | 117/117 全部 PASS | **通过** |
| **采集有效性** | 19 个分段全程无欠压、限频与热节流 (`run_manifest.json`) | 起始温度 $\le 60\ ^\circ\mathrm{C}$，`throttled=0x0`，governor=performance | **通过** |
| **方案 A 耗时对比** | 解决 CasADi 120 ms 预算失败拍问题 | p95 降至 **2.16 ~ 17.47 ms** (降幅 >85%)，max 21.9 ms；4 场景两轮 520 拍 **0 失败、0 超限** | **通过** |
| **方案 A 跟踪精度** | 独立闭环 200 拍 $\times$ 4 场景 | 位置 RMSE 0.048–0.056 m ($\le 0.40$)，航向 RMSE 0.014–0.015 rad ($\le 0.20$) | **通过** |
| **方案 B 回归一致性** | 抽取共用库前后控制量逐元素对比 | 最大控制差 $\le 4.07 \times 10^{-12}$，状态差 $\le 5.8 \times 10^{-13}$，数值零退化 | **通过** |
| **方案 B 耗时水平** | Release 耗时保持极致实时 | p95 稳定在 **0.37 ~ 0.52 ms** | **通过** |
| **独立节点烟测** | 独立 A 节点 60s ACTIVE (`smoke_a_node.json`) | 300/300 拍全部成功，0 HOLD，0 deadline_miss，断流 STANDBY 恢复正常 | **通过** |

---

## 3. 在线身份取证（稳妥双阶段切换）

### 3.1 阶段一：NoOpt 调试版上线取证 (`runtime_noopt.json`)
- 软链：`/home/trevor/usv_runtime -> .../install_noopt`
- 结果：`identity_ok = True`，`failures = []`
- 控制器 PID 1067216，无 `(deleted)`，MAVROS 独占串口 `/dev/ttyAMA10`，动态链接库完整解析。

### 3.2 阶段二：Release 优化版上线取证 (`runtime_release.json`)
- 软链：`/home/trevor/usv_runtime -> .../install_release`
- 结果：`identity_ok = True`，`failures = []`
- 控制器 PID 1397196，无 `(deleted)`，落位 `/home/trevor/usv_releases/pi5-20261113T044740Z-c0d84ac04c81/install_release`
- 控制器实际加载：
  - `libusv_acados_backend.so.0.1.0` (-O3 Release 构建)
  - `libacados.so`、`libhpipm.so`、`libblasfeo.so`
  - 零 `libcasadi.so` 残留
- 参数审计：`control_mode = dynamic`，32 项动力学与推力关键参数与配置逐项匹配。
- 启动日志：`backend=acados`，SQP_RTI 迭代平稳。

---

## 4. 固化证据索引

- 离线全量构建与测试日志：`/home/trevor/usv_releases/pi5-20261113T044740Z-c0d84ac04c81/evidence/`
- 在线 NoOpt 取证：`evidence/runtime_noopt.json`
- 在线 Release 取证：`evidence/runtime_release.json`
- 静态身份声明：`evidence/identity_release.json`
- 节点隔离烟测：`evidence/smoke_a_node.json`
