# C0 完成后的 R5 准备边界与最小下一步

日期：2026-10-08。审查者：`b1_witness_finish`。本文件依据当前源码、`remote_run.template.py` 和主计划 B2/B3 条款形成；没有连接远程主机，没有执行 C0 或 R5，没有编辑源码。C0 现场证据尚未在本审查中验收，以下“C0 通过后”均为条件性的后续路径。

**C0 如果通过，下一步仍是补齐独立 R5 运行入口、事前政策和机制判定器，而不是把现有正常 runner 的 pause 参数改为正数立即运行。** 当前源码具备有限暂停及独立 Witness 基础，但现有 runner 主动拒绝压力，C0 comparator/组合门只允许正常完整源对照。C0 通过不证明真实 512 队列溢出、220 ms 内观察失败、停止后共享槽失效或有压力时的有限收尾。

本轮主任务登记本地 C0 工具 49 个测试通过；远程模板也将其作为执行前门。这里仅核对模板要求和源码行为，不把本地工具测试改写为现场 C0 成功。

## 本轮 C0 模板实际执行的范围

`remote_run.template.py` 钉住预声明 policy SHA、B1 关闭资产守卫、boot、诊断 source/bin、worker bin、diag5 合同、完整工具清单。它通过独立 owned supervisor 调用现有 runner，固定 `duration=10`、Witness 开启、`test_sink_pause_ms=0`。之后分别运行原 application ledger 和新的 source↔Witness comparator，再用 `check_C0_gates.combine()` 合成 C0 结果。

模板保留并绑定同一 run 的 context、summary、postrun、完整 base report、delivery、comparison；重核 raw inputs、Witness/expected header、旧报告和所有工具 SHA，并检查资产无漂移与主机清理。`verification_C0_combined_gates.json` 与外层 `C0_run_result.json` 分别保留独立门及 owned driver 清理结果。最终模板将 R5、M0b 正式冻结、M4、F6、P1 和物理执行资格固定为 false。

因此，C0 成功能建立的是这份**无压力诊断二进制**的正常全 owned 生命周期对照与实际 source/bag/application ledger 闭合。它为 R5 锁定版本提供前置证据，不能填补 R5 尚未执行的触发和失败路径证据。

## 已有机制与尚缺实现

