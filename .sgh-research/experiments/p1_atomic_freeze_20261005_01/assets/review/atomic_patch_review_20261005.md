# 动态B资格与输入原子冻结：最小补丁独立审查

日期：2026-10-05。审查方式：仅读取本地获准镜像、F4归档证据、局部生产补丁与测试载荷；不连接Ubuntu、不改生产文件、不启动仿真。本文件补充同目录 `preflight_reflection_20261005.md`，不替代根任务的现场diff、编译和F5验收。

**结论：生产局部补丁可进入现场应用及回归。** 未发现新锁反序、重复发布、伪造reference或正常输入数学改变。最终基线/pilot验收须以根任务完成的实际F5身份与测试结果为准。新测试初稿发现一处可能悬空的 `std::vector` 元素引用，已通知根任务修正；还建议直接验收冻结后clear的保留策略。

## 1. 审查输入与身份

| 文件 | 本次读到的SHA256 | 审查范围 |
|---|---|---|
| `implementation/apply_atomic_freeze_patch.py` | `a202971adf13eef2d87c533c9c0d59b6e4f89661e33a8fedea02e9e5840b9ce2` | exact F4 source/header guards、函数范围与唯一token锚点、拒绝重复应用、原文件备份 |
| `implementation/atomic_freeze_gate.cpp.txt` | `966038471a04515febdad77fe149593af921f8cce8fb9528d55374d0adae3490` | 唯一生产变化的锁与拒绝路径 |
| `implementation/source_guard.json` | `b672ddc0cae5a1ae9ea935d9b39044c940a75b360c91583f2e662aa2f792b59b` | F4 node/header身份与已归档运行资产一致 |
| `tests/atomic_tests.inc`（初稿） | `986db92532c0e1df61a370bea120d6c6a43a1c5f6ef8092c4e6254c0b5c166a3` | 4条节点行为测试，审查时尚待下述测试修正 |
| `tests/atomic_access.inc` | `1d14bea5c7510e6a0eed55f2e51456ace09255f82278aee8960d46ccbafeaae4` | 仅既有friend测试入口，不新增生产hook |

局部脚本严格要求实际node SHA `0cdcf556a90dde537d39da666c8b52aa2648af866fb2e4463ce190a3107c6b93` 与header SHA `536221d592aec0a2d91705f49ce3739f6706afdb8a0426e9a06e1a7a36fbbf72`。只有 `run_dynamic_mpc_` 内首个 `state_lock_` 紧邻 `current_state <<` 的唯一锚点可改；函数外文本与solve/build调用数保留。header只核验不写入。格式化后的实际源码SHA须由现场重新记录，不能使用预格式化patch预测SHA作为最终F5身份。

本审查独立执行 `test_atomic_patch_guards.py`，6条通过，含旧mirror+作者F4局部修改的语义预览、缺失/重复锚点、重复应用、非F4拒绝写入、运行资产身份绑定。预览未宣称与实际F4逐字一致，也不能替代实际编译与节点测试。

根任务现场已确认328项F4 source/install/model hash通过，并确认不同的Reentrant IO组、MutuallyExclusive control组及三线程executor。故旧precheck至第二临界区间的callback交错具备真实并发前提。该事实来自根任务现场核验，本审查没有再次远端读取全源码。

## 2. 最终生产路径与锁序

1. 外层 `control_loop_` 保留原资格初检与每timer周期账本初始化。
2. 动态入口首个 `state_lock_` 改 `unique_lock`；在复制任何state/source时间或调用参考builder前，重新运行原 `can_solve_()`。
3. 资格失败立即 `unlock()`，再调用原 `enter_standby_(reason)`，观察已armed时保存相同reason，随后return。
4. 资格通过时持续持同一状态锁复制状态与source身份、构建真实reference/metadata及执行原heading warmstart逻辑；出临界区后才进入输出anchor锁与同步solve。

第二次资格检查是本次最终冻结的线性化边界。回调更新只能发生在该临界区之前或之后；不能在资格成立与本次state/path/profile复制之间更换容器。`can_solve_`自身不递归加锁，`unique_lock`不增加一层状态锁。

拒绝分支先解锁是必须条件：原 `enter_standby_` 持 `control_output_mutex_`，发布standby status又会取 `state_lock_`。补丁维持既有output→state顺序，未加入state→output、锁内publish或锁内同步solve。heading warmstart仍位于原state锁内，未改变其既有职责。本轮没有把solver本体改成并发worker，不能据此宣称所有solver接口已为将来的并发worker安全。

外层初检后曾短暂将 `prev_state_` 设ACTIVE；若新复查拒绝，原standby函数将其恢复STANDBY、清失败计数/热启动并发布既有零目标。拒绝不是backend失败，也不推进连续solver失败/HOLD计数。原scale、限幅、deadline、失败回退、正常profile参考、有效path下坏profile的 `cruise_arc_fallback` 均未更改。

