# 第53批事前反思与有限验证选择

2026-10-21，verdict=GO。仅允许两个外部信号触发的 owned 故障 case（R1 预授权取消 / R2 Worker 退出），
运行于当前选定源码/ELF/合同身份；不启动新正常校准，不改数值、RTI、权重或半RMSE。

## 承接

- 47 B5/M0b 选定有限工程冻结（4103 项）。
- 49 隔离 nominal 正常唯一出口组件。
- 50 发布/退出源码关联子组件（16 case，return seam）。
- 51 MANUAL+RC 契约纠正（30 检查）。
- 52 主线状态与下一包计划（无新运行）。

## 为什么必须外部信号

冻结合同 `p1_full_contract.hpp:95` 要求 `fault_injection_enabled==false`，且 Regulator 在
`regulator_owned_execute.cpp:99-100` 显式拒绝 `test_delay_ms!=0 / test_native_block_ms!=0 /
diagnostic_v2.policy!="none"` 的 Worker。因此 R2 只能由 Driver 向已认证 Worker 发进程信号，
不能改 Worker 源码注入故障钩子，也不能把外部 kill 描述成 Worker 自身启用了诊断延迟。

## R1（R1-owned-pre-grant-cancel）

边界：四角色认证完成、Recorder 完整 manifest 已绑定进 ready.json、Regulator ready.json 已产生、
grant.json 尚不存在。刺激：对已认证 Regulator 发一次 SIGINT。

预期：`physical_API_calls==0`；Source 含 `owned_prepare_ready` 与
`owned_prepare_closed_before_API`，不含 `job`/`owned_API_pair`/`regulator_shutdown`；
Regulator rc0 且未被 cleanup 阶梯发信号；其余三角色 rc0、仅 SIGINT；四组空。

## R2（R2-owned-worker-exit）

边界：首次真实双侧 API 被接纳（`owned_API_pair` 且 `kind=="accepted"`、`returned==[true,true]`、
`command_invalid==false`）。刺激：对已重新认证的 Worker 单进程发 SIGKILL（不向组发，避免误杀 Driver 组）。

预期：`worker_unusable_transition` 且 `candidate_after/pending_after` 均 false；之后无新 `job`、
无新 `candidate_registration`；≥2 个 fallback/shutdown pair 且 ramp 未越 rho/gap/span；
Worker rc=-9 且 Driver 未向它发信号；Source 缺 `worker_summary`（如实不完整）；
`normal_complete=false` 是期望值而非失败。已提交 DDS 尾部按 `submit_commit_ns < transition.processed_ns` 因果核对。

## 阻断与停止

无阻断理由。STOP：身份/配置/source/bin/GID 失配、授权前 API、非法正常激活、未声明丢失/超时/partial、
成功侧回滚、cleanup_failed 或旧组不空 → 立即结束该 case 并保留失败，不重试。

## 未授权

完整 M4 阶段、F6、P1、实船接管、active watchdog / capability lease / cleanup_failed /
native 阻塞 / 结果延迟丢失 / 其余七组，本批均不闭合。
