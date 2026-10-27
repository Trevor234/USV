"""Independently check C3.3 publisher release observations for a closed owned run.

This is a bounded localhost component check. Prepared receipts, diagnostics,
transport commands and SQLite records do not prove plant execution. The normal
owned/atomic/Witness checker remains a separate qualification decision.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
SCHEMA = 'p1-C3.3-release-observation-check/v1'
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ROWS = 20000
MAX_FILES = 256
ROLES = ('publisher', 'worker', 'observer', 'synthetic_source', 'recorder')
IDENTITY_KEYS = ('run_id', 'producer_instance_id', 'steady_clock_domain', 'boot_id', 'pid',
    'process_start_ticks', 'source_bundle_sha256', 'binary_sha256', 'baseline_id', 'config_hash',
    'nominal_config_hash', 'contract_sha256', 'owned_manifest_sha256', 'effective_parameters_sha256')
QUALIFICATIONS = {'strict_full_chain': False, 'C3_general': False, 'D1_dynamic': False,
    'P1': False, 'execute': False, 'plant': False, 'true_master_clock': False,
    'research_conclusion': False}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def integer(value):
    return type(value) is int


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def shape(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def strict_json(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, 'duplicate_json_key')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


class Inputs:
    """Bound every read, reject symlinks/special files, retain before/after hashes."""
    def __init__(self):
        self.before = {}
        self.total = 0
        self.deadline = time.monotonic() + 30

    def raw(self, path, limit=MAX_FILE_BYTES, remember=True):
        p = Path(path)
        require(p.is_absolute() and '..' not in p.parts, 'input_path_not_absolute_normalized')
        require(time.monotonic() <= self.deadline, 'checker_read_budget_exceeded')
        require(not any(q.is_symlink() for q in (p, *p.parents)), 'input_symlink_forbidden')
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit,
                    'input_not_bounded_regular_file')
            blocks, size = [], 0
            while True:
                block = os.read(fd, min(1024 * 1024, limit + 1 - size))
                if not block:
                    break
                blocks.append(block)
                size += len(block)
                require(size <= limit and time.monotonic() <= self.deadline, 'input_read_budget_exceeded')
            after = os.fstat(fd)
            def identity(s):
                return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(identity(before) == identity(after) and size == before.st_size,
                    'input_changed_during_read')
            raw = b''.join(blocks)
        finally:
            os.close(fd)
        if remember:
            key = str(p)
            if key not in self.before:
                self.total += len(raw)
            require(self.total <= MAX_TOTAL_BYTES and len(self.before) < MAX_FILES,
                    'aggregate_input_budget_exceeded')
            require(key not in self.before or self.before[key] == digest(raw), 'input_changed_between_reads')
            self.before[key] = digest(raw)
        return raw

    def json(self, path, limit=1024 * 1024):
        return strict_json(self.raw(path, limit))

    def jsonl(self, path):
        raw = self.raw(path)
        require(bool(raw) and raw.endswith(b'\n'), 'jsonl_missing_or_unclosed')
        rows = raw.splitlines()
        require(len(rows) <= MAX_ROWS and all(rows), 'jsonl_row_budget_or_blank_line')
        return [strict_json(row) for row in rows]

    def unchanged(self):
        return {path: digest(self.raw(path, remember=False)) for path in self.before}


def check_gate(gate, release, release_raw, publication, snapshot_ns, mode):
    """Check coherent same-lock fields; native tests separately verify locking."""
    deadline = release['valid_until_steady_ns']
    require(integer(deadline), 'release_deadline_not_exact_integer')
    require(gate['release_read_completed'] is True and gate['release_present_at_last_completed_read'] is True,
            'actual_release_read_incomplete')
    require(gate['release_bytes_count'] == len(release_raw), 'actual_release_read_length_differs')
    require(integer(gate['poll_count']) and gate['poll_count'] > 0 and
            integer(gate['missing_release_count']) and 0 <= gate['missing_release_count'] < gate['poll_count'],
            'gate_poll_counts_invalid')
    require(integer(gate['released_integrity_verify_count']) and gate['released_integrity_verify_count'] >= 0,
            'gate_integrity_count_invalid')
    require(gate['valid_until_steady_ns'] == deadline, 'gate_deadline_differs')
    require(gate['business_policy_changed'] is False and gate['observation_qualifies_physical_release'] is False,
            'gate_observation_promotes_policy_or_physical_release')
    validate = gate['validate_now_ns']
    require(integer(validate) and validate > 0, 'actual_validate_read_missing')
    read_start, read_end = gate['release_read_start_steady_ns'], gate['release_read_end_steady_ns']
    require(integer(read_start) and integer(read_end) and 0 < read_start <= read_end <= validate <= snapshot_ns,
            'release_read_validate_timeline_invalid')
    # The create-only call's atomic link precedes its directory fsync return.
    # Validation can therefore occur before call_end; do not assert the opposite.
    require(validate >= publication['call_start_steady_ns'] and read_end >= publication['call_start_steady_ns'],
            'validation_precedes_release_publication_call_start')
    if mode == 'positive':
        require(gate['gate_state'] == 'Released' and gate['failure_reason'] == '' and
                gate['failure_phase'] == 'none' and gate['failure_steady_ns'] is None,
                'positive_gate_not_released_cleanly')
        require(gate['last_phase'] in ('in_memory_commit', 'released_integrity_verification'),
                'positive_last_phase_invalid')
        require(gate['original_freshness_read_count'] == 3, 'positive_original_freshness_read_count_differs')
        attempt, final = gate['attempt_now_ns'], gate['final_freshness_now_ns']
        require(integer(attempt) and integer(final) and validate <= attempt <= final < deadline and
                0 < deadline - validate <= 60_000_000_000,
                'positive_actual_freshness_values_invalid')
        values = [validate, gate['arm_start_steady_ns'], gate['arm_end_steady_ns'], attempt,
                  gate['receipt_io_start_steady_ns'], gate['receipt_io_end_steady_ns'], final,
                  gate['commit_steady_ns'], snapshot_ns]
        require(all(integer(v) and v > 0 for v in values) and values == sorted(values),
                'positive_actual_phase_timeline_invalid')
        require(gate['receipt_io_completed'] is True and gate['release_file_sha256'] == digest(release_raw) and
                gate['accepted_release_sha256'] == digest(release_raw), 'positive_receipt_or_accepted_hash_differs')
    else:
        require(gate['gate_state'] == 'Fault' and gate['failure_phase'] == 'release_parse_and_validation' and
                gate['last_phase'] == 'release_parse_and_validation' and
                gate['failure_reason'] == 'release expired or validity exceeds 60 seconds',
                'expired_actual_fault_reason_or_phase_differs')
        require(deadline <= validate and deadline <= publication['call_start_steady_ns'], 'fixture_not_actually_expired')
        require(gate['original_freshness_read_count'] == 1 and gate['receipt_io_completed'] is False and
                gate['released_integrity_verify_count'] == 0, 'expired_short_circuit_counts_differs')
        unread = ('attempt_now_ns', 'final_freshness_now_ns', 'arm_start_steady_ns', 'arm_end_steady_ns',
                  'receipt_io_start_steady_ns', 'receipt_io_end_steady_ns', 'commit_steady_ns',
                  'accepted_release_sha256', 'release_file_sha256')
        require(all(gate[k] is None for k in unread), 'expired_invents_unread_or_uncommitted_evidence')
        require(integer(gate['failure_steady_ns']) and validate <= gate['failure_steady_ns'] <= snapshot_ns,
                'expired_failure_timeline_invalid')
    return {'passed': True, 'mode': mode, 'gate_state': gate['gate_state'],
        'failure_reason': gate['failure_reason'], 'failure_phase': gate['failure_phase'],
        'original_freshness_read_count': gate['original_freshness_read_count'],
        'receipt_io_completed': gate['receipt_io_completed'],
        'original_now_reads_repeated_by_checker': False,
        'same_lock_implementation_verified_by_artifact_alone': False,
        'scope': 'coherent captured fields bound to pinned native implementation; concurrency tested separately'}


def check_source_session(session, startup, snapshot, mode):
    require(session['run_id'] == startup['run_id'] and session['producer_instance_id'] == startup['producer_instance_id'] and
            session['flushed'] is True and session['queue_dropped_total'] == 0 and session['publish_errors'] == 0 and
            integer(session['end_steady_ns']) and 0 < session['end_steady_ns'] <= snapshot,
            'publisher_source_session_unclean_or_not_terminal')
    if mode == 'positive':
        require(session['normal_end'] is True and integer(session['start_steady_ns']) and
                0 < session['start_steady_ns'] <= session['end_steady_ns'], 'positive_publisher_session_not_normal')
    else:
        # The original logger defines normal_end = normal_ && armed_ && ... .
        # A release rejected before arm correctly has normal_end=false. Keep
        # this explicit; component absence proof never upgrades normal policy.
        require(session['normal_end'] is False and session['start_steady_ns'] == 0 and
                session['cycle_invocations_started'] == session['interrupted_cycle_sequence'] == 0,
                'expired_publisher_session_not_original_unarmed_state')
    return {'passed': True, 'normal_end': session['normal_end'], 'flushed': session['flushed'],
        'streams': session['streams'], 'normal_policy_qualified_by_this_check': False}


def check_event(event, path, release, raw, startup_hash, prepared_start):
    require(event['schema'] == 'p1-release-create-only-call/v1' and event['release_path'] == str(path),
            'publication_event_path_or_schema_differs')
    for key in ('run_id', 'producer_instance_id', 'release_nonce', 'valid_until_steady_ns'):
        require(event[key] == release[key], 'publication_event_release_identity_differs:' + key)
    require(event['startup_manifest_sha256'] == startup_hash == release['startup_manifest_sha256'],
            'publication_startup_binding_differs')
    start, end = event['call_start_steady_ns'], event['call_end_steady_ns']
    require(integer(start) and integer(end) and 0 < prepared_start <= start <= end,
            'publication_call_timeline_invalid')
    # This checker admits only completed calls in its two declared actual cases.
    # Failed or ambiguous IO is a failed input, never an expected semantic pass.
    require(event['completed'] is True and event['error_type'] is None and event['error'] is None and
            event['publication_state'] == 'visible; create-only call and directory fsync completed' and
            event['release_sha256'] == digest(raw) and 'ambiguous_content_sha256' not in event,
            'publication_call_failed_ambiguous_or_digest_differs')
    return {'passed': True, 'sha256': digest(raw), 'call_start_steady_ns': start,
        'call_end_steady_ns': end, 'completed': True,
        'first_visibility_instant_observed': False,
        'interval_semantics': 'original create_only_json call including directory fsync; publisher may validate before call end'}


def sqlite_storage(reader, bag, topics):
    """Read actual CDR hashes/counts from SQLite, without requiring ROS imports."""
    import yaml
    class UniqueLoader(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        rows = loader.construct_pairs(node, deep=deep)
        out = {}
        for key, value in rows:
            require(key not in out, 'duplicate_yaml_key')
            out[key] = value
        return out
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    metadata = yaml.load(reader.raw(bag / 'metadata.yaml', 1024 * 1024), Loader=UniqueLoader)['rosbag2_bagfile_information']
    require(metadata['storage_identifier'] == 'sqlite3', 'storage_not_declared_sqlite3')
    declared, counts = {}, {}
    for entry in metadata['topics_with_message_count']:
        row = entry['topic_metadata']; topic = row['name']
        require(topic not in declared and row['serialization_format'] == 'cdr', 'metadata_duplicate_or_nonCDR_topic')
        declared[topic] = row['type']; counts[topic] = entry['message_count']
    require(declared == topics and all(integer(c) and c >= 0 for c in counts.values()), 'metadata_topics_or_counts_differs')
    relative = metadata['relative_file_paths']
    require(type(relative) is list and 0 < len(relative) <= 16 and len(set(relative)) == len(relative), 'sqlite_file_list_invalid')
    bag_inventory = sorted(str(p.relative_to(bag)) for p in bag.rglob('*') if p.is_file())
    require(all(type(name) is str and Path(name).name == name and name.endswith('.db3') for name in relative),
            'sqlite_path_not_single_declared_filename')
    require(sorted(bag_inventory) == sorted(['metadata.yaml', *relative]), 'sqlite_inventory_has_extra_or_missing_artifacts')
    rows = {topic: [] for topic in topics}; total = byte_count = 0
    for name in relative:
        database = bag / name; reader.raw(database)
        connection = sqlite3.connect('file:' + quote(str(database), safe='/') + '?mode=ro', uri=True, timeout=1)
        connection.set_progress_handler(lambda: int(time.monotonic() > reader.deadline), 1000)
        try:
            connection.execute('PRAGMA query_only=ON')
            require(connection.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'sqlite_integrity_check_failed')
            table = connection.execute('SELECT id,name,type,serialization_format FROM topics').fetchall()
            typed = {name: typ for _, name, typ, fmt in table}
            require(len(typed) == len(table) and typed == topics and all(fmt == 'cdr' for _, _, _, fmt in table),
                    'sqlite_full_topic_types_differs')
            ids = {ident: name for ident, name, _, _ in table}
            for _, ident, blob, stamp in connection.execute('SELECT id,topic_id,data,timestamp FROM messages ORDER BY id'):
                require(ident in ids and type(blob) is bytes and integer(stamp), 'sqlite_message_shape_invalid')
                total += 1; byte_count += len(blob)
                require(total <= MAX_ROWS and byte_count <= MAX_FILE_BYTES and time.monotonic() <= reader.deadline,
                        'sqlite_scan_budget_exceeded')
                rows[ids[ident]].append((digest(blob), len(blob)))
        finally:
            connection.close()
    actual = {topic: len(value) for topic, value in rows.items()}
    require(actual == counts and metadata['message_count'] == total, 'sqlite_metadata_counts_not_conserved')
    return rows, {'passed': True, 'storage_id': 'sqlite3', 'actual_counts': actual,
        'total_messages': total, 'serialized_bytes': byte_count, 'actual_db_files': relative,
        'typed_payload_decoded': False, 'storage_timestamps_are_source_monotonic': False}, bag_inventory


def analyze(run):
    run = Path(run)
    require(run.is_absolute() and run.is_dir(), 'run_must_be_existing_absolute_directory')
    reader = Inputs()
    inputs = reader.json(run / 'inputs.json'); result = reader.json(run / 'result.json')
    mode = inputs['mode']; run_id = inputs['run_id']
    require(mode in ('positive', 'expired_release') and result['mode'] == mode and result['run_id'] == run_id,
            'case_not_declared_positive_or_expired_release')
    require(run.name == run_id and result['fixture_only'] is True and result['execute_qualified'] is False and
            result['physical_release_qualified'] is False and result['D1_dynamic_qualified'] is False,
            'run_identity_or_scope_differs')
    require(result['cleanup_complete'] is True and result['resource_cleanup_complete'] is True and
            result['cleanup_within_budget'] is True and result['evidence_qualification_clean'] is True and
            result['close_errors'] == [] and result['ledger_failed'] is False and
            integer(result['close_elapsed_ns']) and result['close_elapsed_ns'] <= 15_000_000_000 and
            result['owned_role_returncodes'] == {role: 0 for role in ROLES}, 'closed_run_cleanup_or_returncodes_unclean')
    for role in ROLES:
        c = result['cleanup'][role]
        require(c['cleanup_complete'] is True and c['resource_cleanup_complete'] is True and
                c['qualification_clean'] is True and c['returncode'] == 0 and
                c['remaining_members'] == [] and c['unexpected_descendants'] == [], 'owned_role_cleanup_unclean:' + role)
    require(result['prepare_start_ns'] > 0 and result['prepare_budget_ns'] == 25_000_000_000 and
            result['overall_budget_ns'] == 60_000_000_000 and result['elapsed_ns'] <= 60_000_000_000,
            'original_bounded_run_budgets_differs')
    publication = reader.json(run / 'release_publication_observation.json')
    startup = reader.json(run / 'publisher/startup_manifest.json', 16384)
    owned = {role: reader.json(run / role / 'owned_manifest.json') for role in ROLES}
    report = reader.json(run / 'publisher/release_observation.json', 32768)
    ledger = reader.jsonl(run / 'owned_process_ledger.jsonl')
    spawns = [row for row in ledger if row.get('type') == 'spawn']
    require(len(spawns) == len(ROLES) and {row['name'] for row in spawns} == set(ROLES), 'exact_owned_spawn_set_differs')
    source_details = {}
    for role in ROLES:
        build_role = 'fixture' if role == 'synthetic_source' else role
        pin = inputs['source_bundles'][build_role]; build = inputs['builds'][build_role]
        bundle = reader.json(pin['path']); require(reader.before[str(Path(pin['path']))] == pin['sha256'], 'bundle_digest_differs:' + role)
        require(build['passed'] is True and build['source_bundle']['sha256'] == pin['sha256'] and
                build['source_bundle']['path'] == pin['path'], 'build_source_pin_differs:' + role)
        require(len(bundle['files']) == pin['files'], 'source_bundle_file_count_differs:' + role)
        for row in bundle['files'].values():
            raw = reader.raw(row['path'])
            require(digest(raw) == row['sha256'] and len(raw) == row['bytes'], 'pinned_source_bytes_differs:' + row['path'])
        binary_hash = digest(reader.raw(build['binary']))
        manifest = owned[role]; spawn = next(row for row in spawns if row['name'] == role)
        expected_run = run_id + '-publisher' if role == 'publisher' else run_id
        require(manifest['role'] == role and manifest['run_id'] == expected_run and
                manifest['source_bundle_sha256'] == pin['sha256'] and manifest['binary_sha256'] == build['binary_sha256'] == binary_hash and
                manifest['contract_sha256'] == inputs['contract_sha256'], 'owned_role_input_build_binding_differs:' + role)
        require(spawn['executable_verified'] is True and spawn['expected_sha256'] == binary_hash and
                spawn['expected_exe'] == build['binary'] and spawn['identity']['exe'] == build['binary'] and
                spawn['identity']['exe_sha256'] == binary_hash and spawn['identity']['pid'] == manifest['pid'] and
                spawn['identity']['start_ticks'] == manifest['process_start_ticks'] and spawn['boot_id'] == manifest['boot_id'],
                'owned_role_spawn_binding_differs:' + role)
        source_details[role] = {'source_bundle_sha256': pin['sha256'], 'binary_sha256': binary_hash,
            'pinned_source_files': len(bundle['files'])}
    for tool in ('prepare_fixture.py', 'owned_auth.py', 'owned_release.py'):
        require(digest(reader.raw(run / (tool + '.snapshot'))) == inputs['tool_sha256'][tool], 'captured_driver_tool_digest_differs:' + tool)
    require(publication['schema'] == 'p1-owned-release-publication-observation/v1' and publication['run_id'] == run_id and
            publication['driver_tool_sha256'] == inputs['tool_sha256']['prepare_fixture.py'] and
            publication['owned_auth_sha256'] == inputs['tool_sha256']['owned_auth.py'] and
            publication['stage_qualified'] is False and publication['execute_qualified'] is False,
            'publication_driver_identity_or_scope_differs')
    driver = publication['driver_identity']
    require(driver['boot_id'] == startup['boot_id'] and integer(driver['pid']) and driver['pid'] > 0 and
            integer(driver['start_ticks']) and driver['start_ticks'] > 0 and shape(driver['exe_sha256']) and
            all(row['identity']['ppid'] == driver['pid'] for row in spawns) and
            str(run.parent.parent / 'prepare_fixture.py') in driver['argv'] and run_id in driver['argv'],
            'publication_driver_not_bound_to_owned_spawn_parent')
    require(report['schema_version'] == 'p1-D1-publisher-release-observation-v1' and
            report['identity'] == {key: startup[key] for key in IDENTITY_KEYS}, 'terminal_report_exact_startup_identity_differs')
    startup_hash = reader.before[str(run / 'publisher/startup_manifest.json')]
    require(report['startup_manifest_sha256'] == startup_hash and startup['owned_manifest_sha256'] ==
            reader.before[str(run / 'publisher/owned_manifest.json')], 'terminal_report_startup_owned_digests_differs')
    for key in ('run_id', 'boot_id', 'pid', 'process_start_ticks', 'source_bundle_sha256', 'binary_sha256',
                'contract_sha256', 'effective_parameters_sha256'):
        require(startup[key] == owned['publisher'][key], 'startup_owned_identity_differs:' + key)
    require(report['controller_shutdown_requested'] is True and report['terminal_observation_only'] is True and
            all(report[key] is False for key in ('receipt_qualifies_physical_release', 'physical_release_qualified',
                'execute_qualified', 'research_conclusion')), 'terminal_report_qualifies_more_than_observation')
    snapshot = report['snapshot_steady_ns']; require(integer(snapshot) and snapshot > 0, 'terminal_snapshot_timestamp_invalid')
    require(startup['steady_clock_domain'] == startup['boot_id'] + ':steady_clock', 'clock_domain_not_bound_to_boot')
    release_raw = reader.raw(run / 'release.json', 16384); release = strict_json(release_raw)
    require(release['schema_version'] == 'p1-D1-publisher-release-v1' and
            release['run_id'] == startup['run_id'] and release['producer_instance_id'] == startup['producer_instance_id'] and
            release['gates'] == {'external_worker_zero_hooks': True, 'subscriptions_verified': True, 'unique_dual_channel_owner': True},
            'release_original_identity_or_preparation_gates_differs')
    events = publication['events']; require(type(events) is list and len(events) == (1 if mode == 'positive' else 2), 'publication_actual_event_count_differs')
    event = next((row for row in events if row.get('release_path') == str(run / 'release.json')), None)
    require(event is not None, 'actual_release_publication_event_missing')
    publication_result = check_event(event, run / 'release.json', release, release_raw, startup_hash, result['prepare_start_ns'])
    if mode == 'positive':
        require(result['passed'] is True and result['released'] is True and result.get('error') is None and
                result['release']['release'] == release and result['release']['release_sha256'] == digest(release_raw), 'positive_fixture_result_differs')
        helper_release, helper_event = release, event
        evidence_file = run / 'preparation_evidence.json'
    else:
        require(result['passed'] is False and result['released'] is False and result['held_negative_passed'] is True and
                result['expected_negative_rejection'] is True and result['expired_release_no_receipt'] is True and
                result['rejection'] == 'actual publisher refused expired release' and
                result['expired_fixture_release_sha256'] == digest(release_raw), 'expired_fixture_result_differs')
        require(not (run / 'publisher/release_receipt.json').exists() and not (run / 'synthetic_start.json').exists(),
                'expired_fixture_has_receipt_or_sensor_start')
        candidate_raw = reader.raw(run / 'release_candidate.json', 16384); candidate = strict_json(candidate_raw)
        helper_event = next((row for row in events if row.get('release_path') == str(run / 'release_candidate.json')), None)
        require(helper_event is not None, 'candidate_helper_publication_missing')
        check_event(helper_event, run / 'release_candidate.json', candidate, candidate_raw, startup_hash, result['prepare_start_ns'])
        require({k: v for k, v in candidate.items() if k != 'valid_until_steady_ns'} ==
                {k: v for k, v in release.items() if k != 'valid_until_steady_ns'}, 'expired_fixture_changes_more_than_deadline')
        helper_release = candidate; evidence_file = run / 'candidate_preparation_evidence.json'
    remaining = helper_release['valid_until_steady_ns'] - helper_event['call_start_steady_ns']
    require(0 < remaining <= 3_000_000_000, 'original_helper_three_second_freshness_differs')
    evidence = reader.json(evidence_file)
    require(reader.before[str(evidence_file)] == release['driver_evidence_sha256'] and
            evidence['startup_manifest_sha256'] == startup_hash and evidence['production_execute_qualified'] is False,
            'release_preparation_evidence_digest_or_scope_differs')
    gate_result = check_gate(report['gate'], release, release_raw, event, snapshot, mode)
    session = reader.json(run / 'publisher/session_summary.json')
    session_result = check_source_session(session, startup, snapshot, mode)
    if mode == 'positive':
        receipt = reader.json(run / 'publisher/release_receipt.json', 16384)
        require(receipt['schema_version'] == 'p1-D1-publisher-release-receipt-v1' and
                receipt['status'] == 'prepared_acceptance' and receipt['receipt_qualifies_physical_release'] is False and
                receipt['physical_output_state'] == 'held_pending_in_memory_commit' and
                receipt['startup_manifest_sha256'] == startup_hash and receipt['release_file_sha256'] == digest(release_raw) and
                receipt['attempted_acceptance_steady_ns'] == report['gate']['attempt_now_ns'] and
                receipt['valid_until_steady_ns'] == release['valid_until_steady_ns'] and
                receipt['release_nonce'] == release['release_nonce'] and receipt['driver_evidence_sha256'] == release['driver_evidence_sha256'],
                'positive_prepared_receipt_binding_differs')
        for key in IDENTITY_KEYS:
            require(receipt[key] == startup[key], 'positive_receipt_identity_differs:' + key)
    topics_doc = reader.json(run / 'topics.json'); topics = topics_doc['topics']
    require(reader.before[str(run / 'topics.json')] == inputs['topics_sha256'], 'topics_pin_differs')
    recorder = reader.json(run / 'recorder/terminal.json')
    require(recorder['schema'] == 'p1-owned-recorder-terminal/v1' and recorder['prepared'] is True and
            recorder['Recorder_stop_completed'] is True and recorder['clean'] is True and recorder['error'] == '' and
            recorder['metadata_exists'] is True and recorder['storage_id'] == 'sqlite3' and recorder['storage_uri'] == str(run / 'recorder/bag') and
            recorder['manifest_sha256'] == reader.before[str(run / 'recorder/owned_manifest.json')], 'recorder_terminal_not_clean_or_bound')
    for key in ('run_id', 'boot_id', 'pid', 'process_start_ticks', 'source_bundle_sha256', 'contract_sha256'):
        require(recorder[key] == owned['recorder'][key], 'recorder_terminal_identity_differs:' + key)
    raw_rows, storage, bag_inventory = sqlite_storage(reader, run / 'recorder/bag', topics)
    require(recorder['metadata_sha256'] == reader.before[str(run / 'recorder/bag/metadata.yaml')], 'recorder_metadata_digest_differs')
    transport = reader.jsonl(run / 'synthetic_source/transport_source.jsonl')
    publishers = {}
    for manifest in owned.values():
        for endpoint in manifest['endpoints']:
            if endpoint['kind'] == 'publisher' and endpoint['topic'] in topics:
                require(endpoint['topic'] not in publishers, 'multiple_owned_transport_publisher')
                publishers[endpoint['topic']] = endpoint['gid']
    observed = {topic: [] for topic in topics}
    for ordinal, row in enumerate(transport, 1):
        require(row['type'] == 'transport_message' and row['ordinal'] == ordinal and row['topic'] in topics and
                row['ros_type'] == topics[row['topic']] and row['publisher_gid'] == publishers[row['topic']] and
                row['serialization'] == 'cdr' and shape(row['payload_sha256']) and
                integer(row['serialized_bytes']) and row['serialized_bytes'] > 0, 'transport_row_identity_or_raw_payload_invalid')
        observed[row['topic']].append((row['payload_sha256'], row['serialized_bytes']))
    require(observed == raw_rows, 'whole_transport_sqlite_CDR_digest_length_sequences_differs')
    terminal = reader.json(run / 'synthetic_source/terminal.json')
    counts = {topic: len(rows) for topic, rows in observed.items()}
    require(terminal['normal_end'] is True and terminal['failed'] is False and terminal['run_id'] == run_id and
            terminal['transport_counts'] == counts and terminal['transport_total'] == sum(counts.values()),
            'synthetic_transport_terminal_counts_or_cleanliness_differs')
    physical = [owned['publisher']['effective_parameters'][key]['value']
                for key in ('vrx_left_thrust_topic', 'vrx_right_thrust_topic')]
    command_topics = [*physical, '/research/control/applied']
    require(len(set(command_topics)) == 3 and all(topic in topics for topic in command_topics), 'physical_applied_topics_missing')
    if mode == 'expired_release':
        require(set(session['streams']) == {'applied', 'cycle', 'reference_prediction', 'state'} and
                all(row['generated'] == row['emitted'] == row['dropped'] == row['first_sequence'] == row['last_sequence'] == 0
                    for row in session['streams'].values()), 'expired_publisher_source_stream_not_all_zero')
        require(all(counts[topic] == 0 and storage['actual_counts'][topic] == 0 for topic in command_topics),
                'expired_actual_physical_or_Applied_output_present')
        require(all(value == 0 for value in terminal['published_counts'].values()), 'expired_sensor_start_published')
    after = reader.unchanged()
    require(reader.before == after and bag_inventory == sorted(str(p.relative_to(run / 'recorder/bag'))
            for p in (run / 'recorder/bag').rglob('*') if p.is_file()), 'input_or_bag_inventory_changed')
    return {'schema': SCHEMA, 'passed': True, 'run': str(run), 'run_id': run_id, 'mode': mode,
        'components': {'identity_and_source_build_pins': {'passed': True, 'roles': source_details},
            'actual_release_publication': publication_result, 'actual_gate_observation': gate_result,
            'source_session': session_result,
            'whole_transport_actual_SQLite': storage,
            'expired_no_output': {'applicable': mode == 'expired_release', 'passed': mode == 'expired_release',
                'physical_and_Applied_counts': {topic: counts[topic] for topic in command_topics}}},
        'normal_owned_atomic_Witness_qualification_checked_here': False, 'qualifications': QUALIFICATIONS,
        'input_sha256_before': reader.before, 'input_sha256_after': after, 'inputs_unchanged': True,
        'scope': 'closed bounded localhost actual positive or expired publisher component; exact captured original gate reads',
        'limits': ['prepared receipt is not Released or physical execution proof',
            'diagnostic lock behavior depends on pinned implementation and separate native concurrency tests',
            'command transport and SQLite absence/presence are not plant acknowledgments',
            'no true Master Clock, general Capability, strict full chain, phase or research qualification',
            'historical receipt timeout causes remain unknown'],
        'checker_sha256': digest(Path(__file__).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = analyze(args.run)
    except Exception as error:
        report = {'schema': SCHEMA, 'passed': False, 'run': str(args.run),
            'reader_error': type(error).__name__ + ': ' + str(error), 'qualifications': QUALIFICATIONS,
            'checker_sha256': digest(Path(__file__).read_bytes()), 'semantic_negative_pass': False}
    from owned_release import create_only_json
    create_only_json(args.output, report)
    print(json.dumps({'passed': report['passed'], 'output': str(args.output), 'reader_error': report.get('reader_error')}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
