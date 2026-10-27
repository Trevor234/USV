#!/usr/bin/env python3
"""Create the batch30 reviewable decision artifacts from the checked audit outputs."""
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
W = D.parent
REPO = Path('/home/trevor/USV')
E = W/'p1_execution_architecture_20261005_01'
N = E/'authored_D1_deferred_observation_20261019_v29'
H = REPO/'.sgh-research/handoffs/scheme_A_20261010_01'
rows = json.loads((D/'analysis/frozen_run_comparison_v1.json').read_text())['cases']
interface = json.loads((D/'analysis/dynamic_model_interface_v1.json').read_text())


def text(rel, s):
    with (D/rel).open('x') as f:
        f.write(s.rstrip()+'\n')


def put(rel, d):
    text(rel, json.dumps(d, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))


matrix = [
    ('S0', '资产、工作区及历史失败保持', '已验证本地字节',
     '本批前后全量本地SHA和目录核验；原24处业务diff、单独real.launch差异、旧失败保持；NAS历史镜像当前未核验。',
     'preflight/workspace_initial_local_v2.json', '不将旧端点或整阶段资格转移到本批。'),
    ('S1/S2-S5', 'owned端点、有效全配置及prepare/close', '当前诊断版本已观察',
     '第29批五角色实际认证、参数冻结、Source/Storage闭合及退出0；此批仅读证据。',
     'D29/postrun/final_QA_v1.json', '扩展模型/正式出口前重新界定受影响身份与配置项。'),
    ('D1-source', '明确recipe、完整来源窗、动态传播成功', '受控名义组件已观察',
     '0.05m/s单一名义localhost源；101/101连续接纳；1192状态独立复算。不是Gazebo工况或论文漂移D1。',
     'D29/runs/s005_01/check_result.json', '按需要的声明域补最少具体来源缺口，不能继承到转弯/mixed/plant。'),
    ('D1-branch', '新激活历史选择与至多一次重验', '组件前提；本次分支未命中',
     '第29批actual retry=0、older point=0；Native有限测试存在；第28批真实双次窗口仍有10次拒绝。',
     'D29/postrun/deferred_result_audit_v1.json', '只有受影响分支要求才补有界用例；不把0命中当覆盖。'),
    ('PERF20', '第20批加入的全窗RMSE减半和末5s均速', '原诊断门失败并保留',
     '第29批RMSE0.009195365994>0.007392495755；末5s均速门通过。不是原P1阶段条款中的安全门。',
     'D29/postrun/performance_gate_lineage_v1.json', '停止首控/RTI/权重调试；新研究协议另事前冻结，不重判旧NoGo。'),
    ('B4-params', '参数数值、来源、域、政策的适用登记', '旧登记存在；当前增量待闭合',
     '旧diag5登记74项；当前diag10有81项和8组pending；新参考/首控/历史/重验政策须绑定当前消费者。',
     'D29-author/pair_wakeup_contract_v1.json', '生成81项完整映射和新增政策登记，解释工程选择及域外行为。'),
    ('B4-time', '源年龄、RTF、传播与截止语义', '有限运行已观察；保证范围待选定',
     '当前原150ms截止/T200ms不变；CLOCK_MONOTONIC同boot；名义传播及回调租约不证明plant时钟硬界或WCET。',
     'handoff/4.3 and original B4 register', '固定有限工程假设、拒绝/时钟重置政策；不以20ms统计替代硬界。'),
    ('B4-recovery', '阻塞、失效、部分发布、退出及恢复', '旧证据按版本保留；当前统一版未闭合',
     '本次正常退出0不是压力/恢复证据；Worker当前数值失败终止且同run不复活；双路发布不可撤回。',
     'D29-author/worker/solver_worker.cpp', '对最终选定代码只做受影响压力/关闭/故障确认，明确重启须新run。'),
    ('B5/M0b', '不可变正式执行合同及源码/bin/模型/工具冻结', '待实现与验证',
     '当前temporary_shadow_diagnostic/execute=false；格式合法的freeze hash或空pending不构成证据。',
     'D29-author/observer/src/shadow/p1_full_contract.hpp', '先完成B4及当前版本必要确认，再外层证据绑定；本批不翻资格。'),
    ('M4', '监管器成为唯一实际推力出口', '尚未实现当前接管链',
     '当前Observer为shadow，独立controlled Publisher转发已接受Decision并实际DDS发布；不等于新regulator直接接管。',
     'D29 actual role manifests and Source', 'M0b后单列有限接管入口，验证固定tick、每侧锚点、部分失败及反馈。'),
    ('F6-model-interface', '真实有限模型参数进入优化图', '接口存在；切换未实施',
     '现有全局30维包含19水动力；6维阶段参数只作参考。当前Worker每run只构造一个固定后端。',
     'analysis/dynamic_model_interface_v1.json', '有限已知水动力值可用同生成图的两独占capsule；残差/障碍需改图。'),
    ('F6-transaction', '模型准备/候选/固定tick激活/暖启动隔离', '待实现',
     'Job有model_generation且Candidate完整回显，但没有从模型注册表选择不同数值的当前路径；元数据不同不代表方程不同。',
     'D29-author/worker/protocol.hpp and owned_cold_backend.hpp', '冻结双模型注册表、原子切换、晚到/混版/废弃及不可变保存计划。'),
    ('P1', '原P1整体验收', '部分完成',
     '迟到/混版零执行、阻塞仍调度、命令幅值/率限、双路时差、连续失败斜坡须在真实新出口和模型事务下联合成立。',
     'primary plan/7 P1 and handoff/4.3', 'B4→统一版确认→B5/M0b→M4→有限模型事务/F6→复判P1。'),
    ('P2', '固定有效包络、几何、独立验证、备份证书接续', '待实现与验证',
     '当前ramp/hold是工程降级；没有采样间碰撞、执行器状态集合或剩余时域证书。',
     'primary plan/7 P2', 'P1后建立known finite plant set和有限备份；不把性能模型变化当物理包络变化。'),
    ('P3', '合格执行标签、GP性能/误差年龄机制', '待实现与验证',
     'Applied仅最终发布命令；无plant ACK/实测推力资格；未训练合格GP、未校准学习界。',
     'handoff/5.2', '先最终执行区间和标签准入，固定宽界下再做性能模型。'),
    ('P4/P5', 'PPO建议器、公平强对照和贡献结论', '待实现与验证',
     '仓库scheme=C/当前Git分支不代表研究方案A已执行PPO对照；当前工程结果不能作为论文贡献。',
     'primary plan/7 P4 P5', '同信息/资源/时间/域的B1/B2及消融；没有新结论前保持research=false。'),
]

