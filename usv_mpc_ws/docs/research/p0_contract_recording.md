# P0 动态 B 发布端记录入口

此入口包裹原 `vrx.launch.py`，固定 `scheme=B`、启用控制，关闭原 recorder，另启一个 MCAP recorder。研究记录默认未 armed；ROS graph 门禁通过后由运行器显式 armed。原默认 launch 和方案 C 的 PPO 检查入口仍按各自合同运行。

新入口为 `ros2 launch usv_bringup p0_contract_recording.launch.py`。它要求显式传入唯一 `research_run_id`、预先分配且在验收前完成冻结与核对的 `research_baseline_id`、配置输入清单 SHA256 `research_config_hash`、已冻结 `waypoints_file`、未存在的 `bag_path` 和 `research_output_dir`。两个输出目录应分别保存原始 bag 和源摘要，不能互相包含。入口只检查路径并拒绝覆盖；研究目录由节点创建，bag 目录由 recorder 创建。

坐标参数为 `research_expected_pose_frame`、`research_expected_child_frame` 和布尔值 `research_frame_contract_verified`。最后一个参数默认 false。实际 odom 中出现某个 frame 字符串，只能证明收到的名称，不能证明 twist 已在船体坐标系；运行器必须根据已核验的 VRX 模型/桥接配置声明坐标合同。状态单位固定 `[m,m,rad,m/s,m/s,rad/s]`，发布命令单位为 N。原 v5 ONNX 输出已经是 N，此入口不做 PPO 缩放或训练。

最低话题清单见 `usv_bringup/config/research_bag_topics.yaml`，共 12 条：odom、IMU、clock、path、profile、左右推力、status、predicted trajectory 和三个研究消息。profile 实际类型为 `std_msgs/msg/Float64MultiArray`，status 为 `std_msgs/msg/String`。话题重映射必须同步记录到运行上下文。recorder 使用默认 system receive 记录时间，不启用 `--use-sim-time`。联合发布事件与左右原始推力消息在同一 bag 接收时钟中按预先固定的 20 ms 窗口唯一匹配；显式 `/clock` 用于发布区间的仿真时刻，节点 steady clock 用于计算和发布调用耗时。三者分别保存，不能互相替代。低实时率仿真下，同一个仿真时间窗可能覆盖多次墙钟发布，因此不能把 system receive 的 20 ms 门槛直接用于仿真时间。

一次正常 pilot 按以下顺序执行：

1. 在隔离的 `ROS_DOMAIN_ID` 与 `GZ_PARTITION` 下加载 Jazzy、VRX 和 USV overlay，绑定 F1/当前源码与安装 hash、参考 hash、配置输入 hash；为本次运行新建实验目录。
2. 启动研究入口，保持 `research_logging_armed=false`。9 秒控制节点启动延时只是原启动顺序，不代替 recorder 就绪证明。
3. 在同一 domain 运行 `capture_p0_runtime_context.py --output <实验目录>/topic_graph.json --bag-path <原始bag目录> --run-id <run_id> --baseline-id <baseline_id>`。它等待实际 graph 中每个必录话题恰有一个 recorder 订阅；研究消息及左右物理推力各有唯一原 B 发布者；同时观察 odom 和 clock。返回非零时保留失败上下文，不 armed 后继续冒充成功。
4. 核对 topic/type/QoS、实际参数 dump 与源/安装/基线关系，然后执行 `ros2 param set /mpc_controller_node research_logging_armed true`。记录 arm 请求结果及源摘要开始时刻；按实际计数验收，不用 graph 发现代替 bag 完整性。
5. 记录约 60 秒墙钟。报告实际仿真覆盖和墙钟覆盖，保留 clock 停顿、同步 solve 长保持及记录开销。
6. 在 recorder 仍运行时正常结束源记录，并等待节点有界队列排空及 `session_summary.json`。节点停止和 logger 排空必须按实现的有效 rclcpp context 顺序执行；向整个 launch 同时发 Ctrl-C 不足以证明尾部已录全。
7. 源摘要正常结束后再停止 recorder，等待 MCAP/metadata 刷新。若源异常结束、队列溢出或尾部缺失，保留原 bag 并按失败/未知结论报告。
8. 在 bag 外运行只读 `check_p0_contract.py`，核对实扫计数、metadata、源摘要首尾/计数、时间和身份；生成合同报告、发布区间账本和时延报告。最后一段缺少下一事件时标 `end_unknown`。

`capture_p0_runtime_context.py` 只订阅观测、查询 graph/实际参数，不发布推力，不改变控制参数，不修改 bag。它将实际发布者和订阅者的 GID、QoS、原始 odom frame/四元数/twist 样本、显式 clock、boot_id、domain/partition、包前缀与实际 MPC 参数 dump 写到新报告。参数查询使用 `ros2 param dump --no-daemon --spin-time 2 --timeout 8 /mpc_controller_node`，同时接受 Jazzy dump 的全限定节点名；查询失败应保留上下文并停止 arm。启动前 armed=false 参数快照与后续 arm 请求、源窗口摘要共同构成时间顺序证据。它的 `recorder_graph_ready=true` 只表示启动门禁具备图证据；最终录制完整性由源摘要与 bag 实扫对照确认。

三条研究话题的 `AppliedControl` 语义为 `publisher_command`。publish 调用成功不能证明 Gazebo 接受或左右原子执行。最终即使发布事件合同与录制完整性均通过，`plant_acceptance_observed`、`force_measured`、`execution_atomicity_proven`、`exact_execution_timing_available` 和 `gp_labels_ready` 仍保持 false，直到后续阶段有独立证据。

2026-10-04 已完成直行、左转、右转的 60 秒墙钟 pilot。F2 在测试与 pilot 后按实际部署文件冻结；原 `run_context.json` 保留 pending 标志，另生成 `run_context_f2_reconciled.json` 绑定 F2 清单、安装程序和配置输入哈希。最终只读检查使用后者，原始 bag 与初检结果保留。
