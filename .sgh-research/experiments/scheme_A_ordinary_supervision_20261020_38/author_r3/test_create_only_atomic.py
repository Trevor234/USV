"""C3.4-A real publication edges; monkeypatches are test-only, no ROS."""
import errno
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

import owned_release as release


class CreateOnlyAtomic(unittest.TestCase):
    def setUp(self):
        parent = os.environ.get('C34_A_TEST_ROOT')
        self.temp = tempfile.TemporaryDirectory(prefix='c34-a-', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'release.json'
        self.value = {'value': 17, 'strict': True}

    def assert_no_temporary(self):
        self.assertEqual(list(self.root.glob('.release.json.*.tmp')), [])

    def test_success_single_link_and_mode(self):
        release.create_only_json(self.path, self.value)
        self.assertEqual(self.path.stat().st_nlink, 1)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(release.strict_json(self.path.read_bytes()), self.value)
        self.assert_no_temporary()

    def test_eexist_keeps_original_bytes_and_inode(self):
        release.create_only_json(self.path, self.value)
        before = self.path.read_bytes(), self.path.stat().st_ino
        with self.assertRaises(FileExistsError) as caught:
            release.create_only_json(self.path, {'changed': 18})
        self.assertEqual(caught.exception.errno, errno.EEXIST)
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_ino), before)
        self.assert_no_temporary()

    def test_target_visible_single_link_while_directory_fsync_waits(self):
        native = os.fsync
        reached, resume = threading.Event(), threading.Event()
        results = []
        def barrier(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                reached.set()
                if not resume.wait(5):
                    raise TimeoutError('test directory fsync barrier')
            return native(fd)
        def write():
            try:
                results.append(release.create_only_json(self.path, self.value))
            except BaseException as error:
                results.append(error)
        with patch.object(release.os, 'fsync', barrier):
            worker = threading.Thread(target=write)
            worker.start()
            try:
                self.assertTrue(reached.wait(5))
                self.assertTrue(worker.is_alive())
                self.assertEqual(self.path.stat().st_nlink, 1)
                self.assertEqual(release.strict_json(self.path.read_bytes()), self.value)
                self.assert_no_temporary()
            finally:
                resume.set()
                worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], str)

    def test_directory_fsync_error_keeps_visible_target_and_original_cause(self):
        native = os.fsync
        error = OSError(errno.EIO, 'injected directory fsync error')
        def fail(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise error
            return native(fd)
        with patch.object(release.os, 'fsync', fail):
            with self.assertRaises(release.PublicationAmbiguousError) as caught:
                release.create_only_json(self.path, self.value)
        self.assertIs(caught.exception.__cause__, error)
        self.assertTrue(caught.exception.target_visible)
        self.assertEqual(self.path.stat().st_nlink, 1)
        self.assertEqual(release.strict_json(self.path.read_bytes()), self.value)
        self.assert_no_temporary()

    def test_file_fsync_failure_keeps_target_absent(self):
        original = OSError(errno.EIO, 'injected file fsync error')
        with patch.object(release.os, 'fsync', side_effect=original):
            with self.assertRaises(OSError) as caught:
                release.create_only_json(self.path, self.value)
        self.assertIs(caught.exception, original)
        self.assertFalse(self.path.exists())
        self.assert_no_temporary()

    def test_write_failure_keeps_target_absent(self):
        original = OSError(errno.ENOSPC, 'injected write error')
        with patch.object(release.os, 'write', side_effect=original):
            with self.assertRaises(OSError) as caught:
                release.create_only_json(self.path, self.value)
        self.assertIs(caught.exception, original)
        self.assertFalse(self.path.exists())
        self.assert_no_temporary()

    def test_cleanup_failure_does_not_replace_original_error(self):
        original = OSError(errno.ENOSPC, 'injected write error')
        with patch.object(release.os, 'write', side_effect=original), \
             patch.object(release.os, 'unlink', side_effect=OSError(errno.EACCES, 'cleanup error')):
            with self.assertRaises(OSError) as caught:
                release.create_only_json(self.path, self.value)
        self.assertIs(caught.exception, original)
        self.assertFalse(self.path.exists())

    def test_preexisting_temporary_not_deleted_on_exclusive_create_failure(self):
        temporary = self.root / ('.release.json.' + 'a' * 32 + '.tmp')
        temporary.write_bytes(b'preexisting evidence')
        with patch.object(release.secrets, 'token_hex', return_value='a' * 32):
            with self.assertRaises(FileExistsError):
                release.create_only_json(self.path, self.value)
        self.assertEqual(temporary.read_bytes(), b'preexisting evidence')
        self.assertFalse(self.path.exists())

    def test_symlink_target_and_parent_rejected(self):
        target = self.root / 'original'
        target.write_bytes(b'original')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            release.create_only_json(self.path, self.value)
        self.assertEqual(target.read_bytes(), b'original')
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            release.create_only_json(alias / 'new.json', self.value)
        self.assertFalse((self.root / 'new.json').exists())

    def test_fifo_not_overwritten(self):
        os.mkfifo(self.path)
        inode = self.path.stat().st_ino
        with self.assertRaises(FileExistsError):
            release.create_only_json(self.path, self.value)
        self.assertTrue(stat.S_ISFIFO(self.path.stat().st_mode))
        self.assertEqual(self.path.stat().st_ino, inode)
        self.assert_no_temporary()

    def test_hardlinked_target_not_overwritten(self):
        other = self.root / 'other'
        other.write_bytes(b'original hardlinked data')
        os.link(other, self.path)
        with self.assertRaises(FileExistsError):
            release.create_only_json(self.path, self.value)
        self.assertEqual(self.path.read_bytes(), other.read_bytes())
        self.assertEqual(self.path.stat().st_nlink, 2)
        self.assert_no_temporary()

    def test_unsupported_rename_fails_before_publication(self):
        with patch.object(release, '_renameat2', None):
            with self.assertRaises(OSError) as caught:
                release.create_only_json(self.path, self.value)
        self.assertEqual(caught.exception.errno, errno.ENOSYS)
        self.assertFalse(self.path.exists())
        self.assert_no_temporary()

    def test_original_output_size_and_nonfinite_limits_preserved(self):
        with self.assertRaises(ValueError):
            release.create_only_json(self.path, {'huge': 'x' * release.MAX_JSON})
        with self.assertRaises(ValueError):
            release.create_only_json(self.path, {'value': float('inf')})
        self.assertFalse(self.path.exists())

    def test_strict_json_rejects_float_overflow_and_duplicate_keys(self):
        for raw in (b'{"value":1e309}', b'{"value":-1e309}', b'{"value":NaN}',
                    b'{"value":Infinity}', b'{"value":-Infinity}', b'{"a":1,"a":2}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                release.strict_json(raw)
        self.assertEqual(release.strict_json(b'{"value":1e308}'), {'value': 1e308})
        self.assertEqual(release.strict_json(b'{"value":-0.0}'), {'value': -0.0})


if __name__ == '__main__':
    unittest.main()
