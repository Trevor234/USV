# 第39批复盘

假设成立：保留完整图和参数准备顺序，同时让业务tick等待受认证启动，可消除pre-release旧Decision并使首次phase满足原合同。Native38、唯一实际run与五组审计通过；Source实际active终结后只用INT，Worker正常Source完整，16项实际raw副本反例全部拒绝。

主机制：明确业务启动边界，解决准备/绑定与首业务周期耦合。不是NMPC性能调优，也不把不同run的I/O调度差异当作单因果速度证明。普通策略/认证/合同/Supervisor按原字节复用，真正改变是Observer业务开始时机的显式授权。

经验：完整图与RPC就绪前提不能通过调换启动顺序猜测；原150ms拒绝应保留；Source通知、wait预算和实际组退出分别计时；成功故障用例不等于正常业务或阶段资格。precheck缺少尚未准备的审计文件是一次工具准备错误，补齐后CLI重验，未触发实际重跑。

重复本次active/V3：不需要。下一步当前版本V1及普通lease/必要恢复，confidence=medium、impact=high、cost=bounded、risk=bounded；先列可复用组件与唯一待证事实，再有限预注册，不重新展开全矩阵。EDA route/STA/WNS/PPA不适用。
