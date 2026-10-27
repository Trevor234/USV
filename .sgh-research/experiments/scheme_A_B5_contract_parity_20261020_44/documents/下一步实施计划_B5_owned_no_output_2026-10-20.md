# 方案A：下一步实施计划（B5 owned no_output）

2026-10-20，承接第44批。

当前配置漂移已在新候选实现中修复：当前81/diag10与formal84共用Native原有的精确规范hash。385条对拍、102条准备门组件、25条真实文件入口检查通过；尚无新owned ROS角色运行。旧诊断Driver未就地替换。

## 实施顺序

1. 新增owned正式准备角色和Driver，使用第44批配置loader/Native gate。真实构造函数先核验formal84/fault=false/no_output；创建并认证本进程实际端点和只读参数清单；所有就绪Context来自实际owned身份与回执，禁止从seeded测试复制。旧shadow入口保持封存。
2. 新增只发送声明的clock/odom/IMU/path/profile的合成Fixture。当前Fixture19的名义推进依赖真实legacy Applied，不能直接改名复用。新的有限准备源可采用stationary_zero_equilibrium；不伪造Applied或控制锚点，不声称已经验证名义闭环。Worker35、RecorderC3.4能否复用以实际formal冷启动、参数、GID、回执及关闭验证为准。
3. 仅编译有变更的必要角色，做构造函数与适配层反例；绑定source bundle、编译依赖、实际ELF及已实现差集。随后为新run、新输出目录和已确认隔离的DDS域写具体预注册文件。本计划本身不授权跳过实现源锁直接运行。
4. 执行一轮有限owned no_output准备/关闭：四角色同run/boot/contract/spec；真实输入/参考对/Capability/Recorder就绪后，真实Driver发一次准备请求。证明SolveJob、Decision、Applied与物理Writer/调用均0，所有Source/bag关闭，owned进程组清空。旧授权、错身份、过期、重放须拒绝；保留失败。102条组件通过不能抵消实际运行失败。
5. 审核准备入口与完整Regulator no_output执行语义的差集。当前candidate保留controlled-phase/task-time等策略，准备且零作业不会验证这些策略；真正完整无输出执行需明确自己的源/参考/锚点语义及实证。B5冻结证据必须引用真实产物、明确域和政策；禁止填64hex占位、删除pending或翻execute标志伪造资格。
6. 合适的B5/M0b冻结后，依次M4唯一真实Regulator输出、有限已知模型事务/F6、原始P1联合验收。M4仍需逐侧成功锚点、部分发布、hold/ramp/5misses、关闭、全命令流gap（含启动）、时间/API和原资格回归；已知模型事务仍需真正数值模型切换、模型/计划原子提交、旧候选拒绝与不可变已保存计划。GP/PPO与完整碰撞证书属于后续P2，不增加为当前P1前置要求。

## 停止条件与复验范围

若源码参数/profile/spec再漂移、formal配置被旧shadow guard拒绝、Fixture仍要求legacy Applied、就绪来自未认证布尔量、出现任何输出/作业、或者关闭不完整，则停止并保存本次证据。先改动造成的具体差集，再重跑相关项；不全面重复39–42，也不继续first-control/RTI/权重调参。

机器可读任务边界及验收见`implementation/owned_no_output_integration_plan_v1.json`。这些是现有B5最小计划的实现差集，不是额外引入P1性能验收标准。
