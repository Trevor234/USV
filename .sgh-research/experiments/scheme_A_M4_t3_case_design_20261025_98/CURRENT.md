# 第98批：T3场景设计批（Source队列压力 / cleanup_failed / group边界）

设计批：无代码修改、无owned run、无资格变化。

## 交付
- T3场景设计文档（义务溯源/代码入口事实/场景矩阵/注入机制/安全边界/治理条款/实施计划）
- T3预检登记模板 `T3_case_registration_template.json`（8 case：Q族5 + C族3，JSON已校验）

## 关键设计决定
1. **T3-Q族**（组件级，无ROS上下文）：扩展 `test_v1_sink_queue.cpp` 模式新建 `test_t3_queue_pressure.cpp`；确定性溢出用"阻塞Publisher"（drain恰pop 1条后阻塞在锁外publish），竞态用慢Publisher；判定为具名不变量集（generated==emitted+dropped、QueueOverflow恰1次、failed终态、peak<=capacity）+负控Q4。
2. **T3-C族**（Driver级短run）：首选注入=**角色侧survivor钩子**（recorder测试变体：忽略SIGINT、SIGTERM时fork自带3s硬deadline的可杀survivor后自身退出）→ `killpg(pid,0)` 探测到**真实的**group非空，非模拟；备选=Driver seam注入（须标记 simulated，证据不与首选混同）。
3. cleanup_failed具名声明（实施批最小diff）：Driver stop() 探测后 group_empty==false 或 rc==None → `cleanup_failed` 事件（role/pid/signals/group_empty/check_deadline_ns/finished_ns），审计逐字段绑定 publication_exit.09 三分支。
4. 禁止restart证明：事件流恰4次spawn + 冻结Driver源静态检查（spawn调用点定址4处、无重试包裹）+ 无新进程断言。

## 义务绑定
批67登记 publication_exit.09 / publication_exit.10 / actual_source_recording.03；P1契约L279/L302；批69治理条款；批97指南入口。实施批不得改断言。

## 下一批（99）
Q族实施：写 harness → 登记（回填K值与SHA）→ freeze → 运行Q1d/Q1r/Q2/Q3/Q4 → result.json。失败即停。
