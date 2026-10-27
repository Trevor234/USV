# C3.6 shadow adapter 与 batch11 后续计划对应复核

日期：2026-10-13。只读审查新 N13 源码、登记及 parent batch11 计划，新增本报告与 JSON。此处记录读取时点；v2 构建、native 和真实 4s 运行由本批后续结果决定，未提前声明成功。缺项是后续实施范围，不阻止已登记的有界 shadow 组件验证。

## 与前一批五步计划的对应

依据 [batch11 后续实施计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_20261013_11/方案A_C3_6A后续实施计划_2026-10-13.md) 和 [本批登记](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/preregister/adapter_scope_v1.json)：

| 原计划 | 本批已写入新源码的行为 | 当前结论边界 |
| --- | --- | --- |
| 1. runtime adapter 与 owner lifecycle | 在真实决策 mutex 接入完整冻结 Job/prediction、ready/cutoff、观察消费与取消；Applied 增加真实 MessageInfo GID、typed peer pins、进程 pidfd；driver request/ack 与其他关闭事实分开 | 实现正在验证；Worker callback GID、owner 原生 close intent 和全寿命 endpoint 连续证据尚未补齐 |
| 2. 许可到实际 IO 的线性边界 | `inspect_consume` 只消费 shadow 槽；保留实际 import/ready/inspect 线性点与最终提交完成点，并重查时间/owner/lease/stop | 没有创建 active publish transaction，没有新增真实 regulator IO；逐路 permit/call/result/no-call 边界待新实现 |
| 3. 有限工程政策 | 继承 T=200ms、ready=150ms、±25、rho=80 的 diagnostic 来源；登记 20ms 关闭轮询、1s ack、2s 终端 tail | 这些来源清楚但不构成最终域标定、plant 保持或全调度 WCET；hold/ramp/gap/budget、恢复与 failed-close 政策待锁定 |
| 4. recipe 与必要当前运行 | 本批登记正常 hooks=0、4s 测量、25s 准备、60s 总预算、15s 关闭；新 Observer 与四个原 N10 角色配合 | 当前4s结果待本批证据；20s、turn/mixed、统一版本 pressure/recovery/failed-close 未运行，4s不能替代 |
| 5. 逐阶段复判与 M4 | 各项资格保持独立 false/unknown | 不能从有限组件或4s shadow晋升 B4/M0b/B5/M4、D1/strict/F6/P1/execute 或研究结论 |

## Applied 整对准入与有限组件逐路事实

[真实 Applied 路径](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/observer/src/shadow/regulator_shadow_observer.cpp:496) 先校验实际 GID/pidfd，再调用继承 `p1::shadow::assess`。只有旧整对准入通过、且运行未 terminal，才进入 [Adapter::observe](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/common/c36_runtime_adapter.hpp:11)。不能把组件头中具备逐路 `succeeded/failed/unattempted` 表示能力，解释为实际 runtime 已接入部分调用结果。

N12 的有限政策是成功路更新局部命令事实、失败路未知、未调用路保留原事实，不完整整对禁止新 Job。N13 当前保留旧整对失败策略；部分失败在旧 gate 被拒时，实际组件逐路结果路径不会得到该反馈。该兼容差异已经明确登记；后续须对 permit、真实调用前后、异常和无调用逐项记录，补齐关闭后许可撤销与跨路关闭政策，再评价阶段影响。

[shadow Adapter 证据](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/common/c36_runtime_adapter.hpp:49) 标记 `active_publish_transaction=false`、`actual_regulator_publish=false`、`plant_acceptance_observed=false`。所观察的 Applied 是 Publisher 命令事实；真实 plant 是否接收、保持或产生力仍 unknown。

## Worker、关闭与端点范围

新认证只覆盖 `/research/control/applied` 的 DataWriter。Worker Candidate/Capability 真实 subscription callback 仍没有 `MessageInfo` 参数；原 payload 身份、PIDfd、capability lease、完整 Job echo、资源和 state/clock 检查保留，不能描述为 Worker 已获得新增逐回调 GID 认证。

[driver close](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/prepare_fixture.py:307) 在 Supervisor 发 SIGINT 前建立 create-only 请求并等待 Observer ack；[Observer](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/observer/src/shadow/regulator_shadow_observer.cpp:455) 认证 driver/run/boot/owner manifest/time 后撤销新提交、取消 pending。它证明 driver 请求已被 Observer 看见，不证明原 owner 已产生关闭意图。

