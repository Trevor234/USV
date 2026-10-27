# DecisionEnqueue 最小修复：独立构建与正常对照复核

日期：2026-10-08。范围为本地已保存 `final_build_result.json`、原失败记录、v3 正常对照封装/政策/生成器、旧 C0 已验证封装与工具清单、`final_evidence.json` 内底层报告，以及随后保存到 `raw_review/` 的11份原字节快照。本子任务没有连接 Ubuntu、启动/回收远程进程或重跑测试，没有修改旧源、旧报告和冻结资产。只新增本文。

结论：当前本地证据支持“新普通/诊断候选完成实际源链接的清槽分支回归，新诊断候选的有限正常 no_output 对照通过”。未发现阻止这个有限结论的新封装或身份错误。新源完整 ROS 图 R5 压力仍未重验，默认 ROS install 保持旧版冻结；本次没有晋级正式 M0b/M4/F6/P1 或物理执行资格。

## 本次审查身份

| 对象 | 独立核实的 SHA256 |
| --- | --- |
| 最终本地聚合证据 `final_evidence.json` | `db1cf848c75454a794e5b8687569d93c3317ff71fbdc74b3db9ee33e513e96a2` |
| 最终本地构建结果 `final_build_result.json` | `ad42af3fde80fe17c3c102a5be79a694baf3fae38b0124695471dd39e65502b5` |
| 保留原 v1 构建失败 | `9889cf4a18aa0f407b7dddb1909dd832187b923bd9876d06e5d9463a46f14077` |
| 正常政策 `normal_policy_v3.json` | `47d9fbc99a0559d5d1225baa3cba6e7f9a37eab9498c06ad3938db6a7a5e754f` |
| 正常封装 `run_normal_v3.py` | `adeab1078f68ba48c8020c4576d5078d05c64c2b7b9600fe2edcea6f2e64f7f3` |
| 当前 v2 本地夹具 | `9909f8892ef84891519842056d05afa4f984311e9976ff4801554e88932494bc` |

聚合证据内的 build 和 normal_run 两个对象，与独立保存的最终构建结果、v3 正常结果逐项相同。政策 SHA 与封装固定值和结果一致；本地诊断源、政策、运行 context 的源 SHA 一致。build/政策/context/recovery 的新诊断 binary SHA 均为 `dc43fa95ab9f4cfefa6836016a10e90a6523fa6dd9b9c6d1f22805dbf7fb3eb6`。这是新实验目录候选 binary，不是默认 install 的发布替换。

跨 base/comparison 输入前后清单、delivery/Witness 证据清单和 normal_run inputs 检查了21份不同路径的 SHA 引用，未发现相互冲突。此项为本地已保存报告的交叉一致性复核；实际封装对远程原件的读取前后 SHA 复核结果保留在这些报告中。随后对主任务保存的11份原字节快照逐份独立计算SHA和大小，均与 `raw_review/snapshot_manifest.json` 的remote SHA/大小一致，并直接解析了两个Witness、五份XML、三份source和owned ledger。

## 定向回归：20个新正例与两个旧关键负例

最终构建结果记录新普通、新诊断各10个正例：RC0、无失败、无禁用/错误、有限监督完成；总计20个正例。修订夹具将 Ticket ID 改为递增 `++r.job_id_`，candidate 使用新 ID，未重置 Admission 历史。原 v1 重复 ID 引起的 `fixture admission` 异常有原 XML摘要和原失败 build SHA 保留，不能抹去或解读为生产代码缺陷。

两个关键旧逻辑负例各运行 `FirstFailureZeroExitCleansAllSlots`，均RC1，并在预定断言失败：slots实际2、candidate实际true、pending实际true。此次负例执行名称带 `_v2`，实际复用了初次已编译的旧适配 binary；该关键用例只有第一次播种，不受 v1 重复 ID 夹具错误影响。它们支持旧尾部直接退出未净空的缺项，不额外支持旧诊断 phase8 缺项的动态负例结论。

发行普通/诊断 binary 的 `flags.make` 哈希保留在结果；本轮构建入口在保存成功结果之前断言发行 flags 未含 `-DP1_ENQUEUE_BRANCH_TEST`。结合源 ifdef 和 CMake 目标审查，可支持该构建路径未启用测试构造。没有新增发行故障参数、物理推力入口或安装替换。

