#!/usr/bin/env python3
"""Fresh-copy coherent hash/CDR negatives for the new C3.5 acceptance identity.

The CLI is run normally, without negative-copy hash bypass. Raw input, bag and
closure pins are freshly recomputed after each deliberate mutation. Historical
owned identities, source/binaries/helpers and independent expected roots remain
fixed. Original files are read only, no ROS node is created, all copies retained.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import validate_readiness_c35_v1 as v


def dump(path,value):
    with Path(path).open('x') as f:
        json.dump(value,f,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def replace_json(path,value):
    Path(path).write_text(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n')


def rows(path): return v.inherited.jsonl(Path(path).read_bytes())
def jsonfile(path): return v.inherited.strict_json(Path(path).read_bytes())
def writerows(path,value):
    Path(path).write_text(''.join(json.dumps(x,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n' for x in value))


def worker_edit(root,fn):
    p=root/'worker/source.jsonl';value=rows(p);fn(value)
    value[-1]['source_rows_before_terminal']=value[-1]['source_rows_emitted_before_terminal']=len(value)-1
    writerows(p,value)


def observer_edit(root,fn):
    p=root/'observer/source.jsonl';value=rows(p);fn(value)
    value[-1]['generated']=value[-1]['emitted']=len(value)-1;writerows(p,value)


def drop_pair(root):
    def mutate(r):
        for typ in ('capability_publish_attempt','capability_publish_result'):
            r.remove(next(x for x in r if x['type']==typ))
            for i,x in enumerate([x for x in r if x['type']==typ],1):x['publish_seq']=i
        t=r[-1]['capability_source']
        for k in ('capability_generated','capability_attempt_records','capability_publish_calls','capability_publish_returned','capability_result_records','capability_last_publish_seq'): t[k]-=1
    worker_edit(root,mutate)


def mutate_capability_source_and_storage(root):
    # First bootstrap packet is absent from later observer admission; both
    # publisher-source payload/CDR and complete typed storage are coherently
    # modified. The owned, independently locked normal identity remains acados.
    from rclpy.serialization import deserialize_message,serialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    cls=get_message('usv_research_interfaces/msg/WorkerCapability')
    p=next((root/'recorder/bag').glob('*.db3'))
    with sqlite3.connect(':memory:') as db:
        db.deserialize(p.read_bytes())
        ident,raw=db.execute('SELECT m.id,m.data FROM messages m JOIN topics t ON m.topic_id=t.id WHERE t.name=? ORDER BY m.id LIMIT 1',
            (v.inherited.CAP_TOPIC,)).fetchone()
        message=deserialize_message(raw,cls);message.backend='forged';new=serialize_message(message)
        value=v.inherited.importlib.import_module('check_p1_execution').plain(dict(message_to_ordereddict(message)))
        db.execute('UPDATE messages SET data=? WHERE id=?',(new,ident));db.commit();p.write_bytes(db.serialize())
    digest=v.typed_sha(value)
    def mutate(r):
        a=next(x for x in r if x['type']=='capability_publish_attempt');b=next(x for x in r if x['type']=='capability_publish_result')
        a['payload']=value;a['payload_sha256']=b['payload_sha256']=digest
        a['cdr'].update(hex=new.hex(),bytes=len(new),sha256=v.sha(new))
    worker_edit(root,mutate)
    t=root/'synthetic_source/transport_source.jsonl';r=rows(t)
    first=next(x for x in r if x['topic']==v.inherited.CAP_TOPIC)
    first['payload_sha256']=v.sha(new);first['serialized_bytes']=len(new);writerows(t,r)


def mutate_callback_gid(root):
    observer_edit(root,lambda r:next(x for x in r if x['type']=='capability_admission')['raw_input']['publisher_gid'].__setitem__(0,99))


def mutate_callback_cdr(root):
    from rclpy.serialization import deserialize_message,serialize_message
    from rosidl_runtime_py.utilities import get_message
    cls=get_message('usv_research_interfaces/msg/WorkerCapability')
    def mutate(r):
        a=next(x for x in r if x['type']=='capability_admission');raw=a['raw_input']
        message=deserialize_message(bytes.fromhex(raw['cdr_hex']),cls);message.backend='forged';new=serialize_message(message)
        raw.update(cdr_hex=new.hex(),cdr_bytes=len(new),cdr_sha256=v.sha(new));a['capability']['backend']='forged'
    observer_edit(root,mutate)


def mutate_tail(root,fn):
    p=root/'close_tail_ack.json';a=jsonfile(p);fn(a);replace_json(p,a)
    q=root/'result.json';r=jsonfile(q);r['terminal_tail_ack_sha256']=v.sha(p.read_bytes());replace_json(q,r)


def forged_driver(root):
    mutate_tail(root,lambda a:a['driver_identity'].update(pid=a['driver_identity']['pid']+1))
    p=root/'release_publication_observation.json';a=jsonfile(p);a['driver_identity']['pid']+=1;replace_json(p,a)


def cases():
    return [
        ('source_pair_omitted_coherent_counts',drop_pair,'capability_source_whole_storage_payload_population'),
        ('source_and_storage_full19_forged_backend',mutate_capability_source_and_storage,'capability_source_normal_full_identity'),
        ('header_changed_worker_instance',lambda r:worker_edit(r,lambda x:x[0].update(worker_instance='0'*64)),'capability_source_header_complete_identity'),
        ('publish_result_success_integer',lambda r:worker_edit(r,lambda x:next(y for y in x if y['type']=='capability_publish_result').update(returned=1)),'current_component_schema_or_domain_error'),
        ('publish_result_call_before_snapshot',lambda r:worker_edit(r,lambda x:next(y for y in x if y['type']=='capability_publish_result').update(publish_start_ns=1)),'capability_source_successful_call_order'),
        ('source_terminal_false_as_zero',lambda r:worker_edit(r,lambda x:x[-1]['capability_source'].update(capability_source_io_failed=0)),'capability_source_complete_terminal_conservation'),
        ('callback_full_CDR_wrong_GID',mutate_callback_gid,'capability_callback_actual_writer_GID'),
        ('callback_CDR_payload_coherent_forged_backend',mutate_callback_cdr,'capability_full_identity_contract'),
        ('callback_lease_flags_integer',lambda r:observer_edit(r,lambda x:next(y for y in x if y['type']=='capability_admission').update(renewed=1)),'capability_independent_renewed'),
        ('ready_history_coherent_wrong_hold',lambda r:observer_edit(r,lambda x:next(y for y in x if y['type']=='legacy_ready')['readiness']['held_history'][0].update(n=123.0)),'ready_complete_held_history_replay'),
        ('tail_all_counts_coherently_short',lambda r:mutate_tail(r,lambda a:(a.update(publisher_last_applied_sequence=a['publisher_last_applied_sequence']-1,observer_last_applied_sequence=a['observer_last_applied_sequence']-1,complete_observer_anchor_count=a['complete_observer_anchor_count']-1),a.update(expected_counts={k:n-1 for k,n in a['expected_counts'].items()},transport_counts={k:n-1 for k,n in a['transport_counts'].items()}))),'terminal_tail_exact_count'),
        ('tail_publication_driver_coherently_forged',forged_driver,'terminal_tail_driver_owned_parent_identity'),
        ('unknown_worker_event_coherent_terminal_rows',lambda r:worker_edit(r,lambda x:x.insert(-1,dict(type='unknown_worker_event',data=1))),'unknown_or_failure_worker_source_event'),
        ('publisher_zero_counter_is_boolean',lambda r:replace_json(r/'publisher/session_summary.json',dict(jsonfile(r/'publisher/session_summary.json'),publish_errors=False)),'current_component_schema_or_domain_error'),
    ]


def clone_contract(original,destination):
    source=Path(original['original_run']);shutil.copytree(source,destination)
    return copy.deepcopy(original)


def rebind(contract,original,destination):
    source=Path(original['original_run']);contract['original_run']=str(destination)
    for name,item in contract['record_files'].items():
        p=Path(item['path'])
        if p.is_relative_to(source):contract['record_files'][name]=v.pin(destination/p.relative_to(source))
    for name,item in contract['bag_files'].items():contract['bag_files'][name]=v.pin(destination/'recorder/bag'/name)
    new={}
    for old,item in contract['pin_closure'].items():
        p=Path(old)
        if p.is_relative_to(source):
            p=destination/p.relative_to(source);item=dict(v.pin(p),categories=item['categories'])
        new[str(p)]=item
    contract['pin_closure']=new;contract['coherent_fresh_copy_fixture']=True
    contract['input_origin']='deliberate coherent fresh-copy negative; original historical expectation roots unchanged; never experiment evidence'
    return contract


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--contract',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path)
    args=p.parse_args();started=time.monotonic();original=jsonfile(args.contract);args.output_dir.mkdir(exist_ok=False)
    before=v.verify_closure(original)['sha256'];v.verify_imports(original);cs=cases()
    dump(args.output_dir/'preregister.json',dict(schema='p1-C3.5-readiness-coherent-copy-negatives/v1',
        before_first_case=True,cases=[dict(name=n,expected_code=c) for n,_,c in cs],
        original_contract=v.pin(args.contract),negative_tool=v.pin(__file__),validator=v.pin(v.__file__),
        raw_and_storage_pins_recomputed=True,historical_expected_identity_roots_fixed=True,
        case_timeout_seconds=10,total_work_budget_seconds=45,actual_ROS_nodes_created=False,
        qualification_allowed=False))
    reports=[]
    for name,mutate,wanted in cs:
        if time.monotonic()-started>45:raise RuntimeError('45s total offline budget exceeded')
        case=args.output_dir/name;case.mkdir();destination=case/'copied_run';contract=clone_contract(original,destination)
        mutate(destination);contract=rebind(contract,original,destination);dump(case/'coherent_contract.json',contract)
        with (case/'validator.log').open('x') as log:
            rc=subprocess.run([sys.executable,'-B',str(Path(v.__file__).absolute()),'--contract',str(case/'coherent_contract.json'),
                '--output',str(case/'report.json')],stdout=log,stderr=subprocess.STDOUT,timeout=10).returncode
        report=jsonfile(case/'report.json');codes={x['code'] for c in report.get('components',{}).values() for x in c['issues']}
        reports.append(dict(case=name,returncode=rc,component_suite_passed=report['component_suite_passed'],
            observed_codes=sorted(codes),expected_code=wanted,
            expectation_met=rc==2 and report['component_suite_passed'] is False and wanted in codes and not report.get('reader_error'),
            raw_pin_gate_passed=report.get('pin_closure_unchanged') is True,
            coherent_record_storage_pins=True,qualification_allowed=False))
    unchanged=before==v.verify_closure(original)['sha256']
    summary=dict(schema='p1-C3.5-readiness-coherent-copy-negative-results/v1',
        all_expectations_met=unchanged and all(x['expectation_met'] for x in reports),
        cases=reports,case_count=len(reports),original_pin_closure_unchanged=unchanged,
        elapsed_seconds=time.monotonic()-started,actual_ROS_nodes_created=False,
        fixture_only=True,all_stage_qualifications=False,**{k:False for k in v.FALSE_GATES})
    dump(args.output_dir/'summary.json',summary);print(json.dumps(dict(all_expectations_met=summary['all_expectations_met'],case_count=len(reports))))
    return 0 if summary['all_expectations_met'] else 2
if __name__=='__main__':raise SystemExit(main())
