#!/usr/bin/env python3
"""Read-only P1 source/typed bag checker. No P0 checker or raw bag is modified.

The pure validate_decoded entry point supports deterministic negative fixtures.
ROS dependencies are imported only when independently scanning an actual bag.
Diagnostic agreement is distinct from a qualified normal physical contract.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

TOPICS = {
    "/p1/solve_job": "usv_research_interfaces/msg/SolveJob",
    "/p1/solve_candidate": "usv_research_interfaces/msg/SolveCandidate",
    "/p1/execution_decision": "usv_research_interfaces/msg/ExecutionDecision",
    "/p1/worker_capability": "usv_research_interfaces/msg/WorkerCapability",
}
JOB_ALIASES = {"schema_version": "schema", "tick_origin_steady_ns": "tick_origin_ns",
               "freeze_steady_ns": "freeze_ns", "deadline_steady_ns": "deadline_ns",
               "target_steady_ns": "target_ns", "horizon_steps": "N", "prediction_dt": "dt"}
JOB_FIELDS = ("schema_version run_id boot_id contract_hash nominal_hash worker_instance job_id "
              "target_tick task_generation model_generation config_generation schedule_generation clock_epoch "
              "tick_origin_steady_ns freeze_steady_ns deadline_steady_ns target_steady_ns target_sim_ns "
              "odom_stamp_ns imu_stamp_ns odom_receive_ns imu_receive_ns odom_sequence imu_sequence r_from_imu "
              "horizon_steps prediction_dt frozen_state target_state reference anchor_n anchor_sequence "
              "anchor_publish_ns anchor_known reset_warmstart frozen_clock_sim_ns frozen_clock_receive_ns "
              "assumed_rtf anchor_source anchor_producer anchor_run_id history_sim_ns history_channel history_n").split()
CANDIDATE_ALIASES = {"worker_receive_ns": "receive_ns", "x_prediction": "X", "u_prediction": "U"}
CANDIDATE_FIELDS = ("worker_instance worker_receive_ns solve_start_ns solve_end_ns solver_invoked success "
                    "prediction_available reason backend backend_ms first_control x_prediction u_prediction").split()
DECISION_ALIASES = {"schema_version": "schema", "clock_epoch": "epoch", "tick_planned_ns": "planned_ns",
                    "tick_start_ns": "start_ns", "candidate_ready_commit_ns": "ready_commit_ns",
                    "tick_end_ns": "end_ns", "candidate_accepted": "accepted"}
DECISION_FIELDS = ("schema_version run_id boot_id contract_hash worker_instance mode sequence tick job_id "
                   "task_generation model_generation config_generation schedule_generation clock_epoch "
                   "tick_planned_ns tick_start_ns cutoff_commit_ns candidate_ready_commit_ns "
                   "activation_commit_ns tick_end_ns skipped_ticks candidate_accepted diagnostic_only reason "
                   "control_source target_state activation_state state_error requested_n final_n publish_success "
                   "publish_start_ns publish_end_ns anchor_known anchor_sequence previous_n previous_publish_ns "
                   "odom_age_ns imu_age_ns clock_age_ns normal_contract_complete rho_available "
                   "plant_acceptance_observed previous_anchor_known publish_sim_ns publish_epoch "
                   "publish_clock_age_ns activation_clock_sim_ns activation_clock_receive_ns activation_rtf").split()

DECISION_V2_SOURCE_FIELDS = ("activation_odom_stamp_ns activation_odom_receive_ns activation_odom_sequence "
                             "activation_imu_stamp_ns activation_imu_receive_ns activation_imu_sequence "
                             "activation_r_from_imu").split()
DECISION_V2_FIELDS = DECISION_FIELDS + DECISION_V2_SOURCE_FIELDS
INT64_MAX = (1 << 63) - 1


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def integer(x: Any, minimum: int = 0) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= minimum


def vector(x: Any, n: int) -> bool:
    return isinstance(x, list) and len(x) == n and all(finite(v) for v in x)


def exact(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if finite(a) and finite(b):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def projection(obj: dict, fields: list[str], aliases: dict[str, str]) -> dict:
    return {field: obj[aliases.get(field, field)] for field in fields if aliases.get(field, field) in obj}


def job_projection(obj: dict, source: bool = False) -> dict:
    return projection(obj, JOB_FIELDS, JOB_ALIASES if source else {})


def distribution(values: list[float]) -> dict:
    v = sorted(x for x in values if finite(x))
    def q(p: float) -> float | None:
        if not v:
            return None
        t = (len(v) - 1) * p
        lo = int(t)
        return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (t - lo)
    return {"count": len(v), "p50": q(.5), "p95": q(.95), "p99": q(.99), "max": max(v) if v else None}


def read_json(path: Path) -> dict:
    def bad(value: str) -> None:
        raise ValueError(f"nonfinite JSON constant: {value}")
    obj = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=bad)
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return obj


def read_jsonl(path: Path) -> list[dict]:
    data = path.read_bytes()
    if not data or not data.endswith(b"\n"):
        raise ValueError(f"source is empty or last event is not newline-closed: {path}")
    records = []
    for i, line in enumerate(data.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank JSONL line {i}: {path}")
        def bad(value: str) -> None:
            raise ValueError(f"nonfinite JSON at line {i}: {value}")
        obj = json.loads(line, parse_constant=bad)
        if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
            raise ValueError(f"missing event type at line {i}: {path}")
        records.append(obj)
    return records


def plain(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)) or (hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes))):
        return [plain(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def read_bag(bag: Path) -> tuple[dict[str, list[dict]], dict]:
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message
    meta = yaml.safe_load((bag / "metadata.yaml").read_text(encoding="utf-8"))["rosbag2_bagfile_information"]
    storage = meta["storage_identifier"]
    if storage not in ("mcap", "sqlite3"):
        raise ValueError(f"unsupported actual storage: {storage}")
    expected = {}
    expected_types = {}
    for item in meta["topics_with_message_count"]:
        name = item["topic_metadata"]["name"]
        if name in expected:
            raise ValueError("duplicate metadata topic")
        expected[name] = int(item["message_count"])
        expected_types[name] = item["topic_metadata"]["type"]
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
                rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"))
    actual_types = {x.name: x.type for x in reader.get_all_topics_and_types()}
    if actual_types != expected_types:
        raise ValueError("storage types differ from metadata")
    for topic, typ in TOPICS.items():
        if actual_types.get(topic) != typ:
            raise ValueError(f"missing/wrong typed topic: {topic}")
    classes = {topic: get_message(typ) for topic, typ in TOPICS.items()}
    decoded = {topic: [] for topic in TOPICS}
    counts: Counter = Counter()
    while reader.has_next():
        topic, blob, timestamp = reader.read_next()
        counts[topic] += 1
        if topic in classes:
            obj = plain(dict(message_to_ordereddict(deserialize_message(blob, classes[topic]))))
            decoded[topic].append({"message": obj, "bag_receive_ns": int(timestamp)})
    if {k: counts[k] for k in expected} != expected or sum(counts.values()) != int(meta["message_count"]):
        raise ValueError("metadata counts disagree with independent actual storage scan")
    return decoded, {"storage": storage, "actual_topic_counts": dict(counts), "topic_types": actual_types,
                     "bag_time_semantics": "storage timestamp; never subtracted from CLOCK_MONOTONIC or sim"}


def validate_decoded(reg: list[dict], worker: list[dict], bag: dict[str, list[dict]],
                     contract: dict, context: dict, contract_sha: str) -> dict:
    issues: list[dict] = []
    def fail(code: str, scope: str = "logical", **detail: Any) -> None:
        issues.append({"code": code, "scope": scope, **detail})
    def require(condition: bool, code: str, scope: str = "logical", **detail: Any) -> None:
        if not condition:
            fail(code, scope, **detail)
    def events(items: list[dict], typ: str) -> list[dict]:
        return [e for e in items if e.get("type") == typ]
    def index(items: list[dict], key, label: str) -> dict:
        out = {}
        for obj in items:
            ident = key(obj)
            if ident in out:
                fail("duplicate_identity", "recording", stream=label, identity=ident)
            else:
                out[ident] = obj
        return out
    starts = events(reg, "startup")
    require(len(starts) == 1, "regulator_startup_count", "lifecycle", count=len(starts))
    start = starts[0] if starts else {}
    mode = start.get("mode")
    run = start.get("run_id")
    boot = start.get("boot")
    require(mode in ("no_output", "shadow", "execute"), "unknown_mode", "lifecycle")
    require(start.get("clock") == "CLOCK_MONOTONIC" and start.get("contract_hash") == contract_sha,
            "startup_clock_contract_identity", "recording")
    require(start.get("physical_publisher_endpoints") == (2 if mode == "execute" else 0), "mode_publisher_endpoints", "logical")
    for key, value in (("run_id", run), ("mode", mode), ("contract_hash", contract_sha), ("boot_id", boot)):
        require(context.get(key) == value, "context_identity_missing_or_mismatch", "lifecycle", field=key)
    for issue in context.get("_binding_issues", []):
        fail(issue["code"], "lifecycle", **{k: v for k, v in issue.items() if k != "code"})
    if "_regulator_owned_pid" in context:
        require(start.get("pid") == context["_regulator_owned_pid"], "regulator_owned_pid", "lifecycle")
    graph = context.get("runner_summary_facts", {})
    if mode == "no_output":
        require(graph.get("graph_no_physical_publishers") is True,
                "runner_graph_zero_physical_endpoints_unknown", "lifecycle")
    elif mode in ("shadow", "execute"):
        expected_owner = "mpc_controller_node" if mode == "shadow" else "p1_regulator"
        require(graph.get("graph_sole_physical_owner_verified") is True
                and graph.get("graph_physical_owner_node") == expected_owner
                and exact(graph.get("graph_physical_publishers_per_channel"), {"left": 1, "right": 1}),
                "runner_graph_sole_physical_owner_unknown_or_wrong", "lifecycle")
        if mode == "shadow":
            require(graph.get("graph_new_physical_publishers_zero") is True,
                    "runner_graph_new_physical_publishers_unknown_or_nonzero", "lifecycle")
    verified_instance = context.get("_worker_verified_instance")
    verified_pid = context.get("_worker_owned_pid")
    require(isinstance(verified_instance, str) and bool(verified_instance) and integer(verified_pid, 1),
            "owned_worker_capability_binding_unknown", "lifecycle")
    raw_complete = None
    raw_comparison = {}
    fixture = context.get("_fixture_summary")
    actual_raw = context.get("_actual_topic_counts", {})
    if fixture is not None or mode == "no_output":
        raw_before = len(issues)
        require(isinstance(fixture, dict), "fixture_summary_missing", "raw_recording")
        if isinstance(fixture, dict):
            require(fixture.get("type") == "fixture_summary" and fixture.get("schema") == "p1-synthetic-fixture-v1"
                    and fixture.get("contract_sha256") == contract_sha and fixture.get("boot_id") == boot
                    and integer(context.get("_fixture_owned_pid"), 1)
                    and fixture.get("pid") == context.get("_fixture_owned_pid")
                    and fixture.get("error") in (None, "") and fixture.get("physical_endpoints") == 0
                    and fixture.get("actual_plant") is False and fixture.get("publisher_side_counts_only") is True,
                    "fixture_identity_or_completion_unverified", "raw_recording")
            topics = {**contract.get("input_topics", {}), "clock": "/clock"}
            require(len(set(topics.values())) == 5 and set(topics) == {"clock", "odom", "imu", "path", "profile"},
                    "fixture_raw_topic_scope_unknown", "raw_recording")
            for name in ("clock", "odom", "imu", "path", "profile"):
                topic = topics.get(name)
                published = fixture.get("counts", {}).get(name)
                recorded = actual_raw.get(topic)
                raw_comparison[name] = {"topic": topic, "fixture_published": published, "actual_bag_count": recorded}
                require(integer(published, 1) and integer(recorded) and published == recorded,
                        "fixture_raw_publisher_bag_count_mismatch_or_unknown", "raw_recording", input=name,
                        fixture_published=published, actual_bag_count=recorded)
        raw_complete = not any(i["scope"] == "raw_recording" for i in issues[raw_before:])
    require(contract.get("clock") == "CLOCK_MONOTONIC" and contract.get("N") == 20 and contract.get("dt") == .2
            and contract.get("T_ns") == 200000000 and contract.get("deadline_ns") == 150000000,
            "unsupported_contract", "logical")
    expected_decision_schema = contract.get("decision_schema_version") or (
        "p1-execution-decision-v2" if contract.get("schema") == "p1-execution-contract-v2" or any(k in contract for k in
        ("odom_sim_lag_ns", "imu_sim_lag_ns", "source_future_slack_ns")) else "p1-execution-decision-v1")
    require(expected_decision_schema in ("p1-execution-decision-v1", "p1-execution-decision-v2"),
            "unsupported_decision_schema_contract")
    v2_contract = expected_decision_schema == "p1-execution-decision-v2"
    decision_fields = DECISION_V2_FIELDS if v2_contract else DECISION_FIELDS
    v2_metadata_valid = False
    if v2_contract:
        v2_metadata_valid = (contract.get("schema") == "p1-execution-contract-v2"
                and contract.get("diagnostic_contract_revision") == 2
                and all(integer(contract.get(k), 1) for k in
                    ("odom_sim_lag_ns", "imu_sim_lag_ns", "mixed_skew_ns", "recording_ready_timeout_ns"))
                and integer(contract.get("source_future_slack_ns"))
                and all(isinstance(contract.get(k), str) and 0 < len(contract[k].encode("utf-8")) <= 128 for k in
                        ("expected_pose_frame", "expected_child_frame", "expected_imu_frame")))
        require(v2_metadata_valid, "v2_source_contract_limits_or_frame_missing")
    source_admissions = {
        name: index(events(reg, name + "_admission"), lambda e: e.get("sequence"), name + "_admission")
        for name in ("odom", "imu")}
    source_positions = {id(e): i for i, e in enumerate(reg)}
    qualified = contract.get("execute_qualified") is True and contract.get("parameters_are_diagnostic_only") is False
    require(mode != "execute" or qualified, "unqualified_execute", "logical")
    srcjobs = index(events(reg, "job"), lambda e: e.get("job", {}).get("job_id"), "source_jobs")
    srccands = index(events(worker, "candidate"), lambda e: e.get("job", {}).get("job_id"), "source_candidates")
    srcdec = index(events(reg, "decision"), lambda e: e.get("sequence"), "source_decisions")
    bj = index([r["message"] for r in bag.get("/p1/solve_job", [])], lambda e: e.get("job_id"), "bag_jobs")
    bc = index([r["message"] for r in bag.get("/p1/solve_candidate", [])], lambda e: e.get("job", {}).get("job_id"), "bag_candidates")
    bd = index([r["message"] for r in bag.get("/p1/execution_decision", [])], lambda e: e.get("sequence"), "bag_decisions")
    streams = {}
    for label, src, recorded, fields, aliases in (("jobs", srcjobs, bj, JOB_FIELDS, JOB_ALIASES),
          ("candidates", srccands, bc, CANDIDATE_FIELDS, CANDIDATE_ALIASES),
          ("decisions", srcdec, bd, decision_fields, DECISION_ALIASES)):
        require(set(src) == set(recorded), "source_bag_identity_set", "recording", stream=label,
                missing_in_bag=sorted(set(src)-set(recorded), key=str), bag_only=sorted(set(recorded)-set(src), key=str))
        for ident in set(src) & set(recorded):
            source = src[ident]["job"] if label == "jobs" else src[ident]
            left = projection(source, fields, aliases)
            right = projection(recorded[ident], fields, {})
            require(len(left) == len(fields) and len(right) == len(fields), "source_or_bag_field_missing", "recording",
                    stream=label, identity=ident, source_missing=sorted(set(fields)-set(left)), bag_missing=sorted(set(fields)-set(right)))
            require(exact(left, right), "source_bag_payload_mismatch", "recording", stream=label, identity=ident,
                    fields=[k for k in set(left) & set(right) if not exact(left[k], right[k])])
            if label == "candidates":
                require(exact(job_projection(src[ident].get("job", {}), True), job_projection(recorded[ident].get("job", {}))),
                        "candidate_source_bag_job_echo", "recording", job_id=ident)
        streams[label] = {"source_count": len(src), "bag_count": len(recorded)}
    regsum = events(reg, "source_summary")
    worksum = events(worker, "worker_summary")
    for records, summaries, label in ((reg, regsum, "regulator"), (worker, worksum, "worker")):
        require(len(summaries) == 1 and records and records[-1] is summaries[-1], "terminal_summary_missing_or_nonterminal", "lifecycle", stream=label)
    rs = regsum[-1] if regsum else {}
    ws = worksum[-1] if worksum else {}
    require(rs.get("generated") == rs.get("emitted") == len(reg)-len(regsum) and rs.get("dropped") == 0
            and rs.get("normal_source_complete") is True, "regulator_source_counts_or_incomplete", "recording")
    require(ws.get("generated_candidates") == ws.get("published_candidates") == len(srccands)
            and ws.get("fatal") is False and ws.get("normal_source_complete") is True,
            "worker_source_counts_or_incomplete", "recording")
    # A summary generated before flush is not proof that flush succeeded.
    lifecycle = context.get("lifecycle", {})
    for key in ("regulator_exited", "worker_exited", "recorder_exited", "cleanup_success", "regulator_source_flush_verified", "worker_source_flush_verified"):
        require(lifecycle.get(key) is True, "lifecycle_fact_unknown_or_false", "lifecycle", field=key)
    shutdowns = events(reg, "regulator_shutdown")
    require(len(shutdowns) == 1, "regulator_shutdown_missing", "lifecycle")
    if shutdowns:
        require(shutdowns[0].get("plant_hold_end_known") is False, "plant_hold_end_overclaim", "logical")
    workers = {j.get("worker_instance") for j in bj.values()}
    require(len(workers) <= 1 and None not in workers and "" not in workers, "multiple_or_missing_worker_identity", "recording")
    for jid, j in bj.items():
        require(j.get("worker_instance") == verified_instance, "job_owned_worker_instance", "lifecycle", job_id=jid)
        require(set(JOB_FIELDS) <= set(j), "job_fields_missing", "recording", job_id=jid)
        require(j.get("schema_version") == "p1-solve-job-v1" and j.get("run_id") == run and j.get("boot_id") == boot
                and j.get("contract_hash") == contract_sha and j.get("nominal_hash") == contract.get("nominal_hash"), "job_identity", job_id=jid)
        require(integer(jid, 1) and integer(j.get("target_tick"), 1), "job_identifier", job_id=jid)
        origin, deadline, target, freeze = (j.get(k) for k in ("tick_origin_steady_ns", "deadline_steady_ns", "target_steady_ns", "freeze_steady_ns"))
        if all(integer(v) for v in (origin, deadline, target, freeze)):
            require(origin <= freeze <= deadline and deadline == origin + 150000000 and target == origin + 200000000,
                    "job_original_absolute_time", job_id=jid)
        else:
            fail("job_time_type", job_id=jid)
        require(j.get("horizon_steps") == 20 and j.get("prediction_dt") == .2
                and vector(j.get("frozen_state"), 6) and vector(j.get("target_state"), 6) and vector(j.get("reference"), 126), "job_shape_nonfinite", job_id=jid)
        require(vector(j.get("anchor_n"), 2) and j.get("anchor_known") == [True, True], "job_unknown_anchor", job_id=jid)
        hist = [j.get(k) for k in ("history_sim_ns", "history_channel", "history_n")]
        require(all(isinstance(v, list) for v in hist) and len(hist[0]) == len(hist[1]) == len(hist[2]) <= 256,
                "history_shape", job_id=jid)
        if all(isinstance(v, list) for v in hist):
            require(all(integer(t) for t in hist[0]) and hist[0] == sorted(hist[0]) and all(c in (0, 1) for c in hist[1])
                    and all(finite(v) for v in hist[2]), "history_invalid", job_id=jid)
        if all(integer(j.get(k)) for k in ("frozen_clock_sim_ns", "frozen_clock_receive_ns", "target_steady_ns", "target_sim_ns")):
            require(j.get("assumed_rtf") == 1.0 and j["target_sim_ns"] == j["frozen_clock_sim_ns"] + j["target_steady_ns"]-j["frozen_clock_receive_ns"], "target_sim_mapping", job_id=jid)
        else:
            fail("target_sim_mapping_unknown", job_id=jid)
    for jid, c in bc.items():
        require(c.get("worker_instance") == verified_instance and c.get("worker_instance") == c.get("job", {}).get("worker_instance"),
                "candidate_owned_worker_instance", "lifecycle", job_id=jid)
        require(jid in bj and exact(job_projection(c.get("job", {})), job_projection(bj.get(jid, {}))), "candidate_original_job_echo", job_id=jid)
        require(vector(c.get("first_control"), 2) and vector(c.get("x_prediction"), 126) and vector(c.get("u_prediction"), 40)
                and finite(c.get("backend_ms")) and c["backend_ms"] >= 0, "candidate_shape_nonfinite", job_id=jid)
        times = [c.get("job", {}).get("freeze_steady_ns"), c.get("worker_receive_ns"), c.get("solve_start_ns"), c.get("solve_end_ns")]
        require(all(integer(t) for t in times) and times == sorted(times), "candidate_native_time_order", job_id=jid)
        if c.get("prediction_available") is True:
            require(c.get("success") is True and c.get("solver_invoked") is True, "candidate_prediction_without_success", job_id=jid)
            if vector(c.get("first_control"), 2) and vector(c.get("u_prediction"), 40):
                require(all(abs(c["first_control"][i]-c["u_prediction"][i]) <= 1e-8 for i in range(2)), "candidate_first_control", job_id=jid)
            if vector(c.get("x_prediction"), 126) and vector(c.get("job", {}).get("target_state"), 6):
                require(all(abs(c["x_prediction"][i]-c["job"]["target_state"][i]) <= 1e-7 for i in range(6)), "candidate_initial_prediction", job_id=jid)
        else:
            require(all(v == 0 for k in ("first_control", "x_prediction", "u_prediction") for v in c.get(k, [])), "unavailable_prediction_not_empty_wire", job_id=jid)
    registrations = events(reg, "candidate_registration")
    accepted_regs = index([r for r in registrations if r.get("accepted_registration") is True], lambda r: r.get("job", {}).get("job_id"), "accepted_registrations")
    for jid, r in accepted_regs.items():
        j = bj.get(jid, {})
        require(jid in bc and exact(job_projection(r.get("job", {}), True), job_projection(j)), "registration_original_job_echo", job_id=jid)
        ready = r.get("ready_commit_ns")
        require(integer(ready) and integer(j.get("deadline_steady_ns")) and ready <= j["deadline_steady_ns"], "ready_after_deadline", job_id=jid)
        if jid in bc and integer(ready):
            require(bc[jid].get("solve_end_ns", ready+1) <= ready, "ready_before_native_end", job_id=jid)
    consumed = set()
    accepted_source_checks = []
    activation_source_samples = {name: {"receive_age_ms": [], "sim_lag_ms": []} for name in ("odom", "imu")}
    activation_mixed_skew_ms = []
    metrics: dict[str, list[float]] = {"tick_start_jitter_ms": [], "activation_jitter_ms": [], "solve_wall_ms": [], "backend_ms": [], "publish_span_ms": [], "target_sim_alignment_ms": [], "rtf": []}
    errors = [[] for _ in range(6)]
    physical_ok = mode == "execute"
    normal_flags = bool(bd)
    expected_sequence = 1
    last_accepted_ns = None
    for seq, d in sorted(bd.items(), key=lambda item: str(item[0]) if not integer(item[0]) else f"{item[0]:020d}"):
        require(seq == expected_sequence, "decision_sequence_gap", "recording", expected=expected_sequence, actual=seq)
        expected_sequence += 1
        require(d.get("run_id") == run and d.get("boot_id") == boot and d.get("contract_hash") == contract_sha and d.get("mode") == mode,
                "decision_identity", sequence=seq)
        require(d.get("schema_version") == expected_decision_schema and d.get("plant_acceptance_observed") is False,
                "decision_schema_or_plant_overclaim", sequence=seq)
        require(vector(d.get("final_n"), 2) and all(contract.get("command_min_n", 0) <= v <= contract.get("command_max_n", 0) for v in d.get("final_n", [])),
                "decision_final_command", sequence=seq)
        times = [d.get(k) for k in ("tick_planned_ns", "tick_start_ns", "activation_commit_ns", "tick_end_ns")]
        require(all(integer(v) for v in times) and times == sorted(times), "decision_time_order", sequence=seq)
        if all(integer(v) for v in times):
            metrics["tick_start_jitter_ms"].append((times[1]-times[0])/1e6)
            metrics["activation_jitter_ms"].append((times[2]-times[0])/1e6)
        normal_flags &= d.get("normal_contract_complete") is True
        if d.get("candidate_accepted") is True:
            jid = d.get("job_id")
            source_check_start = len(issues)
            require(d.get("worker_instance") == verified_instance, "activation_owned_worker_instance", "lifecycle", job_id=jid)
            jitter_limit = contract.get("tick_jitter_ns")
            require(integer(jitter_limit, 1) and all(integer(v) for v in times)
                    and 0 <= times[2]-times[0] <= jitter_limit,
                    "accepted_activation_jitter_gate", job_id=jid)
            if v2_contract:
                mixed = d.get("activation_r_from_imu")
                require(type(mixed) is bool, "accepted_activation_mixed_flag_unknown", job_id=jid)
                commit, sim, clock_receive = (d.get(k) for k in
                    ("activation_commit_ns", "activation_clock_sim_ns", "activation_clock_receive_ns"))
                clock_anchor_valid = (all(integer(v) and v <= INT64_MAX for v in (commit, sim, clock_receive))
                                      and clock_receive > 0 and clock_receive <= commit
                                      and sim + commit - clock_receive <= INT64_MAX)
                require(clock_anchor_valid, "accepted_activation_source_clock_anchor_invalid", job_id=jid)
                current_sim = sim + commit - clock_receive if clock_anchor_valid else None
                for name in ("odom", "imu"):
                    prefix = "activation_" + name + "_"
                    stamp, receive, source_sequence = (d.get(prefix+k) for k in ("stamp_ns", "receive_ns", "sequence"))
                    used = name == "odom" or mixed is True
                    if not used:
                        require(type(mixed) is bool and all(type(v) is int and v == 0 for v in
                                (stamp, receive, source_sequence, d.get("imu_age_ns"))),
                                "accepted_activation_unused_imu_not_zero", job_id=jid)
                        continue
                    valid_time = (integer(stamp) and stamp <= INT64_MAX and integer(receive, 1)
                                  and receive <= INT64_MAX and integer(commit, 1) and commit <= INT64_MAX)
                    require(valid_time and integer(source_sequence, 1) and source_sequence < (1 << 64),
                            "accepted_activation_source_time_or_sequence_unknown", job_id=jid, input=name)
                    age = commit - receive if valid_time else None
                    bound = contract.get(name + "_age_ns")
                    require(integer(bound, 1) and integer(age) and age <= bound,
                            "accepted_activation_source_receive_age_gate", job_id=jid, input=name)
                    require(type(d.get(name + "_age_ns")) is int and age is not None
                            and d[name + "_age_ns"] == age,
                            "accepted_activation_source_age_identity", job_id=jid, input=name)
                    if age is not None:
                        activation_source_samples[name]["receive_age_ms"].append(age / 1e6)
                    lag = current_sim - stamp if current_sim is not None and integer(stamp) else None
                    lag_bound, future = contract.get(name + "_sim_lag_ns"), contract.get("source_future_slack_ns")
                    require(integer(lag_bound, 1) and integer(future) and type(lag) is int
                            and -future <= lag <= lag_bound,
                            "accepted_activation_source_sim_lag_or_future_gate", job_id=jid, input=name)
                    if lag is not None:
                        activation_source_samples[name]["sim_lag_ms"].append(lag / 1e6)
                    admission = source_admissions[name].get(source_sequence, {})
                    observed = (admission.get("valid") is True and admission.get("accepted_sequence") == source_sequence
                                and admission.get("stamp_ns") == stamp and admission.get("receive_ns") == receive
                                and source_positions.get(id(admission), len(reg)) < source_positions.get(id(srcdec.get(seq)), -1))
                    require(observed, "accepted_activation_source_admission_missing_or_mismatch", "recording",
                            job_id=jid, input=name, source_sequence=source_sequence)
                    if name == "imu":
                        require(admission.get("frame_id") == contract.get("expected_imu_frame")
                                and admission.get("frame_truncated") is False and finite(admission.get("r_value")),
                                "accepted_activation_imu_frame_gate", job_id=jid)
                    else:
                        require(admission.get("pose_frame") == contract.get("expected_pose_frame")
                                and admission.get("child_frame") == contract.get("expected_child_frame")
                                and admission.get("pose_frame_truncated") is False
                                and admission.get("child_frame_truncated") is False and vector(admission.get("state"), 6),
                                "accepted_activation_odom_frame_or_state_gate", job_id=jid)
                if mixed is True:
                    odom_stamp, imu_stamp, skew_bound = (d.get("activation_odom_stamp_ns"),
                        d.get("activation_imu_stamp_ns"), contract.get("mixed_skew_ns"))
                    valid_skew = integer(odom_stamp) and integer(imu_stamp) and integer(skew_bound, 1)
                    require(valid_skew and abs(odom_stamp-imu_stamp) <= skew_bound,
                            "accepted_activation_mixed_skew_gate", job_id=jid)
                    if valid_skew:
                        activation_mixed_skew_ms.append(abs(odom_stamp-imu_stamp) / 1e6)
            else:
                delta = times[2]-times[1] if all(integer(v) for v in times) else None
                for name in ("odom", "imu"):
                    age = d.get(name + "_age_ns")
                    bound = contract.get(name + "_age_ns")
                    # v1 encodes unused IMU age as zero and logs ages at start.
                    used = name == "odom" or age != 0
                    require(isinstance(age, int) and not isinstance(age, bool) and integer(bound, 1)
                            and integer(delta) and (not used or 0 <= age + delta <= bound),
                            "accepted_activation_source_age_gate", job_id=jid, input=name)
            clock_receive = d.get("activation_clock_receive_ns")
            clock_limit = contract.get("clock_age_ns")
            require(integer(clock_receive, 1) and integer(d.get("activation_commit_ns")) and integer(clock_limit, 1)
                    and 0 <= d["activation_commit_ns"]-clock_receive <= clock_limit,
                    "accepted_activation_clock_age_gate", job_id=jid)
            if v2_contract:
                require(type(d.get("clock_age_ns")) is int and integer(clock_receive, 1)
                        and integer(d.get("activation_commit_ns"))
                        and d["clock_age_ns"] == d["activation_commit_ns"]-clock_receive,
                        "accepted_activation_clock_age_identity", job_id=jid)
            rtf, low, high = d.get("activation_rtf"), contract.get("rtf_low"), contract.get("rtf_high")
            require(finite(rtf) and finite(low) and finite(high) and 0 < low <= high and low <= rtf <= high,
                    "accepted_activation_rtf_gate", job_id=jid)
            require(jid not in consumed, "candidate_consumed_twice", job_id=jid)
            accepted_source_checks.append(v2_contract and d.get("schema_version") == expected_decision_schema
                                          and len(issues) == source_check_start)
            consumed.add(jid)
            j = bj.get(jid, {})
            c = bc.get(jid, {})
            r = accepted_regs.get(jid, {})
            require(jid in bj and jid in bc and jid in accepted_regs, "activation_missing_job_candidate_registration", job_id=jid)
            require(d.get("tick") == j.get("target_tick") and d.get("tick_planned_ns") == j.get("target_steady_ns"), "activation_wrong_target", job_id=jid)
            require(d.get("worker_instance") == j.get("worker_instance"), "activation_worker_instance", job_id=jid)
            require(d.get("candidate_ready_commit_ns") == r.get("ready_commit_ns"), "activation_ready_identity", job_id=jid)
            cutoff = d.get("cutoff_commit_ns")
            require(integer(cutoff) and integer(j.get("deadline_steady_ns")) and cutoff > j["deadline_steady_ns"] and cutoff <= d.get("activation_commit_ns", -1), "cutoff_not_after_deadline", job_id=jid)
            for field in ("task_generation", "model_generation", "config_generation", "schedule_generation", "clock_epoch"):
                require(d.get(field) == j.get(field), "activation_version", job_id=jid, field=field)
            require(exact(d.get("target_state"), j.get("target_state")), "activation_target_state", job_id=jid)
            if vector(d.get("activation_state"), 6) and vector(j.get("target_state"), 6) and vector(d.get("state_error"), 6):
                ee = [d["activation_state"][i]-j["target_state"][i] for i in range(6)]
                ee[2] = math.atan2(math.sin(ee[2]), math.cos(ee[2]))
                require(all(abs(ee[i]-d["state_error"][i]) <= 1e-12 and abs(ee[i]) <= contract["activation_tolerance"][i] for i in range(6)), "activation_state_error_gate", job_id=jid)
                for i, e in enumerate(ee):
                    errors[i].append(abs(e))
            else:
                fail("activation_state_error_unknown", job_id=jid)
            require(exact(d.get("requested_n"), c.get("first_control")) and exact(d.get("requested_n"), d.get("final_n")), "accepted_candidate_mapping_changed", job_id=jid)
            if mode == "execute":
                require(exact(d.get("previous_n"), j.get("anchor_n")) and exact(d.get("previous_publish_ns"), j.get("anchor_publish_ns"))
                        and d.get("previous_anchor_known") == [True, True], "accepted_candidate_previous_anchor", job_id=jid)
            if all(integer(d.get(k)) for k in ("activation_clock_sim_ns", "activation_clock_receive_ns", "activation_commit_ns")) and integer(j.get("target_sim_ns")):
                err = d["activation_clock_sim_ns"]+d["activation_commit_ns"]-d["activation_clock_receive_ns"]-j["target_sim_ns"]
                metrics["target_sim_alignment_ms"].append(abs(err)/1e6)
                require(abs(err) <= contract.get("target_sim_slack_ns", -1), "activation_target_sim_alignment", job_id=jid)
            last_accepted_ns = d.get("activation_commit_ns")
        elif d.get("control_source") == "hold":
            require(integer(last_accepted_ns) and integer(d.get("activation_commit_ns")) and
                    0 <= d["activation_commit_ns"]-last_accepted_ns <= contract.get("hold_ns", -1), "hold_outside_finite_window", sequence=seq)
            if mode == "execute":
                require(exact(d.get("final_n"), d.get("previous_n")), "hold_changed_command", sequence=seq)
        if mode != "execute":
            require(d.get("diagnostic_only") is True and d.get("publish_success") == [False, False]
                    and d.get("publish_start_ns") == [0, 0] and d.get("publish_end_ns") == [0, 0]
                    and d.get("rho_available") is False and d.get("normal_contract_complete") is False,
                    "diagnostic_physical_overclaim", sequence=seq)
        else:
            old_known = d.get("previous_anchor_known")
            successes = d.get("publish_success")
            physical_ok &= successes == [True, True] and old_known == [True, True] and d.get("rho_available") is True
            if successes != [True, True] or old_known != [True, True]:
                require(d.get("rho_available") is False, "rho_available_from_unknown_or_partial", sequence=seq)
            if all(vector(d.get(k), 2) for k in ("final_n", "previous_n")) and all(isinstance(d.get(k), list) and len(d[k]) == 2 for k in ("publish_start_ns", "publish_end_ns", "previous_publish_ns")):
                for i in range(2):
                    ps, pe, prev = d["publish_start_ns"][i], d["publish_end_ns"][i], d["previous_publish_ns"][i]
                    require(integer(ps) and integer(pe) and ps >= d.get("activation_commit_ns", 0) and pe >= ps, "publish_before_activation_or_bad_time", sequence=seq, channel=i)
                    if old_known == [True, True] and successes and successes[i]:
                        delta = ps-prev
                        rate_ok = delta > 0 and abs(d["final_n"][i]-d["previous_n"][i]) <= contract.get("rho_n_s", 0)*delta/1e9+1e-9
                        gap_ok = delta <= contract.get("publish_gap_ns", -1)
                        require(not d.get("rho_available") or rate_ok and gap_ok, "rho_false_positive", sequence=seq, channel=i)
                        physical_ok &= rate_ok and gap_ok
                metrics["publish_span_ms"].append((d["publish_end_ns"][1]-d["publish_start_ns"][0])/1e6)
    for c in bc.values():
        if integer(c.get("solve_start_ns")) and integer(c.get("solve_end_ns")):
            metrics["solve_wall_ms"].append((c["solve_end_ns"]-c["solve_start_ns"])/1e6)
        if finite(c.get("backend_ms")):
            metrics["backend_ms"].append(c["backend_ms"])
    caps = [e["message"] for e in bag.get("/p1/worker_capability", [])]
    require(any(c.get("run_id") == run and c.get("worker_instance") == verified_instance
                and c.get("pid") == verified_pid for c in caps), "owned_worker_capability_missing_from_bag", "lifecycle")
    for c in caps:
        if c.get("run_id") != run:
            continue
        require(c.get("boot_id") == boot and c.get("contract_hash") == contract_sha and c.get("nominal_hash") == contract.get("nominal_hash")
                and c.get("clock_name") == "CLOCK_MONOTONIC" and c.get("backend") == "acados" and c.get("horizon_steps") == 20 and c.get("prediction_dt") == .2
                and c.get("matrix_layout") == "column_major" and c.get("pending_count") in (0, 1), "capability_contract")
        require(c.get("pid") == verified_pid and c.get("worker_instance") == verified_instance,
                "capability_owned_pid_or_instance", "lifecycle")
    metrics["rtf"] = [e["rtf"] for e in events(reg, "clock") if finite(e.get("rtf"))]
    facts = {scope: not any(i["scope"] == scope for i in issues) for scope in ("recording", "logical", "lifecycle")}
    faults = context.get("fault_injection", {})
    fault_run = any(finite(v) and v > 0 for v in faults.values()) if isinstance(faults, dict) else bool(faults)
    fault_run |= context.get("scenario", "normal") not in ("normal", "baseline", "diagnostic_normal")
    if not fault_run:
        require(bool(bj) and bool(bc) and bool(consumed), "normal_diagnostic_has_no_solver_activation", "logical")
    facts = {scope: not any(i["scope"] == scope for i in issues) for scope in ("recording", "logical", "lifecycle")}
    # Completeness is scoped to accepted publisher-side source observation;
    # v1 cannot certify the missing current mixed flag/stamp pair.
    activation_source_contract_complete = (v2_contract and v2_metadata_valid and bool(accepted_source_checks)
                                           and all(accepted_source_checks) and facts["recording"])
    normal = (mode == "execute" and qualified and all(facts.values()) and physical_ok and normal_flags
              and not fault_run and activation_source_contract_complete)
    diagnostic = (mode in ("no_output", "shadow") and all(facts.values()) and not fault_run
                  and (mode != "no_output" or raw_complete is True))
    # Mechanism evidence stays separate from normal source closure. A killed
    # worker may prove an owned cleanup mechanism while its final source remains
    # explicitly unknown; all other evidence gaps fail the mechanism gate.
    def parameter_matches(name: str, value: int) -> bool:
        argv = context.get("_worker_owned_argv", [])
        tokens = [x for x in argv if isinstance(x, str) and x.startswith(name + ":=")]
        return tokens == [name + ":=" + str(value)]
    def fault_capability() -> bool:
        return any(c.get("run_id") == run and c.get("worker_instance") == verified_instance
                   and c.get("pid") == verified_pid and c.get("fault_injection_enabled") is True for c in caps)
    delay_ms = context.get("fault_injection", {}).get("test_delay_ms", 0)
    delay_sources = [c for c in srccands.values() if c.get("solver_invoked") is True]
    delay_observed = (integer(delay_ms, 1) and parameter_matches("test_delay_ms", delay_ms)
        and fault_capability() and bool(delay_sources)
        and all(integer(c.get("publish_start_ns")) and integer(c.get("solve_end_ns"))
                and c["publish_start_ns"] - c["solve_end_ns"] >= delay_ms * 1000000 for c in delay_sources))
    expired_registrations = [r for r in registrations
        if integer(r.get("ready_commit_ns")) and integer(r.get("job", {}).get("deadline_ns"))
        and r["ready_commit_ns"] > r["job"]["deadline_ns"]]
    expired_rejected = all(r.get("accepted_registration") is False
                          and r.get("job", {}).get("job_id") not in consumed for r in expired_registrations)
    block_ms = context.get("fault_injection", {}).get("test_native_block_ms", 0)
    barrier_events = events(worker, "controlled_pre_native_barrier")
    expected_worker_gaps = []
    other_fault_issues = []
    for item in issues:
        expected_gap = (item.get("code") == "worker_source_counts_or_incomplete"
            or (item.get("code") == "terminal_summary_missing_or_nonterminal" and item.get("stream") == "worker")
            or (item.get("code") == "lifecycle_fact_unknown_or_false" and item.get("field") == "worker_source_flush_verified"))
        (expected_worker_gaps if expected_gap else other_fault_issues).append(item)
    block_scope_complete = not other_fault_issues and (mode != "no_output" or raw_complete is True)
    full_fault_scope_complete = all(facts.values()) and (mode != "no_output" or raw_complete is True)
    assertions = []
    for expect in context.get("expected_mechanisms", []):
        if expect == "post_native_delay_observed":
            ok = delay_observed
        elif expect == "original_deadline_respected":
            ok = bool(registrations) and expired_rejected
        elif expect == "late_candidate_rejected":
            # Registration can first reject a stale target as wrong_tick. The
            # original absolute deadline and actual consumption decide expiry.
            ok = bool(expired_registrations) and expired_rejected
        elif expect == "expired_pending_not_invoked":
            ok = any(e.get("solver_invoked") is False for e in events(worker, "pending_expired_before_native"))
        elif expect == "watchdog_invalidated":
            external = context.get("runner_summary_facts", {})
            boundary = context.get("_watchdog_boundary_ns")
            watchdogs = [e for e in events(reg, "active_watchdog")
                         if integer(e.get("observed_ns")) and integer(boundary)
                         and e["observed_ns"] <= boundary]
            barriers = [e for e in barrier_events if integer(e.get("start_ns"))
                        and e.get("duration_ms") == block_ms and e.get("actual_native_invoked") is False
                        and e.get("flush_requested") is True and e.get("job_id") in bj
                        and bj[e["job_id"]].get("worker_instance") == verified_instance]
            pair = next(((b, w) for b in barriers for w in watchdogs
                         if b["job_id"] == w.get("active_job")
                         and integer(contract.get("active_watchdog_ns"), 1)
                         and w["observed_ns"] - b["start_ns"] >= contract["active_watchdog_ns"]), None)
            cutoff = pair[1]["observed_ns"] if pair else None
            ticking = [d for d in bd.values() if pair and integer(d.get("activation_commit_ns"))
                       and pair[0]["start_ns"] <= d["activation_commit_ns"] <= boundary]
            no_after = integer(cutoff) and not any(d.get("candidate_accepted") is True
                       and integer(d.get("activation_commit_ns")) and d["activation_commit_ns"] >= cutoff for d in bd.values())
            no_submit_after = integer(cutoff) and not any(integer(j.get("freeze_steady_ns"))
                              and j["freeze_steady_ns"] >= cutoff for j in bj.values())
            clean = context.get("_worker_owned_cleanup", {})
            signals = context.get("_worker_owned_signals", [])
            signal_sequence = [e.get("signal") for e in signals]
            signal_times = [e.get("monotonic_ns") for e in signals]
            killed = (signal_sequence == [2, 15, 9] and context.get("_worker_owned_signals_valid") is True
                      and all(integer(t) for t in signal_times) and signal_times == sorted(signal_times)
                      and clean.get("returncode") == -9 and clean.get("cleanup_complete") is True
                      and clean.get("remaining_members") == [] and integer(clean.get("monotonic_ns"))
                      and integer(contract.get("kill_postcheck_ns"), 1)
                      and 0 <= clean["monotonic_ns"] - signal_times[-1] <= contract["kill_postcheck_ns"])
            ok = (integer(block_ms, 1) and parameter_matches("test_native_block_ms", block_ms)
                  and fault_capability() and pair is not None and len(ticking) >= 2
                  and no_after and no_submit_after and killed
                  and external.get("watchdog_seen") is True
                  and external.get("stop_reason") == "owned_worker_active_watchdog"
                  and lifecycle.get("cleanup_success") is True)
        elif expect == "new_processes_have_no_physical_publishers":
            ok = mode == "shadow" and graph.get("graph_new_physical_publishers_zero") is True and start.get("physical_publisher_endpoints") == 0 and all(d.get("publish_success") == [False, False] for d in bd.values())
        elif expect == "no_physical_publishers":
            ok = mode != "execute" and start.get("physical_publisher_endpoints") == 0 and all(d.get("publish_success") == [False, False] for d in bd.values())
        else:
            ok = False
        assertions.append({"name": expect, "passed": ok})
    watchdog_fault = "watchdog_invalidated" in context.get("expected_mechanisms", [])
    mechanism_evidence_complete = block_scope_complete if watchdog_fault else full_fault_scope_complete
    mechanism_passed = bool(assertions) and all(a["passed"] for a in assertions) and mechanism_evidence_complete
    return {"schema": "p1-execution-check-v1", "run_id": run, "mode": mode,
            "passed": normal if mode == "execute" else diagnostic,
            "source_bag_contract_complete": facts["recording"], "logical_admission_contract_passed": facts["logical"],
            "lifecycle_verified": facts["lifecycle"], "diagnostic_complete": diagnostic,
            "raw_input_recording_complete": raw_complete, "raw_input_count_comparison": raw_comparison,
            "raw_input_recording_scope": ("fixture publisher counts versus independently scanned five raw topic bag counts; count agreement does not prove callback reconstruction"
                                           if fixture is not None or mode == "no_output" else
                                           "unknown whole-run raw prefix/suffix; typed job/candidate/decision admission observations only"),
            "activation_source_contract_complete": activation_source_contract_complete,
            "activation_source_evidence_limit": (
                "v2 current commit source fields and valid source admissions independently checked; not raw callback/bag reconstruction, coordinate transformation, plant ACK or force"
                if v2_contract else "v1 activation mixed flag and odom/IMU stamp pair absent; independent mixed skew and source sim lag/future gate unavailable"),
            "decision_schema_expected": expected_decision_schema,
            "activation_source_observations": {name: {k: distribution(v) for k, v in samples.items()}
                                               for name, samples in activation_source_samples.items()},
            "activation_mixed_skew_ms": distribution(activation_mixed_skew_ms),
            "normal_contract_complete": normal, "execute_qualified": qualified,
            "fault_run": fault_run, "fault_mechanism_passed": mechanism_passed,
            "fault_mechanism_evidence_complete": mechanism_evidence_complete,
            "fault_expected_worker_source_gaps": expected_worker_gaps if watchdog_fault else [],
            "fault_delay_observations": {"declared_ms": delay_ms, "observed": delay_observed,
                "source_candidate_count": len(delay_sources), "expired_registration_count": len(expired_registrations),
                "expired_all_rejected_and_unconsumed": expired_rejected,
                "semantics": "owned argv and capability plus source publication interval; scheduling overhead included"},
            "mechanism_assertions": assertions, "issues": issues, "streams": streams,
            "regulator_summary": rs, "worker_summary": ws,
            "observed_metrics": {k: distribution(v) for k, v in metrics.items()},
            "activation_component_abs_error": {n: distribution(v) for n, v in zip(("x_m", "y_m", "psi_rad", "u_m_s", "v_m_s", "r_rad_s"), errors)},
            "metrics_semantics": "finite source samples only; diagnostic observations are not worst-case or qualified budgets",
            "guarantees": {"plant_acceptance_observed": False, "plant_force_measured": False,
                           "atomic_physical_execution_proven": False, "exact_plant_step_timing_proven": False,
                           "gp_training_eligible": False, "raw_callback_bag_exact_reconstruction_proven": False}}


def runtime_context(ex: Path, raw: dict) -> tuple[dict, list[Path]]:
    """Normalize explicitly documented runner facts; never invent missing facts."""
    c = dict(raw)
    c["contract_hash"] = raw.get("contract_hash", raw.get("contract_sha256"))
    c["_binding_issues"] = []
    def issue(code: str, **detail: Any) -> None:
        c["_binding_issues"].append({"code": code, **detail})
    files = []
    summary_path, ledger_path = ex / "runner_summary.json", ex / "owned_process_ledger.jsonl"
    summary = read_json(summary_path) if summary_path.is_file() else {}
    ledger = read_jsonl(ledger_path) if ledger_path.is_file() else []
    files.extend(p for p in (summary_path, ledger_path) if p.is_file())
    if summary.get("run_id") != raw.get("run_id"):
        issue("runner_summary_identity_unknown")
    if summary.get("supervision_evidence_complete") is not True:
        issue("supervision_evidence_incomplete_or_unknown")
    clock = raw.get("python_monotonic_clock", {})
    if "CLOCK_MONOTONIC" not in str(clock.get("implementation", "")) or clock.get("monotonic") is not True:
        issue("runner_clock_domain_unverified")
    terminal = [e for e in ledger if e.get("type") == "supervisor_summary"]
    if len(terminal) != 1 or not ledger or ledger[-1] is not terminal[-1]:
        issue("owned_ledger_terminal_unknown")
    spawns = {}
    for e in ledger:
        if e.get("boot_id") != raw.get("boot_id"):
            issue("owned_ledger_boot_mismatch")
        if e.get("type") == "spawn":
            if e.get("name") in spawns:
                issue("owned_name_spawned_twice", name=e.get("name"))
            spawns[e.get("name")] = e
    required_names = {"regulator", "worker", "recorder"}
    if raw.get("mode") == "no_output":
        required_names.add("fixture")
    for name in sorted(required_names | set(spawns)):
        spawn = spawns.get(name, {})
        ident = spawn.get("identity", {})
        if not (spawn.get("executable_verified") is True and integer(ident.get("pid"), 1)
                and ident.get("pid") == ident.get("pgid") == ident.get("sid") and integer(ident.get("start_ticks"), 1)
                and ident.get("exe_sha256") == spawn.get("expected_sha256")):
            issue("owned_spawn_identity_unverified", name=name)
        if name in ("worker", "regulator", "fixture"):
            c[f"_{name}_owned_pid"] = ident.get("pid")
    worker_spawn = spawns.get("worker", {})
    c["_worker_owned_argv"] = worker_spawn.get("argv", [])
    c["_worker_owned_signals"] = [e for e in ledger if e.get("type") == "signal" and e.get("name") == "worker"]
    wid = worker_spawn.get("identity", {})
    c["_worker_owned_signals_valid"] = bool(c["_worker_owned_signals"]) and all(
        any(m.get("pid") == wid.get("pid") and m.get("pgid") == wid.get("pgid")
            and m.get("sid") == wid.get("sid") and m.get("start_ticks") == wid.get("start_ticks")
            for m in e.get("members", [])) for e in c["_worker_owned_signals"])
    wc = [e for e in ledger if e.get("type") == "cleanup_result" and e.get("name") == "worker"]
    c["_worker_owned_cleanup"] = wc[0] if len(wc) == 1 else {}
    handshakes = [e for e in ledger if e.get("type") == "worker_capability_verified"]
    if (len(handshakes) != 1 or handshakes[0].get("pid") != c.get("_worker_owned_pid")
            or not isinstance(handshakes[0].get("worker_instance"), str) or not handshakes[0].get("worker_instance")
            or handshakes[0].get("backend") != "acados"):
        issue("owned_worker_capability_handshake_unverified")
    else:
        c["_worker_verified_instance"] = handshakes[0]["worker_instance"]
    for name, data in raw.get("binaries", {}).items():
        path = Path(data.get("path", ""))
        if not path.is_file() or sha(path) != data.get("sha256"):
            issue("bound_executable_current_hash_unknown_or_changed", name=name)
        elif name in ("worker", "regulator") and spawns.get(name, {}).get("expected_sha256") != data.get("sha256"):
            issue("context_owned_executable_hash_mismatch", name=name)
        if path.is_file():
            files.append(path)
    for name in ("worker", "regulator"):
        if name not in raw.get("binaries", {}):
            issue("bound_executable_identity_missing", name=name)
    clean = summary.get("cleanup", {})
    life = {}
    for name in ("regulator", "worker", "recorder"):
        result = clean.get(name, {})
        ledger_result = [e for e in ledger if e.get("type") == "cleanup_result" and e.get("name") == name]
        life[f"{name}_exited"] = (result.get("cleanup_complete") is True and result.get("returncode") is not None
                                  and len(ledger_result) == 1 and all(exact(result.get(k), ledger_result[0].get(k)) for k in result))
        if name in ("worker", "regulator"):
            console = ex / f"{name}.console.log"
            token = f"{name.upper()}_CLOSE_FLUSH_SUCCESS=true"
            text = console.read_text(encoding="utf-8", errors="replace") if console.is_file() else ""
            life[f"{name}_source_flush_verified"] = result.get("returncode") == 0 and text.splitlines().count(token) == 1 and f"{name.upper()}_CLOSE_FLUSH_SUCCESS=false" not in text
            if console.is_file():
                files.append(console)
    life["cleanup_success"] = summary.get("cleanup_complete") is True and summary.get("cleanup_failed") is False and bool(terminal) and terminal[-1].get("cleanup_failed") is False
    c["lifecycle"] = life
    c["runner_summary_facts"] = {k: summary.get(k) for k in ("cleanup_complete", "cleanup_failed", "calibration_status", "graph_no_physical_publishers", "graph_new_physical_publishers_zero", "graph_sole_physical_owner_verified", "graph_physical_owner_node", "graph_physical_publishers_per_channel", "stop_reason", "expected_fault")}
    c["runner_summary_facts"]["watchdog_seen"] = summary.get("observations", {}).get("watchdog_seen")
    watchdog_ends = [e for e in ledger if e.get("type") in ("calibration_window_end", "validation_window_end") and e.get("reason") == "owned_worker_active_watchdog"]
    c["_watchdog_boundary_ns"] = watchdog_ends[-1].get("monotonic_ns") if watchdog_ends else None
    declaration = raw.get("declaration", {})
    c["fault_injection"] = {k: declaration.get(k, 0) for k in ("test_delay_ms", "test_native_block_ms")}
    expected = declaration.get("expected_fault", summary.get("expected_fault", "none"))
    c["scenario"] = "diagnostic_normal" if expected == "none" else expected
    c["expected_mechanisms"] = (["no_physical_publishers"] if raw.get("mode") == "no_output" else
                                ["new_processes_have_no_physical_publishers"] if raw.get("mode") == "shadow" else [])
    if expected == "post_native_result_delay":
        c["expected_mechanisms"].extend(["post_native_delay_observed", "original_deadline_respected"])
        delay = declaration.get("test_delay_ms")
        if integer(delay, 1) and delay >= 150:
            c["expected_mechanisms"].append("late_candidate_rejected")
    elif expected == "controlled_pre_native_barrier_watchdog":
        c["expected_mechanisms"].append("watchdog_invalidated")
    return c, list(dict.fromkeys(files))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--bag", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--regulator-source", type=Path)
    parser.add_argument("--worker-source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    ex = args.experiment.resolve()
    bagpath = args.bag.resolve()
    output = (args.output or ex / ("check_p1_execution_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))).resolve()
    if output == bagpath or bagpath in output.parents:
        parser.error("report output must be outside the raw bag")
    output.mkdir(parents=True, exist_ok=False)
    before = {}
    result = {"schema": "p1-execution-check-v1", "passed": False, "normal_contract_complete": False}
    try:
        context_path = args.context or ex / "run_context.json"
        context, binding_files = runtime_context(ex, read_json(context_path))
        def source_path(explicit: Path | None, name: str, default: str) -> Path:
            p = explicit or Path(context.get("source_files", {}).get(name, default))
            return p.resolve() if p.is_absolute() else (ex / p).resolve()
        regpath = source_path(args.regulator_source, "regulator", "regulator.jsonl")
        workpath = source_path(args.worker_source, "worker", "worker.jsonl")
        fixture_path = source_path(None, "fixture", "fixture_source.jsonl")
        fixture_files = [fixture_path] if fixture_path.is_file() else []
        paths = list(dict.fromkeys([*fixture_files, args.contract.resolve(), context_path.resolve(), regpath, workpath, *binding_files] + sorted(p for p in bagpath.rglob("*") if p.is_file())))
        before = {str(p): sha(p) for p in paths}
        contract = read_json(args.contract)
        source_errors = []
        sources = []
        for name, path in (("regulator", regpath), ("worker", workpath)):
            try:
                sources.append(read_jsonl(path))
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                sources.append([])
                source_errors.append({"code": "source_parse_or_unclosed", "scope": "recording", "stream": name, "error": str(exc)})
        reg, worker = sources
        if fixture_path.is_file():
            try:
                fixture_events = read_jsonl(fixture_path)
                if len(fixture_events) != 1 or fixture_events[0].get("type") != "fixture_summary":
                    raise ValueError("fixture must contain exactly one terminal fixture_summary")
                context["_fixture_summary"] = fixture_events[0]
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                source_errors.append({"code": "fixture_parse_or_terminal_invalid", "scope": "raw_recording", "error": str(exc)})
        decoded, storage = read_bag(bagpath)
        context["_actual_topic_counts"] = storage["actual_topic_counts"]
        result = validate_decoded(reg, worker, decoded, contract, context, before[str(args.contract.resolve())])
        if source_errors:
            result["issues"].extend(source_errors)
            for k in ("passed", "normal_contract_complete", "diagnostic_complete", "fault_mechanism_passed", "fault_mechanism_evidence_complete"):
                result[k] = False
            if any(e.get("scope") == "recording" for e in source_errors):
                result["source_bag_contract_complete"] = False
                result["activation_source_contract_complete"] = False
        if any(e.get("scope") == "raw_recording" for e in source_errors):
            result["raw_input_recording_complete"] = False
        result["storage"] = storage
        after = {str(p): sha(p) for p in paths}
        result["raw_inputs_unchanged"] = before == after
        result["input_sha256_before"] = before
        result["input_sha256_after"] = after
        if before != after:
            result["issues"].append({"code": "raw_inputs_changed_during_read", "scope": "recording"})
            for k in ("passed", "normal_contract_complete", "diagnostic_complete", "source_bag_contract_complete", "activation_source_contract_complete", "fault_mechanism_passed", "fault_mechanism_evidence_complete"):
                result[k] = False
            if result.get("raw_input_recording_complete") is True:
                result["raw_input_recording_complete"] = False
    except Exception as exc:
        result["reader_error"] = f"{type(exc).__name__}: {exc}"
        result["input_sha256_before"] = before
        result["issues"] = [{"code": "reader_or_source_error", "scope": "recording", "message": str(exc)}]
    result["checker_sha256"] = sha(Path(__file__))
    result["report_created_utc"] = datetime.now(timezone.utc).isoformat()
    (output / "contract_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    md = ["# P1 源记录与实际 typed bag 对账", "", f"- mode：{result.get('mode', 'unknown')}",
          f"- source/bag 契约：{result.get('source_bag_contract_complete', False)}",
          f"- 逻辑准入：{result.get('logical_admission_contract_passed', False)}",
          f"- 生命周期事实：{result.get('lifecycle_verified', False)}",
          f"- raw_input_recording_complete：{result.get('raw_input_recording_complete', 'unknown')}",
          f"- activation_source_contract_complete：{result.get('activation_source_contract_complete', False)}",
          f"- diagnostic_complete：{result.get('diagnostic_complete', False)}",
          f"- normal_contract_complete：{result.get('normal_contract_complete', False)}",
          f"- fault_mechanism_passed：{result.get('fault_mechanism_passed', False)}", "",
          "no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。", "",
          "## 问题", ""]
    md += [f"- {json.dumps(i, ensure_ascii=False)}" for i in result.get("issues", [])] or ["- 未发现本检查范围内的不一致。"]
    md += ["", "## 实测诊断指标", "", "```json", json.dumps(result.get("observed_metrics", {}), ensure_ascii=False, indent=2), "```", "",
           "完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。"]
    (output / "contract_report.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": result.get("passed", False),
                      "normal_contract_complete": result.get("normal_contract_complete", False),
                      "fault_mechanism_passed": result.get("fault_mechanism_passed", False),
                      "issues": len(result.get("issues", []))}, ensure_ascii=False))
    return 0 if result.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
