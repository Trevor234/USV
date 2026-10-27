#!/usr/bin/env python3
"""Give every original M4 clause an explicit evidence/disposition entry."""
from pathlib import Path
from collections import Counter
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
AUTHOR = ROOT / 'implementation/current_author'
MATRIX = BASE / 'scheme_A_formal_execute_profile_20261020_47/freeze/M4_fault_matrix_v1.json'
READS = {}


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    READS[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return READS[str(path)]


def read(path):
    pin(path)
    return json.loads(Path(path).read_text())


def create(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(value, (dict, list)) else value)


matrix = read(MATRIX)
historical = read(ROOT / 'evidence/historical_evidence_catalog_v1.json')['evidence']
evidence = {key: {'path': row['path'], **pin(row['path'])} for key, row in historical.items()}
for key, relative in {
    'source_ranges': 'evidence/source_applicability_v1.json',
    'F5_mapping': 'evidence/F5_fixture_applicability_v1.json',
    'current_policy92': 'evidence/policy92_replay/verification_v1.json',
    'current_core58': 'evidence/core_components_attempt02/verification_v1.json',
    'historical_identity': 'evidence/historical_case_identity_v1.json',
    'historical_raw_reaudit': 'evidence/historical_reaudit/verification_v1.json',
}.items():
    evidence[key] = {'path': str(ROOT / relative), **pin(ROOT / relative)}
core = read(ROOT / 'evidence/core_components_attempt02/verification_v1.json')
policy = read(ROOT / 'evidence/policy92_replay/verification_v1.json')
reaudit = read(ROOT / 'evidence/historical_reaudit/verification_v1.json')
assert core['complete'] and policy['passed'] and reaudit['complete']
test_names = {row['suite'] + '.' + row['name'] for row in core['baseline']['cases']}
policy_names = {row['name'] for row in policy['cases']}

C = 'reusable_component'
O = 'reusable_owned_subitem'
W = 'needs_wiring_validation'
U = 'uncovered_current_path'
labels = {C: '可复用组件', O: '可复用owned子项', W: '需补接线验证', U: '当前路径未覆盖'}
rows = []


def add(group, clause, label, status, refs, proven, remaining='', tests=(), policies=()):
    assert status in labels and all(key in evidence for key in refs)
    assert all(name in test_names for name in tests), tests
    assert all(name in policy_names for name in policies), policies
    rows.append({'id': f'{group}.{sum(row["group"] == group for row in rows) + 1:02d}',
        'group': group, 'original_clause_index': clause, 'case': label,
        'status': status, 'status_label': labels[status], 'evidence_keys': list(refs),
        'proven_scope': proven, 'remaining_current_path_obligation': remaining,
        'current_GTest_cases': list(tests), 'current_policy_cases': list(policies),
        'source_range_evidence': 'source_ranges', 'whole_stage_qualification_implied': False})


g = 'compatibility_input'
for name in ['F5输入资格/数值准入核心', 'F5参考构造与全部metadata', 'F5输入映射/scale/clamp', '原F5 logging off/on回归']:
    add(g, 0, name, C, ['F5_mapping', 'current_core58'],
        '原F5冻结源码/XML/ELF可对应，9项同源oracle与当前7项数学源码匹配；3项日志开关原回归保留。',
        '不声称当前legacy wrapper整文件相同，不关闭M4强制Source/Witness来冒充旧logging测试。')
add(g, 1, '新target-reference独立fixture及共享数学核心', C,
    ['F5_mapping', '49_components', 'current_core58', 'source_ranges'],
    '目标参考独立解析/预测组件与共享构造器，名义hydro19及nominal hash完全相同。',
    '来源明确为.05 nominal RK4，原F5 VRX/plant/reference整体同一性不转移。',
    tests=['InputCore.TargetReferenceIsRebuiltFromPredictedNearestPoint'])
add(g, 1, '输入与输出owner分离，无隐藏输出writer', O, ['66_W2', '49_normal'],
    '已运行四角色身份/端点与Stored对账；Fixture无左右控制writer。')

g = 'time_boundaries'
for name, test in [('ready50ms', 'Ready50msKeepsOriginal200msTarget'),
                   ('ready150ms等号', 'Ready150msEqualityIsAllowed'),
                   ('ready150ms+1ns', 'Ready150msPlusOneNanosecondIsLate'),
                   ('ready250ms', 'Ready250msIsNotRescheduled'),
                   ('ready400ms', 'Ready400msIsNotRescheduled')]:
    add(g, 0, name, C, ['current_core58'], '实际Admission头文件的确定性注册/消费，保留原150ms截止及200ms目标。',
        '这些是合成ready时刻，不改称实际native solve持续了对应毫秒数。',
        tests=['DeadlineMatrix.' + test])
add(g, 0, '完整注册完成点before/equal/after', C, ['current_core58', 'source_ranges'],
    'finalize_ready等号保留、strict-after撤销；实际candidate函数仍在工作之后重读完成时间。',
    tests=['Deadline.EqualityRegistrationSurvivesEitherCutoffOrder',
           'Deadline.RegistrationCompletionAfterDeadlineRetractsSlot'])
add(g, 1, 'early ready不得提前激活', C, ['current_core58'], '到200ms前不能take且只消费一次。',
    tests=['DeadlineMatrix.Ready50msKeepsOriginal200msTarget'])
add(g, 1, 'wrong target/错版本/重复', C, ['current_core58'], 'Ticket准入拒绝，未替代typed Candidate完整接线。',
    tests=['Admission.WrongTargetDuplicateAndVersion'])
add(g, 1, 'delayed tick/错过tick不追赶', C, ['current_core58', 'current_policy92'],
    '实际due_tick和OutputAuthority错拍/jitter规则已验证，固定槽位不滚到新目标。',
    'current tick_loop调度外壳的受控250/400ms交错由T1源链接检查补齐。',
    tests=['Admission.FixedCapacityAndMissedTickNeverRollsForward', 'SchedulerBoundary.ExactAndAdjacentDueTicks'])
add(g, 0, '不延长deadline/target', C, ['current_core58', '66_W2'],
    '改deadline/target即time_contract；真实W2释放后仍依原截止拒绝C。',
    tests=['DeadlineMatrix.ExtendingDeadlineIsAContractFailure', 'DeadlineMatrix.ExtendingTargetIsAContractFailure'])

g = 'native_block_and_delivery'
add(g, 0, 'native边界独立release', O, ['66_W2'],
    'Job2/ordinal1驻留417.85ms；独立pipe释放验证成功，原截止已过，C调用0。')
add(g, 0, '驻留期间多完整tick及真实心跳', O, ['66_W2'], 'tick3/4及2次续租，未失租约/触发watchdog。')
add(g, 0, 'active/pending/ready有界与单backend', O, ['66_W2', 'source_ranges'],
    '本次实际Job多重集1 delivered/2 expired/3 replaced/4 discarded；单计算线程/backend，ready最大1。')
add(g, 1, '投递延迟与native驻留分离', O,
    ['56_W3', 'historical_raw_reaudit', 'historical_identity', 'source_ranges'],
    'W3_05原始Source/Stored重审通过；投递与正常收尾片段逐字节相同；当前未arm的W2路径不等待。',
    '复用原登记case及相同投递层，不声称本次又运行了新66二进制W3。')
add(g, 1, '生成后单次丢弃、no_candidate、恢复', O,
    ['56_W4', 'historical_raw_reaudit', 'historical_identity', 'source_ranges'],
    'W4_05原始记录重审通过；原Job3丢弃与目标tick4/恢复完整，当前同投递片段保留。',
    '连续多次drop不在原这一子句的单次case内，另列未扩展边界，不新增为必经前置。')

g = 'candidate_identity_shape'
for name in ['failed/solver_invoked=false', 'invalid原生prediction shape/available=false',
             '预测或首控制NaN', '重复Candidate', '旧/乱序Job ID',
             '外来producer/Worker', '外来boot', '旧task/model/config/schedule/epoch版本']:
    add(g, 0 if name in ['failed/solver_invoked=false', 'invalid原生prediction shape/available=false',
                          '预测或首控制NaN', '重复Candidate', '旧/乱序Job ID'] else 1,
        name, W, ['source_ranges', 'current_core58'],
        '现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。',
        'T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。')

g = 'task_reference'
for name in ['freeze前clear', 'freeze前single point', '求解/ready期间clear', '求解期间reference replacement',
             '相同内容重发不改语义task', 'path/profile stamp或长度不匹配', '普通new odom不无条件饿死']:
    add(g, 0 if name in ['freeze前clear', 'freeze前single point', '求解/ready期间clear',
                         '求解期间reference replacement'] else 1,
        name, W, ['F5_mapping', '49_components', '50_publication16', 'source_ranges', 'current_core58'],
        '共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。',
        'T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。')

g = 'state_clock'
for name, tests in [
    ('odom stale/future与独立receive/sim age', ['SourceTime.ReceiveAgeAndPhysicalLagAreIndependent',
                                             'SourceTime.LagAndFutureLimitsAreInclusive']),
    ('IMU只在mixed时适用age/skew', ['SourceTime.OnlyMixedStateUsesImuPhysicalAge']),
    ('激活状态不匹配/finite/yaw wrap', ['Activation.SourceSequenceDoesNotReplaceStateAndVersionGate'])]:
    add(g, 0, name, C, ['current_core58', '53_components', 'source_ranges'],
        '源时间/激活selector同源，当前纯组件和旧源链接激活拒绝证据可复用。',
        '若需认证topic到callback到epoch的联合刺激，由T1/T2明确补交错，组件不称新owned故障。', tests=tests)
for name in ['clock pause', 'clock resume', 'clock reset/backward', 'clock大jump', 'RTF低边界', 'RTF高边界']:
    add(g, 1, name, W, ['current_core58', '53_components', 'source_ranges'],
        'ClockWindow reset/jump/ratio与旧真实clock callback回退组件可复用。',
        'T1核当前clock/tick的schedule/epoch失效及不可复活；当前Fixture不能登记这些刺激，T2只补必要跨进程子集。')

g = 'anchor_fallback'
for name, tests, policies in [
    ('区间内改变后回到原值不能伪称等价', ['PublicationHistory.ChangedThenReturnedIsNotSameInputHistory'], []),
    ('same-value republish保留连续历史', ['PublicationHistory.SameValueRepetitionPreservesInputAssumption'], []),
    ('不同左右实际API间隔分别rate', ['Command.AmplitudeAndActualSteadySpacing'], ['invalid_bypasses_hold_each_side_elapsed']),
    ('missing/evicted history不能授权', ['PublicationHistory.MissingChannelOrSequenceCannotProveEquivalence',
                                     'PublicationHistory.EvictedFreezeAnchorDoesNotAuthorizeCurrentValue'], []),
    ('连续五次miss', [], ['five_misses_hold_then_per_side_ramp']),
    ('HOLD等号及重发不续期', [], ['hold_equality_then_ramp_republish_does_not_renew']),
    ('HOLD之后ramp', [], ['hold_equality_then_ramp_republish_does_not_renew']),
    ('invalid立即绕过HOLD', [], ['invalid_bypasses_hold_each_side_elapsed']),
    ('unknown侧零请求无已知零资格', ['Anchor.PartialFailureIsUnknownAndRealPublishUpdatesCannotBeRolledBack'],
                                     ['initial_numeric_zero_is_unknown'])]:
    add(g, 0 if name.startswith(('区间', 'same', '不同', 'missing')) else 1,
        name, C, ['current_core58', 'current_policy92', '50_publication16', '66_W2', 'source_ranges'],
        '当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。',
        '不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。',
        tests=tests, policies=policies)

g = 'publication_exit'
add(g, 0, 'shutdown before submit', O, ['53_R1', 'source_ranges'],
    '原R1实际owned pre-grant取消/零API，核心准备与submit函数沿用。')
for name in ['clear/shutdown after committed submit', 'shutdown与ready/activation交错']:
    add(g, 0, name, W, ['50_publication16', '53_components', 'source_ranges'],
        '旧clear直接helper及ShutdownDuringValidation组件已有；未把它扩成所有真实提交交错。',
        'T1用同一当前Regulator接线覆盖提交前/后及最终activation拒绝；按义务层次决定T2最小case。')
for name in ['left API partial failure', 'right API partial failure']:
    add(g, 0, name, C, ['50_publication16', 'current_policy92', 'source_ranges'],
        '50真实rcl publish seam组件16例；publish与OutputAuthority逻辑保留，成功侧不可回滚。',
        '这是实际API源链接组件，非本次新增四角色部分发布故障run。')
add(g, 1, 'Worker真实死亡', O, ['53_R2', 'source_ranges'],
    '原R2实际owned死亡与有限ramp/关闭；check_worker_locked保持同源。')
add(g, 1, 'active watchdog与心跳/租约互斥', O,
    ['56_W1', 'historical_raw_reaudit', 'source_ranges'],
    'W1_05重审通过，转移时真实租约仍有效，不能再沿用53外部信号无法隔离的历史阻塞结论。')
add(g, 1, 'capability receipt lease到期', O, ['53_R3', 'current_core58', 'source_ranges'],
    '原R3实际owned失租约；当前14项lease组件覆盖等号/续租/终端不可恢复。')
for name in ['cleanup_failed正确失败', '旧group未空禁止restart']:
    add(g, 1, name, U, ['66_W2'],
        '66证明的是健康有限关闭和group为空；自动重试0不是cleanup_failed分支已经验证。',
        'T3对当前关闭/监督实际消费函数注入有界失败并证明无新spawn；保留真实进程与模拟失败范围，不制造不可杀进程。')

g = 'actual_source_recording'
add(g, 0, '隔离normal straight .05真实完整窗', O,
    ['49_normal', 'F5_mapping', 'source_ranges'],
    '49实际20s正常窗/105 API pairs保留；.05来源和数值core对齐。',
    '不把66短W2正常前缀改称新的20s正常资格。')
add(g, 0, 'controlled faults与完整Source/Stored', O,
    ['historical_raw_reaudit', '66_W2', 'source_ranges'],
    '三例旧诊断重新读原始Source/Stored；66W2独立全流对账成立。')
add(g, 1, 'log queue pressure及声明drop', U, ['49_normal', '66_W2'],
    '正常/故障无丢失是已知事实，不等于施加队列压力。',
    'T3以当前enqueue/drain路径施加有界压力，分清generated/emitted/dropped/Stored，异常资格及未解释差额必须拒绝。')
add(g, 1, 'Source/emit/Stored/API计数及身份', O, ['66_W2', 'historical_raw_reaudit'],
    '66完整306条Stored、11条心跳、6组API及三个旧case的原始多重集合重新核对。')
add(g, 1, 'before/after资产保护', C, ['source_ranges', 'F5_mapping'],
    '本批886项66原件、381项源码审计输入、21个普通工作区文件及最终读回将逐项核对。')

groups = []
clauses = []
for original in matrix['groups']:
    selected = [row for row in rows if row['group'] == original['id']]
    assert selected
    for index, clause in enumerate(original['required_cases']):
        ids = [row['id'] for row in selected if row['original_clause_index'] == index]
        assert ids, (original['id'], clause)
        clauses.append({'group': original['id'], 'clause_index': index,
                        'original_verbatim': clause, 'atom_ids': ids})
    counts = dict(Counter(row['status'] for row in selected))
    groups.append({**original, 'status_counts': counts, 'case_atoms': len(selected),
        'ready_for_layered_joint_review': not any(row['status'] in (W, U) for row in selected),
        'current_M4_qualified': False,
        'qualification_note': 'Case evidence/applicability inventory; whole M4 is decided at N3, not by counting tests'})
assert len(groups) == 9 and len(clauses) == 18
assert len({row['id'] for row in rows}) == len(rows)
assert all(row['evidence_keys'] and row['proven_scope'] for row in rows)
catalog = {'schema': 'M4-original-case-layered-applicability-v67',
    'matrix': {'path': str(MATRIX), **pin(MATRIX)},
    'original_clause_count': len(clauses), 'group_count': len(groups),
    'atom_count': len(rows), 'status_labels': labels, 'status_counts': dict(Counter(row['status'] for row in rows)),
    'groups': groups, 'original_clauses': clauses, 'cases': rows, 'evidence': evidence,
    'N1_inventory_complete': True, 'N2_deterministic_component_slice_complete': True,
    'new_ROS_or_owned_runs': 0,
    'no_new_prerequisites': ['acados C-internal permanent hang', 'duplicate release protocol',
                             'continuous multiple delivery drops', 'plant/hardware qualification'],
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance': False, 'hard_realtime': False, 'research_conclusion': False}
create('postrun/case_applicability_v1.json', catalog)
lines = ['# 第67批：原M4逐case证据与差集\n\n',
         f'原9组、18条required_cases，拆为{len(rows)}个具名核对项。状态不是阶段资格，完整M4/F6/P1保持false。\n\n',
         '| ID | 核对项 | 状态 | 证据代号 | 已证范围与剩余义务 |\n| --- | --- | --- | --- | --- |\n']
for row in rows:
    lines.append(f"| {row['id']} | {row['case']} | {row['status_label']} | {', '.join(row['evidence_keys'])} | {row['proven_scope']} {row['remaining_current_path_obligation']} |\n")
lines += ['\n## 证据代号与固定来源\n\n', '| 代号 | 来源 | SHA256 |\n| --- | --- | --- |\n']
for key, row in evidence.items():
    lines.append(f"| {key} | [{Path(row['path']).name}]({row['path']}) | `{row['sha256']}` |\n")
lines += ['\n## 原条款逐字绑定\n\n']
for clause in clauses:
    lines.append(f"- `{clause['group']}[{clause['clause_index']}]`：{clause['original_verbatim']} → {', '.join(clause['atom_ids'])}\n")
create('postrun/case_applicability_v1.md', ''.join(lines))
create('evidence/case_catalog_inputs_v1.json', {'count': len(READS), 'files': READS})
print(json.dumps({'N1_inventory_complete': True, 'original_clauses': len(clauses),
                  'case_atoms': len(rows), 'status_counts': catalog['status_counts'],
                  'ready_for_layered_joint_review': [row['id'] for row in groups
                                                    if row['ready_for_layered_joint_review']]}, ensure_ascii=False))
