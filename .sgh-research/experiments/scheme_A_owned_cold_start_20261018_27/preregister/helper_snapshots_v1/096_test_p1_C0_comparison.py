"""Compare honest full source/Witness lifecycles, including rejected attempts."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if importlib.util.find_spec("check_p1_witness") is None:
    sys.path.append(str(Path(__file__).resolve().parents[2] /
                        "m0b_witness_implementation_20261007" / "runtime"))
import check_p1_C0_comparison as checker
from test_p1_witness import header, valid_witness, phase, recalculate


def refresh_summary(events):
    summaries = [e for e in events if e.get("type") == "source_summary"]
    if summaries:
        summaries[0].update(generated=len(events) - 1, emitted=len(events) - 1)


def decision(row, sequence, source_end, ready=0, commit=None, accepted=False, reason="no_candidate"):
    return {"type": "decision", "schema": "p1-execution-decision-v2", "run_id": header()["run_id"],
        "boot_id": header()["boot_id"], "contract_hash": header()["contract_sha256"],
        "worker_instance": header()["worker_instance"], "mode": "no_output", "sequence": sequence,
        "tick": row["tick"], "job_id": row["job_id"], "task_generation": row["task_generation"],
        "model_generation": row["model_generation"], "config_generation": row["config_generation"],
        "schedule_generation": row["schedule_generation"], "epoch": row["clock_epoch"],
        "planned_ns": row["planned_ns"], "start_ns": row["start_ns"], "end_ns": source_end,
        "activation_commit_ns": commit or row["start_ns"] + 10, "ready_commit_ns": ready,
        "skipped_ticks": row["skipped_ticks"], "accepted": accepted, "reason": reason,
        "diagnostic_only": True, "normal_contract_complete": False}


def job_from_submit(row):
    return {"schema": "p1-solve-job-v1", "run_id": header()["run_id"],
        "boot_id": header()["boot_id"], "contract_hash": header()["contract_sha256"],
        "worker_instance": header()["worker_instance"], **{k: row[k] for k in checker.JOB_REQUIRED
                                                       if k in row}}


def fixture():
    w = valid_witness()
    w["tick"][0]["end_ns"] = 190
    w["tick"][1]["end_ns"] = 290
    w["phase"][-1]["ns"] = 310
    j = job_from_submit(w["submit"][0])
    events = [
        {"type": "startup", "schema": "p1-regulator-v1", "run_id": header()["run_id"],
         "boot": header()["boot_id"], "contract_hash": header()["contract_sha256"],
         "clock": "CLOCK_MONOTONIC", "mode": "no_output", "physical_publisher_endpoints": 0,
         "diagnostic_only": True},
        decision(w["tick"][0], 1, 140),
        {"type": "job", "job": j, "submit_commit_ns": 148, "publish_start_ns": 155},
        {"type": "job_publish_result", "job_id": 1, "publish_start_ns": 156, "publish_end_ns": 160, "success": True},
        {"type": "candidate_registration", "job": copy.deepcopy(j), "ready_commit_ns": 180,
         "accepted_registration": True},
        decision(w["tick"][1], 2, 240, ready=180, commit=220, accepted=True, reason=""),
        {"type": "regulator_shutdown", "last_decision_sequence": 2,
         "finished_ns": 295, "shutdown_grace_exceeded": False},
        {"type": "source_summary", "generated": 7, "emitted": 7, "dropped": 0,
         "normal_source_complete": True, "finished_ns": 300},
    ]
    context = {"schema": "p1-no-output-calibration-context-v1", "mode": "no_output",
        "run_id": header()["run_id"], "boot_id": header()["boot_id"],
        "contract_sha256": header()["contract_sha256"],
        "binaries": {"regulator": {"sha256": header()["binary_sha256"]},
                     "worker": {"sha256": header()["worker_binary_sha256"]}},
        "diagnostic_source": {"sha256": header()["source_sha256"]},
        "fixed_witness": {"enabled": True, "test_sink_pause_ms": 0},
        "declaration": {"duration_s": 10., "test_delay_ms": 0, "test_native_block_ms": 0,
                        "test_prepare_block_ms": 0, "test_tick_block_ms": 0,
                        "expected_fault": "none", "execute_qualified": False}}
    return w, events, context


def append_attempt(w, events, accepted=False, reason="shutdown", code=1):
    row = dict(w["tick"][1], sequence=3, tick=2, target_tick=2, job_id=2,
               planned_ns=300, start_ns=301, end_ns=390)
    w["tick"].append(row)
    submit = dict(w["submit"][0], sequence=2, tick=1, target_tick=2, job_id=2, commit_ns=250)
    w["submit"].append(submit)
    w["activation"].append(dict(w["activation"][0], sequence=2, tick=2, target_tick=2,
        job_id=2, commit_ns=320, ready_commit_ns=280, accepted=accepted, reason_code=code))
    w["phase"][-1]["ns"] = 410
    j = job_from_submit(submit)
    events[-2]["last_decision_sequence"] = 3
    events[-2]["finished_ns"] = 395
    events[-1]["finished_ns"] = 400
    events[-2:-2] = [
        {"type": "job", "job": j, "submit_commit_ns": 248, "publish_start_ns": 255},
        {"type": "job_publish_result", "job_id": 2, "publish_start_ns": 256, "publish_end_ns": 260, "success": True},
        {"type": "candidate_registration", "job": copy.deepcopy(j), "ready_commit_ns": 280,
         "accepted_registration": True},
        decision(row, 3, 340, ready=280, commit=320, accepted=accepted, reason=reason)]
    recalculate(w)
    refresh_summary(events)


class SourceWitnessComparison(unittest.TestCase):
    def setUp(self):
        self.w, self.events, self.context = fixture()

    def report(self):
        return checker.analyze(self.w, header(), self.events, self.context)

    def rejected(self, code=None):
        report = self.report()
        self.assertFalse(report["passed"], report)
        self.assertFalse(report["source_join_verified"])
        if code:
            self.assertIn(code, {i["code"] for i in report["issues"]}, report)
        return report

    def test_full_owned_lifecycle_exact_join_does_not_grant_other_gates(self):
        report = self.report()
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["source_join_verified"])
        self.assertEqual(report["run_id"], header()["run_id"])
        self.assertEqual(report["mode"], "no_output")
        self.assertEqual(report["counts"]["matched"], {"ticks": 2, "submits": 1, "activation_attempts": 1})
        self.assertEqual(report["observed_timestamp_differences_ns"]["tick_whole_minus_source_end_ns"], [50, 50])
        self.assertEqual(report["observed_timestamp_differences_ns"]["submit_authorized_minus_source_gate_sample_ns"], [2])
        self.assertFalse(report["lifecycle_window_clipped"])
        for field in ("source_bag_contract_complete", "normal_window_verified", "owned_process_lifecycle_verified",
                      "normal_contract_complete", "expected_log_overflow_mechanism_passed", "execute_qualified",
                      "C0_performance_comparison_verified", "all_worker_execution_gates_verified"):
            self.assertIs(report[field], False)

    def test_schedule_reset_repeated_numeric_tick_is_not_a_duplicate(self):
        row = dict(self.w["tick"][0], sequence=3, tick=0, schedule_generation=2,
                   clock_epoch=2, planned_ns=300, start_ns=301, end_ns=390)
        self.w["tick"].append(row)
        self.w["phase"][-1]["ns"] = 410
        self.events[-2]["last_decision_sequence"] = 3
        self.events[-2]["finished_ns"] = 395
        self.events[-1]["finished_ns"] = 400
        self.events.insert(-2, decision(row, 3, 340))
        recalculate(self.w)
        refresh_summary(self.events)
        self.assertTrue(self.report()["passed"], self.report())

    def test_every_rejected_attempt_is_compared_and_not_counted_as_accepted(self):
        append_attempt(self.w, self.events)
        self.assertTrue(self.report()["passed"], self.report())
        self.assertEqual(self.report()["counts"]["source_candidate_attempts"], 2)
        self.assertEqual(self.report()["counts"]["source_accepted_attempts"], 1)
        self.w["activation"].pop()
        recalculate(self.w)
        self.rejected("activation_bidirectional_coverage")

    def test_rejected_version_change_compares_current_decision_not_old_job(self):
        append_attempt(self.w, self.events, reason="version_mismatch", code=3)
        self.w["tick"][-1]["task_generation"] = 2
        self.w["activation"][-1]["task_generation"] = 2
        [d for d in self.events if d["type"] == "decision"][-1]["task_generation"] = 2
        self.assertTrue(self.report()["passed"], self.report())

    def test_reduced_reason_dictionary_has_exact_source_mapping(self):
        for reason, code in (("shutdown", 1), ("run_unusable_at_commit", 2),
                             ("worker_unusable", 3), ("version_mismatch", 3)):
            with self.subTest(reason=reason):
                self.w, self.events, self.context = fixture()
                append_attempt(self.w, self.events, reason=reason, code=code)
                self.assertTrue(self.report()["passed"], self.report())
                self.w["activation"][-1]["reason_code"] = 3 if code != 3 else 2
                self.rejected("activation_identity_time_or_result")

    def test_context_declares_exact_normal_policy_and_duration(self):
        cases = [({"mode": "execute"}, None), ({"schema": "unknown"}, None),
                 ({"enabled": False}, "fixed_witness"), ({"test_sink_pause_ms": 1}, "fixed_witness"),
                 ({"test_sink_pause_ms": False}, "fixed_witness"), ({"duration_s": True}, "declaration"),
                 ({"duration_s": 9.999}, "declaration"), ({"expected_fault": "R5"}, "declaration"),
                 ({"execute_qualified": True}, "declaration")]
        for changes, section in cases:
            with self.subTest(changes=changes, section=section):
                self.w, self.events, self.context = fixture()
                (self.context[section] if section else self.context).update(changes)
                report = self.rejected("context_pin_or_normal_declaration")
                self.assertFalse(report["context_verified"])

    def test_all_fault_parameters_require_actual_integer_zero(self):
        for field in ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms", "test_tick_block_ms"):
            for value in (False, 0., 1):
                with self.subTest(field=field, value=value):
                    self.w, self.events, self.context = fixture()
                    self.context["declaration"][field] = value
                    self.rejected("context_pin_or_normal_declaration")
        del self.context["declaration"]["test_delay_ms"]
        self.rejected("context_pin_or_normal_declaration")

    def test_independent_header_matches_context_and_actual_source_identity(self):
        for section, key in ((None, "run_id"), (None, "boot_id"), (None, "contract_sha256"),
                             ("diagnostic_source", "sha256")):
            with self.subTest(section=section, key=key):
                self.w, self.events, self.context = fixture()
                (self.context[section] if section else self.context)[key] = "6" * 64
                self.rejected("context_pin_or_normal_declaration")
        for role in ("regulator", "worker"):
            self.w, self.events, self.context = fixture()
            self.context["binaries"][role]["sha256"] = "6" * 64
            self.rejected("context_pin_or_normal_declaration")
        self.w, self.events, self.context = fixture()
        self.events[1]["worker_instance"] = "6" * 64
        self.rejected("source_decision_fields_or_types")

    def test_disabled_or_overflow_witness_never_proves_source_join(self):
        self.w["enabled"] = False
        self.rejected("basis_witness_incomplete")
        self.w, self.events, self.context = fixture()
        self.w["audit_complete"] = False
        self.w["overflow"] = self.w["incomplete"] = True
        self.w["first_failure"] = {"code": 1, "stream": 1, "ns": 300, "ticket": 257}
        self.w["counters"]["tick"].update(overflow=1, attempts=3)
        self.rejected("basis_witness_incomplete")

    def test_unsupported_pressure_phases_and_failed_snapshots_are_not_normal_case(self):
        for event in (1, 2, 3, 4, 6):
            with self.subTest(event=event):
                self.w, self.events, self.context = fixture()
                self.w["phase"].insert(1, phase(2, event, 300))
                self.w["phase"][-1]["sequence"] = 3
                recalculate(self.w)
                self.rejected("unsupported_normal_phase")
        self.w, self.events, self.context = fixture()
        self.w["activation"][0]["failed"] = True
        # This is normal-case exclusion, not an assertion of an illegal
        # acceptance derived from asynchronous snapshots.
        self.rejected("normal_case_failed_observation")

    def test_allowed_shutdown_invalidation_phase_and_unknown_state_preserved(self):
        self.w["phase"][1:1] = [phase(2, 5, 250), phase(3, 8, 251)]
        self.w["phase"][-1]["sequence"] = 4
        recalculate(self.w)
        self.assertTrue(self.report()["passed"], self.report())
        self.assertEqual(self.report()["basis_witness_check"]["phase_unknown_state_rows"], 4)

    def test_tick_identity_and_real_time_are_exact(self):
        for field in ("planned_ns", "start_ns", "task_generation", "model_generation",
                      "config_generation", "epoch", "skipped_ticks"):
            with self.subTest(field=field):
                self.w, self.events, self.context = fixture()
                self.events[1][field] += 1
                self.rejected("tick_identity_or_time")
        self.w, self.events, self.context = fixture()
        self.events[1]["end_ns"] = 191
        self.rejected("source_end_after_witness_whole_end")

    def test_submit_authorization_sampling_is_bracket_not_falsely_equal(self):
        self.assertTrue(self.report()["passed"], self.report())
        self.events[2]["submit_commit_ns"] = 151
        self.rejected("submit_authorization_time_bracket")
        self.w, self.events, self.context = fixture()
        self.events[2]["publish_start_ns"] = 149
        self.rejected("submit_authorization_time_bracket")

    def test_submit_job_versions_and_target_tick_are_exact(self):
        for field in ("target_tick", *checker.VERSIONS, "clock_epoch"):
            with self.subTest(field=field):
                self.w, self.events, self.context = fixture()
                self.events[2]["job"][field] += 1
                self.rejected("submit_identity")

    def test_activation_ready_commit_result_versions_are_exact(self):
        for field in ("activation_commit_ns", "ready_commit_ns", "task_generation", "epoch"):
            with self.subTest(field=field):
                self.w, self.events, self.context = fixture()
                self.events[5][field] += 1
                self.rejected("activation_identity_time_or_result")
        self.w, self.events, self.context = fixture()
        self.events[5].update(accepted=False, reason="shutdown")
        self.rejected("activation_identity_time_or_result")

    def test_true_job_source_and_exact_accepted_registration_required(self):
        self.events.pop(2)
        refresh_summary(self.events)
        self.rejected("submit_bidirectional_coverage")
        self.w, self.events, self.context = fixture()
        self.events[4]["accepted_registration"] = False
        self.rejected("activation_without_exact_source_registration")
        self.w, self.events, self.context = fixture()
        self.events[4]["ready_commit_ns"] += 1
        self.rejected("activation_without_exact_source_registration")

    def test_duplicate_decision_job_and_accepted_registration_fail(self):
        for index, code in ((1, "duplicate_source_tick"), (2, "duplicate_source_job"),
                            (4, "duplicate_accepted_registration")):
            with self.subTest(index=index):
                self.w, self.events, self.context = fixture()
                self.events.insert(-2, copy.deepcopy(self.events[index]))
                refresh_summary(self.events)
                self.rejected(code)

    def test_missing_extra_rows_in_either_stream_fail_bidirectional_coverage(self):
        self.events.pop(1)
        refresh_summary(self.events)
        self.rejected("tick_bidirectional_coverage")
        self.w, self.events, self.context = fixture()
        self.w["submit"].append(dict(self.w["submit"][0], sequence=2, job_id=2))
        recalculate(self.w)
        self.rejected("submit_bidirectional_coverage")
        self.w, self.events, self.context = fixture()
        self.events.insert(-1, {"type": "invented_extra"})
        refresh_summary(self.events)
        self.rejected("unsupported_source_event")

    def test_source_completion_drop_counts_types_and_terminal_order(self):
        for field, value in (("generated", 8), ("emitted", 6), ("dropped", 1),
                             ("normal_source_complete", 1), ("generated", True), ("finished_ns", 0)):
            with self.subTest(field=field):
                self.w, self.events, self.context = fixture()
                self.events[-1][field] = value
                self.rejected("normal_source_not_complete")
        self.w, self.events, self.context = fixture()
        self.events[-1], self.events[-2] = self.events[-2], self.events[-1]
        self.rejected("source_summary_not_last")

    def test_source_summary_shutdown_and_close_time_relationship(self):
        self.events[-1]["finished_ns"] = 311
        self.rejected("witness_closed_before_source_terminal_flush")
        self.w, self.events, self.context = fixture()
        self.events[-2]["finished_ns"] = 301
        self.rejected("source_shutdown_after_summary")
        self.w, self.events, self.context = fixture()
        self.events[-2]["last_decision_sequence"] = 1
        self.rejected("source_shutdown_not_complete")

    def test_missing_fields_wrong_integer_bool_domains_do_not_crash(self):
        for index, field in ((1, "job_id"), (2, "submit_commit_ns"), (4, "ready_commit_ns")):
            with self.subTest(index=index, field=field):
                self.w, self.events, self.context = fixture()
                del self.events[index][field]
                self.rejected()
        for field, value in (("tick", True), ("epoch", 1.), ("accepted", 1),
                             ("activation_commit_ns", float("inf")), ("sequence", 1 << 64)):
            self.w, self.events, self.context = fixture()
            self.events[1][field] = value
            self.rejected()


class ComparisonFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.witness = self.directory / "fixed_witness.json"
        self.expected = self.directory / "witness_expected_header.json"
        self.source = self.directory / "regulator_source.jsonl"
        self.context = self.directory / "run_context.json"
        self.output = self.directory / "C0_comparison.json"
        w, events, context = fixture()
        self.witness.write_text(json.dumps(w), encoding="utf-8")
        self.expected.write_text(json.dumps(header()), encoding="utf-8")
        self.context.write_text(json.dumps(context), encoding="utf-8")
        self.source.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")

    def invoke(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = checker.main(["--witness", str(self.witness), "--expected-header", str(self.expected),
                "--source", str(self.source), "--context", str(self.context), "--output", str(self.output)])
        return code, captured.getvalue()

    def test_create_only_cli_reports_input_hashes_and_full_scope(self):
        code, _ = self.invoke()
        self.assertEqual(code, 0)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(report["scope"], checker.SCOPE)
        self.assertTrue(report["raw_inputs_unchanged"])
        self.assertEqual(report["run_id"], header()["run_id"])
        self.assertEqual(report["input_sha256_before"], report["input_sha256_after"])
        self.assertEqual(len(report["input_sha256_before"]), 4)
        old = self.output.read_bytes()
        code, emitted = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("report_write_error", emitted)
        self.assertEqual(self.output.read_bytes(), old)

    def test_after_read_hash_exception_resets_any_previously_true_join(self):
        original = checker.sha256_file
        def fail_source_after_read(path):
            if Path(path) == self.source:
                raise OSError("source disappeared during final hash")
            return original(path)
        with patch.object(checker, "sha256_file", side_effect=fail_source_after_read):
            code, _ = self.invoke()
        self.assertEqual(code, 2)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertFalse(report["passed"])
        self.assertFalse(report["source_join_verified"])
        self.assertEqual(report["run_id"], header()["run_id"])
        self.assertFalse(report["raw_inputs_unchanged"])
        self.assertIn("reader_error", report)

    def test_changed_input_hash_fails_independent_join(self):
        original = checker.sha256_file
        def altered_hash(path):
            return "6" * 64 if Path(path) == self.source else original(path)
        with patch.object(checker, "sha256_file", side_effect=altered_hash):
            code, _ = self.invoke()
        self.assertEqual(code, 2)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertFalse(report["source_join_verified"])
        self.assertIn("raw_inputs_changed_during_read", {i["code"] for i in report["issues"]})

    def test_strict_source_raw_json_duplicate_nonfinite_utf8_and_unclosed_tail(self):
        cases = [b'{"type":"clock","x":{"a":1,"a":2}}\n', b'{"type":"clock","type":"job"}\n',
                 b'{"type":"clock","x":NaN}\n', b'{"type":"clock","x":1e309}\n',
                 b'\xff\n', b'{"type":"clock"}', b'\n', b'[]\n',
                 b'{"type":"clock","x":18446744073709551616}\n']
        for raw in cases:
            with self.subTest(raw=raw):
                self.source.write_bytes(raw)
                with self.assertRaises((ValueError, UnicodeError)):
                    checker.load_source(self.source)

    def test_source_finite_size_shape_and_row_bounds(self):
        cases = [b'', b'{"type":"clock","x":' + b'[' * 20 + b'0' + b']' * 20 + b'}\n',
                 b'{"type":"clock","x":"' + b'a' * checker.MAX_LINE_BYTES + b'"}\n']
        for raw in cases:
            self.source.write_bytes(raw)
            with self.assertRaises(ValueError):
                checker.load_source(self.source)
        self.source.write_bytes(b'{"type":"clock"}\n' * 2)
        with patch.object(checker, "MAX_SOURCE_ROWS", 1), self.assertRaises(ValueError):
            checker.load_source(self.source)

    def test_output_cannot_alias_any_input_and_context_is_required(self):
        before = self.source.read_bytes()
        self.output = self.source
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
            self.invoke()
        self.assertEqual(e.exception.code, 2)
        self.assertEqual(self.source.read_bytes(), before)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            checker.main(["--witness", str(self.witness), "--expected-header", str(self.expected),
                          "--source", str(self.source), "--output", str(self.directory / "out.json")])


if __name__ == "__main__":
    unittest.main()
