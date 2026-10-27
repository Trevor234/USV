"""Actual create-only IO outcomes; no authority or plant qualification."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from owned_auth import publish_release_observed
from owned_release import PublicationAmbiguousError


class PublicationObservation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p1-c33-release-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'release.json'
        self.release = {'schema_version':'p1-D1-release-v1', 'run_id':'test-run',
                        'producer_instance_id':'test-producer',
                        'startup_manifest_sha256':'a'*64, 'release_nonce':'b'*32,
                        'valid_until_steady_ns':1234567}
        self.events = []

    def test_actual_success_binds_digest_and_unchanged_deadline(self):
        digest = publish_release_observed(self.path, self.release, self.events)
        self.assertEqual(digest, hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(json.loads(self.path.read_text()), self.release)
        e = self.events[0]
        self.assertTrue(e['completed'])
        self.assertEqual(e['release_sha256'], digest)
        self.assertEqual(e['valid_until_steady_ns'], 1234567)
        self.assertLessEqual(e['call_start_steady_ns'], e['call_end_steady_ns'])
        self.assertIsNone(e['error_type'])

    def test_duplicate_actual_call_preserves_first_bytes_and_exception(self):
        publish_release_observed(self.path, self.release, self.events)
        before = self.path.read_bytes()
        changed = {**self.release, 'release_nonce':'c'*32}
        with self.assertRaises(FileExistsError):
            publish_release_observed(self.path, changed, self.events)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.events), 2)
        self.assertFalse(self.events[1]['completed'])
        self.assertEqual(self.events[1]['error_type'], 'FileExistsError')
        self.assertIsNone(self.events[1]['release_sha256'])

    def test_actual_directory_fsync_failure_retains_visible_ambiguous_commit(self):
        native = os.fsync
        def directory_failure(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('declared directory durability failure')
            return native(fd)
        with patch('owned_release.os.fsync', side_effect=directory_failure):
            with self.assertRaises(PublicationAmbiguousError) as caught:
                publish_release_observed(self.path, self.release, self.events)
        self.assertTrue(self.path.exists())
        e = self.events[0]
        self.assertFalse(e['completed'])
        self.assertEqual(e['publication_state'], 'visible; directory durability unconfirmed')
        self.assertEqual(e['ambiguous_content_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(e['ambiguous_content_sha256'], caught.exception.content_sha256)
        self.assertIsNone(e['release_sha256'])

    def test_actual_prepublication_fsync_failure_never_claims_absence_from_exception(self):
        with patch('owned_release.os.fsync', side_effect=OSError('declared file IO failure')):
            with self.assertRaises(OSError):
                publish_release_observed(self.path, self.release, self.events)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.events[0]['completed'])
        self.assertEqual(self.events[0]['publication_state'], 'unknown; failure does not prove no publication')

    def test_original_exception_object_is_preserved(self):
        original = OSError('unique original exception')
        with patch('owned_auth.create_only_json', side_effect=original):
            try:
                publish_release_observed(self.path, self.release, self.events)
            except OSError as observed:
                self.assertIs(observed, original)
            else:
                self.fail('original IO exception was swallowed')
        self.assertEqual(self.events[0]['error'], str(original))

    def test_only_actual_create_call_is_measured_without_diagnostic_write(self):
        with patch('owned_auth.time.monotonic_ns', side_effect=[100,200]), \
             patch('owned_auth.create_only_json', return_value='d'*64) as operation:
            self.assertEqual(publish_release_observed(self.path, self.release, self.events), 'd'*64)
        operation.assert_called_once_with(self.path, self.release)
        self.assertEqual(self.events[0]['call_start_steady_ns'], 100)
        self.assertEqual(self.events[0]['call_end_steady_ns'], 200)
        self.assertEqual(self.events[0]['valid_until_steady_ns'], 1234567)

    def test_optional_observer_does_not_change_io_exception(self):
        with patch('owned_auth.create_only_json', side_effect=FileExistsError('existing')):
            with self.assertRaises(FileExistsError):
                publish_release_observed(self.path, self.release)


if __name__ == '__main__':
    unittest.main()
