# C3.6-B：N10 → N13 shadow adapter 最小接入点只读审查

日期：2026-10-13。审查对象为冻结 N10 observer 运行源码和冻结 N12 command-anchor 组件。本文只给出接入建议，未修改 N10/N12，没有运行 ROS 节点，没有产生执行资格证据。

源码：

- [N10 regulator_shadow_observer.cpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/observer/src/shadow/regulator_shadow_observer.cpp)
- [N10 p1_admission.hpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/observer/src/shadow/p1_admission.hpp)
- [N10 p1_shadow_entry.hpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/observer/src/shadow/p1_shadow_entry.hpp)
- [N12 command_anchor_v1.hpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_20261013_v12/include/command_anchor_v1.hpp)

## 1. 当前代码的实际线性边界

| 边界 | 实际点位 | 应保留的行为 |
|---|---|---|
| 原始冻结 | N10 `finish_tick` 第 561 行在 `mutex_` 下调用 `snapshot_locked(enqueue_now)`，把 Snapshot 放入单一 preparation pending；`prepare_loop` 第 512 行取出后释放 prep 锁 | Job 的 anchor、version、freeze 时间和完整输入来源来自此 Snapshot。不能在稍后的提交点重新读取当前 anchor 冒充原始冻结。 |
| 提交授权 | 第 528–533 行在 `mutex_` 下复核 worker、stopping、sink、version、current_tick、deadline、resource，分配 job_id、保存完整 Job 并写 WitnessSubmit | 组件 pending 必须与确实授权的 Job 完整 echo 一致；DDS Job publish 在业务锁外。已授权 DDS 尾包允许在后来 terminal 观察后完成。 |
| registration | 第 499–510 行先检查资源、solver success、完整 prediction/command/timing，再在 `mutex_` 中与保存 Job 完整 JSON 比较，register/finalize_ready | 新组件不能用局部 FrozenJob 匹配替代完整 Job/Candidate、state/clock/lease/resource 检查。最终 ready 时间取实际 finalize 完成时刻。 |
| cutoff | 第 641 行在 deadline+1 后持 `mutex_` 执行 Admission.cutoff；第 586 行 Admission.take 也会先执行 cutoff | equality 不关闭；晚于 deadline 才能 cutoff。adapter 应支持 take 的隐式 cutoff并记录真实线性时刻，不能假定只有第 641 行一次入口。 |
| 最终 activation 判断 | 第 602–629 行在 `mutex_` 下再次检查输入 version/odom/imu，完整连续 publication history、worker/lease、当前 input/clock/RTF/age、jitter、target sim、command rate、stop | 新 anchor gate 必须在这些现有 guards 之后且同一业务锁内执行；不可用较早 Snapshot 的合格结果替代最终实情。 |
| Applied | 第 427–468 行在 `mutex_` 下做 whole-pair assessment，才合并 anchor/history、加入 held history 和 readiness | 当前 callback 没有 MessageInfo，payload identity 和启动 count=1 无法实时认证 GID。新 adapter 需要先认证真实来源。 |
| terminal/close | `unusable_locked` 第 367–380 行和 `invalidate_locked` 第 366 行清未提交状态；tick 结束后 prep_stop/finished；`close_source` 第 150–156 行 join 后关闭 sink/witness | 关闭意图、组件关闭、executor stop、source flush、发布者 owner/session/endpoint退出是不同事实；不可合并成一条 closed=true。 |

## 2. N12 不能直接移植到 shadow 的五个原因

1. `activate` 成功会创建 Active，令 `whole_=false` 并清 Pending。shadow 没有 actuator IO，不能编造 start/complete/settle。下一条真实 Applied 会因为 `unexpected_feedback_during_transaction` fault。N13 应增加 observation-only 的最终复核并消耗 pending 路径，成功后仍可接收真实 owner 反馈；不能把 shadow Decision 当真实调用成功。

2. `freeze` 内部 ticket.prediction 始终默认零。adapter 不能在返回 FrozenJob 上填非零预测，因为与组件内部 Pending 的 same_job 会失配。N13 应支持完整、同一业务锁捕获的 ticket/prediction 原子导入，或将原始冻结字段保存为单独不可变输入。Job 首次构造之前还没有 job_id；若在提交点才导入，必须使用原始 Snapshot 的 anchor/freeze，不能读当前组件 anchor。

3. Pending 没有 cancel/expire/consume-reject 接口。没有 Candidate、late Candidate、外部 activation guard 拒绝、skipped tick、preparation replacement 或 version invalidation 都可能留下永久 `slot_busy`。N13 必须清理所有未提交 slot；组件冻结的任务不等于已提交且可激活的候选。增加清理接口时仍要保留单槽、单调 job identity、no stale activation 的约束。

4. N12 last_target 是 owner 生命周期内单调，N10 schedule 改变后可能 origin 重建且 tick=0。不可在 schedule generation 变化后仍比较旧 target=20 与新 target=1。有限政策可以选择终止 owner 并要求新独立 session，或给 `(schedule_generation,target_tick)` 明确排序；不能在未认证新 epoch 的情况下静默重新构造组件绕过 terminal。

