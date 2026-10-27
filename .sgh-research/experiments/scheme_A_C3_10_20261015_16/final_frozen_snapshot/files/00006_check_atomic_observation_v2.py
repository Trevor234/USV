#!/usr/bin/python3
"""Bounded offline C3.2 observation components; no node and no stage Go.

Selection uses the mutex-owned input ordinal, never pre-lock receive sorting.
The input lock is retrospective: this checker records the bytes it read and
requires them unchanged, without claiming an independent pre-run identity pin.
"""
from __future__ import annotations
import argparse
import array
import copy
from collections import Counter, deque
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
N = Path(__file__).absolute().parent
sys.path[:0] = [str(N), str(N / 'runtime')]
import validate_readiness_v3 as safe
import lease_replay_v1 as lease_replay
import check_owned_fixture as reader
import check_source_components_v4 as numerical
import check_activation_provenance_v1 as original_gate
import check_config_identity_v1 as formatter

PREREG = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_4_20261013_09/C_lease/preregister_v1.json')
PREREG_SHA = '81ae2e2678a370de8bacf12f5e446a8c19a6e06f14b9aa281b3e97247f800aea'
CAPTURE_DIGEST_SEMANTICS = 'actual immutable Candidate reserialized CDR integrity; decoded full fields establish payload identity; not network bytes or pointer address'
FORMATTER_CONTRACT = Path('/home/trevor/MPC/scheme_A_config_identity_20261011_04/preregister/formatter_corpus_contract_v1.json')
FORMATTER_SHA = 'cfa8a09a5b1c638aefa9b3acb11c10eb4233d711b386cf9769d5068875b3442c'
MAX_BYTES = 134217728
MAX_ROWS = 20000
SENSORS = numerical.SENSORS
CALLBACK_TYPES = set(SENSORS) | {'legacy_anchor', 'legacy_admission_rejected', 'legacy_history_reset'}
GATE_KEYS = ('early_legacy_enabled early_legacy_measurement early_stopping early_worker_unusable '
    'commit_legacy_enabled commit_legacy_measurement commit_worker_unusable commit_worker_valid commit_sink_failed '
    'final_stopping final_stop_requested fallback_invalid_stopping fallback_invalid_worker_unusable '
    'fallback_source_stopping fallback_source_worker_unusable input_version_equal input_odom_equal input_imu_equal').split()
VERSION = {'task':'task_generation', 'model':'model_generation', 'config':'config_generation',
           'schedule':'schedule_generation', 'epoch':'clock_epoch'}
FLAGS = dict(strict_full_chain=False, C3_general=False, D1=False, B4=False, B5=False,
    M0b=False, M4=False, F6=False, P1=False, execute=False, dynamic_20s_R5=False,
    mixed_turn=False, true_master_clock=False, research_conclusion=False)
sha = lambda raw: hashlib.sha256(raw).hexdigest()
near = original_gate.near


def plain(x):
    if isinstance(x, dict): return {k:plain(v) for k,v in x.items()}
    if hasattr(x, 'tolist'): return plain(x.tolist())
    if isinstance(x, (list, tuple, array.array)): return [plain(v) for v in x]
    return x


class Evidence:
    def __init__(self): self.issues = []; self.groups = {}; self.begin = 0
    def need(self, ok, code, **detail):
        if not ok: self.issues.append({'code':code, **detail})
        return bool(ok)
    def group(self, name, **detail):
        items = self.issues[self.begin:]
        self.groups[name] = {'passed':not items, 'issues':items, **detail}
        self.begin = len(self.issues)


def load(run):
    """Read new-run inputs with no-follow bounded reads and immutable SQLite."""
    root = Path(run).absolute()
    raw = safe.read_regular(PREREG)
    if sha(raw) != PREREG_SHA: raise ValueError('atomic preregistration changed')
    prereg = safe.strict_json(raw)
    if prereg['author_directory'] != str(N): raise ValueError('checker author directory mismatch')
    formatter_raw=safe.read_regular(FORMATTER_CONTRACT)
    if sha(formatter_raw)!=FORMATTER_SHA:raise ValueError('qualified formatter corpus pin mismatch')
    formatter_contract=safe.strict_json(formatter_raw)
    paths = ['inputs.json', 'result.json', 'topics.json', 'observer/source.jsonl',
        'worker/source.jsonl', 'observer/witness.json', 'synthetic_source/transport_source.jsonl']
    paths += [r+'/owned_manifest.json' for r in safe.ROLES]
    paths += ['recorder/bag/'+str(p.relative_to(root/'recorder/bag'))
              for p in sorted((root/'recorder/bag').rglob('*')) if p.is_file() or p.is_symlink()]
    if len(paths) > 256: raise ValueError('file population exceeds bound')
    blobs = {}; total = 0
    for p in paths:
        blobs[p] = safe.read_regular(root/p); total += len(blobs[p])
        if total > MAX_BYTES: raise ValueError('aggregate input budget exceeded')
    hashes = {p:sha(v) for p,v in blobs.items()}
    records = {p:(safe.jsonl(v) if p.endswith('.jsonl') else safe.strict_json(v))
               for p,v in blobs.items() if not p.startswith('recorder/bag/')}
    contract_path = Path(records['inputs.json']['contract'])
    contract_raw = safe.read_regular(contract_path)
    if sha(contract_raw) != records['inputs.json']['contract_sha256']: raise ValueError('run contract pin mismatch')
    cfg = safe.strict_json(contract_raw)
    import yaml
    from rclpy.serialization import deserialize_message, serialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    classes = {}
    def decode(blob, typ):
        if typ not in classes: classes[typ] = get_message(typ)
        return plain(dict(message_to_ordereddict(deserialize_message(blob, classes[typ]))))
    def reserialize(blob, typ):
        if typ not in classes: classes[typ] = get_message(typ)
        return serialize_message(deserialize_message(blob, classes[typ]))
    topics = records['topics.json']['topics']
    metadata = yaml.safe_load(blobs['recorder/bag/metadata.yaml'])['rosbag2_bagfile_information']
    if metadata['storage_identifier'] != 'sqlite3': raise ValueError('this preregistered checker requires SQLite storage')
    declared = {x['topic_metadata']['name']:x['topic_metadata']['type'] for x in metadata['topics_with_message_count']}
    if len(declared) != len(metadata['topics_with_message_count']) or declared != topics:
        raise ValueError('metadata topic/type population mismatch')
    decoded = {t:[] for t in topics}; cdr = {t:[] for t in topics}; bag = {t:[] for t in topics}
    count = size = 0
    db_paths = metadata['relative_file_paths']
    if not db_paths or len(db_paths) > 16: raise ValueError('database file count bound')
    for rel in db_paths:
        rp = Path(rel)
        if rp.is_absolute() or '..' in rp.parts or 'recorder/bag/'+str(rp) not in blobs:
            raise ValueError('unlocked database path')
        database = root/'recorder/bag'/rp
        connection = sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1', uri=True)
        try:
            database_rows=connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
            if database_rows>MAX_ROWS-count:raise ValueError('whole database row population exceeds bound')
            scanned_before=count
            types = {x[1]:x[2] for x in connection.execute('SELECT id,name,type FROM topics')}
            if types != topics: raise ValueError('database topic/type population mismatch')
            cursor = connection.execute('SELECT topics.name,topics.type,messages.timestamp,messages.data '
                'FROM messages JOIN topics ON messages.topic_id=topics.id ORDER BY messages.timestamp,messages.id')
            for topic, typ, timestamp, data in cursor:
                count += 1; size += len(data)
                if count > MAX_ROWS or size > MAX_BYTES: raise ValueError('stored message scan exceeds bound')
                message = decode(data, typ)
                decoded[topic].append({'message':message, 'bag_receive_ns':timestamp})
                digest = sha(data); cdr[topic].append(digest)
                bag[topic].append({'message':message, 'cdr_sha256':digest, 'cdr_bytes':len(data), 'cdr':data,
                    'bag_receive_ns':timestamp, 'ros_type':typ})
            if count-scanned_before!=database_rows:raise ValueError('whole database includes orphan message topic identities')
        finally: connection.close()
    actual_counts = {t:len(v) for t,v in bag.items()}
    declared_counts = {x['topic_metadata']['name']:x['message_count'] for x in metadata['topics_with_message_count']}
    if actual_counts != declared_counts or count != metadata['message_count']:
        raise ValueError('actual database message conservation mismatch')
    helpers={str(Path(m.__file__).absolute()):sha(safe.read_regular(Path(m.__file__).absolute()))
             for m in (safe,reader,numerical,original_gate,formatter,lease_replay)}
    lease_path=Path(lease_replay.__file__).absolute()
    lease_hash=helpers[str(lease_path)]
    if root.parent.parent == N:
        captured=safe.read_regular(root/'lease_replay_v1.py.snapshot')
        if sha(captured)!=records['inputs.json']['tool_sha256'].get('lease_replay_v1.py') or sha(captured)!=lease_hash:
            raise ValueError('current lease replay snapshot/module dependency differs')
        helpers[str(root/'lease_replay_v1.py.snapshot')]=sha(captured)
    else:
        raise ValueError('this N10 atomic checker requires its preregistered current run; historical compatibility uses separate finite replay')
    source_path=Path(records['observer/owned_manifest.json']['effective_parameters']['diagnostic_source_file']['value'])
    source_raw=safe.read_regular(source_path)
    if sha(source_raw)!=records['observer/owned_manifest.json']['effective_parameters']['diagnostic_source_sha256']['value']:
        raise ValueError('observer native source pin mismatch')
    return {'root':str(root), 'records':records, 'configuration':cfg, 'topics':topics,
        'decoded':decoded, 'cdr':cdr, 'bag':bag, 'decode':decode, 'reserialize':reserialize,
        'hashes':hashes, 'paths':paths, 'preregister':prereg,
        'formatter_allowed':set(formatter_contract['allowed_ieee_bits']),
        'external_hashes':{str(PREREG):sha(raw),str(FORMATTER_CONTRACT):sha(formatter_raw),str(contract_path):sha(contract_raw),str(source_path):sha(source_raw),**helpers},
        'storage':{'total_messages':count,'serialized_bytes':size,'actual_counts':actual_counts,
            'timestamp_semantics':'storage receipt; never source selection order'}}


