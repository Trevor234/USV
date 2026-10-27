#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent
B=D/'build/publication_attempt01'


def pin(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def load(rel):return json.loads((D/rel).read_text())


def put(rel,d):
    with (D/rel).open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')


def population():
    result={};dirs=[]
    for p in sorted(D.rglob('*')):
        assert not p.is_symlink(),str(p)
        if p.is_dir():dirs.append(str(p.relative_to(D)))
        else:result[str(p.relative_to(D))]=pin(p)
    return result,dirs


def prepare():
    r=load('build/publication_attempt01/result.json');assert r['passed']
    p=D/'CURRENT.md'
    with (D/'preflight/CURRENT_initial_v1.md.snapshot').open('xb') as f:f.write(p.read_bytes())
    p.write_text('''# 方案A当前状态：第32批（2026-10-19）

新派生regulator已接入共享publication_result_v1.hpp：两侧API返回、每侧实际start锚点、span/gap/rate和关闭结果分账。既有p1_admission fallback、完整合同和协议逐字节未改；execute硬禁用仍在。

首次构建通过，新runtime ELF和一个纯C++Native目标编译完成。14组事件、117断言通过，约73.67s；编译输入1403、runtime loader库54。Native无ROS头/链接/context或执行器端点，send为注入局部事件。新runtime的实际publish分支没有运行，不能称M4或双侧真实执行资格。

新ELF SHA：ada12f87305c266f53eccce249548ab882ad0e907f9865182a2c7315a0f50177；source bundle SHA：71b1bcff743091a931af075df3a34bd549b0930d0093e55d08ea99519f02b2a9。新候选没有owned运行身份；其余四角色只复用原精确bin，不继承旧Observer认证到新ELF。

原第29批101/101接纳及原RMSE失败保留。B4八组pending、B5/M0b/M4/F6/P1仍未闭合，execute/true_plant/research均false。旧业务dirty改动及单独real.launch.py变化保留。

下一步优先V1当前版本真实Sink第一次入队失败：先完成新owned prepare/peer/source绑定，预注册一个有界故障触发及关闭记录；不重新扫同类正常run或启动调参。V2将native阻塞/active watchdog与能力receipt租约分别设计，V3再核验来源/时钟重验交错。顺序B4/最终版确认→B5/M0b→M4→模型事务/F6→P1复判→P2。

MPC只写本批新目录。最终交付权威为delivery_verification.json；该文件不存在时为待交付，存在且passed/二次SHA读回通过后表示交付完成。旧批归档和失败不回写。
''')
    put('batch_status_final.json',dict(schema='publication-component-status/v1',batch=32,date='2026-10-19',
        component_validation_complete=True,Native_cases=14,Native_assertions=117,build_attempts=1,
        runtime_compiled=True,runtime_publish_branch_executed=False,Native_ROS_context_created=False,
        source_fallback_contract_protocol_unchanged=True,old_dirty_changes_preserved=True,
        prior_actual_case_passed=False,new_owned_run_qualified=False,
        stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False,
        next_action='V1 exact candidate owned identity and first real Sink enqueue failure',
        current_delivery_authority='delivery_verification.json if present; otherwise pending'))


def seal():
    old=load('preflight/workspace_initial_local_v1.json');new=load('preflight/workspace_final_local_v1.json')
    assert old['passed'] and new['passed']
    for x in [old,new]:
        p=x['protection'];assert p['unique_raw_files_reread']==41298 and p['logical_bytes_streamed']==5146759919
        assert p['business_diff_sha256']=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5'
    assert old['protection']['boot_id']==new['protection']['boot_id']
    r=load('build/publication_attempt01/result.json');s=load('verification/component_scope_audit_v1.json')
    assert r['passed'] and r['source_unchanged'] and r['elapsed_seconds']<=120 and r['cases']==14 and r['assertions']==117
    assert s['passed'] and not s['unexpected_changes_outside_publication_shutdown_include']
    assert not s['runtime_publish_branch_executed'] and not s['Native_compile_dependency_has_ROS_headers']
    bundle=json.loads((B/'source_bundle.json').read_text())
    assert len(bundle['files'])==36
    for rel,row in bundle['files'].items():
        expected={k:row[k] for k in ['bytes','sha256']}
        assert pin(Path(row['path']))==pin(B/'source_snapshot'/rel)==expected
    for field in ['binary','Native_binary','Native_event_report']:
        row=r[field];assert pin(Path(row['path']))=={k:row[k] for k in ['bytes','sha256']}
    for filename in ['compiler_dependency_pins.json','runtime_library_pins.json']:
        data=json.loads((B/filename).read_text())
        values=list(data['files'].values())+([data['compiler']] if 'compiler' in data else [])
        for row in values:assert pin(Path(row['resolved_path']))=={k:row[k] for k in ['bytes','sha256']}
    f,_=population()
    assert sum(x['bytes'] for x in f.values())<104857600,'whole component archive output budget'
    put('postrun/final_QA_v1.json',dict(schema='publication-component-local-QA/v1',passed=True,
        passed_semantics='new source-derived component and exact local/archive verification only',
        fixed_files=f,fixed_file_count=len(f),source_bundle_sha256=r['source_bundle']['sha256'],runtime_binary_sha256=r['binary']['sha256'],
        Native_cases=14,Native_assertions=117,new_build_attempts=1,component_elapsed_seconds=r['elapsed_seconds'],
        compiler_dependency_inputs=1403,runtime_loader_inputs=54,
        local_old_asset_paths=41298,local_old_asset_bytes=5146759919,
        initial_protection_sha256=pin(D/'preflight/workspace_initial_local_v1.json')['sha256'],
        final_protection_sha256=pin(D/'preflight/workspace_final_local_v1.json')['sha256'],
        new_ROS_runs=0,runtime_publish_branch_executed=False,new_Observer_owned_qualification=False,
        old_real_launch_exception_preserved=True,original_failure_reports_preserved=True,
        current_delivery_pending_at_QA=True,current_delivery_authority='delivery_verification.json',
        stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False))
    f,dirs=population()
    put('archive_inventory_v1.json',dict(schema='publication-component-inventory/v1',directories=dirs,
        files=[dict(relative_path=k,**v) for k,v in f.items()],inventory_excludes_itself=True,
        optional_post_seal_delivery_receipt='delivery_verification.json; create-only after exact full copy and second readback',
        stage_qualified=False,research_conclusion=False))
    actual,_=population();assert set(actual)==set(f)|{'archive_inventory_v1.json'}
    assert all(actual[k]==v for k,v in f.items())
    assert sum(v['bytes'] for v in actual.values())<104857600
    print(json.dumps(dict(passed=True,files=len(actual),bytes=sum(v['bytes'] for v in actual.values()),
        inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],QA_sha256=pin(D/'postrun/final_QA_v1.json')['sha256']),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','seal']);a=p.parse_args()
    prepare() if a.phase=='prepare' else seal()
