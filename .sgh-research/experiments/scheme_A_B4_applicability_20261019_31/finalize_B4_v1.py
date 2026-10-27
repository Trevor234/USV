#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent


def pin(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def load(rel):return json.loads((D/rel).read_text())


def put(rel,d):
    with (D/rel).open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')


def files():return {str(p.relative_to(D)):pin(p) for p in sorted(D.rglob('*')) if p.is_file()}


def prepare():
    b=load('evidence/MPC_backlog_delivery_v1.json');assert b['passed'] and len(b['batches'])==7
    assert sum(r['files'] for r in b['batches'])==5411
    current=D/'CURRENT.md'
    with (D/'preflight/CURRENT_initial_v1.md.snapshot').open('xb') as f:f.write(current.read_bytes())
    current.write_text('''# 方案A当前状态：第31批（2026-10-19）

已实现B4当前配置/政策适用登记和独立检查器：81项合同字段、19项hydro、5角色owned来源/bin/typed参数摘要；13个针对性篡改被拒绝。123项验证输入前后SHA一致；只检查登记/适用性，不授予B4阶段资格。

明确保留模式差异：Observer参考偏移0、Publisher配置偏移2；controlled C绕过后者自主求解。Publisher配置巡航0.6与fixture实际参考0.05m/s分开。5项无直接字面引用的字段明确保留间接消费者核对限制；八组原pending均未关闭。

第29批101/101接纳，原全窗RMSE仍失败。P1部分完成，B4/B5/M0b/M4/F6未闭合，execute/true_plant/research均false。无新增控制实验、Native构建、codegen或调参。旧24处dirty业务修改和单独real.launch.py差异保留。

MPC主机侧可写。第24～30批7个归档、5,411个文件已按封存清单补交，精确人口与二次SHA读回通过；凭据在evidence/MPC_backlog_delivery_v1.json，旧本地sealed档案不回写。本批自己的最终交付只认delivery_verification.json；该文件不存在时为待交付。更早历史远程镜像不因恢复自动宣称重新全检。

下步先复核/派生最小共享发布结果和每侧锚点组件，保持execute关闭，验证部分发布/hold/斜坡/关闭；同一选定版本再完成V1～V3最少必要确认。然后B5/M0b→M4唯一出口→有限模型事务/F6→P1复判→P2。见documents/next_implementation_plan_v1.md。
''')
    put('batch_status_final.json',dict(schema='B4-current-applicability-status/v1',batch=31,date='2026-10-19',
        implementation_complete=True,component_validation='register/source/config integrity only',fields=81,hydro=19,roles=5,
        targeted_cases_rejected=13,new_ROS_runs=0,new_builds=0,old_contract_values_changed=False,
        prior_actual_case_passed=False,backlog_MPC_delivered_batches=7,backlog_MPC_delivered_files=5411,
        current_delivery_authority='delivery_verification.json if present; otherwise pending',
        stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False))


def seal():
    before=load('preflight/workspace_initial_local_v1.json');after=load('preflight/workspace_final_local_v1.json')
    assert before['passed'] and after['passed']
    for x in [before,after]:
        p=x['protection'];assert p['unique_raw_files_reread']==41261 and p['logical_bytes_streamed']==5101947752
        assert p['business_diff_sha256']=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5'
    assert before['protection']['boot_id']==after['protection']['boot_id']
    v=load('verification/verify_register_v2.json');t=load('verification/targeted_checks_v2.json')
    assert v['passed'] and t['passed'] and len(t['targeted_negative_cases'])==13
    assert v['all_inputs_unchanged'] and len(v['input_pins'])==123
    for path,p in v['input_pins'].items():assert pin(Path(path))=={k:p[k] for k in ['bytes','sha256']}
    b=load('evidence/MPC_backlog_delivery_v1.json');assert b['passed'] and len(b['batches'])==7
    assert all(r['full_second_SHA_readback'] and r['exact_population'] for r in b['batches'])
    assert sum(r['files'] for r in b['batches'])==5411
    f=files()
    put('postrun/final_QA_v1.json',dict(schema='B4-current-local-QA/v1',passed=True,
        passed_semantics='current register integrity, targeted rejection and historical backlog delivery; no phase promotion',
        fixed_files=f,fixed_file_count=len(f),
        field_count=81,hydro_count=19,owned_roles=5,typed_digests_recomputed=5,targeted_rejected=13,
        exact_validation_inputs=123,original_pending_groups=8,all_original_pending_groups_closed=False,
        local_old_asset_paths=41261,local_old_asset_bytes=5101947752,
        initial_protection_sha256=pin(D/'preflight/workspace_initial_local_v1.json')['sha256'],
        final_protection_sha256=pin(D/'preflight/workspace_final_local_v1.json')['sha256'],
        backlog_delivery_verified=True,backlog_files=5411,backlog_bytes=sum(r['bytes'] for r in b['batches']),
        current_delivery_pending_at_QA=True,current_delivery_authority='delivery_verification.json',
        stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False))
    f=files();dirs=sorted(str(p.relative_to(D)) for p in D.rglob('*') if p.is_dir())
    put('archive_inventory_v1.json',dict(schema='B4-current-local-inventory/v1',directories=dirs,
        files=[dict(relative_path=k,**v) for k,v in f.items()],inventory_excludes_itself=True,
        optional_post_seal_delivery_receipt='delivery_verification.json; create-only after exact copy/readback; not phase authority',
        stage_qualified=False,research_conclusion=False))
    now=files();assert set(now)==set(f)|{'archive_inventory_v1.json'}
    assert all(now[k]==v for k,v in f.items())
    print(json.dumps(dict(passed=True,files=len(now),bytes=sum(r['bytes'] for r in now.values()),
                         inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],QA_sha256=pin(D/'postrun/final_QA_v1.json')['sha256']),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','seal']);a=p.parse_args()
    prepare() if a.phase=='prepare' else seal()