分支原 Witness 的本地聚合 phase 列表显示 phase5/observation3 与 phase8/observation3 各一次：先 slots2/candidate=true/pending=true，然后 slots0/candidate=false/pending=false，stopping/failed均true。两次采样差639ns，且该测试没有使用下一 TickStart。这里是合成状态与 Witness 身份、真实源尾部和真实诊断队列满的分支证据；639ns是一次夹具内两快照间的观测差，不能作为故障响应上界、硬实时性能或完整 ROS 图压力验收。

随后直接读取哈希绑定的 `raw_review/targeted_witness.json`，独立核实 tick/submit/activation 的数组和 attempts/reserved/published 都为0，phase为7且phase5/8各一次；audit_complete=true、first_failure.code=0、overflow/rejected均0。其header确为a/b/c/d/e合成hash与 `enqueue-branch-linked-test` 身份，不是正式运行资产身份。因此可以引用原件后置计数审计来加强本次夹具证据，仍不能证明重复失效时phase去重或完整ROS图压力首失效。

五份原XML独立解析与构建报告一致：两个新正例各10用例/失败0；两个旧关键负例各1用例/失败1，三个真实失败信息分别为slots2、candidate=true、pending=true；原v1仅 `RepeatedFailureAlwaysClearsNewlySeededSlots` 因 `fixture admission` 异常失败。原件SHA与最终构建报告XML SHA均相同。

`independent_source_review.md` 列出的 pending已空、成功不误停、并发锁等待及 phase去重范围仍适用。实际源链接正例通过不会自动补成真实 prep pop/submit 竞态或 callback 重填并发测试。

## v3 封装、工具继承与四角色回收

v3 的 `E/A/R/G/P` 声明完整切换到本轮新实验目录、其 runtime、R5历史guard和新政策。`prepare_normal_v3.py` 使用已有 `C0_predeclared_policy_v2.json`，替换新诊断源/binary及 regulator recovery pin，并断言回收 map 恰含 regulator/worker/fixture/recorder。worker SHA与原政策一致。

已独立比较 v3 与旧 `remote_run_v2.template.py`：`recover_inner` 和 `call` 全段逐字相同；finally 的回收逻辑逐字相同，仅工具清单验证入口与输出文件改名。这保留了120秒runner上界、超时SIGINT后20秒内层finally allowance、按原owned ledger恢复内层组、监督回收outer runner、父进程退出后再检查及finally最终重查。异常发生后，不只回收outer runner；所有四个已授权内层roles均由同一recover实现处理。缺角色、身份变化、ledger不完整或剩余成员导致unknown/失败，不按进程名发现后批量杀进程。

recover验证本run完整行ledger、runner父PID、boot、各role独立PGID/SID、start_ticks和exe/SHA，再检查组/已知成员后才能发信号。正常 context 中 worker 的规范路径是 build 下可执行文件，与 recovery pin相同；政策启动路径是 install 链接且 SHA相同。Python规范路径为 `/usr/bin/python3.12`，与fixture/recorder pins相同。regulator recovery pin精确指向本轮新binary。

新55份runtime清单与旧C0 v2工具清单逐项SHA完全相同，差异0；旧工具结果记录88测试及两个受控回收实测通过，其中“缺recorder的三组已知子集”只判 group cleanup true、full cleanup false。新wrapper前置、checkers之后和finally均在本轮R路径核对55工具，还核对原部署文件、v2测试文件和发行binary。它没有继续错误引用旧A来读取新build结果。

此次实际正常run按正常停止流程收尾：regulator完成逻辑stop，owned ledger保存worker/fixture/recorder的三个正常SIGINT，四角色最终均RC0/剩余成员0。后置recover报告全四roles absent、其recovery signals为空、ledger稳定。不能把“后置recover未发信号”写成“本run所有进程自然退出/没有发任何信号”。可以说“四角色owned回收和退出证据完整”，不能说本次在异常ROS场景演练了全部错误路径。错误恢复能力的依据是原已验证实现与既有受控进程实测、本轮相同回收路径及新pins绑定。

原ledger独立解析有19行：四个spawn、四个cleanup_result，四role身份均为各自PID=PGID=SID、创建parent同为runner310317、可执行和SHA匹配政策；三个正常SIGINT分别给worker/fixture/recorder。后置恢复无需再发信号。这与wrapper结果及source summary一致。

保留的正常封装v1结果为 `KeyError('recovery_expected_roles')`、steps为空，错误出现在进入首个spawn之前。v2源仍以旧A/P声明读取政策，在首个spawn前的政策SHA断言不匹配；不能把该预启动错误当成一次正常ROS试验失败。当前有完整actual run结果和context的运行身份是 `_03`，它使用修正的v3封装。

