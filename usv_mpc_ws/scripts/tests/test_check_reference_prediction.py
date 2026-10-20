"""Behavioral decoded-record tests; ROS, numpy and bag writes are unnecessary."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_reference_prediction as checker

NS = 1_000_000_000
TYPES = {checker.DEFAULT_TOPICS[role]: value for role, value in checker.TOPIC_TYPES.items()}

def fixture():
    context = {"run_id": "run-4", "producer_instance_id": "producer-4", "baseline_id": "F4-1",
               "config_hash": "a" * 64, "steady_clock_domain": "boot:steady_clock", "frozen_baseline_verified": True,
               "reference_prediction_contract": {"enabled": True, "schema_version": checker.SCHEMA,
                   "matrix_layout": "k_major", "prediction_policy": "accepted_post_deadline_only",
                   "record_policy": "solve_invoked_only", "nominal_config_hash": "b" * 64,
                   "horizon_steps": 2, "prediction_dt": .2, "backend": "acados", "source_node_sha256": "c" * 64,
                   "solver_test_evidence": {"path": "/experiment/test_evidence.json", "file_sha256": "d" * 64}}}
    summary = {key: context[key] for key in checker.IDENTITY}
    summary.update(schema_version="p0-contract-v1", normal_end=True, flushed=True, publish_errors=0,
                   queue_dropped_total=0, interrupted_cycle_sequence=0, cycle_invocations_started=3,
                   start_steady_ns=99 * NS, end_steady_ns=102 * NS,
                   reference_prediction={key: context["reference_prediction_contract"][key] for key in
                       ("enabled", "schema_version", "matrix_layout", "prediction_policy", "record_policy", "nominal_config_hash")},
                   streams={role: {"generated": 3, "emitted": 3, "dropped": 0, "first_sequence": 1, "last_sequence": 3}
                            for role in checker.DEFAULT_TOPICS})
    pub = {"schema": "p0-publisher-contract-report/1", "passed": True, "source_event_contract_valid": True,
           "recorded_stream_complete": True, "original_bag_unchanged": True,
           **{key: context[key] for key in ("run_id", "producer_instance_id", "baseline_id")}}
    evidence = {"schema": "p0-reference-solver-test-evidence/1", "baseline_id": "F4-1",
                "source_node_sha256": "c" * 64, "compiled_test_binary_sha256": "e" * 64,
                "gtest_report_sha256": "f" * 64, "exit_code": 0, "all_required_passed": True,
                "required_cases": list(checker.REQUIRED_SOLVER_TEST_CASES), "tested_cases": list(checker.REQUIRED_SOLVER_TEST_CASES),
                "__verified_file_sha256": "d" * 64}
    records = []
    def add(role, time, payload):
        records.append(checker.Record(checker.DEFAULT_TOPICS[role], time, payload))
    for i in range(3):
        seq, steady = i + 1, (100 * NS + i * 200_000_000)
        common = {key: context[key] for key in checker.IDENTITY}
        common.update(schema_version="p0-contract-v1", sequence=seq, clock_epoch=0, sim_time_ns=10 * NS + i * 200_000_000,
                      clock_receive_steady_ns=steady - 1_000_000, clock_age_ns=1_000_000, clock_status="observed")
        cycle = dict(common, solve_invoked=True, applied_sequence=seq, timer_entry_steady_ns=steady,
                     state_copy_steady_ns=steady + 1_000, reference_ready_steady_ns=steady + 2_000,
                     solve_start_steady_ns=steady + 3_000, solve_end_steady_ns=steady + 4_000,
                     publish_end_steady_ns=steady + 5_000, controller_state_6=[float(i), 0., 0., .1, 0., 0.],
                     state_kind="odom_atomic", received_odom_sequence=40 + seq, received_imu_sequence=0,
                     odom_stamp_ns=10 * NS, imu_stamp_ns=0, success=True, deadline_miss=False, rejection_reason="")
        ref = dict(common, schema_version=checker.SCHEMA, cycle_sequence=seq,
                   **{key: cycle[key] for key in ("applied_sequence", "state_copy_steady_ns", "reference_ready_steady_ns",
                          "solve_start_steady_ns", "solve_end_steady_ns", "controller_state_6", "state_kind",
                          "received_odom_sequence", "received_imu_sequence", "odom_stamp_ns", "imu_stamp_ns")},
                   freeze_steady_ns=steady + 6_000, path_received_sequence=5, profile_received_sequence=7,
                   path_stamp_ns=9 * NS, profile_stamp_ns=9 * NS, profile_stamp_known=True,
                   path_size=10, profile_size=10, nearest_index=i, configured_start_offset=3,
                   effective_start_offset=3, start_index=i + 3, profile_synced=True, profile_sync_reason="synced",
                   reference_mode="profile_time", profile_t0_known=True, profile_t0=.1 * i,
                   nominal_config_hash="b" * 64, backend="acados", horizon_steps=2, prediction_dt=.2,
                   matrix_layout="k_major", reference_rows=6, reference_cols=3,
                   reference_data=[float(i), 0., 0., 1., 0., 0., float(i) + .2, 0., 0., 1., 0., 0., float(i) + .4, 0., 0., 1., 0., 0.],
                   solve_success=True, deadline_miss=False, rejection_reason="", prediction_available=True,
                   prediction_reason="accepted_solution", x_pred_rows=6, x_pred_cols=3,
                   x_pred_data=cycle["controller_state_6"] * 3, u_pred_rows=2, u_pred_cols=2, u_pred_data=[12., 12., 13., 13.])
        # Mapped output intentionally differs from candidate U[0].
        add("state", 500 * NS + i * 200_000_000, dict(common, freeze_steady_ns=steady))
        add("applied", 500 * NS + i * 200_000_000 + 100, dict(common, cycle_sequence=seq, final_n=[6., 6.]))
        add("cycle", 500 * NS + i * 200_000_000 + 200, cycle)
        add("reference_prediction", 500 * NS + i * 200_000_000 + 300, ref)
    return records, summary, context, pub, evidence

def items(records, role):
    return [record.payload for record in records if record.topic == checker.DEFAULT_TOPICS[role]]

def run(records, summary, context, pub=None, evidence=None, cfg=None):
    return checker.validate_events(records, TYPES, summary, context, cfg, pub, evidence)

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.records, self.summary, self.context, self.pub, self.evidence = fixture()

    def check(self, code):
        report, ledger = run(self.records, self.summary, self.context, self.pub, self.evidence)
        self.assertFalse(report["passed"])
        self.assertIn(code, [f["code"] for f in report["failures"]])
        return report, ledger

    def normal(self):
        return run(self.records, self.summary, self.context, self.pub, self.evidence)

    def rejected(self, i=1, late=False):
        c, p = items(self.records, "cycle")[i], items(self.records, "reference_prediction")[i]
        c.update(success=False, deadline_miss=late, rejection_reason="deadline_miss" if late else "solve_failed")
        p.update(solve_success=False, deadline_miss=late, rejection_reason=c["rejection_reason"], prediction_available=False,
                 prediction_reason="solve_rejected", x_pred_rows=0, x_pred_cols=0, x_pred_data=[],
                 u_pred_rows=0, u_pred_cols=0, u_pred_data=[])

    def test_complete_observation_is_not_plant_or_gp_proof(self):
        report, ledger = self.normal()
        self.assertTrue(report["passed"], report["failures"])
        self.assertTrue(report["four_research_streams_complete"])
        self.assertTrue(report["actual_solve_input_verified"])
        for key in ("plant_acceptance_observed", "force_measured", "execution_atomicity_proven", "exact_execution_timing_available",
                    "gp_labels_ready", "raw_path_profile_callback_replay_verified"):
            self.assertFalse(report[key])
        self.assertEqual(ledger[-1]["status"], "end_unknown")
        self.assertNotIn("bag_end", json.dumps(ledger))
        self.assertNotIn("source_observation_gap_ns", ledger[-1])

    def test_mapped_command_may_differ_from_candidate_first_input(self):
        self.assertNotEqual(items(self.records, "applied")[0]["final_n"], items(self.records, "reference_prediction")[0]["u_pred_data"][:2])
        self.assertTrue(self.normal()[0]["passed"])

    def test_reference_bad_length(self):
        items(self.records, "reference_prediction")[1]["reference_data"].pop()
        self.check("reference_matrix_invalid")

    def test_reference_transposed_shape(self):
        items(self.records, "reference_prediction")[0].update(reference_rows=3, reference_cols=6)
        self.check("reference_matrix_invalid")

    def test_reference_wrong_layout(self):
        items(self.records, "reference_prediction")[0]["matrix_layout"] = "row_major"
        self.check("reference_matrix_invalid")

    def test_reference_nonfinite(self):
        items(self.records, "reference_prediction")[0]["reference_data"][0] = float("nan")
        self.check("reference_matrix_invalid")

    def test_prediction_wrong_shape(self):
        items(self.records, "reference_prediction")[0]["u_pred_cols"] = 3
        self.check("prediction_matrix_invalid")

    def test_prediction_nonfinite(self):
        items(self.records, "reference_prediction")[1]["x_pred_data"][0] = float("inf")
        self.check("prediction_matrix_invalid")

    def test_failed_and_late_solutions_remain_complete_without_prediction(self):
        self.rejected(0)
        self.rejected(1, late=True)
        report, _ = self.normal()
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["candidate_prediction_available_count"], 1)

    def test_successful_solver_missing_prediction_is_observed_without_fake_arrays(self):
        p = items(self.records, "reference_prediction")[0]
        p.update(prediction_available=False, prediction_reason="prediction_missing_or_invalid",
                 x_pred_rows=0, x_pred_cols=0, x_pred_data=[], u_pred_rows=0, u_pred_cols=0, u_pred_data=[])
        self.assertTrue(self.normal()[0]["passed"])

    def test_failed_prediction_fabrication(self):
        self.rejected()
        p = items(self.records, "reference_prediction")[1]
        p.update(prediction_available=True, prediction_reason="accepted_solution", x_pred_rows=6, x_pred_cols=3,
                 x_pred_data=[0.] * 18, u_pred_rows=2, u_pred_cols=2, u_pred_data=[0.] * 4)
        self.check("rejected_prediction_fabricated")

    def test_success_with_late_flag_cannot_publish_prediction(self):
        items(self.records, "cycle")[1]["deadline_miss"] = True
        items(self.records, "reference_prediction")[1]["deadline_miss"] = True
        self.check("rejected_prediction_fabricated")

    def test_unavailable_prediction_cannot_retain_stale_solver_arrays(self):
        items(self.records, "reference_prediction")[1].update(prediction_available=False, prediction_reason="prediction_missing_or_invalid")
        self.check("unavailable_prediction_not_empty")

    def test_no_solve_cycle_has_no_manufactured_reference(self):
        items(self.records, "cycle")[1]["solve_invoked"] = False
        target = [r for r in self.records if r.topic == checker.DEFAULT_TOPICS["reference_prediction"]][1]
        self.records.remove(target)
        items(self.records, "reference_prediction")[1]["sequence"] = 2
        self.summary["streams"]["reference_prediction"].update(generated=2, emitted=2, last_sequence=2)
        self.assertTrue(self.normal()[0]["passed"])

    def test_standby_fabricated_reference(self):
        items(self.records, "cycle")[1]["solve_invoked"] = False
        self.check("reference_fabricated_for_no_solve")

    def test_missing_actual_solve_invocation_flag(self):
        items(self.records, "cycle")[0].pop("solve_invoked")
        self.check("cycle_solve_invocation_unknown")

    def test_applied_cycle_link_cannot_point_to_another_invocation(self):
        items(self.records, "applied")[0]["cycle_sequence"] = 2
        self.check("cycle_applied_link_missing")

    def test_missing_reference_for_actual_solve(self):
        self.records.remove([r for r in self.records if r.topic == checker.DEFAULT_TOPICS["reference_prediction"]][-1])
        self.check("solve_reference_coverage_mismatch")

    def test_duplicate_same_cycle_even_with_contiguous_reference_sequences(self):
        items(self.records, "reference_prediction")[1]["cycle_sequence"] = 1
        self.check("duplicate_reference_for_cycle")

    def test_missing_cycle(self):
        items(self.records, "reference_prediction")[1]["cycle_sequence"] = 99
        self.check("reference_cycle_missing")

    def test_duplicate_source_sequence(self):
        items(self.records, "reference_prediction")[1]["sequence"] = 1
        self.check("sequence_gap_duplicate_or_regression")

    def test_frozen_input_not_replaced_after_callback_during_solve(self):
        items(self.records, "reference_prediction")[0]["controller_state_6"] = [99.] * 6
        self.check("reference_cycle_freeze_mismatch")

    def test_versions_not_changed_by_postsolve_latest_container_lookup(self):
        items(self.records, "reference_prediction")[1]["path_size"] = 9
        self.check("reference_container_version_mismatch")

    def test_callback_versions_count_clears_and_may_jump(self):
        items(self.records, "reference_prediction")[1]["path_received_sequence"] = 8
        items(self.records, "reference_prediction")[2]["path_received_sequence"] = 10
        self.assertTrue(self.normal()[0]["passed"])

    def test_version_regression(self):
        items(self.records, "reference_prediction")[1]["profile_received_sequence"] = 6
        self.check("reference_version_regression")

    def test_profile_known_stamp_same_version_mismatch(self):
        items(self.records, "reference_prediction")[1]["profile_stamp_ns"] += 1
        self.check("reference_container_version_mismatch")

    def test_fallback_mode_does_not_fake_time_profile(self):
        for p in items(self.records, "reference_prediction"):
            p.update(profile_synced=False, profile_t0_known=False, profile_t0=0., profile_sync_reason="stamp_mismatch",
                     reference_mode="cruise_arc_fallback")
        self.assertTrue(self.normal()[0]["passed"])

    def test_malformed_profile_stamp_is_explicit_unknown(self):
        for p in items(self.records, "reference_prediction"):
            p.update(profile_stamp_known=False, profile_stamp_ns=-1, profile_synced=False,
                     profile_t0_known=False, profile_t0=0., reference_mode="cruise_arc_fallback", profile_sync_reason="stamp_missing")
        self.assertTrue(self.normal()[0]["passed"])

    def test_unknown_stamp_does_not_reuse_latest_valid_stamp(self):
        for p in items(self.records, "reference_prediction"):
            p["profile_stamp_known"] = False
        self.check("profile_unknown_stamp_fabricated")

    def test_unknown_t0_does_not_reuse_latest_valid_t0(self):
        for p in items(self.records, "reference_prediction"):
            p.update(profile_synced=False, profile_t0_known=False, reference_mode="cruise_arc_fallback")
        self.check("profile_unknown_t0_fabricated")

    def test_bad_synced_profile_size(self):
        items(self.records, "reference_prediction")[0]["profile_size"] = 9
        self.check("profile_mode_inconsistent")

    def test_bad_nearest_start_rule(self):
        items(self.records, "reference_prediction")[0]["start_index"] = 0
        self.check("reference_index_metadata_invalid")

    def test_path_can_clear_between_eligibility_check_and_frozen_build_without_faking_record(self):
        for p in items(self.records, "reference_prediction"):
            p.update(path_size=0, nearest_index=-1, start_index=-1, profile_synced=False, profile_t0_known=False,
                     profile_t0=0., reference_mode="empty_path", profile_sync_reason="empty_path", reference_data=[0.] * 18)
        report, _ = self.normal()
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["reference_path_eligibility_anomaly_count"], 3)

    def test_empty_path_builder_cannot_invent_nonzero_reference(self):
        for p in items(self.records, "reference_prediction"):
            p.update(path_size=0, nearest_index=-1, start_index=-1, profile_synced=False, profile_t0_known=False,
                     profile_t0=0., reference_mode="empty_path", profile_sync_reason="empty_path")
        self.check("empty_path_reference_not_zero")

    def test_path_can_shrink_to_one_point_before_actual_build(self):
        for p in items(self.records, "reference_prediction"):
            p.update(path_size=1, nearest_index=0, start_index=0, profile_synced=False, profile_t0_known=False,
                     profile_t0=0., reference_mode="cruise_arc_fallback", profile_sync_reason="length_mismatch")
        report, _ = self.normal()
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["reference_path_eligibility_anomaly_count"], 3)

    def test_negative_configured_offset_clamps_to_one(self):
        for p in items(self.records, "reference_prediction"):
            p.update(configured_start_offset=-3, effective_start_offset=1, start_index=p["nearest_index"] + 1)
        self.assertTrue(self.normal()[0]["passed"])

    def test_nominal_model_identity_differs(self):
        items(self.records, "reference_prediction")[0]["nominal_config_hash"] = "1" * 64
        self.check("nominal_config_identity_mismatch")

    def test_runtime_horizon_not_assumed(self):
        self.context["reference_prediction_contract"]["horizon_steps"] = 20
        self.check("model_config_mismatch")

    def test_runtime_dt_not_assumed(self):
        self.context["reference_prediction_contract"]["prediction_dt"] = .1
        self.check("model_config_mismatch")

    def test_wrong_producer_identity(self):
        items(self.records, "reference_prediction")[0]["producer_instance_id"] = "other"
        self.check("source_identity_mismatch")

    def test_wrong_extension_schema(self):
        items(self.records, "reference_prediction")[0]["schema_version"] = "p0-contract-v1"
        self.check("source_schema_mismatch")

    def test_epoch_fields_are_frozen_from_cycle(self):
        items(self.records, "reference_prediction")[0]["clock_epoch"] = 1
        self.check("reference_cycle_freeze_mismatch")

    def test_reset_cannot_create_cross_epoch_observation_gap(self):
        for role in ("cycle", "reference_prediction"):
            items(self.records, role)[2]["clock_epoch"] = 1
        report, ledger = self.normal()
        self.assertTrue(report["passed"])
        self.assertEqual(ledger[-2]["status"], "source_boundary_invalid")
        self.assertNotIn("source_observation_gap_ns", ledger[-2])

    def test_reference_freeze_precedes_solve_end(self):
        p = items(self.records, "reference_prediction")[0]
        p["freeze_steady_ns"] = p["solve_start_steady_ns"]
        self.check("reference_steady_timing_invalid")

    def test_unknown_clock_status_is_not_accepted_even_if_cycle_agrees(self):
        for role in ("cycle", "reference_prediction"):
            items(self.records, role)[0]["clock_status"] = "unknown"
        self.check("invalid_clock_metadata")

    def test_source_sim_rollback_without_epoch(self):
        for role in ("cycle", "reference_prediction"):
            items(self.records, role)[1]["sim_time_ns"] = 1
        self.check("unsegmented_clock_regression")

    def test_reference_order_cannot_shuffle_correct_cycle_ids(self):
        a, b = items(self.records, "reference_prediction")[:2]
        a["cycle_sequence"], b["cycle_sequence"] = b["cycle_sequence"], a["cycle_sequence"]
        self.check("solve_reference_order_mismatch")

    def test_summary_drop(self):
        self.summary["streams"]["reference_prediction"]["dropped"] = 1
        self.summary["queue_dropped_total"] = 1
        self.check("source_recorded_count_mismatch")

    def test_summary_prefix_suffix_missing(self):
        self.summary["streams"]["reference_prediction"]["last_sequence"] = 4
        self.check("source_boundary_mismatch")

    def test_summary_new_stream_missing(self):
        del self.summary["streams"]["reference_prediction"]
        self.check("source_summary_count_missing")

    def test_summary_publish_error(self):
        self.summary["publish_errors"] = 1
        self.check("session_end_unknown_or_unflushed")

    def test_original_f3_without_extension_is_not_f4_complete(self):
        self.summary.pop("reference_prediction")
        self.context.pop("reference_prediction_contract")
        report, _ = self.check("reference_extension_not_enabled")
        self.assertFalse(report["actual_solve_input_verified"])

    def test_metadata_detects_simultaneous_all_four_stream_drop(self):
        counts = {topic: 3 for topic in checker.DEFAULT_TOPICS.values()}
        self.records = self.records[:-4]
        report, _ = run(self.records, self.summary, self.context, self.pub, self.evidence, checker.Config(expected_counts=counts))
        self.assertFalse(report["passed"])
        self.assertIn("metadata_decoded_count_mismatch", [f["code"] for f in report["failures"]])

    def test_reference_publication_order_is_independent_of_bag_time_domain(self):
        self.records = [checker.Record(r.topic, r.bag_ns + 1_700_000_000 * NS, r.payload) for r in self.records]
        self.assertTrue(self.normal()[0]["passed"])

    def test_missing_evidence_preserves_four_stream_completeness_but_does_not_certify_input(self):
        report, _ = run(self.records, self.summary, self.context, self.pub)
        self.assertTrue(report["passed"])
        self.assertFalse(report["actual_solve_input_verified"])

    def test_stale_evidence_does_not_certify_new_baseline(self):
        self.evidence["baseline_id"] = "F3-1"
        report, _ = self.normal()
        self.assertTrue(report["passed"])
        self.assertFalse(report["frozen_solver_test_evidence_verified"])

    def test_evidence_empty_required_list_cannot_self_certify(self):
        self.evidence.update(required_cases=[], tested_cases=[])
        self.assertFalse(self.normal()[0]["actual_solve_input_verified"])

    def test_evidence_missing_real_case_cannot_self_certify(self):
        self.evidence["tested_cases"].pop()
        self.assertFalse(self.normal()[0]["actual_solve_input_verified"])

    def test_evidence_hash_not_bound(self):
        self.evidence["__verified_file_sha256"] = "1" * 64
        self.assertFalse(self.normal()[0]["actual_solve_input_verified"])

    def test_unfrozen_baseline_does_not_certify_input(self):
        self.context["frozen_baseline_verified"] = False
        self.assertFalse(self.normal()[0]["actual_solve_input_verified"])

    def test_missing_publisher_checks_do_not_silently_replace_raw_stream_validation(self):
        report, _ = run(self.records, self.summary, self.context, None, self.evidence)
        self.assertTrue(report["four_research_streams_complete"])
        self.assertFalse(report["combined_recording_contract_verified"])
        self.assertFalse(report["actual_solve_input_verified"])

    def test_mismatched_publisher_identity(self):
        self.pub["producer_instance_id"] = "old-producer"
        self.assertFalse(self.normal()[0]["combined_recording_contract_verified"])

    def test_old_three_stream_checker_accepts_extra_summary_stream_without_change(self):
        # Source is unchanged; only inspect its real validation with its existing behavioral fixture.
        scripts = Path(__file__).resolve().parents[2] / "p0_contract_impl_2026-10-03/source/usv_mpc_ws/scripts"
        if not scripts.is_dir():
            self.skipTest("local original checker snapshot is unavailable in this separate test deployment")
        sys.path.insert(0, str(scripts))
        spec = importlib.util.spec_from_file_location("_legacy_p0_fixture", scripts / "tests/test_check_p0_contract.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        records, summary, context = module.fixture()
        summary["reference_prediction"] = self.summary["reference_prediction"]
        summary["streams"]["reference_prediction"] = self.summary["streams"]["reference_prediction"]
        self.assertTrue(module.run(records, summary, context)[0]["passed"])

class ReadonlyTests(unittest.TestCase):
    def cli_fixture(self, path):
        bag = path / "bag"
        bag.mkdir()
        (bag / "metadata.yaml").write_text("metadata", encoding="utf-8")
        records, summary, context, pub, evidence = fixture()
        evidence.pop("__verified_file_sha256")
        evidence_path = path / "evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        context["reference_prediction_contract"]["solver_test_evidence"] = {
            "path": str(evidence_path.resolve()), "file_sha256": checker.hash_file(evidence_path)}
        pub.update(bag_hash_before=checker.hash_bag(bag), bag_hash_after=checker.hash_bag(bag))
        for name, value in (("summary", summary), ("context", context), ("pub", pub)):
            (path / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
        args = [str(bag), "--session-summary", str(path / "summary.json"), "--run-context", str(path / "context.json"),
                "--publisher-contract-report", str(path / "pub.json"), "--output-dir", str(path / "report")]
        return bag, records, args

    def test_cli_hash_binds_evidence_and_keeps_bag_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            bag, records, args = self.cli_fixture(path)
            before = checker.hash_bag(bag)
            with mock.patch.object(checker, "read_bag", return_value=(records, TYPES, {"mocked_reader": True})), contextlib.redirect_stdout(io.StringIO()):
                rc = checker.main(args)
            self.assertEqual(rc, 0)
            self.assertEqual(checker.hash_bag(bag), before)
            report = json.loads((path / "report/reference_prediction_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["actual_solve_input_verified"])
            self.assertTrue(report["original_bag_unchanged"])

    def test_cli_detects_bag_mutation_and_revokes_combined_proof(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            bag, records, args = self.cli_fixture(path)
            def mutate(_bag, _cfg):
                (bag / "metadata.yaml").write_text("changed by a simulated external writer", encoding="utf-8")
                return records, TYPES, {"mocked_reader": True}
            with mock.patch.object(checker, "read_bag", side_effect=mutate), contextlib.redirect_stdout(io.StringIO()):
                rc = checker.main(args)
            self.assertEqual(rc, 2)
            report = json.loads((path / "report/reference_prediction_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["original_bag_unchanged"])
            self.assertFalse(report["actual_solve_input_verified"])
            self.assertFalse(report["four_research_streams_complete"])

    def test_reject_output_inside_bag_before_any_storage_read(self):
        with tempfile.TemporaryDirectory() as td:
            bag = Path(td) / "bag"
            bag.mkdir()
            original = bag / "metadata.yaml"
            original.write_text("metadata", encoding="utf-8")
            before = checker.hash_bag(bag)
            with contextlib.redirect_stderr(io.StringIO()):
                rc = checker.main([str(bag), "--session-summary", "unused", "--run-context", "unused",
                                   "--publisher-contract-report", "unused", "--output-dir", str(bag / "report")])
            self.assertEqual(rc, 1)
            self.assertEqual(checker.hash_bag(bag), before)

    def test_stale_publisher_report_bag_hash_rejected_without_storage_read(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            bag = path / "bag"
            bag.mkdir()
            (bag / "metadata.yaml").write_text("metadata", encoding="utf-8")
            records, summary, context, pub, evidence = fixture()
            for name, value in (("summary", summary), ("context", context), ("pub", pub)):
                (path / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
            with mock.patch.object(checker, "read_bag") as reader, contextlib.redirect_stdout(io.StringIO()):
                rc = checker.main([str(bag), "--session-summary", str(path / "summary.json"), "--run-context", str(path / "context.json"),
                                   "--publisher-contract-report", str(path / "pub.json"), "--output-dir", str(path / "report")])
            self.assertEqual(rc, 1)
            reader.assert_not_called()
            report = json.loads((path / "report/reference_prediction_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["original_bag_unchanged"])
            self.assertFalse(report["actual_solve_input_verified"])

if __name__ == "__main__":
    unittest.main()
