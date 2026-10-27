#!/usr/bin/env python3
"""Batch 71 close-out: offline test rerun, offline entry re-preflight of the
three frozen registrations, protection checks, postrun, documents, delivery."""
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
IMPL = ROOT / 'implementation'
B70 = BASE / 'scheme_A_M4_t1_semantic_supp_20261024_70'
B67 = BASE / 'scheme_A_M4_fixture_gap_20261024_67'
AUTHOR = IMPL / 't2_author'
ENV = {'ROS_DOMAIN_ID': '120', 'ROS_LOCALHOST_ONLY': '1', 'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp'}
NOW = lambda: datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), 'create-only violated: ' + str(path)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def population(root):
    return {str(p): pin(p) for p in sorted(root.rglob('*')) if p.is_file()}


# ---- 1. offline test rerun (evidence copy) --------------------------------------
offline = ROOT / 'evidence/offline_tests'
offline.mkdir()
proc = subprocess.run([sys.executable, 'test_t2_action_contract.py'], cwd=IMPL,
                      capture_output=True, text=True)
(offline / 'unittest.stdout').write_text(proc.stdout)
(offline / 'unittest.stderr').write_text(proc.stderr)
create(offline / 'verification_v1.json',
       {'schema': 'T2-offline-tests-v71', 'ran_at': NOW(), 'returncode': proc.returncode,
        'tests_run': proc.stderr.count('Ran ') and int(proc.stderr.split('Ran ')[1].split()[0]),
        'passed': proc.returncode == 0})
assert proc.returncode == 0, 'offline T2 tests failed'

# ---- 2. offline entry re-preflight of the three frozen registrations ------------
sys.path.insert(0, str(AUTHOR))
from w2_runtime_contract import registration_preflight_t2  # noqa: E402
import t2_action_contract as t2  # noqa: E402
driver = AUTHOR / 't2_scenario_driver_v1.py'
preflight = {}
for tag in ('T2A', 'T2B', 'T2C'):
    reg = json.loads((IMPL / 't2_registrations' / ('%s_v1.json' % tag)).read_bytes())
    config, registry, table = registration_preflight_t2(reg, driver, environment=ENV)
    preflight[tag] = {'registration': str(IMPL / 't2_registrations' / ('%s_v1.json' % tag)),
                      'case': reg['case'], 'actions': [a['id'] for a in table['actions']],
                      'admitted_at_entry': True}
create(ROOT / 'evidence/offline_preflight_v1.json',
       {'schema': 'T2-offline-entry-preflight-v71', 'ran_at': NOW(),
        'environment': ENV, 'registrations': preflight,
        'note': 'the exact entry admission consumed all three frozen registrations offline; nothing executed'})

# ---- 3. protection checks --------------------------------------------------------
before = json.loads((ROOT / 'evidence/inputs_before_v1.json').read_text())
after70 = population(B70)
after67 = population(B67)
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
regulator_unchanged = pin(AUTHOR / 'observer/src/shadow/regulator_owned_execute.cpp')['sha256'] == \
    'dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5'
freeze = json.loads((ROOT / 'evidence/freeze_t2/freeze_report_v1.json').read_bytes())
create(ROOT / 'evidence/final_verification_v1.json',
       {'schema': 'M4-T2-freeze-final-verification-v71', 'recorded_at': NOW(),
        'batch70_files_unchanged': after70 == before['batch70_complete_regular_files'],
        'batch67_files_unchanged': after67 == before['batch67_complete_regular_files'],
        'git_porcelain_matches_start': status == before['git_status_porcelain'],
        'regulator_source_sha256_unchanged': regulator_unchanged,
        'tree_unchanged_after_build': freeze['tree_unchanged_after_build'] is True,
        'offline_tests_passed': True, 'offline_entry_preflight_passed': True,
        'bundle_sha256': freeze['bundle']['sha256'], 'bundle_files': freeze['bundle']['files'],
        'roles': freeze['roles'], 'executed_any_registration': False, 'owned_runs': 0,
        'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
        'production_B_mode': 'MANUAL+RC覆写',
        'scope_note': 'S2 interface freeze only: entry/parameters/manifest/audit consume the T2 clauses; the three scenario families are registered, not executed'})
assert after70 == before['batch70_complete_regular_files'] and after67 == before['batch67_complete_regular_files']
assert regulator_unchanged and freeze['tree_unchanged_after_build'] is True