def input_transactions(rows, ev):
    """Project the callback stream without interpreting unrelated sink order."""
    out = {}; last = 0; projection_count = 0
    for row in rows:
        if row['type'] not in CALLBACK_TYPES: continue
        projection_count += 1; ordinal = row.get('input_commit_ordinal')
        if not ev.need(safe.integer(ordinal,1), 'callback_ordinal_missing_or_invalid', source_type=row['type']): continue
        if ordinal == last:
            allowed = len(out[ordinal]) == 1 and out[ordinal][0]['type'] == 'legacy_history_reset' and row['type'] == 'legacy_anchor' and out[ordinal][0]['sequence'] == row['sequence']
            ev.need(allowed,'callback_ordinal_duplicate_not_Applied_projection',ordinal=ordinal)
            out[ordinal].append(row)
        else:
            ev.need(ordinal == last+1,'callback_ordinal_not_strict_contiguous',previous=last,ordinal=ordinal)
            ev.need(ordinal not in out,'callback_ordinal_reappeared',ordinal=ordinal)
            out.setdefault(ordinal,[]).append(row); last = ordinal
    ev.need(bool(out),'no_input_transactions')
    ev.group('input_transaction_ordinals', transactions=len(out), projections=projection_count,
             selection_order='input mutex commit ordinal only')
    return out


def authenticate_callbacks(s, transactions, ev):
    manifests = {r:s['records'][r+'/owned_manifest.json'] for r in safe.ROLES}
    join = reader.transport_join(s['cdr'],s['records']['synthetic_source/transport_source.jsonl'],manifests,s['topics'])
    ev.need(join['passed'],'whole_storage_transport_identity',details=join['issues'])
    transports={topic:[] for topic in s['topics']}
    for row in s['records']['synthetic_source/transport_source.jsonl']:
        if row.get('type')=='transport_message' and row.get('topic') in transports:transports[row['topic']].append(row)
    for topic,entries in s['bag'].items():
        ev.need(len(transports[topic])==len(entries) and all(type(row.get('serialized_bytes')) is int and row['serialized_bytes']==entry['cdr_bytes'] for row,entry in zip(transports[topic],entries)),
                'whole_transport_serialized_bytes_binding',topic=topic)
    typed = reader.source_typed_join(s['records']['observer/source.jsonl'],s['records']['worker/source.jsonl'],s['decoded'])
    ev.need(typed['passed'],'whole_source_typed_payload_binding',details=typed['issues'])
    publisher_gids = {e['topic']:e['gid'] for m in manifests.values() for e in m['endpoints'] if e['kind']=='publisher'}
    decoded = {}; counts = Counter(); previous = Counter(); offsets = Counter()
    for ordinal, rows in transactions.items():
        for row in rows:
            typ = row['type']
            if typ not in SENSORS: continue
            counts[typ] += 1; raw = row.get('raw_input'); topic, ros_type = SENSORS[typ]
            if not ev.need(type(raw) is dict,'raw_callback_missing',ordinal=ordinal): continue
            ev.need(raw.get('schema')=='p1-input-callback-full-cdr-v1' and raw.get('topic')==topic and raw.get('message_type')==ros_type,'raw_callback_schema_topic_type',ordinal=ordinal)
            sequence = raw.get('callback_sequence')
            ev.need(sequence==previous[typ]+1,'raw_callback_sequence_not_contiguous',ordinal=ordinal,source_type=typ)
            previous[typ] = sequence
            if typ != 'clock': ev.need(row.get('sequence',row.get('received_sequence'))==sequence,'source_raw_callback_sequence_binding',ordinal=ordinal)
            ev.need(safe.equal(raw.get('publisher_gid'),publisher_gids.get(topic)),'raw_callback_actual_publisher_GID',ordinal=ordinal)
            blob = bytes.fromhex(raw['cdr_hex'])
            ev.need(len(blob)<=1048576 and len(blob)==raw['cdr_bytes'] and sha(blob)==raw['cdr_sha256'],'raw_callback_full_cdr_identity',ordinal=ordinal)
            message = s['decode'](blob,ros_type); decoded[ordinal] = message
            stream = s['decoded'][topic]; index = offsets[topic]
            while index < len(stream) and not safe.equal(message,stream[index]['message']): index += 1
            ev.need(index < len(stream),'raw_callback_full_fields_not_ordered_storage_subset',ordinal=ordinal,source_type=typ)
            offsets[topic] = index+1
    applied = s['decoded'].get(safe.APPLIED_TOPIC,[]); applied_map = {}
    for item in applied:
        message = item['message']; key = (message['producer_instance_id'],message['run_id'],message['sequence'])
        ev.need(key not in applied_map,'duplicate_Applied_storage_identity',sequence=key[2]); applied_map[key] = message
    for ordinal, rows in transactions.items():
        for row in rows:
            if row['type']=='legacy_anchor':
                key = (row['producer'],row['run_id'],row['sequence']); actual = applied_map.get(key)
                ev.need(actual is not None and safe.equal({k:actual[k] for k in safe.APPLIED_FIELDS},row['applied']),
                        'admitted_Applied_full_wire_projection',ordinal=ordinal)
    ev.group('whole_raw_CDR_GID_callback_sequences_and_transport', raw_callbacks=dict(counts),
             source_typed_streams=typed['streams'], transport_counts=join['counts'],
             raw_serialization_padding_compared=False, raw_all_decoded_fields_compared=True)
    return decoded


def ref_selection(state):
    return {'ref_present':True,'path_sequence':state['path_sequence'],'profile_sequence':state['profile_sequence'],
        'path_stamp':dict(zip(('sec','nanosec'),state['path_stamp'])),
        'profile_stamp':dict(zip(('sec','nanosec'),state['profile_stamp'])),
        'path_fingerprint':state['path_fingerprint'] if state['path_sequence'] else None,
        'profile_fingerprint':state['profile_fingerprint'] if state['profile_sequence'] else None,
        'path_size':len(state['path']),'profile_size':len(state['profile'])}


