# C0 的实际 bag、source 与 owned 账本：只读审查

审查日期：2026-10-08。审查者：`b1_witness_finish`。本次只读审查既有工具及本轮比较器接口，没有连接远程主机，没有运行测试，没有修改旧工具或任何原始证据；只创建本报告。

结论：**旧正常 checker 能验证完整已关闭源文件中的 Job、Candidate、Decision 与实际 bag 的全量身份集合及已定义 payload 一致，范围包含就绪和关闭尾部，没有按 10 秒测量窗口裁剪。** 但 `source_bag_contract_complete` 单独只代表 recording scope，不能代替 owned 生命周期、关闭 flush、完整测量窗口或 Witness 对账。C0 的组合门必须读取完整旧报告，把这些事实逐项相与，不能只信旧报告的 `passed` 或 runner 的摘要。

一个必须明确的前提是：bag 的 `bag_receive_ns` 属于 storage timestamp；它不是 `CLOCK_MONOTONIC`。旧 reader 明确不将二者相减。本审查支持“全 bag 与全 owned 源文件对账，非窗口局部对账”，**不支持“bag 接收时间已用数值证明位于 monotonic 全局区间内”**。若这里的“全局范围”指完整归属文件和进程生命周期，则已有实现支持；若指跨时钟时间区间，则没有相应映射证据。

## 审查的精确版本

| 工具 | 本地可审查副本 | SHA256 |
|---|---|---|
| 旧 typed bag / source / 生命周期 checker | `m0b_contract_implementation_20261007/runtime/check_p1_execution.py` | `469563fb55523e0202725fdc6fc18af446ece84b612c79ee85794e0288829262` |
| 旧 application 输送账本 | `m0b_contract_implementation_20261007/runtime/check_resource_delivery.py` | `b84d33025f53c92c5af211c5a388cccfa432f0ba825fe41a7975ed13866805aa` |
| 旧 owned supervisor | `m0b_contract_implementation_20261007/runtime/owned_process_supervisor.py` | `7b85044e270e463ff785c957417398ac5f24669aef3f6f9cdbaf7468bbde4173` |
| B1 完成后的正常诊断 runner | `m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py` | `c8bc0141e3ad7b37ff07b1e3ce440c47b01e4386b90bf9f362beda1922ea0766` |

上述相对路径均位于本工作区 `work/p1_execution_architecture_2026-10-05/` 内，SHA 与 B1 已冻结完整运行目录中登记的对应版本一致。本实现使用 `check_p1_execution.read_bag()` 和 `rosbag2_py.SequentialReader`；没有以未读取的独立 `bagio` 模块作为依据。

## 全量 bag 读取与三流对账

`read_bag()` 在 metadata 中读取 storage 类型、topic type、逐 topic count 和总 count，允许 mcap 或 sqlite3；随后打开实际 storage，比较实际 topic type，完整执行 `while reader.has_next(): read_next()`。所有 topic 都进入实际计数；四个 P1 typed topic 被反序列化保存，AppliedControl 存在时也检查类型并读取。它没有设置 storage filter、seek 到窗口、或按 `window_start.json` 排除前缀和尾部。

独立 scan 的逐 topic count 与 metadata 必须一致，总 count 也必须一致；type、反序列化或 storage 读取异常不能成为正常证据。raw 的 clock/odom/imu/path/profile 在此范围只提供完整实际 count 与 fixture 发布 count 对照，不是逐 callback 的重建。

`validate_decoded()` 用完整 regulator JSONL 和 worker JSONL 建立 source 索引，用完整已扫描 bag 建立三流索引：

