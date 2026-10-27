# P1 M0b：Decision 入队失败即时失效——修复与验收

日期：2026-10-08。**本轮最小代码分支修复与新诊断版本有限正常对照已完成；默认 ROS 安装尚未切换，正式 M0b/M4/F6/P1 未晋级。**

## 1. 错误前提与本轮边界

此前R5压力实验确实观察到DecisionEnqueue失败，但首次停态发生在TickStart，且已清理共享槽。因此它不能证明“首次DecisionEnqueue失败后直接退出”的另一顺序。代码审查确认两个原版本均存在漏清理：Sink.add(Decision)返回false仅设置normal/stopping，若final_n为零，shutdown紧接着break，不再进入下一TickStart。

本轮修复的是共享状态失效契约；不撤销本拍已完成的物理publish或此前已提交的DDS尾部。准备线程已pop到栈上的工作仍受原最终提交门限制，不能把清共享pending称为取消所有工作。默认工作空间源码/install已列入2626项旧guard，采用新目录保存修复和发行构建，避免覆盖已验收历史资产。

## 2. 最小修改

普通和诊断版本都在Sink返回false、其队列锁已释放后，取得业务`mutex_`，锁内设置normal=false/stopping=true/首次stop_start并**每次无条件调用现有invalidate_locked()**，清 admission ready/committed、candidate和pending。锁序仍是业务mutex→prep_mutex，与既有最终准备授权门相同；Sink.add与DDS/物理publish仍在业务锁外。

真实Tick尾部提取为finish_tick，发行tick_loop和源链接测试调用同一个方法，保持入队→后继准备→shutdown顺序。诊断在实际清理前记录phase5/DecisionEnqueue3，清理后记录首次phase8/DecisionEnqueue3；去重flag只控制审计记录，不能跳过实际清理。正常与直接退出的audit_tick位置保留。

测试构造/friend仅在测试翻译单元定义`P1_ENQUEUE_BRANCH_TEST`后可用；发行CMake/flags.make没有该定义，未增加正式ROS参数、故障入口或合同放宽。九份公共头、worker、合同、运行工具55文件与旧版本保持对应字节。普通源和诊断源的修改差异见本工作目录diffs；失败体旧源负例由相同尾部提取适配，保留旧业务逻辑。

## 3. 真实分支与对照验证

| 验证 | 实际结果 | 可授予范围 |
|---|---|---|
| 新普通源链接测试 | 10/10，RC0 | 真实finish_tick失败/成功/退出分支 |
| 新诊断源链接测试 | 10/10，RC0 | 同分支，另读取真实有界Sink故障的Witness |
| 原普通/诊断源关键负例 | 各1项RC1，槽2/candidate=true/pending=true残留 | 旧代码缺口被测试检出；预期失败保留原件 |
| 新诊断版正常ROS对照 | runner/base/delivery/comparison各RC0 | 有限正常no_output，全owned源/bag/worker/输入/输送/审计门 |
| 默认安装及物理输出 | 默认旧版保持；no_output publisher物理端点观测0 | 无execute资格，无plant应用证明 |

正例覆盖ready槽、committed槽、两槽、首次零动作退出、非零动作按原shutdown_grace继续、已有失效、重复失效不被审计flag跳过、成功入队不误停、pending已空，以及持prep锁时业务门在清理完成前无法取得同一业务锁。

成功用例worker_valid=false，只验证入队成功不误停，不单独证明后继Preparation入队；pending已空用例也没有实际执行prep pop/最终submit竞态。这些范围不扩大。后继业务链由正常ROS对照另行覆盖；最终提交门和审计去重另有独立源码审查。

诊断专用构造采用容量1、真实暂停消费者并填队列，在`failed=false`且槽已满的前置状态下，真实Decision.add首次拒绝。原Witness字节后置核对：phase5与phase8各一次，均obs3；清理前槽2/候选true/pendingtrue，清理后槽0/false/false；tick/submit/activation审计流均0。这些槽和Witness身份是测试夹具，未运行业务tick/prep线程。普通容量0用例是低层真实Sink拒绝验证，正式资源loader禁止0；正式日志容量512保持原值。不能把这两种测试容量说成正式512压力实测。

phase5→phase8记录差 `639`ns，仅为本测试的采样差，不是锁等待、完整故障响应或硬实时上界。没有完整ROS图首次DecisionEnqueue顺序压力验收。

## 4. 新版本唯一实际正常ROS对照

Run ID：`p1_enqueue_fix_normal_20261008_03`。声明10s，实际单调时钟窗口 **10.002600190s**。静态零状态、RTF约1、真实native acados worker；Witness开启，五个故障hook均0。

| 对象 | 整个owned生命周期数量/结果 |
|---|---|
| Job / Candidate / Decision | 51 / 51 / 52；source与实际MCAP完整payload逐项对账 |
| Witness Tick / Submit / Activation | 52 / 51 / 50；50次接受，逐项与source匹配 |
| regulator source | 1978行含1条summary；generated/emitted1977/1977，dropped0，normal_source_complete=true |
| worker source | 155行；完成/生成/发布51/51/51，fatal=false、terminal_numerical_failure=false |
| fixture→真实bag | clock/odom/imu各653，path/profile各14，全量计数相等 |
| 应用输送缺失/额外 | Job、Candidate、Decision均0/0 |
| owned角色 | regulator、worker、fixture、recorder均RC0、remaining_members=[]；外层清理完整 |
| host末态 | controller/Gazebo=0，不可读cmdline=0，boot未变 |

