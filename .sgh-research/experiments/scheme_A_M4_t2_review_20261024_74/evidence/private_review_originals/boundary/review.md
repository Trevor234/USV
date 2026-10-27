# 第73批只读复核：测量口径、推论及最小 T2 边界设计

仅原件只读及 `/tmp/review73_boundary_plan/` 私有离线材料；没有 ROS/DDS 初始化，没有 owned run，没有修改70–73原件。

路径缩写 P72=`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72/implementation`，A8=`P72/t2_author_rev8`。`measurements.json` 内源路径全部展开，并记 bytes/SHA256；脚本 `reproduce.sh` 可复现（只启动普通 Python 与 C++ 离线小程序）。

## 1. 测量成立部分与必须修订部分

原73 `documents/方案A_第73批_T2B在途窗口实测与可行性结论_2026-10-24.md:7–9` 与 `evidence/t2b_inflight_window_v1.json:43–49` 的数字有真实源，但命名/强推论不成立。

六个 0.442729–1.507248ms 来自 `worker/source.jsonl` 的 `job_received.receive_ns` 到 `candidate.publish_start_ns`；后者是写 candidate Source 行时取的时间（A8/worker/solver_worker_m4.cpp:311），实际 publish 在:324–325。不能叫 Regulator submitted→result，也不等于纯 native solve。Worker 对应行14→16、20→22、26→28、32→34、38→40、44→46。纯 Worker solve_start→solve_end 是0.307805–0.979924ms；backend_ms为0.183078–0.779464ms。

真实 Regulator submit_commit→candidate ready_commit 窗口按Job1…6为3.119183、2.280437、1.573737、1.573913、2.194410、2.271254ms，源行141→143、180→182、223→225、262→264、305→307、344→346。因此“submitted→result亚毫秒”与该流不符；即Worker口径第一Job也超过1ms。

所谓36条 capability 实际是18个 `capability_publish_attempt` +18个 `capability_publish_result`。仅attempt有 `payload.active_job`（18次皆0），result没有payload或active_job，用`get(...,0)`会把缺字段假装成0。源attempt行4,6,8,10,12,18,24,30,36,42,48,50,52,54,56,58,60,62，配对result为后一行。Worker启动一次publish后采用200ms wall timer（A8/worker/solver_worker_m4.cpp:87）；第一间隔85.46ms，其余约199.28–200.84ms。因此可表述“该保留样本18次payload快照均未观察到active Job”；不可提升为“健康系统不可观测”。

A8/t2_scenario_driver_v1.py:284–377 的触发主循环无1ms sleep，check_time:69–70只检查总截止；Fixture主循环:254有2ms sleep。即便存在1ms/2ms周期，这表示相位相关的等待范围/实际调度，而不是每次动作必付的严格最小延迟，两周期之和不能证明架构上不可能命中。六Job样本支持“现有稀疏cap触发在本样本未命中；对短窗口不能给确定性保证”，不支持“架构不可能/唯一确定性路径”。有限boundary/release是可评审的确定性候选方案。

## 2. ready_window 与101点不能合并论证

定义 A8/t2_action_contract.py:11–13,:30–31 已明确 ready_window 是 accepted candidate_registration，结果已经被接纳。它自身不生成第二个旧结果。正常目标Job一次结果已在变更前登记，随后path版本回调会清ready/candidate（A8/observer/src/shadow/regulator_owned_execute.cpp:578,:617,:626），不会凭空再产目标Job的post-change stale registration。其他Job/不同延迟与别的交错应独立论证，不能说所有ready场景永远不可能有stale。

此外当前Driver连“ready确定性可跑”也未做到：缓存的active/ready evidence只有 `{observed_ns,job}`（A8/t2_scenario_driver_v1.py:308–315,:331–332），:356–365原样交validate_command，后者A8/t2_action_contract.py:209–212要求exact `{phase,job,observed_ns,source_role}`，离线重放solve_active、ready_window皆得到 `command trigger evidence exact fields`。T2A after_grant_ms:353自己带齐字段，所以72成功不覆盖这一分支。

101点确在全新Epoch的 `Epoch.propose` 上触发 `static_reference_population`（A8/observer/src/shadow/task_time_profile_v1.hpp:37）。但已经建立epoch后任何绑定变化会经Regulator:578调用Epoch.invalidate_if_changed(:27)，产生 `invalid_reason=epoch_binding_changed`，之后propose:31先返回`epoch_terminal`；201点完整合法新几何同样如此。随后prepare_loop:911会将活动epoch政策失败变成run不可用。这比点数检查更早；因此当前ready几何无stale不能唯一归因于101点。