| 流 | 源位置与索引键 | bag topic | 全量检查 |
|---|---|---|---|
| Job | regulator 的所有 `type=job`，`job.job_id` | `/p1/solve_job` | source/bag identity set 相等，全部 `JOB_FIELDS` 完整且等值，重复 id 拒绝。 |
| Candidate | worker 的所有 `type=candidate`，`job.job_id` | `/p1/solve_candidate` | identity set、`CANDIDATE_FIELDS`、完整原始 Job echo 相等，重复 id 拒绝。 |
| Decision | regulator 的所有 `type=decision`，`sequence` | `/p1/execution_decision` | identity set、完整 v2 Decision fields 相等；全量 Decision sequence 从 1 连续，重复或缺口拒绝。 |

字段别名转换后比较的是已定义结构，包含 run、boot、contract、worker instance、generation、timing、状态/参考、候选原生结果与接纳数据；不能只用三流总 count 替代这一检查。布尔值类型保持严格；有限数值按相等语义比较，不能称为 CDR 原始字节完全相等。

全部 Job 的 run/boot/contract/nominal/owned worker instance 被核对，Candidate 绑定其原 Job 和同一个已验证 worker，Decision 绑定 run/boot/contract/mode。与 owned worker PID/instance 相符的 capability 必须存在于 bag。其他 run 的 capability 被该 capability 循环略过；因此该门的归属结论主要指 Job/Candidate/Decision 三流，不能改写成“bag 中每个 topic 的每条消息都有同样的归属证明”。

最终 `streams.jobs/candidates/decisions` 报告各自 `source_count` 与 `bag_count`。这些是整个已关闭文件/实际 storage 的计数，含 readiness 和 shutdown tail，不能标作恰好 10 秒窗口中的计数。

## 为什么 recording flag 不等于全 owned 关闭

旧 checker 将问题分为 recording、logical、lifecycle scopes。`source_bag_contract_complete` 是 recording scope 没有问题的结果；下面这些 owned/关闭事实属于其他 scope，仍必须另外通过：

1. startup 恰好一个，run/mode/contract/boot 与 context 相符，startup PID 与 regulator 的 owned spawn 相符。
2. `owned_process_ledger.jsonl` 的 boot 统一，spawn 无重名，regulator/worker/recorder/fixture 的身份含 `pid==pgid==sid`、正的 `start_ticks`、`executable_verified=true` 与实际 exe SHA。
3. 恰好一个 `worker_capability_verified`，PID/instance/backend 与 owned worker 相符；context 的 worker/regulator binary 现存 SHA 与 spawn 的 expected SHA 相符。
4. 恰好一个 terminal `supervisor_summary`，它是 ledger 最后一行；runner 记录 `supervision_evidence_complete=true`。
5. regulator/worker/recorder 的 cleanup 结果与 ledger 中唯一对应 `cleanup_result` 相符，退出码已知，`cleanup_complete=true`；全体 owned 清理由 summary 和 terminal ledger 的 `cleanup_failed=false` 支持。fixture 的 spawn、原始发布 summary 与全局 cleanup 也必须保留。
6. regulator/worker source 恰好一个 terminal summary，并且是各自文件最后一行；regulator 的 generated/emitted/实际行数相等、dropped=0，worker generated/published candidate 与全量候选数量相等，fatal=false，两个 source 的 `normal_source_complete=true`。
7. summary 位于 flush 之前，不能单靠它证明落盘。checker 还要求 regulator/worker returncode=0，console 各恰好一个 `*_CLOSE_FLUSH_SUCCESS=true`，且没有 false token。

source JSONL 要求非空、最后一行 newline 关闭、无空行、每行有 type；源损坏、summary 缺失或 counts 不完整会产生明确失败。owned supervisor 每个信号之前检查 boot、leader PID/start_ticks、PGID/SID、已观察后代身份；观测写盘失败时记录 `evidence_failed`，禁止后续启动，但继续有限 owned 清理。清理成功本身不证明源完整。

B1 正常 runner 在逻辑停机之后保持 fixture clock 和 recorder，随后按 **regulator → worker → fixture → recorder** 的顺序清理，在 recorder 停止前另留 250 ms。这样 bag 能保存 regulator 关闭 Decision 与 worker 尾部 publication；最终完整 source/bag 比较将检查这些尾部是否确实记录，而不是把“等待了 250 ms”当成输送保证。