put('analysis/requirements_code_evidence_matrix_v1.json', dict(
    schema='P1-requirement-code-evidence-matrix/v1', passed=True,
    passed_semantics='reviewable mapping completed; not stage acceptance',
    rows=[dict(id=a, requirement=b, current_status=c, observed_or_missing=d, evidence=e, next_minimum=f)
          for a,b,c,d,e,f in matrix],
    source_aliases={'D29':str(W/'scheme_A_deferred_observation_20261019_29'), 'D29-author':str(N), 'handoff':str(H)},
    immutable_primary_docs_edited=False, phase_promoted=False,
    stage_qualified=False, execute_qualified=False, research_conclusion=False))

table='| 批次 | 接纳/尝试；最长连续 | 首Job提交/首API，相对Ready ms | 首命令每侧N | 全窗RMSE m/s | 末5s均速 m/s | 样本x进度 m |\n|---|---|---|---|---|---|---|\n'
for r in rows:
    table += f"| {r['batch']} | {r['accepted']}/{r['attempts']}；{r['consecutive']} | {r['first_job_submit_offset_ns']/1e6:.3f} / {r['first_API_start_offset_ns']/1e6:.3f} | {r['first_command_n'][0]:.6f} | {r['full_RMSE_m_s']:.9f} | {r['last5s_mean_surge_m_s']:.9f} | {r['sampled_x_progress_m']:.6f} |\n"

