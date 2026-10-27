# C3.7 Worker 回调与独立检查器接入审查

日期：2026-10-14。只读审查 N14 初始节点及上批后续计划；本文件不授权 execute 或阶段资格。

1. SolveCandidate 原回调没有 MessageInfo；Capability 有完整 typed CDR 但没有实际 Worker Writer GID 守卫。认证必须先于 Worker instance、完整 Job、lease、ready slot 的业务修改，并为两个接口分别固定 topic/type/GID。
2. 每个收到的回调都计独立接口 sequence/received count；资源拒绝仍保存有限 GID/MessageInfo 与资源事实。完整 CDR 只在资源域和认证成功后序列化；不从被拒绝数据重新构造不受限 payload。
3. Worker 专用 manifest/proc/pidfd 必须绑定 Worker 角色、两个 publisher 端点、nominal hash、worker instance、完整 typed 参数、source 与 binary pins。Manifest 与现场 `/proc` 证据完整；pidfd 仍不证明 post-pin exec 连续性。
4. 单次图快照不能证明 DDS 连续唯一性。外来同名、同 payload Writer 的真实 GID 是身份反例；resource、fatal、instance、lease 与完整 Job/Candidate 守卫仍分别保留。
5. 关闭的 Source 只证明接收日志及自身人口闭合。Worker 发布、Recorder 存储、Observer 接收有独立生命周期；特别是 transient-local startup 和最后 shutdown Capability，不能默认逐条送达。检查器报告完整发布/记录/收到/匹配/未收到集合，不把缺失接收变成 owner 退出或业务合格。
6. 新 Witness-v2 必须由生产端明确区分 observation complete、首次 Accepted 的 BusinessReady、normal contract；检查器完整关联 Source tick/submit/registration/activation/phase，不采用事后固定 30/21/20 人口。正常全拒绝可以观察完整，但 BusinessReady 与 normal 仍为 false。
7. CLOCK_MONOTONIC entry、认证 guard、CDR 生成、语义 callback 完成、最终 Ready 和 activation 是不同点；录包时间/RMW时间不能作主时钟替代。晚于150ms的最终注册必须拒绝，Source输出不能继承提前的认证/序列化时间。

独立 checker 将在新 N14 文件中创建，复用已冻结原 helper 的 typed Storage/transport/Publisher receipts 算法，但旧 Witness-v1 与旧失败不修改。资格标记保持 false；真实4s、native正负例与研究结论分别记账。