| 项目 | 当前源码事实 | R5 前仍须完成的具体工作 |
|---|---|---|
| 有限消费暂停 | `p1_diag_sink.hpp` 支持一次 arm，pause 参数为 0..5000 ms；消费暂停时释放队列 mutex，monotonic 截止结束；Close 可以取消暂停。 | 在独立 R5 runner 中显式配置并仅在业务就绪后发布一次 arm，保存声明、实际 arm、PauseBegin/PauseEnd 与释放原因。不能将“有 hook”称为“已运行压力”。 |
| arm 通道 | 诊断监管器订阅 `/p1/diag/arm_sink_pause`，true 请求调用 `arm_pause()`；它不会自行等到两次原生候选激活后再 arm。 | runner 负责核对 source/worker/clock 就绪、owned capability、至少两次**真实 native 候选的虚拟 accepted activation**与同一 Job/Candidate/Decision 身份，然后才 arm；completed_jobs 或单个 BusinessReady phase 不足以证明这两个激活。 |
| 当前运行入口 | `run_r5_diag_validation.py` 的文档、`validate_normal_parameters()` 和 regulator 命令均是 C0 normal-only；正 pause 或任何故障参数在创建目录前被拒绝，子命令强制 pause0。正常窗口也只支持至多 10s。 | 新建受版本约束的 R5 专用入口；允许唯一预声明 Sink pause，拒绝其他 fault/shadow/execute/不完整身份；上限 15s，不能放宽或改写原 normal 入口。 |
| Witness | 固定 256 Tick、128 Submit、128 Activation attempt、32 Phase；业务就绪、arm/pause、QueueOverflow、SourceFailure、StoppingObserved、InvalidationObserved、Close 等真实观察点已经存在。append 结果不参与业务决定。 | 专用机制 checker 必须识别具体故障边界和实际共享槽状态，保留 accepted/rejected 两类尝试、无 candidate tick、完整前缀尾部。任一容量不足、缺行、unknown 或写失败都使机制失败；不能扩容或重构丢失业务事件来让它通过。 |
| 真实队列溢出 | `DiagSink::add()` 在 mutex 下遇到 `q_.size()>=capacity_` 时增加 dropped、设置 failed，并首次记录 QueueOverflow。成功 push 不越过 capacity。 | 合同仍须固定 log_capacity=512；实际证明 queue 达512且 drop>0，而不是用 fixture 尝试发送频率推算。现有 `peak_depth()` 可读，但未写入当前 source_summary/Witness；事前须定义如何依据 pinned QueueOverflow 路径、capacity 和实际 summary/counter建立这个证据，若要增加独立深度快照则需受控版本和重验。 |
| 失败处理观察 | TickStart 路径记录停止，并调用 `invalidate_locked()` 清 candidate/admission/pending；最终 activation 重验可观察失败并拒绝候选；Decision enqueue 失败路径另记录停止。 | checker 必须区分首次异步 overflow、首次业务观察与 stopping 提交边界；不能假设所有失败都发生在同一处，也不能把 SourceFailure phase 等同共享槽已清空。 |
| 结束与关闭 | `close_source()` 等 Tick/prepare/Sink 生产者结束，记录真实 Close 状态，再独立输出 Witness；Sink failed 会打印 flush false并导致诊断监管器 RC2。 | R5 runner 需要把预期 regulator 早退/RC2作为待机制解释的原始事实保留，同时继续 worker/fixture/recorder 的归属清理；早退本身不能自动判机制通过。 |
| base、ledger、比较器 | 原 normal checker 和 application ledger要求源完整；C0 source↔Witness 比较器要求完整 source 对拍。原 runner 没有 R5 机制 gate。 | 独立 R5 checker/组合报告将机制结果与原 base/正常 ledger失败分列；原工具不改宽。压力时不能强求 C0 的 source 全量相等，也不能把日志缺行作为“停止提交”的证据。worker/recorder/owned/audit 的完整性仍需独立核对。 |

当前有限暂停代码的真实 QueueOverflow 观察发生在 dropped 增计和 failed 置位之后。它可以作为同一 pinned 实现中“至少发生一次容量拒绝”的独立路径证据；具体 depth/counter 数值和 summary 是否确实存在仍须在事前判据中写明。本计划所说的约150回调事件/s只是触发设计，不能代替现场队列事实。如果未触发 overflow，该 run 是未覆盖/未触发，不能在运行中延长暂停或测量直到过关。

## 已知共享槽缺口仍未修复

诊断源码的 Decision enqueue 失败分支目前执行 `normal_complete_=false`、`stopping_=true`，设置 stop_start，并在业务 mutex 下记录 `StoppingObserved/DecisionEnqueue`；**该分支没有调用 `invalidate_locked()`**。随后在同一拍，如果最终请求已经接近零，tick loop 可以直接进入 shutdown 并 break，而无需再经过下一次 TickStart 的 invalidation。

`invalidate_locked()` 才是清空 admission、candidate 和 pending 的既有业务函数。最终 Close phase会在真实锁下观察这些共享状态，不能替业务把它们写为 false。因此当前源码保留了“Decision enqueue failure 同拍退出时，共享槽可能未清”的政策缺口。这里的“可能”是路径风险，不能预测每次运行必然存在非空槽；是否被实际压力路径触发，应由真实停止/Close快照和 commit 记录判断。

C0 不触发该失败分支，因此即使正常对照全部通过，也不能宣布这个缺口已修复。R5 必须保留它作为真实待验行为。若运行中 stopping 之后仍有不允许的 commit、共享槽未清、缺失 invalidation 状态证据或预算超限，机制结果须保持失败。随后另做最小业务失败路径修复，升 source/bin/tool 版本，重验受影响的正常对照和该失败路径；不能修改 Witness、事后换边界、补造状态或把原失败 run 改成成功。

## R5 的事前政策应一次锁定

沿用主计划 B3 的唯一新增批次，不重开已完成的无关故障矩阵。新的 R5 policy 与源码/工具版本、run id、boot、diag5、同一诊断 bin/worker/fixture、512 log queue和所有不相关 fault0一起事前保存。需要锁定以下真实边界与拒绝条件：

