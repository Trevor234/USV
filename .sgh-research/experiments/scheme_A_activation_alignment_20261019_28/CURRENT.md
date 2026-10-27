# 方案A第28批当前状态（2026-10-19）

因果状态选择及最多一次重验已实现并完成唯一一次原首档。**首0.5 N已接受、由唯一Publisher双通道发布并成功记录StoredApplied；实验整体仍NoGo。** 90/100接受、最长连续18；全窗RMSE0.01047524499，原门0.007392495755未通过。五角色正常退出并清理。

本次没有负时间区间/因果状态选择拒绝；完整Source中25次选择较早Odom，最多扫描3条。测量窗41次重验，救回31次；剩余10次均为第一轮IMU变化、第二轮Odom变化。原保护保留。新增快照JSON构造位于验证窗口，需优先移出；该实现开销不能用增加重试或放宽门掩盖。

组件：Worker 9 GTest+103纯检查，Observer 39 GTest+346纯检查，Python76项；诊断修订10，原模型/代价/参考/时间及性能门保持。冻结检查器还有一处父合同SHA常量漏同步；只读复盘确认实际合同正是预注册修订10，原失败不改判，下一版补事前身份消费点负例。

325个作者及原始运行文件已快照。原未提交改动、历史资产、首次编辑断言、两次初始构建失败和本次完整NoGo证据均保留。MPC仍Errno112，本地保存，第24–28批交付待办保留。阶段、execute、实艇与研究优越性资格均false。

见[结果与复盘](/home/trevor/USV/.sgh-research/experiments/scheme_A_activation_alignment_20261019_28/documents/方案A_激活时刻对齐_实际结果与拒绝复盘_2026-10-19.md)、[下一最小计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_activation_alignment_20261019_28/documents/next_deferred_observation_plan_v1.md)。下一步先移出新增诊断JSON并做有限交错验证，再一次原首档；若同机制仍失败先审查原子提交，若仅性能失败则停止首控调试支线、审查目标可达性与研究相关性。
