# C0 最终 Source–Witness 比较器静态审查

日期：2026-10-08。结论：**下列冻结版本没有未解决的静态阻断，可以进入本次新工具的必要独立测试、受控集成及事前声明的正常 C0。**实际 launch 仍需原 source/bag/base/应用与 owned ledger、正常窗口、物理端点和前后资产/host 门全部闭合。本报告不是实际 C0 结果，也不授予 R5、正式冻结或 physical execute。

审查只读最终比较器、测试定义以及其所依赖的 B1 Witness checker，并核对 B1 实际 source 记录点和旧 B0 checker 职责。没有运行测试、远程连接、ROS 或修改源码/旧文件，只新增本报告。

## 1. 冻结输入与证据范围

| 文件 | bytes | SHA256 |
|---|---:|---|
| `runtime/check_p1_C0_comparison.py` | 23629 | `3738f668b5609b18f14bfb3cab9e0b590a131d6c02ce994663896aad26105b59` |
| `runtime/test_p1_C0_comparison.py` | 23828 | `bad376d3345358995fe20672e085d3e518a91459bde4cf6ed28ad9edc139a39f` |

测试文件静态包含 27 个 test 方法；作者报告局部测试通过。本审查未再次执行，因此实际新工具测试结论应引用单独的运行日志与 manifest。比较器依赖 B1 `check_p1_witness.py`，SHA256 `fb13fe66b8f996f96bac72e96eaa6a1b1f21f27af19a8b62b2dac13bc273596f`；实际 source 为 B1 `regulator_r5_diag.cpp`，SHA256 `a67d65fdde95ff754ca26d0bffe93e12f2cfbce9d8943d6cf01047b499e34cdb`。原 B0 v14/worker/B1 bin 和关闭守卫继续由本轮执行层独立验证。

比较器报告 scope 明确为 `full_owned_lifecycle_regulator_source_to_fixed_witness`。它接收四个必需输入：Witness、独立 expected header、完整 regulator source、driver context，不接收裁剪窗口，也不会从 Witness 自报身份反向生成 expected header。

## 2. 独立 header/context 身份门

先调用现有 Witness `analyze(witness, expected_header)`。该基础门验证严格 header 字段集、受限字符串、boot UUID、64hex hash/实际 worker instance、header 与 expected 完全相等、固定容量、真实 stream accounting、published 行、首失败、完整关闭和 BusinessReady 实际 accepted activation。基础完整性失败必留下 issue；不会仅因部分可读行而把 source_join_verified 标为 True。

比较器再独立检查 driver context schema/no_output、run/boot 与 expected 一致、contract SHA、regulator/worker bin SHA、diagnostic source SHA 与 header 一致。Witness 必须 enabled True，sink pause 必须严格 int0；duration 为数值10，四个 fault 参数严格 int0，expected_fault 为 none，declaration.execute_qualified 明确 False。布尔 False、浮点0 或缺字段不能作为 fault int0 通过。

这验证了三方身份的一致性，不自行证明 expected header 的来源可信。实际 driver 应继续使用本轮已审 B1 runner：独立读取资产、验证真实 owned native capability.instance、在 regulator 前 exclusive 保存 expected header。policy pins、运行前工具 manifest、资产守卫及实际 input SHA 必须由执行层保存；不能复制 Witness header 给 expected 文件作为所谓“独立身份”。比较器 CLI 对四个输入独立读取并保存 before/after SHA，汇总层仍应将其真实字节与事前 policy/expected 证据绑定。

## 3. 全生命周期双向覆盖

完整 source 不按 10s 裁剪。原 source 每行必须为 typed JSON object，支持事件类型使用固定集合，未知事件拒绝。source root 非空且有限；startup、source_summary、regulator_shutdown 各要求恰一条。summary 必须为 source 最后记录、generated/emitted 等于全部 source 行数减一、严格 uint dropped0、normal_source_complete True、finished_ns 合法正 int64。startup schema/run/boot/contract/clock/mode 与独立 header 一致，并明确 no_output、diagnostic_only 和物理端点 int0。

Decision 必需字段、run/boot/contract/worker instance、v2 schema、no_output、diagnostic_only、normal_contract_complete False、严格 uint/时间/accepted bool/reason string 都逐项验证。source Decision sequence 以原 source Decision 行顺序要求从1连续；其真实计划、开始、最终 commit、业务 end 有序；accepted 必须等于 reason 为空。无候选 job_id0 不得接受且 ready 必为0。