def capability_scope(s,ev):
    """Closed normal Capability population; admissions are an ordered subset."""
    worker=s['records']['worker/source.jsonl'];obs=s['records']['observer/source.jsonl'];cfg=s['configuration']
    inp=s['records']['inputs.json'];manifest=s['records']['worker/owned_manifest.json']
    headers=[r for r in worker if r['type']=='capability_source_header'];terminals=[r for r in worker if r['type']=='worker_summary']
    if not ev.need(len(headers)==len(terminals)==1,'capability_unique_header_terminal'):
        ev.group('capability_full19_publisher_and_normal_admission_lease',covered=False);return
    header=headers[0];terminal=terminals[0]
    ev.need(worker[0] is header and worker[-1] is terminal,'capability_source_header_terminal_order')
    ev.need(header['schema']=='p1-capability-source-header-v1' and header['run_id']==inp['run_id'] and header['boot_id']==manifest['boot_id'] and header['pid']==manifest['pid'] and header['process_start_ticks']==manifest['process_start_ticks'] and header['worker_instance']==manifest['worker_instance'],'capability_source_header_process_identity')
    ev.need(header['binary_sha256']==inp['builds']['worker']['binary_sha256'] and header['source_bundle_sha256']==inp['source_bundles']['worker']['sha256'] and header['owned_manifest_sha256']==s['hashes']['worker/owned_manifest.json'],'capability_source_header_author_identity')
    endpoints=[e for e in manifest['endpoints'] if e['kind']=='publisher' and e['topic']==safe.CAP_TOPIC]
    ev.need(len(endpoints)==1 and safe.equal(header['endpoint'],endpoints[0]),'capability_source_header_actual_GID')
    attempts=[r for r in worker if r['type']=='capability_publish_attempt'];results=[r for r in worker if r['type']=='capability_publish_result'];count=len(attempts)
    ev.need(count>0 and [r['publish_seq'] for r in attempts]==[r['publish_seq'] for r in results]==list(range(1,count+1)),'capability_source_attempt_result_sequence')
    fields=safe.CAP_FIELDS;previous_end=0;indices={id(r):i for i,r in enumerate(worker)}
    for attempt,result in zip(attempts,results):
        seq=attempt['publish_seq'];value=attempt['payload']
        ev.need(set(value)==fields,'capability_publisher_full19_shape',publish_seq=seq)
        integers=('horizon_steps','pid','startup_ns','completed_jobs','active_job','pending_count')
        booleans=('fault_injection_enabled','fatal')
        ev.need(all(safe.integer(value[k],0,safe.U64) for k in integers) and all(type(value[k]) is bool for k in booleans) and type(value['prediction_dt']) is float and math.isfinite(value['prediction_dt']) and all(type(value[k]) is str for k in fields-set(integers)-set(booleans)-{'prediction_dt'}),'capability_publisher_full19_exact_types',publish_seq=seq)
        ev.need(indices[id(header)]<indices[id(attempt)]<indices[id(result)]<indices[id(terminal)],'capability_source_attempt_result_record_order',publish_seq=seq)
        ev.need(attempt['schema']=='p1-capability-publish-attempt-v1' and result['schema']=='p1-capability-publish-result-v1' and attempt['payload_sha256']==result['payload_sha256']==numerical.typed_sha(value),'capability_typed_full_payload_digest',publish_seq=seq)
        ev.need(previous_end<=attempt['snapshot_ns']<=attempt['attempt_record_ns']<=result['publish_start_ns']<=result['publish_end_ns'] and result['returned'] is True and result['threw'] is False,'capability_publisher_call_time',publish_seq=seq)
        previous_end=result['publish_end_ns'];cdr=attempt['cdr'];raw=bytes.fromhex(cdr['hex'])
        ev.need(0<len(raw)<=1048576 and len(raw)==cdr['bytes'] and sha(raw)==cdr['sha256'] and cdr['representation']=='typed_reserialization_cdr' and safe.equal(s['decode'](raw,'usv_research_interfaces/msg/WorkerCapability'),value),'capability_source_logged_CDR_full19_binding',publish_seq=seq)
        immutable={'schema_version':'p1-worker-capability-v1','run_id':inp['run_id'],'boot_id':manifest['boot_id'],
            'contract_hash':inp['contract_sha256'],'nominal_hash':cfg['nominal_hash'],'worker_instance':manifest['worker_instance'],
            'clock_name':'CLOCK_MONOTONIC','backend':'acados','matrix_layout':'column_major','horizon_steps':cfg['N'],
            'prediction_dt':cfg['dt'],'pid':manifest['pid'],'startup_ns':header['startup_ns'],
            'fault_injection_enabled':cfg['fault_injection_enabled'],'fatal':False,'reason':''}
        ev.need(all(safe.equal(value[k],v) for k,v in immutable.items()),'capability_source_normal_identity_contract',publish_seq=seq)
    actual=[r['message'] for r in s['decoded'][safe.CAP_TOPIC]]
    ev.need(len(actual)==count and all(safe.equal(a['payload'],v) for a,v in zip(attempts,actual)),
            'capability_publisher_source_actual_full19_population',publisher_source=count,storage=len(actual))
    expected={'schema':'p1-capability-source-terminal-v1','capability_generated':count,'capability_attempt_records':count,'capability_publish_calls':count,'capability_publish_returned':count,'capability_publish_threw':0,'capability_result_records':count,'capability_aborted_before_publish':0,'capability_source_io_failed':False,'capability_last_publish_seq':count,'capability_last_payload_sha256':attempts[-1]['payload_sha256'] if attempts else '', 'capability_last_publish_end_ns':results[-1]['publish_end_ns'] if results else 0,'capability_source_complete':True}
    ev.need(safe.equal(terminal['capability_source'],expected) and terminal['finished_ns']>=previous_end and terminal['source_rows_before_terminal']==terminal['source_rows_emitted_before_terminal']==len(worker)-1 and terminal['source_io_failed'] is False,'capability_publisher_terminal_conservation')
    # This inherited pure function uses only the provided new-run fields; it
    # imports no old run and does not confer any old readiness qualification.
    adapter={'records':{'owned_worker':manifest,'contract':cfg,'observer_source':obs},'decoded':s['decoded']}
    def decode_capability_raw(raw,index):
        ev.need(raw.get('schema')=='p1-input-callback-full-cdr-v1' and raw.get('topic')==safe.CAP_TOPIC and raw.get('message_type')=='usv_research_interfaces/msg/WorkerCapability','capability_raw_schema_topic_type',source_index=index)
        ev.need(len(endpoints)==1 and safe.equal(raw.get('publisher_gid'),endpoints[0]['gid']),'capability_raw_actual_writer_GID',source_index=index)
        blob=bytes.fromhex(raw['cdr_hex'])
        ev.need(type(raw.get('cdr_bytes')) is int and 0<len(blob)<=1048576 and len(blob)==raw['cdr_bytes'] and sha(blob)==raw['cdr_sha256'],'capability_raw_complete_CDR_identity',source_index=index)
        return s['decode'](blob,'usv_research_interfaces/msg/WorkerCapability')
    admissions=safe.check_capabilities(ev,adapter,{'run_id':inp['run_id'],'contract_sha256':inp['contract_sha256']},decode_raw=decode_capability_raw,require_observation=True)
    s['lease_replay']=admissions['independent_lease_replay']
    ev.group('capability_full19_publisher_and_normal_admission_lease',publisher_source=count,actual_storage=len(actual),
        admissions=admissions,commit_worker_valid_actual_reads=sum(r['type']=='decision' and r['d0_observation']['gate_reads']['commit_worker_valid'] is not None for r in obs),
        foreign_invalid_terminal_capability_covered=False,packet_unique_identity=False,packet_freshness=False)


def profile_stamp(message):
    result = {'sec':-1,'nanosec':-1}; found = set()
    for dim in message['layout']['dim']:
        for unit in result:
            prefix = 'stamp_'+unit+':'
            if dim['label'].startswith(prefix):
                match = re.match(r'\s*([+-]?\d+)',dim['label'][len(prefix):])
                if not match or not -(1<<31)<=int(match[1])<(1<<31):return (-1,-1)
                result[unit]=int(match[1]);found.add(unit)
    return (result['sec'],result['nanosec']) if len(found)==2 and min(result.values())>=0 else (-1,-1)


def fingerprint(value,allowed):
    # The inherited corpus was independently differential-tested before this
    # batch. New IEEE values are rejected rather than self-whitelisted.
    return sha(formatter.cpp_json(value,allowed).encode())


