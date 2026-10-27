#!/usr/bin/env python3
"""Read back this batch; create derived coverage and a human-readable handoff."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
AUTHOR = ROOT / 'implementation/w2_author'
RUN = ROOT / 'implementation/runs/W2_01'
OLD = ROOT.parent / 'scheme_A_W2_owned_prep_20261023_65'
MATRIX = ROOT.parent / 'scheme_A_formal_execute_profile_20261020_47/freeze/M4_fault_matrix_v1.json'
PRIOR = ROOT.parent / 'scheme_A_M4_owned_faults_20261021_53/postrun/M4_fault_coverage_v1.json'
W56 = ROOT.parent / 'scheme_A_M4_diagnostic_worker_20261021_56'
REPORT_NAME = '方案A_第66批接替实施_W2实测结果与下一步计划_2026-10-23.md'


def read(path):
    return json.loads(Path(path).read_text())


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(value, (dict, list)) else value)


def link(relative, label=None):
    path = Path(relative)
    if not path.is_absolute():
        path = ROOT / path
    return f'[{label or path.name}]({path})'


assert not (ROOT / 'evidence/final_verification_v1.json').exists()
audit = read(ROOT / 'evidence/owned_audit_v1.json')
launch = read(ROOT / 'evidence/owned_launch/launch_receipt_v1.json')
result = read(RUN / 'driver_result.json')
registration_path = ROOT / 'implementation/W2_registration_v1.json'
registration = read(registration_path)
registry_path = Path(registration['registry'])
registry = read(registry_path)
build = read(ROOT / 'evidence/freeze_and_build/freeze_and_build_v1.json')
bundle = read(ROOT / 'evidence/freeze_and_build/source_bundle.json')
wiring = read(ROOT / 'evidence/w2_wiring/wiring_verification_v2.json')
source_contract = read(ROOT / 'evidence/w2_source_contract/source_contract_v1.json')
preflight = read(ROOT / 'evidence/preflight_replay/preflight_replay_v1.json')
facts = audit['checks']['W2_independent_raw_facts']['evidence']
api = audit['checks']['API_full_stream']['evidence']
boundary = result['w2_result']['boundary']
assert audit['owned_W2_qualified'] and all(c['passed'] for c in audit['checks'].values())
assert launch['passed'] and not launch['outer_timeout'] and launch['cleanup_fallback'] == []
assert result['passed'] and all(result['w2_final_checks'].values())
assert registration['automatic_retries'] == 0
assert len(list((ROOT / 'implementation/runs').iterdir())) == 1
assert (ROOT / 'evidence/owned_launch/attempt_started.json').is_file()
for key in ('M4_stage_qualified', 'F6_qualified', 'P1_qualified',
            'plant_acceptance', 'hard_realtime'):
    assert audit[key] is False

preservation = {}
for name in ('takeover_inputs_v1', 'protected_prior_inputs_v1', 'workspace_before_v1'):
    original = read(ROOT / f'evidence/{name}.json')
    mismatches = []
    for filename, expected in original['files'].items():
        path = Path(filename)
        if not path.is_file() or pin(path) != expected:
            mismatches.append(filename)
    preservation[name] = {'checked_files': len(original['files']), 'mismatches': mismatches}
    assert not mismatches, (name, mismatches)
workspace_before = read(ROOT / 'evidence/workspace_before_v1.json')
git_status = subprocess.check_output(
    ['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
assert git_status == workspace_before['status_porcelain'], 'Concurrent git status changed; report it'
preservation['git_status_unchanged'] = True
preservation['scope'] = ('107 selected takeover files, 524 selected historical files, '
                         '21 ordinary workspace files and git porcelain; not a full historical '
                         'or submodule-content scan')

source_mismatches = []
for relative, row in bundle['files'].items():
    path = AUTHOR / relative
    assert str(path) == row['path']
    if pin(path) != {k: row[k] for k in ('bytes', 'sha256')}:
        source_mismatches.append(relative)
assert not source_mismatches
assert set(bundle['files']) == {str(p.relative_to(AUTHOR))
                               for p in AUTHOR.rglob('*') if p.is_file()}
assert pin(Path(build['source_bundle']['path']))['sha256'] == registry['source_bundle_sha256']
assert pin(registration_path)['sha256'] == audit['registration_sha256']
assert pin(registry_path)['sha256'] == registration['registry_sha256']
assert pin(Path(registry['driver']))['sha256'] == registry['driver_tool_sha256']
identity_pins = {'registration': {'path': str(registration_path), **pin(registration_path)},
                 'registry': {'path': str(registry_path), **pin(registry_path)},
                 'source_bundle': {'path': build['source_bundle']['path'],
                                   **pin(build['source_bundle']['path'])},
                 'driver': {'path': registry['driver'], **pin(registry['driver'])}}
for role, record in registry['roles'].items():
    binary = Path(record['binary'])
    assert pin(binary)['sha256'] == record['binary_sha256']
    assert pin(record['source_bundle']['path'])['sha256'] == record['source_bundle']['sha256']
    identity_pins[role] = {'path': str(binary), **pin(binary)}
for tool in ('audit_tool', 'launch_tool'):
    record = registration[tool]
    assert pin(record['path'])['sha256'] == record['sha256']
    identity_pins[tool] = {'path': record['path'], **pin(record['path'])}
library_current = {}
for name, row in registry['acados_runtime'].items():
    path = Path(row['path'])
    st = path.stat()
    assert (st.st_dev, st.st_ino) == (row['device'], row['inode'])
    assert pin(path) == {k: row[k] for k in ('bytes', 'sha256')}
    library_current[name] = {'path': str(path), 'unchanged_since_registry': True}

groups = {}
for row in launch['owned_group_postchecks']:
    spawn = read(RUN / row['role'] / 'spawn.json')
    groups[row['role']] = spawn.get('pgid', row['pid'])
remaining = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        stat = (proc / 'stat').read_text()
        rest = stat[stat.rindex(')') + 2:].split()
        if int(rest[2]) in groups.values():
            remaining.append({'pid': int(proc.name), 'pgid': int(rest[2])})
    except (OSError, ValueError, IndexError):
        continue
assert not remaining, remaining

author_delta = []
for relative in bundle['files']:
    before = OLD / 'implementation/w2_author' / relative
    after = AUTHOR / relative
    if not before.exists() or before.read_bytes() != after.read_bytes():
        author_delta.append({'file': relative, 'kind': 'modified' if before.exists() else 'new',
                             'current': pin(after), 'previous': pin(before) if before.exists() else None})
write_new(ROOT / 'evidence/author_delta_from65_v1.json', {
    'schema': 'W2-author-delta-from-interrupted65-v1', 'count': len(author_delta),
    'files': author_delta, 'root_production_source_modified_by_this_batch': False})

old_matrix = read(MATRIX)
prior = read(PRIOR)
assert pin(MATRIX)['sha256'] == '58c7eccb51eb463a3012de09b4e78d4f4397317025d5618be4cf798a9d0fbd74'
remaining_by_id = {
    'compatibility_input': '核对F5 source/reference/mapping及logging off/on适用性；独立Fixture的输入契约与旧core逐项绑定。',
    'time_boundaries': '本次只实测一个严格过期点；50/150/250/400ms、等号、early ready、wrong target、delayed tick须逐案映射已有证据或补最小差集。',
    'native_block_and_delivery': '边界独立释放子项已通过；56的W3/W4_05需对66的投递路径给出来源/行为差异适用性判定，不能直接转移资格。',
    'candidate_identity_shape': 'failed/shape/NaN/duplicate/reordered/foreign身份的原case，需同源码准入证据与当前接线路径的适用性对账。',
    'task_reference': 'clear/single point、求解中clear/replace、same-content、path/profile不一致与new odom的未覆盖差集。',
    'state_clock': '旧组件/正常段证据保留；当前路径stale/future/mixed skew、pause/reset/jump/RTF差集尚待核对。',
    'anchor_fallback': '本次全API流间隔/跨度/rate通过；不等于五次miss、HOLD等号/之后、invalid bypass、unknown-side矩阵全闭合。',
    'publication_exit': '本次健康有限隔离与清理通过；50/53/56历史子项须适用性核对，cleanup_failed及清理失败禁止重启仍未实证闭合。',
    'actual_source_recording': '本次306条Stored及Source/Witness闭合；没有施加log queue pressure，也未替代所有原正常/故障配置。',
}
coverage_groups = []
for group in old_matrix['groups']:
    coverage_groups.append({**group, 'current_M4_qualified': False,
                           'remaining_obligation': remaining_by_id[group['id']],
                           'historical_evidence_automatically_transferred': False,
                           'new66_evidence': ([str(ROOT / 'evidence/owned_audit_v1.json')]
                               if group['id'] in ('native_block_and_delivery', 'publication_exit',
                                                  'anchor_fallback', 'actual_source_recording',
                                                  'time_boundaries') else [])})
coverage = {
    'schema': 'M4-original-nine-group-derived-delta-v66',
    'parent_matrix': {'path': str(MATRIX), **pin(MATRIX)},
    'prior_coverage': {'path': str(PRIOR), **pin(PRIOR)},
    'groups': coverage_groups,
    'closed_subitems_this_batch': [{
        'group': 'native_block_and_delivery',
        'required_case_verbatim': 'worker held at native boundary until independent release',
        'qualified': True, 'run_id': registration['run_id'],
        'independent_audit': {'path': str(ROOT / 'evidence/owned_audit_v1.json'),
                              **pin(ROOT / 'evidence/owned_audit_v1.json')},
        'complete_ticks': facts['complete_ticks'], 'held_renewals': facts['held_renewals'],
        'target_C_calls': facts['target_C_calls'],
        'scope': 'registered finite native-boundary wait; not a hang within acados C'}],
    'historical_not_reaudited_this_batch': {
        'W1_W3_W4': str(W56 / 'documents/第56批收尾_W4修正与独立审计_2026-10-22.md'),
        'runs': ['W1_05', 'W3_05', 'W4_05'],
        'superseded_runs_are_not_delivery_evidence': ['W1_01', 'W3_01', 'W4_01'],
        'R1_R2_R3': str(PRIOR),
        'note': '53的active_watchdog不可隔离结论是当时外部信号路径的历史限制；56的诊断W1已另有证据，不据此重复宣称仍结构性阻塞。'},
    'all_nine_groups_require_new_long_ROS_runs': False,
    'new_owned_runs': 1, 'automatic_retries': 0,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance': False, 'hard_realtime': False, 'research_conclusion': False,
    'next_order': ['source/applicability and Fixture difference inventory',
                   'minimum uncovered deterministic and owned cases',
                   'M4 joint reassessment', 'finite model transaction/F6', 'P1'],
}
write_new(ROOT / 'postrun/M4_fault_coverage_delta_v66.json', coverage)
coverage_lines = ['# 第66批：原M4九组矩阵差量\n\n',
                  f'原件保持：{link(MATRIX)}。本表是派生差量，完整M4/F6/P1均为false。\n\n',
                  '| 原组 | 本批增量及剩余义务 | 整组资格 |\n| --- | --- | --- |\n']
for group in coverage_groups:
    coverage_lines.append(f"| {group['id']} | {group['remaining_obligation']} | false |\n")
coverage_lines += ['\n本次只关闭原文 `worker held at native boundary until independent release` 子项。',
                   '56的W3/W4投递延迟/丢弃证据保留，待来源与行为差异适用性核对；本次没有重跑它们。',
                   'acados C内部挂起未覆盖，但不是原47这条要求，也不新增为本阶段前置条件。',
                   '无需把九组全部改成新的长ROS运行；先核对已有证据，再跑确切缺口。\n']
write_new(ROOT / 'postrun/M4_fault_coverage_delta_v66.md', ''.join(coverage_lines))

next_steps = [
    {'id': 'N1', 'task': '逐case适用性与Fixture差集清单',
     'inputs': [str(MATRIX), str(PRIOR), str(W56), str(AUTHOR)],
     'deliverable': '每条原required_case绑定原证据/SHA/源码范围/合同；状态为可复用、需补接线验证、未覆盖或明确不适用并给理由。',
     'done_when': '所有原条目都有可审计处置，无空白、无整组资格自动转移；列出需新执行的最小case清单。'},
    {'id': 'N2', 'task': '只实现与执行清单中的最小缺口',
     'depends_on': 'N1',
     'code_plan': '新派生批次复用已冻结core；Fixture提供有界刺激；必要Driver分支与独立事实审计同批固定；执行代码变化重新封存/登记。',
     'candidates_pending_inventory': ['原deadline/target时序边界', 'reference/state/clock变化',
         'HOLD/ramp/anchor差集', 'cleanup_failed禁止重启', 'Source队列压力与已声明丢弃'],
     'constraints': ['上述是待N1筛选的候选集合，不是宣称每项均须新ROS长跑',
         '故障不允许修改150ms截止/600ms租约/1s watchdog/关闭预算',
         '每个owned case先登记、自动重试0、失败原件保留、无plant/硬件'],
     'done_when': '各缺口有真实所需层级证据；组件只证明组件，需owned的case由实际Source/Stored与关闭对账判定。'},
    {'id': 'N3', 'task': 'M4联合复判', 'depends_on': 'N2',
     'done_when': '原九组逐项满足，复用适用性与新增证据共同成立后，才单独判定完整M4；不以通过数量替代覆盖。'},
    {'id': 'N4', 'task': '有限模型事务/F6', 'depends_on': 'M4满足该阶段原登记前置条件',
     'done_when': '读取原F6合同后在新批次细化模型版本、提交/拒绝及失效行为的有限事务验证；本批未实现、未授予F6资格。'},
    {'id': 'N5', 'task': 'P1联合验收', 'depends_on': '原P1全部前置满足',
     'done_when': '按冻结P1合同汇总组件/阶段/实际执行证据，明确API、进程退出、plant接受、硬实时的各自边界。'},
]
write_new(ROOT / 'postrun/next_steps_v1.json', {
    'schema': 'scheme-A-mainline-after-owned-W2-v66', 'order_fixed': True,
    'no_additional_owned_run_executed_this_batch': True, 'steps': next_steps})

now = datetime.datetime.now().astimezone().isoformat()
run_files = {str(p.relative_to(RUN)): pin(p) for p in sorted(RUN.rglob('*')) if p.is_file()}
write_new(ROOT / 'evidence/owned_run_inventory_v1.json', {
    'schema': 'W2-raw-owned-run-inventory-v1', 'run_id': registration['run_id'],
    'files': run_files, 'file_count': len(run_files),
    'outside_run_audit': {'path': str(ROOT / 'evidence/owned_audit_v1.json'),
                          **pin(ROOT / 'evidence/owned_audit_v1.json')}})

effects = {
    'CMakeLists.txt': '仅测试目标加GNU链接包装器，把stop/时钟推进放进真实acados准备调用；执行角色没有该测试注入。',
    'worker/owned_cold_backend.hpp': '在真实C入口观察者按Job计数，成功/异常均保存actual_C_solve_calls_this_job；目标与非目标各自保持最终guard。',
    'owned_m4_diagnostic_driver_v1.py': '共用预检、grant前活库认证、两完整tick及真实续租后独立写帧；补发布事实/目标policy/失败收尾与完整最终判据。',
    'w2_runtime_contract.py': '共享登记校验、活进程maps认证、tick配对和Driver最终事实判据；不以手抄预检代替真实入口。',
    'audit_w2.py': '独立读取原始Source、release、API、manifest、Stored，重建W2事实和每Job终局；不以Driver PASS作case证据。',
    'w2_audit_common.py': '从58原件复制的通用身份/API/Source工具，原字节保留并登记来源；不使用旧W1/W3/W4主审计冒充W2。',
    'worker/test_w2_backend_wiring.cpp': '修复伪准备窗口测试；增加真正准备后stop/过期与真实C返回异常事实检查。',
    'worker/test_w2_driver_contract.py': '23项共用契约、总判据、真实进程活库映射正反例。',
    'worker/test_w2_audit.py': 'W2事实层合成正控及9个只认AssertionError的反例，不作为owned证据。',
    'worker/run_driver_branch_replay.py': '补新观察上下文，保留合法流与四错误流分支重放。',
    'worker/run_wiring_verification.py': '私有构建/日志保留，变异必须prepared；源码组合破坏须命中指定失败而非任意Python异常。',
}
changed_rows = '\n'.join(f"| `{row['file']}` | {'新增' if row['kind']=='new' else '修改'} | {effects[row['file']]} |"
                         for row in author_delta)
hash_rows = '\n'.join(f"| {label} | `{identity_pins[key]['sha256']}` |"
                      for key, label in [('source_bundle', '100项source bundle'), ('driver', 'Driver'),
                         ('worker', 'Worker ELF'), ('regulator', 'Regulator ELF'), ('fixture', 'Fixture ELF'),
                         ('registry', 'registry'), ('registration', 'registration'), ('audit_tool', 'W2审计工具')])
held_ms = (boundary['guard_ns'] - boundary['entered_ns']) / 1e6
late_ms = boundary['past_deadline_ns'] / 1e6
coverage_rows = '\n'.join(f"| `{g['id']}` | {g['remaining_obligation']} | false |" for g in coverage_groups)
report = f'''# 方案A第66批：接替实施、W2实测结果与下一步计划

日期：2026-10-23（北京时间）；整理时间：{now}。

## 1. 当前结论与本次终点

已接替本地Claude在65包中断的工作，按64号复核计划完成有限修正、最终构建登记、**一次实际owned W2**及**独立审计**。本次`owned_W2_qualified=true`，关闭原47矩阵中“worker held at native boundary until independent release”这一子项。完整M4、F6、P1、plant接受、硬实时与研究结论仍为false。

这次从“组件和登记准备”推进到了“真实运行及独立核验”。实际run为`{registration['run_id']}`，只执行1次，自动重试0，实际Driver耗时{result['elapsed_seconds']:.3f}s；没有因为成功再重复运行，也没有改阈值。原实船B继续MANUAL＋RC覆写。

本次代码在新66派生作者树中；没有把诊断角色修改直接合入主工作区生产源码。主工作区已有未提交内容和并行任务改动保留。

## 2. 接替的是哪个停点

最近Claude原始记录为`/home/trevor/.claude/projects/-home-trevor-USV/48837ca4-a874-41f0-8415-7b5535569f2c.jsonl`。65包处于实施中，尾部API 400中断；它不是一次已完成owned W2的交付。

接手时旧65已有构建产物，但`worker/run_source_contract.py`、`worker/test_w2_backend_wiring.cpp`在构建后发生变化，旧bundle与当前作者树不一致，不能沿用旧身份。107项接手输入已固定并快照，原65及失败停点保留。详见{link('evidence/old65_identity_status_v1.json')}、{link('evidence/takeover_inputs_v1.json')}。

时间线保持原纠正：61的D1–D6来自上一轮；62的E1–E6、63正式登记、64复核、65未完成实施、66本次接替是不同版本，不把前一轮改动计入本轮。

## 3. 本次实际修了什么，为什么需要

65中名为Preparation的失败测试仍在entry_observer里设stop，实际发生于Gate wait之前，却要求准备后guard时间，误把合法的`guard_ns=0`提前停止解释成实现错误。停止还可能发生在deadline之前，`past_deadline_ns`为负值本来合理。本次以测试专用链接包装器在真正`acados_update_params`准备调用中注入，才锁定真正准备窗口。

目标调用由Boundary在最后入口判断并刷新事实；非目标调用仍查自身stop与deadline。真实C入口观察者计数在异常路径也保留；不能由“进入C++包装器”推导C已调用。

共用`registration_preflight`让Driver和离线工具执行同一校验。描述性deadline/release/channel政策与权威登记字段必须一致；活Worker的实际maps、文件路径/dev/inode、当前文件hash在业务grant之前认证。Driver写入44字节帧后，Worker验证目标身份，最后仍使用Job原截止，Gate窗口不能延长Job期限。

作者树相对接手时65实际有{len(author_delta)}项差异：

| 文件（位于implementation/w2_author） | 类型 | 作用 |
| --- | --- | --- |
{changed_rows}

作者树之外，`freeze_and_build.py`、`write_registration.py`、`replay_driver_preflight.py`承接并完善正式身份及共用预检；`launch_owned_once.py`与`run_owned_once.sh`执行有限单次运行；`run_audit.sh`只启动离线审计。`run_components.py`、本收尾脚本和交付脚本保存验证及交接产物。逐文件hash见{link('evidence/author_delta_from65_v1.json')}。旧65已经正确完成的目标优先guard等修正保留，未重写其归属。

## 4. 验证分层

| 层次 | 实际结果 | 证明范围 |
| --- | --- | --- |
| C++组件/真实Backend接线 | 15＋13＋13＝41项通过 | gate、entry、Backend；真实准备窗口和C返回异常路径 |
| 接线变异 | 12/12 prepared且捕获 | 删除接线、真实guard、C观察者、名单、terminal清active等均会失败 |
| 源码组合检查 | {len(source_contract['checks'])}/{len(source_contract['checks'])} | Worker消费共用白名单、真实RawBackend调用guard等组合关系 |
| Driver分支重放 | 5/5 | 合法事件流通过；四种错误由指定断言拒绝 |
| Python共享契约/活库组件 | 23项通过 | 合同、最终判据、真实进程映射及错误路径；不启动ROS |
| 审计事实层合成反例 | 正控＋9个断言反例 | 验证事实审计会拒绝篡改；不能替代owned证据 |
| 最终构建与预检 | 100项冻结，真实宏ELF；正控＋5拒绝反例 | 同一预检函数消费真实登记，运行前身份来源有效 |
| 实际owned | 1次，Driver {len(result['w2_final_checks'])}项最终检查全通过 | 真实四角色、DDS、Source、私有pipe及关闭 |
| 运行后独立审计 | {len(audit['checks'])}/{len(audit['checks'])}通过 | 原始事实、身份、API、Stored及有限关闭联合成立 |

完整日志见{link('evidence/w2_wiring/wiring_verification_v2.json')}、{link('evidence/final_python_validation/verification_v1.json')}、{link('evidence/preflight_replay/preflight_replay_v1.json')}。`component_attempt01`是较早组件过程证据；最终身份与实测应引用最终冻结和本节证据，不能拿较早构建SHA代替。

## 5. 正式来源与身份

| 对象 | SHA256 |
| --- | --- |
{hash_rows}

Recorder复用`p1_execution_architecture_20261005_01`的登记产物，未错误标为attempt18。三执行角色含最终bundle/Driver编译期身份。注册的审计工具本身也固定hash。细节见{link('evidence/freeze_and_build/freeze_and_build_v1.json')}。

`index_sha256`仍沿用56的合成EVIDENCE标记，它不是所指合同文件内容hash；真实合同内容单独由`contract_sha256`核对。没有为了消除名称歧义回写56冻结原件。

实际运行库认证不是只看`ldd`输出：Driver在grant前读取本次Worker的live maps并核对3个实际库、路径/dev/inode和文件SHA，保存{link('implementation/runs/W2_01/worker_loaded_libraries.json')}。运行后复核这些登记文件也未变化。

## 6. 唯一实际W2发生了什么

登记固定Job2/ordinal1/nonce20261023，Gate等待上限1.5s；业务周期200ms、Job截止150ms、租约600ms、active watchdog 1s及关闭预算均未放宽。Driver只保留pipe写端，Worker继承只读端，通道身份由本次pipe的dev/inode对账。

前序Job1正常完成、候选发布并接受；它的冷启动多次C调用不能算到目标Job2。目标Job2进入内部边界后，计算线程等待，Regulator与心跳继续运行。完整tick3、tick4及2次真实续租出现后，Driver独立写一次完整44字节release帧。

| 原始事实 | 本次值 |
| --- | --- |
| Boundary entered_ns | {boundary['entered_ns']} |
| Job原deadline_ns | {boundary['job_deadline_ns']} |
| Worker验证released_ns | {boundary['released_ns']} |
| 最后guard_ns | {boundary['guard_ns']} |
| 驻留至guard | {held_ms:.6f}ms |
| 超出原截止 | {late_ms:.6f}ms |
| Gate结果 / 最后处置 | released / expired |
| 目标Job实际C solve | 0 |
| 目标候选生成/发布/注册/激活 | 均无 |
| 原watchdog | 未触发；释放早于1s边界 |

“验证释放成功”和“原Job已过期”同时成立，正是本case预先登记的正确结果。不会因为Gate有1.5s预算给Job续期，也不会把`actual_native_invoked=false`伪改成true来声称覆盖C内部阻塞。

每个已发/已收Job都有明确终局：

| Job | 唯一终局 |
| --- | --- |
| 1 | delivered |
| 2 | expired_at_boundary |
| 3 | replaced |
| 4 | discarded |

实际pending Job4逐Job丢弃，active清零，异常不伪增正常completed。ready最大1。完整来源见{link('implementation/runs/W2_01/driver_result.json')}、{link('implementation/runs/W2_01/worker/source.jsonl')}、{link('implementation/runs/W2_01/regulator/source.jsonl')}、{link('evidence/owned_audit_v1.json')}。

## 7. API、Source、Stored和关闭对账

独立审计读取完整流，未只取业务中段。6组左右API调用：最大间隔分别{api['max_gap_ns'][0]/1e6:.6f}ms、{api['max_gap_ns'][1]/1e6:.6f}ms，低于240ms；最大组跨度{api['max_span_ns']/1e6:.6f}ms，低于5ms；最大实际间隔rate分别{api['max_rate_n_s'][0]:.6f}、{api['max_rate_n_s'][1]:.6f}N/s，低于80N/s。最后零目标及有限关闭核对通过。这是API发布侧证据，不赋予plant接受资格。

Recorder存储306条：clock/odom/imu各86，path/profile各4，capability11，decision/applied/left/right各6，Job4，candidate1。capability Source11与Stored11多重集完全一致。Fixture wire观察305与Stored306差1条capability，在原已登记有界窗口允许范围内；不是未解释业务丢失。Regulator最终Source计数301，Driver提前结束的观察前缀264条不是最终Source缺失。

Witness的`normal_contract_qualified`只表明其记录器局部范围，manifest中的诊断/execute/物理放行标志按合同解释，不能用局部标签推导M4或P1通过。

Regulator RC0；Worker RC2；Fixture/Recorder RC0，关闭信号按登记精确核对。Regulator的关闭表`signals=[]`与显式driver-registered-stimulus分开保存；仅靠空信号表无法证明没有先前关闭刺激，不能据此称无信号自然退出。其余三角色均为登记SIGINT。四组退出后为空；外层未超时、未用兜底清理，也未向其他任务发信号。原始关闭记录见{link('evidence/owned_launch/launch_receipt_v1.json')}。

## 8. 与原M4矩阵对齐：推进在哪里，仍缺什么

原47矩阵保持原字节：{link(MATRIX)}；本批派生更新为{link('postrun/M4_fault_coverage_delta_v66.json')}和{link('postrun/M4_fault_coverage_delta_v66.md')}。

| 原组 | 当前剩余义务/适用性核对 | 整组资格 |
| --- | --- | --- |
{coverage_rows}

原47要求的是边界独立释放，本次已取得对应实际证据；**acados C内部挂起没有验证，也不被新增为这条原要求的必经前置**。`kDuplicateRelease`仍无实际返回路径，本次没有把它另立为阻断主线的协议项目。连续多次丢弃、cleanup_failed、日志队列压力没有被本次覆盖。

56的W1/W3/W4仅引用最终`_05`历史结果，旧`_01`继续在superseded保留；本次没有重审或自动转移它们的整阶段资格。53当时“外部信号无法隔离watchdog”的限制应按历史解释，不能忽略56后来完成的诊断W1。完整组仍需联合证据及来源适用性判定。

## 9. 固定顺序的下一步与代码实施方式

1. **先做逐case适用性与Fixture差集清单。** 读取原47每条required_case，绑定49/50/53/56及本66证据、合同、源码范围和SHA。每条写为可复用、需补接线验证、未覆盖或有依据的不适用。先判别56投递延迟/丢弃路径相对66的变化，决定是否需要定向回归，不以作者树名字不同为由重跑全部历史。
2. **只实现差集中真正缺的刺激。** 在新批次派生，复用core，给Fixture增加有界且可记录的reference/state/clock或发布/Source故障入口。时序等号、身份/shape、HOLD/anchor等能由真实同源码组件证明的先用确定性检查；跨executor/进程/Stored义务才做最小owned。cleanup_failed必须真实区分请求、API、进程组清空及禁止重启，不能由本次清理成功反推失败分支也正确。日志压力须精确计数声明丢弃，不能放宽Source完整标准。
3. **受影响代码重新封存并登记后执行。** Driver增加case分支时，同时补拒绝反例与独立原始事实审计；Fixture刺激要能在Source标出真实发生时刻。每个新owned先固定有限预算、终局、关闭信号、自动重试0，保留首个失败和旧证据。确认运行中不调deadline/租约/watchdog/model/cost阈值。
4. **M4联合复判。** 九组所有原case有适用性解释及足够层级证据后，才单独判定完整M4。无需九组各跑一轮新的长ROS实验，也不能凭通过数量授予资格。
5. **随后有限模型事务/F6，再P1联合验收。** 先读取原F6合同并核对前置，再细化有限模型事务；本批未实施F6。P1最后汇总其原冻结要求，API发布、有限进程退出、plant接受、硬实时分别判定。

机器可读顺序及完成条件见{link('postrun/next_steps_v1.json')}。本批执行停在一次W2及独立审计完成；未启动第二个owned case。

## 10. 保存与交付

最终复核：65接手107项、选定历史524项、普通工作区21项hash均未变化，git porcelain与接手一致。这个范围不等于全历史目录或ardurover子模块内容的全量扫描。最终100项作者树人口与bundle一致，工具/ELF/registry/registration未被跑后改写，37个实际run文件另有库存hash。检查见{link('evidence/final_verification_v1.json')}、{link('evidence/owned_run_inventory_v1.json')}。

源包位于`{ROOT}`；向`/home/trevor/MPC/{ROOT.name}`以新目录镜像交付，库存与交付回执保存于`evidence/package_inventory_v1.json`、`evidence/delivery_to_MPC_v1.json`。这些交付断言须以最终回执的exact_population及SHA回读为准。MPC是完整证据镜像；冻结登记的执行来源绝对路径仍指向USV原作者树，不把镜像静默当成新的可执行身份。
'''
write_new(ROOT / 'documents' / REPORT_NAME, report)
current = f'''# 方案A第66批：owned W2完成，等待Fixture差集

更新：{now}。

- 接替65中断工作；新66作者树修正、正式构建/登记、一次真实owned及独立审计均完成。
- `owned_W2_qualified=true`：Job2/ordinal1驻留{held_ms:.3f}ms，完整tick3/4及2次真实续租后独立释放；超原截止{late_ms:.3f}ms，目标实际C调用0。
- 每Job终局：1 delivered、2 expired_at_boundary、3 replaced、4 discarded；pending4逐Job归账。
- C++41项、12变异、源码组合{len(source_contract['checks'])}项、Driver分支5例、Python23项、合成审计9拒绝反例通过；实际独立审计{len(audit['checks'])}项通过。组件与owned证据分别保存。
- 真实运行1次、自动重试0、Driver耗时{result['elapsed_seconds']:.3f}s；四组有限关闭为空，无外层超时/兜底清理。
- 原47的native-boundary独立释放子项已闭合。完整M4/F6/P1/plant/硬实时/研究结论仍false。
- 原生C内部挂起未覆盖，不新增为原47边界条目的前置；56历史W1/W3/W4保留，未自动转移整组资格。
- 下步固定：逐case来源适用性与Fixture差集 → 最小缺口 → M4联合复判 → 有限模型事务/F6 → P1。
- 生产B仍MANUAL＋RC覆写；65及更早选定资产、主工作区并行改动保持。

主报告：{link('documents/' + REPORT_NAME)}。
运行审计：{link('evidence/owned_audit_v1.json')}。
覆盖差量：{link('postrun/M4_fault_coverage_delta_v66.json')}。
最终保护/身份：{link('evidence/final_verification_v1.json')}。
'''
(ROOT / 'CURRENT.md').write_text(current)

verification = {
    'schema': 'W2-owned-takeover-final-readback-v66', 'checked_at': now,
    'preservation': preservation, 'source_population': len(bundle['files']),
    'source_population_exact': True, 'source_mismatches': source_mismatches,
    'identity_pins': identity_pins, 'runtime_files_current': library_current,
    'runtime_live_maps_authenticated_before_grant': True,
    'owned_runs_executed': 1, 'automatic_retries': 0,
    'owned_run_files': len(run_files), 'groups_currently_visible_remaining': remaining,
    'group_check_scope': 'Current tool-visible /proc; post-exit launcher receipt also retained',
    'component_cpp_tests': sum(s['passed'] for s in wiring['suites'].values()),
    'prepared_mutations_caught': len(wiring['mutations']),
    'shared_preflight_positive_and_five_negatives': preflight['positive_passed'] and
        all(preflight['negative_cases_assertion_rejected'].values()),
    'owned_W2_qualified': True, 'independent_audit_checks': len(audit['checks']),
    'driver_final_checks': len(result['w2_final_checks']),
    'raw_facts': facts, 'API_full_stream': api,
    'report': str(ROOT / 'documents' / REPORT_NAME),
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'plant_acceptance': False, 'hard_realtime': False, 'research_conclusion': False,
}
write_new(ROOT / 'evidence/final_verification_v1.json', verification)
links = []
for document in [ROOT / 'CURRENT.md', ROOT / 'documents' / REPORT_NAME,
                 ROOT / 'postrun/M4_fault_coverage_delta_v66.md']:
    for target in re.findall(r'\]\((/[^)]+)\)', document.read_text()):
        assert Path(target).exists(), (document, target)
        links.append(target)
write_new(ROOT / 'evidence/document_link_check_v1.json', {
    'schema': 'W2-takeover-document-links-v1', 'checked': len(links), 'missing': []})
print(json.dumps({'owned_W2_qualified': True, 'report': str(ROOT / 'documents' / REPORT_NAME),
                  'preservation': preservation, 'author_delta': len(author_delta),
                  'source_population': len(bundle['files']), 'owned_runs': 1,
                  'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False},
                 ensure_ascii=False))
