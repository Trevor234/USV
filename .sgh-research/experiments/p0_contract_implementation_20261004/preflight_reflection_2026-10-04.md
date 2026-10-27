# USV P0 实施前核对与实验门禁

日期：2026-10-04。采用 control-preflight-reflect 的事实、假设、候选方案和 GO/NO-GO 流程；EDA 专用 DEF、WNS、布线约束不适用于 ROS/VRX。

事实：Ubuntu 当前 HEAD 为 1e5becae622782526f20fc93928339133c94ec23，branch codex/scheme-c-rl，有三次修复及用户未提交产物。最终修复文件与既有验收哈希一致。现场进程清单没有正在运行的 NMPC/Gazebo。F1_20261004_three_repairs_original_01 已冻结，122 项源码/配置、53 项安装文件、5 项模型资产，完整性报告通过。源码、模型及恢复副本留在 Ubuntu。静态基线不能证明运行有效参数，manifest runtime_effective_verified=false；pilot 另存实际参数及 graph。

关键假设：原 B 仍是两路物理发布者；Ground truth odom twist 已在 body frame，不能再次旋转。后者通过生成 SDF 的 dimensions=3、map/wamv/base_link，Gazebo 8 OdometryPublisher RotateVectorReverse 及 Jazzy bridge 逐字段复制核对，仍须对本次生成文件和实际 frame 复核。同步 solve 不具备独立监管接管，250/400ms 只验证阻塞和返回后拒绝。

风险排序：1. 首尾记录缺失可能让连续序号假完整；2. IMU/odom 异步组合被错误当成同源快照；3. shutdown 后 publish 静默返回可能制造 emitted 假证据；4. 队列延迟/溢出污染对拍；5. 两路 Float64 没有物理原子性。

方案 A（采用）：版本化三类消息、有界异步研究发布队列、源端完整计数、实际 graph 就绪后 arm、有效 ROS context 中 pre_shutdown 刷新、严格 bag 只读检查，F1/F2 独立。

方案 B：若日志开销超过周期，先优化观测队列/序列化并新建 run；不放宽求解预算。

方案 C：若 frame、overlay、来源计数或关机不能证明，保留失败 bag/报告，停止数据准入，修复后使用新的 run_id。

GO：F1 已通过，允许构建和合同测试。仿真 GO 条件为构建及必要回归通过，保护资产哈希不变、场景无障碍、domain/partition 隔离、参考冻结、运行参数与 graph 就绪核验。未具备条件时 NO-GO。即使三类 pilot 通过，plant 接受、物理力、执行原子性、精确残差和 GP 数据准入均保持 false。
