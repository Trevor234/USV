#!/usr/bin/env python3
"""Persist reviewed facts, bounded follow-up plan, and preservation checks."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
B68 = BASE / 'scheme_A_M4_t1_component_wiring_20261024_68'
B67 = BASE / 'scheme_A_M4_fixture_gap_20261024_67'
REPORT = '方案A_第68批代码复核与第69批验证修正及后续计划_2026-10-24.md'


def read(relative):
    return json.loads((ROOT / relative).read_text())


def pin(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


def create(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(value, (dict, list)) else value)


def link(path, label=None, line=None):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    suffix = f':{line}' if line else ''
    return f'[{label or path.name}]({path}{suffix})'


original = read('evidence/runner_review02/artifact_readback_v1.json')
counter = read('evidence/stale_event_probe/counterexample_v1.json')
runner = read('evidence/reviewed_t1/attempt01/verification_v1.json')
verdict = read('evidence/verdict_tests/verification_v1.json')
reader = read('evidence/event_reader_tests/verification_v1.json')
mirror = read('evidence/mirror68_review_v1.json')
assert counter['counterexample_confirmed'] and runner['complete'] and verdict['passed'] and reader['passed']
assert mirror['originals_currently_match'] and mirror['only_declared_document_copies_extra']
assert all(row['matches'] for row in mirror['derived_documents'].values())

findings = [
    {'id': 'R1', 'priority': 1, 'kind': 'runner/finalizer failure gate',
     'title': '变异失败和最终失败没有可靠传到进程退出码',
     'file': str(B68 / 'scripts/run_t1.py'), 'line': 254,
     'related': [{'file': str(B68 / 'scripts/run_t1.py'), 'line': 194},
                 {'file': str(B68 / 'scripts/run_t1.py'), 'line': 244},
                 {'file': str(B68 / 'scripts/finalize.py'), 'line': 163}],
     'evidence': ['evidence/runner_review02/failure_exit_counterexample_v1.json',
                  'evidence/runner_review02/finalizer_exit_counterexample_v1.json'],
     'finding': '原main在M1未prepared时仍返回0；原finalizer输出all_green=false后正常返回None，入口仍以0退出。mutation caught还把非RUN当断言失败，且未要求mrc=1；atom汇总仍只看RUN。',
     'repair': '新69 runner用同一严格判定函数检查完整人口/执行结果/failures、精确命名断言、RC1、prepared/编译结果、身份前后及3变异非空人口；失败写独立记录并非零退出。',
     'status': 'fixed_in_derived69_not_backwritten_to68'},
    {'id': 'R2', 'priority': 1, 'kind': 'test observation false positive',
     'title': '注册事件没有绑定本次Job，可用旧成功冒充新调用成功',
     'file': str(B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'), 'line': 138,
     'evidence': ['evidence/stale_event_probe/counterexample_v1.json'],
     'finding': '省掉new-version Job2 candidate()调用后，原ReferenceReplaceDuringSolve仍绿；完整Source只有Job1注册。flush_pad的真实填充不等于本次事件确认。',
     'repair': '新helper匹配完整job_json、精确type及ready_commit_ns>=本次调用时间，200ms有限等待；新Job恢复同时核对candidate和slot实际状态。',
     'status': 'fixed_in_derived69_and_retested'},
    {'id': 'R3', 'priority': 1, 'kind': 'coverage interpretation',
     'title': '25项执行通过不能证明原23项每个语义都闭合',
     'file': str(B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'), 'line': 471,
     'related': [{'file': str(B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'), 'line': 232},
                 {'file': str(B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'), 'line': 239},
                 {'file': str(B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'), 'line': 345}],
     'finding': 'CommittedSubmit测试只驱动手工echo/ready ticket/activate helper，没有调用真实prepare_loop提交路径；ReferenceReplace先注册candidate再改path，是ready窗口；shape用例改的是Job horizon/dt，未驱动原生结果维度分支。失败用例同时把三个布尔标志置false，尚未隔离success和solver_invoked各自的拒绝门。',
     'repair': '保留已证消费/回调层，新增小范围真实提交与logical in-flight用例；原生shape先绑定固定类型/生成端证据，不把metadata拒绝改称结果shape已覆盖。',
     'status': 'follow_up_scope_debt_not_a_production_Regulator_bug'},
    {'id': 'R4', 'priority': 1, 'kind': 'T2 causal plan',
     'title': 'T2-B的candidate_received触发位于计算结果之后',
     'file': str(B68 / 'postrun/t1_handoff_to_t2_v1.json'), 'line': 29,
     'finding': '用candidate_received触发clear/replace只能覆盖结果已生成后的窗口；不能据此宣称Worker求解在途。T2-A的silent clock还会先触发100ms receipt stale；T2-C依赖异步Source可见性，必须证明stop早于目标guard。',
     'repair': '将3项改为3个场景族并先固定精确阶段/事件回执；B区分未完成Job与ready窗口，A区分持续投递冻结stamp与完全静默，C校验ready→request→stopping→guard的真实顺序。',
     'status': 'plan_revised_in69_no_owned_run_started'},
    {'id': 'R5', 'priority': 2, 'kind': 'scope reporting',
     'title': 'new_ros_graph=0应更正为存在组件ROS上下文/测试publisher',
     'file': str(B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'), 'line': 204,
     'finding': 'SetUpTestSuite调用rclcpp::init，ShadowTestTag构造Node并创建/p1_test/shadow_decision Publisher。没有控制DataWriter、owned=0成立；完全没有ROS图活动不成立。',
     'repair': '新报告分列component_ROS_context_initialized=true、test publisher、localhost/domain121、control_DataWriter=false、owned_runs=0。',
     'status': 'scope_corrected'},
    {'id': 'R6', 'priority': 2, 'kind': 'delivery/preservation',
     'title': '旧mirror校验只遍历目标，且git porcelain不能证明文件内容未变',
     'file': str(B68 / 'scripts/finalize.py'), 'line': 145,
     'evidence': ['evidence/runner_review02/mirror_population_counterexample_v1.json',
                  'evidence/mirror68_review_v1.json'],
     'finding': '漏掉一个应交付源文件时，原目标侧循环仍返回空mismatches。实际当前639项源文件都匹配，另有5项documents副本也匹配，旧回执639尚未表达后加副本。原mut build使用rmtree会覆盖旧构建证据。',
     'repair': '新交付明确排除build、对预期/实际人口双向比较并记录SHA；build/run/报告均create-only。当前69额外固定68全1725文件、67全203文件和21个普通工作区文件内容。',
     'status': 'actual68_mirror_intact_new_delivery_gate_stricter'},
]
create('postrun/review_findings_v1.json', {'schema': 'M4-T1-code-review-v69', 'findings': findings,
    'original25_execution_pass_retained': True, 'original3_mutation_assertions_retained': True,
    'all23_semantic_coverage_signed_off': False, 'original_T2_plan_ready_for_execution': False,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False})

plan = [
    {'id': 'S0', 'status': 'complete', 'task': '修复观测器与runner失败门',
     'evidence': ['evidence/reviewed_t1/attempt01/verification_v1.json',
                  'evidence/verdict_tests/verification_v1.json', 'evidence/event_reader_tests/verification_v1.json'],
     'done': '25/25及3个指定变异通过严格判定，17项Python判定测试和6项精确事件读取测试通过。'},
    {'id': 'S1', 'status': 'next', 'task': 'T1剩余小范围语义补证，保持Regulator源码原样',
     'code_targets': ['new derived tests through P1_REGULATOR_SOURCE',
                      'existing C33MatrixAccess / P1_C36_COMPLETION_TEST seams'],
     'checks': [
       'success=false与solver_invoked=false分别单独刺激并核对当前Job事件及明确拒绝原因；prediction_available=false单独消费门本69已补。',
       '区分Job horizon/dt非法与原生预测结果shape；绑定既有生成端检查或固定尺寸构造性证据，必要时做受控原生结果组件，不要求新owned坏shape实验。',
       '在真实prepare_loop/最终submit路径取得Job提交事实，再插入clear/shutdown，检查真实cancel或禁止提交，而非手工seed_echo代替提交。',
       '对logical Job在途尚未ready的窗口注入reference变化，再提交旧结果并拒绝；新有效task的candidate/slot/activation做正控。',
       '普通new odom后的候选要实际尝试激活，版本拒绝维度按冻结合同列清，避免只核eligible或测试名字。'],
     'done': '更新23项覆盖为已证范围/仍需T2；不因计数25相同即宣称全覆盖。'},
    {'id': 'S2', 'status': 'planned', 'task': '冻结T2动作表及阶段回执的最小接口',
     'code_targets': ['new owned author derived from frozen66, not component-placeholder ELF',
         'fixture/synthetic_source_m4.cpp', 'owned_m4_diagnostic_driver_v1.py',
         'w2_runtime_contract.py', 'Regulator diagnostic-case/parameter admission'],
     'checks': ['create-only动作表固定run/case/合同SHA、有限动作和触发Job/版本/阶段；既有Fixture writer执行，candidate伪造不进Fixture。',
       '当前preflight和Regulator诊断case只认W1/W2/W3/W4，新增T2值须在入口、有效参数、manifest与审计同时消费；normal scope拒绝这些能力。',
       '动作executed回执与Regulator callback/状态变更回执分开；按完整Job/版本/单调时间核对，不用测试flush_pad充当生产ACK。',
       '先离线正反例验证错误case/hash/顺序/多动作/超时/重复回执；不放宽原150ms截止、600ms租约、1s watchdog或关闭预算。'],
     'done': '三个场景族的时序和失败判据成为被代码消费的登记条款，再固定bundle/Driver/ELF/registry/registration和运行库。'},
    {'id': 'T2-A', 'status': 'planned', 'task': 'clock冻结/恢复场景族',
     'checks': ['优先明确持续投递相同clock stamp以保持receipt新鲜，与完全静默超过100ms的clock stale场景分别登记。',
       '原>400ms pause、RTF无效与schedule失效逐事件核对；resume明确sim与odom/imu stamp、名义模型时间的映射。',
       '要求旧候选不复活；若要声称恢复接纳，必须另有新窗口有效性和新Job接受证据。'],
     'done': '发布→真实callback→pause/resume→epoch/schedule→候选处置链闭合；不把clock stale改名成单独pause证明。'},
    {'id': 'T2-B', 'status': 'planned', 'task': '在途Job与ready窗口的clear/replace场景族',
     'checks': ['job_received只证明收到/排队；求解在途触发须确认同一Job已active或进入计算边界，且未生成或发布结果；candidate_received另标ready窗口。',
       '必要时复用已认证有限boundary/release组件，动作和状态ACK后释放；原Job截止绝不延长，错过窗口按登记失败。',
       '区分因旧task被拒与因过期/Worker终端而未产生候选；后者不能冒充前者。',
       'clear与replace若不能在同一登记内独立归因，则拆子case；保留3个场景族，不提前保证恰好3次run。'],
     'done': '每个目标Job有因果窗口、Fixture writer身份、raw输入/变更版本及唯一结果处置。'},
    {'id': 'T2-C', 'status': 'planned', 'task': 'Driver shutdown与ready/activation交错场景族',
     'checks': ['ready确认必须绑定目标Job及真实完成点；先确认当前异步Source文件是否能在窗口内可靠观测。',
       '若文件可见性不足，再加仅诊断的有界ACK/gate；通知可非阻塞，等待不持共享业务锁，normal scope不放行。',
       '独立核对ready_commit < request <= stopping_observed <= activation_guard；不采信最终reason=shutdown就推断交错发生。',
       'API零请求/实际返回/Source flush/Recorder/进程退出各自对账，按登记信号和退出码处理。'],
     'done': '停止请求确实早于目标激活guard，目标未接受，完整退出与存储证据成立。'},
    {'id': 'T3→N3→F6→P1', 'status': 'retained', 'task': '保留主线剩余义务',
     'checks': ['cleanup_failed与旧group未空禁止restart、Source队列压力尚未覆盖；不被T2三场景族替代。',
       '每个实际owned case先预检登记、单次有限执行、自动重试0、失败原件保留。',
       '原九组联合复判后才按原合同推进有限M0/M1模型事务/F6，再P1；不新增C内部永久挂起/duplicate-release/plant前置。'],
     'done': '组件、阶段资格和研究结论分别判定；生产B仍MANUAL＋RC覆写。'}]
create('postrun/revised_next_plan_v1.json', {'schema': 'M4-after-T1-review-minimum-plan-v69',
    'steps': plan, 'stage_qualified': False,
    'three_scenario_families_not_guaranteed_three_runs': True,
    'original_T2_handoff_atoms': 5, 'other_original_wiring_atoms': 18,
    'original_false_claim_other_atoms_19_corrected': True})

now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
initial = read('evidence/inputs_before_v1.json')
preservation = {}
for label, files in [('batch68', initial['batch68_complete_regular_files_including_build']),
                     ('batch67', initial['batch67_complete_regular_files']),
                     ('workspace', initial['workspace_files'])]:
    mismatches = [name for name, expected in files.items()
                  if not Path(name).is_file() or pin(name) != expected]
    preservation[label] = {'files_checked': len(files), 'mismatches': mismatches}
    assert not mismatches, (label, mismatches)
git_status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
assert git_status == initial['git_status_porcelain']
assert runner['identities_unchanged']
build_inventory = {str(path.relative_to(ROOT)): pin(path) for path in sorted((ROOT / 'build').rglob('*')) if path.is_file()}
create('evidence/retained_build_inventory_v1.json', {'files': build_inventory,
    'count': len(build_inventory), 'bytes': sum(row['bytes'] for row in build_inventory.values()),
    'retained_on_USV': True, 'excluded_from_MPC_mirror': True})

evidence_paths = ['evidence/runner_review02/artifact_readback_v1.json',
    'evidence/runner_review02/failure_exit_counterexample_v1.json',
    'evidence/runner_review02/finalizer_exit_counterexample_v1.json',
    'evidence/stale_event_probe/counterexample_v1.json', 'evidence/reviewed_t1/attempt01/verification_v1.json',
    'evidence/verdict_tests/verification_v1.json', 'evidence/event_reader_tests/verification_v1.json',
    'evidence/mirror68_review_v1.json']
create('evidence/review_evidence_pins_v1.json', {relative: pin(ROOT / relative) for relative in evidence_paths})
findings_text = '\n'.join(f"### {item['id']}（P{item['priority']}）{item['title']}\n\n"
    + f"位置：{link(item['file'], line=item['line'])}。\n\n{item['finding']}\n\n"
    + item['repair'] + '\n' for item in findings)
plan_text = '\n'.join(f"### {item['id']} {item['task']}\n\n"
    + ('\n'.join('- ' + line for line in item.get('checks', [])) + '\n\n' if item.get('checks') else '')
    + '**完成条件：**' + item['done'] + '\n' for item in plan)
report = f'''# 方案A：第68批代码复核、第69批验证修正与后续计划

日期：2026-10-24（北京时间），记录时间：{now}。

## 1. 审查结论

第68批确实推进了当前Regulator回调/准入验证：原run06的25项均无失败，三个指定变异也确由对应GTest断言捕获；flush_pad已写入真实8200字节字符串。**目前证据不足以支持“23项语义全部闭合、下一步直接跑原三例T2”。** 本批找到了可复现的事件读取假阳性与失败退出码漏洞，并将验证器修正落在新69副本，没有回写68原件或67冻结源码。

新69副本修复后25/25通过、三个指定变异仍捕获，17项判定器测试和6项事件读取测试通过。第66批W2、67批已有证据均保留；完整M4/F6/P1、plant/硬实时与研究结论继续false。

## 2. flush_pad是否真正落地

核对最终源码{link(B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp', line=129)}与run06的25个最终Source文件：发现**36条pad事件，每条filler都是8200字节字符串**，不是`filler.size()`整数。本机该版本ofstream实现下，它促进了前序行写出；最终Source summary无drop，原假填充问题已修正。

但DiagSink::add只是入异步队列，pad不是队列drain/flush完成ACK；C++标准也没有固定“所有平台都8KB缓冲”的协议保证。读者还必须确认本次事件身份和实际完成时间。36条pad的逐case证据在{link('evidence/runner_review02/artifact_readback_v1.json')}。保持测试pad为测试手段，不能把它当作T2生产回执通道。

## 3. 主要问题与已落地修正

{findings_text}

### R2的实际C++反例

在69私有harness里只省掉new-version Job2的`candidate()`调用，保留原Regulator源码和原测试的每条断言。原`ReferenceReplaceDuringSolve`仍RC0、1/1通过，完整Source注册Job集合却只有`[1]`。这个反例证明测试可能从旧Job1读出成功，原先“有事件、pad也在”的观察不足以证明新Job2调用发生。

反例程序是故意破坏测试harness，不是声称生产Regulator漏调用；旧68原件未改。原反例Source、命令、ELF hash与输出见{link('evidence/stale_event_probe/counterexample_v1.json')}。

### R1的实际控制流反例

在私有输出目录重放原runner main，使用原run06数据且只让M1找不到模式，原main仍返回0并留下`applied=false`。另以私有finalizer输入把all_passed置false，stdout为all_green=false，main正常返回None；原入口无SystemExit，脚本仍正常退出。这里构建/执行用受控stub，只证明真实Python控制流，不冒充又一次ROS失败run。

## 4. 本批实际改了哪些文件

| 新69文件 | 作用 |
| --- | --- |
| `implementation/runner_verdict_v2.py` | baseline、mutation和完整attempt共享严格判定；检查完整人口、failures、RUN/COMPLETED、跳过、错误、RC及精确命名断言 |
| `implementation/run_reviewed_t1.py` | create-only attempt/run/build/报告；变异失败纳入退出码；错误仍保存报告；CMAKE_HOME_DIRECTORY、源码前后pin与ELF/命令记录 |
| `implementation/reviewed_harness/tests/test_current_candidate_reference_clock.cpp` | 读取精确type、完整Job与本次调用时间；200ms有限等候；新增Job恢复状态断言及available=false单独拒绝门 |
| `implementation/test_runner_verdict_v2.py` | 17项判定测试，包括原实际正控及RUN+failure、skip、缺项、崩溃、RC0假捕获、空/未prepared变异等反例 |
| `implementation/verify_event_reader.py` | 从新helper逐字提取代码，6项纯C++测试拒绝旧Job/旧调用/错任务/错type，接受当前事件 |
| `implementation/audit_and_probe_runner.py` | 原25项/3变异及36条pad读回，runner/finalizer/mirror的私有反例 |
| `implementation/probe_stale_event.py` | 真实C++“省掉新Job2仍通过”的反例 |
| `implementation/audit_mirror68.py` | 双向检查旧交付人口与5项documents派生副本 |

所有测试/runner变化在69派生副本。原Regulator源码SHA仍是`dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5`。原68的`5ff64a08…`是其明确定义的“相对路径逐文件行”聚合hash，与66 JSON bundle文件SHA的算法/编码不同，不能按字符串不同误判源被篡改。

## 5. 验证结果及准确边界

| 项 | 结果 | 范围 |
| --- | --- | --- |
| 原68实际run06 | 25/25，三个原变异真实断言捕获 | 保留原执行事实；不自动授予全部语义覆盖 |
| 旧helper假阳性反例 | 省Job2后1/1仍通过，Source无Job2 | 证明测试观测缺陷 |
| 原runner/finalizer反例 | 未prepared仍RC0；all_green=false仍正常返回 | 真实控制流、受控执行stub，无ROS |
| 新69完整组件 | 25/25＋3指定变异，全部严格通过 | 同一个新harness、同冻结Regulator源码 |
| 判定器 | 17/17 | 完整人口、失败/异常/变异/身份gate |
| 精确事件读取 | 6/6 | 提取同一C++helper，不初始化ROS |
| 原68MPC当前副本 | 639项源文件均匹配，额外5项documents副本匹配 | 当前Linux共享盘核对；旧回执计数未包含后加副本 |

新完整组件执行使用localhost、DDS domain121和独立ROS_LOG_DIR。它会初始化rclcpp并创建`/p1_test/shadow_decision`，没有控制DataWriter，未启动四角色owned。共四个新完整组件进程及一个C++反例进程；不把这些说成“零ROS活动”。17项Python及6项读取测试自身不初始化ROS。

结果入口：{link('evidence/reviewed_t1/attempt01/verification_v1.json')}、{link('evidence/verdict_tests/verification_v1.json')}、{link('evidence/event_reader_tests/verification_v1.json')}。私有probe第一次漏放init_inputs产生FileNotFoundError，已经保留在`evidence/runner_review/`；它是审查工具准备错误，不计为68被正确拒绝的证据，第二次才是有效反例。

## 6. 覆盖结论应怎样更新

将旧“23/23全闭合”改为“当前harness25项执行通过；指定回调/消费路径已取得证据，真实提交、在途阶段及生成端shape范围仍按下列小清单补证”。已有候选拒绝、参考指纹、clock epoch、HOLD/调度等正反例保留，不重跑全部历史，也不推翻W2通过。

`CandidateFailedSolverNotInvoked`一次同时把三个标志置false，不能分辨删除success或invoked检查；新69已额外核available=false单独拒绝，success/invoked仍应各自隔离。`CandidateInvalidShapeAndUnavailable`原来只改horizon/dt，应该标为Job shape/time metadata拒绝，不能改称原生X/U维度分支已执行。`ReferenceReplaceDuringSolve`实际处于ready窗口；`CommittedSubmitClearInvalidates`没有真实prepare_loop提交证据。把这些明确列清，下一步就是有限补证，不是再泛化为新研究门槛。

旧T2列出的跨进程atom是2个clock＋2个reference＋1个shutdown＝5项，23−5＝18；“其余19项”是计数错误。本批计划修正该数字，同时保留未满足的具体语义，不按名字一概移出owned范围。

## 7. 修订后的继续顺序与代码实施计划

{plan_text}

机器可读计划：{link('postrun/revised_next_plan_v1.json')}。S1完成后再冻结T2动作接口与场景登记；本批没有执行T2实际owned，不将组件RTF样本或合成anchor当作硬实时/plant证明。

## 8. 保存、工作区与交付

原68包含build的1725个普通文件（881,081,591字节）、67全203项、当前21个普通已改/未跟踪工作区文件已固定并复核无变化，git porcelain一致。该证明从本次接手时开始，不补造68执行前未记录的普通文件历史hash；不声称扫描了ardurover子模块全部内容。原68失败证据、五轮及后续attempt/run均未删除或覆盖。

原68MPC少了整个build是已声明交付选择，不按6.5MB或14MB的大小判资格，也不存在“67未命名build目录，所以所有批次一律排除构建产物”的通用惯例。本批69的build原件及逐文件SHA保留在USV，MPC明确排除build；执行ELF身份、重建命令、日志和输入代码保留可审查入口。

新69文件交付至`/home/trevor/MPC/{ROOT.name}`，以新增交付库存与完整人口回读回执为准，旧68副本保持。Windows `Documents\\MPC` 不在当前Linux可访问范围，本批只核实Linux/MPC共享盘，不声称修复或再次同步了Windows本地目录。

最终保护和分层结论见{link('evidence/final_verification_v1.json')}；build库存见{link('evidence/retained_build_inventory_v1.json')}。
'''
create('documents/' + REPORT, report)
create('documents/下一步实施计划_T1有限补证与T2三场景族_2026-10-24.md',
       '# T1有限补证与T2三场景族计划\n\n日期：2026-10-24。第68批原件保留，按第69批复核实施。\n\n'
       + plan_text + '\n完整M4/F6/P1/plant/硬实时仍false；实船B仍MANUAL＋RC覆写。\n')
final = {'schema': 'M4-T1-code-review-final-verification-v69', 'checked_at': now,
    'preservation': preservation, 'git_status_unchanged': True,
    'original68_25_pass_retained': True, 'original68_3_mutations_retained': True,
    'flush_pad_real_strings': len(original['flush_pad']),
    'stale_event_real_CPP_counterexample_confirmed': True,
    'runner_failure_exit_counterexample_confirmed': True,
    'reviewed25_and3_mutations_passed': True, 'verdict_tests': 17, 'event_reader_tests': 6,
    'all23_semantic_coverage_signed_off': False,
    'component_ROS_initialized': True, 'new_owned_runs': 0, 'actuator_DataWriter_created': False,
    'T2_plan_revised_not_executed': True, 'report': str(ROOT / 'documents' / REPORT),
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance': False, 'hard_realtime': False, 'research_conclusion': False}
create('evidence/final_verification_v1.json', final)
create('CURRENT.md', f'''# 第69批：第68批T1审查与验证器修正

日期：2026-10-24；更新：{now}。

- 原68的25/25及三个变异真实通过，36条pad为真实8200字节字符串，结论保留。
- 找到真实C++反例：省掉new-version Job2调用仍通过，原Source只有Job1；旧事件助手会读旧成功。
- 原runner未prepared仍RC0，原finalizer all_green=false仍正常返回；新派生runner严格失败门已落地。
- 新69的同一修正harness25/25＋3变异通过；17项Python判定及6项C++事件读取通过。
- 23项语义不能全按用例名字闭合：真实submit、in-flight与结果shape等边界仍需小范围补证。
- 修订T2为三个场景族；candidate_received不得冒充求解在途；pause与receipt stale分清，shutdown先验证真实时序ACK。
- 本批有组件ROS context/test decision publisher；无控制DataWriter、owned=0；生产B仍MANUAL＋RC覆写。
- 68全1725文件、67全203文件、21个普通工作区文件及git状态保持；失败证据不覆盖。
- 下步：S1有限语义补证→T2动作接口/预检登记→最小owned→T3→M4复判→F6→P1。

主报告：{link('documents/' + REPORT)}。
发现：{link('postrun/review_findings_v1.json')}。
下一步：{link('postrun/revised_next_plan_v1.json')}。
完整M4/F6/P1/plant/硬实时/研究结论仍false，第66批W2保留。
''')
missing = []
count = 0
for path in [ROOT / 'CURRENT.md', ROOT / 'documents' / REPORT]:
    for target in re.findall(r'\]\((/[^)]+)\)', path.read_text()):
        file = target.rsplit(':', 1)[0] if re.search(r':\d+$', target) else target
        count += 1
        if not Path(file).exists():
            missing.append(target)
assert not missing, missing
create('evidence/document_links_v1.json', {'checked': count, 'missing': missing})
print(json.dumps({'review_completed': True, 'new69_25_and3_passed': True,
    'semantic_23_signoff': False, 'findings': len(findings), 'preservation': preservation,
    'report': str(ROOT / 'documents' / REPORT)}, ensure_ascii=False))
