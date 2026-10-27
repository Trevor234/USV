# B2/C0 事前范围与源记录语义审查

审查日期：2026-10-08。结论：**本批范围与当前主计划 B2 一致，未发现需要更改业务源码的事前范围阻断；实际 launch 仍须等待新增比较器最终静态审查、必要工具测试、资产与主机门全部闭合。**本报告没有执行测试、远程连接或实际 C0/R5，也没有改变生产入口、B1 工具、旧审查或旧证据。这里只新增本报告。

本次审查发现两组合法且必须保留的时间差：source Job 的 `submit_commit_ns` 是最终提交门之前的时间采样，Witness Submit 的 `commit_ns` 是真实授权存储之后的时间采样；source Decision 的 `end_ns` 是本次业务决定的计算尾部，Witness Tick 的 `end_ns` 是包含 source 入队、下一拍准备请求、停止分支或 cutoff 等尾部的整拍结束。若比较器要求这两组字段相等，将构造假失败；若删掉对应检查，则会漏掉真实错误。应按下面的源顺序和时间包围政策比较。

## 1. 审查输入与身份

读取主计划 `C:/Users/sgh/Documents/MPC/P1_M0b_参数来源与政策表及最小校准计划_2026-10-07.md` 的 B1、B2/B3、相关 checklist 与最新附录。主计划本轮读取 SHA256 为 `ad266d0d0222c1bb6130c552f4ebfed5f1eee0d97204302b154161b9e0e3dc61`。正文前部仍有“下一步 B1”的历史字样，而 2026-10-08 的 checklist/附录已记录 B1 完成；本轮应引用最新 B1 事实与当前 C0 事前声明，不能把历史摘要当成未交付判断。

相对本工作区的主要输入如下。SHA256 为本轮本地读取结果；Ubuntu bin 与关闭清单值继承 B1 最终归档，仍须 root 在实际 C0 前后重新验证。

| 输入 | SHA256 |
|---|---|
| `m0b_witness_implementation_20261007/diag/regulator_r5_diag.cpp` | `a67d65fdde95ff754ca26d0bffe93e12f2cfbce9d8943d6cf01047b499e34cdb` |
| `diag/p1_witness.hpp` | `c114df7d6c587e389ebdacc7344536e7f00dca81cc8dea2d352dac4ada6d6a93` |
| `diag/p1_diag_sink.hpp` | `4a607820a5e7ce1f047d559bcde72965926f4e9d7d86a8ec20cd39add03c2a79` |
| `diag/CMakeLists.txt` | `ca02dc2c28459690dcdd2aa165e5e4ec35a032e18bef952636c389bb0906b4a5` |
| `runtime/run_r5_diag_validation.py` | `c8bc0141e3ad7b37ff07b1e3ce440c47b01e4386b90bf9f362beda1922ea0766` |
| `runtime/check_p1_witness.py` | `fb13fe66b8f996f96bac72e96eaa6a1b1f21f27af19a8b62b2dac13bc273596f` |
| `final_complete_evidence_20261008.json` | `2d34adaf5c8902f8d6737a5806a70a2ab485c82218f7b1fd8461c5ac2211a88f` |

B1 最终报告记录：当前诊断可执行文件位于 Ubuntu `authored_B1_diag_20261008_v3/build/p1_regulator_r5_diag`，SHA256 `43c6cb4ec96e825e0a03701f5aa3044ec1ebadd4568f49190e53607738aa40ab`；原基线源 SHA256 `1163a651580bde314e8b450d39213c1691187fbe977debe63a0366c6e027eb8c`，绑定当前 B0 v14。不能退回 v13 作为本批参考。B1 记录 37 项新 C++ 测试、63 项相关 Python 测试、9 项实际启动拒绝，以及 Witness 实际总大小 54728 bytes。这些是继承的已归档事实，不是本审查再次运行的结果。

