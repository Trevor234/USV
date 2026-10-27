# DecisionEnqueue 首次失败最小修复：独立源审查

日期：2026-10-08。审查者：独立只读子任务。范围为本轮 `generate_sources.py`、普通/诊断候选源、同构旧源负例、`tests/test_enqueue_branch.cpp`、CMake、执行前反思及构建模板。仅读取本地文件和计算哈希；没有连接 Ubuntu、执行远程进程、运行编译/测试，也没有修改 B0/B1/C0/R5 冻结资产。本文是本轮新增审查记录，不替代运行验收。

结论：修复候选的实际业务连接、清槽顺序和锁序在当前源审查范围内成立；旧负例保留原失败逻辑。发现 v1 的重复播种测试夹具有确定错误，已向主任务报告。正例验收必须使用独立修订的夹具再运行；不能据本次静态审查宣布测试通过或正式阶段通过。

## 审查对象与独立核实

| 文件 | 独立计算 SHA256 | 结果 |
| --- | --- | --- |
| 冻结 B0 `safety/regulator.cpp` | `1163a651580bde314e8b450d39213c1691187fbe977debe63a0366c6e027eb8c` | 与生成器固定父源一致 |
| 冻结 B1 `diag/regulator_r5_diag.cpp` | `a67d65fdde95ff754ca26d0bffe93e12f2cfbce9d8943d6cf01047b499e34cdb` | 与生成器固定父源一致 |
| 新普通 `src/ordinary/regulator.cpp` | `7abfaf03722499bbe9d28da19d050404667682ff3918813d2133b98dadfd8477` | 与 source_manifest 一致 |
| 旧普通适配 `negative/ordinary/regulator.cpp` | `18ed3c31a6422b4386502938b6f74cdb9099797fcbaa7287f57ac18cf6eed579` | 与 source_manifest 一致 |
| 新诊断 `src/diagnostic/regulator_r5_diag.cpp` | `a38d563a52570f11da9e68b5743c6c1989b26e77508620358ad3e402bd0a8a3b` | 与 source_manifest 一致 |
| 旧诊断适配 `negative/diagnostic/regulator_r5_diag.cpp` | `a5b63e8e055e7e2da8dedf81fd899705c255b39831b4759c8d1fd0f31d6c83f5` | 与 source_manifest 一致 |
| 生成器 | `1b1e98326f3b453b9812fc5bf2cd18a780a45dc7291a3cc40cae0182476ea54c` | 本次已读版本 |
| v1 测试夹具 | `dc6f11f84ca231ecc970b39ce4cb889a1e874e5c0dd6e42bcc0a1bfcf30e25b1` | 本次错误定位版本，后续修订应另留身份 |

已核对 B0/B1 的九份公共 `.hpp` 文件哈希相同，生成器为诊断副本复制 B0 公共头文件不会在当前版本改变 B1 公共逻辑。诊断专有 Sink/Witness 来自 B1。生成器使用父源完整哈希并以 `xb` 写入新文件，未覆盖冻结来源。

## 实际业务来源与退出连接

冻结两个源中的 `if(!sink_->add(decision_json(d),d))` 提取起点各出现一次；提取终点为紧随原停机判断的 `sleep_until_monotonic(planned+DEADLINE+1)`。完整提取块包含真实 Decision add、原下一 Preparation 门和原零输出/原 shutdown grace 退出判断，未以镜像 reset helper 替代业务路径。

新普通 `finish_tick` 位于源第267行，真实 `tick_loop` 第328行调用；新诊断 `finish_tick` 第320行，真实 `tick_loop` 第395行调用。`true` 对应原同拍 break；`false` 后仍执行原截止提交、后续 tick。诊断原直接退出前的 `audit_tick` 被放到该 `true` 返回分支；继续路径的原 `audit_tick` 保留在截止提交之后。测试包含同一实际源并调用该方法，所以可以覆盖已提取且与生产循环连接的业务尾部。

新的 `const Decision&` 只读参数与原尾部使用相容。调用仍发生在原 `publish(d)` 及 Decision 收尾之后。本修复不能回滚当前拍已经提交/发布的动作，源审查也不把它作为输出撤销机制。

## 清槽和锁序

普通新失败块在 Sink 返回 false 后才取业务 `mutex_`，锁内设置 normal=false/stopping=true，保留原首次 `stop_start=now` 策略，然后无条件调用既有 `invalidate_locked()`。该函数清真实 Admission ready/committed、candidate，再按业务锁→prep锁清 pending。只有清理完成并释放锁，才执行后继门和 direct exit 判断。

诊断采用同一业务顺序，在真实清理之前记录第一次 DecisionEnqueue Stopping 快照；无条件清理之后记录第一次 Invalidation 快照。`phase_locked` 暂取 prep 锁读取真实 pending 后释放，不把 prep 锁跨越到 `invalidate_locked`。首次 Witness flag 限制记录次数，不包住实际 reset。新增 `stop_phase_recorded_=true` 防止由后续 TickStart 再补一份首次 Stop 记录；原全局 Invalidation flag 保留 TickStart 先发生时的原观察者。

真实 Sink add 返回时已释放 queue mutex；Sink 写线程不反取业务 mutex。prepare pop/wait 期间的 prep 锁在进入业务提交门之前释放。新路径没有引入相反的 prep→业务双锁持有顺序。当前静态检查没有发现新增锁环。业务互斥锁仍可能有调度等待，此结论不提供硬实时的失效延迟上界。

prepare 栈上的已 pop 工作不在共享 pending 中。它仍由原最终提交门在业务 mutex 下重新检查 stopping/sink.failed。清槽先持有业务锁时，之后进入门的未提交工作被拒绝；先前已完成提交授权的锁外 DDS 尾部仍按原合同处理。源码保留此门，只读审查不能替代真实 pop/submit 并发验证。

