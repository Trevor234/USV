# 投影参考策略闭环验证预案 v1

日期2026-10-16。前置实际证据：414个Job被历史固化reference archive逐double重建；当前可读p1_input_core.cpp重编object与该archive member逐字节一致。actual acados按104个完整warm前缀重放首控/X/U最大差均0；只改单Job reference.x起点平移约-37.459mm，首控约.228113→.053340N，前103个完全相同。固定state/ref_speed.1对照显示原lead在u.1引发正加速，去lead在u.125引发减速。不将这些Native结果当闭环性能证明。

## 唯一拟改变的语义

profile_time参考原点由“预测target_state最近离散点+max(1,offset2)”改为“预测target_state在path最近segment的连续投影对应profile_time”，不附加carrot。每列仍在t0+k*dt采样相同profileu/r和几何，保留heading展开。无效profile/stamp/退化混合/未来覆盖不足显式拒绝，不静默回退。

新合同projected_contract_v1.json SHA45bc25fc471dfba9ac757ee0727770e0d447bce63cb2fca5ffba8cc12ad17d20：reference_start_offset2→0，新增reference_sampling_policy=projected_profile_time_v1，diagnosticrev5→6。Worker/Observer严格共同支持，effective Source与规范SHA绑定；输入owner基线身份保持原controlledPhase，Publisher/Fixture代码仍冻结复用。Q/R/Rd/Qf/hydro/N/dt/约束/150ms ready/200ms target/所有接纳守卫全部相同。

## 固定顺序/通过条件

构建/原生投影边界测试/新合同类型与字段拒绝测试/来源pin+静态库链接pin通过、source配置/有效参数来源认证后，才Go实际DDS。

按.05→.1→.3→.6m/s每级20秒；每级保持父批>=90连续合法激活、测量期所有候选都接受、首末覆盖>=18秒、无跳拍/Ready失效、完整Source/Storage/Witness/phase实际因果/actualApplied驱动模型核对、全部正常回收。

预先新增性能指标（只针对此直线标称组件）：最后5秒平均surge相对profile误差<=5%；整测量窗surge RMSE不超过父批对应固定观测值的50%（.05:.014784991510502932，.1:.029260913386751467，.3:.08808870950703403，.6:.15508263209306208，各再乘.5）。完整记录启动/关闭，不用关闭后的速度代表稳态。模型数值独立核对仍1e-9，不抬。

任一门失败保留原run与首门，下一速度NoGo；修复须新版本，不改已预注册门槛。不会为达到指标调权重或容差。

## 证据边界

actual warm-prefix只覆盖所选实际cohort；未夸称全部历史静态archive源都曾登记。新策略通过也只是单次直线标称诊断性能改善，不授予dynamic20sR5/B4/M0b/B5/M4/F6/P1、正式execution、真实Plant或研究优越性结论。弯道/离路径/噪声/延迟校准仍另有资格要求。