完整 runtime 为 49 个文件、同目录依赖齐全。最新 B1 关闭守卫包含 2340 项，清单 SHA256 `87323918705c45cbf09cd61645a22ab174d5e3d55d5a83b2aae2c614e912159f`；原 B0 1908 项清单与旧失败构建/测试原件继续保留。当前归档明确 `C0_run=false`、`C0_complete=false`、`R5_run=false`，不能从 B1 工具通过推导真实 source/Witness 对应已验证。

## 2. 本批声明与授权边界

主计划 B2 要求同一 B1 诊断 bin、完整 diag5、512 Sink 队列、暂停钩子关闭，旧合法 50Hz synthetic fixture，业务就绪后正常测量 10s。这里“hook 关闭”必须具体落实为 `test_delay_ms=0`、`test_native_block_ms=0`、`test_prepare_block_ms=0`、`test_tick_block_ms=0`、`test_sink_pause_ms=0`。Witness 需要显式开启才有逐项比较证据；它的启用不等于启用 logger pause 或故障注入。

本批按 `mode=no_output` 运行，不发布两路物理推力。实际声明值须是 10s；runner 支持的其他较短合法时长不能作为本次 B2 的完成替代。窗口从真实 recorder/fixture/source/worker 就绪事实启动，结束原因须为 `declared_duration_elapsed`，实际 monotonic 时间至少覆盖声明 10s。operator stop、启动超时、watchdog、源失败、审计 incomplete 或 owned 清理失败均不得借“收到了若干数据”转为正常通过。

C0 前须保存 run_id、新独立目录、政策与比较器身份、10s 声明、bin/source/worker/contract 摘要和独立 expected header。输入资产和政策不能运行中改阈值或延长直到通过。root 的 `preflight_reflection_20261008_C0.md` 已明确以上门，也明确只有一个事前声明的正常批次。

C0 不执行 R5，不要求队列实际达到 512 或故障后的停机反应覆盖，不修复已知 Decision 入队失败后可能未清 candidate/admission/pending 的业务缺口。C0 正常无 drop 只能验证审计对照，不能证明队列压力机制。R5 的真实溢出、失败前至少五拍、220ms 业务观察、暂停最多 5s、停止后的增量与真实失效状态需另批验证。`normal_contract_complete`、`plant_acceptance_observed`、`execute_qualified`、R5 mechanism 和正式冻结资格继续为 false。

## 3. Source 与 Witness 的真实比较点

### 3.1 Tick：决定结束与整拍结束分别比较

`regulator_r5_diag.cpp:124` 的 `audit_tick()` 从 source Decision 复制 job/tick/版本身份及 planned/start/skipped，随后在调用点采样整拍结束。`regulator_r5_diag.cpp:363` 的 source `d.tick_end_ns` 则在 publish 后、source Decision 入队前采样。正常路径在 source 入队、准备请求之后等待 `planned+DEADLINE+1`，执行 `admission_.cutoff()`，才记录 Witness Tick；停止分支则在真实 shutdown 处理后记录最后 Tick 并 break。

因此完整 owned Decision 与 Tick 要一一对应，至少检查：

- 原始 Decision sequence 连续/唯一、Witness stream sequence 完整；tick 以 schedule generation 与 tick 身份唯一匹配，重复与多余行不能被 dict 覆盖掩盖。
- run/boot/contract/worker 由独立 header 和原 source 检查闭合；job/tick/task/model/config/schedule/epoch 按源字段一一映射；planned/start/skipped 精确一致。
- Witness `candidate_present` 表示该拍实际持有 `t && cand` 这一对最终激活输入，与 source `job_id > 0` 对应。它不是 phase 中仍在共享槽里的 `candidate_present`，不能把两者混为一个值。
- `source.start_ns <= source.activation_commit_ns <= source.end_ns <= witness.end_ns`；witness.end 纳入整拍尾部，不能要求 source.end 与 witness.end 相等。
- 同一 tick 线程的完整 Witness 拍区间不得相互重叠；源检查承担正常 tick 调度/跳拍门，当前 C0 保留既定 tick_jitter 门。