## 旧负例是否保留

独立比较冻结尾部与适配负例：普通尾部仅将唯一 `break` 转为 `return true`；诊断尾部仅将原 `audit_tick(...);break` 外提到真实调用点并转为 `return true`。这样得到的完整尾部逐字存在于两个负例中（普通1374字符、诊断1610字符）。旧 DecisionEnqueue 失败块未补 `invalidate_locked()`，旧诊断失败块也未补首次 Invalidation。

这两个负例是冻结旧业务逻辑的同构尾部适配，具有相同测试构造与提取方法；它们不是冻结现场旧 binary。旧首次失败零输出用例必须在共享槽净空断言失败，不能把预期负例失败计作生产通过。当前远程构建模板只给负例运行 `FirstFailureZeroExitCleansAllSlots`；该负例覆盖旧槽清理缺项，未另外检查旧诊断缺首次 phase8 的负例断言。

## 确定的 v1 夹具错误

`RepeatedFailureAlwaysClearsNewlySeededSlots` 首次 `populate` 使用 Ticket id41；第二次 `populate` 又使用 id41/42。真实 `Admission::invalidate()` 只清 ready/committed，保留 `seen_` 历史。第二次注册 id41 会返回 duplicate，夹具随后抛出 `fixture admission`，还没进入第二次 `finish_tick`。这是测试夹具错误，不能解读为修复业务逻辑再次失效。

最小修正是让重复播种使用新的递增 ID，并让候选 fixture 与新 ID 一致；不要清 Admission.seen/cutoff 历史改变生产语义。主任务已确认另建夹具修订与测试身份，保留原 v1 失败证据。本文未运行或核实后续修订，因此本次测试通过结论保持待验。

## 测试和构建的证据范围

| 当前用例/检查 | 能支持的结论 | 不能支持的结论 |
| --- | --- | --- |
| 真实源 `finish_tick`、真实 Admission/candidate/pending、Sink 返回 false | failure 分支在同拍退出/继续前清共享槽；ready/committed/双槽情况有定向断言 | 完整输入、native solve、callback、activation、DDS 和输出图压力验收 |
| 非零输出与原 grace | 既有退出谓词保持，清槽不依赖下一 TickStart | 墙钟停机延迟或物理零输出到达证明 |
| Sink close 后 add 拒绝 | 真实 Sink add=false 路径及 source.failed 状态 | 生产日志容量压力、正常 source/Witness 完整性 |
| 普通 capacity0 | 测试构造下真实低层队列容量拒绝 | 正式配置支持容量0；正式资源契约要求正容量 |
| 诊断 capacity1、有限 pause、真实队列满 | 定向分支的首次 DecisionEnqueue fail，以及 phase5脏/phase8净空来源顺序 | 完整 ROS 图中实际首失效时序，合成 Witness 身份的运行资格 |
| `PendingAlreadyPopped...` 的 pending=false | pending 已空时清其他共享槽的容忍性 | 真实 prep 线程 pop 后最终 submit 门竞态；测试没有执行这个线程 |
| `SuccessDoesNotStopOrClearSlots` | 本次 add 成功不误停止/清已有槽 | 后继 Preparation 成功入队；夹具 worker_valid 默认为false，相关分支未进入 |
| `BusinessGateWaitsForPrepSlotClear` | failure 清槽等待 prep 锁期间持续持有业务锁；解锁后可完成 | 真实 callback 再填门的并发拒绝，所有生产锁序的压力验证 |
| Prior/repeated failure 的状态断言 | 修订夹具后可证 reset 幂等与 stop_start 保留 | 当前用例未读取 Witness，不能据此宣布首次 phase 去重/来源不变已动态证明 |

诊断 queue 用例读取真实 phase 并检查净空前后值；当前仅布尔检查是否观察到 phase5/8，没有检查每种 event 恰好一次。若最终文本要宣布“首次各一次、重复/原 TickStart 来源保持”，需相应动态断言；否则限为源码 flag/顺序审查，不能将未测内容计入覆盖数。

CMake 的两个发行目标仅包含候选运行源，未定义 `P1_ENQUEUE_BRANCH_TEST`。该宏在测试 TU 中定义；源中的 friend/专用构造均受 ifdef，发行程序无新配置或测试参数。构建模板只以正常 RelWithDebInfo 配置，未全局注入测试宏，并预备读取各目标 `flags.make`；静态规则支持发行构建不含测试入口，实际构建结果和哈希还需用本轮记录核实。本审查没有检查发行 binary 的预处理产物/符号。

测试由外层监督和 CTest TIMEOUT30 提供有限进程上界。async 用例内部的1秒 wait 是局部断言，不能据它保证所有 future 析构无阻塞；不要把它写成硬实时性能证明。

## 建议的通过口径

在修订夹具正例通过、两个保留旧逻辑负例在预定净空断言失败、发行构建身份和无测试宏证据锁定、新正常 ROS 对照严格通过并且历史 guard 无漂移之后，可记录“普通/诊断候选的首次 DecisionEnqueue 失败共享槽退出边界已完成源级修复和实际源链接分支回归；新版本有限正常 ROS 对照通过”。

上述不同证据应分别写清。分支回归不覆盖完整 ROS 图首失效压力次序；正常对照不触发该故障分支，也不能补成其压力验收。真实 pop/submit 并发、callback 竞争以及 phase 重复去重若未运行仍保留未覆盖。B4/B5、正式 M0b、M4/F6/P1、物理执行资格不因此晋级，历史 C0/R5 结论与阈值不改写。
