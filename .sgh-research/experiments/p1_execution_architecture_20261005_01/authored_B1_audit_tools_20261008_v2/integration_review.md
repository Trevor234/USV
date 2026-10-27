# B1 独立诊断副本：集成静态审查

日期：2026-10-08。审查对象为已冻结的 B1 诊断副本、Sink、固定 witness 头文件、独立构建配置及测试声明。本审查只读取本地文件、比较摘要和源码差异，未连接 Ubuntu、启动 ROS、运行测试或修改生产代码；只新增本文。

**结论：最终指纹对应的代码没有未解决的静态阻断项，可以继续已授权的独立构建、纯工具测试和真实启动拒绝验收。此结论不代表 B1 已完成实际验收，不开放 C0/R5 实际批次、物理输出或 M0b 冻结。** 本轮已指出的队列拒绝误分类、暂停取消通知丢失窗口、审计失败仍可能返回 RC0 等问题已在冻结代码中修正。

## 1. 本次锁定的来源

全部路径位于 `C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/`。

| 文件 | 字节 | SHA256 |
|---|---:|---|
| regulator_baseline.cpp | 51966 | `1163a651580bde314e8b450d39213c1691187fbe977debe63a0366c6e027eb8c` |
| regulator_r5_diag.cpp | 58349 | `a67d65fdde95ff754ca26d0bffe93e12f2cfbce9d8943d6cf01047b499e34cdb` |
| p1_diag_sink.hpp | 5305 | `4a607820a5e7ce1f047d559bcde72965926f4e9d7d86a8ec20cd39add03c2a79` |
| p1_witness.hpp | 24118 | `c114df7d6c587e389ebdacc7344536e7f00dca81cc8dea2d352dac4ada6d6a93` |
| CMakeLists.txt | 1476 | `ca02dc2c28459690dcdd2aa165e5e4ec35a032e18bef952636c389bb0906b4a5` |
| test_p1_witness.cpp | 27146 | `92b2bbe66c841440768bebf66402f6141db4963d5be91fe1321d228062e6545d` |
| test_p1_diag_sink.cpp | 4600 | `7f0f4bb646b33125fa5b058dc8706913009cd65f4d6aca87b65819391063a9ae` |
| witness_layout.cpp | 898 | `6d1e8d9f0076a13ae9489af599c87995028fe2586a03b0c9fd5f5728a23c67b3` |

`regulator_baseline.cpp` 与已验收 B0 `safety/regulator.cpp` 的本地摘要相同。本次逐个摘要核对 `p1_admission.hpp`、`p1_capability_lease.hpp`、`p1_clock_window.hpp`、`p1_full_contract.hpp`、`p1_preparation_barrier.hpp`、`p1_resources.hpp`、`p1_tick_barrier.hpp`、`p1_worker_liveness.hpp`、`protocol.hpp`，九个核心头文件均与 B0 本地版本一致。来源绑定是当前 B0/v14，共享合同校验不能退回旧 v13。

既有 B0 `final_evidence.json` 保存的 worker bin SHA 为 `dd7d253b420aff8283a4869ae804e5f49fcb76c3357829c5c6c12f020324c35c`，生产 regulator bin SHA 为 `db2ec8facfc5a60199368f93589955f805eb855332280b7fd6902f90c635562f`。其已关闭资产清单为 `/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/contract_B0_closed_assets_20261007.json`，1908 项，清单 SHA `bc0e932313852ff046b748f9cfa4292d27b5320aea5177a5ef6a20bbff8b1de8`。这是既有材料中的事实，本审查没有重新读取今天的远程主机；部署前仍须重新核查该守卫及现有进程。

## 2. 业务路径保持与入口限制

[诊断入口](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp:45) 先执行 B0 完整合同加载和运行模式门，再明确限制为 `no_output`、v2、diagnostic revision 5。即使 audit 和 pause 关闭，独立诊断入口也不接受 shadow/execute/正式预冻结合同。pause 非零还要求 fault=true 与 witness=true；错误配置门先于 worker liveness、P1 publisher 和 Sink/source 文件构造。ROS Node 基类本身先于这些检查构造，不能据此声称错误入口没有短暂 ROS node。

