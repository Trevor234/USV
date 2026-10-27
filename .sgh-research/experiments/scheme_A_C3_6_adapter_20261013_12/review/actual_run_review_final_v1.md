# C3.6 actual run 最终只读复核 v1

日期：2026-10-14。原 `check_result.json` 保持失败；独立的 `observation_population_result.json` 为 component_observation_passed=true、normal_witness_qualified=false。新 profile 是对固定 30 tick/21 submit/20 rejected activation/3 terminal phase 的事后审计，**不是一般 acceptance validator，也不是运行前资格**。原 normal gate、原 helper/snapshot、首份失败与 raw `audit_complete=true` 在旧 normal 规则下不合格的解释全部保留。

新检查严格验证实际 closed Witness 的字段、typed 值、固定容量、counter、序列、header、terminal 时间及全部 Source-Witness 绑定；Job21 在 target 之前取消。3 个 coherent 反例全部拒绝：submit completion 超 deadline、activation ready completion 重新绑定、最后一 tick 同时删除并修正本地 counters/Source summary。反例只在内存中修改 Source 与 Witness 的 copy 并重算摘要，不是 DDS 运行，也没有改 raw run。

完整记录的人口为 transport ↔ SQLite 共 1552 条，原 CDR SHA 逐 topic 全序列相符。Applied 独立覆盖完整 24 条：Storage、真实 callback GID/CDR、adapter observe 与 legacy anchor 相符。Observer Source 自身 1333 generated/emitted、0 dropped，加 terminal summary 共 1334 行。

WorkerCapability 的 Storage/transport 为 36 条，而实际 Observer callback 为 35 条。这些记录具有不同生命周期：Observer Source 在 `161629336404080` 闭合，transport 的第 36 条 capability receipt 为 `161629480980933`，晚于 Source 闭合 144.576853 ms。Recorder/transport 在 Observer 结束后仍存活。因此 Source 全人口闭合、完整记录链、完整 Applied 收受分别成立；没有证明每个 topic 的每条 publication 均进入 Observer 应用 callback，也不能据此宣称能力消息 source freshness 或 Worker callback GID 新认证通过。

本次实际 accepted activation 为 0；20 个 activation attempt 全因实际 F5 command value 变化导致 anchor_mismatch。21 个 accepted registration 不等于执行候选收受。driver close observation 取消 Job21，观察后的 4 个 Decision 无 job/无 accept。actual queued post-exit zero-tail 分支命中 0 次，阳性 run 没有覆盖该分支。

阶段、execute、dynamic20s、研究结论保持 false；owner close intent、adapter close 时 endpoint 退出、连续 DDS 唯一性、post-pin exec、Worker callback GID、MasterClock、plant、WCET 保持 unknown。最终复核没有再运行检查器或修改源码；仅核对新结果、原失败与 pin/人口/时序。