1. **触发前置**：C0 的现场独立门已完成；owned source/worker/clock就绪，至少两次原生候选虚拟激活已由同一身份链核实。arm最多一次，压力只允许no_output、诊断fault允许、Witness开启和显式声明。
2. **长度**：测量上限15s、pause上限5s；arm、PauseBegin、overflow、首次 SourceFailure/业务观察、stopping commit、解除、Close各自记录，whole-owned前后准备不被伪装成全部在15s内。
3. **真实压力**：实际达到512容量且enqueue dropped>0；QueueOverflow前的暂停期间至少5个真实 Tick完成。没有触发、过早失败、固定审计溢出均不能通过。
4. **时序**：候选 tick jitter20ms；首次业务观察相对首次声明故障边界≤220ms（T+jitter）；pause≤5s；release后的优雅收尾观察≤2.5s。这是本有限实验要求，不是WCET或内核绝对退出保证；每次超预算单列。
5. **停止后行为**：以真实 stopping 业务提交边界为准，之后新 Submit和accepted Activation增量为0；拒绝 activation attempt单列。overflow到业务观察之间已授权在途项保留完整归因，后到的bag/ DDS publication不能反向当成新业务commit。
6. **真实失效状态**：在实际观察边界核对 candidate=false、admission slots=0、pending=false及不能再次提交；哪个phase/快照承担这项证明要在跑前固定。unknown不是false，“没有后续日志”不是槽已清。
7. **完整性分账**：预期失败仅限声明的原Sink；原source dropped/normal_source_complete=false、flush false、RC2、base/正常应用ledger失败照存。summary缺失保持unknown。worker、fixture raw录制、recorder、owned账本、独立Witness的额外缺口、异常或未知尾部仍使机制失败。
8. **收尾与下一次启动**：pause必须解除或被有限Close取消，取消原因和时刻明确；按每owned组SIGINT0.5s、TERM1s、KILL后查1s保留身份与remaining成员事实。任一清理/监督证据不完整禁止下一launch。

Witness容量计算也要覆盖就绪、测量和关闭尾部；15s最多75个正常周期不能说明整个owned生命周期只有75个周期。需要在事前有限readiness/收尾预算下核对容量，容量不够的真实run仍按audit incomplete保存，不能边跑边扩大数组。

## 最小推进顺序

先等待本次 C0 现场证据，并按实际 source/bag/ledger/Witness/窗口/资产/owned 门验收，不用“工具49tests通过”替代它。C0通过后，保持该版本与原件，创建一个独立R5实施包：专用runner、机制checker、事前policy和有限退出/unknown/早退拒绝测试；对默认关闭和配置拒绝做受影响验证，再执行一次已声明压力。

如果无需改C++而可用当前真实phase和计数证明全部判据，R5应与C0复用同一个诊断bin/contract；新R5工具仍需独立版本和hash。如果为了缺失的深度/状态快照必须修改诊断源码，不能沿用旧C0结论称新bin已对照；保存差异、升版本并补一次受影响的C0。若之后发现业务共享槽政策不满足，再单独修复该失败路径并保留原机制失败证据。

最终 `expected_log_overflow_mechanism_passed` 只有全部R5门闭合才可为true；`normal_contract_complete=false`、`publisher_rate_verification_available=false`、`plant_acceptance_observed=false`、`execute_qualified=false`、两物理topics端点全run0必须保留。即使R5通过，动态来源不足仍阻止M0b正式冻结，随后B4逐字段来源决定、B5不可变合同和独立M4确认仍各有剩余工作。

## 依据

- 当前主计划：[P1_M0b_参数来源与政策表及最小校准计划](C:/Users/sgh/Documents/MPC/P1_M0b_参数来源与政策表及最小校准计划_2026-10-07.md:149)，B2/B3及失败保留要求位于其161—174行。
- 当前 C0 现场模板：[remote_run.template.py](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_C0_comparison_20261008/remote_run.template.py)。
- 现有 normal-only 入口：[run_r5_diag_validation.py](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py:49)。
- 有限暂停/overflow实现：[p1_diag_sink.hpp](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/p1_diag_sink.hpp:29)。
- 共享槽清理、TickStart与Decision enqueue失败路径：[regulator_r5_diag.cpp](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp:181)。
