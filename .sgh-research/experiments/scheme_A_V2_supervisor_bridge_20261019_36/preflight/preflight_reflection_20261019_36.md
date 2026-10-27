# V2监督闭环事前反思

事实：第35批选定的两项实际诊断通过，但监督在定向观测结束后才进入整组生命周期清理。实测active终结后505.910ms屏障才释放，2180.917ms Worker组才清空，未证明即时监督链。Source终结由异步Sink输出，不能把其可见延迟记成0。

有效配置来源修正：实际diag10合同SHA仍为89caaaf36783463a1e1d789bda41f7f90dc398981ddb4b3b8cd6037114333f72。worker_grace_ns=500000000，term_grace_ns=1000000000，kill_postcheck_ns=1000000000。前批计划将kill postcheck写成500ms，旧文件保留，本批按真实合同读取。500ms是SIGINT后的等待阶段，不是总退出时间。

原因/假设排序：

1. driver有实际终结事件却先等自然返回、终结能力suffix与正常关闭。这是监督触发未接线；应在第一次经过身份认证的Source active终结后立即调用原owned stop。
2. Source异步输出与观测延迟未单列。采用持有原inode的只读、增量游标，绑定Observer实际Source FD，分别记录check、最早本游标读到、解析完成、身份再认证完成时间。
3. 原账本只记signal调用前事件和最终组空，无法逐段复算。保留原组身份防护，新增实际killpg调用起止/结果与每段wait的开始、deadline、返回/结果。

选择A：复用现有Source、五个ELF及合同。诊断门为check到身份认证≤250ms、认证到首SIGINT≤100ms；两者是有限工程检查，不是通用Source延迟/WCET保证。等待预算从合同取500ms/1s/1s，进程组扫描/调度观察余量各≤100ms另记，不写回合同。若Source不能满足该域通知门，B为最小owned非阻塞通知入口；不通过放大本批门限补判。C为通知身份不可核验时保留失败并先补必要来源证据。

实际运行只预定一个：localhost domain196、Case C、0.05m/s、Sink故障关闭、Worker一次1700ms pre-native屏障，首真实active终结之后才认证并显式SIGSTOP Worker，强制走SIGINT→500ms等待→TERM→1s等待→KILL→1s postcheck。SIGSTOP仅用于确定性覆盖升级分支，不能宣称acados内部挂起；Worker -9和Source不完整必须保留。其余四角色继续，核对tick回退、无新授权、实际认证接收与Stored关闭。

入口：完整本地旧资产保护通过；12项通知/Source身份反例、3个真实Linux owned子进程清理和CLI导入修复后预检通过。全部角色ELF沿用，未修改C++或原owned释放代码。运行前再锁源码/库环境和这些判定规则，实际完整参数/owned端点依原准备流程核验。

GO：仅运行上述一个有限实际诊断。prepare≤20s、监督观察≤8s、close≤15s、overall≤45s，raw≤128MiB，Source游标≤16MiB/20000记录。外部55s保护不算通过。新失败原样保存，无新机制不重复同门。强制退出资源清理与正常Source/业务/阶段资格分别判定。

控制技能的EDA route、WNS/PPA条目不适用，未填造指标。依据为固定源码、实际合同、第35批raw及已封存审计；不作算法优越性或真实推力结论。
