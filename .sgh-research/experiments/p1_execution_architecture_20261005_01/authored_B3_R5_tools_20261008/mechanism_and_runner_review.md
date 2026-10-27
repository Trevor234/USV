# R5 机制工具与 runner 的独立源码审查

日期：2026-10-08。本报告依据本地冻结源码、新工具和离线测试。审查没有连接远程主机，没有启动 ROS 或 R5 现场批次，没有修改已冻结 B1/C0 源码、二进制、旧检查器及旧证据。当前结论是新机制工具已完成本地准备；现场机制是否成立仍须由本批次真实原件和独立门判定。

## 冻结对象与验证范围

机制检查器 [check_R5_mechanism.py](runtime/check_R5_mechanism.py) 为 38,882 bytes，SHA256 为 `cef7bf29e2c52d422c9e101032bea205e50818abc4fe8f3f9f493627c4a275bc`；测试 [test_R5_mechanism.py](runtime/test_R5_mechanism.py) 为 27,135 bytes，SHA256 为 `a375bd4f36f31e5c438a186a7e0999fa21cea74ebda85d217a18671cf8c6c298`。43 个机制测试通过。最后新增的一致性负例禁止已知不可逆故障上界之后仍出现 `failed=false` 的证据，避免只挑选有利的故障前观测。

同期只读核对的最终 runner [run_R5_pressure.py](runtime/run_R5_pressure.py) 为 73,613 bytes，SHA256 为 `9aebd5f57ad3f408f881ebae7f5650c7a388a04a28a5ee3ffad9c8590661d367`；独立 worker/bag/owned 门 [check_R5_independent.py](runtime/check_R5_independent.py) 为 21,835 bytes，SHA256 为 `9053a8f592c9b01b06b7e5313a77f3be08e486b85412fc639cbf1104d5d046db`。这些是审查时的最终版本；正式政策和部署清单须逐项锁定，不应继续引用较早的 `e5ca…` 机制 SHA 或 `025cc7…` runner SHA。

协作 runner 审查报告记录最终三项新工具联合 123 个测试通过，分项为 runner 42、机制 43、独立门 38；本报告直接负责机制 43 个测试及另外两项源码核对。单元测试使用人工构造的离线证据，不能代替真实原件、实际 bag 扫描、实际四角色退出状态或主机清理结果。

## 接口、完整输入与失败封闭

CLI 必须同时提供 `--context --summary --witness --expected-header --worker-source --regulator-source --policy --output`。输出是单个 create-only JSON 文件，不允许覆盖输入或已存在报告。内存 API 为 `analyze(witness, expected_header, regulator_events, worker_events, context, summary, policy)`。结果 schema 为 `p1-R5-mechanism-check-v1`，scope 为 `finite_R5_log_pressure_mechanism_only`。

机制完整性直接调用冻结 B1 Witness 检查器，没有另写宽松替代。四条 Witness 流检查完整 owned 生命周期，不裁切到压力窗口；`audit_complete` 缺失、容量溢出、未发布槽、非法身份或时间域均不能通过。业务 Sink 故障与 Witness 的 `first_failure` 含义不同：前者由真实 phase 表示，后者是审计机制自身故障，压力测试不能把审计故障当作预期日志损失而豁免。

两个 source JSONL 必须完整读取。重复键、非 UTF-8、NaN/Inf、未闭合末行、数值域错误、未知事件、缺少必要字段等均产生失败。JSON 计数与时刻使用真正整数，布尔值不能冒充整数。七份输入均记录读取前和读取后 SHA256；任何漂移或读取后哈希异常会清除先前计算的通过标志，保留失败报告。输出不能从已有有利报告替代重新解析的原件。

机制只授予自己的 `passed / mechanism_passed / expected_log_overflow_mechanism_passed`。`R5_complete`、worker/raw bag/owned 完整性、正常契约、C0 性能比较、M0b/M4/F6/P1 完成与 execute 资格始终为 false。总 R5 门另由 root 的组合函数核对全部独立证据。

## 压力声明、真实 ARM 与容量证明

