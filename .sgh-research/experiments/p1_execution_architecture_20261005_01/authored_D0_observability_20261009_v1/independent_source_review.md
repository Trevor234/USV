# D0 隔离观测源码独立审查

审查日期：2026-10-09。审查方式：只读源码、直接基线差异、文件身份及测试定义核对。未运行本地或远程测试，未启动 ROS，未修改源码、旧报告、生产目录；未读取 packedremote 文件或其中的编码载荷。

**结论：未发现本轮所审冻结源码的具体静态阻断。可以进入新隔离二进制的 `no_output`、`diag5` 机制验证；本结论不授予 D1 shadow、execute、物理输出、动态模型质量或实时行为等价资格。** 此处“保留”指原控制公式、条件、理由优先级、失败清槽顺序和记录身份布局在直接差异中保持；新增观测确实增加运行负载，后续必须以新二进制的实际证据检验。

## 1. 输入、谱系和审查边界

新目录为 `m0b_D0_observability_20261009`，直接基线为 `m0b_enqueue_invalidation_20261008`。审查覆盖：`source_lineage.json`、`create_d0_source.py`、`src/diagnostic/regulator_r5_diag.cpp`、根目录与诊断目录的 `p1_d0_observation.hpp`、两个测试文件、`CMakeLists.txt`，以及继承的诊断头文件身份。声明字段作为待核验数据使用，没有仅凭 lineage 中的布尔声明给出结论。

| 本轮文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| source_lineage.json | 1480 | `1491d73cf4fcb904710e3428af0497e34fef0d8782c948a812bdb3308a6ea486` |
| create_d0_source.py | 5557 | `364cbcfd4dfb5dde72d4d33fb51c2d24331d5a02362b5c57494cf7da77f918e1` |
| src/diagnostic/regulator_r5_diag.cpp | 61694 | `9265108fe2abed1b2d27a7cdb670e7529740286124fc74da60ca059402d0f7db` |
| p1_d0_observation.hpp，两份相同 | 3595 | `ad181ad4a510b8c7e0343d179ade689abef10eeaaeec69002b56068d74920527` |
| tests/test_d0_observation.cpp | 6402 | `6c9e4606670f35ec5069f998769cf7fba7ffde9815fd5e740a4f5bf1f3ed5955` |
| tests/test_enqueue_branch.cpp | 8704 | `9909f8892ef84891519842056d05afa4f984311e9976ff4801554e88932494bc` |
| CMakeLists.txt | 1425 | `593b234680e7331ac2e8b29b97642077416a106ec40bf95dbb85a13b079238b0` |

直接基线诊断源码的 SHA-256 是 `a38d563a52570f11da9e68b5743c6c1989b26e77508620358ad3e402bd0a8a3b`；基线普通 `regulator.cpp` 身份是 `7abfaf03722499bbe9d28da19d050404667682ff3918813d2133b98dadfd8477`。实际计算与 lineage 对应值一致。

生成脚本先对直接基线诊断源码作精确 SHA 断言；每个定点替换要求原片段只出现一次；继承文件与新输出使用排他创建。脚本的目标是新隔离目录，不包含生产安装或远程启动步骤。直接源码差异与其声明的九项改动一致，没有发现悄然替换基线为旧修复前源码的情况。

11 个继承头文件均与 FIX 对应文件字节相同：`p1_admission.hpp`、`p1_capability_lease.hpp`、`p1_clock_window.hpp`、`p1_diag_sink.hpp`、`p1_full_contract.hpp`、`p1_preparation_barrier.hpp`、`p1_resources.hpp`、`p1_tick_barrier.hpp`、`p1_witness.hpp`、`p1_worker_liveness.hpp`、`protocol.hpp`。其中关键身份为：

| 继承文件 | SHA-256 |
| --- | --- |
| p1_admission.hpp | `14c6087674c6c906e0353b556a8c712bde7b6d7a6cef6f18e5047a1f90c5b557` |
| p1_diag_sink.hpp | `4a607820a5e7ce1f047d559bcde72965926f4e9d7d86a8ec20cd39add03c2a79` |
| p1_witness.hpp | `c114df7d6c587e389ebdacc7344536e7f00dca81cc8dea2d352dac4ada6d6a93` |
| protocol.hpp | `f565b4a9b6867e27c7d3ab395a6d91163d02a8d2bbe49fc6134010afd64bb7db` |

