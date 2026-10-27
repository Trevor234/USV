# P1 活进程不响应/能力消息失联：执行前核对（2026-10-06）

沿用control-preflight-reflect，ROS任务中EDA的STA/CTS/DRV/PPA/Slurm不适用。当前事实入口progress_v11：worker v8、regulator v10、revision3、912项guard及已完成的非空pending退出/三项回归。先重新核对host/boot和资产后才提交；身份、物理端点、录制和owned清理失败即停止。

## 事实与假设

regulator有固定pidfd和1s active watchdog，但capability callback将worker_valid保留为true，没有有效消息接收有效期。最后已观测active=0时，对owned worker施加SIGSTOP使整个进程不响应，PID仍存在且没有新capability，理论上tick会继续提交。必须实测，不能仅凭代码勾选。能力消息只有固定startup_ns，无逐包发送序号/时间；不能宣称接收租约是源新鲜度、抗重放或求解进展证书。

假设排序：1. 空闲不响应缺少有限终止政策（高）；2. 无效/外来消息或到期后新消息可能延长旧状态（需明确接纳和终止顺序）；3. 忙时watchdog与消息接收租约应独立，心跳正常也不代表native有进展。

## A/B/C 与提交决定

- **A（选择，GO于复现和诊断修复）**：原regulator v10/revision3先运行一个create-only idle_stop观察run：真实native接纳后确认owned worker active=0/pending=0，SIGSTOP，核验/proc状态T及PID/starttick不变，输入继续1.8s；记录后续提交/决定，SIGCONT后再观察0.8s，仅owned有限清理。旧合同没有失联时限，按“缺口复现”报告，不把未来政策当旧合同已声明阈值。
- 若复现，备份v10；新增**revision4诊断**政策，valid_identity_capability_callback_receipt_lease_terminal_until_new_run，接收租约初值600ms（worker原200ms发布周期的3倍，只是诊断试值、最终执行数值待M0b校准）。以真实验证提交时的CLOCK_MONOTONIC为起点；等于上限允许，超过则终止且禁止同run恢复。每个submit/activation/enqueue及capability callback续租之前检查；无效/外来消息不续租、不更新active watchdog状态。记录完整capability内容、验证提交、续租/失效身份；source freshness available=false。pidfd、原150ms deadline/200ms tick与1s active watchdog均保留。
- 新版验证idle_stop、active_stop（旧受控pre-native barrier+SIGSTOP，不伪称acados真实卡死）、invalid_capability_stop；实际源与MCAP完整字段绑定，终止相对最后valid commit严格超过600ms且不超过600+200+20=820ms诊断观测窗口，之后无新提交/激活/续租；SIGCONT后至少0.8s不自动恢复。invalid副本只有声明字段改变，全量对拍、不能包装成原worker消息。无物理端点。正常、delay150、pre-native watchdog、非空pending退出、VRX shadow各必要回归一次，保留不同正常/故障门禁。
- B：若观测/会计前提失败，保留失败，只修明确错误，新编号重验，不改变阈值。如果不复现则重新分析，不能为实现预设修复强行改代码。
- C（NO-GO）：SIGSTOP整个调节器造失联；把PID存在等同响应；用旧220ms死亡观察预算替代新接收租约；删失败/补源记录；以600ms试值授予execute或F6。

## 验收与停止

每次真实进程固定boot/PID/starttick/可执行hash，全程0物理输出；实际能力消息观察与声明注入、source完整字段与MCAP计数核对；正常source/flush及owned清理；KILL忙时闭合unknown保留。旧缺口可因机制未通过而独立通过“复现证据”门禁，不能伪装修复验收。新诊断每次原capability至少有2次有效续租、失联时至少5个终止决定，源最后valid time决定到期边界，预提交DDS尾部单列。

新策略优先检查既有租约到期再决定续租，到期后即使收到匹配消息也不自动恢复。首条有效能力消息之前worker不能提交；不将初始没有能力消息等同同run恢复。执行级数字、源序号/发送时间、通信真实性、真实最坏负载与输出恢复仍是M0b/后续范围，M2整体不因三个诊断通过自动完成。
