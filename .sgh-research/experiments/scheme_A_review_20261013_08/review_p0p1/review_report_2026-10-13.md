# 方案 A：F5/P1 核心与当前 v9 范围独立复核

日期：2026-10-13。审查目录：`review_p0p1`。本次只读业务源码、原文档和封存资产，未启动 ROS、Gazebo 或控制节点。启动文件 link/fsync/unlink 与 single-link reader 的竞态由主审单独检查，本报告不重复该项。

## 1. 结论与问题分级

未发现足以认定 F5 同锁冻结、迟到解拒绝、发布锚点或当前 v9 原子接纳门新增业务缺陷的证据。原文档对“组件通过不等于阶段通过”的主判断与源码一致；当前 v9 是 shadow-only 诊断入口，尚不能承担 M4 物理执行。

本次发现两处应修改的历史说明、两处应明确的计划/入口边界，以及一处已登记的 checker 泛化缺口。最后一项不能写成新增控制缺陷，也不能仅依据 checker 拒绝判业务失效。

| 编号 | 分类 | 具体问题 | 优先级 |
|---|---|---|---|
| DOC-01 | 文档错误 | 把 timing/deadline 的 repeat-last 行为泛化为所有前几次失败 | 文档本批修订 |
| DOC-02 | 文档错误 | 将完整 shape/finite/foreign/echo 等检查全部归属 `p1_admission.hpp` | 文档本批修订 |
| PLAN-01 | 已知版本/资格缺口 | default 入口与 v9 源码不同，不能通过默认包安装或只改 execute flags 推进 M4 | 下步计划必须声明 |
| PLAN-02 | 计划歧义 | “有限模型/备份/证书事务→F6/P1→P2”容易把 P2 认证备份实现前置成 P1 的循环条件 | 下步计划拆开定义 |
| GAP-01 | 已知 checker 泛化缺口 | 最后一条 Capability receipt 被当成最后有效续期，合法租约可能被误拒 | C3.4 最小工作包 |

## 2. 可操作的文档修订依据

### DOC-01：普通 native 失败不一定重复上一命令

10/12 [逐步讲解](/home/trevor/MPC/方案A_从基线修复到C3_3_逐步讲解_2026-10-12.md:74) 写“旧策略前几次失败重复上一命令”。如果读者以此设计连续数值失败用例，就会把实际 backend 轨迹移位回退误当作异常。

实际触发与行为：

- 超时或非法计时返回：冻结 F5 [mpc_node.cpp](/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp:848) 在 `time_rejected` 分支重置 warm start，然后使用上一拍 `last_commanded_thrust_`；没有历史时使用零。
- native status!=0、non-finite solution 或异常且没有触发 timing gate：当前 [acados_backend.cpp](/home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/src/acados_backend.cpp:255) 返回 `safe_fallback_`；[safe_fallback_](/home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/src/acados_backend.cpp:321) 在有历史轨迹且未耗尽时使用移位轨迹首控制，而非 repeat-last。
- 节点连续失败达到阈值：冻结 F5 [mpc_node.cpp](/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp:868) 覆盖为 HOLD 零目标。

建议改为：“timing/deadline 拒绝在达到节点失败阈值前重复上一入口命令；普通 native 失败沿用 backend 的移位轨迹/零回退；达到原阈值后 HOLD 零目标。旧行为保留，不代表 P1 新监管器的认证备份或变化率资格。”

该判断同时对照冻结 F5 原件，避免只依据后来共享核心提取后的当前文件。F5 文件 SHA256 与原报告登记一致：`2f1b457ce9644d6ceff722e4ce328fa6a5de23a2cb94f8470c022e0bd70f2dd8`。

### DOC-02：准入检查要按真实分工写

[逐步讲解第 7 步](/home/trevor/MPC/方案A_从基线修复到C3_3_逐步讲解_2026-10-12.md:181) 把 shape/finite/foreign/echo 等条件都归给 `p1_admission.hpp`。实际该头文件主要管理 Ticket 的目标拍、版本、150/200 ms 关系、一次性消费，以及状态/动作/历史的纯逻辑辅助检查。

建议改为明确的分工：

- [protocol.hpp](/home/trevor/USV/usv_mpc_ws/src/usv_research_safety_cpp/protocol.hpp:47)：Job 身份、固定维度/时间关系、有限数组、锚点与历史条件。
- [regulator.cpp](/home/trevor/USV/usv_mpc_ws/src/usv_research_safety_cpp/regulator.cpp:210)：Candidate 与 Worker 绑定、solver 结果有限性、first-control/X0 一致性、完整 Job echo、native 计时和最终注册。
- [solver_worker.cpp](/home/trevor/USV/usv_mpc_ws/src/usv_research_safety_cpp/solver_worker.cpp:63)：Worker 收 Job 的资源/身份/顺序/截止判断，以及返回预测的长度和有限性检查。
- [p1_admission.hpp](/home/trevor/USV/usv_mpc_ws/src/usv_research_safety_cpp/p1_admission.hpp:103)：Ticket 的 ready/cutoff/take/invalidate 提交状态机。
- `p1_resources.hpp`：复制/指纹前 typed 资源边界。

