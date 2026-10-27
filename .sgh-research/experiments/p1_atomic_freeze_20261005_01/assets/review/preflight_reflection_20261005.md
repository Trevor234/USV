# 动态B求解资格与输入冻结最小修复：执行前反思

日期：2026-10-05。状态：只读预审与计划；本文未修改生产文件、连接远端、编译或启动仿真。根任务拟在实际F4 hash门禁后执行局部修复、回归、F5冻结及新基准pilot；这些尚不能从本文标成已完成。

## 1. 技能与本次证据锁

应用 [control-preflight-reflect](C:/Users/sgh/.agents/skills/control-preflight-reflect/SKILL.md)，读取其 evidence-lock、checklist、reflection-artifact。该技能的参考模板原为EDA的route/DEF/STA；本任务是USV控制，所以仅采用“先锁定证据、事实与假设分开、A/B/C、GO和停止条件”的流程。EDA文件和BM/BPR/WNS/TNS指标均不适用，不运行EDA helper、不以缺EDA证据阻断USV工作；用实际ROS契约、状态/参考来源、锁和deadline证据替代。

| USV证据 | 已核实内容 | 局限 |
|---|---|---|
| F4归档 `outputs/P0_配置与参考观测_2026-10-05/验收元数据.json` | 321849bytes；SHA256 `ddb60bf3164fe56a4fe16ef10dc57bc3b26e4b61179fe638a0e27e434f3fb758`；24配置比较通过，62不同C++ GTest，三个真实run通过原/新增契约 | 本预审读取归档，不重新运行或读取Ubuntu原bag |
| F4 baseline manifest | ID `F4_20261005_config_reference_01`；manifest SHA256 `25135dee86621b91ff326ae548b626eae84aa5760e87b8b4c6f1f184664c62c7`；146source/config、177installed、5model | 静态runtime标志仍false；运行核验绑定各run context |
| F4 node/header/test身份 | node `0cdcf556a90dde537d39da666c8b52aa2648af866fb2e4463ce190a3107c6b93`；header `536221d592aec0a2d91705f49ce3739f6706afdb8a0426e9a06e1a7a36fbbf72`；test `99dd8bb798d2771c6c64e8cdbf8a635f41e5c5a6c1545f228be9028edd45918b` | 部署前须现场再次核验live source/install/model，不能按旧本地mirror整文件覆盖 |
| 本地node镜像、F4局部telemetry patch与独立阶段审查 | can_solve与input/reference构造分两次state_lock；发布status在output锁内再取state锁；同步solve在state锁外 | node镜像不是F4逐字版本，具体锚点/最终diff与SHA由根任务现场核验 |
| F4运行时间/参考记录 | 三run分别215/224/222次solve，全profile_time；参考资格异常0，warnings空，deadline miss0；有效sim跨度60.06/60.04/60.24s | 正常运行没有触发竞态，不证明竞态不存在；不是公平性能对照 |

F4基准solve P95/max为0.380004/0.446739ms，本地timerentry至publish结束P95/max为0.494443/0.613075ms。后二者包含standby等全cycle；不属于传感器到plant完整端到端时延。两种质量探针也无超时，但它们不能提供最坏执行时间证明。reference拷贝在solve_start前，预测拷贝在publish后，均未全部包含于原solver budget。F4配置隔离与记录链已通过，本工作包不重做质量探针或变更模型/权重/几何。

## 2. 错误前提检查与风险排序

**事实：** 当前control_loop先在state_lock内调用can_solve，释放锁，再调用run_dynamic_mpc；后者重新取得state_lock读取状态、path/profile并构造reference。path/profile/odom/FCU回调可以并发更新容器，而控制timer组本身互斥。

**可构造路径：** 首次资格通过 → 解锁 → path callback clear或改单点 → run取得锁仍复制状态并build → empty_path零矩阵或单点参考被送入同步solve。仅给状态/reference复制加锁没有让先前资格与这次输入成为同一检查事务。

