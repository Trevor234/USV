# 方案A 第53批当前状态（2026-10-21）

**三个真实 owned 故障 case 在同一选定执行链上通过：R1 授权前取消（零物理 API）、R2 首次真实双侧接纳后 Worker 退出、R3 capability 接收租约过期。完整 M4、F6、P1 仍未验收。**

## 本批实际推进

| 项目 | 结果 |
| --- | --- |
| 派生 | 从 49 复制 82 文件 author 树，仅改写 `owned_m4_fault_driver_v1.py`；C++ 源码 0 改动 |
| 身份重建 | driver SHA `cab011f1…`、bundle SHA 均不同于 49 的 `0680f6cc…` / `d6e3b357…`；6 个 target 全部重建 |
| 组件验证 | 52 native policy + 38 GTest + 14 原生入口拒绝 + 14 Recorder 进程用例，全部通过 |
| 源码复用 | 13 个 Regulator 核心方法体与父版本逐字节相同；Recorder 复用原 ELF `d1b91109…` |
| R1 / R2 / R3 | 24.0 s / 25.5 s / 26.2 s，Driver 均 rc0，外层未发任何应急信号 |
| 审计 | 三个 case 均 `passed=true`，变异自检 2 / 3 / 2 项全部被拒 |
| 锁定输入 | 2500 项 |

## R1：授权前取消

边界：四角色认证完成、Recorder 完整 manifest 已绑定、Regulator ready.json 已写、grant.json 不存在。

| 观测 | 值 |
| --- | --- |
| 物理 API 调用 | **0** |
| Regulator 退出码 | **3**（零 tick 时 Witness `records_consistent` 因 `if(!ts.published)return false` 为假） |
| Source 必含 | `owned_execute_waiting` → `owned_full_recorder_bound` → `owned_prepare_ready` → `owned_prepare_closed_before_API` → `owned_reception_closed` |
| Source 禁含 | `job` / `owned_API_pair` / `regulator_shutdown` / `owned_execute_grant_accepted` / `candidate_registration` |

## R2：首次真实接纳后 Worker 退出

边界：首个 `owned_API_pair` 且 `kind=accepted`、`returned=[true,true]`、`command_invalid=false`。刺激：SIGKILL 单进程。

| 观测 | 值 |
| --- | --- |
| 刺激→失活转移 | **175.7 ms** |
| 转移原因 | `worker_process_exited`，candidate/pending 均清空 |
| 转移后 fallback pair | **6 个**，ramp 全部合规 |
| 转移后新 job / 新 candidate | **0 / 0** |
| shutdown | 零推力成功，grace 未超 |
| Worker | rc **-9**，Driver 未向其发信号，无 `worker_summary`（如实不完整） |

## R3：capability 接收租约过期

边界同 R2。刺激：**SIGSTOP** Worker（冻结而非杀死）。

原理：`pidfd` 的 `POLLIN` 只在进程**退出**时触发，SIGSTOP 不会让 `WorkerLiveness` 报告死亡；但 Worker 停止后不再每 200 ms 发布 capability，因此 600 ms 接收租约自然过期。由于 `unusable_locked()` 幂等且租约检查在 `check_worker_locked()` 中先于 1 s active watchdog，该 case **只可能**由租约触发。

| 观测 | 值 |
| --- | --- |
| 刺激→失活转移 | **775.5 ms**（> 600 ms 租约，< 1000 ms watchdog，证明是租约） |
| 转移原因 | `worker_capability_expired` |
| 转移前 accepted pair | **6 个** |
| 转移后 fallback pair | **4 个**，ramp 合规 |
| Worker | 被 Driver SIGCONT 恢复后自行正常关闭，rc 0、仅 SIGINT |
| shutdown | 零推力成功，grace 未超 |

## 结构性阻断（如实记录，未闭合）

`active watchdog` **无法**用外部信号隔离，理由已写入 `implementation/W1_watchdog_not_isolable_v1.json`：

- watchdog 要求在 `worker_active_ != 0` 持续超过 1 s **且** Worker 继续发布 capability；
- 任何冻结 Worker 的外部信号同时停止 capability 发布，600 ms 租约必然先过期；
- `unusable_locked()` 幂等，watchdog 分支此后再无机会执行。

要隔离它需要「capability 持续到达但 active job 停滞」的路径，即故障能力 Worker——冻结合同禁止 `fault_injection_enabled=true`，Regulator 也在 `regulator_owned_execute.cpp:99-100` 显式拒绝。需新合同变体或 Driver 侧 native 停滞机制，属后续工作包。

## 其余九组的可行性判定

| 组 | 外部信号可行 | 阻断点 |
| --- | --- | --- |
| native_block_and_delivery | ❌ | Regulator 拒绝 `test_native_block_ms!=0` 的 Worker；延迟发布需 Worker hook |
| candidate_identity_shape | ❌ | 伪造 candidate 需匹配 Worker GID，`owned_input()` 的 fixture receipt 会拒 |
| state_clock | ❌ | `/clock` 由 Fixture 独占 GID，pause/jump 无法外部注入 |
| task_reference | ❌ | path/profile 由 Fixture 发布，需改 Fixture |
| compatibility_input | ❌ | F5 来源同一性需另一套冻结来源；独立 fixture 需变体 |
| actual_source_recording[1] | ❌ | 队列压力需注入高负载 |
| time_boundaries | ⚠️ 部分 | 150 ms 截止可被 SIGSTOP 间接触发 |
| anchor_fallback | ⚠️ 部分 | 5-miss/HOLD 可被 SIGSTOP 间接触发 |
| cleanup failed | ❌ | 属 Driver 侧逻辑，非 Regulator |

**结论：剩余六组必须修改 C++ 或引入新的合同变体，不能靠外部信号继续推进。**

## 覆盖台账变化

- `publication_exit`：R1 闭合「shutdown before submit」、R2 闭合「worker death」、R3 闭合「capability lease」。
  **`active watchdog` 结构性不可隔离，`cleanup failed` 仍开放**，整组仍 `false`。
- `actual_source_recording`：故障 profile 的容错读取已验证，队列压力仍开放。
- 其余 7 组无变化。

## 未取得

完整 M4 阶段、F6 已知模型事务、P1 联合验收、实船接管、plant 接受、硬实时/WCET、
GP 合格数据、研究优越性结论——全部仍为 false。`production_physical_release_enabled` 保持 false。

## 下一步

剩余六组需要 C++ 改动或合同变体，已超出「外部信号故障包」的范围。建议先决策：

1. 是否派生带限定故障能力的 Worker 变体（用于 native block / delivery delay）；
2. 是否派生可注入 path/profile/clock 的 Fixture 变体（用于 state_clock / task_reference）；
3. 或把剩余组按「需新合同版本」登记为后续工作包，先转入 F6 已知模型事务。