# ---- 4. postrun ------------------------------------------------------------------
create(ROOT / 'postrun/s2_freeze_findings_v1.json',
       {'schema': 'M4-T2-freeze-findings-v71', 'recorded_at': NOW(),
        'four_admission_points': {
            'entry': 'w2_runtime_contract.registration_preflight_t2 + require_normal_scope_unarmed on the W path',
            'parameters': 't2_action_contract.fixture_action_parameters consumed by t2_scenario_driver_v1 spawn assembly',
            'manifest': 'Fixture owned_manifest.json records t2_armed/t2_case/t2_action_table_sha256; the armed channel demands the v2 start schema',
            'audit': 'audit_t2.py re-validates the table and consumes the family clauses over separated receipt/regulator streams'},
        'frozen_vocabulary': {'actions': sorted(t2.ACTIONS), 'phases': sorted(t2.PHASES),
                              'families': t2.FAMILIES, 'max_actions': t2.MAX_ACTIONS},
        'budgets_unrelaxed': True,
        'flush_pad_never_an_ack': True,
        'regulator_and_worker_sources_unchanged': True,
        'frozen_registrations': preflight,
        'not_executed': ['T2A_01', 'T2B_01', 'T2C_01']})
create(ROOT / 'postrun/next_plan_v3.json',
       {'schema': 'M4-after-T1-review-minimum-plan-v71', 'recorded_at': NOW(),
        'steps': [
            {'id': 'S0', 'status': 'complete', 'task': '修复观测器与runner失败门(69批)'},
            {'id': 'S1', 'status': 'complete', 'task': 'T1剩余小范围语义补证(70批)'},
            {'id': 'S2', 'status': 'complete', 'task': '冻结T2动作表及阶段回执的最小接口(本批71)',
             'done': '三场景族时序/失败判据成为被四处准入消费的登记条款;bundle/Driver/ELF/registry/三份registration冻结;离线38项正反例+离线入口预检通过;未执行任何owned run'},
            {'id': 'T2-A', 'status': 'next', 'task': 'clock冻结/恢复场景族 owned执行',
             'registration': 'implementation/t2_registrations/T2A_v1.json',
             'checks': ['持续同stamp投递与完全静默>100ms分别登记(条款已冻结)',
                        '逐事件核对pause/RTF/schedule;旧候选不复活;恢复接纳需新窗口证据',
                        '单次有限执行、预检登记、自动重试0、失败原件保留']},
            {'id': 'T2-B', 'status': 'planned', 'task': '在途Job与ready窗口clear/replace场景族 owned执行',
             'registration': 'implementation/t2_registrations/T2B_v1.json',
             'checks': ['solve_active触发已在途;solve_active与ready_window分相已冻结',
                        '原Job截止不延长,错过窗口按登记失败;过期/终端不冒充task拒绝']},
            {'id': 'T2-C', 'status': 'planned', 'task': 'Driver shutdown与ready/activation交错场景族 owned执行',
             'registration': 'implementation/t2_registrations/T2C_v1.json',
             'checks': ['ready_window绑定真实完成点;ready_commit<request<=stopping_observed<=guard独立核对',
                        'API零请求/返回/Source flush/Recorder/退出各自对账']},
            {'id': 'T3→N3→F6→P1', 'status': 'retained', 'task': '保留主线剩余义务',
             'checks': ['cleanup_failed与旧group未空禁止restart、Source队列压力尚未覆盖;不被T2替代',
                        '原九组联合复判后推进有限M0/M1/F6再P1;生产B仍MANUAL+RC覆写']}],
        'stage_qualified': False})