`tests/test_enqueue_branch.cpp` 也是 FIX 的字节相同副本。源码谱系可核对。本审查先完成静态核验，随后只读收到的 build_result.json；该记录的构建和针对测试事实另列于第 6 节，不据此授予 ROS 运行资格。

## 2. 隔离门与业务范围保留

实际运行构造函数在第 50 行保留三项入口条件：`mode == no_output`、`schema == p1-execution-contract-v2`、`diagnostic_contract_revision == 5`；不满足即抛出异常。此门位于物理 publisher 和 source/sink 创建之前。默认 shadow 不会绕过此门。原本仅 execute 路径创建物理 publisher 的代码保留，但本诊断入口不能进入 execute。

原 audit 默认关闭、pause 参数范围、源/二进制/worker 身份约束、Witness header 不完整拒绝等继承逻辑未在本轮差异中改动。测试专用构造入口仅由测试翻译单元中的 `P1_ENQUEUE_BRANCH_TEST` 启用；运行目标没有定义此宏。因此测试夹具的构造便利不能作为实际运行绕过隔离门的通路。

直接差异没有改动预测模型公式、候选控制映射、命令检查、fallback、发布函数、worker 接纳协议、能力续期协议或正式消息生成。CMake 为独立诊断源码及两个测试目标链接现有依赖，没有 `install()`、普通 regulator 目标或正式消息修改操作。

## 3. 观测来自实际验证快照，最终来源保留内部原始 IMU

tick 在原业务互斥锁内执行实际 `s = snapshot_locked(now)` 后，立即记录 `copy_capture_ns`，然后才执行原 `admission_.take(...)`。序列化的 `validation_snapshot` 使用这个已有 `s`；没有从最终成员重新构造早期验证状态，也没有拿候选作业快照充当本次激活快照。

必须保留两个时间字段的不同含义：`sample_ns` 是原有 `snapshot_locked(now)` 传入的采样参数，`now` 在取得该业务锁之前已取值；新增 `copy_capture_ns` 才是锁内复制完成后的时间。`capture_semantics = mutex_copy_end` 对应新增复制完成标记，不能把原 `sample_ns` 解释为锁内所有字段读取的精确完成时刻。两者并存避免用新增时间覆盖原业务参数。

validation 载荷包括当时的状态六维、来源版本、odom/IMU 原始序列与时间、时钟、混合 IMU 标志、anchor，以及本次预测使用的 held history。最终 `capture_final_source_locked(final_source, commit_now)` 在原最终业务锁内调用，复制最终来源标量和 `commit_now`；没有在释放锁后追读可变化成员。final 载荷是来源快照，不宣称保存最终状态向量或另一次动力学预测。

内部 IMU 来源与规范 Decision 投影的差别保持清楚：观察载荷会保存 `mixed == false` 时仍存在的原始 IMU 序列、stamp、receipt；规范 `activation_imu_*` 继续按原条件置零，`activation_r_from_imu` 继续记录 mixed。新增原始观测未改动是否采用 IMU 的业务决定，也不能把原始 IMU 非零误读成该候选使用了 IMU。

当前输入版本变化门仍在同一最终锁内判断，且只在原 `reason.empty()` 短路位置运行。新增 `input_change_gate_ran` 记录该门是否实际到达；未到达时 `input_change_gate_unchanged` 是 null；运行后 false 仍序列化为 false，未被 optional 的存在性判断误写成 null。

## 4. 原 state_check 理由和部分误差保持，完整误差另行计算

实际 `predict(aligned, cand->job.target_sim_ns)` 调用位置保留。失败仍只在原 reason 为空时设置 `activation_history_or_time`；成功仍将实际 aligned 状态复制到 `d.activation_state`，调用原 `state_check(t->prediction, d.activation_state, limits_, &d.state_error)`，并按原 reason 优先级接纳或保留先前拒绝理由。

原 `state_check` 在首个非有限或超容差维度处早退，因此规范 `d.state_error` 可能只填充前若干维。D0 没有为了补齐误差而继续执行原业务检查，也没有用新的完整误差替代原判定。helper 独立计算 `actual - target` 的六维差，航向维使用同一个 `p1::wrap`。其输入是实际成功预测后保存在 `d.activation_state` 中的结果与本 ticket 的目标状态。

可用性标记与 null 符合保守语义：