5. N12 Owner 只包含 run/boot/producer/config/epoch，而且只是值匹配。它没有 PID/startticks/source/bin/model/typed 参数或实际 DDS endpoint 认证。N13 需要额外不可变身份上下文和 authenticated receipt 入口；不能由一条自称正确的 payload 反向决定 owner。

## 3. 最小认证 adapter

启动前读取并固定 F5 publisher 的 owned manifest 来源和 SHA，核对该 run/boot/PID/startticks/source/bin/config、typed 参数、Applied publisher 的精确 topic/type/GID。记录 observer 自己真实 reader GID，并在 graph arm 期确认所声明 publisher 的精确端点且唯一。graph count/node name只提供图发现辅助事实。

Applied callback 改为接收 `MessageInfo`。先做有限字符串/资源检查，再记录完整 reserialized CDR、实际 rmw publisher_gid、publication/reception sequence、intra_process、callback sequence及实际本地 receipt 时刻；其 CDR 是收到 typed 对象的重新序列化，不能称为网络原始 padding 或投递保证。实际 GID 与固定 owned manifest 不等的回调，不能调用 component.observe 或改变认证 anchor。ready 后即使外来/重复回调不改变 anchor，仍按当前完整 receipt 人口政策 invalidation 后停止新提交。

认证 GID 但 payload owner 错误、认证 payload 但 GID 外来都必须分别拒绝。保持 `p1::shadow::assess` 的全对/时序/clock/sim/history判据。若 N13 要观察认证发布者的部分调用事实，可以在独立诊断行记录真实逐路结果，再保持当前 whole-pair failure 对业务资格的 terminal 影响；不得把部分发布命令事实转换为 whole-pair accepted。

N12 valid_owner 的 producer ≤64 且可见 ASCII，比 N10 LegacyIdentity 的 ≤128/无 NUL 更窄；正常 F5 digest producer 可满足，但更窄支持域须登记并显式拒绝。禁止 trim 后宣称同一 owner。若本批只认证 Applied owner，应明确 WorkerCapability/Candidate 的实时 GID 认证未由这部分实现取得，避免扩大闭合声明。

## 4. 锁与生命周期

固定锁顺序为 Regulator `mutex_` → 组件内部 mutex →（必要时）`prep_mutex_`。prep 线程取 preparation 后必须先释放 prep 锁，再取业务锁；保持旧代码模式。组件不得在内部持锁时调用 adapter 回调、获取 Regulator 锁。manifest IO、DDS publish、thread join 不放在业务锁内。

在终止输入/source/worker/lease/stop 观察时，同原业务锁记录 adapter 关闭意图和清 pending，立即禁止新的 freeze/ready/activation。F5 safeshutdown可能仍产生真实 zero tail，N12 close 在没有 Active 时立即转 closed 并拒绝 observe；因此外层应独立保留认证尾包观测/结算，在登记的尾包边界后才调用组件 close，或将后续tail保存在明确独立诊断人口中。不能为了收尾包重新打开 terminal 决策。pidfd死亡同样禁新提交，原认证 GID 已排队的 DDS tail 是否合并命令事实须独立政策。close_source join 后记录 observer adapter 已停止接收/结算的事实。F5 session 结束、controller cleanup、actual process/endpoint退出需要 driver/owned source关联证据；component Life::closed 仅表示它不再授予新的组件操作。

许可之后关闭与跨路关闭的真实 IO 政策仍须由未来独立 execute adapter定义。此批 shadow 不应调用组件 start/complete，也不应写 publish_success=true、plant_acceptance=true、execution_atomicity=true。历史 F5 start/end 是 F5 的调用事实，不能归因于 N13 adapter 自己发了 IO。

## 5. 必要验证人口

source-linked native adapter 测试至少覆盖下列真实路径和语义边界：

1. 原始冻结后同值连续 Applied、命令变化、变后恢复、history eviction；完整 Job echo仍匹配原冻结且激活等价判断正确。
2. registration equality/late/finalize超期、重放、重复slot、完整 payload 任一字段变化（不是只 job_id 相同）。
3. 没有 Candidate 和早期/最终 state/clock/lease guard 拒绝后，下一任务可进；准备被替换、skipped tick、job publish失败均无 stale slot。
4. implicit take cutoff、显式 cutoff、deadline equality；已经外部 rejected 的任务不能再 activate。
5. schedule重建/tick归零、epoch变化、worker instance变化、source失败与stop；不得复活 terminal owner。
6. 认证GID +错误payload、错误GID +正确payload、第二publisher、GID更换、publisher退出；均保持旧 readiness complete population规则。
7. 左成右败、左失败右未调用、时序异常、clock epoch异常；逐路事实与业务whole-pair拒绝分别记录。
8. close前已有Job DDS publish尾包、close时已有Applied尾包、sink flush失败；关闭意图不抹除已发生事实，也不许可新提交。
9. 死锁受控测试和各锁路径，不使用延迟 runtime hook换取“正常”资格。

真实 owned shadow 运行应另行保存 startup/reader/manifest/CDR/GID/source/bag/Witness/close ledger，在新 source/bin/config 固定后进行，并只称受控 runtime integration验证。native测试、历史重放、反例副本不替代新的20s动态/mixed/压力/恢复/failed-close运行，也不授予 B4/M0b/B5/M4 或研究结论。
