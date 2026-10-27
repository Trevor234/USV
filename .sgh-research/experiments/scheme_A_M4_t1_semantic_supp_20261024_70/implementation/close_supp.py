#!/usr/bin/env python3
"""Batch 70 close-out: verdict tests, case readback, coverage update, postrun,
documents, MPC delivery and final verification. Reads the newest attempt."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
B69 = BASE / 'scheme_A_M4_t1_review_20261024_69'
B67 = BASE / 'scheme_A_M4_fixture_gap_20261024_67'
NOW = lambda: datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), f'create-only violated: {path}'
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def population(root):
    return {str(p): pin(p) for p in sorted(root.rglob('*')) if p.is_file()}


# ---- 1. newest complete attempt ------------------------------------------------
attempts = sorted((ROOT / 'evidence/supp_t1').glob('attempt*'))
attempt = None
for candidate in attempts:
    report = candidate / 'verification_v1.json'
    if report.exists() and json.loads(report.read_text())['complete']:
        attempt = candidate
assert attempt is not None, 'no complete attempt'
verification = json.loads((attempt / 'verification_v1.json').read_text())
run_dir = attempt / 'nominal_run01'
assert verification['nominal']['all_passed'] and verification['identities_unchanged']

# ---- 2. the 17 strict verdict unit tests (module reused verbatim from 69) ------
assert (ROOT / 'implementation/runner_verdict_v2.py').read_bytes() == \
       (B69 / 'implementation/runner_verdict_v2.py').read_bytes(), 'verdict module drifted from 69'
verdict_dir = ROOT / 'evidence/verdict_tests'
verdict_dir.mkdir()
proc = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_runner_verdict_v2'],
                      cwd=ROOT / 'implementation', capture_output=True, text=True)
(verdict_dir / 'unittest.stdout').write_text(proc.stdout)
(verdict_dir / 'unittest.stderr').write_text(proc.stderr)
create(verdict_dir / 'verification_v1.json',
       {'schema': 'T1-S1-verdict-tests-v70', 'ran_at': NOW(), 'returncode': proc.returncode,
        'tests_run': proc.stderr.count('... ok') + proc.stderr.count('ok)'),
        'module_identical_to_69': True,
        'passed': proc.returncode == 0})
assert proc.returncode == 0, 'verdict unit tests failed'

# ---- 3. per-case terminal readback (32 cases, pad bytes, source_summary) -------
cases = {}
for case in sorted((run_dir / 'cases').iterdir()):
    rows = [json.loads(line) for line in (case / 'source.jsonl').read_text().splitlines() if line.strip()]
    summary = [row for row in rows if row.get('type') == 'source_summary']
    pads = [row for row in rows if row.get('type') == 't1_component_flush_pad']
    assert len(summary) == 1, f'missing terminal summary in {case.name}'
    terminal = summary[0]
    cases[case.name] = {
        'events': len(rows),
        'generated': terminal['generated'], 'emitted': terminal['emitted'], 'dropped': terminal['dropped'],
        'pad_bytes': [len(row.get('filler', '')) for row in pads],
        'normal_source_complete': terminal.get('normal_source_complete')}
assert len(cases) == 32
assert all(row['generated'] == row['emitted'] and row['dropped'] == 0 for row in cases.values())
assert all(size == 8200 for row in cases.values() for size in row['pad_bytes'])
create(ROOT / 'evidence/source_terminal_readback_v1.json',
       {'schema': 'T1-S1-source-terminal-readback-v70', 'recorded_at': NOW(),
        'attempt': str(attempt), 'cases': cases,
        'claim': 'every executed case shows a complete terminal source stream (generated==emitted, dropped==0) and real 8200-byte pad payloads'})

# ---- 4. atom coverage update ----------------------------------------------------
S1_NOTES = {
    'candidate_identity_shape.01': 'three boolean rejection gates now each isolated: prediction_available=false (69), success=false and solver_invoked=false (70), all rejecting with solver_failed while the accepted registration is preserved',
    'candidate_identity_shape.02': 'Job horizon/dt metadata gate (shape_or_time_contract) distinguished from native result shape; native dimensions fixed by the wire contract (126/40/2) as constructive evidence, no bad-shape native experiment claimed',
    'candidate_identity_shape.08': 'version rejection dimensions enumerated per the frozen contract: model (isolated 68/69), task/config/schedule (70 ReferenceOrdinaryNewOdomActivation), clock epoch via the state_clock cases',
    'task_reference.03': 'ready-window invalidation proven (69); the in-flight window before ready is now proven on the REAL prepare_loop path (version_changed_before_submit, stale result version_mismatch, new-generation positive control)',
    'task_reference.04': 'ready-window replacement proven (69); in-flight replacement window proven on the REAL prepare_loop path in the same 70 case',
    'task_reference.07': 'eligible check (69) extended with a REAL activation through admission take and the task/config/schedule rejection dimensions (70)',
    'publication_exit.02': 'echo-based committed-submit clear (69) plus REAL prepare_loop submit facts: a real echo admits a result without seed_echo, and shutdown/version changes block the real submit with explicit reasons',
    'publication_exit.03': 'ready-window shutdown rejection (69) plus the real submit-path shutdown guard (shutdown_before_submit); the owned ready/activation interleave remains T2-C',
    'state_clock.04': 'component wiring proven (68/69); owned pause/resume timing remains the T2-A scenario family',
    'state_clock.05': 'component wiring proven (68/69); owned resume scheduling remains the T2-A scenario family',
}
HANDOFF_ATOMS = ['state_clock.04', 'state_clock.05', 'task_reference.03', 'task_reference.04', 'publication_exit.03']
import ast
spec_tree = ast.parse((ROOT / 'evidence/spec68/scripts/run_t1.py').read_text())
atom_map = next(ast.literal_eval(node.value) for node in spec_tree.body
                if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'ATOM_MAP')
atoms = []
for atom, tests in atom_map.items():
    if atom in HANDOFF_ATOMS:
        status = 'component_evidence_extended__t2_owned_pending'
    else:
        status = 'proven_component_scope'
    atoms.append({'atom': atom, 'tests': tests, 's1_status': status,
                  's1_note': S1_NOTES.get(atom, 'no new S1 stimulation required; 68/69 evidence stands for the stated scope'),
                  'evidence': {'attempt': str(attempt),
                               'case_dirs': [str(run_dir / 'cases' / name.split('.')[-1]) for name in tests]}})
assert len(atoms) == 23
create(ROOT / 'postrun/atom_coverage_update_v1.json',
       {'schema': 'M4-T1-S1-atom-coverage-update-v70', 'recorded_at': NOW(),
        'based_on': ['68 ATOM_MAP (evidence/spec68/scripts/run_t1.py)',
                     '69 revised_next_plan_v1.json S1 checks'],
        'atoms': atoms,
        'counts': {'atoms_total': 23, 't2_handoff_atoms': 5,
                   'other_atoms': 18, 'previous_incorrect_other_count': 19,
                   'correction': 'the 69 report corrected the old "19 others" count; this batch records 23-5=18'},
        'claims_guard': '32 executions passing does not imply full semantic closure; each atom status states the exact stimulated scope',
        'mutations': [row['name'] for row in verification['mutations'] if row['assertion_caught']]})

# ---- 5. S1 findings and the S2 next plan ----------------------------------------
observed = {}
for name in ('RealSubmitBlockedByVersionChangeBeforeSubmit', 'RealSubmitBlockedByShutdownBeforeSubmit'):
    rows = [json.loads(line) for line in (run_dir / 'cases' / name / 'source.jsonl').read_text().splitlines() if line.strip()]
    observed[name] = [row.get('reason') for row in rows if row.get('type') == 'job_not_submitted']
create(ROOT / 'postrun/s1_findings_v1.json',
       {'schema': 'M4-T1-S1-findings-v70', 'recorded_at': NOW(),
        's1_checks': [
            'success=false and solver_invoked=false each isolated: solver_failed rejection with the accepted registration preserved (CandidateSuccessFalseAloneRejected, CandidateSolverNotInvokedAloneRejected)',
            'Job horizon/dt metadata distinguished from native result shape; fixed 126/40/2 wire dimensions as constructive evidence (NativePredictionShapeFixedByConstruction)',
            'REAL prepare_loop submission obtained: reference_epoch_committed -> job -> job_publish_result, and the real echo admits a result without seed_echo (RealPrepareLoopSubmitsJob)',
            'shutdown/version-change insertion on the real submit path blocks submission with explicit reasons (RealSubmitBlockedByShutdownBeforeSubmit, RealSubmitBlockedByVersionChangeBeforeSubmit)',
            'in-flight not-yet-ready window: stale result rejected with version_mismatch; new task generation registers, holds the slot and really activates (same case)',
            'ordinary new odom followed by a REAL activation; task/config/schedule version dimensions reject explicitly (ReferenceOrdinaryNewOdomActivation)'],
        'observed_real_submit_blocks': observed,
        'test_design_note': 'a rejected candidate submission leaves its seeded echo in jobs_; distinct job_ids are required for follow-up registrations (observed as job_echo_mismatch in attempt02, fixed in attempt03)',
        'attempts': {'failed_kept': [str(p) for p in attempts if p != attempt], 'complete': str(attempt)},
        'regulator_source_unchanged': True})
create(ROOT / 'postrun/next_plan_v2.json',
       {'schema': 'M4-after-T1-review-minimum-plan-v70', 'recorded_at': NOW(),
        'steps': [
            {'id': 'S0', 'status': 'complete', 'task': '修复观测器与runner失败门(69批)'},
            {'id': 'S1', 'status': 'complete', 'task': 'T1剩余小范围语义补证,Regulator源码原样',
             'evidence': [str(attempt / 'verification_v1.json'), 'postrun/atom_coverage_update_v1.json'],
             'done': '23项覆盖更新为已证范围/仍需T2;18项非移交原子计数修正落档;未宣称全覆盖'},
            {'id': 'S2', 'status': 'next', 'task': '冻结T2动作表及阶段回执的最小接口',
             'code_targets': ['new owned author derived from frozen66 (67 current_author, bundle 732a3549...)',
                              'fixture/synthetic_source_m4.cpp action table',
                              'owned_m4_diagnostic_driver_v1.py', 'w2_runtime_contract.py',
                              'Regulator diagnostic-case/parameter admission'],
             'checks': ['create-only动作表固定run/case/合同SHA、有限动作和触发Job/版本/阶段;既有Fixture writer执行,candidate伪造不进Fixture',
                        '新增T2值须在入口(w2_runtime_contract.py白名单)、有效参数(Driver装配)、manifest与审计(w2_audit_common/audit_w2)同时消费;normal scope拒绝这些能力',
                        '动作executed回执与Regulator callback/状态变更回执分开;按完整Job/版本/单调时间核对,不用测试flush_pad充当生产ACK',
                        '先离线正反例验证错误case/hash/顺序/多动作/超时/重复回执;不放宽原150ms截止、600ms租约、1s watchdog或关闭预算']},
            {'id': 'T2-A', 'status': 'planned', 'task': 'clock冻结/恢复场景族',
             'checks': ['持续投递相同clock stamp保持receipt新鲜与完全静默>100ms的clock stale分别登记',
                        '原>400ms pause、RTF无效与schedule失效逐事件核对;resume明确sim与odom/imu stamp映射',
                        '旧候选不复活;恢复接纳需新窗口有效性和新Job接受证据']},
            {'id': 'T2-B', 'status': 'planned', 'task': '在途Job与ready窗口的clear/replace场景族',
             'checks': ['job_received只证明收到/排队;在途触发须确认同一Job已active或进入计算边界且未产出结果;candidate_received另标ready窗口',
                        '必要时复用已认证有限boundary/release组件;原Job截止绝不延长,错过窗口按登记失败',
                        '区分因旧task被拒与因过期/Worker终端未产生候选;clear与replace不能独立归因则拆子case']},
            {'id': 'T2-C', 'status': 'planned', 'task': 'Driver shutdown与ready/activation交错场景族',
             'checks': ['ready确认绑定目标Job及真实完成点;先确认异步Source文件窗口内可靠观测',
                        '文件可见性不足再加仅诊断有界ACK/gate;通知非阻塞、不持业务锁、normal scope不放行',
                        '独立核对ready_commit<request<=stopping_observed<=activation_guard;各角色退出对账']},
            {'id': 'T3→N3→F6→P1', 'status': 'retained', 'task': '保留主线剩余义务',
             'checks': ['cleanup_failed与旧group未空禁止restart、Source队列压力尚未覆盖;不被T2三场景族替代',
                        '每个实际owned case先预检登记、单次有限执行、自动重试0、失败原件保留',
                        '原九组联合复判后才推进有限M0/M1模型事务/F6,再P1;生产B仍MANUAL+RC覆写']}],
        'stage_qualified': False, 'owned_runs_in_70': 0})

# ---- 6. final verification: inputs unchanged ------------------------------------
before = json.loads((ROOT / 'evidence/inputs_before_v1.json').read_text())
after69 = population(B69)
after67 = population(B67)
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
unchanged69 = after69 == before['batch69_complete_regular_files_including_build']
unchanged67 = after67 == before['batch67_complete_regular_files']
create(ROOT / 'evidence/final_verification_v1.json',
       {'schema': 'M4-T1-S1-final-verification-v70', 'recorded_at': NOW(),
        'batch69_files_unchanged': unchanged69, 'batch69_files': len(after69),
        'batch67_files_unchanged': unchanged67, 'batch67_files': len(after67),
        'git_porcelain_matches_start': status == before['git_status_porcelain'],
        'regulator_source_sha256': pin(B67 / 'implementation/current_author/observer/src/shadow/regulator_owned_execute.cpp')['sha256'],
        'regulator_source_expected': 'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5',
        'nominal_32_of_32': verification['nominal']['all_passed'],
        'mutations_caught': [row['name'] for row in verification['mutations'] if row['assertion_caught']],
        'identities_unchanged': verification['identities_unchanged'],
        'verdict_tests_passed': proc.returncode == 0,
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'owned_runs': 0, 'production_B_mode': 'MANUAL+RC覆写',
        'scope_note': 'component-level source-linked evidence only; component ROS context and test publishers exist, no control DataWriter, no owned four-role run'})
assert unchanged69 and unchanged67, 'protected inputs drifted'
assert pin(B67 / 'implementation/current_author/observer/src/shadow/regulator_owned_execute.cpp')['sha256'] == \
       'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'

# ---- 7. documents and CURRENT.md -------------------------------------------------
report_path = ROOT / 'documents/方案A_第70批_S1语义补证与覆盖结论更新_2026-10-24.md'
assert not report_path.exists()
attempt_id = attempt.name
report_md = f"""# 方案A:第70批S1语义补证与覆盖结论更新

