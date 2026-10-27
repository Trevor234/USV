# W1：最小诊断 Worker 与 active watchdog 隔离 — 结果

日期：2026-10-22　工作包：W1
状态：**合同层 + 运行侧完成；首个登记诊断 case 通过**

---

## 1. 结论

`active_watchdog` 第一次被**独立隔离**并观测到。它与 R3 的租约过期路径被严格分开：

| | R3（53 批，SIGSTOP） | W1（本批，计算线程驻留） |
| --- | --- | --- |
| Worker 心跳 | **停止** | **继续（stall 期间 6 次续租）** |
| 最大续租间隔 | 不适用 | **201.0 ms**（定时器 200 ms） |
| 转移时 lease 年龄 | **792.4 ms** > 600 → lease 过期 | **192.6 ms** < 600 → lease 有效 |
| 失活原因 | `worker_capability_expired` | **`active_watchdog`** |
| stall 时长 | 进程冻结（不可测） | **1700.1 ms**（与登记值一致） |

**这证明**：整进程 SIGSTOP 无法隔离 watchdog（心跳先停、lease 先过期），而"计算线程停住 + 心跳继续"可以。

---

## 2. 做了什么

### 2.1 新增 v4 诊断 profile

| 项 | 内容 |
| --- | --- |
| schema | `p1-execution-contract-v4` |
| qualification | `execution_diagnostic_only` |
| `execute_qualified` | **false** |
| `parameters_are_diagnostic_only` | **true** |
| `fault_injection_enabled` | **true** |
| parameter profile | `P1_owned_diagnostic_worker_20261021_01` |
| 合同 SHA256 | `3a8451d5172423adbef955d78c8550d67bbeec4582a80bd9ba69028b867b9f06` |
| 允许 mode | `no_output` / **`execute`** |

**v3 冻结合同的接受与拒绝规则逐字保留**——`test_m4_native_policy` 的 52 项全部保持原行为。

### 2.2 修改的 12 个位置

| 层次 | 文件 | 改动 |
| --- | --- | --- |
| 合同 | `p1_full_contract.hpp` | `ContractProfile::DiagnosticExecute`；v4 分支；v3 拒绝规则不变 |
| 合同 | `p1_resources.hpp` | v4 与 v3 共用正式资源分支 |
| 身份 | `m4_owned_runtime.hpp` | `diagnostic_scope` / `diagnostic()` / `diagnostic_profile()`；`contract()` 分流；`context()` 与 `grant_fields()` 按 scope 成对校验 |
| 身份 | `owned_worker_peer_c37_v1.hpp` | Worker peer 接受 v3/v4，要求 profile 与 parameter_profile 成对匹配 |
| 策略 | `owned_execution_policy_native_v1.hpp` | `context_gate` 为 v4 放行 execute |
| 节点 | `regulator_owned_execute.cpp` | 拒绝断言拆成互斥的两支；`scope_` 成员 |
| 节点 | `synthetic_source_m4.cpp` | `run_scope_` 成员 |
| 节点 | `solver_worker_m4.cpp` | 走 `m4_owned::contract()` |
| 工具 | `owned_m4_diagnostic_driver_v1.py` | 注入 1700 ms stall；无外部信号；读 Worker Source 的 stall 事件 |
| 工具 | `seal_selected_runtime_diagnostic_v1.py` | 新建（不复用 53 批 seal） |
| 工具 | `run_diagnostic_once_v1.py` | 参数化 |
| 构建 | `author/CMakeLists.txt` | 新 target + include 路径 |

### 2.3 构建与验证

| 项 | 结果 |
| --- | --- |
| 构建 target | **7/7**（6 个原有 + `test_v4_diagnostic_contract`） |
| v4 契约测试 | **7/7 通过** |
| 原有策略回归（v3） | **52/52 通过** |
| 锁定输入 | 1539 项 |

---

## 3. 登记 case 的实测结果

**Run**：`M4_diagnostic_W1_20261022_01`，耗时 25.4 s，自动重试 0，外层未发应急信号。

| 观测项 | 值 | 判据 |
| --- | --- | --- |
| stall 进入 | ✅ | Worker Source `diagnostic_v2_pre_native_enter` |
| stall 释放 | ✅ | Worker Source `diagnostic_v2_pre_native_release` |
| stall 时长 | **1700.1 ms** | 与 `diagnostic_v2_block_ms=1700` 一致 |
| stall 期间 capability 续租 | **6 次** | 心跳未停 |
| 最大续租间隔 | **201.0 ms** | < 600 ms lease |
| 失活原因 | **`active_watchdog`** | ✓ |
| 转移时 lease 年龄 | **192.6 ms** | < 600 → 不是 lease |
| active watchdog 行 | **4 次** | 每 tick 重复，持续捕获 |
| 转移前 API pair | 8 | 业务已正常运行 |
| 转移后 API pair | 3 | fallback |
| ramp 合规 | ✅ | gap/span/rho 未越界 |
| 转移后新 job | **0** | 正确停止提交 |
| 转移后新 candidate | **0** | 正确停止激活 |
| 四角色退出 | 全部 rc 0、group_empty | Regulator 的 SIGINT 由 Driver 发 |

