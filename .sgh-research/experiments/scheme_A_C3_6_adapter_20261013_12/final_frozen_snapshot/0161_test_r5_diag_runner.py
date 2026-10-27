"""C0 entry tests exercise gates and command construction without ROS/process launch."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

# Local B1 authorship contains only additions. A deployed runtime includes the
# unchanged baseline modules alongside them; fall back to the pinned local B0.
if importlib.util.find_spec("owned_process_supervisor") is None:
    sys.path.append(str(Path(__file__).resolve().parents[2] /
                        "m0b_contract_implementation_20261007" / "runtime"))
import run_r5_diag_validation as runner
from test_p1_witness import valid_witness, header


def arguments(**changes):
    result = runner.argument_parser().parse_args([
        "--contract", "contract.json", "--experiment-root", "experiments", "--run-id", "C0_test",
        "--diagnostic-bin", "p1_regulator_r5_diag", "--diagnostic-source", "regulator_r5_diag.cpp"])
    for k, v in changes.items():
        setattr(result, k, v)
    return result


class DiagnosticRunner(unittest.TestCase):
    def test_default_entry_is_normal_and_does_not_enable_witness_pause(self):
        args = arguments()
        runner.validate_normal_parameters(args)
        self.assertFalse(args.witness_enabled)
        self.assertIsNone(args.witness_file)
        self.assertEqual(args.test_sink_pause_ms, 0)
        self.assertEqual(args.duration, 10.)

    def test_every_fault_hook_rejected_before_directory_or_ros(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name in ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms",
                         "test_tick_block_ms", "test_sink_pause_ms"):
                with self.subTest(name=name):
                    args = arguments(experiment_root=Path(temporary), **{name: 1})
                    with self.assertRaisesRegex(ValueError, "R5 gate is not implemented"):
                        runner.run(args)
                    self.assertFalse((Path(temporary) / args.run_id).exists())

    def test_cli_refuses_positive_pause_even_for_fixture_child(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
            runner.main(["--contract", "contract.json", "--fixture-child",
                         "--fixture-source", "fixture.json", "--contract-hash", "a" * 64,
                         "--test-sink-pause-ms", "2000"])
        self.assertEqual(e.exception.code, 2)

    def test_witness_path_requires_enabled_and_explicit_ownership(self):
        for args in (arguments(witness_enabled=True),
                     arguments(witness_file=Path("witness.json")),
                     arguments(diagnostic_bin=None), arguments(diagnostic_source=None)):
            with self.assertRaises(ValueError):
                runner.validate_normal_parameters(args)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "C0_test"
            args = arguments(witness_enabled=True, witness_file=Path("witness.json"))
            self.assertEqual(runner.owned_witness_path(args, directory), directory / "witness.json")
            for value in (Path("../escape.json"), Path("subdir/witness.json"),
                          Path("runner_summary.json"), Path("witness_expected_header.json")):
                with self.subTest(path=value):
                    args.witness_file = value
                    with self.assertRaises(ValueError):
                        runner.owned_witness_path(args, directory)
            directory.mkdir()
            (directory / "existing.json").write_text("original")
            args.witness_file = Path("existing.json")
            with self.assertRaises(ValueError):
                runner.owned_witness_path(args, directory)
            self.assertEqual((directory / "existing.json").read_text(), "original")

    def test_dedicated_loader_requires_diag5_and_full_no_output_validator(self):
        full = Mock(return_value=({"schema": "p1-execution-contract-v2",
                                   "diagnostic_contract_revision": 5}, "a" * 64))
        module = SimpleNamespace(ContractError=ValueError, load_contract=full)
        with patch.dict(sys.modules, p1_full_contract=module):
            runner.load_contract(Path("contract.json"), "a" * 64)
            full.assert_called_once_with(Path("contract.json"), "a" * 64,
                                          mode="no_output", runtime=True)
            for c in ({"schema": "p1-execution-contract-v3"},
                      {"schema": "p1-execution-contract-v2", "diagnostic_contract_revision": 4}):
                full.return_value = (c, "a" * 64)
                with self.assertRaisesRegex(ValueError, "diag5"):
                    runner.load_contract(Path("contract.json"))

    def test_owned_capability_instance_is_verified_before_witness_header(self):
        args = arguments()
        contract = {"nominal_hash": "nominal", "fault_injection_enabled": True}
        cap = SimpleNamespace(schema_version="p1-worker-capability-v1", run_id=args.run_id,
            contract_hash="a" * 64, boot_id=header()["boot_id"], pid=123, backend="acados",
            fatal=False, clock_name="CLOCK_MONOTONIC", horizon_steps=20, prediction_dt=.2,
            matrix_layout="column_major", startup_ns=100,
            nominal_hash="nominal", fault_injection_enabled=True, worker_instance="b" * 64)
        self.assertEqual(runner.verify_worker_capability(cap, 123, args, contract,
                         "a" * 64, header()["boot_id"]), "b" * 64)
        for field, value in (("schema_version", "wrong"), ("pid", 124), ("pid", True),
                             ("worker_instance", "B" * 64), ("worker_instance", "unverified"),
                             ("run_id", "other"), ("contract_hash", "c" * 64),
                             ("fatal", True), ("fault_injection_enabled", False),
                             ("matrix_layout", "row_major"), ("startup_ns", 0),
                             ("startup_ns", -1), ("startup_ns", True), ("startup_ns", 100.),
                             ("startup_ns", 1 << 63)):
            with self.subTest(field=field, value=value):
                bad = copy.copy(cap)
                setattr(bad, field, value)
                with self.assertRaises(RuntimeError):
                    runner.verify_worker_capability(bad, 123, args, contract,
                                                     "a" * 64, header()["boot_id"])

    def test_regulator_command_contains_actual_ownership_pins_and_pause_zero(self):
        args = arguments(witness_enabled=True, witness_file=Path("witness.json"))
        binaries = {"regulator": {"path": "/owned/p1_regulator_r5_diag", "sha256": "c" * 64},
                    "worker": {"sha256": "d" * 64}}
        command = runner.diagnostic_regulator_command(args, ["--ros-args"], 123,
            {"regulator": Path("/owned/regulator_source.jsonl")}, binaries,
            Path("/source/regulator_r5_diag.cpp"), "e" * 64, Path("/owned/witness.json"), "f" * 64)
        self.assertEqual(command[0], "/owned/p1_regulator_r5_diag")
        for value in ("mode:=no_output", "worker_pid:=123", "test_sink_pause_ms:=0",
                      "witness_enabled:=true", "diagnostic_source_sha256:=" + "e" * 64,
                      "diagnostic_binary_sha256:=" + "c" * 64,
                      "worker_binary_sha256:=" + "d" * 64,
                      "witness_worker_instance:=" + "f" * 64):
            self.assertIn(value, command)
        args.witness_enabled = False
        off = runner.diagnostic_regulator_command(args, [], 123,
            {"regulator": Path("regulator.jsonl")}, binaries, Path("regulator_r5_diag.cpp"),
            "e" * 64, None, "f" * 64)
        self.assertIn("witness_enabled:=false", off)
        self.assertFalse(any(p.startswith("witness_file:=") for p in off))
        self.assertFalse(any(p.startswith("witness_worker_instance:=") for p in off))

    def test_header_is_constructed_from_driver_assets_not_witness_input(self):
        args = arguments()
        context = {"boot_id": header()["boot_id"], "contract_sha256": "1" * 64}
        binaries = {"regulator": {"sha256": "3" * 64}, "worker": {"sha256": "4" * 64}}
        expected = runner.independent_witness_header(args, context, binaries, "2" * 64, "5" * 64)
        self.assertEqual(expected, dict(header(), run_id=args.run_id))

    def test_terminal_witness_check_preserves_independent_gate_and_missing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = header()
            (directory / "witness_expected_header.json").write_text(json.dumps(expected))
            witness = directory / "witness.json"
            witness.write_text(json.dumps(valid_witness()))
            result = runner.terminal_witness_check(arguments(witness_enabled=True),
                                                   directory, witness, expected)
            self.assertTrue(result["passed"], result)
            self.assertFalse(result["expected_log_overflow_mechanism_passed"])
            self.assertFalse(result["source_join_verified"])
            self.assertTrue((directory / "witness_check.json").is_file())
            before = (directory / "witness_check.json").read_bytes()
            result = runner.terminal_witness_check(arguments(witness_enabled=True),
                                                   directory, witness, expected)
            self.assertFalse(result["passed"])
            self.assertFalse(result["report_write_succeeded"])
            self.assertEqual((directory / "witness_check.json").read_bytes(), before)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = runner.terminal_witness_check(arguments(witness_enabled=True),
                                                   directory, directory / "absent.json", None)
            self.assertFalse(result["passed"])
            self.assertEqual(result["issues"][0]["code"], "terminal_witness_unreadable")

    def test_witness_off_does_not_create_record_or_claim_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = runner.terminal_witness_check(arguments(), directory, None, None)
            self.assertIsNone(result["passed"])
            self.assertFalse(result["witness_complete"])
            self.assertFalse(list(directory.iterdir()))

    def test_expected_header_file_cannot_replace_driver_owned_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = header()
            modified = dict(expected, worker_instance="6" * 64)
            (directory / "witness_expected_header.json").write_text(json.dumps(modified))
            witness = directory / "witness.json"
            witness.write_text(json.dumps(valid_witness()))
            result = runner.terminal_witness_check(arguments(witness_enabled=True),
                                                   directory, witness, expected)
            self.assertFalse(result["passed"])
            self.assertIn("expected header changed", result["issues"][0]["detail"])

    def test_host_preflight_detects_diagnostic_and_its_fixture(self):
        item = {"pid": 2147483600, "state": "S", "exe": "/owned/executable", "start_ticks": 100}
        for command in (b'/owned/p1_regulator_r5_diag\0--ros-args\0',
                        b'/usr/bin/python3\0/owned/run_r5_diag_validation.py\0--fixture-child\0'):
            with self.subTest(command=command), patch.object(runner.sys, "platform", "linux"), \
                 patch.object(runner, "proc_table", return_value=[item]), \
                 patch.object(Path, "read_bytes", return_value=command):
                with self.assertRaisesRegex(RuntimeError, "prevents startup"):
                    runner.host_preflight()

    def test_normal_source_check_is_called_without_fault_reinterpretation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            def strict_main(argv):
                self.assertEqual(argv, ["--experiment", str(directory), "--bag", str(directory / "raw_bag"),
                    "--contract", str(Path("contract.json").resolve()),
                    "--context", str(directory / "run_context.json"),
                    "--output", str(directory / "normal_source_check")])
                output = directory / "normal_source_check"
                output.mkdir()
                (output / "contract_report.json").write_text(json.dumps({"passed": False,
                    "diagnostic_complete": False, "issues": [{"code": "actual_normal_failure"}]}))
                return 2
            module = SimpleNamespace(main=strict_main)
            with patch.dict(sys.modules, check_p1_execution=module):
                result = runner.normal_source_check(arguments(), directory)
            self.assertFalse(result["passed"])
            self.assertEqual(result["checker_returncode"], 2)
            self.assertFalse(result["expected_log_overflow_mechanism_passed"])

    def test_old_formal_runner_remains_byte_identical(self):
        dependency = importlib.util.find_spec("run_formal_no_output_validation")
        if dependency is not None and dependency.origin is not None:
            # Ubuntu's independent additions bind the original runtime through
            # its frozen PYTHONPATH rather than duplicating baseline modules.
            path = Path(dependency.origin)
        else:
            path = Path(__file__).resolve().parents[2] / "m0b_contract_implementation_20261007" / "runtime" / "run_formal_no_output_validation.py"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "d8098c64defe3b477363c94a959de29eb60c899039885ac13cfd3ce2f5da01cb")

    def test_declared_duration_requires_actual_complete_normal_window(self):
        window = {"started_ns": 100, "duration_s": 10., "expected_fault": "none"}
        before = runner.normal_window_completion(window, "declared_duration_elapsed", 10_000_000_099)
        self.assertFalse(before["normal_window_complete"])
        self.assertEqual(before["observed_duration_ns"], 9_999_999_999)
        finished = runner.normal_window_completion(window, "declared_duration_elapsed", 10_000_000_100)
        self.assertTrue(finished["normal_window_complete"])
        self.assertEqual(finished["required_duration_ns"], finished["observed_duration_ns"])
        # Even when source/audit independently pass, an operator interruption
        # cannot turn partial collection into a normal C0 window.
        interrupted = runner.normal_window_completion(window, "operator_stop", 5_000_000_100)
        self.assertFalse(interrupted["normal_window_complete"])
        self.assertFalse(runner.normal_collection_passed({"passed": True}, {"passed": True},
            True, interrupted, run_error_free=True, cleanup_complete=True,
            supervision_evidence_complete=True))
        self.assertTrue(runner.normal_collection_passed({"passed": True}, {"passed": True},
            True, finished, run_error_free=True, cleanup_complete=True,
            supervision_evidence_complete=True))

    def test_window_unknown_bad_types_fault_and_stop_reasons_are_incomplete(self):
        window = {"started_ns": 100, "duration_s": 10., "expected_fault": "none"}
        for reason in ("operator_stop", "worker_fatal", "startup_or_runtime_exception",
                       "owned_worker_active_watchdog", "not_started"):
            with self.subTest(reason=reason):
                self.assertFalse(runner.normal_window_completion(window, reason,
                    12_000_000_100)["normal_window_complete"])
        for changes in ({"started_ns": True}, {"started_ns": -1}, {"duration_s": True},
                        {"duration_s": float("nan")}, {"duration_s": float("inf")},
                        {"duration_s": 11}, {"expected_fault": "anything"}):
            with self.subTest(changes=changes):
                self.assertFalse(runner.normal_window_completion(dict(window, **changes),
                    "declared_duration_elapsed", 12_000_000_100)["normal_window_complete"])
        self.assertFalse(runner.normal_window_completion(None, "declared_duration_elapsed",
                                                         None)["normal_window_complete"])

    def test_postrun_keeps_independent_gates_and_runtime_failures_closed(self):
        complete = {"normal_window_complete": True}
        options = {"run_error_free": True, "cleanup_complete": True,
                   "supervision_evidence_complete": True}
        for source, audit in (({"passed": False}, {"passed": True}),
                              ({"passed": True}, {"passed": False})):
            self.assertFalse(runner.normal_collection_passed(source, audit, True, complete, **options))
        for field in options:
            self.assertFalse(runner.normal_collection_passed({"passed": True}, {"passed": True},
                True, complete, **dict(options, **{field: False})))
        self.assertTrue(runner.normal_collection_passed({"passed": True}, {"passed": None},
            False, complete, **options))


if __name__ == "__main__":
    unittest.main()
