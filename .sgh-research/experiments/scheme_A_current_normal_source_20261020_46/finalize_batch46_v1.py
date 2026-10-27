#!/usr/bin/env python3
"""Verify declared old/source/actual inputs, update final state and seal once."""
import hashlib,json,time
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):return json.loads((D/p).read_bytes())
def pin(p):
    raw=Path(p).read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def create(name,value):
    with (D/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
def main():
    initial=read('preflight/protection_initial_v1.json');final=read('preflight/protection_final_v1.json')
    assert initial['passed'] and final['passed']
    for k in ['unique_raw_files_reread','logical_bytes_streamed','business_diff_sha256','current_asset_recheck_boot_id']:
        assert initial['protection'][k]==final['protection'][k]
    audit=read('postrun/current_normal_source20s_audit_v1.json');assert audit['passed'] and audit['component_passed']
    assert len(audit['sections'])==7 and all(s['passed'] for s in audit['sections'].values())
    pins={}
    def capture(p,expected=None):
        p=str(p);r=pin(p)
        if expected is not None:assert r=={k:expected[k] for k in ['bytes','sha256']},p
        if p in pins:assert pins[p]==r
        pins[p]=r
    assert audit['input_sha256_before']==audit['input_sha256_after']
    for p,r in audit['input_sha256_before'].items():capture(p,r)
    for version in [1,2,3]:
        path=D/f'preflight/prerun_source_lock_v{version}.json';lock=read(path.relative_to(D));capture(path)
        for p,r in lock['files'].items():capture(p,r)
    extra=['postrun/observed_domain_timing_supplement_v1.json','verification/actual_normal_evidence_negatives_v1.json']
    for leaf in extra:
        r=read(leaf);assert r['passed'] and r['input_sha256_before']==r['input_sha256_after']
        for p,v in r['input_sha256_before'].items():capture(p,v)
        capture(D/leaf)
    ledger=read('implementation/B5_candidate_evidence_ledger_v1.json')
    assert ledger['status']=='candidate_evidence_assembled_not_frozen' and not ledger['B5_formal_freeze_qualified']
    for p,v in ledger['input_sha256'].items():capture(p,v)
    for path in ['verification/normal_source_window_cases_v1.json','verification/independent_window_cases_v1.json',
      'verification/normal_source_reader_budget_cases_v1.json','verification/legacy_Driver_argv_ABI_cases_v1.json','verification/B5_candidate_ledger_checks_v1.json']:
        assert read(path)['passed'];capture(D/path)
    # Every failed raw file remains, not only a textual explanation.
    for run in ['normal_source20s_01','normal_source20s_02']:
        root=D/'author/runs'/run;result=read(root.relative_to(D)/'result.json');assert result['passed'] is False and result['cleanup_complete']
        for p in root.rglob('*'):
            assert not p.is_symlink()
            if p.is_file():capture(p)
    before=dict(pins)
    for p,row in before.items():assert pin(p)==row,p
    create('postrun/final_input_evidence_recheck_v1.json',{'schema':'current-normal-source-final-evidence-recheck-v1','passed':True,
      'unique_paths':len(pins),'files':pins,'source_locks1_2_3_preserved':True,'all_failed_raw_populations_rechecked':True,
      'current_full_audit_passed':True,'stage_qualified':False})
    window=audit['sections']['continuous_current_nominal_source20s']['details'];storage=audit['sections']['Stored_Fixture_actual_command_chain']['details']
    r=read('author_r2/runs/normal_source20s_03/result.json');supp=read('postrun/observed_domain_timing_supplement_v1.json')
    assert r['normal20_source_case_completed'] and r['close_errors']==[] and all(v==0 for v in r['owned_role_returncodes'].values())
    status={'schema':'SchemeA-current-normal-source20s-final-status-v1','passed':True,'normal_source20s_component_passed':True,
      'current_author':'author_r2','current_run':'normal_source20s_03','actual_run_attempts':3,'prior_failed_runs_preserved':2,
      'registration_only_failure_preserved':True,'CXX_builds':0,'all_five_ELFs_unchanged':True,'control_parameters_and81field_contract_unchanged':True,
      'all_actual_control_hooks_zero':True,'actual_control_fault_injections':0,'run_elapsed_ns':r['elapsed_ns'],'normal_close_elapsed_ns':r['close_elapsed_ns'],
      'normal_window':window,'Stored_messages':storage['Stored_messages'],'Stored_Applied':storage['Stored_Applied'],
      'Stored_Decisions':storage['Stored_Decisions'],'Stored_capabilities':storage['Stored_capabilities'],
      'main_independent_audit_sections':7,'main_audit_inputs':len(audit['input_sha256_before']),
      'final_unique_evidence_paths_rechecked':len(pins),'actual_mixed_jobs_separate_age_checks_passed':len(supp['mixed_frozen_jobs']),
      'Source_selector_cases':17,'independent_window_cases':11,'actual_reader_budget_cases':3,'legacy_argv_cases':2,
      'altered_actual_source_evidence_rejections':12,'altered_mixed_evidence_rejections':3,'altered_candidate_ledger_rejections':8,
      'old_local_paths_rechecked':final['protection']['unique_raw_files_reread'],'old_local_bytes_rechecked':final['protection']['logical_bytes_streamed'],
      'old_dirty_and_frozen_assets_preserved':True,'B5_candidate_evidence_ledger_ready':True,'remaining_freeze_actions':2,
      'new_full_no_output_business_run_is_not_an_original_M0b_prerequisite':True,
      'pending8_or_pre_freeze_flags_changed':False,'full_API_gap240ms_qualified':False,'API_gap_full_population':supp['API_gap_population'],
      'general_D1_or_plant_domain_qualified':False,'general_mixed_turning_qualified':False,'hard_clock_or_WCET_proven':False,
      'B5_formal_freeze_qualified':False,'M0b_qualified':False,'M4_qualified':False,'F6_qualified':False,'P1_qualified':False,
      'physical_execute_release_enabled':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False,
      'next':'Lock formal execute target profile source/owner/bootstrap policy and exact field/entry semantics; commit actual immutable B5/M0b freeze package; then M4,knownmodeltransaction/F6,originalP1',
      'delivery_authority':'delivery_verification.json'}
    create('batch_status_final_v1.json',status)
    create('postrun/final_QA_v1.json',{'schema':'current-normal-source20s-component-final-QA-v1',**{k:v for k,v in status.items() if k!='schema'},
      'passed_scope':'same-current-five-ELF normal nominal continuous20s source, all raw/Source/typed storage/Witness and affected normal close; candidate freeze ledger integrity',
      'MPC_delivery_pending_at_QA':True})
    create('postrun/theory_review_decision_v1.json',{'schema':'current-normal-source-postrun-theory-v1','verdict':'CONDITIONAL',
      'blocking_reasons':['Actual normal-source20s and version binding now passed; immutable B5/M0b commit has not occurred.',
        'Formal execute source/soleowner/bootstrap policy and exact profile/entry semantics still need a concrete declaration; legacy startup stream fails240ms.'],
      'assumption_table':[{'assumption':'short39–42 slices can be replaced with one current normal continuous window',
        'evidence':'normal_source20s_03;7-section audit;20.002935074s;101 moving/nonzero anchor Jobs;5901Stored',
        'status':'verified selected nominal component'},
        {'assumption':'full no_output business is a separate mandatoryM0b prior stage','evidence':'originalP1 §7 M0b explicitly permits shadow OR no_output independent calibration',
         'status':'rejected extra requirement; remove it'},
        {'assumption':'legacyDriver argv and terminal Source read defaults fit a longer normal runner','evidence':'attempts01/02 failed; ABI and bounded-reader repairs; attempts03 and targeted checks passed',
         'status':'false assumptions corrected without changing Native/control gates'}],
      'experience_risks':['Do not relabel observer/source tool refusals as NMPC algorithm failure.','Do not repeatedly collect the already closed normal20s window.',
        'Do not promote two observed mixed Jobs into a general domain or clip startup API gaps.'],
      'safe_next_step':'Use assembled candidate ledger to implement/lock formal execute profile policies and immutable freeze; no extra full no_output long-run gate.',
      'override_policy':'NO-GO requires explicit user override; no override used','stage_qualified':False,'research_conclusion':False})
    (D/'postrun/batch46.retro.md').write_text('''# 第46批复盘

flow_policy_mismatch是主要机制：原计划M0b允许shadow或无输出校准，额外要求完整no_output业务会扩大原门。以当前同五ELF正常连续20s补真实缺项，最终7节闭卷通过，Source/Stored/Witness及末帧完整。没有调整控制参数或半RMSE门。

两次实际失败属于工具：旧Driver argv[1]约定被-B破坏；终止场景16MiB读取默认值不适合正常长窗。分别保存原run/注册/源码/关闭错误，恢复ABI并派生64MiB读预算（仍在128MiB总预算内），未放宽Native门、未原目录补跑。一次注册父版本路径错误在spawn前拒绝也保留。

新证据：20.002935074s、101动态非零来源Job、100窗内决策均接纳、全运行103Job/103Candidate/109Decision/5901Stored；2个mixed Job只按其实际时间/域复核。完整API启动gap1.54s仍保留，不冒称240ms整流通过或硬时钟界。

递归选择：正式profile/policy及不可变冻结动作的信心高、影响高、成本中；重复prepare/来源长窗的增益低。只处理候选台账中两个具体冻结动作，然后原M4→模型事务/F6→P1。停止本正常来源工作包，不再穷举raw或调RTI。EDA WNS/PPA/DEF不适用，研究结论保持false。
''')
    (D/'CURRENT.md').write_text(f'''# 方案A 当前状态：第46批（2026-10-20）

已补齐当前同五ELF正常来源窗：normal_source20s_03，Source20.002935074s、odom sim20.001858986s，101动态非零真实锚点Job，窗内100/100决策接纳。全运行103Job/103Candidate/109Decision，5901Stored，普通末帧Applied107与五角色INT-only/RC0/组空闭合。7节独立审计2633项输入通过。

两次失败（argv ABI、16MiB观察读预算）和注册路径失败原件保留；最终author_r2仅增加Source观察读量预算，Native/control参数/合同不变，无新CXX构建或故障刺激。全API流startup约1.54s不标240ms通过；2个mixed Job不扩大为一般域。原dirty/冻结资产49939路径/6389602129字节不变。

范围纠正：原M0b允许独立shadow或无输出校准，不另加完整no_output业务长跑门。当前正常窗组件缺项已关闭，B5候选证据台账已汇成。剩余冻结动作两个：正式execute目标profile来源/owner/启动保持字段语义固定；据真实证据提交不可变冻结包/hash。当前pending8/pre-freeze及physical execute=false保留。

B5/M0b/M4/F6/P1阶段与研究结论仍未提升；候选台账不等于已提交冻结。下一步直接推进上述两个冻结动作，再M4→已知模型事务/F6→原P1，不重复45准备或本批正常来源窗。最终文档与MPC交付见documents及delivery_verification.json。最终证据{len(pins)}个唯一路径再次逐字核验。
''')
    files=[];directories=[]
    for p in sorted(D.rglob('*')):
        assert not p.is_symlink(),str(p)
        if p.is_dir():directories.append(str(p.relative_to(D)))
        else:assert p.is_file();files.append({'relative_path':str(p.relative_to(D)),**pin(p)})
    create('archive_inventory_v1.json',{'schema':'SchemeA-batch46-sealed-local-inventory-v1','sealed_ns':time.monotonic_ns(),'files':files,'directories':directories,
      'bytes_excluding_inventory_receipt':sum(f['bytes'] for f in files),'allowed_later_member_only':'delivery_verification.json','stage_qualified':False,'research_conclusion':False})
    print(json.dumps({'passed':True,'files_before_inventory_receipt':len(files),'bytes_before_inventory_receipt':sum(f['bytes'] for f in files),
      'inventory_sha256':pin(D/'archive_inventory_v1.json')['sha256'],'QA_sha256':pin(D/'postrun/final_QA_v1.json')['sha256'],'final_input_paths':len(pins)}))
if __name__=='__main__':main()
