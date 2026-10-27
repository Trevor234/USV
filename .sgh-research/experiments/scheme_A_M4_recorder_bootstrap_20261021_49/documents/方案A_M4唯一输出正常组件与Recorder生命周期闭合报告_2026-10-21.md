# 方案A：M4唯一输出正常组件与Recorder生命周期闭合

日期：2026-10-21。当前批次49；承接第47批正式profile冻结和第48批实际入口实现。基线仍为仓库scheme=B动态NMPC。

**当前结果：新的Regulator已在隔离nominal环境中成为左右推力唯一出口，完成20秒连续正常来源与完整API流审计；M4正常唯一出口组件通过。完整M4、F6和P1尚未验收。** 本批确实调用了210次控制发布API；普通生产release仍关闭，两者是不同范围。

## 1. 相比上一状态，推进了什么

| 工作 | 结果 | 起到的作用 |
| --- | --- | --- |
| 47正式profile、合同、政策及预算冻结 | 沿用并复核4103项实际输入 | 为当前实现提供固定判据，不在运行后修改门槛 |
| 48新Regulator/Worker/Fixture/Driver与原生接口适配 | 实现和受影响组件验证通过；首次实际run启动失败、控制API为0 | 暴露了Recorder完整就绪与Regulator出口创建之间的依赖环 |
| 49拆分Recorder进程身份与完整记录就绪 | 新版本、新编号一次运行通过，自动重试0 | 消除依赖环，同时保持完整就绪前禁止API |
| 49完整Source、实际wire、SQLite及退出审计 | 独立审计通过 | 把“程序运行成功”推进为有原始证据支持的正常唯一出口组件结果 |

48的失败仍保留在`scheme_A_M4_owned_entry_20261021_48`，没有改为通过或覆盖。49的run为`M4_owned_nominal_20261021_49_01`，不是对48同一注册的隐藏重试。

## 2. 架构及具体改动

运行由四个实际角色组成：Fixture发布名义状态、时钟和参考并按收到的本owner Applied历史推进名义模型；Worker求解并发布候选与能力；Regulator独占SolveJob、Decision、Applied和左右推力五个出口；Recorder订阅12个topic写入SQLite。Driver只管理真实进程、身份、准备、一次grant和有限退出，不作为额外ROS参与者，也没有旧Publisher并行输出。

48已经完成两个原生接口差集：实际FastDDS GID为16字节，以32hex绑定，修正47纯context采用24字节格式的差异，不用补零制造匹配；Worker改为认证完整冻结v3和目标profile。实际Writer和Reader GID都必须对应已登记角色。以上解决的是运行时接口和身份语义，控制数值、模型、RTI及参考生成器保持原版本。

48失败原因是准备顺序互等：Driver等待完整Recorder manifest才启动Regulator；Recorder等待包含Regulator未来五个Writer在内的12个topic准备完成；Regulator构造器又要求完整Recorder pin。增加超时不能解除这个环，NMPC尚未开始求解，不能解释为候选连续拒绝。

49具体改变：

1. 新增`author/common/recorder_process_pin_v1.hpp`。Driver在spawn Recorder后记录实际pid/start/exe、binary/source SHA、argv、pgid/sid、run/boot/contract和topics。Regulator以真实`/proc`、pidfd及固定ELF/源码认证它。17字段明确`process_only=true`、`recording_ready=false`，不能授予记录完整性或Reader权限。
2. 修改`author/owned_m4_driver_v1.py`：先认证Recorder实际进程并写process-only pin，再启动Regulator创建五个出口；随后等待和认证实际完整Recorder manifest，才启动输入并进入正常源准备。
3. 修改`author/observer/src/shadow/regulator_owned_execute.cpp`：process-only身份允许创建端点，但此时API为0。实际完整manifest出现后，独立核对与bootstrap一致的进程、源码/ELF、argv、run/boot/contract/topics、storage及Reader GID，才形成`complete_recorder_pin`。完整源、Worker和图门禁通过后写ready；Driver的一次grant绑定该ready的SHA，之后才允许实际API。
4. 固定首次unknown锚点下的真实zero bootstrap和T=200ms节拍。首次真实成功API建立逐侧历史；初始rho不可用，不伪造零历史，不引用旧owner Applied。shutdown也进入同一实际API流和记账。

