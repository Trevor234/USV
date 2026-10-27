# 2026-10-06 能力消息观察器尾段修正

已执行的 idle_stop_new_01：mechanism_complete=true，但观察器25条/实际MCAP26条能力消息，evidence_accounting_complete=false，selected_gate_passed=false。原始文件、检查报告及外层中止批次保持不变。相同内容重复且v1没有包序号，不能从内容散列定位具体漏掉哪一条。

事实：fixture在停止生产进程的阻塞等待期间不处理rclpy回调，能力消息订阅缓存depth=1；存在停机尾段观察盲区。bag与源记录本身未改。最小修正只增加fixture的有限等待期间回调处理，并将观察器能力订阅缓存设为64；生产DDS端点、原监督器、worker v8、regulator v11及revision4合同均不改。观察器错误记为运行失败，仍继续有限owned清理。

A（行为）：三种已声明故障仍只使用owned SIGSTOP/SIGCONT；保留1.8s停止、0.8s恢复、600ms有效期及820ms有限诊断观察判据，保持原始逐流内容对账门槛。

B（证据）：原检查器不变，不用subset或计数差容忍替代观察器/actual完整多重集相等。新runtime快照v26、独立新run_id；v25旧证据不重判为通过，重复运行与失败都计入实际摘要数量。新增5项测试检查有限等待及观察错误不跳过cleanup。

C（范围）：真实capability v1仍无发送时间/序号，receipt lease仍只约束有效回调本地验证提交时间；不得宣称源新鲜度、抗重放、自然acados挂死或执行资格。新gate仍要求0物理端点、固定实际身份、完整调节器源/包对账及owned清理。active_stop强杀worker的闭合未知保留。

决定：GO，仅修正观察fixture并执行原定3场景与5项必要回归。任何新证据门槛失败即停止相关批次并调查。EDA/Slurm设施不适用于本ROS实验；对应真实原始MCAP/source/owned ledger/hash清单必须保留。
