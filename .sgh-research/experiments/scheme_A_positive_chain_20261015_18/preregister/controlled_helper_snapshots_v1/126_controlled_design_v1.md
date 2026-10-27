# B/C 受控 owner 与动态一致性组件设计 v1

建立日期：2026-10-15；实现准备更新：2026-10-16。依赖：A 实际正常阳性先通过，才允许 B/C 的 ROS 实验。本文不授予任何阶段、执行或研究资格；当前已完成独立纯组件及受控 Observer/Worker 源码接线，等待新冻结构建和真实运行；不改 A 的五角色源码/注册。

## 已定位的必要改动

1. `p1_shadow_entry.hpp` 的 baseline 常量、Observer 与 Worker 各自 `p1_full_contract.hpp` 的 `baseline_input`、新 owner startup 常量必须共同精确绑定新基线 `CONTROLLED_PHASE_20261015_DIAGNOSTIC_01`。不得允许任意字符串、回退 F5、冒用 F5 资格或跳过逐字段完整校验。原合同其余固定数值、150 ms 截止、200 ms 激活、状态容差、GID/PIDfd、历史/锚点守卫全部保持。新合同独立 SHA；N10 Worker 因旧合同固定 F5，不适合直接复用新合同，必须只变基线的独立源码/二进制。
2. 新 owner 可复用 `p1_owned_identity.hpp`、create-only release、真实启动 owned manifest、Supervisor/auth/Source/Storage 验证方式。冻结 F5 的 `PublisherStartupGate` 自带 F5 lineage 常量，必须独立派生新命名 gate，声明 diagnostic lineage；不要复用旧 F5 startup 内容伪造身份。三角色另存 source/build registries，不覆盖 A。
3. 不能只让 owner 订阅 `ExecutionDecision` 后发布。当前 Observer `finish_tick()` 把 Decision 异步入 Sink 后立即 snapshot 并提交下一个 Preparation；实际 Decision DDS 到达 owner 时，下一任务通常已冻结。必须新增显式相位握手。

## 最小真实相位协议

新增 `/p1/controlled_owner_phase`，使用现有 `std_msgs/msg/String` 的严格有界 JSON，避免接口代码生成/overlay 安装。独立固定 schema，恰好声明的字段，无额外/重复字段；64 位整型不接收 bool/浮点。绑定 run、boot、contract SHA、baseline、producer、Decision sequence/tick、Applied sequence、完整双通道调用 start/end、command、发送时间和 `held_until_ns = decision.tick_planned_ns + 200000000`。Source 记录原始有界 CDR 与实际 GID。

owner 的 Phase Writer 必须在 owned manifest 中声明。Observer 用同 owner 的另一组精确 topic/type/GID/PIDfd pins 认证，不能把 payload 自称身份作为权限；owner 的 Job/Decision 订阅也必须绑定原 Observer 的实际 Writer GID/进程。

相位顺序为：

- Observer 完成本拍 Decision，记录该 Decision sequence/tick/planned，进入 `AwaitOwnerApplied`，此时不冻结下一 Job。保留原 planned+150 ms 截止和 planned+200 ms 激活。
- owner 收到、认证该 Decision 后才允许一次真实双通道 publish（首次无 Candidate 时保持零；正常 accepted 时采用 Decision 实际 final_n；普通拒绝时保持旧值）。真实调用全部成功后发布 Applied，再发布 PhaseCommit；期间无另一个输出线程/定时器。
- PhaseCommit 只声明此前实际提交成功的 Applied，并承诺此后保持到下个对应 Decision。不要把 Applied 原有 cycle_sequence 未经新合同解释为决策 ack。
- Applied 与 PhaseCommit 跨 topic 无到达顺序保证。Observer 必须在同 business mutex 内同时拥有完整合法 Applied 和对应合法 PhaseCommit，核对 sequence、双通道值、真实调用时间、owner/contract、Decision 绑定后，才 snapshot/enqueue 下一 Job。二者先后到达均可；不能先写假锚点或只收到承诺就冻结。
- owner 收到此 Job 后进一步核对 target tick/origin/deadline、冻结锚点/Applied sequence，并保持物理命令不变至对应 Decision。重复同值发布可不实现；最小原型直接禁止窗口内任何常规发布。
- phase 缺失、重复、错序、回放、foreign、晚于原截止、调用部分失败均不提交 Job，不移动 origin、不延长 deadline。若命令不确定即整个组件不合格。丢失 Decision 时继续保持，超过诊断 watchdog 仅走有证据的关闭/回收，不自行发布新业务值。

