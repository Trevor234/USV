# T3（98–101）与123登记复审（只读）

## 有效进展

- 99阻塞Publisher设计成立：`picked`在drain锁外publish内自增；观察到picked=1后，队列已pop一条但publish尚未返回；单生产者填满512槽，513 accepted精确可断言。Q1d无需依靠睡眠碰运气。Q1r/Q2竞态分配仅断言守恒，避免要求调度器固定分配。
- 100真实C12证据显示4角色各1次spawn；fixture信号梯SIGINT→SIGTERM，退出rc0但组非空；Driver发具名cleanup_failed；其余角色健康；C3负控健康。注入只在测试变体，生产控制模式未改。
- 信号安全判断须按代码：实际handler仅忽略INT/设置atomic stop flag；fork发生main loop退出之后的`t3_close_with_survivor()`，不是在SIGTERM handler内fork。不得把登记簿的错误描述当实际代码行为。
- 资格边界普遍明确（无Stored四角色队列压力结论、无内核绝对有界退出、无M4/F6/P1资格）。

## F-T3-01 [P1] Q2线程闭包悬空引用，历史真实事件已出现大量重复ID

99 `implementation/t2_author/observer/tests/test_t3_queue_pressure.cpp:99–101` 循环局部`base`以`[&]`捕获；每次迭代末其生命周期结束，线程仍读它。属于C++ undefined behavior；应按值捕获`[&,base]`。

原始`runs/T3-Q2_r2/q2.jsonl`：513条接受事件，仅163个唯一sequence，350条重复，全部在第4线程的2305–2467范围。原14/14判定没有逐ID检查，所以漏报。有限纯native ASAN对原源编译后运行，rc1，明确`stack-use-after-scope`，指向line101读取line99的base。证据：asan_probe.json/asan_stderr.log/q2_actual_id_probe.json。

影响范围：测试本身有UB，Q2并发压力结论须用修正派生树重证；不等于生产DiagSink已经发生同一捕获缺陷。Q1d及无此闭包路径的结果不因此全盘失效。

最小修复：按值捕获base；每线程记录accepted ID集合，并核对Publisher决策ID、JSONL事件ID多重集完全一致；新增重复/丢弃替换变异与ASAN目标。保留原件、不静默重写99。

## F-T3-02 [P2] “failed终态”须明确是资格黏住，不是永久拒绝enqueue

98设计声称溢出后任意add均false；实际DiagSink::add :47–50只因closing或queue full拒绝，不因failed_拒绝。99 Q1d的terminal probe发生仍满时，并不能验证排空后的行为。

实际组件有限probe：capacity1，seed→填满→overflow拒绝→release/drain→再add成功；failed仍true。sticky_probe.json为`add_after_failed_and_drained=true / failed_sticky=true`。

建议默认收窄措辞为“异常资格不可回正，后续诊断仍可接收”；是否要永久禁入应由Source政策决定，勿为让旧文档好看而擅改生产日志语义。补测overflow/drain/re-add/close，normal_source_complete仍false，所有计数可对账。

## F-T3-03 [P2] 独立审计的称谓强于其实际复算范围

101 audit_t3.py :63–78只重算JSONL行数、summary守恒/极性等；phase计数、peak、publisher事实等仍消费result.assertions[].passed，未独立解析原始witness/Publisher逐ID事实。真实Q2重复便被全绿吸收。C部分消费close结果与事件流，15/15不是对每个原始性质完全独立证明。建议把“独立”细分为身份复核、summary复算、原harness断言引用；后续派生审计逐ID复算，不能简单将所有true布尔视为新证据。

101 :44–48哈希bundle文件本身，却不逐项重新哈希bundle中全部source文件；:110 C同理。摘要清单没变不代表所有文件内容不变。若仅证明冻结manifest应如此表述；若证明当前树未变须消费files逐项复算。

## F-T3-04 [P2/P3] survivor可复用实现应收紧，但不反推否定原真实group证据

100 survivor.cpp :95–104：fork()<0未被明确拒绝，记录仍可能pid=-1；仅关闭fd3..255，不能泛称“关闭所有继承fd”。需检查fork错误/正PID，预计算fd上界或显式allowlist/已支持close_range；fork后只用可证明async-signal-safe的POSIX序列（clock_gettime/nanosleep/close/_exit），减少C++库隐含依赖。当前实际fork在主线程，不是signal handler复杂逻辑。

`killpg(pid,0)`与信号梯对真实冻结run的组非空/停止推进/无新spawn证据成立；它证明当前有限Driver关闭路径，不等于已有通用生产restart状态机拒绝所有未来重启请求。测试survivor需与生产supervisor严格分离。

## 123登记与下一步

- I04应改成“SIGTERM设置stop，由主循环fork”，当前“SIGTERM处理器fork”与代码不符。
- I06是有价值且实证的确定性测试方法；宜称可复用工程成果/创新候选。有限测试不是文献新颖性认证，也不证明所有负载/平台性质。
- 登记簿复用路径多为...，应给真实绝对文件或结构化artifact ID、SHA、scope、测试前提、未覆盖项；用事实、可复用成果、衍生研究假设分层。
- 不应把所有剩余工作归为“全部需用户决策”：本轮Q2修复、审计语义收紧、登记文本纠错、集成位点离线梳理都可以先在派生树内完成，不依赖GP/plant/RT资源；资源级数据采集/物理接入另列。
- 集成候选应分开：先做行为最小且证据最清晰模块的独立落位+负控，不捆绑模型、恢复与代际政策。T3压力harness和survivor本身是验证工具，不是生产运行功能。

本子任务未改历史资产；只在/tmp编译运行纯native有限反证，无ROS/owned/信号survivor执行。