日期:2026-10-24(北京时间)。依据第69批复核报告第7节与`revised_next_plan_v1.json`,本批执行S1:T1剩余小范围语义补证,Regulator源码保持原样(SHA `dd03d769…f6b5`,第67批current_author只读)。

## 1. 结论

25项68/69复核用例逐字节保留,新增7项S1补证用例,共32项在同一harness一次执行全部通过;3个指定变异仍被原断言捕获并经严格判定(完整人口、RUN/COMPLETED、RC1、精确命名断言、源码身份前后pin一致)。17项判定器单元测试通过(模块与69逐字节相同)。失败尝试(attempt01-03,含编译错误与两轮测试修正)原件保留。

## 2. 五项S1检查的落点与证据

1. **布尔门隔离**:`CandidateSuccessFalseAloneRejected`、`CandidateSolverNotInvokedAloneRejected`分别仅置success=false或solver_invoked=false,均以`solver_failed`拒绝且已接纳注册保留;prediction_available=false单独门69已补,三个布尔门至此各自隔离。
2. **Job元数据与原生结果shape区分**:`NativePredictionShapeFixedByConstruction`以`static_assert`固定SolveCandidate消息维度(x_prediction 126=21×6、u_prediction 40=20×2、first_control 2、Job reference 126)作为构造性证据;Job horizon/dt非法保持`shape_or_time_contract`元数据拒绝单列。本批不做坏shape原生实验,wire类型本身使错维不可表达。
3. **真实prepare_loop提交**:`RealPrepareLoopSubmitsJob`经C33MatrixAccess缝组装真实Snapshot→pending_→真实prepare_loop线程,取得`reference_epoch_committed → job → job_publish_result`完整事实;**prepare_loop写入的真实echo使结果无需seed_echo即被接纳**(accepted_registration=true)。测试缝内为组件补建`/p1_test/solve_job`测试publisher(ShadowTestTag构造不创建job_pub_),与既有test decision publisher同一披露口径。
4. **提交守卫**:`RealSubmitBlockedByShutdownBeforeSubmit`与`RealSubmitBlockedByVersionChangeBeforeSubmit`在真实提交守卫窗口注入shutdown/version变更,分别以`shutdown_before_submit`、`version_changed_before_submit`拒绝且无echo、无提交;在途旧结果事后提交以`version_mismatch`拒绝。
5. **在途窗口与正控**:同一用例内,新task代际注册成功、槽位=1、经真实admission take激活(control_source=candidate)。普通new odom用例(`ReferenceOrdinaryNewOdomActivation`)实际尝试激活成功,并按冻结合同逐维核对task/config/schedule版本拒绝(model在.08、epoch在clock用例)。