matrix_md='| 条件 | 当前可引用结果 | 未闭合与下一步 |\n|---|---|---|\n'
for a,b,c,d,e,f in matrix:
    matrix_md += f'| {a}：{b} | **{c}**。{d} | {f} |\n'

r29=rows[-1]
prefix_table='| 保留的已观测前缀 | 样本数 | SSE/原全窗总预算 | 其余误差为0时的全窗RMSE下界 |\n|---|---|---|---|\n'
for p in r29['prefixes']:
    prefix_table+=f"| {p['duration_ns']/1e9:.6f}s | {p['samples']} | {100*p['fraction_of_original_allowance']:.3f}% | {p['full_RMSE_floor_if_other_errors_zero']:.9f} |\n"

text('documents/方案A_P1阶段对照与模型接口审查_2026-10-19.md', f'''# 方案A第30批：原P1条件对照、启动目标与有限模型接口

日期：2026-10-19。当前成果是只读审查和可实施设计；本批没有增加控制功能、运行控制实验、构建、codegen或改变阶段资格。

## 1. 本批结论和进度位置

方案A确实有工程进展：owned认证、来源复算、冻结/激活竞争处理已形成实际证据，第29批受控首档101/101连续接纳且无拒绝。但方案A的核心“模型切换时的一致执行与备份有效性”仍没有实现。原P1继续部分完成，B4/B5/M0b、M4、有限模型事务/F6仍需依次闭合；P2～P5尚无相应资格。

持续NoGo有两类不同原因：旧批次真实来源/时序/竞争失败；目前第29批仅剩第20批加入的“全窗RMSE至少减半”诊断目标失败。原交接和原P1阶段条款没有这一减半门。保留这个事前承诺及原失败；把它与原P1未完成条件分开列账，不能把它改名为安全要求，也不能删除后重判旧run为通过。

下一顺序维持 **B4来源/域/政策→最终统一版必要确认→B5/M0b→M4唯一监管器出口→有限模型事务/F6→P1复判→P2**。模型接口及组件设计现在可以准备；实际接管和模型激活不得越过各自入口条件。

## 2. 保护范围与实际版本

本地初检41,167路径、5,039,073,437字节完整复核通过，含第29批961个归档文件和331个author文件。原24处业务dirty diff为151,961字节，SHA `d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5`。另有早已单独登记的real.launch.py变化，保留当前与历史恢复副本；不能宣称所有旧路径均与原始捕获逐字节相同。

当前诊断合同diag10的SHA为 `89caaaf36783463a1e1d789bda41f7f90dc398981ddb4b3b8cd6037114333f72`，81项，qualification=temporary_shadow_diagnostic，execute=false，8组pending未清空。Worker实际复用第28批bin `1462e6be4ffec0079319cb6fb1aed8c3067df1065e9d167351092cd586e595f1`；Observer实际第29批bin `038c87f196459c19323094251bf56014491a7997d9479e0bed81de141c744522`。源码是独立研究原型，当前默认部署未因本批改变。新审核完整输入74项前后SHA相同，清单在evidence/audit_input_lock_v1.json。

五组优先交接材料、主交接和manifest完整读入并保留原字节副本；原历史材料不回写。当前MPC新目录准备在host也返回errno112 Host is down；本地归档与远程交付分开，24,125个历史远程路径的当前内容未验证。本批未改挂载、凭据或远程旧资产。

## 3. 条件—代码—证据矩阵

{matrix_md}

机器可读矩阵：../analysis/requirements_code_evidence_matrix_v1.json。证据别名及精确输入SHA在矩阵和input lock；各批历史case不能简单累加为当前统一版的整阶段资格。

## 4. 五批启动与稳态结果复算

按每个旧run原Ready-inclusive到driver close-request-exclusive窗口，完整读取Source并独立重算样本数量、SSE、RMSE、末5s均速、首次accepted Decision到Publisher API及Applied序号。旧Source/Storage认证结果按原版本引用，本批没有重新运行ROS或重新赋予端点资格。

{table}

表中x进度是窗口内首末实际Source样本位置差，各run样本跨度不同，准确跨度与同跨度0.05m/s参考距离另存JSON；不能把这些进度直接当同一终点任务排名。Applied为DDS命令回报，表中API指Publisher调用，不是plant收到或推进器产生力。

第19/20批按几何位置重定位参考，尚无固定任务时间epoch；第22/28/29批第一笔实际Job提交完成后冻结first-target task epoch。所有首Job原始frozen_state/target_state和模型初态均保存在JSON；当前五次初态为零，首保持约200ms。Ready到首API相位约278～348ms，首Job提交约79～149ms；实际启动相位没有受控配对。因此跨run改善不唯一归因于冷启动、观测移出窗口或参考变化。

第19批末5s均速0.06249，相对目标约高25%；第20批后均速已接近0.05。第29批末5s SSE仅{r29['last5s_SSE']:.6g}，而全窗SSE为{r29['full_SSE']:.12f}。当前应停止继续削减已接近零的稳态误差。

## 5. 第29批启动下界的准确含义

原全窗N={r29['sensor_count']}，门L={r29['diagnostic_comparison_threshold_m_s']:.15f}，允许SSE=N L²={r29['original_allowable_SSE']:.15f}。给定已经观测的前缀，后续平方误差非负，所以全窗RMSE至少为sqrt(prefix_SSE/N)。

{prefix_table}

纯等待到首API的17个零速样本消耗76.244%预算，其下界仍低于原门；因此不能说“等待时延本身已证明不可能通过”。加上观测到的加速前缀，约0.478s第24个样本首次超过整窗预算。保留这一前缀时，只改后半段无法救回旧run。这只针对旧轨迹与固定样本集合，不证明所有控制器、初态或协议不可达。

原命令界±25N、率限80N/s与第29批首拍人为固定0.5N不是同一约束。0.5是额外诊断等式限制，不能据它证明原可行控制集合性能极限。连续动力学、代价、任务起点、相位都可能改变启动误差；本批不为追门进一步调参，不将新协议结果替换旧失败。

## 6. 实际动态NMPC模型接口

实际生成头、安装头、静态链接清单、libcodegen归档及被选中Worker均已核验。维度为物理6+输入记忆2（NX=8），NU=2，N=20；每阶段NP=6仅参考；全局NP_GLOBAL=30，前19项水动力，后11项Q/R/Rd/Qf。现有生成C API `usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies` 把参数预计算到capsule的global_data，生成离散动力学使用它。该setter与动力学符号确实存在于实际Worker和静态归档；这只是静态能力证据，本批没有调用它或求解。

因此要修正对主方案5.2的适用解读：**新增残差/障碍和改变图或布局需要codegen；同一布局内切换已支持的水动力数值，不必重新生成。** 原主方案“p_global仅构造时写入”准确描述当前C++包装的使用方式，不代表生成C库没有更新能力。只改usv_model_dynamic.cpp仍不会自动更新优化图。

当前public AcadosBackend和研究RawBackend都只在构造时设置一次p_global；Worker从单一不可变合同构造一个后端，无运行中选模型入口。SolveJob只有model_generation和固定nominal_hash等身份，Candidate完整回显Job；当前五run model_generation都只有1，未观察真实模型切换。当前C++传播与生成后端必须在未来模型注册表中分别绑定，不能让两处用了不同参数却只改hash。

最小可实现路线见[有限模型事务设计](finite_model_transaction_design_v1.md)：冻结两组已知水动力数值，各自独占capsule，同一Worker串行使用，构造阶段完成全局参数写入，不在活动求解中修改同一capsule。无需新ROS角色或立即扩IDL；固定双模型注册表可以由新contract_hash+model_generation唯一解析并绑定参数hash。任意新模型/残差扩展另行版本化。

## 7. 本批资格与下步

本批通过的是只读输入锁、数值复算、接口检查和可审查设计。没有新Native/闭环验证，没有阶段升级、碰撞安全、GP、真实力或论文结论。第29批原case仍NoGo。

下一具体工作包按[next_implementation_plan_v1.md](next_implementation_plan_v1.md)先闭合当前B4增量与有界最终版验证入口；有限模型组件准备与M4前置分开。无需为了“证明继续”追加相同正常run或更多外围负例。
''')