检查器要求 run/boot/contract、诊断 source、regulator/worker binary、runner/supervisor 等身份与事前 policy/context/expected-header 一致。模式固定 `no_output`，Witness 启用，Sink pause 为真正整数 5000 ms，压力窗口起点固定 `arm_publish_start_ns`，最大跨度 15,000,000,000 ns，其余四个故障 hook 必须是真正整数 0。220 ms、20 ms、5 s、2.5 s 等阈值与政策固定值一致，不能从本次结果反推阈值。

ARM 前至少两条不同 native accepted 链分别连接完整 Job、worker receipt、真实 acados Candidate、Candidate publish result、regulator registration、source accepted Decision、Witness Submit/Activation/Tick，以及 runner 实际 typed accepted 回调。Candidate 的 solver/success/prediction 标志必须为真实 true，向量及时间顺序必须合法。每条 typed 接收时间和 accepted commit 均位于真实 ARM 发布起点之前。仅有 `native_success=true` 或 `publish_success=true` 汇总标志不能授门。

runner 保存实际读取的完整 source 前缀 bytes/rows/SHA 与完整链 payload。机制 CLI 不仅比对前缀 SHA，还在这些实际字节中重新查找所有 ARM 声称的 Job、receipt、Decision、registration、Candidate 和 publish result；不能借用文件稍后出现的原件证明 ARM 前准备。

容量证明来自冻结 [p1_diag_sink.hpp](../m0b_witness_implementation_20261007/diag/p1_diag_sink.hpp) 的 `add()`：在同一 queue mutex 下，`q_.size() >= capacity_` 进入拒绝分支，先增加 dropped 并置 failed，再首次记录 QueueOverflow，成功 push 不允许跨越容量。policy 固定容量 512，并锁定此源码 SHA。实际 Witness 必须出现唯一 QueueOverflow/SinkThread，terminal source summary 必须 dropped>0 且 `generated = emitted + dropped`，emitted 与完整保留 source 行数一致，`normal_source_complete=false`，实际 regulator 返回码为 2。

本 trace 没有实际 queue depth 字段，报告 `observed_queue_depth=null`，不会制造一条 depth=512 的观测。512 是锁定分支与容量不变量共同给出的路径证明，source SHA 或条件不一致就不能使用它。未触发 overflow、缺少 summary、错误 RC、计数矛盾或审计失败均不通过。

## 220 ms 响应上界与真实业务停止边界

Sink `failed=true` 的原子写入先于 QueueOverflow/SourceFailure phase 的时间采样，因此单凭 `StoppingObserved.ns - SourceFailure.ns <= 220 ms` 不能证明真实故障响应。尤其不能使用延迟写出的 SourceFailure 来缩短响应时间。

保守界选取 `L = max(已知 failed=false 的事前采样时刻)`：Tick.start/end、Submit.commit、Activation.commit、phase.ns 的冻结代码均先采样时间，再读取 failed。failed 在本实例只由 false 变 true；故真实故障时刻 F 位于 L 之后，`first_stopping_ns - L` 是响应的保守上界。L 仅取不晚于首个 QueueOverflow/SinkSourceFailure 上界的合法观测；没有足够接近的 L 或上界超过 220 ms，结果失败。已知故障上界之后的 false 观测属于矛盾证据，不能先过滤再隐藏。

报告保存 `latest_known_failed_false_ns` 和 `stopping_response_conservative_upper_ns`，同时保存直接 SourceFailure→Stopping 相差供检查，但后者不独立授门；`failure_atomic_store_ns=null`，没有把日志时间伪称原子写入时间。

至少五个完整 Tick 必须完全位于 PauseBegin 到首个 QueueOverflow 之前，且 start/end 的 failed/stopping 都为 false。使用整 Tick，不仅数 Tick.start，也不延长截止点到较晚的 SourceFailure。完整 Witness Tick 全部要求 skipped=0、实际 start 相对 planned 的迟到不超过 20 ms；超标按原阈值保存失败。

