#!/usr/bin/env python3
"""Seal actual implementation/tests and the failed startup without stage promotion."""
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent


def load(p):return json.loads(p.read_bytes())
def pin(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def emit(p,v):
    with p.open('xb') as f:f.write(v.encode() if type(v) is str else (json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode())


def main():
    a=load(D/'postrun/failed_start_audit_v1.json');c=load(D/'verification/component_verification_v3.json');n=load(D/'verification/native_entry_rejections_v1.json')
    before=load(D/'preflight/workspace_initial_v3.json');after=load(D/'preflight/workspace_final_v3.json')
    assert a['passed'] and not a['actual_run_passed'] and c['passed'] and n['passed'] and before['passed'] and after['passed']
    plan={'schema':'M4-recorder-lifecycle-minimal-fix-plan/v1','root_cause':'Recorder complete-manifest vs future Regulator Writer cyclic dependency',
       'next_source_change':['Driver authenticates actual Recorder process/exe/argv and publishes process-only pin before manifest',
         'Regulator verifies that owned process, then creates endpoints with API count0',
         'Regulator and Driver independently bind actual full Recorder manifest/Reader GIDs after all Writers exist',
         'only full Recorder/storage/typed-source readiness may authorize first API'],
       'thresholds_contract_model_reference_unchanged':True,'old_recorder_ELF_reused':True,
       'same_registration_retried':False,'future_trial_requires_new_source_version_and_registration':True,
       'new_trial_budget':{'whole_driver_seconds':45,'source_window_seconds':20,'automatic_retries':0},
       'M4_stage_qualified':False,'P1_qualified':False,'research_conclusion':False}
    emit(D/'postrun/next_implementation_plan_v1.json',plan)
    text='''# 方案A 第48批：M4入口实现、原生接口验证与首个启动失败

2026-10-21。正式profile/合同沿第47批，不修改数值、19项水动力、RTI、权重或阈值。

## 实际推进

派生新Regulator、Worker、动态nominal Fixture及有限Driver。Regulator独占Job/Decision/Applied及左右推力出口；构建前核对实际FastDDS GID为16字节，修复47纯context24字节格式与原生接口的差集，使用32hex原生表示。Worker认证改为完整冻结v3及目标profile，保留真实Proc/pidfd、独立两Writer和typed配置校验。未补零伪造GID。

来源/候选准入/准备/激活/预测等13个Regulator方法体逐字复用；Worker实际求解循环、缓存RK4名义源与参考生成器不变。新scope固定localhost/domain120、registered nominal .05；普通生产release关闭。实际输出前要求固定合同、真实Driver授权、全部owned身份、完整记录器和源/能力门禁。输出Writer及Reader集合均须对应已登记角色。

52项原生政策检查、38项源码关联激活GTest、14个实际可执行入口拒绝用例最终通过。三轮构建保留：初轮Regulator/Worker成功，Fixture因同条auto声明有符号/无符号类型不一致失败；第二轮五目标成功；第三轮仅Regulator及关联激活目标改变，将管理性prepared回执fsync移到输出线程启动之后，并修正启动后异常的API未知记账。第二、三轮未改的Worker/Fixture/政策产物按具体版本复用。首轮测试工具漏设P1_PAIR_TEST_OUTPUT导致30个SetUp失败，原XML/日志保留；设置独立输出根后38项通过，没有修改预期或控制代码制造通过。

## 唯一一次实际确认：失败，未接管

run `M4_owned_nominal_20261021_48_01`。实际只启动Fixture、Worker、Recorder三个角色；Driver在等待Recorder manifest约10秒后失败。Regulator没有被启动，Job=0、Candidate=0、左右推力API=0，未获得连续20秒正常来源。Fixture RC0，Worker与Recorder RC2均保留；三进程组均已空，无外层应急信号，未把它们标成正常关闭通过。

根因已由实际日志与源码闭合：Driver先等完整Recorder manifest；Recorder只有在所有12个topic的subscription准备完成后才写manifest，包含尚未创建的Regulator五个出口；Regulator构造器又要求完整Recorder pin才能创建出口。属于准备生命周期互等，与NMPC数值解、候选拒绝或阈值无关。不能增大等待时间解决依赖环。

本轮1908项注册输入逐字核验不变。该run保持失败、同注册自动重试0。下一轮应拆分Recorder真实进程认证与完整记录就绪：允许已认证且无API的Regulator先创建出口；完整storage/Reader/源门禁闭合后才能授权首次API。独立新版本、新编号和有限预算确认，不能复用这次失败作通过证据。

## 工作区变化与保护

本次开始前HEAD已变为feb50823a07054879e3c6f8d437c02595ce26976，原24文件的151961字节diff及SHA d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5已等字节进入提交，当前clean；本批不恢复旧dirty状态、不提交。两个旧活动备份头文件已在开始前缺失，从F5相同SHA快照在本批目录保全，不恢复原路径；.gitignore也已由新HEAD改变，保留当前快照、旧hash及原始核验失败，旧内容未声称完整恢复。47冻结索引4103项实际输入未缺失且全量复核通过。旧原路径不能概括为全部未变；本批完整字节保护按显式例外记录与当前基线执行，历史封存目录/失败未覆盖。

## 资格分层

组件：新入口及受影响检查通过。阶段：B5/M0b选定工程冻结沿用；M4首个实际正常确认失败，M4/F6/P1未验收。研究：无plant/Gazebo/硬件、F5完整plant/reference同一性、一般1.2m/s/转弯/mixed、WCET或性能优越性结论，GP/PPO仍未接入。

固定后续顺序仍为：解决本次Recorder生命周期环→新唯一输出正常/原故障矩阵→已知数值模型事务/F6→原P1联合复判。不得重跑已关闭45/46来源校准或调半RMSE来绕过本问题。
'''
    emit(D/'documents/方案A_M4入口实现与首次启动失败分析_2026-10-21.md',text)
    emit(D/'documents/下一步实施计划_Recorder生命周期拆分_2026-10-21.md','''# 下一步：拆分Recorder进程认证与完整就绪

2026-10-21。48实际启动失败为准备互等，不改合同/阈值，不重试旧run。

1. Driver在spawn Recorder后固定实际pid/start/exe/binary/source/argv，明确process-only、recording_ready=false。
2. Regulator认证该进程后创建5个出口，API仍0；完整Recorder manifest出现后，再与独立process pin核对source/argv/typed配置、实际Reader GIDs、storage/discovery状态。
3. Driver也认证完整Recorder manifest，再启动inputs；Regulator源/Worker/Reader门禁闭合后才出ready及接收一次grant。不能把process-only当full recording-ready。
4. 新源码/ELF/工具/注册hash封存；增加真实Recorder进程pin及篡改反例，保留52/38/14受影响回归。再单独编号正常Source20s、Driver45s、自动重试0。
5. 原9组M4故障、F6已知模型事务及原P1仍后续。首次局部nominal owner确认不自动取得原F5 plant/reference整体资格。

STOP：source/argv/身份失配、full-ready前有API、双owner/外部Reader、预算超期、cleanup_failed。保存失败，不覆盖48或47。
''')
    emit(D/'CURRENT.md','''# 第48批当前状态（2026-10-21）

M4实际入口已实现并构建；52项政策、38项源码关联GTest、14项实际入口拒绝通过。GID原生16字节/32hex及正式frozen Worker认证已落实，控制数值/模型/RTI不变。

唯一实际run01失败：Driver等待Recorder完整manifest，但Recorder等待未来Regulator出口，Regulator又要求Recorder pin。仅3个角色已启动；Regulator/Job/Candidate/推力API均0。实际退出RC0/2/2保留，全部组空；不标正常通过、无自动重试。1908注册输入不变，失败审计闭合。

B5/M0b冻结沿用；M4/F6/P1未验收。下一步拆分Recorder process-only身份与full recording-ready，独立版本/编号验证，再原M4故障→F6→P1。旧45/46不重跑，全部失败保留。

HEAD已在本批之前变为feb5082且旧24项内容等字节提交；当前clean保持。两旧备份头活动路径缺失以F5副本保全、.gitignore已外部改变，原路径全部未变不成立。47冻结4103项仍完整；详见preflight显式转移/恢复记录。
''')
    emit(D/'postrun/control_retro_v1.md','''# 第48批复盘

主机制flow_policy_mismatch：把旧Recorder完整就绪屏障直接放到新Writer创建之前，产生依赖环。实际0控制API，不能解释为NMPC拒绝。新变量应为process-only认证→endpoint创建→full Recorder/源认证→一次grant的分阶段生命周期；不增加等待预算。

下一修复confidence高、impact高、cost中、risk中，要求真实进程pin与full-ready分开验证，full-ready之前禁止API。允许单个独立新注册确认，旧run不重试。STOP沿原owned/时序/记录/退出规则。假设及经验：bootstrap实际锚点；原生GID格式；强typed完整配置；零请求/进程退出不当plant证明；原来证据不能替代新执行分支。EDA指标不适用。
''')
    qa={'schema':'SchemeA-M4-entry-batch-integrity-QA/v1','passed':True,'batch_deliverable_integrity_passed':True,
       'native_policy_cases':52,'source_linked_GTest_cases':38,'native_entry_refusals':14,'component_verification_passed':True,
       'actual_registered_normal_runs':1,'actual_normal_run_passed':False,'actual_roles_spawned':3,'Regulator_started':False,'control_API_calls':0,
       'M4_normal_component_qualified':False,'M4_stage_qualified':False,'F6_qualified':False,'P1_qualified':False,'stage_qualified':False,
       'B5_M0b_frozen_parent_preserved':True,'ordinary_production_release_enabled':False,'research_conclusion':False,
       'same_registration_retried':False,'source_thresholds_tuned':False,'owned_groups_empty':True,
       'workspace_resumed_HEAD':'feb50823a07054879e3c6f8d437c02595ce26976','original24_now_committed_content_equal':True,
       'all_historical_original_paths_unchanged':False,'explicit_preexisting_path_changes':['two pre_reference_prediction_v1 backup headers absent; exact F5 content recovered in new batch','.gitignore changed by resumed committed HEAD; old bytes not fully recovered'],
       'proofs':{str(p.relative_to(D)):pin(p) for p in [D/'postrun/failed_start_audit_v1.json',D/'verification/component_verification_v3.json',D/'verification/native_entry_rejections_v1.json',D/'preflight/workspace_initial_v3.json',D/'preflight/workspace_final_v3.json']}}
    emit(D/'postrun/final_QA_v1.json',qa)
    files=[];dirs=[]
    for p in sorted(D.rglob('*')):
        assert not p.is_symlink(),str(p)
        if p.is_dir():dirs.append(str(p.relative_to(D)))
        else:files.append({'relative_path':str(p.relative_to(D)),**pin(p)})
    emit(D/'archive_inventory_v1.json',{'schema':'SchemeA-M4-entry-archive/v1','files':files,'directories':dirs,'file_count_before_inventory_receipt':len(files),'bytes_before_inventory_receipt':sum(r['bytes'] for r in files),'actual_normal_run_passed':False,'M4_stage_qualified':False,'P1_qualified':False})
    print(json.dumps({'passed':True,'files_before_inventory_receipt':len(files),'bytes':sum(r['bytes'] for r in files),'inventory':pin(D/'archive_inventory_v1.json'),'QA':pin(D/'postrun/final_QA_v1.json')}))


if __name__=='__main__':main()
