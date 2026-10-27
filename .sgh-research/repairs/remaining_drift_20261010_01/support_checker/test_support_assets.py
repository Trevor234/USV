#!/usr/bin/env python3
"""Run real filesystem fixtures. No ROS imports, nodes, or remote operations."""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).with_name("check_support_assets.py")
SPEC = importlib.util.spec_from_file_location("support_asset_checker_under_test", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
ROOT = None
CASE_RESULTS = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_asset(path):
    return {"path": str(path.absolute()), "type": "file",
            "resolved_path": str(path.resolve(strict=True)),
            "link_target": None, "sha256": digest(path)}


def link_asset(path, is_directory=False):
    return {"path": str(path.absolute()),
            "type": "symlink_directory" if is_directory else "symlink_file",
            "resolved_path": str(path.resolve(strict=True)),
            "link_target": os.readlink(path),
            "sha256": None if is_directory else digest(path)}


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / self._testMethodName
        self.folder.mkdir()
        self.original = self.folder / "module.py"
        self.original.write_bytes(b"A_FIXED_MODULE = 1\n")
        self.manifest = self.folder / "manifest.json"

    def declare(self, assets):
        document = {"schema": CHECKER.MANIFEST_SCHEMA, "scope": CHECKER.SCOPE,
                    "version": "fixture_fixed_expected_v1", "assets": assets}
        with self.manifest.open("xb") as stream:
            stream.write((json.dumps(document, sort_keys=True, indent=2) + "\n").encode())
        self.manifest_before = self.manifest.read_bytes()
        self.manifest_sha = digest(self.manifest)
        return document

    def observe(self, expected_code=None, expected_pass=False):
        result = CHECKER.check_manifest(self.manifest, self.manifest_sha)
        self.assertEqual(result["support_assets_match"], expected_pass)
        if expected_code:
            self.assertIn(expected_code, {entry["code"] for entry in result["failures"]})
        self.assertEqual(self.manifest.read_bytes(), self.manifest_before,
                         "Checker must never repair or refresh expected values")
        self.assertNotIn("global_release_passed", result)
        CASE_RESULTS.append({"test": self._testMethodName, "passed": True,
                             "expected_support_assets_match": expected_pass,
                             "checker_result": result})
        return result

    def make_link(self, path, target, is_directory=False):
        # Failure to create a real symlink is a test failure, never a silent skip.
        os.symlink(str(target), path, target_is_directory=is_directory)

    def test_01_fixed_regular_file_passes(self):
        self.declare([file_asset(self.original)])
        self.observe(expected_pass=True)

    def test_02_fixed_real_symlink_passes(self):
        link = self.folder / "import_module.py"
        self.make_link(link, self.original)
        self.declare([link_asset(link)])
        self.observe(expected_pass=True)

    def test_03_fixed_real_directory_symlink_passes(self):
        target = self.folder / "package_target"
        target.mkdir()
        link = self.folder / "package_link"
        self.make_link(link, target, True)
        self.declare([link_asset(link, True)])
        self.observe(expected_pass=True)

    def test_04_file_content_change_fails(self):
        self.declare([file_asset(self.original)])
        self.original.write_bytes(b"A_FIXED_MODULE = 2\n")
        self.observe("asset_sha256_mismatch")

    def test_05_file_deletion_fails(self):
        self.declare([file_asset(self.original)])
        self.original.unlink()
        self.observe("asset_missing")

    def test_06_file_replaced_by_directory_fails(self):
        self.declare([file_asset(self.original)])
        self.original.unlink()
        self.original.mkdir()
        self.observe("asset_type_mismatch")

    def test_07_equal_content_link_redirect_fails(self):
        replacement = self.folder / "equal_content_module.py"
        replacement.write_bytes(self.original.read_bytes())
        link = self.folder / "import_module.py"
        self.make_link(link, self.original)
        self.declare([link_asset(link)])
        self.assertEqual(digest(replacement), digest(self.original))
        link.unlink()
        self.make_link(link, replacement)
        result = self.observe("asset_link_target_mismatch")
        self.assertIn("asset_resolved_path_mismatch", {x["code"] for x in result["failures"]})
        self.assertNotIn("asset_sha256_mismatch", {x["code"] for x in result["failures"]})

    def test_08_link_target_deleted_fails(self):
        link = self.folder / "import_module.py"
        self.make_link(link, self.original)
        self.declare([link_asset(link)])
        self.original.unlink()
        self.observe("asset_broken_symlink")

    def test_09_link_deleted_fails(self):
        link = self.folder / "import_module.py"
        self.make_link(link, self.original)
        self.declare([link_asset(link)])
        link.unlink()
        self.observe("asset_missing")

    def test_10_parent_link_equal_content_redirect_fails(self):
        target = self.folder / "target_one"
        other = self.folder / "target_two"
        target.mkdir()
        other.mkdir()
        (target / "helper.py").write_bytes(self.original.read_bytes())
        (other / "helper.py").write_bytes(self.original.read_bytes())
        parent = self.folder / "package"
        self.make_link(parent, target, True)
        child = parent / "helper.py"
        self.declare([file_asset(child)])
        parent.unlink()
        self.make_link(parent, other, True)
        self.observe("asset_resolved_path_mismatch")

    def test_11_raw_link_spelling_change_fails(self):
        # The resolved target/content stays identical; raw link contract changes.
        link = self.folder / "import_module.py"
        self.make_link(link, self.original)
        self.declare([link_asset(link)])
        link.unlink()
        self.make_link(link, Path(self.original.name))
        result = self.observe("asset_link_target_mismatch")
        self.assertNotIn("asset_resolved_path_mismatch", {x["code"] for x in result["failures"]})

    def test_12_expected_manifest_binding_change_fails(self):
        document = self.declare([file_asset(self.original)])
        # Simulate someone refreshing expected after the caller fixed its digest.
        document = copy.deepcopy(document)
        self.original.write_bytes(b"A_FIXED_MODULE = 999\n")
        document["assets"][0]["sha256"] = digest(self.original)
        self.manifest.write_text(json.dumps(document), encoding="utf-8")
        changed_bytes = self.manifest.read_bytes()
        result = CHECKER.check_manifest(self.manifest, self.manifest_sha)
        self.assertFalse(result["support_assets_match"])
        self.assertIn("manifest_sha256_mismatch", {x["code"] for x in result["failures"]})
        self.assertEqual(self.manifest.read_bytes(), changed_bytes)
        CASE_RESULTS.append({"test": self._testMethodName, "passed": True,
                             "expected_support_assets_match": False, "checker_result": result})

    def test_13_relative_path_manifest_rejected(self):
        asset = file_asset(self.original)
        asset["path"] = "module.py"
        self.declare([asset])
        self.observe("manifest_invalid")

    def test_14_wrong_scope_manifest_rejected(self):
        document = {"schema": CHECKER.MANIFEST_SCHEMA, "scope": "FULL_SIMULATION",
                    "version": "fixture_invalid", "assets": [file_asset(self.original)]}
        self.manifest.write_text(json.dumps(document), encoding="utf-8")
        self.manifest_before = self.manifest.read_bytes()
        self.manifest_sha = digest(self.manifest)
        self.observe("manifest_invalid")

    def test_15_cli_failure_exit_code_and_json(self):
        self.declare([file_asset(self.original)])
        self.original.write_bytes(b"CLI_NEGATIVE = True\n")
        completed = subprocess.run([sys.executable, "-B", str(SCRIPT), str(self.manifest),
                                    "--expected-manifest-sha256", self.manifest_sha],
                                   capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertFalse(result["support_assets_match"])
        self.assertIn("asset_sha256_mismatch", {x["code"] for x in result["failures"]})
        self.assertEqual(self.manifest.read_bytes(), self.manifest_before)
        CASE_RESULTS.append({"test": self._testMethodName, "passed": True,
                             "expected_support_assets_match": False, "checker_result": result})


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    args = parser.parse_args()
    ROOT = Path(args.run_directory).absolute()
    allowed = Path(__file__).parent.resolve(strict=True)
    if not ROOT.is_relative_to(allowed):
        parser.error("Fixture directory must remain within this review directory")
    ROOT.mkdir(parents=False, exist_ok=False)
    runner = unittest.TextTestRunner(verbosity=2)
    outcome = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(CheckerTests))
    report = {"schema": "sim-shared-support-checker-fixture-result/v1", "scope": CHECKER.SCOPE,
              "checker_sha256": digest(SCRIPT), "test_script_sha256": digest(Path(__file__)),
              "run_directory": str(ROOT), "tests_run": outcome.testsRun,
              "failures": len(outcome.failures), "errors": len(outcome.errors),
              "skipped": len(outcome.skipped), "all_fixture_tests_passed": outcome.wasSuccessful(),
              "details": CASE_RESULTS,
              "test_failures": [{"test": str(test), "traceback": tb}
                                for test, tb in outcome.failures + outcome.errors],
              "remote_operations": False, "ROS_nodes_started": False,
              "fixture_paths_retained": True}
    output = ROOT / "test_results.json"
    with output.open("xb") as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"path": str(output), "sha256": digest(output),
                      "tests_run": outcome.testsRun, "passed": outcome.wasSuccessful()}))
    return 0 if outcome.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
