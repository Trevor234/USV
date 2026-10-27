# 114 B0/B1 与 112 实际输出权威实现复核

只读审查；未改 112/113/114、未运行 ROS/owned。离线程序直接 include 112 原始头文件，编译及运行输出见同目录。

## 1. B0 当前写法不能实施：混淆两个不相同的组件

114 报告第二节 B0 写“通知 own_authority_（change_version 路径：pending 重置、锚随权威事实）”，第三节称最小 diff。实际：

- `112/implementation/t2_author/observer/src/shadow/regulator_owned_execute.cpp:1289` 的 `own_authority_` 类型是 `p1::owned_execution::OutputAuthority`，实际类在 `.../owned_execution_policy_native_v1.hpp:60–143`。
- 该类无 `change_version()`、无 `version_` / `pending_` / `active_` / 内部互斥。头部第 7–9 行明确要求独占输出线程串行调用。`authority_interface.cpp` 编译期 SFINAE 断言已证明此接口不存在。
- 全树真正的 `change_version()` 在 `common/command_anchor_v2.hpp:223–231`，是 C3.6 shadow adapter 的 `CommandAnchor`。其调用是 `common/c36_runtime_adapter.hpp:22`。该函数第 225 行拒绝任何 active 事务，第 226 行拒绝与 owner 不同的 clock epoch，第 231 行只更新 version、清 pending；它完全不清 anchor/history/API 成功事实。
- `probe.cpp` 直接调用此实际组件，验证同 epoch 的 schedule 更新后 anchor 的 known/n/time/seq 原样保留；新 epoch 返回 `version_time_or_epoch`；active 事务时返回 `version_change_not_permitted`。

结论：B0 不能按现报告作为“复用已有版本协议”的一行改动。必须先改设计，说明新 policy 接口、单写者/同步、物理事实与仿真时间历史的不同失效条件。

## 2. 114 的竞态解释可成立，但不能写成唯一实测顺序或必然结果

实际 Regulator 的 clock 回调第 630 行持业务 mutex 清 `anchor_.known`，逐侧发布提交第 964–968 行分别持同一 mutex，二者可合法交错。`publication_result_v1.hpp:21–23` 在每侧真实返回后只更新该侧 known/n/time/seq。

`probe.cpp` 直接调用真实 `apply_channel_result`：side 0 commit → clear known → side 1 commit，能复现历史 `[false,true]`，与权威 `[true,true]` 的差别只有 known；n/time/seq 全同。这是强机制证据。

但同一 reset 若在两侧提交之前，则两侧提交后也可全同。因此“合法纪元变更瞬间必然分歧”不是普遍命题。原 Source 没有给每次 anchor reset 与侧提交完整线性化日志，精确发生顺序仍应表述为“与该交错一致且由组件复现”，不能声称排除了所有竞争顺序。另 `push_history_locked` 第 844 行也会因 sim 历史逆序清 known，在复现矩阵中必须覆盖，不能只检查第 630 行。

## 3. 不能通过清掉两套物理锚来消除差异

`owned_execution_policy_native_v1.hpp:96–98` 明确：“Successful sides remain irreversible after partial failure, rate/gap/span failure, or stop.”

权威 anchor 的 n/time/seq 是实际 API 的稳态时间事实，不是仿真时钟映射资格；clock epoch 变化不会撤回已经成功的 publish。该类第 119–121 行用真实前锚检查 rho。若为了“对称”把 authority known 也清掉，会改变 rate 检验适用条件与 unknown→zero 的规则，必须作为实质政策改变单独证明，不是保持原守卫语义。

相反，可研究保留物理 API 账本，单独失效 sim/propagation history、旧 Job/Ticket/RTF/reference epoch，再由真实新侧结果重建新 sim epoch 的传播覆盖。当前 `predict()` 第 866–867 行要求两侧在 odom stamp 前各有有效 held event，这正是应保留的资格门；没有覆盖不能用物理 anchor 冒充 sim 历史。

## 4. 线程与原子性要求

现有 own_authority 的 `tick`（1100）、`business_permitted`（983）、`record_pair`（1232）都由输出线程访问。若 clock 回调直接调用新 mutator，将引入无锁跨线程读写。给 mutator 单独加 mutex 也不足以使 history 的逐侧 commit 与 authority 在 pair 后一次性 record 共同原子化。

推荐新设计让时钟线程只提交 epoch-invalidated 标志/版本（在现业务 mutex 下）；输出线程作为唯一 authority writer，在明确 transaction barrier 上处理。API 调用不可持业务 mutex，成功 API ledger 无条件先记录。必须保留 per-side publish_epoch 与旧/新 epoch 的归属，不能用重贴新 epoch 修饰旧调用。

## 5. 建议下一步

1. B2' 单因素：先做 Fixture 恢复连续性组件测试与 pin 归因；保留原守卫，无 B0/B1 放宽。
2. B0 重写为“物理事实不可撤回 / sim epoch 历史独立失效”的设计批，定义事务边界和重建条件后再动 Regulator。至少覆盖 reset 在 pair 前、左调用前后、两侧之间、右侧后、API/Applied 记账前后、partial side failure，以及 push_history sim regression。
3. 正控：新 epoch 的新鲜 odom、两侧传播历史覆盖、RTF 资格齐全后才恢复；负控：旧 Job 不复活、deadline 不续期、真实 rho/gap/span/侧失败仍停止。
4. 不采用 B1 仅按 N ms 时间窗豁免真实锚分歧；“绑定 epoch 事件”不等于证明分歧由该事件唯一引起。若确需过渡协议，必须验证调用身份/事实归属，不能把不一致统统 re-anchor 后继续。

本审查不证明任何 proposed policy 已安全实施；只闭合接口事实与离线交错反例。M4/F6/P1 不升格。