源码复用审计证明13个准入、准备、激活、预测等Regulator方法体、Worker求解循环以及名义RK4/参考生成器保持逐字一致。49新建6个目标全部构建成功；未install、未codegen、未修改冻结参数。

## 3. 必要验证及一次正常运行

受影响验证：52项政策检查、38项源码关联激活GTest、14个实际可执行入口拒绝用例、14项真实Recorder进程pin及篡改副本用例通过。真实Recorder进程组件故意停在不完整准备阶段，SIGINT后RC2如实保留；它证明process-only认证，不能称完整记录就绪或正常退出。实际正常run的四角色则全部RC0。

注册于运行前固定：localhost/domain120、nominal直行参考0.05m/s、Source至少20s、Driver上限45s、外层90s、自动重试0。实际Driver耗时23.956s；外层含输入hash与进程扫描为59.847s。冻结的deadline=150ms、T=200ms、完整流gap≤240ms、pair span≤5ms、tick jitter≤20ms、rho≤80N/s等不变。

| 实际观测 | 结果及范围 |
| --- | --- |
| 动态正常来源窗 | 20.001765169s，101个动态Job（ID3～103）；odom模拟时间跨度20.000079766s |
| 窗内决策 | 100/100接纳；全流103 Job、103 Candidate、105 Decision，其中102接纳 |
| 完整控制API流 | 105对、210次实际调用，包括bootstrap、业务和shutdown；未裁掉首尾 |
| 首对API | grant后0.908464ms开始，首次rho不可用；实际zero成功 |
| 最大逐侧API间隔 | 左200.139220ms，右200.174616ms，均小于240ms |
| 最大pair span / tick启动迟差 | 0.100671ms / 0.840588ms，分别小于5ms / 20ms |
| 最大实际逐侧变化率 | 左约2.499834、右约2.499986N/s，均小于80N/s |
| 正常窗实际平面速度 | 约0.011220～0.061928m/s；是局部名义动态覆盖 |
| 四角色退出 | 全部仅SIGINT、RC0、owned进程组为空，无外层应急信号 |

全流非接纳原因各一次：初始`unknown_anchor`、温启`no_candidate`、`shutdown`。首次准备时缺少odom之前的双侧实际历史，曾正确记录一次`job_not_submitted`；并未伪造bootstrap锚点。不能把这些事前定义的阶段事实称为100%全流接纳，也不意味着20秒正常窗失败。

Driver正常窗快照曾观测104对API；最终shutdown完成后，独立审计从完整Source/Stored核验105对，最终结果采用后者。两份证据都保留，不覆盖快照。

## 4. 记录完整性、回调覆盖与资格界限

SQLite共4053条，12个topic全部类型解码核验：Clock/Odom/IMU各1076，Path/Profile各44，Job/Candidate各103，Decision/Applied/LeftFloat/RightFloat各105，Capability111。Fixture实际wire记录4052条；多出的一条Stored为Fixture关闭后的末次Capability，已由Worker Source、时间与类型字段单独对应，没有未解释Stored丢失。Source侧generated/emitted/dropped、候选及能力、真实API历史均进行了独立核对；Regulator Source为4323条、dropped=0。

Recorder实际terminal为clean/prepared/stop-complete/manifest-written；其内部`storage_stream_accounting_verified=false`原样保留，因为完整流对应由外部审计完成，不能反写成Recorder内部证明。独立审计的`external_storage_accounting_passed=true`说明外部逐条核验结果，不改变原回执。

Regulator实际接收的回调数量是另一种范围：Clock1061、Odom/IMU各1068、Path/Profile各43、Capability108、Candidate103。Clock采用keep-last=1，其他输入包含best-effort语义；1076次Clock发布中有15次没有成为Regulator回调，其中bootstrap前5、API流期间2、末次API后8。所有Job的源年龄、模拟时间lag/future、实际历史检查仍通过。完整Fixture/wire/Stored捕获不能代替“每次DDS发布都被Actor收到”的证明；本批没有作此声明。详见`postrun/callback_capture_scope_v1.json`。

