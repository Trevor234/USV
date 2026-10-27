"""Full-lifecycle C0 regulator-source to fixed-Witness comparison only.

The independent header and driver context are required. No time window is cut
from either stream. Typed bag, worker-source closure, owned-process cleanup,
normal-window completion, C0 performance comparisons and R5 are separate gates.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re

from check_p1_witness import analyze as witness_analyze
from check_p1_witness import load_json as load_bounded_json

SCHEMA = "p1-C0-source-witness-comparison-v1"
SCOPE = "full_owned_lifecycle_regulator_source_to_fixed_witness"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_SOURCE_ROWS = 200000
MAX_DEPTH = 12
MAX_ROW_NODES = 32768
U64_MAX = (1 << 64) - 1
I64_MAX = (1 << 63) - 1
NORMAL_PHASES = {5, 7, 8, 9}
SUPPORTED_SOURCE_TYPES = {
    "startup", "recording_ready", "recording_ready_failed", "worker_unusable_transition",
    "odom_admission", "imu_admission", "path_version", "profile_version", "clock",
    "resource_rejected", "capability_admission", "candidate_registration",
    "job_not_submitted", "job", "job_publish_result", "decision",
    "scheduler_skipped_ticks", "active_watchdog", "prepare_pending_replaced",
    "regulator_shutdown", "source_summary",
}
VERSIONS = ("task_generation", "model_generation", "config_generation", "schedule_generation")
DECISION_REQUIRED = {
    "schema", "run_id", "boot_id", "contract_hash", "worker_instance", "mode",
    "sequence", "tick", "job_id", *VERSIONS, "epoch", "planned_ns", "start_ns", "end_ns",
    "activation_commit_ns", "ready_commit_ns", "skipped_ticks", "accepted", "reason",
    "diagnostic_only", "normal_contract_complete",
}
JOB_REQUIRED = {"schema", "run_id", "boot_id", "contract_hash", "worker_instance",
                "job_id", "target_tick", *VERSIONS, "clock_epoch"}


def uint(value):
    return type(value) is int and 0 <= value <= U64_MAX


def timestamp(value, zero=False):
    return type(value) is int and (0 if zero else 1) <= value <= I64_MAX


def hexhash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def domain(value):
    """Finite JSON values; source records may contain signed and uint64 fields."""
    pending = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > MAX_DEPTH or visited > MAX_ROW_NODES:
            raise ValueError("JSON row exceeds finite shape budget")
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise ValueError("JSON keys must be strings")
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("nonfinite JSON number")
        elif type(item) is int and not -(1 << 63) <= item <= U64_MAX:
            raise ValueError("JSON integer outside supported wire domain")
        elif type(item) is str:
            item.encode("utf-8")
        elif item is not None and type(item) not in (bool, int, float):
            raise ValueError("unsupported JSON value")


def parse_line(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("duplicate JSON key: " + k)
            result[k] = v
        return result
    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)
    try:
        item = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except RecursionError as error:
        raise ValueError("JSON exceeds parser nesting budget") from error
    domain(item)
    return item


def load_source(path):
    rows, total = [], 0
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            raw = source.readline(MAX_LINE_BYTES + 1)
            if not raw:
                break
            total += len(raw)
            if (len(raw) > MAX_LINE_BYTES or total > MAX_SOURCE_BYTES
                    or len(rows) >= MAX_SOURCE_ROWS or not raw.endswith(b"\n")):
                raise ValueError("source exceeds finite budget or has an unclosed terminal line")
            digest.update(raw)
            row = parse_line(raw)
            if type(row) is not dict or type(row.get("type")) is not str:
                raise ValueError("every source line must be a typed JSON object")
            rows.append(row)
    if not rows:
        raise ValueError("empty regulator source")
    return rows, digest.hexdigest()


def analyze(witness, expected_header, source_events, context):
    issues = []
    metrics = {"tick_whole_minus_source_end_ns": [],
               "submit_authorized_minus_source_gate_sample_ns": [],
               "source_publish_start_minus_submit_authorized_ns": []}
    matched = {"ticks": 0, "submits": 0, "activation_attempts": 0}

    def fail(code, category="source_join", **detail):
        issues.append({"code": code, "category": category, **detail})

    basis = witness_analyze(witness, expected_header)
    if not basis["passed"]:
        fail("basis_witness_incomplete", "witness", basis_issues=basis["issues"])
    context_ok = True
    def context_require(condition, field):
        nonlocal context_ok
        if not condition:
            context_ok = False
            fail("context_pin_or_normal_declaration", "context", field=field)

    h = expected_header if type(expected_header) is dict else {}
    c = context if type(context) is dict else {}
    context_require(c.get("schema") == "p1-no-output-calibration-context-v1", "schema")
    context_require(c.get("mode") == "no_output", "mode")
    for name in ("run_id", "boot_id"):
        context_require(c.get(name) == h.get(name) and type(c.get(name)) is str, name)
    context_require(hexhash(c.get("contract_sha256")) and c.get("contract_sha256") == h.get("contract_sha256"), "contract_sha256")
    assets = c.get("binaries", {})
    assets = assets if type(assets) is dict else {}
    for role, header_key in (("regulator", "binary_sha256"), ("worker", "worker_binary_sha256")):
        asset = assets.get(role, {})
        asset = asset if type(asset) is dict else {}
        context_require(hexhash(asset.get("sha256")) and asset.get("sha256") == h.get(header_key), "binaries." + role)
    implementation = c.get("diagnostic_source", {})
    implementation = implementation if type(implementation) is dict else {}
    context_require(hexhash(implementation.get("sha256")) and implementation.get("sha256") == h.get("source_sha256"), "diagnostic_source.sha256")
    fixed = c.get("fixed_witness", {})
    fixed = fixed if type(fixed) is dict else {}
    context_require(fixed.get("enabled") is True, "fixed_witness.enabled")
    context_require(type(fixed.get("test_sink_pause_ms")) is int and fixed["test_sink_pause_ms"] == 0, "fixed_witness.test_sink_pause_ms")
    declaration = c.get("declaration", {})
    declaration = declaration if type(declaration) is dict else {}
    duration = declaration.get("duration_s")
    context_require(type(duration) in (int, float) and duration == 10, "declaration.duration_s")
    for key in ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms", "test_tick_block_ms"):
        context_require(type(declaration.get(key)) is int and declaration[key] == 0, "declaration." + key)
    context_require(declaration.get("expected_fault") == "none", "declaration.expected_fault")
    context_require(declaration.get("execute_qualified") is False, "declaration.execute_qualified")

    rows = source_events if type(source_events) is list else []
    if type(source_events) is not list or not rows or len(rows) > MAX_SOURCE_ROWS:
        fail("source_root_or_budget")
    grouped = {}
    for number, row in enumerate(rows, 1):
        try:
            domain(row)
        except (ValueError, UnicodeError):
            fail("source_value_domain", line=number)
            continue
        if type(row) is not dict or type(row.get("type")) is not str:
            fail("source_event_type", line=number)
            continue
        kind = row["type"]
        if kind not in SUPPORTED_SOURCE_TYPES:
            fail("unsupported_source_event", line=number, event_type=kind)
        grouped.setdefault(kind, []).append(row)

    def exactly_one(kind):
        found = grouped.get(kind, [])
        if len(found) != 1:
            fail("source_terminal_or_startup_count", event_type=kind, observed=len(found))
            return {}
        return found[0]

    startup, summary, shutdown = (exactly_one(k) for k in ("startup", "source_summary", "regulator_shutdown"))
    if summary:
        if rows[-1] is not summary:
            fail("source_summary_not_last")
        if (not all(uint(summary.get(k)) for k in ("generated", "emitted", "dropped"))
                or summary.get("generated") != len(rows) - 1
                or summary.get("emitted") != len(rows) - 1
                or summary.get("dropped") != 0 or summary.get("normal_source_complete") is not True
                or not timestamp(summary.get("finished_ns"))):
            fail("normal_source_not_complete", "normal_case")
    if startup:
        for key, expected in (("schema", "p1-regulator-v1"), ("run_id", h.get("run_id")),
                              ("boot", h.get("boot_id")), ("contract_hash", h.get("contract_sha256")),
                              ("clock", "CLOCK_MONOTONIC"), ("mode", "no_output")):
            if type(startup.get(key)) is not str or startup[key] != expected:
                fail("source_startup_identity", field=key)
        if (startup.get("diagnostic_only") is not True
                or type(startup.get("physical_publisher_endpoints")) is not int
                or startup["physical_publisher_endpoints"] != 0):
            fail("source_startup_not_no_output", "normal_case")

    def source_identity(row):
        return all(type(row.get(k)) is str and row[k] == h.get(v) for k, v in (
            ("run_id", "run_id"), ("boot_id", "boot_id"),
            ("contract_hash", "contract_sha256"), ("worker_instance", "worker_instance")))

    decisions = []
    for index, d in enumerate(grouped.get("decision", [])):
        valid = (DECISION_REQUIRED <= set(d) and source_identity(d)
                 and d.get("schema") == "p1-execution-decision-v2" and d.get("mode") == "no_output"
                 and d.get("diagnostic_only") is True and d.get("normal_contract_complete") is False
                 and all(uint(d.get(k)) for k in ("sequence", "tick", "job_id", *VERSIONS, "epoch", "skipped_ticks"))
                 and all(timestamp(d.get(k)) for k in ("planned_ns", "start_ns", "end_ns", "activation_commit_ns"))
                 and timestamp(d.get("ready_commit_ns"), zero=True)
                 and type(d.get("accepted")) is bool and type(d.get("reason")) is str)
        if not valid:
            fail("source_decision_fields_or_types", index=index)
            continue
        if (d["sequence"] != index + 1 or not d["planned_ns"] <= d["start_ns"] <= d["activation_commit_ns"] <= d["end_ns"]
                or d["accepted"] != (d["reason"] == "") or (d["job_id"] == 0 and (d["accepted"] or d["ready_commit_ns"] != 0))):
            fail("source_decision_order_or_candidate", index=index)
        decisions.append(d)

    def mapping(values, key, code):
        result = {}
        for row in values:
            identity = key(row)
            if identity in result:
                fail(code, identity=identity)
            else:
                result[identity] = row
        return result

    source_ticks = mapping(decisions, lambda d: (d["schedule_generation"], d["tick"]), "duplicate_source_tick")
    w = witness if type(witness) is dict else {}
    # Failed base structure remains evidence, but malformed rows must never be
    # dereferenced as though they were verified business observations.
    witness_rows = {k: w.get(k, []) if basis["schema_valid"] else [] for k in ("tick", "submit", "activation", "phase")}
    witness_ticks = mapping(witness_rows["tick"], lambda r: (r["schedule_generation"], r["tick"]), "duplicate_witness_tick")
    if set(source_ticks) != set(witness_ticks):
        fail("tick_bidirectional_coverage", missing_witness=sorted(set(source_ticks) - set(witness_ticks)), extra_witness=sorted(set(witness_ticks) - set(source_ticks)))
    for key in source_ticks.keys() & witness_ticks.keys():
        d, r = source_ticks[key], witness_ticks[key]
        before = len(issues)
        expected = {"sequence": d["sequence"], "job_id": d["job_id"], "tick": d["tick"],
                    "target_tick": d["tick"] if d["job_id"] else 0, "clock_epoch": d["epoch"],
                    "planned_ns": d["planned_ns"], "start_ns": d["start_ns"], "skipped_ticks": d["skipped_ticks"],
                    "candidate_present": d["job_id"] > 0, **{k: d[k] for k in VERSIONS}}
        for field, value in expected.items():
            if type(r[field]) is not type(value) or r[field] != value:
                fail("tick_identity_or_time", identity=key, field=field)
        if d["end_ns"] > r["end_ns"]:
            fail("source_end_after_witness_whole_end", identity=key)
        metrics["tick_whole_minus_source_end_ns"].append(r["end_ns"] - d["end_ns"])
        if len(issues) == before:
            matched["ticks"] += 1

    jobs = []
    for index, e in enumerate(grouped.get("job", [])):
        j = e.get("job")
        if (type(j) is not dict or not JOB_REQUIRED <= set(j) or not source_identity(j)
                or j.get("schema") != "p1-solve-job-v1"
                or not all(uint(j.get(k)) for k in ("job_id", "target_tick", *VERSIONS, "clock_epoch"))
                or j.get("job_id") == 0 or j.get("target_tick") == 0
                or not timestamp(e.get("submit_commit_ns")) or not timestamp(e.get("publish_start_ns"))):
            fail("source_job_fields_or_types", index=index)
            continue
        jobs.append(e)
    source_jobs = mapping(jobs, lambda e: e["job"]["job_id"], "duplicate_source_job")
    submits = mapping(witness_rows["submit"], lambda r: r["job_id"], "duplicate_witness_submit")
    if set(source_jobs) != set(submits):
        fail("submit_bidirectional_coverage", missing_witness=sorted(set(source_jobs) - set(submits)), extra_witness=sorted(set(submits) - set(source_jobs)))
    for jid in source_jobs.keys() & submits.keys():
        e, r = source_jobs[jid], submits[jid]
        j, before = e["job"], len(issues)
        for field in ("job_id", "target_tick", *VERSIONS, "clock_epoch"):
            if r[field] != j[field]:
                fail("submit_identity", job_id=jid, field=field)
        if r["tick"] != j["target_tick"] - 1:
            fail("submit_preparation_tick", job_id=jid)
        if not e["submit_commit_ns"] <= r["commit_ns"] <= e["publish_start_ns"]:
            fail("submit_authorization_time_bracket", job_id=jid)
        metrics["submit_authorized_minus_source_gate_sample_ns"].append(r["commit_ns"] - e["submit_commit_ns"])
        metrics["source_publish_start_minus_submit_authorized_ns"].append(e["publish_start_ns"] - r["commit_ns"])
        if len(issues) == before:
            matched["submits"] += 1

    registrations = {}
    for index, e in enumerate(grouped.get("candidate_registration", [])):
        j = e.get("job")
        if (type(j) is not dict or not JOB_REQUIRED <= set(j) or not source_identity(j)
                or not all(uint(j.get(k)) for k in ("job_id", "target_tick", *VERSIONS, "clock_epoch"))
                or j["job_id"] == 0 or type(e.get("accepted_registration")) is not bool
                or not timestamp(e.get("ready_commit_ns"))):
            fail("source_registration_fields_or_types", index=index)
            continue
        if e["accepted_registration"]:
            if j["job_id"] in registrations:
                fail("duplicate_accepted_registration", job_id=j["job_id"])
            registrations[j["job_id"]] = e

    attempts = mapping([d for d in decisions if d["job_id"]], lambda d: d["job_id"], "duplicate_source_activation_attempt")
    activations = mapping(witness_rows["activation"], lambda r: r["job_id"], "duplicate_witness_activation_attempt")
    if set(attempts) != set(activations):
        fail("activation_bidirectional_coverage", missing_witness=sorted(set(attempts) - set(activations)), extra_witness=sorted(set(activations) - set(attempts)))
    for jid in attempts.keys() & activations.keys():
        d, r, before = attempts[jid], activations[jid], len(issues)
        expected = {"job_id": jid, "tick": d["tick"], "target_tick": d["tick"],
                    "clock_epoch": d["epoch"], "commit_ns": d["activation_commit_ns"],
                    "ready_commit_ns": d["ready_commit_ns"], "accepted": d["accepted"],
                    **{k: d[k] for k in VERSIONS}}
        expected["reason_code"] = (0 if d["accepted"] else 1 if d["reason"] == "shutdown"
                                   else 2 if d["reason"] == "run_unusable_at_commit" else 3)
        for field, value in expected.items():
            if type(r[field]) is not type(value) or r[field] != value:
                fail("activation_identity_time_or_result", job_id=jid, field=field)
        registration = registrations.get(jid)
        if registration is None or registration["ready_commit_ns"] != d["ready_commit_ns"]:
            fail("activation_without_exact_source_registration", job_id=jid)
        elif jid in source_jobs:
            for field in JOB_REQUIRED:
                if registration["job"][field] != source_jobs[jid]["job"][field]:
                    fail("registration_job_identity", job_id=jid, field=field)
        if len(issues) == before:
            matched["activation_attempts"] += 1

    for stream in ("tick", "submit", "activation"):
        failure_fields = ("failed_start", "failed_end") if stream == "tick" else ("failed",)
        for r in witness_rows[stream]:
            if any(r[k] for k in failure_fields):
                fail("normal_case_failed_observation", "normal_case", stream=stream, sequence=r["sequence"])
    for r in witness_rows["phase"]:
        if r["event_code"] not in NORMAL_PHASES:
            fail("unsupported_normal_phase", "normal_case", sequence=r["sequence"], event_code=r["event_code"])
        if r["failed"] is True or r["pause_active"] is True:
            fail("normal_phase_failed_or_paused", "normal_case", sequence=r["sequence"])
    closes = [r for r in witness_rows["phase"] if r["event_code"] == 7]
    if closes and summary and timestamp(summary.get("finished_ns")) and closes[0]["ns"] < summary["finished_ns"]:
        fail("witness_closed_before_source_terminal_flush")
    if shutdown:
        if (not uint(shutdown.get("last_decision_sequence")) or not decisions
                or shutdown["last_decision_sequence"] != decisions[-1]["sequence"]
                or not timestamp(shutdown.get("finished_ns"))
                or shutdown.get("shutdown_grace_exceeded") is not False):
            fail("source_shutdown_not_complete", "normal_case")
        elif summary and timestamp(summary.get("finished_ns")) and shutdown["finished_ns"] > summary["finished_ns"]:
            fail("source_shutdown_after_summary")
    passed = not issues
    return {"schema": SCHEMA, "scope": SCOPE, "run_id": h.get("run_id"),
            "mode": c.get("mode"), "passed": passed,
            "source_join_verified": passed, "context_verified": context_ok,
            "basis_witness_check": basis, "issues": issues,
            "counts": {"source_rows": len(rows), "source_decisions": len(decisions),
                       "witness_ticks": len(witness_rows["tick"]), "source_jobs": len(jobs),
                       "witness_submits": len(witness_rows["submit"]),
                       "source_candidate_attempts": len(attempts), "witness_activation_attempts": len(activations),
                       "source_accepted_attempts": sum(d["accepted"] for d in decisions),
                       "witness_accepted_attempts": sum(r["accepted"] for r in witness_rows["activation"]),
                       "matched": matched}, "observed_timestamp_differences_ns": metrics,
            "lifecycle_window_clipped": False, "measurement_duration_declared_s": 10,
            "normal_window_verified": False, "owned_process_lifecycle_verified": False,
            "worker_source_compared": False, "source_bag_contract_complete": False,
            "all_worker_execution_gates_verified": False, "C0_performance_comparison_verified": False,
            "normal_contract_complete": False, "expected_log_overflow_mechanism_passed": False,
            "execute_qualified": False}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while data := source.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("witness", "expected-header", "source", "context", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    paths = [args.witness, args.expected_header, args.source, args.context]
    if args.output.resolve() in {p.resolve() for p in paths}:
        parser.error("create-only report must not alias a raw input")
    before = {}
    run_id = None
    try:
        witness, before[str(args.witness)] = load_bounded_json(args.witness)
        expected, before[str(args.expected_header)] = load_bounded_json(args.expected_header)
        run_id = expected.get("run_id") if type(expected) is dict else None
        context, before[str(args.context)] = load_bounded_json(args.context)
        events, before[str(args.source)] = load_source(args.source)
        result = analyze(witness, expected, events, context)
        after = {str(p): sha256_file(p) for p in paths}
        result["input_sha256_before"], result["input_sha256_after"] = before, after
        result["raw_inputs_unchanged"] = before == after
        if before != after:
            result["passed"] = result["source_join_verified"] = False
            result["issues"].append({"code": "raw_inputs_changed_during_read", "category": "input_integrity"})
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        result = {"schema": SCHEMA, "scope": SCOPE, "run_id": run_id,
                  "passed": False, "source_join_verified": False,
                  "reader_error": str(error), "issues": [{"code": "input_unreadable_or_invalid", "category": "input_integrity"}],
                  "input_sha256_before": before, "raw_inputs_unchanged": False,
                  "source_bag_contract_complete": False, "normal_contract_complete": False,
                  "expected_log_overflow_mechanism_passed": False, "execute_qualified": False}
    result["checker_sha256"] = sha256_file(Path(__file__))
    try:
        with args.output.open("x", encoding="utf-8") as report:
            json.dump(result, report, ensure_ascii=False, indent=2, allow_nan=False)
            report.write("\n")
    except OSError as error:
        print(json.dumps({"passed": False, "source_join_verified": False, "report_write_error": str(error)}))
        return 2
    print(json.dumps({k: result[k] for k in ("passed", "source_join_verified", "issues")}))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
