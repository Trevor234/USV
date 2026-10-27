# D0a 来源可重建契约与 D0c 工况/时钟决定

日期：2026-10-09。本文是本轮隔离观察版的**初始字段契约建议及只读审计**，不是新观察版已运行或资格完成证明。只读取当前 enqueue 普通/诊断源码、既存 B4 分析及历史原始数据、F4/F5 小型摘要、三个旧 bag metadata；不访问远程、不启动 ROS、不执行新 run，不修改 root 源码、普通安装、旧数据或原登记。

机器可读对应：[source_reconstruction_contract.json](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_D0_observability_20261009/source_reconstruction_contract.json)。其中保存受审文件 SHA256/bytes、前后不变检查、字段规则、历史缺失矩阵、已有场景摘要及剩余依赖。

## 1. 先固定真实模式入口

[regulator_r5_diag.cpp:48](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_enqueue_invalidation_20261008/src/diagnostic/regulator_r5_diag.cpp:48) 的专用 B1/R5 诊断入口明确要求三项同时满足：`mode=no_output`、`schema=p1-execution-contract-v2`、`diagnostic_contract_revision=5`，否则抛出 `B1 diagnostic entry requires no_output diag5`。

**diag5 是合同修订号5，不是运行5秒。** 本入口仍会检查共享full-contract loader；共享Diagnostic profile允许no_output或shadow，但该专用构造函数更严格。因此D0保留专用模式门就只能做no_output观察验证，不能直接启动F5 shadow。普通入口支持Diagnostic shadow，也不表示专用观察代码已经获得该模式支持或版本资格。

本轮决定：保持专用门。no_output可验证字段生成、失败/无候选编码、wrapped误差与原业务门可比性；不能当作动态plant工况补证。D1若仍需要旧F5唯一物理publisher、新观察者shadow，必须先形成受控的观察入口/模式支持设计、对应source/binary/contract绑定及受影响验证。不能靠传`mode=shadow`绕过专用门，也不能称当前观察版已可直接F5 shadow。

## 2. 旧证据哪些能重建，哪些不能

复用已保存全量B4重算，未再次无界扫描大型jsonl。历史对象仍是 `p1_capability_regression_shadow_20261006_01`：183 decision、163 job、160完整名义状态对、23无job、2接纳。完整对包含156 anchor_mismatch、2 rtf_unaligned及2接纳；不是只分析两条幸存样本。

| 对象 | 现有可用 | 不可用/限制 |
|---|---:|---|
| decision身份、status、最终reason | 183 | 全生命周期，精确测量窗起止ledger仍缺 |
| job冻结来源/初始状态 | 163 | metadata能匹配raw；5个mixed冻结job均skew=0 |
| decision target/activation完整数值对 | 160 | 23初始化零不可当状态差样本 |
| 全六维wrapped差值重算 | 160 | 是名义传播对齐差，不是plant残差 |
| raw独立predict_success字段 | 0 | 160成功写入由exact旧caller+数据推断，不能泛化nonzero启发式 |
| raw显式tick-start validation snapshot | 0 | 全183条都没有独立保存此快照字段 |
| 完整对的快照=final来源门认证 | 2 | 158拒绝项缺该认证，不是断言158条都变化 |
| old raw完整误差computed/finite标志 | 0 | 原state_check可早退；重算160组不等于补造历史标志 |
| 旧传播core exact正文 | 0 | old hash a626758…，当前6180198…，不能替代回放证明 |
| 精确validation_window_start/end正文 | 0 | source183、driver103及另一run171不能互换 |

当前普通源码的tick-start `s`在:294复制，:302用于predict；final来源在:318–320从当前成员填写。当前诊断源码对应:353/:362/:384–386；input-change门:365只在reason仍为空时运行。此归属缺口仍存在，需要新观察字段，不能只写分析器从最终成员补回。

旧全raw只有decision31见IMU receive时刻落在tick_start/final_commit区间，但receive取于回调获取mutex之前，无锁内commit时刻。这是来源变化候选，不足以证明前后相对次序。新D0应直接保存真实`Snapshot s`，避免继续依赖该类时间猜测。

历史2次接纳的binary、旧caller、propagation core身份与当前观察版不同。恢复exact旧源码及context绑定不是恢复旧binary，也不是新版本可自动继承旧R5压力资格。

## 3. 初始观察字段契约

推荐使用source侧诊断旁路记录，与原decision用完整身份一一对应，保持ROS IDL、正式合同字段和固定Witness布局不变。最终名字可由root实现选择，但应明确schema/revision与映射，不能只保留含糊的activation标签。

| 组 | 最小信息 | 关键语义 |
|---|---|---|
| 身份 | run/boot/contract/source/binary/worker、sequence/tick/job_id | 同一decision严格join；新观察版有自己的source/bin身份 |
| validation snapshot | 原始六维state，version/epoch，odom/IMU seq/stamp/receipt/mixed，clock sim/receipt/rtf_valid/rtf/paused，anchor与bounded history引用 | 复制实际用于predict的` s `；早期拒绝和无job也可记录，但不可重采final成员冒充 |
| 时刻语义 | capture_request_ns、copy_capture_ns、capture_semantics | 旧tick_start的now取于mutex之前；保持旧业务now不变，诊断另记锁内复制时刻及“copy-end”等准确语义 |
| predict | attempted/success、from_sim/target_sim、输入/输出state、有限标志、输入锚点与found两通道 | 直接观察原bool结果；nojob不attempt；不得由nonzero数组推成功 |
| 完整误差 | available、computed[6]/finite[6]、完整wrapped误差、定义 | 只在真实预测成功后独立算六维，航向atan2(sin(delta),cos(delta))；不改原state_check早退、reason和接纳规则 |
| 原门结果 | 原state_check是否调用/返回reason、原error向量、input-change gate是否执行/通过 | 原reason可能遮蔽后续状态reason，二者需分别记录；额外序号比较是观察，不能变成新控制门 |
| final commit | 原activation_*、commit时间、当前source/clock、accepted/final reason/control_source/命令 | 明确它们是final-current来源，与validation快照区分 |
| clock/范围 | 全receive clock/epoch、job frozen clock及目标，source生成时刻/延迟界是否存在，明确测量窗起止 | 自洽1:1、后到达proxy与运行时真值分开 |
| unavailable/失败 | available=false、原因、逐维finite/computed、sink失败/drop/summary | 缺失值和真实零有不同含义；不能以零补未计算数组 |