- 没有 candidate/ticket 配对：不执行预测，状态为 `not_attempted`，候选标识、预测目标时间、预测状态和完整误差均按相应可用性置 null。
- 实际预测返回 false：状态为 `history_or_time_failed`，预测状态与完整误差为 null，不能以初始化零数组补造有效样本。
- 返回 true 但预测状态非有限：`predict_success` 仍忠实记录返回值，`predicted_state_available` 和 `full_error_available` 均为 false，数组不作为有效数据发布。
- 预测状态有限而目标非有限，或六维减法溢出：完整误差不可用并输出 null；有限的预测状态可以独立保留。
- 有效零误差由 available 为 true 的零数组表达，与缺证 null 可区分。

helper 的宽泛失败状态并不细分所有历史失败原因；精确业务 reason 仍在同一个规范 Decision 中。已有其他门拒绝时，即使观测预测成功，也不意味着候选可接纳或获得了动态跟踪资格。

## 5. 同一个 Decision 入队，Witness/typed 布局和已修清槽分支未改

`finish_tick` 新增可选观察指针，先调用原 `decision_json(d)`，再把 `d0_observation` 作为该 JSON 的一个嵌套属性，然后仍以同一个 `d` 调用一次 `sink_->add(std::move(source_row), d)`。没有为 D0 另加一个 sink 事件，也没有新增 typed Decision 字段、额外 candidate 事件或独立 Witness 记录。

因此去除新增嵌套属性后的规范 Decision 投影保持原定义，源事件与原 Decision 身份对应；正式消息、protocol 与 Witness 布局均未修改。日志条目数量不因每个 Decision 的嵌套观察增加一条，但每个条目的大小、分配成本和写入耗时会增加。

affected enqueue 的关键顺序保留在第 329–344 行：source 入队失败并且 sink 已释放自身队列锁后，取得原业务锁，设置 stopping/normal incomplete，记录一次 `StoppingObserved/DecisionEnqueue`，执行真实 `invalidate_locked()`，再记录一次 `InvalidationObserved/DecisionEnqueue`。原下一次 preparation 授权仍有两层 stopping/worker/sink 门；零目标的同 tick 直接退出与非零既有 grace 分支位于真实失效之后。没有把清槽挪到一个可能不会出现的后继 TickStart，没有依靠补造 phase 假装失效。

新增 JSON 构造在原 `d.tick_end_ns` 之后、实际 finish/入队之前；这保留原 Decision 的结束时间语义，却意味着其 `tick_end_ns` 不能单独代表新观测、排队和退出处理的完整耗时。完整 tick 的 Witness 审计位置未移动：直接退出仍先完成 finish，再执行 `audit_tick`；正常路径仍走原 cutoff 后审计。后续时序检查必须继续使用正确的完整包络，不能换用更短的规范 Decision 区间。

## 6. 针对测试的覆盖和局限

静态核实有 8 个 D0 测试，以及 enqueue 文件中的 11 个文本测试定义。后者第 69–73 行通过 P1_DIAGNOSTIC_TEST 互斥选择第十例：诊断目标运行 BoundedQueueFirstFailureTakesDecisionEnqueue；普通分支选择 CapacityRejectFirstFailureCleansBeforeExit。因此本轮 CMake 诊断目标实际包含 10 个 enqueue 测试，加上 8 个 D0 测试共 18 例，无须同时运行两个互斥分支。测试通过 `P1_REGULATOR_SOURCE` 直接包含本轮实际诊断源码，使用 friend 访问实际 snapshot/predict/final capture/Decision projection/finish 边界，而非另写一份模拟业务实现。两个 CMake 测试目标各有 30 秒超时；运行目标不启用测试构造宏。

| D0 测试 | 所针对的问题 |
| --- | --- |
| ValidationSnapshotCannotBeBackfilledFromFinalMembers | 早期实际验证状态及 history 不被后续成员变化回填 |
| InactiveImuIsRawInObservationAndMaskedInCanonical | mixed=false 的内部来源可见，规范投影仍为零 |
| MissingCandidateIsExplicitNullRatherThanZeroSample | 无候选不伪造有效预测零样本 |
| ActualBackwardPropagationFailureCannotProduceZeroSample | 调用实际 predict 的倒退时间失败与 null |
| CompleteObservationSurvivesOriginalFirstDimensionEarlyExit | 原 state_check 首维早退保留，独立六维误差完整 |
| HeadingCrossingPiUsesWrappedFullDifference | 航向跨 ±π 的统一 wrap |
| NonfiniteAndSubtractionOverflowHaveExplicitAvailability | 非有限状态及有限输入减法溢出的可用性 |
| DecoratedDecisionSharesOneEventAndKeepsCanonicalProjection | 一次实际 finish/source 事件、规范投影相同、optional false 保留 |

