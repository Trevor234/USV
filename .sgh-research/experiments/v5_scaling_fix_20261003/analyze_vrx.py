#!/usr/bin/env python3
"""Read-only VRX rosbag metrics for the physical-N v5 repair.

The old graph is a known-defective diagnostic baseline. Metrics do not imply
equal closed-loop inputs, improved tracking, historical training equivalence,
or a safety proof. Transition-to-STANDBY zeros are classified separately from
the nominal 16 N per-frame constraint on consecutive ACTIVE status messages.
"""
from __future__ import annotations

import argparse
import bisect
from collections import Counter
import json
import math
from pathlib import Path
import time

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import yaml


TOPICS = {
    "status": "/mpc/status",
    "path": "/path/reference",
    "odom": "/wamv/sensors/position/ground_truth_odometry",
    "left": "/wamv/thrusters/left/thrust",
    "right": "/wamv/thrusters/right/thrust",
}
LIMIT_N = 25.0
DELTA_LIMIT_N = 16.0
TOLERANCE_N = 1e-5


def describe(values: list[float]) -> dict | None:
    if not values:
        return None
    values = sorted(values)
    return {
        "n": len(values), "mean": sum(values) / len(values),
        "rms": math.sqrt(sum(v * v for v in values) / len(values)),
        "min": values[0], "max": values[-1],
        "p95": values[int(.95 * (len(values) - 1))],
    }


def number(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def distance(x: float, y: float, points: list[tuple[float, float]]) -> float | None:
    result = []
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        ratio = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / length2)) if length2 else 0.0
        result.append(math.hypot(x - a[0] - ratio * dx, y - a[1] - ratio * dy))
    return min(result) if result else None


def storage_id(bag: Path) -> str:
    metadata = bag / "metadata.yaml"
    if metadata.exists():
        data = yaml.safe_load(metadata.read_text(encoding="utf-8"))
        identifier = data.get("rosbag2_bagfile_information", {}).get("storage_identifier")
        if identifier:
            return identifier
    if list(bag.glob("*.mcap")):
        return "mcap"
    if list(bag.glob("*.db3")):
        return "sqlite3"
    raise FileNotFoundError(f"No supported bag storage found in {bag}")


def nearest(samples: list[tuple[float, float]], timestamp: float) -> tuple[float, float] | None:
    if not samples:
        return None
    idx = bisect.bisect_left(samples, (timestamp, -math.inf))
    candidates = samples[max(0, idx - 1):min(len(samples), idx + 1)]
    return min(candidates, key=lambda item: abs(item[0] - timestamp))


