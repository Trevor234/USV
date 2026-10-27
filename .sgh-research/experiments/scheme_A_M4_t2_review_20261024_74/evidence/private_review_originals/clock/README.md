# 第72批 T2A_14 只读独立审查

本目录是私有复现材料。没有修改第71/72/73批；没有启动 ROS、owned 角色或发信号。Python 只对已关闭 sqlite 使用 `mode=ro` 并反序列化 CDR；C++ 只用历史 JSON 重放冻结纯策略类。

登记 `implementation/T2A_registration_v11.json:17` 实际把 T2A_14 定位到第72批 `implementation/runs/T2A_14`。第71批 `runs` 是该批早期 T2A_02..04 的位置；本审查没有把早期路径误当作 T2A_14。

以下相对路径均以 `/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_clock_freeze_owned_20261024_72` 为根。

## 可复现结论

1. **“全部冻结条款通过”的审计覆盖不成立（审计实现缺陷）。** `implementation/t2_author_rev8/audit_t2.py:58-75` 只计算回执存在、receipt-stale 时长、最小登记时长，以及保持后是否存在任意带 processed/submit 时间的 Regulator 行。冻结表 `implementation/T2A_table_v11.json:30-36` 的 pause_confirm=400ms、old_candidate_must_not_revive、resume_requires_new_window、same_stamp_keeps_receipt_fresh 没有接入语义检查。审计 `:36-38` 不读取身份、角色退出、API、witness、Source summary 或 Stored。私有脚本在内存中把整个 Regulator 流替换成一条 arbitrary_row，移除所有 clock/decision/candidate/API/witness/Stored/身份/关闭证据，仍得到全部 true；把 a1 action 改成 not_clock_hold、command_sha256 改成全0、模式改成 same_stamp、duration 改成50ms，也仍全部 true。回执函数 `t2_action_contract.py:223-251` 未把 action/parameters/hash/trigger Job 与冻结表、真实 command bytes 对账。因此 `close_t2a.py:43-55` 的断言不能支持其 all_clauses_hold；`:58-61` 的轨迹摘要也只用弱 any/count 条件。

2. **rc3 来自 witness 结构一致性失败，不能称为预期 normal-contract 资格拒绝（真实观察/实现问题）。** `regulator/witness.json:1` 中 seq10 为 tick9/generation2，seq11 为 tick0/generation2。`p1_witness.hpp:403-405` 的同 generation 单调 tick 谓词要求下一个 tick10，因此连 `records_consistent(false)` 都失败。它经 `p1_witness.hpp:314`、`regulator_owned_execute.cpp:316,1302` 导致 observation_complete=false、rc3。`first_failure={code:0,stream:0,ns:0,ticket:0}` 是因为 `records_consistent()` 只 return false；`failure()`/first_failure 只被 append/lifecycle/write 错误调用（`:445-450`）。这与 incomplete=false/overflow=false 不冲突。具体排序入口：`regulator_owned_execute.cpp:1094` 先记 last_schedule，`:1101` 后增 schedule，`:1104` 把新代际写入当前旧 tick；下一轮才回零。这个结构断点独立于下面的 API 断档。

3. **恢复后 seq12 存在真实 history/authority 分叉及 API/Applied 断档（场景暴露的运行时缺陷，不只是 RTF 不对齐）。** 原始 `regulator/source.jsonl:494` 明确记录 `owned_pair_policy_failed`, sequence12, returned=[true,true]，reason=`M4 actual per-side authority agrees with command history`。seq12没有候选（`:495` 中job_id=0，candidate_capture.candidate_present=false、ticket_present=false、pair=false）；冲突双方是 held-history anchor 和独立 OutputAuthority anchor，并非候选与history。seq11 两侧工程外推 sim 为 `[102543990010,102544034165]`，seq12 恢复后的为 `[101966060606,101966115306]`。seq12 左侧相对历史最后一条右侧倒退 **577,973,559ns**。`regulator_owned_execute.cpp:952-958` 在成功 API 后追加这些 sim 事件；`:843` 清空两侧 known，右 API 完成后右侧又变 true，Source seq12 明确为 anchor_known=[false,true]（`:495`）。冻结 `OutputAuthority::record_pair` 则按两次成功 API 保持 known=[true,true]（`owned_execution_policy_native_v1.hpp:115-125`）。纯 C++ 历史重放精确复现全部13个 Source anchor_known/sequence，仅 seq12 出现分叉；全部 policy tick_ok=true、seq12 authority_terminal=false、command_invalid=false。

   `regulator_owned_execute.cpp:1221` 的 require 在 `:1224-1230` API/Applied 记账之前抛出；`:963` catch 设置 stop_requested=true；下一 tick `:1096-1099` 观察到停止并输出 seq13 shutdown。所以 API 和 Applied Source 序列均为 `[1..11,13]`。闭合 bag 独立反序列化确认 Decision `[1..13]`、Applied `[1..11,13]`，两侧 thrust 各13条；复用纯通用检查 API_full_stream 因 non-contiguous API pair sequence 失败、typed_Source_Stored 因 applied sequence is not contiguous 失败。

   实际成功发零及最后受控关闭有证据，**“600ms hold 耗尽导致关停”则不符合真实因果**：首个零在 seq8，距最后 accepted 200,002,277ns、距 hold 102,720,561ns，早于600ms。`p1_admission.hpp:131-135` 的 hold 只是 no-candidate 有效保持；`regulator_owned_execute.cpp:1071` 在 stale reason 下选择 invalid fallback。最后 shutdown 是上述 stop_requested 的确定路径。

