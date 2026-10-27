# B1 后续 C0 正常运行入口：静态审查

日期：2026-10-08。只读审查新增 `runtime/run_r5_diag_validation.py`、`runtime/test_r5_diag_runner.py`，并读取它们依赖的 B0 严格 checker 与拥有进程 supervisor。本次未连接远程、运行任何测试或修改已有文件；仅新增本文，不改先前 integration_review。

**结论：最终 SHA 对应的新入口没有未解决的静态阻断项，可继续新版本运行工具的依赖核对及纯测试验收。它实现的是未来 C0 的正常 no_output 收集入口，全部 fault/pause hook 为零；C0 对照、witness/source 逐项关联和 R5 溢出机制仍未由此入口实施或证明。**

## 1. 锁定输入及版本口径

| 文件 | 字节 | SHA256 |
|---|---:|---|
| 新 runtime/run_r5_diag_validation.py | 54329 | `c8bc0141e3ad7b37ff07b1e3ce440c47b01e4386b90bf9f362beda1922ea0766` |
| 新 runtime/test_r5_diag_runner.py | 17531 | `929a94df22dfbb3ee95ffee259055fb226e90f782a56ce4f9067b14e09bfdcd6` |
| B0 runtime/check_p1_execution.py | 76366 | `469563fb55523e0202725fdc6fc18af446ece84b612c79ee85794e0288829262` |
| B0 runtime/run_formal_no_output_validation.py | 39783 | `d8098c64defe3b477363c94a959de29eb60c899039885ac13cfd3ce2f5da01cb` |
| B0 runtime/owned_process_supervisor.py | 9875 | `7b85044e270e463ff785c957417398ac5f24669aef3f6f9cdbaf7468bbde4173` |

新文件位于 `C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/runtime/`；B0 文件来自相邻 `m0b_contract_implementation_20261007/runtime/`。旧 formal runner 的本地摘要与新增测试声明锁定的摘要相同。

本审查锁定的是这次修订后的新 runner/test，没有把此前构建或远程工具测试失败记录回写为通过。新版本部署与结果须使用新目录、保存旧失败归档。先前 integration_review 的固定输入仍属于其原审查快照；Sink 测试格式后续编译修订不能悄悄套用到旧摘要。

## 2. 入口与默认关闭

[validate_normal_parameters](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py:50) 在创建运行目录与 ROS 初始化前拒绝任何非零 delay/native-block/prepare-block/tick-block/Sink-pause。main 的 fixture-child 分支也位于这个全 hook 为零的 CLI 门之后。诊断 C++ 命令固定 mode=no_output，prepare/tick/Sink hook=0；没有发送 arm_sink_pause 消息。文件名中 r5 并不表示已开放 R5。

合同先调用 B0 full_load，指定 mode=no_output、runtime=True，再要求完整 v2 diagnostic revision5。它不只读取旧 revision 字段，也不绕过完整字段/类型/固定 profile 校验。支持诊断合同中的故障许可位不等于本入口实施故障；非零实验参数仍被拒绝。

witness 默认 false。开启须显式提供 owned witness-file；关闭却指定文件也被拒绝。fresh witness 路径必须直接位于本次 create-only 运行目录内，不能逃出目录、进入子目录、覆盖已有文件或与源日志、bag、context、expected-header、checker等保留路径冲突。运行根须已存在，运行目录 mkdir(exist_ok=False)，不会接续旧 run。

关闭模式没有传 witness-file/worker-instance 参数给 regulator，terminal_witness_check 不创建 witness 或 audit checker文件，也不声称 witness_complete。driver 仍保存独立 expected-header 元数据及 worker handshake，用于来源绑定；这份元数据不等同启用了记录。

## 3. 独立身份与真实 worker instance

资产摘要来自 driver 自己读的 contract、diagnostic translation unit、真实可执行文件和 Python/ros2，而不是从 witness 文件复制。诊断 executable/source 还检查正确 basename、存在的普通文件；调用方提供的事先源/bin SHA 如不匹配，在目录创建前拒绝。SHA 参数在 CLI 中是可选的，因此实际 C0 仍应由外层已冻结 manifest/资产守卫提供并核对预声明 hash；仅由入口当天计算的摘要不能自行代表已验收的 B0/clone 来源。

worker 通过原 Supervisor 启动，绑定 proc 的 PID、start_ticks、PGID、SID、boot 与 exe SHA。driver 的真实 ROS subscription先收到 capability，再把其 pid 与自己拥有的 worker child PID比对，核对 run/boot/contract/nominal、acados、非fatal、CLOCK_MONOTONIC、column_major、20/.2、fault许可位与64小写hex实例；worker还须在 regulator启动前存活。

本轮指出并已修复 capability 启动条件遗漏：[verify_worker_capability](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py:85) 现要求 startup_ns 是正 signed-int64整数，并补齐 matrix_layout=column_major。不会把0、负数、bool、float或超过int64的值当成有效启动时间。worker_instance使用实际 capability值，不尝试从PID重算原worker含启动 monotonic 的digest。

