# 派生 observer 启动握手：源码实施说明

本目录从 `m0b_D1_prerequisites_20261009/entry_v2` 逐文件复制，父目录不修改。派生运行目标 `p1_regulator_shadow_observer_ready_v1`，入口政策 `D1_shadow_startup_handshake_v1`。源码已编写，编译、测试、远程 owned 准备/关闭和实际图就绪均由 root 单独验证；本文件不声明通过。

原 constructor 的 recording_ready 仍只证明指定 ROS 图订阅。新增 mandatory 参数 `legacy_ready_timeout_ms`，整数范围 1..60000，默认 0 会拒绝。准备时间从 constructor 成功 recording_ready 后开始，deadline 固定；参数不写入或修改冻结 diag5 contract。

`legacy_ready` 的唯一发出路径是实际 executor 输入 callback 调用的 `try_legacy_ready_locked`，由原 business mutex 保护。tick 只检查 deadline，不能生成就绪。准备条件包含：

- exact 六项 legacy pins；从 sequence 1 开始、连续的 whole-pair admitted 历史，received == admitted == 当前 sequence；两 anchor known 且均指向当前 pair。
- 最新 odom 的真实 callback receipt 晚于 pair processed，stamp 不早于两 channel sim stamp；真实 held_history 的双路 pre-odom 项确实覆盖该 stamp。
- 当前有效 path/profile，同 stamp 同长度，accepted IMU、odom、clock，冻结 1:1 source age/lag/skew 门和有效 RTF；没有直接修改业务 RTF-valid 标记。
- 当时真实有效的 Worker capability，lease 未过期，PID/run/boot/contract/nominal 正确，Worker instance 与外部固定 Witness header 相同，pidfd liveness 有效。
- source sink、Witness identity 和 run 未失效。

事件保留六项 legacy identity、epoch、两 anchor 的 sequence/value/publish/sim/end、pair processed、原始 current input stamps/receive/sequences、reference stamps/hash/version、完整 bounded held history 与两条 pre-odom witness，以及当前 full capability/lease/prepare 时间。`measurement_eligible=true` 仅表示 observer 准备输入门；它不表示 D1、域、external Worker hooks、owned 图或全链合格。

`legacy_anchor` 在父字段外新增 39 项 AppliedControl 消息字段投影，用于新 checker 对源事件与 bag 的共同接纳元数据进行核对。三个非身份字符串（clock_status/control_source/publish_error）有 128-byte 上界与显式 truncation flag；发生截断不能初次 ready。默认源政策和 formal ROS 消息不变。

once-ready 后 producer/history/sequence/clock epoch/pause/Worker 不可用，或真正 reference fingerprint 改变，发一次 `legacy_ready_invalidated` 并通过原统一 terminal 转移清除未提交工作。后续 history coverage 丢失同样 terminal。普通新 odom/IMU/clock、相同 fingerprint 的 path/profile 周期刷新可继续；暂时新 stamp 到达顺序仍由原每 tick eligibility 判断，不能将每次正常刷新当作永久失败。就绪事件不重新发出。初次之前 lifecycle history 的 invalidation/gap 会使后续 ready 不可能成立，固定 deadline 到期单次失败并请求有界停止。

新增 shadow job enqueue 门：在 actual legacy_ready 之前不提交 shadow job；准备失效之后永久关闭。tick 的候选状态使用 `legacy_not_ready`，canonical Decision 字段、20ms、nominal、模型、权重、物理 publisher 路径、五项 hook=0 不变。当前可运行 mode 仍仅 shadow，无 physical output endpoint。

原 41 个 source-linked case 源文件逐字保留，另新增 24 个实际包含同一 regulator.cpp 的 case（共65个待执行）。新 tests 的 constructor seam 明示 `recording_ready.test_fixture=true`，无 executor tick/preparation thread，使用真实 input/capability/applied callback 与就绪路径；正例用两次真实 clock callback 和 420ms 有限间隔获得冻结 ClockWindow 的 RTF。test-only macro 只在新 test translation unit，production target 未定义。源事件 JSONL 导出于 root 设置的新 `P1_BRANCH_TEST_OUTPUT` 目录，可用于 shared readiness checker 的有限组件正链，不能冒充 production constructor 实际图或全 lifecycle strict bag 正例。

首次 source freeze/build 前的独立审查修复：准备资格改为 atomic，并在最终 activation commit 的原锁内再次检查；ready 后任何未接纳 receipt（包括 duplicate/foreign）、全生命周期计数不守恒或投影截断都会永久关闭 gate。新增三项真实源回归 case。test-only ready constructor 从创建 Witness header 时即使用冻结 contract hash `0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933`，不修改已经发出的 source row。

本次 agent 未运行任何测试、构建或远程命令。等待 root 锁定源码 hash、事前 Go、受影响父版本回归与新用例执行，再记录实际结果。
