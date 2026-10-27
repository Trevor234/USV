"""Host-independent negative cases; no process or ROS execution."""

import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import owned_process_supervisor as ops
from run_no_output_calibration import source_observation


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.supervisor = ops.Supervisor.__new__(ops.Supervisor)
        self.supervisor.boot = "same-boot"
        self.supervisor.event = Mock()
        self.supervisor.cleanup_failed = False
        self.supervisor.evidence_failed = False
        self.supervisor.owned = {}
        self.child = ops.Owned("worker", SimpleNamespace(pid=1234, poll=Mock(return_value=None)),
                               {"pid": 1234, "start_ticks": 555}, io.BytesIO(), {1234: 555})

    def test_reused_leader_never_receives_signal(self):
        with patch.object(ops, "boot_id", return_value="same-boot"), \
             patch.object(ops, "proc_identity", return_value={"start_ticks": 556}), \
             patch.object(ops.os, "killpg", create=True) as kill:
            with self.assertRaisesRegex(RuntimeError, "PID was reused"):
                self.supervisor.send(self.child, 15)
            kill.assert_not_called()

    def test_foreign_session_never_receives_signal(self):
        foreign = {"pid": 1235, "pgid": 1234, "sid": 9999, "start_ticks": 666}
        with patch.object(ops, "boot_id", return_value="same-boot"), \
             patch.object(ops, "proc_identity", return_value={"start_ticks": 555}), \
             patch.object(ops, "proc_table", return_value=[foreign]), \
             patch.object(ops.os, "killpg", create=True) as kill:
            with self.assertRaisesRegex(RuntimeError, "foreign session"):
                self.supervisor.send(self.child, 15)
            kill.assert_not_called()

    def test_unrelated_group_is_excluded_from_target(self):
        member = {"pid": 1234, "pgid": 1234, "sid": 1234, "start_ticks": 555}
        other = {"pid": 9999, "pgid": 9999, "sid": 9999, "start_ticks": 777}
        with patch.object(ops, "boot_id", return_value="same-boot"), \
             patch.object(ops, "proc_identity", return_value={"start_ticks": 555}), \
             patch.object(ops, "proc_table", return_value=[member, other]), \
             patch.object(ops.os, "killpg", create=True) as kill:
            self.supervisor.send(self.child, 15)
            kill.assert_called_once_with(1234, 15)

    def test_postkill_timeout_is_terminal_cleanup_failure(self):
        self.supervisor.wait_empty = Mock(return_value=False)
        self.supervisor.send = Mock()
        self.supervisor.members = Mock(return_value=[{"pid": 1234}])
        with patch.object(ops.signal, "SIGKILL", 9, create=True):
            result = self.supervisor.stop(self.child, .5, 1., 1.)
        self.assertFalse(result["cleanup_complete"])
        self.assertTrue(self.supervisor.cleanup_failed)
        self.assertEqual([call.args[1] for call in self.supervisor.send.call_args_list], [2, 15, 9])
        self.assertEqual([call.args[1] for call in self.supervisor.wait_empty.call_args_list], [0, .5, 1., 1.])
        with self.assertRaisesRegex(RuntimeError, "spawning further children"):
            self.supervisor.spawn("second", [], {}, Path("."), "unused")

    def test_cleanup_rejects_unbounded_waits_before_signals(self):
        for duration in (float("nan"), float("inf"), -1, 60.01):
            self.supervisor.send = Mock()
            with self.assertRaises(ValueError):
                self.supervisor.stop(self.child, duration, 1., 1.)
            self.supervisor.send.assert_not_called()

    def test_truncated_source_tail_is_retained_without_completeness_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "worker.jsonl"
            source.write_text('{"type":"candidate"}\n{"type":"worker_sum', encoding="utf-8")
            observed = source_observation(source)
            self.assertEqual(observed["types"], {"candidate": 1})
            self.assertEqual(observed["parse_errors"][0]["line"], 2)
            self.assertFalse(observed["completeness_proven"])

    def test_ledger_failure_preserves_cleanup_path_and_forbids_new_launch(self):
        self.supervisor.ledger = Mock()
        self.supervisor.ledger.write.side_effect = OSError("disk full")
        self.supervisor.memory_tail = []
        self.supervisor.event = lambda kind, **kw: ops.Supervisor.event(self.supervisor, kind, **kw)
        ops.Supervisor.event(self.supervisor, "observation")
        self.assertTrue(self.supervisor.evidence_failed)
        self.assertFalse(self.supervisor.cleanup_failed)
        self.supervisor.wait_empty = Mock(return_value=True)
        self.supervisor.members = Mock(return_value=[])
        result = self.supervisor.stop(self.child, .5, 1., 1.)
        self.assertTrue(result["cleanup_complete"])
        with self.assertRaisesRegex(RuntimeError, "ledger failed"):
            self.supervisor.spawn("second", [], {}, Path("."), "unused")


if __name__ == "__main__":
    unittest.main()
