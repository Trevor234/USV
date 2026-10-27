#!/usr/bin/env python3
"""Create final status/QA/inventory once; leaves delivery receipt to MPC tool."""
import hashlib
import json
from pathlib import Path
import time

D=Path(__file__).resolve().parent


def read(rel):return json.loads((D/rel).read_bytes())


def create(rel,value):
    with (D/rel).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')


def main():
    initial=read('preflight/protection_initial_v1.json');final=read('preflight/protection_final_v1.json')
    assert initial['passed'] and final['passed']
    for key in ['unique_raw_files_reread','logical_bytes_streamed','business_diff_sha256',
                'current_asset_recheck_boot_id']:
        assert initial['protection'][key]==final['protection'][key]
    audit=read('postrun/component_evidence_audit_v1.json');assert audit['passed']
    assert audit['input_sha256_before']==audit['input_sha256_after']
    # Do not reduce the audit to trust in an old report: repeat its exact pins
    # after all implementation/test writes, immediately before sealing.
    for path,expected in audit['input_sha256_before'].items():
        raw=Path(path).read_bytes()
        assert len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256'],path
    parity=read('verification/contract_parity_v2.json');gate=read('verification/formal_prepare_cases_v1.json')
    file_entry=read('verification/formal_contract_entry_v1.json')
    assert all(r['passed'] for r in [parity,gate,file_entry])
    assert [r['case_count'] for r in [parity,gate,file_entry]]==[385,102,25]
    env=read('evidence/post_component_environment_v1.json')
    assert env['MPC_accessible'] and not env['observed_existing_native_P1_roles']
    status={'schema':'SchemeA-batch44-final-status/v1','updated_local':'2026-10-20 Asia/Shanghai',
      'current':'B5 current81/diag10 spec compatibility repaired in new candidate artifacts; formal no_output preparation file entry and permission core verified',
      'same_spec_SHA256_as_existing_Native':True,
      'spec_sha256':'317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798',
      'current_diag_fields':81,'formal_pre_freeze_fields':84,'hydro_fields':19,
      'fixed_parameters_changed':False,'old_diagnostic_driver_replaced':False,
      'contract_parity_cases':385,'parity_accepted':38,'parity_rejected':347,
      'formal_prepare_core_seeded_cases':102,'formal_file_source_actual_cases':25,
      'preserved_probe_failure_attempts':1,'CXX_builds':3,'actual_ROS_runs':0,
      'actual_native_solver_runs':0,'actual_Gazebo_runs':0,'physical_control_runs':0,
      'old_paths_preserved':final['protection']['unique_raw_files_reread'],
      'old_local_bytes_rechecked':final['protection']['logical_bytes_streamed'],
      'evidence_inputs_pinned':audit['source_evidence_inputs'],
      'current_selected_B4_review_complete':True,'B5_spec_component_complete':True,
      'B5_no_output_prepare_component_complete':True,'live_owned_no_output_prepare_entry_proven':False,
      'B5_formal_freeze_completed':False,'M0b_formal_qualified':False,'M4_qualified':False,
      'known_model_transaction_F6_completed':False,'P1_qualified':False,
      'physical_execute_release_enabled':False,'stage_qualified':False,'execute_qualified':False,
      'true_plant_qualified':False,'WCET_proven':False,'research_conclusion':False,
      'next':'Implement new owned no_output prepare role/driver and no-legacy fixture; source-lock and preregister one actual prepare/close proof, then close appropriate B5/M0b differences before M4/model transaction/P1',
      'delivery_authority':'delivery_verification.json'}
    create('batch_status_final_v1.json',status)
    theory={'schema':'B5-batch44-postrun-theory-review/v1','verdict':'CONDITIONAL',
      'blocking_reasons':['Actual owned formal no_output role/driver/fixture integration has not run.',
                          'Permission Context is seeded in component cases; actual live GID/process/receipt/recording bindings remain required.',
                          'Prepare-only zero-job scope does not validate full no_output Regulator source/reference/anchor execution semantics or satisfy B5 formal freezing.'],
      'assumption_table':[{'assumption':'configuration drift can be repaired without retuning Native',
                          'evidence':'exact existing Native spec hash recovered;385 independent parity cases',
                          'status':'verified component'},
                          {'assumption':'new prepare permission core need not request legacy Applied or fault permission',
                          'evidence':'new policy/entry;102 seeded cases +25 real file cases;zero outputs allowed',
                          'status':'verified components; actual owned adapter pending'}],
      'experience_risks':['First probe failed on error-report UTF8 serialization; v1 raw failure preserved, v2 independent full corpus passed.',
                          'Diagnostic role identities/configs cannot be promoted by field shape or a fictitious64hex freeze marker.'],
      'safe_next_step':'Implement actual constructor/owned adapter and independent no-legacy fixture under the locked next-step plan; no physical release.',
      'override_policy':'NO-GO requires explicit user override; none requested or used',
      'GO_scope':'new owned no_output adapter implementation and targeted constructor verification',
      'formal_freeze_qualified':False,'stage_qualified':False,'research_conclusion':False}
    create('postrun/theory_review_decision_v1.json',theory)
    qa={'schema':'B5-contract-and-no-output-preparation-component-final-QA/v1','passed':True,
        'passed_scope':'current contract compatibility, actual file-source entry, seeded no_output prepare policy core, source/reproduction/byte preservation',
        **{k:v for k,v in status.items() if k not in ['schema','current','next','delivery_authority']},
        'source_inputs_unchanged':True,'generated_outputs_reproduced':5,
        'Native_rules_semantically_unchanged':True,'old74_rejection_preserved':True,
        'shape_only_Frozen_cannot_authorize_execute':True,'original_pending8_preserved':True,
        'three_small_component_builds_only':True,'MPC_delivery_pending_at_QA':True,
        'delivery_authority':'delivery_verification.json'}
    create('postrun/final_QA_v1.json',qa)
    retro='''# 第44批复盘

机制分类：主要为flow_policy_mismatch（旧Python规范与当前Native脱节）；初轮探针异常为tool_stability_issue（错误文本序列化），已保留失败并有界修复。

假设验证：恢复规范恰好重现Native已有317ec56f…6d798 hash，说明本次不需要控制参数优化；385条独立期望对拍成立。独立fault=false/no_output准备配置来源入口25条实际文件检查和准备权限核心102条seeded检查成立。完整owned ROS身份与准备运行仍缺证，禁止提升为M0b/B5冻结或P1结论。

下一方案评分：owned新入口与无legacy Fixture集成的信心中、影响高、成本中、风险受无输出范围约束；复用当前Worker/Recorder需真实formal冷启动与端点核验。直接放宽shadow guard或复制seeded ready值的信心低、风险高，不执行。

选择下一步：按机器可读owned_no_output_integration_plan_v1逐项实现；先构造/适配层，再锁源预注册一轮prepare/close。预算和停止条件随实际实现注册；本批没有自动启动任何ROS/物理执行。若配置漂移、任一未认证事实进入Context、出现SolveJob/Decision/Applied/物理Writer，或关闭不完整，停止并保留证据，不调低门槛。

经历条目：保留旧74规范与旧拒绝；禁止把并无参数变化的兼容修复说成性能提升；禁止把seeded组件、阶段资格、研究结论合并。无WNS/TNS/PPA/DEF指标，USV本批不适用。后续固定顺序为B5/M0b差集、M4、已知模型事务/F6、原始P1验收。
'''
    with (D/'postrun/batch44.retro.md').open('x') as f:f.write(retro)
    current='''# 方案A 当前状态：第44批（2026-10-20）

已完成：新候选中修复当前81/diag10规范兼容，精确重现既有Native规范SHA；385条Python/Native对拍通过。formal84的配置文件入口25条实际文件测试、独立准备门102条seeded组件测试通过。五份产物重现和848项输入锁审计通过。

保持：旧诊断Driver及五个角色ELF/封存资产不变，24处业务改动及单列real.launch.py改动保留；首轮探针非法UTF8错误序列化崩溃保留。物理execute总闸false，pending8未修改。初末保护48362路径/6168977834字节通过。

未完成：真实owned formal no_output端点准备/关闭、完整no_output Regulator语义、B5正式冻结、M0b/M4、有限模型事务/F6和P1。当前组件pass不是阶段资格或研究结论。

下一步：新owned准备角色/Driver加无legacy Applied依赖的Fixture；真实Worker/Recorder绑定、源码锁定后预注册有限准备/关闭。详见documents中的本批报告和下一步计划。MPC本批交付及逐字复核以delivery_verification.json为准。
'''
    with (D/'CURRENT.md').open('x') as f:f.write(current)
    # Include every regular file and every directory; no unknown/special paths.
    rows=[];directories=[]
    for path in sorted(D.rglob('*')):
        assert not path.is_symlink(),str(path)
        if path.is_dir():directories.append(str(path.relative_to(D)));continue
        assert path.is_file(),str(path)
        raw=path.read_bytes();rows.append({'relative_path':str(path.relative_to(D)),
            'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    inventory={'schema':'SchemeA-batch44-sealed-local-inventory/v1','sealed_steady_ns':time.monotonic_ns(),
        'files':rows,'directories':directories,'regular_file_count_excluding_inventory_receipt':len(rows),
        'bytes_excluding_inventory_receipt':sum(r['bytes'] for r in rows),
        'later_allowed_file_only':'delivery_verification.json','stage_qualified':False,'research_conclusion':False}
    create('archive_inventory_v1.json',inventory)
    print(json.dumps({'passed':True,'files_before_inventory_receipt':len(rows),
                      'bytes_before_inventory_receipt':inventory['bytes_excluding_inventory_receipt'],
                      'inventory_sha256':hashlib.sha256((D/'archive_inventory_v1.json').read_bytes()).hexdigest(),
                      'QA_sha256':hashlib.sha256((D/'postrun/final_QA_v1.json').read_bytes()).hexdigest()}))


if __name__=='__main__':main()
