#!/usr/bin/env python3
"""Read-only check of PPO published-command records, not realized actuator forces.

ROS dependencies are imported only by read_bag().  The pure validate_records()
entry point also accepts synthetic records, so loss and timing checks can be
tested without ROS.  Receive-time matching cannot prove common-drop absence or
precise input holding intervals; these limitations are explicit in the report.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass, field
import json
import math
from numbers import Real
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


DEFAULT_TOPICS = {
    "left": "/wamv/thrusters/left/thrust",
    "right": "/wamv/thrusters/right/thrust",
    "status": "/mpc/status",
    "odom": "/wamv/sensors/position/ground_truth_odometry",
    "imu": "/wamv/sensors/imu/imu/data",
    "path": "/path/reference",
    "reference_profile": "/path/reference_profile",
    "clock": "/clock",
}
TOPIC_TYPES = {
    "left": "std_msgs/msg/Float64",
    "right": "std_msgs/msg/Float64",
    "status": "std_msgs/msg/String",
    "odom": "nav_msgs/msg/Odometry",
    "imu": "sensor_msgs/msg/Imu",
    "path": "nav_msgs/msg/Path",
    "reference_profile": "std_msgs/msg/Float64MultiArray",
    "clock": "rosgraph_msgs/msg/Clock",
}
LIMITATIONS = [
    "Recorded values are published commands, not measured or acknowledged actuator forces.",
    "Float64/status lack a source timestamp and control sequence; receive-time pairing is approximate.",
    "A common loss of left/right/status may be unidentifiable without a visible simulation-time gap.",
    "Thrust bounds alone do not verify physical units; bind the model and manifest hashes in run_context.",
    "This check does not establish precise hold intervals, execution latency, or GP label readiness.",
]


@dataclass(frozen=True)
class Record:
    topic: str
    bag_ns: int
    payload: dict[str, Any]


@dataclass
class Config:
    profile: str = "ppo-actions-v1"
    topics: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TOPICS))
    match_window_s: float = 0.02
    tolerance_n: float = 1e-5
    nominal_dt_s: float = 0.2
    thrust_limit_n: float = 25.0
    min_active: int = 0
    require_nonzero_active: bool = False
    expected_counts: dict[str, int] | None = None

    def validate(self) -> None:
        if self.profile not in ("ppo-actions-v1", "legacy-actions"):
            raise ValueError("unknown profile")
        for name in ("match_window_s", "nominal_dt_s", "thrust_limit_n"):
            if not _finite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not _finite(self.tolerance_n) or self.tolerance_n < 0:
            raise ValueError("tolerance_n must be nonnegative and finite")
        if self.match_window_s >= 0.5 * self.nominal_dt_s:
            raise ValueError("match_window_s must be strictly below half nominal_dt_s")
        if isinstance(self.min_active, bool) or not isinstance(self.min_active, int) or self.min_active < 0:
            raise ValueError("min_active must be a nonnegative integer")
        if set(self.topics) != set(DEFAULT_TOPICS):
            raise ValueError("topics must contain exactly the eight documented role names")
        if any(not isinstance(v, str) or not v.startswith("/") for v in self.topics.values()):
            raise ValueError("topic names must be absolute ROS names")
        if len(set(self.topics.values())) != len(self.topics):
            raise ValueError("topic roles must have distinct names")
        if self.expected_counts is not None:
            for count in self.expected_counts.values():
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ValueError("metadata counts must be nonnegative integers")


def _finite(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _stamp_ns(stamp: Mapping[str, Any]) -> int:
    sec, nanosec = stamp["sec"], stamp["nanosec"]
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (sec, nanosec)):
        raise ValueError("timestamp sec/nanosec must be integers")
    if sec < 0 or not 0 <= nanosec < 1_000_000_000:
        raise ValueError("timestamp out of range")
    return sec * 1_000_000_000 + nanosec


def _first_nonfinite_path(value: Any, path: str = "payload") -> str | None:
    """Check all numeric fields retained from real deserialized ROS messages."""
    if isinstance(value, Real) and not isinstance(value, bool):
        if not math.isfinite(value):
            return path
    elif isinstance(value, Mapping):
        for key, child in value.items():
            result = _first_nonfinite_path(child, f"{path}.{key}")
            if result is not None:
                return result
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            result = _first_nonfinite_path(child, f"{path}[{index}]")
            if result is not None:
                return result
    return None


def validate_records(records: Iterable[Record], topic_types: Mapping[str, str],
                     config: Config | None = None) -> dict[str, Any]:
    """Validate actual decoded records; invalid config raises ValueError.

    Payloads use the ROS field names: {data: float}, {data: JSON string},
    {clock: {sec, nanosec}}, or {header: {stamp: {sec, nanosec}}}.
    A status JSON object may also be passed directly.  Decode failures can be
    represented by {"__decode_error__": "reason"}; they still count as records.
    """
    cfg = config or Config()
    cfg.validate()
    strict = cfg.profile == "ppo-actions-v1"
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    decoded: Counter[str] = Counter()
    by_role: dict[str, list[tuple[int, int, Any]]] = {key: [] for key in DEFAULT_TOPICS}
    role_for_topic = {topic: role for role, topic in cfg.topics.items()}

    def issue(code: str, detail: str, *, warning: bool = False, **context: Any) -> None:
        (warnings if warning else failures).append({"code": code, "detail": detail, **context})

    for role, topic in cfg.topics.items():
        if topic not in topic_types:
            issue("missing_topic", f"Missing {role} topic", topic=topic,
                  warning=(role == "clock" and not strict))
        elif topic_types[topic] != TOPIC_TYPES[role]:
            issue("wrong_topic_type", f"Expected {TOPIC_TYPES[role]}", topic=topic,
                  actual_type=topic_types[topic])

    for index, rec in enumerate(records):
        counts[rec.topic] += 1
        role = role_for_topic.get(rec.topic)
        if role is None:
            continue
        if isinstance(rec.bag_ns, bool) or not isinstance(rec.bag_ns, int) or rec.bag_ns < 0:
            issue("invalid_bag_timestamp", "Bag timestamp must be a nonnegative integer", record_index=index)
            continue
        try:
            if not isinstance(rec.payload, dict):
                raise ValueError("decoded payload is not a mapping")
            if "__decode_error__" in rec.payload:
                raise ValueError(rec.payload["__decode_error__"])
            invalid_path = _first_nonfinite_path(rec.payload)
            if invalid_path is not None:
                raise ValueError(f"nonfinite numeric field {invalid_path}")
            if topic_types.get(rec.topic) != TOPIC_TYPES[role]:
                continue
            if role in ("left", "right"):
                value = rec.payload["data"]
                if not _finite(value):
                    raise ValueError("thrust must be a finite numeric value")
                value = float(value)
                if abs(value) > cfg.thrust_limit_n + cfg.tolerance_n:
                    issue("thrust_out_of_range", "Published thrust exceeds configured limit", topic=rec.topic,
                          record_index=index, value_n=value)
            elif role == "status":
                value = json.loads(rec.payload["data"]) if "data" in rec.payload else dict(rec.payload)
                if not isinstance(value, dict):
                    raise ValueError("status JSON must be an object")
                invalid_path = _first_nonfinite_path(value, "status")
                if invalid_path is not None:
                    raise ValueError(f"nonfinite numeric field {invalid_path}")
                for name in ("tl_n", "tr_n", "tl_cmd_n", "tr_cmd_n", "dynamic_dt"):
                    if not _finite(value.get(name)):
                        raise ValueError(f"missing/nonfinite status field {name}")
                if value["dynamic_dt"] <= 0:
                    raise ValueError("dynamic_dt must be positive")
                if cfg.match_window_s >= 0.5 * value["dynamic_dt"]:
                    issue("window_exceeds_dynamic_dt", "Match window is not below half this status dynamic_dt",
                          record_index=index)
                if value.get("state") not in ("ACTIVE", "STANDBY"):
                    raise ValueError("state must be ACTIVE or STANDBY")
                identity = {"control_mode": "rl", "backend": "onnx_ppo", "actuation_anchor_source": "vrx_published"}
                if any(value.get(k) != v for k, v in identity.items()):
                    issue("wrong_controller_identity", "Status is not a PPO VRX published-command anchor",
                          record_index=index)
                for name in ("tl_n", "tr_n", "tl_cmd_n", "tr_cmd_n"):
                    if abs(value[name]) > cfg.thrust_limit_n + cfg.tolerance_n:
                        issue("thrust_out_of_range", f"Status {name} exceeds configured limit",
                              record_index=index, value_n=value[name])
            elif role == "clock":
                value = _stamp_ns(rec.payload["clock"])
            elif role in ("odom", "imu", "path"):
                value = _stamp_ns(rec.payload["header"]["stamp"])
            else:
                value = rec.payload["data"]
                if not isinstance(value, (list, tuple)) or not value or not all(_finite(x) for x in value):
                    raise ValueError("reference_profile data must be a nonempty finite numeric array")
            decoded[rec.topic] += 1
            by_role[role].append((rec.bag_ns, index, value))
        except (KeyError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            issue("invalid_payload", str(exc), topic=rec.topic, record_index=index)

    for role, topic in cfg.topics.items():
        if decoded[topic] == 0 and topic in topic_types:
            issue("no_decodable_records", f"No usable {role} records", topic=topic,
                  warning=(role == "clock" and not strict and counts[topic] == 0))
    if cfg.expected_counts is not None:
        for topic in set(counts) | set(cfg.expected_counts):
            if counts[topic] != cfg.expected_counts.get(topic, 0):
                issue("metadata_count_mismatch", "Actual scanned message count differs from metadata", topic=topic,
                      actual_count=counts[topic], metadata_count=cfg.expected_counts.get(topic, 0))

    for role, stream in by_role.items():
        if any(current[0] < previous[0] for previous, current in zip(stream, stream[1:])):
            issue("bag_time_regression", f"Receive time regressed on {role}")
        stream.sort(key=lambda item: (item[0], item[1]))

    statuses = by_role["status"]
    active_count = sum(value["state"] == "ACTIVE" for _, _, value in statuses)
    nonzero_active = sum(value["state"] == "ACTIVE" and
                         (abs(value["tl_n"]) > cfg.tolerance_n or abs(value["tr_n"]) > cfg.tolerance_n)
                         for _, _, value in statuses)
    if active_count < cfg.min_active:
        issue("insufficient_active", "ACTIVE count below smoke-test minimum", actual=active_count, minimum=cfg.min_active)
    if cfg.require_nonzero_active and nonzero_active == 0:
        issue("no_nonzero_active", "Smoke test requires a nonzero ACTIVE published command")

    # Match by time/order only.  Values are deliberately unavailable until a
    # unique, unused temporal candidate has been selected.
    matching: dict[str, Any] = {}
    # Use integer bounds: subtracting a float from epoch-scale nanoseconds loses
    # precision and can misclassify a record one nanosecond inside the window.
    # ceil retains the strict threshold for discrete integer-nanosecond stamps.
    window_ns = math.ceil(cfg.match_window_s * 1_000_000_000)
    all_statuses_paired = True
    for role, status_field in (("left", "tl_n"), ("right", "tr_n")):
        stream = by_role[role]
        times = [entry[0] for entry in stream]
        used: set[int] = set()
        matched = 0
        max_error = 0.0
        max_offset_ns = 0
        last_match = -1
        for time_ns, status_index, status in statuses:
            lower = bisect_right(times, time_ns - window_ns)
            upper = bisect_left(times, time_ns + window_ns)
            candidates = list(range(lower, upper))
            if not candidates:
                issue("missing_action_match", f"No {role} message inside strict temporal window",
                      status_index=status_index, status_bag_ns=time_ns)
                all_statuses_paired = False
                continue
            if len(candidates) != 1:
                issue("ambiguous_action_match", f"Multiple {role} temporal candidates; values cannot resolve them",
                      status_index=status_index, candidate_indices=[stream[j][1] for j in candidates])
                all_statuses_paired = False
                continue
            position = candidates[0]
            if position in used or position <= last_match:
                issue("reused_or_out_of_order_action", f"{role} message cannot be reused or matched out of order",
                      status_index=status_index, action_index=stream[position][1])
                all_statuses_paired = False
                continue
            used.add(position)
            last_match = position
            matched += 1
            offset_ns = abs(stream[position][0] - time_ns)
            error = abs(stream[position][2] - status[status_field])
            max_error = max(max_error, error)
            max_offset_ns = max(max_offset_ns, offset_ns)
            if error > cfg.tolerance_n:
                issue("action_value_mismatch", f"{role} publication differs from status {status_field}",
                      status_index=status_index, action_index=stream[position][1], error_n=error)
        unpaired = [entry[1] for j, entry in enumerate(stream) if j not in used]
        if unpaired:
            issue("unmatched_action_records", f"Unpaired {role} records, including any boundary fragments",
                  record_indices=unpaired)
        matching[role] = {"message_count": len(stream), "matched_count": matched,
                          "status_match_rate": matched / len(statuses) if statuses else 0.0,
                          "unmatched_count": len(unpaired), "max_error_n": max_error,
                          "max_abs_offset_s": max_offset_ns / 1_000_000_000}

    timing: dict[str, Any] = {
        "timing_incomplete": not bool(by_role["clock"]),
        "mapping_method": "latest preceding /clock by bag receive timestamp; no interpolation across reset",
        "gap_threshold_dynamic_dt_factor": 1.5,
        "odom_sim_coverage_tolerance_s": 0.5 * cfg.nominal_dt_s,
        "clock_reset_count": 0, "odom_reset_count": 0, "clock_equal_sample_count": 0,
        "clock_segments": [], "clock_pause_segments": [],
        "active_visible_gaps": [], "max_active_sim_interval_s": None,
        "active_nonprogressing_intervals": [], "max_preceding_clock_receive_age_s": None,
        "max_adjacent_active_receive_interval_s": None,
    }
    if not by_role["clock"] and not strict:
        issue("timing_incomplete", "Clock absent: receive-time command consistency only", warning=True)
    for role in ("clock", "odom"):
        stream = by_role[role]
        resets = [(a[1], b[1]) for a, b in zip(stream, stream[1:]) if b[2] < a[2]]
        timing[f"{role}_reset_count"] = len(resets)
        if resets:
            issue("simulation_time_reset", f"{role} time regressed; do not join segments", warning=not strict,
                  role=role, reset_record_indices=resets)
        if role == "clock":
            timing["clock_equal_sample_count"] = sum(a[2] == b[2] for a, b in zip(stream, stream[1:]))
            if stream:
                segment_start = 0
                pause_start = None
                for position in range(1, len(stream) + 1):
                    at_end = position == len(stream)
                    reset = not at_end and stream[position][2] < stream[position - 1][2]
                    equal = not at_end and stream[position][2] == stream[position - 1][2]
                    if equal and pause_start is None:
                        pause_start = position - 1
                    elif not equal and pause_start is not None:
                        timing["clock_pause_segments"].append({
                            "start_record_index": stream[pause_start][1],
                            "end_record_index": stream[position - 1][1],
                            "simulation_ns": stream[pause_start][2],
                            "receive_duration_s": (stream[position - 1][0] - stream[pause_start][0]) / 1e9,
                            "interpretation": "equal received clock samples; absence of clock while paused is not observable here",
                        })
                        pause_start = None
                    if at_end or reset:
                        timing["clock_segments"].append({
                            "start_record_index": stream[segment_start][1],
                            "end_record_index": stream[position - 1][1],
                            "bag_range_ns": [stream[segment_start][0], stream[position - 1][0]],
                            "simulation_range_ns": [stream[segment_start][2], stream[position - 1][2]],
                        })
                        segment_start = position
        if statuses and stream and (stream[0][0] > statuses[0][0] or stream[-1][0] < statuses[-1][0]):
            timing["timing_incomplete"] = True
            issue("control_interval_not_covered", f"{role} receive-time range does not cover all status records",
                  warning=not strict, role=role,
                  stream_range_ns=[stream[0][0], stream[-1][0]],
                  status_range_ns=[statuses[0][0], statuses[-1][0]])

    clocks = by_role["clock"]
    clock_times = [item[0] for item in clocks]
    mapped: list[int | None] = []
    clock_receive_ages = []
    for status_time, _, _ in statuses:
        index = bisect_right(clock_times, status_time) - 1
        mapped.append(clocks[index][2] if index >= 0 else None)
        if index >= 0:
            clock_receive_ages.append((status_time - clocks[index][0]) / 1e9)
    timing["max_preceding_clock_receive_age_s"] = max(clock_receive_ages) if clock_receive_ages else None
    if statuses and clocks and any(value is None for value in mapped):
        timing["timing_incomplete"] = True
        issue("missing_preceding_clock", "Some controls have no preceding clock record", warning=not strict)
    if statuses and by_role["odom"] and mapped and all(value is not None for value in mapped):
        odom_stamps = [item[2] for item in by_role["odom"]]
        margin_ns = 0.5 * cfg.nominal_dt_s * 1_000_000_000
        if min(odom_stamps) > min(mapped) + margin_ns or max(odom_stamps) < max(mapped) - margin_ns:
            timing["timing_incomplete"] = True
            issue("odom_sim_interval_not_covered", "Odometry stamps do not cover mapped control simulation times",
                  warning=not strict)
    intervals = []
    receive_intervals = []
    if timing["clock_reset_count"] == 0:
        for index in range(1, len(statuses)):
            previous, current = statuses[index - 1], statuses[index]
            if previous[2]["state"] != "ACTIVE" or current[2]["state"] != "ACTIVE":
                continue
            receive_intervals.append((current[0] - previous[0]) / 1_000_000_000)
            if mapped[index] is None or mapped[index - 1] is None:
                continue
            interval_s = (mapped[index] - mapped[index - 1]) / 1_000_000_000
            intervals.append(interval_s)
            if interval_s <= 0:
                nonprogress = {"before_status_index": previous[1], "after_status_index": current[1],
                               "simulation_interval_s": interval_s}
                timing["active_nonprogressing_intervals"].append(nonprogress)
                timing["timing_incomplete"] = True
                issue("nonprogressing_active_sim_time",
                      "Clock cannot distinguish adjacent ACTIVE controls; pause, coarse clock, or stale mapping is possible",
                      warning=not strict, **nonprogress)
            if interval_s > 1.5 * previous[2]["dynamic_dt"]:
                gap = {"before_status_index": previous[1], "after_status_index": current[1],
                       "simulation_interval_s": interval_s,
                       "threshold_s": 1.5 * previous[2]["dynamic_dt"]}
                timing["active_visible_gaps"].append(gap)
                issue("visible_active_gap", "Mapped ACTIVE interval exceeds configured dynamic_dt factor",
                      warning=not strict, **gap)
    timing["max_active_sim_interval_s"] = max(intervals) if intervals else None
    timing["max_adjacent_active_receive_interval_s"] = max(receive_intervals) if receive_intervals else None
    action_codes = {"invalid_payload", "wrong_topic_type", "missing_topic", "no_decodable_records",
                    "thrust_out_of_range", "wrong_controller_identity", "window_exceeds_dynamic_dt",
                    "missing_action_match", "ambiguous_action_match", "reused_or_out_of_order_action",
                    "action_value_mismatch", "unmatched_action_records", "invalid_bag_timestamp", "bag_time_regression"}
    action_topics = {cfg.topics[name] for name in ("left", "right", "status")}
    action_failures = [item for item in failures if item["code"] in action_codes and
                       ("topic" not in item or item["topic"] in action_topics)]
    consistent = bool(statuses) and all_statuses_paired and not action_failures
    return {
        "schema": "ppo-bag-actions-check/1", "profile": cfg.profile, "passed": not failures,
        "exit_code": 0 if not failures else 2,
        "recorded_action_stream_consistent": consistent,
        "simulation_clock_recorded": bool(clocks),
        "common_drop_identifiable": False, "exact_execution_timing_available": False,
        "gp_labels_ready": False, "action_recording_complete": False,
        "action_recording_complete_note": "No source sequence: entire planned control stream completeness is unproven.",
        "allowed_use": (["published_command_statistics_with_timing_limits", "trajectory_analysis_with_limits"]
                        if consistent else ["trajectory_and_observation_analysis_with_limits"]),
        "actual_message_counts": dict(counts), "decoded_message_counts": dict(decoded),
        "metadata_message_counts": cfg.expected_counts,
        "topic_types": dict(topic_types), "active_count": active_count,
        "nonzero_active_count": nonzero_active, "matching": matching, "timing": timing,
        "parameters": {"topics": dict(cfg.topics), "match_window_s": cfg.match_window_s,
                       "window_is_strict": True, "tolerance_n": cfg.tolerance_n,
                       "nominal_dt_s": cfg.nominal_dt_s, "thrust_limit_n": cfg.thrust_limit_n,
                       "thrust_limit_source": "explicit validator argument; not inferred from recorded values",
                       "min_active": cfg.min_active, "require_nonzero_active": cfg.require_nonzero_active},
        "failures": failures, "warnings": warnings, "limitations": LIMITATIONS,
    }


def _message_payload(role: str, msg: Any) -> dict[str, Any]:
    def stamp(value: Any) -> dict[str, int]:
        return {"sec": int(value.sec), "nanosec": int(value.nanosec)}
    if role in ("left", "right", "status"):
        return {"data": msg.data}
    if role == "reference_profile":
        return {"data": list(msg.data)}
    if role == "clock":
        return {"clock": stamp(msg.clock)}
    # Keep all sensor/path numeric fields so a successful CDR decode does not
    # falsely count NaN/Inf observations as usable.  This is not a physics or
    # reference-layout validator.
    from rosidl_runtime_py.convert import message_to_ordereddict
    return message_to_ordereddict(msg)


def read_bag(bag: Path, cfg: Config) -> tuple[list[Record], dict[str, str], dict[str, Any]]:
    """Read metadata-selected storage without creating/writing any bag file."""
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    metadata_path = bag / "metadata.yaml"
    with metadata_path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    info = document["rosbag2_bagfile_information"]
    storage_id = info["storage_identifier"]
    if not isinstance(storage_id, str) or not storage_id:
        raise ValueError("metadata storage_identifier missing or invalid")
    files = info.get("relative_file_paths", [])
    if not files or any(not isinstance(name, str) or not name for name in files):
        raise ValueError("metadata relative_file_paths missing or invalid")
    for name in files:
        candidate = (bag / name).resolve()
        if not candidate.is_relative_to(bag):
            raise ValueError("metadata storage path escapes bag directory")
        if not candidate.is_file():
            raise ValueError(f"missing storage file {name}")
    expected_counts: dict[str, int] = {}
    metadata_types: dict[str, str] = {}
    for item in info["topics_with_message_count"]:
        entry = item["topic_metadata"]
        name = entry["name"]
        if name in expected_counts:
            raise ValueError(f"duplicate metadata topic {name}")
        expected_counts[name] = item["message_count"]
        metadata_types[name] = entry["type"]
    cfg.expected_counts = expected_counts
    cfg.validate()
    total = info["message_count"]
    if isinstance(total, bool) or not isinstance(total, int) or total != sum(expected_counts.values()):
        raise ValueError("metadata total message count differs from per-topic totals")
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage_id),
                rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"))
    actual_types = {entry.name: entry.type for entry in reader.get_all_topics_and_types()}
    if actual_types != metadata_types:
        raise ValueError("storage topic definitions disagree with metadata")
    role_for_topic = {topic: role for role, topic in cfg.topics.items()}
    classes: dict[str, Any] = {}
    for topic, role in role_for_topic.items():
        if actual_types.get(topic) == TOPIC_TYPES[role]:
            try:
                classes[topic] = get_message(actual_types[topic])
            except Exception as exc:
                raise ImportError(f"Cannot load required ROS message class {actual_types[topic]}: {exc}") from exc
    records = []
    while reader.has_next():
        topic, serialized, bag_ns = reader.read_next()
        payload: dict[str, Any] = {}
        if topic in role_for_topic:
            if topic in classes:
                try:
                    payload = _message_payload(role_for_topic[topic], deserialize_message(serialized, classes[topic]))
                except Exception as exc:
                    payload = {"__decode_error__": f"{type(exc).__name__}: {exc}"}
        records.append(Record(topic, int(bag_ns), payload))
    return records, actual_types, {"bag": str(bag), "storage_id": storage_id,
                                  "storage_files": files, "metadata_total_message_count": total,
                                  "recorder_time_mode": "not inferred; see external run_context.json"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--profile", choices=("ppo-actions-v1", "legacy-actions"), default="ppo-actions-v1")
    parser.add_argument("--report", type=Path, required=True, help="JSON report outside the original bag directory")
    parser.add_argument("--match-window-ms", type=float, default=20.0)
    parser.add_argument("--match-window-s", type=float, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--value-tolerance-n", "--tolerance-n", dest="tolerance_n", type=float, default=1e-5)
    parser.add_argument("--nominal-dt-s", type=float, default=0.2)
    parser.add_argument("--thrust-limit-n", type=float, default=25.0)
    parser.add_argument("--min-active", type=int, default=0)
    parser.add_argument("--require-nonzero-active", action="store_true")
    for role, topic in DEFAULT_TOPICS.items():
        if role == "reference_profile":
            parser.add_argument("--profile-topic", "--reference-profile-topic", dest="reference_profile_topic", default=topic)
        else:
            parser.add_argument(f"--{role}-topic", default=topic)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1
    bag = args.bag.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    if report_path == bag or report_path.is_relative_to(bag):
        print("Configuration error: report must be outside the original bag directory", file=sys.stderr)
        return 1
    cfg = Config(profile=args.profile,
                 topics={role: getattr(args, f"{role}_topic") for role in DEFAULT_TOPICS},
                 match_window_s=(args.match_window_ms / 1000.0 if args.match_window_s is None else args.match_window_s),
                 tolerance_n=args.tolerance_n,
                 nominal_dt_s=args.nominal_dt_s, thrust_limit_n=args.thrust_limit_n,
                 min_active=args.min_active, require_nonzero_active=args.require_nonzero_active)
    try:
        cfg.validate()
        if not bag.is_dir():
            raise ValueError("bag must be an existing directory containing metadata.yaml")
        records, types, provenance = read_bag(bag, cfg)
        report = validate_records(records, types, cfg)
        report["reading"] = provenance
        exit_code = report["exit_code"]
    except Exception as exc:
        report = {"schema": "ppo-bag-actions-check/1", "profile": cfg.profile, "passed": False,
                  "exit_code": 1, "configuration_or_read_error": f"{type(exc).__name__}: {exc}",
                  "bag": str(bag), "common_drop_identifiable": False,
                  "exact_execution_timing_available": False, "gp_labels_ready": False,
                  "limitations": LIMITATIONS}
        exit_code = 1
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError) as exc:
        print(f"Cannot write external report: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"passed": report["passed"], "exit_code": exit_code, "report": str(report_path),
                      "failure_count": len(report.get("failures", [])),
                      "error": report.get("configuration_or_read_error")}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