text('documents/common_comparison_protocol_draft_v1.md', '''# 共同实验协议草案v1（未执行，未用于重判旧run）

目的：把系统启动、任务跟踪和模型事务分别测量，保证所有方法享有相同信息、初态、时间和资源。原20s Ready-inclusive减半目标和原NoGo完整保留，不为方案A单独删除启动段。

## 1. 保留的原指标

原窗口、每个原sensor和原关闭边界不变。列出全窗速度RMSE/SSE、末5s均速、首API、初始化费用与所有拒绝。旧run无论用新窗口算出什么值，原passed字段均不更改。第19批原本没有减半门，其用于分母和事后比较；第20批及之后有明确诊断事前承诺。

## 2. 未来统一task协议（设计）

独立实验调度器冻结TaskStart，不以“本方法首成功Job/首接受”动态推迟起点。全方法同一初态、plant参数/模型失配、路径/profile、时钟/RTF、传感器消息及已知未来参考。准备上限和TaskStart相对共同source起点的整数tick偏移K事前给定；late method记准备/截止失败，不重置task epoch。

冷启动与预热作为两个独立层，不混在结果中。冷启动不做额外求解；预热层全部方法允许相同次数/时限/CPU的预备调用且记录所有费用。准备阶段保持共同零命令，不能只给新方法提前加速。初始化、双capsule内存、预计算及预热时间全部单列并纳入端到端资源比较。具体K/调用预算必须在实现测量后、正式比较前冻结，本草案不构成已选数值合同。

task位置参考统一为x_ref=x0+v_ref*(task_time)，相同路径/任务变更才重新锚定；单纯性能模型切换不暗中重置任务进度。性能中心不参与真值/观测泄漏；oracle仅离线评价。所有方法使用同样±25N、实际锚点率限、150ms绝对截止/200ms tick和准备/执行线程预算；新增计算资源另做等资源层。

任务指标从固定TaskStart计完整时长，包含零输入等待、拒绝、降级、停止及失败，不按成功窗口裁剪。另报告完整启动-inclusive指标。指标至少包括速度/位置/航向误差、任务进度、命令与实际受控执行区间、拒绝原因、模型事务、失效恢复、尾延迟和费用。没有plant ACK时明确是命令层，没有电流电压时仅报告控制努力。

## 3. 机制与性能判定分账

有限模型组件先判断是否真实改变优化动力学、数值与绑定是否一致、晚到/混版是否零激活、旧保存计划是否独立于热启动。其目标不要求任意已知错误模型都提升RMSE。P1阶段资格仍依原P1条件；工程降级不获得P2认证备份语义。

强比较至少包含相同时序修正和执行/验证条件的固定模型基线；后续P2/P3再形成有效固定宽界B1/B2。先验强基线条件不满足时缩小名称与结论。按episode、同seed成对比较，初筛/校准/确认集分离；不把逐拍样本作独立重复。旧调试五run只用于设计，不成为独立确认集。

本批没有确定新的性能成功阈值或挑选新的有利seed；未来阈值按任务需求/明确假设事前选择，用于所有方法，另保留旧减半门结果。这里没有取得统计优势或普遍不可达证明。
''')

