#!/usr/bin/env python3
"""Offline, pinned readiness and terminal component checks; never a shared full-chain gate.

No ROS node is created. Actual stored CDR is decoded using the sealed parent
reader, then extra source/ready/history joins are independently checked here.
The record lock is retrospective for the selected run, not experiment Go.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time

MAX_BYTES = 128 * 1024 * 1024
MAX_ROWS = 20000
I64 = (1 << 63) - 1
U64 = (1 << 64) - 1
ROLES = ('publisher', 'worker', 'observer', 'synthetic_source', 'recorder')
READY_FIELDS = set(('schema graph_arm_ns legacy_ready_ns executor_spinning evidence_source measurement_eligible '
    'legacy_identity clock_epoch legacy_received_count legacy_admitted_count anchor_sequence anchor_n anchor_known '
    'anchor_publish_ns anchor_sim_ns pair_processed_ns pair_publish_end_ns odom_stamp_ns odom_receive_ns odom_sequence '
    'imu_stamp_ns imu_receive_ns imu_sequence r_from_imu clock_sim_ns clock_receive_ns rtf rtf_valid paused path_sequence '
    'profile_sequence path_stamp profile_stamp path_fingerprint profile_fingerprint version held_history preodom_held '
    'worker_capability capability_validation_commit_ns capability_lease_last_valid_ns capability_timeout_ns '
    'prepare_start_ns prepare_deadline_ns').split())
APPLIED_FIELDS = set(('schema_version run_id producer_instance_id baseline_id config_hash sequence clock_epoch sim_time_ns '
    'clock_receive_steady_ns clock_age_ns clock_status steady_clock_domain cycle_sequence control_source event_semantics '
    'requested_known requested_n final_n left_publish_success right_publish_success left_publish_start_steady_ns '
    'left_publish_end_steady_ns right_publish_start_steady_ns right_publish_end_steady_ns left_sim_time_ns right_sim_time_ns '
    'left_clock_epoch right_clock_epoch left_clock_age_ns right_clock_age_ns map_scale lower_n upper_n previous_anchor_known '
    'previous_final_n plant_acceptance_observed force_measured execution_atomicity_proven publish_error').split())
CAP_FIELDS = set(('schema_version run_id boot_id contract_hash nominal_hash worker_instance clock_name backend matrix_layout '
    'horizon_steps prediction_dt pid startup_ns completed_jobs active_job pending_count fault_injection_enabled fatal reason').split())
APPLIED_TOPIC = '/research/control/applied'
CAP_TOPIC = '/p1/worker_capability'
PUB_STREAMS = {'state': '/research/state_snapshot', 'applied': APPLIED_TOPIC,
    'cycle': '/research/cycle_timing', 'reference_prediction': '/research/reference_prediction'}
OBSERVER_EVENTS = set(('recording_ready startup capability_admission decision clock path_version profile_version '
    'imu_admission odom_admission legacy_anchor legacy_ready job job_publish_result candidate_registration '
    'anchor_validation regulator_shutdown source_summary').split())
WORKER_EVENTS = set(('worker_recording_ready worker_capability_recording_ready job_received candidate '
    'candidate_publish_result worker_summary capability_source_header capability_publish_attempt capability_publish_result').split())
FALSE_GATES = ('strict_shared_v2_full_chain_qualified', 'all_old_v2_gates_reexecuted',
    'nominal_propagation_independently_recomputed', 'complete_input_callback_raw_provenance',
    'capability_all_population_bijection', 'capability_publisher_source_count_verified',
    'live_endpoint_ownership_reauthenticated', 'clean_resource_lifecycle_independently_proven',
    'D1_dynamic_qualified', 'B4_qualified', 'M0b_qualified', 'execute_qualified')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute input path without traversal required')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=directory)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            raise ValueError('nonregular or over-budget input: ' + str(path))
        parts, count = [], 0
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            count += len(part)
            if count > MAX_BYTES:
                raise ValueError('input grew over budget')
            parts.append(part)
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        def identity(item):
            return (item.st_dev, item.st_ino, item.st_mode, item.st_size,
                    item.st_mtime_ns, item.st_ctime_ns)
        if identity(st) != identity(after) or identity(st) != identity(named) or count != st.st_size:
            raise ValueError('input changed during bounded read: ' + str(path))
        return b''.join(parts)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def strict_json(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate JSON key: ' + k)
            result[k] = v
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + x)))
    def bounded(v, depth=0):
        if depth > 32:
            raise ValueError('JSON depth exceeds bound')
        if type(v) is dict:
            return 1 + sum(bounded(x, depth + 1) for x in v.values())
        if type(v) is list:
            return 1 + sum(bounded(x, depth + 1) for x in v)
        if type(v) is float and not math.isfinite(v):
            raise ValueError('nonfinite JSON number')
        return 1
    if bounded(value) > 2000000:
        raise ValueError('JSON population exceeds bound')
    return value


def jsonl(raw):
    if not raw or not raw.endswith(b'\n'):
        raise ValueError('source not newline-closed')
    lines = raw.splitlines()
    if len(lines) > MAX_ROWS or any(not x for x in lines):
        raise ValueError('source row budget or blank row')
    rows = [strict_json(x) for x in lines]
    if any(type(x) is not dict or type(x.get('type')) is not str for x in rows):
        raise ValueError('source event is not a typed object')
    return rows


def integer(x, lower=0, upper=I64):
    return type(x) is int and lower <= x <= upper


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def equal(a, b):
    """Exact JSON shape, bool/int typing, and IEEE double values including signed zero."""
    if type(a) is dict and type(b) is dict:
        return set(a) == set(b) and all(equal(a[k], b[k]) for k in a)
    if type(a) is list and type(b) is list:
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if type(a) is float or type(b) is float:
        return finite(a) and finite(b) and struct.pack('>d', a) == struct.pack('>d', b)
    return type(a) is type(b) and a == b


def rows_of(rows, tag):
    return [r for r in rows if r['type'] == tag]


class Gate:
    def __init__(self):
        self.issues = []
    def need(self, value, code, **detail):
        if not value:
            self.issues.append({'code': code, **detail})
        return value
    def once(self, rows, tag):
        chosen = rows_of(rows, tag)
        if not self.need(len(chosen) == 1, 'exactly_one_event_required', event=tag, count=len(chosen)):
            raise ValueError('missing/duplicate event: ' + tag)
        return chosen[0]


def import_sealed(contract):
    # Hash every imported file first; no unchecked copied helper is consulted.
    for item in contract['sealed_helpers'].values():
        if digest(read_regular(item['path'])) != item['sha256']:
            raise ValueError('sealed helper changed: ' + item['path'])
    parent = Path(contract['parent_root'])
    for p in (parent, parent / 'runtime'):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    mods = {n: importlib.import_module(n) for n in ('check_owned_fixture', 'check_p1_execution', 'owned_auth')}
    for n, mod in mods.items():
        relative = 'runtime/check_p1_execution.py' if n == 'check_p1_execution' else n + '.py'
        if Path(mod.__file__).resolve() != Path(contract['sealed_helpers'][relative]['path']).resolve():
            raise ValueError('imported module path differs from sealed helper: ' + n)
    return mods


def load_snapshot(contract, *, negative_copy=None):
    """A negative copy is only for the fresh-copy regression harness, never CLI."""
    base = Path(contract['original_run'])
    total, records, hashes, paths = 0, {}, {}, {}
    for name, pin in contract['record_files'].items():
        original = Path(pin['path'])
        path = Path(negative_copy) / original.relative_to(base) if negative_copy and original.is_relative_to(base) else original
        raw = read_regular(path)
        total += len(raw)
        if total > MAX_BYTES:
            raise ValueError('total inputs exceed byte budget')
        hashes[name] = digest(raw)
        if negative_copy is None and hashes[name] != pin['sha256']:
            raise ValueError('record input differs from preregistered hash: ' + name)
        records[name] = jsonl(raw) if path.suffix == '.jsonl' else strict_json(raw)
        paths[name] = str(path)
    bag = Path(negative_copy or base) / 'recorder/bag'
    present = sorted(str(p.relative_to(bag)) for p in bag.rglob('*') if p.is_file())
    if present != sorted(contract['bag_files']):
        raise ValueError('actual bag file population differs')
    for relative, pin in contract['bag_files'].items():
        raw = read_regular(bag / relative)
        total += len(raw)
        if total > MAX_BYTES:
            raise ValueError('total record and bag bytes exceed budget')
        hashes['bag/' + relative] = digest(raw)
        if negative_copy is None and hashes['bag/' + relative] != pin['sha256']:
            raise ValueError('bag differs from preregistered hash: ' + relative)
        paths['bag/' + relative] = str(bag / relative)
    helpers = import_sealed(contract)
    decoded, raw_cdr, storage = helpers['check_owned_fixture'].read_actual_storage(bag, records['topics_file']['topics'])
    return {'records': records, 'hashes': hashes, 'paths': paths, 'decoded': decoded,
            'raw_cdr': raw_cdr, 'storage': storage, 'helpers': helpers,
            'negative_copy': str(negative_copy) if negative_copy else None}


def check_historical_binding(g, s, expected):
    r, h = s['records'], s['hashes']
    inputs, prep, result, startup = (r[k] for k in ('run_inputs','preparation','run_result','startup_manifest'))
    g.need(inputs['run_id'] == expected['run_id'] == result['run_id'], 'independent_run_identity_differs')
    g.need(h['contract'] == expected['contract_sha256'] == inputs['contract_sha256'], 'independent_contract_sha_differs')
    g.need(equal(inputs['expected_parameters'], expected['expected_parameters']), 'independent_configuration_root_differs')
    g.need(equal(inputs['builds'], expected['builds']) and equal(inputs['source_bundles'], expected['source_bundles']), 'build_source_roots_differ')
    g.need(set(prep['roles']) == set(ROLES), 'preparation_role_population_differs')
    g.need(equal(prep['roles'], expected['roles']), 'preparation_independent_roles_differ')
    ledger = r['ledger']
    spawns = rows_of(ledger, 'spawn')
    g.need([x['name'] for x in spawns] == ['recorder','publisher','synthetic_source','worker','observer'], 'owned_spawn_order_or_population_differs')
    for name in ROLES:
        m = r['owned_' + name]
        pin = expected['roles'][name]
        a = pin['owned']
        role = 'fixture' if name == 'synthetic_source' else name
        g.need(h['owned_' + name] == pin['manifest_sha256'], 'role_raw_sha_differs', role=name)
        wanted = {'schema_version':'p1-owned-role-v1','role':name,'run_id':expected['run_id'] + '-publisher' if name=='publisher' else expected['run_id'],
            'boot_id':a['boot_id'],'pid':a['pid'],'process_start_ticks':a['start_ticks'],'binary_sha256':a['exe_sha256'],
            'source_bundle_sha256':expected['source_bundles'][role]['sha256'],'contract_sha256':expected['contract_sha256'],'argv':a['argv'],
            'effective_parameters_sha256':pin['effective_parameters_sha256'],'effective_parameters_immutable':True,
            'effective_parameters_digest_encoding':'p1-typed-ieee754-v1','gid_storage_size':16,'rmw_implementation':'rmw_fastrtps_cpp'}
        for k, v in wanted.items():
            g.need(equal(m.get(k), v), 'owned_role_identity_or_configuration_binding_differs', role=name, field=k)
        g.need(s['helpers']['owned_auth'].parameter_digest(m['effective_parameters']) == pin['effective_parameters_sha256'], 'effective_parameter_digest_not_recomputed', role=name)
        values = {k:v['value'] for k,v in m['effective_parameters'].items()}
        g.need(equal(values, expected['expected_parameters'][name]), 'effective_parameter_values_differ', role=name)
        g.need(set(m['parameter_overrides']) <= set(values), 'unknown_parameter_override', role=name)
        start = result['prepare_start_ns']
        g.need(integer(m['created_steady_ns'], start) and m['created_steady_ns'] <= prep['checked_ns'], 'manifest_creation_order_invalid', role=name)
        spawn = [x for x in spawns if x['name']==name]
        if g.need(len(spawn)==1, 'spawn_missing', role=name):
            row=spawn[0]
            g.need(row['executable_verified'] is True and row['expected_sha256']==a['exe_sha256'] and row['expected_exe']==a['exe'] and equal(row['argv'],a['argv']), 'spawn_binary_argv_mismatch', role=name)
            g.need(all(equal(row['identity'].get(k),a[k]) for k in ('pid','pgid','sid','start_ticks','exe','exe_sha256')), 'spawn_pid_start_identity_mismatch', role=name)
        if name in ('worker','observer'):
            g.need(equal(m['contract_configuration'], r['contract']), 'effective_contract_differs', role=name)
            hooks = ['test_delay_ms','test_native_block_ms'] + ([] if name=='worker' else ['test_prepare_block_ms','test_tick_block_ms','test_sink_pause_ms'])
            for key in hooks:
                g.need(m['effective_parameters'][key]['type']==2 and type(values[key]) is int and values[key]==0, 'nonzero_or_wrong_type_hook', role=name, field=key)
    identity_keys=('run_id','producer_instance_id','baseline_id','config_hash','steady_clock_domain')
    pub=r['owned_publisher']
    g.need(startup['owned_manifest_sha256']==h['owned_publisher'] and equal(startup['application_endpoints'],pub['endpoints']), 'startup_owned_file_or_endpoints_differs')
    for key in ('pid','process_start_ticks','boot_id','binary_sha256','source_bundle_sha256','contract_sha256','effective_parameters_sha256'):
        g.need(equal(startup[key],pub[key]), 'startup_owned_identity_differs', field=key)
    g.need(prep['startup_manifest_sha256']==h['startup_manifest'] and prep['legacy_ready'] is False, 'preparation_startup_or_legacy_order_differs')
    graph=prep['graph']
    # Recheck exact endpoint membership without pretending this is a live /proc check.
    endpoints={}
    for name in ROLES:
        m=r['owned_'+name]
        for e in m['endpoints']:
            g.need(type(e['gid']) is list and len(e['gid'])==16 and any(e['gid']) and all(type(v) is int and 0<=v<=255 for v in e['gid']), 'actual_gid_shape', role=name)
            key=(e['kind'],e['topic'])
            endpoints.setdefault(key,[]).append({'node':m['node'],'type':e['type'],'gid':e['gid']})
    for (kind,topic), rows in endpoints.items():
        actual=graph['topics'][topic][kind+'s']
        g.need(len(actual)==len(rows) and all(sum(equal(x,y) for y in actual)==1 for x in rows), 'historical_graph_endpoint_population_differs', topic=topic, kind=kind)
    g.need(0 <= prep['checked_ns']-graph['observed_ns'] <= 1_000_000_000, 'historical_graph_age_differs')
    for kind,name,count,key in (('reader','observer',1,'applied'),('capability','worker',3,'capability')):
        n=r['native_'+kind];m=r['owned_'+name]
        g.need(h['native_'+kind]==prep['native_applied_reader_ready_sha256' if kind=='reader' else 'native_capability_ready_sha256'], 'native_receipt_sha_differs', role=name)
        g.need(n['schema']=='p1-owned-native-'+kind+'-ready-v1' and n['owned_manifest_sha256']==h['owned_'+name], 'native_receipt_schema_binding_differs', role=name)
        for k in ('role','run_id','contract_sha256','boot_id','pid','process_start_ticks'):
            g.need(equal(n[k],m[k]), 'native_receipt_identity_differs', role=name, field=k)
        countkey='applied_matched_publishers' if kind=='reader' else 'capability_matched_subscribers'
        g.need(type(n[countkey]) is int and n[countkey]==count and n[key+'_endpoint'] in m['endpoints'], 'native_actual_match_differs', role=name)
        g.need(result['prepare_start_ns']<=n['checked_steady_ns']<=prep['checked_ns'], 'native_receipt_order_differs', role=name)
    release,receipt=r['release'],r['receipt']
    for k in ('run_id','producer_instance_id'):
        g.need(release[k]==startup[k] and receipt[k]==startup[k], 'release_identity_differs', field=k)
    g.need(release['startup_manifest_sha256']==h['startup_manifest'] and release['driver_evidence_sha256']==h['preparation'], 'release_evidence_sha_differs')
    g.need(result['release']['release_sha256']==h['release'] and result['release']['evidence_sha256']==h['preparation'] and equal(result['release']['release'],release), 'driver_release_originals_differ')
    g.need(receipt['startup_manifest_sha256']==h['startup_manifest'] and receipt['driver_evidence_sha256']==h['preparation'] and receipt['release_file_sha256']==h['release'] and receipt['release_nonce']==release['release_nonce'], 'prepared_receipt_originals_differ')
    g.need(receipt['status']=='prepared_acceptance' and receipt['receipt_qualifies_physical_release'] is False and receipt['physical_output_state']=='held_pending_in_memory_commit', 'receipt_claims_actual_release')
    g.need(integer(release['valid_until_steady_ns'],1) and prep['checked_ns']<=receipt['attempted_acceptance_steady_ns']<release['valid_until_steady_ns'] and receipt['valid_until_steady_ns']==release['valid_until_steady_ns'], 'release_expired_or_acceptance_order_invalid')
    g.need(prep['checked_ns']-result['prepare_start_ns']<=expected['prepare_budget_ns'], 'preparation_total_budget_exceeded')
    return {'historical_evidence_only':True,'live_process_reauthentication':False,'expected_identity_fields':list(identity_keys)}


def check_applied(g,s,expected):
    r=s['records'];decoded=s['decoded'];startup=r['startup_manifest'];applied=[x['message'] for x in decoded[APPLIED_TOPIC]]
    anchors=rows_of(r['observer_source'],'legacy_anchor')
    session=r['publisher_session'];streams=session['streams']
    g.need(set(streams)==set(PUB_STREAMS),'publisher_four_streams_missing_or_unknown')
    for name,topic in PUB_STREAMS.items():
        rows=[x['message'] for x in decoded[topic]]
        if name not in streams:
            continue
        n=len(rows);count=streams[name]
        g.need(all(type(count[k]) is int for k in ('generated','emitted','dropped','first_sequence','last_sequence')), 'publisher_count_types', stream=name)
        g.need(count['generated']==count['emitted']==n and count['dropped']==0 and count['first_sequence']==(1 if n else 0) and count['last_sequence']==n, 'publisher_complete_stream_counts', stream=name)
        g.need([x['sequence'] for x in rows]==list(range(1,n+1)), 'publisher_stream_sequence_gap',stream=name)
        for x in rows:
            g.need(all(equal(x[k],startup[k]) for k in ('run_id','producer_instance_id','baseline_id','config_hash','steady_clock_domain')), 'publisher_stream_identity', stream=name)
    g.need(session['normal_end'] is True and session['flushed'] is True and session['queue_dropped_total']==0 and session['publish_errors']==0 and session['interrupted_cycle_sequence']==0,'publisher_close_not_normal')
    g.need(len(applied)>0 and len(anchors)==len(applied), 'whole_applied_anchor_population_differs', storage=len(applied), source=len(anchors))
    g.need([x['sequence'] for x in anchors]==list(range(1,len(applied)+1)), 'whole_anchor_sequence_gap')
    strings=('schema_version','run_id','producer_instance_id','baseline_id','config_hash','clock_status','steady_clock_domain','control_source','event_semantics','publish_error')
    bools=('requested_known','left_publish_success','right_publish_success','previous_anchor_known','plant_acceptance_observed','force_measured','execution_atomicity_proven')
    arrays=('requested_n','final_n','previous_final_n')
    doubles=('map_scale','lower_n','upper_n')
    ints=APPLIED_FIELDS-set(strings)-set(bools)-set(arrays)-set(doubles)
    for i,m in enumerate(applied):
        g.need(set(m)==APPLIED_FIELDS,'applied_39_field_shape',sequence=i+1)
        g.need(all(type(m[k]) is str and len(m[k].encode())<=256 for k in strings),'applied_string_type_bound',sequence=i+1)
        g.need(all(type(m[k]) is bool for k in bools),'applied_bool_type',sequence=i+1)
        g.need(all(integer(m[k],0,U64 if k in ('sequence','cycle_sequence','clock_epoch','left_clock_epoch','right_clock_epoch') else I64) for k in ints),'applied_integer_type',sequence=i+1)
        g.need(all(type(m[k]) is list and len(m[k])==2 and all(finite(v) for v in m[k]) for k in arrays) and all(finite(m[k]) for k in doubles),'applied_finite_payload',sequence=i+1)
        g.need(m['schema_version']=='p0-contract-v1' and m['event_semantics']=='publisher_command','applied_schema_semantics')
        g.need(all(m[k] is False for k in ('plant_acceptance_observed','force_measured','execution_atomicity_proven')),'publisher_command_claims_plant_ack')
        g.need(m['left_publish_success'] is True and m['right_publish_success'] is True and m['publish_error']=='','applied_pair_not_successful',sequence=i+1)
        g.need(m['lower_n']==r['contract']['command_min_n'] and m['upper_n']==r['contract']['command_max_n'] and m['map_scale']==r['contract']['map_scale'],'applied_mapping_contract_differs')
        g.need(all(m['lower_n']<=v<=m['upper_n'] for v in m['final_n']),'applied_final_out_of_bound')
        if i<len(anchors):
            a=anchors[i]
            g.need(a['applied_text_truncated'] is False and equal(a['applied'],m),'whole_applied_anchor_39_payload_differs',sequence=i+1)
            g.need(a['received_count']==a['admitted_count']==a['sequence']==i+1,'anchor_lifecycle_counts',sequence=i+1)
            g.need(a['known']==[True,True] and equal(a['final_n'],m['final_n']) and a['producer']==m['producer_instance_id'] and a['run_id']==m['run_id'] and a['clock_epoch']==m['clock_epoch'],'anchor_projection_differs',sequence=i+1)
            starts=[m['left_publish_start_steady_ns'],m['right_publish_start_steady_ns']]
            ends=[m['left_publish_end_steady_ns'],m['right_publish_end_steady_ns']]
            g.need(equal(a['publish_ns'],starts) and all(0<st<=en<=a['processed_ns'] for st,en in zip(starts,ends)), 'applied_pair_source_order',sequence=i+1)
            g.need(r['receipt']['attempted_acceptance_steady_ns']<=min(starts),'applied_before_prepared_receipt')
            if i:
                previous=applied[i-1]
                g.need(m['previous_anchor_known'] is True and equal(m['previous_final_n'],previous['final_n']),'applied_previous_anchor_chain',sequence=i+1)
                g.need(all(starts[c]>previous[('left' if c==0 else 'right')+'_publish_start_steady_ns'] for c in (0,1)), 'applied_publish_order',sequence=i+1)
    for channel,topic in enumerate(expected['physical_topics']):
        actual=[x['message']['data'] for x in decoded[topic]]
        wanted=[m['final_n'][channel]/m['map_scale'] for m in applied if m[('left' if channel==0 else 'right')+'_publish_success']]
        g.need(equal(actual,wanted),'physical_full_value_order_differs',channel=channel,storage=len(actual),applied=len(wanted))
    g.need(r['run_result']['final_publisher_applied_sequence']==len(applied)==session['streams']['applied']['last_sequence'],'terminal_applied_sequence_differs')
    if applied:
        g.need(applied[-1]['control_source']=='shutdown_zero' and equal(applied[-1]['final_n'],[0.0,0.0]), 'terminal_shutdown_applied_missing')
    return {'applied_fields':len(APPLIED_FIELDS),'actual_applied':len(applied),'observer_anchors':len(anchors),
            'whole_population':True,'physical_value_order_checked':True,'plant_acknowledgement':False}


def check_capabilities(g,s,expected):
    r=s['records'];m=r['owned_worker'];C=r['contract']
    typed=[x['message'] for x in s['decoded'][CAP_TOPIC]]
    admissions=rows_of(r['observer_source'],'capability_admission')
    immutable={'schema_version':'p1-worker-capability-v1','run_id':expected['run_id'],'boot_id':m['boot_id'],
        'contract_hash':expected['contract_sha256'],'nominal_hash':C['nominal_hash'],'worker_instance':m['worker_instance'],
        'clock_name':'CLOCK_MONOTONIC','backend':'acados','matrix_layout':'column_major','horizon_steps':C['N'],
        'prediction_dt':C['dt'],'pid':m['pid'],'fault_injection_enabled':C['fault_injection_enabled'],'fatal':False,'reason':''}
    def shape(cap):
        g.need(set(cap)==CAP_FIELDS,'capability_19_field_shape')
        for k,v in immutable.items():
            g.need(equal(cap[k],v),'capability_full_identity_contract',field=k)
        for k in ('pid','startup_ns','completed_jobs','active_job','pending_count','horizon_steps'):
            g.need(integer(cap[k],1 if k in ('pid','startup_ns','horizon_steps') else 0,U64),'capability_integer',field=k)
        g.need(cap['pending_count']<=1,'capability_pending_exceeds_bound')
    for cap in typed:
        shape(cap)
    last,cursor,matched=0,0,[]
    for i,a in enumerate(admissions):
        cap=a['capability'];shape(cap)
        g.need(a['identity_valid'] is True and a['valid'] is True and a['renewed'] is True and a['terminal_run'] is False and a['source_freshness_available'] is False,'capability_callback_invalid',index=i)
        now=a['validation_commit_ns'];received=a['receive_ns']
        g.need(integer(received,1) and integer(now,received) and now>last,'capability_callback_time')
        g.need(a['lease_timeout_ns']==C['worker_capability_receipt_timeout_ns'] and a['lease_last_before_ns']==last and a['lease_last_after_ns']==now and (last==0 or now-last<=a['lease_timeout_ns']),'capability_lease_replay',index=i)
        last=now
        while cursor<len(typed) and not equal(typed[cursor],cap):
            cursor+=1
        if g.need(cursor<len(typed),'capability_admission_no_ordered_typed_payload',index=i):
            matched.append(cursor);cursor+=1
    g.need(bool(admissions),'capability_admission_missing')
    g.need(bool(typed),'capability_storage_missing')
    return {'capability_fields':len(CAP_FIELDS),'storage_count':len(typed),'admission_count':len(admissions),
        'all_admission_payloads_checked':True,'typed_ordered_subsequence_only':True,'matched_storage_indices':matched,
        'unmatched_storage_count':len(typed)-len(matched),'complete_population_bijection':False,
        'publisher_source_publish_counts_available':False,'source_packet_freshness_available':False}


def check_readiness(g,s,expected):
    r=s['records'];src=r['observer_source'];C=r['contract'];readyrow=g.once(src,'legacy_ready');q=readyrow['readiness']
    g.need(set(readyrow)=={'type','schema','run_id','readiness'} and readyrow['schema']=='p1-D1-legacy-ready-source-v1' and readyrow['run_id']==expected['run_id'],'ready_source_shape_identity')
    g.need(set(q)==READY_FIELDS,'ready_44_field_shape',missing=sorted(READY_FIELDS-set(q)),unknown=sorted(set(q)-READY_FIELDS))
    g.need(q['schema']=='p1-D1-legacy-ready-v1' and q['executor_spinning'] is True and q['evidence_source']=='executor_callback_join' and q['measurement_eligible'] is True,'ready_schema_callback_flags')
    booleans=('executor_spinning','measurement_eligible','r_from_imu','rtf_valid','paused')
    for k in booleans:
        g.need(type(q[k]) is bool,'ready_bool_type',field=k)
    array_ints=('anchor_sequence','anchor_publish_ns','anchor_sim_ns','pair_publish_end_ns','path_stamp','profile_stamp')
    for k in array_ints:
        g.need(type(q[k]) is list and len(q[k])==2 and all(integer(v) for v in q[k]),'ready_integer_pair_type',field=k)
    g.need(type(q['anchor_n']) is list and len(q['anchor_n'])==2 and all(finite(v) for v in q['anchor_n']) and q['anchor_known']==[True,True] and all(type(v) is bool for v in q['anchor_known']),'ready_anchor_types')
    exclude=set(booleans)|set(array_ints)|{'schema','evidence_source','legacy_identity','anchor_n','anchor_known','rtf','path_fingerprint','profile_fingerprint','version','held_history','preodom_held','worker_capability'}
    for k in READY_FIELDS-exclude:
        g.need(integer(q[k],0 if k=='clock_epoch' else 1),'ready_integer_type',field=k)
    g.need(type(q['version']) is dict and set(q['version'])=={'task','model','config','schedule','epoch'} and all(integer(v) for v in q['version'].values()),'ready_version_shape')
    for k in ('path_fingerprint','profile_fingerprint'):
        g.need(type(q[k]) is str and re.fullmatch('[0-9a-f]{64}',q[k]) is not None,'ready_fingerprint_shape',field=k)
    startup=g.once(src,'startup');arm=g.once(src,'recording_ready');legacy=r['startup_manifest']
    identity={k:legacy[k] for k in ('run_id','producer_instance_id','baseline_id','config_hash','steady_clock_domain')};identity['schema']='p0-contract-v1'
    g.need(equal(q['legacy_identity'],identity) and equal(startup['legacy_expected_identity'],identity),'ready_independent_legacy_identity')
    g.need(q['graph_arm_ns']==arm['ready_ns'] and q['prepare_start_ns']==startup['legacy_prepare_start_ns'] and q['prepare_deadline_ns']==startup['legacy_prepare_deadline_ns'],'ready_prepare_source_binding')
    now=q['legacy_ready_ns']
    g.need(q['graph_arm_ns']<q['prepare_start_ns']<now<=q['prepare_deadline_ns'] and q['prepare_deadline_ns']-q['prepare_start_ns']==startup['legacy_ready_timeout_ns'],'ready_prepare_order_or_expiry')
    g.need(now-r['run_result']['prepare_start_ns']<=expected['prepare_budget_ns'],'ready_total_prepare_budget_exceeded')
    q_index=src.index(readyrow);prefix=src[:q_index]
    anchors=rows_of(prefix,'legacy_anchor');n=len(anchors)
    g.need(n>0 and q['legacy_received_count']==q['legacy_admitted_count']==n and q['anchor_sequence']==[n,n],'ready_complete_prefix_pair_lifecycle')
    last=anchors[-1];a=last['applied']
    g.need(equal(q['anchor_n'],a['final_n']) and equal(q['anchor_publish_ns'],[a['left_publish_start_steady_ns'],a['right_publish_start_steady_ns']]) and equal(q['anchor_sim_ns'],[a['left_sim_time_ns'],a['right_sim_time_ns']]) and equal(q['pair_publish_end_ns'],[a['left_publish_end_steady_ns'],a['right_publish_end_steady_ns']]) and q['pair_processed_ns']==last['processed_ns'],'ready_actual_pair_projection')
    g.need(q['clock_epoch']==a['clock_epoch']==q['version']['epoch'],'ready_epoch_differs')
    history=[]
    for anchor in anchors:
        m=anchor['applied']
        for channel,side in enumerate(('left','right')):
            if m[side+'_publish_success']:
                history.append({'sim_ns':m[side+'_sim_time_ns'],'channel':channel,'n':m['final_n'][channel],'sequence':m['sequence'],'publish_ns':m[side+'_publish_start_steady_ns']})
        history=history[-C['history_capacity']:]
    g.need(equal(q['held_history'],history),'ready_complete_held_history_replay')
    held=[None,None]
    for entry in history:
        if entry['sim_ns']<=q['odom_stamp_ns']:
            held[entry['channel']]=entry
    g.need(all(x is not None for x in held) and equal(q['preodom_held'],held),'ready_latest_preodom_held_replay')
    g.need(q['odom_receive_ns']>q['pair_processed_ns'] and q['odom_stamp_ns']>=max(q['anchor_sim_ns']),'ready_postpair_odom_order')
    for tag,kind in (('odom_admission','odom'),('imu_admission','imu')):
        candidates=rows_of(prefix,tag)
        g.need([x['sequence'] for x in candidates]==list(range(1,len(candidates)+1)),'ready_input_callback_sequence',source=kind)
        valid=[x for x in candidates if x['valid'] is True]
        if not valid:
            raise ValueError('ready input callback missing: '+kind)
        v=valid[-1]
        g.need(v['accepted_sequence']==q[kind+'_sequence'] and v['stamp_ns']==q[kind+'_stamp_ns'] and v['receive_ns']==q[kind+'_receive_ns'],'ready_latest_input_callback_join',source=kind)
        if kind=='odom':
            g.need(v['pose_frame']==C['expected_pose_frame'] and v['child_frame']==C['expected_child_frame'] and v['pose_frame_truncated'] is False and v['child_frame_truncated'] is False,'ready_odom_frames')
        else:
            g.need(v['frame_id']==C['expected_imu_frame'] and v['frame_truncated'] is False and finite(v['r_value']),'ready_imu_frame_payload')
        receive=q[kind+'_receive_ns'];stamp=q[kind+'_stamp_ns'];sim_now=q['clock_sim_ns']+now-q['clock_receive_ns']
        g.need(0<=now-receive<=C[kind+'_age_ns'] and -C['source_future_slack_ns']<=sim_now-stamp<=C[kind+'_sim_lag_ns'],'ready_source_age_lag_future',source=kind)
    g.need(abs(q['odom_stamp_ns']-q['imu_stamp_ns'])<=C['mixed_skew_ns'],'ready_input_skew')
    g.need(q['r_from_imu']==(q['imu_receive_ns']>q['odom_receive_ns']),'ready_latest_yaw_rate_source')
    clocks=rows_of(prefix,'clock');clock=clocks[-1]
    g.need(q['clock_receive_ns']==clock['receive_ns'] and q['clock_sim_ns']==clock['sim_ns'] and q['clock_epoch']==clock['epoch'] and equal(q['rtf'],clock['rtf']) and q['version']['schedule']==clock['schedule_generation'],'ready_clock_source_join')
    g.need(0<=now-q['clock_receive_ns']<=C['clock_age_ns'] and q['paused'] is False and q['rtf_valid'] is True and finite(q['rtf']) and C['rtf_low']<=q['rtf']<=C['rtf_high'],'ready_clock_age_rtf')
    for kind in ('path','profile'):
        versions=rows_of(prefix,kind+'_version');v=versions[-1]
        g.need(v['valid'] is True and v['resource_valid'] is True and v['received_sequence']==q[kind+'_sequence'] and v['fingerprint']==q[kind+'_fingerprint'],'ready_reference_callback_join',source=kind)
        g.need([x['received_sequence'] for x in versions]==list(range(1,len(versions)+1)), 'reference_callback_sequence',source=kind)
        g.need(q['version']['task']>=v['task_generation'],'ready_task_generation')
    g.need(equal(q['path_stamp'],q['profile_stamp']) and 0<=q['path_stamp'][1]<1_000_000_000,'ready_reference_stamp_pair')
    caps=[x for x in rows_of(prefix,'capability_admission') if x['renewed'] is True];cap=caps[-1]
    g.need(equal(q['worker_capability'],cap['capability']) and q['capability_validation_commit_ns']==cap['validation_commit_ns'] and q['capability_lease_last_valid_ns']==cap['lease_last_after_ns'] and q['capability_timeout_ns']==C['worker_capability_receipt_timeout_ns'] and 0<=now-q['capability_lease_last_valid_ns']<=q['capability_timeout_ns'],'ready_actual_capability_lease_join')
    return {'ready_fields':len(READY_FIELDS),'once_callback_ready':True,'ready_prefix_applied':n,'history_entries':len(history),
        'history_recomputed_from_actual_applied':True,'reference_fingerprint_recomputed_from_raw':False,
        'rtf_estimator_independently_recomputed':False,'nominal_prediction_recomputed':False}


def check_jobs(g,s,expected):
    r=s['records'];src=r['observer_source'];worker=r['worker_source'];helper=s['helpers']['check_p1_execution']
    def project(j):
        result=helper.projection(j,helper.JOB_FIELDS,helper.JOB_ALIASES)
        g.need(len(result)==len(helper.JOB_FIELDS),'immutable_job_missing_field')
        return result
    def index(rows,key,label):
        d={}
        for x in rows:
            k=key(x);g.need(k not in d,'duplicate_job_join_identity',stream=label,identity=k);d[k]=x
        return d
    jobs=index(rows_of(src,'job'),lambda x:x['job']['job_id'],'observer_job')
    received=index(rows_of(worker,'job_received'),lambda x:x['job']['job_id'],'worker_received')
    candidates=index(rows_of(worker,'candidate'),lambda x:x['job']['job_id'],'candidate')
    registrations=index(rows_of(src,'candidate_registration'),lambda x:x['job']['job_id'],'registration')
    publishes=index(rows_of(src,'job_publish_result'),lambda x:x['job_id'],'job_publish_result')
    candidate_pubs=index(rows_of(worker,'candidate_publish_result'),lambda x:x['job_id'],'candidate_publish_result')
    for label,d in (('worker_received',received),('candidate',candidates),('registration',registrations),('job_publish_result',publishes),('candidate_publish_result',candidate_pubs)):
        g.need(set(d)==set(jobs),'complete_job_pipeline_population_differs',stream=label,expected=len(jobs),observed=len(d))
    for key in jobs.keys() & received.keys() & candidates.keys() & registrations.keys() & publishes.keys() & candidate_pubs.keys():
        job=jobs[key];j=project(job['job']);recv=received[key];c=candidates[key];reg=registrations[key];p=publishes[key];cp=candidate_pubs[key]
        for name,obj in (('worker_received',recv),('candidate',c),('registration',reg)):
            g.need(equal(j,project(obj['job'])),'immutable_job_pipeline_payload_differs',identity=key,stream=name)
        g.need(recv['worker_instance']==r['owned_worker']['worker_instance']==c['worker_instance']==reg['worker_instance'],'pipeline_worker_instance_differs',identity=key)
        g.need(job['submit_commit_ns']<=job['publish_start_ns']<=p['publish_start_ns']<=p['publish_end_ns'] and p['success'] is True,'job_publish_commit_order',identity=key)
        g.need(recv['receive_ns']<=recv['commit_ns']<=c['solve_start_ns']<=c['solve_end_ns']<=cp['publish_start_ns']<=cp['publish_end_ns']<=reg['ready_commit_ns'] and cp['success'] is True,'candidate_receive_solve_publish_registration_order',identity=key)
        g.need(reg['solve_start_ns']==c['solve_start_ns'] and reg['solve_end_ns']==c['solve_end_ns'] and equal(reg['first_control'],c['first_control']),'registration_candidate_payload_differs',identity=key)
        g.need(type(reg['accepted_registration']) is bool and type(reg['reason']) is str and (reg['reason']=='' if reg['accepted_registration'] else reg['reason']!=''),'registration_accept_reason_consistency',identity=key)
        # Native success leaves the diagnostic error string empty in the sealed Worker.
        g.need(c['success'] is True and c['solver_invoked'] is True and c['prediction_available'] is True and c['reason']=='' and c['backend']=='acados','candidate_native_result_not_normal',identity=key)
    return {'jobs':len(jobs),'worker_received':len(received),'candidates':len(candidates),'registrations':len(registrations),'immutable_job_field_count':len(helper.JOB_FIELDS),'nominal_recomputed':False}


def check_lifecycle(g,s,expected):
    r=s['records'];src=r['observer_source'];worker=r['worker_source'];ledger=r['ledger'];result=r['run_result']
    g.need(set(x['type'] for x in src)<=OBSERVER_EVENTS,'unknown_or_failure_observer_source_event',unknown=sorted(set(x['type'] for x in src)-OBSERVER_EVENTS))
    g.need(set(x['type'] for x in worker)<=WORKER_EVENTS,'unknown_or_failure_worker_source_event',unknown=sorted(set(x['type'] for x in worker)-WORKER_EVENTS))
    summary=g.once(src,'source_summary');ws=g.once(worker,'worker_summary');shutdown=g.once(src,'regulator_shutdown')
    g.need(src[-1] is summary and summary['generated']==summary['emitted']==len(src)-1 and summary['dropped']==0 and summary['normal_source_complete'] is True,'observer_complete_terminal_source')
    n=len(rows_of(worker,'candidate'))
    g.need(worker[-1] is ws and ws['generated_candidates']==ws['published_candidates']==ws['completed_jobs']==n and ws['fatal'] is False and ws['terminal_numerical_failure'] is False and ws['normal_source_complete'] is True,'worker_complete_terminal_source')
    decisions=rows_of(src,'decision')
    g.need(shutdown['last_decision_sequence']==len(decisions) and shutdown['normal_contract_complete'] is True and shutdown['shutdown_grace_exceeded'] is False and shutdown['zero_target_published'] is False and shutdown['plant_hold_end_known'] is False,'shadow_shutdown_source_not_normal')
    g.need(decisions[-1]['reason']=='shutdown' and decisions[-1]['end_ns']<=shutdown['finished_ns']<=summary['finished_ns'],'shadow_shutdown_decision_order')
    for d in decisions:
        g.need(d['mode']=='shadow' and d['diagnostic_only'] is True and d['normal_contract_complete'] is False and d['publish_success']==[False,False],'shadow_decision_claims_physical_execution')
    g.need(result['ledger_failed'] is False and result['cleanup_complete'] is True and result['cleanup_within_budget'] is True and not result.get('error'),'historical_driver_close_or_evidence_failed')
    g.need(result['elapsed_ns']<=expected['overall_budget_ns'] and result['close_elapsed_ns']<=expected['close_budget_ns'],'historical_overall_or_close_budget_exceeded')
    g.need(set(result['owned_role_returncodes'])==set(ROLES) and all(type(x) is int and x==0 for x in result['owned_role_returncodes'].values()),'owned_role_nonzero_or_missing_rc')
    allowed={'spawn','signal','cleanup_result','supervisor_summary'}
    g.need(set(x['type'] for x in ledger)<=allowed,'unknown_child_or_lifecycle_ledger_event',unknown=sorted(set(x['type'] for x in ledger)-allowed))
    ls=g.once(ledger,'supervisor_summary')
    g.need(ledger[-1] is ls and ls['cleanup_failed'] is False and ls['unverified_children']==[] and set(ls['children'])==set(ROLES),'supervisor_terminal_failure')
    for name in ROLES:
        clean=ls['children'][name]
        g.need(clean['cleanup_complete'] is True and clean['returncode']==0 and clean.get('remaining_members')==[] and equal(clean,result['cleanup'][name]),'owned_close_record_differs',role=name)
    signals=rows_of(ledger,'signal')
    g.need([x['name'] for x in signals]==['publisher','observer','worker','synthetic_source','recorder'] and all(x['signal']==2 for x in signals),'normal_close_signal_order_or_escalation')
    for row in signals:
        a=expected['roles'][row['name']]['owned']
        g.need(len(row['members'])==1 and all(row['members'][0].get(k)==a[k] for k in ('pid','pgid','sid','start_ticks')),'unknown_child_in_signal_population',role=row['name'])
    terminal=r['recorder_terminal'];rec=r['owned_recorder']
    g.need(terminal['clean'] is True and terminal['Recorder_stop_completed'] is True and terminal['metadata_exists'] is True and terminal['error']=='','recorder_stop_or_storage_close_failed')
    g.need(terminal['manifest_sha256']==s['hashes']['owned_recorder'] and terminal['metadata_sha256']==s['hashes']['bag/metadata.yaml'],'recorder_closed_metadata_sha_differs')
    for k in ('run_id','boot_id','pid','process_start_ticks','contract_sha256','source_bundle_sha256'):
        g.need(equal(terminal[k],rec[k]),'recorder_terminal_identity',field=k)
    helper=s['helpers']['check_owned_fixture'];basis=helper.witness_source_join(r['witness'],expected['expected_witness_header'],src)
    g.need(basis['passed'],'whole_source_fixed_witness_join_failed',issues=basis['issues'])
    witness=r['witness']
    stop_ns=next(x['monotonic_ns'] for x in signals if x['name']=='observer')
    for stream in ('tick','submit','activation','phase'):
        for i,row in enumerate(witness[stream]):
            for k in ('failed','failed_start','failed_end'):
                if k in row:
                    g.need(row[k] is False,'witness_failed_lifecycle_state',stream=stream,index=i,field=k)
            for k in ('stopping','stopping_start','stopping_end'):
                if k in row and row[k] is True:
                    ns=row.get('start_ns',row.get('commit_ns',row.get('ns',0)))
                    g.need(ns>=stop_ns,'witness_stopping_before_owned_shutdown',stream=stream,index=i)
            if stream=='phase':
                g.need(all(row[k] is not None for k in ('candidate_present','pending_present','failed','stopping','pause_active')) and row['admission_slots']>=0,'witness_unknown_phase_state')
    g.need(witness['first_failure']['code']==0,'witness_first_failure_recorded')
    return {'source_rows':len(src),'worker_rows':len(worker),'normal_recorded_close':True,
            'witness_join':basis,'continuous_unknown_child_observation_proven':False,
            'v2_tail_wait_acknowledgement_proven':False,'resource_lifecycle_qualified':False}


def validate_snapshot(s,contract):
    """Pure semantic gates; used on fresh copied inputs by the negative harness."""
    started=time.monotonic_ns();components={};expected=contract['expected']
    funcs=(('historical_pins_configuration_release',check_historical_binding),('whole_applied_publisher_physical',check_applied),
        ('capability_admission_subset_lease',check_capabilities),('legacy_ready_schema_history_callbacks',check_readiness),
        ('worker_received_immutable_pipeline',check_jobs),('source_recorded_close_witness',check_lifecycle))
    for name,fn in funcs:
        g=Gate();detail={}
        try:
            detail=fn(g,s,expected)
        except (ValueError,KeyError,TypeError,IndexError,StopIteration,OverflowError) as e:
            g.need(False,'component_input_or_schema_error',error=type(e).__name__+': '+str(e))
        components[name]={'passed':not g.issues,'issues':g.issues,**detail}
    g=Gate();r=s['records'];helper=s['helpers']['check_owned_fixture']
    try:
        transport=helper.transport_join(s['raw_cdr'],r['transport_source'],{k:r['owned_'+k] for k in ROLES},r['topics_file']['topics'])
        g.need(transport['passed'],'transport_full_cdr_storage_join',issues=transport['issues'])
        source=helper.source_typed_join(r['observer_source'],r['worker_source'],s['decoded'])
        g.need(source['passed'],'sealed_source_typed_full_payload_join',issues=source['issues'])
        t=r['synthetic_terminal'];counts=s['storage']['actual_counts']
        expected_raw={e['topic'] for e in r['owned_synthetic_source']['endpoints'] if e['kind']=='publisher'}
        g.need(set(t['published_counts'])==expected_raw,'synthetic_full_raw_count_key_set')
        g.need(t['normal_end'] is True and t['failed'] is False and t['synthetic'] is True and t['run_id']==expected['run_id'],'synthetic_terminal_failed')
        g.need(all(type(n) is int and n==counts[k] for k,n in t['published_counts'].items()),'synthetic_full_raw_storage_count')
        g.need(equal(t['transport_counts'],transport['counts']) and t['transport_total']==sum(counts.values()),'synthetic_terminal_transport_counts')
        log=r['transport_source']
        g.need(all(set(x)=={'type','topic','ros_type','serialization','publisher_gid','payload_sha256','serialized_bytes','receive_ns','ordinal'} and x['type']=='transport_message' and x['serialization']=='cdr' and integer(x['serialized_bytes'],1) and integer(x['receive_ns'],1) and integer(x['ordinal'],1) for x in log),'transport_row_shape_or_semantics')
        g.need([x['ordinal'] for x in log]==list(range(1,len(log)+1)), 'transport_global_ordinal_sequence')
    except (ValueError,KeyError,TypeError,IndexError) as e:
        g.need(False,'transport_source_schema_error',error=type(e).__name__+': '+str(e))
    components['sealed_reader_transport_and_typed_supplement']={'passed':not g.issues,'issues':g.issues,'actual_storage':s['storage']}
    report={'schema':'p1-current-legacy-rule-components/v5','component_suite_passed':all(x['passed'] for x in components.values()),
        'scope':'selected independently checked readiness/terminal components only; not a strict full-chain acceptance',
        'fixture_only':True,'negative_copy_semantic_testing':s['negative_copy'] is not None,'components':components,
        'input_sha256':s['hashes'],'limits':contract['limits'],'elapsed_ns':time.monotonic_ns()-started,
        'limitations':['historical external ownership records are checked; exited processes are not live-reauthenticated',
            'capability observer subset has no packet sequence/send-time or publisher-source count; omitted prepare/tail population remains explicit',
            'input callback logs omit portions of raw payload; reference fingerprint and RTF estimator not independently recomputed',
            'nominal propagation/reference/model replay and every inherited schema-v2 gate are not independently rerun',
            'v2 lacks continuous unknown-child observations and explicit final-delivery close acknowledgement']}
    report.update({k:False for k in FALSE_GATES})
    return report


def rehash_snapshot(s):
    return {k:digest(read_regular(v)) for k,v in s['paths'].items()}


def create_only(path,value):
    path=Path(path);raw=(json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o644)
    try:
        view=memoryview(raw)
        while view:
            count=os.write(fd,view);view=view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return digest(raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();contract_raw=read_regular(args.contract.absolute());contract=strict_json(contract_raw)
    try:
        s=load_snapshot(contract);report=validate_snapshot(s,contract)
        unchanged=rehash_snapshot(s)==s['hashes']
        report['raw_inputs_unchanged']=unchanged
        report['component_suite_passed'] &= unchanged
    except Exception as e:
        report={'schema':'p1-readiness-v3-offline-components/v1','component_suite_passed':False,'reader_error':type(e).__name__+': '+str(e),'fixture_only':True,**{k:False for k in FALSE_GATES}}
    report['contract_sha256']=digest(contract_raw);report['validator_sha256']=digest(read_regular(__file__))
    create_only(args.output,report)
    print(json.dumps({'component_suite_passed':report['component_suite_passed'],'output':str(args.output),
        'strict_shared_v2_full_chain_qualified':False,'reader_error':report.get('reader_error')},ensure_ascii=False))
    return 0 if report['component_suite_passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