Tick 以 `(schedule_generation,tick)` 匹配，允许合法 schedule reset 后 numeric tick 重复，禁止同一 schedule/tick 重复。Submit 与 Activation 以 job_id 匹配。每个 mapping 在重复时先记录失败，不会静默覆盖旧行来掩盖重复；两边 key 集必须完全相等，多出/缺失任一行均拒绝。不会只比较成功 activation、只比较窗口内行或只验证某边为另一边子集。

Witness 结构已经失败时，不把 malformed 原始 row 当成已验证对象继续解引用；可读片段只作为失败证据，不会产生通过。基础 Witness 还分别覆盖 stream 序列、counter/aggregate 数量、跨拍顺序、Submit/ready/activation 前后关系和实际 Close/BusinessReady。

## 4. Tick 对照保留合法整拍尾部

每个 source Decision 和 Witness Tick 精确匹配 sequence、job/tick/target、当前 task/model/config/schedule/epoch、planned/start/skipped 和实际 candidate pair presence。Witness 的 target_tick 在有候选时为本拍 tick，无候选时为0；candidate_present 对应 source.job_id>0，正确使用本拍 `t && cand`，没有把 phase 的共享 candidate 槽状态当成本拍输入。

B1 source 在 publish 后、Decision enqueue 前采样 `d.tick_end_ns`；Witness 在真实 enqueue/准备请求/正常 cutoff 或停止处理后采样 whole end。因此比较器要求 `source.end_ns <= witness.end_ns`，同时 source 自身要求 planned<=start<=activation_commit<=source.end。没有错误要求两个 end 相等，也没有用20ms jitter限制有意包含 cutoff 等待的 whole tick duration。

报告保存 `tick_whole_minus_source_end_ns` 的实际有限整数差值，不依据这组平均或差值推断 WCET、控制性能或正常窗口完成。启动前置、正常窗口和最后停止拍全部参加 join。

## 5. Submit 对照使用真实门前/授权后包围关系

source Job 对象要求真正的 p1-solve-job-v1、完整 run/boot/contract/worker instance、严格正 job/target 与版本/epoch；source event 的 submit_commit_ns 与 publish_start_ns 必须为合法正 int64。对应 Witness Submit 的 job/target/版本/epoch 精确一致，preparation tick=source.target_tick−1。

比较器采用：

`source.submit_commit_ns <= witness.commit_ns <= source Job.publish_start_ns`

这与 B1 源码一致：业务 mutex 内先采样原门时间，再进行最终门和资源检查，随后 job_id/ledger 存储真正授权，才采样 Witness commit；退出 mutex 后创建 source Job publication 起点。比较器不把两种采样强行相等，也没有额外把 Witness 授权后采样当成旧 deadline 门时间来引入新业务政策。报告分别保存授权后减门前、source publication 起点减授权后的实际差值。

未提交的 job_not_submitted 不被补成 Witness Submit；正常 source 完整时，多出 Witness 授权或多出 source Job 均通过双向覆盖拒绝。Sink 入队顺序、DDS reception 顺序没有被拿来代替跨线程真实授权顺序。

职责限度必须保留：`job_publish_result` 在比较器中属于合法 source 支持事件；本工具没有单独验证其实际 DDS publish_start/end/success，也没有扫描 typed bag。其 `publish_start_ns` 上界明确是 source Job 事件中声明的起点，不宣称完整 DDS 发布审计。实际 Job/Candidate/Decision source–bag 一致、真实 worker 原件、发布与正常 ledger 完整性仍须原 checker/实际采集和独立汇总门并列闭合，不可把比较器 pass 替代这些门。

## 6. Activation 对照覆盖 accepted 与 rejected 全部尝试

每个 source job_id>0 的 Decision 对应一条 Witness Activation。job/tick/target、当前 Decision 版本/epoch、ready_commit_ns、activation_commit_ns、accepted 和 reason_code 使用精确值与类型比较。source `commit_now` 与 Witness commit 本来是同一采样，因此这里正确要求精确相等。

reason_code 按真实源码映射：accepted0、shutdown1、run_unusable_at_commit2、其他拒绝3。它是约简枚举，工具保持 `all_worker_execution_gates_verified=false`，没有把 code3 解释为某一完整具体拒绝门。accepted/拒绝数量单列；不能把拒绝尝试算成 accepted，也不能删掉正常收尾拒绝以得到全接受样本。

