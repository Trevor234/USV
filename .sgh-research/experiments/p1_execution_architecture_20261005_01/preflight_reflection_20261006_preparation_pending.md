# P1 非空 preparation pending 与退出并发：执行前核对（2026-10-06）

沿用 control-preflight-reflect。EDA 的 STA/CTS/DRV/PPA/Slurm 不适用，ROS 等价证据为源记录、实际 MCAP、进程身份、有限清理和冻结资产清单。

事实：38 类候选矩阵已完成；前面的 worker 退出记录均为调节器 pending_before=false，不能推导非空 preparation pending 已验收。871 项当前资产无漂移；boot=5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb；controller/Gazebo=0，不可读 cmdline=0。worker v8、regulator v9、合同 revision3 为本次修改前身份。

缺口：准备线程通常很快取走队列，靠循环碰撞无法保证明确前提。worker pending_count 与调节器 preparation pending 是两种队列。当前 pending_before 的读取与 reset 分两次加锁，准备线程可能在中间取走任务；应把旧值和清除放在同一临界区，记录清除的目标 tick。

## A/B/C 与提交决定

- **A（选择，GO）**：新增默认 0 的有限诊断准备屏障，只允许 fault_injection_enabled 且 no_output，非零最大3000ms，在第3次取出准备任务时只触发一次。条件等待释放准备锁，节拍、退出检测和入队保持运行；退出/停机即时唤醒。原合同150ms deadline、200ms周期、诊断退出观察220ms均不变。先备份 regulator v9 源码/二进制/CMake，升 regulator v10，worker/原F5资源不变。独立新编号验证：首次两个实际 native 结果和正常接纳；屏障期间真实入队 pending；owned worker SIGKILL；源事件 pending_before=true、after=false 和清除tick绑定；屏障中主动任务退出后丢弃；退出后1.4s不提交/激活。保留全部证据。正常、150ms迟到、VRX shadow 回归各一次。
- B：若入队/退出/记录前提失败，保留失败，新编号只修明确证据或代码错误，不改阈值；如退出判据失败先停止批次分析。
- C（NO-GO）：通过冻结整个 regulator 造 pending，虚构 native hang，修改已有bag，或把诊断屏障当成真实最坏负载和安全保证。

门槛：源事件和实际 job/candidate/decision 完整字段对账；输入发布内容对bag；原始录制/flush/清理一致；实际worker进程身份和SIGKILL；至少5个退出后决定、0物理端点、无准备任务重新入队。独立checker的空pending、错tick、漏释放、后提交、后接纳等变异必须失败。新增C++验证屏障上限、默认关闭、模式约束和有限取消；Ubuntu相关Python回归。

stop：身份、物理端点、记录、有限清理或关键机制任一失败，保留并停止依赖实验。尚未覆盖活进程失联、真实物理预算、GP标签、证明和F6；M2整体及M0b/M4不因本用例通过而完成。