首次实际 phase5、observer TickStart 或 DecisionEnqueue 的 `stopping=true` 是业务停止边界。之后 `Submit.commit >= stop_ns` 或 accepted Activation.commit >= stop_ns 均失败，边界相等也按失败处理；Submit 的 stopping 快照为 true、accepted 的 stopping 快照为 true 也失败。停止后的 rejected activation 单独计数，不能混成新的成功接纳。

## Submit/Activation 异步采样裁定

冻结 [regulator_r5_diag.cpp](../m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp) 第 287–289 行先用 `sink_->failed()` 判是否授权，随后 `jobs_.push_back(j)`，再采样 Witness Submit.commit 与 Submit.failed。另一个线程可能在授权成功之后、Witness 记录之前置 failed。因此 `Submit.failed=true` 本身不能证明授权时已经故障，Submit.commit 晚于 Sink failure phase 本身也不能独立证明授权违规。这两项不能替代真正的停止边界。

当前机制保留 `submit_failed_after_authorization_snapshots` 计数；不以该异步 failed 快照独立判提交违规。仍严格禁止停止边界后的 Submit.commit 和 stopping=true Submit。这是实测前根据冻结源码作出的时点语义修正，没有基于现场结果放宽规则。

Activation.commit 在第 337 行采样，第 339 行随后执行最终 failed gate，第 345 行再采样 Witness.failed。accepted Activation.failed=true 单独也可能是门后异步变化，只保留 `accepted_failed_after_commit_snapshots`。但如果某个已知真实 failure phase 上界已经不晚于 Activation.commit，则故障已先于最终 gate，可据此禁止 accepted。Activation 与 Submit 的记录顺序不同，不能套用同一个 failed/commit 推断。

## 失效快照、关闭与未修复分支

机制要求唯一真实 phase8/observer TickStart 的 `first_invalidation_observed`，其 failed/stopping=true、candidate=false、admission_slots=0、pending=false，且在首次 stopping 之后不超过 220 ms。Close phase 也必须完整净空；Close 不能补作遗漏的业务失效 phase。SinkThread 不持有业务锁，真实记录业务槽为 unknown/-1；检查器保留这些 unknown，不要求 Sink 伪报业务净空。

冻结源码第 315–318 行 TickStart 路径先记录 stopping，再执行 `invalidate_locked()`，随后记录 phase8，能直接观察这一分支。第 364–366 行 DecisionEnqueue failure 路径只置 stopping 并记录 phase5，未在该分支同步调用 `invalidate_locked()` 或记录真实 phase8。若 no_output 的 zero 条件使本 Tick 直接退出，不能假定下一 Tick 一定补齐失效。

此共享槽缺口仍未修复。机制检查器不会从 Close、终态汇总或假定代码意图补造 phase8。实际 R5 若走到这个分支并缺少真实 phase8 或失效不净，应按失败保留全部原件，再创建新诊断版本进行修复与重验；即使本次其它分支通过，也不能扩大为该分支已修复。

PauseBegin→PauseEnd 真实跨度必须为正且不超过 5 s，允许关闭取消等待造成短于 5 s，禁止把声明 5000 ms 当成实际持续时间。source summary.finished 必须在 PauseEnd 之后、Close 之前，Close 为 producer join 后真实终态。

自然失败退出路径保存 runner 首次 poll 到实际 RC2 的时刻，`release_kind=natural_failure_exit`，不捏造逻辑 release；要求 Close≤observed_exit≤window_finished，observed_exit−first_stopping≤2.5 s。poll 时间晚于实际退出，使用它给出保守的关闭时限。

逻辑释放路径使用首次真实发布 STOP=true 之前采样的 `release_requested_ns`，要求 stop_release 相同且 Close−release≤2.5 s；Close 可以位于压力窗口结束后的真实 graceful 尾部，不强行把它裁进窗口。窗口和 shutdown 是两个实际时段，不能用其中一个的时间补造另一个。

## Runner 与独立证据门核对

