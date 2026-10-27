# R5 独立 runner、验收 gate 与外层模板交叉审查

审查日期：2026-10-08。审查人：独立子任务 `b1_checker_finish`。

本次结论：以下最终版本之间的实际调用接口、产物字段与作用范围兼容；已发现的四项独立 gate 假阳性、JSON 加载接口错误和旧 delivery 入口调用错误均在冻结前修正。新 R5 三个工具的 **123 项本地离线测试通过**，其中 runner 42 项、mechanism 43 项、independent 与组合门 38 项。本次审查没有连接 Ubuntu，没有启动 ROS，没有启动或重跑 R5 实验。

## 最终审查对象

| 对象 | SHA256 |
| --- | --- |
| `runtime/run_R5_pressure.py` | `9aebd5f57ad3f408f881ebae7f5650c7a388a04a28a5ee3ffad9c8590661d367` |
| `runtime/test_R5_pressure_runner.py` | `d849c7865e7e98a4698a1c1e771b65677ed01390edc7e19bb6bb28ec6465ecd7` |
| `generate_R5_runner.py` | `b33cac90f59d3bfeb573e4dac37272f56a7607728099a19baf412e12be28dc0c` |
| `runtime/check_R5_mechanism.py` | `cef7bf29e2c52d422c9e101032bea205e50818abc4fe8f3f9f493627c4a275bc` |
| `runtime/test_R5_mechanism.py` | `a375bd4f36f31e5c438a186a7e0999fa21cea74ebda85d217a18671cf8c6c298` |
| `runtime/check_R5_independent.py` | `9053a8f592c9b01b06b7e5313a77f3be08e486b85412fc639cbf1104d5d046db` |
| `runtime/test_R5_independent.py` | `e26635fd7b3df6b193aa3208d9a7f7e7cde92edc16de33bb9b2d4c00e6e985cf` |
| `remote_run_R5.template.py` | `f5a7f581766a4aebd736b5de4a38299a80b8b99f914a47ed6504a00294471e4d` |

原 B1 正常 runner `run_r5_diag_validation.py` 保持 `c8bc0141e3ad7b37ff07b1e3ce440c47b01e4386b90bf9f362beda1922ea0766`，未修改旧 B0/B1/C0 工具、生产 C++ 或历史证据。模板包含待填的政策 SHA 与测试数量占位符，部署生成物须另行锁定 SHA。

## 修正并复验的问题

审查最初使用 `test_R5_independent.fixture()` 构造四项纯内存负例，初版均返回 `passed=True`。修正后复测结果如下，正常 fixture 仍返回 `passed=True`、`issues=[]`。

| 负例 | 最终结果与主要 issue |
| --- | --- |
| `candidate_publish_result.publish_start_ns=1, publish_end_ns=2`，早于真实 solve | 失败：`candidate_publish_complete` |
| Job receipt 的 `receive_ns=-1, commit_ns=-1` | 失败：`worker_receipt_chronology`、`candidate_receipt_time_echo` |
| owned terminal 前插入 `name=foreign` 的 signal | 失败：`unknown_role_signal_or_descendant` |
| 全部匹配 Job 中 `N/horizon_steps` 同步改为 `20.0` | 失败：`native_job_shape` |

修正版要求 receipt receive→commit→solve、Candidate 源时间→实际发布开始→发布结束的真实顺序；Job echo 与 cleanup 字段使用递归且区分类型的比较；整数 horizon 和浮点 dt 保持接口类型；未知角色 signal/descendant 拒绝接纳。

另核对了两项真实入口问题：

1. 冻结的 `check_p1_witness.load_json()` 返回 `(value, SHA256)`。独立 gate 的政策、context、summary、contract 四处调用现已解包，且有真实临时文件 CLI 测试。读取或事后计算 SHA 异常会生成失败 JSON。
2. 冻结的 `check_resource_delivery.main()` 不接受 argv 参数。独立 runner 现通过临时 `sys.argv` 调用旧 `main()`，并在 `finally` 恢复 runner argv。原工具实际 RC 和报告原样保存；异常保留 unknown RC，不捏造 RC2 或正常报告。两项定向离线测试验证正常失败返回与异常恢复。

## runner 与两个 gate 的兼容关系

独立 runner 在建立 run 目录、context、header 与 owned 记录之前校验配置。限定 `no_output`、diag5、fault flag 真布尔 True、Witness 真布尔 True、Sink pause 真整数 5000 ms、声明窗口 15 s 上限，其余四项 hook 真整数 0。Witness 文件使用本 run 的固定相对文件名 `fixed_witness.json`。AST 与运行时测试确认只有末尾一个 main guard，在压力 helper 和新 main 定义之后调用；自身 runner SHA 来自新文件，旧 normal main 不会先运行。

原完整 readiness 门保留。发 arm 之前须读取已经落盘的完整 source 行，并匹配至少两条不同真实 Job、acados native Candidate、registration、source Decision 和 typed accepted Decision 链。prearm helper 另要求 receipt/registration 自身 worker identity、registration 的成功 reason、solve times 和 first_control 与 native Candidate 一致，typed 收到时间不早于实际 activation commit。未 flush 的 source 只作为 pending，最多等待有界 readiness 时间；不会补造或无限等待未知证据。

