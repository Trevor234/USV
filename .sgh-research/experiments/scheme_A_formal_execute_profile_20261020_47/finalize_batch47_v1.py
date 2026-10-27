#!/usr/bin/env python3
"""Emit the reviewed status, report, next plan, QA, and create-only archive seal."""
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
M = Path('/home/trevor/MPC') / D.name


def load(p):
    return json.loads(p.read_bytes())


def pin(p):
    data = p.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def emit(p, value):
    with p.open('xb') as f:
        f.write(value.encode() if type(value) is str else (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())


def main():
    audit = load(D / 'postrun/independent_freeze_audit_v1.json')
    sub = load(D / 'freeze/freeze_submission_v1.json')
    initial = load(D / 'preflight/workspace_initial_v1.json')
    final = load(D / 'preflight/workspace_final_v1.json')
    parity = load(D / 'verification/profile_parity_v1.json')
    entry = load(D / 'verification/entry_policy_cases_v2.json')
    binder = load(D / 'verification/freeze_binding_cases_v1.json')
    assert audit['passed'] and initial['passed'] and final['passed'] and parity['passed'] and entry['passed'] and binder['passed']
    assert initial['protection']['logical_bytes_streamed'] == final['protection']['logical_bytes_streamed'] == 6548663296
    seal = []
    for p in sorted((D / 'freeze').iterdir()):
        assert p.is_file() and not p.is_symlink()
        before = pin(p);p.chmod(0o444);assert pin(p) == before
        seal.append({'path': str(p), **before, 'mode': p.stat().st_mode & 0o777})
    emit(D / 'postrun/freeze_read_only_seal_v1.json', {'schema': 'P1-engineering-freeze-logical-and-read-only-seal/v1',
         'files': seal, 'hash_bound_immutable_version': True, 'OS_write_impossible_claimed': False,
         'server_durable_storage_claimed': False, 'old_asset_modes_changed': False})
    next_plan = {
        'schema': 'P1-after-M0b-next-M4-implementation-plan/v1', 'based_on_freeze_index_sha256': sub['freeze_index_sha256'],
        'frozen_contract_sha256': sub['contract_sha256'], 'current_step_closed': 'B5/M0b selected finite engineering contract and policy freeze',
        'steps': [
            {'order': 1, 'id': 'M4-owned-runtime-entry', 'action': 'derive current Observer39 admission/tick + formal owned identity/config preparation + frozen47 entry policy; regulator becomes sole SolveJob/Decision/Applied and dual thrust owner; old Publisher absent; adapt only affected Worker/Fixture/Recorder interfaces',
             'required_binding': 'new immutable source/bin/config/run/boot/GID manifest references parent frozen index+contract; existing calibration ELFs are not execute owner proof',
             'gate': 'exact v3 profile/mode/resource typing; disabled ordinary production release; explicit isolated nominal M4 entry and owned gate before any API; no fake bootstrap anchor or legacy Applied authority'},
            {'order': 2, 'id': 'M4-affected-tests-and-assets', 'action': 'review exact F5/current nominal/plant/reference asset mapping and new code differences; rerun affected deterministic ownership, source/task/admission, fallback/partial/close and config regressions only',
             'gate': 'source fixtures 0.05m/s calibrated subset explicitly identified; source/plant/reference differences cannot be named original full M4 qualification; no new threshold, weights, model, GP or RTI tuning'},
            {'order': 3, 'id': 'M4-first-isolated-normal', 'action': 'preregister new four-role owned local nominal run without legacy Publisher; begin immediate real zero bootstrap and fixed T200ms heartbeat, then normal solver jobs; collect complete 20s Source/Raw/Witness/Stored and full API stream',
             'budget': {'source_window_ns': 20000000000, 'whole_driver_wall_ns': 45000000000, 'automatic_retries': 0},
             'gate': 'first actual zero pair has rho unavailable, later per-side successful start anchors; full startup/business/fallback/shutdown gap<=240ms, span<=5ms, jitter<=20ms; all expected close outcomes retained'},
            {'order': 4, 'id': 'M4-original-fault-confirmation', 'action': 'after normal pass, register original nine-group fault matrix cases for the exact new runtime; use each appropriate deterministic or actual controlled trigger and exact exception flags',
             'gate': 'new runtime output branch cannot inherit old calibration identity; no extra unexplained loss/timeout/partial; native block and late delivery stay distinct; no production flag flip to hide test scope'},
            {'order': 5, 'id': 'F6-known-model-transaction', 'action': 'under sole execution chain prepare two finite immutable numeric M0/M1 capsules, atomic model+plan commit, old/mixed rejection, saved plan immutability and separate warmstart',
             'gate': 'NX8/NU2/N20/NP6/NP_GLOBAL30 layout and fixed numerical setter path; no new codegen, GP or PPO'},
            {'order': 6, 'id': 'P1-original-joint-review', 'action': 'review original time/version/ownership/normal-fault/known-model obligations and complete source/bin/config/record bindings; freeze F6 and report actual P1 result',
             'gate': 'M4 normal success alone does not close faults/model transaction; no half-RMSE tuning or P2 full collision certificate added as new P1 gate'},
        ],
        'stop_conditions': ['old/new physical owners overlap', 'frozen index/contract or live run/boot/proc/GID/effective config mismatch',
                            'invalid/late/wrong-target/old-task candidate becomes normal output', 'unknown or partial output relabeled known success',
                            'full stream timing/source/recording budget exceeded without predeclared exception', 'cleanup_failed or old owned group not empty'],
        'do_not_repeat': ['batch45 prepared formal four-role source', 'batch46 current five-ELF normal20s source', 'old39-42 faults without affected-code reason'],
        'physical_execute_release_enabled': False, 'M4_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'automatic_next_ROS_run_registered': False, 'research_conclusion': False,
    }
    emit(D / 'postrun/next_implementation_plan_v1.json', next_plan)
    report = f'''# 方案A 第47批：正式profile、owned入口政策与B5/M0b冻结

2026-10-20。承接46的当前版本正常来源窗及43/44/45的政策、同源契约和正式准备组件。本批完成两个原定冻结动作：**正式execute目标profile/来源/owner/bootstrap政策固定；真实不可变合同与证据索引提交并核验。**

## 当前资格

| 层次 | 实际结果 |
|---|---|
| 组件验证 | 同源双profile校验、纯owned入口政策核、冻结绑定校验通过 |
| B5/M0b | 选定有限工程域的参数/政策合同已冻结；新合同pending8清空，旧pre-freeze原件仍有8项 |
| M4 | 新Regulator实际唯一输出入口及其正常/故障确认尚未完成 |
| F6 / 完整P1 | 已知模型事务及原P1联合复判尚未完成 |
| 研究结论 | 未新增控制性能优越性、plant/6DOF、一般转弯/mixed、完整1.2m/s域或硬实时证明 |

新合同中的`execute_qualified=true`表示v3规定的工程合同冻结状态；本批实际运行释放开关`physical_execute_release_enabled=false`，未启动ROS/物理输出。纯组件输入中的GID、PID和API返回均为确定性测试事实，不能当作M4实际所有权证据。

## 修改与作用

1. `implementation/current_contract_spec_v1.json`派生同源profile目录，原diag10/81字段和旧v3识别保留。生成器从同一份spec生成Python/C++规则及资源约束，正式schema仍为v3、84字段。

| 相对旧正式pre-freeze的接口字段 | 新值/含义 |
|---|---|
| supported_parameter_profile | P1_owned_nominal_execution_20261020_01 |
| baseline_input | F5_NOMINAL_SOURCE_OWNED_REGULATOR_20261020_01，具体校准资产另表绑定 |
| preparation_retry_policy | owned reference-pair完成门；脱离旧phase Publisher授权 |
| propagation_semantics | 新Regulator逐侧真实成功API的publish-start历史；mixed保留独立IMU戳；未来held输入、RK4名义点预测 |

仅上述4个字符串字段构成profile语义差集。N20/dt0.2、19项水动力、Q/R/Rd、幅值/映射、rho80、H600ms及年龄/RTF/jitter/gap/span/watchdog/lease/清理预算均未调参。最终frozen合同另有5项资格/证据字段变化：qualification、execute_qualified、parameters_are_diagnostic_only、pending_final_calibration、freeze_evidence_sha256。

2. `owned_execution_policy_v1.json`及`native/owned_execution_entry_v2.hpp`固定入口规则。必须绑定新run/boot/合同/manifest/GID，非owner输出数为0，旧物理owner已退出。初始两侧均unknown，数字零不构成权威；每侧真实API成功后，才以该侧实际起始时间建立锚点。部分失败保留成功侧事实，失败侧unknown，业务终止不自动复活。

prepare grant即固定tick起点，首零请求pair须在200ms内开始；后续按T200ms维持零请求，直到输入/能力等门禁有效且可提交业务。最大gap240ms、pair span5ms、tick jitter20ms事前固定，迟拍不补发追赶。HOLD从最后接纳激活计时，重复发布不续期；invalid直接ramp；unknown侧只能请求零而无变化率资格。shutdown把零请求、各API成功、进程退出和plant未知分别记账。

这些是可编译、可对拍的离线入口政策核，M4还需把它接入实际Regulator计时、准入、owned图和发布API。当前Observer39仍保持原diag10+shadow；45仅正式prepare；未把旧legacy Applied改名当作新owner历史。

3. `python/freeze_binding_v1.py`要求调用方同时提供独立固定的index与contract SHA。它严格解析完整v3、核验去除marker后的合同模板、policy/spec、全部文件字节与大小、参数来源、故障判据和资格范围。64hex形状不能替代真实证据；更改任何冻结参数/资源或证据字节会拒绝。路径要求规范绝对路径及无symlink别名，读取期间核对文件身份并采用有限预算。

索引先绑定marker为空的规范化frozen模板，再把索引实际SHA写入最终合同，避免自引用hash。冻结文件已设只读并按hash封存；不宣称操作系统不可修改、文件系统已加锁或共享盘持久性得到证明。M4启动仍需重新核验和现场owned门禁。

## 实际验证与失败保留

- Python/C++原始字节对拍：641项通过（原385＋新256；53项预期接纳、588项预期拒绝）。旧类型/重复键/NaN/资源/mode规则保留；execute运行模式继续拒绝。
- 纯owned入口政策：92项通过，覆盖unknown、双成功、partial、实际逐侧时间、启动整流gap、HOLD等号/超界、5次miss、ramp、jitter、shutdown及context身份/类型。
- 真实冻结绑定及altered-copy：24项通过（3项接纳、21项拒绝），包括实际包、精确副本、伪造marker、源文件同大小改写、阈值/资源改写、旧pre-freeze、错误profile、越权execute。
- 同源生成5个输出逐字复现；两次离线构建涉及3个probe ELF，均成功，未重编译五个业务ELF。
- 19项提交条件和23项最终独立审计通过。最终审计再次逐字核验索引全部{sub['artifact_count']}项资产。

初轮入口测试有1项失败：把右侧ramp末值预期写为0；右侧实际锚点晚200ns，正确剩余为0.000016N。原v1源码/请求/输出/失败报告/ELF保留；v2修正预期，并根据代码审查增加等待期零请求、bootstrap不可复用两条约束及反例。未修改数值预算，也没有把失败覆盖成通过。

本批前后各核验50,790条既有记录路径、6,548,663,296字节；原24项业务diff保持151,961字节、SHA d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5。已单独登记的real.launch.py差异、Git HEAD/分支、旧封存资产与全部失败保持本批开始时状态。原MPC历史镜像未在本批全量重读；本批交付的逐字核验以delivery_verification.json为准。

## 冻结身份与适用范围

- spec SHA：`{sub['spec_sha256']}`
- policy SHA：`{sub['policy_sha256']}`
- freeze index SHA：`{sub['freeze_index_sha256']}`
- frozen contract SHA：`{sub['contract_sha256']}`
- 索引文件数{sub['artifact_count']}，合计{sub['artifact_bytes']:,}字节；包括源码、当前校准ELF、模型、配置、工具、阈值来源及新政策组件ELF。

校准来源仍为46的owned nominal直行0.05m/s短域：20.002935074s、101个动态Job、窗内100/100接纳、2个mixed Job。完整legacy启动API gap约1.54s仍是240ms失败事实；新bootstrap政策由既有T/gap预算和确定性规则固定，等待M4实际确认。近1:1外推、可信prepared图、名义点模型、本地有限调度仍为工程前提。F5 nominal/plant/reference与当前fixture的具体映射必须在M4差集审查中核实；0.05校准资产不能自动取得原M4整体或plant资格。

原M0b允许shadow或无输出校准；本批没有另增“完整no_output业务长跑”门，也没有要求首次execute观测作为冻结来源。旧半RMSE NoGo（0.009195365994 > 0.007392495755）保留，未作为新的P1门槛或通过理由。

## 下一步

按固定顺序推进：**M4新Regulator唯一输出入口 → 受影响差集回归与新正常/故障确认 → 已知数值模型事务/F6 → 原P1联合复判。** 不重跑45准备、46正常校准或无差集的39～42故障；不调RTI/权重/半RMSE，不引入GP/PPO。具体任务、有限首跑预算和STOP见[下一步实施计划](下一步实施计划_M4唯一输出_2026-10-20.md)及postrun/next_implementation_plan_v1.json。

本批目录`{D}`；MPC交付目录`{M}`。冻结索引引用本机原始资产绝对路径，本批MPC镜像不重复复制所有前序原始数据；校验依赖原路径可读和精确字节一致。
'''
    emit(D / 'documents/方案A_正式profile与B5M0b冻结实施报告_2026-10-20.md', report)
    plan = f'''# 下一步实施计划：M4唯一Regulator输出

2026-10-20，承接第47批。B5/M0b有限工程合同已提交并通过独立字节核验；不再把“正式profile/冻结hash尚未提交”列为缺项。

固定上游：profile `P1_owned_nominal_execution_20261020_01`；freeze index `{sub['freeze_index_sha256']}`；contract `{sub['contract_sha256']}`。旧pre-freeze、失败及校准范围保留。当前物理release=false，M4/F6/P1均未验收。

## 1. 实现实际owned执行入口

从Observer39的准入/绝对tick和Worker35数值后端承接，结合45实际owned身份、有效配置、准备链及47的v3/policy/binding，派生新的Regulator业务入口。只有新Regulator创建左右推力Writer和SolveJob/Decision/Applied出口，Worker/Fixture/Recorder不创建物理输出Writer。旧Publisher必须在新run之前退出，不能同run热切换。

审查Worker/Fixture/Recorder对正式profile、角色身份、Applied来源及有效配置的实际差集，只改必要接口；不把已有shadow ELF或prepare-only ELF改名。新source/bin/config/run/boot/GID必须有独立manifest，绑定上述冻结父合同；未来ELF不能回填旧冻结索引。普通生产release仍关闭，隔离nominal M4入口需明确的本地owned门禁与run绑定。

真实零bootstrap成功前两侧unknown、无Job；成功侧以自身实际API起始时间建锚。grant时开始固定T200ms零请求心跳，准备/温启期间也不能出现1秒静默。partial、HOLD、ramp、5misses、shutdown按47冻结政策接入实际API，保留成功侧不可回滚事实。

## 2. 做受影响回归与资产对照

先逐项核对F5 nominal/plant/reference与当前0.05 fixture的来源和差异，说明本次隔离来源到底覆盖哪个工程组件。未闭合原F5资产要求时不能宣称原M4整体通过。沿用冻结预算和数值；新mode/owner/profile/source接口受影响项按实际差集回归，已有同版本证据直接引用。

## 3. 一次有限新正常确认，再原故障矩阵

新四角色隔离nominal运行（Regulator、Worker、Fixture、Recorder），无legacy Publisher。先正常直行，连续Source窗20s，whole Driver wall上限45s，自动重试0；清理各阶段沿合同有限值，进程组未空即cleanup_failed并禁止重启。

核对两侧实际Writer同owner、完整bootstrap到shutdown的API流、gap≤240ms/span≤5ms/jitter≤20ms、实际逐侧rho/unknown、Job→Candidate→Decision/Applied、Source/Raw/Witness/Stored及普通关闭。首次zero pair不声称rho可用，不剪掉启动gap，不把零请求或进程退出当plant零推力。

正常通过后按freeze/M4_fault_matrix_v1.json原9组判据逐项注册当前版本受控故障。native阻塞与结果晚送分开；partial/drop/强制退出的normal完整性、rate、worker session等flag按实际false/unknown保留，额外未解释异常仍失败。冻结数值不能在确认run内调节。

## 4. F6与原P1

唯一执行链闭合后，做有限已知数值M0/M1模型准备、model+plan原子提交、旧/mixed候选拒绝、已保存plan不可变及warmstart分离；随后原P1联合复判。保留NX8/NU2/N20/NP6/NP_GLOBAL30与既有数值setter，不新codegen、不加GP/PPO。

STOP：双物理owner；合同/图/进程/GID/配置绑定不一致；迟到/错target/旧task/非法候选成为正常输出；partial/unknown被伪装成功；整流时间或记录预算超限；清理失败。保存失败，修复具体差集后升版本，不覆盖旧包、不无原因重跑已关组件。

本计划没有启动新的ROS运行。机器计划见postrun/next_implementation_plan_v1.json。
'''
    emit(D / 'documents/下一步实施计划_M4唯一输出_2026-10-20.md', plan)
    emit(D / 'CURRENT.md', f'''# 方案A 当前状态：第47批（2026-10-20）

已完成正式owned execute目标profile/政策接口与真实B5/M0b有限工程冻结。v3仍84字段，4个来源/owner/profile字符串差集；控制数值/19hydro/预算不变。新frozen合同pending=[]，旧pre-freeze原件pending8保留。index SHA {sub['freeze_index_sha256']}；contract SHA {sub['contract_sha256']}。

641项Python/C++对拍、92项纯入口政策、24项冻结绑定（21拒绝）通过；5生成输出逐字复现，19提交条件与23最终独立审计通过。索引4103文件/373401307字节；首轮右侧ramp预期错误及v1源码/ELF/失败保留。新实际ROS/输出0，物理release=false。

资产前后50790记录路径/6548663296字节与本批开始状态一致，原24项业务diff和已登记real.launch.py差异保留。只对新MPC交付做逐字双回读，旧镜像不称全量重验。

阶段区分：组件通过；B5/M0b选定工程合同已冻结；M4唯一实际输出、F6已知模型事务、完整P1尚未完成。nominal0.05短域、旧startup gap约1.54s失败、plant/一般域/WCET未证明及半RMSE NoGo均保留。

下一步直接M4实际owned入口/受影响回归/新正常与原故障矩阵→F6模型事务→原P1。45准备、46当前正常来源缺项已关闭，不重跑。主报告与M4计划在documents；完整证据、冻结包与交付回执在本目录。
''')
    emit(D / 'postrun/control_retro_v1.md', '''# 第47批复盘

结果：正式profile从诊断legacy来源语义派生为owned目标；原数值不变；工程合同与真实索引已封存。主机制flow_policy_mismatch：原profile/owner/bootstrap来源不能支持正式执行入口身份；通过明确4字段差集、同源规则和纯政策核消除接口定义缺项。WNS/PPA/DEF等EDA项不适用。

假设验证：可在首次execute之前使用shadow来源、既有观察和确定性校验固定有限门槛，成立；无需另增完整no_output业务长跑。实际新Regulator输出与plant未验证，留给原M4。右侧200ns实际锚点差异导致初轮预期错误，保留失败并按物理单位修正；不是阈值调整。

经验：数字零不等于成功API锚点；整流startup gap不能裁剪；每侧时刻必须独立计算；shape marker不能替代文件绑定；当前组件证据不升格为实际执行证明。

下一步M4入口与新正常/故障：confidence高、impact高、cost中、risk中；证据足以承接合同政策，实际新增实现需独立差集审查和有限注册。重复旧准备/正常校准：impact低，不选。停止条件沿next plan：双owner、身份/合同失配、非法动作、整流超限或cleanup_failed。未自动启动递归ROS实验/后台任务；先落实具体运行入口及受影响验证。
''')
    qa = {'schema': 'SchemeA-formal-owned-profile-M0b-final-QA/v1', 'passed': True,
          'B5_contract_freeze_qualified': True, 'M0b_selected_engineering_freeze_qualified': True,
          'formal_profile_and_policy_component_passed': True, 'immutable_frozen_package_verified': True,
          'M4_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
          'stage_qualified': False, 'stage_qualified_scope': 'overall P1; B5/M0b qualification is stated separately',
          'physical_execute_release_enabled': False, 'actual_ROS_runs': 0, 'physical_API_calls': 0,
          'profile_contract_execute_qualified_field': True, 'new_contract_pending_count': 0, 'old_pre_freeze_pending_count': 8,
          'spec_sha256': sub['spec_sha256'], 'policy_sha256': sub['policy_sha256'],
          'freeze_index_sha256': sub['freeze_index_sha256'], 'frozen_contract_sha256': sub['contract_sha256'],
          'frozen_artifact_count': sub['artifact_count'], 'frozen_artifact_bytes': sub['artifact_bytes'],
          'profile_raw_parity_cases': 641, 'old_raw_cases': 385, 'new_profile_cases': 256,
          'entry_policy_cases': 92, 'binding_cases': 24, 'binding_expected_refusals': 21,
          'generator_exact_outputs': 5, 'freeze_condition_checks': 19, 'independent_final_audit_checks': 23,
          'offline_compiled_probe_ELFs': 3, 'old_business_ELFs_rebuilt': 0,
          'first_entry_test_failure_preserved': True, 'old_failures_and_pre_freeze_preserved': True,
          'original_business_diff_bytes': 151961, 'historical_recorded_paths_rechecked': 50790,
          'historical_logical_bytes_rechecked': 6548663296, 'historical_MPC_mirrors_whole_bytes_rechecked': False,
          'current_MPC_delivery_verified_by_separate_receipt': True,
          'plant_qualified': False, 'full_1_2_turn_mixed_domain_claimed': False, 'hard_realtime_claimed': False,
          'control_numeric_tuning_performed': False, 'GP_or_PPO_or_codegen_added': False,
          'research_conclusion': False,
          'proofs': {str(p.relative_to(D)): pin(p) for p in [D / 'postrun/independent_freeze_audit_v1.json', D / 'postrun/frozen_package_verification_v1.json', D / 'verification/profile_parity_v1.json', D / 'verification/entry_policy_cases_v2.json', D / 'verification/freeze_binding_cases_v1.json', D / 'preflight/workspace_initial_v1.json', D / 'preflight/workspace_final_v1.json']},
          'next_plan': 'postrun/next_implementation_plan_v1.json'}
    emit(D / 'postrun/final_QA_v1.json', qa)
    files = [];directories = []
    for p in sorted(D.rglob('*')):
        assert not p.is_symlink(), str(p)
        if p.is_dir():directories.append(str(p.relative_to(D)))
        else:files.append({'relative_path': str(p.relative_to(D)), **pin(p)})
    inventory = {'schema': 'SchemeA-formal-profile-freeze-archive-inventory/v1', 'batch': D.name,
                 'files': files, 'directories': directories, 'file_count_before_inventory_and_receipt': len(files),
                 'total_bytes_before_inventory_and_receipt': sum(f['bytes'] for f in files),
                 'scope': 'this new batch only; index and receipt are detached archive metadata; old roots untouched',
                 'B5_contract_freeze_qualified': True, 'M0b_selected_engineering_freeze_qualified': True,
                 'physical_execute_release_enabled': False, 'M4_qualified': False, 'P1_qualified': False}
    emit(D / 'archive_inventory_v1.json', inventory)
    print(json.dumps({'passed': True, 'files_before_inventory_and_receipt': len(files),
                      'bytes_before_inventory_and_receipt': inventory['total_bytes_before_inventory_and_receipt'],
                      'inventory_sha256': pin(D / 'archive_inventory_v1.json')['sha256'],
                      'QA_sha256': pin(D / 'postrun/final_QA_v1.json')['sha256'],
                      'B5_M0b_engineering_freeze': True, 'physical_release': False}))


if __name__ == '__main__':
    main()
