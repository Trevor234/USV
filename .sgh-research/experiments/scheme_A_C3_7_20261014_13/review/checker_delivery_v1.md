# C3.7 当前接入只读复核与检查器交付

日期：2026-10-14。查看节点、Worker 专用 peer、driver 当前控制流和新 Witness-v2，未修改这些生产文件。检查器及其有限测试为新 N14 文件。

## 接入复核

Worker 认证在应用 publisher、Sink 和业务线程启动前完成，绑定 Worker 的两个接口、角色/process/pidfd/source/binary/完整 typed config。实际 Capability/Candidate 回调携带 MessageInfo；有限 resource shape 和实际 GID/pidfd 验证先于完整 CDR、语义回调、lease/ready merge。被拒绝回调仍增加接收计数，metadata 与同一 business lock 下 before/after 快照留证。

完整 Candidate/Job echo、native success/prediction、clock/state/history、deadline、lease/liveness 和最终 ready/activation 时点沿用原守卫。GID认证点、后续alive poll、raw CDR生成和语义完成点在 Source 中分别记录；认证点不能替代最终 ready completion。

main 使用 SingleThreadedExecutor；移除节点后才声明 executor_detached，随后 join tick/prep 并发出一次 receiver-close 原生计数，再关闭 Sink/Source 和 Witness。接收闭合是观察人口事实，Worker endpoint 退出仍 unknown。当前正常 driver 的实际停止顺序是 Publisher→Observer→Worker→synthetic source→Recorder；declared close_order 描述不能代替控制流/ledger。Worker 最后 Capability 可以在 Observer 已关闭后仍被 Recorder 记录。

没有发现需要阻止本轮构建的新接入问题。仍需实际构建、source-linked/native 正负例、真实 bounded run 和独立回读才能形成组件验证结果。

## 检查器范围

新 `check_c37_owned_run.py` 明确要求 preregistered `closed_shadow_observation` profile，不采用旧 v1 normal Witness 或事后固定数量。完整扫描实际 Storage/CDR、transport、Publisher session、Worker Source header/attempt/result/terminal；Capability full19 字段/typed IEEE digest 与完整 CDR关联，Job/Candidate/publish result 人口及不可变 echo关联。

每个 Worker received callback 的 sequence/count 与 receiver-close 原生计数闭合；完整 MessageInfo GID、typed CDR、before/after typed snapshot、语义 receipt 和真实 receipt-lease replay 分开核验。正常4s profile要求资源域内、live-owned回调；resource/foreign/process-exit 拒绝由 source-linked/native 场景单独验证，不被伪装成正常业务。Worker actual SIGINT 必须晚于 Observer receiver-close 和 Source flush。

Observer 接收是完整 Storage 的 occurrence subset。相同 Capability 完整 payload 没有 wire packet ID，报告中的 greedy storage ordinal 只分配等价 payload occurrence，不能指认某个唯一丢包。未关联的存储 occurrence 明示保留；闭合 Source 不能授权 all-subscriber delivery。

新 Witness-v2 decoder 校验完整型别、固定stream counters与profile；本检查器另外关联所有 Source tick/submit/activation attempts，精确绑定首次真实 Accepted 的 BusinessReady 与末尾 Source-flush/Close。全拒绝观察可完整，normal business/阶段/研究资格仍分别记账。未在 Source 中逐条输出的 phase 仅具有 POD完整性范围，不冒称全部 callback因果已由Source证明。

22 项有限 Python predicate 测试通过（Worker人口15项与Source/Witness人口7项），包括明示 terminal未接收正例、GID/型别/顺序/echo/人口/closure-counter反例，以及 Accepted/全拒绝两种Witness Source正例。它们是有限copy/predicate验证，真实DDS运行数为0。实际run尚未由本检查器评价。

旧资产、旧helper、旧normal gate及失败不变。具体文件SHA见同目录 `checker_delivery_v1.json`；root 构建与run前仍应冻结最后版本。