## 静态发现：旧异常分支不能仅信 passed

发现旧 `check_p1_execution.main()` 的一个后置异常处理缺口：`validate_decoded()` 已经返回 `passed=true` 后，如果计算 `input_sha256_after` 时文件突然变为不可读或消失，外层 `except` 只新增 `reader_error` 和 recording `issues`，没有重置前面已返回的 `passed`、`diagnostic_complete` 或 `source_bag_contract_complete`。最后返回码仍由 `result.passed` 决定。因此只读取 RC0、`passed=true` 或 runner 的 `normal_source_check.passed`，不能保证未知源/后置读取失败不被通过。

这是一项**静态代码发现**，本审查没有注入故障或宣称已经实际触发。已告知主任务及比较器代理；不修改已冻结的旧 checker。C0 的独立组合门需要读取完整 `normal_source_check/contract_report.json`，对 `reader_error` 存在、`issues` 非空、`raw_inputs_unchanged` 不是严格 true、before/after map 缺失或不完整、pin 不匹配等情况严格拒绝。这样可在本次 C0 的授权范围内保持未知状态不通过，而不重写历史工具结果。

三流或 fixture 的显式 parse error、正常 summary incomplete、前后 hash 明确不同等常规分支已经会置相应门为 false；不能把这点扩展为旧异常处理所有分支都能自动 fail closed。

## 结果文件与组合规则

同一次 create-only owned run 应保留以下相互独立的原件。比较器的输出路径由 `--output` 事前指定，下面不假定一个尚未声明的固定文件名。

| 文件/结果 | 必须读取的关键字段 | 证明范围 |
|---|---|---|
| `run_context.json` | run_id、mode、boot_id、contract_sha256、binaries、source_files、runner/supervisor SHA、fixed_witness、declaration | 本次运行与各工具、诊断二进制、worker 和合同的身份；no_output、diag5、pause0、全部 fault0、10s 由事前政策核对。 |
| `owned_process_ledger.jsonl` | spawn/capability_verified、window start/end、cleanup_result、terminal supervisor_summary | 真实归属、就绪、测量窗口、关闭和清理。 |
| `runner_summary.json` | failure、stop_reason、cleanup_complete/failed、supervision_evidence_complete、graph_no_physical_publishers、window_completion、sources | 运行错误、图观测和窗口/清理摘要；不是 source 完整性独立证明。 |
| `raw_bag/metadata.yaml` 与实际 storage 文件 | 全 topic types/counts、实际 typed messages | 完整实际录制输入，必须在关闭后独立扫描。 |
| `normal_source_check/contract_report.json` | schema、run_id/mode、checker_sha256、passed、diagnostic_complete、source_bag_contract_complete、logical_admission_contract_passed、lifecycle_verified、raw_input_recording_complete、activation_source_contract_complete、streams、issues、reader_error、raw_inputs_unchanged、input_sha256_before/after | 旧 checker 的完整 source/bag 与 owned/逻辑门；C0 组合必须看原报告，不能只看 runner 转抄的少量字段。 |
| `normal_source_check/contract_report.md` | 与 JSON 对应的可读说明 | 展示产物，判断以完整 JSON 和 SHA 为准。 |
| `witness_expected_header.json` 与 Witness 原文件 | 独立 header pins、完整四流、counters、first failure | 归属固定记录及其终端关闭，含完整 owned 生命周期。 |
| `witness_check.json` | passed、witness_complete、scope、source_join_verified=false、evidence SHA | Witness 自身完整性；单独不证明 source 或 bag 对账。 |
| C0 comparator 的预声明 `--output` JSON | schema=`p1-C0-source-witness-comparison-v1`、passed、source_join_verified、scope=`full_owned_lifecycle_regulator_source_to_fixed_witness`、basis_witness_check、context_verified、counts、input_sha256_before/after、raw_inputs_unchanged | regulator source ↔ Witness 的完整身份/时间逐项对照。它不读取 bag，不产生 `source_bag_join_verified`，也不复制旧 bag flag 为 true。 |
| `postrun_checks.json` | normal_source_check、fixed_witness_check、window_completion、normal_window_complete、passed、C0_comparison_performed=false | B1 runner 原来的正常收集门；不包含新 comparator 的完整组合。 |
| 独立 application ledger 结果目录内 `resource_delivery_check.json` | passed、application_delivery_accounting_complete、counts、jobs、issues、scope、evidence_sha256 | 全量应用边：submit→worker receipt/outcome→candidate publication→registration，并以 bag multiset 再次对照。须另行调用工具产生，B1 runner 本身不会自动生成。 |
| 本轮最终 C0 独立组合 JSON（主任务预声明路径） | 上述各门的独立结果、其文件 SHA/身份、实际 window 完结、normal/execute/R5=false | 最终 C0 判断；应明示三类 join 的各自范围。 |