def replay_prefix(s, transactions, decoded, ev):
    cfg = s['configuration']; state = dict(state=[0.]*6,odom_sequence=0,imu_sequence=0,
        odom_stamp_ns=0,odom_receive_ns=0,imu_stamp_ns=0,imu_receive_ns=0,r_from_imu=False,
        clock_sim_ns=0,clock_receive_ns=0,rtf=0.,rtf_valid=False,paused=False,
        path=[],profile=[],path_sequence=0,profile_sequence=0,path_stamp=(-1,-1),profile_stamp=(-1,-1),
        path_fingerprint='',profile_fingerprint='',held_history=[],publication_history=[],
        anchor={'n':[0.,0.],'sequence':[0,0],'publish_ns':[0,0],'known':[False,False]},
        anchor_producer='',anchor_run_id=s['records']['inputs.json']['run_id'],anchor_source='legacy_publisher',
        version={'task':0,'model':1,'config':1,'schedule':1,'epoch':0})
    # legacy_run_ is the specified publisher run even before its first callback.
    startup = next((r for r in s['records']['observer/source.jsonl'] if r['type']=='startup'),{})
    state['anchor_run_id'] = startup.get('legacy_expected_identity',{}).get('run_id',state['anchor_run_id'])
    identity = next((r.get('expected_identity') for r in s['records']['observer/source.jsonl'] if r.get('expected_identity')),None)
    if identity: state['anchor_run_id'] = identity.get('run_id',state['anchor_run_id'])
    # The observer's own frozen parameter is authoritative for configured legacy run.
    observer_params = s['records']['observer/owned_manifest.json'].get('effective_parameters',{})
    if 'legacy_run_id' in observer_params: state['anchor_run_id'] = observer_params['legacy_run_id']['value']
    prefixes = {0:copy.deepcopy(state)}; counters = Counter(); window=deque(); last_clock=(0,0)
    for ordinal, rows in transactions.items():
        for row in rows:
            typ=row['type']; message=decoded.get(ordinal)
            if typ=='odom_admission' and message is not None:
                counters[typ]+=1; pose=message['pose']['pose']; twist=message['twist']['twist']; q=pose['orientation']
                a=[pose['position']['x'],pose['position']['y'],twist['linear']['x'],twist['linear']['y'],twist['angular']['z']]
                norm=sum(q[k]*q[k] for k in ('x','y','z','w'))
                valid=all(math.isfinite(v) for v in a+list(q.values())) and math.isfinite(norm) and norm>=1e-12 and message['header']['frame_id']==cfg['expected_pose_frame'] and message['child_frame_id']==cfg['expected_child_frame']
                ev.need(row['valid']==valid,'raw_odom_admission',ordinal=ordinal)
                if valid:
                    state.update(state=[a[0],a[1],numerical.yaw(q),a[2],a[3],a[4]],odom_sequence=counters[typ],odom_stamp_ns=numerical.stamp(message['header']['stamp']),odom_receive_ns=row['receive_ns'],r_from_imu=False)
                ev.need(row['accepted_sequence']==state['odom_sequence'] and near(row['state'],state['state']),'raw_odom_state_composition',ordinal=ordinal)
            elif typ=='imu_admission' and message is not None:
                counters[typ]+=1; value=message['angular_velocity']['z'];valid=math.isfinite(value) and message['header']['frame_id']==cfg['expected_imu_frame']
                ev.need(row['valid']==valid and row['r_value']==value,'raw_imu_admission',ordinal=ordinal)
                if valid:
                    state['state'][5]=value;state.update(imu_sequence=counters[typ],imu_stamp_ns=numerical.stamp(message['header']['stamp']),imu_receive_ns=row['receive_ns'],r_from_imu=True)
                ev.need(row['accepted_sequence']==state['imu_sequence'],'raw_imu_accepted_sequence',ordinal=ordinal)
            elif typ=='path_version' and message is not None:
                resource=len(message['poses'])<=cfg['max_path_points'] and len(message['header']['frame_id'].encode())<=cfg['max_path_frame_bytes']
                points=[[float(p['pose']['position']['x']),float(p['pose']['position']['y']),numerical.yaw(p['pose']['orientation'])] for p in message['poses']]
                valid=resource and message['header']['frame_id']==cfg['expected_pose_frame'] and all(math.isfinite(v) for p in points for v in p)
                if not valid: points=[]
                fp=fingerprint({'frame':message['header']['frame_id'] if resource else 'resource_rejected','path':points},s['formatter_allowed'])
                if fp!=state['path_fingerprint'] or len(points)<2:state['version']['task']+=1;state['path_fingerprint']=fp
                counters[typ]+=1;state.update(path=points,path_sequence=counters[typ],path_stamp=(message['header']['stamp']['sec'],message['header']['stamp']['nanosec']))
                ev.need(row['valid']==valid and row['resource_valid']==resource and row['fingerprint']==fp and row['points']==len(points) and row['task_generation']==state['version']['task'],'raw_path_fingerprint_content_version',ordinal=ordinal)
            elif typ=='profile_version' and message is not None:
                dims=message['layout']['dim']; data=message['data']
                resource=len(data)<=cfg['max_profile_rows']*4 and len(dims)<=cfg['max_profile_dims'] and all(len(d['label'].encode())<=cfg['max_profile_label_bytes'] for d in dims)
                values=[[float(x) for x in data[i:i+4]] for i in range(0,len(data),4)]
                valid=resource and bool(data) and len(data)%4==0 and all(math.isfinite(x) for v in values for x in v) and all(values[i][3]>values[i-1][3] for i in range(1,len(values)))
                if not valid:values=[]
                fp=fingerprint(values,s['formatter_allowed'])
                if fp!=state['profile_fingerprint']:state['version']['task']+=1;state['profile_fingerprint']=fp
                counters[typ]+=1;state.update(profile=values,profile_sequence=counters[typ],profile_stamp=profile_stamp(message) if resource else (-1,-1))
                ev.need(row['valid']==valid and row['resource_valid']==resource and row['fingerprint']==fp and row['rows']==len(values) and row['task_generation']==state['version']['task'],'raw_profile_fingerprint_content_version',ordinal=ordinal)
            elif typ=='clock' and message is not None:
                receive=row['receive_ns'];sim=numerical.stamp(message['clock']);lr,ls=last_clock
                if lr and (receive<=lr or sim<ls or sim-ls>5_000_000_000):window.clear()
                if lr and (sim<ls or sim-ls>5_000_000_000):
                    state['version']['epoch']+=1;state['version']['schedule']+=1;state['held_history']=[];state['publication_history']=[];state['anchor']['known']=[False,False]
                # Tick-side pause/resume is outside input ordinals. It is only
                # admitted in this checker when the callback reports no such change.
                ev.need(row['paused'] is False,'scope_clock_pause_not_covered',ordinal=ordinal)
                while window and receive-window[0][0]>600_000_000:window.popleft()
                if not window or receive-window[-1][0]>=10_000_000:window.append((receive,sim))
                while len(window)>100:window.popleft()
                span=receive-window[0][0];rtf=0. if span<400_000_000 else (sim-window[0][1])/span
                valid=span>=400_000_000 and cfg['rtf_low']<=rtf<=cfg['rtf_high']
                state.update(clock_receive_ns=receive,clock_sim_ns=sim,rtf=rtf,rtf_valid=valid,paused=False)
                ev.need(row['sim_ns']==sim and row['rtf_window_span_ns']==span and row['rtf_stored_samples']==len(window) and abs(row['rtf']-rtf)<=1e-12 and row['rtf_valid']==valid and row['epoch']==state['version']['epoch'] and row['schedule_generation']==state['version']['schedule'],'raw_clock_full_window_version',ordinal=ordinal)
                last_clock=(receive,sim)
            elif typ=='legacy_history_reset' or (typ=='legacy_admission_rejected' and row['history_invalidated']):
                state['held_history']=[];state['publication_history']=[];state['anchor']['known']=[False,False]
            elif typ=='legacy_anchor':
                m=row['applied'];state['anchor_producer']=m['producer_instance_id'];state['anchor_run_id']=m['run_id']
                for ch,side in enumerate(('left','right')):
                    time=m[side+'_publish_start_steady_ns'];sim=m[side+'_sim_time_ns'];a=state['anchor']
                    good=m[side+'_publish_success'] and time>0 and time<=row['processed_ns'] and (not a['known'][ch] or time>a['publish_ns'][ch])
                    if not good:a['known'][ch]=False;continue
                    a['n'][ch]=m['final_n'][ch];a['sequence'][ch]=m['sequence'];a['publish_ns'][ch]=time;a['known'][ch]=True
                    if state['held_history'] and sim<state['held_history'][-1]['sim_ns']:
                        state['held_history']=[];state['publication_history']=[];a['known']=[False,False]
                    else:state['held_history'].append({'sim_ns':sim,'channel':ch,'value':m['final_n'][ch]})
                    state['publication_history'].append({'channel':ch,'sequence':m['sequence'],'publish_ns':time,'n':m['final_n'][ch],'known':a['known'][ch]})
                    state['held_history']=state['held_history'][-cfg['history_capacity']:];state['publication_history']=state['publication_history'][-cfg['history_capacity']:]
                ev.need(safe.equal(row['known'],state['anchor']['known']) and safe.equal(row['publish_ns'],state['anchor']['publish_ns']),'Applied_actual_anchor_transition',ordinal=ordinal)
        state['input_commit_ordinal']=ordinal;prefixes[ordinal]=copy.deepcopy(state)
    prefixes[0]['input_commit_ordinal']=0
    ev.group('independent_input_state_reference_clock_and_Applied_prefix', prefixes=len(prefixes),
             full_reference_stamp_pairs=True, formatter_domain='recorded finite ASCII/IEEE values only',
             noninput_pause_schedule_mutations_covered=False)
    return prefixes


def check_snapshot(snapshot, prefixes, ev, label, identity):
    ordinal=snapshot.get('input_commit_ordinal');prefix=prefixes.get(ordinal)
    if not ev.need(prefix is not None,'snapshot_ordinal_not_in_callback_prefix',snapshot=label,identity=identity,ordinal=ordinal):return None
    ev.need(near(snapshot.get('state'),prefix['state']),'snapshot_full_state_from_last_ordinal',snapshot=label,identity=identity)
    for key in ('version','odom_sequence','odom_stamp_ns','odom_receive_ns','imu_sequence','imu_stamp_ns','imu_receive_ns','r_from_imu','clock_sim_ns','clock_receive_ns','rtf_valid','paused'):
        ev.need(safe.equal(snapshot.get(key),prefix[key]),'snapshot_selected_input_identity',snapshot=label,identity=identity,field=key)
    ev.need(abs(snapshot['rtf']-prefix['rtf'])<=1e-12,'snapshot_selected_RTF',snapshot=label,identity=identity)
    ev.need(safe.equal(snapshot.get('ref_selection'),ref_selection(prefix)),'snapshot_reference_sequence_stamp_pair_fingerprint_size',snapshot=label,identity=identity)
    for key in ('anchor','held_history','publication_history','anchor_producer','anchor_run_id','anchor_source'):
        ev.need(safe.equal(snapshot.get(key),prefix[key]),'snapshot_full_prefix_history_anchor_identity',snapshot=label,identity=identity,field=key)
    ev.need(snapshot.get('history_count')==len(prefix['held_history']) and snapshot.get('publication_history_count')==len(prefix['publication_history']),'snapshot_full_history_counts',snapshot=label,identity=identity)
    return prefix