此调度只允许已有正常 DDS 回调继续处理，不暂停 Applied 接收、不扩大任何容差、不强制 Accepted。Shadow Observer 本身仍无执行权限；额外命令 owner 仅用于隔离 localhost 诊断，不是正式 execution。

## B：单一输入变化对照

先用新受控基线跑 A2（零参考、零状态、零命令、相位握手）证明其本身连续合法接纳。A2 与 B 的二进制、合同、参考、状态、owner 身份规则、运行预算一致；唯一业务差异是预先声明的 B mode：owner 收到一个原生真实 Job 后，在其 origin+100 ms（且实际仍小于原 deadline/target）执行一次小非零双通道脉冲，例如 +0.1 N，然后保持至对应 Decision。

脉冲是有意违反 held-input 前提的负例，不伪造 PhaseCommit，不覆盖旧反馈，不改变路径/参考或 Synthetic 状态；原始 Applied 必须真实收到，原生锚点/历史守卫应该拒绝该 Job。观测到拒绝以后才允许按下一相位回零。判据必须包含同 Job：Ready 成功、版本不变、状态输入不变、完整 Applied 时序/值改变、实际最终 anchor_mismatch 或 anchor_history_changed；不得仅数 Accepted=0。

## C：ActualApplied 驱动 Plant

在相同单 owner 相位机制下，将 Synthetic 改为独立诊断 Plant：以合同固定 hydro 参数调用已固定的 `USVDynamicModel`，按每通道实际 Applied 的仿真调用时间分段 RK4 积分；不得用 Candidate、requested_n、预定调用时刻替代实际 Applied。双通道调用非原子，中间区间必须分别使用各通道旧/新值。

Plant 发布状态的 stamp 不能领先于已处理实际输入水印；收到稍晚的 Applied 时按有界历史事件回放（恢复之前状态、按事件真实调用时间重新积分），未来传感器才使用纠正后的状态；已发旧传感器不追溯改写。每次状态发布需 Source 记录 state、stamp、Applied sequence/watermark、模型/参数 SHA、积分分段，离线独立复算。50 Hz 传感器与实际时钟继续新鲜；首个最小动态原型参考采用预注册的真实 0.05 m/s 直线；必须有实际非零命令与状态变化，不能以零参考充当动态结果。该低速原型通过也不能授予 0.6 m/s 或正式航行资格。

先验证非零命令真实发生、状态非零变化及输入/状态复算一致，再检查连续实际 Accepted 与冻结窗口输入不变。C 只能报告 nominal diagnostic Plant 闭环；真实 Plant 接纳、硬件、M4/F6/P1 资格仍未证明。

## 独立最小实现准备

`controlled_phase/phase_protocol.hpp` 提供无 ROS/IO 的精确相位状态组件与边界判据；`phase_protocol_test.cpp` 做真值表/错序/晚包/跨 topic 顺序的有限验证。纯组件本身不认证实际 GID、不发布命令。受控 Observer 现已实际接入第二 OwnedPeer（同 owner 的独立 Phase GID/PIDfd）、严格有界 17 字段 JSON、原生 Applied 接纳完成后的相位记录、跨 topic 合流后冻结，以及 executor detach 后的接收人口闭合 Source 行。Worker 与 Observer 的合同固定常量已单独派生为新基线。45 项纯 phase、20 项 Observer 合同/身份守卫、18 项 Worker 合同守卫合计 83 项已以独立 native 编译通过；最终冻结构建、runtime identity 和实际运行由根任务后续验证，不代表 B/C 已完成。

## 当前停止线

A 未通过时只定位 A 的首个真实失败原因；A 通过后先 A2，再 B，再 C。不能用本设计或纯组件测试替代实际 DDS/owner/Plant 运行证据。

## 2026-10-16 当前事实

A 已完成实际 DDS 阳性：22 个连续 Accepted，25 个 Applied 为精确零，原有 checker 全部 joins 通过。受控 A2、B、C 的真实运行尚未验证；当前按 A2→B→C 顺序执行，任何阳性未通过即定位首个实际阻塞，不增加外围负例。C 的预注册参考为 0.05 m/s。