作用不是调整行为，而是让下一实施者知道应该修改哪一层，避免误以为增加一个 Admission 条件便覆盖全 Candidate 语义。

## 3. 已核实实现、保留的旧问题与实际运行范围

### F5 冻结/deadline/锚点实现与记录相符

冻结 F5 [run_dynamic_mpc_](/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp:758) 在同一 `state_lock_` 内重新判断资格、复制状态和构造参考，失去资格时先解锁再 standby；native solve 在锁外执行。冻结后的 clear 仍允许当前同步候选完成，是原报告明确测试并保留的旧政策，不是本次发现的新竞态。

迟到判定严格 `>` 预算；完整调用 wall-time 与 backend-time 都检查，但 reference/logging/publish 未全部算进原 200 ms。该 gate 等待同步 solve 返回，不能声称 200 ms 到点独立接管。[节点后返回 gate](/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp:838) 对此有明确代码注释。

入口命令与映射后 N 分开保存；[发布后的 set_applied_control](/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01/source_snapshot/usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp:889) 使用实际本地映射返回值，因此重复入口命令不会重复乘 scale。这里仍是 publisher-side N，不是实测推进器力。

F5 到阈值直接给零、reference/path 准入及 solve 后输入失效等旧政策必须保留其原范围；不能把新监管器的 rho-ramp/版本失效结论授予旧 F5。也不能为了让原 guard 通过改写旧冻结 expected。

### PLAN-01：当前 v9 与默认生产目录不是同一入口

当前 v9 [constructor](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/regulator_shadow_observer.cpp:59) 首先调用 `require_shadow_mode(mode_)`，并要求完整 diag5；[第 80 行](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/regulator_shadow_observer.cpp:80) 的 entry policy 在应用 publisher/sink 创建前验证。v9 还存在独立 [execute 硬关闭](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/p1_full_contract.hpp:102)。因此 v9 中残留 `publish(mode==execute)` 代码不表示该分支已可达、已测试或有 M4 资格。

默认 [regulator.cpp](/home/trevor/USV/usv_mpc_ws/src/usv_research_safety_cpp/regulator.cpp:303) 仍保留 Decision enqueue 失败只置 stopping、随后可能立即退出的旧路径。v9 [finish_tick](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/regulator_shadow_observer.cpp:547) 才在原业务 mutex 下立即失效 admission/candidate/pending。这是已明确隔离实现的版本事实，不是本次发现的新回归；默认包安装不能自动获得 v9 的源码能力与证据。

主方案旧版 [当前入口](/home/trevor/USV/.sgh-research/handoffs/scheme_A_20261010_01/source_docs/首选A_现有ROS平台可行性与实施方案_2026-10-03.md:427) 应保持历史快照；新当前状态文档另列默认 source/install、冻结 F5 和 sealed v9 三种身份。进入 M4 必须创建新执行版、明确归入 v9 必要业务修复和输出路径，重新冻结 source/bin/contract/IDL，不能仅把 `execute_qualified` 或 `physical_execute_release_enabled` 改成 true。

### C3.3 原生矩阵与 owned run 均有具体范围

v9 [test_c33_input_matrix.cpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/tests/test_c33_input_matrix.cpp:20) 使用 source-including callback/tick 夹具，显式禁用 startup legacy readiness；[第 71 行](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/tests/test_c33_input_matrix.cpp:71) 还播种 RTF、anchor、history、ticket 等先决条件。真实源码门和一次受控 callback 线程交错得到测试，但 raw_input=null，不认证真实非法 wire、一般并发或 Master Clock。

10/12机器状态登记 86 项 fresh native 与 69 项 Python；本次没有把历史这些数字改记为新执行。当前 owned 正例 35 Decision、1 次零尾部接受、21 次 anchor_mismatch；实际 expired 5 Decision、0 接受，零输出按预期关闭。这些与 [第07批状态](/home/trevor/MPC/scheme_A_C3_3_20261012_07/batch_status_2026-10-12.json) 一致。没有 Gazebo/plant；唯一接受不构成非零动态接管性能证据。所有阶段 flags 仍 false。

## 4. GAP-01：已知 last-valid checker 缺口的准确触发

v9 业务 [capability callback](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/regulator_shadow_observer.cpp:408) 先检查已到期/终态；foreign 或 nonfatal backend-invalid 不续期，也不替换原有效 lease。仅 `renewed=true` 才更新 [last_capability_ 与 last_capability_commit_ns_](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/regulator_shadow_observer.cpp:421)。matching identity 的实例变化/fatal 和 lease 到期按原政策终止。

然而 [check_atomic_observation_v2.py](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/check_atomic_observation_v2.py:760) 对 `commit_worker_valid` 从全部 `capability_admission` 取最后一条，并要求其 `valid/identity_valid/renewed`。触发序列是：有效续期 → foreign/普通 invalid receipt → 租约未过期的最终提交。业务保留有效 lease，checker 却会给 `worker_valid_lease_source_binding` 失败。

