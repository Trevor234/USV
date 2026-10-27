"""Finite pressure evidence, honest unknowns, independent source chains and IO failures."""
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
    sys.path.append(str(Path(__file__).resolve().parents[2] / "m0b_witness_implementation_20261007" / "runtime"))
import check_R5_mechanism as checker
from test_p1_witness import header, identity, phase, recalculate


def fixture():
    h = header()
    w = {"schema": "p1-fixed-witness-v1", "enabled": True, "closed": True, "audit_complete": True,
         "overflow": False, "incomplete": False, "clock_name": "CLOCK_MONOTONIC", "header": h,
         "capacities": {"tick": 256, "submit": 128, "activation": 128, "phase": 32}, "counters": {},
         "first_failure": {"code": 0, "stream": 0, "ns": 0, "ticket": 0}, "tick": [], "submit": [], "activation": [], "phase": []}
    def tick(number, planned, job=0, failed=False, stopping=False):
        return dict(identity(job, number, number if job else 0), sequence=len(w["tick"]) + 1,
                    planned_ns=planned, start_ns=planned + 1000, end_ns=planned + 150000000,
                    candidate_present=bool(job), skipped_ticks=0, failed_start=failed, failed_end=failed,
                    stopping_start=stopping, stopping_end=stopping)
    reg = [{"type": "startup", "run_id": h["run_id"], "boot": h["boot_id"], "contract_hash": h["contract_sha256"],
            "mode": "no_output", "clock": "CLOCK_MONOTONIC", "diagnostic_only": True, "physical_publisher_endpoints": 0}]
    worker = []
    w["tick"].append(tick(0, 1000000000))
    for jid, planned in ((1, 1200000000), (2, 1400000000)):
        t = tick(jid, planned, jid)
        w["tick"].append(t)
        submit = dict(identity(jid, jid - 1, jid), sequence=jid, commit_ns=planned - 40000000, failed=False, stopping=False)
        a = dict(identity(jid, jid, jid), sequence=jid, commit_ns=planned + 20000000,
                 ready_commit_ns=planned - 10000000, accepted=True, failed=False, stopping=False, reason_code=0)
        w["submit"].append(submit)
        w["activation"].append(a)
        j = {"schema": "p1-solve-job-v1", "run_id": h["run_id"], "boot_id": h["boot_id"],
             "contract_hash": h["contract_sha256"], "worker_instance": h["worker_instance"],
             **{k: submit[k] for k in checker.JOB_ID}, "freeze_ns": planned - 45000000,
             "target_state": [0.0] * 6, "reference": [0.0] * 126}
        reg.extend([
            {"type": "job", "job": j, "submit_commit_ns": submit["commit_ns"] - 1000, "publish_start_ns": submit["commit_ns"] + 1000},
            {"type": "candidate_registration", "job": copy.deepcopy(j), "ready_commit_ns": a["ready_commit_ns"],
             "accepted_registration": True, "worker_instance": h["worker_instance"], "solve_start_ns": planned - 30000000,
             "solve_end_ns": planned - 20000000, "first_control": [0.0, 0.0], "reason": ""},
            {"type": "decision", "run_id": h["run_id"], "boot_id": h["boot_id"], "contract_hash": h["contract_sha256"],
             "worker_instance": h["worker_instance"], "sequence": t["sequence"], "job_id": jid, "tick": jid,
             **{k: t[k] for k in checker.VERSIONS}, "epoch": 1, "planned_ns": planned, "start_ns": t["start_ns"],
             "end_ns": planned + 30000000, "activation_commit_ns": a["commit_ns"], "ready_commit_ns": a["ready_commit_ns"],
             "accepted": True, "reason": "", "schema": "p1-execution-decision-v2", "mode": "no_output",
             "diagnostic_only": True, "normal_contract_complete": False, "skipped_ticks": 0}])
        worker.extend([
            {"type": "job_received", "job": copy.deepcopy(j), "worker_instance": h["worker_instance"], "receive_ns": planned - 35000000},
            {"type": "candidate", "job": copy.deepcopy(j), "worker_instance": h["worker_instance"], "receive_ns": planned - 35000000,
             "solve_start_ns": planned - 30000000, "solve_end_ns": planned - 20000000, "publish_start_ns": planned - 15000000,
             "backend": "acados", "backend_ms": 0.3, "success": True, "solver_invoked": True, "prediction_available": True,
             "reason": "", "first_control": [0.0, 0.0], "X": [0.0] * 126, "U": [0.0] * 40},
            {"type": "candidate_publish_result", "job_id": jid, "worker_instance": h["worker_instance"],
             "publish_start_ns": planned - 14000000, "publish_end_ns": planned - 12000000, "success": True}])
    for number, planned in enumerate(range(2200000000, 3000000001, 200000000), 3):
        w["tick"].append(tick(number, planned))
    final = tick(8, 3200000000, failed=True, stopping=True)
    final["end_ns"] = 3210000000
    w["tick"].append(final)
    def ph(kind, obs, time, **updates):
        r = phase(len(w["phase"]) + 1, kind, time)
        r.update(observation_code=obs)
        if obs == 5:
            r.update(failed=False, pause_active=False)
        else:
            r.update(admission_slots=0, candidate_present=False, pending_present=False, failed=False, stopping=False, pause_active=False)
        r.update(updates)
        w["phase"].append(r)
    ph(9, 2, 1220000000, job_id=1, tick=1)
    ph(1, 5, 2000001000)
    ph(2, 5, 2001000000, pause_active=True)
    ph(3, 5, 3180000000, failed=True, pause_active=True)
    ph(4, 5, 3180010000, failed=True, pause_active=True)
    ph(5, 1, 3200002000, failed=True, stopping=True, pause_active=True, tick=8)
    ph(8, 1, 3200003000, failed=True, stopping=True, pause_active=True, tick=8)
    ph(6, 5, 3250000000, failed=True)
    ph(7, 6, 3400000000, failed=True, stopping=True, tick=8)
    recalculate(w)
    reg.append({"type": "source_summary", "emitted": len(reg), "generated": len(reg) + 13,
                "dropped": 13, "normal_source_complete": False, "finished_ns": 3300000000})
    worker.append({"type": "worker_summary", "generated_candidates": 2, "published_candidates": 2,
                   "completed_jobs": 2, "fatal": False, "normal_source_complete": True, "finished_ns": 3500000000})
    pins = {"boot_id": h["boot_id"], "contract_sha256": h["contract_sha256"], "diagnostic_source_sha256": h["source_sha256"],
            "regulator_binary_sha256": h["binary_sha256"], "worker_binary_sha256": h["worker_binary_sha256"],
            "runner_sha256": "6" * 64, "supervisor_sha256": "7" * 64}
    policy = {"schema": "p1-R5-predeclared-policy-v1", "run_id": h["run_id"], "mode": "no_output", "pins": pins,
              "declared_duration_ns": 15000000000, "log_capacity": 512, "test_sink_pause_ms": 5000,
              "limits": copy.deepcopy(checker.LIMITS), "response_rule": checker.RESPONSE_RULE,
              "invalidation_boundary": "first_invalidation_observed", "shutdown_rule": checker.SHUTDOWN_RULE,
              "window_origin": "arm_publish_start_ns", "C0_evidence_sha256": "8" * 64, "witness_enabled": True,
              "hooks": {k: 0 for k in ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms", "test_tick_block_ms")},
              "queue_overflow_proof": {"kind": "pinned_capacity_rejection_branch_and_no_overcapacity_invariant", "capacity": 512,
                "sink_source_sha256": checker.SINK_SHA256, "required_phase": {"event_code": 3, "observation_code": 5},
                "required_summary_dropped_positive": True, "actual_depth_trace_available": False, "max_depth_above_capacity_allowed": False}}
    context = {"schema": "p1-R5-pressure-context-v1", "run_id": h["run_id"], "mode": "no_output",
               "boot_id": h["boot_id"], "contract_sha256": h["contract_sha256"], "runner_sha256": pins["runner_sha256"],
               "supervisor_sha256": pins["supervisor_sha256"], "binaries": {"regulator": {"sha256": h["binary_sha256"]}, "worker": {"sha256": h["worker_binary_sha256"]}},
               "diagnostic_source": {"sha256": h["source_sha256"]}, "fixed_witness": {"enabled": True, "test_sink_pause_ms": 5000},
               "declaration": {"duration_s": 15., "pressure_window_origin": "arm_publish_start_ns", "expected_fault": "sink_logger_pause_overflow",
                               "test_delay_ms": 0, "test_native_block_ms": 0, "test_prepare_block_ms": 0, "test_tick_block_ms": 0,
                               "test_sink_pause_ms": 5000, "execute_qualified": False}}
    arm = {"schema": "p1-R5-pressure-arm-v1", "run_id": h["run_id"], "boot_id": h["boot_id"], "contract_sha256": h["contract_sha256"],
           "publish_start_ns": 2000000000, "publish_end_ns": 2000100000, "publish_success": True, "arm_attempts": 1,
           "accepted_chains": [], "source_prefixes": {label: {"path": label + "-source.jsonl", "complete_bytes": 1,
            "sha256": "0" * 64, "rows": 1, "tail_bytes": 0} for label in ("regulator", "worker")}}
    for jid in (1, 2):
        d = next(r for r in reg if r.get("type") == "decision" and r["job_id"] == jid)
        ca = next(r for r in worker if r.get("type") == "candidate" and r["job"]["job_id"] == jid)
        registration = next(r for r in reg if r.get("type") == "candidate_registration" and r["job"]["job_id"] == jid)
        publication = next(r for r in worker if r.get("type") == "candidate_publish_result" and r["job_id"] == jid)
        arm["accepted_chains"].append({**{k: d[k] for k in ("job_id", "tick", "sequence", "schedule_generation", "ready_commit_ns", "activation_commit_ns")},
            "typed_received_ns": d["activation_commit_ns"] + 1000, "native_solver_invoked": True, "native_success": True,
            "prediction_available": True, "job": ca["job"], "source_decision": d, "worker_candidate": ca,
            "candidate_registration": registration, "candidate_publish_result": publication})
    summary = {"schema": "p1-R5-pressure-runner-summary-v1", "run_id": h["run_id"], "pressure_arm": arm,
               "window_start": {"started_ns": 2000000000}, "window_completion": {"window_started_ns": 2000000000,
               "window_finished_ns": 3410000000, "observed_duration_ns": 1410000000, "maximum_duration_ns": 15000000000,
               "stop_reason": "expected_sink_failure_exit", "normal_window_complete": False},
               "actual_returncodes": {"regulator": 2}, "observed_regulator_exit": {"observed_ns": 3410000000, "returncode": 2, "natural": True},
               "release_kind": "natural_failure_exit", "release_requested_ns": None, "stop_release_ns": 3410000000,
               "stop_reason": "expected_sink_failure_exit", "R5_complete": False, "normal_contract_complete": False, "execute_qualified": False}
    return w, h, reg, worker, context, summary, policy


class Mechanism(unittest.TestCase):
    def setUp(self):
        self.w, self.h, self.reg, self.worker, self.c, self.s, self.p = fixture()

    def result(self):
        return checker.analyze(self.w, self.h, self.reg, self.worker, self.c, self.s, self.p)

    def rejected(self, code=None):
        r = self.result()
        self.assertIs(r["passed"], False, r)
        self.assertIs(r["expected_log_overflow_mechanism_passed"], False)
        if code:
            self.assertIn(code, {i["code"] for i in r["issues"]}, r)
        return r

    def ph(self, event, observer=None):
        return next(r for r in self.w["phase"] if r["event_code"] == event and (observer is None or r["observation_code"] == observer))

    def test_real_pressure_gate_only_preserves_drop_and_unknown_depth(self):
        r = self.result()
        self.assertTrue(r["passed"], r)
        self.assertTrue(r["mechanism_passed"])
        self.assertEqual(r["counts"]["native_prearm_accepted"], 2)
        self.assertEqual(r["counts"]["whole_pause_ticks_before_failure"], 5)
        self.assertEqual(r["counts"]["source_dropped"], 13)
        self.assertIsNone(r["observations"]["observed_queue_depth"])
        self.assertIsNone(r["observations"]["failure_atomic_store_ns"])
        for key in ("R5_complete", "worker_source_complete", "raw_bag_complete", "owned_process_lifecycle_verified", "normal_contract_complete", "execute_qualified"):
            self.assertIs(r[key], False)

    def test_rc_unknown_zero_or_boolean_does_not_match_expected_failure(self):
        for value in (None, 0, False, "2"):
            with self.subTest(value=value):
                self.s["actual_returncodes"]["regulator"] = value
                self.rejected("expected_regulator_failure_rc")

    def test_source_drop_counts_and_terminal_summary_must_be_actual(self):
        self.reg[-1]["generated"] += 1
        self.rejected("pressure_source_counts")

    def test_pressure_not_triggered_or_fake_source_complete_cannot_pass(self):
        self.reg[-1].update(dropped=0, normal_source_complete=True)
        self.rejected("pressure_source_counts")

    def test_missing_source_summary_stays_unknown(self):
        self.reg.pop()
        self.rejected("source_event_cardinality")

    def test_witness_incomplete_capacity_and_unpublished_never_grant_mechanism(self):
        self.w.update(audit_complete=False, incomplete=True)
        self.w["first_failure"] = {"code": 1, "stream": 1, "ns": 3200000000, "ticket": 257}
        self.w["counters"]["tick"]["overflow"] = 1
        self.rejected("basis_witness_incomplete")

    def test_missing_and_duplicate_arm_fail_even_with_publication_claim(self):
        self.w["phase"].insert(2, copy.deepcopy(self.ph(1)))
        for i, row in enumerate(self.w["phase"], 1):
            row["sequence"] = i
        recalculate(self.w)
        self.rejected("phase_cardinality")

    def test_wrong_observer_and_fake_known_sink_slots_rejected(self):
        self.ph(3)["observation_code"] = 3
        self.rejected("phase_observer_path")

    def test_business_unknown_slots_cannot_be_replaced_by_clean_close(self):
        self.ph(8)["pending_present"] = None
        self.rejected("business_state_unknown")

    def test_missing_invalidation_is_not_synthesized_from_close(self):
        self.w["phase"].remove(self.ph(8))
        for i, r in enumerate(self.w["phase"], 1):
            r["sequence"] = i
        recalculate(self.w)
        self.rejected("phase_cardinality")

    def test_dirty_candidate_or_pending_or_admission_at_boundary_rejected(self):
        for key, value in (("candidate_present", True), ("pending_present", True), ("admission_slots", 1)):
            with self.subTest(key=key):
                saved = copy.deepcopy(self.ph(8))
                self.ph(8)[key] = value
                self.rejected("invalidation_not_real_clean")
                self.ph(8).update(saved)

    def test_close_dirty_state_is_a_business_failure_not_audit_success(self):
        self.ph(7)["candidate_present"] = True
        self.rejected("close_not_real_clean")

    def test_four_whole_pause_ticks_are_coverage_failure(self):
        self.w["tick"][3]["start_ns"] = 2000000001
        self.w["tick"][3]["planned_ns"] = 2000000000
        self.rejected("pause_ticks_before_failure_insufficient")

    def test_late_failure_log_cannot_hide_response_bound(self):
        self.ph(5)["ns"] = 3380000000
        self.ph(8)["ns"] = 3380001000
        self.rejected("failure_response_conservative_bound")

    def test_false_snapshot_after_known_failure_is_not_cherry_picked_out(self):
        self.w["tick"][-1]["failed_start"] = False
        self.rejected("failed_false_after_known_failure")

    def test_tick_jitter_and_skipped_ticks_not_silent_performance_pass(self):
        self.w["tick"][4]["start_ns"] += 20000001
        self.rejected("tick_jitter_or_skips")

    def test_native_prearm_full_job_echo_and_true_flags_required(self):
        ca = next(r for r in self.worker if r["type"] == "candidate")
        ca["job"]["reference"][0] = 1.0
        self.rejected("native_prearm_chain_incomplete")

    def test_pretending_boolean_solver_native_is_not_success(self):
        ca = next(r for r in self.worker if r["type"] == "candidate")
        ca["solver_invoked"] = 1
        self.rejected("native_prearm_chain_incomplete")

    def test_only_one_real_accepted_before_arm_rejects(self):
        self.s["pressure_arm"]["publish_start_ns"] = 1300000000
        self.s["window_start"]["started_ns"] = 1300000000
        self.s["window_completion"]["window_started_ns"] = 1300000000
        self.s["window_completion"]["observed_duration_ns"] = 2110000000
        self.rejected("native_prearm_minimum")

    def test_rejected_after_stop_is_counted_separately(self):
        self.w["submit"].append(dict(identity(3, 7, 8), sequence=3, commit_ns=3155000000, failed=False, stopping=False))
        a = copy.deepcopy(self.w["activation"][-1])
        a.update(sequence=3, job_id=3, tick=8, target_tick=8, commit_ns=3205000000, ready_commit_ns=3170000000,
                 accepted=False, failed=True, stopping=True, reason_code=1)
        self.w["activation"].append(a)
        self.w["tick"][-1].update(job_id=3, target_tick=8, candidate_present=True)
        recalculate(self.w)
        r = self.result()
        self.assertTrue(r["passed"], r)
        self.assertEqual(r["counts"]["rejected_after_stopping"], 1)

    def test_accepted_commit_at_stop_boundary_rejected(self):
        self.w["submit"].append(dict(identity(3, 7, 8), sequence=3, commit_ns=3155000000, failed=False, stopping=False))
        self.w["activation"].append(dict(identity(3, 8, 8), sequence=3, commit_ns=self.ph(5)["ns"], ready_commit_ns=3170000000,
                                         accepted=True, failed=True, stopping=True, reason_code=0))
        self.w["tick"][-1].update(job_id=3, target_tick=8, candidate_present=True)
        recalculate(self.w)
        self.rejected("accepted_activation_after_stopping")

    def test_submit_commit_after_stop_rejected(self):
        self.w["submit"].append(dict(identity(3, 8, 9), sequence=3, commit_ns=3205000000, failed=True, stopping=True))
        recalculate(self.w)
        self.rejected("submit_after_stopping")

    def test_pause_grace_and_invalidation_deadline_are_fixed_before_run(self):
        self.ph(8)["ns"] = self.ph(5)["ns"] + 220000001
        self.ph(6)["ns"] = 3500000000
        self.ph(7)["ns"] = 3600000000
        self.rejected("invalidation_boundary_time")

    def test_natural_exit_cannot_use_negative_close_minus_release_as_grace(self):
        self.s["observed_regulator_exit"]["observed_ns"] = 6000000000
        self.s["stop_release_ns"] = 6000000000
        self.rejected("shutdown_release_budget")

    def test_logical_stop_has_real_release_to_close_budget(self):
        self.s.update(release_kind="logical_stop_publish", release_requested_ns=3260000000, stop_release_ns=3260000000)
        self.s["observed_regulator_exit"] = None
        self.s["window_completion"].update(window_finished_ns=3259000000, observed_duration_ns=1259000000)
        self.assertTrue(self.result()["passed"], self.result())

    def test_async_failed_submit_snapshot_does_not_move_authorization_gate(self):
        self.w["submit"].append(dict(identity(3, 7, 8), sequence=3, commit_ns=3179999999, failed=True, stopping=False))
        recalculate(self.w)
        r = self.result()
        self.assertTrue(r["passed"], r)
        self.assertEqual(r["counts"]["submit_failed_after_authorization_snapshots"], 1)

    def test_candidate_success_does_not_require_invented_empty_native_diagnostic(self):
        ca = next(r for r in self.worker if r["type"] == "candidate")
        ca["reason"] = "backend_success_detail"
        self.assertTrue(self.result()["passed"], self.result())

    def test_context_policy_hash_time_and_hook_types_are_independent(self):
        self.c["declaration"]["test_delay_ms"] = False
        self.rejected("unrelated_hook_nonzero_or_unknown")

    def test_changed_binary_and_posthoc_budget_not_accepted(self):
        self.p["pins"]["regulator_binary_sha256"] = "9" * 64
        self.p["limits"]["observation_max_ns"] = 230000000
        self.rejected("policy_asset_pin")

    def test_arm_native_flags_alone_cannot_replace_raw_worker_proof(self):
        self.s["pressure_arm"]["accepted_chains"][0] = {"job_id": 1, "native_solver_invoked": True, "native_success": True, "prediction_available": True}
        self.rejected("arm_chain_payload_mismatch")

    def test_arm_typed_accept_must_be_before_actual_publication(self):
        self.s["pressure_arm"]["accepted_chains"][0]["typed_received_ns"] = self.s["pressure_arm"]["publish_start_ns"]
        self.rejected("arm_typed_accept_before_publication")

    def test_queue_path_proof_must_match_fixed_sink_without_depth_invention(self):
        self.p["queue_overflow_proof"]["capacity"] = 513
        self.p["queue_overflow_proof"]["actual_depth_trace_available"] = True
        self.rejected("pinned_queue_path_proof")

    def test_retained_pressure_source_rows_do_not_bypass_type_validation(self):
        next(r for r in self.reg if r["type"] == "decision")["skipped_ticks"] = False
        self.rejected("retained_decision_fields_or_types")

    def test_unknown_source_event_is_not_silently_partitioned_as_expected_drop(self):
        self.worker.append({"type": "invented_business_commit"})
        self.rejected("source_unknown_type")

    def test_nan_unused_source_and_missing_summary_do_not_pass(self):
        self.worker[-1]["unused"] = float("nan")
        self.rejected("source_domain")

    def test_direct_malformed_field_returns_false_without_exception(self):
        self.s["window_completion"]["window_finished_ns"] = "bad"
        self.rejected()


class Files(unittest.TestCase):
    def create(self, root):
        w, h, reg, worker, context, summary, policy = fixture()
        values = {"witness": w, "expected-header": h, "regulator-source": reg, "worker-source": worker,
                  "context": context, "summary": summary, "policy": policy}
        args = []
        for label, rows in (("regulator", reg), ("worker", worker)):
            path = root / (label + "-source.jsonl")
            raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
            import hashlib
            summary["pressure_arm"]["source_prefixes"][label] = {"path": str(path), "complete_bytes": len(raw), "rows": len(rows), "tail_bytes": 0, "sha256": hashlib.sha256(raw).hexdigest()}
        for key, value in values.items():
            path = root / (key + (".jsonl" if key.endswith("-source") else ".json"))
            path.write_bytes(("".join(json.dumps(row) + "\n" for row in value) if key.endswith("-source") else json.dumps(value)).encode("utf-8"))
            args.extend(["--" + key, str(path)])
        output = root / "result.json"
        return args + ["--output", str(output)], output

    def test_cli_required_inputs_create_only_and_full_before_after_hashes(self):
        with tempfile.TemporaryDirectory() as name, contextlib.redirect_stdout(io.StringIO()):
            args, output = self.create(Path(name))
            self.assertEqual(checker.main(args), 0)
            r = json.loads(output.read_text())
            self.assertTrue(r["raw_inputs_unchanged"])
            self.assertEqual(len(r["input_sha256_before"]), 7)
            before = output.read_bytes()
            self.assertEqual(checker.main(args), 2)
            self.assertEqual(output.read_bytes(), before)

    def test_after_hash_exception_resets_previously_true_mechanism(self):
        with tempfile.TemporaryDirectory() as name, contextlib.redirect_stdout(io.StringIO()):
            args, output = self.create(Path(name))
            original = checker.sha256_file
            calls = []
            def broken(path):
                calls.append(path)
                if len(calls) == 1:
                    raise OSError("read-after error")
                return original(path)
            with patch.object(checker, "sha256_file", side_effect=broken):
                self.assertEqual(checker.main(args), 2)
            r = json.loads(output.read_text())
            self.assertIs(r["mechanism_passed"], False)
            self.assertIs(r["expected_log_overflow_mechanism_passed"], False)
            self.assertIs(r["raw_inputs_unchanged"], False)

    def test_changed_input_hash_rejects(self):
        with tempfile.TemporaryDirectory() as name, contextlib.redirect_stdout(io.StringIO()):
            args, output = self.create(Path(name))
            original = checker.sha256_file
            def changed(path):
                return "0" * 64 if Path(path).name == "summary.json" else original(path)
            with patch.object(checker, "sha256_file", side_effect=changed):
                self.assertEqual(checker.main(args), 2)
            r = json.loads(output.read_text())
            self.assertIn("input_sha_changed_during_read", {i["code"] for i in r["issues"]})

    def test_strict_source_duplicate_nonfinite_utf8_and_unclosed_line(self):
        for raw in (b'{"type":"x","type":"y"}\n', b'{"type":"x","n":NaN}\n', b'\xff\n', b'{"type":"x"}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as name:
                path = Path(name) / "x.jsonl"
                path.write_bytes(raw)
                with self.assertRaises((ValueError, UnicodeError)):
                    checker.load_source(path)

    def test_output_alias_to_input_does_not_modify_raw(self):
        with tempfile.TemporaryDirectory() as name, contextlib.redirect_stderr(io.StringIO()):
            args, output = self.create(Path(name))
            args[-1] = args[1]
            path = Path(args[1])
            before = path.read_bytes()
            with self.assertRaises(SystemExit):
                checker.main(args)
            self.assertEqual(path.read_bytes(), before)

    def test_before_arm_consumed_prefix_sha_is_verified_against_full_source(self):
        with tempfile.TemporaryDirectory() as name, contextlib.redirect_stdout(io.StringIO()):
            args, output = self.create(Path(name))
            summary_path = Path(name) / "summary.json"
            summary = json.loads(summary_path.read_text())
            summary["pressure_arm"]["source_prefixes"]["worker"]["sha256"] = "0" * 64
            summary_path.write_text(json.dumps(summary))
            self.assertEqual(checker.main(args), 2)
            self.assertIs(json.loads(output.read_text())["mechanism_passed"], False)

    def test_early_prefix_pin_cannot_borrow_later_source_native_rows(self):
        import hashlib
        with tempfile.TemporaryDirectory() as name, contextlib.redirect_stdout(io.StringIO()):
            args, output = self.create(Path(name))
            summary_path = Path(name) / "summary.json"
            summary = json.loads(summary_path.read_text())
            source = Path(name) / "worker-source.jsonl"
            first = source.read_bytes().splitlines(keepends=True)[0]
            summary["pressure_arm"]["source_prefixes"]["worker"].update(complete_bytes=len(first), rows=1, sha256=hashlib.sha256(first).hexdigest())
            summary_path.write_text(json.dumps(summary))
            self.assertEqual(checker.main(args), 2)
            self.assertIs(json.loads(output.read_text())["mechanism_passed"], False)


if __name__ == "__main__":
    unittest.main()
