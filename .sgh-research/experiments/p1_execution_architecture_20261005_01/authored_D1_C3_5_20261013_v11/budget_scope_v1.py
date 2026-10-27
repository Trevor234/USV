#!/usr/bin/env python3
"""Offline finite-window evidence, with explicit unproved execution dependencies.

This module never starts ROS or changes a recorded input.  ``analyze_data`` is a
semantic component entry point; ``analyze_manifest`` additionally locks every
preregistered input to its original bytes.  It does not replace the owned,
atomic, lease, release, configuration, CDR or SQLite checkers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat


SCHEMA = "p1-C3.5-budget-scope/v1"
STATES = ("passed", "failed", "unknown", "not_run")
POLICY = {
    "T_ns": 200_000_000, "ready_ns": 150_000_000,
    "release_ns": 3_000_000_000, "prepare_ns": 25_000_000_000,
    "total_ns": 60_000_000_000, "close_ns": 15_000_000_000,
    "normal_observer_hooks": [0, 0, 0, 0, 0],
    "normal_worker_hooks": [0, 0], "measurement_ns": 4_000_000_000,
    "dynamic_measurement_ns": 20_000_000_000,
    "source_planar_speed_max_m_s": 1.2,
    "source_stamp_gap_max_ns": 250_000_000,
}
STAGE_FLAGS = (
    "strict_full_chain", "C3_general", "D1", "B4", "B5", "M0b", "M4",
    "F6", "P1", "execute", "dynamic_20s_R5", "mixed_turn",
    "true_master_clock", "research_conclusion",
)


class BudgetScopeError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise BudgetScopeError(reason)


def integer(value, label, *, minimum=0):
    require(type(value) is int and minimum <= value <= 2**63 - 1,
            f"{label}: exact bounded int64 required")
    return value


def boolean(value, label):
    require(type(value) is bool, f"{label}: exact bool required")
    return value


def finite(value, label):
    require(type(value) in (int, float) and math.isfinite(value),
            f"{label}: finite numeric value required")
    return value


def canonical_equal(left, right):
    """Comparison must retain bool/int and int/float distinctions."""
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def anchor_types(row, prefix):
    for field, check in (("known", boolean), ("sequence", integer),
                         ("publish_ns", integer), ("n", finite)):
        values = row[prefix + field]
        require(type(values) is list and len(values) == 2, "two-channel anchor shape required")
        for value in values:
            check(value, prefix + field)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(raw):
    def bad(value):
        raise BudgetScopeError(f"nonfinite JSON token: {value}")
    result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=bad)
    def walk(value):
        if type(value) is float:
            finite(value, "JSON number")
        elif isinstance(value, dict):
            for x in value.values():
                walk(x)
        elif isinstance(value, list):
            for x in value:
                walk(x)
    walk(result)
    return result


def locked_bytes(path, pin):
    """Read actual nofollow FD, single-link regular file, stable identity/hash."""
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                f"unsupported pinned input type/link count: {path}")
        require(before.st_size <= 64 * 1024 * 1024, f"bounded input exceeded: {path}")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
    require(all(getattr(before, x) == getattr(after, x) for x in fields),
            f"pinned input changed during FD read: {path}")
    require(len(raw) == pin["bytes"] and hashlib.sha256(raw).hexdigest() == pin["sha256"],
            f"original input pin mismatch: {path}")
    return raw


def one(rows, kind):
    found = [r for r in rows if r.get("type") == kind]
    require(len(found) == 1, f"expected exactly one {kind}")
    return found[0]


def index(rows, kind, key):
    result = {}
    for row in rows:
        if row.get("type") != kind:
            continue
        value = key(row)
        require(value not in result, f"duplicate {kind} identity: {value}")
        result[value] = row
    return result


def window(start, end, label):
    start = integer(start, label + ".start")
    end = integer(end, label + ".end")
    require(end >= start, f"reversed original operation window: {label}")
    return {"start_ns": start, "end_ns": end, "elapsed_ns": end - start}


def distribution(values):
    values = [integer(x, "finite observation") for x in values]
    return {"count": len(values), "min_ns": min(values) if values else None,
            "max_ns": max(values) if values else None,
            "sum_ns": sum(values), "wcet_ns": None,
            "wcet_status": "unknown", "semantics": "observed finite original windows"}


def item(status, reason, observed=None, bound=None):
    require(status in STATES, "unsupported dependency status")
    return {"status": status, "reason": reason, "observed": observed, "bound": bound}


def observed_bound(values, bound, reason):
    return item("not_run" if not values else
                "passed" if all(x <= bound for x in values) else "failed",
                reason, distribution(values), bound)


def gate_status(dependencies):
    states = [x["status"] for x in dependencies.values()]
    if "failed" in states:
        return "failed"
    if "unknown" in states:
        return "unknown"
    if "not_run" in states:
        return "not_run"
    return "passed"


def _hooks(data, startup):
    observer_names = ("test_delay_ms", "test_native_block_ms", "test_prepare_block_ms",
                      "test_sink_pause_ms", "test_tick_block_ms")
    worker_names = ("test_delay_ms", "test_native_block_ms")
    for role, names, expected in [
            ("observer", observer_names, POLICY["normal_observer_hooks"]),
            ("worker", worker_names, POLICY["normal_worker_hooks"])]:
        actual = []
        for name in names:
            query = data[f"live_parameters_{role}.json"][name]
            require(type(query["type"]) is int and query["type"] == 2,
                    f"{role}.{name}: typed integer query required")
            actual.append(integer(query["value"], f"{role}.{name}"))
            require(query["value"] == query["canonical_value"] ==
                    data["inputs.json"]["expected_parameters"][role][name],
                    f"{role}.{name}: complete typed/expected hook mismatch")
        require(actual == expected, f"normal {role} hooks differ from frozen policy")
    require(startup["fault_hook_values"] == POLICY["normal_observer_hooks"] and
            all(type(x) is int for x in startup["fault_hook_values"]),
            "normal native observer hook Source differs")


def _job_metrics(observer, worker, witness):
    jobs = index(observer, "job", lambda r: integer(r["job"]["job_id"], "job_id", minimum=1))
    received = index(worker, "job_received", lambda r: r["job"]["job_id"])
    candidates = index(worker, "candidate", lambda r: r["job"]["job_id"])
    registration = index(observer, "candidate_registration", lambda r: r["job"]["job_id"])
    job_publish = index(observer, "job_publish_result", lambda r: r["job_id"])
    candidate_publish = index(worker, "candidate_publish_result", lambda r: r["job_id"])
    require(set(jobs) == set(received) == set(candidates) == set(registration) ==
            set(job_publish) == set(candidate_publish), "full finite job/candidate join differs")
    metrics = {key: [] for key in ("freeze_to_submit", "job_publish", "job_transport",
               "worker_receive_to_solve_start", "worker_native_solve", "worker_completion",
               "candidate_publish", "candidate_ready", "ready_slack")}
    detailed = []
    for job_id, row in jobs.items():
        job = row["job"]
        rc, cand, reg = received[job_id], candidates[job_id], registration[job_id]
        jp, cp = job_publish[job_id], candidate_publish[job_id]
        require(all(canonical_equal(job, other) for other in (rc["job"], cand["job"], reg["job"])),
                f"complete immutable job fields differ: {job_id}")
        origin = integer(job["tick_origin_ns"], "tick_origin_ns")
        deadline = integer(job["deadline_ns"], "deadline_ns")
        target = integer(job["target_ns"], "target_ns")
        require(deadline - origin == POLICY["ready_ns"] and
                target - origin == POLICY["T_ns"], "job changed fixed T/ready gate")
        require(rc["receive_ns"] == cand["receive_ns"] and
                cand["solve_start_ns"] == cp["solve_start_ns"] == reg["solve_start_ns"] and
                cand["solve_end_ns"] == cp["solve_end_ns"] == reg["solve_end_ns"],
                f"native solve timestamps do not join: {job_id}")
        stamps = [job["freeze_ns"], row["submit_commit_ns"], jp["publish_start_ns"],
                  rc["receive_ns"], rc["commit_ns"], cand["solve_start_ns"],
                  cand["solve_end_ns"], cand["publish_start_ns"], cp["publish_start_ns"],
                  reg["ready_commit_ns"]]
        for left, right in zip(stamps, stamps[1:]):
            window(left, right, f"job {job_id} Source order")
        window(jp["publish_start_ns"], jp["publish_end_ns"], "job publish")
        window(cp["publish_start_ns"], cp["publish_end_ns"], "candidate publish")
        require(all(boolean(x["success"], "publish/native success") for x in (jp, cp, cand)) and
                boolean(reg["accepted_registration"], "accepted_registration"),
                "finite completed normal job is unsuccessful")
        require(cand["first_control"] == reg["first_control"], "candidate first-control join differs")
        detailed.append({"job_id": job_id, "origin_ns": origin, "deadline_ns": deadline,
                         "ready_ns": reg["ready_commit_ns"],
                         "ready_before_deadline": reg["ready_commit_ns"] <= deadline})
        intervals = {
            "freeze_to_submit": (job["freeze_ns"], row["submit_commit_ns"]),
            "job_publish": (jp["publish_start_ns"], jp["publish_end_ns"]),
            "job_transport": (jp["publish_start_ns"], rc["receive_ns"]),
            "worker_receive_to_solve_start": (rc["receive_ns"], cand["solve_start_ns"]),
            "worker_native_solve": (cand["solve_start_ns"], cand["solve_end_ns"]),
            "worker_completion": (job["freeze_ns"], cand["solve_end_ns"]),
            "candidate_publish": (cp["publish_start_ns"], cp["publish_end_ns"]),
            "candidate_ready": (origin, reg["ready_commit_ns"]),
        }
        for name, (start, end) in intervals.items():
            metrics[name].append(window(start, end, name)["elapsed_ns"])
        # A negative slack is evidence of a missed bound, not an invalid negative duration.
        metrics["ready_slack"].append(deadline - reg["ready_commit_ns"])
    return jobs, registration, metrics, detailed


def replay_anchor_history(expected, actual, entries):
    """Independent full history: unchanged commands may advance identities.

    Endpoint equality is insufficient for a change-then-return history, and
    sequence advancement alone is not a command mismatch.
    """
    for channel in (0, 1):
        if not expected["known"][channel] or not actual["known"][channel]:
            return "unknown_anchor"
        if not math.isfinite(expected["n"][channel]) or not math.isfinite(actual["n"][channel]):
            return "unknown_anchor"
        if expected["n"][channel] != actual["n"][channel]:
            return "anchor_mismatch"
        first, last = expected["sequence"][channel], actual["sequence"][channel]
        first_ns, last_ns = expected["publish_ns"][channel], actual["publish_ns"][channel]
        if last < first or last_ns < first_ns:
            return "anchor_history_incomplete"
        if first == last:
            if first_ns != last_ns:
                return "anchor_history_incomplete"
            continue
        selected = [r for r in entries if r["channel"] == channel and first <= r["sequence"] <= last]
        if not selected:
            return "anchor_history_incomplete"
        previous_seq, previous_ns = None, None
        for row in selected:
            if not row["known"] or not math.isfinite(row["n"]):
                return "unknown_anchor"
            if row["n"] != expected["n"][channel]:
                return "anchor_history_changed"
            if previous_seq is None:
                if row["sequence"] != first or row["publish_ns"] != first_ns:
                    return "anchor_history_incomplete"
            elif row["sequence"] != previous_seq + 1 or row["publish_ns"] <= previous_ns:
                return "anchor_history_incomplete"
            previous_seq, previous_ns = row["sequence"], row["publish_ns"]
        if previous_seq != last or previous_ns != last_ns:
            return "anchor_history_incomplete"
    return ""


def _decision_metrics(observer, witness, jobs, registration, contract, publisher_end):
    decisions = index(observer, "decision", lambda r: integer(r["sequence"], "Decision.sequence", minimum=1))
    ticks = {r["sequence"]: r for r in witness["tick"]}
    require(len(ticks) == len(witness["tick"]) and set(decisions) == set(ticks),
            "finite Decision/Witness tick join differs")
    anchors = index(observer, "anchor_validation", lambda r: r["sequence"])
    legacy = index(observer, "legacy_anchor", lambda r: r["sequence"])
    activation_rows = witness["activation"]
    require(len(activation_rows) == len(anchors), "Witness activation/anchor count differs")
    phase = []
    accepted = []
    mismatches = []
    ages = {"odom": [], "clock": [], "imu": []}
    jitters = []
    for sequence, decision in decisions.items():
        tick = ticks[sequence]
        for key in ("job_id", "tick", "planned_ns", "start_ns", "skipped_ticks"):
            require(decision[key] == tick[key] and type(decision[key]) is int,
                    f"Decision/Witness original {key} differs")
        require(decision["mode"] == "shadow" and
                boolean(decision["diagnostic_only"], "diagnostic_only") and
                not boolean(decision["plant_acceptance_observed"], "plant observed"),
                "shadow observation cannot claim execution/plant acceptance")
        require(decision["publish_success"] == [False, False] and
                all(type(x) is bool for x in decision["publish_success"]),
                "shadow source cannot claim actual regulator publish success")
        for key in ("publish_start_ns", "publish_end_ns", "publish_clock_age_ns"):
            require(decision[key] == [0, 0] and all(type(x) is int for x in decision[key]),
                    "shadow no-call values do not establish a publish budget")
        phase.append(window(decision["start_ns"], decision["end_ns"], "Decision computation")["elapsed_ns"])
        window(decision["end_ns"], tick["end_ns"], "Witness tick encompasses cutoff wait")
        jitters.append(abs(integer(decision["start_ns"], "start_ns") -
                           integer(decision["planned_ns"], "planned_ns")))
        boolean(decision["accepted"], "accepted")
        if sequence not in anchors:
            require(not decision["accepted"], "accepted candidate has no anchor validation")
            continue
        anchor = anchors[sequence]
        anchor_types(anchor, "expected_")
        anchor_types(anchor, "actual_")
        job_id = integer(decision["job_id"], "activation job_id", minimum=1)
        require(job_id in jobs and anchor["job_id"] == job_id, "anchor job identity differs")
        job = jobs[job_id]["job"]
        for field, jf in [("known", "anchor_known"), ("n", "anchor_n"),
                          ("publish_ns", "anchor_publish_ns"), ("sequence", "anchor_sequence")]:
            require(anchor[f"expected_{field}"] == job[jf], "candidate expected anchor differs from immutable job")
        if all(anchor["actual_known"]):
            for channel, seq in enumerate(anchor["actual_sequence"]):
                require(seq in legacy, "actual anchor has no original Applied anchor")
                source = legacy[seq]
                require(source["known"][channel] == anchor["actual_known"][channel] and
                        source["final_n"][channel] == anchor["actual_n"][channel] and
                        source["publish_ns"][channel] == anchor["actual_publish_ns"][channel],
                        "actual anchor differs from original Applied Source")
        for entry in anchor["entries"]:
            channel = integer(entry["channel"], "history channel")
            require(channel in (0, 1), "history channel outside two-channel domain")
            sequence_id = integer(entry["sequence"], "history sequence", minimum=1)
            require(sequence_id in legacy, "anchor history lacks original Applied Source")
            original = legacy[sequence_id]
            require(entry["known"] == original["known"][channel] and
                    type(entry["known"]) is bool and
                    entry["n"] == original["final_n"][channel] and
                    entry["publish_ns"] == original["publish_ns"][channel],
                    "anchor history entry differs from original Applied Source")
        history_reason = replay_anchor_history(
            {k: anchor["expected_" + k] for k in ("known", "n", "sequence", "publish_ns")},
            {k: anchor["actual_" + k] for k in ("known", "n", "sequence", "publish_ns")},
            anchor["entries"])
        require(anchor["history_reason"] == history_reason, "independent complete anchor history differs")
        mismatch = bool(history_reason)
        require(anchor["accepted"] == decision["accepted"] and
                anchor["decision_reason"] == decision["reason"] and
                anchor["check_ns"] == decision["activation_commit_ns"] and
                decision["ready_commit_ns"] == registration[job_id]["ready_commit_ns"],
                "activation/anchor/registration source join differs")
        matching = [r for r in activation_rows if r["job_id"] == job_id and r["tick"] == decision["tick"]]
        require(len(matching) == 1 and matching[0]["accepted"] == decision["accepted"] and
                matching[0]["commit_ns"] == decision["activation_commit_ns"] and
                matching[0]["ready_commit_ns"] == decision["ready_commit_ns"],
                "activation Witness join differs")
        if mismatch:
            require(not decision["accepted"] and decision["reason"] == history_reason,
                    "changed anchor incorrectly accepted or mislabeled")
            mismatches.append({"sequence": sequence, "job_id": job_id,
                               "expected_sequence": anchor["expected_sequence"],
                               "actual_sequence": anchor["actual_sequence"]})
        if decision["accepted"]:
            require(not mismatch and decision["reason"] == anchor["history_reason"] == "",
                    "accepted candidate anchor validation differs")
            require(decision["ready_commit_ns"] <= job["deadline_ns"],
                    "accepted candidate was not ready within original fixed gate")
            accepted.append({"sequence": sequence, "job_id": job_id,
                             "activation_ns": decision["activation_commit_ns"],
                             "requested_n": decision["requested_n"],
                             "publisher_tail": publisher_end is not None and
                                               decision["activation_commit_ns"] >= publisher_end,
                             "actual_regulator_publish": False,
                             "plant_acceptance": None})
        final = decision["d0_observation"]["final_snapshot"]
        for name in ("odom", "clock"):
            age = window(final[name + "_receive_ns"], decision["activation_commit_ns"],
                         f"activation {name} receipt age")["elapsed_ns"]
            require(age == decision[name + "_age_ns"], "original source receipt age differs")
            ages[name].append(age)
        if boolean(decision["activation_r_from_imu"], "mixed activation"):
            age = window(final["imu_receive_ns"], decision["activation_commit_ns"],
                         "activation imu receipt age")["elapsed_ns"]
            require(age == decision["imu_age_ns"], "original mixed receipt age differs")
            ages["imu"].append(age)
        finite(decision["activation_rtf"], "activation RTF")
    return {"count": len(decisions), "activation_count": len(anchors),
            "anchor_mismatch_count": len(mismatches), "anchor_mismatches": mismatches,
            "accepted_shadow": accepted, "compute_windows": distribution(phase),
            "jitter": distribution(jitters), "jitter_observed_ns": jitters,
            "receipt_ages": {k: distribution(v) for k, v in ages.items()},
            "receipt_age_observed_ns": ages}


def analyze_data(data, contract, policy=POLICY):
    """Compute metrics from complete finite original documents; no phase grants."""
    require(canonical_equal(policy, POLICY), "current policy differs; new version/preregister required")
    require(contract["T_ns"] == POLICY["T_ns"] and
            contract["deadline_ns"] == POLICY["ready_ns"] and
            type(contract["T_ns"]) is type(contract["deadline_ns"]) is int,
            "actual diagnostic contract T/ready mismatch")
    inputs, result = data["inputs.json"], data["result.json"]
    observer, worker = data["observer/source.jsonl"], data["worker/source.jsonl"]
    witness, ledger = data["observer/witness.json"], data["owned_process_ledger.jsonl"]
    startup, ws = one(observer, "startup"), one(worker, "capability_source_header")
    run_id = inputs["run_id"]
    require(startup["run_id"] == result["run_id"] == ws["run_id"] == run_id,
            "run identity differs")
    require(startup["boot"] == ws["boot_id"] == witness["header"]["boot_id"] and
            startup["clock"] == ws["clock"] == witness["clock_name"] == "CLOCK_MONOTONIC",
            "monotonic scope requires explicit same boot/clock")
    require(all(r["boot_id"] == startup["boot"] for r in ledger),
            "ledger crosses boot domain")
    _hooks(data, startup)
    require(integer(result["prepare_budget_ns"], "prepare budget") == POLICY["prepare_ns"] and
            integer(result["overall_budget_ns"], "overall budget") == POLICY["total_ns"],
            "reported runtime budgets differ from fixed policy")
    require(type(inputs["measurement_seconds"]) is int and inputs["measurement_seconds"] == 4,
            "current source recipe is bounded 4s, not dynamic20s")
    start = integer(result["prepare_start_ns"], "prepare start")
    summary = one(ledger, "supervisor_summary")
    total_observed = window(start, summary["monotonic_ns"], "prepare start to ledger summary")
    elapsed_reported = integer(result["elapsed_ns"], "driver original elapsed")
    require(elapsed_reported >= total_observed["elapsed_ns"],
            "driver total duration omits observed ledger tail")
    signals = [r for r in ledger if r["type"] == "signal"]
    require(len(signals) == 5 and {r["name"] for r in signals} ==
            {"publisher", "observer", "worker", "synthetic_source", "recorder"},
            "finite owned close signal roles differ")
    signal_times = [integer(x["monotonic_ns"], "close signal") for x in signals]
    require(signal_times == sorted(signal_times), "close ledger signal order differs")
    close_observed = window(signal_times[0], summary["monotonic_ns"], "first close signal to ledger summary")
    close_reported = integer(result["close_elapsed_ns"], "original close elapsed")
    require(close_reported >= close_observed["elapsed_ns"],
            "reported close omits finite original ledger window")
    cleanup = index(ledger, "cleanup_result", lambda r: r["name"])
    require(set(cleanup) == {r["name"] for r in signals}, "close cleanup roles differ")
    close_roles = {}
    for row in signals:
        end = cleanup[row["name"]]
        close_roles[row["name"]] = window(row["monotonic_ns"], end["monotonic_ns"], row["name"] + " close")
        require(type(end["returncode"]) is int and end["returncode"] == 0 and
                boolean(end["cleanup_complete"], "cleanup complete") and
                boolean(end["resource_cleanup_complete"], "resource cleanup complete"),
                "current three finite closes are not clean native exit")
    preparation = [v for k, v in data.items() if k.endswith("preparation_evidence.json")]
    require(len(preparation) == 1, "finite preparation evidence count differs")
    prepare_window = window(start, preparation[0]["checked_ns"], "preparation check")
    pub = data["publisher/release_observation.json"]
    gate = pub["gate"]
    session = data["publisher/session_summary.json"]
    publisher_end = integer(session["end_steady_ns"], "publisher session end")
    jobs, registration, costs, detailed = _job_metrics(observer, worker, witness)
    dm = _decision_metrics(observer, witness, jobs, registration, contract, publisher_end)
    shutdown = one(observer, "regulator_shutdown")
    require(not boolean(shutdown["plant_hold_end_known"], "plant hold known"),
            "source does not contain actual plant held interval")
    publications = data["release_publication_observation.json"]["events"]
    release_windows = []
    actual_release = []
    for event in publications:
        span = window(event["call_start_steady_ns"], event["call_end_steady_ns"], "release create-only call")
        span.update({"path": event["release_path"], "completed": boolean(event["completed"], "release call complete"),
                     "first_visibility_ns": None})
        release_windows.append(span)
        if Path(event["release_path"]).name == "release.json":
            actual_release.append(event)
    mode = inputs["mode"]
    require(mode == result["mode"] and mode in ("positive", "expired_release", "prepare_io_ambiguous"),
            "unsupported finite input recipe")
    gate_windows = {}
    for name, begin, finish in [
            ("read", "release_read_start_steady_ns", "release_read_end_steady_ns"),
            ("arm", "arm_start_steady_ns", "arm_end_steady_ns"),
            ("receipt", "receipt_io_start_steady_ns", "receipt_io_end_steady_ns")]:
        left, right = gate[begin], gate[finish]
        if left is None or right is None:
            require(left is None and right is None, "partial original gate interval needs explicit new applicability")
            gate_windows[name] = None
        else:
            gate_windows[name] = window(left, right, "publisher gate " + name)
    if mode == "positive":
        require(gate["gate_state"] == "Released" and len(actual_release) == 1,
                "positive original release gate differs")
        require(gate["commit_steady_ns"] <= gate["valid_until_steady_ns"],
                "original release committed after expiry")
        event = actual_release[0]
        lifetime = integer(event["valid_until_steady_ns"], "release until") - event["call_start_steady_ns"]
        require(0 < lifetime <= POLICY["release_ns"], "release validity exceeded fixed 3s")
    else:
        require(gate["gate_state"] == ("Fault" if mode == "expired_release" else "Held") and
                gate["commit_steady_ns"] is None and gate["arm_start_steady_ns"] is None,
                "finite pre-arm failure branch differs")
        require(not jobs and not dm["accepted_shadow"], "pre-arm failure contains normal solve acceptance")
        lifetime = None
    clocks = [r for r in observer if r["type"] == "clock"]
    valid_rtf = [finite(r["rtf"], "Clock RTF") for r in clocks if boolean(r["rtf_valid"], "RTF valid")]
    clock_span = window(clocks[0]["receive_ns"], clocks[-1]["receive_ns"], "finite clock receipt span") if clocks else None
    dependencies = {
        "fixed_policy_and_same_boot": item("passed", "original exact T/ready/runtime/hook and boot fields joined"),
        "prepare_observed": observed_bound([prepare_window["elapsed_ns"]], POLICY["prepare_ns"], "original check endpoint within bounded prepare; full IO WCET unavailable"),
        "total_observed": observed_bound([elapsed_reported, total_observed["elapsed_ns"]], POLICY["total_ns"], "original driver duration plus independent ledger lower window"),
        "close_observed": observed_bound([close_reported, close_observed["elapsed_ns"]], POLICY["close_ns"], "original close duration plus independently joined signal/cleanup windows"),
        "candidate_ready_observed": observed_bound(costs["candidate_ready"], POLICY["ready_ns"], "full native receive/solve/registration timing joined against 150ms gate"),
        "tick_jitter_observed": observed_bound(dm.pop("jitter_observed_ns"), contract["tick_jitter_ns"], "finite actual tick-start minus planned; no scheduling hard-bound claim"),
        "master_clock_hard_bound": item("unknown", "CLOCK_MONOTONIC same boot identifies local order; no Master Clock hardware/OS hard bound", None, None),
        "worker_io_schedule_wcet": item("unknown", "finite Source maxima do not prove WCET or all log/directory IO/scheduler costs", None, None),
        "plant_receive_and_hold": item("unknown", "AppliedControl is publisher command; no plant ACK, actual force or held interval", None, None),
        "dual_publish_budget_rho_gap": item("not_run", "shadow has no actual regulator publish calls; zero no-call fields cannot prove 5ms/gap/rho", None,
                                            {k: contract[k] for k in ("publish_budget_ns", "publish_gap_ns", "rho_n_s")}),
        "anchor_guard_observed": item("passed", "immutable expected/current Applied Source and actual rejection joined", dm["anchor_mismatch_count"]),
        "nonzero_anchor_execution_contract": item("failed" if dm["anchor_mismatch_count"] else "not_run", "current moving publisher anchor rejects candidate; tail shadow acceptance provides no actual nonzero execution", dm["anchor_mismatch_count"]),
        "current_dynamic_20s_R5": item("not_run", "current fixture declares 4s; 20s dynamic current-version R5 not executed", None, POLICY["dynamic_measurement_ns"]),
        "turn_and_mixed": item("not_run", "current normal source is straight odom; turn/mixed current recipe has no run", None, None),
        "current_pressure_recovery_failed_close": item("not_run", "three normal/pre-arm finite closes do not exercise final unified-version pressure/recovery/failed-close", None, None),
        "execution_contract_identity_freeze": item("not_run", "requires parent new acceptance contract source/tool/binary closure and scope review", None, None),
    }
    for name, values in dm.pop("receipt_age_observed_ns").items():
        dependencies[name + "_receipt_age_observed"] = observed_bound(values, contract[name + "_age_ns"], "activation original snapshot receipt age; pre-ready missing sources excluded")
    stage_names = {
        "B4": ("fixed_policy_and_same_boot", "prepare_observed", "candidate_ready_observed",
               "master_clock_hard_bound", "worker_io_schedule_wcet", "nonzero_anchor_execution_contract",
               "current_dynamic_20s_R5", "current_pressure_recovery_failed_close", "execution_contract_identity_freeze"),
        "M0b": ("close_observed", "total_observed", "worker_io_schedule_wcet", "current_pressure_recovery_failed_close",
                "execution_contract_identity_freeze", "current_dynamic_20s_R5"),
        "B5": ("execution_contract_identity_freeze", "worker_io_schedule_wcet", "current_dynamic_20s_R5",
               "current_pressure_recovery_failed_close"),
        "M4": ("nonzero_anchor_execution_contract", "dual_publish_budget_rho_gap", "plant_receive_and_hold",
               "execution_contract_identity_freeze", "current_dynamic_20s_R5", "turn_and_mixed"),
    }
    stages = {}
    for stage, names in stage_names.items():
        subset = {key: dependencies[key] for key in names}
        stages[stage] = {"status": gate_status(subset), "qualified": False,
                         "dependencies": subset, "scope": "necessary budget dependencies only; parent full stage adds its own gates"}
    ready = [r["readiness"] for r in observer if r["type"] == "legacy_ready"]
    return {"schema": SCHEMA, "run_id": run_id, "mode": mode,
            "component_status": "passed", "policy": policy,
            "scope": "pinned finite command/diagnostic observations in same-boot CLOCK_MONOTONIC; no phase qualification",
            "original_flags_used_as_acceptance": False, "wcet_proven": False,
            "master_clock_hard_bound_ns": None, "plant_hold_interval_ns": None,
            "prepare": prepare_window, "total_driver_original_ns": elapsed_reported,
            "total_ledger_lower_window": total_observed, "close_driver_original_ns": close_reported,
            "close_ledger_lower_window": close_observed, "close_roles": close_roles,
            "release_create_only_windows": release_windows, "release_lifetime_observed_ns": lifetime,
            "publisher_gate_last_original_windows": gate_windows,
            "publisher_gate_last_observation": {
                "gate_state": gate["gate_state"],
                "release_read_completed": boolean(gate["release_read_completed"], "release read completed"),
                "release_present_at_last_completed_read": boolean(gate["release_present_at_last_completed_read"], "release present at last completed read"),
                "original_freshness_read_count": integer(gate["original_freshness_read_count"], "original freshness read count"),
                "receipt_io_completed": boolean(gate["receipt_io_completed"], "receipt IO completed"),
                "semantics": "read span may be a missing-file attempt; spans are original last-recorded windows, not all poll WCET"},
            "native_worker_windows": {key: distribution(v) for key, v in costs.items() if key != "ready_slack"},
            "ready_slack_ns": {"count": len(costs["ready_slack"]),
                                "min": min(costs["ready_slack"]) if costs["ready_slack"] else None,
                                "max": max(costs["ready_slack"]) if costs["ready_slack"] else None},
            "jobs": detailed, "decisions": dm,
            "clock": {"receipts": len(clocks), "receipt_span": clock_span,
                       "valid_rtf_count": len(valid_rtf),
                       "rtf_min": min(valid_rtf) if valid_rtf else None,
                       "rtf_max": max(valid_rtf) if valid_rtf else None,
                       "hard_guarantee_status": "unknown"},
            "legacy_ready": [{"ready_ns": r["legacy_ready_ns"], "prepare_start_ns": r["prepare_start_ns"],
                              "prepare_deadline_ns": r["prepare_deadline_ns"]} for r in ready],
            "dependencies": dependencies, "stage_budget_dependency_matrix": stages,
            "stage_flags": {name: False for name in STAGE_FLAGS},
            "current_dynamic_recipe": {"schema": "p1-current-dynamic-recipe-predeclaration/v1",
                "status": "not_run", "measurement_ns": POLICY["dynamic_measurement_ns"],
                "T_ns": POLICY["T_ns"], "ready_ns": POLICY["ready_ns"],
                "prepare_ns": POLICY["prepare_ns"], "total_ns": POLICY["total_ns"], "close_ns": POLICY["close_ns"],
                "hooks": "normal exact zero", "domain": ["nonzero", "turn", "mixed"],
                "source_planar_speed_max_m_s": POLICY["source_planar_speed_max_m_s"],
                "source_stamp_gap_max_ns": POLICY["source_stamp_gap_max_ns"],
                "turn_reference_parameters_status": "unknown", "mixed_reference_parameters_status": "unknown",
                "execution_go": "not_run", "stage_qualified": False}}


def load_manifest(path):
    manifest = strict_json(Path(path).read_bytes())
    require(manifest["schema"] == "p1-C3.5-budget-preregister/v2" and canonical_equal(manifest["policy"], POLICY),
            "budget preregistration/policy identity differs")
    raw = {key: locked_bytes(key, pin) for key, pin in manifest["files"].items()}
    contract_path = next(key for key in raw if key.endswith("/p1_shadow_contract_v5.json"))
    contract = strict_json(raw[contract_path])
    runs = []
    for run in manifest["runs"]:
        data = {}
        for name, actual in run["files"].items():
            require(actual in raw, "run input outside preregistered pin closure")
            data[name] = ([strict_json(row) for row in raw[actual].splitlines() if row]
                          if name.endswith(".jsonl") else strict_json(raw[actual]))
        require(data["inputs.json"]["run_id"] == run["run_id"] and
                data["inputs.json"]["mode"] == run["mode"], "preregistered run identity differs")
        runs.append(data)
    return manifest, contract, runs


def analyze_manifest(path):
    manifest, contract, runs = load_manifest(path)
    reports = [analyze_data(data, contract) for data in runs]
    after = {key: hashlib.sha256(locked_bytes(key, pin)).hexdigest()
             for key, pin in manifest["files"].items()}
    observed_names = ("prepare_observed", "total_observed", "close_observed")
    observed_ok = all(r["dependencies"][key]["status"] == "passed"
                      for r in reports for key in observed_names)
    evidence = [{"run_id": r["run_id"], "mode": r["mode"],
                 "dependencies": {key: r["dependencies"][key] for key in observed_names}}
                for r in reports]
    rules = {
        "observed_runtime_budgets": {"status": "passed" if observed_ok else "failed",
            "evidence": evidence, "scope": "finite original prepare/total/close windows only; no WCET or phase qualification"},
        "observed_ready_gate": {"status": "passed" if all(
            r["dependencies"]["candidate_ready_observed"]["status"] == "passed"
            for r in reports if r["mode"] == "positive") else "failed", "evidence": [
            {"run_id": r["run_id"], "observation": r["dependencies"]["candidate_ready_observed"]}
            for r in reports], "scope": "23 finite native ready windows against unchanged 150ms gate; no hard bound"},
        "anchor_guard_observed": {"status": "passed", "evidence": [
            {"run_id": r["run_id"], "anchor_mismatch_count": r["decisions"]["anchor_mismatch_count"],
             "accepted_shadow": r["decisions"]["accepted_shadow"]} for r in reports],
            "scope": "independent immutable job/current Source/Witness joins; closing tail accepted is diagnostic only"},
        "anchor_execution_contract": {"status": "unknown", "evidence": [
            r["dependencies"]["nonzero_anchor_execution_contract"] for r in reports],
            "scope": "current moving legacy anchor conflicts with candidates; no executable anchor contract or nonzero regulator output"},
        "master_clock_hard_bound": {"status": "unknown", "evidence": None,
            "scope": "same boot CLOCK_MONOTONIC establishes local order; hard Master Clock bound unproved"},
        "plant_hold_interval": {"status": "unknown", "evidence": None,
            "scope": "publisher command has no actual plant acceptance/holding interval"},
        "worker_io_schedule_wcet": {"status": "unknown", "evidence": [
            {"run_id": r["run_id"], "native_worker_windows": r["native_worker_windows"]} for r in reports],
            "scope": "finite observed maxima are not worst-case guarantees"},
        "current_dynamic20s": {"status": "not_run", "evidence": [r["current_dynamic_recipe"] for r in reports],
            "scope": "20s recipe predeclaration does not inherit the actual 4s fixture qualification"},
        "current_turn_mixed": {"status": "not_run", "evidence": None,
            "scope": "turn/mixed values and current-version run remain required"},
        "current_stress_recovery_failed_close": {"status": "not_run", "evidence": None,
            "scope": "finite normal/pre-arm closure is not final unified-version stress/recovery/failed-close"},
    }
    return {"schema": "p1-C3.5-budget-matrix/v1", "component_status": "passed", "passed": True,
            "preregister": {"path": str(Path(path).resolve()),
                            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()},
            "input_count": len(after), "original_before_after_equal": True,
            "input_sha256_before": {key: pin["sha256"] for key, pin in manifest["files"].items()},
            "input_sha256_after": after, "runs": reports, "rules": rules,
            "qualifications": {name: False for name in STAGE_FLAGS},
            "stage_flags": {name: False for name in STAGE_FLAGS}}


def verify_report(report, data, contract):
    require(canonical_equal(report, analyze_data(data, contract)), "reported budget/state/qualification differs from independent derivation")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregister", type=Path,
                        default=Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/budget_scope/preregister_v2.json"))
    parser.add_argument("--out", "--output", dest="out", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_manifest(args.preregister)
    with args.out.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"component_status": report["component_status"],
                      "runs": len(report["runs"]), "input_count": report["input_count"],
                      "original_before_after_equal": report["original_before_after_equal"],
                      "stage_qualification_promoted": False}))


if __name__ == "__main__":
    main()