text('documents/finite_model_transaction_design_v1.md', '''# 有限已知模型事务：最小实现设计v1

状态：可审查设计，尚未实现/求解/运行。进入实际执行严格保持B4→统一版确认→M0b→M4→有限事务/F6顺序。

## 1. 最小选择及范围

使用现有生成图支持的水动力参数，先不加人工离散残差、GP或障碍。M0为冻结当前合同19项hydro；M1仅把Xu（全局index9，当前−2.272063）乘1.2成为−2.7264756，其他29项全局值、N20/dt.2、幅值/率限和代价不变。这是人工已知性能模型，不是辨识/学习，不等于真实plant改变；固定plant和固定状态/输入对照单列。精确浮点序列见analysis/dynamic_model_interface_v1.json。

选两独占capsule，在同一个Worker线程串行使用；各自构造时设置30维p_global，避免求解过程中修改活跃实例。首次组件仅new纯C++注册表、选择器和两capsule包装，无新ROS进程/端点、无codegen、无IDL或install变更。总活跃Job≤1、pending≤1、模型数=2；活动模型切换与求解器实例切换分别记账。

## 2. 模型身份和输入绑定

固定注册表包含schema、模型槽位/代数、完整30维typed参数及hash、19项hydro、生成图/库hash、布局、N/dt、固定权重/约束、传播实现hash。有限注册表由新不可变contract_hash绑定；既有Job的(contract_hash, model_generation)可唯一解析模型并核对内部snapshot hash，因此有限首版无需扩IDL。nominal_hash继续标识基础名义模型，不能同时模糊表示两个不同模型。若允许动态新快照、注册表变化或独立接收模型消息，再升级独立model_snapshot_hash和接口schema；旧版本默认拒绝。

模型Generation不是参数本身。Worker必须在执行前按注册表选确切capsule，并记录完整typed模型指纹和选择事件；Candidate整个Job回显。Observer在准备和激活时验证请求模型槽位、参数hash、Job/候选身份及deadline。伪改generation、遗漏参数或hash与数值不符均拒绝。

测量到目标时刻的状态传播/执行历史仍以明示的基础reconciliation模型进行；候选X/U数值一致性使用所选性能模型。两种传播用途和参数分别记录；不能用基础模型检查M1预测后制造假拒绝。当前名义点传播不获得物理误差集合或plant保证。

## 3. 准备和固定tick激活

状态机保留active=M0、pending=M1。准备M1时旧已接受工程计划按原有效期保持，不能提前把active改为M1。Job为pending模型求解；返回时只进入pending slot，先核对模型/状态/输入锚点/任务/时钟/截止，再于固定tick一次业务提交原子切换(active model, accepted immutable plan, activation metadata)。迟到、旧版本、来源变化或无候选都不激活pending。

旧候选、旧pending和旧active各有明确寿命。拒绝pending不回滚已发生的命令，也不把旧计划续命；即使重发同命令也不能刷新原持有/备份有效期。没有P2证书时保存的只是不可变工程轨迹，不能称认证备份。之后P2需同时绑定固定物理包络、障碍、执行器历史、有效期、剩余Tb/hmax及接续集合。

当前reference_epoch把model_generation纳入失效绑定；未来需要明确性能模型切换与task epoch的关系。为共同任务公平，单纯M0→M1保持同一TaskStart/进度，不能因模型变化把x_ref重新锚定；真实任务/路径/时钟重置另作新generation。此变动涉及参考、输入冻结和候选准入，需要单列受影响验证。

两capsule暖启动矩阵完全独立。切换后首求解从同一实际状态/执行锚点初始化；从另一模型缓存拷贝仅可作明示启发式并重新传播，首版不做跨模型迁移。被接受X/U深拷贝，不引用任一可变warm buffer。当前0.5N/4RTI首Job策略是旧诊断特例，不能自动套到任意M1首次Job；最初模型组件按相同单次RTI预算比较，无该额外等式，旧run保持。

## 4. 必要验证与退出预算（待实施）

先纯C++、不建ROS context，不启动闭环。只运行下列与新模型功能直接相关的检查：

1. 注册表两模型布局/精确hash/有限性和质量矩阵非奇异；未知槽位、NaN、错维、权重或约束越界拒绝。生成库调用之前做检查，不能让生成C函数的exit(1)成为正常校验。
2. 同一冻结六维状态/两输入，用当前基础和M1各自生成离散函数，与各自独立C++ RK4对拍；基础模型复现原数值，M1在非零u探针上确实改变下一状态，零状态零输入控制探针允许相同。输入记忆精确Tprev←u。原始探针状态预先固定，不能把所有模型都相同的零点当切换成功。
3. 同一冻结Job/参考/锚点，串行选择M0/M1/M0；记录实用p_global、capsule地址/所有权、X/U/有限状态和所选模型defect。单RTI结果不当最优解，控制输出恰相同不单独判切换失败，真实模型函数变化与数值对拍是主要证据。
4. 暖启动隔离、保存轨迹深拷贝、pending废弃和回到M0不污染原M0；晚到/错槽/错模型数值/旧task/错anchor的有界状态机事件不激活。只有组件语义；不能据此授予M4或压力资格。

首次实现预算：新增组件最多2个头/实现+1个针对性Native测试；已有生成库只读链接；一次构建最多2次修正；组件总墙钟≤120s、输出≤100MiB、模型数=2、不批量闭环。失败保存首次命令/完整输出/源/bin/静态输入；达到预算即交付具体原因和最小修复，不用增加相同正常run掩盖。

## 5. 后续实际链的必要改动

正式实施时需新合同/registry hash、Worker模型选择与能力/配置声明、Observer pending/active事务、Job输入/参考epoch绑定、数值检查器以及当前版本来源证据。两模型注册表可复用现有消息字段，不代表现有消息消费者已支持切换；不得只改JSON就运行旧bin。

M4要求新监管器直接成为每侧唯一实际出口；当前controlled Publisher转发Decision只作诊断来源。完成M0b后才设计有界独占接管运行，单独验证部分发布、实际publish-start率限与最终反馈。有限模型激活按原P1注入50/150/250/400ms结果返回延迟、数值失败、旧状态、版本混合和连续5拍无候选；由独立释放调度器安排，不让独占Worker堆积延迟任务。

工程时序/输入成功只支持P1有限范围。P2物理宽界、备份接续、残差/障碍codegen和年龄安全语义另行实现；不存在当前安全证书或性能改善承诺。
''')

