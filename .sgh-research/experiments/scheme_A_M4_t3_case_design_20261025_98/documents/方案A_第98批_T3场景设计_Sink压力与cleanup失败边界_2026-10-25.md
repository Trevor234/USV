# 第98批：T3场景设计——Source队列压力 / cleanup_failed / group边界

日期：2026-10-25。设计批：无代码修改、无owned run、无资格变化。

目标：把批67登记的3项未覆盖义务转化为可执行、可审计、可复现的场景设计，供实施批（99+）按批70组件harness模式与批90+冻结模式执行。本批固定场景矩阵、注入机制、逐条断言与治理条款；实施批不得改断言。

---

## 一、义务溯源（权威绑定，不得改写）

| 义务 | 权威出处 | 原文要点 |
|---|---|---|
| publication_exit.09 cleanup_failed正确失败 | [批67登记](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/postrun/case_applicability_v1.md) L69 | 66批证明健康有限关闭+group为空；自动重试0≠cleanup_failed分支已验证。T3对当前关闭/监督**实际消费函数**注入有界失败并证明无新spawn；保留真实进程与模拟失败范围，**不制造不可杀进程** |
| publication_exit.10 旧group未空禁止restart | 同上 L70 | 同上 |
| actual_source_recording.03 log queue pressure及声明drop | 同上 L73 | 正常/故障无丢失≠施加队列压力。T3以当前enqueue/drain路径施加**有界压力**，分清generated/emitted/dropped/Stored，**异常资格及未解释差额必须拒绝** |
| P1契约语义 | [P1契约](/home/trevor/USV/.sgh-research/handoffs/scheme_A_20261010_01/source_docs/P1_时间与候选接纳契约及独立执行架构_最小实施计划_2026-10-05.md) L279/L302 | 进程终止只是有界尝试：worker退出→停止submit→有限grace→TERM→有限期限KILL→确认退出才标清理成功；**到检查期限仍未退出→记录cleanup_failed、终止该run推进并禁止重启，不伪造资源清理完成** |
| T3治理条款 | [批69计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t1_review_20261024_69/documents/下一步实施计划_T1有限补证与T2三场景族_2026-10-24.md) L54-60 | 不被T2场景族替代；每owned case预检登记/单次有限执行/自动重试0/失败原件保留；组件、阶段资格、研究结论分别判定 |
| 方法约束 | [批97指南](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t3_design_20261025_97/documents/T3_next_session_quickstart.md) | Sink类queue/buffer/overflow入口；组件级测试（批70 harness模式），不需完整owned run |

---

## 二、当前代码事实（入口清单，基于批91树）

树根：`experiments/scheme_A_M4_g4c_fix_20261025_91/implementation/t2_author/`（下称 TREE）。实施批从批91树复制并经freeze.py重建ELF/registry。

### 2.1 Sink enqueue/drain路径（actual_source_recording.03对象）

组件：`TREE/observer/src/shadow/p1_diag_sink.hpp` 的 `DiagSink<Decision,Publisher>`。

| 事实 | 位置 | 内容 |
|---|---|---|
| 有界入队 | L39-51 | `add()`持锁`generated_++`；`closing_||q_.size()>=capacity_`→`dropped_++;failed_=true`，溢出时`overflow_recorded_.exchange(true)`恰好一次→`QueueOverflow`相位；成功→`q_.push_back`，`peak_`更新 |
| drain | L85-102 | 独立线程：锁内pop、锁外publish+file写；任一失败→`failed_=true`+`SourceFailure`相位 |
| 对账 | L100 | `source_summary`: generated/emitted/dropped，`normal_source_complete = !failed && generated==emitted` |
| 关闭 | L76-77 | `close()`置closing_并join，队列排空后退出 |
| 容量 | 契约`log_capacity=512`；v1模式要求`capacity<=512` | `common/p1_full_contract.hpp` L20 |

已覆盖（`TREE/observer/tests/test_v1_sink_queue.cpp`，3 case）：disabled正常路径；**V1饱和armed门**（arm后第二decision在真实容量被拒，填充事件入队）；close取消未触发门。

