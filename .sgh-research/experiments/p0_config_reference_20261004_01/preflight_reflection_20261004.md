# P0 配置独立与实际参考观测：执行前反思

日期：2026-10-04。使用既有 sgh-code-reproduction、control-preflight-reflect 流程继续首选 A。EDA 专属 DEF/STA 不适用于 USV，本次证据锁采用源/安装/模型 SHA、ROS 实际参数、源端计数与原始 bag。

## 已核实事实与缺口

F3 manifest SHA256=9c64426cc68d3eb1949fa63d564725499870bbb02d649022a2116088a0bfeb35；新工作开始前全清单 current hash 匹配，无控制/Gazebo遗留进程。F3 的57个不同C++ GTest和291种不同nominal数值输入已通过，新正常pilot通过。现有三类消息和旧bag仍不足以证明plant执行时刻或GP标签有效。

plant生成的effective_vehicle现在同时加载到B，求解器T_max/T_min也由plant参数提供。将文件改名却继续沿用同一生成产物不能算配置独立。实际reference在state_lock下与controller输入一起构造，可以在这个位置冻结，不能在离线重算或solve后再取当前path伪造输入。当次SolveInfo具有X_pred/U_pred；warm-start getter已经可能shift，不作为当次预测证据。

根因/风险排序：1. 同源配置将模型失配隐式消除，阻碍研究对照；2. 缺实际ref与预测矩阵，无法区分前瞻/代价作用和plant误差；3. 观测插桩的分配、序列化与队列开销可能改变时序，必须实测并标界。

## A/B/C 与验收

A（选定）：新增研究配置入口，分别提供plant和nominal YAML、分别hash并核对真实运行值。基准数值保持F3；仅改plant.mass到17.04kg、仅改nominal.mass到17.04kg，各以新run保留。未改的一方19项必须逐项与基准相等；变更一方mass正确且其余输入声明不变。B的solver推力约束单独来源，物理输出边界仍明确，不把全部控制配置独立作为未经核验的结论。

观测使用新附加消息，保留旧三类消息格式和旧检查器兼容性。冻结实际ref、path/profile回调身份/采样戳、nearest/idx/t0、N/dt；绑定当次cycle、controller输入与配置身份。仅使用当次求解返回的可用预测，failed/rejected/no-solve不冒充有效预测。独立有界队列、源摘要与录包实扫必须闭合新stream。矩阵维度/顺序、有限性、版本及来源都应有明确负例。

验证顺序：先脚本/实际C++节点回归（开启关闭动作一致；新回调不能改已冻结记录；失败、迟到、STANDBY和队列丢弃不伪造完整性），再必要包构建与既有回归，冻结F4，最后新基准正常pilot与两个单因素隔离probe。每个run验证实际参数和安装身份、全部新消息源计数、bag完整性及关闭流程。计时以实际clock/steady分别报告，不以固定0.2s补造输入保持区间。

B：若源/安装、维度/版本或同输入动作回归失败，保留失败、定位最小补丁，不调MPC权重、不重训策略、不更换数值门槛掩盖问题。

C：若只完成软件核验，报告只升级对应工程门槛；不声称配置实际运行隔离、速度超调因果、plant等价、实时独立监管或GP数据准入。

## 决策

GO：上述配置/观测最小工作包及受控仿真。NO-GO：本轮直接实施GP、把publisher视作plant确认、修改旧F1/F2/F3、覆盖历史bag、把候选预测当最终执行动作或宣称P1已经完成。P1继续是后续独立worker/固定tick工作包，另需阻塞期间的实际提交验证。
