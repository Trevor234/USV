# 首次 DecisionEnqueue 失败：共享槽即时失效的独立最小设计审查

日期：2026-10-08。审查范围：冻结 B0 普通 regulator 与冻结 B1 诊断 regulator 的真实业务路径。当前仅只读审查和设计，没有修改冻结文件，没有连接 Ubuntu，没有运行 ROS。

## 前提核对与确定缺口

| 冻结来源 | SHA256 | 关键位置 |
| --- | --- | --- |
| `m0b_contract_implementation_20261007/safety/regulator.cpp` | `1163a651580bde314e8b450d39213c1691187fbe977debe63a0366c6e027eb8c` | `invalidate_locked` 135；prepare pop 223；DecisionEnqueue 303；直接 break 306 |
| `m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp` | `a67d65fdde95ff754ca26d0bffe93e12f2cfbce9d8943d6cf01047b499e34cdb` | `phase_locked` 117；`invalidate_locked` 181；TickStart 316–318；DecisionEnqueue 364–366；直接 break 369 |

两个文件均存在同一真实缺口：`sink_->add(decision_json(d),d)` 首次失败后，设置 normal=false/stopping=true，但不调用 `invalidate_locked()`。紧接着 `d.final_n` 为零时可以同拍直接 break，因而不会进入下一 TickStart 的既有清槽路径。析构和 `close_source()` 只 join/close，不补做共享 admission/candidate/pending 失效；diag Close 会照实读到当时状态。

已经关闭最终提交/接纳门，不等于共享槽已即时净空。这次修复针对共享槽的退出边界；不应把前提扩大为“已执行的当前物理命令可以撤销”或“所有历史、在途工作都应删除”。此前真实 R5 是 TickStart 首先观察失效并清槽，其后才经过 DecisionEnqueue，因此不能作为首次入队失败分支已修复的证据。

## 最小业务修改

建议从上述固定来源生成本轮独立副本，保持旧源、旧 binary、C0/R5 原始报告和 checker 不变。普通和诊断副本各只修改 DecisionEnqueue 失败块：

1. 保持 `sink_->add(decision_json(d),d)` 和 DDS 发布在业务 `mutex_` 外。Sink add 返回后，其内部 queue mutex 已释放。
2. add 返回 false 后获取业务 `mutex_`；在该锁内设置 `normal_complete_=false`、`stopping_=true`，保持原 `if(!stop_start) stop_start=now` 的首次时间策略。
3. 在同一业务锁内**每次无条件**调用既有 `invalidate_locked()`：清 admission ready/committed、`candidate_` 和共享 `pending_`。
4. 业务清槽完成之后才离开失败块，继续原来的 next-preparation 禁止门与零输出/超时 break 判断。这样首次失败且同拍直接 break 也已净空。

无需清 `jobs_`、Admission 的 seen history、anchor、publication history 或输入 history；这些不是本次共享可接纳槽。无需改变 worker identity、代际、运行参数、Sink 容量、native success、deadline、命令缩放或 shutdown grace。

普通副本的最小逻辑应等价于：

```cpp
if (!sink_->add(decision_json(d), d)) {
  std::lock_guard<std::mutex> l(mutex_);
  normal_complete_ = false;
  stopping_ = true;
  if (!stop_start) stop_start = now;
  invalidate_locked();
}
```

这段仅是设计说明；尚未写入任何冻结或 live 源文件。

## 锁序与幂等

`invalidate_locked()` 已约定调用者持有 `mutex_`，内部按 `mutex_ → prep_mutex_` 清 pending。现有 callbacks、path/profile/clock 失效和 TickStart 使用同一锁序。prepare 线程持有 `prep_mutex_` 时只 pop pending 或进入会释放锁的 wait；之后释放该锁，才进入业务 `mutex_` 的提交门。当前没有 `prep_mutex_ → mutex_` 同时持有的反向路径。

