# 方案 A：Capability 租约代码与实行记录的独立审查

审查日期：2026-10-13（Asia/Shanghai）。审查对象为第 07 批封存的 `authored_D1_C3_3_20261012_v9`。本次只读审查历史源码、原生回调日志与实行记录；新增本目录中的说明、离线复现脚本和结果。未修改业务代码、N9 作者目录、封存文档、原运行记录或资格字段，未启动 ROS/Gazebo。

## 结论

发现 1 项应在 C3.4 优先关闭的 **P2 检查器泛化缺口**：运行端以最后一次有效续约维护 Capability 租约，而离线原子观测检查器在实际门禁读到 `worker_valid` 时，要求最后一条 Capability admission 必须有效且已续约。有效续约后到达非终态无效包或 foreign 包，运行端会正确保留原租约；原检查器会拒绝该合法状态。

这已明确登记在 [C3.4 原最小计划](/home/trevor/MPC/scheme_A_C3_3_20261012_07/next_minimal_plan_C3_4.json) 第 7–8 行，不是本次发现的未披露运行端退化。N9 检查器自身把 Capability 证据范围限定为正常完整发布人口，并明确 `foreign_invalid_terminal_capability_covered=False`；现有正常 fixture 的组件结论仍受原范围约束。不能据此把 C3_general、D1、M0b、M4、F6、P1、execute 或研究结论改为 true。

## 发现 1：[P2] 离线 `cap[-1]` 门禁绑定应按 last-valid-renewal 重放

### 位置与实际行为

| 对象 | 准确位置 | 审查所见 |
|---|---|---|
| 运行端 Capability callback | [regulator_shadow_observer.cpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/regulator_shadow_observer.cpp:408)（408–421 行） | 先检查资源，再在原 mutex 下检查 liveness/租约；identity 不符不续约；匹配 identity 的 fatal 或 instance 变化触发不可逆 unusable；只有 `valid && !worker_unusable_` 才续约、设置 worker_valid 和更新 last_capability。 |
| 运行端租约类 | [p1_capability_lease.hpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/observer/src/shadow/p1_capability_lease.hpp:14)（14–24 行） | 用最后有效续约时间计算 age；严格 `age > timeout` 才过期，等于 timeout 仍有效；过期/时钟错误原因不可逆。 |
| 原子观测离线绑定 | [check_atomic_observation_v2.py](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/check_atomic_observation_v2.py:760)（760–762 行） | 取 `validation_commit_ns <= final_commit_ns` 的 admission，随后要求 `cap[-1]` 同时 valid、identity_valid、renewed 且未过期。未搜索并重放最后有效续约。 |
| 继承正常人口检查 | [validate_readiness_v3.py](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/validate_readiness_v3.py:369)（369–403 行，尤其 389–393 行） | 所有 typed/admission 都必须符合正常身份，所有 admission 都必须 valid/renewed；每条 admission 都把 `last` 推进到其 commit。这是明确的 normal-only 检查，单改 762 行无法让无效/foreign 场景通过。 |
| 检查器自身范围 | [check_atomic_observation_v2.py](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9/check_atomic_observation_v2.py:244)（244–287 行） | 名为 `Closed normal Capability population`，把 foreign/invalid/terminal 覆盖标为 false；publisher payload 中 fatal 固定 false、reason 固定空串。 |

触发顺序为：有效 Capability 在 t0 续约；在期限内 t1 收到 backend 不符、horizon 不符、dt 不符或 foreign 身份 Capability；原 callback 不续约但保留 last_valid=t0；t2 门禁仍能读到 worker_valid=true。只要 t2−t0 不超过原 timeout 且未发生终态事件，这个运行端状态合法。当前检查器因最新 admission 为无效或 foreign，误拒绝该泛化场景。

在 shadow 正常 fixture 中，所有已接纳 Capability 都是正常续约，因此这个问题不会自动推翻该 fixture 的已报告组件结果。它阻止把目前检查器用于 C3.4 非正常 Capability 证据，也阻止据此宣称通用 lease 认证闭合。

### 独立离线复现及适用边界

脚本：[reproduce_lease_predicate.py](/home/trevor/USV/.sgh-research/experiments/scheme_A_review_20261013_08/review_lease/reproduce_lease_predicate.py)。结果：[lease_predicate_evidence.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_review_20261013_08/review_lease/lease_predicate_evidence.json)。

复现从原 checker AST 提取 `worker_valid_lease_source_binding` 的原表达式，不导入或修改其模块。输入来自 N9 `native_matrix03` 中的实际 callback source 日志，保留每个输入 SHA256。取末条 admission commit+1 ns 作为**假设提交时间**，并按 callback 的已记录状态和原测试断言使用假设 `commit_worker_valid=true`，用来展示原局部谓词与运行规则的差别。这些假设字段没有写回原日志，不是假称记录到新的 Decision。

| 保留的实际原生回调场景 | 假设提交相对最后有效续约的 age | 原局部谓词 | last-valid 加终态规则 | 说明 |
|---|---:|---|---|---|
| InvalidAfterValidKeepsLease | 82,464 ns | false | 可用 | 后续 invalid 不更新有效续约；600,000,000 ns 原期限尚未到。 |
| ForeignAfterValidKeepsLease | 66,115 ns | false | 可用 | foreign 的 fatal 标志也不应使匹配 Worker 终止。 |
| ResourceRejectedAfterValidKeepsLease | 1 ns | true | 可用 | resource rejection 在 admission 外返回，最后 admission 仍为有效续约；边界对照。 |
| ExpiredLeaseIsIrreversible | 见结果 | false | 不可用 | 原日志已有 `worker_capability_expired` 终态；即便后续再次送正常包也不可恢复。 |
| ChangedInstanceIsTerminal | 见结果 | false | 不可用 | 匹配 identity 的 instance 变化已触发不可逆终态。 |
| MatchingFatalIsTerminal | 见结果 | false | 不可用 | 匹配 identity 的 fatal 已触发不可逆终态。 |

