#!/usr/bin/env python3
"""Read-only extension checker for actual solver reference/prediction observations.

The original P0 checker, its three schemas and old bags remain unchanged. This
module decodes four research streams. A separately hash-bound publisher report
supplies raw odometry/actuator/clock checks; neither report certifies plant ACKs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

NS = 1_000_000_000
SCHEMA = "p0-reference-prediction-v1"
DEFAULT_TOPICS = {"state": "/research/state_snapshot", "applied": "/research/control/applied",
                  "cycle": "/research/cycle_timing", "reference_prediction": "/research/reference_prediction"}
TOPIC_TYPES = {"state": "usv_research_interfaces/msg/StateSnapshot",
               "applied": "usv_research_interfaces/msg/AppliedControl",
               "cycle": "usv_research_interfaces/msg/CycleTiming",
               "reference_prediction": "usv_research_interfaces/msg/ReferencePrediction"}
IDENTITY = ("run_id", "producer_instance_id", "baseline_id", "config_hash", "steady_clock_domain")
REQUIRED_SOLVER_TEST_CASES = (
    "ReferencePredictionContract.ExactFrozenReferenceSuppliedToSolver",
    "ReferencePredictionContract.AcceptedPredictionCopiedFromSameSolveInfo",
    "ReferencePredictionContract.FailedLateAndStandbyNoFabrication",
    "ReferencePredictionContract.LoggingOffAndOnPreserveSameReferenceAndCommands",
)
LIMITATIONS = [
    "The reference matrix is an observation of the local solver input; raw callback-to-bag replay is not proved.",
    "Path/profile versions count all received callbacks, including invalid/clear callbacks; they are not accepted-message sequences.",
    "Prediction is a candidate from the same accepted SolveInfo; U[0] is not required to equal the mapped published command.",
    "Publisher return, local observation and model prediction do not prove plant acceptance, measured force or atomic execution.",
    "The final observation has no observed right boundary; bag end cannot supply that boundary.",
    "This checker does not authorize exact residual labels or GP training.",
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
    numeric_tolerance: float = 1e-9

    def validate(self):
        if set(self.topics) != set(DEFAULT_TOPICS) or len(set(self.topics.values())) != 4:
            raise ValueError("four distinct research topic mappings required")
        if any(not isinstance(t, str) or not t.startswith("/") for t in self.topics.values()):
            raise ValueError("absolute topic names required")
        if not finite(self.numeric_tolerance) or self.numeric_tolerance < 0:
            raise ValueError("finite nonnegative numeric_tolerance required")
        if self.expected_counts is not None and any(not integer(v) for v in self.expected_counts.values()):
            raise ValueError("metadata counts must be nonnegative integers")

def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

def integer(v, minimum=0):
    return isinstance(v, int) and not isinstance(v, bool) and v >= minimum

def sha(v):
    return isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)

def vector(v, n):
    return isinstance(v, (list, tuple)) and len(v) == n and all(finite(x) for x in v)

def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def hash_bag(bag):
    result = {}
    for path in sorted(Path(bag).rglob("*")):
        if path.is_symlink():
            raise ValueError("bag symlink is not a contained readonly asset")
        if path.is_file():
            result[str(path.relative_to(bag))] = hash_file(path)
    return result

def evidence_check(evidence, context):
    """Validate fixed-test external evidence. Missing evidence never makes up proof."""
    failures = []
    spec = context.get("reference_prediction_contract", {})
    if evidence is None:
        return False, ["solver_test_evidence_missing"]
    if evidence.get("schema") != "p0-reference-solver-test-evidence/1":
        failures.append("solver_test_evidence_schema")
    if evidence.get("baseline_id") != context.get("baseline_id"):
        failures.append("solver_test_evidence_baseline")
    for key in ("source_node_sha256", "compiled_test_binary_sha256", "gtest_report_sha256"):
        if not sha(evidence.get(key)):
            failures.append("solver_test_evidence_hash_missing:" + key)
    if evidence.get("source_node_sha256") != spec.get("source_node_sha256"):
        failures.append("solver_test_evidence_source_node")
    if evidence.get("exit_code") != 0 or evidence.get("all_required_passed") is not True:
        failures.append("solver_test_evidence_execution_failed")
    required, tested = evidence.get("required_cases"), evidence.get("tested_cases")
    if (not REQUIRED_SOLVER_TEST_CASES or not isinstance(required, list) or
            set(required) != set(REQUIRED_SOLVER_TEST_CASES) or
            not isinstance(tested, list) or not set(REQUIRED_SOLVER_TEST_CASES).issubset(tested)):
        failures.append("solver_test_evidence_required_cases")
    binding = spec.get("solver_test_evidence", {})
    if not sha(binding.get("file_sha256")) or evidence.get("__verified_file_sha256") != binding.get("file_sha256"):
        failures.append("solver_test_evidence_file_not_bound")
    return not failures, failures

def validate_events(records: Iterable[Record], topic_types: dict[str, str],
                    session: dict[str, Any], context: dict[str, Any], cfg: Config | None = None,
                    publisher_report: dict[str, Any] | None = None,
                    solver_test_evidence: dict[str, Any] | None = None):
    cfg = cfg or Config()
    cfg.validate()
    failures, warnings, ledger = [], [], []
    def issue(code, message, scope="source", **detail):
        failures.append(dict(code=code, message=message, scope=scope, **detail))
    streams, counts = defaultdict(list), Counter()
    roles = {topic: role for role, topic in cfg.topics.items()}
    for rec in records:
        counts[rec.topic] += 1
        if rec.topic in roles:
            role = roles[rec.topic]
            streams[role].append(rec)
            if not integer(rec.bag_ns):
                issue("invalid_bag_timestamp", "bag receive timestamp must be nonnegative integer", role=role)
            if not isinstance(rec.payload, dict) or "__decode_error__" in rec.payload:
                issue("source_decode_error", "research message did not decode", role=role)
    for role, topic in cfg.topics.items():
        if topic_types.get(topic) != TOPIC_TYPES[role]:
            issue("topic_missing_or_wrong_type", "four research topic definitions required", role=role)
        if cfg.expected_counts is not None and cfg.expected_counts.get(topic) != counts[topic]:
            issue("metadata_decoded_count_mismatch", "selected topic record count differs from storage metadata", scope="recording", role=role)
    spec = context.get("reference_prediction_contract", {})
    extension = session.get("reference_prediction", {})
    if spec.get("enabled") is not True or extension.get("enabled") is not True:
        issue("reference_extension_not_enabled", "legacy baseline without reference observations cannot certify extension", scope="recording")
    policies = {"schema_version": SCHEMA, "matrix_layout": "k_major", "prediction_policy": "accepted_post_deadline_only",
                "record_policy": "solve_invoked_only"}
    for key, value in policies.items():
        if spec.get(key) != value or extension.get(key) != value:
            issue("reference_extension_policy_mismatch", "extension policy must match its frozen schema", scope="recording", field=key)
    if not sha(spec.get("nominal_config_hash")) or extension.get("nominal_config_hash") != spec.get("nominal_config_hash"):
        issue("nominal_config_identity_mismatch", "nominal effective asset identity differs or is absent")
    if not integer(spec.get("horizon_steps"), 1) or not finite(spec.get("prediction_dt")) or spec.get("prediction_dt", 0) <= 0:
        issue("model_config_unknown", "actual runtime horizon and dt are required")
    if not isinstance(spec.get("backend"), str) or not spec.get("backend"):
        issue("model_backend_unknown", "actual backend identity is required")
    for key in IDENTITY:
        if not isinstance(context.get(key), str) or not context.get(key) or session.get(key) != context.get(key):
            issue("session_identity_mismatch", "session and context must share complete identity", scope="recording", field=key)
    if not sha(context.get("config_hash")):
        issue("config_identity_invalid", "full configuration SHA256 required")
    if session.get("schema_version") != "p0-contract-v1":
        issue("wrong_session_schema", "three-stream session schema must remain v1", scope="recording")
    if session.get("normal_end") is not True or session.get("flushed") is not True or session.get("publish_errors") != 0:
        issue("session_end_unknown_or_unflushed", "normal complete source flush without publish errors required", scope="recording")
    if session.get("queue_dropped_total") != 0:
        issue("logger_queue_overflow", "source queue overflow or unknown count", scope="recording")
    if session.get("interrupted_cycle_sequence") != 0:
        issue("interrupted_cycle_at_session_end", "unfinished invocation prohibits completeness", scope="recording")
    source_counts = session.get("streams", {})
    start, end = session.get("start_steady_ns"), session.get("end_steady_ns")
    valid_capture = integer(start, 1) and integer(end, 1) and end >= start
    if not valid_capture:
        issue("session_capture_boundary_unknown", "ordered local steady capture boundaries required", scope="recording")
    indexed = {}
    for role in DEFAULT_TOPICS:
        seqs, index = [], {}
        previous_epoch, previous_sim = None, None
        for rec in streams[role]:
            p = rec.payload
            seq = p.get("sequence")
            seqs.append(seq)
            if integer(seq, 1) and seq not in index:
                index[seq] = p
            for key in IDENTITY:
                if p.get(key) != context.get(key):
                    issue("source_identity_mismatch", "research identity differs from current context", role=role, sequence=seq, field=key)
            schema = SCHEMA if role == "reference_prediction" else "p0-contract-v1"
            if p.get("schema_version") != schema:
                issue("source_schema_mismatch", "research schema differs from fixed role", role=role, sequence=seq)
            for key in ("clock_epoch", "clock_receive_steady_ns", "clock_age_ns"):
                if not integer(p.get(key)):
                    issue("invalid_clock_metadata", "clock epoch and local receive/age require nonnegative integers", role=role, field=key)
            sim, epoch = p.get("sim_time_ns"), p.get("clock_epoch")
            if not isinstance(sim, int) or isinstance(sim, bool) or p.get("clock_status") not in ("not_received", "observed", "paused", "reset", "jump"):
                issue("invalid_clock_metadata", "explicit integer simulation timestamp and recognized status required", role=role)
            if integer(epoch) and isinstance(sim, int) and not isinstance(sim, bool):
                if previous_epoch is not None and (epoch < previous_epoch or (epoch == previous_epoch and sim < previous_sim)):
                    issue("unsegmented_clock_regression", "simulation rollback must have a new source epoch", role=role)
                previous_epoch, previous_sim = epoch, sim
            if p.get("clock_status") == "not_received" and (sim != 0 or p.get("clock_receive_steady_ns") != 0):
                issue("invalid_clock_metadata", "unreceived clock must not invent observed timestamps", role=role)
        if seqs != list(range(1, len(seqs) + 1)):
            issue("sequence_gap_duplicate_or_regression", "each generated stream must be recorded exactly once from sequence 1", scope="recording", role=role)
        declared = source_counts.get(role, {})
        for key in ("generated", "emitted", "dropped", "first_sequence", "last_sequence"):
            if not integer(declared.get(key)):
                issue("source_summary_count_missing", "four-stream counter field required", scope="recording", role=role, field=key)
        if declared.get("generated") != len(seqs) or declared.get("emitted") != len(seqs) or declared.get("dropped") != 0:
            issue("source_recorded_count_mismatch", "generated/emitted/recorded counts differ or dropped", scope="recording", role=role)
        if declared.get("first_sequence") != (1 if seqs else 0) or declared.get("last_sequence") != len(seqs):
            issue("source_boundary_mismatch", "recorded prefix/suffix does not match source boundaries", scope="recording", role=role)
        indexed[role] = index
    if not integer(session.get("cycle_invocations_started")) or session.get("cycle_invocations_started") != len(streams["cycle"]):
        issue("started_completed_cycle_count_mismatch", "all armed timer invocations must complete", scope="recording")
    cycle_index, action_index = indexed["cycle"], indexed["applied"]
    for seq, cycle in cycle_index.items():
        if not isinstance(cycle.get("solve_invoked"), bool):
            issue("cycle_solve_invocation_unknown", "actual solve invocation requires an explicit boolean", cycle_sequence=seq)
        action = action_index.get(cycle.get("applied_sequence"))
        if action is None or action.get("cycle_sequence") != seq:
            issue("cycle_applied_link_missing", "every completed invocation binds its recorded applied event", cycle_sequence=seq)
    expected_solved = {seq for seq, p in cycle_index.items() if p.get("solve_invoked") is True}
    actual_solved, versions = [], {"path": {}, "profile": {}}
    last_version = {"path": 0, "profile": 0}
    freeze_times = []
    for rec in streams["reference_prediction"]:
        p = rec.payload
        sequence, cycle_seq = p.get("sequence"), p.get("cycle_sequence")
        actual_solved.append(cycle_seq)
        c = cycle_index.get(cycle_seq)
        if c is None:
            issue("reference_cycle_missing", "reference must bind one recorded CycleTiming", sequence=sequence)
            continue
        if c.get("solve_invoked") is not True:
            issue("reference_fabricated_for_no_solve", "standby cycles must not manufacture solve observations", sequence=sequence)
        for key in ("applied_sequence", "state_copy_steady_ns", "reference_ready_steady_ns", "solve_start_steady_ns", "solve_end_steady_ns",
                    "controller_state_6", "state_kind", "received_odom_sequence", "received_imu_sequence", "odom_stamp_ns", "imu_stamp_ns",
                    "clock_epoch", "sim_time_ns", "clock_receive_steady_ns", "clock_age_ns", "clock_status"):
            if p.get(key) != c.get(key):
                issue("reference_cycle_freeze_mismatch", "frozen reference input/source/timing must equal actual cycle", sequence=sequence, field=key)
        if not vector(p.get("controller_state_6"), 6):
            issue("controller_input_invalid", "six finite frozen controller values required", sequence=sequence)
        for key, ckey in (("solve_success", "success"), ("deadline_miss", "deadline_miss"), ("rejection_reason", "rejection_reason")):
            if p.get(key) != c.get(ckey):
                issue("reference_result_mismatch", "result must describe same post-deadline cycle", sequence=sequence, field=key)
        action = action_index.get(p.get("applied_sequence"))
        if action is None or action.get("cycle_sequence") != cycle_seq:
            issue("reference_applied_link_missing", "reference and applied command must bind the same cycle", sequence=sequence)
        times = [p.get(key) for key in ("state_copy_steady_ns", "reference_ready_steady_ns", "solve_start_steady_ns", "solve_end_steady_ns", "freeze_steady_ns")]
        if any(not integer(t, 1) for t in times) or times != sorted(times):
            issue("reference_steady_timing_invalid", "frozen observation times must be ordered within one steady domain", sequence=sequence)
        elif valid_capture and not start <= times[-1] <= end:
            issue("source_event_outside_capture", "reference freeze timestamp lies outside source session", scope="recording", sequence=sequence)
        freeze_times.append(p.get("freeze_steady_ns"))
        if p.get("nominal_config_hash") != spec.get("nominal_config_hash"):
            issue("nominal_config_identity_mismatch", "record must bind actual effective nominal asset", sequence=sequence)
        for key in ("horizon_steps", "prediction_dt", "backend"):
            if p.get(key) != spec.get(key):
                issue("model_config_mismatch", "record and frozen runtime model config differ", sequence=sequence, field=key)
        n = p.get("horizon_steps")
        n_valid = integer(n, 1)
        if (p.get("matrix_layout") != "k_major" or p.get("reference_rows") != 6 or not n_valid or
                p.get("reference_cols") != n + 1 or not vector(p.get("reference_data"), 6 * (n + 1) if n_valid else -1)):
            issue("reference_matrix_invalid", "actual reference must be finite k_major 6x(N+1)", sequence=sequence)
        # Index/version metadata describes the same locked container copy.
        path_size = p.get("path_size")
        nearest, offset, idx = p.get("nearest_index"), p.get("effective_start_offset"), p.get("start_index")
        offset_valid = (integer(p.get("configured_start_offset"), -2**31) and integer(offset, 1) and
                        offset == max(1, p.get("configured_start_offset", 0)))
        indices_valid = (integer(path_size, 1) and integer(nearest) and nearest < path_size and
                         idx == min(nearest + offset, path_size - 1)) if offset_valid else False
        if path_size == 0:
            indices_valid = nearest == -1 and idx == -1 and p.get("reference_mode") == "empty_path"
            if n_valid and p.get("reference_data") != [0.0] * (6 * (n + 1)):
                issue("empty_path_reference_not_zero", "actual empty-path builder returns the allocated zero reference", sequence=sequence)
        if not offset_valid or not indices_valid:
            issue("reference_index_metadata_invalid", "nearest/start indices must follow the frozen offset rule", sequence=sequence)
        if integer(path_size) and path_size < 2:
            warnings.append({"code": "solve_reference_path_not_eligible", "sequence": sequence,
                             "message": "actual solve observes fewer than two path points; a callback between eligibility check and reference build is a possible cause, not proved here"})
        for role, stampkey, known in (("path", "path_stamp_ns", True), ("profile", "profile_stamp_ns", p.get("profile_stamp_known"))):
            version = p.get(role + "_received_sequence")
            if not integer(version, 1 if role == "path" else 0) or version < last_version[role]:
                issue("reference_version_regression", "callback received container versions cannot regress", sequence=sequence, role=role)
            else:
                last_version[role] = version
                meta = (p.get(stampkey), p.get(role + "_size"), known)
                if version in versions[role] and versions[role][version] != meta:
                    issue("reference_container_version_mismatch", "same callback version cannot describe changed container metadata", sequence=sequence, role=role)
                versions[role][version] = meta
            if not integer(p.get(role + "_size")) or (known is True and not integer(p.get(stampkey), -1 if role == "path" else 0)):
                issue("reference_container_metadata_invalid", "received sizes/stamps must have explicit valid semantics", sequence=sequence, role=role)
        if not isinstance(p.get("profile_stamp_known"), bool) or not isinstance(p.get("profile_t0_known"), bool) or not finite(p.get("profile_t0")):
            issue("profile_metadata_invalid", "profile stamp/t0 availability must be explicit and finite", sequence=sequence)
        if p.get("profile_stamp_known") is False and p.get("profile_stamp_ns") != -1:
            issue("profile_unknown_stamp_fabricated", "unknown profile stamp uses the fixed -1 sentinel", sequence=sequence)
        if p.get("profile_t0_known") is False and p.get("profile_t0") != 0.0:
            issue("profile_unknown_t0_fabricated", "unavailable profile t0 must retain zero default without claiming a sample", sequence=sequence)
        if p.get("profile_synced") is True:
            if (p.get("profile_size") != path_size or p.get("profile_t0_known") is not True or p.get("reference_mode") != "profile_time"):
                issue("profile_mode_inconsistent", "synced time profile requires matching lengths and known t0", sequence=sequence)
        elif p.get("profile_synced") is False:
            expected_mode = "empty_path" if path_size == 0 else "cruise_arc_fallback"
            if p.get("profile_t0_known") is not False or p.get("reference_mode") != expected_mode:
                issue("profile_mode_inconsistent", "fallback arc mode must not invent profile t0", sequence=sequence)
        else:
            issue("profile_mode_inconsistent", "explicit profile synchronization boolean required", sequence=sequence)
        if not isinstance(p.get("profile_sync_reason"), str) or not p.get("profile_sync_reason"):
            issue("profile_sync_reason_missing", "profile synchronization decision reason required", sequence=sequence)
        accepted = p.get("solve_success") is True and p.get("deadline_miss") is False
        available = p.get("prediction_available")
        if not isinstance(p.get("solve_success"), bool) or not isinstance(p.get("deadline_miss"), bool) or not isinstance(available, bool):
            issue("prediction_result_boolean_invalid", "result and availability must be explicit booleans", sequence=sequence)
        if available is True:
            if not accepted or p.get("prediction_reason") != "accepted_solution":
                issue("rejected_prediction_fabricated", "failed/late results cannot supply accepted prediction", sequence=sequence)
            if (not n_valid or p.get("x_pred_rows") != 6 or p.get("x_pred_cols") != n + 1 or
                    not vector(p.get("x_pred_data"), 6 * (n + 1) if n_valid else -1) or p.get("u_pred_rows") != 2 or
                    p.get("u_pred_cols") != n or not vector(p.get("u_pred_data"), 2 * n if n_valid else -1)):
                issue("prediction_matrix_invalid", "available predictions must be finite X6x(N+1),U2xN", sequence=sequence)
        else:
            if any(p.get(key) != 0 for key in ("x_pred_rows", "x_pred_cols", "u_pred_rows", "u_pred_cols")) or p.get("x_pred_data") != [] or p.get("u_pred_data") != []:
                issue("unavailable_prediction_not_empty", "unavailable prediction must have zero shapes and empty arrays", sequence=sequence)
            reason = "prediction_missing_or_invalid" if accepted else "solve_rejected"
            if p.get("prediction_reason") != reason:
                issue("prediction_reason_mismatch", "availability reason must follow post-deadline result", sequence=sequence)
        ledger.append({"sequence": sequence, "cycle_sequence": cycle_seq, "applied_sequence": p.get("applied_sequence"),
                       "clock_epoch": p.get("clock_epoch"), "freeze_steady_ns": p.get("freeze_steady_ns"),
                       "prediction_available": available, "reference_mode": p.get("reference_mode"),
                       "status": "end_unknown", "plant_execution_observed": False})
    if len(actual_solved) != len(set(actual_solved)):
        issue("duplicate_reference_for_cycle", "each actual solve may have exactly one reference observation", scope="recording")
    if set(actual_solved) != expected_solved:
        issue("solve_reference_coverage_mismatch", "all and only solve_invoked cycles require observations", scope="recording",
              expected=sorted(expected_solved), observed=actual_solved)
    if actual_solved != sorted(expected_solved):
        issue("solve_reference_order_mismatch", "observations must preserve the actual invocation order", scope="recording")
    if any(not integer(t, 1) for t in freeze_times) or any(b <= a for a, b in zip(freeze_times, freeze_times[1:]) if integer(a) and integer(b)):
        issue("reference_freeze_order_invalid", "completed source observations must have increasing local freeze timestamps")
    for left, right in zip(ledger, ledger[1:]):
        a, b = left["freeze_steady_ns"], right["freeze_steady_ns"]
        if integer(a, 1) and integer(b, 1) and b > a and left["clock_epoch"] == right["clock_epoch"]:
            left.update(status="next_reference_observed", next_freeze_steady_ns=b,
                        source_observation_gap_ns=b-a)
        else:
            left["status"] = "source_boundary_invalid"
    # These are source observation boundaries, never actuator hold intervals.
    publisher_verified = (isinstance(publisher_report, dict) and publisher_report.get("schema") == "p0-publisher-contract-report/1"
                          and publisher_report.get("passed") is True and publisher_report.get("source_event_contract_valid") is True
                          and publisher_report.get("recorded_stream_complete") is True)
    if publisher_verified:
        for key in ("run_id", "producer_instance_id", "baseline_id"):
            if publisher_report.get(key) != context.get(key):
                publisher_verified = False
        publisher_verified = publisher_verified and publisher_report.get("original_bag_unchanged") is True
    if not publisher_verified:
        warnings.append({"code": "publisher_report_missing_or_unverified", "message": "raw sensor/physical stream checks require the matching readonly publisher report"})
    evidence_verified, evidence_failures = evidence_check(solver_test_evidence, context)
    warnings.extend({"code": code, "message": "external frozen solver test evidence not verified"} for code in evidence_failures)
    source_valid = not any(f["scope"] == "source" for f in failures)
    complete = not failures
    report = {"schema": "p0-reference-prediction-report/1", "passed": complete, "exit_code": 0 if complete else 2,
              "four_research_streams_complete": complete, "source_reference_contract_valid": source_valid,
              "publisher_contract_verified": publisher_verified,
              "combined_recording_contract_verified": complete and publisher_verified,
              "frozen_solver_test_evidence_verified": evidence_verified,
              "actual_solve_input_verified": complete and publisher_verified and evidence_verified and context.get("frozen_baseline_verified") is True,
              "actual_solve_input_verification_basis": "same-cycle frozen observations plus externally hash-bound real C++ solver capture tests",
              "raw_path_profile_callback_replay_verified": False, "candidate_prediction_available_count": sum(p.get("prediction_available") is True for p in indexed["reference_prediction"].values()),
              "reference_path_eligibility_anomaly_count": sum(integer(p.get("path_size")) and p["path_size"] < 2 for p in indexed["reference_prediction"].values()),
              "source_stream_counts": source_counts, "actual_message_counts": dict(counts),
              "metadata_message_counts": cfg.expected_counts, "topic_types": topic_types,
              "run_id": context.get("run_id"), "producer_instance_id": context.get("producer_instance_id"), "baseline_id": context.get("baseline_id"),
              "last_reference_right_boundary": "end_unknown" if ledger else "no_reference_observation",
              "plant_acceptance_observed": False, "force_measured": False, "execution_atomicity_proven": False,
              "exact_execution_timing_available": False, "gp_labels_ready": False,
              "failures": failures, "warnings": warnings, "limitations": LIMITATIONS}
    return report, ledger

def read_bag(bag, cfg):
    """Actual metadata storage; deserialize only four research topics, readonly."""
    import yaml
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.utilities import get_message
    info = yaml.safe_load((bag / "metadata.yaml").read_text(encoding="utf-8"))["rosbag2_bagfile_information"]
    storage, paths = info["storage_identifier"], info["relative_file_paths"]
    if not isinstance(storage, str) or not storage or not isinstance(paths, list) or not paths:
        raise ValueError("metadata storage identity/files absent")
    for name in paths:
        if not isinstance(name, str) or not name:
            raise ValueError("invalid storage filename")
        path = (bag / name).resolve()
        if not path.is_relative_to(bag) or not path.is_file():
            raise ValueError("storage file missing or outside bag")
    types, counts = {}, {}
    for item in info["topics_with_message_count"]:
        meta = item["topic_metadata"]
        if meta["name"] in types:
            raise ValueError("duplicate metadata topic")
        types[meta["name"]], counts[meta["name"]] = meta["type"], item["message_count"]
    if any(not integer(v) for v in counts.values()) or not integer(info["message_count"]) or info["message_count"] != sum(counts.values()):
        raise ValueError("metadata message counts invalid")
    cfg.expected_counts = {topic: counts.get(topic, 0) for topic in cfg.topics.values()}
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
                rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"))
    actual_types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    if actual_types != types:
        raise ValueError("storage definitions differ from metadata")
    classes = {topic: get_message(TOPIC_TYPES[role]) for role, topic in cfg.topics.items() if types.get(topic) == TOPIC_TYPES[role]}
    records, actual_counts = [], Counter()
    while reader.has_next():
        topic, serialized, timestamp = reader.read_next()
        actual_counts[topic] += 1
        if topic in cfg.topics.values():
            payload = {}
            if topic in classes:
                try:
                    payload = dict(message_to_ordereddict(deserialize_message(serialized, classes[topic])))
                except Exception as exc:
                    payload = {"__decode_error__": f"{type(exc).__name__}: {exc}"}
            records.append(Record(topic, int(timestamp), payload))
    if dict(actual_counts) != {k: v for k, v in counts.items() if v}:
        raise ValueError("actual whole-bag record counts differ from metadata")
    return records, types, {"storage_id": storage, "storage_files": paths, "metadata_total_message_count": info["message_count"],
                            "decoded_roles": list(DEFAULT_TOPICS), "bag_time_domain": "external run_context; no cross-domain subtraction"}

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--session-summary", type=Path, required=True)
    parser.add_argument("--run-context", type=Path, required=True)
    parser.add_argument("--publisher-contract-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    for role, topic in DEFAULT_TOPICS.items():
        parser.add_argument("--" + role.replace("_", "-") + "-topic", default=topic)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1
    bag, output = args.bag.expanduser().resolve(), args.output_dir.expanduser().resolve()
    if output == bag or output.is_relative_to(bag) or output.exists():
        print("reports require a new directory outside the original bag", file=sys.stderr)
        return 1
    before, report, ledger = None, {}, []
    try:
        if not bag.is_dir():
            raise ValueError("existing bag directory required")
        before = hash_bag(bag)
        session, context, pub = load_json(args.session_summary), load_json(args.run_context), load_json(args.publisher_contract_report)
        if pub.get("bag_hash_before") != before or pub.get("bag_hash_after") != before:
            raise ValueError("publisher report is not bound to this unchanged bag")
        cfg = Config(topics={role: getattr(args, role + "_topic") for role in DEFAULT_TOPICS})
        records, types, reading = read_bag(bag, cfg)
        evidence = None
        binding = context.get("reference_prediction_contract", {}).get("solver_test_evidence", {})
        if binding.get("path"):
            path = Path(binding["path"])
            if not path.is_absolute():
                raise ValueError("solver evidence path must be absolute")
            evidence = load_json(path)
            evidence["__verified_file_sha256"] = hash_file(path)
        report, ledger = validate_events(records, types, session, context, cfg, pub, evidence)
        report.update(reading=reading, publisher_report_path=str(args.publisher_contract_report.resolve()),
                      publisher_report_sha256=hash_file(args.publisher_contract_report))
        after = hash_bag(bag)
        report.update(bag_hash_before=before, bag_hash_after=after, original_bag_unchanged=before == after)
        if before != after:
            report["failures"].append({"code": "original_bag_changed", "scope": "recording", "message": "bag bytes changed during readonly check"})
            for key in ("passed", "four_research_streams_complete", "combined_recording_contract_verified", "actual_solve_input_verified"):
                report[key] = False
            report["exit_code"] = 2
        code = report["exit_code"]
    except Exception as exc:
        report = {"schema": "p0-reference-prediction-report/1", "passed": False, "exit_code": 1,
                  "configuration_or_read_error": f"{type(exc).__name__}: {exc}", "four_research_streams_complete": False,
                  "actual_solve_input_verified": False, "plant_acceptance_observed": False, "force_measured": False,
                  "execution_atomicity_proven": False, "exact_execution_timing_available": False, "gp_labels_ready": False,
                  "limitations": LIMITATIONS}
        if before is not None:
            try:
                after = hash_bag(bag)
                report.update(bag_hash_before=before, bag_hash_after=after, original_bag_unchanged=before == after)
            except Exception as exc_hash:
                report["bag_hash_after_error"] = str(exc_hash)
        code = 1
    try:
        output.mkdir(parents=True, exist_ok=False)
        (output / "reference_prediction_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        with (output / "reference_observation_ledger.jsonl").open("w", encoding="utf-8") as stream:
            for row in ledger:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    except (OSError, ValueError) as exc:
        print("cannot write external report: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"passed": report["passed"], "exit_code": code, "output_dir": str(output),
                      "actual_solve_input_verified": report.get("actual_solve_input_verified")}, ensure_ascii=False))
    return code

if __name__ == "__main__":
    raise SystemExit(main())
