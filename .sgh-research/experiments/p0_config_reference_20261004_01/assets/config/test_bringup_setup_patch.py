"""Guard and installed-package-layout smoke checks; real colcon gate is external."""

import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from apply_bringup_setup_patch import F3_SETUP_SHA256, patched_bytes


HERE = Path(__file__).resolve().parent
SYNTHETIC_SETUP = b'''from setuptools import setup\npackage_name = 'usv_bringup'\nsetup(name=package_name, packages=[], data_files=[('launch', ['a.launch.py'])])\n'''


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class SetupPackagePatch(unittest.TestCase):
    def test_single_setup_keyword_changed_and_other_fields_preserved(self):
        # On Ubuntu bind the actual immutable setup bytes, rather than the
        # already-patched production file. Local default uses the tiny fixture.
        source_root = os.environ.get("P0_TEST_SOURCE_ROOT")
        raw = (Path(source_root) / "usv_bringup/setup.py").read_bytes() if source_root else SYNTHETIC_SETUP
        expected_sha = F3_SETUP_SHA256 if source_root else digest(SYNTHETIC_SETUP)
        result = patched_bytes(raw, expected_sha)
        self.assertEqual(result, raw.replace(b'packages=[]', b'packages=[package_name]'))
        ast.parse(result)

    def test_wrong_hash_duplicate_anchor_and_reapply_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA256"):
            patched_bytes(SYNTHETIC_SETUP + b'\n', digest(SYNTHETIC_SETUP))
        duplicate = SYNTHETIC_SETUP + b'# packages=[]\n'
        with self.assertRaisesRegex(ValueError, "exactly once"):
            patched_bytes(duplicate, digest(duplicate))
        result = patched_bytes(SYNTHETIC_SETUP, digest(SYNTHETIC_SETUP))
        with self.assertRaisesRegex(ValueError, "already changed"):
            patched_bytes(result, digest(result))

    def test_wrong_package_and_multiple_setup_calls_rejected(self):
        wrong = SYNTHETIC_SETUP.replace(b'usv_bringup', b'other_package')
        with self.assertRaisesRegex(ValueError, "package_name"):
            patched_bytes(wrong, digest(wrong))
        multiple = SYNTHETIC_SETUP + b'setup()\n'
        with self.assertRaisesRegex(ValueError, "one setuptools"):
            patched_bytes(multiple, digest(multiple))

    def test_line_endings_preserved(self):
        crlf = SYNTHETIC_SETUP.replace(b'\n', b'\r\n')
        result = patched_bytes(crlf, digest(crlf))
        self.assertEqual(result, crlf.replace(b'packages=[]', b'packages=[package_name]'))

    def test_helper_imports_from_package_layout_without_working_tree_path(self):
        # This proves the proposed Python layout. It is not a colcon/install claim.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / 'usv_bringup'
            package.mkdir()
            for filename in ('__init__.py', 'research_config_sources.py'):
                (package / filename).write_bytes((HERE / filename).read_bytes())
            command = [sys.executable, '-I', '-c',
                       'import sys; sys.path.insert(0, sys.argv[1]); '
                       'import usv_bringup.research_config_sources as m; '
                       'assert len(m.VEHICLE_KEYS)==19; print(m.__file__)', str(root)]
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(package), result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
