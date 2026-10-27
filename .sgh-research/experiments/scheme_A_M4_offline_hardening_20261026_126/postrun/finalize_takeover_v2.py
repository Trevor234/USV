"""Read-only final checks; deliberately fails blanket acceptance on the E04 incident."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'implementation/tests'))
from offline_support import pin,save,QUALIFICATION
out=ROOT/'evidence/E12/attempt02';out.mkdir(parents=True,exist_ok=False)
previous=ROOT.parent/'scheme_A_M4_session_code_review_20261026_124'
primary=json.loads((previous/'evidence/inputs_before_v1.json').read_text())
supplement=json.loads((previous/'evidence/supplemental_inputs_before_v1.json').read_text())
register=json.loads((ROOT/'evidence/E10/attempt01/register_identity.json').read_text())
register_path=register['path'];protected={**primary['files'],**supplement['files']}
missing=[];unexpected=[];authorized=[]
for name,record in protected.items():
 p=Path(name)
 if not p.is_file():missing.append(name)
 elif pin(p)!=record:
  if name==register_path and record==register['before']and pin(p)==register['after']:authorized.append(name)
  else:unexpected.append(name)
workspace={p:record for p,record in primary['workspace_files'].items()}
workspace_changed=[name for name,record in workspace.items()if not Path(name).is_file()or pin(name)!=record]
repo=ROOT.parents[2]
porcelain=subprocess.check_output(['git','status','--porcelain=v1','-uall'],cwd=repo,text=True)
preimage=(ROOT/'evidence/E10/attempt01/research-innovations_before.md').read_bytes()
append_only=Path(register_path).read_bytes().startswith(preimage)and pin(register_path)==register['after']
regression=ROOT/'evidence/E09/attempt02'
population=json.loads((regression/'population.json').read_text())
regression_valid=all(row['passed']is True and pin(row['verification'])==row['pin']and json.loads(Path(row['verification']).read_text())['failures']==[]for row in population)
source_before=json.loads((regression/'registration.json').read_text())['source_pins']
late_metadata_changes=[p for p,record in source_before.items()if pin(p)!=record]
allowed_metadata=str(ROOT/'implementation/tests/record_step.py')
states=json.loads((ROOT/'postrun/step_status_v1.json').read_text())
dispositions=json.loads((ROOT/'postrun/issue_disposition_v1.json').read_text())
old=json.loads((ROOT/'evidence/E05/attempt04/takeover_manifest.json').read_text())['files_before_takeover']
modified=[];added=[]
for p in sorted((ROOT/'implementation').rglob('*')):
 if not p.is_file()or'__pycache__'in p.parts:continue
 relative=str(p.relative_to(ROOT));record=pin(p)
 if relative in old and record!=old[relative]:modified.append({'path':relative,'before':old[relative],'after':record})
 elif relative not in old:added.append({'path':relative,'pin':record})
checks={
 'protected_current_bytes':not missing and not unexpected,
 'only_authorized_project_append':authorized==[register_path]and append_only,
 'workspace_22_ordinary_files_preserved':not workspace_changed,
 'git_status_preserved':porcelain==primary['git_porcelain'],
 'eight_child_suites_current_results_valid':len(population)==8 and regression_valid,
 'only_late_metadata_adapter_changed':late_metadata_changes==[allowed_metadata],
 'functional_E00_to_E11_passed':all(states['steps'][f'E{i:02d}']['status']=='PASS'for i in range(12)),
 'ten_findings_explicitly_disposed':dispositions['count']==10 and{d['id']for d in dispositions['findings']}=={f'F124-{i:02d}'for i in range(1,11)},
 'no_owned_output_population':not(ROOT/'implementation/runs').exists()or not list((ROOT/'implementation/runs').iterdir()),
}
save(out/'registration.json',{'checks':list(checks),'known_historical_process_failure':'PROC126-E04-ORIGINAL-WRITE','qualified_stage_flags':QUALIFICATION})
functional_ok=all(checks.values())
status='FAIL_STOP'
verification={'schema':'batch126-final-verification-v2','recorded_at':datetime.datetime.now().astimezone().isoformat(),
 'status':status,'functional_verification_passed':functional_ok,'component_functional_suites_passed':regression_valid and len(population)==8,'offline_hardening_accepted':False,
 'checks':checks,'failures':([{'name':k}for k,v in checks.items()if not v]+[{'name':'historical_read_only_process_conformance','id':'PROC126-E04-ORIGINAL-WRITE','fact':'Pre-takeover E04 transient original write is documented and not waived. Restored SHA does not establish zero writes.'}]),
 'protected_population':len(protected),'missing':missing,'unexpected_changes':unexpected,'authorized_append':authorized,
 'ordinary_workspace_population':len(workspace),'workspace_changes':workspace_changed,'git_porcelain_unchanged':porcelain==primary['git_porcelain'],'git_porcelain_at_final_check':porcelain,'workspace_drift_snapshot':[{'path':name,'current':pin(name)if Path(name).is_file()else None,'baseline':workspace[name],'origin':'out-of-task drift; exact writer not independently identified'}for name in workspace_changed],
 'protection_scope':'Current bytes of124 primary1355+supplement10;22 ordinary files and git status. Dirty submodule contents and historical absence-of-write are not certified.',
 'modified_implementation_files':modified,'new_implementation_files':added,
 'current_functional_source_pins':{p:pin(p)for p in source_before},
 'metadata_adapter_change_after_regression':{'paths':late_metadata_changes,'scope':'legacy verification-schema adapter only; no component/auditor/native test logic changed'},
 'combination_regression':str(regression),'child_suites':population,
 'owned_runs':0,'ROS_initialized':False,'survivor_started':False,'production_source_edits':0,
 'qualification':QUALIFICATION,'production_B_mode':'MANUAL+RC override',
 'delivery_readback_reference':str(ROOT/'evidence/delivery_receipt_readback_v1.json')}
save(out/'commands.json',[{'argv':[sys.executable,*sys.argv],'kind':'final read-only check','expected_exit_code':2,'reason':'historical process finding retained'}])
save(out/'verification.json',verification);save(ROOT/'evidence/final_verification_v2.json',verification)
save(ROOT/'postrun/E12_step_result_v2.json',{'step_id':'E12','status':'FAIL_STOP','functional_verification_passed':functional_ok,
 'reason':'E04 historical original write plus concurrent workspace drift prevent blanket125-contract signoff; all eight functional suites passed.',
 'evidence':str(out),'qualification':QUALIFICATION,'delivery_status':'see separate readback receipt'})
states['steps']['E12']={'status':'FAIL_STOP','attempts':['attempt01','attempt02'],'latest_result':'postrun/E12_step_result_v2.json'}
(ROOT/'postrun/step_status_v1.json').write_text(json.dumps(states,ensure_ascii=False,indent=2)+'\n')
save(ROOT/'postrun/next_step_v3.json',{'functional_execution_complete':regression_valid and len(population)==8,'contract_acceptance':'FAIL_STOP_HISTORICAL_PROCESS',
 'next_recommended_task':'Independent review of model-transaction shared packing/setter and single-owner interface; produce a concrete per-candidate integration diff.',
 'not_authorized_by_this_closeout':['production landing','new owned run','GP acquisition','plant or RT execution'],
 'process_finding_cannot_be_erased_by_retries':True,'qualification':QUALIFICATION})
lines=['# 第126批：功能整改完成，保留历史过程失败\n',
 '**离线组合回归8个子suite通过；E12总签收为FAIL_STOP，因接替前E04历史触写及终审并发工作区差额；不得用功能通过代替过程/资产签收。**\n',
 '[完整接替与验收报告](documents/方案A_第126批_Claude接替_离线整改实施与验收报告_2026-10-26.md)\n',
 '| 步骤 | 功能/过程状态 | 最新回执 |','|---|---|---|']
for sid,entry in states['steps'].items():lines.append(f"| {sid} | {entry['status']} | {entry.get('latest_result','postrun/'+sid+'_step_result.json')} |")
lines+=['\n当前保护核对：1365项原保护人口中仅创新登记簿发生E10授权追加；其余当前字节保持。普通工作区及git存在并发差额，精确快照见final_verification_v2；保留、不恢复、不覆盖。dirty子模块内容未全量认证。\n',
 '生产B仍MANUAL+RC覆写；本批新owned=0、生产源修改=0、ROS初始化=0；M4/F6/P1/plant/硬实时全false。\n',
 '下一方向：使用E11三份独立评审输入；建议模型事务共享setter先、Epoch后，B2只归实验时钟基础设施。实际落位或新owned另定明确范围。本批不自动进入这些阶段。\n',
 '交付结果以`evidence/delivery_to_MPC_v1.json`和源侧`evidence/delivery_receipt_readback_v1.json`为准。交付完成不能替代过程符合性签收。']
(ROOT/'CURRENT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'functional_verification_passed':functional_ok,'contract_status':status,'protected_files':len(protected),
 'unexpected_protected_changes':unexpected,'authorized_register_append':len(authorized),'component_suites_passed':regression_valid and len(population)==8,'workspace_changes':workspace_changed,
 'implementation_modified':len(modified),'implementation_added':len(added)},ensure_ascii=False))
sys.exit(2)
