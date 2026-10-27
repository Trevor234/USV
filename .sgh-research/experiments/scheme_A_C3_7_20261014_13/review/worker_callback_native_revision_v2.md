# C3.7 Worker native 首轮失败诊断与 v2 测试修订（2026-10-14）

首轮 `native_attempt01` 中 Worker peer 32 项只有 `ActualDDSBothInterfacesIdenticalPayloadForeignDataWritersRejected` 失败，Node callback 13 项只有 `ActualSamePayloadForeignCandidatePreservesExistingReadySlot` 失败。两者失败断言均为两次独立 Candidate 重序列化 CDR 的整串 bytes 相等；GID 接受/拒绝、租约和 ready slot 的相应分支断言没有失败。

## 具体证据

create-only 的 `worker_cdr_padding_diagnosis_v2.json` 按当前完整 `SolveCandidate.msg` 和 `SolveJob.msg` 解析 GTest XML 留下的两条完整 bytes 表示。所有整型、bool、string、sequence、fixed arrays 和 float64 原始字段 bits 都保留；诊断为离线解析，没有启动 ROS 或重跑测试。

| 首轮失败 | 两条 CDR 长度 | 字段改变 | 字节改变位置 |
|---|---:|---:|---|
| Worker peer 同 payload、foreign DataWriter | 2908 / 2908 | 0 | offset 9、10、11，均为第一空 string 后的 alignment padding |
| Node 同 payload、foreign Candidate 保留 ready slot | 3276 / 3276 | 0 | 48 个位置，全部位于 IDL 字段间的 alignment padding |

每条 Candidate 解析为 72 个字段/length/count 记录，消费到 CDR 末尾；两对完整 typed 字段包括全部浮点 IEEE bits 无改变。XML 保留原样，SHA256 分别为：

```text
peer XML: 9d02929c00722318201ce4e0ebf1d313e32b4871669defeeedfbdc146ce8d224
Node XML: 0a5d414ef58440066f9920f89578cef728f9a527da7152785102646c575a5270
diagnosis JSON: 3d313dd3482739a0262d87672971fa21a767add4586aa98786253e77f338aab6
```

解析 GTest 表示时 `\0` 是一个 NUL，随后 ASCII 数字按字面字符解析，不能按 C octal 的三位 escape 合并。对于空 sequence，实际 CDR 字段消费遵循序列化结果，不把 size-estimation 的 element alignment 误当成存在的字段字节。

这说明首轮测试把重序列化产生的 alignment padding 当成跨 capture 的 payload 语义身份。原 scope 文档预期“same CDR bytes”的说法由本次证据更正为“same full decoded typed payload”。每条 raw CDR 仍可以用其 own SHA 校验记录完整性，不能要求另一条独立 capture 具有相同的 padding/SHA。

## 两份测试源码的修订

修订仅发生于 N14 两份 mutable test cpp：

```text
test_owned_worker_peer_c37_v1.cpp:
  dca0e4e0212cf118bfbb03fbaf5adcb8bad69d9046d5448af81cfb6d0dc4776b
test_c37_worker_callbacks.cpp:
  5eb70102f2a2ccb099423452713a389e43fe7ab8d03d11a4dda2459a5d81aea6
```

同 payload 比较现在分别通过真实 ROS deserializer 解码每条保留的 CDR，构造完整 Capability 或 Candidate（含完整 Job）typed 记录，对所有 float64 递归执行 IEEE754 canonical encoding；既比较合法/foreign 两条完整 typed 记录，也比较实际发送的完整原始对象。string、bool、所有标识、时间、完整 reference/history、预测数组均参与，没有缩减为 worker/job ID 或 first control 子集。实际 callback MessageInfo/GID 判定、foreign 拒绝和业务状态断言完全保留，生产 Node/header 未由本修订改变。

另追加一个明确的 metadata mutation 组件用例：两接口各对真实 MessageInfo 副本执行 wrong RMW identifier、null identifier、zero GID，共 6 个拒绝输入。要求实际接收函数不抛异常、保留 rejected received 人口、准确记录 RMW/foreign GID 理由，并保持原 trusted state、无 full CDR、无 semantic callback、无续租和 Candidate mutation。该用例不宣称这些变异为真实网络 metadata。

Worker peer 测试仍为 32 项；Node callback 变为 14 项。受控 real exec-child 死亡用例保留。主代理负责 v2 source bundle、fresh build 和统一验证。本文件写入时没有对 v2 编译或启动 ROS，也不预先判定修订后的测试通过。

## 保留和资格边界

首轮 source snapshot/build01、两个失败 XML、branch Source、child Source/manifest/退出请求、已有冻结资产均未更改或覆盖。旧失败仍为失败证据，后续通过只能说明 v2 验证结果。

上述诊断和修订属于组件验证；没有建立连续 DDS 唯一性、post-pin exec 连续性、原 N10 solver Worker 网络尾部闭合、plant 接受或阶段资格。阶段与研究结论仍由主任务独立判定。
