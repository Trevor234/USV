# C0 驱动候选只读审查（2026-10-08）

结论：实际 runner / delivery / comparator / combine 接口已匹配；本次审查发现一个需要在 C0 启动前处理的外层超时清理缺口。该问题不会使已有组合门自动通过，但会使 `outer_cleanup_complete` 的范围小于整个 C0 owned 生命周期。没有执行远程命令、ROS 或 C0；没有修改冻结 runner、supervisor、比较器或驱动代码。

## 审查对象与范围

- `remote_run.template.py` SHA256：`2497e8bc0003071221c2e2a4c2403540e689ec0abdb7b40fd492dcc8b19eeead`。
- `pack_C0_tools.py` SHA256：`a8c93f15254194d48a053d67794a60f8b54758ef0074688b6c955d28271c7875`。
- 冻结 `owned_process_supervisor.py` SHA256：`7b85044e270e463ff785c957417398ac5f24669aef3f6f9cdbaf7468bbde4173`。
- 只读交叉验证冻结 `run_r5_diag_validation.py`、`check_resource_delivery.py`、`run_worker_fault_matrix.py` 与当前 `check_C0_gates.py`。本报告不是 R5 机制或 execute 判定，也不是现场性能报告。

## 已核实的兼容部分

1. 驱动传入的 `--diagnostic-bin`、`--diagnostic-source`、`--diagnostic-source-sha256`、`--witness-enabled`、`--witness-file fixed_witness.json`、`--test-sink-pause-ms 0` 和原 runner 参数均存在。所有其他 fault hook 使用默认 0；冻结 runner 在创建运行目录前拒绝任何正故障参数。声明正常窗口为 10 秒。
2. source checker 的实际路径为 `normal_source_check/contract_report.json`；runner 实际产物为 `run_context.json`、`runner_summary.json`、`postrun_checks.json`、`witness_expected_header.json`、`witness_check.json`、`fixed_witness.json`。驱动路径一致。
3. delivery 的实际 CLI 为位置参数 experiment 加 `--base-report`、`--output`；实际输出是输出目录内的 `resource_delivery_check.json`，结论字段是 `application_delivery_accounting_complete`。当前组合门使用了这个实际字段。
4. comparator 的 `--output` 是单个 create-only JSON 文件；驱动调用正确。comparator 不提供 `evidence_sha256`，最新版驱动已独立检查它的 `input_sha256_before == input_sha256_after`、`raw_inputs_unchanged is True`，并重新读取每项文件 SHA，覆盖 Witness、独立 header、source 和 context。
5. `combine(**reports, ...)` 的六个参数名与函数签名一致；正常窗口、旧 source/bag/checker、delivery、Witness、source—Witness、RC0、owned、host 和资产门分别组合。旧 checker 的 after-hash 错误不能仅凭 `passed` 被批准：组合门还检查 reader error、issues、输入清单前后与 fresh SHA。
6. packer 只安装旧 49 个 runtime 的字节相同副本、新 4 个工具及预声明附加产物；新工具测试选择仅 comparator 与 combine 的 49 distinct tests。部署和执行入口分开；包安装没有 C0 launch。旧资产 2340 清单与工具 53 文件 / extra 文件的前后 SHA 守卫存在。policy 固定单次正常 10 秒、pause 0，未扩大 R5 或物理发布权限。

## Blocking：外层超时可以先杀 runner，留下它的独立 owned 进程组

`remote_run.template.py:call` 在 deadline 后调用 `sup.stop(item, .5, 1, 1)`。这在 SIGINT 后最多 0.5 秒、SIGTERM 后最多 1 秒就升级到 SIGKILL。runner 为 SIGINT 和 SIGTERM 注册停止请求处理器；它的 `finally` 依次清理 regulator、worker、fixture、recorder，每项使用合同的 0.5 秒 / 1 秒 / 1 秒，recorder 前还有 0.25 秒等待。四项最坏预算为 10.25 秒，另有逻辑停止及 ROS 关闭。外层升级到 SIGKILL 的 1.5 秒不足以容纳该流程。

更关键的是旧 `Supervisor.spawn` 对每个 child 使用 `start_new_session=True`；旧 `Supervisor.members` 只认 `entry['pgid'] == item.process.pid`。因此外层 runner 的 PGID 集合不含其内层 regulator / worker / fixture / recorder 的独立 PGID。外层杀 runner 后，内层子进程可能仍在运行；`outer_cleanup_complete=True` 此时仅表示 runner 自己的组为空。

本地纯内存复现：通过 AST 提取冻结 `Supervisor.members` 方法，提供 boot 相同的假 proc 表：runner PID/PGID/SID=1000，child PID/PGID/SID=1001、PPID=1000。返回集合仅 `[1000]`，遗漏 child 1001。断言通过，没有创建 OS 子进程。这证明清理范围缺口，不声称现场已发生超时。

最小修正应在新外层驱动完成：允许 runner 的有限内层清理预算；对于仍需强杀的 runner，必须核对并保全其独立 owned ledger 身份，或明确将内层清理作为未知 / 失败且停止后续调用，不能把 runner PGID 为空当作整个运行已清空。只增大 grace 降低风险，但不自动证明不响应 runner 的独立子组已退出。无需改变旧 Supervisor / runner 字节，也不应使用按名称或发现结果的全局 kill。

## 非 blocking 的结果消费注意

当前脚本捕获执行失败、写 `C0_run_result.json` 后正常打印；未显式 `sys.exit`，所以失败的外层 Python 仍可能返回 0。`C0_complete` 会保持 False，因此只要调用方明确读结果并要求这个布尔值，不能造成 C0 伪通过。若调用方只凭 shell RC0，必须补独立 JSON 门或让外层失败返回非零。

本报告只记录上述 SHA 对应候选。root 后续修正应创建新版本和新 SHA、保留旧安装与测试证据；本报告没有授权覆盖已冻结远程包。