[expected header](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py:102) 从 driver已有context、资产hash和已校验instance构造，在启动 regulator之前以exclusive JSON保存，并在拥有进程 ledger锁定header/hash。CPP独立读取/proc/self/exe、worker exe与source，并校对这些pins。后续callback只接受已锁PID/instance的capability。

terminal验收重新读取expected-header，但必须与driver内存保存的expected_header相等；再分析witness，并核对读取前后文件SHA。它没有从witness.header构造expected，也没有因expected文件和witness同时被改就自洽通过。数据pins的独立性已保留；这些材料仍需由实际运行前后外层守卫和ledger保存。

## 4. 主机、采集与清理

host_preflight扩展包含 p1_regulator_r5_diag，以及旧 normal、新 formal、新 diagnostic三种 fixture-child脚本；原controller/PPO/Gazebo禁并行检查和cmdline不可读即拒绝保留。driver与所有children使用ROS_DOMAIN_ID=96、ROS_LOCALHOST_ONLY=1；启动前发现既有ROScontroller/fixture或任一物理输出topic publisher就拒绝，启动等待及正常窗口继续观察零物理端点。

bag recorder先由已验证Python启动，实际 recorder订阅齐全后再启动worker。fixture须实际clock/odom/imu/path/profile五个writer同时匹配recorder与regulator，保存owned pid/boot/contract/armed_ns及计数后才发数据。窗口就绪要求arm之后有效owned capability、来源decision及同job实际candidate；readiness明确 candidate_acceptance_required=false，不把启动就绪伪装成激活成功。enabled witness的独立checker后续另要求真实BusinessReady与activation coverage。

该窗口从业务就绪后计时。source、bag和witness记录包含owned准备/关闭尾部，因此full-owned计数或tick极值不能默认视为严格裁剪的10秒测量区间。C0对照须独立声明两个口径的关联。

结束先发逻辑stop，保持fixture与recorder供关闭尾部使用，再依次清理regulator、worker、fixture、recorder；原Supervisor只对本次minted group及身份核对通过的members发送信号，等待均为contract中的有限界，没有按发现列表清理外部进程。source观察仍标completeness_proven=false，真正源/实际bag验收交给原严格checker。

## 5. 正常窗口完成门及源/audit分账

本轮发现的另一个问题是operator stop可提前结束，却仍把failure=None的部分采集组合成passed。修订后的[normal_window_completion](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py:187) 在实际measurement window结束时核对：start/end均为正signed-int64整数、声明duration有限且在[1,10]、expected_fault=none、stop_reason=declared_duration_elapsed、实际elapsed达到声明duration。operator_stop、watchdog/fatal、启动异常、unknown时间或不足声明时长均不能获得normal_window_complete。

[postrun组合](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py:864) 还要求run无error、cleanup完整、supervision evidence完整、旧normal source checker通过，以及enabled时独立audit通过。异常之后即使曾完成测量窗口，run_error_free仍能阻止整体通过。部分raw采集照存，不改写原source/audit各自结果。任一上述门失败，runner退出非零。

normal_source_check直接调用原check_p1_execution.main，使用原experiment/bag/contract/context/output参数，没有放宽源缺失、typedbag、真实exe SHA、handshake、owned terminal ledger、flush token/RC或cleanup要求。源报告的passed=false/RC2保留，不将失败重解释为预期log overflow。

audit与normal源结果分列，默认off审计passed=None；开启时缺失/损坏witness、expected-header变化、独立身份不符、audit incomplete或报告不能exclusive写入均保持失败。normal_contract_complete、execute_qualified和expected_log_overflow_mechanism_passed都保持false。

两个独立checker都通过尚不代表witness已和普通source逐项join。固定witness checker仍报告source_join_verified=false，postrun仍明确C0_comparison_performed=false与R5_mechanism_gate_implemented=false；后续C0必须做真正对照与join，R5必须独立预声明并执行真实512队列溢出。

## 6. 测试声明与后续证据

最终test_r5_diag_runner源码可见17个test方法，覆盖默认关闭、所有hook前置拒绝、路径所有权、完整loader调用、真实capability条件、命令pins、driver独立header、missing/changed/既存report、host诊断/fixture覆盖、旧严格checker原样调用与formal runner指纹，以及完成窗口的边界、提前停止和独立postrun gate组合。新增测试使用stub/mock/temp目录，不启动ROS/控制器；它们不能证明实际DDS、10秒业务执行或C0对照。

本审查未运行测试，也不把父任务报告的测试通过数量当作自己独立实测。后续交付应保存本版本实际测试日志/方法身份、依赖原runtime_v30的byte级守卫、新目录部署manifest，以及最终采用的clone bin/source/witness/Sink header全输入图。旧工具失败日志与旧目录保留。

最终静态结论无阻断；本文件只核准继续工具验收，不宣布B1/C0/R5业务验收、M0b正式冻结、M4、F6或P1整体完成。