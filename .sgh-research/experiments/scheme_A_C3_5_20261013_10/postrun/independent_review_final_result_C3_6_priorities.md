# C3.5 最终实际结果与 C3.6 优先项：独立只读复核

日期：2026-10-13，Asia/Shanghai。没有修改锁定源码、合同、旧资产或原始记录，没有复跑完整验证。

**实际 v3 已完成 14 个注册 job，全部通过；资格边界准确。C3.6 应先闭合 anchor 执行契约与有限执行政策，再补具体动态和当前版本故障证据。M4 接管继续后置。**

## 1. 当前实际结果

当前结果为 [`full_attempt03/result.json`](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/acceptance/full_attempt03/result.json)，绑定 v3 合同 SHA `927e9f0776b8deee4c1b77e730409549eba0916df1061e8cd11b1583e73281af`。实际运行耗时 7,007,803,377 ns，是离线检查耗时；不是控制周期或动态测量窗。14 个 job 的工具、数据集 argv、结果键、精确整数 rc=0 和精确 passed 状态与注册定义一致，所有实际生成报告的 SHA 和精确 bool 通过字段又读回一致。

Root 全次 Reader 共读取 424 个唯一路径，其中 410 个为固定输入，14 个为本次生成的子报告。固定输入、生成报告和原生/ROS 场景分别统计。本次没有新 ROS 节点、Gazebo、plant 或硬件运行。

独立按当前 `rules` 与锁定依赖矩阵重算 assessment，与实际结果一致：component passed；B4/M0b/B5/M4 均为 unknown，`all_required_passed=false`、`profile_supports_phase_qualification=false`、`qualified=false`；14 个阶段/研究 flags 全为精确 false。此结果准确区分了组件、阶段和研究结论。机器复核：[最终结果与优先项](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/postrun/independent_review_final_result_C3_6_priorities.json)、[实际 14 个子报告读回](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/postrun/independent_review_actual_reports_v3.json)。

## 2. 与 C3.4 后续计划的对照

对照 MPC 中的 [C3.5 原计划](/home/trevor/MPC/scheme_A_C3_4_20261013_09/方案A_C3_5下一步实施计划_2026-10-13.md)，新组件规则、工具/传递导入/source/bin/raw 闭包、精确四状态和实际原件重放已完成。ASCII/finite 支持域继续有界；旧 shared-v2 身份没有恢复或冒充；阶段依赖完整保留。

预算和来源目前属于有限观测：Worker/IO/调度观测最大值不能升为 WCET；Master Clock 硬界、plant ACK/保持区间仍 unknown。current dynamic recipe 只有预声明，turn/mixed 具体参考参数 unknown，20s 动态 not_run。pressure/recovery/failed-close 尚未在最终统一执行版本取得资格。该部分还没有达到原计划的 B4/M0b/B5 执行合同退出条件。

21 次 anchor_mismatch 表明既有 guard 正确拒绝当前推进的 F5 anchor 与候选不一致；不能将这些拒绝解释成已选定的新执行方案失败。唯一关闭尾部约 7.95 的 shadow accepted 且 `publish_success=[false,false]`，也不能当作 regulator 非零输出或接管证据。

## 3. C3.6 的五个优先实施项

1. **anchor 执行与反馈契约。** 先明确 job freeze、validation、commit 各自使用的左右 anchor 身份、序号、值、publish-start 时间和更新政策。新作者版本做 source-linked 非零/anchor 变更、旧 job/candidate 拒绝、左右 known/unknown 与关闭窗口检查。保持 ready150ms 和 anchor 门；不得延长期限或删门取得通过。退出依据是明确可实施契约和对应反例，而非一次关闭尾部 accepted。

2. **本版本有限工程时间、支持域、失效/恢复/关闭政策。** 给出必要数值的来源与选择理由，固定同 boot command/monotonic 的可证明范围、年龄/RTF/域外处置、HOLD/ramp、部分发布失败、恢复与 close 状态表。约束和资格分开：Master Clock/plant/WCET 未证明项保持 unknown；采用有限工程保证时说明假设和域外动作。保持现有 T200ms、ready150ms、release3s 和25/60/15s，改变必须独立登记。

3. **具体 current dynamic/turn/mixed recipe 与20s有限 shadow。** 先选实际非零输入、转弯/profile/mixed 来源与参数、初态和完整 typed 配置，核验真实输入域和来源时钟，不把参考速度写成实际体速度。事前锁准备/测量/关闭窗口及 raw/source/storage 证据。若只做受控 synthetic shadow，应明确其资格范围；20s动态窗、R5日志压力和plant动态域分别判定，不能由时长或用例标签自动合并。

4. **当前统一源码的压力、恢复与 failed-close 必要场景。** 按受影响路径补新案例，包括首次 DecisionEnqueue 失效顺序、Worker 终端/资源边界、close 并发或失败、原 Source/Witness/transport/storage 尾部及 owned 清理。正常例保持零 hooks；故障例的注入机制和范围单独事前登记。只补新缺口，不重复正常例累计阶段资格，不把旧 R5/close 版本事实转移到新源。

5. **候选执行合同登记与阶段复判。** 运行前就锁定新作者 source/bin/model/config/tools、候选规则和场景预期；上述证据成立后，再用独立执行 profile 完成 B4/M0b/B5 评定与不可变冻结。当前 bounded profile 本身不具备阶段资格。M4 随后单独建立新执行版，证明 F5 owner 退出后 regulator 唯一双路出口、实际非零/部分发布、rho/gap/span/预算与连续反馈/owner 证据；其后实施有限模型/执行事务与候选一致性，再评定 F6/P1。

继续保留已有 dirty、冻结版本、失败、unknown 与原 expected。P2 实际备份/证书、GP/PPO 和研究比较继续在相应执行前置成立之后推进。