不能用 20ms jitter 预算限制 `witness.end-start`，因为正常整拍结束包含有意的 cutoff 等待。不能仅因正常无候选或停机尾拍而删行；这些拍仍应参与完整日志对照。

### 3.2 Submit：原门前采样与真正授权后采样

`regulator_r5_diag.cpp:286-289` 中，业务 mutex 内先进行 worker 检查，采样 source `submit_commit_ns`，再检查 stopping/source/version/current_tick/deadline/resource。通过后才分配 `job_id`、存入 `jobs_` ledger，并采样 Witness Submit `commit_ns`。释放业务 mutex 后，在 `regulator_r5_diag.cpp:293-294` 创建 source Job 入队，之后才进行真实 DDS job publication，并独立记录 publication result。

每个真实授权 Job 与 Witness Submit 一一对应：job_id、job 的 target_tick/版本/epoch 精确一致，Witness preparation tick 应为 source job.target_tick−1。合法时间关系是：

`source.submit_commit_ns <= witness.commit_ns <= source Job.publish_start_ns <= job_publish_result.publish_start_ns <= job_publish_result.publish_end_ns`

后两个字段来自实际 publication result；正常 C0 的 source 与实际 bag 门应同时要求相应真实发布证据闭合。未提交的 `job_not_submitted` 记录不是 Witness Submit，不应补造授权记录。相反，在正常 source 完整、drop=0 的 C0 中，Witness 多出授权 Submit 却没有 source Job 也必须失败。

这里不额外把 witness.commit 当成旧 source 提交门时间。原 deadline 门比较的是门前 source.submit_commit；如果比较器对授权后采样额外施加相同 deadline，会悄悄引入新的业务政策。可以报告授权后采样与 deadline 的差值，但不能改写原门语义。异步 failed/stopping 快照也是记录时观察，不足以反推更早的源门已经失败。

Source Sink FIFO 表示各线程事件的入队顺序。准备线程授权后释放业务 mutex，到 source Job 入队之间，tick 或 callback 可能合法插入其他事件；DDS reception 顺序也不是授权线性化顺序。比较时采用真实身份与对应时刻关系，不能依赖整份 JSONL 或 bag 中相邻行来推导跨线程 commit 因果。

### 3.3 Activation：同一 final commit 精确匹配

`regulator_r5_diag.cpp:345-348` 在最终业务 mutex 内将同一个 `commit_now` 写入 source Decision.activation_commit_ns 和 Witness Activation.commit_ns；ready_commit_ns 来源为同一个 ticket.ready_ns。仅当 `t && cand` 时记录带 candidate 的 Activation 尝试，accepted 与 rejected 均保留。

每个 source `job_id > 0` 的 Decision 对应一条 Witness Activation，job/tick/当前 Decision 的版本/epoch、ready、commit、accepted 精确一致。reason 采用真实四值映射：accepted→0，`shutdown`→1，`run_unusable_at_commit`→2，其他 rejection→3。此数值枚举没有完整表示所有 worker/eligible 拒绝原因，报告仍应保留 source 原字符串，不能称 reason_code 证明每项具体门。

Activation 与本拍 source 时间区间以及已授权 Submit/ready 的前后关系也要验证。对于 accepted，job 与最终 Decision 的身份必须一致；对于合法 rejected，当前 Decision 版本与早期 source job 版本可能已经不同，不能无条件把两者强制相等。Witness/Decision 当前身份仍须精确相等，拒绝原因仍按实际源字符串绑定。

正常关闭可能包含最后的无候选 Decision、stopping/invalidation/close phase，不能把它们剪掉来保持“全行 accepted”。正常 C0 不允许 pause、overflow 或 sourcefailure phase；在枚举中应具体拒绝 PauseArmed=1、PauseBegin=2、QueueOverflow=3、SourceFailure=4、PauseEnd=6，正常停止观察=5、Close=7、失效观察=8、BusinessReady=9 则按完整性与真实关闭语义验证。

