# 第45批：owned正式无输出准备

复用control-preflight-reflect/control-theory-veto/control-postrun-retro；EDA专属WNS/PPA/DEF不适用。

根因前三：1.44批只有纯权限Context，缺实际端点/进程/配置/Recorder回执；2.旧Fixture依赖Publisher/Applied，需要独立无legacy源；3.Worker35冷启动有实际candidate与3个capability Reader要求，新图必须真实满足。

A选定：新preparer(p1_regulator)+stationary Fixture(p1_synthetic_source)+原Worker35+原Recorder四角色。Preparer零Writer，仅读取五输入、Capability、Candidate；Fixture五输入Writer和Capability Reader；Recorder七Reader。Native实际构造使用44规范及门核心，物理执行关闭。B放宽旧shadow guard或Worker准备校验拒绝；C伪造Applied/ready布尔量拒绝。

验收：先保护，源锁/构造反例后预注册一轮独立DDS域准备/关闭；四角色真实有效配置、manifest/proc/GID、真实源及租约、真实一次授权、零Job/Decision/Applied/thrust Writer/call、Source/bag关闭与组空。预注册前不运行ROS。每次编译180s最多两次修复；单次运行最多35s，关闭总预算10s，保留全部失败。复用385+102+25已证组件，只验证新差集。准备only不授予B5/M0b/M4/P1资格或模型/轨迹结论。