源码差异主要是替换诊断 Sink、增加身份核对、独立订阅一次 arm、记录授权/激活/tick/阶段及最终审计状态。原提交门、candidate registration、admission take/cutoff、激活理由优先序、fallback、物理 publish 逻辑与业务 invalidation 保留。没有在 witness helper 或 pause 中新增 admission.invalidate、candidate.reset、pending.reset，也没有直接置 source failed 来伪造溢出。业务授权不读取记录是否成功、数组是否溢出或审计摘要；审计结果只影响最终诊断退出资格。

原 B0 的重要缺口仍可观察：[Decision enqueue 失败](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp:364) 只置 stopping，新增阶段在原 flag 写入后取得决定 mutex，按决定→prep 锁序读取真实槽；没有补清槽。若零请求使该拍立即退出，下一 tick-start 的原 invalidate 仍可能没有机会执行，Close 阶段会保留当时的实际槽状态。不能预先把此路径写成清槽政策已通过。

## 3. Sink 与一次性消费暂停

[DiagSink](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/p1_diag_sink.hpp:38) 保留原 `closing || depth >= capacity` 拒绝决定及 generated/dropped/failed/source_summary 语义；QueueOverflow 现在仅在实际 depth 已达 capacity 时记录。closing 且队列未满的拒绝不会被误称容量溢出。peak 取实际队列深度，不能由请求发送数推算队列深度或 R5 的 512 溢出。

暂停默认 0，policy 和 Sink ctor 都拒绝负值及大于 5000ms；一次 arm 通过 0→1 原子状态转换，之后不会复位。消费线程在 queue mutex 内决定进入暂停，随后释放该 mutex；PauseBegin 与截止时间共用 entered monotonic timestamp。整个暂停等待使用独立 pause mutex/condition variable，不取得 queue mutex，生产者仍可 enqueue。关闭方先在 queue mutex 下设 closing 并释放，再在 pause mutex 下设 cancellation 并释放，之后通知，两把锁不同时持有。此同步修复了取消通知发生在 predicate 检查与实际入睡之间可能丢失的窗口。

Sink 阶段只读原子状态并记录固定行，不取得 business/prep mutex，避免与原业务→Sink 锁序反转。不能取得的 candidate/pending/stopping 状态保留 Unknown，admission_slots=-1。source 写入、DDS 异常、队列拒绝均保留 source failure；witness 不替换 source 的失败结果。

5000ms 是预声明 monotonic 截止策略，线程调度迟到仍需在实际记录中报告；静态代码不能证明实际 PauseEnd 恰好不超过该时间。纯工具小队列溢出或取消测试也不等于正式 R5 的512容量业务压力。

## 4. Witness 发布、关闭与身份

固定四流为256 tick、128 submit、128 activation、32 phase。每行是固定 POD；发布路径无磁盘 I/O、堆分配或业务锁。MPSC reservation 单调分配，满后拒绝，不扩容、不复用或覆盖。slot 从 reserved→writing→committed，payload 写完才以 release 发布 committed；读取以 acquire 核对 committed。计数与 accepted/no-candidate aggregate 在 producer lifecycle 退出前更新。

单个 lifecycle 原子同时承载 active 数和 closed bit，close 与 producer entry 的修改顺序明确：关闭时尚活跃或关闭后尝试记录都会留下 incomplete。first_failure 使用独立原子 reservation 和 release 发布，未完成发布的 payload 不会被当作已知数据读取。该字段是审计记录机制的首个已保留失败，不能冒称原业务 source 的精确首个原子置位时刻；MPSC phase 的 reservation sequence 也不保证全局时间排序。

[真正关闭顺序](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp:107) 是 main 的单线程 executor remove_node 后，join tick、停止并 join prep、close/join Sink，再记录最后 Close，检查身份，close_after_join，独立 terminal 写入。没有将 terminal 文件送回失效 Sink。O_EXCL 创建防止已有文件/符号链接目标被覆盖；失败或部分文件照存，不能换一个路径重试补造成功证据。文件只是终端快照，仍不能自己证明外部调用者以后永不尝试写入；本应用的 writer 退出与 join 次序提供实际约束。