所有带 candidate 的尝试都要求实际 source accepted_registration 及精确 ready 时间，重复 accepted registration 拒绝。对应 registration.job 与 source Job 的必需身份完全一致。对于 rejected，source Decision 的当前版本可合法不同于早期 Job，比较器以当前 Decision 对照 Witness Activation；没有因版本变化拒绝合法 rejection，也没有放宽 accepted 的 job/tick 身份（基础 Witness 对 accepted 另有一致性门）。

source 未有 candidate 的 tick 不造 Activation，只由完整 Tick、无候选 aggregate 与 source Decision 覆盖。accepted registration 后在停止/失效中未消费的候选也不被补造成 activation；该工具的比较对象是实际最终尝试。

## 7. 正常 case 与 terminal 时间关系

正常 C0 拒绝 Tick/Submit/Activation 的任何 source failed 快照；phase 只允许5/7/8/9，即正常停止观察、Close、真实失效观察和 BusinessReady。1/2/3/4/6 的 arm/pause/overflow/sourcefailure/解除压力事件均拒绝；phase failed=True 或 pause_active=True 也拒绝。

未知 phase 状态保持由基础 Witness checker 单列，不反向补造成已知业务状态，也没有把异步 failed/stopping 快照直接当成更早原门输入。source 最后 shutdown 的 last_decision_sequence 必须对应最后 Decision，finished_ns 正常有界域，shutdown_grace_exceeded False，shutdown 不得晚于 source summary；Close 不得早于 source summary finished。基础 Witness 还要求真实 Close 恰一条、是 phase 最后记录且不早于所有 producer，保证 source summary/整拍尾部不会被比较窗口剪掉。

该时间关系验证终端观测顺序，不单独证明 source 真实 flush 或 owned 进程已经退出。flush marker、actor PID/start_ticks/PGID/SID/boot/exe 身份、有界 cleanup 和全 run physical topics0 仍由原生命周期与汇总门验证。

## 8. 输入与报告的失败关闭

source reader 的最大预算为64MiB、单行256KiB、200000行；JSON shape 最大深度12、每 row32768节点。UTF-8错误、重复 JSON key、NaN/Infinity/非有限指数、超出 signed/uint64 wire 域整数、无最终换行、空文件、错误 row type 和未知事件拒绝。Witness/header/context 使用已有 bounded JSON loader，保持其严格结构与身份门。

CLI 的四输入都必需，输出不得 resolve 到任一 raw input。报告以 `open("x")` 只创建方式写入，不覆盖原报告或输入，输出失败返回2。before/after SHA 不同会明确将 passed/source_join_verified 置 False 并追加 integrity issue；后读取哈希或其他 reader 发生异常则重建失败 result，不能保留 analyze 的 prior true。报告包含工具自身 checker SHA。读取异常、输入变化和输出失败的测试定义已存在。

闭合分析仅设置 `source_join_verified=passed`。报告明确固定：normal_window_verified、owned_process_lifecycle_verified、worker_source_compared、source_bag_contract_complete、all_worker_execution_gates_verified、C0_performance_comparison_verified、normal_contract_complete、expected_log_overflow_mechanism_passed、execute_qualified 全 False；`lifecycle_window_clipped=False`。不能凭声明10s或 source–Witness 行一致推导实际10s、bag/worker完整、R5或执行资格。

## 9. 最终结论与晋级条件

没有发现这两个冻结文件在本次声明范围内遗漏完整 Tick/Submit/最终 Activation 尝试双向覆盖，或错误地要求合法时间采样差相等。没有发现 disabled/incomplete Witness、缺源行、重复行、错身份、错 accepted/reason/ready/commit、source drop、压力 phase、读取异常/漂移会转为 source_join_verified=True 的静态路径。

本次审查发生在真实 C0 launch 前，没有根据现场数据放宽政策。允许完成新工具的必要独立测试和受控运行集成；最终 C0_complete 应由本次 gates 将比较器、原 source/bag/base/ledger、独立 audit、真实10s、RC/cleanup、资产与 host/physical 门合取。任何失败批次保留原件；工具修复或业务修复需独立说明、升版本和新事前声明，不能把旧批改成通过。