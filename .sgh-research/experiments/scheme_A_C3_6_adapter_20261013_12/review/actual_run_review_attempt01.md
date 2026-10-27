# C3.6 实际 owned shadow run 只读复核 attempt01

日期：2026-10-14。实际 run：`/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/runs/owned_C36_adapter_positive_01`。

Driver 4 秒测量/完整关闭通过，总耗时 10.4935 秒、关闭 1.9328 秒，五个 owned role returncode 均 0 且 cleanup clean。**原始 v1 独立检查器仍失败；normal Witness 不合格。** 原 helper、run snapshot、首份失败结果均保留。

## 人口与原失败

24 条 Applied 在实际 SQLite、transport、Observer callback、adapter observation 与 legacy anchor 全人口同序列。callback MessageInfo GID 均为钉住的 Publisher DataWriter，完整 typed CDR 与实际 Storage payload 匹配。queued post-exit terminal tail 分支实际命中 0 次，不能宣称此 run 覆盖该分支。

21 Job、21 native Candidate、21 accepted registration；30 Decision、20 activation attempt、0 accepted activation。20 个尝试均 `anchor_mismatch`；其余 Decision 为 5 legacy_not_ready、4 no_candidate、1 shutdown。注册收受与最终执行候选收受是不同阶段。

Observer Source 共 1334 行，terminal summary 声明 1333 generated/emitted、0 dropped；adapter 的 98 条 evidence 均 observation-only，无 active publish transaction、无 regulator 实际 publication。Source/typed Storage/Publisher session 三组原 checker 通过。

原 Witness 包含 30 tick、21 submit、20 rejected activation、3 phase（Stop/Invalidate/Close）。旧 normal gate 要求与首个真实 accepted activation 对应的 BusinessReady；本 run 没有 accepted activation，故原失败准确保留为 `business_ready_count=0` 与 `complete_flag_disagrees`。原 raw `audit_complete=true` 不能直接转换为 normal 或新组件 pass。

## 关闭时序与 Job21

| 点 | CLOCK_MONOTONIC ns |
|---|---:|
| Job21 ready 完成 | 161628538134375 |
| driver request | 161628649195533 |
| Observer 观察关闭 | 161628728366384 |
| driver ack 检查 | 161628792199948 |
| Job21 原 target | 161628735642071 |
| Publisher SIGINT | 161628835814471 |
| Publisher cleanup complete | 161629095871335 |
| 完整 terminal-tail ack | 161629122296666 |
| Source terminal flush | 161629336404080 |
| Witness Close | 161629336438630 |

Observer 观察关闭比 Job21 target 提前 7.275687 ms，close evidence 的 pending=false；Job21 没有 activation。观察关闭之后的 4 个 Decision 均 job_id=0 / accepted=false。driver ack 在 Publisher SIGINT 之前；最后实际 shutdown_zero 仍完成收受，tail ack 覆盖 24 条完整 Applied。

## 分账与后续

新事后登记 `/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/postrun/observation_population_scope_v1.json` 只允许独立检查本次已观察到的全拒绝闭合人口。新增 helper 严格检查 raw Witness typed/capacity/counter/sequence/header/terminal 时间及 Source-Witness 全人口绑定，并附三个 coherent 内存反例；其运行结果由 root 另行保存。本 review 不提前宣称新 profile 通过，不修改旧 normal gate，不回填 BusinessReady/accepted。

阶段 B4/M0b/B5/M4、执行资格、研究结论均 false。owner close intent、观察关闭时 endpoint 退出、持续 DDS 唯一性、post-pin exec continuity、Worker callback GID、MasterClock、plant、WCET 保持 unknown。实际 runtime per-channel partial/unattempted execution adapter 仍未验证。
