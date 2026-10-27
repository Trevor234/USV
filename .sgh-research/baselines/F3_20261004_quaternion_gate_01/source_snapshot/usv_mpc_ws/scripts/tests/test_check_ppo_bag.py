"""Independent data-contract tests for the read-only PPO bag checker.

These fixtures represent decoded bag records, so the tests do not require ROS.
The real-bag reader is separately exercised on the Ubuntu ROS installation.
"""

import copy
import contextlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_ppo_bag as checker


TOPICS = {
    "left": "/wamv/thrusters/left/thrust",
    "right": "/wamv/thrusters/right/thrust",
    "status": "/mpc/status",
    "odom": "/wamv/sensors/position/ground_truth_odometry",
    "imu": "/wamv/sensors/imu/imu/data",
    "path": "/path/reference",
    "reference_profile": "/path/reference_profile",
    "clock": "/clock",
}
TYPES = {
    TOPICS["left"]: "std_msgs/msg/Float64",
    TOPICS["right"]: "std_msgs/msg/Float64",
    TOPICS["status"]: "std_msgs/msg/String",
    TOPICS["odom"]: "nav_msgs/msg/Odometry",
    TOPICS["imu"]: "sensor_msgs/msg/Imu",
    TOPICS["path"]: "nav_msgs/msg/Path",
    TOPICS["reference_profile"]: "std_msgs/msg/Float64MultiArray",
    TOPICS["clock"]: "rosgraph_msgs/msg/Clock",
}
NS = 1_000_000_000