## 4. 完整 owned 证据与 10s 窗口分别陈述

逐项 join 的对象必须是完整 owned source/Witness，含启动阶段、窗口内和有界停止尾部。固定容量 256 Tick、128 Submit、128 Activation、32 Phase 也覆盖完整 owned 生命周期。任何容量满、unpublished、invalid record、after-close 或首失败不能通过切成 10s 子集隐藏。

窗口指标可按事前声明采用 tick.start、submit.commit 或 activation.commit 是否位于窗口等明确规则，并单列边界穿越/右删失；不能把某 stream 的不同时间字段混用。完整 owned 行数通常包含启动与收尾拍，不能硬编码“正好 50/51 拍”取代数据完整性。10s 正常完成与完整生命周期 join 是独立门，两者须同时通过。

原 source/base checker、实际 bag、正常应用 ledger、owned supervisor、close 与 cleanup、physical topics 全 run 0、独立 witness 结构检查、新 source–Witness join 和实际正常窗口分别保存结果。最终 C0 可以是这些结果的合取，但不能修改任何独立失败/unknown 报告。runner 当前 `postrun_checks.json` 明确 `C0_comparison_performed=false`，因为其已有 checker 只做 source 检查和独立 Witness 检查；新比较器必须另交付真实 join 报告才有 B2 通过证据。

Independent expected header 来自 driver 独立读取的 bin/source/contract 和已验证的实际 native worker capability.instance。不能从 Witness 自报身份反向构造 expected 值，也不能用 PID 拼接代替真实 worker instance。policy、context、expected header 与实际输入读取前后应有 SHA 锁，所有 raw/source/bag/checker 结果保持原件；比较器默认拒绝缺项、错类型、重复、额外行和未知尾部。

## 5. 启动前与结束后的必要门

本报告不代替 root 的真实 preflight。实际启动前应确认 2340 项 B1 关闭清单无漂移、当前 B0 v14 和 B1 source/bin 固定、完整 diag5/worker/fixture/runtime 身份匹配；主机 controller/Gazebo/新旧 diag/新旧 fixture/PPO 残留与不可读 cmdline 均为 0。发现非 owned 进程只能拒绝本次启动，不能依据扫描结果杀进程。

运行使用声明的 ROS_DOMAIN_ID=96、ROS_LOCALHOST_ONLY=1；bag/真实 subscriptions 先就绪，native capability 的 run/boot/contract/PID/startup_ns/instance/模型接口与 owned 实际 worker 对应后才 launch regulator。两物理 topics 端点全 run 0，任何新物理 publisher 都拒绝晋级。停止后保留有限录制尾部，以真实 PID/start_ticks/PGID/SID/boot/exe 身份清理 owned actor，清理与 supervision ledger 均须完整；最后重新核验关闭守卫与主机状态。

已有 known gap 是业务失败路径的真实待验项，不是 scope 审查可消除的事实。本次 C0 不触发压力，也不把普通正常停机作为该 gap 的通过证据。若实际 C0 发现比较工具缺陷，保存失败原件，依据本次预先锁定源码语义修工具、升版本、复审后才讨论重试；若发现业务缺口，应另立最小修复，不通过 witness 补造状态或修改原 normal checker。

## 6. 审查结论与未完成事项

本次 root 事前声明与主计划 B2、最终 B1 source 记录点相符；提交与整拍时间差有真实合法源码依据。以上按源顺序的比较政策没有要求新增业务决定、清槽或故障记录，不授予 R5 或物理执行资格。**范围审查没有静态阻断；新增比较器的最终实现尚待独立审查，实际 C0 的采集、原检查、逐项比较与前后守卫尚未由本报告证明。**