本轮诊断分支的 10 个 enqueue 测试覆盖首次失败的同 tick 零退出、ready/committed/pending 槽失效、非零 grace、先前失效/重复失败的幂等行为、成功不清槽、prep 锁边界及真实有界队列拒绝进入 DecisionEnqueue 路径。第十例还检查实际 Witness StoppingObserved/InvalidationObserved 的 observation code 和清槽前后真实状态。普通分支的容量拒绝例在本轮未构建，不作为诊断目标的额外第十一例。

只读 build_result.json 记录本轮 configure、compile 和两个测试目标返回码均为 0，10 个 enqueue 与 8 个 D0 用例的名称完整列出，expectation_met 均为 true，failure 为 null。其源码/CMake/测试哈希与本报告输入一致；新 regulator binary SHA-256 为 ef101b9ee48b6bc552125700341385e6284b1b5ee0820ff6374b3dc136538ef8。记录中前后守卫均为 3067 项、drift 为空，各步骤回收完整，owned_cleanup_complete 为 true。本审查者没有执行这些命令，也没有独立远程复跑；这里准确引用已落地的构建记录，报告身份见下方。部分 D0 测试直接验证 helper 和源码边界，不覆盖整个 ROS tick 生命周期；例如 inactive IMU 测试本身不能代替真实运行中规范字段构造的检查。针对测试已记录通过，受控正常无输出运行与完整 ROS 压力资格仍需各自证据。

构建记录身份：`build_result.json`，14207 字节，SHA-256 `fd7b37d5609b723036145aec87d03786685d7b3b95342593e6d8eca368675e87`。记录列出的两个测试 XML SHA-256 分别为 `b682d8517e6b73391344f431b60e2fc482579cdf52c44581733ccf52be228fd5` 与 `48ddea99c58f713dadb4654c49e49e2cb44e6b70bab83e466dcd21d90e47bd26`；此处未把摘要引用描述成重新执行测试。

## 7. 本轮正常无输出机制验证和后续资格边界

没有需要先修源码才能开始 no_output 机制验证的具体静态缺陷。本轮事前范围是已执行的 18 个针对测试，加一次 10 秒正常 no_output 验证；本静态审查不新增本轮必须执行的 ROS 压力矩阵。当前执行和后续资格应保留以下边界：

1. 构建本报告所列新源码和 helper，固定新 regulator 二进制身份，同时固定实际运行 worker、contract、boot/run/worker instance；保留新 CMake、测试与生成谱系身份。不能把旧二进制 hash 当作本轮 binary hash。
2. 保存本轮实际 8+10 共 18 例的退出码、名称、摘要及报告身份；本地构建记录已记录全部通过，不能误报为 19 例，也不需要为本静态审查重复运行。互斥的普通容量例不作为当前诊断构建的缺失用例。
3. 对事前声明的单次 10 秒 no_output 正常运行，核对每条真实 Decision 的嵌套观测、配对身份、validation 与 final 的时序/来源、空值规则、mixed=false 原始 IMU 与规范零投影；同时保留原 source、实际 bag、Worker/Witness 和生命周期回收的独立门，不仅检查新增 JSON 能解析。
4. 本轮 native 的诊断队列测试已记录真实 DecisionEnqueue fail/stop/invalidation 和槽状态验证；不把它冒授为完整 ROS 压力资格。后续如需为统一新版本重新授予 affected pressure/close 资格，须另行事前声明，并获取本轮二进制的真实压力、完整 tick 和 close 证据。该后续资格保持 pending，旧 FIX、C0/R5 结果仅作为谱系，不能自动继承；预期失败报告及 source/audit/实际返回码仍应分列。
5. 不改阈值或判定规则来迁就新观察负载；如果机制或时序门失败，记录失败，再定位原因。通过 no_output 也只证明该机制与观测契约，后续 D1 shadow 仍须独立事前声明与审查。

额外 Snapshot 对象、完整误差运算、history/JSON 构造与复制、以及更大日志载荷都可能增加锁内停留、CPU/内存使用或队列写出时间，影响 jitter、输入在两次锁之间变化的概率和压力触发位置。新增计算没有改变公式，不等于实际调度行为与旧二进制等价；capacity 仍是 512 条事件，也不等于原有字节占用或 logger 吞吐相同。本审查仅允许在保持隔离门和原独立门的前提下获取这些新证据。