## 3. 观察账本与退出边界

新gate位于state_copy/reference_ready/solve_start/solve_invoked填写前。失败返回时，外层正常timer仍保存一个 `solve_invoked=false`、`state_kind=no_solve` 的CycleTiming；相关input/source/solve阶段字段保持默认零，reason为原 `can_solve_` 原因。standby命令仍通过已有AppliedControl记录并由外层绑定同cycle/applied_sequence。F4局部reference对象虽可能已创建，但gate前未build/copy/enqueue，不能由对象创建误称新增ReferencePrediction事件。

gate未新增shutdown策略。现有异步shutdown可能让动态入口在原检查处提前返回，summary继续使用原interrupted-cycle/normal_end门槛；本补丁不能证明shutdown在固定时限内交接。拒绝分支standby调用与reason赋值之间没有额外求解/发布，reason晚于实际待机发布记录并不改变最终cycle关联。

冻结成功后清空path依然不取消在途同步solve；已有local state/reference矩阵继续是本次求解输入，完成后仍受原deadline与shutdown门禁。下一周期读取clear后容器才进入no_path待机。这是本轮保留的兼容性策略，后续P1须明确是否引入任务版本失效与取消门禁，不能把本次修复写成clear即时停止。

`atomic solve资格/state/reference冻结` 只指控制源临界区事务。左右命令仍分别publish；plant ACK、测得力、plant执行原子性、精确执行时间、GP标签继续没有新证明。

## 4. 测试审查结果与局限

初稿4个新用例覆盖：原成功precheck后真实path clear/改单点，进入实际动态入口时拒绝且builder getters/solver调用均0；真实timer拒绝周期没有reference且关联standby命令；builder内N() barrier期间三类callback等待，解除后第一周期仍使用旧冻结输入/版本，下一周期使用已完成的新输入/版本；正常logging off/on输入、reference与命令一致。

通过既有friend先调用真实旧precheck、再回调、再直接调用真实dynamic入口，是对精确旧交错顺序的确定性建模。它没有声称实际executor会以某概率自然重现，也没有把直接入口调用伪装成真实timer事件。单独的实际timer用例核验正常账本收尾。并发barrier在真实builder持状态锁期间阻塞，getter barrier仅测试线程控制，不是生产hook；不能据此获得TSAN或全程序无数据竞争结论。

**已报告测试修正：** `CallbacksWaitDuringFreezeAndNextCycleUsesNewVersions` 保存 `const auto & first = references_.front()`，第二次 `reference_run()` 向同一 `std::vector` 追加后再读取 `first.received_odom_sequence`。追加可能reallocate，使该引用悬空；应保存值副本或先保存所需sequence。测试本身的未定义行为不能作为生产修复失败或通过的有效证据。

**建议补充的兼容性用例：** 实际fake solve已entered后调用真实path clear，完成当前冻结solve并验证原策略没有取消，随后真实timer周期验证no_solve/no_reference/standby。旧F4 `ExactFrozenReferenceSuppliedToSolver` 在在途solve中只替换为另一条有效path，clear发生在solve完成后，尚未直接覆盖这个边界。

旧 `DeadlineControl::make` 只写数值state/path并直接调用dynamic入口，没有真实odom/path_received/FCU资格；新gate正确拒绝该不完整fixture。测试应通过真实odom/path回调建立资格，显式设置fixture的FCU与timeout假设，不应松动生产gate。ResearchContract已设置FCU/timeout并通过真实odomcallback建立资格，未见相同问题。

## 5. 当前GO与停止条件

允许根任务在严格F4身份门禁通过的现场应用此局部生产patch；修正测试引用、补齐旧fixture后执行旧新C++回归及格式检查。实际diff若只有已审局部变化且全部节点测试通过，才可新冻结 `F5_20261005_atomic_freeze_01`，生成绑定F5源码、编译测试binary与GTest报告的新source-capture证据，再运行新正常baseline。

现场guard/唯一锚点失败、新增state→output锁、新参考/数学/预算变化、clear/单点仍进入solve、异常summary/cycle关联、旧新回归失败、引用悬空未修、沿用F4证据冒充F5，均须停止验收并保留诊断。一个正常pilot只能说明该运行契约、计数和来源链通过，不证明竞态概率为0、同步求解最大阻塞或实际plant时序。

本轮完成后的下一P1工作仍是独立solver worker与不可变任务、状态/参考/模型/任务版本门禁、独立固定执行tick和唯一输出、临时fallback从最后实际publisher锚点约束变化，以及阻塞/迟到/乱序/失效/版本变化/生命周期故障注入。零推力publish不能直接解释为船停下；stop observer的收尾窗口也不能解释为固定tick监管机制。
