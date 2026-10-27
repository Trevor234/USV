# B5 compatibility batch44 preflight

2026-10-20。沿用 control-preflight-reflect、control-theory-veto、control-postrun-retro。研究/比较范围限定于配置与无输出准备入口；不作轨迹性能结论。

根因排序：1. 当前 Native81/diag10 与旧 Python74/diag5 的规范来源发生漂移，且 profile/spec hash 不一致。2. 现有 owned Observer 在解析契约前仅允许 shadow；formal v3 pre-freeze 仅允许 no_output，二者没有合法交集。3. 当前 business gate 依赖 fault=true 与真实 legacy Applied，不能直接用于 fault=false 的正式准备入口。

A（选定）：捕获当前已审查81字段、39整数键、19 hydro 和精确 profile，为 Python/C++ 生成同源产物；用独立期望的原始字节/类型/资源/模式矩阵对拍，再实现隔离的 no_output 准备权限核心，预注册真正 owned 准备/关闭运行的差集。B：直接放宽旧 Observer shadow gate，会混入 legacy 控制锚点，拒绝。C：重写正式 schema，已有 v3 足够，拒绝。

验收：保留81字段原值，正式84字段；固定范围及原模式矩阵保持；旧74拒绝和全部旧失败保留。新 native 与 Python 对每条 corpus 独立期望一致，Frozen形状不解锁 execute。 no_output 准备必须 fault=false、execute=false，不生成物理 Writer 或伪造 Applied；ready/driver 身份、run/boot/hash/TTL、终态重放拒绝。先保护核验，编译最多三次，每次独立目录，单次180秒，测试单次60秒；全部日志保存。任何分歧先保存失败再修复。

GO：只限小型 validator 和无输出权限/准备组件编译验证。新 ROS 运行须在实现锁定后另写确切准入文件；没有该文件不启动。B5正式冻结/M0b/M4/P1资格仍未授予。WNS/TNS/PPA/DEF 是EDA指标，本USV批次不适用；此处用字段/字节/模式/身份/资源边界证据。
