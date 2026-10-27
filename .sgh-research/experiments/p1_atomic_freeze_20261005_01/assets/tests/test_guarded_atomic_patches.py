"""Unit tests of append-only guards, not a claim that ROS GTests ran on Windows."""
import hashlib
from pathlib import Path
import tempfile
import unittest

import apply_atomic_tests as atomic
import apply_deadline_fixture as deadline


def fixture(newline="\n"):
    # Minimal synthetic text validates insertion guards only. Actual C++ cases
    # use the installed ROS node and the verified F4 fixture on Ubuntu.
    return newline.join([
        "#include <condition_variable>", "namespace usv_mpc {",
        "class MpcControllerNodeTestAccess { public:",
        "void reference_solver(); void reference_path_version(); void reference_profile_version();",
        "}; }", "namespace {", "class ResearchContract {};",
        "class ReferenceEvidenceSolver {};", "class ReferencePredictionContract {};",
        "// P0_REFERENCE_PREDICTION_TEST_CASES_V1", "}  // namespace", ""]).encode()


def deadline_fixture(newline="\n"):
    return newline.join([
        "class MpcControllerNodeTestAccess {", "void make() {",
        "node->max_solve_time_ms_ = 200.0;", "    " + deadline.OLD,
        "return node; }", "void run() { node.run_dynamic_mpc_(); }", "};",
        "class DeadlineControl {};", ""]).encode()


class GuardedPatches(unittest.TestCase):
    def test_atomic_appends_five_real_node_tests_and_preserves_existing_bytes(self):
        for newline in ("\n", "\r\n"):
            raw = fixture(newline)
            new = atomic.prepare(raw)
            self.assertEqual(new.count(b"TEST_F(AtomicFreezeContract,"), 5)
            self.assertIn(b"node.can_solve_()", new)
            self.assertIn(b"node.run_dynamic_mpc_()", new)
            self.assertIn(b"node.path_callback_(msg)", new)
            text = new.decode()
            access = (atomic.HERE / "atomic_access.inc").read_text(encoding="utf-8")
            cases = (atomic.HERE / "atomic_tests.inc").read_text(encoding="utf-8")
            text = text.replace(newline + access.replace("\n", newline), "", 1)
            text = text.replace(newline + cases.replace("\n", newline) + newline, "", 1)
            self.assertEqual(text.encode(), raw)

    def test_atomic_rejects_reapplication_missing_fixture_and_duplicate_anchor(self):
        raw = fixture()
        for bad in (atomic.prepare(raw), raw.replace(b"class ResearchContract", b"class Missing"),
                    raw + b"\n} // namespace\n"):
            with self.assertRaises(ValueError):
                atomic.prepare(bad)

    def test_atomic_dry_run_hash_and_create_only_backup(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test_research_contract.cpp"
            raw = fixture()
            path.write_bytes(raw)
            sha = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(ValueError):
                atomic.apply(path, "0" * 64, True)
            self.assertEqual(path.read_bytes(), raw)
            self.assertFalse(atomic.apply(path, sha)["written"])
            self.assertEqual(path.read_bytes(), raw)
            report = atomic.apply(path, sha, True)
            self.assertEqual(Path(report["backup"]).read_bytes(), raw)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), report["after_sha256"])
            with self.assertRaises(ValueError):
                atomic.apply(path, report["after_sha256"], True)

    def test_deadline_only_replaces_the_original_fixture_assignment(self):
        for newline in ("\n", "\r\n"):
            raw = deadline_fixture(newline)
            new = deadline.prepare(raw)
            self.assertNotIn(b"node->reference_path_ =", new)
            self.assertIn(b"node->odom_callback_(state)", new)
            self.assertIn(b"node->path_callback_(path)", new)
            self.assertIn(b"node->require_fcu_state_ = false", new)
            self.assertIn(b"node->odom_timeout_s_ = 0.0", new)
            self.assertTrue(new.endswith(b"class DeadlineControl {};" + newline.encode()))
            self.assertEqual(new.count(deadline.MARKER.encode()), 1)

    def test_deadline_rejects_duplicate_assignment_and_repeat(self):
        raw = deadline_fixture()
        for bad in (deadline.prepare(raw), raw + deadline.OLD.encode()):
            with self.assertRaises(ValueError):
                deadline.prepare(bad)

    def test_deadline_actual_hash_guard_and_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test_deadline_control.cpp"
            raw = deadline_fixture()
            path.write_bytes(raw)
            sha = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(ValueError):
                deadline.apply(path, deadline.F4_DEADLINE_SHA256, True)
            self.assertEqual(path.read_bytes(), raw)
            report = deadline.apply(path, sha, False)
            self.assertFalse(report["written"])
            self.assertEqual(path.read_bytes(), raw)
            report = deadline.apply(path, sha, True)
            self.assertEqual(Path(report["backup"]).read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