**T3差集（本设计新增，不与已证重复）**：
1. 自然持续压力——不arm V1、不用填充事件，真实生产者打满真实队列；
2. 多生产者并发压力；
3. 溢出后终态保持与drain完整性对账；
4. 压力下generated/emitted/dropped逐项平衡与"未解释差额必须拒绝"。

### 2.2 进程组关闭链（publication_exit.09/.10对象）

组件：`TREE/owned_m4_diagnostic_driver_v1.py`（下称 Driver）。

| 事实 | 位置 | 内容 |
|---|---|---|
| spawn | L165-172 | 每角色`Popen(start_new_session=True)`→自成session/pgid；`spawn.json`+`role_spawned`事件；每角色恰1处spawn调用点（4处定址） |
| stop()信号梯 | L226-238 | `[(SIGINT, worker_grace 0.5s/其余 shutdown_grace 2.5s),(SIGTERM, term_grace 1s),(SIGKILL, kill_postcheck 1s)]`：逐级`killpg`+有界`wait`；`child.poll()非None即break`；末尾`killpg(pid,0)`探测→`group_empty`；产出`owned_role_closed`事件 |
| 收尾编排 | L768-777 | `finally`按regulator/fixture/worker/recorder逐角色stop；异常→`close_failure`事件+`group_empty:False`行 |
| 成功门 | L789-795 | `common_ok`：4角色rc==0、worker/fixture/recorder信号梯==[SIGINT]、`len(closed)==4`且**全部group_empty** |
| hook先例 | L788-789 | 注释明确"fault是deliberate in-process hook, never a kill or a freeze"——本设计沿用该安全边界 |
| 监督侧消费 | `regulator_owned_execute.cpp` L592 | `check_worker_locked`：对等进程死亡→unusable→stop_requested（T3-C不重复证此链，仅引用） |

**当前缺口**：group_empty=False时仅使`common_ok=false`（run失败）；**无具名cleanup_failed声明**、无"禁止restart"显式断言、无对"失败后无新spawn"的审计条款。P1契约的三分支（记录cleanup_failed/终止推进/禁止重启）未被任何场景作为具名分支驱动。

---

## 三、场景矩阵

命名：T3-Q族（queue pressure，组件级，无ROS上下文）；T3-C族（cleanup/group边界，Driver级短run）。所有case单次执行、有界时长、自动重试0。

### 3.1 T3-Q族（组件级，扩展test_v1_sink_queue.cpp同模式）

新harness：`TREE/observer/tests/test_t3_queue_pressure.cpp`（native构建，无rclcpp初始化，同现有CMake wiring）。测试Publisher可配置：`blocking`（阻塞至测试释放）/`delay_ms`。

| Case | 刺激 | 判定（逐条具名断言，登记后不得改） |
|---|---|---|
| **T3-Q1d** 确定性自然溢出 | Publisher阻塞；单生产者连续add共`capacity+K`次（K≥1024，登记固定值） | ①前`capacity+1`次add返回true（drain恰pop 1条后阻塞在publish，锁外）②其余K次返回false ③`dropped==K` ④`failed()==true`且终态（溢出后任意add均false）⑤`peak_depth==capacity` ⑥witness中`QueueOverflow`相位恰1次、`SourceFailure`恰1次 ⑦释放Publisher、close后：`publisher.calls==capacity+1`、file事件行数==capacity+1、`source_summary.generated==emitted+dropped` ⑧`normal_source_complete==false` |
| **T3-Q1r** 竞态压力 | Publisher每publish延迟2ms（慢drain模型）；单生产者全速add至`capacity+K`次 | 不变量（不要求精确分配）：①`generated==capacity+K` ②accepted+dropped==generated（accepted=add返回true计数）③close后emitted==accepted ④`peak_depth<=capacity` ⑤dropped>0（压力确实施加）⑥QueueOverflow恰1次 ⑦failed终态 ⑧balance成立 |
| **T3-Q2** 并发生产者 | 同Q1r，P=4生产者线程×M次add（P*M>capacity+K） | Q1r全部不变量＋⑨4线程有界join（超时即批次失败）⑩无崩溃/无重复QueueOverflow |
| **T3-Q3** 溢出后drain完整 | Q1d刺激后停止生产，有界等待`publisher.calls==accepted`再close | ①accepted条全部送达Publisher且仅一次 ②file行数==accepted（+summary 1行）③dropped与拒绝数一致 ④异常资格：`normal_source_complete==false`，**不宣称正常完成** |
| **T3-Q4** 负控基线 | 无压力：常规速率少量add后正常close | 全部emitted、dropped==0、`normal_source_complete==true`——证明Q1-Q3失败判定由压力引起，非构造性必败 |