数量覆盖整个owned生命周期，不是仅裁剪10秒窗；fixture完整发布653不等于regulator callback数量。独立严格base证明声明的source/bag/lifecycle/raw input范围，DDS内部packet丢包原因仍unknown，不推导所有callback无丢失。实际MCAP读取在Ubuntu执行，Windows保存了源/Witness/XML/owned原字节，没有下载或在Windows重扫MCAP。

collector摘要保留source_completeness_proven=false及各sources.completeness_proven=false；这是收集阶段未授予资格。后置独立base的source_bag_contract_complete、lifecycle_verified、raw_input_recording_complete、diagnostic_complete等为true，结合delivery与comparison独立门通过。不要把collector改成true，或把comparison仅source-Witness的通过扩写为bag/lifecycle通过。

有限样本tick jitter max 0.061453ms、activation jitter max 0.107881ms、native solve wall max 0.483643ms，只用于本次静态正常样本定位。无物理publish样本，不能计算新监管器双路物理预算或真实变化率，更不能宣称性能改进。

## 5. 原失败与修正记录

首轮测试重复播种重用Job ID41/42，真实Admission保留seen_历史，第二次注册被duplicate拒绝。该夹具错误在到达重复finish_tick前已发生；首轮普通测试RC1、原XML/console/build_result保留。tests_v2改为递增新ID，不重置Admission历史；新20项正例通过。

正常封装v1从较早C0政策取值，缺recovery_expected_roles，在spawn前KeyError；v2生成替换误指旧A与旧政策，SHA门在spawn前AssertionError。两次都未spawn runner或四个内部ROS角色，不是两个完成的正常窗口。v3直接验证新A/R/P声明，完整4角色回收身份表中的regulator路径/SHA绑定新bin，才执行唯一实际run _03。失败driver、政策、v1结果和v2回溯诊断均保留。v2回溯诊断明示为后置只读确认，不伪造当时测量时间戳。

本轮正常退出后的4组不存在已实测；异常内层回收能力来自复用已验证实现及此前88个单元和2个受控回收测试，不改称本轮异常ROS演练。

## 6. 版本、证据与冻结身份

Ubuntu修复根目录：`/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_enqueue_fix_20261008_v1`。普通发行入口`build/p1_regulator`；独立诊断入口`build/p1_regulator_r5_diag`。默认workspace source/install仍旧版，下一验证必须显式绑定新路径，不能继续用旧ros2 run入口再声称新修复已部署。

| 对象 | SHA256 |
|---|---|
| 新普通源 | `7abfaf03722499bbe9d28da19d050404667682ff3918813d2133b98dadfd8477` |
| 新诊断源 | `a38d563a52570f11da9e68b5743c6c1989b26e77508620358ad3e402bd0a8a3b` |
| 新普通发行bin | `50e2af0904d5635e9a698eb98b17364f8f6b247c3668fd7d9e94c82fd4c98c1a` |
| 新诊断发行bin | `dc43fa95ab9f4cfefa6836016a10e90a6523fa6dd9b9c6d1f22805dbf7fb3eb6` |
| 实际normal事前政策 | `47d9fbc99a0559d5d1225baa3cba6e7f9a37eab9498c06ad3938db6a7a5e754f` |
| 本地事实包 | `db1cf848c75454a794e5b8687569d93c3317ff71fbdc74b3db9ee33e513e96a2` |
| Ubuntu事实原件 | `9ae8c145a905ad77005292ac18e695c0ad7cd9fd5f018ccdceae9235649b2ead` |
| 旧R5关闭guard（2626项） | `0e53dcf332c0d4ceae8f377533720e21329675e8e59639811bccbe97a11908bc` |
| 新关闭guard（3067项，新增441项） | `f3e10a0f5ee97381094c39978794f1ceac2f5d12732d1028899dc7c8b4a63146` |

新guard：`/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/enqueue_fix_closed_assets_20261008.json`，末态drift=[]。新旧源/bin、原测试失败、负例失败、两次封装拒绝、工具/台账/严格报告/实际MCAP和Witness都保留；外部Python/ROS入口与resolved worker另核SHA不变。

本地：[事实包](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/final_evidence.json)；[构建与20正例/2负例](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/final_build_result.json)；[正常对照](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/normal_run_result_v3.json)；[原字节快照索引](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/raw_review/snapshot_manifest.json)；[独立源审查](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/independent_source_review.md)；[独立运行审查](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/independent_runtime_review.md)；[preflight](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/preflight_reflection.md)；[postrun复盘](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/slurm_logs/04_delay_modeling/p1_enqueue_invalidation_20261008.retro.md)。

## 7. 完成标记与下一步

- [x] 普通/诊断首次DecisionEnqueue失败即时失效修复。
- [x] 新20正例和旧两源关键负例；诊断实际首停obs3净空原件复核。
- [x] 新诊断版本唯一正常无输出对照、严格对账和owned关闭。
- [x] 独立审查、失败原件保留、新guard与方案同步。
- [ ] 最终统一版本的压力/恢复/关闭/部分发布政策证据适用性复核。
- [ ] B4来源补齐、B5正式冻结、默认安装版本切换。
- [ ] M4物理接管、新基线/F6、P1整体和execute资格。

下一最小动作是B4来源与版本矩阵：逐字段区分模型推导、测量样本、工程预算与unknown，列出对应源/bin/合同SHA及验收范围；把新版本R5压力资格单列待补，不能从旧R5继承。B5前以最终统一版本核对压力、恢复、关闭、部分发布与物理发布预算政策，证据满足后再创建正式冻结并决定默认安装切换。动态状态域、真实非零变化率、双路部分发布和plant响应仍缺相应数据。本轮分支目标已满足，停止重复本次静态测试，M0b正式冻结/M4/F6/P1/execute均保持false。
