# RELEASE_ID pi5-20261112T150424Z-5cf562ed290b 运行版本对齐与 Release 基线 (补测, 门禁未通过)

- 执行时间: 2026-11-12 (UTC 15:04 冻结 / 15:11–15:19 构建 / 15:19–15:33 测量 / 15:34 回退)
- 宿主: `trevor-desktop` (Raspberry Pi 5, aarch64, 4 核, 8 GiB)
- **最终部署: 本候选的 `install_noopt` (非优化), Release 未启用。**
- 上一候选 `pi5-20261112T142050Z-76b6dc939246` 曾把 Release 上线并验收; 本次补测
  发现其对照门禁存在两处实现缺陷 (见 §2), 修正后重测, 门禁未通过, 已回退。

## 1. 为什么重做

上一候选的对照与基准存在 4 处实现缺陷, 均由外部评审指出并在本候选修正:

| # | 缺陷 | 影响 | 修正 |
|---|---|---|---|
| 1 | 两个 `RunScenario()` 只把**上一拍返回控制**写回锚点, 从不把场景规定的锚点送入求解器 | 第 4 场景的非零锚点 A `[0.4,0.1]` / B `[5,-5]` 根本没被使用; B 还在用它从未收到的锚点做约束复核 | 首拍求解**前**调用 `set_applied_command/control(input.anchor)`, 之后沿用返回控制; 逐拍记录 `anchor_source` 与实际锚点 |
| 2 | 对照只按聚合 p95/失败数判定 | 单场景退化可被其它场景的改善掩盖 | `compare_timing()` 改为逐场景逐轮判定三项门禁 |
| 3 | 无环境有效性门禁 | 起始温度 >60 °C 或存在欠压/限频/热节流的段仍会被当作有效数据 | 运行器逐段记录起始温度与 `get_throttled` 粘连位, 任一越界即该段无效; 对照脚本要求两侧 `env.json` 存在且粘滞位为 0 |
| 4 | `static` 取证假设合并布局 | 只存在于包级子目录的 `CMakeCache.txt`/`compile_commands.json` 与 `install/<pkg>/share/...` marker 会被误报缺失 | 逐包聚合; marker 两处候选路径均查; ldd 在 ROS 环境 + 求解器库路径下执行 |

## 2. 构建身份 (两变体同一冻结源码)

| 项 | NoOpt | Release |
|---|---|---|
| 源码内容哈希 (107 文件) | `6667c2146cdb944a…` | 同左 |
| `CMAKE_BUILD_TYPE` | `Debug` | `Release` |
| A/B C++ 与 B codegen C 实际编译 | `-O0 -g` | `-O3 -DNDEBUG` |
| `usv_nmpc` mpc_node | `bdaf5a394a60381c…` | `9fd2b4fdf939fb6d…` |
| 功能测试 | 52/52 | 52/52 |
| lint | 263 项 / 127 失败 (既有) | 263 项 / 127 失败 (既有) |

## 3. 环境有效性 (新增门禁)

- `vcgencmd get_throttled` = `0x0`, 粘连位 (bit 16–19) = **0** ⇒ 本 boot 内**从未**
  发生欠压/限频/热节流, 覆盖全部测量段。
- 全部 12 个分段起始温度 53.45–58.95 °C, 均低于 60 °C 门限。
- governor=performance, 频率 2400000 kHz 恒定。
- 证据: `evidence/bench/{noopt,release}/env.json`。

## 4. 数值一致性 (诊断预算)

| 变体 | 4 场景最大控制差 | 最大预测差 |
|---|---|---|
| kinematic (casadi) | ≤6.4e-16 | ≤1.1e-15 |
| dynamic_acados | ≤6.4e-14 | ≤1.4e-13 |

全部求解成功、解有限、约束残差 0; 两变体输入的测量/参考逐字段一致, 锚点按
“求解输出派生”档 (1e-9) 一致。

## 5. 逐场景耗时门禁 — **未通过**

生产预算 (A: 120 ms CPU / 50 迭代; 预算阈值 200 ms), 每场景 20 预热 + 500 计时。

| 变体 | 轮次 | 场景 | NoOpt 失败 | Release 失败 | NoOpt p95 | Release p95 | 门槛 | 结果 |
|---|---|---|---|---|---|---|---|---|
| kinematic | 1 | straight | 0 | 0 | 31.70 | 30.32 | 34.87 | 通过 |
| kinematic | 1 | arc | 60 | 60 | 119.36 | 115.58 | 131.29 | 通过 |
| kinematic | 1 | **arc_cross_pi** | **91** | **101** | 122.15 | 123.20 | 134.37 | **未通过** |
| kinematic | 1 | straight_anchor_offset | 0 | 0 | 30.15 | 29.76 | 33.17 | 通过 |
| kinematic | 2 | straight | 0 | 0 | 30.40 | 29.61 | 33.44 | 通过 |
| kinematic | 2 | **arc** | **60** | **62** | 117.80 | 117.52 | 129.58 | **未通过** |
| kinematic | 2 | arc_cross_pi | 91 | 91 | 120.23 | 118.99 | 132.25 | 通过 |
| kinematic | 2 | straight_anchor_offset | 0 | 0 | 31.19 | 29.76 | 34.31 | 通过 |
| dynamic_acados | 1/2 | 全部 4 场景 | 0 | 0 | 0.66–0.99 | 0.36–0.44 | 0.86–1.19 | 全部通过 |