若主任务使用 `source_bag_join_verified` 名称，它只能作为独立组合结果：旧 checker 返回码 0，完整报告 schema/run/mode/checker SHA 正确，`passed`、`diagnostic_complete`、`source_bag_contract_complete`、`logical_admission_contract_passed`、`lifecycle_verified`、`raw_input_recording_complete`、`raw_inputs_unchanged` 均严格 true，`issues=[]`，没有 `reader_error`，before/after SHA map 完整且相等，且对应真实本次 owned 输入。还应核对 v2 当前激活来源门 `activation_source_contract_complete`，不能让未知激活来源获得 C0 完整链资格。

随后将这个 source/bag/owned 门与 comparator 的 `passed && source_join_verified && context_verified && raw_inputs_unchanged`、独立 Witness 完整门、完整 10s 正常测量门、运行无错误、监督证据完整、owned 清理完整，以及独立 application 输送账本门相与。各报告身份及 SHA 必须指同一次运行，不能用另一份旧 run 的成功报告填补本次缺口。输出或核查失败、缺字段、unknown 或 false 不能归为通过。

旧 application ledger 检查 publisher/source/bag multisets、唯一 worker receipt/outcome、publisher success、candidate registration；缺少边或多个未解释 outcome 均拒绝。它的 `evidence_sha256` 在 scan 后生成，没有自行提供完整 before/after 不变门，因此本轮组合还应以旧 checker 的完整 input pin 和最终只读前后 asset/hash 核查覆盖它所使用的同一份 source、context、base report 与 storage。`dds_internal_loss_count=null` 必须保留，应用账本缺口不能推断 DDS 内部丢包原因。

## 资格及计数边界

旧 checker 在 no_output 模式中要求 startup 物理 publisher endpoint 为 0、runner 图观测 `graph_no_physical_publishers=true`，Decision 的物理 publication flag 均 false。其 `passed` 在此模式代表诊断完整，`normal_contract_complete` 仅 execute 模式可为 true；diag5 的 `execute_qualified=false` 必须保持。C0 comparator 的 `source_bag_contract_complete`、`normal_contract_complete`、`expected_log_overflow_mechanism_passed` 和 `execute_qualified` 也固定为 false，避免一个 source↔Witness 门被当成其他门。

就绪与关闭尾部的全量 count 和有限 timing 样本可以分别报告，但不能借它们推断完整 10s 窗口已结束。窗口要求 `expected_fault=none`、实际 `stop_reason=declared_duration_elapsed`、实际 elapsed≥声明 10s；早停、watchdog、运行异常和未知窗口均拒绝。

正常 source完整、bag全量匹配和有限无输出接纳不证明 plant ACK、真实推力、两物理通道原子执行、精确 plant 时间步、GP 训练资格或最坏实时界限。C0 最终若通过，只能完成本阶段正常对照；R5、M0b 正式冻结、M4、F6、P1整体及 physical execute 的资格仍须保持关闭。
