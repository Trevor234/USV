#!/usr/bin/env python3
"""Create-only local seal. Delivery is separate and never inferred from mkdir."""
import argparse
import hashlib
import json
from pathlib import Path
import stat

D = Path(__file__).resolve().parent


def sha(p):
    b = p.read_bytes()
    return dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def put(p, d):
    with p.open('x') as f:
        json.dump(d, f, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def load(rel):
    return json.loads((D/rel).read_text())


def population():
    files, dirs = {}, []
    for p in sorted(D.rglob('*')):
        assert not p.is_symlink(), 'unreviewed archive symlink: '+str(p)
        if p.is_dir():
            dirs.append(str(p.relative_to(D)))
        else:
            assert stat.S_ISREG(p.stat().st_mode)
            files[str(p.relative_to(D))] = sha(p)
    return files, dirs


def prepare():
    current = D/'CURRENT.md'
    with (D/'preflight/CURRENT_initial_v1.md.snapshot').open('xb') as f:
        f.write(current.read_bytes())
    current.write_text('''# 方案A当前状态：第30批（2026-10-19）

本批只读审查/设计完成：16项条件—代码—证据矩阵，五批原窗口独立复算，实际生成库/Worker模型接口检查，以及共同协议/有限模型最小设计。无新增控制功能、构建或闭环运行。

第29批0.05m/s受控名义源已101/101连续接纳、零拒绝，旧case仍因全窗RMSE0.009195365994>0.007392495755失败。减半目标来自第20批诊断预注册；与原P1未完成条件分账，旧判定不改。

现有NP_GLOBAL=30含19项水动力，可复用同生成图准备两独占capsule；当前Worker每run只有一个固定合同后端，模型数值切换/准备/固定tick事务尚未实现。残差/障碍新增参数仍需改图/codegen。所有本批模型值均为待实施设计。

原24处dirty业务改动和已登记real.launch.py差异保留。初检41,167个本地路径、5,039,073,437字节通过；终检见preflight/workspace_final_local_v2.json。74项审查输入前后SHA一致。

组件结果：本批只读审查完成；旧实际接纳组件按精确版本引用。阶段资格：B4/B5/M0b/M4/F6/P1未闭合，execute=false、true_plant=false、research=false。

下步：当前B4的81项配置/政策增量及最终统一版最少确认入口→必要压力/恢复/关闭确认→B5/M0b→M4唯一监管器出口→有限模型事务/F6→复判P1→P2。停止追加首控/RTI/权重调试。见documents/next_implementation_plan_v1.md。

MPC共享盘host检查errno112 Host is down，尚未复制或读回；本批及此前待交付批次均保留本地，delivery_pending=true。归档证据权威见archive_inventory_v1.json，远程成功只认后续真实delivery_verification.json。
''')
    put(D/'batch_status_final.json', dict(schema='P1-scope-audit-status/v1',
        batch=30, date='2026-10-19', scope_audit_completed=True,
        report=str(D/'documents/方案A_P1阶段对照与模型接口审查_2026-10-19.md'),
        code_functionality_added=False, new_control_experiment=False, build=False, codegen=False, install=False,
        parameter_tuning=False, historical_failures_preserved=True,
        component_validation='read-only audit, exact input locks, independent frozen-window arithmetic and static interface capability',
        prior_actual_acceptance='D29 101/101, exact selected roles only',
        prior_case_passed=False, phase_status='P1 partial; B4/B5/M0b/M4/F6 pending',
        stage_qualified=False, execute_qualified=False, true_plant_qualified=False, research_conclusion=False,
        MPC_delivery_pending=True, MPC_error_number=112,
        next_order=['B4 current delta','final unified-version affected confirmation','B5/M0b','M4','finite model transaction/F6','P1 review','P2'],
        next_design=str(D/'documents/next_implementation_plan_v1.md')))


def finalize():
    initial = load('preflight/workspace_initial_local_v2.json')
    final = load('preflight/workspace_final_local_v2.json')
    assert initial['passed'] and final['passed']
    for p in [initial['protection'],final['protection']]:
        assert p['unique_raw_files_reread'] == 41167
        assert p['logical_bytes_streamed'] == 5039073437
        assert p['business_diff_sha256'] == 'd901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5'
        assert p['local_D29_archive_files'] == 961 and p['local_N29_source_files'] == 331
        assert not p['stage_qualified'] and p['D29_original_RMSE_failure_preserved']
    assert initial['protection']['boot_id'] == final['protection']['boot_id']
    lock = load('evidence/audit_input_lock_v1.json')
    assert lock['passed'] and lock['input_sha256_before'] == lock['input_sha256_after']
    assert lock['input_count'] == 74
    for path,pin in lock['input_sha256_before'].items():
        assert sha(Path(path)) == {k:pin[k] for k in ['bytes','sha256']}, 'audit input changed: '+path
        assert str(Path(path).resolve()) == pin['resolved_path']
    comp = load('analysis/frozen_run_comparison_v1.json')
    inter = load('analysis/dynamic_model_interface_v1.json')
    matrix = load('analysis/requirements_code_evidence_matrix_v1.json')
    assert comp['passed'] and inter['passed'] and matrix['passed']
    assert [r['batch'] for r in comp['cases']] == [19,20,22,28,29]
    assert all(r['model_generations']==[1] and not r['stage_qualified'] for r in comp['cases'])
    assert not inter['current_run_model_parameters_dynamically_switched']
    assert not inter['codegen_needed_for_same_layout_hydro_values']
    assert inter['codegen_needed_for_new_residual_obstacle_or_shape']
    assert len(matrix['rows']) == 16
    assert all(not r['inherited_original_case_passed'] for r in comp['cases'] if r['batch']!=19)
    delivery = load('preflight/MPC_delivery_preparation_v1.json')
    assert delivery['passed'] is False and delivery['error_number'] == 112
    assert not delivery['files_overwritten'] and not delivery['mount_changed']
    assert load('preflight/workspace_initial_local_v1.json')['passed'] is False
    assert 'AssertionError' in (D/'analysis/audit_attempt01.log').read_text()
    assert json.loads((D/'analysis/audit_attempt02.log').read_text())['passed']
    files,_ = population()
    qa = dict(schema='P1-scope-local-QA/v1', passed=True,
              passed_semantics='local read-only audit and archive consistency only, no phase acceptance',
              actual_new_control_runs=0, actual_new_builds=0, actual_new_codegen=0,
              independent_frozen_run_metric_recomputations=5, matrix_requirements=16,
              interface_evidence='source, exact installed header, pinned linked archive and actual Worker defined symbols; no model switch execution',
              inspected_input_count=74, input_SHA_unchanged=True,
              initial_local_protection_sha256=sha(D/'preflight/workspace_initial_local_v2.json')['sha256'],
              final_local_protection_sha256=sha(D/'preflight/workspace_final_local_v2.json')['sha256'],
              local_old_asset_paths=41167, local_old_asset_bytes=5039073437,
              original_real_launch_exception_preserved=True, business_diff_sha256=final['protection']['business_diff_sha256'],
              first_helper_path_failure_and_audit_type_failure_retained=True,
              original_D20_D22_D28_D29_failed_reports_preserved=True,
              current_source_or_binary_rewritten=False, component_validation_complete=True,
              stage_qualified=False, execute_qualified=False, true_plant_qualified=False, research_conclusion=False,
              MPC_delivery_verified=False, MPC_delivery_pending=True, historical_MPC_paths_currently_verified=False,
              fixed_file_count=len(files), fixed_files=files)
    put(D/'postrun/final_QA_v1.json', qa)
    allfiles, dirs=population()
    inv=dict(schema='P1-scope-local-archive-inventory/v1',
             directories=dirs, files=[dict(relative_path=p,**v) for p,v in sorted(allfiles.items())],
             inventory_excludes_itself_only=True, local_sealed=True, current_qualification='read-only audit only',
             bytes_excluding_inventory=sum(v['bytes'] for v in allfiles.values()),
             MPC_delivery_pending=True, stage_qualified=False, research_conclusion=False)
    put(D/'archive_inventory_v1.json', inv)
    # Full final readback of exact archive population, without modifying the seal.
    actual, actualdirs = population()
    assert set(actual)==set(allfiles)|{'archive_inventory_v1.json'}
    assert actualdirs==dirs
    assert all(actual[p]==pin for p,pin in allfiles.items())
    print(json.dumps(dict(passed=True, files=len(actual), bytes=sum(v['bytes'] for v in actual.values()),
                          inventory_sha256=sha(D/'archive_inventory_v1.json')['sha256'],
                          QA_sha256=sha(D/'postrun/final_QA_v1.json')['sha256'],
                          report=str(D/'documents/方案A_P1阶段对照与模型接口审查_2026-10-19.md'),
                          MPC_delivery_pending=True,stage_qualified=False),ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=['prepare','finalize'])
    args=parser.parse_args()
    prepare() if args.phase=='prepare' else finalize()
