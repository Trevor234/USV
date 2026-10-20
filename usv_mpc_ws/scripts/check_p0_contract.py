#!/usr/bin/env python3
"""Read-only publisher-side P0 contract checker; never certifies plant execution.

The pure decoded-record validator also runs without ROS. The real-bag reader
loads rosbag2 storage and message support only when invoked from the CLI.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

NS = 1_000_000_000
DEFAULT_TOPICS = {
    "state": "/research/state_snapshot",
    "applied": "/research/control/applied",
    "cycle": "/research/cycle_timing",
    "odom": "/wamv/sensors/position/ground_truth_odometry",
    "imu": "/wamv/sensors/imu/imu/data",
    "clock": "/clock",
    "path": "/path/reference",
    "profile": "/path/reference_profile",
    "left": "/wamv/thrusters/left/thrust",
    "right": "/wamv/thrusters/right/thrust",
    "status": "/mpc/status",
}
TOPIC_TYPES = {
    "state": "usv_research_interfaces/msg/StateSnapshot",
    "applied": "usv_research_interfaces/msg/AppliedControl",
    "cycle": "usv_research_interfaces/msg/CycleTiming",
    "odom": "nav_msgs/msg/Odometry", "imu": "sensor_msgs/msg/Imu",
    "clock": "rosgraph_msgs/msg/Clock", "path": "nav_msgs/msg/Path",
    "profile": "std_msgs/msg/Float64MultiArray", "left": "std_msgs/msg/Float64",
    "right": "std_msgs/msg/Float64", "status": "std_msgs/msg/String",
}
LIMITATIONS = [
    "AppliedControl describes local publisher calls; publish return is not a DDS or plant acknowledgment.",
    "The two Float64 channels are not proven atomic, and physical thrust is not measured.",
    "Callback-local receive sequences cannot prove no sensor loss before callback reception.",
    "Steady times describe this producer/boot only; the local callback-to-publish path is not sensor-to-actuator end-to-end latency.",
    "The last interval has no observed right boundary; bag end is not a substitute.",
    "Publisher-side records alone do not authorize exact residual labels or GP training.",
]

@dataclass(frozen=True)
class Record:
    topic: str
    bag_ns: int
    payload: dict[str, Any]

@dataclass
class Config:
    topics: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TOPICS))
    expected_counts: dict[str, int] | None = None
    nominal_dt_s: float = 0.2
    thrust_limit_n: float = 25.0
    tolerance_n: float = 1e-5
    rate_limit_n_s: float = 80.0

    def validate(self) -> None:
        if set(self.topics) != set(DEFAULT_TOPICS) or len(set(self.topics.values())) != len(self.topics):
            raise ValueError("topics require distinct mappings for every contract role")
        if any(not isinstance(x, str) or not x.startswith("/") for x in self.topics.values()):
            raise ValueError("topic names must be absolute nonempty strings")
        for name in ("nominal_dt_s", "thrust_limit_n", "rate_limit_n_s"):
            value = getattr(self, name)
            if not finite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not finite(self.tolerance_n) or self.tolerance_n < 0:
            raise ValueError("tolerance_n must be finite and nonnegative")
        if self.expected_counts is not None and any(not integer(n, minimum=0) for n in self.expected_counts.values()):
            raise ValueError("metadata counts must be nonnegative integers")

def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def integer(value: Any, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum

def vector(value: Any, size: int) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == size and all(finite(x) for x in value)

def stamp_ns(value: Any) -> int:
    if not isinstance(value, dict) or not isinstance(value.get("sec"), int) or isinstance(value.get("sec"), bool):
        raise ValueError("invalid sec")
    nanos = value.get("nanosec")
    if not integer(nanos) or nanos >= NS:
        raise ValueError("invalid nanosec")
    return value["sec"] * NS + nanos

def finite_tree(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_tree(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return all(finite_tree(v) for v in value)
    return True

def distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None, "mean": None}
    ordered = sorted(values)
    return {"count": len(values), "min": ordered[0], "median": ordered[(len(ordered)-1)//2],
            "p95": ordered[min(len(ordered)-1, math.ceil(.95*len(ordered))-1)],
            "max": ordered[-1], "mean": sum(values)/len(values)}

def hash_bag(bag: Path) -> dict[str, str]:
    """Hash every regular file and reject symlinks before any storage read."""
    result = {}
    for path in sorted(bag.rglob("*")):
        if path.is_symlink():
            raise ValueError("bag contains symlink; readonly provenance requires regular contained files")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            result[str(path.relative_to(bag))] = digest.hexdigest()
    return result

def external_report_path(bag: Path, output: Path) -> None:
    if output == bag or output.is_relative_to(bag):
        raise ValueError("reports must be outside the original bag directory")
    if output.exists():
        raise ValueError("report directory already exists; choose a new output directory")

def validate_events(records: Iterable[Record], topic_types: dict[str, str],
                    session: dict[str, Any], context: dict[str, Any],
                    cfg: Config | None = None) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Validate decoded source events, source counts, and per-channel intervals.

    Never fills a missing boundary, infers sensor sequence from Header, or
    turns a publisher call into a measured plant action.
    """
    cfg = cfg or Config()
    cfg.validate()
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def issue(code: str, message: str, *, scope: str = "source", warning: bool = False, **detail: Any) -> None:
        (warnings if warning else failures).append({"code": code, "message": message, "scope": scope, **detail})

    roles = {topic: role for role, topic in cfg.topics.items()}
    actual = Counter()
    decoded = Counter()
    streams: dict[str, list[Record]] = defaultdict(list)
    last_bag: dict[str, int] = {}
    for index, record in enumerate(records):
        actual[record.topic] += 1
        role = roles.get(record.topic)
        if not integer(record.bag_ns):
            issue("invalid_bag_timestamp", "bag timestamp must be nonnegative integer ns", scope="recording", index=index)
        elif record.topic in last_bag and record.bag_ns < last_bag[record.topic]:
            issue("bag_time_regression", "per-topic bag order regressed", scope="recording", topic=record.topic)
        last_bag[record.topic] = record.bag_ns
        if role is None:
            continue
        if "__decode_error__" in record.payload or not finite_tree(record.payload):
            issue("invalid_payload", "decode error or nonfinite data", role=role, index=index)
            continue
        decoded[record.topic] += 1
        streams[role].append(record)

    for role, topic in cfg.topics.items():
        if topic_types.get(topic) != TOPIC_TYPES[role]:
            issue("missing_or_wrong_topic_type", "required role has missing/wrong type", scope="recording", role=role,
                  expected=TOPIC_TYPES[role], actual=topic_types.get(topic))
        if not actual[topic]:
            issue("empty_required_topic", "required topic has no records", scope="recording", role=role)
    if cfg.expected_counts is not None:
        for topic in set(actual) | set(cfg.expected_counts):
            if actual[topic] != cfg.expected_counts.get(topic, 0):
                issue("metadata_actual_count_mismatch", "metadata disagrees with independent actual scan", scope="recording",
                      topic=topic, metadata_count=cfg.expected_counts.get(topic, 0), actual_count=actual[topic])

    identities: dict[str, list[int]] = {}
    for role in ("state", "applied", "cycle"):
        sequences = []
        previous = None
        previous_epoch = None
        previous_sim = None
        for record in streams[role]:
            p = record.payload
            for key in ("run_id", "producer_instance_id", "baseline_id", "config_hash", "steady_clock_domain"):
                value = p.get(key)
                if not isinstance(value, str) or not value:
                    issue("missing_identity", "required source identity missing", role=role, field=key)
                expected = context.get(key)
                if expected is not None and value != expected:
                    issue("source_identity_mismatch", "message differs from frozen run context", role=role, field=key)
            if p.get("schema_version") != "p0-contract-v1":
                issue("wrong_schema", "research message schema differs", role=role)
            seq = p.get("sequence")
            if not integer(seq, 1):
                issue("invalid_sequence", "source sequence must be positive integer", role=role)
                continue
            sequences.append(seq)
            if previous is not None and seq != previous + 1:
                issue("sequence_gap_duplicate_or_regression", "source events are not strictly contiguous in recorded order",
                      scope="recording", role=role, before=previous, after=seq)
            previous = seq
            for key in ("clock_epoch", "clock_receive_steady_ns", "clock_age_ns"):
                if not integer(p.get(key)):
                    issue("invalid_time_field", "time/epoch requires nonnegative integer ns", role=role, field=key)
            if not isinstance(p.get("sim_time_ns"), int) or isinstance(p.get("sim_time_ns"), bool):
                issue("invalid_sim_time", "simulation time requires integer ns", role=role)
            if p.get("clock_status") not in ("not_received", "observed", "paused", "reset", "jump"):
                issue("unknown_clock_status", "explicit clock observation status required", role=role)
            if p.get("clock_status") == "not_received" and (p.get("sim_time_ns") != 0 or p.get("clock_receive_steady_ns") != 0):
                issue("missing_clock_has_fabricated_time", "missing clock must not carry invented observed simulation time", role=role)
            epoch, sim = p.get("clock_epoch"), p.get("sim_time_ns")
            if integer(epoch) and isinstance(sim, int):
                if previous_epoch is not None and (epoch < previous_epoch or (epoch == previous_epoch and sim < previous_sim)):
                    issue("unsegmented_clock_regression", "clock regression must create a new monotonically increasing epoch", role=role)
                previous_epoch, previous_sim = epoch, sim
            age_limit = context.get("max_clock_receive_age_ns")
            if integer(age_limit) and integer(p.get("clock_age_ns")) and p["clock_age_ns"] > age_limit:
                issue("stale_clock_observation", "source event clock observation exceeds declared clock age", role=role)
        identities[role] = sequences

    for key in ("run_id", "producer_instance_id", "baseline_id", "config_hash", "steady_clock_domain"):
        if not isinstance(context.get(key), str) or not context.get(key):
            issue("missing_run_context_identity", "run context identity/steady domain required", field=key)
    config_hash = context.get("config_hash")
    if not isinstance(config_hash,str) or len(config_hash)!=64 or any(c not in "0123456789abcdef" for c in config_hash):
        issue("invalid_config_hash", "effective configuration identity must be lowercase SHA256")
    if context.get("steady_clock_domain") in ("unknown", "", None):
        issue("steady_domain_unknown", "unknown steady clock domain cannot support timing subtraction")
    if context.get("frame_contract_verified") is not True:
        issue("frame_contract_unverified", "pose/twist frame semantics need explicit producer/bridge verification")
    if not context.get("expected_pose_frame") or not context.get("expected_child_frame"):
        issue("expected_frame_missing", "run context must bind verified pose and child/body frames")
    if context.get("twist_frame") != "body":
        issue("twist_frame_unverified", "P0 snapshot contract expects verified body-frame twist")
    publishers = context.get("physical_publisher_counts", {})
    for role in ("left", "right"):
        count = publishers.get(role, publishers.get(cfg.topics[role]))
        if count != 1:
            issue("physical_publisher_count", "a unique physical publisher is required", role=role, count=count)

    if not isinstance(session, dict):
        session = {}
    if session.get("schema_version") != "p0-contract-v1":
        issue("wrong_session_schema", "source summary must declare P0 contract schema",scope="recording")
    for key in ("run_id", "producer_instance_id", "baseline_id", "config_hash", "steady_clock_domain"):
        if session.get(key) != context.get(key):
            issue("session_identity_mismatch", "source session identity differs/missing", scope="recording", field=key)
    if session.get("normal_end") is not True or session.get("flushed") is not True:
        issue("session_end_unknown_or_unflushed", "normal source end and queue flush are required for complete recording", scope="recording")
    if session.get("queue_dropped_total") != 0:
        issue("logger_queue_overflow", "source queue overflow or unknown drop count", scope="recording",
              dropped=session.get("queue_dropped_total"))
    if session.get("interrupted_cycle_sequence") != 0:
        issue("interrupted_cycle_at_session_end", "source run stopped with an uncompleted synchronous invocation",scope="recording",
              interrupted_cycle_sequence=session.get("interrupted_cycle_sequence"))
    capture_start,capture_end=session.get("start_steady_ns"),session.get("end_steady_ns")
    if not integer(capture_start,1) or not integer(capture_end,1) or capture_end<capture_start:
        issue("session_capture_boundary_unknown", "source start/end must be ordered local steady ns",scope="recording")
    else:
        for role,key in (("state","freeze_steady_ns"),("applied","left_publish_start_steady_ns"),("cycle","timer_entry_steady_ns")):
            for record in streams[role]:
                boundary=record.payload.get(key)
                if not integer(boundary) or not capture_start<=boundary<=capture_end:
                    issue("source_event_outside_capture", "source event local timestamp lies outside its source capture window",scope="recording",role=role)
    source_counts = session.get("streams", {})
    if (not integer(session.get("cycle_invocations_started"))
        or session.get("cycle_invocations_started") != source_counts.get("cycle",{}).get("generated")):
        issue("started_completed_cycle_count_mismatch", "armed timer entries must match generated CycleTiming events at normal end",scope="recording",
              started=session.get("cycle_invocations_started"),generated=source_counts.get("cycle",{}).get("generated"))
    for role in ("state", "applied", "cycle"):
        declared = source_counts.get(role, {})
        seqs = identities[role]
        for field in ("generated", "emitted", "dropped", "first_sequence", "last_sequence"):
            if not integer(declared.get(field)):
                issue("source_summary_count_missing", "source stream counter/boundary missing", scope="recording", role=role, field=field)
        expected = len(streams[role])
        if declared.get("generated") != expected or declared.get("emitted") != expected or declared.get("dropped") != 0:
            issue("source_recorded_count_mismatch", "actual research count differs from source generated/emitted/dropped",
                  scope="recording", role=role, recorded=expected, declared=declared)
        if seqs and (declared.get("first_sequence") != seqs[0] or declared.get("last_sequence") != seqs[-1]):
            issue("source_boundary_mismatch", "prefix/suffix research events missing or incorrect", scope="recording", role=role)

    clock_values = set()
    for record in streams["clock"]:
        try:
            clock_values.add(stamp_ns(record.payload["clock"]))
        except (KeyError, TypeError, ValueError):
            issue("invalid_raw_clock", "raw /clock timestamp must be integer sec/ns")
    for role in ("state", "applied", "cycle"):
        for record in streams[role]:
            p = record.payload
            if p.get("clock_status") != "not_received" and p.get("sim_time_ns") not in clock_values:
                issue("source_clock_sample_not_recorded", "event's explicit latest clock observation is absent from raw bag", scope="recording", role=role)

    odoms: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    imus: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for role, target in (("odom", odoms), ("imu", imus)):
        for record in streams[role]:
            p = record.payload
            try:
                header = p["header"]
                stamp = stamp_ns(header["stamp"])
                key = (stamp, header["frame_id"], p["child_frame_id"]) if role == "odom" else stamp
                target[key].append(p)
            except (KeyError, TypeError, ValueError):
                issue("invalid_raw_sensor_header", "raw source timestamp/frame missing or invalid", role=role)

    state_by_odom: dict[int, dict[str, Any]] = {}
    state_by_sequence: dict[int, dict[str, Any]] = {}
    for record in streams["state"]:
        p = record.payload
        seq = p.get("received_odom_sequence")
        if not integer(seq, 1) or seq in state_by_odom:
            issue("snapshot_odom_identity", "atomic snapshot must identify a unique received odom", sequence=p.get("sequence"))
        state_by_odom[seq] = p
        state_by_sequence[p.get("sequence")] = p
        if p.get("source_topic") != cfg.topics["odom"]:
            issue("snapshot_source_topic", "snapshot source must be configured ground-truth odom")
        if p.get("valid") is not True:
            issue("invalid_snapshot", "snapshot is explicitly invalid; retain raw data but do not approve state contract",
                  reason=p.get("quality_reason"))
        if not vector(p.get("state_6"), 6):
            issue("invalid_snapshot_state", "six finite state components required")
            continue
        if p.get("frame_id") != context.get("expected_pose_frame") or p.get("child_frame_id") != context.get("expected_child_frame"):
            issue("snapshot_frame_mismatch", "snapshot frame differs from verified producer frame")
        recv, frozen = p.get("receive_steady_ns"), p.get("freeze_steady_ns")
        if not integer(recv) or not integer(frozen) or frozen < recv:
            issue("snapshot_freeze_time", "snapshot freeze must follow receive on same producer steady clock")
        lag_limit = context.get("max_source_clock_lag_ns")
        future_limit = context.get("max_source_clock_future_ns")
        if integer(lag_limit) and integer(future_limit) and isinstance(p.get("odom_stamp_ns"), int):
            lag = p["sim_time_ns"] - p["odom_stamp_ns"]
            if lag > lag_limit or lag < -future_limit:
                issue("source_stamp_outside_declared_clock_window", "fresh callback does not make old/future sensor stamp valid", lag_ns=lag)
        matching = odoms.get((p.get("odom_stamp_ns"), p.get("frame_id"), p.get("child_frame_id")), [])
        if not matching:
            issue("snapshot_raw_source_missing", "atomic snapshot has no recorded raw odom with original stamp/frame", scope="recording")
            continue
        expected_states = []
        for odom in matching:
            try:
                pose, twist = odom["pose"]["pose"], odom["twist"]["twist"]
                q = pose["orientation"]
                qv = [q[key] for key in ("x", "y", "z", "w")]
                norm = sum(x*x for x in qv)
                if norm <= 1e-12:
                    issue("degenerate_quaternion", "zero/degenerate raw quaternion cannot define yaw")
                    continue
                # Same body-frame twist, with no yaw rotation applied again.
                yaw = math.atan2(2*(q["w"]*q["z"]+q["x"]*q["y"]), 1-2*(q["y"]**2+q["z"]**2))
                expected_states.append([pose["position"]["x"], pose["position"]["y"], yaw,
                                        twist["linear"]["x"], twist["linear"]["y"], twist["angular"]["z"]])
            except (KeyError, TypeError):
                issue("raw_odom_fields_missing", "raw odom pose/twist missing")
        if expected_states and not any(all(abs(a-b) <= 1e-5 for a, b in zip(p["state_6"], candidate)) for candidate in expected_states):
            issue("snapshot_not_atomic_odom", "snapshot differs from same-odom pose/yaw/body twist")

    actions = [record.payload for record in streams["applied"]]
    applied_by_sequence = {p.get("sequence"): p for p in actions}
    for p in actions:
        if p.get("event_semantics") != "publisher_command":
            issue("wrong_event_semantics", "AppliedControl must remain publisher_command")
        for key in ("plant_acceptance_observed", "force_measured", "execution_atomicity_proven"):
            if p.get(key) is not False:
                issue("unsupported_physical_claim", "P0 cannot assert physical execution evidence", field=key)
        if not isinstance(p.get("control_source"), str) or not p.get("control_source"):
            issue("control_source_missing", "original control branch/source must be recorded")
        if not vector(p.get("final_n"), 2):
            issue("invalid_final_command", "finite joint physical-N command required")
            continue
        if any(abs(n) > cfg.thrust_limit_n + cfg.tolerance_n for n in p["final_n"]):
            issue("thrust_out_of_range", "publisher command exceeds declared physical-N envelope")
        for channel in ("left", "right"):
            success = p.get(channel + "_publish_success")
            start, end = p.get(channel + "_publish_start_steady_ns"), p.get(channel + "_publish_end_steady_ns")
            if not isinstance(success, bool):
                issue("publication_success_unknown", "each channel must declare call result", channel=channel)
            if not integer(start) or not integer(end) or (success and (start == 0 or end < start)):
                issue("invalid_publish_call_times", "successful publish needs ordered steady call boundaries", channel=channel)
            channel_epoch, channel_age = p.get(channel+"_clock_epoch"),p.get(channel+"_clock_age_ns")
            if not integer(channel_epoch) or not integer(channel_age):
                issue("channel_clock_identity_missing", "each publish call must retain clock epoch and observation age",channel=channel)
            elif channel_epoch != p.get("clock_epoch"):
                issue("channel_clock_epoch_mismatch", "clock reset between channel calls prevents a joint time boundary",scope="timing",channel=channel)
        if not (p.get("left_publish_success") and p.get("right_publish_success")):
            issue("partial_or_failed_publication", "partial/failed physical publication is explicit and invalidates joint intervals")
        if p.get("requested_known") is True:
            if not vector(p.get("requested_n"), 2) or not all(finite(p.get(k)) for k in ("map_scale", "lower_n", "upper_n")):
                issue("invalid_requested_mapping", "known request needs finite scale/clamp parameters")
            elif p["lower_n"] > p["upper_n"]:
                issue("invalid_mapping_bounds", "map lower bound exceeds upper")
            else:
                mapped = [max(p["lower_n"], min(p["upper_n"], x*p["map_scale"])) for x in p["requested_n"]]
                if any(abs(a-b) > cfg.tolerance_n for a, b in zip(mapped, p["final_n"])):
                    issue("command_mapping_mismatch", "final N differs from original declared scale/clamp")
        elif p.get("requested_known") is not False:
            issue("requested_validity_missing", "unknown request must carry explicit false validity")
        if p.get("previous_anchor_known") is True and not vector(p.get("previous_final_n"), 2):
            issue("invalid_previous_anchor", "known previous published anchor requires finite joint N")

    physical_matching: dict[str, Any] = {}
    window_ns = context.get("physical_match_window_ns")
    if not integer(window_ns, 1) or window_ns >= cfg.nominal_dt_s * NS / 2:
        issue("physical_match_window_unknown_or_excessive", "declare positive strict bag receive-time window below half nominal period")
        window_ns = 0
    for channel, component in (("left", 0), ("right", 1)):
        published = [r for r in streams["applied"] if r.payload.get(channel + "_publish_success") is True and vector(r.payload.get("final_n"), 2)]
        raw = streams[channel]
        raw_times = [r.bag_ns for r in raw]
        used: set[int] = set()
        last_index = -1
        offsets = []
        for applied in published:
            event = applied.payload
            candidates = list(range(bisect_right(raw_times, applied.bag_ns-window_ns), bisect_left(raw_times, applied.bag_ns+window_ns)))
            if len(candidates) != 1:
                issue("physical_match_missing_or_ambiguous", "unique strict temporal candidate required; values cannot resolve ambiguity",
                      scope="recording", channel=channel, sequence=event.get("sequence"), candidate_count=len(candidates))
                continue
            index = candidates[0]
            if index in used or index <= last_index:
                issue("physical_record_reuse_or_regression", "raw publication cannot be reused/out of order", scope="recording", channel=channel)
                continue
            used.add(index)
            last_index = index
            record = raw[index]
            offsets.append(abs(record.bag_ns-applied.bag_ns)/1e6)
            value = record.payload.get("data")
            if not finite(value) or abs(value-event["final_n"][component]) > cfg.tolerance_n:
                issue("physical_command_value_mismatch", "ordered physical Float64 differs from joint publisher event",
                      scope="recording", channel=channel, position=index, sequence=event.get("sequence"))
        interior_unmatched = []
        outside_count = len(raw)
        if used:
            start, end = min(used), max(used)
            interior_unmatched = [i for i in range(start,end+1) if i not in used]
            outside_count = start + len(raw)-end-1
        if interior_unmatched:
            issue("physical_interior_records_unmatched", "unmatched physical records inside armed matched span", scope="recording",
                  channel=channel, record_indices=interior_unmatched)
        physical_matching[channel] = {"actual_raw_count":len(raw), "source_successful_calls":len(published),
                                      "matched_count":len(used), "outside_armed_matched_span_count":outside_count,
                                      "interior_unmatched_count":len(interior_unmatched),
                                      "max_bag_receive_offset_ms":max(offsets) if offsets else None,
                                      "strict_match_window_ns":window_ns,
                                      "outside_span_claim":"retained raw outputs outside source capture; no completeness claim for these"}

    solve_ms, local_ms, backend_ms = [], [], []
    deadline_misses = 0
    for record in streams["cycle"]:
        p = record.payload
        if p.get("solve_invoked") is False:
            start, end = p.get("timer_entry_steady_ns"), p.get("publish_end_steady_ns")
            if not integer(start) or not integer(end) or (end and end < start):
                issue("nonsolve_cycle_time_order", "non-solve timer has ordered actual entry/publication boundary")
            elif end:
                local_ms.append((end-start)/1e6)
            if p.get("applied_sequence", 0):
                action = applied_by_sequence.get(p["applied_sequence"])
                if action is None or action.get("cycle_sequence") != p.get("sequence"):
                    issue("cycle_action_link_missing", "non-solve publication must also link actual cycle", scope="recording")
            continue
        if p.get("solve_invoked") is not True:
            issue("solve_invoked_unknown", "cycle must explicitly declare whether backend was invoked")
        keys = ("timer_entry_steady_ns", "state_copy_steady_ns", "reference_ready_steady_ns",
                "solve_start_steady_ns", "solve_end_steady_ns", "publish_end_steady_ns")
        times = [p.get(key) for key in keys]
        if not all(integer(value) for value in times) or times != sorted(times):
            issue("cycle_time_order", "actual invocation times require ordered nonnegative steady ns")
        else:
            local_ms.append((times[-1]-times[0])/1e6)
            if p.get("solve_invoked") is True:
                solve_ms.append((times[-2]-times[-3])/1e6)
        if not vector(p.get("controller_state_6"), 6):
            issue("invalid_controller_state", "actual copied solve input needs six finite components")
            continue
        odom_seq, imu_seq = p.get("received_odom_sequence"), p.get("received_imu_sequence")
        snapshot = state_by_odom.get(odom_seq)
        if snapshot is None:
            # The first armed timer can legitimately consume the last odom
            # before state logging was armed. Keep its raw sensor evidence,
            # rather than inventing a prearm StateSnapshot or cutting it out.
            first_received = min((s for s in state_by_odom if integer(s,1)), default=0)
            matching = odoms.get((p.get("odom_stamp_ns"), context.get("expected_pose_frame"), context.get("expected_child_frame")), [])
            if integer(odom_seq,1) and first_received and odom_seq < first_received and matching:
                for raw_odom in matching:
                    try:
                        pose, twist = raw_odom["pose"]["pose"],raw_odom["twist"]["twist"]
                        q=pose["orientation"]
                        yaw=math.atan2(2*(q["w"]*q["z"]+q["x"]*q["y"]),1-2*(q["y"]**2+q["z"]**2))
                        candidate=[pose["position"]["x"],pose["position"]["y"],yaw,twist["linear"]["x"],twist["linear"]["y"],twist["angular"]["z"]]
                        if all(abs(a-b)<=1e-5 for a,b in zip(candidate[:5],p["controller_state_6"][:5])):
                            snapshot={"odom_stamp_ns":p["odom_stamp_ns"],"state_6":candidate}
                            break
                    except (KeyError,TypeError):
                        continue
                if snapshot:
                    issue("controller_snapshot_precedes_armed_window", "prearm source is bound to raw odom; no synthetic snapshot added", warning=True,
                          received_odom_sequence=odom_seq)
            if snapshot is None:
                issue("controller_odom_source_missing", "actual controller input has no associated same-odom evidence", scope="recording")
        if snapshot is not None:
            if p.get("odom_stamp_ns") != snapshot.get("odom_stamp_ns"):
                issue("controller_odom_stamp_mismatch", "controller must retain pre-solve original odom stamp")
            if vector(snapshot.get("state_6"), 6) and any(abs(a-b)>1e-5 for a,b in zip(p["controller_state_6"][:5],snapshot["state_6"][:5])):
                issue("controller_input_not_frozen", "controller xy/yaw/u/v differs from declared pre-solve odom identity")
        if p.get("state_kind") == "controller_mixed":
            if not integer(imu_seq, 1):
                issue("controller_mixed_kind_missing", "IMU-associated r needs a received IMU identity")
            matching = imus.get(p.get("imu_stamp_ns"), [])
            if not matching:
                issue("controller_imu_source_missing", "mixed controller r lacks recorded raw IMU original stamp", scope="recording")
            else:
                values = [m.get("angular_velocity", {}).get("z") for m in matching]
                if not any(finite(r) and abs(p["controller_state_6"][5]-r)<=1e-5 for r in values):
                    issue("controller_mixed_r_mismatch", "mixed input r differs from linked pre-solve IMU")
        elif p.get("state_kind") != "odom_atomic":
            issue("controller_atomic_kind_missing", "without IMU overwrite input must identify odom_atomic")
        elif snapshot and vector(snapshot.get("state_6"),6) and abs(p["controller_state_6"][5]-snapshot["state_6"][5])>1e-5:
            issue("controller_atomic_r_mismatch", "odom-atomic r differs from linked odom")
        if not finite(p.get("backend_time_ms")) or p["backend_time_ms"] < 0 or not finite(p.get("budget_ms")) or p["budget_ms"] <= 0:
            issue("invalid_backend_budget", "backend time and real deadline budget must be finite")
        else:
            backend_ms.append(p["backend_time_ms"])
            if p.get("deadline_miss") is True:
                deadline_misses += 1
                if p.get("success") is True:
                    issue("late_solution_accepted", "deadline-miss cycle must not be accepted successful candidate")
        action = applied_by_sequence.get(p.get("applied_sequence"))
        if action is None or action.get("cycle_sequence") != p.get("sequence"):
            issue("cycle_action_link_missing", "cycle/action sequence must mutually identify actual publication", scope="recording")

    ledger: list[dict[str, Any]] = []
    intervals_s, left_right_ms = [], []
    closed = 0
    for index, event in enumerate(actions):
        following = actions[index+1] if index+1 < len(actions) else None
        row = {"run_id": event.get("run_id"), "producer_instance_id": event.get("producer_instance_id"),
               "clock_epoch": event.get("clock_epoch"), "sequence": event.get("sequence"),
               "event_semantics": "publisher_command", "final_n": event.get("final_n"),
               "next_sequence": following.get("sequence") if following else None,
               "status": "end_unknown", "reason": "no next event", "left": None, "right": None,
               "plant_interval_proven": False}
        if integer(event.get("left_publish_start_steady_ns")) and integer(event.get("right_publish_start_steady_ns")):
            left_right_ms.append(abs(event["right_publish_start_steady_ns"]-event["left_publish_start_steady_ns"])/1e6)
        if following:
            identity_keys = ("run_id", "producer_instance_id", "clock_epoch", "steady_clock_domain")
            valid = (all(event.get(k)==following.get(k) for k in identity_keys)
                     and integer(event.get("sequence"),1) and following.get("sequence")==event["sequence"]+1
                     and all(p.get(c+"_publish_success") is True and p.get(c+"_clock_epoch")==p.get("clock_epoch")
                             for p in (event,following) for c in ("left","right")))
            row["status"], row["reason"] = "invalid", "identity/epoch/sequence or partial-publication boundary"
            if valid:
                durations = []
                for channel in ("left","right"):
                    start, end = event.get(channel+"_publish_start_steady_ns"),following.get(channel+"_publish_start_steady_ns")
                    sim_start, sim_end = event.get(channel+"_sim_time_ns"),following.get(channel+"_sim_time_ns")
                    if not integer(start) or not integer(end) or end<=start or not isinstance(sim_start,int) or not isinstance(sim_end,int) or sim_end<=sim_start:
                        valid = False
                    row[channel] = {"start_call_steady_ns": start, "end_call_steady_ns": end,
                                    "start_call_window_steady_ns": [start,event.get(channel+"_publish_end_steady_ns")],
                                    "end_call_window_steady_ns": [end,following.get(channel+"_publish_end_steady_ns")],
                                    "start_observed_sim_ns": sim_start,"end_observed_sim_ns": sim_end,
                                    "sim_duration_s": (sim_end-sim_start)/NS if isinstance(sim_start,int) and isinstance(sim_end,int) else None,
                                    "steady_duration_s": (end-start)/NS if integer(start) and integer(end) else None}
                    if isinstance(sim_start,int) and isinstance(sim_end,int):
                        durations.append((sim_end-sim_start)/NS)
                if valid:
                    row["status"],row["reason"] = "closed_publisher_interval", "two contiguous successful calls in same clock segment"
                    closed += 1
                    intervals_s.extend(durations)
                    if max(durations)>1.5*cfg.nominal_dt_s:
                        issue("long_publisher_hold", "observed command interval exceeds nominal period; synchronous hold remains observable",
                              warning=True, sequence=event["sequence"],duration_s=max(durations))
                    if vector(event.get("final_n"),2) and vector(following.get("final_n"),2):
                        for component,channel in enumerate(("left","right")):
                            dt = row[channel]["sim_duration_s"]
                            delta = abs(following["final_n"][component]-event["final_n"][component])
                            rate = delta/dt
                            if rate > cfg.rate_limit_n_s + cfg.tolerance_n:
                                issue("observed_rate_limit_exceeded", "real publisher spacing exposes rate exceedance; logging does not repair control",
                                      warning=True,sequence=event["sequence"],channel=channel,rate_n_s=rate,
                                      rate_time_domain="per-channel latest observed /clock",steady_rate_n_s=delta/row[channel]["steady_duration_s"])
                else:
                    row["reason"] = "unknown/nonprogressing clock or steady boundary"
        ledger.append(row)

    if any(row["status"]=="invalid" for row in ledger):
        issue("publisher_interval_boundaries_unknown", "one or more publisher intervals lack valid same-segment boundaries", scope="timing")

    source_valid = not any(f["scope"]=="source" for f in failures)
    complete = not any(f["scope"]=="recording" for f in failures)
    timing_available = bool(closed) and all(row["status"] == "closed_publisher_interval" for row in ledger[:-1])
    timing = {"schema":"p0-publisher-timing/1", "local_callback_to_publish_ms": distribution(local_ms),
              "complete_solve_ms": distribution(solve_ms),"backend_reported_ms":distribution(backend_ms),
              "per_channel_observed_sim_interval_s":distribution(intervals_s),"left_right_call_start_difference_ms":distribution(left_right_ms),
              "deadline_miss_count":deadline_misses,"joint_events":len(actions),"closed_intervals":closed,
              "possible_intervals":max(0,len(actions)-1),"closed_interval_fraction":closed/max(1,len(actions)-1),
              "terminal_end_unknown_count":sum(row["status"]=="end_unknown" for row in ledger),
              "invalid_interval_count":sum(row["status"]=="invalid" for row in ledger),
              "nominal_dt_s":cfg.nominal_dt_s,"steady_domain":context.get("steady_clock_domain"),
              "is_sensor_to_actuator_end_to_end":False,"is_plant_hold_measurement":False}
    report = {"schema":"p0-publisher-contract-report/1", "passed":not failures,
              "exit_code":0 if not failures else 2,"source_event_contract_valid":source_valid,
              "recorded_stream_complete":complete,"published_command_timing_available":timing_available,
              "frozen_baseline_verified":context.get("frozen_baseline_verified") is True and source_valid,
              "frozen_baseline_verification_source":"external run_context; message identity agreement checked here",
              "plant_acceptance_observed":False,"force_measured":False,"execution_atomicity_proven":False,
              "exact_execution_timing_available":False,"gp_labels_ready":False,
              "source_received_sequences_prove_precallback_completeness":False,
              "actual_message_counts":dict(actual),"decoded_message_counts":dict(decoded),
              "metadata_message_counts":cfg.expected_counts,"source_stream_counts":source_counts,
              "physical_matching":physical_matching,
              "source_stream_loss_diagnostics":{
                  role:{"generated":source_counts.get(role,{}).get("generated"),
                        "emitted":source_counts.get(role,{}).get("emitted"),"recorded_decoded":len(streams[role]),
                        "source_to_recorded_missing_fraction":max(0,1-len(streams[role])/source_counts[role]["generated"])
                         if integer(source_counts.get(role,{}).get("generated"),1) else None}
                  for role in ("state","applied","cycle")},
              "run_id":context.get("run_id"),"producer_instance_id":context.get("producer_instance_id"),
              "baseline_id":context.get("baseline_id"),"topic_types":dict(topic_types),
              "failures":failures,"warnings":warnings,"limitations":LIMITATIONS}
    return report,timing,ledger