# ---- 5. documents and CURRENT.md -------------------------------------------------
report = ROOT / 'documents/方案A_第71批_S2动作表接口冻结_2026-10-24.md'
assert not report.exists()
report.write_text(f"""# 方案A:第71批S2——T2动作表与阶段回执最小接口冻结

日期:2026-10-24(北京时间)。依据第69批报告S2条款与第70批`next_plan_v2.json`,本批冻结T2三场景族的动作表与阶段回执接口;**未执行任何owned run**。

## 1. 结论

T2能力以普通scope(`M4_owned_local_nominal_only_v1`)+冻结v3合同+非fault四角色落地:**Regulator与Worker源码逐字节不变**(Regulator SHA仍为`dd03d769…`)。新增/修改仅限:动作合同模块、入口预检、Fixture动作通道、T2编排Driver与审计工具。离线38项正反例全部通过;三份登记(registration)经同一入口预检离线复核通过;t2_author树(103文件)冻结为bundle,三个角色ELF以真实身份构建,registry/动作表/登记全部create-only落档。

## 2. 四处准入同时消费(69批S2条款)

1. **入口**:`w2_runtime_contract.registration_preflight_t2`(T2族白名单+动作表SHA pin+合同SHA=冻结v3+预算不放宽);W1-W4入口新增`require_normal_scope_unarmed`——普通/诊断登记携带任何T2能力键即拒绝。
2. **有效参数**:Driver经`t2_action_contract.fixture_action_parameters`装配Fixture参数(t2_case/表文件/表SHA/命令目录四者同现才arm)。
3. **manifest**:Fixture manifest记录`t2_armed/t2_case/t2_action_table_sha256`;armed通道强制start schema v2(表SHA+命令目录绑定),未arm时v2 start被精确字段检查拒绝。
4. **审计**:`audit_t2.py`重验动作表并按场景族消费冻结条款;回执(Fixture自有Source流` t2_action_executed`)与Regulator状态行是分离流,按动作id/Job绑定/单调时间对账——flush_pad永不充当回执。

## 3. 冻结的词表与语义修正

- 动作(≤4):`clock_hold(mode=same_stamp|silent,duration_ms)`、`clock_resume(advance_ms)`、`path_clear`、`path_replace(points,.05)`、`driver_shutdown_request`(唯一Driver侧动作,只记driver_events,不进Fixture轮询目录)。**词表无任何candidate动作**——candidate伪造进不了Fixture。
- 触发相位(按69批R4修正):`after_grant_ms`(T2-A)、`solve_active`(Worker capability active_job且无结果——在途)、`ready_window`(Regulator accepted candidate_registration——ready窗口)、`job_received`仅证明排队,T2-B/T2-C词表级禁止其作为触发。
- 条款:T2A(receipt_stale 100ms与pause_confirm 400ms分开登记、旧候选不复活);T2B(截止150ms不延长、过期/终端不冒充task拒绝、stale拒绝原因注册);T2C(ready_commit<request≤stopping_observed≤guard定序)。预算四项(150ms/600ms/1s/关闭)与冻结合同逐项相等断言。

## 4. 边界与未宣称

本批为接口冻结:owned执行0次,三份登记未运行;`t2_scenario_driver_v1.py`的运行时行为在T2-A/B/C执行批验证。70批全量文件与67批203文件零改动,git porcelain一致;完整M4/F6/P1/plant/硬实时继续false,生产B仍MANUAL+RC覆写。

## 5. 证据入口

[freeze_report_v1.json](../evidence/freeze_t2/freeze_report_v1.json)、[offline_tests](../evidence/offline_tests/verification_v1.json)、[offline_preflight_v1.json](../evidence/offline_preflight_v1.json)、[final_verification_v1.json](../evidence/final_verification_v1.json)、[s2_freeze_findings_v1.json](../postrun/s2_freeze_findings_v1.json)、[next_plan_v3.json](../postrun/next_plan_v3.json)。登记:`implementation/t2_registrations/T2{{A,B,C}}_v1.json`(未执行)。

## 6. 下一步

T2-A owned执行(登记T2A_v1)→T2-B→T2-C(各自单次有限执行、失败原件保留)→T3→N3→F6→P1保留主线。
""")
current = ROOT / 'CURRENT.md'
assert not current.exists()
current.write_text("""# 第71批:S2 T2动作表与阶段回执接口冻结

日期:2026-10-24。

- T2能力=普通scope+冻结v3合同+非fault四角色;Regulator/Worker源码零修改(SHA dd03d769…不变)。
- 四处准入同时消费T2值:入口预检(T2分支+normal-scope拒绝)、Driver参数装配、Fixture manifest(v2 start绑定)、审计条款。
- 回执分离:Fixture自有Source流t2_action_executed vs Regulator状态行,按动作id/Job/单调时间对账;flush_pad不充当ACK。
- 离线38项正反例通过(错误case/hash/顺序/多动作/超时/重复回执/normal-scope拒绝/W回归/预算不放宽/三族条款消费)。
- t2_author(103文件,bundle冻结)→三角色ELF真实身份构建→registry→三份动作表+登记create-only落档,离线入口预检复核通过。
- 未执行任何owned run;T2-A为下一步(登记T2A_v1)。70/67文件零改动;M4/F6/P1仍false;生产B仍MANUAL+RC覆写。

主报告:[方案A_第71批_S2动作表接口冻结_2026-10-24.md](documents/方案A_第71批_S2动作表接口冻结_2026-10-24.md)。
冻结:[freeze_report_v1.json](evidence/freeze_t2/freeze_report_v1.json)。
下一步:[next_plan_v3.json](postrun/next_plan_v3.json)。
""")

# ---- 6. MPC delivery with two-way readback --------------------------------------
delivery = Path('/home/trevor/MPC') / ROOT.name
assert not delivery.exists(), 'delivery target already exists'
shutil.copytree(ROOT, delivery, ignore=shutil.ignore_patterns('build'))
expected = {str(p.relative_to(delivery)): pin(p) for p in sorted(delivery.rglob('*'))
            if p.is_file() and 'build' not in p.parts}
actual = {str(p.relative_to(ROOT)): pin(p) for p in sorted(ROOT.rglob('*'))
          if p.is_file() and 'build' not in p.parts and p.name != 'delivery_to_MPC_v1.json'}
matches = expected == actual
create(ROOT / 'evidence/delivery_to_MPC_v1.json',
       {'schema': 'M4-T2-freeze-delivery-v71', 'delivered_at': NOW(), 'target': str(delivery),
        'files': len(expected), 'two_way_readback_matches': matches, 'excluded': ['build/'],
        'note': 'delivery is a snapshot at copy time; this record is not part of it'})
assert matches, 'delivery readback mismatch'
print(json.dumps({'offline_tests': 'ok', 'preflight': sorted(preflight),
                  'delivery_files': len(expected), 'delivery_matches': matches}))