**Stored映射声明**：组件层"交付观测"=测试Publisher计数（publish seam）。四角色Stored（Recorder袋）对账**不在Q族声称范围**；若未来需要，另立owned case登记，不改称Q族已覆盖。

result schema：`T3-queue-pressure/v1`；`ROS_context_created:false`、`stage_qualified:false`、`execute_qualified:false`、`research_conclusion:false`（沿用现有test L33字段约定）。

### 3.2 T3-C族（Driver级短run，真实进程+有界注入）

基础：批91树freeze重建；registration复用T2C短场景模板改T3C登记；隔离DDS域（setup_env.sh）。

**注入机制（核心设计）——角色侧survivor钩子（首选）**：

在**单一角色**（选定recorder，行为最简单且收尾在finally链末端）的测试变体二进制中：
- SIGINT处理器=no-op（跨过第一级）；
- SIGTERM处理器=`fork()`一个survivor子进程（继承同pgid；survivor忽略INT/TERM；**自带硬性自终止deadline=3000ms**；不ptrace、不SIGSTOP、不进D状态），随后角色自身`exit(0)`。

时序（全部真实代码路径）：stop(recorder)→SIGINT（角色忽略，wait超时）→SIGTERM（fork survivor+角色退出，wait成功）→循环因`poll()!=None` break（SIGKILL不发出）→`killpg(pid,0)`探测：survivor真实存活→**group_empty=False是真实事实**，非模拟。断言完成后harness以自有预算（不计入被测函数）回收survivor；回收失败=批次失败，不掩盖。

该变体经freeze.py入registry（新binary_sha256），registration中登记为T3专用角色；其余3角色用批91原二进制不变。

**备选机制（仅当首选被实施复核否决）**：Driver侧probe seam注入（in-process hook参数使探测取失败分支）。语义=模拟失败范围（批67允许），但group事实非真实；采用时须在结果中标记`injection:"driver_seam_simulated"`，且不得与首选case混同计证据。

| Case | 刺激 | 判定 |
|---|---|---|
| **T3-C1** cleanup_failed正确失败 | 正常T2C短场景至close；recorder为survivor变体 | ①`owned_role_closed(recorder)`事件`group_empty==false` ②run`passed==false`（不得因其余角色健康而放行）③survivor存活事实被记录（pid+进程证据）④**具名cleanup_failed记录**（见下）⑤失败原件保留：run目录（spawn.json/事件流/close行/stdout.stderr）SHA在审计复算下稳定 |
| **T3-C2** 旧group未空禁止restart | C1同一run的收尾全程 | ①事件流`role_spawned`恰4次（每角色1次），无任何第2次spawn ②cleanup_failed后**无新进程产生**（事件流+进程计数）③run终态失败，无静默重试事件（自动重试0）④冻结Driver源静态检查：spawn调用点仅4处定址、无循环/重试包裹 |
| **T3-C3** 负控健康关闭 | 无survivor变体，4角色全原批91二进制，正常stop | ①4角色rc==0、信号梯==[SIGINT]、全部group_empty==true ②`common_ok`成立——复现批66已证范围，不改称新资格 ③证明C1/C2失败由注入引起 |

