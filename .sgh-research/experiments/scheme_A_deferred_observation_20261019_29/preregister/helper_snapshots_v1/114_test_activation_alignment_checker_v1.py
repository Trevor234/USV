import copy
import json
from pathlib import Path
import unittest
import activation_alignment_audit_v1 as independent
import check_activation_alignment_v1 as check
import check_pair_wakeup_v1 as run_check
import cold_start_contract_v1 as strict
from test_pair_retry_checker_v1 import event

HERE = Path(__file__).resolve().parent


class ActivationChecker(unittest.TestCase):
    def setUp(self):
        self.c = json.loads((HERE / 'pair_wakeup_contract_v1.json').read_text())
        row = json.loads((HERE / 'observer/tests/data/parent_activation_prefixes_v1.json').read_text())['rows'][0]
        self.frames = row['frames']; self.target = row['target_sim_ns']
        self.a = dict(raw_snapshot=row['snapshot'], sample_ns=row['snapshot']['sample_ns'],
                      history_generation=row['history_generation'], frame_count=len(self.frames),
                      selected_frame=row['expected_selected_frame'], frames_scanned=0)
        _, self.a['frames_scanned'] = independent.select_frame(self.frames, self.a['raw_snapshot'], self.target, self.c, self.a['history_generation'])

    def test_actual_parent_prefix_selection_matches(self):
        self.assertTrue(check.selection_valid(self.a, self.frames, self.target, self.c)[0])

    def test_foreign_selected_origin_rejected(self):
        a = copy.deepcopy(self.a); a['selected_frame']['origin_sequence'] += 1
        self.assertFalse(check.selection_valid(a, self.frames, self.target, self.c)[0])

    def test_missing_frame_population_rejected(self):
        a = copy.deepcopy(self.a); a['frame_count'] -= 1
        self.assertFalse(check.selection_valid(a, self.frames, self.target, self.c)[0])

    def test_future_imu_for_every_frame_cannot_be_used(self):
        frames = copy.deepcopy(self.frames)
        for f in frames: f.update(r_from_imu=True, imu_sequence=1, imu_stamp_ns=self.target+1)
        selected, _ = independent.select_frame(frames, self.a['raw_snapshot'], self.target, self.c, self.a['history_generation'])
        self.assertIsNone(selected)

    def test_future_receive_cannot_be_used(self):
        frames = copy.deepcopy(self.frames)
        for f in frames: f['odom_receive_ns'] = self.a['sample_ns']+1
        selected, _ = independent.select_frame(frames, self.a['raw_snapshot'], self.target, self.c, self.a['history_generation'])
        self.assertIsNone(selected)

    def test_original_short_circuit_imu_operand_not_fabricated(self):
        raw = dict(version=dict(epoch=0), odom_sequence=1, imu_sequence=2)
        a = dict(raw_snapshot=raw, guard_snapshot=dict(raw, odom_sequence=2), input_change_gate_ran=True,
                 input_change_gate_unchanged=False, input_gate_reads=dict(input_version_equal=True, input_odom_equal=False, input_imu_equal=None))
        self.assertTrue(check.guard_reads_valid(a)); a['input_gate_reads']['input_imu_equal'] = True
        self.assertFalse(check.guard_reads_valid(a))

    def test_exact_contract_delta_only_declared_fields(self):
        old = json.loads((HERE.parent / 'authored_D1_owned_cold_start_20261018_v27/pair_wakeup_contract_v1.json').read_text())
        changed = {k for k in set(old) | set(self.c) if old.get(k) != self.c.get(k)}
        self.assertEqual(changed, {'diagnostic_contract_revision', 'activation_state_policy', 'activation_sensor_history_capacity', 'activation_validation_attempts'})
        self.assertEqual(strict.validate(self.c), self.c)

    def test_attempt_capacity_and_policy_types_and_values_rejected(self):
        for key, value in [('activation_state_policy','latest_only'), ('activation_sensor_history_capacity', True),
                           ('activation_sensor_history_capacity',32.0), ('activation_sensor_history_capacity',33),
                           ('activation_validation_attempts',3), ('activation_validation_attempts',2.0)]:
            c = copy.deepcopy(self.c); c[key] = value
            with self.assertRaises(ValueError): strict.validate(c)

    def initial(self):
        e = event(); e.update(trigger='profile', path_sequence=0, path_stamp_ns=-1000000001,
                             froze=False, phase_still_awaiting=True)
        source = dict(type='profile_version', received_sequence=e['profile_sequence'],
                      input_commit_ordinal=e['input_commit_ordinal'], processed_ns=e['started_ns']-1,
                      valid=True, resource_valid=True)
        return e, source

    def test_missing_opposite_startup_record_valid_only_with_actual_absence(self):
        e, source = self.initial(); self.assertTrue(run_check.retry_shape(e))
        c = run_check.c36.Checks(); run_check.reference_pair_retry_population([source,e],c)
        self.assertEqual(c.issues, [])

    def test_existing_opposite_cannot_be_falsely_zero(self):
        e, source = self.initial(); old = dict(type='path_version', received_sequence=1,
            input_commit_ordinal=e['input_commit_ordinal']-1, processed_ns=e['started_ns']-2, valid=True, resource_valid=True)
        c = run_check.c36.Checks(); run_check.reference_pair_retry_population([old,source,e],c)
        self.assertTrue(any(r['code']=='pair_retry_missing_opposite_actual_prefix' for r in c.issues))

    def test_missing_opposite_cannot_freeze(self):
        e, _ = self.initial(); e.update(froze=True, phase_still_awaiting=False)
        self.assertFalse(run_check.retry_shape(e))

    def test_trigger_cannot_be_zero_or_bad_missing_sentinel(self):
        e, _ = self.initial(); e['profile_sequence']=0; self.assertFalse(run_check.retry_shape(e))
        e, _ = self.initial(); e['path_stamp_ns']=0; self.assertFalse(run_check.retry_shape(e))


if __name__ == '__main__': unittest.main()