def check_jobs(s, prefixes, ev):
    cfg=s['configuration'];jobs={};proof=[]
    for row in s['records']['observer/source.jsonl']:
        if row['type']!='job':continue
        job=row['job'];key=job['job_id'];p=row.get('input_provenance',{});ordinal=p.get('input_commit_ordinal');prefix=prefixes.get(ordinal)
        ev.need(key not in jobs,'duplicate_Job_identity',job=key);jobs[key]=row
        if not ev.need(p.get('schema')=='p1-job-input-selection-v2' and prefix is not None,'Job_v2_ordinal_selection_missing',job=key):continue
        ev.need(safe.equal(p.get('ref_selection'),ref_selection(prefix)),'Job_reference_sequence_stamp_pair_fingerprint_size',job=key)
        expected={'odom_sequence':prefix['odom_sequence'],'imu_sequence_raw':prefix['imu_sequence'],'r_from_imu':prefix['r_from_imu'],
            'path_sequence':prefix['path_sequence'],'profile_sequence':prefix['profile_sequence'],
            'path_stamp_ns':prefix['path_stamp'][0]*1_000_000_000+prefix['path_stamp'][1],
            'profile_stamp_ns':prefix['profile_stamp'][0]*1_000_000_000+prefix['profile_stamp'][1],
            'clock_sim_ns':prefix['clock_sim_ns'],'clock_receive_ns':prefix['clock_receive_ns'],
            'rtf_valid':prefix['rtf_valid'],'paused':prefix['paused'],'freeze_ns':job['freeze_ns']}
        ev.need(all(safe.equal(p.get(k),v) for k,v in expected.items()) and abs(p['rtf']-prefix['rtf'])<=1e-12,'Job_unmasked_input_selected_prefix',job=key)
        ev.need(near(job['frozen_state'],prefix['state']) and all(job[k]==prefix[k] for k in ('odom_sequence','odom_stamp_ns','odom_receive_ns')) and all(job[wire]==prefix['version'][key] for key,wire in VERSION.items()),'Job_frozen_state_version',job=key)
        ev.need(all(job[k]==(prefix[k] if prefix['r_from_imu'] else 0) for k in ('imu_sequence','imu_stamp_ns','imu_receive_ns')),'Job_canonical_inactive_IMU_mask',job=key)
        hist=[{'sim_ns':a,'channel':b,'value':c} for a,b,c in zip(job['history_sim_ns'],job['history_channel'],job['history_n'])]
        anchor={'n':job['anchor_n'],'sequence':job['anchor_sequence'],'publish_ns':job['anchor_publish_ns'],'known':job['anchor_known']}
        ev.need(len(job['history_sim_ns'])==len(job['history_channel'])==len(job['history_n']) and safe.equal(hist,prefix['held_history']) and safe.equal(anchor,prefix['anchor']) and all(job[k]==prefix[k] for k in ('anchor_producer','anchor_run_id','anchor_source')),'Job_full_held_anchor_identity',job=key)
        target=prefix['clock_sim_ns']+job['target_ns']-prefix['clock_receive_ns']
        ev.need(job['target_sim_ns']==target and job['assumed_rtf']==1.,'Job_target_original_mapping',job=key)
        nominal=numerical.propagate(prefix['state'],prefix['odom_stamp_ns'],target,prefix['anchor']['n'],[(e['sim_ns'],e['channel'],e['value']) for e in prefix['held_history']],cfg['hydro'])
        reference,meta=numerical.reference(nominal,prefix['path'],prefix['profile'],prefix['path_stamp'],prefix['profile_stamp'],cfg)
        ev.need(near(job['target_state'],nominal) and near(job['reference'],reference) and all(row[k]==v for k,v in meta.items()),'Job_independent_nominal_reference126',job=key)
        ev.need(job['reset_warmstart']==(abs(numerical.angle(nominal[2]-reference[2]))>math.pi*.75),'Job_original_warmstart',job=key)
        proof.append({'job_id':key,'input_commit_ordinal':ordinal,'reference_selection':ref_selection(prefix)})
    ev.group('immutable_Job_ordinal_reference_history_nominal',jobs=len(jobs),proof=proof,
        dynamic_or_mixed_turn_qualified=False)
    return jobs


def decode_captured_preimage(cap,decode,ev,sequence):
    encoded=cap.get('cdr_hex');size=cap.get('cdr_bytes');digest=cap.get('cdr_sha256')
    shape=type(encoded) is str and safe.integer(size,1,1048576) and len(encoded)==size*2 and re.fullmatch('[0-9a-f]+',encoded) is not None
    if not ev.need(shape,'actual_candidate_captured_CDR_preimage_integrity',decision=sequence,part='bounded_hex_shape'):return None
    blob=bytes.fromhex(encoded)
    if not ev.need(len(blob)==size and sha(blob)==digest,'actual_candidate_captured_CDR_preimage_integrity',decision=sequence,part='length_SHA256'):return None
    return decode(blob,'usv_research_interfaces/msg/SolveCandidate')


def registration_source_population(source,jobs,candidates,ev):
    registrations={}
    for row in source:
        if row['type']!='candidate_registration':continue
        accepted=row.get('accepted_registration');reason=row.get('reason')
        if not ev.need(type(accepted) is bool,'registration_accepted_flag_strict_bool'):continue
        ev.need(type(reason) is str and accepted==(reason==''),'registration_acceptance_reason_consistency')
        if accepted is not True:continue
        key=row['job'].get('job_id')
        if not ev.need(safe.integer(key,1,safe.U64),'accepted_registration_job_id_strict_uint'):continue
        ev.need(key not in registrations,'accepted_registration_identity_not_unique',job=key)
        if key in registrations:continue
        registrations[key]=row
        original=jobs.get(key,{}).get('job');entry=candidates.get(key)
        ev.need(original is not None and entry is not None,'accepted_registration_original_Job_Candidate_population',job=key)
        projection=reader.projection(row['job'],reader.JOB_FIELDS,reader.JOB_ALIASES)
        if original is not None:ev.need(len(projection)==len(reader.JOB_FIELDS) and safe.equal(projection,reader.projection(original,reader.JOB_FIELDS,reader.JOB_ALIASES)),
                                       'accepted_registration_original_Job_payload_binding',job=key)
        if entry is not None:ev.need(len(projection)==len(reader.JOB_FIELDS) and safe.equal(projection,reader.projection(entry['message']['job'],reader.JOB_FIELDS,{})),
                                    'accepted_registration_actual_Candidate_Job_payload_binding',job=key)
    return registrations