def analyze(args) -> dict:
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(args.bag), storage_id=storage_id(args.bag)),
                rosbag2_py.ConverterOptions("", ""))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types() if t.name in TOPICS.values()}
    counts, states, reasons, backends = Counter(), Counter(), Counter(), Counter()
    path, statuses, odoms = [], [], []
    outputs = {"left": [], "right": []}
    malformed_status = []
    cte, active_cte, odom_speed, active_speed, infer_ms, active_times = [], [], [], [], [], []
    active_delta, standby_transition_delta = [], []
    active_saturated_raw = active_saturated_applied = active_above_one = active_success = deadline_miss = 0
    nonfinite_active = 0
    previous_status = None
    raw_abs, applied_abs = [], []
    first_bag_time = last_bag_time = None
    while reader.has_next():
        topic, data, stamp_ns = reader.read_next()
        timestamp = stamp_ns * 1e-9
        first_bag_time = timestamp if first_bag_time is None else first_bag_time
        last_bag_time = timestamp
        counts[topic] += 1
        if topic not in types:
            continue
        message = deserialize_message(data, types[topic])
        if topic == TOPICS["path"]:
            path = [(p.pose.position.x, p.pose.position.y) for p in message.poses]
        elif topic == TOPICS["odom"]:
            x, y = message.pose.pose.position.x, message.pose.pose.position.y
            speed = math.hypot(message.twist.twist.linear.x, message.twist.twist.linear.y)
            sim_stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
            odoms.append((x, y, sim_stamp))
            if math.isfinite(speed):
                odom_speed.append(speed)
            d = distance(x, y, path)
            if d is not None and math.isfinite(d):
                cte.append(d)
        elif topic in (TOPICS["left"], TOPICS["right"]):
            side = "left" if topic == TOPICS["left"] else "right"
            outputs[side].append((timestamp, float(message.data)))
        elif topic == TOPICS["status"]:
            try:
                status = json.loads(message.data)
                if not isinstance(status, dict):
                    raise ValueError("Status JSON is not an object")
            except Exception as error:
                malformed_status.append({"bag_time_s": timestamp, "error": str(error)})
                previous_status = None
                continue
            state = status.get("state", "missing")
            states[state] += 1
            reasons[status.get("standby_reason", "")] += 1
            backends[status.get("backend", "missing")] += 1
            row = {"bag_time_s": timestamp, "latest_odom_sim_time_s": odoms[-1][2] if odoms else None, "state": state,
                   "raw_n": [number(status.get("tl_cmd_n")), number(status.get("tr_cmd_n"))],
                   "applied_n": [number(status.get("tl_n")), number(status.get("tr_n"))],
                   "x": number(status.get("x")), "y": number(status.get("y")),
                   "standby_reason": status.get("standby_reason", "")}
            statuses.append(row)
            if state == "ACTIVE":
                active_times.append(timestamp)
                active_success += bool(status.get("success"))
                deadline_miss += bool(status.get("deadline_miss"))
                raw, applied = row["raw_n"], row["applied_n"]
                if None in raw or None in applied:
                    nonfinite_active += 1
                else:
                    raw_abs.extend(abs(v) for v in raw)
                    applied_abs.extend(abs(v) for v in applied)
                    active_saturated_raw += any(abs(v) >= LIMIT_N - TOLERANCE_N for v in raw)
                    active_saturated_applied += any(abs(v) >= LIMIT_N - TOLERANCE_N for v in applied)
                    active_above_one += any(abs(v) > 1.0 + TOLERANCE_N for v in applied)
                    if previous_status is not None and previous_status["state"] == "ACTIVE" and None not in previous_status["applied_n"]:
                        active_delta.append({
                            "bag_time_s": timestamp,
                            "wall_interval_s": timestamp - previous_status["bag_time_s"],
                            "estimated_sim_interval_s": row["latest_odom_sim_time_s"] - previous_status["latest_odom_sim_time_s"]
                                if row["latest_odom_sim_time_s"] is not None and previous_status["latest_odom_sim_time_s"] is not None else None,
                            "delta_n": [abs(a - b) for a, b in zip(applied, previous_status["applied_n"])],
                        })
                if row["x"] is not None and row["y"] is not None:
                    d = distance(row["x"], row["y"], path)
                    if d is not None and math.isfinite(d):
                        active_cte.append(d)
                u, v = number(status.get("u")), number(status.get("v"))
                if u is not None and v is not None:
                    active_speed.append(math.hypot(u, v))
                infer = number(status.get("solve_time_ms"))
                if infer is not None:
                    infer_ms.append(infer)
            elif previous_status is not None and previous_status["state"] == "ACTIVE" and None not in row["applied_n"] and None not in previous_status["applied_n"]:
                standby_transition_delta.append({
                    "bag_time_s": timestamp, "reason": row["standby_reason"],
                    "previous_applied_n": previous_status["applied_n"],
                    "published_n": row["applied_n"],
                    "delta_n": [abs(a - b) for a, b in zip(row["applied_n"], previous_status["applied_n"])],
                })
            previous_status = row

    for side in outputs:
        outputs[side].sort()
    max_delta = max((max(v["delta_n"]) for v in active_delta), default=None)
    delta_violations = [v for v in active_delta if max(v["delta_n"]) > DELTA_LIMIT_N + TOLERANCE_N]
    # A gap suggests dropped bag samples; report it rather than silently call
    # multiple unobserved commands a single nominal-rate control frame.
    active_gaps = [v for v in active_delta if v["estimated_sim_interval_s"] is not None and v["estimated_sim_interval_s"] > .3]
    matches, missing_matches = {"left": [], "right": []}, {"left": [], "right": []}
    for row in statuses:
        if row["state"] != "ACTIVE" or None in row["applied_n"]:
            continue
        for channel, side in enumerate(("left", "right")):
            sample = nearest(outputs[side], row["bag_time_s"])
            if sample is None or abs(sample[0] - row["bag_time_s"]) > .1:
                missing_matches[side].append(row["bag_time_s"])
            else:
                matches[side].append({"bag_time_s": row["bag_time_s"],
                                      "timestamp_offset_s": sample[0] - row["bag_time_s"],
                                      "error_n": abs(sample[1] - row["applied_n"][channel])})
    active_count = states.get("ACTIVE", 0)
    published_values = [v for side in outputs.values() for _, v in side]
    finite_publish = all(math.isfinite(v) for v in published_values)
    max_publish = max((abs(v) for v in published_values if math.isfinite(v)), default=None)
    checks = {
        "entered_active": active_count > 0,
        "finite_active_status_commands": nonfinite_active == 0,
        "finite_real_published_commands": finite_publish and bool(published_values),
        "real_published_within_25_n": max_publish is not None and max_publish <= LIMIT_N + TOLERANCE_N,
        "active_status_applied_within_25_n": bool(applied_abs) and max(applied_abs) <= LIMIT_N + TOLERANCE_N,
        "consecutive_active_delta_within_16_n": bool(active_delta) and not delta_violations,
        "no_large_gap_in_consecutive_active_status": not active_gaps,
        "real_thrust_matches_active_status": active_count > 0 and all(not missing_matches[side] and
            bool(matches[side]) and max(row["error_n"] for row in matches[side]) <= TOLERANCE_N for side in matches),
        "status_json_valid": not malformed_status,
    }
    report = {
        "label": args.label, "bag_path": str(args.bag), "analyzed_unix": time.time(),
        "purpose": "known-unit-defect diagnostic baseline" if args.diagnostic_old else "short-run physical-N deployment acceptance",
        "known_unit_defect": bool(args.diagnostic_old),
        "passed_current_interface_checks": all(checks.values()), "checks": checks,
        "thresholds": {"physical_limit_n": LIMIT_N, "nominal_dt_s": .2,
                       "nominal_delta_limit_n": DELTA_LIMIT_N, "numeric_tolerance_n": TOLERANCE_N,
                       "status_publish_match_window_wall_s": .1, "active_gap_diagnostic_sim_s": .3},
        "topic_counts": dict(counts), "states": dict(states), "standby_reasons": dict(reasons),
        "backends": dict(backends), "active_count": active_count, "active_success_count": active_success,
        "deadline_miss_count": deadline_miss, "nonfinite_active_count": nonfinite_active,
        "recorded_bag_seconds": last_bag_time - first_bag_time if first_bag_time is not None else None,
        "active_status_span_seconds": active_times[-1] - active_times[0] if active_times else None,
        "active_status_intervals_wall_seconds": describe([b-a for a,b in zip(active_times, active_times[1:])]),
        "consecutive_active_intervals_estimated_sim_seconds": describe([v["estimated_sim_interval_s"] for v in active_delta if v["estimated_sim_interval_s"] is not None]),
        "odom_sim_seconds": odoms[-1][2] - odoms[0][2] if odoms else None,
        "odom_first_xy": list(odoms[0][:2]) if odoms else None, "odom_last_xy": list(odoms[-1][:2]) if odoms else None,
        "odom_speed_mps": describe(odom_speed), "active_speed_mps": describe(active_speed),
        "cte_all_odom_m": describe(cte), "cte_active_status_m": describe(active_cte),
        "infer_ms": describe(infer_ms), "raw_abs_n": describe(raw_abs), "applied_abs_n": describe(applied_abs),
        "raw_saturated_active_frames": active_saturated_raw,
        "applied_saturated_active_frames": active_saturated_applied,
        "raw_saturation_fraction": active_saturated_raw / active_count if active_count else None,
        "applied_saturation_fraction": active_saturated_applied / active_count if active_count else None,
        "applied_above_1_n_active_frames": active_above_one,
        "left_published_n": describe([v for _, v in outputs["left"] if math.isfinite(v)]),
        "right_published_n": describe([v for _, v in outputs["right"] if math.isfinite(v)]),
        "consecutive_active_delta_n_max": max_delta,
        "consecutive_active_delta_count": len(active_delta), "active_delta_violations": delta_violations,
        "large_active_status_gaps": active_gaps,
        "transition_to_standby_events_excluded_from_nominal_delta": standby_transition_delta,
        "publish_status_matches": {side: {"count": len(values),
            "max_error_n": max((v["error_n"] for v in values), default=None),
            "max_abs_timestamp_offset_s": max((abs(v["timestamp_offset_s"]) for v in values), default=None),
            "missing_active_match_count": len(missing_matches[side])} for side, values in matches.items()},
        "malformed_status": malformed_status,
        "limitations": ["This is one short-run simulation, not a safety or stability proof.",
            "Old and new closed-loop observations may differ; the 25-times graph relation is tested only on frozen identical raw observations.",
            "ACTIVE recording gaps use simulation time estimated from the latest received odometry; wall-time bag timestamps can stretch when Gazebo runs below real time.",
            "Large transitions to standby zero are reported separately as existing behavior.",
            "The source of historical training range and checkpoint/normalizer pairing is not inferred from this bag."],
    }
    complete = args.bag.parent / "complete.json"
    if complete.exists():
        report["run_complete"] = json.loads(complete.read_text(encoding="utf-8"))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--label", default="new_physical_n")
    parser.add_argument("--diagnostic-old", action="store_true")
    args = parser.parse_args()
    result = analyze(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in ("label", "known_unit_defect", "passed_current_interface_checks", "active_count", "checks", "raw_abs_n", "applied_abs_n", "consecutive_active_delta_n_max", "infer_ms", "cte_active_status_m", "active_speed_mps")}, ensure_ascii=False))
    return 0 if args.diagnostic_old or result["passed_current_interface_checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
