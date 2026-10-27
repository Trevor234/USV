# P0 发布端数据契约 v1

实施日期：2026-10-04。ROS2 Jazzy，动态 NMPC `scheme=B`。三个消息的共同身份为 `schema_version=p0-contract-v1`、run_id、producer_instance_id、baseline_id、config_hash、sequence、clock_epoch、steady_clock_domain。

`StateSnapshot` 六维 `[x,y,psi,u,v,r]` 完全来自同一条 ground-truth odom。保留原采样戳、接收序号、接收/冻结steady、pose/child frame、显式clock值/年龄及valid/quality_reason。已在body frame的twist不再旋转。NaN/Inf、全零四元数、frame未知等会使快照无效；原消息另留bag。无效数值的有限占位必须连同valid=false解释，不能当训练值。

`CycleTiming` 单独保存求解前实际controller_state_6。原控制器可由IMU覆盖r，后到odom又覆盖r；state_kind据实际最近写入来源为controller_mixed或odom_atomic。accepted odom/IMU接收身份和原戳与冻结值一起保存，求解期间的新回调不能改写该记录。无solve的STANDBY周期标solve_invoked=false，其solve字段为0。计时为本机可观察回调/参考/solve/发布调用链，不能称传感器到执行器完整端到端。

`AppliedControl` 的event_semantics固定为publisher_command。每次记录窗口内发布尝试都有新sequence，相同N值也不合并。记录请求、映射/限幅后最终左右N、control_source、cycle关联、前次观察锚点、两路调用起止及各自clock epoch/age。左成功右失败形成partial事件，保留异常，不伪造联合成功。关机记录真实零推力尝试。

运行窗口：研究记录默认关闭；启用时先建立publisher/显式clock订阅，armed仍false。只有实际graph、录包订阅、有效参数及frame核验通过，runner才设置research_logging_armed=true；下一控制回调开始源端计数。原bag保留arm前原始数据，但完整性声明针对明示的源端记录窗口，不声称覆盖节点启动至arm之前的过程。关闭研究记录时保留原控制分支。

观测消息经容量1024的有界队列由独立线程发布；控制回调不写磁盘。溢出仍增加生成序号并统计dropped，不能悄悄跳过。有效context中的pre_shutdown完成真实零输出和队列刷新，再关闭ROS上下文；未完成同步solve被shutdown中断时，interrupted_cycle_sequence/started计数使正常完整结论失败。session_summary记录生成/发出/丢弃/首末、开始/结束、normal_end和flushed；bag实扫计数由独立checker对照。

新研究recorder采用默认system receive记录时间域。DDS接收时间唯一匹配窗为20ms；它用于同一bag时间域的两路Float64与研究发布事件配对。显式消息clock才用于仿真物理时间区间，steady仅用于同boot计算耗时，三者不混算。该匹配给出发布端数据一致性，不给出Gazebo接受时刻。

离线区间只连接同run/producer/clock epoch且连续sequence、双路publish成功的相邻事件。左右边界分别保留，暂停不造正物理Δt；重启/失败/跨epoch不跨接，最后一段end_unknown。幅值/变化率诊断按实际观测间隔报告，不改变HOLD原分支。

Gazebo生成模型使用OdometryPublisher dimensions=3，odom_frame=map、robot_base_frame=wamv/base_link。Gazebo 8源码通过RotateVectorReverse产生body twist；Jazzy bridge复制twist与frame；运行graph和生成SDF逐run核对。其twist实现还存在滚动平均，不能将它无条件等同瞬时速度。[Gazebo 8源代码](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/odometry_publisher/OdometryPublisher.cc)、[Jazzy bridge](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/src/convert/nav_msgs.cpp)

原quaternion_to_yaw对全零四元数计算atan2(0,1)=0；原odom控制入口注释称退化处理，但当前函数不会据此拒绝全零值。本工作包不改变原控制消费行为，新快照明确invalid并由checker拒绝。控制入口补齐退化四元数门禁是后续明确修复项；当前pilot实际四元数需有效，不据日志改造宣称原入口已修复。

始终保留plant_acceptance_observed=false、force_measured=false、execution_atomicity_proven=false、exact_execution_timing_available=false、gp_labels_ready=false。本工作包允许继续P1执行监管，未完成Python/C++模型对拍、controller/plant解耦、训练历史动作时序或GP数据准入。