text('documents/next_implementation_plan_v1.md', '''# 第31批最小实施入口与后续顺序

第30批完成只读条件矩阵、五run复算和实际接口审查。原第29批NoGo不改，停止首控/RTI调试。下一批优先处理B4当前合同增量；有限模型组件准备有明确边界，不能绕过正式执行顺序。

## 1. 先落实当前B4增量，而非重新做整套S0～S5

以第29批准确代码/bin/diag10合同为基准，在新批目录实现一份机器可读参数/政策适用登记和独立检查器。覆盖当前81个top-level字段、19个hydro以及新参考时间、pair retry、首Job冷策略、32历史和最多两次校验、延后观测政策。读取实际五角色owned配置及源/bin/contract，证明“值从哪里来、谁使用、哪个版本验证过、哪些仍是工程选择”；不是把旧diag5的74项数字改成81。

登记中的B4时间/域、输入斜坡、源失效/部分发布、Worker同run不复活和关闭政策按现有消费者逐条给出；把旧8组pending拆成具体所需证据及已具备前提。没有数值校准/正式域证据的保持pending，不能删列表或填hash获得Frozen。检查器只验证身份/覆盖/适用逻辑，不颁发阶段资格。

只补新登记/消费者错配的必要离线检查；已有原输入锁和正常101/101结果直接引用，不重复完整正常run、所有Native或任意消息负例。代码范围≤一个登记生成/检查脚本、一份schema/数据、一份明确缺口表；首次处理墙钟≤10min、输出≤100MiB，失败证据留存。不得再为该范围建新ROS角色或codegen。

## 2. 在同批明确最终版最少确认用例及停止条件

基于受影响图选择有限压力/源失效/恢复/部分发布/关闭集合，写定故障触发点、支持域、固定150ms截止与20ms工程检查的限定语、退出条件和预算。与历史R5差异必须具体到当前代码/角色。只有受影响条件需真实触发；不增加无关排列，也不把正常退出0当压力确认。

B4登记和最终版确认设计可审查后即停止本工作包。不启动新控制实验，除非新实施内容已经形成明确事前Go和必要入口；原性能减半门不再作为无限追加启动调试的理由。

## 3. 沿固定顺序继续

最终统一版必要确认完成后→B5/M0b正式证据冻结→M4监管器唯一双路出口→有限已知模型准备/固定tick事务及原P1故障用例→F6/P1复判→P2物理包络/有限备份。

finite_model_transaction_design_v1.md中的双capsule纯组件可以作为该主线的代码准备；若实施，独立记录其组件结果，不启用execute或模型激活，不把它作为M4完成。它复用现有30维全局参数，不需要为已支持水动力值重新codegen。新增残差/障碍留待相应阶段。

统一状态字段分为component_validation、stage_qualified、execute_qualified、true_plant_qualified、research_conclusion；MPC恢复后按本地sealed inventory精确新目录复制及二次SHA读回，未完成前持续delivery_pending。
''')

