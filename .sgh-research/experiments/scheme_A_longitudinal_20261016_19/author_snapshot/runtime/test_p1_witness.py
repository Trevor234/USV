"""Meaningful independent integrity checks for the fixed diagnostic witness."""
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import check_p1_witness as checker


def header():
    return {"run_id": "B1_test_01", "boot_id": "5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb",
            "contract_sha256": "1" * 64, "source_sha256": "2" * 64,
            "binary_sha256": "3" * 64, "worker_binary_sha256": "4" * 64,
            "worker_instance": "5" * 64}


def identity(job=0, tick=0, target=0):
    return {"job_id": job, "tick": tick, "target_tick": target,
            "task_generation": 1, "model_generation": 1, "config_generation": 1,
            "schedule_generation": 1, "clock_epoch": 1}


def phase(sequence, event, ns):
    return {"sequence": sequence, "event_code": event, "observation_code": 6 if event == 7 else 0,
            "ns": ns, "tick": 0, "job_id": 0, "admission_slots": -1,
            "candidate_present": None, "pending_present": None, "failed": None,
            "stopping": None, "pause_active": None}


def valid_witness():
    w = {"schema": checker.SCHEMA, "enabled": True, "closed": True,
         "audit_complete": True, "overflow": False, "incomplete": False,
         "clock_name": "CLOCK_MONOTONIC", "header": header(),
         "capacities": copy.deepcopy(checker.CAPACITIES), "counters": {},
         "tick": [], "submit": [], "activation": [], "phase": [],
         "first_failure": {"code": 0, "stream": 0, "ns": 0, "ticket": 0}}
    common = {"skipped_ticks": 0, "failed_start": False, "stopping_start": False,
              "failed_end": False, "stopping_end": False}
    w["tick"] = [dict(identity(), sequence=1, planned_ns=100, start_ns=101,
                      end_ns=140, candidate_present=False, **common),
                 dict(identity(1, 1, 1), sequence=2, planned_ns=200, start_ns=201,
                      end_ns=240, candidate_present=True, **common)]
    w["submit"] = [dict(identity(1, 0, 1), sequence=1, commit_ns=150,
                        failed=False, stopping=False)]
    w["activation"] = [dict(identity(1, 1, 1), sequence=1, commit_ns=220,
                            ready_commit_ns=180, accepted=True,
                            failed=False, stopping=False, reason_code=0)]
    w["phase"] = [dict(phase(1, 9, 220), tick=1, job_id=1, observation_code=2),
                  phase(2, 7, 250)]
    recalculate(w)
    return w


def recalculate(w):
    for stream in checker.STREAMS:
        n = len(w[stream])
        w["counters"][stream] = {"attempts": n, "reserved": n, "published": n,
                                  "overflow": 0, "rejected": 0}
    w["counters"]["ticks_without_candidate"] = sum(not r["candidate_present"] for r in w["tick"])
    w["counters"]["accepted_activations"] = sum(r["accepted"] for r in w["activation"])


