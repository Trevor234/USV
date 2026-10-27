#!/usr/bin/env python3
"""Summarize completed N1 and the deterministic part of N2, preserving inputs."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
AUTHOR = ROOT / 'implementation/current_author'
REPORT = '方案A_第67批原M4逐项适用性_Fixture差集与后续实施_2026-10-24.md'


def read(relative):
    return json.loads((ROOT / relative).read_text())


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def create(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(value, (dict, list)) else value)


def link(relative, label=None):
    path = Path(relative)
    if not path.is_absolute():
        path = ROOT / path
    return f'[{label or path.name}]({path})'


catalog = read('postrun/case_applicability_v1.json')
core = read('evidence/core_components_attempt02/verification_v1.json')
policy = read('evidence/policy92_replay/verification_v1.json')
reaudit = read('evidence/historical_reaudit/verification_v1.json')
source = read('evidence/source_applicability_v1.json')
f5 = read('evidence/F5_fixture_applicability_v1.json')
structure = read('evidence/catalog_verification_v1.json')
assert core['complete'] and policy['passed'] and reaudit['complete'] and structure['complete']

backlog = []
for task_id, title, ids, files, implementation, done in [
    ('T1', '当前Regulator候选/参考/时钟接线组件',
     [row['id'] for row in catalog['cases'] if row['status'] == 'needs_wiring_validation'],
     ['new tests/test_current_candidate_reference_clock.cpp',
      'existing observer/src/shadow/regulator_owned_execute.cpp through P1_REGULATOR_SOURCE',
      'existing C33MatrixAccess/ShadowTestTag test seam'],
     ['新测试使用现成friend/测试构造器驱动真实candidate/path/profile/clock/activate/submit代码，不复制准入算法。',
      '候选8类、参考7类、时钟6类、发布退出2类逐项映射到23项缺口；再补250/400ms delayed tick外壳组合。',
      '明确种入readiness/lease/ticket前提，禁止把该组件说成新四角色owned资格；不创建控制DataWriter。',
      '断言ready/committed/pending无旧身份复活、每候选最多一次、截止不续期、明确拒绝原因。'],
     '所有23项都有实际调用及正反例结果；未覆盖的跨进程部分精确移交T2，不由测试名代替路径。'),
    ('T2', 'Fixture最小有限刺激接口与必要owned差集', [],
     ['new derived fixture/synthetic_source_m4.cpp', 'new diagnostic schedule validator/header',
      'new Driver case/registration and independent raw audit'],
     ['仅为T1仍须跨进程核验的输入交错增加create-only固定动作表，普通.05默认行为保持。',
      '由原Fixture已有path/profile/odom/imu/clock writer执行clear/replace或时钟刺激；禁止另造外来writer绕过GID/owner认证。',
      '动作表固定case/run/文件hash、有限步数/数值/持续预算和触发事件；Source记录计划、实际触发和拒绝原因。',
      'Candidate伪造不交给Fixture；在已声明诊断Worker或源链接callback组件中验证。',
      '代码变化后重新bundle→Driver SHA→真实ELF→registry/registration→共享预检；逐case有限运行、自动重试0。'],
     '只执行已经由T1证明需要owned的最小case清单；每次独立Source/Stored/API/退出对账，不预定九组各一次长run。'),
    ('T3', '队列压力与cleanup_failed监督消费路径',
     [row['id'] for row in catalog['cases'] if row['status'] == 'uncovered_current_path'],
     ['current p1_diag_sink.hpp actual enqueue/drain path', 'current Driver wait_close/final cleanup consumer'],
     ['队列压力沿真实enqueue/drain路径有界注入；逐类generated/emitted/dropped/Stored及正常资格标志对账。',
      'cleanup_failed通过有界监督组件故障注入覆盖实际消费分支；记录请求/API/进程组事实，证明失败后没有新spawn。',
      '使用真实进程关闭作正控，并诚实标记失败刺激是监督组件注入；不制造不可杀进程或留下孤儿。',
      '自动重试0和历史清理成功不当作cleanup_failed分支已通过。'],
     '三项当前未覆盖义务取得对应层级正反例；需要owned的压力子项先固定例外与差额判据再执行。'),
]:
    backlog.append({'id': task_id, 'title': title, 'gap_atom_ids': ids,
                    'code_targets': files, 'implementation': implementation, 'done_when': done})
backlog.extend([
    {'id': 'N3', 'title': '原九组联合复判',
     'done_when': '原18条、69项按证据层次与来源适用性逐项完成；不能以150个测试或43个复用项自动授予M4。'},
    {'id': 'N4', 'title': '有限M0/M1模型事务/F6',
     'done_when': 'M4满足原前置后，依原NX8/NU2/N20/NP6/NP_GLOBAL30数值setter路径验证prepare/原子提交/固定tick激活/旧或mixed候选拒绝/独立warm-start，不codegen、不接GP/PPO。'},
    {'id': 'N5', 'title': 'P1联合验收',
     'done_when': '依原P1冻结合同联合检查，API/进程退出/plant接受/硬实时分别判定。'},
])
create('postrun/next_implementation_plan_v1.json', {
    'schema': 'scheme-A-after-case-inventory-minimum-gap-plan-v67',
    'major_order_fixed': ['W2 complete', 'Fixture difference and minimum gap', 'M4 reassess', 'F6', 'P1'],
    'component_before_new_owned': True, 'steps': backlog,
    'no_new_prerequisite_C_internal_hang_or_duplicate_release': True,
    'current_owned_run_count': 0,
    'baseline_constraints': {'T_ns': 200000000, 'deadline_ns': 150000000,
        'lease_ns': 600000000, 'active_watchdog_ns': 1000000000,
        'automatic_retries': 0, 'B_real_mode': 'MANUAL + RC override'},
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False})

initial = read('evidence/inputs_before_v1.json')
checks = {}
for label, files in [('previous66', initial['previous_batch_full_regular_file_population']),
                     ('workspace', initial['workspace_files']),
                     ('source_audit', read('evidence/source_audit_inputs_v1.json')['files']),
                     ('F5_fixture', read('evidence/F5_fixture_inputs_v1.json')['files']),
                     ('historical_raw', read('evidence/historical_reaudit/inputs_before_v1.json')['files']),
                     ('catalog', read('evidence/case_catalog_inputs_v1.json')['files']),
                     ('core', core['inputs_before'])]:
    mismatches = [name for name, expected in files.items()
                  if not Path(name).is_file() or pin(name) != expected]
    checks[label] = {'files_checked': len(files), 'mismatches': mismatches}
    assert not mismatches, (label, mismatches)
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'],
                                 cwd=REPO, text=True)
assert status == initial['status_porcelain'], 'workspace status changed; preserve and label'
current_bundle = json.loads((ROOT.parent / 'scheme_A_W2_owned_takeover_20261023_66/evidence/freeze_and_build/source_bundle.json').read_text())
assert set(current_bundle['files']) == {str(p.relative_to(AUTHOR)) for p in AUTHOR.rglob('*') if p.is_file()}
assert all(pin(AUTHOR / relative) == {key: row[key] for key in ('bytes', 'sha256')}
           for relative, row in current_bundle['files'].items())

now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
status_counts = catalog['status_counts']
summary_rows = '\n'.join(f"| `{group['id']}` | {group['case_atoms']} | "
    + '、'.join(catalog['status_labels'][key] + str(value) for key, value in group['status_counts'].items())
    + ' |' for group in catalog['groups'])
mutations = '\n'.join(f"| `{name}` | {', '.join(row['failing_tests'])} |"
                      for name, row in core['mutations'].items())
plan_text = '\n'.join(f"### {step['id']} {step['title']}\n\n"
    + ('\n'.join('- ' + item for item in step.get('implementation', [])) + '\n\n'
       if step.get('implementation') else '')
    + '**完成条件：**' + step['done_when'] + '\n' for step in backlog)
report = f'''# 方案A第67批：原M4逐项适用性、Fixture差集与后续实施

日期：2026-10-24（北京时间）。整理时间：{now}。

## 1. 本批已推进到哪里

已完成第66批计划N1，并实施N2中必要的确定性组件部分。原9组18条required_cases全部逐字绑定，拆为69个具名核对项：**可复用组件{status_counts['reusable_component']}项、可复用owned子项{status_counts['reusable_owned_subitem']}项、需补当前接线{status_counts['needs_wiring_validation']}项、当前路径未覆盖{status_counts['uncovered_current_path']}项**。这是证据处置清单，不是覆盖率百分比或阶段通过率。

当前头文件的原92项策略重放全部通过；另外58项确定性组件测试全部通过，其中7项补齐明确毫秒/纳秒时序要求；3个定向代码变异均由GTest断言捕获。W1/W3/W4三个旧实际run的Source/Stored离线重审也全部通过，26个适用反例被拒绝。本批没有新增ROS图、owned run或硬件动作。

第66批W2成功结论保留。完整M4/F6/P1、plant接受、硬实时及研究结论仍false。生产B保持MANUAL＋RC覆写，主工作区未提交文件和并行改动保留。

## 2. 逐case清单与原要求的关系

原47矩阵原件不变：{link(catalog['matrix']['path'])}。完整清单含原条款、子项、证据代号/路径/SHA、已证范围和具体差额，见{link('postrun/case_applicability_v1.md')}及{link('postrun/case_applicability_v1.json')}。

| 原组 | 核对项数 | 证据处置 |
| --- | --- | --- |
{summary_rows}

清单结构审计正控通过，缺条款、弱化原文、重复人口、空证据、伪pin、偷升阶段、删除范围、缺口无下一步共8个变异均由断言拒绝。结构审计不能自动证明语义充分性，见{link('evidence/catalog_verification_v1.json')}。

原矩阵之外的C内部永久挂起、重复release协议、连续多次投递丢弃、plant/硬件资格均不新增为本轮必经前置。原矩阵内的queue pressure和cleanup_failed仍明确保留。

## 3. 哪些源码能复用，哪些不能按文件名推断

新建`implementation/current_author`为第66批100项源码的逐字节私有副本，用于读审和组件编译；它没有新的owned执行登记。相对49/53/56，当前分别有70/70/77项同名文件完全相同。Regulator的prepare_loop、candidate、activate_candidate、predict、odom、imu、path、profile、clock、snapshot及Source capture等18个明确方法与49/53保持字节相同；与56还有tick_loop等20个方法相同。未找到的函数不计入相同项。

输出策略类`OutputAuthority`与原47完全相同，5291字节、SHA `512392b6e0da176feaf4e4b101fbcbab14cf36c63da95a7757e4fcd99c4a2128`；Admission核心也相同。类外context_gate已有诊断profile与FastDDS原生32hex GID变化，本批明确对该差异做重放，没有假称全文件相同。

Worker的整个work()有W2边界/事实计数/终端异常差异，不能整段自动转移。但56到66的两个具体正常路径片段完全相同：

| 片段 | 字节 | SHA |
| --- | --- | --- |
| 原生结果映射到候选、delay/drop/publish | 3451 | `bf6b57574d985bed4e581f630db9174f6d1dfe8b754714e3b3dac697ff9001d5` |
| completed/active与数值失败收尾 | 807 | `855416c6c07cd651b59af2319ca294f738efdcfa273a836e6ae4a0f7dc983b17` |

当前无W2 fd时入口校验按默认值返回、Boundary不构造、不等待；新增RawBackend marker是C调用事实记录。W2专用final guard由attach_boundary安装；不能把有arm分支的约束错误套到未arm的W3/W4。完整差量和可定位范围见{link('evidence/source_applicability_v1.json')}及`evidence/source_deltas/`。

## 4. F5来源、参考、映射与logging适用性

原F5第二次pilot自身检查通过。其名义19个水动力值、共享核心输入及±25N边界已逐项绑定；nominal文件SHA仍是`78d7133fd4f11d47bd534d820b02489e440bd8664bef254893e830fe4bc7dc84`。19项明细在{link('evidence/F5_fixture_applicability_v1.json')}。

原M1的F5 backup、core header/source、model header/source、utils header/source及公共fixture现在仍匹配原oracle清单。原9项数学等价GTest、600组参考fixture及带/不带metadata调用可以在原范围复用。当前legacy `mpc_node.cpp`整文件与旧M1记录不同，这个事实已显式记录；既有并行修改未回滚，未宣称整wrapper相同。

原F5日志开关的3项相关回归具有冻结source hash、XML hash和7.7MB测试ELF对应关系，ELF SHA仍为`4717abb34ee50f39956365b35acd41a75e818917709465b5d60df426ad7f95f8`。它们是原同步F5输入/参考/命令的off/on组件回归。当前M4 Source/Witness是必需记录，不应关闭新owned记录来重复旧开关测试。

当前Fixture来源是已认证owned Applied驱动的名义RK4点模型，.05m/s直线、201点、dt .2s，sensor 50Hz，每25拍重发参考，sim=100s+steady elapsed。原F5使用VRX/plant传感来源；**名义数值/core数学对应，不等于原plant/reference全域同一性**。本阶段把该映射和范围说清，保留隔离工程组件资格；不把上船、plant等价或1.2m/s扩域变成额外前置。

## 5. 本次实际执行的组件验证

### 5.1 原92项策略用当前头文件重放

使用原entry_probe_v2，仅将include指向当前`owned_execution_policy_native_v1.hpp`；请求中原48hex GID显式换为当前原生32hex，接受/拒绝和全部策略期望保持。92/92通过，包含HOLD等号/之后、五次miss、invalid绕过HOLD、unknown、逐侧实际间隔、partial、shutdown、gap/span/jitter和上下文拒绝。

该程序不初始化ROS，不链接ROS/acados，不创建执行端点。其API时间/结果为合成输入，不能写成一次实际owned故障。结果：{link('evidence/policy92_replay/verification_v1.json')}。

### 5.2 当前确定性核心58项与3变异

复用现有`test_p1_admission`、lease、tick barrier测试，编译当前冻结Admission/ClockWindow等头文件，以及实际p1_input_core.cpp、utils.cpp和同源模型。58/58通过。新7项分别为ready50ms、150ms等号、150ms+1ns、250ms、400ms、篡改deadline、篡改target；不会将这些合成ready时刻说成solver实测耗时。

| 变异 | 捕获它的真实失败用例 |
| --- | --- |
{mutations}

首轮构建缺少p1_input_core.cpp与utils.cpp链接，保留在`evidence/core_components/`；修正只补两个实际源，第二轮在新目录`core_components_attempt02`构建并通过，未覆盖失败证据。当前生产源文件只读。

老InputCore测试中GUIDED只是显式allowed_modes合成输入，验证通用资格优先级；没有据此改变实船模式契约。当前真实B仍MANUAL＋RC覆写。

结果及每个失败断言：{link('evidence/core_components_attempt02/verification_v1.json')}。

## 6. 旧实际W1/W3/W4离线重审

调用已硬化审计代码，仅读原`runs/W1_05`、`W3_05`、`W4_05`的Source、manifest、ELF/bundle、原登记、capability与Stored；所有输出重定向到第67批。未启动ROS或重新运行旧角色，没有写56原目录。

| case | 原run | 本次离线结果 | 断言反例 |
| --- | --- | --- | --- |
| W1 | M4_diagnostic_W1_20261022_05 | 通过；active_watchdog时租约仍有效 | 9 |
| W3 | M4_diagnostic_W3_20261022_05 | 通过；迟到拒绝，未失活 | 8 |
| W4 | M4_diagnostic_W4_20261022_05 | 通过；Job3被记账丢弃，目标tick降级后恢复 | 9 |

这些是原已登记case的重新核验，并结合前节字节相同范围支持投递/完成层复用；没有给第66批二进制补写一个未执行的W3/W4 run。旧`_01`及superseded继续保留。结果：{link('evidence/historical_reaudit/verification_v1.json')}。

## 7. 真实差集与代码入口

**23项需补当前接线：** candidate失败/shape/NaN/重复/旧乱序/foreign身份共8项；reference clear/single/replace/重发/不匹配/new odom共7项；clock pause/resume/reset/jump/RTF共6项；已提交任务后的clear/shutdown及activation交错2项。旧底层组件不能替代这些当前组合路径。

**3项当前未覆盖：** cleanup_failed正确失败、旧group未空禁止restart、log queue pressure。第66批清理成功和自动重试0不能替代这三项。

当前Fixture构造器只放行固定C/.05参数，publish_step稳定发五种输入，**没有登记故障动作表**。因此后续必须在已有writer里增加有限刺激接口，不能另开外来Publisher绕过owner/GID认证；Candidate变异应在诊断Worker或真实callback组件中验证。clock刺激还应说明名义模型与sim epoch关系，不在reset后无证据声称恢复有效。

不把26项缺口机械变成26次新ROS运行。先用当前真实Regulator源链接组件把组合义务做完，剩余确需跨进程的部分才注册最小owned case。下一步实施入口、约束和完成条件如下。

{plan_text}

机器可读顺序：{link('postrun/next_implementation_plan_v1.json')}。完整M4复判要联合原条款和证据层次，不能以测试数150或可复用数43自动通过。

## 8. 本批修改文件及保护

本批新增脚本：`init_inputs.py`固定886项66原件及21个普通工作区文件；`audit_sources.py`比较指定方法/片段并认证旧身份；`audit_fixture_and_F5.py`绑定F5；`replay_policy92.py`重放原策略期望；`replay_core_components.py`与`test_deadline_matrix.cpp`完成当前确定性组件；`reaudit_historical.py/.sh`重审旧原始记录；`build_case_catalog.py`生成69项清单；`validate_catalog.py`验证结构及8反例；本收尾及交付脚本保存状态。

100项current_author只是第66批的字节副本，未修改已有源码。当前无新owned registry/registration或可执行来源资格。所有临时变异位于独立组件目录。

最终按范围核对：66全886普通文件、源码审计381项、F5绑定输入、三个旧run原始人口、组件编译输入及21个普通工作区文件均未变化，git porcelain与接手相同。该保护不声称扫描了所有历史目录/子模块内容。详见{link('evidence/final_verification_v1.json')}。

完整新包镜像至`/home/trevor/MPC/{ROOT.name}`，以最终交付回执和逐文件回读为准；不覆盖66或任何旧交付。实际owned来源仍是第66批已登记路径，MPC镜像是交付副本。
'''
create('documents/' + REPORT, report)
verification = {
    'schema': 'M4-case-applicability-final-verification-v67', 'checked_at': now,
    'preservation': checks, 'git_status_unchanged': True,
    'current_author_exact_population': 100, 'current_author_identical_to66': True,
    'N1_inventory_complete': True, 'N2_deterministic_component_slice_complete': True,
    'original_groups': 9, 'original_clauses': 18, 'case_atoms': catalog['atom_count'],
    'case_status_counts': status_counts,
    'new_policy_cases_passed': 92, 'new_core_GTests_passed': 58,
    'new_deadline_cases': 7, 'code_mutations_caught': 3,
    'catalog_mutations_assertion_rejected': 8,
    'historical_diagnostic_raw_reaudits_passed': 3,
    'new_ROS_graphs_or_owned_runs': 0,
    'production_source_edited': False, 'original66_W2_qualified_retained': True,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance': False, 'hard_realtime': False, 'research_conclusion': False,
    'next': 'T1 current-source candidate/reference/clock/shutdown wiring component',
    'report': str(ROOT / 'documents' / REPORT)}
create('evidence/final_verification_v1.json', verification)
(ROOT / 'CURRENT.md').write_text(f'''# 第67批：N1逐项适用性完成，进入最小接线差集

日期：2026-10-24（北京时间）；更新：{now}。

- 原9组18条全部映射为69项：30组件复用、13 owned子项复用、23需补当前接线、3当前未覆盖。不是阶段通过率。
- 当前头文件原92项策略重放通过；当前核心58项GTest通过（新增7项明确时序）；3代码变异全部断言捕获。
- 原W1/W3/W4_05完整Source/Stored离线重审通过，26反例拒绝；没有重新跑旧角色。
- F5名义hydro19相同，原同源数学9项/日志开关3项的身份链保留；当前来源.05 nominal，不转移plant资格。
- 新100项作者副本保持66原字节；本批未新增ROS图/owned/硬件，未改生产源。
- 保护：66全886普通文件、选定历史审计输入、21个普通工作区文件及git状态一致；首轮链接失败原件保留。
- 下一步T1：真实当前candidate/path/profile/clock/submit/activate接线组件；随后最小Fixture刺激、压力/清理失败路径、M4联合复判、F6、P1。
- 第66批W2子项资格保留。完整M4/F6/P1/plant/硬实时/研究结论仍false。生产B仍MANUAL＋RC覆写。

主报告：{link('documents/' + REPORT)}。
逐项清单：{link('postrun/case_applicability_v1.md')}。
下一步：{link('postrun/next_implementation_plan_v1.json')}。
验证与保护：{link('evidence/final_verification_v1.json')}。
''')
links = []
for path in [ROOT / 'CURRENT.md', ROOT / 'documents' / REPORT, ROOT / 'postrun/case_applicability_v1.md']:
    for target in re.findall(r'\]\((/[^)]+)\)', path.read_text()):
        assert Path(target).exists(), (path, target)
        links.append(target)
create('evidence/document_links_v1.json', {'checked': len(links), 'missing': []})
print(json.dumps({key: verification[key] for key in ('N1_inventory_complete',
    'case_atoms', 'case_status_counts', 'new_policy_cases_passed', 'new_core_GTests_passed',
    'historical_diagnostic_raw_reaudits_passed', 'new_ROS_graphs_or_owned_runs')}, ensure_ascii=False))
