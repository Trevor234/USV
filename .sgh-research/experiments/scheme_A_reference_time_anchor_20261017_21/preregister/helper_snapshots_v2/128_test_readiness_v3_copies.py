#!/usr/bin/env python3
"""Bounded offline original-positive/fresh-copy semantic negatives. No ROS nodes.

Every case materializes its changed inputs under a new evidence directory.
Identity roots remain those independently locked in the validation contract.
Copy digests deliberately differ: this tests semantic rejection beyond the
normal CLI's immutable-input hash gate. No copy can qualify an actual run.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import validate_readiness_v3 as v


def write_json(path,value):
    path.write_text(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n')


def read_json(path):
    return v.strict_json(path.read_bytes())


def change_json(root,name,fn):
    p=root/name;d=read_json(p);fn(d);write_json(p,d)


def change_source(root,name,fn):
    p=root/name;rows=v.jsonl(p.read_bytes());fn(rows)
    p.write_text(''.join(json.dumps(r,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n' for r in rows))


def change_ready(root,fn):
    change_source(root,'observer/source.jsonl',lambda rows:fn(next(x for x in rows if x['type']=='legacy_ready')['readiness']))


def drop_source(root,name,tag,first=False):
    def mutate(rows):
        indices=[i for i,x in enumerate(rows) if x['type']==tag]
        del rows[indices[0] if first else indices[-1]]
        # Preserve terminal count accounting to expose the missing semantic row.
        if rows[-1]['type']=='source_summary':
            rows[-1]['generated']=rows[-1]['emitted']=len(rows)-1
    change_source(root,name,mutate)


def modify_storage(root,topic,mode):
    # SQLite is copied, never opened for write at the original path.
    # The host filesystem rejected SQLite writable locking for copied bags.
    # Mutate an in-memory SQLite image, then persist only the copied file bytes.
    path=next((root/'recorder/bag').glob('*.db3'))
    script='''import sqlite3,struct,sys
from pathlib import Path
path,topic,mode=sys.argv[1:]
with sqlite3.connect(':memory:') as db:
 db.deserialize(Path(path).read_bytes())
 rows=db.execute('SELECT m.id,m.data,t.type FROM messages m JOIN topics t ON m.topic_id=t.id WHERE t.name=? ORDER BY m.id',(topic,)).fetchall()
 if mode in ('drop_first','drop_last'):
  chosen=rows[0] if mode=='drop_first' else rows[-1]
  db.execute('DELETE FROM messages WHERE id=?',(chosen[0],))
 elif mode=='wrong_value':
  ident,data,typ=rows[-1]
  assert typ=='std_msgs/msg/Float64' and len(data)==12 and data[:4]==b'\\x00\\x01\\x00\\x00'
  db.execute('UPDATE messages SET data=? WHERE id=?',(data[:4]+struct.pack('<d',.123456),ident))
 elif mode=='wrong_order':
  one,two=rows[0],rows[1]
  db.execute('UPDATE messages SET data=? WHERE id=?',(two[1],one[0]))
  db.execute('UPDATE messages SET data=? WHERE id=?',(one[1],two[0]))
 db.commit()
 Path(path).write_bytes(db.serialize())
'''
    subprocess.run([sys.executable,'-c',script,str(path),topic,mode],check=True,timeout=2)


def negative_cases():
    return [
        ('missing_first_applied',lambda r:modify_storage(r,v.APPLIED_TOPIC,'drop_first'),'whole_applied_anchor_population_differs'),
        ('missing_last_applied',lambda r:modify_storage(r,v.APPLIED_TOPIC,'drop_last'),'whole_applied_anchor_population_differs'),
        ('missing_last_anchor',lambda r:drop_source(r,'observer/source.jsonl','legacy_anchor'),'whole_applied_anchor_population_differs'),
        ('physical_same_count_wrong_value',lambda r:modify_storage(r,'/wamv/thrusters/left/thrust','wrong_value'),'physical_full_value_order_differs'),
        ('physical_same_count_wrong_order',lambda r:modify_storage(r,'/wamv/thrusters/left/thrust','wrong_order'),'physical_full_value_order_differs'),
        ('ready_history_tamper',lambda r:change_ready(r,lambda q:q['held_history'][0].update(n=q['held_history'][0]['n']+1)),'ready_complete_held_history_replay'),
        ('ready_preodom_tamper',lambda r:change_ready(r,lambda q:q['preodom_held'][0].update(sequence=2)),'ready_latest_preodom_held_replay'),
        ('ready_postpair_not_later',lambda r:change_ready(r,lambda q:q.update(odom_receive_ns=q['pair_processed_ns'])),'ready_postpair_odom_order'),
        ('ready_after_deadline',lambda r:change_ready(r,lambda q:q.update(legacy_ready_ns=q['prepare_deadline_ns']+1)),'ready_prepare_order_or_expiry'),
        ('ready_stale_input',lambda r:change_ready(r,lambda q:q.update(odom_receive_ns=q['legacy_ready_ns']-100000001)),'ready_source_age_lag_future'),
        ('ready_bool_is_integer',lambda r:change_ready(r,lambda q:q.update(executor_spinning=1)),'ready_bool_type'),
        ('ready_unknown_field',lambda r:change_ready(r,lambda q:q.update(added_true=True)),'ready_44_field_shape'),
        ('capability_payload_tamper',lambda r:change_source(r,'observer/source.jsonl',lambda rows:next(x for x in rows if x['type']=='capability_admission')['capability'].update(backend='forged')),'capability_full_identity_contract'),
        ('capability_lease_tamper',lambda r:change_source(r,'observer/source.jsonl',lambda rows:next(x for x in rows if x['type']=='capability_admission').update(lease_last_after_ns=1)),'capability_lease_replay'),
        ('worker_received_job_omitted',lambda r:drop_source(r,'worker/source.jsonl','job_received'),'complete_job_pipeline_population_differs'),
        ('registration_immutable_job_changed',lambda r:change_source(r,'observer/source.jsonl',lambda rows:next(x for x in rows if x['type']=='candidate_registration')['job'].update(target_ns=1)),'immutable_job_pipeline_payload_differs'),
        ('registration_control_changed',lambda r:change_source(r,'observer/source.jsonl',lambda rows:next(x for x in rows if x['type']=='candidate_registration').update(first_control=[0.0,0.0])),'registration_candidate_payload_differs'),
        ('publisher_stream_omitted',lambda r:change_json(r,'publisher/session_summary.json',lambda d:d['streams'].pop('cycle')),'publisher_four_streams_missing_or_unknown'),
        ('unknown_source_event',lambda r:change_source(r,'observer/source.jsonl',lambda rows:rows[0].update(type='unknown_event')),'unknown_or_failure_observer_source_event'),
        ('failed_witness',lambda r:change_json(r,'observer/witness.json',lambda d:d['tick'][0].update(failed_end=True)),'witness_failed_lifecycle_state'),
        ('unknown_child_ledger',lambda r:change_source(r,'owned_process_ledger.jsonl',lambda rows:rows.insert(-1,dict(type='owned_descendant_observed',name='worker',monotonic_ns=1,boot_id=rows[0]['boot_id'],identity={'pid':999999}))),'unknown_child_or_lifecycle_ledger_event'),
        ('ledger_failed_result',lambda r:change_json(r,'result.json',lambda d:d.update(ledger_failed=True)),'historical_driver_close_or_evidence_failed'),
        ('expired_receipt',lambda r:change_json(r,'publisher/release_receipt.json',lambda d:d.update(attempted_acceptance_steady_ns=d['valid_until_steady_ns'])),'release_expired_or_acceptance_order_invalid'),
        ('replaced_release',lambda r:change_json(r,'release.json',lambda d:d.update(release_nonce='0'*32)),'prepared_receipt_originals_differ'),
        ('source_terminal_missing',lambda r:drop_source(r,'observer/source.jsonl','source_summary'),'exactly_one_event_required'),
        ('source_bad_count',lambda r:change_source(r,'observer/source.jsonl',lambda rows:rows[-1].update(generated=1)),'observer_complete_terminal_source'),
        ('recorder_stop_failure',lambda r:change_json(r,'recorder/terminal.json',lambda d:d.update(Recorder_stop_completed=False,clean=False)),'recorder_stop_or_storage_close_failed'),
        ('synthetic_missing_count_key',lambda r:change_json(r,'synthetic_source/terminal.json',lambda d:d['published_counts'].pop('/clock')),'synthetic_full_raw_count_key_set'),
        ('duplicate_json_key',lambda r:(r/'result.json').write_bytes(b'{"run_id":"a","run_id":"b"}\n'),'reader_error'),
    ]


def replace_fifo(path):
    path.unlink();os.mkfifo(path)


def replace_symlink(path,target):
    path.unlink();path.symlink_to(target)


def replace_parent_symlink(root):
    real=root/'observer_real';(root/'observer').rename(real);(root/'observer').symlink_to(real,target_is_directory=True)


def io_stability_cases(directory):
    results=[];plain=directory/'regular_component.bin';plain.write_bytes(b'bounded-regular-file\n')
    results.append({'case':'regular_file_component','expectation_met':v.read_regular(plain)==b'bounded-regular-file\n'})
    changing=directory/'changed_during_read.bin';changing.write_bytes(b'a'*2048)
    actual_read=os.read;modified=False
    def altered_read(fd,n):
        nonlocal modified
        raw=actual_read(fd,n)
        if raw and not modified:
            modified=True
            with changing.open('ab',buffering=0) as f:
                f.write(b'changed');os.fsync(f.fileno())
        return raw
    rejected=False
    try:
        with patch.object(v.os,'read',side_effect=altered_read):
            v.read_regular(changing)
    except ValueError as e:
        rejected='changed during bounded read' in str(e)
    results.append({'case':'changed_read_component','expectation_met':rejected,'deterministic_injected_file_append':True})
    # MPC's host filesystem refuses named pipes. Use a real temporary POSIX
    # fixture and record the measured result, rather than faking a FIFO target.
    with tempfile.TemporaryDirectory(prefix='p1-readiness-io-') as temporary:
        root=Path(temporary);regular=root/'regular.bin';regular.write_bytes(b'actual-posix-file\n')
        fifo=root/'fifo';os.mkfifo(fifo)
        target=root/'target_link';target.symlink_to(regular)
        actual_dir=root/'actual';actual_dir.mkdir();(actual_dir/'data').write_bytes(b'directory-component\n')
        alias=root/'directory_link';alias.symlink_to(actual_dir,target_is_directory=True)
        for label,path in [('FIFO_nonblocking_rejection',fifo),('target_symlink_rejection',target),('parent_symlink_rejection',alias/'data')]:
            rejected=False;error=None;start=time.monotonic_ns()
            try:v.read_regular(path)
            except (ValueError,OSError) as e:
                error=type(e).__name__+': '+str(e);rejected=True
            elapsed=time.monotonic_ns()-start
            results.append({'case':label,'expectation_met':rejected and elapsed<1_000_000_000,
                'elapsed_ns':elapsed,'error':error,'actual_fixture_type':label,
                'created_actual_POSIX_fixture':True,'fixture_directory':temporary,'fixture_removed_after_test':True})
    return results


def copy_inputs(contract,destination):
    original=Path(contract['original_run']);destination.mkdir(exist_ok=False)
    for pin in contract['record_files'].values():
        p=Path(pin['path'])
        if p.is_relative_to(original):
            target=destination/p.relative_to(original);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    for relative,pin in contract['bag_files'].items():
        target=destination/'recorder/bag'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(pin['path'],target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--io-only',action='store_true',help='only the independent bounded reader IO component fixtures')
    args=parser.parse_args();started=time.monotonic();args.contract=args.contract.absolute();contract=v.strict_json(v.read_regular(args.contract))
    args.output_dir.mkdir(exist_ok=False);reports=[]
    if args.io_only:
        reports=io_stability_cases(args.output_dir)
        summary={'schema':'p1-readiness-v3-reader-io-components/v1','all_expectations_met':all(x['expectation_met'] for x in reports),
            'case_count':len(reports),'cases':reports,'elapsed_seconds':time.monotonic()-started,
            'validator_sha256':v.digest(v.read_regular(v.__file__)), 'negative_tool_sha256':v.digest(v.read_regular(__file__)),
            'actual_ROS_nodes_created':False,'fixture_only':True,**{k:False for k in v.FALSE_GATES}}
        v.create_only(args.output_dir/'summary.json',summary)
        print(json.dumps({'all_expectations_met':summary['all_expectations_met'],'case_count':len(reports),'elapsed_seconds':summary['elapsed_seconds']}))
        return 0 if summary['all_expectations_met'] else 2
    original=v.load_snapshot(contract);before=v.rehash_snapshot(original)
    baseline=v.validate_snapshot(original,contract)
    v.create_only(args.output_dir/'original_positive.json',baseline)
    reports.append({'case':'original_positive','component_suite_passed':baseline['component_suite_passed'],'expectation_met':baseline['component_suite_passed']})
    for name,mutate,wanted in negative_cases():
        if time.monotonic()-started>40:
            raise RuntimeError('negative tool finite 40s work budget expired')
        directory=args.output_dir/name;copy_inputs(contract,directory);mutate(directory)
        try:
            snapshot=v.load_snapshot(contract,negative_copy=directory)
            report=v.validate_snapshot(snapshot,contract)
            # These missing stored rows should be rejected already by the reader's
            # metadata count conservation; all later gates are then unreachable.
            codes={x['code'] for c in report['components'].values() for x in c['issues']}
            matched=(not report['component_suite_passed'] and wanted in codes)
        except Exception as e:
            report={'schema':'p1-readiness-v3-copy-negative/v1','component_suite_passed':False,
                    'reader_error':type(e).__name__+': '+str(e),**{k:False for k in v.FALSE_GATES}}
            matched=wanted=='reader_error' or (name in ('missing_first_applied','missing_last_applied') and 'metadata counts do not conserve' in str(e))
            codes={'reader_error'}
        report.update(negative_case=name,expected_negative_code=wanted,negative_expectation_met=matched,
            deliberate_mutation_semantic_test=True,qualification_allowed=False)
        v.create_only(directory/'component_report.json',report)
        reports.append({'case':name,'expectation_met':matched,'expected_code':wanted,'observed_codes':sorted(codes)})
    reports.extend(io_stability_cases(args.output_dir))
    unchanged=v.rehash_snapshot(original)==before
    summary={'schema':'p1-readiness-v3-copy-regression/v1','all_expectations_met':unchanged and all(x['expectation_met'] for x in reports),
        'original_inputs_unchanged':unchanged,'cases':reports,'case_count':len(reports),
        'elapsed_seconds':time.monotonic()-started,'raw_negative_copies_preserved':True,
        'contract_sha256':v.digest(v.read_regular(args.contract)),
        'validator_sha256':v.digest(v.read_regular(v.__file__)),'negative_tool_sha256':v.digest(v.read_regular(__file__)),
        'fixture_only':True,**{k:False for k in v.FALSE_GATES}}
    v.create_only(args.output_dir/'summary.json',summary)
    print(json.dumps({'all_expectations_met':summary['all_expectations_met'],'cases':len(reports),
        'elapsed_seconds':summary['elapsed_seconds'],'original_inputs_unchanged':unchanged}))
    return 0 if summary['all_expectations_met'] else 2


if __name__=='__main__':
    raise SystemExit(main())