这已经登记在 C3.4，属于检验证据泛化缺口。不能仅筛 `renewed=true` 就宣布完成：离线规则还必须按真实 callback 顺序重放 expiry-before-renew、matching fatal/instance change、不可复活终态，并绑定认证 writer 的实际 wire/source/storage；丢失终态消息不能靠之前有效 receipt 遮掩。

## 5. 下步实施顺序建议与退出条件

1. **C3.4 具体修复。** 新作者目录中实现 last-valid lease 重放；对 legal-invalid/foreign/matching-terminal/expiry 给有限原生与独立 offline 用例。只为这些具体缺口建立实际认证 wire 用例，保持 Worker 零 hook，不扩展到任意恶意 raw 穷举。完成门为 Source/原 callback/transport/storage/lease 轨迹逐条一致，正常/预期负例分别判定。receipt-timeout/IO 相关计划合并主审结果，历史未知保持未知。
2. **B4/M0b 当前版本限定。** 明确支持 recipe、mixed/turn 域与 clock 政策，对当前统一版本补有影响的动态/压力/恢复/关闭证据。T200、deadline150、lease600、20ms 对齐门必须分别给来源/预算/有限测量/unknown，不能按通过率改数值。缺少真实主时钟硬界时限定陈述，而非伪造其资格。
3. **B5 执行合同冻结。** 明确准备、接纳、输出、部分发布、unknown anchor、重启/时钟变化、异常关闭和监督回收政策，并绑定精确 source/bin/contract/IDL/source/storage/Witness；当前 v9 的所有性能/动态资格继续不自动继承。
4. **M4 新执行版。** 先离线/source-linked 验证输出与失效边界，再独立 run 关闭 F5，由新执行监管器每通道唯一发布。必须覆盖非零命令、左右部分失败、rho、跨双路预算、输出 gap、同 run 故障/恢复和 shutdown，不把 publisher 记录写成 plant ACK。正式 runner 和不通过的证据也应保留。
5. **有限模型事务与 F6/P1。** 冻结有限已知模型、人工偏置快照、warm-start 与版本接纳/旧结果拒绝，明确事务提交边界，形成当前执行版新基线。可预留 Backup/Certificate 的身份和事务接口，但不可用尚未存在的认证备份作为 P1 已完成事实。
6. **P2 认证备份。** 固定有限 plant set/物理误差来源 → 静态障碍/船体 → 当前集合独立传播/采样间距离 → 有限4s反馈备份/接续集合/剩余时域/age/障碍版本 → D0/D2 反例与执行一致性；完整 Backup/Certificate 产生和生命周期的研究验收在这里闭合。GP 数据和年龄机制仍在 P3，未取得作用区间/标签资格不得提前学习后宣称安全缩界。

这消除 [10/12 下一步第5/6项](/home/trevor/MPC/方案A_从基线修复到C3_3_逐步讲解_2026-10-12.md:529) “备份/证书事务先于 P2”的歧义：P1 做有限模型与执行事务及接口；P2 做具有包络和可达依据的实际有限备份/证书。与原主方案 [P1](/home/trevor/USV/.sgh-research/handoffs/scheme_A_20261010_01/source_docs/首选A_现有ROS平台可行性与实施方案_2026-10-03.md:414) 和 [P2](/home/trevor/USV/.sgh-research/handoffs/scheme_A_20261010_01/source_docs/首选A_现有ROS平台可行性与实施方案_2026-10-03.md:431) 分工一致。

## 6. 本次必要验证与局限

新增仅审查目录中的 [admission_review.cpp](/home/trevor/USV/.sgh-research/experiments/scheme_A_review_20261013_08/review_p0p1/admission_review.cpp)，直接包含原 v9 `p1_admission.hpp`；lease 头与 v9 对应头 SHA 相同（`391c10d527ba9d111c0e54f00a61e33d913bdbd1c05c7b217d550a105f0dd27c`）。用 `g++ -std=c++17 -Wall -Wextra -Werror -fsanitize=undefined -fno-sanitize-recover=undefined` 编译执行。

五组边界均通过：deadline 等号及一次消费；完成时间超截止回撤；invalidate 清 committed；已知±25 N 锚点在200ms后按80 N/s降到±9 N；lease 等号仍有效、+1ns到期且同run不可复活。[实际输出](/home/trevor/USV/.sgh-research/experiments/scheme_A_review_20261013_08/review_p0p1/admission_review.stdout.txt) 保留。

这些是本次新增 header 组件检查，不复算历史 86/69，不验证 native solver、真实 wire、总调度预算、publish/plant 或现场工作区完整身份。没有新阶段/研究资格。F5/backend 分支、v9 constructor/worker/回调/最终门与 checker 的结论主要来自源码审查；若要改变业务代码，仍须新派生版和适配实际触发的验证。

13份审阅输入的 SHA/字节数保存在 [review_inputs.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_review_20261013_08/review_p0p1/review_inputs.json)。未修改任何旧业务源码、旧报告或封存材料。
