"""Full finite evidence and coherent budget/state counterexamples; originals read only."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import budget_scope_v1 as b


PREREG = Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/budget_scope/preregister_v2.json")


class BudgetScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.contract, runs = b.load_manifest(PREREG)
        cls.runs = {x["inputs.json"]["mode"]: x for x in runs}
        cls.original_sha = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                            for p in cls.manifest["files"]}

    @classmethod
    def tearDownClass(cls):
        after = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                 for p in cls.manifest["files"]}
        assert cls.original_sha == after, "test mutated a historical pinned input"

    def positive(self):
        return copy.deepcopy(self.runs["positive"])

    def analyze(self, data=None):
        return b.analyze_data(self.positive() if data is None else data, self.contract)

    def test_original_positive_full_join(self):
        r = self.analyze()
        self.assertEqual(r["component_status"], "passed")
        self.assertEqual(len(r["jobs"]), 23)
        self.assertEqual(r["decisions"]["count"], 47)
        self.assertEqual(r["decisions"]["anchor_mismatch_count"], 21)

    def test_original_expired_preserves_unknown_not_zero(self):
        r = self.analyze(self.runs["expired_release"])
        self.assertEqual(r["publisher_gate_last_original_windows"]["arm"], None)
        self.assertEqual(r["publisher_gate_last_original_windows"]["receipt"], None)
        self.assertEqual(r["native_worker_windows"]["worker_native_solve"]["count"], 0)
        self.assertEqual(r["native_worker_windows"]["worker_native_solve"]["max_ns"], None)
        self.assertEqual(r["dependencies"]["candidate_ready_observed"]["status"], "not_run")

    def test_original_ambiguous_preparation_has_no_release_call(self):
        r = self.analyze(self.runs["prepare_io_ambiguous"])
        self.assertEqual(r["release_create_only_windows"], [])
        self.assertIsNone(r["release_lifetime_observed_ns"])
        self.assertTrue(r["publisher_gate_last_observation"]["release_read_completed"])
        self.assertFalse(r["publisher_gate_last_observation"]["release_present_at_last_completed_read"])
        self.assertEqual(r["publisher_gate_last_observation"]["original_freshness_read_count"], 0)

    def test_real_tail_acceptance_is_diagnostic(self):
        accepted = self.analyze()["decisions"]["accepted_shadow"]
        self.assertEqual(len(accepted), 1)
        self.assertTrue(accepted[0]["publisher_tail"])
        self.assertFalse(accepted[0]["actual_regulator_publish"])
        self.assertIsNone(accepted[0]["plant_acceptance"])
        self.assertGreater(accepted[0]["requested_n"][0], 7)

    def test_clock_and_plant_hard_bounds_unknown(self):
        r = self.analyze()
        self.assertIsNone(r["master_clock_hard_bound_ns"])
        self.assertIsNone(r["plant_hold_interval_ns"])
        self.assertEqual(r["dependencies"]["master_clock_hard_bound"]["status"], "unknown")
        self.assertEqual(r["dependencies"]["plant_receive_and_hold"]["status"], "unknown")

    def test_original_finite_maximum_is_not_wcet(self):
        r = self.analyze()
        self.assertGreater(r["native_worker_windows"]["worker_native_solve"]["max_ns"], 0)
        self.assertIsNone(r["native_worker_windows"]["worker_native_solve"]["wcet_ns"])
        self.assertFalse(r["wcet_proven"])

    def test_stage_dependencies_do_not_promote(self):
        r = self.analyze()
        self.assertTrue(all(v is False for v in r["stage_flags"].values()))
        self.assertTrue(all(v["qualified"] is False for v in r["stage_budget_dependency_matrix"].values()))
        self.assertNotEqual(r["stage_budget_dependency_matrix"]["M0b"]["status"], "passed")

    def test_dynamic20s_predeclaration_is_not_run(self):
        r = self.analyze()
        self.assertEqual(r["current_dynamic_recipe"]["measurement_ns"], 20_000_000_000)
        self.assertEqual(r["current_dynamic_recipe"]["status"], "not_run")
        self.assertFalse(r["current_dynamic_recipe"]["stage_qualified"])

    def test_coherent_source_time_bool_rejected(self):
        d = self.positive()
        d["result.json"]["close_elapsed_ns"] = True
        with self.assertRaisesRegex(b.BudgetScopeError, "exact bounded int64"):
            self.analyze(d)

    def test_original_window_reversal_rejected(self):
        d = self.positive()
        gate = d["publisher/release_observation.json"]["gate"]
        gate["receipt_io_end_steady_ns"] = gate["receipt_io_start_steady_ns"] - 1
        with self.assertRaisesRegex(b.BudgetScopeError, "reversed original"):
            self.analyze(d)

    def test_coherent_immutable_job_change_rejected(self):
        d = self.positive()
        job = next(r for r in d["worker/source.jsonl"] if r["type"] == "job_received")["job"]
        job["anchor_sequence"] = [2, 2]
        with self.assertRaisesRegex(b.BudgetScopeError, "complete immutable job"):
            self.analyze(d)

    def test_native_candidate_time_change_rejected(self):
        d = self.positive()
        cand = next(r for r in d["worker/source.jsonl"] if r["type"] == "candidate")
        cand["solve_end_ns"] += 1
        with self.assertRaisesRegex(b.BudgetScopeError, "native solve timestamps"):
            self.analyze(d)

    def test_coherent_moving_anchor_acceptance_rejected(self):
        d = self.positive()
        a = next(r for r in d["observer/source.jsonl"] if r["type"] == "anchor_validation")
        dec = next(r for r in d["observer/source.jsonl"] if r["type"] == "decision" and r["sequence"] == a["sequence"])
        act = next(r for r in d["observer/witness.json"]["activation"] if r["job_id"] == a["job_id"])
        dec["accepted"] = a["accepted"] = act["accepted"] = True
        dec["reason"] = a["decision_reason"] = a["history_reason"] = ""
        act["reason_code"] = 0
        with self.assertRaisesRegex(b.BudgetScopeError, "independent complete anchor history|changed anchor incorrectly accepted"):
            self.analyze(d)

    def test_history_constant_command_identity_advance_is_valid(self):
        expected = {"known": [True, True], "n": [4.0, 5.0], "sequence": [1, 1], "publish_ns": [10, 11]}
        actual = {"known": [True, True], "n": [4.0, 5.0], "sequence": [3, 3], "publish_ns": [30, 31]}
        entries = [{"channel": c, "sequence": s, "publish_ns": 10 * s + c,
                    "n": expected["n"][c], "known": True} for s in (1, 2, 3) for c in (0, 1)]
        self.assertEqual(b.replay_anchor_history(expected, actual, entries), "")

    def test_coherent_history_change_then_return_is_rejected(self):
        expected = {"known": [True, True], "n": [4.0, 5.0], "sequence": [1, 1], "publish_ns": [10, 11]}
        actual = {"known": [True, True], "n": [4.0, 5.0], "sequence": [3, 3], "publish_ns": [30, 31]}
        entries = [{"channel": c, "sequence": s, "publish_ns": 10 * s + c,
                    "n": 6.0 if s == 2 and c == 0 else expected["n"][c], "known": True}
                   for s in (1, 2, 3) for c in (0, 1)]
        self.assertEqual(b.replay_anchor_history(expected, actual, entries), "anchor_history_changed")

    def test_endpoint_equality_with_sequence_gap_is_rejected(self):
        expected = {"known": [True, True], "n": [4.0, 5.0], "sequence": [1, 1], "publish_ns": [10, 11]}
        actual = {"known": [True, True], "n": [4.0, 5.0], "sequence": [3, 3], "publish_ns": [30, 31]}
        entries = [{"channel": c, "sequence": s, "publish_ns": 10 * s + c,
                    "n": expected["n"][c], "known": True} for s in (1, 3) for c in (0, 1)]
        self.assertEqual(b.replay_anchor_history(expected, actual, entries), "anchor_history_incomplete")

    def test_coherent_late_ready_classified_failed(self):
        d = self.positive()
        reg = next(r for r in d["observer/source.jsonl"] if r["type"] == "candidate_registration")
        late = reg["job"]["deadline_ns"] + 1
        reg["ready_commit_ns"] = late
        for r in d["observer/source.jsonl"]:
            if r["type"] == "decision" and r["job_id"] == reg["job"]["job_id"]:
                r["ready_commit_ns"] = late
        for r in d["observer/witness.json"]["activation"]:
            if r["job_id"] == reg["job"]["job_id"]:
                r["ready_commit_ns"] = late
        r = self.analyze(d)
        self.assertEqual(r["dependencies"]["candidate_ready_observed"]["status"], "failed")
        self.assertLess(r["ready_slack_ns"]["min"], 0)
        with self.assertRaisesRegex(b.BudgetScopeError, "independent derivation"):
            b.verify_report(self.analyze(), d, self.contract)

    def test_coherent_shadow_physical_publish_claim_rejected(self):
        d = self.positive()
        dec = next(r for r in d["observer/source.jsonl"] if r["type"] == "decision" and r["accepted"])
        dec["publish_success"] = [True, True]
        with self.assertRaisesRegex(b.BudgetScopeError, "actual regulator publish"):
            self.analyze(d)

    def test_report_wcets_cannot_be_promoted(self):
        d = self.positive()
        r = self.analyze(d)
        r["wcet_proven"] = True
        r["native_worker_windows"]["worker_native_solve"]["wcet_ns"] = r["native_worker_windows"]["worker_native_solve"]["max_ns"]
        with self.assertRaisesRegex(b.BudgetScopeError, "independent derivation"):
            b.verify_report(r, d, self.contract)

    def test_report_unknown_cannot_be_zero_and_passed(self):
        d = self.positive()
        r = self.analyze(d)
        r["master_clock_hard_bound_ns"] = 0
        r["dependencies"]["master_clock_hard_bound"]["status"] = "passed"
        with self.assertRaisesRegex(b.BudgetScopeError, "independent derivation"):
            b.verify_report(r, d, self.contract)

    def test_report_stage_flags_cannot_be_promoted(self):
        d = self.positive()
        r = self.analyze(d)
        r["stage_flags"]["execute"] = True
        with self.assertRaisesRegex(b.BudgetScopeError, "independent derivation"):
            b.verify_report(r, d, self.contract)

    def test_report_dynamic20s_claim_rejected(self):
        d = self.positive()
        r = self.analyze(d)
        r["current_dynamic_recipe"]["status"] = "passed"
        r["current_dynamic_recipe"]["stage_qualified"] = True
        with self.assertRaisesRegex(b.BudgetScopeError, "independent derivation"):
            b.verify_report(r, d, self.contract)

    def test_plant_hold_claim_has_no_observation(self):
        d = self.positive()
        one = next(r for r in d["observer/source.jsonl"] if r["type"] == "regulator_shutdown")
        one["plant_hold_end_known"] = True
        with self.assertRaisesRegex(b.BudgetScopeError, "actual plant held interval"):
            self.analyze(d)

    def test_zero_no_call_fields_cannot_prove_publish_budget(self):
        r = self.analyze()
        self.assertEqual(r["dependencies"]["dual_publish_budget_rho_gap"]["status"], "not_run")
        self.assertIsNone(r["dependencies"]["dual_publish_budget_rho_gap"]["observed"])

    def test_report_omitting_close_tail_rejected(self):
        d = self.positive()
        d["result.json"]["close_elapsed_ns"] = 1
        with self.assertRaisesRegex(b.BudgetScopeError, "close omits finite"):
            self.analyze(d)

    def test_coherent_close_budget_overflow_classified_failed(self):
        d = self.positive()
        d["result.json"]["close_elapsed_ns"] = b.POLICY["close_ns"] + 1
        r = self.analyze(d)
        self.assertEqual(r["dependencies"]["close_observed"]["status"], "failed")
        with self.assertRaisesRegex(b.BudgetScopeError, "independent derivation"):
            b.verify_report(self.analyze(), d, self.contract)

    def test_policy_bool_substitution_rejected(self):
        policy = copy.deepcopy(b.POLICY)
        policy["normal_worker_hooks"] = [False, False]
        with self.assertRaisesRegex(b.BudgetScopeError, "policy differs"):
            b.analyze_data(self.positive(), self.contract, policy)

    def test_policy_ready_relaxation_rejected(self):
        policy = copy.deepcopy(b.POLICY)
        policy["ready_ns"] += 1
        with self.assertRaisesRegex(b.BudgetScopeError, "policy differs"):
            b.analyze_data(self.positive(), self.contract, policy)

    def test_cross_boot_window_rejected(self):
        d = self.positive()
        d["owned_process_ledger.jsonl"][-1]["boot_id"] = "different boot"
        with self.assertRaisesRegex(b.BudgetScopeError, "crosses boot"):
            self.analyze(d)

    def test_actual_anchor_source_join_rejected(self):
        d = self.positive()
        a = next(r for r in d["observer/source.jsonl"] if r["type"] == "anchor_validation")
        a["actual_n"][0] += 1
        with self.assertRaisesRegex(b.BudgetScopeError, "original Applied Source"):
            self.analyze(d)

    def test_anchor_boolean_identity_rejected(self):
        d = self.positive()
        a = next(r for r in d["observer/source.jsonl"] if r["type"] == "anchor_validation")
        a["expected_sequence"][0] = True
        with self.assertRaisesRegex(b.BudgetScopeError, "exact bounded int64"):
            self.analyze(d)

    def test_no_foreign_module_or_pinned_file_mutation(self):
        matrix = b.analyze_manifest(PREREG)
        self.assertIs(matrix["passed"], True)
        self.assertEqual(matrix["input_sha256_before"], matrix["input_sha256_after"])
        self.assertEqual(matrix["input_count"], 47)
        self.assertTrue(all(v is False for v in matrix["qualifications"].values()))

    def test_fd_reader_rejects_symlink_and_bytes_change(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.json"
            p.write_bytes(b"{}")
            pin = {"bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()}
            self.assertEqual(b.locked_bytes(p, pin), b"{}")
            q = p.with_name("link.json")
            q.symlink_to(p)
            with self.assertRaises(OSError):
                b.locked_bytes(q, pin)
            p.write_bytes(b"[]")
            with self.assertRaisesRegex(b.BudgetScopeError, "pin mismatch"):
                b.locked_bytes(p, pin)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(b.BudgetScopeError, "duplicate JSON key"):
            b.strict_json('{"ready_ns":1,"ready_ns":2}')

    def test_overflow_nonfinite_rejected(self):
        with self.assertRaisesRegex(b.BudgetScopeError, "finite numeric"):
            b.strict_json('{"bound":1e309}')


if __name__ == "__main__":
    unittest.main()