观察细节:被拒绝的candidate提交会把已seed的echo留在jobs_,后续注册需独立job_id(attempt02反例保留);替换参考后须补齐profile配对,否则激活门以`profile_pair_incomplete`回退ramp_zero(attempt03反例保留)。

## 3. 覆盖结论更新(S1完成条件)

23项原子逐项标注"已证范围/仍需T2":18项非移交原子为proven_component_scope;5项移交原子(state_clock.04/05、task_reference.03/04、publication_exit.03)中,task_reference.03/04与publication_exit.03本批新增组件级在途/真实提交证据,owned场景族仍登记待执行。旧"其余19项"计数错误修正为18项(23−5)。32项通过不等于全覆盖:各项status写明实际刺激面,见[atom_coverage_update_v1.json](../postrun/atom_coverage_update_v1.json)。

## 4. 边界与未宣称

本批为组件级source-linked证据:初始化rclcpp组件ROS上下文、创建`/p1_test/shadow_decision`与`/p1_test/solve_job`测试publisher,无控制DataWriter,owned四角色执行0次。完整M4/F6/P1/plant/硬实时/研究结论继续false;生产B仍MANUAL+RC覆写。测试flush_pad仅为可见性辅助,36+条pad为真实8200字节,不充当生产ACK。

## 5. 保护、交付与证据入口

