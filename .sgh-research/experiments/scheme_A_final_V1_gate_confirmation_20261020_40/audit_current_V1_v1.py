#!/usr/bin/env python3
"""Decode one closed current V1 run, independently check all sections and preserve raw inputs."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import traceback

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
from audit_fault_close_core_v1 import check as check_close
from audit_V1_strict_core_v1 import check as check_strict
from audit_business_start_v1 import check as check_start

PINS = {}


def need(value, why):
    if not value:
        raise ValueError(why)


def raw(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink(), 'plain_input_file:' + str(path))
    data = path.read_bytes()
    need(len(data) < 128 * 1024**2, 'bounded_input_file')
    pin = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    need(str(path) not in PINS or PINS[str(path)] == pin, 'input_changed:' + str(path))
    PINS[str(path)] = pin
    return data


def load(path):
    return json.loads(raw(path))


def rows(path):
    data = raw(path)
    need(data.endswith(b'\n'), 'unterminated_Source:' + str(path))
    return [json.loads(line) for line in data.splitlines()]


def dump(path, obj):
    with path.open('x') as stream:
        json.dump(obj, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def decode_runs():
    import yaml
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from usv_research_interfaces.msg import AppliedControl, ExecutionDecision
    from std_msgs.msg import String
    def decoded(data, cls):
        return json.loads(json.dumps(message_to_ordereddict(deserialize_message(data, cls))))
    lock=load(D/'preflight/prerun_source_lock_v1.json')
    for p,f in lock['files'].items():
        need(dict(bytes=len(raw(p)),sha256=hashlib.sha256(raw(p)).hexdigest())==f,'prerun_input_changed:'+p)
    results=[]
    for run in ['final_V1_01']:
        root = D/'author/runs'/run
        population_before = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())
        for name in population_before:
            raw(root / name)
        result, inputs = load(root / 'result.json'), load(root / 'inputs.json')
        manifests = {role: load(root / role / 'owned_manifest.json') for role in
                     ['observer', 'publisher', 'worker', 'synthetic_source', 'recorder']}
        binary_hashes = {role: hashlib.sha256(raw(m['exe'])).hexdigest() for role, m in manifests.items()}
        need(hashlib.sha256(raw(inputs['contract'])).hexdigest() == inputs['contract_sha256'], 'exact_contract')
        observer_source_sha = hashlib.sha256(raw(manifests['observer']['effective_parameters']['diagnostic_source_file']['value'])).hexdigest()
        publisher_rows = rows(root / 'publisher/controlled_source.jsonl')
        publisher_applied = {}
        for row in publisher_rows:
            if row.get('type') != 'controlled_Applied_emitted':
                continue
            wire = bytes.fromhex(row['cdr_hex'])
            need(len(wire) == row['cdr_bytes'] and hashlib.sha256(wire).hexdigest() == row['cdr_sha256'], 'Publisher_CDR_self_integrity')
            value = decoded(wire, AppliedControl)
            need(value['sequence'] == row['applied_sequence'] and str(value['sequence']) not in publisher_applied,
                 'Publisher_unique_CDR_sequence')
            publisher_applied[str(value['sequence'])] = value
        db_paths = list((root / 'recorder/bag').glob('*.db3'))
        need(len(db_paths) == 1, 'one_closed_SQLite')
        db = sqlite3.connect(db_paths[0].resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            integrity = db.execute('pragma integrity_check').fetchone()[0]
            all_topics = {name: 0 for (name,) in db.execute('select name from topics')}
            storage = db.execute('select t.name,m.data from messages m join topics t on m.topic_id=t.id order by m.id').fetchall()
        finally:
            db.close()
        stored_applied, stored_decisions, stored_phase, stored_decision_wire = [], [], [], []
        for topic, wire in storage:
            all_topics[topic] += 1
            if topic == '/research/control/applied':
                stored_applied.append({'decoded': decoded(wire, AppliedControl), 'wire_sha256': hashlib.sha256(wire).hexdigest(), 'wire_bytes': len(wire)})
            elif topic == '/p1/execution_decision':
                value=decoded(wire,ExecutionDecision);stored_decisions.append(value)
                stored_decision_wire.append(dict(decoded=value,wire_sha256=hashlib.sha256(wire).hexdigest(),wire_hex=wire.hex()))
            elif topic=='/p1/controlled_owner_phase':
                value=json.loads(deserialize_message(wire,String).data)
                stored_phase.append(dict(decoded=value,wire_sha256=hashlib.sha256(wire).hexdigest(),wire_hex=wire.hex()))
        metadata_bytes = raw(root / 'recorder/bag/metadata.yaml')
        metadata = yaml.safe_load(metadata_bytes)['rosbag2_bagfile_information']
        bundle = {'schema': 'batch40-current-closed-raw/v1',
            'requested_profile': 'sink-fault-self-close-v1', 'run_id': run,
            'boot_id': manifests['observer']['boot_id'], 'original_result': result, 'inputs': inputs,
            'ledger': rows(root / 'owned_process_ledger.jsonl'), 'manifests': manifests,
            'manifest_hashes': {role: hashlib.sha256(raw(root / role / 'owned_manifest.json')).hexdigest() for role in manifests},
            'binary_hashes': binary_hashes, 'preparation': load(root / 'preparation_evidence.json'),
            'fault': load(root / 'observer/v1_fault.json'), 'witness': load(root / 'observer/witness.json'),
            'expected_header': load(root / 'expected_witness_header.json'),
            'observer_source': rows(root / 'observer/source.jsonl'), 'observer_source_sha256': observer_source_sha,
            'publisher_source': publisher_rows, 'publisher_applied': publisher_applied,
            'publisher_session': load(root / 'publisher/session_summary.json'),
            'transport': rows(root / 'synthetic_source/transport_source.jsonl'),
            'fixture_terminal': load(root / 'synthetic_source/terminal.json'),
            'recorder_terminal': load(root / 'recorder/terminal.json'),
            'stored_applied': stored_applied, 'stored_decisions': stored_decisions,
            'db_integrity_check': integrity, 'metadata_sha256': hashlib.sha256(metadata_bytes).hexdigest(),
            'metadata_counts': {r['topic_metadata']['name']: r['message_count'] for r in metadata['topics_with_message_count']},
            'metadata_total': metadata['message_count'], 'storage_counts': all_topics,
            'original_run_root': str(root), 'derived_data_from_current_actual_run': True,
            'fault_close_driver':load(root/'fault_self_close_driver.json'),
            'stored_phase':stored_phase,'stored_decision_wire':stored_decision_wire}
        dump(D / 'evidence' / (run + '_normalized_v1.json'), bundle)
        sections={}
        def section(name,fn):
            try:sections[name]=dict(passed=True,details=fn())
            except Exception as e:sections[name]=dict(passed=False,error=repr(e),traceback=traceback.format_exc())
        section('business_start_then_original_tick',lambda:check_start(root,bundle['observer_source'],publisher_rows,bundle['witness'],
            load(root/'business_start_request.json'),load(root/'business_start_observation.json'),bundle['preparation'],inputs,result,manifests))
        section('strict_actual_accepted_Applied_authenticated_ack_before_arm',lambda:check_strict(bundle))
        section('current_fault_profile_owned_close_and_Stored_zero',lambda:check_close(bundle))
        need(population_before == sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()), 'raw_population_changed')
        results.append(dict(run=run,sections=sections,passed=all(r['passed'] for r in sections.values()),
            original_normal_status=result['passed'],original_error=result.get('error'),original_close_errors=result['close_errors']))
    raw(yaml.__file__)
    before = dict(PINS)
    for path in before:
        raw(path)
    need(PINS == before, 'final_pin_set_changed')
    report = dict(schema='current-V1-closed-raw-audit/v1',passed=all(r['passed'] for r in results),actual_new_runs=1,
        cases=results,input_sha256_before=before,input_sha256_after=PINS,inputs_unchanged=True,
        new_driver_executed_live=True,normal_close_qualified=False,stage_qualified=False,execute_qualified=False,
        true_plant_qualified=False,research_conclusion=False)
    dump(D/'postrun/current_V1_actual_audit_v1.json',report)
    print(json.dumps(dict(passed=report['passed'],raw_inputs=len(PINS),sections={k:dict(passed=v['passed'],error=v.get('error')) for k,v in results[0]['sections'].items()},actual_new_runs=1)))
    return 0 if report['passed'] else 2

if __name__ == '__main__':
    try:raise SystemExit(decode_runs())
    except Exception as error:
        dump(D/'postrun/current_V1_actual_audit_failure_v1.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),read_input_pins=PINS))
        print(traceback.format_exc());raise SystemExit(2)
