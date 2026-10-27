# 方案A：第59号W2接线前复核与内部hook实施状态

日期：2026-10-22（北京时间）。复核 58 包组件 v2、审计 v4 与非 ROS FD 验证，并实施 59 号计划 §4–§6.2 的内部 hook 接线；未做 §6.3 登记与 §6.4 owned 运行。

主报告：[W2接线前复核结论与内部hook实施计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_pre_wiring_review_20261022_59/documents/方案A_W2接线前复核结论与内部hook实施计划_2026-10-22.md)。
实施记录：[W2内部hook接线实施记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_pre_wiring_review_20261022_59/documents/W2内部hook接线实施记录_2026-10-22.md)。

## 复核（本次重放成立）

- 组件 v2：22 + 13 = 35 项通过，7 个变异全部命中。
- 审计 v4：三例 baseline 与六个反例重放一致。
- 原 FD 脚本的继承/隔离成立；其收帧与 EOF 是父进程回环，已在 59 号计划中指出并由真实 C++ exec 补证。

## 已实施

**派生作者树** `implementation/w2_author/`（自 56 包 author 派生，未改原件）。

**内部 hook 接线**：
- 新增 `worker/w2_native_boundary.hpp`：gate 等待窗口与 Job 绝对截止分别管理，五个互不相同的终局（`not_armed`/`allowed`/`expired`/`stopped`/`wait_failed`）。
- `worker/owned_cold_backend.hpp`：在内部 `invoke` 的 deadline 检查之后、`solver_.step` 之前挂 gate；`actual_native_invoked` 只在 guard 通过后置位。
- `worker/solver_worker_m4.cpp`：校验继承 fd 为只读 pipe、拒绝无诊断 profile 的启用、绑定 Job+ordinal、发出 `w2_boundary_entered`。
- Driver：建私有 pipe，`pass_fds=(read_fd,)`，spawn 后立即关闭父进程读端；观察到边界进入后，等至少两个完整业务 tick 再发单次 release。

**验证**：`native_boundary` 15/15、`backend_wiring` 5/5，5 个变异全部被捕获。真实 C++ exec 验收器（`verify_exec_gate.py`）在 v2 头文件下 5 例通过，已纳入本包工具。

## 变异测试抓到的真实缺陷

**Backend 把非注册调用误判为拒绝。** 初版写 `if (boundary_ && boundary_->enter(...))`，而 `enter()` 对非匹配调用返回 false，于是 Job 1 的全部调用都会抛 `w2_boundary_not_armed`。修法是先问 `matches()` 再进 gate。这个缺陷只在接线后出现，单独的 boundary 测试发现不了。

## 如实记录的不足

- boundary 里 `gate_->wait()` 之后的 `stop_at_release` 检查在当前 v2 Gate 下**不可达**（Gate 自己先返回 `stop_requested`）。已从变异列表中移除，文档记为“不可达的纵深防御”，不称为已覆盖。
- 未做 §6.3 registry/registration 新生效，新 Driver/bundle/ELF 身份未固定，本树不能作为 owned run 的合法来源。
- 未做 §6.4 最小 owned W2；`expired` 终局在真实路径下的生命周期（继续服务还是隔离退出）未定。
- `kDuplicateRelease` 仍无实际返回路径。
- `verify_exec_gate.py` 的接收端不是 Worker ELF，其 `actual_native_invoked=false` 不能被读成“真实 Backend 过期 guard 已验证”。

## 资格

| 层次 | 状态 |
| --- | --- |
| Gate/PipeReader 组件 | 35 项 + 7 变异，重放成立 |
| 审计 v4 | 三例 baseline + 六反例，重放成立 |
| 内部 hook 接线 | 20 项测试 + 5 变异，本次新增 |
| 真实 exec 补证 | 5 例通过 |
| registry/登记 | 未做 |
| 最小 owned W2 | 未做 |
| 完整 M4、F6、P1 | false |
| plant 接受、硬实时、研究结论 | 未取得 |

## 下一步

§6.3 构建与登记 → §6.4 最小 owned W2 → W2 审计 → Fixture 差集 → M4 复判 → F6 → P1。

未修改 56/57/58 原件；未启动 ROS、NMPC 或硬件控制；用户并行工作区保留。
