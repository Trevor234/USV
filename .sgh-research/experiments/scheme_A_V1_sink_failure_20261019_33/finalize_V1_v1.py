#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

D=Path(__file__).resolve().parent


def pin(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def load(rel):return json.loads((D/rel).read_text())


def put(rel,d):
    with (D/rel).open('x') as f:json.dump(d,f,indent=2,sort_keys=True,ensure_ascii=False);f.write('\n')


def population(root):
    f={};dirs=[]
    for p in sorted(root.rglob('*')):
        assert not p.is_symlink(),str(p)
        if p.is_dir():dirs.append(str(p.relative_to(root)))
        else:f[str(p.relative_to(root))]=pin(p)
    return f,dirs


def prepare():
    a=load('postrun/V1_actual_fault_audit_v1.json');b=load('postrun/V1_actual_fault_audit_r2_v1.json')
    assert a['passed'] and b['passed'] and not a['V1_preregistered_case_passed'] and b['V1_preregistered_case_passed']
    p=D/'CURRENT.md'
    with (D/'preflight/CURRENT_initial_v1.md.snapshot').open('xb') as f:f.write(p.read_bytes())
    p.write_text('''# 方案A当前状态：第33批（2026-10-19）

V1真实队列故障局部条件已在修复版本观察通过。首run首次Applied比PauseArmed晚2.227552ms，严格门失败，原作者树/数据/报告不改；独立v33r2将arm移到首accepted Decision匹配的认证phase/Applied grant。修复run实际Applied早于arm0.663935ms，并有Stored/GID/认证回调关联。

修复run11.931s，44既有项+468明确诊断记录填满容量512，Decision22(job2/tick21)真实拒绝。Witness记录同次stopping和失效；失败Decision未见于Stored或Owner，后续无新accepted activation或submit授权。槽位当时为空，未命中失败前非空槽交错。五个owned组均空，Observer因Source失败返回2，其余角色0，Recorder正常停止。

正常关闭仍有独立失败：首run尾段接收器已退出，修复run关闭ACK deadline/identity未满足；normal passed=false保持。故障自关闭、Stored近零尾段及owned清理不能变成正常最终版关闭资格。Recorder自报stream_accounting=false不改，SQL/metadata及目标消息另行独立核对。

最终版本Native三组/23断言通过；共三次构建，含测试误用Witness.close导致的首次失败，以及真实先后关系修复。两个raw run、所有审计失败/版本和两套作者树完整封存。数值合同不变，execute禁用，默认workspace/install及旧dirty/冻结资产不变。

修复ELF SHA：697417883320e20d47470a17de1d787252ba988a8da5cde861c0342df862544d；source bundle SHA：9f19e32863ef7910800e43d2bceaf66d89aed94e205ba2ca61eec11e569b70ab。r2是诊断实现修订，不是模型generation切换。B4/B5/M0b/M4/F6/P1及execute/true_plant/research仍未整体合格。

下步先用现有raw实现显式故障自关闭driver/检查分支，不让已退出Observer补发ACK或接收正常尾段；旧正常关闭门不放宽、不重判。然后V2分别验证native阻塞/active watchdog和能力receipt租约，V3后再复判最终统一版。无新缺口不重复V1实际run。

MPC只写本批新归档。交付成功仅认delivery_verification.json；文件不存在时仍为待交付，存在且passed/二次SHA读回通过后表示完成。
''')
    put('batch_status_final.json',dict(schema='V1-real-queue-fault-status/v1',batch=33,date='2026-10-19',
        Native_final_cases=3,Native_final_assertions=23,build_attempts=3,actual_runs=2,
        first_run_preregistered_case_passed=False,repaired_run_preregistered_case_passed=True,
        V1_fault_local_component_observed=True,normal_final_version_close_qualified=False,
        first_original_normal_status=False,repaired_original_normal_status=False,
        stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False,
        new_actual_Observer_physical_output=False,old_failures_reclassified=False,
        delivery_authority='delivery_verification.json if present; otherwise pending',
        next='fault-self-close explicit profile using existing raw; then independent V2 designs'))


def seal():
    start=load('preflight/workspace_initial_local_v1.json');end=load('preflight/workspace_final_local_v2.json')
    assert start['passed'] and end['passed']
    for p in [start['protection'],end['protection']]:
        assert p['unique_raw_files_reread']==41473 and p['logical_bytes_streamed']==5219129128
        assert p['business_diff_sha256']=='d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5'
    assert start['protection']['boot_id']==end['protection']['boot_id']
    freeze=load('postrun/author_freeze_v1.json');assert len(freeze['revisions'])==2
    for rev in freeze['revisions']:
        names={r['relative_path'] for r in rev['files']}
        for root in [Path(rev['author']),Path(rev['snapshot'])]:
            f,dirs=population(root);assert set(f)==names and dirs==rev['directories']
            assert len(f)==rev['count'] and sum(x['bytes'] for x in f.values())==rev['bytes']
            for row in rev['files']:assert f[row['relative_path']]=={k:row[k] for k in ['bytes','sha256']}
    audits=[load('postrun/V1_actual_fault_audit_v1.json'),load('postrun/V1_actual_fault_audit_r2_v1.json')]
    assert audits[0]['passed'] and audits[1]['passed'] and not audits[0]['V1_preregistered_case_passed'] and audits[1]['V1_preregistered_case_passed']
    supplemental=[]
    for rev,audit in zip(freeze['revisions'],audits):
        assert audit['input_sha256_before']==audit['input_sha256_after']
        for path,row in audit['input_sha256_before'].items():assert pin(Path(path))==row
        assert not audit['original_normal_status'] and not audit['normal_final_version_close_qualified']
        assert audit['Recorder_clean_drain'] and audit['actual_owned_groups_all_empty']
        root=Path(rev['author']);run=next((root/'runs').iterdir())
        term=json.loads((run/'recorder/terminal.json').read_text());manifest=json.loads((run/'recorder/owned_manifest.json').read_text())
        assert term['pid']==manifest['pid'] and term['process_start_ticks']==manifest['process_start_ticks']
        assert term['manifest_sha256']==pin(run/'recorder/owned_manifest.json')['sha256']
        assert term['metadata_sha256']==pin(run/'recorder/bag/metadata.yaml')['sha256']
        pub=json.loads((run/'publisher/owned_manifest.json').read_text())
        gid=next(e['gid'] for e in pub['endpoints'] if e['topic']=='/research/control/applied' and e['kind']=='publisher')
        transport=[json.loads(s) for s in (run/'synthetic_source/transport_source.jsonl').read_text().splitlines()]
        db=sqlite3.connect((run/'recorder/bag/bag_0.db3').as_uri()+'?mode=ro',uri=True)
        applied=db.execute("select m.data from messages m join topics t on m.topic_id=t.id where t.name='/research/control/applied'").fetchall();db.close()
        for raw, in applied:
            h=hashlib.sha256(raw).hexdigest();assert any(r['topic']=='/research/control/applied' and r['payload_sha256']==h and r['publisher_gid']==gid for r in transport)
        assert sum(p.stat().st_size for p in run.rglob('*') if p.is_file())<=104857600
        supplemental.append(dict(run=str(run),Recorder_terminal_identity_and_metadata_SHA_verified=True,all_Stored_Applied_CDRs_match_actual_owner_transport=True,Stored_applied=len(applied)))
    put('verification/storage_identity_closure_v1.json',dict(passed=True,runs=supplemental,stage_qualified=False))
    for attempt in [2,3]:
        base=D/'build'/('publication_attempt'+str(attempt).zfill(2));r=json.loads((base/'result.json').read_text())
        assert r['passed'] and r['cases']==3 and r['assertions']==23 and r['elapsed_seconds']<=120
        for leaf in ['compiler_dependency_pins.json','runtime_library_pins.json']:
            j=json.loads((base/leaf).read_text());rows=list(j['files'].values())+([j['compiler']] if 'compiler' in j else [])
            for row in rows:assert pin(Path(row['resolved_path']))=={k:row[k] for k in ['bytes','sha256']}
    assert load('build/publication_attempt01/result.json')['passed'] is False
    f,dirs=population(D)
    assert sum(r['bytes'] for r in f.values())<=268435456,'archive finite output budget'
    put('postrun/final_QA_v1.json',dict(schema='V1-fault-local-final-QA/v1',passed=True,
        passed_semantics='archive integrity, fault-local evidence and faithful case verdicts; no normal-close/stage promotion',
        fixed_file_count=len(f),fixed_files=f,first_case_gate_passed=False,repaired_case_gate_passed=True,
        Native_final_cases=3,Native_final_assertions=23,actual_runs=2,build_attempts=3,
        frozen_author_revisions=[dict(author=r['author'],count=r['count'],bytes=r['bytes']) for r in freeze['revisions']],
        source_failure_expected_Observer_exitcode=2,normal_close_qualified=False,original_normal_reports_both_false=True,
        local_old_asset_paths=41473,local_old_asset_bytes=5219129128,
        initial_protection_sha256=pin(D/'preflight/workspace_initial_local_v1.json')['sha256'],final_protection_sha256=pin(D/'preflight/workspace_final_local_v2.json')['sha256'],
        author_freeze_sha256=pin(D/'postrun/author_freeze_v1.json')['sha256'],
        original_failures_preserved=True,nonempty_pre_failure_slot_interleaving_proven=False,
        current_delivery_pending_at_QA=True,current_delivery_authority='delivery_verification.json',
        stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False))
    f,dirs=population(D)
    put('archive_inventory_v1.json',dict(schema='V1-fault-local-archive-inventory/v1',directories=dirs,
        files=[dict(relative_path=k,**v) for k,v in f.items()],inventory_excludes_itself=True,
        optional_post_seal_delivery_receipt='delivery_verification.json; create-only after exact copy and second readback',
        stage_qualified=False,research_conclusion=False))
    actual,_=population(D);assert set(actual)==set(f)|{'archive_inventory_v1.json'}
    assert all(actual[k]==v for k,v in f.items())
    print(json.dumps(dict(passed=True,files=len(actual),bytes=sum(v['bytes'] for v in actual.values()),inventory_sha256=pin(D/'archive_inventory_v1.json')['sha256'],QA_sha256=pin(D/'postrun/final_QA_v1.json')['sha256']),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','seal']);a=p.parse_args()
    prepare() if a.phase=='prepare' else seal()