def candidate_captures(s, decisions, jobs, ev):
    candidates={};transport=s['records']['synthetic_source/transport_source.jsonl'];proof=[]
    for entry in s['bag'].get('/p1/solve_candidate',[]):
        key=entry['message']['job']['job_id'];ev.need(key not in candidates,'duplicate_full_wire_Candidate',job=key);candidates[key]=entry
    registrations=registration_source_population(s['records']['observer/source.jsonl'],jobs,candidates,ev)
    actual={}
    for d in decisions:
        seq=d['sequence'];ob=d['d0_observation'];cap=ob.get('candidate_capture',{})
        ev.need(set(cap)=={'ticket_present','candidate_present','pair','digest_semantics','cdr_bytes','cdr_sha256','cdr_hex','job_id','worker_instance','first_control'},'actual_candidate_capture_shape',decision=seq)
        if not ev.need(all(type(cap.get(k)) is bool for k in ('ticket_present','candidate_present','pair')),'actual_candidate_capture_presence_types',decision=seq):continue
        ev.need(cap['pair']==(cap['ticket_present'] and cap['candidate_present'])==ob['candidate_pair_available'],'actual_candidate_capture_pair',decision=seq)
        ev.need(cap.get('digest_semantics')==CAPTURE_DIGEST_SEMANTICS,'actual_candidate_digest_semantics',decision=seq)
        if not cap['candidate_present']:
            ev.need(all(cap.get(k) is None for k in ('cdr_bytes','cdr_sha256','cdr_hex','job_id','worker_instance','first_control')),'absent_actual_candidate_null_metadata',decision=seq)
            actual[seq]=None;continue
        if not ev.need(safe.integer(cap.get('job_id'),1,safe.U64),'actual_candidate_job_id_strict_uint',decision=seq):continue
        entry=candidates.get(cap['job_id'])
        if not ev.need(entry is not None,'actual_candidate_capture_not_recorded',decision=seq,job=cap['job_id']):continue
        message=entry['message'];actual[seq]=message
        captured=decode_captured_preimage(cap,s['decode'],ev,seq)
        ev.need(captured is not None and safe.equal(captured,message),
                'actual_candidate_captured_full_fields_wire_identity',decision=seq,job=cap['job_id'])
        # Captured typed reserialization and stored wire bytes are distinct
        # representations. Each has its own preimage/SHA; identity is established
        # by independently decoded complete Candidate+Job fields, exact IEEE.
        ev.need(any(r.get('topic')=='/p1/solve_candidate' and r.get('payload_sha256')==entry['cdr_sha256'] and r.get('serialized_bytes')==entry['cdr_bytes'] for r in transport),
                'actual_candidate_wire_digest_transport_binding',decision=seq)
        ev.need(cap['worker_instance']==message['worker_instance'] and safe.equal(cap['first_control'],message['first_control']),'actual_candidate_metadata_full_wire_binding',decision=seq)
        key=cap['job_id'];registration=registrations.get(key)
        ev.need(registration is not None,'actual_candidate_captured_before_accepted_registration',decision=seq)
        original=jobs.get(key,{}).get('job')
        actual_job=reader.projection(message['job'],reader.JOB_FIELDS,{})
        ev.need(original is not None and len(actual_job)==len(reader.JOB_FIELDS) and safe.equal(actual_job,reader.projection(original,reader.JOB_FIELDS,reader.JOB_ALIASES)),
                'actual_candidate_full_echoed_Job_original_binding',decision=seq,job=key)
        if registration:
            registration_job=reader.projection(registration['job'],reader.JOB_FIELDS,reader.JOB_ALIASES)
            ev.need(len(registration_job)==len(reader.JOB_FIELDS) and safe.equal(actual_job,registration_job),
                    'actual_candidate_full_echoed_Job_registration_binding',decision=seq,job=key)
            ev.need(registration['ready_commit_ns']<=d['start_ns'] and near(registration['first_control'],message['first_control']),'actual_candidate_registered_before_capture',decision=seq)
            owned_instance=s['records']['worker/owned_manifest.json']['worker_instance']
            ev.need(message['worker_instance']==registration['worker_instance']==message['job']['worker_instance']==owned_instance and
                all(registration[field]==message[field] for field in ('solve_start_ns','solve_end_ns')),
                'actual_candidate_registration_worker_and_timing_fields',decision=seq,job=key)
            ev.need(message['job']['freeze_steady_ns']<=message['worker_receive_ns']<=message['solve_start_ns']<=message['solve_end_ns']<=registration['ready_commit_ns']<=message['job']['deadline_steady_ns'],
                    'actual_candidate_original_receive_solve_registration_timing',decision=seq,job=key)
            ev.need(message['backend']=='acados' and message['solver_invoked'] is True and message['success'] is True and message['prediction_available'] is True and message['reason']=='' and
                type(message['backend_ms']) in (int,float) and math.isfinite(message['backend_ms']) and message['backend_ms']>=0 and
                len(message['x_prediction'])==126 and len(message['u_prediction'])==40 and all(math.isfinite(x) for x in message['x_prediction']+message['u_prediction']+message['first_control']) and
                near(message['first_control'],message['u_prediction'][:2],1e-8) and near(message['x_prediction'][:6],message['job']['target_state'],1e-7),
                'actual_candidate_full_solver_prediction_control_scope',decision=seq,job=key)
        if cap['pair']:
            ev.need(d['job_id']==key==ob['candidate_job_id'] and key in jobs and ob['candidate_target_tick']==message['job']['target_tick']==d['tick'],'actual_candidate_ticket_echoed_Job_binding',decision=seq)
            ev.need(registration is not None and d['ready_commit_ns']==registration['ready_commit_ns'],
                    'actual_candidate_ticket_registration_ready_commit_binding',decision=seq,job=key)
            ev.need(ob['prediction_target_sim_ns']==message['job']['target_sim_ns'],
                    'actual_candidate_prediction_target_sim_binding',decision=seq,job=key)
            ev.need(near(d['target_state'],message['job']['target_state']),
                    'actual_candidate_canonical_Decision_target_state_binding',decision=seq,job=key)
        proof.append({'decision':seq,'ticket_present':cap['ticket_present'],'candidate_present':True,'pair':cap['pair'],'job_id':key,
            'captured_cdr_sha256':cap['cdr_sha256'],'captured_cdr_bytes':cap['cdr_bytes'],
            'wire_cdr_sha256':entry['cdr_sha256'],'wire_cdr_bytes':entry['cdr_bytes'],
            'representation_SHA_equal':cap['cdr_sha256']==entry['cdr_sha256'],
            'representation_distinct':True,'full_decoded_Candidate_and_Job_equal':captured is not None and safe.equal(captured,message)})
    ev.group('actual_immutable_Candidate_full_CDR_transport',captures=len(decisions),present=len(proof),proof=proof,
             pointer_address_identity_claimed=False, full_echoed_Job_CDR_in_digest=True,
             captured_SHA_required_equal_to_network_wire_SHA=False, full_decoded_Candidate_IEEE_identity=True)
    return actual


def eligibility(prefix, snapshot, now, cfg):
    return original_gate.eligibility(snapshot,prefix['state'],(prefix['path'],prefix['profile'],prefix['path_stamp'],prefix['profile_stamp']),prefix['anchor'],now,cfg)


def flag_possible(rows, initial, true_events, false_events, lower, upper):
    """Only constrain separately observed flag transitions outside the read window."""
    transitions=[]
    for row in rows:
        if row['type'] in true_events|false_events:
            ns=row.get('processed_ns',row.get('check_ns',row.get('validation_commit_ns',row.get('ns'))))
            if row['type']=='legacy_ready':ns=row['readiness']['legacy_ready_ns']
            if ns is not None:transitions.append((ns,row['type'] in true_events))
    possible={initial};current=initial
    for ns,value in sorted(transitions):
        if ns<lower:current=value;possible={current}
        elif ns<=upper:possible.add(value);current=value
    return possible


def irreversible_flag_reads(decisions,ev):
    orders={'stopping':('early_stopping','final_stopping','fallback_invalid_stopping','fallback_source_stopping'),
        'worker_unusable':('early_worker_unusable','commit_worker_unusable','fallback_invalid_worker_unusable','fallback_source_worker_unusable')}
    last={name:False for name in orders};proof={name:[] for name in orders}
    for d in decisions:
        reads=d['d0_observation'].get('gate_reads',{})
        for flag,names in orders.items():
            for name in names:
                value=reads.get(name)
                if value is None:continue
                ev.need(not (last[flag] is True and value is False),
                    'irreversible_original_flag_true_to_false',decision=d['sequence'],flag=flag,gate=name)
                if type(value) is bool:last[flag]=last[flag] or value
                proof[flag].append({'decision':d['sequence'],'gate':name,'value':value})
    return proof