Witness记录完整，首个真实接纳激活与BusinessReady一致；旧标签`closed_shadow_observation`原样保留。这里只用其观测和阶段一致性，不把Witness内部标志提升为M4控制资格。图唯一性基于受控prepared图及登记进程/GID前提，不能扩大为任意外部参与者下的持续全局唯一性。

Fixture使用实际本owner Applied驱动名义点模型，非真实plant测量。shutdown实际zero API成功也不证明推进器归零、保持或物理停船。F5完整plant/reference同一性、一般1.2m/s/转弯/mixed、6DOF/Gazebo/硬件、硬实时/WCET、算法优越性和GP数据资格都未取得。

## 5. 资产、工作区和失败保留

47冻结索引4103项、373401307字节复核通过；本次1840项注册输入及41项运行审计输入前后hash一致。48封存包、历史组件和失败按显式当前基线复核；49自身源码/ELF/日志/SQLite/验证/报告进入本批清单，MPC交付通过单独回执核验。

本次开始前，HEAD已变为`feb50823a07054879e3c6f8d437c02595ce26976`、分支`codex/scheme-c-rl`。原24文件的151961字节历史diff等字节进入提交，SHA仍为`d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5`；当前主仓受跟踪文件diff=0、staging为空。本来已有的`?? .zcodeignore`及`ardurover-argus`子模块状态标记仍存在，前后status与递归子模块状态完全相同，不能称整个工作区无未提交内容。本批没有提交、重置、清理这些内容或恢复旧dirty状态。

同时有必须显式保留的事前变化：两个`pre_reference_prediction_v1`活动备份头文件已经缺失，从F5相同SHA副本保全在48的恢复目录，原活动路径及dangling安装别名未恢复；`.gitignore`已随新HEAD改变，当前1287字节快照/SHA保留，旧1052字节仅旧hash已知，未声称完整恢复。`real.launch.py`既有15602字节版本与已登记历史515字节差异均保留。因此“所有历史原路径都未变”不成立，保护通过仅在列明例外和当前基线内成立。

48的早期构建/验证/保护失败及首次实际启动失败保留；49清单工具首版缺少只读helper导入的失败也保留，新v2使用有hash的helper后才成功。49终态资产复核首个会话被用户消息中断且没有结果文件，单独留证后以新文件名重做；未重复实际ROS run，也未把中断推断为通过。

## 6. 当前资格与下一步

| 层级 | 当前结论 |
| --- | --- |
| 已有B5/M0b选定工程冻结 | 沿用47冻结及其范围 |
| M4组件 | **隔离nominal正常唯一出口组件合格**；入口、真实Recorder两阶段认证及受影响验证通过 |
| 完整M4阶段 | 未合格：当前版本原9组故障判据尚待逐项确认，F5来源/参考适用范围需明确收口 |
| F6、原P1联合验收 | 未合格：有限已知数值模型的model+plan原子事务和联合复判尚未完成 |
| 研究结论 | 未宣称性能优越、碰撞安全、递归可行性、概率保证或学习数据资格 |

后续保持原顺序：当前版本M4故障与范围差集闭合 → 已知模型事务/F6 → 原P1联合复判。按47的原9组判据选用适当的确定性检查和实际受控触发；不把已有38项单元检查替代整个当前版本故障确认，也不无差别重跑45/46及无受影响代码理由的39～42。无需另加完整no_output业务阶段，不以半RMSE、RTI或权重调参绕过尚未闭合的事务与故障义务。

独立审计：`postrun/actual_normal_audit_v1.json`；最终完整性/资格分层：`postrun/final_QA_v1.json`；后续工作见同目录《下一步实施计划_M4受控故障确认_2026-10-21.md》。最终归档人口、hash及MPC两次读回以`archive_inventory_v1.json`、`delivery_verification.json`为准。