修复不能把失败块放在已持有 `prep_mutex_` 的代码内再拿业务锁，也不能在清槽时调用可能阻塞的 DDS。Sink producer 的失败返回与业务清槽之间仍可能有调度延迟；普通 mutex 也不提供硬实时界，本次补丁不能自称消除所有失效延迟。

`Admission::invalidate()` 只 reset ready/committed，`candidate_.reset()` 与 `pending_.reset()` 对空状态安全，因此重复清槽本身幂等。**Witness 首次记录可以用 flag 去重，真实清槽不能被首次 flag 包住**。例如 TickStart 已记录失效后，再遇 DecisionEnqueue 失败，仍执行清槽，但不需要第二个首次 Invalidation 记录。

`prepare_loop` 已 pop 到栈上的 `Preparation p` 不再属于共享 pending，清槽不能撤销它。最终 submit commit 在同一业务锁内重新读 stopping/sink.failed 的原门必须保留；该门阻止清槽后新提交。先前已提交、随后在锁外完成的 DDS 尾部仍允许完成，不能因本补丁假称它被撤销。当前拍的 `t/cand/d` 也是先前快照或已提交对象，不属于后继共享槽。

失败同拍直接 break 后，原 tick 尾部设置 `prep_stop_=true` 并 notify，原 `close_source()` 有限 join 行为继续生效。仅 notify 而不改变 predicate，不会让现有 preparation-barrier 的等待自动取消；不应把一次 notify 写成在途 prepare 已完成清理的证明。

## 诊断证据最小补齐

diag 副本保留原 DecisionEnqueue phase5/observation3 首次记录。在业务锁内先记录真实 Stopping 快照，再调用 `invalidate_locked()`，之后若尚未记录首次 Invalidation，记录 phase8/observation3 的真实净空快照并置 `invalidate_phase_recorded_`。

建议顺序为：

```text
sink.add false（Sink 锁已经释放）
  → mutex_
  → normal=false, stopping=true, first stop_start
  → 首次 DecisionEnqueue Stopping phase（允许槽仍脏）
  → 每次真实 invalidate_locked（mutex_ → prep_mutex_）
  → 首次 Invalidation phase（槽真实净空）
  → 释放 mutex_
  → 原 direct-break 判定/后续 shutdown
```

`phase_locked()` 自己只暂时取得 prep mutex 读取 pending，没有把该锁保留到下一次 invalidate，因此不会递归锁住 prep mutex。每个 phase 的时间应在实际记录点采样，不把 phase8 提前到清槽之前，也不补造 candidate/pending/slots=false。保留 `enqueue_failed_recorded_` 对该路径 phase5 的去重，保留全局 `invalidate_phase_recorded_` 对首次 phase8 的去重；若 TickStart 首先清理并记录，后续 DecisionEnqueue 不应换写已记录的 observer 身份。

`WitnessObservation::DecisionEnqueue` 已是值3，基础 Witness schema 可以表达它。**冻结的旧 R5 mechanism checker 只接受 phase8/TickStart1**；不可为了新源、新分支的测试修改历史 checker。若后续要验证实际首次 enqueue 压力路径，应建立本轮独立 checker/政策/运行身份，并明确新增 phase8/DecisionEnqueue3 的来源规则。基础 Witness 审计通过也不能替代首次失败路径的业务净空证明。

## 有意义的定向测试方案

Admission 单独的 reset 测试或把失败块复制到测试 helper 后断言 reset，都不能覆盖此次缺口。测试必须调用**实际业务 Decision 入队结果处理和随后的同拍 direct-break 路径**，并且使旧源在对应断言处失败。

优先采用编译实际新副本的单拍 tick tail：如果为了离线可测性提取一个 `finish_tick`/tail 方法，必须把现有 `sink.add` 判定、实际失败块、后继 preparation 门和 stopping/direct-break 判定完整移入该生产方法，原 `tick_loop` 调用这个方法；测试也调用该方法，使用真实 admission 和真实共享状态。允许 narrow test fixture/friend 初始化状态与可控 Sink/clock；不创建控制线程、物理 publisher 或 native solver。单独调用新增“清槽 helper”不算真实业务路径覆盖。

