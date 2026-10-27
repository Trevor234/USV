# 第20批参考速度偏差审计预检与最小实验计划

日期2026-10-16。父批四档20秒408/408合法接受，但末5秒surge高于profile约22%–25%。本批只解释并隔离参考构造因素，保持Q/R/Rd/Qf/hydro/N/dt/constraints及接纳守卫不变，保留旧数据/失败与未提交改动。

## 当前证据与假设排序

1. 实际Job所有reference相邻位置差/dt等于profileu，误差仅浮点量级，不支持简单“0.2变0.25”的倍率猜测。
2. Observer先从输入state传播到target_state，再按该target_state选nearest+max(1,offset2)。profile_time起点因此在预测目标位置前再加约0.30–0.49秒路程；当前首要假设是这段不断移动的空间carrot造成跟踪速度偏高。
3. 不能把fresh solver与实际warm Job直接比较。acados SQP_RTI具有热启动状态，baseline必须按原Worker全部solve前缀重放，再验证firstcontrol与已存candidate一致。
4. 历史编译来源边界必须精确：实际static libmpc_core_lib.a有旧flat roster原始SHA pin；当前cpp/o未发现对应历史独立原pin。新增probe会固定当前捕获时刻、实际archive黑盒行为和真实Jobs，不能以新源hash冒充过去源码证明。

## 固定顺序

A. 旧资产/工作区保护；实际reference builder archive/ELF/link/headers/source当前捕获；逐真实Job核验ReferenceMetadata、target/frozen位置、profileu与位置导数。
B. 相同实际acados安装后端、完整实际前缀baseline精确重放；只在选中Job平移整个reference.x使ref0.x=target_state.x，不改速度或空间增量，比较firstcontrol/预测与加速度。另用解析平衡阻力输入在u=.1和.125固定state验证原/去lead参考的加速或减速方向。
C. 仅在A/B因果证据成立后，提出明确版本的投影式profile_time参考原点候选及测试，实际配置必须与实现一致。若需合同扩展，严格新schema/字段/版本/hash和Source，不能悄然忽略原offset2。当前不改正式工作区业务源，不直接调整Q/R或容差。

## Go / No-go

当前Go为新scope实现、只读分析、真实静态库probe与无ROS求解前缀重放（无codegen/install）。实际DDS/闭环修复在来源、baseline重放、单因素方向判据与新配置认证完成后才Go；未达条件则保留失败并定位首门，不强行发布“修复成功”。

## 分层结果

固定Job/原生后端/诊断闭环均只组件证据。父批接受率与数值一致性不能替代本批速度性能门槛。阶段、正式执行、真实Plant与研究优越性结论仍未授予。
