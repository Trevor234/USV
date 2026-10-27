# 第47批执行前反思与有限计划

承接46已关闭的连续正常来源组件、45正式prepare组件、43八组政策审查与原M0b条文。本批沿用control-preflight-reflect / control-theory-veto流程。EDA route/STA/WNS/PPA等不适用，无新算法比较。

根因排序：1. 正式v3目前仍绑定diagnostic profile/legacy owner，不能冒充own-output入口。2. 当前legacy startup真实API gap约1.54s不满足240ms，M4需事先固定启动保持规则。3. 只有候选台账，没有真实不可变索引；64hex形状不足以认证。

A（选择）：派生同源双profile validator，保留旧81/v3，正式目标84只改变来源/owner/启动政策等明确字符串；实现纯入口政策状态核、严格冻结绑定校验，原数值/模型不变。有限编译与确定性正反例后，满足原M0b才提交工程冻结。物理release始终false。
B：再跑20s正常来源。已有组件证据，无新差集，拒绝重复。
C：直接启用实际execute。所有权和M4真实路径未实现，不提交该动作。

验收：精确字段diff与模式矩阵；旧385原始语料回归；新profile及重复键/类型/超界/旧profile混合等反例；逐侧unknown→真实API成功、启动cadence、HOLD/ramp、partial/shutdown纯组件边界；冻结索引真实字节/SHA与合同模板无环绑定，篡改实际包必须拒绝；源/二进制/工具/证据索引及预声明故障矩阵完整。全部失败独立保存。阶段结论独立于组件通过，M4/F6/P1/plant均不升级。

预算：本批无ROS/plant/故障刺激/代码生成，无参数调优。C++纯组件单次编译180s、最多2次修复，测试单组120s。新旧资产前后全字节核验。仅在本批目录写入；MPC交付需受控写权限。

理论裁决 GO（限定离线实现与M0b工程冻结）。blocking_reasons: []。假设：trusted prepared graph、近1:1工程外推、19参数RK4名义点模型、本地有限调度，沿43/46原适用范围；均不是plant误差界、WCET或全局连续排他证明。重复经验风险：startup整流gap必须保留；不新增完整no_output门；不以未来execute当M0b前置。safe_next_step：固定profile和逐侧bootstrap可校验规则。override_policy：若后续发现NO-GO，不执行受阻动作，保留证据并继续无依赖离线工作。
