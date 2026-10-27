#!/usr/bin/env python3
"""Decoded fixtures test actual contract risks without ROS or simulated bag claims."""
import copy
import unittest
import json
from pathlib import Path
import tempfile
import check_p1_execution as checker


def fixture():
    digest = "a" * 64
    c = {"clock": "CLOCK_MONOTONIC", "N": 20, "dt": .2, "T_ns": 200000000,
         "deadline_ns": 150000000, "execute_qualified": False, "parameters_are_diagnostic_only": True,
         "nominal_hash": "b" * 64, "command_min_n": -25, "command_max_n": 25,
         "activation_tolerance": [.25, .25, .15, .3, .2, .15], "rho_n_s": 80,
         "publish_gap_ns": 240000000, "target_sim_slack_ns": 20000000,
         "tick_jitter_ns": 20000000, "odom_age_ns": 100000000, "imu_age_ns": 100000000,
         "clock_age_ns": 100000000, "rtf_low": .95, "rtf_high": 1.05,
         "input_topics": {"odom": "/odom", "imu": "/imu", "path": "/path", "profile": "/profile"}}
    context = {"run_id": "run", "mode": "no_output", "boot_id": "boot", "contract_hash": digest,
               "_worker_verified_instance": "worker", "_worker_owned_pid": 42,
               "_fixture_owned_pid": 43,
               "runner_summary_facts": {"graph_no_physical_publishers": True},
               "_fixture_summary": {"type": "fixture_summary", "schema": "p1-synthetic-fixture-v1",
                   "contract_sha256": digest, "boot_id": "boot", "pid": 43, "error": None,
                   "physical_endpoints": 0, "actual_plant": False, "publisher_side_counts_only": True,
                   "counts": {"clock": 500, "odom": 500, "imu": 500, "path": 10, "profile": 10}},
               "_actual_topic_counts": {"/clock": 500, "/odom": 500, "/imu": 500, "/path": 10, "/profile": 10},
               "lifecycle": {key: True for key in ("regulator_exited", "worker_exited", "recorder_exited", "cleanup_success",
                                                   "regulator_source_flush_verified", "worker_source_flush_verified")}}
    job = {k: 0 for k in checker.JOB_FIELDS}
    job.update(schema_version="p1-solve-job-v1", run_id="run", boot_id="boot", contract_hash=digest,
               nominal_hash=c["nominal_hash"], worker_instance="worker", job_id=1, target_tick=1,
               task_generation=1, model_generation=1, config_generation=1, schedule_generation=1,
               tick_origin_steady_ns=1000000000, freeze_steady_ns=1010000000,
               deadline_steady_ns=1150000000, target_steady_ns=1200000000, target_sim_ns=1200000000,
               odom_stamp_ns=1000000000, odom_receive_ns=1001000000, odom_sequence=1,
               r_from_imu=False, horizon_steps=20, prediction_dt=.2, frozen_state=[0.]*6,
               target_state=[0.]*6, reference=[0.]*126, anchor_n=[0., 0.], anchor_sequence=[1, 1],
               anchor_publish_ns=[990000000, 990000000], anchor_known=[True, True], reset_warmstart=False,
               frozen_clock_sim_ns=1010000000, frozen_clock_receive_ns=1010000000, assumed_rtf=1.,
               anchor_source="synthetic_static_fixture", anchor_producer="reg", anchor_run_id="run",
               history_sim_ns=[], history_channel=[], history_n=[])
    candidate = {"job": job, "worker_instance": "worker", "worker_receive_ns": 1020000000,
                 "solve_start_ns": 1030000000, "solve_end_ns": 1040000000, "solver_invoked": True,
                 "success": True, "prediction_available": True, "reason": "", "backend": "acados", "backend_ms": .1,
                 "first_control": [0., 0.], "x_prediction": [0.]*126, "u_prediction": [0.]*40}
    d = {k: 0 for k in checker.DECISION_FIELDS}
    d.update(schema_version="p1-execution-decision-v1", run_id="run", boot_id="boot", contract_hash=digest,
             worker_instance="worker", mode="no_output", sequence=1, tick=1, job_id=1,
             task_generation=1, model_generation=1, config_generation=1, schedule_generation=1,
             tick_planned_ns=1200000000, tick_start_ns=1200000000, cutoff_commit_ns=1150000001,
             candidate_ready_commit_ns=1100000000, activation_commit_ns=1200000000,
             tick_end_ns=1200001000, candidate_accepted=True, diagnostic_only=True, reason="",
             control_source="candidate", target_state=[0.]*6, activation_state=[0.]*6, state_error=[0.]*6,
             requested_n=[0., 0.], final_n=[0., 0.], publish_success=[False, False], publish_start_ns=[0, 0],
             publish_end_ns=[0, 0], anchor_known=[True, True], anchor_sequence=[1, 1], previous_n=[0., 0.],
             previous_publish_ns=[990000000, 990000000], normal_contract_complete=False, rho_available=False,
             plant_acceptance_observed=False, previous_anchor_known=[True, True], publish_sim_ns=[0, 0],
             publish_epoch=[0, 0], publish_clock_age_ns=[0, 0], activation_clock_sim_ns=1200000000,
             activation_clock_receive_ns=1200000000, activation_rtf=1.)
    sj = {checker.JOB_ALIASES.get(k, k): v for k, v in job.items()}
    sc = {checker.CANDIDATE_ALIASES.get(k, k): v for k, v in candidate.items() if k != "job"}
    sc.update(type="candidate", job=sj)
    sd = {checker.DECISION_ALIASES.get(k, k): v for k, v in d.items()}
    sd["type"] = "decision"
    reg = [{"type": "startup", "mode": "no_output", "run_id": "run", "boot": "boot", "clock": "CLOCK_MONOTONIC",
            "contract_hash": digest, "physical_publisher_endpoints": 0}, {"type": "job", "job": sj},
           {"type": "candidate_registration", "job": sj, "accepted_registration": True, "ready_commit_ns": 1100000000},
           sd, {"type": "regulator_shutdown", "plant_hold_end_known": False},
           {"type": "source_summary", "generated": 5, "emitted": 5, "dropped": 0, "normal_source_complete": True}]
    worker = [sc, {"type": "worker_summary", "generated_candidates": 1, "published_candidates": 1,
                   "fatal": False, "normal_source_complete": True}]
    bag = {topic: [] for topic in checker.TOPICS}
    bag["/p1/solve_job"] = [{"message": job}]
    bag["/p1/solve_candidate"] = [{"message": candidate}]
    bag["/p1/execution_decision"] = [{"message": d}]
    bag["/p1/worker_capability"] = [{"message": {"run_id": "run", "worker_instance": "worker", "pid": 42,
        "boot_id": "boot", "contract_hash": digest, "nominal_hash": c["nominal_hash"],
        "clock_name": "CLOCK_MONOTONIC", "backend": "acados", "horizon_steps": 20,
        "prediction_dt": .2, "matrix_layout": "column_major", "pending_count": 0}}]
    # Independent decoded sources are essential: mutations must not share lists
    # with the simulated storage message and accidentally conceal mismatches.
    return tuple(copy.deepcopy(v) for v in (reg, worker, bag, c, context, digest))


