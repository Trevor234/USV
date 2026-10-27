# C3.7 Worker 两接口端点绑定组件范围（2026-10-14）

本文件记录新 N14 Worker peer 组件的实现和拟验证范围。编译、测试和真实 owned 运行由主代理统一执行；本文件不预先判定通过。

## 原始来源和角色分离

已完整读取上一批真实 run `owned_C36_adapter_positive_01/worker/owned_manifest.json`，文件 SHA256 为 `947d4f8a7ba8c400a671d4bdef178be1b08dba55f7ef9127fa53d6ff0e692923`，并读取 Worker Source 开头的 capability header、recording-ready、真实 publish attempt/result。

真实 Worker manifest 角色是 `worker`，使用 `worker_instance` 和 `nominal_hash`；其 application DataWriter 是 `/p1/worker_capability` 的 `WorkerCapability` 和 `/p1/solve_candidate` 的 `SolveCandidate`。它另有 SolveJob subscription，不能将 subscription 的 GID 作为上述任一 DataWriter。

新组件只写 N14 的 `common/owned_worker_peer_c37_v1.hpp` 和 `tests/test_owned_worker_peer_c37_v1.cpp`。旧 N13、N10、旧 Source 和失败证据未修改。复用 N14 内复制的 C3.6 工具函数以保留 manifest、typed JSON 和实际 process 的认证口径，但不构造 Publisher peer，不借用 producer/config 字段。

## 接口和独立 pins

命名空间为 `c37_owned`。`WorkerPins::from_json` 及 free `from_json` 严格要求以下 17 个键，未知键和缺失键均拒绝：

```text
manifest_path, manifest_sha256, run_id, boot_id, contract_sha256,
worker_instance, nominal_hash, exe, binary_sha256,
source_bundle_sha256, effective_parameters_sha256, pid,
process_start_ticks, capability_topic, capability_type,
candidate_topic, candidate_type
```

`Interface::Capability` 和 `Interface::Candidate` 区分两类回调；`OwnedWorkerPeer` 提供 `callback_reason(info, interface)`、`gid_matches`、`expected_gid(interface)`、`alive()`、`evidence()` 和 `graph_matches_snapshot(Node&)`。

构造函数按外部 supervisor 独立给出的 pins 认证 exact bytes 和 manifest；role 必须为 worker，两接口 type 固定为上述消息类型，必须各有一个 publisher endpoint，两个 GID 不同。所有 endpoint GID 都要求 16 字节整型值、非零且唯一。Worker manifest 出现 `producer_instance_id` 或 `config_hash` 时拒绝。

有效参数使用 typed/IEEE canonical digest。`run_id`、`contract_hash`、`owned_manifest_file` 必须是 type 4，并分别等于对应独立 pins。manifest 顶层 nominal 和 `contract_configuration.nominal_hash` 必须一致，execute/physical/immutable 等资格标志要求严格 boolean 值。认证 `/proc/PID` 的 boot、PID、start ticks、exe、binary、argv、pgid、sid 后取得 pidfd，再重复认证 process 和 manifest。

## 回调边界

构造时 manifest nofollow、FD/name 稳定回读，上限 256 KiB；严格 JSON 拒绝重复键、非有限数，嵌套深度最多 32；参数最多 512 项，数组最多 8192 项；process executable 最多 512 MiB。这些成本发生在构造期。

回调仅比较实际 `MessageInfo` 的 RMW/from-intra 标志和对应接口的 16 字节 DataWriter GID，然后对已取得的 pidfd 执行零等待 poll；不会读取 manifest、进程文件或重新哈希。交换 Capability/Candidate 的 GID 也拒绝。匹配 GID 但 process 已退出返回 `worker_process_exited`，不能作为 live Worker 的能力续租或 Candidate 注册。

graph 检查分别读取两接口的 publisher graph，要求各自瞬时人口为 1、类型、节点名和 GID 全匹配；两次 graph 查询不构成原子图快照，也不证明整个运行期间持续唯一。

## 32 项拟执行 native 用例

组件 tests 包含真实两路 DDS：第二个节点使用相同节点名，在 Capability 和 Candidate 两个 topic 发布与合法 Worker 完全相同的 typed payload；比较合法和 foreign 两次 callback 的 CDR bytes，检查两接口各自正确 GID 接受、foreign GID 拒绝，并把实际合法回调 metadata 交给另一接口检查交换 GID 拒绝。另有两接口图人口读取。

负例覆盖 pins 严格类型、借用 Publisher 字段/角色、固定接口类型、duplicate JSON、manifest leaf/parent symlink、FIFO、oversize、wrong byte SHA、wrong instance/nominal、typed canonical 和 digest、coherent digest 重绑定后 run/contract/path/nominal 不一致，以及 process start/bin/exe/boot 重绑定。只证明这些具体反例被拒绝；外部 supervisor 的 pins 本身是可信前提，不能将任意完全重写并重新授权的 manifest 副本都称为密码学攻击。

## 资格和未决事实

该组件结果只涉及 application 内的 Worker role/manifest/process/DataWriter 绑定。`post_pin_exec_continuity`、`continuous_DDS_uniqueness`、`worker_close_intent`、`worker_endpoints_exited`、`plant_acceptance` 保持 unknown；`stage_qualified`、`execute_qualified` 和 `physical_release_qualified` 为 false。

本组件没有重新实现 solver，没有执行 actuator publish，没有建立 master-clock 来源或 plant 接受证据。middleware 先于 application callback 的反序列化成本、所有调度成本的 WCET、Worker 全运行期间不 exec 和连续 DDS 唯一性仍未得到证明。B4/M0b/B5/M4 等阶段资格由主任务独立审查，不能由本组件测试替代。
