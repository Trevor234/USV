# 下一批最小计划：先V1当前版本首次日志入队失败

1. 使用本批candidate_version_v1.json中的准确新Observer ELF/source bundle，复用原四个其余角色的精确版本。生成新run的peer、owned配置/端点及Source/Storage身份；旧Observer manifest不可重命名移用。先只读核验新ELF与现有prepare/checker接口，必要时最小派生绑定，不改默认install。
2. 审查当前Sink的原有有界暂停/容量/首次失败机制，选一个真实DecisionEnqueue失败触发点，写定Source/Witness/应用分账、退出和同一次stopping/失效判据。若现有机制无法命中，先补最小注入/入口组件，不把模拟receipt当实际Sink入队失败。
3. 保持diag10原数值、150ms绝对deadline和200ms tick，execute继续关闭。新批事前Go后只做必要V1一个有界实际run；每run≤30s，受影响日志≤100MiB；若完整准备链超过预算，先报告并独立修订预算，不能悄悄延长。
4. 原正常/激活组件未改的不重复全套；当前14组/117断言作为本组件前提保留。新实际故障未闭合就不授予正式阶段资格。失败留原证据，先具体分析，不用更多同类正常run稀释。
5. V2分别设计native阻塞/active watchdog与能力回调receipt租约失效，不能假定两线程阻塞都会发生；V3核验来源/时钟/历史重验交错。全部针对同一选定版本，再B5/M0b→M4→模型事务/F6→P1复判→P2。

本批到组件交付即停止，不启动V1～V3或M4。MPC只写新批目录，旧封存历史与失败保持。
