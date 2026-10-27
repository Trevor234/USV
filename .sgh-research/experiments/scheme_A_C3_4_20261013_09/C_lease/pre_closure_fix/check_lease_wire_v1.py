#!/usr/bin/python3
"""Actual DDS finite lease component joins, separate from normal owned runs."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.dont_write_bytecode=True
import lease_replay_v1 as lease
import validate_readiness_v3 as safe

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load_json(path):return safe.strict_json(safe.read_regular(path))
def load_rows(path):return [safe.strict_json(x) for x in safe.read_regular(path).splitlines() if x]

def check(run):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    typ=get_message('usv_research_interfaces/msg/WorkerCapability')
    root=Path(run).absolute();issues=[]
    def need(ok,code,**detail):
        if not ok:issues.append(dict(code=code,**detail))
        return bool(ok)
    files=['manifest.json','terminal.json','publisher_source.jsonl','observer_source.jsonl','recorder_source.jsonl','capability.db3']
    hashes={name:sha(safe.read_regular(root/name)) for name in files}
    manifest=load_json(root/'manifest.json');terminal=load_json(root/'terminal.json')
    published=load_rows(root/'publisher_source.jsonl');observer=load_rows(root/'observer_source.jsonl');recorded=load_rows(root/'recorder_source.jsonl')
    need(manifest['schema']=='p1-C3.4-capability-wire-component-v1' and manifest['component_verification_only'] is True and
        manifest['production_owned_startup_qualified'] is False and manifest['physical_publisher_endpoints']==0 and
        manifest['packet_freshness'] is False,'wire_component_scope')
    need(manifest['evidence_producer_role']=='explicitly-seeded-source-linked-component; not production Worker or native solver',
        'wire_component_producer_role')
    gids=[manifest[k]['gid'] for k in ('publisher','observer_subscription','recorder_subscription')]
    need(all(type(g) is list and len(g)==24 and all(type(b) is int and 0<=b<=255 for b in g) and any(g) for g in gids),
        'wire_actual_endpoint_GID_shape')
    gid=gids[0];topic=manifest['publisher']['topic'];topic_type=manifest['publisher']['type']
    def decode(blob):
        message=deserialize_message(blob,typ)
        return {name:getattr(message,name) for name in lease.FIELDS}
    database=sqlite3.connect((root/'capability.db3').as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        topics=database.execute('SELECT id,name,type,serialization_format FROM topics').fetchall()
        need(topics==[(1,topic,topic_type,'cdr')],'wire_SQLite_exact_topic')
        stored=database.execute('SELECT id,topic_id,timestamp,data FROM messages ORDER BY id').fetchall()
        total=database.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
        need(total==len(stored)<=64,'wire_SQLite_whole_population_bound')
    finally:database.close()
    callbacks=[r for r in observer if r.get('type')=='capability_admission' or (r.get('type')=='resource_rejected' and r.get('interface')=='capability')]
    count=len(published)
    need(count>0 and count==len(stored)==len(recorded)==len(callbacks),'wire_four_population_exact_counts')
    need(terminal.get('passed') is True and all(type(terminal.get(k)) is int and terminal[k]==count for k in
        ('publisher_count','observer_count','recorder_count')),'wire_terminal_conservation')
    for i,(publication,storage,record,callback) in enumerate(zip(published,stored,recorded,callbacks),1):
        _,topic_id,stored_ns,blob=storage;decoded=decode(blob);raw=callback.get('raw_input')
        need(publication['sequence']==record['sequence']==i and topic_id==1,'wire_ordered_population_sequence',index=i)
        need(lease.exact_payload(decoded) and safe.equal(publication['payload'],decoded),
             'wire_publisher_full19_actual_SQLite_join',index=i)
        pub_blob=bytes.fromhex(publication['cdr_hex'])
        need(type(publication.get('cdr_bytes')) is int and len(pub_blob)==publication['cdr_bytes'] and
            sha(pub_blob)==publication['cdr_sha256'] and safe.equal(decode(pub_blob),decoded),
            'wire_publisher_source_complete_CDR',index=i)
        need(record['receive_ns']==stored_ns and record['serialized_bytes']==len(blob) and record['cdr_sha256']==sha(blob),
            'wire_recorder_source_actual_SQLite_CDR_join',index=i)
        need(safe.equal(publication['publisher_gid'],gid) and safe.equal(record['publisher_gid'],gid),
            'wire_publisher_recorder_actual_writer_GID',index=i)
        if not need(type(raw) is dict,'wire_original_callback_raw_missing',index=i):continue
        need(raw['callback_sequence']==i and raw['schema']=='p1-input-callback-full-cdr-v1' and raw['topic']==topic and
            raw['message_type']==topic_type and safe.equal(raw['publisher_gid'],gid),
            'wire_original_callback_actual_GID_sequence',index=i)
        callback_blob=bytes.fromhex(raw['cdr_hex'])
        need(type(raw.get('cdr_bytes')) is int and len(callback_blob)==raw['cdr_bytes'] and sha(callback_blob)==raw['cdr_sha256'] and
            safe.equal(decode(callback_blob),decoded),'wire_original_callback_full_CDR_SQLite_typed_join',index=i)
        need(type(publication['publish_start_ns']) is int and type(publication['publish_end_ns']) is int and
             publication['publish_start_ns']<=publication['publish_end_ns'] and raw['entry_steady_ns']<=callback['receive_ns']<=callback.get('validation_commit_ns',callback['receive_ns']),
            'wire_original_callback_observed_time_order',index=i)
    def decode_raw(raw,index):return decode(bytes.fromhex(raw['cdr_hex']))
    replay=lease.replay(observer,manifest['expected'],manifest['timeout_ns'],need,decode_raw=decode_raw,require_observation=True)
    actual=terminal['actual_original_callback_state'];want=replay['final']
    for key in ('last_valid_ns','worker_instance','worker_valid','worker_unusable','last_capability'):
        need(safe.equal(actual[key],want[key]),'wire_actual_original_callback_final_state',field=key)
    need(type(actual['input_commit_ordinal']) is int and actual['input_commit_ordinal']==0,'wire_capability_does_not_increment_input_ordinal')
    scenario=manifest['scenario'];proof=replay['proof']
    expected_renewed={'invalid_foreign':[True,False,False,True],'fatal':[True,False,False],
        'instance':[True,False,False],'expired':[True,False],'duplicate':[True,True],'no_valid':[False]}
    need([p['renewed'] for p in proof]==expected_renewed[scenario],'wire_declared_scenario_independent_renewals')
    need(want['worker_unusable'] is (scenario in ('fatal','instance','expired')),'wire_declared_scenario_terminal')
    # Coherent copies change mutually supporting logged flags and lease fields,
    # retaining all original raw/typed populations. Independent replay must
    # reject the changed semantic fields, rather than relying on file hashes.
    negatives=[]
    for name in ('renewed_before_after','terminal_worker_valid'):
        forged=copy.deepcopy(observer);admitted=[r for r in forged if r.get('type')=='capability_admission']
        target=next((r for r in admitted if not r['renewed']),admitted[-1])
        if name=='renewed_before_after':
            target['renewed']=not target['renewed'];target['lease_last_after_ns']=target['validation_commit_ns'] if target['renewed'] else 0
        else:
            target['terminal_run']=not target['terminal_run'];target['lease_observation']['after']['worker_unusable']=target['terminal_run']
            target['lease_observation']['after']['worker_valid']=not target['terminal_run']
        failures=[]
        lease.replay(forged,manifest['expected'],manifest['timeout_ns'],lambda ok,code,**detail: failures.append(dict(code=code,**detail)) if not ok else None,decode_raw=decode_raw,require_observation=True)
        semantic=any(x['code'].startswith('capability_independent_') for x in failures)
        need(semantic,'wire_coherent_state_forgery_not_rejected',case=name)
        negatives.append(dict(case=name,semantic_rejected=semantic,issues=failures))
    unchanged={name:sha(safe.read_regular(root/name)) for name in files}==hashes
    need(unchanged,'wire_inputs_changed_during_check')
    return dict(schema='p1-C3.4-lease-wire-check-v1',passed=not issues,issues=issues,run=str(root),scenario=scenario,
        storage_count=len(stored),source_count=count,callback_count=len(callbacks),independent_replay=replay,
        coherent_negatives=negatives,input_sha256=hashes,input_bytes_unchanged=unchanged,
        component_verification_only=True,normal_owned_startup_qualified=False,source_packet_freshness=False,
        resource_oversize_wire_covered=False,exact_timeout_equality_wire_covered=False,
        C3_general=False,execute=False,P1=False,research_conclusion=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=check(a.run)
    with a.output.open('x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print(json.dumps({k:result[k] for k in ('passed','scenario','storage_count','callback_count','issues')},sort_keys=True));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
