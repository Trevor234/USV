#!/usr/bin/env python3
"""Whole-population check for a preregistered C3.7 owned shadow observation.

Read-only input scan. Worker published, recorded and Observer received populations
are independent; a closed Source never makes an all-subscriber delivery claim.
No count of accepted candidates is prescribed. No phase qualification is granted.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import struct
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE/'runtime')]
import check_c36_adapter_run as c36
import check_owned_fixture as base
from check_p1_execution import exact, plain, projection, JOB_FIELDS, JOB_ALIASES, CANDIDATE_FIELDS, CANDIDATE_ALIASES
from owned_auth import parameter_digest
from owned_release import create_only_json
import lease_replay_v1 as lease

SCHEMA = 'p1-C3.7-owned-shadow-observation-run-check-v2'
PROFILE = 'closed_shadow_observation'
FLAGS = c36.QUALIFICATIONS.copy()
UNKNOWNS = {k:v for k,v in c36.UNKNOWNS.items() if k!='Worker_callback_GID_authentication'}
UNKNOWNS.update(Worker_all_published_received='unknown', Worker_endpoint_exit='unknown')
WORKER = {'capability':('/p1/worker_capability','usv_research_interfaces/msg/WorkerCapability'),
          'candidate':('/p1/solve_candidate','usv_research_interfaces/msg/SolveCandidate')}
RAW_FIELDS=set('schema topic message_type callback_sequence entry_steady_ns publisher_gid rmw_implementation source_timestamp received_timestamp publication_sequence_number reception_sequence_number from_intra_process cdr_bytes cdr_sha256 cdr_hex'.split())


def gid(value):
    return type(value) is list and len(value)==16 and all(type(x) is int and 0<=x<=255 for x in value) and any(value)



def worker_fault_permission(manifest,checker):
    """Worker publishes the contract permission; it is not a ROS parameter."""
    cfg=manifest.get('contract_configuration')
    value=cfg.get('fault_injection_enabled') if type(cfg) is dict else None
    checker.need(type(value) is bool,'Worker_fault_permission_exact_contract_boolean')
    return value if type(value) is bool else None


def worker_contract_configuration(inputs,manifest,checker):
    path=Path(inputs['contract']);cfg=c36.load(path)
    digest=c36.sha(path)
    checker.need(digest==inputs.get('contract_sha256')==manifest.get('contract_sha256'),
        'Worker_complete_contract_file_manifest_SHA_binding')
    checker.need(type(cfg) is dict and exact(manifest.get('contract_configuration'),cfg),
        'Worker_complete_actual_contract_configuration_binding')
    parameters=manifest.get('effective_parameters',{})
    checker.need(parameters.get('contract_file',{}).get('value')==str(path)
        and parameters.get('contract_hash',{}).get('value')==digest,
        'Worker_actual_typed_contract_parameter_source_binding')
    return worker_fault_permission(manifest,checker)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def capability_digest(value):
    payload=dict(value)
    payload['prediction_dt']={'ieee754_binary64_be':struct.pack('>d',value['prediction_dt']).hex()}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def worker_publication_population(run,inputs,worker,observer,decoded,manifest,checker,*,decode=None):
    """All Worker source attempts/results plus full typed actual Storage joins."""
    issues_before=len(checker.issues)
    if decode is None:
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.convert import message_to_ordereddict
        from rosidl_runtime_py.utilities import get_message
        decode=lambda blob,typ:plain(dict(message_to_ordereddict(deserialize_message(blob,get_message(typ)))))
    headers=[r for r in worker if r.get('type')=='capability_source_header']
    terminals=[r for r in worker if r.get('type')=='worker_summary']
    checker.need(len(headers)==len(terminals)==1,'Worker_unique_Source_header_and_terminal')
    if len(headers)!=1 or len(terminals)!=1:return {}
    header=headers[0];terminal=terminals[0]
    checker.need(worker[0] is header and worker[-1] is terminal,'Worker_Source_header_terminal_order')
    expected={'schema':'p1-capability-source-header-v1','run_id':manifest['run_id'],
        'boot_id':manifest['boot_id'],'pid':manifest['pid'],
        'process_start_ticks':manifest['process_start_ticks'],'worker_instance':manifest['worker_instance'],
        'contract_hash':manifest['contract_sha256'],'nominal_hash':manifest['nominal_hash'],
        'binary_sha256':inputs['builds']['worker']['binary_sha256'],
        'source_bundle_sha256':inputs['source_bundles']['worker']['sha256'],
        'owned_manifest_sha256':c36.sha(run/'worker/owned_manifest.json'),'clock':'CLOCK_MONOTONIC'}
    checker.need(all(exact(header.get(k),v) for k,v in expected.items()),'Worker_Source_header_full_identity')
    endpoints=[e for e in manifest['endpoints'] if e['kind']=='publisher' and e['topic']==WORKER['capability'][0]]
    checker.need(len(endpoints)==1 and exact(header.get('endpoint'),endpoints[0]),'Worker_Source_header_actual_GID')
    attempts=[r for r in worker if r.get('type')=='capability_publish_attempt']
    results=[r for r in worker if r.get('type')=='capability_publish_result'];count=len(attempts)
    checker.need(count>0 and [r.get('publish_seq') for r in attempts]
        ==[r.get('publish_seq') for r in results]==list(range(1,count+1)),
        'entire_Worker_Capability_publish_attempt_result_sequence')
    indices={id(r):i for i,r in enumerate(worker)};previous_end=0
    for a,r in zip(attempts,results):
        seq=a.get('publish_seq');value=a.get('payload');valid=lease.exact_payload(value)
        checker.need(valid,'Worker_Capability_Source_exact_full19_payload',publish_seq=seq)
        if not valid:continue
        checker.need(a.get('schema')=='p1-capability-publish-attempt-v1'
            and r.get('schema')=='p1-capability-publish-result-v1'
            and a.get('typed_digest_encoding')=='p1-capability-typed-ieee754-v1'
            and a.get('payload_sha256')==r.get('payload_sha256')==capability_digest(value),
            'Worker_Capability_Source_typed_payload_digest',publish_seq=seq)
        checker.need(indices[id(header)]<indices[id(a)]<indices[id(r)]<indices[id(terminal)],
            'Worker_Capability_Source_attempt_result_record_order',publish_seq=seq)
        times=[a.get('snapshot_ns'),a.get('attempt_record_ns'),r.get('publish_start_ns'),r.get('publish_end_ns')]
        checker.need(all(c36.integer(x,1) for x in times) and previous_end<=times[0]
            and times==sorted(times) and r.get('returned') is True and r.get('threw') is False,
            'Worker_Capability_Source_call_time_order',publish_seq=seq)
        if c36.integer(r.get('publish_end_ns'),1):previous_end=r['publish_end_ns']
        cdr=a.get('cdr',{});text=cdr.get('hex')
        if not isinstance(text,str) or len(text)>2*c36.MAX_CALLBACK_CDR:
            checker.need(False,'Worker_Capability_Source_CDR_domain',publish_seq=seq);continue
        try:
            blob=bytes.fromhex(text)
            checker.need(0<len(blob)<=c36.MAX_CALLBACK_CDR and len(blob)==cdr.get('bytes')
                and hashlib.sha256(blob).hexdigest()==cdr.get('sha256')
                and cdr.get('representation')=='typed_reserialization_cdr'
                and exact(decode(blob,WORKER['capability'][1]),value),
                'Worker_Capability_Source_complete_CDR_full19_binding',publish_seq=seq)
        except Exception as error:
            checker.need(False,'Worker_Capability_Source_CDR_decode',publish_seq=seq,error=repr(error))
        normal={'run_id':manifest['run_id'],'boot_id':manifest['boot_id'],
            'contract_hash':manifest['contract_sha256'],'nominal_hash':manifest['nominal_hash'],
            'worker_instance':manifest['worker_instance'],'pid':manifest['pid'],'startup_ns':header['startup_ns'],
            'schema_version':'p1-worker-capability-v1','clock_name':'CLOCK_MONOTONIC','backend':'acados',
            'matrix_layout':'column_major','horizon_steps':20,'prediction_dt':.2,'fatal':False,'reason':'',
            'fault_injection_enabled':worker_fault_permission(manifest,checker)}
        checker.need(all(exact(value.get(k),v) for k,v in normal.items()),
            'Worker_Capability_Source_normal_pinned_contract',publish_seq=seq)
    recorded=[r['message'] for r in decoded.get(WORKER['capability'][0],[])]
    checker.need(len(recorded)==count and all(exact(a.get('payload'),m) for a,m in zip(attempts,recorded)),
        'entire_Worker_Capability_Source_Storage_population',published=count,recorded=len(recorded))
    counters={'schema':'p1-capability-source-terminal-v1','capability_generated':count,
        'capability_attempt_records':count,'capability_publish_calls':count,'capability_publish_returned':count,
        'capability_publish_threw':0,'capability_result_records':count,'capability_aborted_before_publish':0,
        'capability_source_io_failed':False,'capability_last_publish_seq':count,
        'capability_last_payload_sha256':attempts[-1]['payload_sha256'] if attempts else '',
        'capability_last_publish_end_ns':results[-1]['publish_end_ns'] if results else 0,
        'capability_source_complete':True}
    checker.need(exact(terminal.get('capability_source'),counters)
        and c36.integer(terminal.get('finished_ns'),1) and terminal['finished_ns']>=previous_end
        and terminal.get('source_rows_before_terminal')==terminal.get('source_rows_emitted_before_terminal')==len(worker)-1
        and terminal.get('source_io_failed') is False and terminal.get('normal_source_complete') is True,
        'entire_Worker_Source_terminal_count_conservation')
    jobs=checker.index([r for r in observer if r.get('type')=='job'],lambda r:r['job']['job_id'],'Source_submit_job')
    received=checker.index([r for r in worker if r.get('type')=='job_received'],lambda r:r['job']['job_id'],'Worker_received_job')
    candidates=checker.index([r for r in worker if r.get('type')=='candidate'],lambda r:r['job']['job_id'],'Worker_source_candidate')
    published=checker.index([r for r in worker if r.get('type')=='candidate_publish_result'],lambda r:r['job_id'],'Worker_candidate_publish_result')
    checker.need(set(jobs)==set(received)==set(candidates)==set(published),'whole_Worker_Job_Candidate_call_population')
    for jid,row in received.items():
        j=jobs.get(jid,{});cand=candidates.get(jid,{});pub=published.get(jid,{})
        checker.need(exact(projection(row['job'],JOB_FIELDS,JOB_ALIASES),projection(j.get('job',{}),JOB_FIELDS,JOB_ALIASES))
            and exact(projection(cand.get('job',{}),JOB_FIELDS,JOB_ALIASES),projection(row['job'],JOB_FIELDS,JOB_ALIASES)),
            'full_Job_immutable_Source_Worker_Candidate_echo',job_id=jid)
        checker.need(row['receive_ns']<=row['commit_ns']<=cand.get('solve_start_ns',0)
            <=cand.get('solve_end_ns',0)<=pub.get('publish_start_ns',0)<=pub.get('publish_end_ns',0)
            <=terminal['finished_ns'] and pub.get('worker_instance')==manifest['worker_instance']
            and pub.get('success') is True and pub.get('solve_start_ns')==cand.get('solve_start_ns')
            and pub.get('solve_end_ns')==cand.get('solve_end_ns'),
            'Worker_Candidate_actual_solve_and_publish_result_time',job_id=jid)
    return {'passed':len(checker.issues)==issues_before,'capability_published':count,'capability_recorded':len(recorded),
        'jobs_received':len(received),'candidates_published':len(published),
        'Worker_Source_finished_ns':terminal['finished_ns'],'all_subscriber_delivery_proven':False}


def decode_callback(raw,checker,label):
    """Typed received reserialization. Network padding and send freshness unclaimed."""
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message
    if not isinstance(raw,dict):
        checker.need(False,'worker_callback_full_raw_missing',label=label); return None
    text=raw.get('cdr_hex')
    if not isinstance(text,str) or len(text)>2*c36.MAX_CALLBACK_CDR:
        checker.need(False,'worker_callback_CDR_domain',label=label); return None
    try:
        blob=bytes.fromhex(text)
        checker.need(0<len(blob)<=c36.MAX_CALLBACK_CDR and raw.get('cdr_bytes')==len(blob)
            and raw.get('cdr_sha256')==hashlib.sha256(blob).hexdigest(),
            'worker_callback_complete_CDR_sha',label=label)
        return plain(dict(message_to_ordereddict(deserialize_message(blob,get_message(raw['message_type'])))))
    except Exception as error:
        checker.need(False,'worker_callback_CDR_decode',label=label,error=repr(error)); return None


def worker_population(observer,decoded,worker_manifest,peer,checker,*,decode=None):
    """Independent complete received population, subset matching to actual Storage."""
    if decode is None: decode=lambda raw,label:decode_callback(raw,checker,label)
    callbacks=[r for r in observer if r.get('type')=='adapter_worker_callback']
    summaries=[r for r in observer if r.get('type')=='source_summary']
    close=summaries[0].get('finished_ns') if len(summaries)==1 else None
    checker.need(c36.integer(close,1),'worker_reception_window_closed_Source')
    closures=[r for r in observer if r.get('type')=='adapter_worker_reception_closed']
    checker.need(len(closures)==1,'Worker_reception_terminal_event_once')
    receiver=closures[0] if len(closures)==1 else {}
    receiver_ns=receiver.get('closed_ns')
    checker.need(receiver.get('schema')=='p1-C3.7-worker-reception-close-v1'
        and receiver.get('executor_detached') is True and receiver.get('tick_joined') is True
        and receiver.get('prep_joined') is True and c36.integer(receiver_ns,1)
        and c36.integer(close,1) and receiver_ns<=close
        and type(receiver.get('worker_process_alive')) is bool
        and receiver.get('all_Worker_publications_received') is None
        and receiver.get('worker_endpoints_exited')=='unknown',
        'Worker_actual_receiver_lifecycle_close_facts')
    endpoint={}
    for kind,(topic,typ) in WORKER.items():
        rows=[e for e in worker_manifest['endpoints'] if e.get('kind')=='publisher'
              and e.get('topic')==topic and e.get('type')==typ]
        checker.need(len(rows)==1,'unique_Worker_manifest_endpoint',interface=kind)
        endpoint[kind]=rows[0] if len(rows)==1 else {}
    report={}; raw_by_interface={}; matched_all={}; events_by_interface={}
    for kind,(topic,typ) in WORKER.items():
        received=[r for r in callbacks if r.get('interface')==kind]
        events_by_interface[kind]={r.get('callback_sequence'):r for r in received}
        checker.need(bool(received),'Worker_actual_received_nonempty',interface=kind)
        checker.need([r.get('callback_sequence') for r in received]==list(range(1,len(received)+1))
            and [r.get('received_count') for r in received]==list(range(1,len(received)+1)),
            'entire_Worker_callback_sequence_and_count',interface=kind)
        checker.need(type(receiver.get(kind+'_received')) is int
            and type(receiver.get(kind+'_callback_sequence')) is int
            and receiver.get(kind+'_received')==receiver.get(kind+'_callback_sequence')==len(received),
            'Worker_native_receiver_terminal_counter_conservation',interface=kind)
        # The wire lacks a per-Capability packet identity. Match exact full typed
        # occurrences and report unmatched storage, preserving duplicate payloads.
        recorded=[r['message'] for r in decoded.get(topic,[])]
        storage_count=Counter(canonical(m) for m in recorded)
        seen=Counter(); match_indices=[]; used=set(); raw_by_interface[kind]={}
        last_entry=0
        for r in received:
            seq=r.get('callback_sequence'); label={'interface':kind,'callback_sequence':seq}
            raw=r.get('raw_input'); auth=r.get('authentication_reason')
            checker.need(c36.integer(r.get('entry_ns'),1)
                and c36.integer(r.get('authentication_checked_ns'),1)
                and c36.integer(r.get('processed_ns'),1)
                and c36.integer(receiver_ns,1)
                and last_entry<=r['entry_ns']<=r['authentication_checked_ns']<=r['processed_ns']<=receiver_ns<=close,
                'Worker_callback_finite_observation_time_order',**label)
            if c36.integer(r.get('entry_ns'),1):last_entry=r['entry_ns']
            checker.need(gid(r.get('actual_gid')) and gid(r.get('expected_gid'))
                and r.get('actual_gid')==endpoint[kind].get('gid')
                and r.get('expected_gid')==endpoint[kind].get('gid'),
                'Worker_callback_actual_owned_GID',**label)
            checker.need(r.get('resource_valid') is True and r.get('resource_reason')==''
                and auth=='' and r.get('worker_process_alive_at_guard') is True
                and type(r.get('later_worker_process_alive')) is bool
                and r.get('full_cdr_serialized') is True and r.get('semantic_callback_invoked') is True
                and r.get('callback_completed_ns')==r.get('processed_ns'),
                'normal_Worker_callback_resource_and_identity_guard',**label)
            for phase in ('before','after'):
                state=r.get(phase,{})
                checker.need(type(state) is dict and set(state)=={'worker_instance','worker_valid',
                    'worker_unusable','lease_last_valid_ns','candidate_present','admission_slots'}
                    and type(state.get('worker_instance')) is str
                    and all(type(state.get(k)) is bool for k in ('worker_valid','worker_unusable','candidate_present'))
                    and c36.integer(state.get('lease_last_valid_ns'))
                    and c36.integer(state.get('admission_slots')) and state.get('admission_slots',2)<=1,
                    'Worker_callback_actual_snapshot_typed',phase=phase,**label)
            if not isinstance(raw,dict):
                checker.need(False,'normal_Worker_callback_raw_present',**label);continue
            checker.need(set(raw)==RAW_FIELDS and raw.get('schema')=='p1-input-callback-full-cdr-v1'
                and raw.get('topic')==topic and raw.get('message_type')==typ
                and raw.get('callback_sequence')==seq
                and raw.get('publisher_gid')==endpoint[kind].get('gid')
                and raw.get('rmw_implementation')=='rmw_fastrtps_cpp'
                and raw.get('from_intra_process') is False
                and c36.integer(raw.get('entry_steady_ns'),1)
                and r['authentication_checked_ns']<=raw['entry_steady_ns']<=r['processed_ns'],
                'Worker_callback_actual_typed_interface',**label)
            m=decode(raw,label)
            if m is None:continue
            checker.need(type(m) is dict and ((kind=='capability' and lease.exact_payload(m))
                or (kind=='candidate' and set(m)==set(CANDIDATE_FIELDS)|{'job'}
                    and type(m.get('job')) is dict and set(m['job'])==set(JOB_FIELDS))),
                'Worker_callback_complete_typed_payload_field_domain',**label)
            raw_by_interface[kind][seq]=m
            key=canonical(m);seen[key]+=1
            checker.need(seen[key]<=storage_count[key],
                'every_received_Worker_full_typed_occurrence_in_Storage',**label)
            index=next((i for i,x in enumerate(recorded) if i not in used and exact(x,m)),None)
            if index is not None:used.add(index);match_indices.append(index)
            checker.need(all(exact(m.get(k),v) for k,v in {
                'worker_instance':worker_manifest['worker_instance']}.items()),
                'Worker_callback_bound_worker_instance',**label)
            if kind=='capability':
                checker.need(all(exact(m.get(k),v) for k,v in {'run_id':worker_manifest['run_id'],
                    'boot_id':worker_manifest['boot_id'],'contract_hash':worker_manifest['contract_sha256'],
                    'nominal_hash':worker_manifest['nominal_hash'],'pid':worker_manifest['pid']}.items()),
                    'Worker_callback_complete_capability_role_identity',**label)
        checker.need(all(seen[key]<=n for key,n in storage_count.items()),
            'Worker_received_population_is_Storage_occurrence_subset',interface=kind)
        missing=[{'storage_ordinal':i+1,'payload_sha256':hashlib.sha256(canonical(m).encode()).hexdigest(),
                   'job_id':m.get('job',{}).get('job_id'),'completed_jobs':m.get('completed_jobs'),
                   'active_job':m.get('active_job'),'reason':m.get('reason')}
                 for i,m in enumerate(recorded) if i not in used]
        report[kind]={'recorded':len(recorded),'received':len(received),'matched':len(used),
            'recorded_not_observed':missing,'complete_received_population':len(raw_by_interface[kind])==len(received),
            'all_recorded_received':len(used)==len(recorded),
            'packet_identity_available':kind=='candidate','expected_owned_gid':endpoint[kind].get('gid'),
            'occurrence_assignment_semantics':('exact unique Job identity' if kind=='candidate' else
                'full typed payload occurrence subset; identical Capability occurrences interchangeable; greedy storage ordinals are not unique packet identities'),
            'reception_window_close_monotonic_ns':receiver_ns,
            'Source_flush_complete_monotonic_ns':close}
        matched_all[kind]=set(raw_by_interface[kind])
    checker.need(all(r.get('interface') in WORKER for r in callbacks),'Worker_callback_known_interfaces')
    if len(closures)==1:
        closure_index=observer.index(closures[0])
        checker.need(all(observer.index(r)<closure_index for r in callbacks),
            'Worker_received_callback_events_before_native_receiver_close')
    # Normal owned profile only: every admitted callback has one semantic receipt.
    for kind,event in (('capability','capability_admission'),('candidate','candidate_registration')):
        semantic=[r for r in observer if r.get('type')==event]
        semantic_map=checker.index(semantic,lambda r:r.get('callback_sequence'),'Worker_'+event)
        checker.need(set(semantic_map)==matched_all[kind],
            'entire_Worker_received_semantic_receipt_population',interface=kind)
        for seq,row in semantic_map.items():
            checker.need(row.get('received_count')==seq,'Worker_semantic_received_count',interface=kind,callback_sequence=seq)
            callback=events_by_interface[kind].get(seq,{})
            checker.need(exact(row.get('raw_input'),callback.get('raw_input')),
                'Worker_semantic_exact_callback_raw_observation',interface=kind,callback_sequence=seq)
            m=raw_by_interface[kind].get(seq)
            if m is None:continue
            if kind=='capability':
                checker.need(exact(row.get('capability'),m),'Worker_semantic_full_capability_binding',callback_sequence=seq)
            else:
                checker.need(exact(projection(row.get('job',{}),JOB_FIELDS,JOB_ALIASES),
                                   projection(m.get('job',{}),JOB_FIELDS,{}))
                    and exact(row.get('first_control'),m.get('first_control')),
                    'Worker_semantic_full_candidate_Job_and_control_binding',callback_sequence=seq)
    checker.need(not any(r.get('type') in ('adapter_worker_auth_rejected','adapter_worker_resource_rejected')
                for r in observer),'normal_Worker_no_auth_or_resource_rejections')
    return report,raw_by_interface


def worker_binding(run,inputs,manifests,peer,checker):
    pins=peer.get('worker_peer',{})
    wm=manifests['worker'];om=manifests['observer']
    pinmap={'manifest_path':str(run/'worker/owned_manifest.json'),
        'manifest_sha256':c36.sha(run/'worker/owned_manifest.json'),'run_id':wm['run_id'],
        'boot_id':wm['boot_id'],'contract_sha256':wm['contract_sha256'],
        'worker_instance':wm['worker_instance'],'nominal_hash':wm['nominal_hash'],
        'exe':wm['exe'],'binary_sha256':wm['binary_sha256'],
        'source_bundle_sha256':wm['source_bundle_sha256'],
        'effective_parameters_sha256':wm['effective_parameters_sha256'],
        'pid':wm['pid'],'process_start_ticks':wm['process_start_ticks'],
        'capability_topic':WORKER['capability'][0],'capability_type':WORKER['capability'][1],
        'candidate_topic':WORKER['candidate'][0],'candidate_type':WORKER['candidate'][1]}
    checker.need(set(pins)==set(pinmap) and all(exact(pins.get(k),v) for k,v in pinmap.items()),
        'complete_Worker_peer_manifest_process_source_binary_config_pins')
    evidence=om.get('worker_peer_binding',{})
    checker.need(evidence.get('schema')=='p1-owned-worker-peer-C3_7-v1'
        and all(exact(evidence.get(k),v) for k,v in pinmap.items()
                if k not in ('capability_topic','capability_type','candidate_topic','candidate_type'))
        and evidence.get('pidfd_alive_at_evidence_call') is True
        and evidence.get('callback_policy')=='interface_specific_exact_DataWriter_GID_and_zero_wait_pidfd'
        and evidence.get('continuous_DDS_uniqueness')=='unknown'
        and evidence.get('post_pin_exec_continuity')=='unknown'
        and evidence.get('stage_qualified') is False and evidence.get('execute_qualified') is False
        and evidence.get('physical_release_qualified') is False,
        'actual_Observer_Worker_peer_pin_evidence')
    for kind,(topic,typ) in WORKER.items():
        endpoints=[e for e in wm['endpoints'] if e['kind']=='publisher' and e['topic']==topic and e['type']==typ]
        expected=endpoints[0] if len(endpoints)==1 else None
        checker.need(exact(evidence.get('endpoints',{}).get(kind),expected),
            'actual_Observer_Worker_peer_endpoint_evidence',interface=kind)
    return pinmap


def configurations(run,inputs,result,manifests,checker):
    for role,m in manifests.items():
        checker.need(m.get('effective_parameters_digest_encoding')=='p1-typed-ieee754-v1'
            and m.get('effective_parameters_immutable') is True
            and parameter_digest(m['effective_parameters'])==m['effective_parameters_sha256']
            and exact({k:v['value'] for k,v in m['effective_parameters'].items()},inputs['expected_parameters'][role]),
            'full_effective_configuration_source',role=role)
        checker.need(m.get('execute_qualified') is False and m.get('physical_release_qualified') is False,
            'owned_role_no_phase_qualification',role=role)
        if role!='recorder':
            query=c36.load(run/('live_parameters_'+role+'.json'))
            checker.need(exact(query,m['effective_parameters'])
                and result.get('live_parameter_queries',{}).get(role,{}).get('complete_name_set') is True
                and result.get('live_parameter_queries',{}).get(role,{}).get('mutation_rejected') is True,
                'external_full_live_configuration_receipt',role=role)


def asset_pins(inputs,checker):
    out={}
    for role,record in inputs['source_bundles'].items():
        path=Path(record['path']);out[str(path)]=c36.sha(path)
        checker.need(out[str(path)]==record['sha256'],'author_source_bundle_current_pin',role=role)
        for item in c36.load(path)['files'].values():
            p=Path(item['path']);out[str(p)]=c36.sha(p)
            checker.need(out[str(p)]==item['sha256'],'author_source_file_current_pin',role=role,path=str(p))
    for role,b in inputs['builds'].items():
        path=Path(b['binary']);out[str(path)]=c36.sha(path)
        checker.need(out[str(path)]==b['binary_sha256'],'role_binary_current_pin',role=role)
    return out


def witness_source_population(witness,expected_header,observer,checker):
    issues_before=len(checker.issues)
    from check_p1_witness_v2 import analyze as witness_analyze
    basis=witness_analyze(witness,expected_header,profile=PROFILE)
    checker.need(basis.get('passed') is True,'new_Witness_v2_integrity_profile_passed',issues=basis.get('issues'))
    versions=('task_generation','model_generation','config_generation','schedule_generation')
    get=lambda kind:[r for r in observer if r.get('type')==kind]
    decisions=checker.index(get('decision'),lambda r:(r['schedule_generation'],r['tick']),'Source_Witness_decision')
    ticks=checker.index(witness.get('tick',[]),lambda r:(r['schedule_generation'],r['tick']),'Witness_Source_tick')
    checker.need(set(decisions)==set(ticks),'entire_Source_Witness_tick_identity_sets')
    for key in decisions.keys() & ticks.keys():
        d=decisions[key];r=ticks[key]
        wanted={'sequence':d['sequence'],'job_id':d['job_id'],'tick':d['tick'],
            'target_tick':d['tick'] if d['job_id'] else 0,'clock_epoch':d['epoch'],
            'planned_ns':d['planned_ns'],'start_ns':d['start_ns'],'skipped_ticks':d['skipped_ticks'],
            'candidate_present':d['job_id']>0,**{k:d[k] for k in versions}}
        checker.need(all(exact(r.get(k),v) for k,v in wanted.items()) and d['end_ns']<=r['end_ns'],
            'entire_Source_Witness_tick_full_payload_binding',identity=key)
    jobs=checker.index(get('job'),lambda r:r['job']['job_id'],'Source_Witness_job')
    submits=checker.index(witness.get('submit',[]),lambda r:r['job_id'],'Witness_Source_submit')
    checker.need(set(jobs)==set(submits),'entire_Source_Witness_submit_identity_sets')
    for jid in jobs.keys() & submits.keys():
        e=jobs[jid];j=e['job'];r=submits[jid]
        checker.need(all(exact(r.get(k),j[k]) for k in ('job_id','target_tick','clock_epoch',*versions))
            and r['tick']==j['target_tick']-1 and r['commit_ns']==e['submit_commit_ns']<=e['publish_start_ns'],
            'entire_Source_Witness_submit_exact_completion_binding',job_id=jid)
    attempts=checker.index([d for d in decisions.values() if d['job_id']],lambda r:r['job_id'],'Source_Witness_attempt')
    activations=checker.index(witness.get('activation',[]),lambda r:r['job_id'],'Witness_Source_activation')
    registrations=checker.index(get('candidate_registration'),lambda r:r['job']['job_id'],'Source_Witness_registration')
    checker.need(set(attempts)==set(activations),'entire_Source_Witness_activation_identity_sets')
    for jid in attempts.keys() & activations.keys():
        d=attempts[jid];r=activations[jid];reg=registrations.get(jid)
        wanted={'job_id':jid,'tick':d['tick'],'target_tick':d['tick'],'clock_epoch':d['epoch'],
            'commit_ns':d['activation_commit_ns'],'ready_commit_ns':d['ready_commit_ns'],
            'accepted':d['accepted'],**{k:d[k] for k in versions}}
        wanted['reason_code']=0 if d['accepted'] else 1 if d['reason']=='shutdown' else 2 if d['reason']=='run_unusable_at_commit' else 3
        checker.need(all(exact(r.get(k),v) for k,v in wanted.items())
            and reg is not None and reg.get('accepted_registration') is True
            and reg.get('ready_commit_ns')==d['ready_commit_ns'],
            'entire_Source_Witness_activation_exact_final_ready_binding',job_id=jid)
    accepted=[d for d in decisions.values() if d.get('accepted') is True]
    ready=[r for r in witness.get('phase',[]) if r.get('event_code')==9]
    ready_bound=False
    if accepted:
        first=min(accepted,key=lambda r:r['activation_commit_ns'])
        ready_bound=len(ready)==1 and ready[0].get('observation_code')==2 \
            and ready[0].get('ns')==first['activation_commit_ns'] and ready[0].get('tick')==first['tick']
        ready_bound=ready_bound and ready[0].get('job_id')==first['job_id'] if ready_bound else False
        checker.need(ready_bound,'Source_first_real_accepted_BusinessReady_exact_binding')
    else:
        checker.need(ready==[] and witness.get('business_ready_observed') is False
            and basis.get('business_ready_observed') is False and basis.get('normal_business') is False,
            'all_rejected_population_has_no_BusinessReady_or_normal_business')
    summaries=get('source_summary');closes=[r for r in witness.get('phase',[]) if r.get('event_code')==7]
    checker.need(len(summaries)==1 and observer[-1] is summaries[0] and len(closes)==1
        and closes[0]['ns']>=summaries[0]['finished_ns'],'Witness_close_after_all_Source_flush')
    complete=len(checker.issues)==issues_before
    return {'passed':complete,'basis':basis,'profile':PROFILE,'counts':{'decisions':len(decisions),'ticks':len(ticks),
        'jobs':len(jobs),'submits':len(submits),'attempts':len(attempts),'activations':len(activations)},
        'business_ready_source_bound':ready_bound,'normal_business_contract_qualified':False,
        'whole_population_source_join':complete,'window_clipped':False,
        'unlogged_phase_callback_fact_scope':'phase POD integrity; accepted BusinessReady and terminal Close additionally bound to Source'}


def analyze(run):
    run=Path(run).resolve();c=c36.Checks()
    inputs=c36.load(run/'inputs.json');result=c36.load(run/'result.json')
    ci=c36.load(run/'checker_inputs.json')
    required={'bag','topics_file','transport_source','synthetic_terminal','publisher_session',
        'startup_manifest','observer_source','worker_source','witness','expected_witness_header','owned_manifests'}
    c.need(required<=set(ci),'complete_checker_input_declarations')
    declarations={'bag':'recorder/bag','topics_file':'topics.json',
        'transport_source':'synthetic_source/transport_source.jsonl','synthetic_terminal':'synthetic_source/terminal.json',
        'publisher_session':'publisher/session_summary.json','startup_manifest':'publisher/startup_manifest.json',
        'observer_source':'observer/source.jsonl','worker_source':'worker/source.jsonl',
        'witness':'observer/witness.json','expected_witness_header':'expected_witness_header.json'}
    c.need(all(Path(ci[k]).resolve()==run/v for k,v in declarations.items()),'declared_checker_inputs_are_current_run')
    c.need(set(ci['owned_manifests'])==c36.ROLES and all(Path(p).resolve()==run/role/'owned_manifest.json'
        for role,p in ci['owned_manifests'].items()),'complete_owned_current_run_manifest_set')
    allfiles=[p for p in run.rglob('*') if p.is_file() and p.name!='check_c37_owned_run.json']
    before={str(p):c36.sha(p) for p in allfiles}
    manifests={k:c36.load(v) for k,v in ci['owned_manifests'].items()}
    peer=c36.load(run/'adapter_peer_pins.json');pub=manifests['publisher'];om=manifests['observer'];wm=manifests['worker']
    observer=c36.lines(ci['observer_source']);worker=c36.lines(ci['worker_source'])
    topics=c36.load(ci['topics_file'])['topics']
    decoded,raw_rows,storage=base.read_actual_storage(ci['bag'],topics)
    transport=base.transport_join(raw_rows,c36.lines(ci['transport_source']),manifests,topics)
    source=base.source_typed_join(observer,worker,decoded)
    publisher=base.publisher_join(c36.load(ci['publisher_session']),decoded,c36.load(ci['startup_manifest']),pub)
    for name,r in (('transport_storage',transport),('source_typed_storage',source),('publisher_session',publisher)):
        c.need(r.get('passed') is True,name+'_passed',issues=r.get('issues'))
    c.need(result.get('passed') is True and result.get('released') is True
        and inputs.get('mode')=='positive' and inputs.get('measurement_seconds')==4
        and inputs.get('witness_validation_profile')==PROFILE
        and inputs.get('close_policy')=='publisher-first' and result.get('cleanup_complete') is True
        and result.get('cleanup_within_budget') is True and result.get('evidence_qualification_clean') is True
        and result.get('close_errors')==[] and result.get('ledger_failed') is False
        and set(result.get('cleanup',{}))==c36.ROLES
        and all(x.get('cleanup_complete') is True and x.get('qualification_clean') is True
            and x.get('remaining_members')==[] for x in result['cleanup'].values())
        and result.get('owned_role_returncodes')=={r:0 for r in c36.ROLES},
        'bounded_owned_shadow_driver_complete_and_clean')
    params=om['effective_parameters']
    c.need(params['mode']['value']=='shadow'
        and params['adapter_peer_pins_file']['value']==str(run/'adapter_peer_pins.json')
        and params['adapter_peer_pins_sha256']['value']==c36.sha(run/'adapter_peer_pins.json')
        and params['adapter_driver_close_file']['value']==str(run/'adapter_driver_close_request.json')
        and om.get('adapter_pins_sha256')==c36.sha(run/'adapter_peer_pins.json'),
        'effective_Observer_current_peer_configuration')
    c.need(peer['publisher_peer'].get('manifest_sha256')==c36.sha(run/'publisher/owned_manifest.json')
        and all(exact(peer['publisher_peer'].get(k),pub[v]) for k,v in {
            'pid':'pid','process_start_ticks':'process_start_ticks','binary_sha256':'binary_sha256',
            'effective_parameters_sha256':'effective_parameters_sha256','source_bundle_sha256':'source_bundle_sha256'}.items()),
        'Applied_owner_manifest_process_source_binary_config_pins')
    worker_binding(run,inputs,manifests,peer,c)
    worker_contract_configuration(inputs,wm,c)
    configurations(run,inputs,result,manifests,c)
    close=c36.close_population(run,inputs,result,peer,observer,pub,c)
    applied=c36.callback_population(observer,decoded.get(c36.APPLIED,[]),pub,close,c)
    component=c36.component_population(observer,close,c)
    business=c36.business_population(observer,worker,close,om['contract_configuration'],c)
    worker_receipts,raw_worker=worker_population(observer,decoded,wm,peer,c)
    worker_publications=worker_publication_population(run,inputs,worker,observer,decoded,wm,c)
    ledger=c36.lines(run/'owned_process_ledger.jsonl')
    signals=[r for r in ledger if r.get('type')=='signal' and r.get('name')=='worker']
    receiver=[r for r in observer if r.get('type')=='adapter_worker_reception_closed']
    summaries=[r for r in observer if r.get('type')=='source_summary']
    c.need(len(signals)==len(receiver)==len(summaries)==1
        and signals[0].get('signal')==2 and signals[0].get('boot_id')==wm['boot_id']
        and receiver[0]['closed_ns']<=summaries[0]['finished_ns']<=signals[0]['monotonic_ns'],
        'actual_Worker_stop_after_Observer_receiver_close_and_Source_flush')
    expected={k:wm[k] for k in ('run_id','boot_id')}
    expected.update(contract_hash=wm['contract_sha256'],nominal_hash=wm['nominal_hash'],pid=wm['pid'],
        fault_injection_enabled=worker_fault_permission(wm,c))
    lease_result=lease.replay(observer,expected,om['contract_configuration']['worker_capability_receipt_timeout_ns'],
        c.need,decode_raw=lambda raw,index:raw_worker['capability'].get(raw['callback_sequence']),require_observation=True)
    # New production/profile checker; the old v1 expected/normal gate is untouched.
    witness=witness_source_population(c36.load(ci['witness']),c36.load(ci['expected_witness_header']),observer,c)
    physical={pub['effective_parameters'][n]['value'] for n in ('vrx_left_thrust_topic','vrx_right_thrust_topic')}
    c.need(om.get('physical_publisher_endpoints')==0
        and not any(e['kind']=='publisher' and e['topic'] in physical for e in om['endpoints']),
        'Observer_has_no_physical_publisher_endpoint')
    recorder=c36.load(run/'recorder/terminal.json')
    c.need(recorder.get('clean') is True and recorder.get('prepared') is True
        and recorder.get('Recorder_stop_completed') is True and recorder.get('metadata_exists') is True
        and recorder.get('metadata_sha256')==c36.sha(run/'recorder/bag/metadata.yaml')
        and recorder.get('storage_id')=='sqlite3'
        and recorder.get('manifest_sha256')==c36.sha(run/'recorder/owned_manifest.json'),
        'actual_SQLite_recorder_terminal')
    terminal=c36.load(ci['synthetic_terminal'])
    c.need(terminal.get('normal_end') is True and terminal.get('failed') is False
        and terminal.get('run_id')==inputs['run_id'] and terminal.get('transport_counts')==transport['counts']
        and terminal.get('transport_total')==sum(transport['counts'].values())
        and all(storage['actual_counts'].get(topic)==count for topic,count in terminal.get('published_counts',{}).items()
            if topic in topics),'synthetic_terminal_entire_population_counts')
    pins=asset_pins(inputs,c)
    after={str(p):c36.sha(p) for p in allfiles}
    c.need(before==after,'entire_run_inputs_unchanged')
    c.need(all(c36.sha(p)==value for p,value in pins.items()),'author_assets_unchanged_during_check')
    deps=[HERE/'check_c36_adapter_run.py',HERE/'check_owned_fixture.py',HERE/'runtime/check_p1_execution.py',
        HERE/'runtime/check_p1_witness_v2.py',HERE/'lease_replay_v1.py',HERE/'owned_auth.py',HERE/'owned_release.py']
    for path in [Path(__file__),*deps]:
        rel=str(path.relative_to(HERE));snapshot=run/(rel.replace('/','__')+'.snapshot')
        c.need(snapshot.is_file() and c36.sha(snapshot)==c36.sha(path)
            and inputs.get('tool_sha256',{}).get(rel)==c36.sha(path),
            'executed_checker_dependency_matches_prerun_snapshot',tool=rel)
    return c.result(schema=SCHEMA,profile=PROFILE,run_dir=str(run),run_id=inputs['run_id'],qualifications=FLAGS,
        unknowns=UNKNOWNS,storage=storage,transport_storage=transport,source_typed_storage=source,
        publisher_session=publisher,applied_callbacks=applied,worker_callbacks=worker_receipts,
        worker_publications=worker_publications,
        component=component,business=business,witness_v2=witness,
        capability_receipt_lease={'callbacks':lease_result['callbacks'],'final':lease_result['final'],
            'source_packet_freshness_available':False,'solve_progress_proven_by_lease':False},
        input_sha256_before=before,input_sha256_after=after,author_asset_sha256=pins,
        checker_dependencies={str(p):c36.sha(p) for p in deps},complete_population_window_clipped=False,
        callback_authentication_scope='Applied, WorkerCapability and SolveCandidate exact DataWriter GID and zero-wait pidfd',
        source_closed_implies_all_Worker_publications_received=False,
        accepted_count_is_preregistered=False,normal_business_contract_qualified=False,
        regulatory_physical_publication=False,Applied_runtime_partial_failure_adapter_verified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try: report=analyze(args.run_dir)
    except Exception as error:
        report={'schema':SCHEMA,'profile':PROFILE,'passed':False,'run_dir':str(args.run_dir.resolve()),
            'reader_error':type(error).__name__+': '+str(error),'qualifications':FLAGS,'unknowns':UNKNOWNS}
    report['checker_sha256']=c36.sha(__file__)
    if args.output:create_only_json(args.output,report)
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False))
    return 0 if report['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