def read_bag(bag: Path, cfg: Config) -> tuple[list[Record], dict[str, str], dict[str, Any]]:
    """Select actual metadata storage; deserialize known topics without writing."""
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message

    with (bag / "metadata.yaml").open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    info = document["rosbag2_bagfile_information"]
    storage = info["storage_identifier"]
    if not isinstance(storage, str) or not storage:
        raise ValueError("metadata lacks storage_identifier")
    paths = info["relative_file_paths"]
    if not isinstance(paths, list) or not paths:
        raise ValueError("metadata lacks storage files")
    for name in paths:
        if not isinstance(name, str) or not name:
            raise ValueError("invalid storage filename")
        candidate = (bag / name).resolve()
        if not candidate.is_relative_to(bag) or not candidate.is_file():
            raise ValueError("storage file missing or outside bag")
    counts: dict[str, int] = {}
    types: dict[str, str] = {}
    for item in info["topics_with_message_count"]:
        topic = item["topic_metadata"]
        name = topic["name"]
        if name in counts:
            raise ValueError("duplicate metadata topic")
        counts[name] = item["message_count"]
        types[name] = topic["type"]
    cfg.expected_counts = counts
    cfg.validate()
    total = info["message_count"]
    if not integer(total) or total != sum(counts.values()):
        raise ValueError("metadata total differs from per-topic counts")
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
                rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"))
    actual_types = {entry.name: entry.type for entry in reader.get_all_topics_and_types()}
    if actual_types != types:
        raise ValueError("storage topic definitions differ from metadata")
    roles = {topic: role for role, topic in cfg.topics.items()}
    classes = {topic: get_message(TOPIC_TYPES[role]) for topic, role in roles.items()
               if actual_types.get(topic) == TOPIC_TYPES[role]}
    records = []
    while reader.has_next():
        topic, serialized, timestamp = reader.read_next()
        payload = {}
        if topic in classes:
            try:
                payload = dict(message_to_ordereddict(deserialize_message(serialized, classes[topic])))
            except Exception as exc:
                payload = {"__decode_error__": f"{type(exc).__name__}: {exc}"}
        records.append(Record(topic, int(timestamp), payload))
    return records, actual_types, {"bag": str(bag), "storage_id": storage,
                                   "storage_files": paths, "metadata_total_message_count": total,
                                   "recorder_time_domain": "see external run_context; not inferred from numeric timestamps"}

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--session-summary", type=Path, required=True)
    parser.add_argument("--run-context", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="new report directory outside original bag")
    parser.add_argument("--nominal-dt-s", type=float, default=.2)
    parser.add_argument("--thrust-limit-n", type=float, default=25.)
    parser.add_argument("--rate-limit-n-s", type=float, default=80.)
    parser.add_argument("--tolerance-n", type=float, default=1e-5)
    for role, topic in DEFAULT_TOPICS.items():
        parser.add_argument(f"--{role}-topic", default=topic)
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1
    bag = args.bag.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    try:
        external_report_path(bag, output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    cfg = Config(topics={role: getattr(args, f"{role}_topic") for role in DEFAULT_TOPICS},
                 nominal_dt_s=args.nominal_dt_s, thrust_limit_n=args.thrust_limit_n,
                 rate_limit_n_s=args.rate_limit_n_s, tolerance_n=args.tolerance_n)
    before = None
    try:
        cfg.validate()
        if not bag.is_dir():
            raise ValueError("bag must be an existing directory with metadata.yaml")
        before = hash_bag(bag)
        with args.session_summary.open(encoding="utf-8") as handle:
            session = json.load(handle)
        with args.run_context.open(encoding="utf-8") as handle:
            context = json.load(handle)
        records, types, reading = read_bag(bag, cfg)
        report, timing, ledger = validate_events(records, types, session, context, cfg)
        report["reading"] = reading
        after = hash_bag(bag)
        report["bag_hash_before"] = before
        report["bag_hash_after"] = after
        report["original_bag_unchanged"] = before == after
        if before != after:
            report["failures"].append({"code": "original_bag_changed", "message": "bag hashes changed during readonly validation"})
            report["passed"] = report["recorded_stream_complete"] = False
            report["exit_code"] = 2
        code = report["exit_code"]
    except Exception as exc:
        report = {"schema": "p0-publisher-contract-report/1", "passed": False, "exit_code": 1,
                  "configuration_or_read_error": f"{type(exc).__name__}: {exc}", "bag": str(bag),
                  "source_event_contract_valid": False, "recorded_stream_complete": False,
                  "published_command_timing_available": False, "frozen_baseline_verified": False,
                  "exact_execution_timing_available": False, "gp_labels_ready": False,
                  "plant_acceptance_observed": False, "force_measured": False,
                  "execution_atomicity_proven": False, "limitations": LIMITATIONS}
        if before is not None:
            try:
                after = hash_bag(bag)
                report.update(bag_hash_before=before, bag_hash_after=after, original_bag_unchanged=before == after)
            except (OSError,ValueError) as hash_error:
                report.update(bag_hash_before=before,bag_hash_after_error=str(hash_error),original_bag_unchanged=False)
        timing, ledger, code = {}, [], 1
    try:
        output.mkdir(parents=True, exist_ok=False)
        for filename, value in (("contract_report.json", report), ("timing_report.json", timing)):
            with (output / filename).open("w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        with (output / "interval_ledger.jsonl").open("w", encoding="utf-8") as handle:
            for row in ledger:
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    except (OSError, ValueError) as exc:
        print(f"Cannot write external reports: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"passed": report["passed"], "exit_code": code,
                      "output_dir": str(output), "failure_count": len(report.get("failures", [])),
                      "error": report.get("configuration_or_read_error")}, ensure_ascii=False))
    return code

if __name__ == "__main__":
    sys.exit(main())