69全760文件、67全203文件内容与本批接手时一致,git porcelain一致;失败attempt与全部证据create-only保留。证据入口:[verification_v1.json](../evidence/supp_t1/{attempt_id}/verification_v1.json)、[source_terminal_readback_v1.json](../evidence/source_terminal_readback_v1.json)、[verdict_tests](../evidence/verdict_tests/verification_v1.json)、[s1_findings_v1.json](../postrun/s1_findings_v1.json)、[next_plan_v2.json](../postrun/next_plan_v2.json)。

## 6. 下一步

S2:冻结T2动作表及阶段回执最小接口(自frozen66派生新owned author;入口/有效参数/manifest/审计四处同时消费新增T2值;动作回执与Regulator回执分离;先离线正反例;不放宽150ms/600ms/1s预算),随后T2-A/B/C三场景族与T3→N3→F6→P1保留主线。
"""
report_path.write_text(report_md)

current = ROOT / 'CURRENT.md'
assert not current.exists()
current.write_text(f"""# 第70批:S1 T1剩余小范围语义补证

日期:2026-10-24。

- 25项68/69复核用例逐字节保留,新增7项S1用例,32/32通过;3变异严格捕获;17项判定器测试通过。
- 真实prepare_loop提交事实落档:reference_epoch_committed→job→job_publish_result,真实echo免seed_echo接纳结果。
- shutdown/version守卫在真实提交路径拒绝(shutdown_before_submit/version_changed_before_submit);在途旧结果version_mismatch;新代际正控注册+激活。
- 布尔门三隔离、定维构造性证据(126/40/2)、普通new odom真实激活+版本维度(task/config/schedule)落档。
- 23原子覆盖更新:18项非移交proven_component_scope,5项移交中3项新增组件级证据、owned待T2;19→18计数修正。
- Regulator源码SHA不变;69/67文件零改动;失败attempt保留;owned=0;M4/F6/P1仍false,生产B仍MANUAL+RC覆写。
- 下步:S2冻结T2动作表接口(frozen66派生,四处准入)→T2-A/B/C→T3→N3→F6→P1。