| 排序 | 判断与假设 | 支持证据/待验证 |
|---|---|---|
| 1 | 资格与冻结的TOCTOU窗口是本工作包直接修复目标 | 两段锁之间真实callback可更换path，源码路径成立；新确定性节点测试应在此窗口注入clear/单点，不能只依赖自然pilot |
| 2 | 将失败发布分支塞进state锁会制造自锁/反序风险 | enter_standby拿output锁后publish_standby_status又拿state锁；已有成功status也是output→state。必须锁内检查/构造，锁外发布 |
| 3 | 冻结之后clear、同步阻塞期间旧计划继续成为候选，是另一项版本/执行策略 | 本次保持已冻结任务语义，不新增取消门禁。需记录此边界，不把修复称为task-clear即时停止或独立监管 |

无证据把本竞态作为F4速度偏差根因。F4没有实际参考资格异常；其速度差异受起始条件和几何探针等变量影响。本次目标是可复现代码缺陷与确定性资格门禁，不是优化性能。

## 3. A/B/C与选定方案

| 方案 | 实现与验收 | 选择 |
|---|---|---|
| A：动态B冻结前同锁复核 | 在实际构造state/reference的同一个state_lock临界区先can_solve，再复制状态/来源、build真实reference/metadata。资格失效只保存reason；释放state锁后走既有STANDBY。保持现有同步solve及发布门禁 | **选定：最小修复。** 若保留control_loop第一道廉价检查，第二次检查才是资格与冻结的线性化边界；不能复用第一道布尔值 |
| B：直接合并完整worker/监管重构 | 一次重做候选、版本、worker、固定tick、输出归属及fallback | 本轮NO-GO：使原子冻结修复与独立执行机制混在一起，难以判定回归来源；保留给正式P1 |
| C：保留现状，仅记录空参考警告 | 有诊断价值，但仍允许可构造的资格失效输入进入solve | 不足以声称已修复；若源码身份或锁证据不足可暂缓部署，但不能勾选原子冻结完成 |

本修复仅动态B路径。资格定义继续调用原can_solve：no_odom、odom_timeout、no_path以及开启FCU要求时的no_state/state_timeout/disarmed/wrong_mode。profile malformed或stamp不匹配但合法path仍存在时，保留原cruise_arc_fallback；不顺带加严profile规则或改控制目标。

## 4. 阶段语义与锁边界

选定流程：timer观察身份 → 原外层资格检查（若保留） → **state_lock内最终资格复核+状态/odom/IMU身份+真实reference与path/profile metadata冻结** → 解锁 → 合格任务按原同步solve/deadline/映射/发布处理；拒绝任务在锁外enter_standby并完成真实no_solve周期。

1. state锁内不调用enter_standby、publish_status/publish_standby_status、物理publish或拿control_output_mutex。保持现有output→state次序，不引入state→output。research clock/logger锁也不新增反向调用状态锁的路径。
2. solver调用不得置入state_lock；callback在solve期间仍可更新容器。原capsule控制timer互斥、热启动/上一发布锚点逻辑不改变；本轮不新增worker并发。
3. 最终资格失败时应未设置solve_invoked，状态类型保持no_solve，未执行phase/source IDs/time保留零，不生成ReferencePrediction。仍完成CycleTiming与真实AppliedControl的同cycle关联，rejection_reason为实际资格失败原因。
4. control_loop曾提前置prev_state=ACTIVE时，拒绝分支应由锁外enter_standby覆盖到STANDBY，不能被caller事后再置ACTIVE。沿用standby_release零发布及原warm-start/history reset，不换成重复上次命令或backend失败HOLD。
5. 零推力只是既有发布策略，不证明船立即停止、变化率连续或碰撞安全；这些不在本工作包验收。
6. 冻结后clear不取消这次在途同步结果：若原deadline允许，仍可处理原冻结候选；下一次控制资格检查再进入STANDBY。其原因是本轮只闭合资格/输入事务，发布前任务版本取消属于后续P1策略。不能把它称为clear即时接管。

## 5. 验收矩阵与停止条件

