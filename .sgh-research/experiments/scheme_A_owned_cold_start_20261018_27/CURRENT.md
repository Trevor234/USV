# 方案A第27批当前状态（2026-10-18）

owned Worker 因果冷启动集成及有限组件验证完成；原 0.05 m/s、20 s 五角色 localhost 实验已执行，**NoGo**。首 Job 实际求解四次，生成 `[0.5,0.5]` N，但激活时拒绝，未通过 Applied 链路施加。测量窗 90/100 次接受，最长连续 19 次，全窗 RMSE 0.0110037220 m/s，原门 0.0073924958 m/s 未通过。五角色均正常退出并清理。

拒绝已逐条分类：7 次最新 Odom 略晚于冻结目标，3 次验证期间输入变化。另有一次合法缺侧参考启动重试被原检查器判为记录域失败；原报告保留，不能改变整体 NoGo。

原生组件：Worker 9 GTest + 94 项纯检查，Observer 19 GTest + 337 项纯检查，Python 64 项通过。诊断修订 9；模型、目标函数、150 ms/200 ms 与原全部性能门保持。本批没有方案A阶段资格、execute 资格或研究性能结论。

见[结果与拒绝复盘](/home/trevor/USV/.sgh-research/experiments/scheme_A_owned_cold_start_20261018_27/documents/方案A_owned冷启动集成_结果与拒绝复盘_2026-10-18.md)及[下一步最小计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_owned_cold_start_20261018_27/documents/next_activation_alignment_plan_v1.md)。固定顺序：先离线因果状态选择审查，再独立新修订的有界状态历史与最多一次原子重验，最后同门槛首档一次。

315 个作者/运行文件已快照；历史本地 35,912 条路径、4,152,821,165 字节末次复核通过。原 24 个业务未提交改动、已声明 real.launch.py 差异、冻结资产和所有失败均保留。MPC 宿主访问仍为 Errno 112，当前本地保存，第24–27批共享盘交付及历史远端镜像复核待办保留；仅成功的 delivery_verification.json 可证明交付。