冻结前核对原生 worker 与 regulator 源码后，进一步区分两种 `reason`：Candidate 复制 native answer 的诊断文本，要求真字符串，但成功且 prediction available 时可以非空；registration 的 reason 表示接纳拒绝原因，成功接纳仍须空字符串。此修正来自既有源码语义，未依据现场结果调整。新增定向测试证明非空 native 诊断加成功、预测与完整接纳链可以 arm，而 `success=False` 即使携带相同诊断文本仍被拒绝。

arm 仅尝试一次：先独立持久化 intent 和 owned event，再发布 Bool true，再独立记录实际 publish 起止时间和 `pressure_arm.json`。机制 CLI 进一步确认各 claimed 原始行确实存在于 runner 当时消费的两个 source prefix 内，并重验 prefix SHA。`window_origin` / `pressure_window_origin` 统一为 `arm_publish_start_ns`；时间起点为真实开始发布 arm 的时刻，最多 15 s。

自然 regulator RC2 记录为 `expected_sink_failure_exit`，保存首次 runner 观察退出的真实时间、`release_kind=natural_failure_exit` 与 `release_requested_ns=null`。它是退出时刻的观测上界。物理输出资格、normal contract 和 R5 机制成功始终不由 runner 授予。runner RC0 仅代表所声明的压力证据收集流程完成；机制和独立门仍须分别判定。

两份旧严格报告留在原路径：`normal_source_check/contract_report.json` 与 `strict_application_delivery/resource_delivery_check.json`。其实际失败 RC2 被保留。Sink 丢失不能替代完整 worker、typed bag、raw fixture 或 owned lifecycle 证据。独立 gate 比较完整生命周期的实际 typed 消息与 surviving regulator source、完整 worker source，核对五项 raw fixture 发布计数与实际 MCAP 扫描计数，要求四角色 cleanup 证据和实际退出值；它不会重建已丢失的 regulator 行。

机制门对 SourceFailure/Stopping/Invalidation/PauseEnd/Close 使用独立 Witness 证据。审查特别确认：Submit 或 accepted Activation 的 `failed=True` 晚采快照不单独证明门前违规；修正版保留异步快照计数，仍严格拒绝 Stopping 边界之后的 Submit 或 accepted activation，以及已知 failure 上界之后的 accepted activation。Submit 的 Witness 时间采在 `jobs_.push_back` 之后，故不单独依据晚采时间超过 failure 上界反推门前授权违规。失败响应量使用最近一次已知 failed=False 时点构造保守上界，不声明观测到 atomic store 的精确时刻。

## 外层模板静态审查

`remote_run_R5.template.py` 的 runner、mechanism、independent CLI 均与最终入口兼容；两个验收输出参数是单个 create-only JSON 文件。模板从 runner 保存的旧 base/delivery 结果读取真实 RC，不重跑后改写正常报告。组合门要求 runner0/base2/delivery2/mechanism0/independent0，以及独立 reports、输入 SHA、工具资产和 owned/host 清理全部通过。

模板在启动前和结束后验证 61 个 runtime 工具文件及额外工具、政策、旧闭合资产清单，固定 source/bin/contract/sink 资产。使用 outer Supervisor 和已审查的 C0 inner identity recovery：只从本 run ledger 的授权 PID/start_ticks/PGID/SID/exe/hash 身份清理；runner timeout 先给 SIGINT 和有限收尾机会，随后验证内外 owned 清理；不按进程名称扫描后杀进程。`verify_assets()` 与 `host_preflight()` 遇到资产 drift、控制器/fixture 残留或未知进程读权限会抛异常，使最终结果失败。

本次静态审查没有发现模板中导致旧入口误执行、正常报告覆写或无限等待的 blocking。root 仍须把模板替换占位符后生成的实际 driver、工具清单、正式政策和测试结果一起冻结。

## 结论范围与执行前剩余项

离线测试证明配置拒绝、接口调用、证据比较和典型负例的实现行为；它们不证明本机 DDS 在压力下的实际响应、source buffer 落盘速度、首次失效究竟发生在 TickStart 还是 DecisionEnqueue、实际 Invalidation 是否出现或实际 pause/shutdown 时间满足政策。

下一步仅是在正式政策、工具 SHA、预声明测试数量、同 boot 的资产/host preflight 均锁定以后，执行一次声明的有限 `no_output` Sink 压力采集。若首失效路径没有真实 Invalidation、任何 raw/worker/bag/owned 门失败、出现未知退出或输入改变，应保留原始失败证据并判定该次 R5 不通过。不得从已有 C0 或其他 R5 路径的成功补授权该分支，也不得依据现场结果放宽阈值。

本审查不授予 R5 已完成、M0b 正式冻结、M4、F6、P1 或 physical execute 资格。