class WitnessIntegrity(unittest.TestCase):
    def setUp(self):
        self.w = valid_witness()

    def check(self, expected=None, **kwargs):
        return checker.analyze(self.w, header() if expected is None else expected, **kwargs)

    def rejected(self, code=None):
        r = self.check()
        self.assertFalse(r["passed"], r)
        if code:
            self.assertIn(code, {i["code"] for i in r["issues"]}, r)
        return r

    def test_valid_complete_run_does_not_grant_other_qualification(self):
        r = self.check()
        self.assertTrue(r["passed"], r)
        self.assertTrue(r["schema_valid"])
        self.assertTrue(r["witness_complete"])
        for field in ("source_join_verified", "expected_log_overflow_mechanism_passed",
                      "normal_contract_complete", "execute_qualified",
                      "activation_reason_covers_all_worker_gates"):
            self.assertIs(r[field], False)

    def test_unknown_phase_state_remains_explicitly_unknown(self):
        r = self.check()
        self.assertTrue(r["passed"], r)
        self.assertEqual(r["phase_unknown_state_rows"], 2)
        self.assertIsNone(self.w["phase"][0]["failed"])

    def test_rejected_activation_is_attempt_not_accepted(self):
        self.w["tick"].append(dict(self.w["tick"][1], sequence=3, tick=2, target_tick=2,
                                  job_id=2, planned_ns=300, start_ns=301, end_ns=340))
        self.w["submit"].append(dict(self.w["submit"][0], sequence=2, tick=1, target_tick=2,
                                    job_id=2, commit_ns=250))
        self.w["activation"].append(dict(self.w["activation"][0], sequence=2, tick=2,
                                        target_tick=2, job_id=2, commit_ns=320,
                                        ready_commit_ns=280, accepted=False, reason_code=3))
        # A rejected old-version candidate need not match current state versions.
        self.w["activation"][1]["task_generation"] = 2
        self.w["phase"][-1]["ns"] = 350
        recalculate(self.w)
        self.assertTrue(self.check()["passed"], self.check())
        self.assertEqual(self.w["counters"]["accepted_activations"], 1)
        self.assertEqual(len(self.w["activation"]), 2)

    def test_async_failure_snapshot_does_not_imply_illegal_acceptance(self):
        self.w["activation"][0].update(failed=True, stopping=True)
        self.w["tick"][1].update(failed_end=True, stopping_end=True)
        self.assertTrue(self.check()["passed"], self.check())

    def test_independent_header_pins_every_identity_field(self):
        for field in checker.HEADER_FIELDS:
            with self.subTest(field=field):
                expected = header()
                expected[field] = "6" * 64 if field in checker.HASH_FIELDS else (
                    "other_run" if field == "run_id" else "6a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb")
                r = self.check(expected)
                self.assertFalse(r["passed"])
                self.assertIn("header_pin_mismatch", {i["code"] for i in r["issues"]})

    def test_header_domain_utf8_bound_uuid_and_lowercase_hash(self):
        cases = [("run_id", "中" * 43), ("run_id", "bad\nrun"), ("run_id", "bad\x7frun"),
                 ("run_id", "\ud800"), ("boot_id", "b" * 36),
                 ("worker_instance", "x" * 64), ("binary_sha256", "A" * 64)]
        for field, value in cases:
            with self.subTest(field=field, value=repr(value)):
                w = copy.deepcopy(self.w)
                w["header"][field] = value
                r = checker.analyze(w, w["header"])
                self.assertFalse(r["passed"])
                self.assertIn("header_fields_or_types", {i["code"] for i in r["issues"]})

    def test_missing_or_extra_root_fields(self):
        for field in checker.ROOT_FIELDS:
            with self.subTest(field=field):
                w = copy.deepcopy(self.w)
                del w[field]
                r = checker.analyze(w, header())
                self.assertFalse(r["passed"])
        self.w["unexpected"] = 1
        self.rejected("root_fields")

    def test_all_root_flags_require_actual_boolean(self):
        for field in ("enabled", "closed", "audit_complete", "overflow", "incomplete"):
            for value in (0, 1, "false", None):
                with self.subTest(field=field, value=value):
                    w = copy.deepcopy(self.w)
                    w[field] = value
                    r = checker.analyze(w, header())
                    self.assertFalse(r["passed"])
                    self.assertIn("flag_type", {i["code"] for i in r["issues"]})

    def test_clock_schema_and_checker_mode(self):
        self.w["clock_name"] = "ROS_TIME"
        self.rejected("clock_domain")
        self.w = valid_witness()
        self.w["schema"] = "p1-fixed-witness-v2"
        self.rejected("schema_version")
        r = checker.analyze(valid_witness(), header(), require_enabled=1)
        self.assertFalse(r["passed"])

    def test_fixed_capacities_are_never_tunable_by_record(self):
        for stream in checker.STREAMS:
            for value in (True, 1, checker.CAPACITIES[stream] + 1):
                with self.subTest(stream=stream, value=value):
                    w = copy.deepcopy(self.w)
                    w["capacities"][stream] = value
                    self.assertFalse(checker.analyze(w, header())["passed"])

    def test_counter_types_accounting_and_capacity(self):
        cases = [("attempts", True), ("reserved", -1), ("published", 1.0),
                 ("overflow", checker.U64_MAX + 1), ("rejected", "0"),
                 ("attempts", 99), ("reserved", 257), ("published", 3)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                w = copy.deepcopy(self.w)
                w["counters"]["tick"][field] = value
                self.assertFalse(checker.analyze(w, header())["passed"])

    def test_unpublished_reservation_and_partial_array_cannot_pass(self):
        self.w["counters"]["tick"].update(attempts=3, reserved=3)
        r = self.rejected("unpublished_reservation")
        self.rejected("counter_failure_without_first_failure")
        self.assertFalse(r["witness_complete"])
        self.w = valid_witness()
        self.w["tick"].pop()
        self.rejected("published_row_count")

    def test_overflow_is_preserved_separate_from_r5_mechanism(self):
        tick = copy.deepcopy(self.w["tick"][0])
        self.w["tick"] = [dict(tick, sequence=i + 1, tick=i, planned_ns=100 + i * 100,
                               start_ns=101 + i * 100, end_ns=140 + i * 100) for i in range(256)]
        self.w["submit"] = self.w["activation"] = []
        self.w["phase"] = [phase(1, 7, 26000)]
        recalculate(self.w)
        self.w["overflow"] = self.w["incomplete"] = True
        self.w["audit_complete"] = False
        self.w["counters"]["tick"].update(attempts=257, overflow=1)
        self.w["first_failure"] = {"code": 1, "stream": 1, "ns": 26000, "ticket": 257}
        r = self.rejected("stream_not_complete")
        self.assertTrue(r["schema_valid"], r)
        self.assertFalse(r["expected_log_overflow_mechanism_passed"])
        self.assertIn("audit_first_failure", {i["code"] for i in r["issues"]})

    def test_overflow_flag_disagreement(self):
        self.w["overflow"] = True
        self.rejected("overflow_flag_disagrees")

    def test_first_failure_explicit_unknown_time_and_location(self):
        for code, stream, ticket in ((2, 1, 0), (3, 0, 0), (4, 1, 0),
                                    (5, 0, 0), (6, 2, 0), (7, 0, 0)):
            with self.subTest(code=code):
                w = copy.deepcopy(self.w)
                w["first_failure"] = {"code": code, "stream": stream, "ns": 0, "ticket": ticket}
                if code in (2, 6):
                    w["counters"][checker.STREAMS[stream - 1]]["rejected"] = 1
                    w["counters"][checker.STREAMS[stream - 1]]["attempts"] += 1
                w["incomplete"] = True
                w["audit_complete"] = False
                r = checker.analyze(w, header())
                self.assertFalse(r["passed"])
                self.assertTrue(r["schema_valid"], r)
                self.assertIn("audit_first_failure", {i["code"] for i in r["issues"]})

    def test_first_failure_cannot_disappear_behind_complete_flag(self):
        self.w["first_failure"] = {"code": 5, "stream": 0, "ns": 0, "ticket": 0}
        self.rejected("failure_without_incomplete_flag")
        self.w = valid_witness()
        self.w["incomplete"] = True
        self.rejected("incomplete_without_first_failure")

    def test_first_failure_types_ranges_and_markers(self):
        for field, value in (("code", True), ("code", 8), ("stream", 5),
                             ("ns", -1), ("ticket", 1.0)):
            with self.subTest(field=field):
                w = copy.deepcopy(self.w)
                w["first_failure"][field] = value
                self.assertFalse(checker.analyze(w, header())["passed"])
        self.w["first_failure"]["ns"] = 1
        self.rejected("no_failure_marker")

    def test_each_stream_sequence_and_duplicate_rows(self):
        for stream in checker.STREAMS:
            for value in (True, 0, checker.CAPACITIES[stream] + 1):
                with self.subTest(stream=stream, value=value):
                    w = copy.deepcopy(self.w)
                    w[stream][0]["sequence"] = value
                    self.assertFalse(checker.analyze(w, header())["passed"])
        self.w["activation"].append(copy.deepcopy(self.w["activation"][0]))
        self.w["activation"][1]["sequence"] = 2
        recalculate(self.w)
        self.rejected("duplicate_activation_job")

    def test_partial_reservation_gap_preserved_as_incomplete(self):
        self.w["phase"][1]["sequence"] = 3
        self.w["counters"]["phase"].update(attempts=3, reserved=3)
        self.w["first_failure"] = {"code": 4, "stream": 4, "ns": 0, "ticket": 0}
        self.w["audit_complete"] = False
        self.w["incomplete"] = True
        r = self.rejected("reservation_sequence_gap")
        self.assertTrue(r["schema_valid"], r)

    def test_impossible_overflow_or_failure_counter_cannot_pass_schema(self):
        self.w["counters"]["tick"].update(attempts=3, overflow=1)
        self.rejected("overflow_before_full_capacity")
        self.w = valid_witness()
        self.w["first_failure"] = {"code": 2, "stream": 1, "ns": 0, "ticket": 0}
        self.w["incomplete"] = True
        self.w["audit_complete"] = False
        self.rejected("rejected_failure_without_rejection")

    def test_each_stream_missing_extra_field_and_integer_types(self):
        for stream in checker.STREAMS:
            w = copy.deepcopy(self.w)
            del w[stream][0]["job_id"]
            self.assertFalse(checker.analyze(w, header())["passed"])
            w = copy.deepcopy(self.w)
            w[stream][0]["extra"] = None
            self.assertFalse(checker.analyze(w, header())["passed"])
            for value in (True, 1.0, -1, checker.U64_MAX + 1):
                with self.subTest(stream=stream, value=value):
                    w = copy.deepcopy(self.w)
                    w[stream][0]["tick"] = value
                    self.assertFalse(checker.analyze(w, header())["passed"])

    def test_tick_with_and_without_candidate_identity(self):
        self.w["tick"][0]["job_id"] = 9
        self.rejected("tick_without_candidate_identity")
        self.w = valid_witness()
        self.w["tick"][1]["target_tick"] = 2
        self.rejected("candidate_tick_identity")

    def test_tick_actual_chronology_and_nonoverlap(self):
        for field, value, code in (("start_ns", 199, "tick_time_order"),
                                   ("end_ns", 199, "tick_time_order"),
                                   ("planned_ns", 100, "tick_planned_time_reversal")):
            with self.subTest(field=field):
                self.w = valid_witness()
                self.w["tick"][1][field] = value
                self.rejected(code)
        self.w = valid_witness()
        self.w["tick"][0]["end_ns"] = 202
        self.rejected("tick_intervals_overlap")

    def test_tick_schedule_skip_and_reset_generation(self):
        self.w["tick"][1]["tick"] = self.w["tick"][1]["target_tick"] = 3
        self.w["activation"][0]["tick"] = self.w["activation"][0]["target_tick"] = 3
        self.w["submit"][0]["target_tick"] = 3
        self.w["submit"][0]["tick"] = 2
        self.w["tick"][1]["skipped_ticks"] = 2
        self.w["phase"][0]["tick"] = 3
        self.assertTrue(self.check()["passed"], self.check())
        self.w["tick"][1]["skipped_ticks"] = 1
        self.rejected("tick_schedule_sequence")
        self.w = valid_witness()
        self.w["tick"][1]["schedule_generation"] = 0
        self.rejected("schedule_generation_reversal")

    def test_tick_time_integer_domain(self):
        for field in ("planned_ns", "start_ns", "end_ns"):
            for value in (True, 0, -1, 1.0, checker.I64_MAX + 1, float("inf"), float("nan")):
                with self.subTest(field=field, value=value):
                    w = copy.deepcopy(self.w)
                    w["tick"][0][field] = value
                    self.assertFalse(checker.analyze(w, header())["passed"])

    def test_submission_target_identity_and_duplicate_job(self):
        self.w["submit"][0]["target_tick"] = 2
        self.rejected("submit_target_tick")
        self.w = valid_witness()
        self.w["submit"].append(copy.deepcopy(self.w["submit"][0]))
        self.w["submit"][1]["sequence"] = 2
        recalculate(self.w)
        self.rejected("duplicate_submit_job")

    def test_candidate_attempt_coverage_and_submit_presence(self):
        self.w["activation"].clear()
        recalculate(self.w)
        self.rejected("candidate_attempt_coverage")
        self.w = valid_witness()
        self.w["submit"].clear()
        recalculate(self.w)
        self.rejected("activation_without_submit")

    def test_candidate_commit_is_within_tick_and_after_ready_submit(self):
        for field, value, code in (("commit_ns", 250, "activation_tick_commit"),
                                   ("commit_ns", 179, "activation_time_order"),
                                   ("ready_commit_ns", 0, "row_time"),
                                   ("ready_commit_ns", 140, "ready_before_submit")):
            with self.subTest(field=field):
                self.w = valid_witness()
                self.w["activation"][0][field] = value
                self.rejected(code)

    def test_accepted_candidate_versions_bind_to_submit_and_tick(self):
        for field in checker.IDENTITY_FIELDS - {"tick", "job_id", "target_tick"}:
            with self.subTest(field=field):
                self.w = valid_witness()
                self.w["activation"][0][field] += 1
                self.rejected("accepted_identity_mismatch")

    def test_reason_is_reduced_dictionary_not_full_execution_gate(self):
        self.w["activation"][0].update(accepted=False, reason_code=99)
        recalculate(self.w)
        self.rejected("activation_reason_code")
        self.w["activation"][0]["reason_code"] = 0
        self.rejected("rejected_with_accepted_reason")
        self.w = valid_witness()
        self.w["activation"][0]["reason_code"] = 3
        self.rejected("accepted_without_attempt_commit")

    def test_aggregate_counts_recomputed_from_rows(self):
        self.w["counters"]["accepted_activations"] = 2
        self.rejected("activation_aggregate_count")
        self.w = valid_witness()
        self.w["counters"]["ticks_without_candidate"] = 0
        self.rejected("tick_aggregate_count")

    def test_phase_bounds_state_type_and_observation_domain(self):
        for field, value in (("event_code", 10), ("event_code", True),
                             ("observation_code", 7), ("admission_slots", 3),
                             ("admission_slots", True), ("failed", 0), ("ns", 0)):
            with self.subTest(field=field):
                w = copy.deepcopy(self.w)
                w["phase"][0][field] = value
                self.assertFalse(checker.analyze(w, header())["passed"])

    def test_mpsc_phase_reservations_need_not_be_time_sorted(self):
        self.w["phase"] = [dict(phase(1, 9, 220), tick=1, job_id=1), phase(2, 4, 190),
                           phase(3, 8, 185), phase(4, 7, 250)]
        recalculate(self.w)
        self.assertTrue(self.check()["passed"], self.check())

    def test_empty_enabled_library_snapshot_is_not_complete_run(self):
        for stream in checker.STREAMS:
            self.w[stream] = []
        recalculate(self.w)
        self.rejected("no_actual_ticks")
        self.rejected("business_ready_count")
        self.rejected("terminal_close_count")

    def test_business_ready_binds_first_accepted_commit(self):
        for field, value in (("ns", 80), ("tick", 0), ("job_id", 2)):
            with self.subTest(field=field):
                self.w = valid_witness()
                self.w["phase"][0][field] = value
                self.rejected("business_ready_activation_binding")
        self.w = valid_witness()
        self.w["activation"][0].update(accepted=False, reason_code=3)
        recalculate(self.w)
        self.rejected("business_ready_without_accepted_activation")

    def test_business_ready_and_close_are_exactly_once(self):
        for event, code in ((9, "business_ready_count"), (7, "terminal_close_count")):
            with self.subTest(event=event):
                self.w = valid_witness()
                self.w["phase"].insert(1, dict(self.w["phase"][0], event_code=event))
                for i, row in enumerate(self.w["phase"]):
                    row["sequence"] = i + 1
                recalculate(self.w)
                self.rejected(code)

    def test_terminal_close_is_after_all_producers_and_last_phase(self):
        self.w["phase"][-1]["ns"] = 239
        self.rejected("terminal_close_before_producers")
        self.w = valid_witness()
        self.w["phase"].append(phase(3, 4, 249))
        recalculate(self.w)
        self.rejected("terminal_close_not_last_phase")

    def test_closed_terminal_and_complete_flags(self):
        self.w["closed"] = False
        self.rejected("witness_not_closed")
        self.w = valid_witness()
        self.w["audit_complete"] = False
        self.rejected("audit_not_complete")

    def test_disabled_zero_records_is_not_enabled_proof(self):
        self.w["enabled"] = self.w["audit_complete"] = False
        for stream in checker.STREAMS:
            self.w[stream] = []
        recalculate(self.w)
        self.rejected("witness_disabled")
        r = self.check(require_enabled=False)
        self.assertTrue(r["passed"], r)
        self.assertFalse(r["witness_complete"])

    def test_disabled_cannot_hide_records_or_claim_complete(self):
        self.w["enabled"] = False
        self.rejected("disabled_has_records")
        self.rejected("disabled_claims_complete")

    def test_wrong_root_or_counter_structures_do_not_crash(self):
        for value in (None, [], 1, True):
            self.assertFalse(checker.analyze(value, header())["passed"])
        for field, value in (("counters", None), ("tick", {}), ("first_failure", [])):
            w = copy.deepcopy(self.w)
            w[field] = value
            self.assertFalse(checker.analyze(w, header())["passed"])


class WitnessFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.witness = self.directory / "witness.json"
        self.expected = self.directory / "header.json"
        self.output = self.directory / "report.json"
        self.witness.write_text(json.dumps(valid_witness()), encoding="utf-8")
        self.expected.write_text(json.dumps(header()), encoding="utf-8")

    def invoke(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = checker.main([str(self.witness), "--expected-header", str(self.expected),
                                 "--output", str(self.output), *extra])
        return code, captured.getvalue()

    def test_file_hash_binding_and_create_only_report(self):
        digest = hashlib.sha256(self.witness.read_bytes()).hexdigest()
        code, _ = self.invoke("--witness-sha256", digest)
        self.assertEqual(code, 0)
        r = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(r["evidence_sha256"][str(self.witness)], digest)
        before = self.output.read_bytes()
        code, emitted = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("report_write_failed", emitted)
        self.assertEqual(self.output.read_bytes(), before)

    def test_witness_hash_mismatch_preserved(self):
        code, _ = self.invoke("--witness-sha256", "0" * 64)
        self.assertEqual(code, 2)
        r = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertFalse(r["passed"])
        self.assertIn("witness_file_hash_mismatch", {i["code"] for i in r["issues"]})

    def test_raw_duplicate_keys_utf8_and_nonfinite_rejected(self):
        for raw in (b'{"header":{"run_id":"a","run_id":"b"}}',
                    b'{"schema":"a","schema":"b"}', b'\xff', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e309}'):
            with self.subTest(raw=raw):
                self.witness.write_bytes(raw)
                with self.assertRaises((ValueError, UnicodeError)):
                    checker.load_json(self.witness)

    def test_empty_oversize_and_deep_json_have_finite_rejection(self):
        for raw in (b'', b' ' * (checker.MAX_BYTES + 1), b'[' * 2000 + b']' * 2000):
            with self.subTest(length=len(raw)):
                self.witness.write_bytes(raw)
                with self.assertRaises(ValueError):
                    checker.load_json(self.witness)

    def test_input_unreadable_and_missing_output_parent_return_failure(self):
        self.witness.unlink()
        code, _ = self.invoke()
        self.assertEqual(code, 2)
        r = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(r["issues"][0]["code"], "input_unreadable")
        self.output = self.directory / "missing" / "report.json"
        code, emitted = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("report_write_failed", emitted)


if __name__ == "__main__":
    unittest.main()
