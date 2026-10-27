# 方案A第19批预注册推进计划

日期2026-10-16。父批第18批A22/A2-20/B-19+1/C21实际组件通过，C357条模型状态独立重算一致；阶段/执行/研究结论未授予。本批承接其下一优先级，所有旧资产只读。

## 风险排序与选择

1. 高信度：旧NominalHistory每sensor从起点全重算，时长增加会放大开销；仅把4秒改20秒不足以证明Clock/状态新鲜。改为增量checkpoint，晚到实际Applied仍必须回放修正未来state，所有已发记录保留。
2. 高信度：旧61点低速路径只覆盖12秒参考时间，不适合20秒+4秒预测窗。固定201点，dt0.2，按显式参考速度构造40秒长路径；不能随odom平移触发task变更。
3. 中信度：0.05m/s有限4秒成功不保证高速长时稳定、截止和rate合格。逐级隔离运行，不抬状态/锚点/rate门，不补外围负例来替代首个失败门。

## 固定顺序与通过条件

0. 保留原25处业务改动（24旧摘要+独立real.launch增量）、旧失败/快照、父批2503文件MPC交付，核验当前boot与新端点身份，不沿用旧PID权限。
1. 新Fixture原生测试：长时、不对称推力、晚到事件、与旧全重放独立oracle一致；Source记录工作步数/回退/预算，常规每次只推进新增区间。模型合同19个hydro参数与SHA完全一致；原40秒/20000步/1024事件容量保留，并声明单query硬工作上限512步。
2. 先0.05m/s测量20秒；通过后0.1、0.3、0.6依次每级20秒。每级不少于90次连续候选激活接受；测量期所有实际候选激活必须接受、无skipped tick、无readiness invalidation；首末接受覆盖至少18秒。
3. 全population Source/Storage/Witness/实际Float64/phase发送因果/actualApplied接收前缀/真实传感器与独立Fossen RK4一致，仍沿用1e-9数值核对阈值；不得改用Source自报state作为重算起点。完整当前端点、typed live参数、SourceFD、关闭/回收必须通过。
4. Driver prepare25秒、measurement20秒、close15秒、overall90秒；独立offline checker可300秒，不能扩大原150ms ready或200ms target。运行输出仍<=128MiB；horizon20/dt0.2/状态容差/rho/hold与contract全部保持。

## Go / No-go

当前Go仅授权新Fixture/检查器实现、构建与纯组件验证。实际DDS运行在保护、source/binary pins、原生测试、完整preregister后Go；下一速度仅在上一速度完整通过后Go。任一首门失败立即保留原run与来源，定位原因，修订须新版本/快照，不放宽判据。

## 证据边界

本批仍为隔离localhost DDS、shadow Observer、唯一诊断owner和标称模型。20秒长窗组件通过不自动授予dynamic20sR5/B4/M0b/B5/M4/F6/P1、正式执行或真实Plant资格；不作性能优越性或真实模型精度结论。
