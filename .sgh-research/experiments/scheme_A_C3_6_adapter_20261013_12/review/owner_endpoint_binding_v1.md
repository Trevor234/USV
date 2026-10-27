# C3.6-B：Applied owner 与 endpoint 最小绑定实现

本文件记录新 N13 组件及其声明域。旧 N10/N12 资产没有修改。此代理只编辑新 peer 头、对应测试与本说明；实际编译、DDS 运行和整批认证由主代理执行，本文件不预先宣布测试通过或阶段合格。

## 已确认的原接口边界

N10 [真实 Applied callback](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/observer/src/shadow/regulator_shadow_observer.cpp:122) 只有消息指针，[legacy_applied](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/observer/src/shadow/regulator_shadow_observer.cpp:427) 校验 payload 身份。该回调没有逐条接收 DataWriter GID。现有 [callback_raw_v4.hpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/observer/src/shadow/callback_raw_v4.hpp:14) 已能读取 MessageInfo、真实 GID、完整 typed reserialized CDR，但尚未用于 Applied。当前新范围只补 Applied owner 绑定，不扩称 Worker Candidate/Capability 新增逐回调 GID 认证。

原 [owned auth](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/owned_auth.py:75) 从外部 Supervisor 冻结进程身份核验角色 manifest，再用 [pre-release graph](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10/owned_auth.py:133) 核验真实 endpoint GID。graph 是时点观察。原 Supervisor 的 poll、进程组、session 和 start ticks 证据不等于连续 DDS 唯一性。

## 新组件

[owned_peer_c36_v1.hpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/common/owned_peer_c36_v1.hpp) 提供 `c36_owned::PeerPins`、`from_json(Json)` 与 `OwnedPeer`。主代理将独立认证的 Supervisor pins 文件与 SHA 传给新 Observer；peer 只读取其中的精确 peer 子对象。文件 SHA 是内容 pin，不能单独证明 manifest 的作者身份。

`from_json` 的精确 15 键是 `manifest_path`、`manifest_sha256`、`run_id`、`boot_id`、`contract_sha256`、`producer_instance_id`、`config_hash`、`exe`、`binary_sha256`、`source_bundle_sha256`、`effective_parameters_sha256`、`pid`、`process_start_ticks`、`topic`、`type`。驱动关闭请求和其他角色材料放在外层，独立解释。

构造阶段逐层 nofollow 打开 manifest 父目录，读取有界 regular FD，拒绝 leaf symlink/FIFO、超限、文件名/FD stat 变化与 SHA 变化；JSON 拒绝重复键、深度超限、非有限数值。字段保持精确类型，不用 bool/int 宽松相等。角色身份、参数完整 canonical digest、真实 endpoint topic/type/GID、argv 和 PGID/SID 都核对。完成 `/proc` boot/PID/start/exe/binary/argv 核验后打开 pidfd，再核验一次；昂贵的文件读取、SHA 和 `/proc` 操作只发生在初始化。

声明域：manifest 256 KiB，JSON 深度 32，endpoint 数量 128，参数 512、参数数组 8192、参数字符串 65536 字节；进程 exe 文件哈希上限 512 MiB；FastDDS `rmw_fastrtps_cpp` 与 16 字节非零 GID。run 128、boot 64、producer 64 字节可见 ASCII，producer 不 trim。该 producer 域比历史 legacy 载荷支持域更窄，须在新登记中显式锁定。完整 Applied payload、state/clock/lease/resource、N12 owner 与 Job/Candidate 匹配仍由原 gate 和新 adapter 实现。

运行 API：

- `callback_reason(MessageInfo)` 先拒绝 foreign GID/RMW/intra-process，再做零等待 pidfd poll；空串表示本次 callback 所见 GID 匹配且 pinned 进程当时未被观察为退出。
- `gid_matches(MessageInfo)` 独立核对原 GID；可供驱动关闭后的有限终端 tail 策略使用，不附带进程活着或新 Job 许可的含义。
- `alive()` 是本次零等待 pidfd 观察。
- `expected_gid()` 与 `evidence()` 给出被绑定的原 GID、来源与认证时刻。
- `graph_matches_snapshot(Node&)` 核验 Applied topic 当前仅一个匹配 node/type/GID 的 publisher；它只给这个调用时点的 snapshot。

pidfd 保存同一进程实例的引用，并使已退出实例不能因 PID 数字被回收而重新变活。它不能证明之后未 exec、DDS endpoint 全寿命或连续唯一性。`post_pin_exec_continuity`、`continuous_DDS_uniqueness`、`owner_close_intent`、`owner_endpoints_exited`、`plant_acceptance` 均在 evidence 中保留 `unknown`，stage/execute 标志为 false。

## 关闭证据必须分开

`driver_close_request` 只证明 driver 请求关闭。真实 `owner_close_intent` 需要在 owner 原关闭路径中采集；本批复用 N10 publisher 二进制，没有把信号调用或日志 normal_end 重新命名为 owner 意图。

session end/flushed 是日志收尾证据；Supervisor cleanup 是进程组资源证据；DDS endpoint 缺席要独立观察。pidfd exited 不能替代 graph 缺席，graph 缺席不能替代 owner intent。反之，进程退出后队列中仍可能收到来自原 DataWriter 的终端 tail。主代理的新外层登记应明确：driver closing、原 GID、严格 payload、`shutdown_zero` 和有限窗口内，只保存/结算终端命令事实；进程仍显示不活着，禁止新 Job，不授予 owner endpoint 退出或 M4 资格。

N12 `CommandAnchor::close` 在无 active 时立即 local closed，随后 `observe` 拒绝反馈；因此新 adapter 不能把关闭请求、组件 closed 和系统 owner destroyed 混成一个状态。异常记录或证据 I/O 失败也必须继续已有 owned cleanup。

## 新测试人口

[test_owned_peer_c36_v1.cpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/tests/test_owned_peer_c36_v1.cpp) 包含真实 DDS 两个 DataWriter 的正负对照：同 node 名、完全相同 Applied reserialized CDR，原 GID 可接受，foreign GID 被拒；另有当前唯一 graph snapshot，且结果不晋升 continuous 唯一性。

其余用例覆盖完整字节与 SHA 重绑定后的重复 JSON key、leaf/parent symlink、FIFO、超限、PID bool、start float、进程 start/bin/exe/boot 与实际 `/proc` 不符、flags int、GID bool、wrong/duplicate endpoint、参数 bool/int、integer/float、canonical 数组数值类型、parameter digest 与明确 producer 支持域。它们检验组件拒绝语义，不是当前真实系统压力或研究结论。

本说明中的实现范围与测试清单应关联主代理本批的实际 build/运行结果及保留的失败记录；只有结果形成后才能称组件验证通过。B4/M0b/B5/M4 与连续 owner handoff 仍需要其他已登记依赖。