startup enabled header 绑定 bounded run/boot/contract/source/bin/worker-bin/worker-instance。source 文件、/proc/self/exe 和已登记 worker PID 的 exe 被实际计算 SHA，并与事先传入摘要比较；worker-instance 是原 worker 含启动 monotonic 的实际实例 digest，不能用 PID 重算替代。后续有效且身份一致的 capability 若实例与固定 header 不符，只标审计 Header invalid，不干预控制决定。仅格式正确的 header 并不证明其实例已见；后续运行 checker 的实际 BusinessReady/activation/submit 覆盖以及事先保存的 worker startup/capability pins仍须单独验证。

header 内 source SHA 只覆盖 regulator translation unit，不能单独代表所有 include。因此部署 manifest/构建输入/运行前后守卫须同时锁定本表的 witness/Sink/header 与九个 B0 core header、实际 bin及 worker来源。

## 5. 记录口径与退出分账

- submit 行在原最终门通过、job_id 与 jobs ledger 授权后取 witness commit_ns，并在同一决定 mutex 中记录。原 source submit_commit_ns 的取时保持不改。锁外已经授权的 job/DDS 尾部可能晚完成，不能当作停止后的新授权。
- submit/activation 中 failed/stopping 是记录时的独立状态快照。异步 failed 可在原 gate 读取与后续快照之间改变；不得把后来的 true 反写为原 gate 的判据。
- final activation 保留所有 `t && cand` 的 accepted/rejected 尝试；tick.candidate_present在本副本明确指这对实际最终激活输入，而不是原共享 candidate slot 任意非空。共享槽的真实存在性由锁内 phase 的 candidate_present 另行表达，no-pair tick 仍有完整行。
- FinalActivation 的 SourceFailure phase 表示最终尝试处观察到 failed；原 source gate 有 reason/worker 条件短路，因此该 phase不能单独证明原 `run_unusable_at_commit` 条件已被使用。
- witness tick end 在正常路径的 Decision add、后继准备 enqueue、停止处理、DEADLINE+1 等待和 cutoff后记录；同拍 shutdown break 路径也在退出前记录。它不沿用原较早的 Decision.tick_end_ns，但不包含终端线程 join/文件关闭时间；那些由独立 Close 阶段表达。

[source关闭与审计退出](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp:110) 先保存 terminal，再以 write成功且 audit_complete决定审计成功。source正常且audit失败为RC3；source失败保持RC2，即使审计机制成功也不改写为RC0；启动异常为RC1。REGULATOR_CLOSE_FLUSH_SUCCESS 与 DIAGNOSTIC_WITNESS_COMPLETE分列。Default off不创建 witness 文件，phase/tick helper提前返回；无法由关闭记录宣称 enabled audit已完整。

## 6. 本审查的覆盖与后续证据

CMake 是独立 standalone build，只有诊断 regulator、布局程序和工具测试，没有 install 到生产 ROS workspace。所引用的 witness/header/test/layout文件已齐全。静态声明可见29个 witness TEST和8个 Sink/policy TEST；这只是源码声明，实际数量、通过状态、没有 failed/skipped等必须由本次实际测试结果与XML核实。

源码测试覆盖声明包括默认关闭、四流精确容量/下一次拒绝、POD完整发布、弃置reservation、并发与关闭竞态、header/bounds/target关系、first-failure保留、终端失败及已有文件/符号链接/竞争创建保留。Sink测试声明覆盖 mode/fault/finite bounds、独立ctor上界、一次arm、暂停期间可enqueue、close cancellation、真实小队列溢出与closing误分类。布局程序仅在实际构建后输出平台sizeof；本审查没有推算或虚构总字节。

部署前重新核对B0的1908项守卫与host状态；实际验收必须保存clone source/bin/header输入图、编译日志、当前XML身份、固定字节报告及真实错误组合source创建前拒绝证据。纯工具通过之后仍需独立C0默认钩子关闭对照与预声明R5实测。R5的实际queue512/drop>0、首次业务观察≤220ms、失败前≥5完整tick、pause实际释放和清槽状态等在本审查中均未覆盖。

本审查无未解决静态阻断。M0b正式冻结、R5、M4、F6、P1整体和physical execute资格保持未完成；不能用本文件或纯工具测试替代这些验收。