put('preflight/theory_scope_decision_v1.json', dict(
    schema='control-theory-scope-decision/v1', verdict='GO', scope='read-only audit and design only',
    reasons=['no solver/context or new control experiment','local source, actual linked symbols and frozen complete windows inspected',
             'half-RMSE diagnostic commitment preserved separately from original P1 requirements'],
    assumptions=[{'assumption':'Source/Storage joins apply only to exact old versions','status':'historical verified evidence, no transfer'},
                 {'assumption':'same-layout p_global hydro influences generated graph','status':'source/API/actual symbol evidence; dynamic switch not tested'},
                 {'assumption':'observed prefix lower bound','status':'fixed old trajectory/population, no universal infeasibility claim'}],
    risks=['metadata-only model switch','task epoch reanchor on model change','warm cache aliasing saved trajectory',
           'engineering hold/ramp mislabeled certified backup','parameter inventory growth replacing research mechanism'],
    safe_next='bounded B4 delta registration and exact affected final-version plan; two-capsule design only before execution gates',
    override_policy='no override requested or needed for this read-only scope; any future control experiment requires its own concrete preflight',
    EDA_STA_PPA_route='not applicable; local control Source/Storage/config identities used',
    new_control_experiment_submitted=False, stage_qualified=False, execute_qualified=False, research_conclusion=False))