原 `native_matrix03/gtest.xml` 中上述六个 case 均为 completed、0 failure；此次只读取这些历史结果，没有重跑原生测试。对 `owned_C3_3_positive_01` 的实际 Source Decision 还逐项计算了同一个原局部谓词：实际到达 `commit_worker_valid` 的 **1 个** Decision 通过。该数字是一个局部谓词的计算次数，不是新的原生测试数、全 checker 通过数或网络测试数。

此次新增运行端测试=0、网络测试=0、完整 checker 重跑=0。六个 direct callback 的原 scope 明确 `raw_network_authenticated=false`，其 fixture 前置状态可注入。不能把本离线证明计为 actual wire、Master Clock、严格全链或阶段资格。所有被读历史输入在计算前后摘要一致。

## 相邻规则核对

1. `CapabilityLease` 使用 receipt/validation commit，WorkerCapability v1 没有每包发送时间和序号。不能把租约有效解释为源包新鲜、求解有进展或没有重复包。现有类注释与实行记录一致。
2. valid 但未 renewed 的包不能恢复过期租约：callback 先 `check_worker_locked`，再检查 valid 与 worker_unusable；lease 的错误原因也不可逆。C3.4 若仅过滤 `valid=true` 行，会引入比当前误拒绝更严重的错误接纳。
3. identity 匹配但 instance 改变，即使 backend 等字段无效，也会终止旧 Worker；匹配 fatal 同样终止。foreign fatal 不终止本角色。不能把所有 invalid 都简单归类为“忽略包”。
4. resource_rejected 不产生 capability_admission；应保留实际 resource rejection 证据，不能为它补造续约或 admission。callback 资源拒绝不取消已有有效租约，租约检查仍由原 tick/Worker 检查路径执行。
5. 运行端门禁在原锁下读取 worker_valid，相关 callback 不能在该提交临界区中穿插；目前没有逐 operand 时间。C3.4 不能仅凭诊断写入时间创造更细的跨线程总序，也不能改变原锁序或在控制路径中增加阻塞 I/O。

本次未确认额外影响已认证 normal-only fixture 的 lease/checker 缺陷。上述 2–5 是修复时必须保留的约束，不是本次新增资格结论。

## 建议的 C3.4 最小工作包

1. **另建作者与审查目录并预登记。** 保留 N9 与 batch07 原字节；冻结 callback 规则、原 timeout、所用 Source/wire/storage join 和有限场景。若要支持异常 payload，使用明确的独立证据生产者角色和认证边界，保留零故障 hook/owned 原政策。
2. **新增通用 Capability 状态重放。** 从实际 callback 的 identity/valid 判定、资源拒绝、租约 check、terminal transition 重建 last-valid-renewal、worker_valid、worker_unusable、当前实例。每条 admission 的 before/after/renewed/terminal 都独立计算，不能直接相信这些日志布尔值；normal-only 检查作为兼容模式保留。
3. **绑定每个真正读取的门禁。** 依据该 Decision 的原提交窗口与已认证历史求有效状态；短路未读保持 null。允许非终态 invalid/foreign 保留旧租约，同时拒绝无有效续约、age>timeout、终态后恢复和 backward/invalid clock。不要只把 `cap[-1]` 换成最后 valid 行。
4. **先完成离线有限矩阵，再补 authenticated wire。** 至少含有效→invalid→gate、有效→foreign→gate、资源拒绝、匹配 fatal、instance 更换、恰好 timeout、timeout+1、重复有效 payload、到期后有效包不可复活。原生 actual callback、离线 checker、wire/storage 各自报告结果；任一缺失都保持相应范围未认证。
5. **增加有意义的语义负例。** coherent 改写 renewed、before/after、terminal、门禁 worker_valid 或无效 payload 身份后，须由独立规则拒绝；Source/typed/CDR/GID/storage 一致仍应拒绝语义造假。普通解析失败不计语义负例成功。
6. **限定交付结论。** normal-only 回归通过、通用有限 lease 组件通过、authenticated 异常 wire 有界验证通过分别记账。单项 lease 闭合不能独自升级 strict full chain；publisher receipt/IO 边界、shared-v2 四工具身份、formatter 域、动态 recipe/clock 政策仍需原计划分别关闭。

验收原则：原正常 fixture 不回退；无效/foreign 包不会延长租约；有效期限等号边界保持；过期/fatal/instance 终态不可恢复；实际 producer/source/transport/storage 认证不因新场景而放宽；旧失败证据与旧资格标记保留。

## 与实行文档的对应

- [第 07 批当前状态](/home/trevor/MPC/scheme_A_C3_3_20261012_07/current-status.md) 已写明“通用 lastvalid 离线租约证据”未闭合，本次源码与离线复现支持这一状态。
- [C3.4 原最小计划](/home/trevor/MPC/scheme_A_C3_3_20261012_07/next_minimal_plan_C3_4.json) 明确优先 last-valid-renewal 而非 last-receipt，方向正确；建议把实现任务扩展为“通用状态重放 + admission 分类 + 门禁绑定 + authenticated 有限 wire”，避免仅改一处 `cap[-1]`。
- [逐步讲解文档](/home/trevor/MPC/方案A_从基线修复到C3_3_逐步讲解_2026-10-12.md) 可补一段具体例子：C3.3 actual callback 测试已证明 invalid/foreign 保留租约，但当前离线 checker 只认证正常人口，因此这两项不是同一证据闭合。不要把本次局部 AST 复现写成通用 C3.4 实施完成。