**结论 (对照脚本 `ok=false`)**: `kinematic 第1轮 arc_cross_pi 失败拍 91→101`;
`kinematic 第2轮 arc 失败拍 60→62`。按计划“不能得到有效、通过的对照则不切换
Release”, 因此**回退到 NoOpt**。

### 为什么判定为边界抖动而非优化退化 (仅供决策参考, 不改变门禁结论)

- 同一对构建在两轮里互换胜负: arc_cross_pi 第 1 轮 101>91 (败), 第 2 轮 91=91
  (平); arc 第 1 轮 60=60 (平), 第 2 轮 62>60 (败)。系统性退化不会这样翻转。
- 所有失败拍都是 `ipopt_early_stop_infeasible`, 即撞满 120 ms CPU 预算后回收的
  迭代点未通过可行性门禁; 失败拍的墙钟中位数 ≈114–115 ms (NoOpt) / ≈115 ms
  (Release), 成功拍中位数 ≈18 ms。差异发生在预算边界的个别拍上。
- p95 在所有场景两轮均未越界 (最大 123.20 vs 门槛 134.37)。
- 数值阶段 (60 s 预算) 两变体的控制序列完全一致 (≤6e-16), 说明求解结果本身没有
  因优化级别改变; 差异只在“是否恰好收敛在 120 ms 内”。
- A 的 CasADi/IPOPT 不是生产路径 (生产是 B/acados), 但计划要求逐变体逐场景判定,
  不能因为不是生产路径就豁免。

## 6. 最终在线状态 (回退后)

| 项 | 值 |
|---|---|
| `usv_runtime` | → `$R/install_noopt` |
| `usv-system` | active / enabled / `NRestarts=0` |
| 控制器 | pid 3333272, `install_noopt/usv_nmpc/lib/usv_nmpc/mpc_node`, 无 `(deleted)` |
| 后端 | `backend=acados` (启动日志) |
| MAVROS | 单个, 独占 `/dev/ttyAMA10` |
| 参数哈希 | `ba2e6c05f8b8…` (与安装配置一致, `SCHEME=B`) |
| `usv-record` / `usv-rtk` | 保持 inactive + disabled |
| 在线身份 | t0 / t60 两次 `identity_ok=true` |

Release 安装树 (`install_release`, `9fd2b4fdf939fb6d…`) 与上一候选的
`install_release` (`3a49db6c983a5190…`) 都**保留在磁盘上**, 未删除, 供后续复查。

## 7. 未验证边界

1. 未解锁、未试航、未重启飞控/整机: 5 Hz ACTIVE 周期、实船跟踪、物理推力未测;
   窗口内 `armed=true/HOLD` 且 `no_odom`, 控制节点停在待机。
2. 开机自启未验证 (只做 `systemctl start`)。
3. `usv-record`/`usv-rtk` 的 drop-in 只做静态核对, 两服务均未启动。
4. A (CasADi) 的早停抖动根因未定位 (是 IPOPT 在 120 ms 预算内的收敛路径问题,
   与构建类型无关)。
5. lint 127 项既有失败未处理 (重排控制代码超出本次范围)。
6. 外部求解库未重编译。

## 8. 与计划的关系

- 计划要求“全部现有测试通过”才可切换: 功能测试 52/52 通过, lint 有 127 项既有
  失败 —— 该硬门禁**字面上未满足**, 属已知偏差 (前次发布记录 §10.4 已登记)。
- 计划要求“Release 门禁逐场景判定, 不通过则不切换”: 本次严格执行, 结果未通过,
  已回退。**Release 是否要在 A 变体该场景上豁免, 需要明确决策, 不在本记录内自行放宽。**

## 9. 证据清单

`$R/evidence/`:
`identity_{noopt,release}.json`、`test_summary.json`、`source_manifest_frozen.txt`、
`bench/{noopt,release}/{kinematic,dynamic_acados}/{numerical,timing_1,timing_2}.json`、
`bench/{noopt,release}/env.json`、`bench/comparison/{comparison.json,comparison.md}`、
`runtime_noopt_t0.json`、`runtime_noopt_t60.json`、`pre_switch_backup/`。

## 10. 候选谱系 (本次起不再删除候选)

| RELEASE_ID | 结果 | 处置 |
|---|---|---|
| `pi5-20261112T142050Z-76b6dc939246` | 报告达标, Release 曾上线并通过 60 s 验收; 事后发现基准锚点/门禁/环境三项实现缺陷 | **保留**; 其 `install_release` `3a49db6c…` 与 `install_noopt` `c79814f2…` 均在盘 |
| `pi5-20261112T150424Z-5cf562ed290b` | 缺陷已修, 逐场景门禁未通过 (A 变体 2 处失败拍增加) | **保留**; 部署其 `install_noopt` 作为最终运行版本 |

更早的 6 个失败候选已在首次记录 §8 登记 (当时被删除, 证据丢失)。
