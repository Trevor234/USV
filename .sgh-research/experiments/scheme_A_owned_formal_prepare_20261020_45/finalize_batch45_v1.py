#!/usr/bin/env python3
"""Recheck both actual source locks, update final docs/status and seal once."""
import hashlib
import json
from pathlib import Path
import time

D=Path(__file__).resolve().parent


def read(p):return json.loads((D/p).read_bytes())
def pin(p):
    b=Path(p).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def create(name,value):
    with (D/name).open('x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')


def main():
    initial=read('preflight/protection_initial_v1.json');final=read('preflight/protection_final_r2_v1.json')
    assert initial['passed'] and final['passed']
    for k in ['unique_raw_files_reread','logical_bytes_streamed','business_diff_sha256','current_asset_recheck_boot_id']:
        assert initial['protection'][k]==final['protection'][k]
    audits=[read('postrun/actual_prepare_audit_v1.json'),read('postrun/actual_prepare_audit_v2.json')]
    pins={}
    for audit in audits:
        assert audit['passed'] and audit['input_sha256_before']==audit['input_sha256_after']
        assert len(audit['altered_actual_evidence_cases'])==12 and all(n['rejected'] for n in audit['altered_actual_evidence_cases'])
        for p,row in audit['input_sha256_before'].items():
            assert pin(p)==row,p
            if p in pins:assert pins[p]==row
            pins[p]=row
    constructors=read('verification/constructor_checks_v3.json');assert constructors['passed'] and constructors['case_count']==26
    build=read('build/native_formal_attempt04/build_result_v1.json');assert build['passed'] and build['new_input_boundary_test']['checks']==21
    assert read('postrun/resource_revision_difference_v1.json')['changed_files']==3
    current=audits[1]['metrics'];previous=audits[0]['metrics']
    r1=read('runs/formal_prepare_01/driver_result.json');r2=read('runs/formal_prepare_02/driver_result.json')
    term=read('runs/formal_prepare_02/preparer/terminal.json')
    create('postrun/final_input_lock_recheck_v1.json',{'schema':'formal-prepare-final-input-recheck-v1',
        'passed':True,'source_inputs':len(pins),'input_sha256':pins,'both_actual_runs_rechecked':True,'stage_qualified':False})
    status={'schema':'SchemeA-batch45-final-status-v1','passed':True,'current_source':'author_r2',
      'current_registry':'build/native_formal_attempt04/runtime_registry_v1.json',
      'current_selected_run':'runs/formal_prepare_02','prior_run_preserved':'runs/formal_prepare_01',
      'owned_formal_prepare_close_component_passed':True,'actual_four_role_sessions':2,
      'current_run_seconds':r2['elapsed_seconds'],'previous_run_seconds':r1['elapsed_seconds'],
      'current_metrics':current,'previous_metrics':previous,'actual_control_fault_injection_runs':0,
      'current_input_boundary_checks':21,'current_actual_constructor_rejections':26,
      'previous_actual_constructor_rejections_preserved':44,'current_altered_evidence_rejections':12,
      'build_attempts':4,'build_attempts_passed':3,'first_compile_failure_preserved':True,
      'declared_capacity_fix_included':True,'same84_contract_bytes':True,'same_existing_Native_spec_SHA':True,
      'Worker35_and_Recorder_C3_4_ELFs_reused_unchanged':True,
      'both_source_locks_final_byte_rechecked':True,'unique_audit_inputs_final_rechecked':len(pins),
      'old_local_paths_rechecked':final['protection']['unique_raw_files_reread'],
      'old_local_bytes_rechecked':final['protection']['logical_bytes_streamed'],
      'old_dirty_changes_and_failed_evidence_preserved':True,
      'pending8_preserved':True,'full_Regulator_no_output_qualified':False,
      'D1_general_dynamic_domain_qualified':False,'B5_formal_freeze_qualified':False,'M0b_qualified':False,
      'M4_qualified':False,'F6_qualified':False,'P1_qualified':False,'physical_execute_release_enabled':False,
      'stage_qualified':False,'execute_qualified':False,'true_plant_qualified':False,'research_conclusion':False,
      'next':'Stop expanding proved prepare/close; map originalD1/B4/B5/M0b final-version freeze differences, supplement only concrete missing implementation/evidence, then M4/modeltransaction/F6/P1',
      'delivery_authority':'delivery_verification.json'}
    create('batch_status_final_v1.json',status)
    create('postrun/final_QA_v1.json',{'schema':'formal-owned-prepare-close-final-QA-v1',**{k:v for k,v in status.items() if k!='schema'},
      'passed_scope':'actual bounded four-role formal no_output preparation-close, independent source/typed storage accounting and resource-entry difference',
      'raw_reserialization_SHA_equals_wire_SHA_claimed':False,'raw_comparison_failures_preserved':True,
      'frozen_marker_or_pending_flags_promoted':False,'MPC_delivery_pending_at_QA':True})
    create('postrun/theory_review_decision_v1.json',{'schema':'formal-prepare-postrun-theory-review-v1','verdict':'CONDITIONAL',
      'blocking_reasons':['Prepare-only has noJob/Decision/activation/Witness; fullRegulator execution is a separate condition.',
        'OriginalD1 domain/final-policy/version evidence and B5/M0b freeze requirements still need their explicit difference matrix.'],
      'assumption_table':[{'assumption':'formal84/fault=false can prepare on actual owned endpoints without legacyApplied',
        'evidence':'two actual runs + independent audits; current revision resource checks21 and constructor26',
        'status':'verified bounded preparation component'},
        {'assumption':'typed reserialization hash equals bag wire hash','evidence':'raw diagnostics retained; fields/explicit padding analysis',
         'status':'rejected assumption; all typed fields and exact input accounting verified independently'}],
      'experience_risks':['Resource-domain lower-capacity entry needed a concrete versioned repair; runs01 and02 kept separately.',
        'Repeated preparation or arbitraryraw mutation expansion would add no evidence for the remaining originalfreeze conditions.'],
      'safe_next_step':'Follow originalhandoffS5: close this component and build final-version D1/B4/B5/M0b freeze difference matrix.',
      'override_policy':'NO-GO requires explicit user override; no override used',
      'stage_qualified':False,'research_conclusion':False})
    retro='''# 第45批复盘

主要机制为flow_policy_mismatch：旧shadow/legacy准备前提不能直接用于formal no_output。新Native准备角色、独立stationary Fixture与真实Worker/Recorder/Driver已补齐这一具体组件差集。两轮真实准备/关闭独立通过，最终source为author_r2。

实现问题：初编译使用错误Jazzy重载，保留失败并改显式Executor；参考对更新保留最后完整pair；最终审查补资源下界和有效容量copy前检查。后三项是具体代码修正，没有改变控制参数、contract或scope门槛。首轮当时的2048容量事实仍有效，不自动代表所有资源变体。

证据问题：typed重序列化与wire raw SHA不同；counts相同仍不足以闭合。独立解码核对所有输入字段/唯一stamp，Worker19字段和明确padding字节归一后闭合，原始SHA比较和解析失败保留。Recorder内部accounting标志没有被改写。两轮各12个altered-evidence反例不是运行时故障注入。

下一方案：原冻结差集矩阵的信心高、影响高、成本低、风险低；按矩阵补一轮确实缺的正常域或业务入口差集，信心中、影响高、成本中；继续扩大已证prepare、穷举raw或调半RMSE门，影响低且范围风险高，不执行。

停止条件：已证组件按原handoffS5结束。本批不自行打开physical execute，不授予B5/M0b/M4/P1。下一步只围绕原门的具体未闭合条件；原params、冻结资产和旧失败保持。WNS/PPA/DEF为EDA指标，本USV批次不适用。
'''
    (D/'postrun/batch45.retro.md').write_text(retro)
    # Keep the first-run draft separately, and make the main document describe
    # the actual final implementation rather than the pre-repair conversation.
    report=(D/'evidence/first_run_report_draft_v1.md').read_text()
    report=report.replace('**一次真实四角色准备/关闭已通过独立审计；该组件工作包闭合。','**最终修订版的真实四角色准备/关闭已通过独立审计；两轮证据分别保留，该组件工作包闭合。')
    report=report.replace('实现保留20s准备预算','最终修订`author_r2`另显式要求Path/Profile声明容量至少21，并在typed复制前按有效契约容量检查；通用规范允许的小资源配置不再误入固定21点准备角色。这是角色适用域检查，未改变通用规范、控制参数或本批实际契约。修改仅涉及三个新角色文件，首轮author原件保持。\n\n实现保留20s准备预算')
    report=report.replace('最终候选编译通过，17项新增typed输入边界检查通过；最终ELF的22项真实构造拒绝检查通过','最终候选编译通过，21项typed输入边界检查通过；最终ELF的26项真实构造拒绝检查通过')
    report=report.replace('前一候选同样22项结果保留，区别于本轮只有一次完整四角色运行。','此前两轮各22项构造结果保留；这些构造拒绝不是完整四角色会话。')
    report=report.replace('唯一实际运行：`runs/formal_prepare_01`，独立DDS197，总用时 **9.714841s**。',f'最终实际运行：`runs/formal_prepare_02`，独立DDS197、新run/新目录，总用时 **{r2["elapsed_seconds"]:.6f}s**。首轮`formal_prepare_01`用时9.714841s、Stored370条，其源码/源锁/运行/审计保持；因明确资源边界修订，另预注册并只补跑一次最终版本。')
    report=report.replace('每路69条，五路共345条','每路70条，五路共350条').replace('发布25条','发布21条')
    report=report.replace('370条=345输入+25Capability','371条=350输入+21Capability')
    report=report.replace('278条输入、23条Capability',f'{current["admitted_input_receipts"]}条输入、{term["capability_receipts"]}条Capability')
    report=report.replace('Native轮询824次，保留42条周期图快照',f'Native轮询{current["native_graph_poll_count"]}次，保留{current["periodic_graph_checks_recorded"]}条周期图快照')
    report=report.replace('不把278条准备输入与完整345条发布',f'不把{current["admitted_input_receipts"]}条准备输入与完整350条发布')
    report=report.replace('逐一匹配345个','逐一匹配350个').replace('25条Capability的全部19字段','21条Capability的全部19字段')
    report=report.replace('第三次构建为最终候选，并重新做受影响构造检查。','第三次候选重新做构造检查并完成首轮运行；最终审查再派生author_r2加入资源下界/有效容量检查，第四次构建为最终候选，按扩展预注册做26项构造检查及新目录定向运行。')
    report=report.replace('也没有为修正检查器重复控制运行。','也没有为修正检查器重复控制运行；第二次运行由实际角色资源检查代码改变触发。')
    report=report.replace('25条Capability的Source typed CDR各425字节、bag raw各428字节','首轮25条及修订版21条Capability的Source typed CDR各425字节、bag raw各428字节')
    report=report.replace('未取得源packet新鲜度保证。','未取得源packet新鲜度保证。进程exe/argv在pin时认证，此后以零等待pidfd和清单一致性检查存活；不宣称连续exec身份或全局DDS唯一性已获证明。')
    (D/'documents/方案A_owned正式无输出准备与关闭_2026-10-20.md').write_text(report)
    nextplan=read('postrun/next_implementation_plan_v1.json')
    nextplan['current_batch45_proved'][-1]='current revision zero jobs/forbiddenoutputs;INT-only4role close;Source/Stored371 typed accounted;prior370 preserved'
    nextplan['current_source_revision']='author_r2';nextplan['resource_capacity_domain_checked']=True
    (D/'postrun/next_implementation_plan_v1.json').write_text(json.dumps(nextplan,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    np=D/'documents/下一步实施计划_B5M0b冻结差集_2026-10-20.md'
    np.write_text(np.read_text().replace('Source-to-Stored370条','最终修订Source-to-Stored371条（首轮370条保留）'))
    current_text=f'''# 方案A 当前状态：第45批（2026-10-20）

已闭合：actual owned formal no_output prepare/close组件。最终author_r2+build04运行formal_prepare_02，formal84/fault=false，四角色实际进程/端点/有效配置和Source FD绑定；一次真实授权及重放拒绝；Stored371条=350输入+21Capability；Job/Decision/Applied/推力调用0；全角色INT-only/RC0/组空。26个当前构造拒绝、21个边界检查、12项离线篡改证据反例通过。首轮370条证据及原始编译/布局诊断失败保留。

证据：两轮各1326项输入锁，最终合并{len(pins)}个唯一路径逐字复查；初末49215条历史路径/6223044075字节不变。旧24处业务dirty、单列real.launch.py、冻结资产均未改。Worker35/RecorderC3.4原ELF复用，control参数/contract字节及Native规范hash不变。资源角色门已拒绝21点容量不足，并用有效声明容量copy前检查。

资格边界：当前只准备关闭，没有Regulator Job/Decision/activation/Witness业务；不是完整no_output、动态域、B5冻结/M0b/M4/F6/P1或研究结论。pending8和physical execute=false保持。

下一步：按原handoffS5结束准备工作包，建立原D1/B4/B5/M0b最终版本冻结差集，只补具体缺项；再B5/M0b→M4→已知模型事务/F6→原P1。不要扩大raw穷举、重跑39–42或新增半RMSE/RTI调参门。详见documents报告与下一步计划；MPC交付以delivery_verification.json为准。
'''
    (D/'CURRENT.md').write_text(current_text)
    # Seal every file/directory after the last planned source/status write.
    files=[];directories=[]
    for p in sorted(D.rglob('*')):
        assert not p.is_symlink(),str(p)
        if p.is_dir():directories.append(str(p.relative_to(D)))
        else:
            assert p.is_file();files.append({'relative_path':str(p.relative_to(D)),**pin(p)})
    create('archive_inventory_v1.json',{'schema':'SchemeA-batch45-sealed-inventory-v1','sealed_ns':time.monotonic_ns(),
      'files':files,'directories':directories,'bytes_excluding_inventory_receipt':sum(r['bytes'] for r in files),
      'allowed_later_member_only':'delivery_verification.json','stage_qualified':False,'research_conclusion':False})
    print(json.dumps({'passed':True,'files_before_inventory_receipt':len(files),'bytes_before_inventory_receipt':sum(r['bytes'] for r in files),
      'inventory_sha256':pin(D/'archive_inventory_v1.json')['sha256'],'QA_sha256':pin(D/'postrun/final_QA_v1.json')['sha256'],'combined_input_pins':len(pins)}))


if __name__=='__main__':main()
