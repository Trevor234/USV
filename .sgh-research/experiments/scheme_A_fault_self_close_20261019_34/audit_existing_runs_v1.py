#!/usr/bin/env python3
"""Read closed batch33 raw bytes, not ROS nodes. No historical output is written."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import traceback

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D / 'implementation'))
from check_fault_self_close_v1 import check

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
    def decoded(data, cls):
        return json.loads(json.dumps(message_to_ordereddict(deserialize_message(data, cls))))
    base = D.parent / 'p1_execution_architecture_20261005_01'
    results = []
    for author, run in [('authored_D1_V1_sink_failure_20261019_v33', 'v1_sink_01'),
                        ('authored_D1_V1_sink_failure_20261019_v33r2', 'v1_sink_ack_02')]:
        root = base / author / 'runs' / run
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
        stored_applied, stored_decisions = [], []
        for topic, wire in storage:
            all_topics[topic] += 1
            if topic == '/research/control/applied':
                stored_applied.append({'decoded': decoded(wire, AppliedControl), 'wire_sha256': hashlib.sha256(wire).hexdigest(), 'wire_bytes': len(wire)})
            elif topic == '/p1/execution_decision':
                stored_decisions.append(decoded(wire, ExecutionDecision))
        metadata_bytes = raw(root / 'recorder/bag/metadata.yaml')
        metadata = yaml.safe_load(metadata_bytes)['rosbag2_bagfile_information']
        bundle = {'schema': 'batch34-derived-normalized-existing-raw/v1',
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
            'original_run_root': str(root), 'derived_data_not_new_execution': True}
        dump(D / 'evidence' / (run + '_normalized_v1.json'), bundle)
        report = check(bundle)
        need(report['original_V1_strict_order_passed'] == (run == 'v1_sink_ack_02'), 'historical_V1_order_changed')
        dump(D / 'verification' / (run + '_fault_closure_v1.json'), report)
        need(population_before == sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()), 'raw_population_changed')
        results.append(report)
    raw(yaml.__file__)
    before = dict(PINS)
    for path in before:
        raw(path)
    need(PINS == before, 'final_pin_set_changed')
    report = {'passed': True, 'actual_new_runs': 0, 'retrospective_cases': results,
              'input_sha256_before': before, 'input_sha256_after': PINS,
              'inputs_unchanged': True, 'new_driver_executed_live': False,
              'normal_close_qualified': False, 'stage_qualified': False, 'execute_qualified': False,
              'true_plant_qualified': False, 'research_conclusion': False}
    dump(D / 'verification/existing_runs_audit_v1.json', report)
    print(json.dumps({'passed': True, 'raw_inputs': len(PINS), 'retrospective_cases': len(results),
                      'actual_new_runs': 0, 'normal_close_qualified': False}))


if __name__ == '__main__':
    try:
        decode_runs()
    except Exception as error:
        dump(D / 'verification/existing_runs_audit_failure_v1.json',
             {'passed': False, 'error': repr(error), 'traceback': traceback.format_exc(), 'read_input_pins': PINS})
        print(repr(error))
        raise SystemExit(2)