def replay_gates(d, v, f, vp, fp, candidate, job, cfg, last_accepted, ev):
    """Recompute reason flow from raw-selected inputs and actual operands."""
    ob=d['d0_observation'];reads=ob.get('gate_reads',{});seq=d['sequence'];trace=[];visited=set()
    ev.need(set(reads)==set(GATE_KEYS) and all(x is None or type(x) is bool for x in reads.values()),'gate_reads_exact_nullable_shape',decision=seq)
    def operand(name, ran=True, expected=None):
        visited.add(name);value=reads.get(name)
        ev.need((type(value) is bool) if ran else value is None,'gate_operand_short_circuit_shape',decision=seq,gate=name,ran=ran,value=value)
        if expected is not None and ran:ev.need(value is expected,'gate_operand_independent_value',decision=seq,gate=name,expected=expected,actual=value)
        trace.append({'gate':name,'ran':ran,'value':value})
        return value is True if ran else False
    reason=eligibility(vp,v,v['sample_ns'],cfg)
    if operand('early_legacy_enabled') and not operand('early_legacy_measurement'):reason='legacy_not_ready'
    elif reads.get('early_legacy_enabled') is False:operand('early_legacy_measurement',False)
    if operand('early_stopping'):reason='shutdown'
    if operand('early_worker_unusable'):reason='worker_unusable'
    if d['start_ns']-d['planned_ns']>cfg['tick_jitter_ns']:reason='tick_jitter'
    requested=[0.,0.];command=[0.,0.];pair=ob['candidate_pair_available'];prediction=None
    if pair and job is not None and candidate is not None:
        version={k:job[wire] for k,wire in VERSION.items()}
        if not reason and version!=v['version']:reason='version_mismatch'
        expected_anchor={'n':job['anchor_n'],'sequence':job['anchor_sequence'],'publish_ns':job['anchor_publish_ns'],'known':job['anchor_known']}
        if not reason:reason=original_gate.publication_gate(expected_anchor,vp['anchor'],vp['publication_history'])
        initial=list(vp['anchor']['n']);found=[False,False];history=[(e['sim_ns'],e['channel'],e['value']) for e in vp['held_history']]
        for when,ch,value in history:
            if when<=vp['odom_stamp_ns']:initial[ch]=value;found[ch]=True
        success=all(found) and 0<=job['target_sim_ns']-vp['odom_stamp_ns']<=1_000_000_000
        prediction=numerical.propagate(vp['state'],vp['odom_stamp_ns'],job['target_sim_ns'],initial,history,cfg['hydro']) if success else [0.]*6
        ev.need(ob['predict_invoked'] is True and ob['predict_success']==success and ob['predict_status']==('success' if success else 'history_or_time_failed') and ob['predicted_state_available']==success and ob['full_error_available']==success,'actual_pair_prediction_lifecycle',decision=seq)
        if success:
            full=[numerical.angle(prediction[i]-job['target_state'][i]) if i==2 else prediction[i]-job['target_state'][i] for i in range(6)]
            state_reason,errors=original_gate.state_gate(job['target_state'],prediction,cfg,numerical.angle)
            ev.need(near(ob['predicted_state'],prediction) and near(d['activation_state'],prediction) and near(ob['full_error'],full) and near(d['state_error'],errors),'independent_activation_prediction_full_error',decision=seq)
            if not reason:reason=state_reason or ''
        else:
            ev.need(ob['predicted_state'] is None and ob['full_error'] is None and near(d['activation_state'],[0.]*6) and near(d['state_error'],[0.]*6),'failed_prediction_unavailable_fields',decision=seq)
            if not reason:reason='activation_history_or_time'
        if not reason:
            requested=list(candidate['first_control']);lo=max(cfg['command_min_n'],-cfg['publisher_max_n']);hi=min(cfg['command_max_n'],cfg['publisher_max_n'])
            command=[min(hi,max(lo,x*cfg['map_scale'])) for x in requested]
            reason=original_gate.command_gate(command,vp['anchor'],v['sample_ns'],cfg) or ''
            if math.hypot(*(x-y for x,y in zip(command,requested)))>1e-9:reason='candidate_mapping_changed'
    else:
        ev.need(not ob['predict_invoked'] and ob['predict_status']=='not_attempted' and not ob['predict_success'] and ob['predicted_state'] is None and ob['full_error'] is None and ob['candidate_job_id'] is None and ob['candidate_target_tick'] is None and ob['prediction_target_sim_ns'] is None,'nonpair_observation_null_prediction',decision=seq)
        if not reason:reason='no_candidate'
    input_ran=not reason
    ev.need(ob['input_change_gate_ran']==input_ran,'input_comparison_original_occurrence',decision=seq)
    same_version=operand('input_version_equal',input_ran, v['version']==f['version'])
    same_odom=operand('input_odom_equal',input_ran and same_version,v['odom_sequence']==f['odom_sequence'])
    same_imu=operand('input_imu_equal',input_ran and same_version and same_odom,v['imu_sequence']==f['imu_sequence'])
    unchanged=same_version and same_odom and same_imu
    ev.need(ob['input_change_gate_unchanged']==(unchanged if input_ran else None),'input_comparison_nullable_result',decision=seq)
    if input_ran and not unchanged:reason='activation_input_changed_during_validation'
    if not reason and pair:reason=original_gate.publication_gate(expected_anchor,fp['anchor'],fp['publication_history']) or ''
    if not reason:reason=eligibility(fp,f,f['commit_ns'],cfg)
    enabled=operand('commit_legacy_enabled',not reason)
    measurement=operand('commit_legacy_measurement',not reason and enabled)
    if not reason and enabled and not measurement:reason='legacy_not_ready_at_commit'
    worker_unusable=operand('commit_worker_unusable',not reason)
    worker_valid=operand('commit_worker_valid',not reason and not worker_unusable)
    sink_failed=operand('commit_sink_failed',not reason and not worker_unusable and worker_valid)
    if not reason and (worker_unusable or not worker_valid or sink_failed):reason='run_unusable_at_commit'
    if not reason and f['commit_ns']-d['planned_ns']>cfg['tick_jitter_ns']:reason='tick_jitter_at_commit'
    if not reason and candidate and abs(fp['clock_sim_ns']+f['commit_ns']-fp['clock_receive_ns']-candidate['job']['target_sim_ns'])>cfg['target_sim_slack_ns']:reason='target_sim_mismatch'
    if not reason:reason=original_gate.command_gate(command,fp['anchor'],f['commit_ns'],cfg) or ''
    stopping=operand('final_stopping');stop_requested=operand('final_stop_requested',not stopping)
    if stopping or stop_requested:reason='shutdown'
    accepted=not reason
    ev.need(d['accepted']==accepted and d['reason']==reason,'independent_original_reason_overrides',decision=seq,expected_reason=reason,actual_reason=d['reason'])
    if accepted:
        for key in ('fallback_invalid_stopping','fallback_invalid_worker_unusable','fallback_source_stopping','fallback_source_worker_unusable'):operand(key,False)
        source='candidate';last_accepted=f['commit_ns']
    else:
        invalid_stopping=operand('fallback_invalid_stopping')
        invalid_worker=operand('fallback_invalid_worker_unusable',not invalid_stopping)
        invalid=invalid_stopping or invalid_worker or reason!='no_candidate'
        held=not invalid and last_accepted>0 and f['commit_ns']-last_accepted<=cfg['hold_ns']
        command=[]
        for ch in (0,1):
            a=fp['anchor']
            value=0. if not a['known'][ch] else a['n'][ch] if held else math.copysign(max(0.,abs(a['n'][ch])-cfg['rho_n_s']*max(0,f['commit_ns']-a['publish_ns'][ch])/1e9),a['n'][ch])
            command.append(value)
        requested=command[:]
        source_stop=operand('fallback_source_stopping',last_accepted>0)
        source_worker=operand('fallback_source_worker_unusable',last_accepted>0 and not source_stop)
        source='hold' if last_accepted>0 and not source_stop and not source_worker and reason=='no_candidate' and f['commit_ns']-last_accepted<=cfg['hold_ns'] else 'ramp_zero'
    ev.need(near(d['requested_n'],requested) and near(d['final_n'],command) and d['control_source']==source,'independent_original_fallback_output',decision=seq)
    ev.need(set(visited)==set(GATE_KEYS),'all_gate_occurrences_accounted',decision=seq)
    return last_accepted,{'decision':seq,'reason':reason,'accepted':accepted,'gate_trace':trace,'final_command':command}


def witness_integrity(s, decisions, ev):
    w=s['records']['observer/witness.json'];source=s['records']['observer/source.jsonl'];phases=w['phase'];ticks=w['tick']
    ev.need(w.get('enabled') is True and w.get('closed') is True and w.get('audit_complete') is True and not w.get('overflow') and not w.get('incomplete') and w.get('first_failure',{}).get('code')==0,'Witness_closed_component_integrity')
    mapping={(x['schedule_generation'],x['tick']):x for x in ticks}
    ev.need(len(mapping)==len(ticks)==len(decisions),'Witness_whole_tick_population')
    for d in decisions:
        row=mapping.get((d['schedule_generation'],d['tick']))
        if not ev.need(row is not None,'Witness_tick_missing',decision=d['sequence']):continue
        expected={'sequence':d['sequence'],'job_id':d['job_id'],'target_tick':d['tick'] if d['d0_observation']['candidate_pair_available'] else 0,'clock_epoch':d['epoch'],'planned_ns':d['planned_ns'],'start_ns':d['start_ns'],'candidate_present':d['d0_observation']['candidate_pair_available'],'skipped_ticks':d['skipped_ticks']}
        ev.need(all(safe.equal(row[k],v) for k,v in expected.items()) and d['end_ns']<=row['end_ns'],'Witness_full_tick_source_identity',decision=d['sequence'])
        ev.need(safe.equal(d['d0_observation'].get('audit_reads_start'),{'sink_failed':row['failed_start'],'stopping':row['stopping_start']}),'Witness_audit_reads_separately_bound',decision=d['sequence'])
    accepted=sum(d['accepted'] for d in decisions);business=[p for p in phases if p['event_code']==9]
    ev.need(bool(business)==bool(accepted),'Witness_BusinessReady_actual_activation_population',accepted=accepted)
    closes=[p for p in phases if p['event_code']==7];stops=[p for p in phases if p['event_code']==5];shutdown=[r for r in source if r['type']=='regulator_shutdown'];summary=[r for r in source if r['type']=='source_summary']
    ev.need(len(closes)==len(stops)==len(shutdown)==len(summary)==1,'independent_shutdown_full_population')
    if len(closes)==len(summary)==1:ev.need(closes[0]['ns']>=summary[0]['finished_ns'],'Witness_close_after_source_flush')
    if shutdown:ev.need(shutdown[-1]['last_decision_sequence']==decisions[-1]['sequence'],'shutdown_final_decision_identity')
    manifest=s['records']['observer/owned_manifest.json'];worker=s['records']['worker/owned_manifest.json']
    params=manifest['effective_parameters']
    header={'run_id':s['records']['inputs.json']['run_id'],'boot_id':manifest['boot_id'],
        'contract_sha256':s['records']['inputs.json']['contract_sha256'],
        'source_sha256':params['diagnostic_source_sha256']['value'],
        'binary_sha256':manifest['binary_sha256'],'worker_binary_sha256':worker['binary_sha256'],
        'worker_instance':worker['worker_instance']}
    basis=reader.analyze_witness(w,header)
    normal_pass=basis['passed']
    if accepted:ev.need(normal_pass,'unchanged_normal_Witness_rule')
    else:
        ev.need(not normal_pass,'all_rejected_does_not_weaken_normal_Witness_rule')
        ev.need({x['code'] for x in basis['issues']}=={'business_ready_count','complete_flag_disagrees'},
                'all_rejected_only_expected_normal_Witness_failures',details=basis['issues'])
    ev.group('Witness_shutdown_components_separate_from_normal_policy',accepted=accepted,
             all_rejected=accepted==0,normal_Witness_passed=normal_pass,
             normal_Witness_issues=basis['issues'], expected_header=header,
             normal_Witness_policy_unchanged=True,physical_zero_or_OS_exit_proven_here=False)


