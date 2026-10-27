# 方案A：第58号W2组件审查与修正实施状态

日期：2026-10-22（北京时间）。审查 57 包 gate/pipe 组件与审计 v3，并实施其 §6–§7.2 的修正；未做 Worker 接线，未启动 ROS 或 NMPC 实验。

主报告：[W2组件与审计v3代码审查及接线计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_component_review_20261022_58/documents/方案A_W2组件与审计v3代码审查及接线实施计划_2026-10-22.md)。
实施记录：[W2组件小修与审计补强实施记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_component_review_20261022_58/documents/W2组件小修与审计补强实施记录_2026-10-22.md)。

## 审查结论（已复现）

- 重新执行原 19 项组件、12 项 pipe、7 个变异，结果与原报告一致。
- 审计 v3 三例 baseline 与原四个反例结果成立；MPC 八项文件一致。
- **新增补测复现四条缺陷**：
  - EINTR 成功路径少记约 100 ms（实际 200.3 ms，报告 100.1 ms）。
  - 600 ms Gate 预算在约 750 ms 后仍返回 `released`。
  - 读取期间 stop 置 true 仍返回 `released`。
  - 三角色配置共同偏离合同、Driver `tool_sha256` 错误，v3 仍通过。
- `const bool *` 不能作为 `atomic<bool>` 的 relaxed 视图。
- 接线文档 `pass_fds=(write_fd,)` 方向错误，应为 `read_fd`；作用点应保持在内部 `BeforeCall`。

## 已实施（本次）

派生副本，未改 56/57 源码。

**组件 v2**（`implementation/w2_gate_v2/`）：
- EINTR 计时从调用入口统一测量，所有返回路径一致。
- 预算改为绝对期限，分片 50 ms；装配后复查 stop 与 deadline。
- stop 接口改为 `StopPredicate`，读取后再次检查。
- **22 + 13 = 35 项测试全绿，7 个变异全部被捕获。**

**审计 v4**（`implementation/audit_v4/`）：
- 完整配置基准改为已固定合同 `c`（原为 Worker 自己的声明）。
- Driver 工具 SHA 改用真实字段 `tool_sha256` 并要求存在。
- 变异比较改为同层次 `(mutated, original)`。
- **三例 baseline 通过，六个反例全部由正确断言拒绝**（新增两个：三角色共同偏离合同、Driver 工具 SHA）。

**FD exec 验证**（`implementation/w2_fd_exec/`）：
- 真实 `execve` 后 9 项检查全部通过：Worker 只见读端、只持该通道一次、读端不可写、兄弟角色无 pipe、写端未关无 EOF、帧完整到达、关写端得 EOF、写读端被拒。
- 用 pipe inode 身份比较，不用 fd 号（fd 号是每进程的）。
- **这直接证实了 57 包文档的 write_fd 方向是错的。**

## 未做

- §7.1 作者树派生与源码接线。
- §7.3 `BeforeCall` 内部 hook 挂接、Driver 释放逻辑。
- 任何 W2 owned 运行；跨多拍的过期分支仍未验证。
- `kDuplicateRelease` 仍无实际返回路径（gate 用 `done_` 保证只消费一次）。

## 版本时间线

`audit_diagnostic_v2.py`：首次 57 号封存快照为 54526 字节 `b0d4ab22…`，本次读入为 58973 字节 `28414eb4…`。`28414eb4` 是本次工作起点，本次全程未再改动。不推断变更来源，作为独立版本登记。三个 `_05` run 及其他 130 项未变。

## 边界

- 所有 `probe_*`/`passed=true` 均为内存篡改输入，是**漏检证据**，不是有效运行或阶段资格。
- 组件、接线验证、阶段资格、研究结论分账。
- 完整 M4、F6、P1、plant 接受、硬实时及研究结论保持 false。