4. **“冻结词表下恢复不可达”过度外推（范围/场景结论）。** `documents/方案A_第72批_T2A时钟冻结场景族首次owned执行_2026-10-24.md:11` 声称词表上界无法表达600ms追赶；但 `t2_action_contract.py:108` 允许 advance_ms=0..1000。T2A_14 的 last clock `source.jsonl:362` 到 first resumed clock `:474` receive delta=799,481,816ns，sim delta=20,625,671ns，无补偿的首区间比约0.025799。同域中 +779ms 追赶足以使该区间比接近1；这只是离线算术说明，未声称该动作已运行或已证明成功恢复。0/+100 两种已运行场景不能证明整个0..1000域的新窗口不可达。

## 支持的有限场景事实与通过项

- hold 回执 `fixture/nominal_steps.jsonl:102`，resume `:146`，实际间隔791,951,916ns，超过100ms stale和500ms登记保持；保持期 Regulator clock 行数为0。
- 5次 accepted 在保持前；首个 accepted 与 BusinessReady 绑定。4个静默 stale 决策 Source 行377/406/432/462 的 clock_age_ns 分别106,389,712 / 306,405,362 / 506,370,454 / 706,404,540；pause raw snapshot 从第三个开始 true。resume 后 schedule3/tick0、rtf_unaligned，没有再 accepted。
- 没有旧候选复活这一负例得到该运行支持；same_stamp 新鲜回执分支未运行；恢复新窗口后成功提交/接纳没有被触发。
- 当前磁盘四角色 ELF、103文件 rev8 source bundle、Driver SHA、contract/registry/table/audit pin 对账通过。Driver manifest 原始登记SHA匹配；registration_copy 只是序列化格式不同，语义相同。没有发现身份不符。
- Driver 四角色关闭记录 group_empty 全 true；regulator rc3无signal，其余 rc0 且仅SIGINT；Recorder clean/Recorder_stop_completed=true。关闭的成功不抵消上述审计缺口和结构/流问题。
- Source summary generated=emitted=533、dropped=0，normal_source_complete=true；Worker capability Source/Stored=18/18；wire/GID 517 observed、518 Stored、仅1条额外 capability，全部通过。Source flush完整与 witness observation_complete=false可同时成立。
- **154 vs115不是漏包证据。** `fixture/terminal.json:1` 声称 clock published_counts154，但 `synthetic_source_m4.cpp:82` 把所有sensor/model `count_`当clock计数；`:235` 在silent的39步确实不publish clock；`:240` 仍增count。transport clock115与Stored clock115一致。该计数器语义应修复，不能报39条丢失。

## 有限修复入口

- 先修 witness schedule increment/reset 的观测顺序，使代际与 tick 回零对应；保持该结构失败作为单独回归用例。
- 在冻结 resume 映射下定义工程外推发布历史如何跨 pause 连接，并保证“输入/历史失效”不会任意清掉已成功物理 API 的独立输出权限；修复两套 anchor 的一致性问题。
- 真实 API 事实应在可抛出的 policy一致性检查之前不可丢失地记录；异常路径保留该次 Applied/API审计事实及失败原因，避免 seq12 这种真实成功发布从完整账本消失。
- 扩展冻结 T2审计逐项消费全部条款，并组合身份/Source/API/Stored/退出证据；针对 same_stamp 与恢复新窗口分别登记有限测试，不修改既定deadline/预算，不引入native C挂起、硬实时或plant前置。

## 复现

```bash
g++ -std=c++17 -O0 /tmp/review72_clock_audit/replay_anchor.cpp -o /tmp/review72_clock_audit/replay_anchor
/tmp/review72_clock_audit/replay_anchor > /tmp/review72_clock_audit/replay_anchor.stdout.json
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
/usr/bin/python3 -B /tmp/review72_clock_audit/validate_t2a14.py --output /tmp/review72_clock_audit/reproduction_summary.json > /tmp/review72_clock_audit/validator.stdout.json
```

主入口：`reproduction_summary.json`。原始输出：`validator.stdout.json`、`frozen_audit.stdout.json`、`replay_anchor.stdout.json`；相应 stderr及build stderr均为空。`replay_anchor.cpp`直接包含rev8纯策略头，只复播过去数据，创建的合成对象不作为实时 ownership 或新owned运行证明。