def analyze(s):
    ev=Evidence();source=s['records']['observer/source.jsonl'];cfg=s['configuration']
    transactions=input_transactions(source,ev)
    decoded=authenticate_callbacks(s,transactions,ev)
    capability_scope(s,ev)
    prefixes=replay_prefix(s,transactions,decoded,ev)
    jobs=check_jobs(s,prefixes,ev)
    decisions=[r for r in source if r['type']=='decision']
    ev.need(bool(decisions) and [d['sequence'] for d in decisions]==list(range(1,len(decisions)+1)),'whole_Decision_sequence')
    forbidden={'source_failure','scheduler_skipped_ticks','worker_capability_lease_expired','active_watchdog'}
    ev.need(not (forbidden & {r['type'] for r in source}),'bounded_scope_uncovered_policy_transition',types=sorted(forbidden & {r['type'] for r in source}))
    ev.need(all(d['mode']=='shadow' for d in decisions),'scope_shadow_observation_only')
    proof={}
    for d in decisions:
        seq=d['sequence'];ob=d.get('d0_observation',{});v=ob.get('validation_snapshot',{});f=ob.get('final_snapshot',{})
        if not ev.need(ob.get('schema')=='p1-d0-observation-v2','D0v2_schema_required',decision=seq):continue
        vp=check_snapshot(v,prefixes,ev,'validation',seq);fp=check_snapshot(f,prefixes,ev,'final',seq)
        ev.need(v['capture_semantics']=='mutex_copy_end' and v['sample_ns']==d['start_ns'] and v['sample_ns']<=v['copy_capture_ns']<=f['commit_ns']==d['activation_commit_ns']<=d['end_ns'],'D0v2_original_capture_order',decision=seq)
        ev.need(v['input_commit_ordinal']<=f['input_commit_ordinal'],'snapshot_ordinal_monotonic_between_locks',decision=seq)
        ev.need(all(d['activation_'+k]==f[k] for k in ('clock_receive_ns','clock_sim_ns','odom_receive_ns','odom_stamp_ns','odom_sequence','r_from_imu')) and abs(d['activation_rtf']-f['rtf'])<=1e-12 and all(d['activation_'+k]==(f[k] if f['r_from_imu'] else 0) for k in ('imu_sequence','imu_receive_ns','imu_stamp_ns')),'canonical_Decision_final_source_with_inactive_IMU_mask',decision=seq)
        ev.need(d['odom_age_ns']==f['commit_ns']-f['odom_receive_ns'] and d['clock_age_ns']==f['commit_ns']-f['clock_receive_ns'] and d['imu_age_ns']==(f['commit_ns']-f['imu_receive_ns'] if f['r_from_imu'] else 0),'final_source_age_arithmetic',decision=seq)
        if vp is not None and fp is not None:proof[seq]=(vp,fp)
    ev.group('both_full_atomic_snapshots_last_ordinal_input_identity',decisions=len(decisions),
             snapshots=2*len(proof),final_anchor_from_raw_prefix=True,
             later_canonical_Decision_anchor_used_for_final=False)
    captures=candidate_captures(s,decisions,jobs,ev)
    irreversible_proof=irreversible_flag_reads(decisions,ev)
    last_accepted=0;gates=[]
    for d in decisions:
        seq=d['sequence'];ob=d['d0_observation'];v=ob['validation_snapshot'];f=ob['final_snapshot']
        if seq not in proof:continue
        vp,fp=proof[seq];job=jobs.get(d['job_id'],{}).get('job')
        # Boolean values are observed at each original operand; source readiness
        # transitions constrain them independently, never from Decision.reason.
        reads=ob.get('gate_reads',{})
        possible=flag_possible(source,False,{'legacy_ready'},{'legacy_ready_invalidated','legacy_ready_failed'},v['sample_ns'],f['commit_ns'])
        for name in ('early_legacy_measurement','commit_legacy_measurement'):
            if reads.get(name) is not None:ev.need(reads[name] in possible,'legacy_measurement_source_transition_binding',decision=seq,gate=name,possible=sorted(possible))
        for name in ('early_legacy_enabled','commit_legacy_enabled'):
            if reads.get(name) is not None:ev.need(reads[name] is True,'shadow_legacy_enabled_original_read',decision=seq,gate=name)
        possible=flag_possible(source,False,{'worker_unusable_transition'},set(),v['sample_ns'],f['commit_ns'])
        for name in ('early_worker_unusable','commit_worker_unusable','fallback_invalid_worker_unusable','fallback_source_worker_unusable'):
            if reads.get(name) is not None:ev.need(reads[name] in possible,'worker_unusable_source_transition_binding',decision=seq,gate=name)
        if reads.get('commit_sink_failed') is not None:ev.need(reads['commit_sink_failed'] is False,'complete_source_sink_failed_operand',decision=seq)
        phases=[{'type':'stopping_observed','ns':p['ns']} for p in s['records']['observer/witness.json']['phase'] if p['event_code']==5]
        possible=flag_possible(phases,False,{'stopping_observed'},set(),d['start_ns'],d['end_ns'])
        for name in ('early_stopping','final_stopping','fallback_invalid_stopping','fallback_source_stopping'):
            if reads.get(name) is not None:ev.need(reads[name] in possible,'stopping_operand_independent_Witness_phase_window',decision=seq,gate=name,possible=sorted(possible))
        if reads.get('commit_worker_valid') is not None:
            lease=lease_replay.state_at(s['lease_replay'],f['commit_ns'])
            ev.need(type(reads['commit_worker_valid']) is bool and reads['commit_worker_valid'] is lease['worker_valid'] and (not lease['worker_valid'] or (not lease['worker_unusable'] and 0<=f['commit_ns']-lease['last_valid_ns']<=cfg['worker_capability_receipt_timeout_ns'])),'worker_valid_lease_source_binding',decision=seq)
        last_accepted,p=replay_gates(d,v,f,vp,fp,captures.get(seq),job,cfg,last_accepted,ev);gates.append(p)
    ev.group('actual_gate_short_circuit_shape_and_independent_reason_fallback',decisions=len(gates),proof=gates,
             irreversible_flag_read_proof=irreversible_proof,
             Decision_reason_used_as_input=False,operand_read_timestamps_available=False)
    witness_integrity(s,decisions,ev)
    return {'schema':'p1-C3.2-atomic-observation-components-v2','passed':not ev.issues,
        'groups':ev.groups,'issues':ev.issues,'run_id':s['records']['inputs.json']['run_id'],
        'run':s['root'],'component_verification_only':True,'preregister_sha256':PREREG_SHA,
        'input_sha256':s['hashes'],'external_input_sha256':s['external_hashes'],'storage':s['storage'],
        'independent_pre_run_record_pin_claimed':False,'original_authenticity_qualified':False,
        'scope_limits':['bounded synthetic shadow inputs only','recorded finite ASCII reference fingerprint domain',
            'noninput pause/schedule mutation not covered','operand values at original reads observed; no per-operand timestamp',
            'normal Witness eligibility separate from all-rejected component integrity',
            'no dynamic20s/mixed-turn/plant acceptance or stage qualification'],**FLAGS}


def unchanged(s):
    return all(sha(safe.read_regular(Path(s['root'])/p))==h for p,h in s['hashes'].items()) and all(sha(safe.read_regular(Path(p)))==h for p,h in s['external_hashes'].items())


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    try:
        s=load(args.run);report=analyze(s);report['original_inputs_unchanged']=unchanged(s)
        if not report['original_inputs_unchanged']:report['passed']=False;report['issues'].append({'code':'input_changed_during_check'})
        report['checker_sha256']=sha(safe.read_regular(N/'check_atomic_observation_v2.py'))
    except Exception as error:
        report={'schema':'p1-C3.2-atomic-observation-components-v2','passed':False,'component_verification_only':True,
            'issues':[{'code':'bounded_input_or_checker_error','detail':type(error).__name__+': '+str(error)}],**FLAGS}
    # O_EXCL also rejects dangling symlinks; all inputs were no-follow bounded.
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':report['passed'],'issues':report['issues'][:20],
        'groups':{k:v['passed'] for k,v in report.get('groups',{}).items()}},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