actual header离线小反例 `epoch_probe.cpp`→`epoch_probe.json`：201点第一proposal/commit成功；fresh101→static_reference_population；active201换binding但不调用invalidate→epoch_binding_changed；调用Regulator同一invalidate之后，无论201或101均→epoch_terminal。链接仅现有utils.cpp作参考采样/角度数学，不含ROS或native solver。

## 3. 推荐 T2 scoped 诊断 variant，而非改普通登记偷渡W2

现成Worker gate在A8/worker/solver_worker_m4.cpp:111–113要求fault_injection_enabled=true且parameters_are_diagnostic_only=true；而普通T2入口A8/w2_runtime_contract.py:267–278要求ordinary scope+fault=false+普通冻结contract，Driver spawn:79–80 close_fds=true且不传pipe。故不可能只给当前普通登记加w2_release字段就复用成功。

建议新增独立、有限、预登记的T2 scoped诊断variant，source/bundle/ELF/entry/audit均重新pin。复用既有 `w2_entry_contract.hpp`、`w2_release_gate.hpp`、`w2_native_boundary.hpp` 与 owned_cold Backend的attach_boundary路径，不复制44B release协议，也不增加任何native C内部挂起。保留诊断scope、fault=true、physical/M4/P1/F6 qualification=false；普通profile参数仍 fd=-1/job=-1/ordinal=0/nonce=0/wait=0，不arm、不等待，普通入口继续拒绝散装诊断参数。

仅注册一个目标Job+一个call ordinal（如Job2/ordinal1），有限wait预算、唯一nonce及原pipe device/inode，严格单次release。W2 Boundary在BeforeCall等待并在真正C入口再次guard（A8/worker/owned_cold_backend.hpp:19–44,:76–108；w2_native_boundary.hpp:120–136,:169–226）；ACK实际native=false，不能冒称C调用内在途。原W2“两完整tick后释放”绝不能照搬：200ms tick×2必越过原150ms Job deadline。

触发应是绑定目标的 `w2_boundary_entered` Source ACK（现Worker:133–138在等待前写并flush），作为T2新登记phase/证据对象，带齐phase/job/observed_ns/source_role；不依赖200ms capability观察，因为finite150ms内无法保证出现下一次cap快照。Driver缓存同Job全tuple并核对run/worker/source身份；窗口丢失须注册失败，不能改用job_received或睡眠当ACK。

最小及时语义 case 可只做一次path_clear（该action已在T2B词汇中），减少替换后epoch恢复要求。Driver看到boundary ACK→发原Fixture命令→Fixture publication receipt→等Regulator自己的path_version ACK（同动作后、task_generation严格大于目标旧代、实际fingerprint改变/clear）→才写私有release。若使用replace则完整绑定path/profile回调及预期版本，不能把Fixture publish返回当DDS到达/版本提交ACK。Regulator现有source足够提供ACK，无需增加第二协议。

## 4. 及时旧版本拒绝与过期隔离必须分case

及时 case应冻结下列同Job因果链：submit_commit≤worker_receive≤boundary_entered≤Fixture动作receipt<Regulator版本ACK≤release.write_start≤boundary.released≤final_guard≤原deadline；原deadline必须严格等于tick_origin+150000000。还必须实际native invocation=true、solver成功、旧Job完整echo不变、candidate生成并在原deadline内到达Regulator、current_tick仍对应target-1、最终candidate_registration accepted=false且reason=version_mismatch、无Worker终止/隔离冒充。这一结果只证明旧代在途结果拒绝，不宣称新代恢复（当前epoch本来就不支持动态重绑）。Admission的version检查优先late（p1_admission.hpp:105–109），所以仅见version_mismatch仍不足证明timely，必须另核ready_commit≤deadline。

过期 case应独立标作boundary expiry/Worker isolation：单次合法release可在gate私有wait窗口内却晚于原deadline，记录released=true、disposition=expired、guard>deadline、past_deadline正确、actual_native_invoked=false；Backend抛w2_boundary_expired（owned_cold_backend.hpp:84–92），Worker terminal_exception/fatal并按现有能力/隔离路径关闭。这不是T2B的任务版本拒绝；candidate缺失、late、wrong_tick、run_unusable、timeout/EOF或Worker terminal都不能给及时case通过。有限wait失败与expiry也各自报告，禁止自动重试/延长deadline补齐。

最小设计修复的验证应覆盖：普通默认未arm、目标/非目标Job及ordinal隔离；绑定/通道完整性；boundary ACK→真实Regulator版本ACK→release顺序；及时路径严格同Job版本拒绝；超时/过期独立否决；不把W2隔离通过当作T2B stale通过。第74批只需登记这一设计并修审计/结论，不执行B/C。
