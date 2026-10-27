# W1 事前反思与有限验证选择

2026-10-22，verdict=GO。仅允许一次登记的最小诊断运行：Worker 在受控计算边界驻留
1700 ms，capability 持续发布，Regulator 的 active watchdog 在 1 s 触发。

## 承接

- 53 批 R1/R2/R3：外部信号故障（预授权取消 / SIGKILL / SIGSTOP）。
- W0（55 批）：审计补强，22 项缺口闭合。
- W1 阶段一（本批前半）：v4 诊断 profile 合同层，7/7 契约测试 + 52/52 原有策略回归。

## 为什么必须是新 profile

冻结合同 v3 硬性要求 `fault_injection_enabled==false`（`p1_full_contract.hpp:95`），
而 `Diagnostic` profile 只允许 `no_output`/`shadow`（`:110-111`），watchdog 需要 tick 运行。
v4 是唯一同时满足「允许 execute」与「允许故障能力」的路径，且与 v3 身份完全分离。

## 本 case 的边界

- 刺激：**Worker 自身的** `diagnostic_v2_policy=pre_native_once_after_completed_v1`，
  `diagnostic_v2_block_ms=1700`，在**完成 1 个 job 后**触发一次。
- 不发送任何外部进程信号。
- 观察：Regulator Source 中的 `owned_API_pair` / `capability_admission` /
  `active_watchdog` / `worker_unusable_transition`。

## 预期

| 项 | 期望值 |
| --- | --- |
| 转移原因 | **`active_watchdog`**（不是 lease、不是 process_exited） |
| 刺激到转移 | ≈1000 ms（1 s watchdog），且 **< 1700 ms** stall 时长 |
| stall 期间 capability 年龄 | ≤ 600 ms（租约始终有效） |
| 转移后 fallback pair | ≥1 |
| 转移后新 job / 新 candidate | 0 / 0 |
| 四角色退出码 | 全部 0，仅 SIGINT，组空 |

## 阻断与停止

STOP：身份/配置/source/bin/GID 失配、授权前 API、非法正常激活、未声明丢失/超时/partial、
成功侧回滚、cleanup_failed 或组不空 → 立即结束并保留失败，不重试。

## 未授权

本 case 只证明**计算线程受控驻留**下的 watchdog 行为。
`v2_diagnostic::Block` 的事件明确记录 `actual_native_invoked=false`——
它**不是** native C 内部挂起的证明，那是独立的 W2-native-boundary-hold 义务。

完整 M4、F6、P1、实船接管、plant 接受、硬实时/WCET 全部保持 false。
