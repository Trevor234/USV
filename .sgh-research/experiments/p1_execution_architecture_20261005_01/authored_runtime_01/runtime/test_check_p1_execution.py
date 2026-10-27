#!/usr/bin/env python3
"""Decoded fixtures test actual contract risks without ROS or simulated bag claims."""
import copy
import unittest
import check_p1_execution as checker


def fixture():
    digest = "a" * 64
    c = {"clock": "CLOCK_MONOTONIC", "N": 20, "dt": .2, "T_ns": 200000000,
         "deadline_ns": 150000000, "execute_qualified": False, "parameters_are_diagnostic_only": True,
         "nominal_hash": "b" * 64, "command_min_n": -25, "command_max_n": 25,
         "activation_tolerance": [.25, .25, .15, .3, .2, .15], "rho_n_s": 80,
         "publish_gap_ns": 240000000, "target_sim_slack_ns": 20000000}
    context = {"run_id": "run", "mode": "no_output", "boot_id": "boot", "contract_hash": digest,
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
    # Independent decoded sources are essential: mutations must not share lists
    # with the simulated storage message and accidentally conceal mismatches.
    return tuple(copy.deepcopy(v) for v in (reg, worker, bag, c, context, digest))


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


if __name__ == "__main__":
    unittest.main()