若完整 ROS SDK 不能在当前测试环境编译，可另用源驱动 harness：从两个源文件的明确、唯一 marker 自动取出**完整实际 tick tail 控制块**和既有真实 `invalidate_locked`/diag `phase_locked`，直接编译该源块，包含原 add=false 分支、后继门和 break 判断；支持状态和可控 clock/Sink 放在 harness。固定源 SHA、每个 marker 唯一，并保证删掉生产清槽调用会使测试失败。不能手写一个逻辑相似的 helper，不能只正则检查新增文本。该适配证明的是实际源块的控制行为；若没有同时证明原 tick_loop 的调用连接，应明确列为待补证据。

最小定向集建议如下：

| 用例 | 初始/触发状态 | 必须检查的真实结果 |
| --- | --- | --- |
| 普通首次失败且零输出直接退出 | stopping=false、normal=true，真实 ready/committed admission、candidate、pending 非空；Sink 对本次 Decision 返回 false；final_n=0 | 同拍返回 break 前三共享槽已空、stopping=true、normal=false，未入队后继 preparation |
| 诊断首次失败且零输出直接退出 | 同上，旧首次 flags 均 false | phase5/obs3 在净空之前，phase8/obs3 在净空之后；真实 slots=0、candidate=false、pending=false；首次各一次 |
| 首次失败但非零、尚未达到 grace | 同上但 final_n 非零 | 本拍不直接 break，三共享槽仍即时空；不会新增 preparation；后继拍保持 stop 行为 |
| TickStart 已失效后再 enqueue 失败 | 原 TickStart 已记录 phase5/phase8，状态可能已空 | 重复业务清槽安全，首次 Invalidation 不重复、不改 observation；不得因 flags 绕过实际 reset |
| 重复 enqueue 失败/空状态 | 上一失败后再次进入实际 tail | stop_start 不重置，槽仍空，diag enqueue/first invalidation 记录不重复 |
| 正常入队成功对照 | Sink 成功、stopping=false、准备资源正常 | 不误设置 stopping/normal=false，不误清已有合法后继共享槽；原 next-preparation 行为保留 |
| pending 已被 prepare pop | 可控线程在真实 pop 后暂停，另一线程走实际 enqueue 失败块，再允许 prepare 到最终提交门 | pending 槽为空，栈上 p 不能产生新的 submit commit；此前已提交尾部仍按原合同处理 |
| 并发注册/清槽锁序 | callback 在清槽前后竞争 mutex，prepare 竞争 prep mutex | 清槽后 callback 的既有 stopping/sinkfailed 门拒绝再填；无反向双锁死锁，测试以有限 watchdog 失败退出 |

关键旧源负例必须分别针对 B0 与 B1 的实际 tail：首次 add=false 且零输出直接 break 时，原源未净空/缺首次 phase8，测试应失败；新源应通过。去掉新源的 `invalidate_locked()` 调用同样必须失败。这比只证明原 Admission.invalidate 能 reset 有实际价值。

所有测试要使用真正非空的 admission slot，而不是测试自己维护的计数。特别应至少覆盖一个 ready slot 和一个已 cutoff 的 committed slot；因真实 Admission 可同时有不同 target 的两个槽，也可补双槽情况。幂等时不要 reset Admission.seen 或 cutoff 历史来造“全新”对象，验证真实现有行为即可。

## 实施和结论边界

最小步骤是：冻结来源/hash → 新目录生成普通与诊断候选 → 两个实际入队失败块补清槽/diag证据 → 真实路径旧源负例与新源定向测试 → diff/锁序独立审查。本子任务仅输出只读设计审查，没有覆盖 live。

补丁通过静态和定向测试，只能先证明这两个候选源中的共享槽退出边界。后续普通/诊断编译、部署资产锁定、正常回归和首次 DecisionEnqueue 实际触发都应以本轮独立身份与原阈值另行验证。不得改写已完成 C0/R5 的旧结论或把新业务路径直接标成现场验收通过，也不能据此扩大为物理执行/硬实时资格。
