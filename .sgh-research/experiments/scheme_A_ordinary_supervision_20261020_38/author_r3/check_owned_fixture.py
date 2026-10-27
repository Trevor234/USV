"""Actual storage/transport/source/Witness joins for a bounded owned fixture.

This checker supplements the inherited components. It does not replace the
missing shared v2 readiness validator or confer any D1/execute qualification.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'runtime'))
from check_p1_execution import (JOB_FIELDS, JOB_ALIASES, CANDIDATE_FIELDS,
    CANDIDATE_ALIASES, DECISION_V2_FIELDS, DECISION_ALIASES, exact, plain, projection)
from check_p1_witness import analyze as analyze_witness
from owned_release import create_only_json

MAX_ROWS = 20000
MAX_INPUT_BYTES = 128 * 1024 * 1024
VERSIONS = ('task_generation', 'model_generation', 'config_generation', 'schedule_generation')
PUBLISHER_STREAMS = {'state': '/research/state_snapshot', 'applied': '/research/control/applied',
                     'cycle': '/research/cycle_timing', 'reference_prediction': '/research/reference_prediction'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('input exceeds finite byte budget')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def load_jsonl(path):
    raw = Path(path).read_bytes()
    if not raw or len(raw) > MAX_INPUT_BYTES or not raw.endswith(b'\n'):
        raise ValueError('source missing/unclosed/over budget: ' + str(path))
    lines = raw.splitlines()
    if len(lines) > MAX_ROWS or any(not line for line in lines):
        raise ValueError('source row count/blank line exceeds policy')
    return [json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite JSON'))) for line in lines]


def read_actual_storage(bag, expected_topics):
    """Decode every actual stored message, retaining each original CDR SHA."""
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message
    bag = Path(bag)
    meta = yaml.safe_load((bag / 'metadata.yaml').read_text())['rosbag2_bagfile_information']
    storage = meta['storage_identifier']
    if storage not in ('sqlite3', 'mcap'):
        raise ValueError('unsupported actual storage')
    declared = {}
    declared_counts = {}
    for item in meta['topics_with_message_count']:
        topic = item['topic_metadata']['name']
        if topic in declared:
            raise ValueError('duplicate metadata topic')
        declared[topic] = item['topic_metadata']['type']
        declared_counts[topic] = item['message_count']
    if declared != expected_topics:
        raise ValueError('actual metadata full topic/type set differs from pinned declaration')
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
                rosbag2_py.ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr'))
    actual_types = {x.name: x.type for x in reader.get_all_topics_and_types()}
    if actual_types != expected_topics:
        raise ValueError('actual reader full topic/types differ from pinned declaration')
    classes = {topic: get_message(typ) for topic, typ in actual_types.items()}
    raw_rows = {topic: [] for topic in classes}
    decoded = {topic: [] for topic in classes}
    total_bytes = 0
    total = 0
    while reader.has_next():
        topic, blob, stamp = reader.read_next()
        total += 1
        total_bytes += len(blob)
        if total > MAX_ROWS or total_bytes > MAX_INPUT_BYTES:
            raise ValueError('actual storage scan exceeds finite message/byte budget')
        message = plain(dict(message_to_ordereddict(deserialize_message(blob, classes[topic]))))
        decoded[topic].append({'message': message, 'bag_receive_ns': int(stamp)})
        raw_rows[topic].append(hashlib.sha256(blob).hexdigest())
    counts = {topic: len(rows) for topic, rows in raw_rows.items()}
    if counts != declared_counts or total != meta['message_count']:
        raise ValueError('actual storage metadata counts do not conserve')
    return decoded, raw_rows, {'storage_id': storage, 'topic_types': actual_types,
        'actual_counts': counts, 'total_messages': total, 'serialized_bytes': total_bytes,
        'storage_timestamp_semantics': 'storage receive timestamps; not CLOCK_MONOTONIC or source stamps'}


def transport_join(raw_rows, transport, owned_manifests, expected_topics):
    issues = []
    expected_gids = {}
    for manifest in owned_manifests.values():
        for e in manifest['endpoints']:
            if e['kind'] == 'publisher' and e['topic'] in expected_topics:
                if e['topic'] in expected_gids:
                    issues.append({'code': 'multiple_owned_publishers', 'topic': e['topic']})
                expected_gids[e['topic']] = e['gid']
    seen = {topic: [] for topic in expected_topics}
    for row in transport:
        if row.get('type') != 'transport_message':
            continue
        topic = row.get('topic')
        if topic not in seen:
            issues.append({'code': 'unknown_transport_topic', 'topic': topic})
            continue
        if row.get('ros_type') != expected_topics[topic] or row.get('publisher_gid') != expected_gids.get(topic):
            issues.append({'code': 'transport_actual_type_gid_differs', 'topic': topic})
        seen[topic].append(row.get('payload_sha256'))
    for topic, hashes in raw_rows.items():
        if seen[topic] != hashes:
            issues.append({'code': 'complete_transport_storage_cdr_sequence_differs', 'topic': topic,
                           'transport_count': len(seen[topic]), 'storage_count': len(hashes)})
    return {'passed': not issues, 'scope': 'entire_recorded_stream_including_prepare_and_terminal',
            'counts': {topic: len(rows) for topic, rows in seen.items()}, 'issues': issues}


def source_typed_join(observer, worker, decoded):
    issues = []
    def mapping(rows, key, label):
        result = {}
        for row in rows:
            ident = key(row)
            if ident in result:
                issues.append({'code': 'duplicate_source_or_typed_identity', 'stream': label, 'identity': ident})
            result[ident] = row
        return result
    streams = {}
    definitions = (
        ('jobs', [e['job'] for e in observer if e['type'] == 'job'], '/p1/solve_job', lambda r:r['job_id'], JOB_FIELDS, JOB_ALIASES),
        ('candidates', [e for e in worker if e['type'] == 'candidate'], '/p1/solve_candidate', lambda r:r['job']['job_id'], CANDIDATE_FIELDS, CANDIDATE_ALIASES),
        ('decisions', [e for e in observer if e['type'] == 'decision'], '/p1/execution_decision', lambda r:r['sequence'], DECISION_V2_FIELDS, DECISION_ALIASES))
    for label, source, topic, key, fields, aliases in definitions:
        s = mapping(source, key, label + '_source')
        b = mapping([r['message'] for r in decoded.get(topic, [])], key, label + '_bag')
        streams[label] = {'source': len(source), 'storage': len(decoded.get(topic, []))}
        if set(s) != set(b):
            issues.append({'code': 'source_typed_full_identity_sets_differ', 'stream': label,
                           'missing_storage': sorted(set(s)-set(b)), 'extra_storage': sorted(set(b)-set(s))})
        for ident in s.keys() & b.keys():
            left, right = projection(s[ident], fields, aliases), projection(b[ident], fields, {})
            if len(left) != len(fields) or len(right) != len(fields) or not exact(left, right):
                issues.append({'code': 'source_typed_full_payload_differs', 'stream': label, 'identity': ident})
            if label == 'candidates' and not exact(projection(s[ident]['job'], JOB_FIELDS, JOB_ALIASES), projection(b[ident]['job'], JOB_FIELDS, {})):
                issues.append({'code': 'candidate_immutable_job_differs', 'identity': ident})
    summaries = [e for e in observer if e['type'] == 'source_summary']
    if len(summaries) != 1 or observer[-1] is not summaries[0]:
        issues.append({'code': 'observer_terminal_source_summary_missing_or_not_last'})
    else:
        s = summaries[0]
        if (s.get('generated') != len(observer)-1 or s.get('emitted') != len(observer)-1
            or s.get('dropped') != 0 or s.get('normal_source_complete') is not True):
            issues.append({'code': 'observer_source_total_count_not_conserved'})
    summaries = [e for e in worker if e['type'] == 'worker_summary']
    if len(summaries) != 1 or worker[-1] is not summaries[0]:
        issues.append({'code': 'worker_terminal_summary_missing_or_not_last'})
    else:
        s = summaries[0]
        count = streams['candidates']['source']
        if s.get('generated_candidates') != count or s.get('published_candidates') != count or s.get('normal_source_complete') is not True or s.get('fatal') is not False:
            issues.append({'code': 'worker_candidate_publish_count_not_conserved'})
    return {'passed': not issues, 'streams': streams, 'issues': issues, 'window_clipped': False}


def publisher_join(session, decoded, startup, publisher_manifest):
    issues = []
    counts = {}
    for name, topic in PUBLISHER_STREAMS.items():
        if name not in session.get('streams', {}):
            continue
        rows = [r['message'] for r in decoded.get(topic, [])]
        s = session['streams'][name]
        count = len(rows)
        counts[name] = {'session_generated':s.get('generated'), 'session_emitted':s.get('emitted'), 'storage':count}
        if s.get('generated') != count or s.get('emitted') != count or s.get('dropped') != 0:
            issues.append({'code': 'publisher_full_session_storage_count_differs', 'stream':name})
        if count and ([r.get('sequence') for r in rows] != list(range(1,count+1)) or s.get('first_sequence') != 1 or s.get('last_sequence') != count):
            issues.append({'code': 'publisher_full_stream_sequences_not_conserved', 'stream':name})
        for r in rows:
            if any(r.get(k) != startup.get(k) for k in ('run_id','producer_instance_id','baseline_id','config_hash','steady_clock_domain')):
                issues.append({'code': 'publisher_stream_identity_differs', 'stream':name})
                break
    if session.get('normal_end') is not True or session.get('flushed') is not True or session.get('queue_dropped_total') != 0 or session.get('publish_errors') != 0:
        issues.append({'code': 'publisher_terminal_not_normal_or_flush_unverified'})
    applied = [r['message'] for r in decoded.get('/research/control/applied', [])]
    parameters=publisher_manifest['effective_parameters']
    physical = [parameters[k]['value'] for k in ('vrx_left_thrust_topic','vrx_right_thrust_topic')]
    if len(physical) != 2:
        # Publisher full role may independently declare the channels in startup pins.
        issues.append({'code': 'publisher_physical_topic_pins_missing'})
    else:
        for channel, key in enumerate(('left_publish_success','right_publish_success')):
            expected = sum(r.get(key) is True for r in applied)
            actual = len(decoded.get(physical[channel], []))
            if actual != expected:
                issues.append({'code': 'applied_physical_channel_count_differs', 'channel':channel, 'expected':expected, 'storage':actual})
    if not applied:
        issues.append({'code':'no_actual_applied'})
    return {'passed':not issues, 'counts':counts, 'issues':issues, 'commands_are_plant_ack':False}


def witness_source_join(witness, expected_header, observer):
    basis = analyze_witness(witness, expected_header)
    issues = []
    if not basis['passed']:
        return {'passed':False, 'basis':basis, 'issues':[{'code':'fixed_witness_integrity_failed'}]}
    def index(rows, key, label):
        out = {}
        for r in rows:
            k = key(r)
            if k in out:
                issues.append({'code':'duplicate_join_identity','stream':label,'identity':k})
            out[k] = r
        return out
    decisions = index([e for e in observer if e['type']=='decision'],lambda r:(r['schedule_generation'],r['tick']),'source_tick')
    ticks = index(witness['tick'],lambda r:(r['schedule_generation'],r['tick']),'witness_tick')
    if set(decisions)!=set(ticks):
        issues.append({'code':'entire_source_witness_tick_sets_differ'})
    for key in decisions.keys() & ticks.keys():
        d,r=decisions[key],ticks[key]
        wanted={'sequence':d['sequence'],'job_id':d['job_id'],'tick':d['tick'],'target_tick':d['tick'] if d['job_id'] else 0,
                'clock_epoch':d['epoch'],'planned_ns':d['planned_ns'],'start_ns':d['start_ns'],
                'skipped_ticks':d['skipped_ticks'],'candidate_present':d['job_id']>0,**{k:d[k] for k in VERSIONS}}
        if any(not exact(r[k],v) for k,v in wanted.items()) or d['end_ns']>r['end_ns']:
            issues.append({'code':'source_witness_whole_tick_differs','identity':key})
    jobs=index([e for e in observer if e['type']=='job'],lambda r:r['job']['job_id'],'source_job')
    submits=index(witness['submit'],lambda r:r['job_id'],'witness_submit')
    if set(jobs)!=set(submits):
        issues.append({'code':'entire_source_witness_submit_sets_differ'})
    for key in jobs.keys() & submits.keys():
        e,r=jobs[key],submits[key];j=e['job']
        if (any(r[k]!=j[k] for k in ('job_id','target_tick','clock_epoch',*VERSIONS)) or r['tick']!=j['target_tick']-1
            or not e['submit_commit_ns']<=r['commit_ns']<=e['publish_start_ns']):
            issues.append({'code':'source_witness_submit_binding_differs','identity':key})
    attempts=index([d for d in decisions.values() if d['job_id']],lambda r:r['job_id'],'source_attempt')
    activations=index(witness['activation'],lambda r:r['job_id'],'witness_activation')
    registrations=index([e for e in observer if e['type']=='candidate_registration' and e['accepted_registration']],lambda r:r['job']['job_id'],'registration')
    if set(attempts)!=set(activations):
        issues.append({'code':'entire_source_witness_activation_sets_differ'})
    for key in attempts.keys() & activations.keys():
        d,r=attempts[key],activations[key]
        wanted={'job_id':key,'tick':d['tick'],'target_tick':d['tick'],'clock_epoch':d['epoch'],
                'commit_ns':d['activation_commit_ns'],'ready_commit_ns':d['ready_commit_ns'],'accepted':d['accepted'],**{k:d[k] for k in VERSIONS}}
        wanted['reason_code']=0 if d['accepted'] else 1 if d['reason']=='shutdown' else 2 if d['reason']=='run_unusable_at_commit' else 3
        reg=registrations.get(key)
        if any(not exact(r[k],v) for k,v in wanted.items()) or reg is None or reg['ready_commit_ns']!=d['ready_commit_ns']:
            issues.append({'code':'source_witness_activation_binding_differs','identity':key})
    summaries=[e for e in observer if e['type']=='source_summary']
    closes=[e for e in witness['phase'] if e['event_code']==7]
    if len(summaries)!=1 or len(closes)!=1 or closes[0]['ns']<summaries[0]['finished_ns']:
        issues.append({'code':'source_witness_terminal_flush_order_differs'})
    return {'passed':not issues,'basis':basis,'issues':issues,'window_clipped':False,
            'counts':{'decisions':len(decisions),'ticks':len(ticks),'jobs':len(jobs),'submits':len(submits),'attempts':len(attempts),'activations':len(activations)}}


def analyze_inputs(inputs):
    required=('bag','topics_file','transport_source','synthetic_terminal','publisher_session','startup_manifest',
              'observer_source','worker_source','witness','expected_witness_header','owned_manifests')
    if any(k not in inputs for k in required):
        raise ValueError('missing declared checker input')
    files=[Path(inputs[k]) for k in required if k not in ('bag','owned_manifests')]
    files += [Path(v) for v in inputs['owned_manifests'].values()]
    files += sorted(p for p in Path(inputs['bag']).rglob('*') if p.is_file())
    before={str(p):sha(p) for p in files}
    topics=load_json(inputs['topics_file'])['topics']
    manifests={name:load_json(path) for name,path in inputs['owned_manifests'].items()}
    decoded,raw_rows,storage=read_actual_storage(inputs['bag'],topics)
    observer,worker=load_jsonl(inputs['observer_source']),load_jsonl(inputs['worker_source'])
    transport=transport_join(raw_rows,load_jsonl(inputs['transport_source']),manifests,topics)
    source=source_typed_join(observer,worker,decoded)
    startup=load_json(inputs['startup_manifest'])
    publisher=publisher_join(load_json(inputs['publisher_session']),decoded,startup,manifests['publisher'])
    witness=witness_source_join(load_json(inputs['witness']),load_json(inputs['expected_witness_header']),observer)
    terminal=load_json(inputs['synthetic_terminal'])
    raw_issues=[]
    if terminal.get('normal_end') is not True or terminal.get('failed') is not False or terminal.get('run_id')!=manifests['synthetic_source']['run_id']:
        raw_issues.append({'code':'synthetic_source_terminal_not_normal_or_wrong_identity'})
    for topic,count in terminal.get('published_counts',{}).items():
        if topic in topics and storage['actual_counts'].get(topic)!=count:
            raw_issues.append({'code':'entire_synthetic_publish_storage_count_differs','topic':topic,'published':count,'storage':storage['actual_counts'].get(topic)})
    if terminal.get('transport_counts')!=transport['counts'] or terminal.get('transport_total')!=sum(transport['counts'].values()):
        raw_issues.append({'code':'synthetic_transport_terminal_counts_do_not_conserve'})
    capability_issues=[]
    capability_rows=decoded.get('/p1/worker_capability',[])
    wm=manifests['worker']
    for row in capability_rows:
        m=row['message']
        expected={'run_id':wm['run_id'],'boot_id':wm['boot_id'],'contract_hash':wm['contract_sha256'],
                  'worker_instance':wm['worker_instance'],'nominal_hash':wm['nominal_hash'],'pid':wm['pid']}
        if any(not exact(m.get(k),v) for k,v in expected.items()):
            capability_issues.append({'code':'actual_worker_capability_identity_differs'})
            break
    if not capability_rows:
        capability_issues.append({'code':'actual_worker_capability_missing'})
    ready=[e for e in observer if e['type']=='legacy_ready']
    invalidated=[e for e in observer if e['type'] in ('legacy_ready_failed','legacy_ready_invalidated')]
    legacy_ready={'once_actual_source_row':len(ready)==1,'invalidated_or_failed_rows':len(invalidated),
                  'shared_validator_executed':False}
    after={str(p):sha(p) for p in files}
    passed=all(x['passed'] for x in (transport,source,publisher,witness)) and not raw_issues and not capability_issues and before==after and len(ready)==1 and not invalidated
    return {'schema_version':'p1-owned-fixture-stream-check-v1','passed':passed,'storage':storage,
            'transport_storage':transport,'source_typed_storage':source,'publisher_session':publisher,
            'source_fixed_witness':witness,'synthetic_raw_issues':raw_issues,'raw_inputs_unchanged':before==after,
            'worker_capability_issues':capability_issues,'legacy_ready_source_observation':legacy_ready,
            'input_sha256_before':before,'input_sha256_after':after,'shared_v2_readiness_checker_executed':False,
            'shared_v2_full_chain_qualified':False,'fixture_only':True,'D1_dynamic_qualified':False,'execute_qualified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:report=analyze_inputs(load_json(args.inputs))
    except Exception as error:report={'schema_version':'p1-owned-fixture-stream-check-v1','passed':False,'reader_error':type(error).__name__+': '+str(error),'execute_qualified':False,'shared_v2_full_chain_qualified':False}
    report['checker_sha256']=sha(__file__)
    create_only_json(args.output,report)
    print(json.dumps({'passed':report['passed'],'output':str(args.output),'reader_error':report.get('reader_error')}))
    return 0 if report['passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
