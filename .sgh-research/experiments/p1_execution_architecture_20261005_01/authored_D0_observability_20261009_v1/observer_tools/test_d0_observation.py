"""Pure decoded D0 observation tests, including independent adverse contracts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import check_d0_observation as checker

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "resource_closure_20261006/p1_shadow_contract_v5.json"


def base_fixture():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    identity = {"run_id": "d0-pure-fixture", "boot_id": "fixture-boot", "contract_hash": "a" * 64}
    startup = {"type": "startup", "run_id": identity["run_id"], "boot": identity["boot_id"], "contract_hash": identity["contract_hash"], "mode": "no_output", "clock": "CLOCK_MONOTONIC", "physical_publisher_endpoints": 0}
    odom = {"type": "odom_admission", "sequence": 2, "valid": True, "pose_frame": contract["expected_pose_frame"], "pose_frame_truncated": False, "child_frame": contract["expected_child_frame"], "child_frame_truncated": False, "accepted_sequence": 2, "stamp_ns": 299000000, "receive_ns": 999000000, "state": [0.] * 6}
    clock = {"type": "clock", "sim_ns": 300000000, "receive_ns": 999999000, "epoch": 0, "schedule_generation": 1, "paused": False, "rtf": 1., "rtf_valid": True}
    job = dict(identity, schema="p1-solve-job-v1", nominal_hash=contract["nominal_hash"], worker_instance="worker-fixture", job_id=1, target_tick=5, task_generation=1, model_generation=1, config_generation=1, schedule_generation=1, clock_epoch=0, tick_origin_ns=800000000, freeze_ns=800001000, deadline_ns=950000000, target_ns=1000000000, target_sim_ns=300000000, odom_stamp_ns=100000000, imu_stamp_ns=0, odom_receive_ns=800000000, imu_receive_ns=0, odom_sequence=1, imu_sequence=0, r_from_imu=False, N=20, dt=.2, frozen_state=[0.] * 6, target_state=[0.] * 6, reference=[0.] * 126, anchor_n=[0., 0.], anchor_sequence=[1, 1], anchor_publish_ns=[800000000, 800000000], anchor_known=[True, True], reset_warmstart=False, frozen_clock_sim_ns=100000000, frozen_clock_receive_ns=800000000, assumed_rtf=1., anchor_source="synthetic_static_fixture", anchor_producer="producer-fixture", anchor_run_id=identity["run_id"], history_sim_ns=[], history_channel=[], history_n=[])
    oldodom = copy.deepcopy(odom)
    oldodom.update(sequence=1, accepted_sequence=1, stamp_ns=100000000, receive_ns=800000000)
    registration = {"type": "candidate_registration", "job": copy.deepcopy(job), "ready_commit_ns": 800004000, "accepted_registration": True, "reason": "", "solve_start_ns": 800002000, "solve_end_ns": 800003000, "worker_instance": job["worker_instance"], "first_control": [0., 0.]}
    version = {"task": 1, "model": 1, "config": 1, "schedule": 1, "epoch": 0}
    source = {"version": version, "odom_sequence": 2, "odom_stamp_ns": odom["stamp_ns"], "odom_receive_ns": odom["receive_ns"], "imu_sequence": 0, "imu_stamp_ns": 0, "imu_receive_ns": 0, "r_from_imu": False, "clock_sim_ns": clock["sim_ns"], "clock_receive_ns": clock["receive_ns"], "rtf": 1., "rtf_valid": True, "paused": False}
    validation = copy.deepcopy(source)
    validation.update(sample_ns=1000000000, copy_capture_ns=1000000010, capture_semantics="mutex_copy_end", state=[0.] * 6, anchor={"n": [0., 0.], "sequence": [1, 1], "publish_ns": [800000000, 800000000], "known": [True, True]}, history_count=0, held_history=[])
    final = copy.deepcopy(source)
    final["commit_ns"] = 1000000020
    observation = {"schema": checker.SCHEMA, "candidate_pair_available": True, "candidate_job_id": 1, "candidate_target_tick": 5, "prediction_target_sim_ns": job["target_sim_ns"], "predict_invoked": True, "predict_success": True, "predict_status": "success", "predicted_state_available": True, "predicted_state": [0.] * 6, "full_error_available": True, "full_error": [0.] * 6, "validation_snapshot": validation, "input_change_gate_ran": True, "input_change_gate_unchanged": True, "final_snapshot": final}
    decision = {k: 0 for k in checker.CANONICAL_KEYS}
    decision.update(type="decision", schema="p1-execution-decision-v2", **identity, worker_instance=job["worker_instance"], mode="no_output", sequence=1, tick=5, job_id=1, task_generation=1, model_generation=1, config_generation=1, schedule_generation=1, epoch=0, planned_ns=1000000000, start_ns=1000000000, cutoff_commit_ns=950000001, ready_commit_ns=800004000, activation_commit_ns=final["commit_ns"], end_ns=1000000030, accepted=True, diagnostic_only=True, reason="", control_source="candidate", target_state=[0.] * 6, activation_state=[0.] * 6, state_error=[0.] * 6, requested_n=[0., 0.], final_n=[0., 0.], previous_n=[0., 0.], previous_publish_ns=[800000000, 800000000], previous_anchor_known=[True, True], anchor_known=[True, True], anchor_sequence=[1, 1], activation_clock_sim_ns=final["clock_sim_ns"], activation_clock_receive_ns=final["clock_receive_ns"], activation_rtf=1., activation_odom_stamp_ns=final["odom_stamp_ns"], activation_odom_receive_ns=final["odom_receive_ns"], activation_odom_sequence=2, activation_imu_stamp_ns=0, activation_imu_receive_ns=0, activation_imu_sequence=0, activation_r_from_imu=False, odom_age_ns=final["commit_ns"] - final["odom_receive_ns"], imu_age_ns=0, clock_age_ns=final["commit_ns"] - final["clock_receive_ns"], normal_contract_complete=False, rho_available=False, plant_acceptance_observed=False, d0_observation=observation)
    for k in ["publish_start_ns", "publish_end_ns", "publish_sim_ns", "publish_epoch", "publish_clock_age_ns"]:
        decision[k] = [0, 0]
    decision["publish_success"] = [False, False]
    rows = [startup, oldodom, {"type": "job", "job": job}, registration, odom, clock, decision]
    close(rows)
    return rows, contract


def close(rows):
    if rows and rows[-1].get("type") == "source_summary":
        rows.pop()
    rows.append({"type": "source_summary", "generated": len(rows), "emitted": len(rows), "dropped": 0, "normal_source_complete": True, "finished_ns": 1000000100})


def decision(rows):
    return next(r for r in rows if r["type"] == "decision")


def obs(rows):
    return decision(rows)["d0_observation"]


def rejected(rows, reason="unknown_anchor", gate=False):
    d = decision(rows)
    d.update(accepted=False, reason=reason, control_source="ramp_zero")
    obs(rows)["input_change_gate_ran"] = gate
    obs(rows)["input_change_gate_unchanged"] = True if gate else None


class ObservationTests(unittest.TestCase):
    def assert_pass(self, rows, contract):
        report = checker.validate_events(rows, contract)
        self.assertTrue(report["passed"], report["issues"])
        self.assertFalse(report["execute_qualified"])
        self.assertFalse(report["dynamic_source_qualified"])
        self.assertFalse(report["nominal_propagation_independently_recomputed"])
        self.assertIsNone(report["close_flush_verified"])
        return report

    def bad(self, mutate):
        rows, contract = base_fixture()
        mutate(rows, contract)
        report = checker.validate_events(rows, contract)
        self.assertFalse(report["passed"], report)
        self.assertTrue(report["issues"])

    def test_accepted_finite_source_contract(self):
        rows, c = base_fixture()
        r = self.assert_pass(rows, c)
        self.assertEqual((r["accepted_registration_count"], r["paired_consumed_job_count"], r["full_error_sample_count"]), (1, 1, 1))

    def test_no_candidate_explicit_unavailable(self):
        rows, c = base_fixture()
        d, o = decision(rows), obs(rows)
        rejected(rows, "no_candidate")
        d.update(job_id=0, ready_commit_ns=0, cutoff_commit_ns=0)
        o.update(candidate_pair_available=False, candidate_job_id=None, candidate_target_tick=None, prediction_target_sim_ns=None, predict_invoked=False, predict_success=False, predict_status="not_attempted", predicted_state_available=False, predicted_state=None, full_error_available=False, full_error=None)
        r = self.assert_pass(rows, c)
        self.assertEqual(r["phase_counts"]["not_attempted"], 1)

    def test_failed_propagation_explicit_unavailable(self):
        rows, c = base_fixture()
        rejected(rows, "activation_history_or_time")
        obs(rows).update(predict_success=False, predict_status="history_or_time_failed", predicted_state_available=False, predicted_state=None, full_error_available=False, full_error=None)
        self.assert_pass(rows, c)

    def test_early_rejection_still_observes_full_error(self):
        rows, c = base_fixture()
        rejected(rows)
        decision(rows)["activation_state"] = [1., 2., .1, .5, .4, .2]
        obs(rows).update(predicted_state=list(decision(rows)["activation_state"]), full_error=list(decision(rows)["activation_state"]))
        decision(rows)["state_error"] = [1., 0., 0., 0., 0., 0.]
        self.assert_pass(rows, c)

    def test_heading_wrap_crosses_pi(self):
        rows, c = base_fixture()
        target = -checker.math.pi + .01
        pred = checker.math.pi - .01
        rows[2]["job"]["target_state"][2] = target
        rows[3]["job"]["target_state"][2] = target
        decision(rows)["target_state"][2] = target
        decision(rows)["activation_state"][2] = pred
        obs(rows)["predicted_state"][2] = pred
        obs(rows)["full_error"][2] = -.02
        self.assert_pass(rows, c)

    def test_raw_inactive_imu_preserved_and_canonical_masked(self):
        rows, c = base_fixture()
        rows.insert(2, {"type": "imu_admission", "sequence": 1, "accepted_sequence": 1, "valid": True, "frame_id": c["expected_imu_frame"], "frame_truncated": False, "r_value": .1, "stamp_ns": 90000000, "receive_ns": 790000000})
        for s in [obs(rows)["validation_snapshot"], obs(rows)["final_snapshot"]]:
            s.update(imu_sequence=1, imu_stamp_ns=90000000, imu_receive_ns=790000000)
        close(rows)
        self.assert_pass(rows, c)

    def test_mixed_imu_provenance(self):
        rows, c = base_fixture()
        rows.insert(-1, {"type": "imu_admission", "sequence": 1, "accepted_sequence": 1, "valid": True, "frame_id": c["expected_imu_frame"], "frame_truncated": False, "r_value": .05, "stamp_ns": 299000000, "receive_ns": 999000000})
        for s in [obs(rows)["validation_snapshot"], obs(rows)["final_snapshot"]]:
            s.update(imu_sequence=1, imu_stamp_ns=299000000, imu_receive_ns=999000000, r_from_imu=True)
        obs(rows)["validation_snapshot"]["state"][5] = .05
        decision(rows).update(activation_r_from_imu=True, activation_imu_sequence=1, activation_imu_stamp_ns=299000000, activation_imu_receive_ns=999000000, imu_age_ns=1000020)
        close(rows)
        self.assert_pass(rows, c)

    def test_input_changed_gate_uses_raw_imu_even_when_inactive(self):
        rows, c = base_fixture()
        rows.insert(-1, {"type": "imu_admission", "sequence": 1, "accepted_sequence": 1, "valid": True, "frame_id": c["expected_imu_frame"], "frame_truncated": False, "r_value": .1, "stamp_ns": 299000000, "receive_ns": 1000000015})
        rejected(rows, "activation_input_changed_during_validation", True)
        obs(rows)["input_change_gate_unchanged"] = False
        obs(rows)["final_snapshot"].update(imu_sequence=1, imu_stamp_ns=299000000, imu_receive_ns=1000000015)
        close(rows)
        self.assert_pass(rows, c)

    def test_rejected_foreign_registration_is_not_used(self):
        rows, c = base_fixture()
        foreign = copy.deepcopy(rows[3])
        foreign.update(accepted_registration=False, reason="foreign_worker")
        foreign["job"].update(job_id=99, run_id="foreign-run")
        rows.insert(-1, foreign)
        close(rows)
        r = self.assert_pass(rows, c)
        self.assertEqual(r["rejected_registration_count"], 1)

    def test_missing_sources_legitimate_no_pair(self):
        rows, c = base_fixture()
        d, o = decision(rows), obs(rows)
        rejected(rows, "no_odom")
        d.update(job_id=0, ready_commit_ns=0, cutoff_commit_ns=0)
        o.update(candidate_pair_available=False, candidate_job_id=None, candidate_target_tick=None, prediction_target_sim_ns=None, predict_invoked=False, predict_success=False, predict_status="not_attempted", predicted_state_available=False, predicted_state=None, full_error_available=False, full_error=None)
        for s in [o["validation_snapshot"], o["final_snapshot"]]:
            for key in ["odom_sequence", "odom_stamp_ns", "odom_receive_ns", "clock_sim_ns", "clock_receive_ns"]:
                s[key] = 0
            s.update(rtf=0., rtf_valid=False)
        d.update(activation_odom_sequence=0, activation_odom_stamp_ns=0, activation_odom_receive_ns=0, activation_clock_sim_ns=0, activation_clock_receive_ns=0, activation_rtf=0., odom_age_ns=d["activation_commit_ns"], clock_age_ns=d["activation_commit_ns"])
        self.assert_pass(rows, c)

    def test_history_finite_ordered_exact_count(self):
        rows, c = base_fixture()
        v = obs(rows)["validation_snapshot"]
        v.update(history_count=2, held_history=[{"sim_ns": 100000000, "channel": 0, "value": 1.}, {"sim_ns": 100000000, "channel": 1, "value": 2.}])
        self.assert_pass(rows, c)

    def test_same_fixture_canonical_projection_is_exact(self):
        rows, c = base_fixture()
        expected = copy.deepcopy(rows)
        expected[6].pop("d0_observation")
        self.assertTrue(checker.compare_canonical_decisions(rows, expected))
        expected[6]["reason"] = "changed"
        self.assertFalse(checker.compare_canonical_decisions(rows, expected))

    def test_json_rejects_duplicate_keys(self):
        with self.assertRaises(checker.Invalid):
            checker.strict_loads('{"type":"decision","type":"job"}')

    def test_json_rejects_nan_literal(self):
        with self.assertRaises(checker.Invalid):
            checker.strict_loads('{"value":NaN}')

    def test_json_rejects_truncated_line(self):
        with self.assertRaises(ValueError):
            checker.strict_loads('{"type":')

    def test_cli_create_only_real_hash_and_footprint(self):
        rows, contract = base_fixture()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            contract_path = root / 'contract.json'
            source = root / 'regulator.jsonl'
            report_path = root / 'report.json'
            contract_path.write_text(json.dumps(contract), encoding='utf-8')
            actual = hashlib.sha256(contract_path.read_bytes()).hexdigest()
            for event in rows:
                if event['type'] == 'startup':
                    event['contract_hash'] = actual
                if event['type'] == 'decision':
                    event['contract_hash'] = actual
                if event['type'] in ['job', 'candidate_registration']:
                    event['job']['contract_hash'] = actual
            source.write_text('\n'.join(json.dumps(e) for e in rows) + '\n', encoding='utf-8')
            before = source.read_bytes()
            self.assertEqual(checker.main(['--source', str(source), '--contract', str(contract_path), '--output', str(report_path)]), 0)
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(report['source_footprint']['source_file_bytes'], len(before))
            self.assertEqual(report['source_footprint']['decision_row_byte_samples'], 1)
            self.assertFalse(report['source_footprint']['hard_byte_bound_certified'])
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaises(checker.Invalid):
                checker.main(['--source', str(source), '--contract', str(contract_path), '--output', str(report_path)])


NEGATIVES = {
    'fake_zero_unavailable': lambda r,c: obs(r).update(predicted_state_available=False, predicted_state=[0.] * 6),
    'failed_predict_fabricated_available': lambda r,c: obs(r).update(predict_success=False, predict_status='history_or_time_failed'),
    'wrong_wrapped_error': lambda r,c: obs(r)['full_error'].__setitem__(2, 6.28),
    'bad_error_shape': lambda r,c: obs(r).update(full_error=[0.] * 5),
    'nonfinite_error': lambda r,c: obs(r)['full_error'].__setitem__(0, float('inf')),
    'hidden_finite_success': lambda r,c: obs(r).update(predicted_state_available=False, predicted_state=None, full_error_available=False, full_error=None),
    'changed_candidate_target': lambda r,c: obs(r).update(candidate_target_tick=6),
    'wrong_prediction_sim_target': lambda r,c: obs(r).update(prediction_target_sim_ns=300000001),
    'unknown_candidate_job': lambda r,c: obs(r).update(candidate_job_id=999),
    'foreign_source_job': lambda r,c: r[2]['job'].update(run_id='foreign'),
    'candidate_echo_drift': lambda r,c: r[3]['job']['reference'].__setitem__(125, 1.),
    'wrong_registration_ready_time': lambda r,c: decision(r).update(ready_commit_ns=800004001),
    'late_accepted_registration': lambda r,c: r[3].update(ready_commit_ns=950000001),
    'missing_accepted_registration': lambda r,c: (r.pop(3), close(r)),
    'duplicate_accepted_registration': lambda r,c: (r.insert(4, copy.deepcopy(r[3])), close(r)),
    'misreported_raw_gate': lambda r,c: obs(r).update(input_change_gate_unchanged=False),
    'accepted_skipped_gate': lambda r,c: obs(r).update(input_change_gate_ran=False, input_change_gate_unchanged=None),
    'skipped_gate_has_false_result': lambda r,c: (rejected(r), obs(r).update(input_change_gate_unchanged=False)),
    'bool_copy_time': lambda r,c: obs(r)['validation_snapshot'].update(copy_capture_ns=True),
    'copy_before_sample': lambda r,c: obs(r)['validation_snapshot'].update(copy_capture_ns=999999999),
    'copy_after_commit': lambda r,c: obs(r)['validation_snapshot'].update(copy_capture_ns=1000000021),
    'raw_state_source_mismatch': lambda r,c: obs(r)['validation_snapshot']['state'].__setitem__(3, .5),
    'final_source_substitution': lambda r,c: obs(r)['final_snapshot'].update(odom_sequence=1),
    'clock_rtf_fabrication': lambda r,c: obs(r)['validation_snapshot'].update(rtf=1.01),
    'inactive_imu_not_canonical_masked': lambda r,c: decision(r).update(activation_imu_sequence=1),
    'history_count_mismatch': lambda r,c: obs(r)['validation_snapshot'].update(history_count=1),
    'history_channel_invalid': lambda r,c: obs(r)['validation_snapshot'].update(history_count=1, held_history=[{'sim_ns': 1, 'channel': 2, 'value': 0.}]),
    'history_capacity_overflow': lambda r,c: obs(r)['validation_snapshot'].update(history_count=c['history_capacity']+1, held_history=[{'sim_ns': 1, 'channel': 0, 'value': 0.}]*(c['history_capacity']+1)),
    'history_out_of_order': lambda r,c: obs(r)['validation_snapshot'].update(history_count=2, held_history=[{'sim_ns': 2, 'channel': 0, 'value': 0.}, {'sim_ns': 1, 'channel': 1, 'value': 0.}]),
    'decision_sequence_gap': lambda r,c: decision(r).update(sequence=2),
    'physical_publish_claim': lambda r,c: decision(r).update(publish_success=[True, False]),
    'execute_qualification_claim': lambda r,c: decision(r).update(normal_contract_complete=True),
    'extra_canonical_key': lambda r,c: decision(r).update(bogus_new_key=1),
    'missing_observation': lambda r,c: decision(r).pop('d0_observation'),
    'wrong_observation_schema': lambda r,c: obs(r).update(schema='other'),
    'footer_dropped': lambda r,c: r[-1].update(dropped=1),
    'footer_generated_drift': lambda r,c: r[-1].update(generated=99),
    'footer_normal_false': lambda r,c: r[-1].update(normal_source_complete=False),
    'footer_not_terminal': lambda r,c: r.append({'type': 'late_extra'}),
    'wrong_revision': lambda r,c: c.update(diagnostic_contract_revision=4),
    'foreign_startup_clock': lambda r,c: r[0].update(clock='different'),
    'accepted_future_or_stale_clock': lambda r,c: c.update(clock_age_ns=100),
    'accepted_source_receive_age': lambda r,c: c.update(odom_age_ns=100),
    'accepted_source_sim_lag': lambda r,c: c.update(odom_sim_lag_ns=100),
    'accepted_state_tolerance': lambda r,c: (decision(r)['activation_state'].__setitem__(0, .3), obs(r)['predicted_state'].__setitem__(0, .3), obs(r)['full_error'].__setitem__(0, .3)),
}


def install_negative(name, mutate):
    def test(self):
        self.bad(mutate)
    test.__name__ = 'test_reject_' + name
    setattr(ObservationTests, test.__name__, test)


for _name, _mutate in NEGATIVES.items():
    install_negative(_name, _mutate)

if __name__ == '__main__':
    unittest.main(verbosity=2)
