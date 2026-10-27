"""Independent Witness v2 profiles; recording, BusinessReady and phase qualification differ."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re

SCHEMA = "p1-fixed-witness-v2"
PRODUCTION_PROFILE = "closed_shadow_observation"
EVALUATION_PROFILES = ("closed_shadow_observation", "normal_business")
NORMAL_CONTRACT_SCOPE = "Witness records and first real accepted activation/BusinessReady consistency only; no control or phase qualification"
CAPACITIES = {"tick": 256, "submit": 128, "activation": 128, "phase": 32}
STREAMS = tuple(CAPACITIES)
MAX_BYTES = 512 * 1024
MAX_JSON_DEPTH = 8
MAX_JSON_NODES = 32768
U64_MAX = (1 << 64) - 1
I64_MAX = (1 << 63) - 1
HEADER_FIELDS = frozenset(("run_id", "boot_id", "contract_sha256", "source_sha256",
                           "binary_sha256", "worker_binary_sha256", "worker_instance"))
HASH_FIELDS = frozenset(("contract_sha256", "source_sha256", "binary_sha256",
                         "worker_binary_sha256", "worker_instance"))
HEADER_LIMITS = {"run_id": 128, "boot_id": 36, "contract_sha256": 64,
                 "source_sha256": 64, "binary_sha256": 64,
                 "worker_binary_sha256": 64, "worker_instance": 64}
IDENTITY_FIELDS = frozenset(("job_id", "tick", "target_tick", "task_generation",
                             "model_generation", "config_generation",
                             "schedule_generation", "clock_epoch"))
COUNTER_FIELDS = frozenset(("attempts", "reserved", "published", "overflow", "rejected"))
ROOT_FIELDS = frozenset(("schema", "profile", "normal_contract_scope", "enabled", "closed",
                         "observation_complete", "business_ready_observed", "normal_contract_qualified", "overflow",
                         "incomplete", "clock_name", "header", "capacities", "counters",
                         *STREAMS, "first_failure"))
ROW_FIELDS = {
    "tick": IDENTITY_FIELDS | {"sequence", "planned_ns", "start_ns", "end_ns",
                               "skipped_ticks", "candidate_present", "failed_start",
                               "stopping_start", "failed_end", "stopping_end"},
    "submit": IDENTITY_FIELDS | {"sequence", "commit_ns", "failed", "stopping"},
    "activation": IDENTITY_FIELDS | {"sequence", "commit_ns", "ready_commit_ns",
                                     "accepted", "failed", "stopping", "reason_code"},
    "phase": frozenset(("sequence", "event_code", "observation_code", "ns", "tick",
                         "job_id", "candidate_present", "admission_slots", "pending_present",
                         "failed", "stopping", "pause_active")),
}
BOOL_FIELDS = {
    "tick": ("candidate_present", "failed_start", "stopping_start", "failed_end", "stopping_end"),
    "submit": ("failed", "stopping"),
    "activation": ("accepted", "failed", "stopping"),
    "phase": (),
}
PHASE_STATE_FIELDS = ("candidate_present", "pending_present", "failed", "stopping", "pause_active")


def _uint(v):
    return type(v) is int and 0 <= v <= U64_MAX


def _time(v, zero=False):
    return type(v) is int and (0 if zero else 1) <= v <= I64_MAX


def _bounded_string(v, limit):
    try:
        return (type(v) is str and 0 < len(v.encode("utf-8")) <= limit
                and not any(ord(c) < 32 or ord(c) == 127 for c in v))
    except UnicodeError:
        return False


def _header_valid(h):
    return (type(h) is dict and set(h) == HEADER_FIELDS
            and all(_bounded_string(h[k], limit) for k, limit in HEADER_LIMITS.items())
            and len(h["boot_id"].encode("utf-8")) == 36
            and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", h["boot_id"])
            and all(re.fullmatch(r"[0-9a-f]{64}", h[k]) for k in HASH_FIELDS))


def _normal_records_complete(rows, *, require_normal=True):
    """Recompute the bounded producer semantic condition; never trust its flag."""
    if set(rows) != set(STREAMS) or not rows["tick"]:
        return False
    phases = rows["phase"]
    closes = [r for r in phases if r["event_code"] == 7]
    if (len(closes) != 1 or closes[0] is not phases[-1]
            or closes[0]["observation_code"] != 6):
        return False
    if require_normal and any(r["event_code"] in (3, 4) or r["failed"] is True for r in phases):
        return False
    if require_normal and (any(r["failed_start"] or r["failed_end"] for r in rows["tick"])
            or any(r["failed"] for k in ("submit", "activation") for r in rows[k])):
        return False
    times = [r["ns"] for r in phases]
    for stream, field in (("tick", "end_ns"), ("submit", "commit_ns"), ("activation", "commit_ns")):
        times.extend(r[field] for r in rows[stream])
    if closes[0]["ns"] < max(times):
        return False
    for previous, current in zip(rows["tick"], rows["tick"][1:]):
        if current["start_ns"] < previous["end_ns"] or current["planned_ns"] <= previous["planned_ns"]:
            return False
        if current["schedule_generation"] == previous["schedule_generation"]:
            if current["tick"] != previous["tick"] + 1 + current["skipped_ticks"]:
                return False
        elif current["schedule_generation"] <= previous["schedule_generation"]:
            return False
    for stream in ("submit", "activation"):
        if any(c["commit_ns"] < p["commit_ns"] for p, c in zip(rows[stream], rows[stream][1:])):
            return False
    submits = {r["job_id"]: r for r in rows["submit"]}
    ticks = {r["job_id"]: r for r in rows["tick"] if r["candidate_present"]}
    activations = {r["job_id"]: r for r in rows["activation"]}
    if (len(submits) != len(rows["submit"]) or len(activations) != len(rows["activation"])
            or len(ticks) != sum(r["candidate_present"] for r in rows["tick"])
            or set(ticks) != set(activations)):
        return False
    for jid, a in activations.items():
        t, s = ticks.get(jid), submits.get(jid)
        if (s is None or t is None or t["tick"] != a["tick"]
                or not t["start_ns"] <= a["commit_ns"] <= t["end_ns"]
                or a["ready_commit_ns"] < s["commit_ns"] or a["commit_ns"] < s["commit_ns"]):
            return False
        if a["accepted"] and any(a[k] != s[k] or a[k] != t[k] for k in IDENTITY_FIELDS - {"tick"}):
            return False
    return True


def analyze(witness, expected_header, *, profile, require_enabled=True):
    """Check terminal structure and independent identity pins, retaining unknown phase states.

    The caller supplies the independently pinned header, not a copy taken from this witness.
    A structural gate is separate from later C0 source joins and R5 mechanism budgets.
    """
    issues = []

    def fail(code, category="structure", **detail):
        issues.append({"code": code, "category": category, **detail})

    def result():
        structural = not any(i["category"] not in ("completeness", "normal_business") for i in issues)
        enabled = type(witness) is dict and witness.get("enabled") is True
        complete = structural and enabled and not any(i["category"] != "normal_business" for i in issues)
        normal = complete and business_binding and normal_records
        passed = complete if profile == "closed_shadow_observation" else normal
        if not require_enabled and not enabled and profile == "closed_shadow_observation":
            passed = structural and not any(i["category"] != "normal_business" for i in issues)
        return {"schema": "p1-fixed-witness-check-v2", "passed": passed,
                "evaluation_profile": profile, "production_profile": PRODUCTION_PROFILE,
                "schema_valid": structural, "witness_complete": complete,
                "observation_complete": complete, "business_ready_observed": business_binding,
                "normal_business": normal, "normal_contract_qualified": normal,
                "normal_contract_scope": NORMAL_CONTRACT_SCOPE,
                "enabled": enabled, "scope": "terminal_fixed_witness_integrity_only",
                "activation_reason_dictionary": {
                    "0": "accepted", "1": "shutdown", "2": "run_unusable", "3": "other_rejected"},
                "activation_reason_covers_all_worker_gates": False,
                "phase_unknown_state_rows": unknown_phase_rows,
                "issues": issues, "source_join_verified": False,
                "expected_log_overflow_mechanism_passed": False,
                "normal_contract_complete": False, "execute_qualified": False,
                "phase_qualified": False, "research_conclusion": False}

    unknown_phase_rows = 0
    business_binding = normal_records = False
    if type(require_enabled) is not bool:
        fail("invalid_checker_mode")
    if type(profile) is not str or profile not in EVALUATION_PROFILES:
        fail("invalid_evaluation_profile")
    if type(witness) is not dict:
        fail("root_not_object")
        return result()
    if set(witness) != ROOT_FIELDS:
        fail("root_fields", missing=sorted(ROOT_FIELDS - set(witness)),
             unknown=sorted(set(witness) - ROOT_FIELDS))
    if witness.get("schema") != SCHEMA:
        fail("schema_version")
    if witness.get("profile") != PRODUCTION_PROFILE:
        fail("production_profile")
    if witness.get("normal_contract_scope") != NORMAL_CONTRACT_SCOPE:
        fail("normal_contract_scope")
    if witness.get("clock_name") != "CLOCK_MONOTONIC":
        fail("clock_domain")
    for k in ("enabled", "closed", "observation_complete", "business_ready_observed",
              "normal_contract_qualified", "overflow", "incomplete"):
        if type(witness.get(k)) is not bool:
            fail("flag_type", field=k)
    h = witness.get("header")
    if not _header_valid(h):
        fail("header_fields_or_types", category="identity")
    if not _header_valid(expected_header):
        fail("expected_header_invalid", category="identity")
    elif h != expected_header:
        fail("header_pin_mismatch", category="identity")
    caps = witness.get("capacities")
    if (type(caps) is not dict or set(caps) != set(CAPACITIES)
            or any(type(caps.get(k)) is not int or caps[k] != v for k, v in CAPACITIES.items())):
        fail("fixed_capacities")

    counters = witness.get("counters")
    counter_root = set(STREAMS) | {"ticks_without_candidate", "accepted_activations"}
    counters_ok = type(counters) is dict and set(counters) == counter_root
    if not counters_ok:
        fail("counter_fields")
        counters = {}
    for k in ("ticks_without_candidate", "accepted_activations"):
        if not _uint(counters.get(k)):
            fail("counter_type", field=k)
            counters_ok = False
    valid_counts = {}
    valid_rows = {}
    for stream, capacity in CAPACITIES.items():
        c = counters.get(stream)
        if (type(c) is not dict or set(c) != COUNTER_FIELDS
                or any(not _uint(v) for v in c.values())):
            fail("stream_counter_fields_or_types", stream=stream)
            counters_ok = False
        else:
            valid_counts[stream] = c
            if c["reserved"] > capacity or c["published"] > c["reserved"]:
                fail("counter_capacity", stream=stream)
            if c["overflow"] and c["reserved"] != capacity:
                fail("overflow_before_full_capacity", stream=stream)
            if c["attempts"] != c["reserved"] + c["overflow"] + c["rejected"]:
                fail("counter_accounting", stream=stream)
            if c["reserved"] != c["published"]:
                fail("unpublished_reservation", "completeness", stream=stream)
            if c["overflow"] or c["rejected"]:
                fail("stream_not_complete", "completeness", stream=stream)
        rows = witness.get(stream)
        if type(rows) is not list or len(rows) > capacity:
            fail("row_array_bounds", stream=stream)
            continue
        if stream in valid_counts and len(rows) != valid_counts[stream]["published"]:
            fail("published_row_count", "completeness", stream=stream)
        usable = []
        previous_sequence = 0
        for index, row in enumerate(rows):
            if type(row) is not dict or set(row) != ROW_FIELDS[stream]:
                fail("row_fields", stream=stream, index=index)
                continue
            before = len(issues)
            sequence = row["sequence"]
            if (not _uint(sequence) or sequence <= previous_sequence or sequence > capacity
                    or (stream in valid_counts and sequence > valid_counts[stream]["reserved"])):
                fail("row_sequence", stream=stream, index=index)
            elif sequence != index + 1:
                fail("reservation_sequence_gap", "completeness", stream=stream, index=index)
            if _uint(sequence):
                previous_sequence = sequence
            for k in BOOL_FIELDS[stream]:
                if type(row[k]) is not bool:
                    fail("row_bool_type", stream=stream, index=index, field=k)
            uint_fields = IDENTITY_FIELDS if stream != "phase" else ("tick", "job_id")
            for k in uint_fields:
                if not _uint(row[k]):
                    fail("row_uint_type", stream=stream, index=index, field=k)
            # Do not perform arithmetic or joins on a failed primitive type.
            # Malformed typed JSON must produce a finite failure report.
            if len(issues) != before:
                continue
            if stream == "tick":
                for k in ("planned_ns", "start_ns", "end_ns"):
                    if not _time(row[k]):
                        fail("row_time", stream=stream, index=index, field=k)
                if all(_time(row[k]) for k in ("planned_ns", "start_ns", "end_ns")):
                    if not row["planned_ns"] <= row["start_ns"] <= row["end_ns"]:
                        fail("tick_time_order", index=index)
                if not _uint(row["skipped_ticks"]):
                    fail("row_uint_type", stream=stream, index=index, field="skipped_ticks")
                if row["candidate_present"] is False and (row["job_id"] != 0 or row["target_tick"] != 0):
                    fail("tick_without_candidate_identity", index=index)
                if row["candidate_present"] is True and (row["job_id"] == 0 or row["target_tick"] != row["tick"]):
                    fail("candidate_tick_identity", index=index)
            elif stream in ("submit", "activation"):
                if not _time(row["commit_ns"]):
                    fail("row_time", stream=stream, index=index, field="commit_ns")
                if row["job_id"] == 0:
                    fail("commit_job_identity", stream=stream, index=index)
                if stream == "submit" and row["target_tick"] != row["tick"] + 1:
                    fail("submit_target_tick", index=index)
                if stream == "activation":
                    if not _time(row["ready_commit_ns"]):
                        fail("row_time", stream=stream, index=index, field="ready_commit_ns")
                    elif _time(row["commit_ns"]) and row["ready_commit_ns"] > row["commit_ns"]:
                        fail("activation_time_order", index=index)
                    if type(row["reason_code"]) is not int or row["reason_code"] not in range(4):
                        fail("activation_reason_code", index=index)
                    if row["accepted"] is True and row["reason_code"] != 0:
                        fail("accepted_without_attempt_commit", index=index)
                    if row["accepted"] is False and row["reason_code"] == 0:
                        fail("rejected_with_accepted_reason", index=index)
                    if row["target_tick"] != row["tick"]:
                        fail("activation_target_tick", index=index)
            else:
                if type(row["event_code"]) is not int or row["event_code"] not in range(1, 10):
                    fail("phase_event_code", index=index)
                if type(row["observation_code"]) is not int or row["observation_code"] not in range(7):
                    fail("phase_observation_code", index=index)
                if not _time(row["ns"]):
                    fail("phase_time", index=index)
                for k in PHASE_STATE_FIELDS:
                    if row[k] is not None and type(row[k]) is not bool:
                        fail("phase_state_type", index=index, field=k)
                if type(row["admission_slots"]) is not int or not -1 <= row["admission_slots"] <= 2:
                    fail("phase_admission_slots", index=index)
                if any(row[k] is None for k in PHASE_STATE_FIELDS) or row["admission_slots"] == -1:
                    unknown_phase_rows += 1
            if len(issues) == before:
                usable.append(row)
        if len(usable) == len(rows):
            valid_rows[stream] = usable

    failure = witness.get("first_failure")
    failure_ok = (type(failure) is dict and set(failure) == {"code", "stream", "ns", "ticket"}
                  and type(failure["code"]) is int and failure["code"] in range(8)
                  and type(failure["stream"]) is int and failure["stream"] in range(5)
                  and _time(failure["ns"], zero=True) and _uint(failure["ticket"]))
    if not failure_ok:
        fail("first_failure_fields_or_types")
    elif failure["code"] == 0 and any(failure[k] != 0 for k in ("stream", "ns", "ticket")):
        fail("no_failure_marker")
    elif failure["code"] != 0:
        # Header/close/write/unpublished failures can be detected after all
        # producer clocks are unavailable, so zero is an explicit unknown time.
        stream = failure["stream"]
        ticket = failure["ticket"]
        code = failure["code"]
        if code in (3, 5, 7) and (stream != 0 or ticket != 0):
            fail("failure_location")
        if code in (1, 2, 6) and stream == 0:
            fail("failure_location")
        if code in (2, 6) and ticket != 0:
            fail("failure_ticket")
        if code == 1 and stream in range(1, 5) and ticket != CAPACITIES[STREAMS[stream - 1]] + 1:
            fail("capacity_failure_ticket")
        fail("audit_first_failure", "completeness", failure_code=failure["code"])

    if failure_ok and failure["code"] == 0 and witness.get("incomplete") is True:
        fail("incomplete_without_first_failure")
    if failure_ok and failure["code"] == 0 and any(
            c["overflow"] or c["rejected"] or c["reserved"] != c["published"]
            for c in valid_counts.values()):
        fail("counter_failure_without_first_failure")
    if failure_ok and failure["code"] != 0 and witness.get("incomplete") is not True:
        fail("failure_without_incomplete_flag")
    if failure_ok and failure["stream"] in range(1, 5):
        failed_stream = STREAMS[failure["stream"] - 1]
        count = valid_counts.get(failed_stream)
        if count is not None:
            if failure["code"] == 1 and not count["overflow"]:
                fail("capacity_failure_without_overflow")
            if failure["code"] in (2, 6) and not count["rejected"]:
                fail("rejected_failure_without_rejection")

    if counters_ok and len(valid_counts) == 4:
        expected_overflow = any(c["overflow"] for c in valid_counts.values())
        if witness.get("overflow") is not expected_overflow:
            fail("overflow_flag_disagrees")
    if "tick" in valid_rows and _uint(counters.get("ticks_without_candidate")):
        if counters["ticks_without_candidate"] != sum(not r["candidate_present"] for r in valid_rows["tick"]):
            fail("tick_aggregate_count")
    if "activation" in valid_rows and _uint(counters.get("accepted_activations")):
        if counters["accepted_activations"] != sum(r["accepted"] for r in valid_rows["activation"]):
            fail("activation_aggregate_count")
    # The diagnostic tick, preparation and final-activation paths each have one
    # producer. Phase is MPSC; its reservation sequence is not clock order.
    for stream, time_field in (("tick", "start_ns"), ("submit", "commit_ns"),
                               ("activation", "commit_ns")):
        rows = valid_rows.get(stream, [])
        for previous, current in zip(rows, rows[1:]):
            if current[time_field] < previous[time_field]:
                fail("stream_time_reversal", stream=stream, sequence=current["sequence"])
            if stream == "tick":
                if current["start_ns"] < previous["end_ns"]:
                    fail("tick_intervals_overlap", sequence=current["sequence"])
                if current["planned_ns"] <= previous["planned_ns"]:
                    fail("tick_planned_time_reversal", sequence=current["sequence"])
                if current["schedule_generation"] == previous["schedule_generation"]:
                    if current["tick"] != previous["tick"] + 1 + current["skipped_ticks"]:
                        fail("tick_schedule_sequence", sequence=current["sequence"])
                elif current["schedule_generation"] <= previous["schedule_generation"]:
                    fail("schedule_generation_reversal", sequence=current["sequence"])
    if all(k in valid_rows for k in ("tick", "submit", "activation")):
        submits = {r["job_id"]: r for r in valid_rows["submit"]}
        ticks = {r["job_id"]: r for r in valid_rows["tick"] if r["candidate_present"]}
        activations = {r["job_id"]: r for r in valid_rows["activation"]}
        if len(submits) != len(valid_rows["submit"]):
            fail("duplicate_submit_job")
        if len(ticks) != sum(r["candidate_present"] for r in valid_rows["tick"]):
            fail("duplicate_candidate_tick_job")
        if len(activations) != len(valid_rows["activation"]):
            fail("duplicate_activation_job")
        if set(ticks) != set(activations):
            fail("candidate_attempt_coverage", "completeness")
        for jid, a in activations.items():
            t, s = ticks.get(jid), submits.get(jid)
            if s is None:
                fail("activation_without_submit", job_id=jid)
            if t is not None and not (t["tick"] == a["tick"] and t["start_ns"] <= a["commit_ns"] <= t["end_ns"]):
                fail("activation_tick_commit", job_id=jid)
            if s is not None:
                if a["ready_commit_ns"] < s["commit_ns"]:
                    fail("ready_before_submit", job_id=jid)
                if a["commit_ns"] < s["commit_ns"]:
                    fail("activation_before_submit", job_id=jid)
            if a["accepted"] and s is not None and t is not None:
                for k in IDENTITY_FIELDS - {"tick"}:
                    if a[k] != s[k] or a[k] != t[k]:
                        fail("accepted_identity_mismatch", job_id=jid, field=k)

    # A terminal library snapshot is insufficient evidence of a running B1/C0
    # case. BusinessReady observes the first real accepted activation; it does
    # not mean startup readiness or authorize a subsequent action.
    if witness.get("enabled") is True:
        if "tick" in valid_rows and not valid_rows["tick"]:
            fail("no_actual_ticks", "completeness")
        if "phase" in valid_rows:
            close_rows = [r for r in valid_rows["phase"] if r["event_code"] == 7]
            ready_rows = [r for r in valid_rows["phase"] if r["event_code"] == 9]
            if len(close_rows) != 1:
                fail("terminal_close_count", "completeness", observed=len(close_rows))
            else:
                close = close_rows[0]
                if valid_rows["phase"] and close["sequence"] != valid_rows["phase"][-1]["sequence"]:
                    fail("terminal_close_not_last_phase")
                observed_times = [r["ns"] for r in valid_rows["phase"]]
                for stream, field in (("tick", "end_ns"), ("submit", "commit_ns"),
                                      ("activation", "commit_ns")):
                    observed_times.extend(r[field] for r in valid_rows.get(stream, []))
                if observed_times and close["ns"] < max(observed_times):
                    fail("terminal_close_before_producers")
            accepted = [r for r in valid_rows.get("activation", []) if r["accepted"]]
            if ready_rows:
                if len(ready_rows) != 1:
                    fail("business_ready_count", observed=len(ready_rows))
                elif not accepted:
                    fail("business_ready_without_accepted_activation")
                else:
                    first = min(accepted, key=lambda r: (r["commit_ns"], r["sequence"]))
                    ready = ready_rows[0]
                    business_binding = (ready["observation_code"] == 2 and
                        (ready["ns"], ready["tick"], ready["job_id"]) ==
                        (first["commit_ns"], first["tick"], first["job_id"]))
                    if not business_binding:
                        fail("business_ready_activation_binding")
            if accepted and not business_binding:
                fail("real_business_ready_not_observed", "normal_business")
            if not accepted:
                fail("no_accepted_activation", "normal_business")

    normal_records = _normal_records_complete(valid_rows)
    internal_complete = (witness.get("enabled") is True and witness.get("closed") is True
        and witness.get("incomplete") is False and witness.get("overflow") is False
        and _header_valid(h) and failure_ok and failure["code"] == 0
        and len(valid_counts) == 4 and all(c["reserved"] == c["published"]
            and not c["overflow"] and not c["rejected"] for c in valid_counts.values()))
    ready_count = sum(r["event_code"] == 9 for r in valid_rows.get("phase", []))
    observation_records = (_normal_records_complete(valid_rows, require_normal=False)
                           and (ready_count == 0 or (ready_count == 1 and business_binding)))
    producer_observation = internal_complete and observation_records
    if witness.get("observation_complete") is not producer_observation:
        fail("producer_observation_complete_disagrees")
    if witness.get("business_ready_observed") is not business_binding:
        fail("producer_business_ready_disagrees")
    producer_normal = producer_observation and business_binding and normal_records
    if witness.get("normal_contract_qualified") is not producer_normal:
        fail("producer_normal_contract_disagrees")
    if not normal_records:
        fail("normal_record_conditions_not_met", "normal_business")
    if witness.get("enabled") is False:
        if any(witness.get(k) for k in STREAMS) or (counters_ok and any(
                any(c.values()) for c in valid_counts.values())) or counters.get("ticks_without_candidate", 0) or counters.get("accepted_activations", 0):
            fail("disabled_has_records")
        if require_enabled:
            fail("witness_disabled", "completeness")
    elif witness.get("observation_complete") is not True:
        fail("observation_not_complete", "completeness")
    if witness.get("closed") is not True:
        fail("witness_not_closed", "completeness")
    if witness.get("incomplete") is not False or witness.get("overflow") is not False:
        fail("observation_incomplete_or_overflow", "completeness")
    return result()


def load_json(path):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("witness/identity JSON empty or exceeds finite byte budget")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON key: " + key)
            out[key] = value
        return out

    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except RecursionError as error:
        raise ValueError("witness/identity JSON nesting exceeds parser budget") from error
    pending = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > MAX_JSON_DEPTH or visited > MAX_JSON_NODES:
            raise ValueError("witness/identity JSON exceeds finite shape budget")
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("nonfinite JSON number")
    return value, hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--expected-header", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--witness-sha256")
    parser.add_argument("--profile", required=True, choices=EVALUATION_PROFILES)
    args = parser.parse_args(argv)
    try:
        witness, digest = load_json(args.witness)
        expected, expected_digest = load_json(args.expected_header)
        report = analyze(witness, expected, profile=args.profile)
        report["evidence_sha256"] = {str(args.witness): digest, str(args.expected_header): expected_digest}
        if args.witness_sha256 is not None and digest != args.witness_sha256:
            report["passed"] = report["witness_complete"] = report["observation_complete"] = report["normal_business"] = report["normal_contract_qualified"] = False
            report["issues"].append({"code": "witness_file_hash_mismatch", "category": "identity"})
    except (OSError, UnicodeError, ValueError) as error:
        report = {"schema": "p1-fixed-witness-check-v2", "passed": False,
                  "witness_complete": False, "observation_complete": False, "normal_business": False,
                  "normal_contract_qualified": False, "business_ready_observed": False,
                  "evaluation_profile": args.profile, "phase_qualified": False,
                  "research_conclusion": False, "issues": [{"code": "input_unreadable", "detail": str(error)}],
                  "expected_log_overflow_mechanism_passed": False, "execute_qualified": False}
    try:
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(report, target, indent=2, allow_nan=False)
            target.write("\n")
    except OSError as error:
        # Never overwrite or silently retry a partial/existing evidence record.
        print(json.dumps({"passed": False, "witness_complete": False,
                          "issues": [{"code": "report_write_failed", "detail": str(error)}]}))
        return 2
    print(json.dumps({k: report[k] for k in ("passed", "witness_complete", "issues")}))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
