# C0 汇总门最终静态审查

日期：2026-10-08。结论：**下列冻结版 `check_C0_gates.py` 与 `test_C0_gates.py` 没有未解决的静态阻断，可进入本次新工具的独立测试和受控集成。**本结论没有证明 C0 实际运行通过，也没有代替 source–Witness 比较器最终审查。本审查未运行测试、未连接 Ubuntu、未修改生产、旧证据或原 scope 报告，只新增本文件。

## 1. 冻结输入与审查范围

| 文件 | bytes | SHA256 |
|---|---:|---|
| `runtime/check_C0_gates.py` | 9660 | `287caa5253b7d983a70b9a3758b677f1a09c9a6230327a08a5d0aa035eb705be` |
| `runtime/test_C0_gates.py` | 8476 | `d53a50577e5b427af0963c967ba23ec88d19993dff1637c8eb88fc3eadf198dd` |

测试文件静态包含 22 个 test 方法。root 报告初版 20 项本地通过；最后两项缺项/类型回归及冻结版的实际运行仍应由新工具测试证据确认，本报告不将该信息写成“22 项已由审查人执行通过”。

对照读取了不改宽的 B0 `runtime/check_p1_execution.py`，B1 `runtime/run_r5_diag_validation.py`、独立 `check_p1_witness.py`，以及当前 B0 `safety/solver_worker.cpp` 的真实终端摘要结构。具体确认旧 reader 异常分支、正常报告字段、runner 的正常窗口结果、独立 audit/report_write 字段和 source summary 的来源。

## 2. 旧 source reader 错误不会被 prior passed 掩盖

旧 `check_p1_execution.py:1036` 的外层异常分支在已经计算 result 后，可能保留先前 `passed=true` 等字段，同时添加 `reader_error`、只保留 before inventory 和 reader issue。因此，仅采用旧 passed 或旧 checker RC0 会产生错误结论；本次汇总门必须独立否决这些异常，不可改旧 checker 结果。

新 `source_gate()` 同时要求八个基础完整性标志均为明确 True、`issues==[]`、没有非空 reader_error、normal_contract_complete 与 execute_qualified 明确 False。before/after inventory 必须都是非空且所有值为合法 64 位小写 SHA256，两个 inventory 完全相同，并与调用者重新读取的实际 input inventory 完全相同。指定 required_paths 必须非空且全部列在该 inventory 中。

因此，即便旧 report 的 passed 保持 True，reader_error、异常 issue、缺 after、读取后文件变更、缺 required 输入或未知生命周期仍导致 source_gate false。新门仅判本批 C0 是否闭合，不会反写、补造或放宽旧 report。

## 3. 摘要缺失、drop 与 worker 失败均阻止正常 C0

最终版不只依赖旧完整性标志，还直接要求实际 `regulator_summary` 与 `worker_summary` 为对象并具有正确 type。

- regulator 必须是 `source_summary`，generated/emitted 均为严格 uint64 范围整数且相等，dropped 为严格 int 0，normal_source_complete 明确 True。
- worker 必须是 `worker_summary`，generated_candidates/published_candidates 均为严格 uint64 范围整数且相等，fatal、terminal_numerical_failure 明确 False，normal_source_complete 明确 True。

这些字段与真实源码匹配：原 regulator Sink 终端摘要记录 generated/emitted/dropped/normal_source_complete；当前 B0 worker `solver_worker.cpp:33` 记录 generated/published candidates、fatal、terminal_numerical_failure 与正常完整性。布尔 False 不可借 Python 的 `False==0` 充当计数。摘要缺失、错误 type、计数缺失、drop 非零、fatal/数值失败或未知字段均否决。

终端位置、唯一 summary、flush 和源/bag 行数相等仍由原 base/lifecycle checker 负责；新门要求其 recording/lifecycle 完整标志并保持 issues 空，不宣称单个 summary 自身证明已经刷盘。

## 4. 10s 正常窗口与事前身份政策

policy 要求 `p1-C0-predeclared-policy-v1`、no_output、严格整数声明 10000000000ns、严格整数 log_capacity512。run_id 非空且与 context/summary/postrun/base/delivery/comparison 全部一致。八个 SHA pin 必须明确存在且格式合法：contract、diagnostic source、worker bin、regulator bin、runner、supervisor、Witness checker、base checker；boot_id 必须具有小写 UUID 结构。

context 的 mode、contract/boot、diagnostic source、两 bin、runner/supervisor 与政策逐项一致。base checker SHA 与政策一致；该字段确由旧 `check_p1_execution.py:1040` 实际生成，不是只在新测试夹具中存在的字段。

context 声明 duration_s 必须为数值 10，四个 fault 参数为严格 int0，expected_fault 为 none；fixed_witness 必须 enabled True，sink pause 为严格 int0。Witness 开启仅用于本批审计；故障与 logger pause 保持关闭。

summary 必须正常完成声明窗口、stop_reason 为 declared_duration_elapsed。window completion 要求实际 started/finished/observed 为严格整数，started>0，finished>=started，observed 等于时间差且至少 10000000000ns，required_duration_ns 为 10000000000、normal_window_complete True。postrun 不仅要自身正常，还须具有与 summary 完全相同的 window_completion 对象。operator stop、短于 10s、未知窗口、错结束原因或 postrun 的不同窗口不能通过。