| 类别 | 必需证据/门槛 |
|---|---|
| 身份/改动范围 | 现场F4 source/install/model gate通过；局部guarded patch/diff只涉及动态B资格/冻结与必要测试，三修复、nominal/plant配置、消息、checker、预算与映射不变；旧快照不覆盖 |
| 窗口clear | 先确认旧资格可通过，再在实际freeze前走真实clear callback；新分支solver调用数0、参考流0新增、no_solve周期和standby_release零事件存在且同cycle |
| 窗口单点 | 同上；拒绝reason no_path，不能用零矩阵/单点参考调用solver后再称为拒绝 |
| 合格输入 | 正常profile与合法path的fallback；真实solver收到矩阵与source IDs/版本严格等于记录；新odom到达时消费本次最终锁内状态，不复用旧外层状态 |
| 同锁与锁序 | 确定性阻塞/回调测试证明构建输入期间容器不能被中途替换；拒绝路径能完成，锁外STANDBY不死锁；不靠长sleep偶然“通过” |
| 冻结后clear | 控制的blocking fake在solve进入后clear，验证本次冻结reference/版本不变及既定未取消语义；下一周期无path时真实no_solve。与deadline失败用例分开控制条件 |
| 原回归 | 原62个不同节点GTest全部通过，加新增唯一名称测试；原迟到250/400ms拒绝、关机和F4捕获证据均保留；实际编译binary/XML hash归档 |
| F5/新pilot | 新不可覆盖F5冻结、必要源码/install hash与四项capture证据绑定F5；新baseline独立run_id/目录，旧/new checker及actual_solve_input门槛通过；source drop/publish error0、正常flush、最后end_unknown，资格异常0 |
| 资源/诚实结论 | 记录新solve和本地cycle时间、CPU、源计数及失败；只比较实现/契约，不用一次正常pilot证明竞态概率或最坏RT上界 |

**STOP/NO-GO条件：** F4 hash不符或应用锚点未知；出现state→output锁路径/在state锁内发布；clear/单点仍solve或造ref；新理由被当backend失败导致HOLD语义变化；正常profile/fallback或输入身份改变；旧回归/构建失败；新captured证据仍错误绑定F4；队列drop、publish error、interrupted cycle、checksum变化；为了通过而放宽20ms matcher、隐去shutdown/失败记录。停止扩大试验，保留原件、diff和诊断，先修可定位问题。

## 6. GO决策与剩余边界

**GO：** 选A作局部guarded实现，并在现场F4门禁、独立补丁/锁审查与节点回归通过后冻结F5，再跑一组新的正常baseline记录验收。当前预审不替代补丁final diff；补丁未审或测试未通过时，对仿真批次为CONDITIONAL，不能先宣称实施完成。

**NO-GO：** 本轮重写worker/固定执行tick、改变已冻结后clear取消策略、改模型/权重/路径/质量/几何、PPO/GP重训，或升级plant ACK/force/atomic执行、精确执行时间与GP标签。

F5完成只证明最终求解资格与实际state/reference同锁冻结，以及拒绝时正确走原发布分支。它不自动完成P1独立worker、固定tick、唯一输出；生命周期stop observer仍只是实验收尾，不能当监管器。plant_acceptance_observed、force_measured、execution_atomicity_proven、exact_execution_timing_available、gp_labels_ready继续false，P0/P1整阶段仍按原门槛分别验收。

## 7. 现场前提核验补充（根任务2026-10-05执行）

根任务报告已实际核验F4全部328个current source/install/model hash，结果通过，并保存 `/home/trevor/USV/.sgh-research/experiments/p1_atomic_freeze_20261005_01/preflight.json`。targeted source核验确认io callback group为Reentrant、control group为MutuallyExclusive且为不同group，`mpc_node_main.cpp`使用三线程MultiThreadedExecutor；因此path回调与控制锁间窗口有真实并发执行前提，并非依赖单线程模型的猜测。根任务同时确认can_solve自身不加锁、enter_standby持control_output_mutex。本补充记录根任务现场事实，不代表本审查重新读取了远端完整源码。

本轮候选新冻结ID为 `F5_20261005_atomic_freeze_01`。F4身份前提已满足；生产patch final diff、旧新回归、F5 source/install hash与新pilot仍分别待根任务验收。记录此门槛进展不将planned产物写成已完成。
