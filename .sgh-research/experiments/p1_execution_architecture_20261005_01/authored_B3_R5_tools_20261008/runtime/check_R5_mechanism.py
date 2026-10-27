"""Fail-closed finite R5 logger-pressure mechanism gate; no total qualification."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re

from check_p1_witness import analyze as witness_analyze, load_json

SCHEMA = "p1-R5-mechanism-check-v1"
SCOPE = "finite_R5_log_pressure_mechanism_only"
MAX_SOURCE_BYTES, MAX_LINE_BYTES, MAX_ROWS = 64 * 1024 * 1024, 256 * 1024, 200000
U64_MAX, I64_MAX = (1 << 64) - 1, (1 << 63) - 1
VERSIONS = ("task_generation", "model_generation", "config_generation", "schedule_generation")
JOB_ID = ("job_id", "target_tick", *VERSIONS, "clock_epoch")
LIMITS = {"native_prearm_min": 2, "ticks_before_failure_min": 5,
          "observation_max_ns": 220000000, "tick_jitter_max_ns": 20000000,
          "pause_max_ns": 5000000000, "release_grace_max_ns": 2500000000,
          "invalidation_max_after_stop_ns": 220000000}
RESPONSE_RULE = "latest_known_failed_false_before_first_sink_failure"
SHUTDOWN_RULE = "natural_failure_stopping_to_exit_or_logical_release_to_close"
SINK_SHA256 = "4a607820a5e7ce1f047d559bcde72965926f4e9d7d86a8ec20cd39add03c2a79"
REGULATOR_TYPES = {"startup", "recording_ready", "recording_ready_failed", "worker_unusable_transition",
                  "odom_admission", "imu_admission", "path_version", "profile_version", "clock", "resource_rejected",
                  "capability_admission", "candidate_registration", "job_not_submitted", "job", "job_publish_result",
                  "decision", "scheduler_skipped_ticks", "active_watchdog", "prepare_pending_replaced",
                  "regulator_shutdown", "source_summary"}
WORKER_TYPES = {"pending_discarded", "worker_summary", "worker_recording_ready", "worker_recording_ready_failed",
                "resource_rejected", "job_rejected", "job_received", "pending_replaced", "pending_expired_before_native",
                "controlled_pre_native_barrier", "native_result_resource_oversize", "candidate", "candidate_publish_result",
                "terminal_exception", "terminal_numerical_failure", "terminal_pending_discarded"}


def uint(x):
    return type(x) is int and 0 <= x <= U64_MAX


def ns(x):
    return type(x) is int and 0 < x <= I64_MAX


def hexhash(x):
    return type(x) is str and re.fullmatch("[0-9a-f]{64}", x) is not None


def exact(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return set(a) == set(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def domain(value):
    pending, count = [(value, 0)], 0
    while pending:
        x, depth = pending.pop()
        count += 1
        if depth > 12 or count > 32768:
            raise ValueError("source JSON shape exceeds budget")
        if type(x) is dict:
            if any(type(k) is not str for k in x):
                raise ValueError("source JSON keys must be strings")
            pending.extend((v, depth + 1) for v in x.values())
        elif type(x) is list:
            pending.extend((v, depth + 1) for v in x)
        elif type(x) is int and not -(1 << 63) <= x <= U64_MAX:
            raise ValueError("source JSON integer domain")
        elif type(x) is float and not math.isfinite(x):
            raise ValueError("source JSON nonfinite number")
        elif type(x) is str:
            x.encode("utf-8")
        elif x is not None and type(x) not in (bool, int, float):
            raise ValueError("source JSON unsupported value")


def load_source(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate source JSON key")
            out[k] = v
        return out
    def constant(value):
        raise ValueError("nonfinite source JSON constant")
    rows, total, digest = [], 0, hashlib.sha256()
    with Path(path).open("rb") as source:
        while raw := source.readline(MAX_LINE_BYTES + 1):
            total += len(raw)
            if len(raw) > MAX_LINE_BYTES or total > MAX_SOURCE_BYTES or len(rows) >= MAX_ROWS or not raw.endswith(b"\n"):
                raise ValueError("source budget or unclosed line")
            digest.update(raw)
            try:
                row = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
            except RecursionError as error:
                raise ValueError("source parser nesting budget") from error
            domain(row)
            if type(row) is not dict or type(row.get("type")) is not str:
                raise ValueError("source line must be typed object")
            rows.append(row)
    if not rows:
        raise ValueError("source empty")
    return rows, digest.hexdigest()


def empty_report(run_id=None):
    return {"schema": SCHEMA, "scope": SCOPE, "run_id": run_id,
            "passed": False, "mechanism_passed": False,
            "expected_log_overflow_mechanism_passed": False,
            "R5_complete": False, "normal_contract_complete": False,
            "source_bag_contract_complete": False, "raw_bag_complete": False,
            "worker_source_complete": False, "owned_process_lifecycle_verified": False,
            "C0_performance_comparison_verified": False, "execute_qualified": False,
            "M0b_formally_complete": False, "M4_complete": False, "F6_complete": False, "P1_complete": False,
            "plant_acceptance_observed": False, "publisher_rate_verification_available": False,
            "physical_execute_release_enabled": False, "issues": []}


def _analyze(witness, expected_header, regulator_events, worker_events, context, summary, policy):
    """No clipping of either source stream; expected regulator drops remain explicit."""
    h = expected_header if type(expected_header) is dict else {}
    report = empty_report(h.get("run_id"))
    issues, counts, observations = report["issues"], {}, {}
    def require(ok, code, **detail):
        if not ok:
            issues.append({"code": code, **detail})
    basis = witness_analyze(witness, expected_header)
    report["basis_witness_check"] = basis
    require(basis["passed"] is True, "basis_witness_incomplete")
    report["counts"], report["observations"] = counts, observations
    c = context if type(context) is dict else {}
    s = summary if type(summary) is dict else {}
    p = policy if type(policy) is dict else {}
    require(p.get("schema") == "p1-R5-predeclared-policy-v1", "policy_schema")
    require(c.get("schema") == "p1-R5-pressure-context-v1", "context_schema")
    require(s.get("schema") == "p1-R5-pressure-runner-summary-v1", "summary_schema")
    for x in (c, s, p):
        require(type(x.get("run_id")) is str and x["run_id"] == h.get("run_id"), "run_identity")
    require(c.get("mode") == p.get("mode") == "no_output", "no_output_mode")
    for name, expected in (("declared_duration_ns", 15000000000), ("log_capacity", 512), ("test_sink_pause_ms", 5000)):
        require(type(p.get(name)) is int and p[name] == expected, "policy_value", field=name)
    require(p.get("response_rule") == RESPONSE_RULE, "policy_response_rule")
    require(p.get("invalidation_boundary") == "first_invalidation_observed", "policy_invalidation_boundary")
    require(p.get("shutdown_rule") == SHUTDOWN_RULE, "policy_shutdown_rule")
    require(p.get("window_origin") == "arm_publish_start_ns", "policy_window_origin")
    require(hexhash(p.get("C0_evidence_sha256")), "policy_C0_evidence_pin")
    require(type(p.get("limits")) is dict and exact(p["limits"], LIMITS), "predeclared_limits")
    queue_proof = p.get("queue_overflow_proof") if type(p.get("queue_overflow_proof")) is dict else {}
    require(queue_proof.get("kind") == "pinned_capacity_rejection_branch_and_no_overcapacity_invariant"
            and type(queue_proof.get("capacity")) is int and queue_proof["capacity"] == 512
            and queue_proof.get("sink_source_sha256") == SINK_SHA256
            and exact(queue_proof.get("required_phase"), {"event_code": 3, "observation_code": 5})
            and queue_proof.get("required_summary_dropped_positive") is True
            and queue_proof.get("actual_depth_trace_available") is False
            and queue_proof.get("max_depth_above_capacity_allowed") is False, "pinned_queue_path_proof")
    hooks = p.get("hooks") if type(p.get("hooks")) is dict else {}
    require(exact(hooks, {k: 0 for k in ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms", "test_tick_block_ms")})
            and p.get("witness_enabled") is True, "policy_hooks_and_witness")
    pins = p.get("pins") if type(p.get("pins")) is dict else {}
    for key, header_key in (("contract_sha256", "contract_sha256"), ("diagnostic_source_sha256", "source_sha256"),
                            ("regulator_binary_sha256", "binary_sha256"), ("worker_binary_sha256", "worker_binary_sha256")):
        require(hexhash(pins.get(key)) and pins[key] == h.get(header_key), "policy_asset_pin", field=key)
    require(pins.get("boot_id") == h.get("boot_id") == c.get("boot_id"), "boot_identity")
    require(c.get("contract_sha256") == h.get("contract_sha256"), "contract_identity")
    for key in ("runner_sha256", "supervisor_sha256"):
        require(hexhash(pins.get(key)) and c.get(key) == pins[key], "runtime_pin", field=key)
    assets = c.get("binaries") if type(c.get("binaries")) is dict else {}
    for role, key in (("regulator", "binary_sha256"), ("worker", "worker_binary_sha256")):
        a = assets.get(role) if type(assets.get(role)) is dict else {}
        require(a.get("sha256") == h.get(key) and hexhash(a.get("sha256")), "context_binary_pin", role=role)
    src = c.get("diagnostic_source") if type(c.get("diagnostic_source")) is dict else {}
    require(src.get("sha256") == h.get("source_sha256") and hexhash(src.get("sha256")), "context_source_pin")
    fixed = c.get("fixed_witness") if type(c.get("fixed_witness")) is dict else {}
    require(fixed.get("enabled") is True and type(fixed.get("test_sink_pause_ms")) is int and fixed["test_sink_pause_ms"] == 5000, "witness_pressure_enabled")
    dec = c.get("declaration") if type(c.get("declaration")) is dict else {}
    require(type(dec.get("duration_s")) in (int, float) and dec["duration_s"] == 15, "finite_15s_declaration")
    require(dec.get("pressure_window_origin") == "arm_publish_start_ns", "pressure_window_origin")
    require(dec.get("expected_fault") == "sink_logger_pause_overflow" and dec.get("execute_qualified") is False, "expected_pressure_declaration")
    for key in ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms", "test_tick_block_ms"):
        require(type(dec.get(key)) is int and dec[key] == 0, "unrelated_hook_nonzero_or_unknown", field=key)
    require(type(dec.get("test_sink_pause_ms")) is int and dec["test_sink_pause_ms"] == 5000, "declared_pause")
    # Domain errors invalidate full inputs, including unused rows; summaries never substitute for rows.
    groups = []
    for label, events in (("regulator", regulator_events), ("worker", worker_events)):
        grouped = {}
        require(type(events) is list and 0 < len(events) <= MAX_ROWS, "source_root", stream=label)
        for index, e in enumerate(events if type(events) is list else []):
            try:
                domain(e)
            except (ValueError, UnicodeError) as error:
                require(False, "source_domain", stream=label, index=index, error=str(error))
                continue
            if type(e) is not dict or type(e.get("type")) is not str:
                require(False, "source_row_type", stream=label, index=index)
                continue
            require(e["type"] in (REGULATOR_TYPES if label == "regulator" else WORKER_TYPES), "source_unknown_type", stream=label, index=index)
            require(e["type"] != "controlled_pre_native_barrier", "unrelated_native_barrier_event")
            grouped.setdefault(e["type"], []).append(e)
        groups.append(grouped)
    reg, worker = groups
    def one(group, kind, required=True):
        rows = group.get(kind, [])
        require(len(rows) == 1 if required else len(rows) <= 1, "source_event_cardinality", event=kind)
        return rows[0] if len(rows) == 1 else {}
    terminal = one(reg, "source_summary")
    if terminal:
        require(regulator_events[-1] is terminal, "source_summary_not_terminal")
        generated, emitted, dropped = (terminal.get(k) for k in ("generated", "emitted", "dropped"))
        require(all(uint(v) for v in (generated, emitted, dropped)) and dropped > 0
                and generated == emitted + dropped and emitted == len(regulator_events) - 1, "pressure_source_counts")
        require(terminal.get("normal_source_complete") is False and ns(terminal.get("finished_ns")), "pressure_source_terminal")
        counts.update(source_generated=generated, source_emitted=emitted, source_dropped=dropped)
    startup = one(reg, "startup")
    for key, val in (("run_id", h.get("run_id")), ("boot", h.get("boot_id")), ("contract_hash", h.get("contract_sha256")),
                     ("mode", "no_output"), ("clock", "CLOCK_MONOTONIC")):
        require(type(startup.get(key)) is str and startup[key] == val, "startup_identity", field=key)
    require(startup.get("diagnostic_only") is True and type(startup.get("physical_publisher_endpoints")) is int and startup["physical_publisher_endpoints"] == 0, "startup_physical_endpoints")
    arm = s.get("pressure_arm") if type(s.get("pressure_arm")) is dict else {}
    require(arm.get("schema") == "p1-R5-pressure-arm-v1", "arm_schema")
    for key, val in (("run_id", h.get("run_id")), ("boot_id", h.get("boot_id")), ("contract_sha256", h.get("contract_sha256"))):
        require(type(arm.get(key)) is str and arm[key] == val, "arm_identity", field=key)
    require(type(arm.get("arm_attempts")) is int and arm["arm_attempts"] == 1 and arm.get("publish_success") is True, "arm_once_publication")
    require(ns(arm.get("publish_start_ns")) and ns(arm.get("publish_end_ns")) and arm["publish_start_ns"] <= arm["publish_end_ns"], "arm_publication_times")
    # Stop dereferencing unverified Witness rows; retain all independent earlier failures.
    if not basis["schema_valid"]:
        return report
    w = witness
    ticks, submits, acts, phases = (w[k] for k in ("tick", "submit", "activation", "phase"))
    def phase(kind, observer, required=True):
        rows = [r for r in phases if r["event_code"] == kind and r["observation_code"] == observer]
        require(len(rows) == 1 if required else len(rows) <= 1, "phase_cardinality", event=kind, observer=observer)
        return rows[0] if len(rows) == 1 else {}
    allowed = {(1, 5), (2, 5), (3, 5), (4, 5), (4, 2), (5, 1), (5, 3), (6, 5), (7, 6), (8, 1), (9, 2)}
    for r in phases:
        require((r["event_code"], r["observation_code"]) in allowed, "phase_observer_path", sequence=r["sequence"])
        if r["observation_code"] == 5:
            require(r["admission_slots"] == -1 and all(r[k] is None for k in ("candidate_present", "pending_present", "stopping")), "sink_must_not_claim_business_state")
            require(type(r["failed"]) is bool and type(r["pause_active"]) is bool, "sink_known_own_state")
        else:
            require(r["admission_slots"] >= 0 and all(type(r[k]) is bool for k in ("candidate_present", "pending_present", "failed", "stopping", "pause_active")), "business_state_unknown")
        if r["event_code"] == 4:
            require(r["failed"] is True, "source_failure_phase_without_failed")
    armed, begin, overflow, failed, end, close, invalid = (phase(a, b) for a, b in ((1, 5), (2, 5), (3, 5), (4, 5), (6, 5), (7, 6), (8, 1)))
    for kind, obs in ((4, 2), (5, 1), (5, 3), (9, 2)):
        phase(kind, obs, required=kind == 9)
    stops = [r for r in phases if r["event_code"] == 5 and r["observation_code"] in (1, 3)]
    require(bool(stops), "business_stopping_missing")
    stop = min(stops, key=lambda r: r["ns"]) if stops else {}
    if not all((armed, begin, overflow, failed, end, close, invalid, stop)) or not ns(arm.get("publish_start_ns")):
        return report
    arm_ns, fail_ns, stop_ns = arm["publish_start_ns"], min(overflow["ns"], failed["ns"]), stop["ns"]
    require(arm_ns <= armed["ns"] <= begin["ns"] <= overflow["ns"] <= failed["ns"] <= close["ns"]
            and begin["ns"] <= stop_ns <= close["ns"], "pressure_phase_time_order")
    require(armed["failed"] is False and armed["pause_active"] is False and begin["failed"] is False and begin["pause_active"] is True, "pressure_begin_state")
    require(overflow["failed"] is True and overflow["pause_active"] is True and failed["failed"] is True and failed["pause_active"] is True, "pressure_failure_state")
    require(end["pause_active"] is False and end["failed"] is True and overflow["ns"] <= end["ns"] <= close["ns"], "pause_end_state_or_order")
    pause_span = end["ns"] - begin["ns"]
    require(0 < pause_span <= LIMITS["pause_max_ns"], "pause_time_budget")
    require(all(r["failed"] is True and r["stopping"] is True for r in stops), "stopping_commit_state")
    require(invalid["failed"] is True and invalid["stopping"] is True and invalid["candidate_present"] is False and invalid["admission_slots"] == 0 and invalid["pending_present"] is False, "invalidation_not_real_clean")
    require(stop_ns <= invalid["ns"] <= stop_ns + LIMITS["invalidation_max_after_stop_ns"], "invalidation_boundary_time")
    require(close["failed"] is True and close["stopping"] is True and close["candidate_present"] is False and close["admission_slots"] == 0 and close["pending_present"] is False and close["pause_active"] is False, "close_not_real_clean")
    require(terminal and ns(terminal.get("finished_ns")) and end["ns"] <= terminal["finished_ns"] <= close["ns"], "source_terminal_after_pause_before_close")
    before_failure_ticks = [r for r in ticks if begin["ns"] <= r["start_ns"] <= r["end_ns"] < fail_ns and r["failed_start"] is False and r["failed_end"] is False and r["stopping_start"] is False and r["stopping_end"] is False]
    require(len(before_failure_ticks) >= LIMITS["ticks_before_failure_min"], "pause_ticks_before_failure_insufficient")
    require(all(r["skipped_ticks"] == 0 and r["start_ns"] - r["planned_ns"] <= LIMITS["tick_jitter_max_ns"] for r in ticks), "tick_jitter_or_skips")
    # Timestamp is sampled before the failed read in every selected frozen-code path.
    # Monotonic false->true gives F>=L. Late SourceFailure timestamps are upper bounds only.
    false_times = []
    for r in ticks:
        for time_key, flag in (("start_ns", "failed_start"), ("end_ns", "failed_end")):
            if r[flag] is False:
                false_times.append(r[time_key])
    for rows in (submits, acts):
        false_times.extend(r["commit_ns"] for r in rows if r["failed"] is False)
    false_times.extend(r["ns"] for r in phases if r["failed"] is False)
    # True sink failure is monotonic; false reads after its known upper bound are invalid evidence.
    require(not any(t >= fail_ns for t in false_times), "failed_false_after_known_failure")
    pre_failure_false_times = [t for t in false_times if t <= fail_ns]
    lower = max(pre_failure_false_times) if pre_failure_false_times else None
    response = stop_ns - lower if lower is not None else None
    require(lower is not None and 0 <= response <= LIMITS["observation_max_ns"], "failure_response_conservative_bound")
    require(not any(r["commit_ns"] >= stop_ns for r in submits), "submit_after_stopping")
    require(not any(r["commit_ns"] >= stop_ns and r["accepted"] for r in acts), "accepted_activation_after_stopping")
    require(not any(r["stopping"] for r in submits), "submit_at_stopping_snapshot")
    require(not any(r["accepted"] and (r["stopping"] or r["commit_ns"] >= fail_ns) for r in acts), "accepted_after_failure_or_stopping")
    counts.update(ticks=len(ticks), submits=len(submits), activation_attempts=len(acts), accepted_activations=sum(r["accepted"] for r in acts),
                  rejected_activations=sum(not r["accepted"] for r in acts), rejected_after_stopping=sum(not r["accepted"] and r["commit_ns"] >= stop_ns for r in acts),
                  submit_failed_after_authorization_snapshots=sum(r["failed"] for r in submits),
                  accepted_failed_after_commit_snapshots=sum(r["accepted"] and r["failed"] for r in acts),
                  whole_pause_ticks_before_failure=len(before_failure_ticks))
    observations.update(pause_begin_ns=begin["ns"], pause_end_ns=end["ns"], pause_span_ns=pause_span,
                        queue_overflow_ns=overflow["ns"], source_failure_phase_ns=failed["ns"], first_stopping_ns=stop_ns,
                        latest_known_failed_false_ns=lower, stopping_response_conservative_upper_ns=response,
                        stopping_minus_source_failure_phase_ns=stop_ns - failed["ns"], invalidation_ns=invalid["ns"], close_ns=close["ns"],
                        queue_capacity_proof="pinned_DiagSink_add_full_capacity_branch_and_positive_terminal_dropped", queue_capacity=512,
                        observed_queue_depth=None, failure_atomic_store_ns=None)
    # Full retained source rows are validated/partitioned, not falsely treated as a normal complete join.
    def job_ok(j):
        return (type(j) is dict and j.get("schema") == "p1-solve-job-v1" and
                all(type(j.get(k)) is str and j[k] == h.get(v) for k, v in (("run_id", "run_id"), ("boot_id", "boot_id"), ("contract_hash", "contract_sha256"), ("worker_instance", "worker_instance")))
                and all(uint(j.get(k)) for k in JOB_ID) and j["job_id"] > 0 and j["target_tick"] > 0)
    def indexed(events, key, code):
        out = {}
        for e in events:
            v = key(e)
            if not uint(v) or v == 0 or v in out:
                require(False, code)
            else:
                out[v] = e
        return out
    jobs = indexed(reg.get("job", []), lambda e: e.get("job", {}).get("job_id") if type(e.get("job")) is dict else None, "source_job_duplicate_or_id")
    registrations = indexed([r for r in reg.get("candidate_registration", []) if r.get("accepted_registration") is True], lambda e: e.get("job", {}).get("job_id") if type(e.get("job")) is dict else None, "registration_duplicate_or_id")
    candidates = indexed(worker.get("candidate", []), lambda e: e.get("job", {}).get("job_id") if type(e.get("job")) is dict else None, "candidate_duplicate_or_id")
    receipts = indexed(worker.get("job_received", []), lambda e: e.get("job", {}).get("job_id") if type(e.get("job")) is dict else None, "receipt_duplicate_or_id")
    publishes = indexed(worker.get("candidate_publish_result", []), lambda e: e.get("job_id"), "candidate_publication_duplicate_or_id")
    submit_by_id = {r["job_id"]: r for r in submits}
    decisions = indexed(reg.get("decision", []), lambda e: e.get("sequence"), "decision_duplicate_or_sequence")
    tick_by_seq = {r["sequence"]: r for r in ticks}
    decision_by_job = {}
    for d in decisions.values():
        require(d.get("schema") == "p1-execution-decision-v2" and d.get("mode") == "no_output"
                and d.get("diagnostic_only") is True and d.get("normal_contract_complete") is False
                and type(d.get("accepted")) is bool and type(d.get("reason")) is str
                and d.get("accepted") == (d.get("reason") == "")
                and all(uint(d.get(k)) for k in ("sequence", "tick", "job_id", *VERSIONS, "epoch", "skipped_ticks"))
                and all(ns(d.get(k)) for k in ("planned_ns", "start_ns", "activation_commit_ns", "end_ns"))
                and type(d.get("ready_commit_ns")) is int and 0 <= d["ready_commit_ns"] <= I64_MAX,
                "retained_decision_fields_or_types")
        require(all(type(d.get(k)) is str and d[k] == h.get(v) for k, v in (("run_id", "run_id"), ("boot_id", "boot_id"), ("contract_hash", "contract_sha256"), ("worker_instance", "worker_instance"))), "retained_decision_identity")
        r = tick_by_seq.get(d["sequence"])
        require(r is not None, "retained_decision_without_witness")
        if r:
            require(all(type(d.get(k)) is int and d[k] == r[v] for k, v in (("tick", "tick"), ("job_id", "job_id"), ("epoch", "clock_epoch"), ("planned_ns", "planned_ns"), ("start_ns", "start_ns"), *[(v, v) for v in VERSIONS])), "retained_decision_tick_identity")
            require(ns(d.get("end_ns")) and r["start_ns"] <= d["end_ns"] <= r["end_ns"] and type(d.get("accepted")) is bool, "retained_decision_time_or_result")
            require(ns(d.get("activation_commit_ns")) and r["start_ns"] <= d["activation_commit_ns"] <= d["end_ns"], "retained_decision_commit_time")
        if uint(d.get("job_id")) and d["job_id"] > 0:
            require(d["job_id"] not in decision_by_job, "duplicate_source_activation_job")
            decision_by_job[d["job_id"]] = d
    for jid, e in jobs.items():
        j, r = e.get("job"), submit_by_id.get(jid)
        require(job_ok(j) and r is not None, "retained_job_identity_or_witness")
        if job_ok(j) and r:
            require(all(j[k] == r[k] for k in JOB_ID), "retained_job_witness_identity")
            require(ns(e.get("submit_commit_ns")) and ns(e.get("publish_start_ns")) and e["submit_commit_ns"] <= r["commit_ns"] <= e["publish_start_ns"], "retained_submit_bracket")
    for r in reg.get("candidate_registration", []):
        require(job_ok(r.get("job")) and ns(r.get("ready_commit_ns")) and type(r.get("accepted_registration")) is bool
                and type(r.get("reason")) is str and r.get("accepted_registration") == (r.get("reason") == ""), "retained_registration_fields_or_types")
    prearm = []
    def finite_vector(x, n):
        return type(x) is list and len(x) == n and all(type(v) in (int, float) and math.isfinite(v) for v in x)
    for a in acts:
        if not a["accepted"] or a["commit_ns"] >= arm_ns:
            continue
        jid = a["job_id"]
        je, ca, re, rr, pub, d = jobs.get(jid), candidates.get(jid), receipts.get(jid), registrations.get(jid), publishes.get(jid), decision_by_job.get(jid)
        valid = all(type(e) is dict for e in (je, ca, re, rr, pub, d))
        if valid:
            j = je["job"]
            valid = (job_ok(j) and all(exact(e.get("job"), j) for e in (ca, re, rr)) and
                     ca.get("worker_instance") == re.get("worker_instance") == pub.get("worker_instance") == h.get("worker_instance") and
                     ca.get("backend") == "acados" and ca.get("solver_invoked") is True and ca.get("success") is True and ca.get("prediction_available") is True and type(ca.get("reason")) is str and
                     type(ca.get("backend_ms")) in (int, float) and math.isfinite(ca["backend_ms"]) and ca["backend_ms"] >= 0 and
                     all(ns(ca.get(k)) for k in ("receive_ns", "solve_start_ns", "solve_end_ns", "publish_start_ns")) and
                     ca["receive_ns"] == re.get("receive_ns") and ca["receive_ns"] <= ca["solve_start_ns"] <= ca["solve_end_ns"] <= ca["publish_start_ns"] <= rr.get("ready_commit_ns", 0) == a["ready_commit_ns"] <= a["commit_ns"] < arm_ns and
                     pub.get("success") is True and ns(pub.get("publish_start_ns")) and ns(pub.get("publish_end_ns")) and ca["solve_end_ns"] <= pub["publish_start_ns"] <= pub["publish_end_ns"] < arm_ns and
                     rr.get("accepted_registration") is True and rr.get("worker_instance") == h.get("worker_instance") and rr.get("solve_start_ns") == ca["solve_start_ns"] and rr.get("solve_end_ns") == ca["solve_end_ns"] and
                     finite_vector(ca.get("first_control"), 2) and finite_vector(ca.get("X"), 126) and finite_vector(ca.get("U"), 40) and exact(rr.get("first_control"), ca["first_control"]) and
                     d.get("accepted") is True and d.get("reason") == "" and d.get("activation_commit_ns") == a["commit_ns"] and d.get("ready_commit_ns") == a["ready_commit_ns"] and
                     all(j[k] == a[k] for k in JOB_ID) and all(d.get(k) == a[k] for k in VERSIONS))
        require(valid, "native_prearm_chain_incomplete", job_id=jid)
        if valid:
            prearm.append(jid)
    require(len(set(prearm)) >= LIMITS["native_prearm_min"], "native_prearm_minimum")
    claimed = arm.get("accepted_chains") if type(arm.get("accepted_chains")) is list else []
    claimed_ids = []
    require(len(claimed) >= 2, "arm_native_chains_missing")
    for claim in claimed:
        if type(claim) is not dict or not uint(claim.get("job_id")) or claim["job_id"] not in prearm:
            require(False, "arm_native_chain_not_independently_proven")
            continue
        jid = claim["job_id"]
        d = decision_by_job[jid]
        require(jid not in claimed_ids, "arm_native_chain_duplicate")
        claimed_ids.append(jid)
        require(all(claim.get(k) is True for k in ("native_solver_invoked", "native_success", "prediction_available"))
                and all(type(claim.get(k)) is int and claim[k] == d.get(k) for k in ("job_id", "tick", "sequence", "schedule_generation", "ready_commit_ns", "activation_commit_ns"))
                and ns(claim.get("typed_received_ns")) and d["activation_commit_ns"] <= claim["typed_received_ns"] < arm_ns,
                "arm_typed_accept_before_publication")
        require(all(exact(claim.get(k), value) for k, value in (("job", jobs[jid]["job"]), ("source_decision", d),
                ("worker_candidate", candidates[jid]), ("candidate_registration", registrations[jid]), ("candidate_publish_result", publishes[jid]))),
                "arm_chain_payload_mismatch")
    require(len(set(claimed_ids)) >= 2, "arm_native_distinct_minimum")
    prefixes = arm.get("source_prefixes") if type(arm.get("source_prefixes")) is dict else {}
    for label in ("regulator", "worker"):
        pref = prefixes.get(label) if type(prefixes.get(label)) is dict else {}
        require(type(pref.get("path")) is str and bool(pref["path"]) and hexhash(pref.get("sha256"))
                and type(pref.get("complete_bytes")) is int and 0 < pref["complete_bytes"] <= MAX_SOURCE_BYTES
                and type(pref.get("rows")) is int and 0 < pref["rows"] <= MAX_ROWS
                and type(pref.get("tail_bytes")) is int and 0 <= pref["tail_bytes"] <= MAX_LINE_BYTES,
                "arm_source_prefix_pin", stream=label)
    counts.update(native_prearm_accepted=len(set(prearm)), regulator_retained_rows=len(regulator_events), worker_rows=len(worker_events),
                  retained_decisions=len(decisions), retained_jobs=len(jobs), native_prearm_job_ids=prearm)
    wc = s.get("window_completion") if type(s.get("window_completion")) is dict else {}
    start = s.get("window_start") if type(s.get("window_start")) is dict else {}
    require(start.get("started_ns") == arm_ns and type(start.get("started_ns")) is int, "window_origin_matches_arm")
    require(ns(wc.get("window_finished_ns")) and wc.get("window_started_ns") == arm_ns and type(wc.get("observed_duration_ns")) is int and wc["window_finished_ns"] - arm_ns == wc["observed_duration_ns"] and 0 < wc["observed_duration_ns"] <= 15000000000 and type(wc.get("maximum_duration_ns")) is int and wc["maximum_duration_ns"] == 15000000000 and wc.get("normal_window_complete") is False, "finite_pressure_window")
    rc = s.get("actual_returncodes") if type(s.get("actual_returncodes")) is dict else {}
    require(type(rc.get("regulator")) is int and rc["regulator"] == 2, "expected_regulator_failure_rc")
    require(s.get("R5_complete") is False and s.get("execute_qualified") is False and s.get("normal_contract_complete") is False, "runner_scope_flags")
    observed = s.get("observed_regulator_exit") if type(s.get("observed_regulator_exit")) is dict else {}
    shutdown_span = None
    if s.get("release_kind") == "natural_failure_exit":
        require(type(observed.get("returncode")) is int and observed["returncode"] == 2 and ns(observed.get("observed_ns"))
                and close["ns"] <= observed["observed_ns"] <= wc.get("window_finished_ns", 0), "regulator_exit_observed")
        require(observed.get("natural") is True and s.get("release_requested_ns") is None and s.get("stop_release_ns") == observed.get("observed_ns") and wc.get("stop_reason") == s.get("stop_reason") == "expected_sink_failure_exit", "natural_exit_release_facts")
        if ns(observed.get("observed_ns")):
            shutdown_span = observed["observed_ns"] - stop_ns
    elif s.get("release_kind") == "logical_stop_publish":
        release = s.get("release_requested_ns")
        require(ns(release) and s.get("stop_release_ns") == release and stop_ns <= release <= close["ns"]
                and ns(wc.get("window_finished_ns")) and wc["window_finished_ns"] <= release, "logical_release_facts")
        if ns(release):
            shutdown_span = close["ns"] - release
    else:
        require(False, "release_kind_unknown")
    require(shutdown_span is not None and 0 <= shutdown_span <= LIMITS["release_grace_max_ns"], "shutdown_release_budget")
    observations["shutdown_grace_observed_upper_ns"] = shutdown_span
    report.update(passed=not issues, mechanism_passed=not issues, expected_log_overflow_mechanism_passed=not issues,
                  source_pressure_expected_incomplete=True, lifecycle_window_clipped=False)
    return report


def analyze(witness, expected_header, regulator_events, worker_events, context, summary, policy):
    try:
        return _analyze(witness, expected_header, regulator_events, worker_events, context, summary, policy)
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError) as error:
        h = expected_header if type(expected_header) is dict else {}
        result = empty_report(h.get("run_id"))
        result["issues"] = [{"code": "mechanism_value_domain_or_missing_field", "error": str(error)}]
        return result


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while data := source.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def verify_arm_prefixes(summary, paths):
    arm = summary.get("pressure_arm") if type(summary) is dict else None
    prefixes = arm.get("source_prefixes") if type(arm) is dict else None
    if type(prefixes) is not dict:
        raise ValueError("arm source-prefix inventory missing")
    consumed = {}
    for label in ("regulator", "worker"):
        p = prefixes.get(label)
        path = paths[label + "-source"]
        if (type(p) is not dict or type(p.get("path")) is not str or Path(p["path"]).resolve() != path.resolve()
                or type(p.get("complete_bytes")) is not int or not 0 < p["complete_bytes"] <= MAX_SOURCE_BYTES
                or not hexhash(p.get("sha256")) or type(p.get("rows")) is not int):
            raise ValueError("invalid arm source-prefix pin: " + label)
        with path.open("rb") as source:
            raw = source.read(p["complete_bytes"])
        if (len(raw) != p["complete_bytes"] or not raw.endswith(b"\n") or raw.count(b"\n") != p["rows"]
                or hashlib.sha256(raw).hexdigest() != p["sha256"]):
            raise ValueError("arm consumed source prefix changed: " + label)
        # The complete files have already passed strict duplicate/domain parsing.
        consumed[label] = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    claimed = arm.get("accepted_chains")
    if type(claimed) is not list or len(claimed) < 2:
        raise ValueError("arm native claims absent from consumed prefixes")
    for claim in claimed:
        if type(claim) is not dict:
            raise ValueError("arm native claim type")
        for label, fields in (("regulator", ("source_decision", "candidate_registration")),
                              ("worker", ("worker_candidate", "candidate_publish_result"))):
            if any(not any(exact(row, claim.get(field)) for row in consumed[label]) for field in fields):
                raise ValueError("arm native chain outside consumed prefix: " + label)
        if (not any(row.get("type") == "job" and exact(row.get("job"), claim.get("job")) for row in consumed["regulator"])
                or not any(row.get("type") == "job_received" and exact(row.get("job"), claim.get("job")) for row in consumed["worker"])):
            raise ValueError("arm Job/receipt outside consumed prefixes")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("context", "summary", "witness", "expected-header", "worker-source", "regulator-source", "policy", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    paths = {k: getattr(args, k.replace("-", "_")) for k in ("context", "summary", "witness", "expected-header", "worker-source", "regulator-source", "policy")}
    if args.output.resolve() in {p.resolve() for p in paths.values()}:
        parser.error("create-only report must not alias input")
    before, report = {}, empty_report()
    try:
        values = {}
        for key, path in paths.items():
            values[key], before[str(path)] = load_source(path) if key.endswith("-source") else load_json(path)
        verify_arm_prefixes(values["summary"], paths)
        report = analyze(values["witness"], values["expected-header"], values["regulator-source"], values["worker-source"], values["context"], values["summary"], values["policy"])
        report["arm_consumed_prefixes_verified"] = True
        after = {str(p): sha256_file(p) for p in paths.values()}
        report.update(input_sha256_before=before, input_sha256_after=after, raw_inputs_unchanged=before == after)
        if before != after:
            for key in ("passed", "mechanism_passed", "expected_log_overflow_mechanism_passed"):
                report[key] = False
            report["issues"].append({"code": "input_sha_changed_during_read"})
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, OverflowError) as error:
        old_issues = report.get("issues", [])
        report = empty_report(report.get("run_id"))
        report.update(reader_error=str(error), input_sha256_before=before, input_sha256_after={}, raw_inputs_unchanged=False)
        report["issues"] = old_issues + [{"code": "input_unreadable_or_invalid"}]
    report["checker_sha256"] = sha256_file(Path(__file__))
    try:
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2, ensure_ascii=False, allow_nan=False)
            output.write("\n")
    except OSError as error:
        print(json.dumps({"passed": False, "report_write_error": str(error)}))
        return 2
    print(json.dumps({k: report[k] for k in ("passed", "mechanism_passed", "issues")}))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
