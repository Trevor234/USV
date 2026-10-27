# D0来源机制实验复盘

2026-10-09。依据run.summary.md、run.manifest.tsv、evidence_analysis.json、完整原source/actual-bag严格报告和owned账本；采用control-postrun-retro的事实/机制/下一步/停止条件结构，EDA的WNS/PPA指标在此无适用含义。

## 结果与假设

H1：原validation快照与final来源缺乏区分。新同DecisionJSON记录实际s，原来源零投影与raw内部IMU分开；18针对测试和一次normal字段门支持机制假设。没有补造旧158拒绝的来源。

H2：原早退partial errors和无job初始化零可能被误当完整样本。新explicit predict/finite/available与null、独立full6 wrap，针对恶意输入、首维超限、失败、非有限和缺失样例全过；真实normal仅50成功零误差+2未尝试，其他边界由测试支撑，不能写成真实ROS边界覆盖。

H3：静止机制通过即足以冻结动态域或20ms真值。证据不足，假设不成立：速度0/history0/1mixed标签不足；no_output入口不支持D1 shadow。保留原≤1.2待冻结、20ms待论证工程门；未独立重算RK4 RHS，尚无plant残差/GP标签。

主要剩余机制insufficient_evidence；次要flow_policy_mismatch为D1所需shadow与专用no_output门差异。没有观察到logger drop/owned泄漏/旧资产漂移，不将它們写成已发生故障。

## 下一选择和成本

选A：只读恢复既有工况正文并审查shadow入口差异。对定位当前缺口confidence高、impact中、cost低至中、risk低，符合先证据再有限执行。

选B：若正文/域内可复现条件足够，单独创建隔离shadow观察入口并作针对验证。confidence中、impact高、cost中、risk需模式/owner/0fault门闭合；本轮不自动执行或移植旧资格。

不选C：重复static/no_output或修改slack/扩大1.3凑覆盖。对动态来源缺口没有相应新增机制依据，无法提高结论强度。

## 停止条件

本轮已完成一次声明normal并停止，未递归launch第二场。下一轮只读阶段回答正文/域内条件/入口差异即可结束；不能满足则输出具体No-Go，不无限检索或重复采样。D1需独立事前policy且仅一次20s测量窗；新具体失败机制才触发下一有限修订。历史B4和本轮源/错误/拒绝/未消费job全部保留。