def stamp(ns):
    return {"sec": ns // NS, "nanosec": ns % NS}


def record(key, bag_ns, payload):
    return checker.Record(TOPICS[key], bag_ns, payload)


def status_payload(left=3.0, right=4.0, state="ACTIVE", **overrides):
    value = {
        "state": state,
        "control_mode": "rl",
        "backend": "onnx_ppo",
        "actuation_anchor_source": "vrx_published",
        "dynamic_dt": 0.2,
        "tl_cmd_n": left,
        "tr_cmd_n": right,
        "tl_n": left,
        "tr_n": right,
    }
    if state == "STANDBY":
        value["standby_reason"] = "no_path"
    value.update(overrides)
    return {"data": json.dumps(value)}


def complete_records(n=5, left=3.0, right=4.0, state="ACTIVE"):
    """0.2 s control ticks with independent left/right/status arrivals."""
    records = []
    for index in range(n):
        start = NS + index * 200_000_000
        records.extend([
            record("left", start + 1_000_000, {"data": left}),
            record("right", start + 2_000_000, {"data": right}),
            record("status", start + 3_000_000,
                   status_payload(left, right, state)),
        ])
    end = NS + n * 200_000_000
    for bag_ns in range(NS, end + 10_000_000, 10_000_000):
        records.append(record("clock", bag_ns,
                              {"clock": stamp(10 * NS + bag_ns - NS)}))
    for bag_ns in (900_000_000, end + 100_000_000):
        records.append(record("odom", bag_ns,
                              {"header": {"stamp": stamp(10 * NS + bag_ns - NS)}}))
    records.extend([
        record("imu", NS, {"header": {"stamp": stamp(10 * NS)}}),
        record("path", NS, {"header": {"stamp": stamp(10 * NS)}, "poses": []}),
        record("reference_profile", NS, {"data": [0.0, 0.8, 0.0]}),
    ])
    return sorted(records, key=lambda item: item.bag_ns)


def replace_payload(records, key, occurrence, payload):
    result, count = [], 0
    for item in records:
        if item.topic == TOPICS[key]:
            if count == occurrence:
                item = checker.Record(item.topic, item.bag_ns, payload)
            count += 1
        result.append(item)
    return result


def remove_occurrence(records, key, occurrence):
    result, count = [], 0
    for item in records:
        if item.topic == TOPICS[key]:
            if count == occurrence:
                count += 1
                continue
            count += 1
        result.append(item)
    return result


def without_topic(records, key):
    return [item for item in records if item.topic != TOPICS[key]]


class PpoBagContractTests(unittest.TestCase):
    def check(self, records=None, topic_types=None, **config):
        return checker.validate_records(
            complete_records() if records is None else records,
            TYPES if topic_types is None else topic_types,
            checker.Config(**config),
        )

    def assertFails(self, records=None, topic_types=None, **config):
        report = self.check(records, topic_types, **config)
        self.assertFalse(report["passed"], report)
        self.assertTrue(report["failures"], report)
        return report

    def test_complete_stream_passes_without_predictive_trajectory(self):
        report = self.check()
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["recorded_action_stream_consistent"])
        self.assertTrue(report["simulation_clock_recorded"])
        self.assertFalse(report["common_drop_identifiable"])
        self.assertFalse(report["exact_execution_timing_available"])
        self.assertFalse(report["gp_labels_ready"])

    def test_validation_leaves_input_records_and_metadata_unchanged(self):
        records, types = complete_records(), copy.deepcopy(TYPES)
        old_payloads = [(x.topic, x.bag_ns, copy.deepcopy(x.payload)) for x in records]
        self.assertTrue(self.check(records, types)["passed"])
        self.assertEqual(old_payloads, [(x.topic, x.bag_ns, x.payload) for x in records])
        self.assertEqual(types, TYPES)

    def test_legacy_without_clock_passes_with_timing_limitation(self):
        records = without_topic(complete_records(), "clock")
        types = {key: value for key, value in TYPES.items() if key != TOPICS["clock"]}
        report = self.check(records, types, profile="legacy-actions")
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["simulation_clock_recorded"])
        self.assertTrue(report["warnings"], report)
        self.assertFalse(report["gp_labels_ready"])

    def test_strict_without_clock_fails(self):
        self.assertFails(without_topic(complete_records(), "clock"))

    def test_missing_left_right_or_status_fails_even_if_metadata_lists_topic(self):
        for key in ("left", "right", "status"):
            with self.subTest(key=key):
                self.assertFails(without_topic(complete_records(), key))

    def test_missing_required_observation_reference_topics_fails(self):
        for key in ("odom", "imu", "path", "reference_profile"):
            with self.subTest(key=key):
                self.assertFails(without_topic(complete_records(), key))

    def test_single_internal_drop_is_not_hidden_by_constant_values(self):
        for key in ("left", "right", "status"):
            with self.subTest(key=key):
                self.assertFails(remove_occurrence(complete_records(), key, 2))

    def test_shared_drop_with_visible_simulation_gap_fails_strict(self):
        records = complete_records()
        for key in ("left", "right", "status"):
            records = remove_occurrence(records, key, 2)
        self.assertFails(records)

    def test_shared_drop_without_clock_is_not_claimed_identifiable(self):
        records = complete_records()
        for key in ("left", "right", "status"):
            records = remove_occurrence(records, key, 2)
        report = self.check(without_topic(records, "clock"), profile="legacy-actions")
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["recorded_action_stream_consistent"])
        self.assertFalse(report["common_drop_identifiable"])
        self.assertFalse(report["exact_execution_timing_available"])

    def test_duplicate_constant_command_reports_ambiguity(self):
        records = complete_records()
        records.append(record("left", NS + 5_000_000, {"data": 3.0}))
        report = self.assertFails(sorted(records, key=lambda item: item.bag_ns))
        self.assertTrue(any("ambig" in failure["code"] for failure in report["failures"]), report)

    def test_temporal_pair_is_checked_before_matching_equal_value_elsewhere(self):
        records = complete_records(n=2)
        records = replace_payload(records, "left", 0, {"data": 9.0})
        records = replace_payload(records, "left", 1, {"data": 3.0})
        self.assertFails(records)

    def test_numerical_mismatch_fails(self):
        self.assertFails(replace_payload(complete_records(), "right", 2, {"data": 4.25}))

    def test_numerical_tolerance_is_configurable(self):
        records = replace_payload(complete_records(), "left", 2, {"data": 3.00002})
        self.assertFails(records)
        self.assertTrue(self.check(records, tolerance_n=0.00003)["passed"])

    def test_near_window_edge_passes_and_exact_edge_fails(self):
        for offset_ns, expected in ((19_999_999, True), (20_000_000, False)):
            records = [checker.Record(x.topic, x.bag_ns + 2_000_000 - offset_ns, x.payload)
                       if x.topic == TOPICS["left"] else x for x in complete_records()]
            report = self.check(sorted(records, key=lambda item: item.bag_ns))
            self.assertEqual(report["passed"], expected, report)

    def test_epoch_scale_receive_timestamps_preserve_nanosecond_window_boundary(self):
        epoch_offset_ns = 1_700_000_000_000_000_000
        for offset_ns, expected in ((19_999_999, True), (20_000_000, False)):
            with self.subTest(offset_ns=offset_ns):
                records = [checker.Record(x.topic,
                                          epoch_offset_ns + x.bag_ns +
                                          (2_000_000 - offset_ns if x.topic == TOPICS["left"] else 0),
                                          x.payload)
                           for x in complete_records()]
                report = self.check(sorted(records, key=lambda item: item.bag_ns))
                self.assertEqual(report["passed"], expected, report)

    def test_unmatched_beginning_and_ending_records_are_not_discarded(self):
        for occurrence in (0, 4):
            with self.subTest(occurrence=occurrence):
                self.assertFails(remove_occurrence(complete_records(), "right", occurrence))

    def test_extra_command_outside_status_window_fails(self):
        records = complete_records()
        records.append(record("left", 500_000_000, {"data": 0.0}))
        self.assertFails(sorted(records, key=lambda item: item.bag_ns))

    def test_all_standby_zero_is_valid_data_but_fails_active_smoke(self):
        records = complete_records(left=0.0, right=0.0, state="STANDBY")
        self.assertTrue(self.check(records)["passed"])
        self.assertFails(records, min_active=10, require_nonzero_active=True)

    def test_active_zero_is_valid_data_but_fails_nonzero_smoke(self):
        records = complete_records(n=10, left=0.0, right=0.0)
        self.assertTrue(self.check(records, min_active=10)["passed"])
        self.assertFails(records, min_active=10, require_nonzero_active=True)

    def test_smoke_minimum_and_nonzero_pass_when_satisfied(self):
        self.assertTrue(self.check(complete_records(n=10), min_active=10,
                                   require_nonzero_active=True)["passed"])
        self.assertFails(complete_records(n=9), min_active=10)

    def test_mixed_control_identity_fails(self):
        for override in ({"control_mode": "nmpc"}, {"backend": "ipopt"},
                         {"actuation_anchor_source": "actual_sensor"}):
            with self.subTest(override=override):
                self.assertFails(replace_payload(complete_records(), "status", 2,
                                                  status_payload(**override)))

    def test_unknown_state_and_missing_applied_fields_fail(self):
        self.assertFails(replace_payload(complete_records(), "status", 2,
                                          status_payload(state="UNKNOWN")))
        value = json.loads(status_payload()["data"])
        del value["tr_n"]
        self.assertFails(replace_payload(complete_records(), "status", 2,
                                          {"data": json.dumps(value)}))

    def test_malformed_json_fails(self):
        for payload in ({"data": "{"}, {"data": "[]"}, {"data": "null"}):
            with self.subTest(payload=payload):
                self.assertFails(replace_payload(complete_records(), "status", 2, payload))

    def test_nonfinite_command_or_status_fields_fail(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self.assertFails(replace_payload(complete_records(), "left", 2, {"data": value}))
                self.assertFails(replace_payload(complete_records(), "status", 2,
                                                  status_payload(tl_cmd_n=value)))

    def test_nonfinite_observation_reference_values_fail(self):
        payloads = {
            "odom": {"header": {"stamp": stamp(9_900_000_000)},
                     "pose": {"pose": {"position": {"x": math.nan}}}},
            "imu": {"header": {"stamp": stamp(10 * NS)},
                    "angular_velocity": {"z": math.inf}},
            "path": {"header": {"stamp": stamp(10 * NS)},
                     "poses": [{"pose": {"position": {"y": -math.inf}}}]},
            "reference_profile": {"data": [0.0, math.nan, 0.0]},
        }
        for key, payload in payloads.items():
            with self.subTest(key=key):
                self.assertFails(replace_payload(complete_records(), key, 0, payload))

    def test_status_dynamic_period_must_be_positive_finite_and_bound_window(self):
        for value in (0.0, -0.2, math.nan, 0.03):
            with self.subTest(value=value):
                self.assertFails(replace_payload(complete_records(), "status", 2,
                                                  status_payload(dynamic_dt=value)))

    def test_wrong_topic_type_fails(self):
        for key in ("left", "status", "clock", "odom", "reference_profile"):
            with self.subTest(key=key):
                types = dict(TYPES)
                types[TOPICS[key]] = "std_msgs/msg/Bool"
                self.assertFails(topic_types=types)

    def test_clock_reset_fails_strict(self):
        records = complete_records()
        records = [checker.Record(x.topic, x.bag_ns,
                                   {"clock": stamp(1 * NS + x.bag_ns - NS)})
                   if x.topic == TOPICS["clock"] and x.bag_ns >= NS + 400_000_000
                   else x for x in records]
        self.assertFails(records)

    def test_clock_with_receive_coverage_but_no_sim_progress_fails_strict(self):
        records = [checker.Record(x.topic, x.bag_ns, {"clock": stamp(10 * NS)})
                   if x.topic == TOPICS["clock"] else x for x in complete_records()]
        self.assertFails(records)
        report = self.check(records, profile="legacy-actions")
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["warnings"], report)

    def test_stale_clock_must_not_mask_adjacent_active_control_intervals(self):
        records = [x for x in complete_records()
                   if x.topic != TOPICS["clock"] or x.bag_ns in (NS, 2 * NS)]
        self.assertFails(records)

    def test_clock_must_cover_both_control_boundaries(self):
        for condition in (lambda x: x.bag_ns >= NS + 100_000_000,
                          lambda x: x.bag_ns <= NS + 700_000_000):
            records = [x for x in complete_records()
                       if x.topic != TOPICS["clock"] or condition(x)]
            self.assertFails(records)

    def test_odometry_message_exists_but_does_not_cover_controls(self):
        self.assertFails(remove_occurrence(complete_records(), "odom", 1))

    def test_odometry_simulation_stamps_must_cover_mapped_control_time(self):
        records = [checker.Record(x.topic, x.bag_ns,
                                   {"header": {"stamp": stamp(NS)}})
                   if x.topic == TOPICS["odom"] else x for x in complete_records()]
        self.assertFails(records)

    def test_remapped_topics_pass_only_with_matching_configuration(self):
        remapped = {key: "/test" + topic for key, topic in TOPICS.items()}
        names = {TOPICS[key]: remapped[key] for key in TOPICS}
        records = [checker.Record(names[x.topic], x.bag_ns, x.payload) for x in complete_records()]
        types = {names[key]: value for key, value in TYPES.items()}
        self.assertFails(records, types)
        self.assertTrue(self.check(records, types, topics=remapped)["passed"])

    def test_thrust_limit_is_a_parameter_not_a_fixed_25_n_rule(self):
        records = complete_records(left=-12.0, right=12.0)
        self.assertTrue(self.check(records, thrust_limit_n=12.0)["passed"])
        self.assertFails(records, thrust_limit_n=11.0)
        self.assertTrue(self.check(complete_records(left=30.0, right=30.0),
                                   thrust_limit_n=35.0)["passed"])

    def test_actual_scanned_counts_must_agree_with_metadata(self):
        counts = {}
        for item in complete_records():
            counts[item.topic] = counts.get(item.topic, 0) + 1
        self.assertTrue(self.check(expected_counts=counts)["passed"])
        counts[TOPICS["left"]] += 1
        report = self.assertFails(expected_counts=counts)
        self.assertTrue(any(x["code"] == "metadata_count_mismatch" for x in report["failures"]), report)

    def test_cli_refuses_report_inside_bag_before_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            bag = Path(directory) / "bag"
            bag.mkdir()
            metadata = bag / "metadata.yaml"
            metadata.write_text("sentinel", encoding="utf-8")
            with mock.patch.object(checker, "read_bag") as read, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(checker.main([str(bag), "--report", str(metadata)]), 1)
            read.assert_not_called()
            self.assertEqual(metadata.read_text(encoding="utf-8"), "sentinel")

    def test_cli_invalid_configuration_exits_one_with_external_error_report(self):
        with tempfile.TemporaryDirectory() as directory:
            bag = Path(directory) / "bag"
            bag.mkdir()
            output = Path(directory) / "error.json"
            with mock.patch.object(checker, "read_bag") as read, contextlib.redirect_stdout(io.StringIO()):
                result = checker.main([str(bag), "--report", str(output), "--match-window-ms", "100"])
            self.assertEqual(result, 1)
            read.assert_not_called()
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["exit_code"], 1)
            self.assertFalse(report["passed"])

    def test_cli_data_failure_exits_two_with_external_data_report(self):
        with tempfile.TemporaryDirectory() as directory:
            bag = Path(directory) / "bag"
            bag.mkdir()
            output = Path(directory) / "acceptance.json"
            records = remove_occurrence(complete_records(), "left", 2)
            with mock.patch.object(checker, "read_bag", return_value=(records, TYPES, {})), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = checker.main([str(bag), "--report", str(output)])
            self.assertEqual(result, 2)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["exit_code"], 2)
            self.assertFalse(report["passed"])

    def test_bad_configuration_raises_valueerror(self):
        cases = [
            {"profile": "unknown"}, {"match_window_s": 0},
            {"match_window_s": -0.1}, {"match_window_s": 0.1},
            {"match_window_s": math.nan}, {"nominal_dt_s": 0},
            {"tolerance_n": -1}, {"tolerance_n": math.inf},
            {"thrust_limit_n": 0}, {"thrust_limit_n": math.nan},
            {"min_active": -1},
            {"topics": {**TOPICS, "right": TOPICS["left"]}},
        ]
        for config in cases:
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.check(**config)


if __name__ == "__main__":
    unittest.main()
