"""Targeted semantic tests for independent C3.3 release evidence checking."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import yaml
import check_release_observation_v1 as check


class GateObservation(unittest.TestCase):
    def setUp(self):
        self.release = {'run_id': 'r-publisher', 'producer_instance_id': 'r-publisher:p',
            'release_nonce': '1' * 32, 'startup_manifest_sha256': '2' * 64,
            'valid_until_steady_ns': 3_000_000_100}
        self.raw = json.dumps(self.release).encode()
        self.event = {'schema': 'p1-release-create-only-call/v1', 'release_path': '/tmp/release.json',
            **self.release, 'call_start_steady_ns': 90, 'call_end_steady_ns': 200,
            'completed': True, 'error_type': None, 'error': None,
            'release_sha256': check.digest(self.raw),
            'publication_state': 'visible; create-only call and directory fsync completed'}
        self.gate = {'gate_state': 'Released', 'failure_phase': 'none', 'failure_reason': '',
            'failure_steady_ns': None, 'last_phase': 'in_memory_commit', 'release_read_completed': True,
            'release_present_at_last_completed_read': True, 'release_bytes_count': len(self.raw),
            'poll_count': 3, 'missing_release_count': 2, 'released_integrity_verify_count': 0,
            'valid_until_steady_ns': self.release['valid_until_steady_ns'],
            'business_policy_changed': False, 'observation_qualifies_physical_release': False,
            'release_read_start_steady_ns': 95, 'release_read_end_steady_ns': 100,
            'validate_now_ns': 110, 'arm_start_steady_ns': 115, 'arm_end_steady_ns': 120,
            'attempt_now_ns': 125, 'receipt_io_start_steady_ns': 135, 'receipt_io_end_steady_ns': 145,
            'final_freshness_now_ns': 150, 'commit_steady_ns': 155, 'original_freshness_read_count': 3,
            'receipt_io_completed': True, 'release_file_sha256': check.digest(self.raw),
            'accepted_release_sha256': check.digest(self.raw)}

    def positive(self):
        return check.check_gate(self.gate, self.release, self.raw, self.event, 300, 'positive')

    def expired(self):
        self.release['valid_until_steady_ns'] = 89
        self.raw = json.dumps(self.release).encode()
        self.gate.update(gate_state='Fault', failure_phase='release_parse_and_validation',
            last_phase='release_parse_and_validation', failure_reason='release expired or validity exceeds 60 seconds',
            failure_steady_ns=115, valid_until_steady_ns=89, original_freshness_read_count=1,
            receipt_io_completed=False, release_bytes_count=len(self.raw))
        for key in ('attempt_now_ns', 'final_freshness_now_ns', 'arm_start_steady_ns', 'arm_end_steady_ns',
                    'receipt_io_start_steady_ns', 'receipt_io_end_steady_ns', 'commit_steady_ns',
                    'accepted_release_sha256', 'release_file_sha256'):
            self.gate[key] = None
        return check.check_gate(self.gate, self.release, self.raw, self.event, 300, 'expired_release')

    def test_positive_validation_before_driver_return_is_valid(self):
        self.assertLess(self.gate['validate_now_ns'], self.event['call_end_steady_ns'])
        self.assertTrue(self.positive()['passed'])

    def test_prepared_receipt_without_released_commit_cannot_pass(self):
        self.gate['gate_state'] = 'Held'
        self.gate['commit_steady_ns'] = None
        with self.assertRaisesRegex(ValueError, 'positive_gate_not_released_cleanly'):
            self.positive()

    def test_postreceipt_expired_gate_cannot_be_called_positive(self):
        self.gate['final_freshness_now_ns'] = self.release['valid_until_steady_ns']
        with self.assertRaisesRegex(ValueError, 'positive_actual_freshness_values_invalid'):
            self.positive()

    def test_actual_expiry_one_read_and_unread_nulls_pass(self):
        self.assertTrue(self.expired()['passed'])

    def test_expired_fixture_cannot_invent_second_clock_read(self):
        self.expired()
        self.gate['attempt_now_ns'] = 110
        with self.assertRaisesRegex(ValueError, 'expired_invents_unread_or_uncommitted_evidence'):
            check.check_gate(self.gate, self.release, self.raw, self.event, 300, 'expired_release')

    def test_expired_wrong_failure_phase_is_semantic_failure(self):
        self.expired()
        self.gate['failure_phase'] = 'receipt_io'
        with self.assertRaisesRegex(ValueError, 'expired_actual_fault_reason_or_phase_differs'):
            check.check_gate(self.gate, self.release, self.raw, self.event, 300, 'expired_release')

    def test_wrong_release_digest_is_semantic_failure(self):
        self.gate['accepted_release_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'positive_receipt_or_accepted_hash_differs'):
            self.positive()

    def test_completed_publication_exact_digest_and_interval_pass(self):
        self.assertTrue(check.check_event(self.event, Path('/tmp/release.json'), self.release,
            self.raw, '2' * 64, 80)['passed'])

    def test_ambiguous_visible_IO_is_failed_input(self):
        self.event.update(completed=False, error_type='PublicationAmbiguousError',
            error='directory fsync', publication_state='visible; directory durability unconfirmed',
            ambiguous_content_sha256=check.digest(self.raw))
        with self.assertRaisesRegex(ValueError, 'publication_call_failed_ambiguous_or_digest_differs'):
            check.check_event(self.event, Path('/tmp/release.json'), self.release, self.raw, '2' * 64, 80)

    def test_complete_publication_cannot_hide_IO_error(self):
        self.event['error_type'] = 'OSError'
        with self.assertRaisesRegex(ValueError, 'publication_call_failed_ambiguous_or_digest_differs'):
            check.check_event(self.event, Path('/tmp/release.json'), self.release, self.raw, '2' * 64, 80)


class OriginalUnarmedSession(unittest.TestCase):
    def setUp(self):
        self.startup = {'run_id': 'r-publisher', 'producer_instance_id': 'r-publisher:p'}
        self.session = {**self.startup, 'normal_end': False, 'flushed': True, 'queue_dropped_total': 0,
            'publish_errors': 0, 'end_steady_ns': 200, 'start_steady_ns': 0,
            'cycle_invocations_started': 0, 'interrupted_cycle_sequence': 0, 'streams': {}}

    def test_expiry_keeps_original_unarmed_normal_end_false(self):
        r = check.check_source_session(self.session, self.startup, 300, 'expired_release')
        self.assertTrue(r['passed']); self.assertFalse(r['normal_end'])
        self.assertFalse(r['normal_policy_qualified_by_this_check'])

    def test_unarmed_false_cannot_qualify_positive_normal_session(self):
        with self.assertRaisesRegex(ValueError, 'positive_publisher_session_not_normal'):
            check.check_source_session(self.session, self.startup, 300, 'positive')

    def test_expired_session_cannot_rewrite_normal_end_true(self):
        self.session['normal_end'] = True
        with self.assertRaisesRegex(ValueError, 'expired_publisher_session_not_original_unarmed_state'):
            check.check_source_session(self.session, self.startup, 300, 'expired_release')


class BoundedInputAndSQLite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='c33_release_checker_')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate_json_key'):
            check.strict_json(b'{"a":1,"a":2}')

    def test_symlink_and_special_input_refused(self):
        value = self.root / 'value'; value.write_text('{}')
        link = self.root / 'link'; link.symlink_to(value)
        with self.assertRaisesRegex(ValueError, 'input_symlink_forbidden'):
            check.Inputs().json(link)
        import os
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, 'input_not_bounded_regular_file'):
            check.Inputs().raw(fifo)

    def test_before_after_detects_mutation(self):
        p = self.root / 'value'; p.write_text('{"x":1}')
        reader = check.Inputs(); reader.json(p); p.write_text('{"x":2}')
        self.assertNotEqual(reader.before, reader.unchanged())

    def make_sqlite(self, with_message=False):
        bag = self.root / 'bag'; bag.mkdir()
        topics = {'/left': 'std_msgs/msg/Float64', '/right': 'std_msgs/msg/Float64',
            '/applied': 'usv_research_interfaces/msg/AppliedControl'}
        db = sqlite3.connect(bag / 'data.db3')
        db.execute('CREATE TABLE topics(id INTEGER PRIMARY KEY,name TEXT,type TEXT,serialization_format TEXT)')
        db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,topic_id INTEGER,data BLOB,timestamp INTEGER)')
        for i, (name, typ) in enumerate(topics.items(), 1):
            db.execute('INSERT INTO topics VALUES(?,?,?,?)', (i, name, typ, 'cdr'))
        if with_message:
            db.execute('INSERT INTO messages VALUES(1,1,?,1)', (b'actual_CDR_bytes',))
        db.commit(); db.close()
        metadata = {'rosbag2_bagfile_information': {'storage_identifier': 'sqlite3',
            'relative_file_paths': ['data.db3'], 'message_count': int(with_message),
            'topics_with_message_count': [{'topic_metadata': {'name': name, 'type': typ,
                'serialization_format': 'cdr'}, 'message_count': int(with_message and name == '/left')}
                for name, typ in topics.items()]}}
        (bag / 'metadata.yaml').write_text(yaml.safe_dump(metadata))
        return bag, topics

    def test_actual_SQLite_zero_messages_is_checked(self):
        bag, topics = self.make_sqlite()
        rows, report, _ = check.sqlite_storage(check.Inputs(), bag, topics)
        self.assertEqual(report['actual_counts'], {topic: 0 for topic in topics})
        self.assertTrue(all(value == [] for value in rows.values()))

    def test_actual_SQLite_message_preserves_digest_and_length(self):
        bag, topics = self.make_sqlite(with_message=True)
        rows, report, _ = check.sqlite_storage(check.Inputs(), bag, topics)
        self.assertEqual(rows['/left'], [(check.digest(b'actual_CDR_bytes'), len(b'actual_CDR_bytes'))])
        self.assertEqual(report['actual_counts']['/left'], 1)

    def test_SQLite_metadata_wrong_zero_count_fails(self):
        bag, topics = self.make_sqlite(with_message=True)
        p = bag / 'metadata.yaml'; data = yaml.safe_load(p.read_text())
        data['rosbag2_bagfile_information']['topics_with_message_count'][0]['message_count'] = 0
        p.write_text(yaml.safe_dump(data))
        with self.assertRaisesRegex(ValueError, 'sqlite_metadata_counts_not_conserved'):
            check.sqlite_storage(check.Inputs(), bag, topics)

    def test_SQLite_undeclared_artifact_fails(self):
        bag, topics = self.make_sqlite()
        (bag / 'extra').write_text('unclosed recorder artifact')
        with self.assertRaisesRegex(ValueError, 'sqlite_inventory_has_extra_or_missing_artifacts'):
            check.sqlite_storage(check.Inputs(), bag, topics)


if __name__ == '__main__':
    unittest.main()