若需独立重放propagation，还应保存或可严格索引实际held history（上限256）、initial publisher commands和found[2]、actual_from_sim/target_sim与propagation core身份。hash/digest只能认证已有正文，不能独自恢复未保存的history。观察payload只用固定state6/error6/command2及受限history，不添加无界递归metadata。

no_output当前允许没有两侧historical input仍传播，属于synthetic fixture政策；不能将它作为shadow输入history齐全证明。新增记录有CPU、payload和Sink排队/失败影响，“只观察”不等于零负载或资格自动不受影响，针对验证应保存受影响范围。

## 4. 已有工况查阅与研究域决定

有限查阅范围是已保存F4/F5摘要/预注册fixture和三个旧bag metadata，未读取不存在的远端CSV或MCAP，没有扩大扫描范围凑场景。

| 来源 | 已有事实 | 能否补D0动态来源 |
|---|---|---|
| v11完整shadow | 1817实测体速1.239153–1.259542m/s，全>原1.2；参考u=.8/v=r=0，曲率0 | 能描述该域外直线来源，不支持原≤1.2冻结 |
| F4 baseline摘要 | controller_ref_state_u min1.166233/max1.256615/mean1.248533m/s；参考首u .707107–.8、v0 | 有低于1.2的u标量线索；没有本地可join六维体速/IMU/history快照正文，不能直接校准 |
| F4 plant/nominal mass pilots | 同straight.yaml、profile u=.8、fallback .6；质量配置变化 | 配置隔离和任务线索，不是低速/曲率来源认证 |
| F5 pilot | straight.yaml，193 profile_time/stamp_match、N20/dt.2，60.06s valid sim span | 未给独立低速、曲率或mixed来源段，不能由cruise参数当实际速度 |
| 旧vrx_twin_circle_007_fixed / vrx_scheme_b_circle_001 | 本地metadata含odom/IMU/path相关topic计数 | 场景名及topic存在是线索；本地目录仅metadata，无MCAP/CSV正文及D0身份，不是已验证转弯域 |
| 旧scheme_b_straight_001 | 仅metadata，另有MAVROS/model/usv_2m topic | 平台/来源不同，不能直接并入F5/P1来源 |
| 现有static no_output | synthetic零状态的普通管线正常及少量mixed标签 | 可验证机制，不能替代动态低速/曲率/非零skew域 |

F4的min u低于1.2意味着**不能断言所有历史段都在域外**；但u不是sqrt(u²+v²)，摘要没有逐段来源时间、足够长度和D0快照归属，所以这里保留“潜在域内早期段线索”，不升级为可用校准段。旧circle目录名字也不能证明实际曲率或当前源码/合同兼容。

**决定：原≤1.2m/s研究域保持pending，不自动扩1.3，不修改参考、模型或控制参数制造覆盖。** 5个mixed冻结job的skew全0，不能覆盖非零mixed时间窗。若后续需要域内真实来源，应先确认可重现参考和实际速度条件及来源正文，不应先launch再事后选幸存段。

## 5. 20ms时钟政策决定

沿用1:1映射 `target_sim=frozen_clock_sim+(target_monotonic-frozen_clock_receive)`、assumed_rtf=1.0及20ms目标接纳门；不改为乘测得平均RTF，不因已有异常扩大slack。400–600ms平均RTF0.95–1.05不提供逐时刻速率、发送/传输/回调延迟或20ms真值界。

[clock_independent_review.md](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_B4_sources_20261009/clock_independent_review.md) 已复核163任务：2个point proxy>20ms、4个received bracket不能整体在20ms内。job16实际旧v11接纳，同时有约+65.233ms后接收线性proxy和333.200ms接收gap；不能说全部空洞都被拒绝，也不能把65.233ms称其真实plant时间偏差。未来receipt插值用了事后端点，是离线proxy。

**决定：20ms保持待论证工程接纳门，source生成/仿真主时钟与延迟界未给出时，不称真实时间硬界。** receipt age、source sim lag/future、平均RTF、pause、target mismatch应分别说明；同一1:1公式的自洽差不能验证独立真值。需要真实界时补真实源生成/主时钟/延迟证据；若仅做proxy研究，明确其假设与限制，B4不能被改名“已证明”。

## 6. 下一依赖与状态

本轮可完成D0a缺失/可重建合同及D0c具体域/时钟决定；历史实际validation快照无法补造，因此D0b观察有明确必要。D0b针对字段/控制门等价性验证完成后，仍需处理专用no_output入口与D1 shadow需求的模式支持差异，以及实际域内可用参考/状态来源。

当前 `D1_launch_ready=false`、`B4_complete=false`、`M0b_complete=false`、`execute_qualified=false`。本审查不将一次源采集或无界重复全域campaign自动列为当前已可执行动作；先补具体来源、入口和工况缺口，再决定有限运行是否必要。ordinary/source/history/metadata所有受审输入前后SHA均不变；3067资产守卫和新binary压力资格由root对应证据单列，本只读审查不代替。
