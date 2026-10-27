#!/usr/bin/env python3
"""Strict, read-only D0 SOURCE observation validation; no ROS or bag decoding.

A successful result validates the recorded observation contract and finite source
counts. It does not certify native/model equivalence, unchanged runtime timing,
source flush, plant time, physical acceptance, or a dynamic research domain.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys

SCHEMA = "p1-d0-observation-v1"
CANONICAL_KEYS = set("type schema run_id boot_id contract_hash worker_instance model_generation config_generation mode sequence tick job_id task_generation schedule_generation epoch planned_ns start_ns cutoff_commit_ns ready_commit_ns activation_commit_ns end_ns skipped_ticks accepted diagnostic_only reason control_source target_state activation_state state_error requested_n final_n publish_success publish_start_ns publish_end_ns previous_anchor_known publish_sim_ns publish_epoch publish_clock_age_ns activation_clock_sim_ns activation_clock_receive_ns activation_rtf activation_odom_stamp_ns activation_odom_receive_ns activation_odom_sequence activation_imu_stamp_ns activation_imu_receive_ns activation_imu_sequence activation_r_from_imu previous_n previous_publish_ns anchor_known anchor_sequence odom_age_ns imu_age_ns clock_age_ns normal_contract_complete rho_available plant_acceptance_observed".split())
OBS_KEYS = set("schema candidate_pair_available candidate_job_id candidate_target_tick prediction_target_sim_ns predict_invoked predict_success predict_status predicted_state_available predicted_state full_error_available full_error validation_snapshot input_change_gate_ran input_change_gate_unchanged final_snapshot".split())
VERSION_KEYS = {"task", "model", "config", "schedule", "epoch"}
SOURCE_KEYS = set("odom_sequence odom_stamp_ns odom_receive_ns imu_sequence imu_stamp_ns imu_receive_ns r_from_imu clock_sim_ns clock_receive_ns rtf rtf_valid paused".split())
VALIDATION_KEYS = SOURCE_KEYS | {"sample_ns", "copy_capture_ns", "capture_semantics", "version", "state", "anchor", "history_count", "held_history"}
FINAL_KEYS = SOURCE_KEYS | {"commit_ns", "version"}
JOB_IDENTITIES = "run_id boot_id contract_hash nominal_hash worker_instance".split()
CANONICAL_VERSION = {"task": "task_generation", "model": "model_generation", "config": "config_generation", "schedule": "schedule_generation", "epoch": "epoch"}
STATE_ATOL = 1e-10

class Invalid(ValueError):
    pass

def need(condition, message):
    if not condition:
        raise Invalid(message)

def integer(value, name, maximum=(1 << 63) - 1):
    need(type(value) is int and 0 <= value <= maximum, f"{name}: bounded nonnegative JSON integer required")
    return value

def number(value, name):
    need(type(value) in (int, float) and math.isfinite(value), f"{name}: finite JSON number required")
    return value

def boolean(value, name):
    need(type(value) is bool, f"{name}: JSON boolean required")
    return value

def vector(value, size, name):
    need(type(value) is list and len(value) == size, f"{name}: array length {size} required")
    return [number(x, f"{name}[{i}]") for i, x in enumerate(value)]

def exact_keys(value, keys, name):
    need(type(value) is dict and set(value) == keys, f"{name}: exact key set required")

def same_vector(a, b, name):
    aa = vector(a, len(b), name)
    need(all(abs(x - y) <= STATE_ATOL for x, y in zip(aa, b)), f"{name}: value mismatch")

def full_error(prediction, target):
    errors = []
    for i, (a, b) in enumerate(zip(prediction, target)):
        e = a - b
        if not math.isfinite(e):
            return None
        if i == 2:
            e = math.atan2(math.sin(e), math.cos(e))
        if not math.isfinite(e):
            return None
        errors.append(e)
    return errors

def strict_loads(text):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, f"duplicate JSON key: {k}")
            result[k] = v
        return result
    def constant(value):
        raise Invalid(f"nonfinite JSON literal: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)

def read_events(path):
    events = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        need(bool(line.strip()), f"line {i}: empty JSONL row")
        try:
            event = strict_loads(line)
            need(type(event) is dict and type(event.get("type")) is str, "object with type required")
            events.append(event)
        except (Invalid, ValueError) as exc:
            raise Invalid(f"line {i}: {exc}") from exc
    return events

def snapshot(s, final, contract):
    name = "final_snapshot" if final else "validation_snapshot"
    exact_keys(s, FINAL_KEYS if final else VALIDATION_KEYS, name)
    exact_keys(s["version"], VERSION_KEYS, name + ".version")
    for key, value in s["version"].items():
        integer(value, name + ".version." + key, (1 << 64) - 1)
    for key in SOURCE_KEYS - {"r_from_imu", "rtf", "rtf_valid", "paused"}:
        integer(s[key], name + "." + key)
    for key in ["r_from_imu", "rtf_valid", "paused"]:
        boolean(s[key], name + "." + key)
    number(s["rtf"], name + ".rtf")
    integer(s["commit_ns"] if final else s["sample_ns"], name + ".time")
    if final:
        return
    integer(s["copy_capture_ns"], name + ".copy_capture_ns")
    need(s["capture_semantics"] == "mutex_copy_end", "copy capture semantics mismatch")
    need(s["copy_capture_ns"] >= s["sample_ns"], "copy capture precedes prelock assessment")
    # Source receipt can be after prelock sample, but not after the actual copy.
    for key in ["odom_receive_ns", "imu_receive_ns", "clock_receive_ns"]:
        need(s[key] <= s["copy_capture_ns"], "source receipt after mutex copy")
    vector(s["state"], 6, "validation state")
    exact_keys(s["anchor"], {"n", "sequence", "publish_ns", "known"}, "anchor")
    vector(s["anchor"]["n"], 2, "anchor.n")
    for key in ["sequence", "publish_ns", "known"]:
        need(type(s["anchor"][key]) is list and len(s["anchor"][key]) == 2, "anchor shape")
        for x in s["anchor"][key]:
            boolean(x, "anchor.known") if key == "known" else integer(x, "anchor." + key)
    integer(s["history_count"], "history_count")
    need(type(s["held_history"]) is list and len(s["held_history"]) == s["history_count"], "history count mismatch")
    need(s["history_count"] <= contract["history_capacity"], "history exceeds contract capacity")
    previous = -1
    for entry in s["held_history"]:
        exact_keys(entry, {"sim_ns", "channel", "value"}, "history entry")
        integer(entry["sim_ns"], "history.sim_ns")
        need(entry["sim_ns"] >= previous, "history out of order")
        previous = entry["sim_ns"]
        integer(entry["channel"], "history.channel", 1)
        number(entry["value"], "history.value")

def source_binding(s, odoms, imus, clocks):
    if s["odom_sequence"]:
        need(s["odom_sequence"] in odoms, "snapshot references missing/invalid odom")
        o = odoms[s["odom_sequence"]]
        need((s["odom_stamp_ns"], s["odom_receive_ns"]) == (o["stamp_ns"], o["receive_ns"]), "snapshot odom provenance mismatch")
        if "state" in s:
            expected = list(o["state"])
            if s["r_from_imu"]:
                need(s["imu_sequence"] in imus, "used IMU is missing/invalid")
                expected[5] = imus[s["imu_sequence"]]["r_value"]
            same_vector(s["state"], expected, "validation raw state/source")
    else:
        need(s["odom_stamp_ns"] == s["odom_receive_ns"] == 0, "missing odom has fabricated stamp/receipt")
    if s["imu_sequence"]:
        need(s["imu_sequence"] in imus, "raw IMU provenance is missing/invalid")
        m = imus[s["imu_sequence"]]
        need((s["imu_stamp_ns"], s["imu_receive_ns"]) == (m["stamp_ns"], m["receive_ns"]), "snapshot raw IMU provenance mismatch")
    else:
        need(s["imu_stamp_ns"] == s["imu_receive_ns"] == 0 and not s["r_from_imu"], "missing IMU has fabricated provenance")
    if s["clock_receive_ns"]:
        key = (s["version"]["epoch"], s["clock_receive_ns"], s["clock_sim_ns"])
        need(key in clocks, "snapshot clock is missing or from a different epoch")
        c = clocks[key]
        need(s["rtf_valid"] == c["rtf_valid"] and abs(s["rtf"] - c["rtf"]) <= STATE_ATOL, "snapshot clock RTF mismatch")
        # paused/schedule can change in the tick without a new clock callback.
    else:
        need(s["clock_sim_ns"] == 0 and not s["rtf_valid"], "missing clock fabricated qualification")

def canonical(d):
    exact_keys(d, CANONICAL_KEYS | {"d0_observation"}, "decision source")
    need(d["type"] == "decision" and d["schema"] == "p1-execution-decision-v2", "canonical decision schema changed")
    need(d["mode"] == "no_output" and d["diagnostic_only"] is True, "dedicated diagnostic mode changed")
    for key in ["accepted", "normal_contract_complete", "rho_available", "plant_acceptance_observed", "activation_r_from_imu"]:
        boolean(d[key], "canonical." + key)
    need(not d["normal_contract_complete"] and not d["plant_acceptance_observed"] and not d["rho_available"], "no_output upgraded to physical qualification")
    for key in ["run_id", "boot_id", "contract_hash", "worker_instance", "reason", "control_source"]:
        need(type(d[key]) is str and len(d[key]) <= (256 if key == "reason" else 128), "canonical string type/bound")
    array_bool = {"publish_success", "previous_anchor_known", "anchor_known"}
    array_number = {"requested_n", "final_n", "previous_n"}
    array_time = {"publish_start_ns", "publish_end_ns", "publish_sim_ns", "publish_epoch", "publish_clock_age_ns", "previous_publish_ns", "anchor_sequence"}
    for key in array_bool | array_time:
        need(type(d[key]) is list and len(d[key]) == 2, "canonical channel shape")
        for value in d[key]:
            boolean(value, key) if key in array_bool else integer(value, key)
    for key in array_number:
        vector(d[key], 2, key)
    for key in ["target_state", "activation_state", "state_error"]:
        need(type(d[key]) is list and len(d[key]) == 6, "canonical state shape")
        for x in d[key]:
            # C++ JSON serializes nonfinite to null; unavailable observation is
            # separately explicit. Accepted canonical states must be finite.
            if x is not None:
                number(x, key)
            elif d["accepted"]:
                raise Invalid("accepted canonical state contains null")
    number(d["activation_rtf"], "canonical.activation_rtf")
    string_keys = {"type", "schema", "mode", "run_id", "boot_id", "contract_hash", "worker_instance", "reason", "control_source"}
    skip = string_keys | array_bool | array_number | array_time | {"target_state", "activation_state", "state_error", "activation_rtf", "accepted", "normal_contract_complete", "rho_available", "plant_acceptance_observed", "activation_r_from_imu", "diagnostic_only", "d0_observation"}
    for key in CANONICAL_KEYS - skip:
        integer(d[key], "canonical." + key)
    need(not any(d["publish_success"]) and not any(d["publish_start_ns"]) and not any(d["publish_end_ns"]), "no_output has physical publish claims")


def validate_decision(d, jobs, registrations, odoms, imus, clocks, contract, identity):
    canonical(d)
    for key in ["run_id", "boot_id", "contract_hash"]:
        need(d[key] == identity[key], "foreign decision " + key)
    o = d["d0_observation"]
    exact_keys(o, OBS_KEYS, "d0_observation")
    need(o["schema"] == SCHEMA, "D0 schema mismatch")
    for key in ["candidate_pair_available", "predict_invoked", "predict_success", "predicted_state_available", "full_error_available", "input_change_gate_ran"]:
        boolean(o[key], "observation." + key)
    v, f = o["validation_snapshot"], o["final_snapshot"]
    snapshot(v, False, contract); snapshot(f, True, contract)
    need(v["sample_ns"] == d["start_ns"] and f["commit_ns"] == d["activation_commit_ns"], "snapshot phase time mismatch")
    need(v["copy_capture_ns"] <= f["commit_ns"] <= d["end_ns"], "copy/commit/end order")
    for key, mapped in CANONICAL_VERSION.items():
        need(v["version"][key] == d[mapped], "validation/decision version mismatch")
    for key in ["odom_receive_ns", "imu_receive_ns", "clock_receive_ns"]:
        need(f[key] <= f["commit_ns"], "final source receipt after commit")
    source_binding(v, odoms, imus, clocks); source_binding(f, odoms, imus, clocks)
    for kind in ["odom", "imu"]:
        for suffix in ["stamp_ns", "receive_ns", "sequence"]:
            value = f[kind + "_" + suffix] if kind == "odom" or f["r_from_imu"] else 0
            need(d["activation_" + kind + "_" + suffix] == value, "canonical final source differs from observation")
    need(d["activation_r_from_imu"] == f["r_from_imu"], "final mixed flag mismatch")
    need(d["activation_clock_sim_ns"] == f["clock_sim_ns"] and d["activation_clock_receive_ns"] == f["clock_receive_ns"] and abs(d["activation_rtf"] - f["rtf"]) <= STATE_ATOL, "canonical final clock mismatch")
    need(d["odom_age_ns"] == f["commit_ns"] - f["odom_receive_ns"] and d["imu_age_ns"] == (f["commit_ns"] - f["imu_receive_ns"] if f["r_from_imu"] else 0) and d["clock_age_ns"] == f["commit_ns"] - f["clock_receive_ns"], "canonical final ages mismatch")
    if o["input_change_gate_ran"]:
        boolean(o["input_change_gate_unchanged"], "gate unchanged")
        unchanged = v["version"] == f["version"] and v["odom_sequence"] == f["odom_sequence"] and v["imu_sequence"] == f["imu_sequence"]
        need(o["input_change_gate_unchanged"] == unchanged, "input-change gate misreports actual compared values")
    else:
        need(o["input_change_gate_unchanged"] is None, "skipped gate must have null result")
    if not o["candidate_pair_available"]:
        need(d["job_id"] == 0, "no pair has canonical job")
        need(all(d[k] == [0.0] * 6 for k in ["target_state", "activation_state", "state_error"]), "no-pair canonical initializer changed")
        need(all(o[k] is None for k in ["candidate_job_id", "candidate_target_tick", "prediction_target_sim_ns", "predicted_state", "full_error"]), "unavailable no-pair values must be null")
        need(not any(o[k] for k in ["predict_invoked", "predict_success", "predicted_state_available", "full_error_available"]) and o["predict_status"] == "not_attempted", "no-pair fabricated prediction")
    else:
        integer(o["candidate_job_id"], "candidate_job_id", (1 << 64) - 1)
        integer(o["candidate_target_tick"], "candidate_target_tick", (1 << 64) - 1)
        integer(o["prediction_target_sim_ns"], "prediction_target_sim_ns")
        need(o["candidate_job_id"] == d["job_id"] and d["job_id"] in jobs, "candidate/decision/job link mismatch")
        j = jobs[d["job_id"]]
        need(d["job_id"] in registrations, "paired candidate lacks accepted registration")
        need(d["ready_commit_ns"] == registrations[d["job_id"]]["ready_commit_ns"], "candidate ready time differs from actual registration")
        need(o["candidate_target_tick"] == d["tick"] == j["target_tick"] and o["prediction_target_sim_ns"] == j["target_sim_ns"], "candidate target changed")
        need(j["target_ns"] == d["planned_ns"], "activation target tick time mismatch")
        for key in ["run_id", "boot_id", "contract_hash", "worker_instance"]:
            need(j[key] == d[key], "foreign candidate job " + key)
        need(j["nominal_hash"] == contract["nominal_hash"], "foreign job nominal hash")
        same_vector(d["target_state"], vector(j["target_state"], 6, "job.target_state"), "canonical job target")
        need(o["predict_invoked"], "pair prediction was not invoked")
        need(o["predict_status"] == ("success" if o["predict_success"] else "history_or_time_failed"), "prediction status mismatch")
        if not o["predict_success"]:
            need(not o["predicted_state_available"] and d["activation_state"] == [0.0] * 6 and d["state_error"] == [0.0] * 6, "failed predict changed canonical initializers")
        if o["predicted_state_available"]:
            need(o["predict_success"], "failed prediction has available state")
            predicted = vector(o["predicted_state"], 6, "predicted_state")
            same_vector(d["activation_state"], predicted, "canonical observed prediction")
            error = full_error(predicted, vector(j["target_state"], 6, "job.target_state"))
            need(o["full_error_available"] == (error is not None), "full error availability misreported")
            if error is not None:
                same_vector(o["full_error"], error, "full wrapped error")
            else:
                need(o["full_error"] is None, "nonfinite full error must be null")
        else:
            need(o["predicted_state"] is None and not o["full_error_available"] and o["full_error"] is None, "unavailable prediction/error must be null")
            if o["predict_success"]:
                need(any(x is None for x in d["activation_state"]), "finite successful canonical prediction hidden as unavailable")
    if d["accepted"]:
        need(o["candidate_pair_available"] and o["predict_success"] and o["predicted_state_available"] and o["full_error_available"] and o["input_change_gate_ran"] and o["input_change_gate_unchanged"], "accepted without observed prediction and unchanged-source gate")
        need(d["reason"] == "" and f["rtf_valid"] and not f["paused"], "accepted has rejection/clock invalidity")
        need(all(abs(x) <= t for x, t in zip(o["full_error"], contract["activation_tolerance"])), "accepted state exceeds tolerance")
        j = jobs[d["job_id"]]
        for key, mapped in CANONICAL_VERSION.items():
            jobkey = "clock_epoch" if key == "epoch" else mapped
            need(j[jobkey] == v["version"][key], "accepted job/snapshot version mismatch")
        need(j["freeze_ns"] <= d["ready_commit_ns"] <= j["deadline_ns"] < d["cutoff_commit_ns"] <= f["commit_ns"], "accepted ready/cutoff deadline order")
        need(j["target_ns"] <= f["commit_ns"] <= j["target_ns"] + contract["tick_jitter_ns"], "accepted activation early or beyond jitter")
        need(contract["rtf_low"] <= f["rtf"] <= contract["rtf_high"], "accepted RTF outside finite contract")
        need(0 < f["clock_receive_ns"] <= f["commit_ns"] and d["clock_age_ns"] <= contract["clock_age_ns"], "accepted clock receipt stale/future")
        sim_now = f["clock_sim_ns"] + f["commit_ns"] - f["clock_receive_ns"]
        need(abs(sim_now - j["target_sim_ns"]) <= contract["target_sim_slack_ns"], "accepted target sim alignment mismatch")
        used = ["odom"] + (["imu"] if f["r_from_imu"] else [])
        for source in used:
            need(f[source + "_sequence"] > 0 and 0 < f[source + "_receive_ns"] <= f["commit_ns"], "accepted source missing/future receipt")
            need(f["commit_ns"] - f[source + "_receive_ns"] <= contract[source + "_age_ns"], "accepted source receipt stale")
            lag = sim_now - f[source + "_stamp_ns"]
            need(-contract["source_future_slack_ns"] <= lag <= contract[source + "_sim_lag_ns"], "accepted source sim lag/future")
        if f["r_from_imu"]:
            need(abs(f["imu_stamp_ns"] - f["odom_stamp_ns"]) <= contract["mixed_skew_ns"], "accepted mixed source skew")
    return o


def validate_events(events, contract, expected_identity=None):
    issues = []
    phases = collections.Counter()
    samples = []
    identities = []
    jobs, odoms, imus, clocks, registrations = {}, {}, {}, {}, {}
    registration_events = []
    decisions, summaries = [], []
    consumed = set()
    lifecycle = collections.Counter()
    try:
        need(type(events) is list and bool(events), "source has no rows")
        need(type(contract) is dict and contract.get("schema") == "p1-execution-contract-v2" and type(contract.get("diagnostic_contract_revision")) is int and contract["diagnostic_contract_revision"] == 5, "D0 only supports unchanged diagnostic revision5")
        integer(contract["history_capacity"], "history capacity")
        vector(contract["activation_tolerance"], 6, "activation tolerance")
        for index, event in enumerate(events):
            need(type(event) is dict and type(event.get("type")) is str, "source row object/type required")
            kind = event["type"]
            lifecycle[kind] += 1
            if kind in ["odom_admission", "imu_admission"]:
                boolean(event["valid"], kind + ".valid")
            if kind == "startup":
                identities.append({"run_id": event["run_id"], "boot_id": event["boot"], "contract_hash": event["contract_hash"]})
                integer(event["physical_publisher_endpoints"], "startup physical endpoint count")
                need(event["mode"] == "no_output" and event["clock"] == "CLOCK_MONOTONIC" and event["physical_publisher_endpoints"] == 0, "startup mode/clock/physical mismatch")
            elif kind == "job":
                j = event["job"]
                integer(j["job_id"], "job id", (1 << 64) - 1)
                need(j["job_id"] > 0 and j["job_id"] not in jobs, "duplicate/zero job id")
                need(j["schema"] == "p1-solve-job-v1" and j["N"] == 20 and j["dt"] == .2, "job shape/schema mismatch")
                for key in JOB_IDENTITIES:
                    need(type(j[key]) is str, "job identity string required")
                for key in ["target_tick", "target_ns", "target_sim_ns", "tick_origin_ns", "deadline_ns", "freeze_ns", "task_generation", "model_generation", "config_generation", "schedule_generation", "clock_epoch"]:
                    integer(j[key], "job." + key)
                need(j["target_ns"] == j["tick_origin_ns"] + 200000000 and j["deadline_ns"] == j["tick_origin_ns"] + 150000000, "job absolute time contract")
                vector(j["target_state"], 6, "job target")
                jobs[j["job_id"]] = j
            elif kind in ["odom_admission", "imu_admission"] and event.get("valid") is True:
                integer(event["sequence"], kind + ".sequence")
                need(event["accepted_sequence"] == event["sequence"], "valid admission did not accept its sequence")
                target = odoms if kind == "odom_admission" else imus
                need(event["sequence"] not in target, "duplicate source admission sequence")
                integer(event["stamp_ns"], "admission stamp"); integer(event["receive_ns"], "admission receipt")
                if kind == "odom_admission":
                    vector(event["state"], 6, "odom state")
                    need(event["pose_frame"] == contract["expected_pose_frame"] and event["child_frame"] == contract["expected_child_frame"] and event["pose_frame_truncated"] is False and event["child_frame_truncated"] is False, "valid odom frame mismatch")
                else:
                    number(event["r_value"], "IMU yaw rate")
                    need(event["frame_id"] == contract["expected_imu_frame"] and event["frame_truncated"] is False, "valid IMU frame mismatch")
                target[event["sequence"]] = event
            elif kind == "clock":
                for key in ["epoch", "receive_ns", "sim_ns"]:
                    integer(event[key], "clock." + key)
                number(event["rtf"], "clock.rtf"); boolean(event["rtf_valid"], "clock.rtf_valid")
                key = (event["epoch"], event["receive_ns"], event["sim_ns"])
                need(key not in clocks, "duplicate clock identity")
                clocks[key] = event
            elif kind == "candidate_registration":
                boolean(event["accepted_registration"], "accepted_registration")
                integer(event["ready_commit_ns"], "registration ready")
                need(type(event["reason"]) is str, "registration reason string")
                registration_events.append(event)
                if event["accepted_registration"]:
                    j = event["job"]
                    need(j["job_id"] in jobs and exact_json(j, jobs[j["job_id"]]), "accepted candidate registration differs from submitted job")
                    need(j["job_id"] not in registrations, "duplicate accepted candidate registration")
                    need(event["worker_instance"] == j["worker_instance"] and event["reason"] == "", "accepted registration worker/reason mismatch")
                    vector(event["first_control"], 2, "registration first_control")
                    for key in ["solve_start_ns", "solve_end_ns"]:
                        integer(event[key], "registration." + key)
                    need(j["freeze_ns"] <= event["solve_start_ns"] <= event["solve_end_ns"] <= event["ready_commit_ns"] <= j["deadline_ns"], "accepted registration timing/deadline")
                    registrations[j["job_id"]] = event
                else:
                    # Rejected foreign echoes may legitimately have no submitted
                    # job; rejection observation must not claim they were used.
                    need(bool(event["reason"]), "rejected registration missing reason")
            elif kind == "decision":
                decisions.append(event)
            elif kind == "source_summary":
                summaries.append((index, event))
        need(len(identities) == 1, "exactly one startup identity required")
        identity = identities[0]
        if expected_identity is not None:
            need(identity == expected_identity, "source differs from externally expected identity")
        need(bool(decisions), "no decisions observed")
        need([d["sequence"] for d in decisions] == list(range(1, len(decisions) + 1)), "decision sequence gap/duplicate/reorder")
        for j in jobs.values():
            need(all(j[k] == identity[k] for k in ["run_id", "boot_id", "contract_hash"]), "foreign source job identity")
        for d in decisions:
            try:
                o = validate_decision(d, jobs, registrations, odoms, imus, clocks, contract, identity)
                if o["candidate_pair_available"]:
                    need(d["job_id"] not in consumed, "candidate consumed more than once")
                    consumed.add(d["job_id"])
                phases[o["predict_status"]] += 1
                phases["gate_ran" if o["input_change_gate_ran"] else "gate_skipped"] += 1
                if o["full_error_available"]:
                    phases["full_error_available"] += 1
                    samples.append(o["full_error"])
            except (Invalid, KeyError, TypeError, ValueError, OverflowError) as exc:
                issues.append(f"decision {d.get('sequence')}: {exc}")
        need(len(summaries) == 1 and summaries[0][0] == len(events) - 1, "exactly one terminal source_summary required")
        summary = summaries[0][1]
        for key in ["generated", "emitted", "dropped", "finished_ns"]:
            integer(summary[key], "source_summary." + key)
        boolean(summary["normal_source_complete"], "source_summary.normal_source_complete")
        need(summary["emitted"] == len(events) - 1, "emitted count differs from parsed source rows")
        need(summary["generated"] == summary["emitted"] and summary["dropped"] == 0 and summary["normal_source_complete"], "source completeness not proven: generation/drop/failure")
        counts_closed = True
    except (Invalid, KeyError, TypeError, ValueError, OverflowError) as exc:
        issues.append(str(exc))
        counts_closed = False
    return {"schema": "p1-d0-source-check-v1", "passed": not issues and counts_closed, "issues": issues,
            "source_counts_closed": counts_closed, "source_rows": len(events), "decision_count": len(decisions),
            "phase_counts": {k: phases[k] for k in ["not_attempted", "history_or_time_failed", "success", "gate_ran", "gate_skipped", "full_error_available"]},
            "lifecycle_counts": dict(lifecycle),
            "job_count": len(jobs), "registration_count": len(registration_events),
            "accepted_registration_count": len(registrations), "rejected_registration_count": sum(not r["accepted_registration"] for r in registration_events),
            "paired_consumed_job_count": len(consumed), "accepted_decision_count": sum(d.get("accepted") is True for d in decisions),
            "full_error_sample_count": len(samples),
            "full_error_component_abs_max": [max((abs(x[i]) for x in samples), default=None) for i in range(6)],
            "source_only_observation": True, "new_fields_verified_in_bag": False,
            "canonical_behavior_equivalence_proven": False, "nominal_propagation_independently_recomputed": False,
            "close_flush_verified": None, "dynamic_source_qualified": False, "B4_complete": False,
            "execute_qualified": False, "plant_acceptance_proven": False, "force_measured": False,
            "execution_atomicity_proven": False, "gp_labels_ready": False,
            "scope": "Recorded source snapshots, job/decision identity, full wrapped error and finite source count closure only; no independent RK4/plant truth, durable flush, owned lifecycle or new typed-bag fields."}


def exact_json(a, b):
    # Numbers can differ in JSON integer/float spelling, but booleans are never
    # numeric evidence. No tolerance applies to immutable job echo.
    if type(a) is bool or type(b) is bool:
        return type(a) is type(b) and a == b
    if type(a) in (int, float) and type(b) in (int, float):
        return math.isfinite(a) and math.isfinite(b) and a == b
    if type(a) is dict and type(b) is dict:
        return set(a) == set(b) and all(exact_json(a[k], b[k]) for k in a)
    if type(a) is list and type(b) is list:
        return len(a) == len(b) and all(exact_json(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def byte_footprint(path):
    raw = Path(path).read_bytes()
    sizes = []
    for line in raw.splitlines():
        event = strict_loads(line.decode("utf-8-sig"))
        if event.get("type") == "decision":
            sizes.append(len(line))
    sizes.sort()
    def quantile(p):
        if not sizes:
            return None
        at = p * (len(sizes) - 1)
        left = int(at)
        right = min(left + 1, len(sizes) - 1)
        return sizes[left] + (sizes[right] - sizes[left]) * (at - left)
    return {"source_file_bytes": len(raw), "decision_row_byte_samples": len(sizes),
            "decision_row_bytes_total": sum(sizes), "decision_row_bytes_min": min(sizes) if sizes else None,
            "decision_row_bytes_p50": quantile(.5), "decision_row_bytes_p95": quantile(.95),
            "decision_row_bytes_max": max(sizes) if sizes else None,
            "serialization_scope": "Actual UTF-8 source decision line bytes excluding newline; source total includes newline and all rows.",
            "hard_byte_bound_certified": False}


def canonical_projection(event):
    return {k: v for k, v in event.items() if k != "d0_observation"}

def compare_canonical_decisions(new_events, expected_events):
    actual = [canonical_projection(x) for x in new_events if x.get("type") == "decision"]
    expected = [canonical_projection(x) for x in expected_events if x.get("type") == "decision"]
    return bool(actual) and exact_json(actual, expected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True, help="Create-only JSON report path")
    parser.add_argument("--canonical-expected-source", help="Optional same deterministic fixture expected canonical source")
    args = parser.parse_args(argv)
    source, contract, output = map(lambda x: Path(x).resolve(), [args.source, args.contract, args.output])
    need(output not in [source, contract] and not output.exists(), "report must be create-only and distinct from inputs")
    paths = [source, contract] + ([Path(args.canonical_expected_source).resolve()] if args.canonical_expected_source else [])
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    try:
        events = read_events(source)
        c = strict_loads(contract.read_text(encoding="utf-8-sig"))
        report = validate_events(events, c)
        report["source_footprint"] = byte_footprint(source)
        startups = [x for x in events if x.get("type") == "startup"]
        if len(startups) != 1 or startups[0]["contract_hash"] != hashes[str(contract)]:
            report["issues"].append("actual contract file SHA is not the startup contract identity")
            report["passed"] = False
        if args.canonical_expected_source:
            report["same_fixture_canonical_exact_match"] = compare_canonical_decisions(events, read_events(paths[2]))
            if not report["same_fixture_canonical_exact_match"]:
                report["issues"].append("same-fixture canonical decision projection changed")
                report["passed"] = False
    except (Invalid, ValueError) as exc:
        report = {"schema": "p1-d0-source-check-v1", "passed": False, "issues": [str(exc)], "source_counts_closed": False,
                  "execute_qualified": False, "dynamic_source_qualified": False, "new_fields_verified_in_bag": False}
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    need(hashes == after, "reviewed input changed during checking")
    report.update(input_sha256_before=hashes, input_sha256_after=after, inputs_unchanged=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": report["passed"], "issues": len(report["issues"]), "report": str(output)}))
    return 0 if report["passed"] else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Invalid, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
