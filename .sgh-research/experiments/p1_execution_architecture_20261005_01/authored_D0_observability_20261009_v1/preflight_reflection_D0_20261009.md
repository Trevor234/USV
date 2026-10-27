# D0 隔离观察版：运行前反思

2026-10-09。沿用 control-preflight-reflect 的事实、假设、A/B/C和Go/No-Go流程；其原EDA指标与本ROS实验无关，不移植为验收事实。

## 已锁定事实

当前诊断src SHA a38d563a52570f11da9e68b5743c6c1989b26e77508620358ad3e402bd0a8a3b；普通src 7abfaf03722499bbe9d28da19d050404667682ff3918813d2133b98dadfd8477。既有3067资产守卫SHA f3e10a0f5ee97381094c39978794f1ceac2f5d12732d1028899dc7c8b4a63146。worker/diag5/publisher nominal保持既有身份，实际主机/守卫/新目录空缺由live_preflight.json确认，不依据缓存假定。

旧B4全160状态对可作数学差值观察；158拒绝不能认证原validation来源。原tick-start `now`采于mutex前。原state_check首次超限即返回，原partial errors不能自动认作完整观察。诊断constructor硬门no_output+diag5；本轮不得F5 shadow。

## 根因与假设（按优先级）

1. 来源缺字段：在同Decision记录原`s`及final raw来源，能对每次传播绑定真实验证输入，不能回填旧记录。
2. 可用性混淆：predict布尔结果、finite availability和null能区分失败/无候选初始化零；独立full6差值不受原早退影响。
3. 版本与时间适用不足：增加序列化负载会影响时间；静止no_output只能验证机制，不能证明动态域、真实20ms界或继承旧版本压力资格。

## A/B/C 与验收

- A（本轮选择）：创建only-new authored_D0_observability_20261009_v1，native编译；8个针对来源/null/wrap/overflow/原早退/同事件projection例及10个受影响enqueue回归必须全运行通过。独立源码审查无未处理阻断；新strict checker恶意/缺失输入测试全通过。随后仅一次10s、原50Hz静止fixture、native acados、no_output控制。55旧严格工具字节不变，源/实际bag/Witness/owned账本和新观察全过门；时间窗用actualmonotonic，owned准备收尾分列；零物理出口、历史守卫不漂移、owned清理完整。
- B：任何字段/对账/清理失败，保留失败证据，只修明确机制，不重复运行凑样本。
- C：D1 shadow延期。≤1.2原域和20ms工程门保持pending；工况正文及shadow入口契约未闭合时不launch。

Go：允许上述隔离编译/针对测试。单次ROS Go依live守卫/host、全部相关测试、独立源码review及事前policy pins闭合；任何失败No-Go。全程不安装，不覆盖普通/default工作空间，不改变formal ROS/Witness/合同/控制公式。RK4提供重算所需有界输入记录，但本轮checker只认证来源/状态绑定与差值数学，未独立认证nominal RHS，报告明确此限。

停止条件：一次normal回答字段机制后停止。B4/M0b/B5/M4/F6/P1/execute全部保持未闭合。
