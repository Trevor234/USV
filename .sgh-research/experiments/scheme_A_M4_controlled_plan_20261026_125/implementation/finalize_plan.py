#!/usr/bin/env python3
"""Create planning artifacts and read-only baseline checks. Executes no research step."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
PREVIOUS = ROOT.parent / 'scheme_A_M4_session_code_review_20261026_124'
DOC = ROOT / 'documents/方案A_第125批_严格执行顺序与逐步验收计划_2026-10-26.md'
CONTRACT = ROOT.parent / 'scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json'
CONTRACT_SHA = '19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'
QUALIFICATION = {k: False for k in ('M4', 'F6', 'P1', 'plant', 'hard_realtime')}
BUDGETS = {
    'T_ns': 200000000, 'deadline_ns': 150000000, 'hold_ns': 600000000,
    'active_watchdog_ns': 1000000000, 'worker_capability_receipt_timeout_ns': 600000000,
    'publish_budget_ns': 5000000, 'publish_gap_ns': 240000000, 'tick_jitter_ns': 20000000,
    'shutdown_grace_ns': 2500000000, 'worker_grace_ns': 500000000,
}
ISSUES = {
    'E00': [], 'E01': ['F124-01'], 'E02': ['F124-02'], 'E03': ['F124-03'],
    'E04': ['F124-04'], 'E05': ['F124-05'], 'E06': ['F124-06', 'F124-07'],
    'E07': ['F124-08'], 'E08': ['F124-09'], 'E09': [], 'E10': ['F124-10'],
    'E11': ['F124-07'], 'E12': [],
}
GAPS = [
    {'id': 'G01', 'scope': 'F6完整mixed参考/模型身份、真实tick激活、生产故障对拍', 'next': '模型事务集成评审'},
    {'id': 'G02', 'scope': '生成setter内部不可观测错误传播', 'next': '单独API/生成码适配评审'},
    {'id': 'G03', 'scope': 'B2任意接收抖动/长hold的普遍恢复', 'next': '新需求触发的时域政策设计'},
    {'id': 'G04', 'scope': 'survivor全部fd清理/fork失败的通用复用', 'next': '专项工具硬化'},
    {'id': 'G05', 'scope': 'B0真实clock-epoch恢复、B1豁免', 'next': '独立需求/设计'},
    {'id': 'G06', 'scope': 'GP采集、plant、RT平台、P1联合验收', 'next': '资源决策与独立计划'},
    {'id': 'G07', 'scope': '论文新颖性与写作', 'next': '文献与写作工作流'},
]


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write_json(relative, value):
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as out:
        out.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def verify_files(files):
    missing, changed = [], []
    for name, record in files.items():
        path = Path(name)
        if not path.is_file():
            missing.append(name)
        elif pin(path) != record:
            changed.append(name)
    return {'count': len(files), 'missing': missing, 'changed': changed,
            'all_match': not missing and not changed}


def nonbuild_files(root):
    for directory, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('build') and d not in ('cmake_build', 'CMakeFiles', '__pycache__')]
        for name in sorted(names):
            if name.endswith('.pyc'):
                continue
            path = Path(directory) / name
            if path.is_file():
                yield path


now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
document = DOC.read_text(encoding='utf-8')
matches = list(re.finditer(r'^### (E\d{2})｜(.+)$', document, re.M))
assert [m.group(1) for m in matches] == [f'E{i:02d}' for i in range(13)]
steps = []
for i, match in enumerate(matches):
    end = matches[i + 1].start() if i + 1 < len(matches) else document.index('\n## 5.')
    body = document[match.end():end].strip()
    allow = re.search(r'\*\*白名单：\*\* (.+)', body)
    steps.append({
        'id': match.group(1), 'title': match.group(2), 'status': 'NOT_STARTED',
        'depends_on': [] if i == 0 else [f'E{i - 1:02d}'],
        'addresses': ISSUES[match.group(1)],
        'allowed_changes': allow.group(1).strip() if allow else '唯一新执行包内的基线、派生副本、manifest和执行约束；原件只读',
        'requirements_verbatim_markdown': body,
        'requirements_sha256': hashlib.sha256(body.encode()).hexdigest(),
        'release_gate': 'all_mandatory_requirements_and_expected_cases_pass_with_complete_evidence',
        'evidence_required': [
            f'evidence/{match.group(1)}/attemptNN/commands.json',
            f'evidence/{match.group(1)}/attemptNN/verification.json',
            f'postrun/{match.group(1)}_step_result.json', 'CURRENT.md'],
        'skip_allowed': False, 'owned_runs_allowed': 0,
    })

contract = json.loads(CONTRACT.read_text())
assert pin(CONTRACT)['sha256'] == CONTRACT_SHA
assert all(contract[k] == v and f'| {k} | {v}' in document for k, v in BUDGETS.items())
assert set().union(*(set(s['addresses']) for s in steps)) == {f'F124-{i:02d}' for i in range(1, 11)}
for step in steps:
    if step['id'] != 'E00':
        assert f"**依赖：** {step['depends_on'][0]} PASS。" in step['requirements_verbatim_markdown']

plan = {
    'schema': 'schemeA-controlled-execution-plan-v125', 'recorded_at': now,
    'planning_complete': True, 'execution_started': False,
    'document': str(DOC), 'document_pin': pin(DOC),
    'precedence': '最新明确用户指令优先；本MD为执行条款，JSON逐步原文必须与MD一致；发现分歧先停止依赖动作并登记',
    'source_review': str(PREVIOUS),
    'default_scope_on_future_execute_request': 'E00–E12 offline hardening only',
    'sequential': True, 'automatic_owned_runs': False,
    'future_execution_package': 'E00分配唯一新目录，不能在125或旧冻结包内执行整改',
    'steps': steps, 'allowed_remaining_gaps': GAPS,
    'outcome_dimensions': ['observed_facts', 'run_accepted', 'coverage', 'stage_qualified'],
    'statuses': ['NOT_STARTED', 'RUNNING', 'PASS', 'FAIL_STOP', 'BLOCKED_SPEC', 'NOT_COVERED', 'N/A'],
    'mandatory_coverage_cannot_be_demoted_after_run': True,
    'final_execution_state_if_all_steps_pass': 'OFFLINE_HARDENING_ACCEPTED',
    'mutations_require': ['prepared', 'executed', 'intended_assertion_or_sanitizer_finding', 'no_unrelated_prerequisite_failure'],
    'failed_attempt_policy': {'create_only': True, 'retain_all': True, 'unchanged_retry': False,
                              'unexplained_consecutive_failure_pause_threshold': 2},
    'normal_next_step_requires_new_confirmation': False,
    'contract': {'path': str(CONTRACT), 'pin': pin(CONTRACT), 'budgets_ns': BUDGETS,
                 'other_profiles_keep_own_pins': True},
    'model_dimensions': {'NX': 8, 'NU': 2, 'N': 20, 'NP': 6, 'NPG': 30},
    'finite_F6_existing_tolerance': 1e-8,
    'project_level_write_exception': {'only_at': 'E10', 'path': str(REPO / '.sgh-research/research-innovations.md'),
                                      'append_corrective_review_only': True, 'preimage_pin_diff_required': True},
    'qualification': QUALIFICATION, 'production_B_mode': 'MANUAL+RC override',
}
write_json('postrun/execution_plan_v1.json', plan)
checklist = ['step_id\tdepends_on\tstatus\ttask\trelease_gate\tevidence\n']
for step in steps:
    checklist.append('\t'.join([step['id'], ','.join(step['depends_on']) or '-', 'NOT_STARTED', step['title'],
                                step['release_gate'], ';'.join(step['evidence_required'])]) + '\n')
with (ROOT / 'postrun/execution_checklist_v1.tsv').open('x', encoding='utf-8') as out:
    out.writelines(checklist)

baseline = json.loads((PREVIOUS / 'evidence/inputs_before_v1.json').read_text())
supplement = json.loads((PREVIOUS / 'evidence/supplemental_inputs_before_v1.json').read_text())
primary_check = verify_files(baseline['files'])
supplement_check = verify_files(supplement['files'])
workspace_check = verify_files(baseline['workspace_files'])
historical_added = []
for batch in baseline['batches']:
    historical_added.extend(str(p) for p in nonbuild_files(batch) if str(p) not in baseline['files'])
porcelain = subprocess.run(['git', '-C', str(REPO), 'status', '--porcelain=v1', '-uall'],
                           check=True, capture_output=True, text=True).stdout
git_same = porcelain == baseline['git_porcelain']
previous_files = {str(p): pin(p) for p in sorted(nonbuild_files(PREVIOUS))}
inputs = {**previous_files, str(CONTRACT): pin(CONTRACT)}
write_json('evidence/planning_inputs_v1.json', {
    'schema': 'schemeA-controlled-plan-inputs-v125', 'recorded_at': now,
    'files': inputs, 'count': len(inputs), 'scope': '124非build人口与本计划固定合同；不声称包含全部历史build',
    'previous_protection_manifests': [str(PREVIOUS / 'evidence/inputs_before_v1.json'),
                                      str(PREVIOUS / 'evidence/supplemental_inputs_before_v1.json')],
    'previous_primary_comparison': primary_check, 'previous_supplement_comparison': supplement_check,
    'workspace_comparison': workspace_check, 'git_porcelain': porcelain,
    'git_matches_124': git_same, 'historical_population_added': historical_added,
})
write_json('evidence/final_verification_v1.json', {
    'schema': 'schemeA-controlled-plan-verification-v125', 'recorded_at': now,
    'scope': '计划人口/一致性/预算/保护核对，不是E00或任何组件实现验收',
    'planning_complete': True, 'implementation_steps_started': 0,
    'steps_exact': [s['id'] for s in steps], 'all_steps_NOT_STARTED': True,
    'strict_sequential_dependencies': True, 'findings_assigned': 10,
    'document_json_requirements_identical': True, 'fixed_budgets_match_actual_contract': True,
    'document_sha256': pin(DOC)['sha256'],
    'primary_protected_check': primary_check, 'supplemental_protected_check': supplement_check,
    'workspace_ordinary_check': workspace_check, 'git_porcelain_matches_124': git_same,
    'historical_population_added': historical_added,
    'planning_input_files_rechecked': verify_files(inputs),
    'code_fixes_implemented': False, 'single_innovation_register_edited': False,
    'ROS_initialized': False, 'owned_runs_this_batch': 0, 'survivor_role_started': False,
    'qualification': QUALIFICATION, 'production_B_mode': 'MANUAL+RC override',
    'protection_scope': baseline['scope'] + '; 另核对10个补充文件和22个工作区普通文件；dirty子模块不作内容全量保证',
})
assert primary_check['all_match'] and supplement_check['all_match'] and workspace_check['all_match']
assert not historical_added and git_same
print(json.dumps({'plan_steps': len(steps), 'execution_steps_started': 0, 'document_sha256': pin(DOC)['sha256'],
                  'protected_old_files_verified': primary_check['count'] + supplement_check['count'],
                  'workspace_files_preserved': workspace_check['count'], 'planning_input_count': len(inputs),
                  'git_status_unchanged': git_same, 'qualification': QUALIFICATION}, ensure_ascii=False))