**cleanup_failed具名声明（实施批最小diff，本设计固定语义）**：Driver `stop()`探测后，若`group_empty==false`或`returncode is None`，发事件`cleanup_failed`，字段：role/pid/signals梯/group_empty/check_deadline_ns（=kill_postcheck_ns）/finished_ns；run结果加`cleanup_failed_roles`列表。审计逐字段绑定publication_exit.09原文三分支：记录失败/终止推进（passed=false且无后续推进事件）/禁止重启（C2断言）。

**T3-C资格边界**：ROS_context_created:true；`stage_qualified:false`、`execute_qualified:false`、`research_conclusion:false`；M4/F6/P1/plant/硬实时全部保持false。

---

## 四、安全边界（批67约束的落地）

1. **不制造不可杀进程**：survivor可杀（SIGKILL致死）、自带3s硬deadline、不用SIGSTOP/ptrace/D状态构造；
2. 注入只作用于测试变体角色与专用registration，生产配置零修改；生产B仍MANUAL+RC覆写；
3. C族在隔离DDS域运行（沿用setup_env.sh），不触网；
4. Q族纯native无ROS上下文，不产生任何端点；
5. 所有case有界时长：Q族<60s/case，C族<120s/case；超时即失败，不放宽；
6. harness回收survivor的预算独立于被测close函数预算，回收失败如实上报。

---

## 五、治理条款（每case，批69原文落地）

| 条款 | 落地 |
|---|---|
| 预检登记 | 执行前提交`T3_case_registration.json`（模板见本批documents/）：case_id/义务绑定/树与bundle SHA/harness与注入spec/**逐条断言清单**/预算；登记后不得改断言，改断言=新case新ID |
| 单次有限执行 | 每case恰1次运行；重复执行需新登记并声明原因 |
| 自动重试0 | 失败不重跑；harness与Driver均无重试路径（C2静态检查含此） |
| 失败原件保留 | 失败run目录原样冻结（含stderr/stdout/事件流/ELF/registry），审计SHA复算 |

---

## 六、实施批计划（99+，每批独立CURRENT.md，失败即停）

| 批 | 内容 | 前置 |
|---|---|---|
| 99 | Q族：写`test_t3_queue_pressure.cpp`+登记→freeze→运行Q1d/Q1r/Q2/Q3/Q4→result.json | 本批 |
| 100 | C族：survivor变体构建入registry+Driver最小diff（cleanup_failed事件）+登记→短run C1/C2/C3 | 99通过 |
| 101 | `audit_t3.py`逐条款审计（Q族balance/相位；C族三分支/无spawn/原件SHA）+批67登记表3项状态更新（已证/部分，按实际） | 99+100 |
| 102 | T3收束报告+差集复判输入（供N3/M4九组联合复判） | 101 |

---

## 七、不声称清单（防夸大，逐条预先声明）

1. Q族不声称四角色Stored对账（组件层以publish seam为交付观测）；
2. C3不改称新资格——仅复现批66健康关闭范围并作为C1/C2的负控；
3. 不声称cleanup_failed的内核级绝对有界退出（P1契约原文：KILL也不证明内核层绝对有界退出）；
4. 不覆盖T2-B新代际正控（scoped Epoch设计，另批）；
5. 全部case不产生阶段资格/研究结论；组件、阶段资格、研究结论分别判定；
6. 完整M4/F6/P1/plant/硬实时保持false。

---

## 八、与既有证据的关系（不替代声明）

| 既有证据 | 已证范围 | T3新增（不重名） |
|---|---|---|
| 批66_W2 | 健康有限关闭+group为空+自动重试0 | C1/C2驱动group**非空**失败分支 |
| test_v1_sink_queue.cpp | V1饱和armed门+close取消 | Q族自然/并发压力+balance对账 |
| publication_exit.04/.05 | API partial failure（真实rcl seam 16例） | 不重复；T3不触发布partial |
| T2三场景族 | clock/job/shutdown交错 | T3不被其替代（批69原文），也不替代T2 |
