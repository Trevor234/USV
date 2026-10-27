# 方案A：第57号审查包当前状态

日期：2026-10-22（北京时间）。仅审查 56 包 attempt18 的 W1/W3/W4 各自 `_05` 结果，并承接其两项后续实施；不是新的控制实验。

主报告：[第56批收尾审查与W2独立释放实施计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_review_20261022_57/documents/方案A_第56批收尾审查与W2独立释放实施计划_2026-10-22.md)。

## 已完成

### 审查（原主报告）

- 1541 项原锁定输入无失配，84 项作者 bundle 成员一致，三例 registration/Driver/实际角色 ELF 身份链一致。
- 三份原审计只读重放通过。另行复算支持 W1 租约年龄、W3 投递延迟、W4 目标 tick/HOLD/恢复/idle 状态，capability Source 与 Stored 逐字段一致。
- 原审计仍接受 4 类私有错误输入：W1 已过期租约、W3 零投递延迟、W4 active 未清零、错误 manifest ELF SHA。

### 任务 1：离线审计 v3 补丁（已完成）

文档：[审计v3_注册条件与身份链补丁](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_review_20261022_57/documents/审计v3_注册条件与身份链补丁_2026-10-22.md)。

- **根因比原记录更直接**：`check_role_identity()` 与 `check_registration_pins()` 在 v2 中已实现但**从未被 main() 调用**。身份链不是"检查太弱"，而是根本没执行。
- 新增 `check_case_W1/W3/W4`，直接读 registration 的 `expected` 并测量：W1 独立重算租约年龄并要求 stall 跨过转移瞬间；W3 从 raw 时间重算延迟并要求实测超 deadline；W4 要求丢弃 Job 的目标 tick 为 `no_candidate`、精确 idle 窗口内 active 清零、之后恢复接受。
- 新增 capability Source ↔ Stored 完整 typed 多重集对账（16/16、8/8、11/11）。
- 变异harness 拆成 prepare/check 两步：无法施加的变异记为 `inapplicable`，**不再算作拒绝**——这正是原工具把 W3 `m_hold` 准备期 AssertionError 计进 7/7 的原因。
- 每个 case 必须由其**注册条件**对应的变异实际拒绝，否则审计失败。
- 更正 W1 claim 文字（原写 "watchdog must not fire"，与实际相反）。

结果：三例 baseline 全部通过；四个反例全部由明确断言拒绝（附拒绝原文）。

### 任务 2 步骤 1：W2 release gate 组件 + pipe 层（已完成，仅组件）

文档：[W2步骤1_私有pipe_release_gate组件](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_review_20261022_57/documents/W2步骤1_私有pipe_release_gate组件_2026-10-22.md)。

- 新增 44 字节单次释放帧，绑定 run/Job/ordinal/nonce/release-sequence + CRC32。
- 十种互不相同的终局（含 `timeout` vs `partial_frame`、`bad_crc` vs `identity_mismatch`）。
- 组件不持任何共享锁；`stop_requested` 由调用方传入，组件不为同步策略做决定。
- **19 个单元测试 + 12 个真实 pipe 测试全绿；7 个变异全部被捕获。**
- **变异测试发现并修掉了两个真实缺陷**：
  - EINTR 记账错误——初版把整个请求 slice 计入已等待时间，一次信号就烧光预算，普通信号投递会被误报成“Driver 从未释放”。
  - 无效 fd 干等整个预算——初版返回 −1（超时）而非 0（EOF）。
  - 这两条若不带 pipe 层测试与变异自检，会一路带到 owned 运行，症状是“W2 偶发超时”。

## 尚未做

- **W2 接线与 owned 运行**：进程是否真的停在 native 边界、Driver 是否只向 Worker 继承读端、跨多拍后的过期分支，均未验证。需新派生作者树、重建、重新登记。
- Fixture 差集 → M4 复判 → F6 → P1：按原顺序，未开始。
- 未复核 47/49/50/51/53 全部历史目录，也未逐项检查 superseded 材料。

## 重要边界

- `evidence/auditor_replays/probe_*` 中的 `passed=true` 是原 v2 漏检的证据，**绝非**有效运行通过或阶段资格。v3 对应目录（`evidence/audit_v3_replays/probe_*`）中同样输入均被拒绝。
- 任务 2 只完成组件层，**不提升任何矩阵子项**。
- 完整 M4、F6、P1、plant 接受、硬实时和研究结论均保持 false。
- 56 包原件未修改：`audit_diagnostic_v2.py` SHA 仍为 `28414eb4…`，run 目录无新文件，未启动 ROS 进程。

## 产物索引

| 产物 | 入口 |
| --- | --- |
| 审计 v3 工具 | `implementation/audit_v3/audit_diagnostic_v3.py` |
| 审计 v3 验证 | `implementation/audit_v3/run_audit_v3_verification.py` → `evidence/audit_v3_replays/verification_v1.json` |
| 审计 v3 交付记录 | `evidence/audit_v3_delivery_v1.json` |
| W2 gate 组件 | `implementation/w2_gate/w2_release_gate.hpp` |
| W2 pipe 适配器 | `implementation/w2_gate/w2_pipe_reader.hpp` |
| W2 gate 单元测试 | `implementation/w2_gate/test_w2_release_gate.cpp` |
| W2 pipe 集成测试 | `implementation/w2_gate/test_w2_pipe_integration.cpp` |
| W2 gate 验证 | `implementation/w2_gate/run_component_verification.py` → `evidence/w2_gate/component_verification_v1.json` |
