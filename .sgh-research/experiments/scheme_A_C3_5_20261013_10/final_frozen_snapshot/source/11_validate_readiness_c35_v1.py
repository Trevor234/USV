#!/usr/bin/env python3
"""C3.5 retrospective bounded-fixture readiness acceptance; no ROS node.

This independent new identity supplements frozen N10 readiness v3 with full
helper/source/binary/raw pin closure, transitive import-path authentication, exact
field domains, actual Capability publisher population/CDR/callback joins and the
current explicit terminal tail acknowledgement. It grants no research stage.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
import time

N10=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_4_20261013_v10')
sys.path.insert(0,str(N10))
import validate_readiness_v3 as inherited

FALSE_GATES=tuple(inherited.FALSE_GATES)+('M4_qualified','P1_qualified','strict_full_chain_qualified','research_conclusion')
EXTRA_WORKER_EVENTS={'capability_source_header','capability_publish_attempt','capability_publish_result'}
MODULE_PATHS={'lease_replay_v1':'lease_replay_v1.py','strict_types_v1':'strict_types_v1.py',
    'check_owned_fixture':'check_owned_fixture.py','owned_auth':'owned_auth.py','owned_release':'owned_release.py',
    'check_p1_execution':'runtime/check_p1_execution.py','check_p1_witness':'runtime/check_p1_witness.py',
    'p1_contract_revision':'runtime/p1_contract_revision.py','validate_readiness_v3':'validate_readiness_v3.py'}


def sha(raw): return hashlib.sha256(raw).hexdigest()
def pin(path):
    raw=inherited.read_regular(Path(path).absolute())
    return dict(path=str(Path(path).absolute()),bytes=len(raw),sha256=sha(raw))


def verify_closure(contract):
    if contract['schema']!='p1-C3.5-retrospective-readiness-component-contract/v1' or contract['fixture_only'] is not True:
        raise ValueError('new retrospective component contract identity differs')
    if contract['parent_root']!=str(N10): raise ValueError('sealed helper parent is not frozen N10')
    if contract['validator']!=pin(__file__): raise ValueError('new validator identity differs')
    if contract['limits']!={'max_file_bytes':134217728,'max_rows':20000,'max_total_bytes':134217728,'timeout_seconds':45}:
        raise ValueError('fixed bounded acceptance limits differ')
    total=0; hashes={}
    if len(contract['pin_closure'])>512: raise ValueError('pin closure population exceeds bound')
    for path,item in contract['pin_closure'].items():
        if item['path']!=path: raise ValueError('pin key/path differs')
        actual=pin(path); total+=actual['bytes']
        if total>134217728: raise ValueError('full closure total byte budget exceeded')
        if actual['bytes']!=item['bytes'] or actual['sha256']!=item['sha256']:
            raise ValueError('pin closure input changed: '+path)
        hashes[path]=actual['sha256']
    run=Path(contract['original_run']);population=[]
    for path in run.rglob('*'):
        if path.is_symlink(): raise ValueError('symlink in complete run population')
        if path.is_file():
            population.append(str(path.relative_to(run)))
            if str(path) not in hashes: raise ValueError('run file absent from complete pin closure: '+str(path))
    if sorted(population)!=contract['historical_run_file_population']:
        raise ValueError('complete historical run file population differs')
    if set(contract['sealed_helpers'])!=set(MODULE_PATHS.values()):
        raise ValueError('complete sealed helper population differs')
    # Every used record/bag/helper/validator and all actual bundle/source/binaries
    # must be in the closure; an omitted entry cannot silently disable checking.
    required=[contract['validator']]+list(contract['record_files'].values())+list(contract['bag_files'].values())+list(contract['sealed_helpers'].values())
    for role,build in contract['expected']['builds'].items():
        required.append(dict(path=build['binary'],sha256=build['binary_sha256']))
        required.extend(build.get('native_binaries',{}).values())
    for role,bundle_pin in contract['expected']['source_bundles'].items():
        required.append(bundle_pin)
        bundle=inherited.strict_json(inherited.read_regular(bundle_pin['path']))
        if bundle['role']!=role or len(bundle['files'])!=bundle_pin['files']:
            raise ValueError('actual source bundle role or population differs')
        required.extend(bundle['files'].values())
    for item in required:
        if item['path'] not in hashes or hashes[item['path']]!=item['sha256']:
            raise ValueError('used input absent from full pin closure: '+item['path'])
    # Historical snapshots remain authoritative for what ran. Current builder
    # drift is declared, not rebound to the old runtime identity.
    for item in contract['historical_tool_audit']:
        name=item['tool']; original=Path(contract['original_run'])/(name.replace('/','__')+'.snapshot')
        if hashes.get(str(original))!=item['historical_sha256'] or hashes.get(str(N10/name))!=item['current_sha256']:
            raise ValueError('tool snapshot/current identity audit differs')
        same=item['historical_sha256']==item['current_sha256']
        if type(item['current_matches_historical']) is not bool or item['current_matches_historical'] is not same:
            raise ValueError('tool historical/current match declaration differs')
        if not same and name!='build_c34_v10.py': raise ValueError('unexpected historical helper drift')
    return dict(files=len(hashes),bytes=total,sha256=hashes,
        historical_tool_versions_independently_distinguished=True)


def verify_imports(contract):
    inherited.import_sealed(contract)
    origins={}
    for name,relative in MODULE_PATHS.items():
        module=importlib.import_module(name);expected=contract['sealed_helpers'][relative]
        path=Path(module.__file__).absolute()
        if path!=Path(expected['path']) or pin(path)['sha256']!=expected['sha256']:
            raise ValueError('transitive sealed helper import differs: '+name)
        origins[name]=dict(path=str(path),sha256=expected['sha256'])
    return origins


def exact_domains(snapshot):
    d=importlib.import_module('strict_types_v1');r=snapshot['records']
    for name,value in r.items(): d.finite_tree(value,path=name)
    d.result(r['run_result']);d.session(r['publisher_session']);d.release(r['release'])
    for row in r['ledger']: d.ledger(row)
    for name in inherited.ROLES: d.owned(r['owned_'+name])
    for name in ('recorder_terminal','synthetic_terminal'): d.terminal(r[name])
    d.report(r['gate_observation'])
    for row in r['publication_observation']['events']: d.publication_event(row)
    return dict(exact_boolean_integer_domains=True,finite_native_64bit_tree=True)


def typed_sha(value):
    value=copy.deepcopy(value)
    value['prediction_dt']={'ieee754_binary64_be':struct.pack('>d',value['prediction_dt']).hex()}
    return sha(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())


def check_capability_source(g,s,expected):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    def decode(blob):
        return s['helpers']['check_p1_execution'].plain(dict(message_to_ordereddict(
            deserialize_message(blob,get_message('usv_research_interfaces/msg/WorkerCapability')))))
    r=s['records']; worker=r['worker_source']; manifest=r['owned_worker'];cfg=r['contract']
    header=g.once(worker,'capability_source_header');terminal=g.once(worker,'worker_summary')
    g.need(worker[0] is header and worker[-1] is terminal,'capability_source_header_terminal_order')
    identity=dict(schema='p1-capability-source-header-v1',run_id=expected['run_id'],boot_id=manifest['boot_id'],
        pid=manifest['pid'],process_start_ticks=manifest['process_start_ticks'],worker_instance=manifest['worker_instance'],
        binary_sha256=expected['builds']['worker']['binary_sha256'],
        source_bundle_sha256=expected['source_bundles']['worker']['sha256'],owned_manifest_sha256=s['hashes']['owned_worker'],
        contract_hash=expected['contract_sha256'],nominal_hash=cfg['nominal_hash'],clock='CLOCK_MONOTONIC',wire_contract_unchanged=True)
    g.need(all(inherited.equal(header.get(k),v) for k,v in identity.items()),'capability_source_header_complete_identity')
    endpoints=[e for e in manifest['endpoints'] if e['kind']=='publisher' and e['topic']==inherited.CAP_TOPIC]
    g.need(len(endpoints)==1 and inherited.equal(header['endpoint'],endpoints[0]),'capability_source_header_actual_GID')
    attempts=inherited.rows_of(worker,'capability_publish_attempt');results=inherited.rows_of(worker,'capability_publish_result')
    count=len(attempts);indices={id(x):i for i,x in enumerate(worker)};previous_end=0
    g.need(count>0 and [x['publish_seq'] for x in attempts]==[x['publish_seq'] for x in results]==list(range(1,count+1)),
        'capability_publisher_complete_attempt_result_sequence')
    d=importlib.import_module('strict_types_v1')
    for a,b in zip(attempts,results):
        d.fields(a,counts=('publish_seq',),times=('snapshot_ns','attempt_record_ns'),path='capability_attempt')
        d.fields(b,counts=('publish_seq',),times=('publish_start_ns','publish_end_ns'),bools=('returned','threw'),path='capability_result')
        value=a['payload'];seq=a['publish_seq']
        g.need(inherited.lease_replay.exact_payload(value),'capability_source_exact_full19_types',publish_seq=seq)
        g.need(a['schema']=='p1-capability-publish-attempt-v1' and b['schema']=='p1-capability-publish-result-v1' and
            a['typed_digest_encoding']=='p1-capability-typed-ieee754-v1' and a['payload_sha256']==b['payload_sha256']==typed_sha(value),
            'capability_source_independent_typed_payload_digest',publish_seq=seq)
        g.need(indices[id(header)]<indices[id(a)]<indices[id(b)]<indices[id(terminal)] and
            previous_end<=a['snapshot_ns']<=a['attempt_record_ns']<=b['publish_start_ns']<=b['publish_end_ns'] and
            b['returned'] is True and b['threw'] is False,'capability_source_successful_call_order',publish_seq=seq)
        previous_end=b['publish_end_ns'];cdr=a['cdr'];blob=bytes.fromhex(cdr['hex'])
        g.need(type(cdr['bytes']) is int and 0<len(blob)<=1048576 and len(blob)==cdr['bytes'] and sha(blob)==cdr['sha256'] and
            cdr['representation']=='typed_reserialization_cdr' and inherited.equal(decode(blob),value),
            'capability_source_full_CDR_payload_binding',publish_seq=seq)
        wanted=dict(schema_version='p1-worker-capability-v1',run_id=expected['run_id'],boot_id=manifest['boot_id'],
            contract_hash=expected['contract_sha256'],nominal_hash=cfg['nominal_hash'],worker_instance=manifest['worker_instance'],
            clock_name='CLOCK_MONOTONIC',backend='acados',matrix_layout='column_major',horizon_steps=cfg['N'],prediction_dt=cfg['dt'],
            pid=manifest['pid'],startup_ns=header['startup_ns'],fault_injection_enabled=cfg['fault_injection_enabled'],fatal=False,reason='')
        g.need(all(inherited.equal(value[k],v) for k,v in wanted.items()),'capability_source_normal_full_identity',publish_seq=seq)
    stored=[x['message'] for x in s['decoded'][inherited.CAP_TOPIC]]
    g.need(len(stored)==count and all(inherited.equal(a['payload'],b) for a,b in zip(attempts,stored)),
        'capability_source_whole_storage_payload_population',source=count,storage=len(stored))
    expected_terminal=dict(schema='p1-capability-source-terminal-v1',capability_generated=count,capability_attempt_records=count,
        capability_publish_calls=count,capability_publish_returned=count,capability_publish_threw=0,capability_result_records=count,
        capability_aborted_before_publish=0,capability_source_io_failed=False,capability_last_publish_seq=count,
        capability_last_payload_sha256=attempts[-1]['payload_sha256'],capability_last_publish_end_ns=results[-1]['publish_end_ns'],
        capability_source_complete=True)
    g.need(inherited.equal(terminal['capability_source'],expected_terminal) and terminal['finished_ns']>=previous_end and
        type(terminal['source_rows_before_terminal']) is int and type(terminal['source_rows_emitted_before_terminal']) is int and
        terminal['source_rows_before_terminal']==terminal['source_rows_emitted_before_terminal']==len(worker)-1 and terminal['source_io_failed'] is False,
        'capability_source_complete_terminal_conservation')
    def decode_raw(raw,index):
        g.need(raw.get('schema')=='p1-input-callback-full-cdr-v1' and raw.get('topic')==inherited.CAP_TOPIC and
            raw.get('message_type')=='usv_research_interfaces/msg/WorkerCapability' and raw.get('rmw_implementation')=='rmw_fastrtps_cpp',
            'capability_callback_raw_contract',source_index=index)
        g.need(len(endpoints)==1 and inherited.equal(raw['publisher_gid'],endpoints[0]['gid']),
            'capability_callback_actual_writer_GID',source_index=index)
        blob=bytes.fromhex(raw['cdr_hex'])
        g.need(type(raw['cdr_bytes']) is int and 0<len(blob)<=1048576 and len(blob)==raw['cdr_bytes'] and sha(blob)==raw['cdr_sha256'],
            'capability_callback_complete_CDR_identity',source_index=index)
        return decode(blob)
    admissions=inherited.check_capabilities(g,s,expected,decode_raw=decode_raw,require_observation=True)
    return dict(source_publish_count=count,storage_count=len(stored),normal_only=True,actual_typed_CDR_verified=True,
        actual_GID_and_callback_CDR_verified=True,admissions=admissions,
        complete_admission_population_bijection=False,packet_unique_identity=False,packet_freshness=False)


def check_tail(g,s,expected):
    r=s['records'];a=r['close_tail_ack'];n=len(s['decoded'][inherited.APPLIED_TOPIC]);signals=inherited.rows_of(r['ledger'],'signal')
    counts={topic:n for topic in [inherited.APPLIED_TOPIC]+expected['physical_topics']}
    g.need(a['schema']=='p1-owned-terminal-tail-ack-v1' and a['run_id']==expected['run_id'] and
        a['receiver_roles_alive'] is True and a['stage_qualified'] is False,'terminal_tail_scope')
    for k in ('publisher_last_applied_sequence','observer_last_applied_sequence','complete_observer_anchor_count'):
        g.need(type(a[k]) is int and a[k]==n,'terminal_tail_exact_count',field=k)
    g.need(inherited.equal(a['expected_counts'],counts) and inherited.equal(a['transport_counts'],counts),'terminal_tail_complete_counts')
    g.need(a['publisher_session_sha256']==s['hashes']['publisher_session'] and r['run_result']['terminal_tail_ack_sha256']==s['hashes']['close_tail_ack'],
        'terminal_tail_raw_digest_binding')
    g.need(a['driver_sha256']==r['run_inputs']['tool_sha256']['prepare_fixture.py'] and
        a['driver_sha256']==r['publication_observation']['driver_tool_sha256'] and
        inherited.equal(a['driver_identity'],r['publication_observation']['driver_identity']), 'terminal_tail_driver_identity')
    g.need(all(x['identity']['ppid']==a['driver_identity']['pid'] for x in inherited.rows_of(r['ledger'],'spawn')),
        'terminal_tail_driver_owned_parent_identity')
    stop={x['name']:x['monotonic_ns'] for x in signals}
    g.need(type(a['checked_ns']) is int and r['publisher_session']['end_steady_ns']<=a['checked_ns']<stop['observer'],
        'terminal_tail_checked_before_receiver_close')
    return dict(current_v1_acknowledgement_record_consistency=True,source_storage_full_tail_counts=True,
        plant_hold_end_known=False,continuous_unknown_child_observation=False)


def validate_snapshot(snapshot,contract):
    # Current Worker events are admitted only with the independent complete
    # source/CDR/identity/conservation component below. No event is discarded.
    previous=inherited.WORKER_EVENTS
    inherited.WORKER_EVENTS=previous|EXTRA_WORKER_EVENTS
    try: report=inherited.validate_snapshot(snapshot,contract)
    finally: inherited.WORKER_EVENTS=previous
    extra=(('exact_current_field_domains',lambda g:exact_domains(snapshot)),
        ('current_capability_source_CDR_population',lambda g:check_capability_source(g,snapshot,contract['expected'])),
        ('current_terminal_tail_acknowledgement',lambda g:check_tail(g,snapshot,contract['expected'])))
    for name,fn in extra:
        g=inherited.Gate();detail={}
        try: detail=fn(g)
        except (ValueError,KeyError,TypeError,IndexError,OverflowError) as e:
            g.need(False,'current_component_schema_or_domain_error',error=type(e).__name__+': '+str(e))
        report['components'][name]=dict(passed=not g.issues,issues=g.issues,**detail)
    report.update(schema='p1-C3.5-readiness-bounded-component-acceptance/v1',
        component_suite_passed=all(x['passed'] for x in report['components'].values()),
        actual_ROS_nodes_created=False,no_old_shared_v2_identity_claim=True,
        historical_evidence_only=True,all_stage_qualifications=False,
        scope='current frozen N10 synthetic owned fixture readiness/terminal components under independent C3.5 rule identity')
    report['coherent_fresh_copy_fixture']=contract.get('coherent_fresh_copy_fixture',False) is True
    report.update({k:False for k in FALSE_GATES})
    report['limitations']=[x for x in report['limitations'] if 'publisher-source count' not in x and 'final-delivery close' not in x]+[
        'Capability publisher population is closed for this normal fixture; observer admission remains ordered subset without packet identity/freshness',
        'current terminal tail acknowledgement has historical full source/storage counts; no continuous unknown-child or plant ACK qualification']
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--contract',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();start=time.monotonic_ns();raw=inherited.read_regular(args.contract.absolute());contract=inherited.strict_json(raw)
    try:
        before=verify_closure(contract);origins=verify_imports(contract);snapshot=inherited.load_snapshot(contract)
        report=validate_snapshot(snapshot,contract);after=verify_closure(contract)
        report['pin_closure_unchanged']=before['sha256']==after['sha256'];report['raw_inputs_unchanged']=inherited.rehash_snapshot(snapshot)==snapshot['hashes']
        report['component_suite_passed'] &= report['pin_closure_unchanged'] and report['raw_inputs_unchanged']
        report['pin_closure']=dict(files=before['files'],bytes=before['bytes']);report['sealed_import_origins']=origins
    except Exception as e:
        report=dict(schema='p1-C3.5-readiness-bounded-component-acceptance/v1',component_suite_passed=False,
            reader_error=type(e).__name__+': '+str(e),fixture_only=True,actual_ROS_nodes_created=False,all_stage_qualifications=False,
            **{k:False for k in FALSE_GATES})
    report.update(contract_sha256=sha(raw),validator_sha256=pin(__file__)['sha256'],elapsed_ns=time.monotonic_ns()-start)
    inherited.create_only(args.output,report)
    print(json.dumps(dict(component_suite_passed=report['component_suite_passed'],reader_error=report.get('reader_error'),output=str(args.output))))
    return 0 if report['component_suite_passed'] else 2
if __name__=='__main__': raise SystemExit(main())
