# C3.5 readiness 独立合同与组件验证

2026-10-13。本批针对冻结的 `owned_C3_4_positive_01` 实现了新身份的离线接受合同，10 个组件通过，14 个 coherent fresh-copy 负例均按预期拒绝。原 N10 readiness v3 对当前数据的兼容失败保留。没有创建 ROS 节点，没有修改 N10、旧合同、旧 raw 或安装目录。

这一结果说明当前合成 owned fixture 的指定 readiness 与终端证据组件可以在独立合同下闭合。合同为事后锁定（retrospective），身份期望取自当时的 inputs、owned preparation 与原始 Witness header；并未将当前结果改写成预注册实验或阶段资格。B4、M0b、M4、D1 dynamic、P1、execute、strict full-chain 和研究结论继续为 false。

## 发现与实现

旧的 prepare-close_02 readiness 合同仅提供规则模板。本次重新读取实际 N10 positive_01 的输入和证据，不复制模板中的旧 run ID、参数、角色 PID、GID、binary/source SHA 或 expected 结果。

生成器首次严格核对运行时工具与当前源，发现 `build_c34_v10.py` 发生版本差异。当时保存的 snapshot 与 `inputs.tool_sha256` 完全一致；当前冻结工具的字节为另一身份。新合同分别绑定历史 snapshot 和当前工具，显式声明这一个 build wrapper 差异，其他实际 helper/driver/tool snapshot 都与当前文件相符。它没有用当前 builder 冒充当时实际工具。

原 N10 `validate_readiness_v3.py` 实际执行后，7 个组件中 6 个通过，唯一失败是 lifecycle 的允许事件集合尚不认识 Worker 的 `capability_source_header`、`capability_publish_attempt`、`capability_publish_result`。新 validator 将这三类事件纳入独立、全量的 Source/CDR/身份/计数校验，再接受它们；没有删除真实日志。

新实现包括：

| 新工具 | 作用 |
|---|---|
| [generate_readiness_contract_c35.py](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11/generate_readiness_contract_c35.py) | 新建事后合同，重读并锁定所有实际 record、run 文件集合、role source bundle 内的源文件、binary/native binary、历史工具 snapshot、当前工具、参数证据、bag、辅助工具和 interpreter。 |
| [validate_readiness_c35_v1.py](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11/validate_readiness_c35_v1.py) | 在冻结 N10 v3 规则基础上，以新身份增加全 pin/population closure、9 个 helper 的真实传递导入路径核对、exact 字段域、完整 Capability 发布群体/CDR/回调验证及 terminal tail acknowledgement 一致性检查。 |
| [test_readiness_c35_coherent.py](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11/test_readiness_c35_coherent.py) | 为每个负例创建新拷贝，修改后重新绑定 record、storage、closure 哈希，运行正常 CLI。原始身份期望和 source/binary/helper 保持固定，验证能够越过正确的 hash gate 后被语义规则拒绝。 |

## 当前证据

最终合同为 [readiness_c35_contract_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/readiness/readiness_c35_contract_v1.json)，SHA256：

`548f821778d3492231d6d1cb9879f3d9b8251da7cc40b2c1cce04f47a7d930df`

它闭合 152 个文件、92,200,740 字节，包含 28 个 record 输入和 9 个 sealed helper；`lease_replay_v1.py`、`strict_types_v1.py` 及全部传递 helper 的实际导入路径均核对为冻结 N10 的路径。每次完整校验前后重读这些 pin，并核对完整历史 run 文件集合与实际 bag 文件集合。

[最终正例报告](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/readiness/readiness_c35_result_v1.json) 的 `component_suite_passed` 是真正的 Boolean `true`。10 个组件覆盖历史 pins/配置/release、完整 Applied/物理通道值序、receipt lease、legacy ready/callback/history、immutable Worker pipeline、Source/close/Witness、actual transport/CDR/typed storage、exact 当前字段域、完整当前 Capability Source、当前 tail acknowledgement。

当前 Capability publisher Source 和实际 storage 各有 69 条，完整 19 字段、独立 typed 摘要、实际可解码 CDR、GID、callback CDR 和 lease observation 均验证。Observer admission 仍是有序子集；消息没有独立 packet ID/send-time，不能由相同 payload 推出唯一包身份、源新鲜度或全 admission 群体双射。报告中的 inherited/shared-v2 全局资格标志继续为 false；本次组件通过由 `components.current_capability_source_CDR_population.passed` 和实际 69/69 计数表达。

tail acknowledgement 核对了 publisher/session 原字节、所有 Applied 和双通道的完整计数、Observer anchor 总数、driver identity 与 owned spawn parent、receiver close 之前的检查时刻。它属于当前 v1 的历史记录一致性；连续未知子进程监测、plant ACK、force measurement 或真实 plant held interval 均未因此得到证明。

## coherent 负例

[最终负例汇总](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/readiness/coherent_negatives_v1/summary.json) 记录 14/14 预期成立，22.86 秒完成，原始 pin closure 未变。所有负例保留拷贝、合同、CLI log 和 report。

| 负例 | 主要独立拒绝依据 |
|---|---|
| 成对删 Capability attempt/result，重排 sequence 并重算终端计数 | 完整 Source/Storage 群体不符 |
| 同时伪造 Source payload、typed 摘要、CDR、actual SQLite 和 transport 的 backend | 独立 normal identity 仍要求实际 acados |
| Header 改 Worker instance | Owned/header 完整身份不符 |
| Result 的 `returned=true` 改整数 1 | exact Boolean 域 |
| publish start 早于 snapshot | 实际发布调用因果顺序 |
| 终端 `source_io_failed=false` 改整数 0 | exact payload/terminal conservation |
| 回调原始 GID 变更 | 实际 owned writer GID |
| 同步修改 callback CDR、CDR hash 与 payload backend | 独立完整 Capability 合同 |
| lease `renewed=true` 改整数 1 | 独立 lease exact Boolean |
| Ready held-history 力值变更 | 从完整实际 Applied prefix 重算 history |
| 同步缩小全部 tail 计数并更新 result 的 ack SHA | 完整实际 storage/anchor 群体 |
| 同步伪造 tail 与 publication 的 driver PID | 当时 owned spawn 的 parent PID |
| 加未知 Worker 事件并重算 terminal 行数 | 明确允许的源事件集合 |
| publisher 零错误计数改 Boolean false | exact uint64 域 |

## 失败保留与下一步

[failure_inventory_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/readiness/failure_inventory_v1.json) 区分了 generator 首次历史/当前 builder 身份拒绝、原 N10 v3 当前兼容失败、新 generator 首次遗漏旧 contract 的 closure reader failure，以及修复后的当前成功。没有把这些失败替换为通过，也没有修改旧 expected。

[current_state_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/readiness/current_state_v1.json) 记录当前工具/合同/结果 SHA、组件数、负例数、资格状态和下一步。

下一步由主依赖合同绑定这一个新 readiness 身份，与当前执行合同和预算一并判定依赖。后续 M4 唯一双路接管须使用独立执行版本及对应预注册验证；本合同不能授权 execute 或替代旧 shared-v2 validator/tool 身份。

离线复核命令（输出必须是不存在的新路径）：

```bash
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash
PYTHONDONTWRITEBYTECODE=1 timeout 45s python3 -B \
  /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11/validate_readiness_c35_v1.py \
  --contract /home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/readiness/readiness_c35_contract_v1.json \
  --output /tmp/c35-readiness-new-report.json
```