---

## 4. 过程中修掉的 14 个真实问题

| # | 问题 | 层 |
| --- | --- | --- |
| 1 | `formal_profile_overrides()` 缺 v4 profile | 合同 |
| 2 | v4 走错资源合同分支 | 合同 |
| 3 | Regulator 缺 `v2_diagnostic_block.hpp` | 构建 |
| 4 | Fixture 局部 `scope` 遮蔽全局常量 | 节点 |
| 5 | `test_m4_activation_alignment` 缺 include 路径 | 构建 |
| 6 | Driver / run harness 断言仍是 53 批值 | 工具 |
| 7 | 锁文件 pin 了尚未创建的 launch 脚本（自指） | 工具 |
| 8 | `owned_worker_peer_c37_v1.hpp` 只认 Frozen | 身份 |
| 9 | `context_gate` 强制 Frozen + 只允许 `no_output` | 策略 |
| 10 | `context()` 硬编码 `own.m4_release_scope==scope` | 身份 |
| 11 | `grant_fields()` 的 scope/contract/index 三元组全绑 frozen | 身份 |
| 12 | `context()` 的 `freeze_evidence_sha256` / `policy_sha256` 未随 scope 切换 | 身份 |
| 13 | Driver 从 Regulator Source 找 stall 事件（实际在 Worker Source） | 工具 |
| 14 | Driver 的 `capability_age_ns` 字段不存在（实际是 `lease_last_after_ns`） | 工具 |

**每一处都是真实的分层防御**：每跑一次暴露下一层。这正是 54 号文档要求的"不能只把一个 bool 改成 true"的实证。

---

## 5. 证据边界（必须保留）

### 5.1 这是「计算线程受控驻留」，不是「native C 内部挂起」

`v2_diagnostic::Block` 在**调用 `solve_owned()` 之前** sleep
（`solver_worker_m4.cpp:158/163` vs `:168`），且所有 stall 事件硬编码
`actual_native_invoked=false`、`native_C_hang_claimed=false`。

**W1 不能关闭 `native_block_and_delivery` 组的 native 阻塞义务。** 那是独立的
`W2-native-boundary-hold` case，需要覆盖真实调用边界的适配实现。

### 5.2 未证明的项

| 项 | 状态 |
| --- | --- |
| capability lease 过期（另一条路径） | 已由 53 批 R3 覆盖 |
| worker 进程退出 | 已由 53 批 R2 覆盖 |
| cleanup failed | 未覆盖 |
| 结果投递延迟 / 丢失（W3/W4） | 未覆盖 |
| 完整 M4 阶段 | **false** |
| F6 / P1 / 研究结论 | **false** |
| plant 接受 / 硬实时 / WCET | **false** |

### 5.3 身份隔离

诊断 scope 有独立身份：新 bundle SHA、新 scope 字符串、新 contract SHA。
它与 47/49/53 的任何冻结资产**不共享资格**。

---

## 6. 交付物

```
scheme_A_M4_diagnostic_worker_20261021_56/
├── author/                          # 12 处修改
├── implementation/
│   ├── p1_execution_contract_v4.json
│   ├── selected_runtime_registry_v1.json
│   ├── W1_registration_v1.json
│   └── m4_topics_v1.json
├── preflight/{prerun_source_lock_v1.json, preflight_reflection_v1.md, frozen47_verification_v1.json}
├── verification/component_verification_v1.json
├── build/diagnostic_attempt01..07/  # 失败全部保留
├── runs/W1_01/                      # 首次登记诊断运行
└── documents/                       # 本文件 + 阶段一报告
```

**未修改**：47/49/50/51/53 的归档原件、`audit_fault_v1/v2.py`、W0 的产物。

---

## 7. 下一步

按计划：

1. **W1 剩余 case**：`W2-native-boundary-hold`、`W3-result-delivery-delay`、`W4-result-delivery-drop`
2. **W2**：按九组差集补 Fixture（注意 `task_reference` 的替换义务受 `task_time_profile_v1.hpp:35-42` 的静态直线域限制）
3. **M4 复判**（W2 后统一）
4. **W3 / F6**：有限模型事务