主报告:[方案A_第70批_S1语义补证与覆盖结论更新_2026-10-24.md](documents/方案A_第70批_S1语义补证与覆盖结论更新_2026-10-24.md)。
覆盖:[atom_coverage_update_v1.json](postrun/atom_coverage_update_v1.json)。
下一步:[next_plan_v2.json](postrun/next_plan_v2.json)。
""")

# ---- 8. MPC delivery with two-way readback --------------------------------------
delivery = Path('/home/trevor/MPC') / ROOT.name
assert not delivery.exists(), 'delivery target already exists'
shutil.copytree(ROOT, delivery, ignore=shutil.ignore_patterns('build'))
expected = {str(p.relative_to(delivery)): pin(p) for p in sorted(delivery.rglob('*'))
            if p.is_file() and 'build' not in p.parts}
actual = {str(p.relative_to(ROOT)): pin(p) for p in sorted(ROOT.rglob('*'))
          if p.is_file() and 'build' not in p.parts and p.name != 'delivery_to_MPC_v1.json'}
matches = expected == actual
create(ROOT / 'evidence/delivery_to_MPC_v1.json',
       {'schema': 'M4-T1-S1-delivery-v70', 'delivered_at': NOW(),
        'target': str(delivery), 'files': len(expected), 'two_way_readback_matches': matches,
        'excluded': ['build/'], 'note': 'delivery is a snapshot at copy time; this record is not part of it'})
assert matches, 'delivery readback mismatch'
final = json.loads((ROOT / 'evidence/final_verification_v1.json').read_text())
final['delivery'] = {'target': str(delivery), 'files': len(expected), 'two_way_readback_matches': True}
(ROOT / 'evidence/final_verification_v1.json').write_text(json.dumps(final, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'attempt': str(attempt), 'cases': len(cases), 'atoms': len(atoms),
                  'unchanged69': unchanged69, 'unchanged67': unchanged67,
                  'delivery_files': len(expected), 'delivery_matches_source': matches}))