def decision_update(f, **fields):
    for field, value in fields.items():
        f[0][3][checker.DECISION_ALIASES.get(field, field)] = copy.deepcopy(value)
        f[2]["/p1/execution_decision"][0]["message"][field] = copy.deepcopy(value)


def shadow_fixture():
    f = fixture()
    f[0][0]["mode"] = f[4]["mode"] = "shadow"
    decision_update(f, mode="shadow")
    f[4].pop("_fixture_summary")
    f[4].pop("_fixture_owned_pid")
    f[4]["runner_summary_facts"] = {"graph_no_physical_publishers": False,
        "graph_new_physical_publishers_zero": True, "graph_sole_physical_owner_verified": True,
        "graph_physical_owner_node": "mpc_controller_node",
        "graph_physical_publishers_per_channel": {"left": 1, "right": 1}}
    return f


class CheckerRisks(unittest.TestCase):
    def check(self, f):
        return checker.validate_decoded(*f)

    def has(self, report, code):
        self.assertIn(code, [e["code"] for e in report["issues"]])

    def test_complete_no_output_does_not_certify_physical_contract(self):
        r = self.check(fixture())
        self.assertEqual(r["issues"], [])
        self.assertTrue(r["diagnostic_complete"])
        self.assertFalse(r["normal_contract_complete"])
        self.assertFalse(r["guarantees"]["plant_force_measured"])

    def test_exact_u_payload_mismatch(self):
        f = fixture(); f[1][0]["U"][3] = .125
        self.has(self.check(f), "source_bag_payload_mismatch")

    def test_duplicate_bag_decision_cannot_hide_in_dict(self):
        f = fixture(); f[2]["/p1/execution_decision"].append(copy.deepcopy(f[2]["/p1/execution_decision"][0]))
        self.has(self.check(f), "duplicate_identity")

    def test_unflushed_unknown_is_not_inferred_from_complete_counts(self):
        f = fixture(); del f[4]["lifecycle"]["worker_source_flush_verified"]
        r = self.check(f)
        self.assertTrue(r["source_bag_contract_complete"])
        self.assertFalse(r["lifecycle_verified"])
        self.assertFalse(r["passed"])

    def test_completion_one_ns_late_rejected_by_checker(self):
        f = fixture(); f[0][2]["ready_commit_ns"] = 1150000001
        self.has(self.check(f), "ready_after_deadline")

    def test_equal_completion_is_valid(self):
        f = fixture(); f[0][2]["ready_commit_ns"] = 1150000000
        f[0][3]["ready_commit_ns"] = 1150000000
        f[2]["/p1/execution_decision"][0]["message"]["candidate_ready_commit_ns"] = 1150000000
        self.assertEqual(self.check(f)["issues"], [])

    def test_wrong_target_and_new_task_generation(self):
        f = fixture(); f[0][3]["tick"] = 2; f[2]["/p1/execution_decision"][0]["message"]["tick"] = 2
        self.has(self.check(f), "activation_wrong_target")
        f = fixture(); f[0][3]["task_generation"] = 2; f[2]["/p1/execution_decision"][0]["message"]["task_generation"] = 2
        self.has(self.check(f), "activation_version")

    def test_target_clock_drift_not_just_state_zero(self):
        f = fixture(); f[0][3]["activation_clock_sim_ns"] += 21000000
        f[2]["/p1/execution_decision"][0]["message"]["activation_clock_sim_ns"] += 21000000
        self.has(self.check(f), "activation_target_sim_alignment")

    def test_missing_source_field_cannot_be_backfilled_from_bag(self):
        f = fixture(); del f[1][0]["backend_ms"]
        self.has(self.check(f), "source_or_bag_field_missing")

    def test_diagnostic_physical_publish_is_not_allowed(self):
        f = fixture(); f[0][3]["publish_success"] = [True, False]
        f[2]["/p1/execution_decision"][0]["message"]["publish_success"] = [True, False]
        self.has(self.check(f), "diagnostic_physical_overclaim")

    def test_nan_prediction_is_not_finite(self):
        f = fixture(); f[2]["/p1/solve_candidate"][0]["message"]["x_prediction"][5] = float("nan")
        self.has(self.check(f), "candidate_shape_nonfinite")

    def test_worker_summary_drop_is_not_normal_complete(self):
        f = fixture(); f[1][-1]["published_candidates"] = 0
        self.has(self.check(f), "worker_source_counts_or_incomplete")

    def test_activation_jitter_equal_passes_one_ns_after_fails(self):
        for jitter, valid in ((19999999, True), (20000000, True), (20000001, False)):
            with self.subTest(jitter=jitter):
                f = fixture()
                decision_update(f, activation_commit_ns=1200000000+jitter, tick_end_ns=1200001000+jitter)
                r = self.check(f)
                if valid:
                    self.assertEqual(r["issues"], [])
                else:
                    self.has(r, "accepted_activation_jitter_gate")

    def test_odom_age_advances_between_start_and_activation(self):
        f = fixture()
        decision_update(f, odom_age_ns=90000000, activation_commit_ns=1220000000, tick_end_ns=1220001000)
        self.has(self.check(f), "accepted_activation_source_age_gate")
        decision_update(f, odom_age_ns=80000000)
        self.assertEqual(self.check(f)["issues"], [])

    def test_received_during_tick_lock_wait_can_have_negative_start_age(self):
        f = fixture()
        decision_update(f, odom_age_ns=-1000000, activation_commit_ns=1202000000, tick_end_ns=1202001000)
        self.assertEqual(self.check(f)["issues"], [])
        decision_update(f, odom_age_ns=-3000000)
        self.has(self.check(f), "accepted_activation_source_age_gate")

    def test_positive_imu_age_rechecked_zero_is_explicitly_unproven_mixed_flag(self):
        f = fixture()
        decision_update(f, imu_age_ns=100000001)
        self.has(self.check(f), "accepted_activation_source_age_gate")
        decision_update(f, imu_age_ns=0)
        r = self.check(f)
        self.assertEqual(r["issues"], [])
        self.assertFalse(r["activation_source_contract_complete"])
        self.assertIn("mixed", r["activation_source_evidence_limit"])

    def test_latest_clock_receive_not_obsolete_tick_start_clock_age(self):
        f = fixture()
        # Tick-start clock is old, but a later callback provided current clock.
        decision_update(f, clock_age_ns=90000000, activation_commit_ns=1220000000,
                        tick_end_ns=1220001000, activation_clock_receive_ns=1220000000,
                        activation_clock_sim_ns=1220000000)
        self.assertEqual(self.check(f)["issues"], [])

    def test_current_clock_age_equal_stale_future_and_missing(self):
        for age, valid in ((100000000, True), (100000001, False), (-1, False)):
            with self.subTest(age=age):
                f = fixture()
                decision_update(f, activation_clock_receive_ns=1200000000-age,
                                activation_clock_sim_ns=1200000000-age)
                r = self.check(f)
                if valid:
                    self.assertEqual(r["issues"], [])
                else:
                    self.has(r, "accepted_activation_clock_age_gate")
        f = fixture()
        del f[0][3]["activation_clock_receive_ns"]
        self.has(self.check(f), "source_or_bag_field_missing")

    def test_rtf_inclusive_bounds_and_nonfinite(self):
        for rtf, valid in ((.95, True), (1.05, True), (.949999, False), (1.050001, False), (float("nan"), False)):
            with self.subTest(rtf=rtf):
                f = fixture(); decision_update(f, activation_rtf=rtf)
                r = self.check(f)
                if valid:
                    self.assertEqual(r["issues"], [])
                else:
                    self.has(r, "accepted_activation_rtf_gate")
        f = fixture(); del f[3]["rtf_low"]
        self.has(self.check(f), "accepted_activation_rtf_gate")

    def test_owned_worker_instance_cannot_be_substituted_consistently(self):
        f = fixture(); f[4]["_worker_verified_instance"] = "foreign-worker"
        r = self.check(f)
        self.has(r, "job_owned_worker_instance")
        self.has(r, "candidate_owned_worker_instance")
        self.has(r, "activation_owned_worker_instance")
        self.assertFalse(r["lifecycle_verified"])

    def test_owned_worker_pid_or_handshake_unknown_not_inferred(self):
        f = fixture(); f[4]["_worker_owned_pid"] = 999
        self.has(self.check(f), "capability_owned_pid_or_instance")
        f = fixture(); f[4].pop("_worker_verified_instance")
        self.has(self.check(f), "owned_worker_capability_binding_unknown")
        f = fixture(); f[2]["/p1/worker_capability"] = []
        self.has(self.check(f), "owned_worker_capability_missing_from_bag")

    def test_shadow_legacy_sole_owner_is_valid_despite_nonzero_whole_graph(self):
        r = self.check(shadow_fixture())
        self.assertEqual(r["issues"], [])
        self.assertTrue(r["diagnostic_complete"])
        self.assertIsNone(r["raw_input_recording_complete"])
        self.assertIn("unknown whole-run", r["raw_input_recording_scope"])
        self.assertFalse(r["normal_contract_complete"])

    def test_shadow_owner_new_publishers_counts_and_unknown_rejected(self):
        mutations = (("graph_new_physical_publishers_zero", False, "runner_graph_new_physical_publishers_unknown_or_nonzero"),
                     ("graph_sole_physical_owner_verified", None, "runner_graph_sole_physical_owner_unknown_or_wrong"),
                     ("graph_physical_owner_node", "p1_regulator", "runner_graph_sole_physical_owner_unknown_or_wrong"),
                     ("graph_physical_publishers_per_channel", {"left": 2, "right": 1}, "runner_graph_sole_physical_owner_unknown_or_wrong"))
        for key, value, code in mutations:
            with self.subTest(key=key):
                f = shadow_fixture(); f[4]["runner_summary_facts"][key] = value
                self.has(self.check(f), code)

    def test_raw_prefix_gap_cannot_be_hidden_by_typed_complete(self):
        f = fixture()
        f[4]["_fixture_summary"]["counts"].update(clock=493, odom=493, imu=493)
        f[4]["_actual_topic_counts"].update({"/clock": 351, "/odom": 351, "/imu": 351})
        r = self.check(f)
        self.assertTrue(r["source_bag_contract_complete"])
        self.assertFalse(r["raw_input_recording_complete"])
        self.assertFalse(r["diagnostic_complete"])
        self.assertFalse(r["passed"])
        self.has(r, "fixture_raw_publisher_bag_count_mismatch_or_unknown")

    def test_all_five_raw_topics_independently_required(self):
        for name in ("clock", "odom", "imu", "path", "profile"):
            with self.subTest(input=name):
                f = fixture()
                topic = "/clock" if name == "clock" else f[3]["input_topics"][name]
                f[4]["_actual_topic_counts"][topic] -= 1
                self.assertFalse(self.check(f)["raw_input_recording_complete"])
        f = fixture(); del f[4]["_fixture_summary"]
        r = self.check(f)
        self.has(r, "fixture_summary_missing")
        self.assertFalse(r["diagnostic_complete"])

    def test_raw_complete_does_not_require_source_callbacks_equal_publishes(self):
        f = fixture()
        # Publisher/bag counts are distinct from the source callbacks actually
        # received and represented by frozen jobs. No equality is invented.
        r = self.check(f)
        self.assertTrue(r["raw_input_recording_complete"])
        self.assertEqual(r["streams"]["jobs"]["source_count"], 1)
        self.assertEqual(r["raw_input_count_comparison"]["odom"]["fixture_published"], 500)
        self.assertFalse(r["guarantees"]["raw_callback_bag_exact_reconstruction_proven"])

    def test_fixture_wrong_identity_or_unclosed_error_not_complete(self):
        for key, value in (("pid", 999), ("contract_sha256", "foreign"), ("error", "write failed"), ("actual_plant", True)):
            with self.subTest(key=key):
                f = fixture(); f[4]["_fixture_summary"][key] = value
                self.has(self.check(f), "fixture_identity_or_completion_unverified")

    def test_runtime_reads_verified_handshake_and_does_not_require_shadow_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            ex = Path(directory)
            binary = ex / "authored_dummy_executable"; binary.write_bytes(b"test executable identity")
            digest = checker.sha(binary)
            raw = {"run_id": "run", "mode": "shadow", "boot_id": "boot",
                   "contract_sha256": "a"*64, "python_monotonic_clock": {"implementation": "clock_gettime(CLOCK_MONOTONIC)", "monotonic": True},
                   "binaries": {name: {"path": str(binary), "sha256": digest} for name in ("worker", "regulator")}}
            cleanup = {name: {"cleanup_complete": True, "returncode": 0} for name in ("worker", "regulator", "recorder")}
            summary = {"run_id": "run", "supervision_evidence_complete": True, "cleanup_complete": True,
                       "cleanup_failed": False, "cleanup": cleanup, "expected_fault": "none",
                       "graph_no_physical_publishers": False, "graph_new_physical_publishers_zero": True,
                       "graph_sole_physical_owner_verified": True, "graph_physical_owner_node": "mpc_controller_node",
                       "graph_physical_publishers_per_channel": {"left": 1, "right": 1}}
            ledger = [{"type": "spawn", "name": name, "boot_id": "boot", "executable_verified": True,
                       "expected_sha256": digest, "identity": {"pid": pid, "pgid": pid, "sid": pid,
                       "start_ticks": 123, "exe_sha256": digest}}
                      for name, pid in (("worker", 42), ("regulator", 44), ("recorder", 45))]
            ledger.append({"type": "worker_capability_verified", "boot_id": "boot", "pid": 42,
                           "worker_instance": "worker", "backend": "acados"})
            ledger += [{"type": "cleanup_result", "boot_id": "boot", "name": name, **value} for name, value in cleanup.items()]
            ledger.append({"type": "supervisor_summary", "boot_id": "boot", "cleanup_failed": False})
            (ex / "runner_summary.json").write_text(json.dumps(summary))
            def write_ledger():
                (ex / "owned_process_ledger.jsonl").write_text("".join(json.dumps(e)+"\n" for e in ledger))
            write_ledger()
            for name in ("worker", "regulator"):
                (ex / f"{name}.console.log").write_text(f"{name.upper()}_CLOSE_FLUSH_SUCCESS=true\n")
            c, _ = checker.runtime_context(ex, raw)
            self.assertEqual(c["_binding_issues"], [])
            self.assertEqual(c["_worker_verified_instance"], "worker")
            self.assertEqual(c["_worker_owned_pid"], 42)
            self.assertNotIn("_fixture_owned_pid", c)
            ledger[3]["pid"] = 999; write_ledger()
            c, _ = checker.runtime_context(ex, raw)
            self.assertIn("owned_worker_capability_handshake_unverified", [i["code"] for i in c["_binding_issues"]])


if __name__ == "__main__":
    unittest.main()