该函数接受已解析事实，不能单独证明这些时刻来自真实 owned 运行。实际调用者必须保存并核验原 runner/context/window/ledger 的完整原件和读取哈希，不能用人工拼出的摘要替代真正采集。

## 5. 独立 audit、source report、delivery 与比较门分别闭合

最终版要求 postrun.fixed_witness_check 为对象，requested、passed、witness_complete、report_write_succeeded 均明确 True，issues 空，checker SHA 等于事前政策。不能只依赖 postrun.passed；audit 缺失、未知完整性或写出失败都拒绝。

`report_write_succeeded` 的实际来源已核对：B1 runner 在独立 witness_check.json 写出后才将此字段加入内存 report，然后写入 postrun。因此把此字段检查放在 postrun audit 内是正确的，不能误要求先前独立 witness_check.json 必然包含该字段。

postrun.normal_source_check 必须明确 passed True、严格整数 checker_returncode0。新门同时要求实际 artifact inventory 中明确存在合法 `base_report_sha256`，normal_source_check.contract_report_sha256 也必须合法，且两者相等。缺两边时不会使用 `None==None` 误通过。actual hash 应来自调用者对真实 base report 字节的独立读取，不得直接复制 normal_source_check 自报 hash。

delivery 必须 passed 与 application_delivery_accounting_complete 明确 True、issues 空；comparison 必须 passed 与 source_join_verified 明确 True、issues 空。source gate、独立 audit、实际 ledger 与 source–Witness comparison 任一失败都会使 C0 false，不能以另一个 passed 替代。

本函数不会自己读取比较器、artifact 或原始数据，也不重新实现 source join。比较器与其 policy/expected header/input 哈希必须由本次独立比较器和执行层真实验证，报告原件并列保留；本次汇总门审查不意味着比较器已通过最终审查。

## 6. 清理、真实返回码与无输出边界

summary 必须 failure None、cleanup_complete True、cleanup_failed False、supervision_evidence_complete True、graph_no_physical_publishers True。返回码 inventory 必须恰含 runner/base/delivery/comparison 四项，且各值为严格 int0；True/False、缺 key 或非零均拒绝。assets_unchanged 与 host_clean 均须明确 True。

实际输入仍需 root 的执行层使用预声明资产清单、真实 host 前后扫描和 owned supervisor；本函数只是消费这些已核实事实，不能把这两个布尔值自身视为哈希/主机扫描证明。前置 2340 项 B1 关闭清单与原 B0 v14 身份守卫、本轮新目录和工具 manifest、全 run 两物理 topics0、有限 owned 清理等条件仍按 scope/preflight 执行。

summary/postrun/comparison 的 normal_contract_complete 和 execute_qualified 也必须明确 False；正常结果固定输出 R5_complete、expected_log_overflow_mechanism_passed、M0b_formally_complete、M4_complete、F6_complete、P1_complete、normal_contract_complete、plant_acceptance_observed、execute_qualified 全 False。C0 只代表有限正常无输出完整 owned 对照，不能授予压力机制、正式冻结或物理执行资格。

## 7. 冻结前发现并已关闭的问题

静态审查期间已向 root 报告并在最终冻结版复读确认关闭：

1. 最早版本未直接验证 source/worker summary：已加入正确 type、严格计数、正常完整性与 fatal/数值失败门。
2. combine 顶层字典预检未含 base，base=None 会进入 .get 异常：现包含 base，明确返回 C0 false。
3. policy.pins 或 normal_source_check 为 None/list 时，前面的 type 判失败后仍可能 .get 异常：现 pins 在无效时规范为仅供安全拒绝的空字典，normal hash 分支有独立 type guard；已有对应静态测试定义。
4. normal 与 actual artifact 同时缺 base report hash 时，None==None 可能被接受：现明确要求 actual key 存在、两边合法64hex后才比较；已有对应回归定义。
5. summary 与 postrun 可以引用不同正常窗口、postrun 原 source 报告与 actual report 未绑定：现窗口完全相等，base report 字节 SHA 独立绑定。

以上修正在真实 C0 启动前完成，没有依据某个现场失败放宽事前时序、正常 source 门、阈值或 qualification 政策。后续若出现现场失败，仍必须保留原失败批次；修工具需依据锁定源语义、升版本、复审和新事前声明，不得回写该批为通过。

## 8. 结论与后续条件

在上述两个 SHA256 对应的冻结源代码上，未发现 reader 错误、缺摘要、错身份、短窗口、缺独立 audit、报告缺 hash、非零 RC、清理失败或物理端点未知被合并为 C0 true 的静态路径。允许完成本次新工具的必要独立测试、最终比较器审查和执行层集成检查；实际启动仍按事前 scope/preflight 和资产/host 门。

测试通过、报告实际生成、source–Witness 完整 join、实际 10s、正常 source/bag/ledger 与前后守卫的最终结果必须由 root 单列真实证据。本报告不执行或代替这些步骤。