runner 的最终 `main()` 确实进入完整 run；内部 fixture 入口与压力入口分别校验，压力入口不是仅执行 helper 的假入口。读取 fault-enabled capacity512 契约后，真实 ARM 由独立 intent 与 owned ledger 先记录，再实际 publish 一次，分别保存 publish_start/end；`arm_delivery_known / arm_sink_acceptance_known` 保持 false，真正接纳由 Witness phase 证明。

压力循环以实际 ARM 起点计算 15 s 最大窗口。regulator poll 到 RC2 时自然记录 exit；其它 owned 子进程提前退出、worker fatal、非 RC2 regulator 退出均保留失败。runner 本身只授 `pressure_collection_complete` 这一收集结果；postrun 的机制、R5、normal、execute 标志均保持 false。窗口结束后仍保留 regulator→worker→fixture→recorder 的关闭尾部及 recorder drain，不能只收集压力窗口内消息。

旧 normal-source checker 与旧 strict application-delivery checker 都真实调用，原失败报告、原返回码和 SHA 保存。预期 regulator 日志损失不变成正常完整性通过，也不能豁免 worker、recorder 或 raw bag 缺失。

独立门调用冻结 base 的 full `read_bag()`，使用实际 SequentialReader 返回的 `actual_topic_counts`，逐项核对 typed 消息数量、metadata 与完整 bag。Job/Candidate/Decision 使用完整 payload multiset 对账；压力中缺失的 regulator 行不被重建。Worker 要求完整终态，真实 `generated_candidates=published_candidates=实际 Candidate 数`，fatal=false、terminal_numerical_failure=false、normal_source_complete=true；每个实际 Job 具备匹配 receipt 和唯一闭合 outcome，native 成功及发布时间和预测向量另行验证。

原始 fixture 的五类输入发布计数与实际 full bag 对应 topic 计数一一相等且为正；这些是发布侧计数与实际存储侧全量对账，没有声称回调级重建。四个 owned 角色必须全部存在且各唯一，身份与 pinned executable 绑定，cleanup.remaining_members=[]；实际 regulator RC2，worker/fixture/recorder 均实际 RC0。summary 与 ledger cleanup 配对，终态 supervisor 完整；缺少角色、余留成员、worker 终态失败或 raw bag 不完整均不能因为压力而通过。读取后 SHA 异常也落失败 JSON，不保留先前 passed=true。

组合门另要求正式 frozen-before-run 政策、原 normal/base 与 delivery 的实际 RC2/false、runner/mechanism/independent 的实际 RC0、原资产与原件无漂移、inner/outer 清理与 host 无物理 publisher。只有全部门成立，才可标记这一有限 no_output R5 实验通过；该标记仍不授正常运行、性能、实际执行或整个 P1 完成。

## 现场前需保留的实际限制

审查初版 runner 发现 accepted_native_chains 额外要求成功 Candidate.reason 为空。冻结 worker 会把 native 的诊断文本复制到 Candidate.reason，成功标志与诊断文本并不互斥；regulator registration.reason 则表示接纳拒绝原因。root 据冻结 worker 与 registration 源码核实后，在部署和实测前授权 runner 作者修正：最终第 1082 行仅要求 Candidate.reason 为真正字符串，允许成功结果携带非空诊断，registration.reason 仍须为空，所有 native 成功、身份、向量、时间、typed/source/Witness 链门继续保留。新增相应测试后 runner 42 个测试通过。此修正解决启动可用性限制，没有改变压力参数、时间阈值或机制通过条件；不是依据现场结果作出的调整。

15 s 与 5 s 都核对实际时间，线程调度或 polling 延迟可能使实际跨度超阈值，即使声明参数正确仍不能通过。该风险不能靠现场后放宽窗口或阈值解决。实际 ARM 未触发、日志故障未发生、响应界缺证据、业务失效缺口、后停止新 commit、审计不完整、终态 source unknown、worker/raw bag/owned 失败等都应保留为本批次事实，再决定是否需要新版本。

当前没有实际 R5 批次结果。本地 43 个机制测试及源码兼容审查支持事前准备完成，不支持预判现场必通过。