## 新正常对照底层事实

| 验证对象 | 本地已保存结果 |
| --- | --- |
| 身份与模式 | `p1_enqueue_fix_normal_20261008_03`；新诊断候选；no_output；native worker；所有故障hooks0；Witness启用 |
| 声明/观测窗口 | 声明10秒，观测 `10002600190ns`，即10.002600190秒；declared_duration_elapsed |
| regulator source | 1978行，包含1行summary；generated=emitted=1977、dropped0、normal_source_complete=true |
| native消息 | Job51、Candidate51、Decision52；Worker收到/完成/发布51；candidate注册51 |
| activation连接 | source/Witness各50次尝试且50次accepted；52ticks和51submits也全双向匹配 |
| 原始fixture输入/bag | clock/odom/imu各653，path/profile各14；fixture发布数与真实bag逐项相同 |
| application输送 | Job/Candidate/Decision各missing0、extra0，无未解释pending/拒绝；DDS内部损失数量仍unknown |
| checker | runner/base/delivery/comparison全部RC0；base、postrun、delivery、comparison均passed且issues为空 |
| owned生命周期 | regulator/worker/fixture/recorder各RC0、剩余成员0；inner/outer最终回收完整，host尾部controller/Gazebo0、unreadable0 |
| 物理输出 | graph_no_physical_publishers=true；no_output；execute资格false |
| 原资产 | 同一boot；2626文件R5guard前后无漂移 |

原source独立解析再次核实 regulator1978行/Job51/Decision52/注册51、worker155行/收到与生成/发布各51、fixture1行/五topic计数653/653/653/14/14。原正常Witness独立核实header绑定新源/new binary/worker/run `_03`，tick52/submit51/activation50、accepted50、phase4、audit_complete=true且无审计失败/溢出/拒绝；其正常phase8来源为TickStart1、failed=false、槽净空，与正常stop一致。

52个Decision覆盖完整owned生命周期，不能把它们说成恰好10秒窗口内52个控制周期。51个Candidate、51个注册与50个最终activation也不是相互矛盾的计数，它们对应不同边；本轮独立报告按全生命周期和双向身份连接检查。MCAP没有下载到本地，本子任务没有在Windows重复bag扫描；真实MCAP读取、typed missing/extra和严格payload连接仍引用本轮remote checker的哈希绑定报告，不能写成Windows已独立重扫MCAP。

## Collector与独立验证的完整性字段

runner summary明确保留 `source_completeness_proven=false`，regulator/worker/fixture 的 `sources.*.completeness_proven` 也都false。Collector只保存了存在、可解析、类型计数和来源summary，未凭读取日志自行宣布完整性。regulator自身summary的normal_source_complete=true和drop0，也不能单独替代独立跨source/bag/lifecycle验证。

独立base checker在实际源、真实bag、原始fixture计数、worker及owned生命周期核对之后，得到 `source_bag_contract_complete=true`、`lifecycle_verified=true`、`raw_input_recording_complete=true`、`diagnostic_complete=true`。独立comparison核对source-Witness双向连接，combine再汇总这些证据得到本轮有限正常C0_complete=true。这些不同层次的字段没有矛盾，不应把collector字段改成true或写成“collector已证明完整”。

同理，基础Witness checker的source_join_verified=false表达其“仅terminal integrity”的范围，另一个独立comparison才给source_join_verified=true。comparison本身的normal_window_verified/owned_process_lifecycle_verified等false表达不在该checker职责内；窗口和生命周期由base/summary/combine补足。DDS内部损失原因仍unknown、bag存储时间未映射为monotonic，不做跨钟相减或零丢包机制推断。

## 最终可采用的解释

可以采用：“普通和诊断候选已修复首次DecisionEnqueue失败后同拍退出前的共享槽清理缺项，20个实际源链接正例通过，两个保留旧逻辑的关键负例在预定净空断言失败。新诊断候选通过一次有限正常no_output对照，独立source/bag/Witness/输送/窗口/owned生命周期验证完整，原资产无漂移。”

应同时保留：“这次代码分支测试与正常ROS对照分别提供不同证据。新版本完整ROS图首次DecisionEnqueue失效压力尚未重验；默认install仍是冻结旧版，尚未把修复发布到默认控制入口。正式M0b/M4/F6/P1和物理执行资格保持未完成。”