text('postrun/retro.md', '''# 第30批复盘

本批把诊断性能门、原阶段要求和模型能力分账，独立复算五run并形成下一最小实现设计。仅组件/文档审查完成，没有新增控制器功能或阶段资格。

首次保护helper误把归档run路径写成author run名；保留v1与失败输出，v2使用实际归档s005_01路径及原SHA完成全本地核验。首次审查脚本把已decode的头字符串与bytes比较导致自身断言失败；原源码/安装头实际逐字节相同，原SHA未变。保留v1、attempt01日志及当时副本；v2修正比较类型后通过74项前后输入锁。两次均为本批工具实现错误，不是旧模型/端点失败，不靠改expected消除。

MPC在host明确errno112，交付待完成，不触发反复重挂载。旧失败、本地资产和原业务diff保留。

理论反思：静态C接口/符号不等于动态切换验收；固定观测前缀下界不等于所有控制策略不可达；阶段门不得靠文档状态翻转。下一批只做具体B4增量与必要版本确认设计，不再追加同类启动试验。有限模型原型使用现有全局参数与独占capsule，避免未经需要更改生成图。EDA STA/PPA/route不适用。
''')
print(json.dumps({'passed':True,'matrix_rows':len(matrix),'documents_created':4,'stage_qualified':False},ensure_ascii=False))