组件 join 后 local closed、Publisher session end/flushed、Supervisor cleanup、pidfd 退出及 DDS graph 缺席是独立事实。pidfd 引用同一进程实例但不能证明后续未 exec；单次 graph snapshot 不能证明全寿命唯一性；组件 closed 不能证明原 owner endpoints 已退出。`owner_close_intent`、`owner_endpoints_exited_at_adapter_close`、`continuous_DDS_unique_owner`、`post_pin_exec_continuity` 保持 unknown。

退出后 queued terminal tail 必须同时满足原 GID、已认证 driver closing、完整有限且实际双路成功的零命令、调用时间不早于 driver request、有限 2s 窗口。它只结算原命令事实，进程继续显示已退出，不重新授予新 Job 许可。异常或超限 receipt 不能被裁剪来恢复生命周期完整性。应用层序列化前的文本限额不等于中间件反序列化或全机器资源上界。

## source、binary 与有效配置来源

读取时新 Observer 使用 `observer_source_bundle_C36_v2.json`：34 文件，SHA `82b4ce2c96882ef0772e0db494ea0b253ec96bdb7983f5fed7d20cd59d281db7`；全部实际文件匹配。四个 reused source bundle 和 binary 原 N10 pins 均独立重新读取 SHA 匹配。来源明细与本次审查文件 SHA 位于 [JSON](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/review/plan_alignment_v1.json)。这只是读取时点的字节核验；新的运行仍须形成 final build manifest、配置锁和检查前后输入 SHA。

读取时 `build_manifest_current.json` 尚未形成，v2 runtime binary 文件已出现；文件存在不代表构建或测试通过。首版问题、源码快照与二进制需保留。最终 Observer 二进制来源以本批 build manifest、编译命令、依赖记录和 native 结果为准，不能拿首版成功替代修订版。

实际 contract 来自 `/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_v13_resource_20261007/p1_shadow_contract_v5.json`，固定 SHA `0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933`。Publisher 初始参数来自 `/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/vrx_shadow_fixed_f5_preflight_20261006_01.json` 的 `f5_actual_parameters`，新 run 只按 driver 明列覆盖 run/output/release/contract 参数。Worker/Observer 的 owned manifest 要求完整 effective contract 等于声明；支持的各角色外部 live typed 参数要与全部 expected、canonical digest 相符。新增三个 Observer 参数固定 peer pin 文件、文件 SHA 与 driver close 路径。当前真实配置认证结果须由新 run 产生；现有声明及哈希不替代这一步。

## 下一步顺序

1. 完成本批 v2 native 守卫、真实 DDS peer 反例、4s owned shadow 及完整人口独立检查；锁 final source/bin/helper/config，保留失败，更新 status 与新的 MPC create-only SHA 回读归档。单独报告组件结果，不晋升阶段。
2. 补 Worker Candidate/Capability 的实际 MessageInfo GID 与 owned peer 认证；保留原 lease/resource/full echo 检查，用相同 payload 的 foreign writer 作正负对照。
3. 新登记有限支持域、时间/年龄/RTF/clock、rho/gap/hold/ramp/publish-budget、恢复及 failed-close 政策；写明未知依赖如何影响各阶段要求。观察最大值不称 WCET。
4. 实现 source-linked 逐路 permit/call/result/no-call adapter；采集 owner 原关闭意图、session、cleanup、endpoint 独立事实；逐项决定新逐路事实与旧整对政策的兼容。先单元和受控 shadow 集成，不直接开启 execute。
5. 固定完整 typed 非零20s 与 turn/mixed recipe、初态和来源；重封 source/bin/config/helper；正常 hooks=0，另跑最终统一版本 pressure/recovery/failed-close。组件 failed-close 拒绝语义测试不替代真实统一版本 failed-close 运行。
6. 依不可变合同与当前证据分别复判 B4/M0b/B5；其后独立新 M4 execute 版本证明连续 F5 owner/endpoint 退出、regulator 唯一双路出口、真实非零/部分发布与 rho/gap/budget。F6/P1 模型事务和候选一致性、GP/PPO/强对照继续按原路线后置。

截至本次只读审查，B4/M0b/B5/M4 status=unknown、qualified=false，其余 D1/strict/F6/P1/execute/research=false。dynamic20s、turn/mixed、当前统一版本压力/恢复/failed-close 为 not_run；Master Clock、plant接收/保持、全调度WCET与当前统一运行执行契约为 unknown。后续本批成功可更新组件验证状态，不自动改变上述判定。
