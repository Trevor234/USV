"""Owned endpoint/configuration gate for the bounded localhost fixture.

Trust starts with the caller's Supervisor spawn records and predeclared build
pins, never a file's PID or a node name. This gate has no execute qualification.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import secrets
import struct
import stat
import time
from owned_release import (require, digest, read_regular, strict_json,
                           create_only_json, authenticate_owned, authenticate_startup)

def canonical_parameters(parameters):
    result = {}
    for name, row in parameters.items():
        require(type(name) is str and type(row) is dict, 'invalid parameter row')
        kind, value = row['type'], row['value']
        require(type(kind) is int and 0 <= kind <= 9, 'invalid parameter type')
        scalar_checks = {0:lambda v:v is None, 1:lambda v:type(v) is bool,
                         2:lambda v:type(v) is int and -(1<<63) <= v < (1<<63),
                         3:lambda v:type(v) in (int,float) and math.isfinite(v),
                         4:lambda v:type(v) is str}
        if kind <= 4:
            require(scalar_checks[kind](value), 'parameter value type differs: ' + name)
        else:
            require(type(value) is list, 'parameter array required')
            element_checks = {5:lambda v:type(v) is int and 0 <= v <= 255,
                              6:scalar_checks[1], 7:scalar_checks[2],
                              8:scalar_checks[3], 9:scalar_checks[4]}
            require(all(element_checks[kind](v) for v in value), 'parameter array element type differs: ' + name)
        if kind == 3:
            require(type(value) in (int, float), 'double parameter required')
            canonical = struct.pack('>d', value).hex()
        elif kind == 8:
            require(type(value) is list, 'double array required')
            canonical = [struct.pack('>d', item).hex() for item in value]
        else:
            canonical = value
        require(row.get('canonical_value') == canonical, 'canonical parameter differs: ' + name)
        result[name] = {'type': kind, 'canonical_value': canonical}
    return result

def parameter_digest(parameters):
    raw = json.dumps(canonical_parameters(parameters), sort_keys=True,
                     ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    return digest(raw)

def authenticate_role(path, owned, boot, pins, expected_parameters, prepare_start_ns):
    actual = authenticate_owned(owned, boot)
    raw = read_regular(path)
    m = strict_json(raw)
    require(m.get('schema_version') == 'p1-owned-role-v1', 'owned role schema mismatch')
    for key, value in pins.items():
        require(m.get(key) == value, 'owned role pin mismatch: ' + key)
    require(m.get('pid') == actual['pid'] and m.get('process_start_ticks') == actual['start_ticks'], 'owned manifest author differs')
    require(m.get('binary_sha256') == actual['exe_sha256'] and m.get('boot_id') == boot, 'owned binary/boot differs')
    require(m.get('argv') == actual['argv'], 'owned effective argv differs')
    created = m.get('created_steady_ns')
    require(type(created) is int and prepare_start_ns <= created <= time.monotonic_ns(), 'owned manifest timestamp invalid')
    require(m.get('effective_parameters_digest_encoding') == 'p1-typed-ieee754-v1', 'parameter digest protocol differs')
    require(parameter_digest(m['effective_parameters']) == m.get('effective_parameters_sha256'), 'effective parameter digest differs')
    require(m.get('effective_parameters_immutable') is True, 'configuration not frozen')
    observed_values = {k: r['value'] for k, r in m['effective_parameters'].items()}
    expected_types = {bool:1, int:2, float:3, str:4, type(None):0}
    for name,value in expected_parameters.items():
        typ = expected_types.get(type(value))
        if type(value) is list and value:
            typ = {bool:6,int:7,float:8,str:9}.get(type(value[0]))
        require(name in m['effective_parameters'] and (typ is None or m['effective_parameters'][name]['type'] == typ), 'expected parameter type differs: ' + name)
    changed = [k for k in observed_values.keys() & expected_parameters.keys() if observed_values[k] != expected_parameters[k]]
    require(observed_values == expected_parameters, 'full effective configuration differs: missing=' + str(sorted(expected_parameters.keys()-observed_values.keys())) + ', extra=' + str(sorted(observed_values.keys()-expected_parameters.keys())) + ', changed=' + str(changed))
    for name,value in expected_parameters.items():
        actual_row=m['effective_parameters'][name]
        if actual_row['type'] == 3:
            require(actual_row['canonical_value'] == struct.pack('>d',value).hex(), 'full effective configuration differs: double bits '+name)
        elif actual_row['type'] == 8:
            require(actual_row['canonical_value'] == [struct.pack('>d',v).hex() for v in value], 'full effective configuration differs: double array bits '+name)
    require(set(m.get('parameter_overrides', {})) <= set(expected_parameters), 'unknown parameter override')
    endpoints = m.get('endpoints')
    require(type(endpoints) is list and endpoints, 'actual endpoint population empty')
    keys = set()
    for e in endpoints:
        require(e.get('kind') in ('publisher', 'subscription'), 'endpoint kind invalid')
        require(type(e.get('topic')) is str and e['topic'].startswith('/'), 'endpoint topic invalid')
        require(type(e.get('type')) is str and '/msg/' in e['type'], 'endpoint type invalid')
        gid = e.get('gid')
        require(m.get('gid_storage_size') == 16 and type(gid) is list and len(gid) == 16 and any(gid) and all(type(v) is int and 0 <= v <= 255 for v in gid), 'actual GID malformed')
        key = (e['kind'], e['topic'], tuple(e['gid']))
        require(key not in keys, 'duplicate application endpoint')
        keys.add(key)
    return {'manifest': m, 'sha256': digest(raw), 'actual': actual}

def verify_owned_graph(graph, roles, physical_topics, allowed_driver_node=None):
    require(0 <= time.monotonic_ns() - graph['observed_ns'] <= 1_000_000_000, 'graph observation stale')
    expected = {}
    for role in roles.values():
        m = role['manifest']
        for e in m['endpoints']:
            key = (e['kind'], e['topic'])
            expected.setdefault(key, []).append((m['node'], e['type'], e['gid']))
    for (kind, topic), records in expected.items():
        rows = graph['topics'][topic][kind + 's']
        for name, typ, gid in records:
            match = [r for r in rows if r['node'] == name and r['type'] == typ and r['gid'] == gid]
            require(len(match) == 1, 'exact owned endpoint missing/foreign/ambiguous: ' + topic + ':' + name)
            require(match[0]['type'] == typ and match[0]['gid'] == gid, 'owned endpoint type/GID differs: ' + topic)
        if kind == 'publisher':
            require(len(rows) == len(records), 'foreign publisher present: ' + topic)
        else:
            require(all(any(r['node'] == n and r['type'] == t and r['gid'] == g for n,t,g in records)
                        for r in rows), 'unknown subscription owner: ' + topic)
    for topic in physical_topics:
        rows = graph['topics'][topic]['publishers']
        require(len(rows) == 1 and rows[0]['type'] == 'std_msgs/msg/Float64', 'unique dual physical publisher not proven')
    return True

def source_fd_matches(role, expected_path):
    m, actual = role['manifest'], role['actual']
    f = m.get('source_fd')
    require(type(f) is dict and type(f.get('fd')) is int and f['fd'] >= 0, 'actual source FD missing')
    p = Path('/proc') / str(actual['pid']) / 'fd' / str(f['fd'])
    require(os.readlink(p) == str(expected_path), 'source FD target differs')
    s = p.stat()
    require(stat.S_ISREG(s.st_mode) and s.st_mode == f['mode'], 'source FD not declared regular file')
    require(f.get('path') == str(expected_path), 'source FD declared path differs')
    require(s.st_dev == f['device'] and s.st_ino == f['inode'], 'source FD inode differs')
    flags = int((p.parent.parent / 'fdinfo' / str(f['fd'])).read_text().split('flags:\t')[1].splitlines()[0], 8)
    flags &= ~os.O_CLOEXEC  # fdinfo includes descriptor CLOEXEC; F_GETFL does not.
    require(flags == f['flags'] and bool(flags & os.O_APPEND) == f['append'] and flags & os.O_ACCMODE == f['access_mode'], 'source FD flags differ')
    require(flags & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR), 'source FD not writable')
    return True

def authorize_fixture_release(*, startup, roles, graph, physical_topics,
                              evidence_path, release_path, native_reader_ready_path, native_capability_ready_path, boot, prepare_start_ns,
                              prepare_budget_ns, driver_node):
    require(os.environ.get('RMW_IMPLEMENTATION') == 'rmw_fastrtps_cpp', 'fixture requires pinned FastDDS')
    require(os.environ.get('ROS_LOCALHOST_ONLY') == '1', 'fixture localhost isolation required')
    require(type(prepare_budget_ns) is int and 0 < prepare_budget_ns <= 60_000_000_000, 'finite prepare budget required')
    require(0 <= time.monotonic_ns()-prepare_start_ns <= prepare_budget_ns, 'prepare deadline expired')
    verify_owned_graph(graph, roles, physical_topics, driver_node)
    native_raw=read_regular(native_reader_ready_path)
    native=strict_json(native_raw)
    observer_role=roles['observer']
    om=observer_role['manifest']
    require(native.get('schema') == 'p1-owned-native-reader-ready-v1', 'native reader schema differs')
    for k in ('role','run_id','contract_sha256','boot_id','pid','process_start_ticks'):
        require(native.get(k)==om.get(k), 'native reader identity differs: '+k)
    require(native.get('owned_manifest_sha256')==observer_role['sha256'], 'native reader owned manifest binding differs')
    require(type(native.get('applied_matched_publishers')) is int and native['applied_matched_publishers']==1, 'native Applied match unproven')
    ep=native.get('applied_endpoint')
    require(ep in om['endpoints'] and ep['kind']=='subscription' and ep['topic']=='/research/control/applied' and ep['type']=='usv_research_interfaces/msg/AppliedControl', 'native Applied reader handle differs')
    require(type(native.get('checked_steady_ns')) is int and prepare_start_ns<=native['checked_steady_ns']<=time.monotonic_ns(), 'native reader receipt timestamp differs')

    capability_raw=read_regular(native_capability_ready_path)
    capability=strict_json(capability_raw)
    worker_role=roles['worker'];wm=worker_role['manifest']
    require(capability.get('schema')=='p1-owned-native-capability-ready-v1', 'native capability schema differs')
    for k in ('role','run_id','contract_sha256','boot_id','pid','process_start_ticks'):
        require(capability.get(k)==wm.get(k), 'native capability identity differs: '+k)
    require(capability.get('owned_manifest_sha256')==worker_role['sha256'], 'native capability owned manifest binding differs')
    require(type(capability.get('capability_matched_subscribers')) is int and capability['capability_matched_subscribers']==3, 'native capability receivers unproven')
    ep=capability.get('capability_endpoint')
    require(ep in wm['endpoints'] and ep['kind']=='publisher' and ep['topic']=='/p1/worker_capability' and ep['type']=='usv_research_interfaces/msg/WorkerCapability', 'native capability handle differs')
    require(type(capability.get('checked_steady_ns')) is int and prepare_start_ns<=capability['checked_steady_ns']<=time.monotonic_ns(), 'native capability receipt timestamp differs')
    worker = roles['worker']['manifest']['effective_parameters']
    observer = roles['observer']['manifest']['effective_parameters']
    for p, hooks in ((worker, ('test_delay_ms','test_native_block_ms')),
                     (observer, ('test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms','test_sink_pause_ms'))):
        for name in hooks:
            require(p[name]['type'] == 2 and type(p[name]['value']) is int and p[name]['value'] == 0, 'actual nonzero hook')
    for role in roles.values():
        authenticate_owned(role['actual'], boot)
    role_refs = {name: {'manifest_sha256':r['sha256'], 'owned':r['actual'],
                       'effective_parameters_sha256':r['manifest']['effective_parameters_sha256'],
                       'source_bundle_sha256':r['manifest']['source_bundle_sha256']}
                 for name,r in roles.items()}
    evidence = {'schema_version':'p1-owned-fixture-preparation-v2', 'checked_ns':time.monotonic_ns(),
                'roles':role_refs, 'startup_manifest_sha256':startup['manifest_sha256'], 'graph':graph,
                'native_applied_reader_ready_sha256':digest(native_raw), 'native_applied_reader_matched_verified':True,
                'native_capability_ready_sha256':digest(capability_raw), 'native_capability_receivers_matched_verified':True,
                'owned_dds_endpoint_binding_verified':True,
                'publisher_effective_configuration_verified':True,
                'external_worker_zero_hooks':True, 'subscriptions_verified':True,
                'unique_dual_channel_owner':True, 'fixture_only':True,
                'production_execute_qualified':False, 'legacy_ready':False}
    h = create_only_json(evidence_path, evidence)
    require(time.monotonic_ns()-prepare_start_ns <= prepare_budget_ns, 'prepare deadline expired after evidence IO')
    m = startup['manifest']
    release = {'schema_version':'p1-D1-publisher-release-v1', 'run_id':m['run_id'],
               'producer_instance_id':m['producer_instance_id'],
               'startup_manifest_sha256':startup['manifest_sha256'],
               'release_nonce':secrets.token_hex(16), 'driver_evidence_sha256':h,
               'valid_until_steady_ns':time.monotonic_ns()+3_000_000_000,
               'gates':{'external_worker_zero_hooks':True, 'subscriptions_verified':True,
                        'unique_dual_channel_owner':True}}
    return {'evidence_sha256':h, 'release_sha256':create_only_json(release_path, release), 'release':release}
