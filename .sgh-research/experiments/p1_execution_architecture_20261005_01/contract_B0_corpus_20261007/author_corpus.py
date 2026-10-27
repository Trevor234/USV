"""Create-only, manually expected raw JSON corpus, then independently run Python.

Expected outcomes below come from the declared B0 semantics, not the validator.
Structural frozen objects are fixtures with a fabricated evidence marker only.
"""
from pathlib import Path
import copy
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
B = HERE.parent
SPEC_SHA = "33fb4a5eef93aa6abce5a61e7549dd7217f90c9572e5097791731fbb89661ffd"
PRE_SHA = "0258c05fb9988187096fa57599a3168fdc411eb4352bb36e6bc440f80bc6bcf9"
MAX_BYTES = 65536
sha = lambda data: hashlib.sha256(data).hexdigest()


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_json(path, value):
    with path.open("xb") as stream:
        stream.write(raw(value))


def build():
    spec_bytes = (B / "p1_contract_spec_v1.json").read_bytes()
    pre_bytes = (B / "p1_execution_pre_freeze_v1.json").read_bytes()
    assert sha(spec_bytes) == SPEC_SHA and sha(pre_bytes) == PRE_SHA
    spec = json.loads(spec_bytes)
    diag = spec["legacy_baseline"]
    pre = json.loads(pre_bytes)
    frozen = copy.deepcopy(pre)
    frozen.update(qualification="execution_frozen", execute_qualified=True,
                  parameters_are_diagnostic_only=False, pending_final_calibration=[],
                  freeze_evidence_sha256="a" * 64)
    assert len(diag) == 74 and len(pre) == len(frozen) == 77
    cases = []
    ids = set()

    def add(case_id, value, mode="no_output", schema=True, mode_ok=None,
            runtime_ok=None, reason="manually declared supported B0 semantics", encoded=False):
        assert case_id not in ids
        ids.add(case_id)
        mode_ok = schema if mode_ok is None else mode_ok
        runtime_ok = mode_ok if runtime_ok is None else runtime_ok
        cases.append({"id": case_id, "raw": value if encoded else raw(value),
                      "mode": mode, "expected_schema_valid": schema,
                      "expected_mode_valid": mode_ok,
                      "expected_runtime_valid": runtime_ok, "expectation_basis": reason})

    def bad(case_id, value, reason, encoded=False):
        add(case_id, value, schema=False, reason=reason, encoded=encoded)

    add("valid_diag5_no_output", diag)
    add("valid_diag5_shadow", diag, mode="shadow")
    add("valid_pre_freeze_no_output", pre)
    add("structural_frozen_no_output_fixture", frozen,
        reason="structural fixture; fabricated evidence marker is not an approved frozen asset")
    add("structural_frozen_pure_execute_runtime_closed_fixture", frozen, mode="execute",
        runtime_ok=False,
        reason="pure frozen matrix accepts execute; physical B5/M4 release remains false")
    for name, profile, mode in (("diag", diag, "execute"), ("pre", pre, "execute"),
                                 ("pre", pre, "shadow"), ("frozen", frozen, "shadow")):
        add(f"invalid_mode_{name}_{mode}", profile, mode=mode, mode_ok=False,
            runtime_ok=False, reason="schema valid, role/mode combination unsupported")
    for name, profile in (("diag", diag), ("pre", pre), ("frozen", frozen)):
        for label, mode in (("empty", ""), ("foreign", "foreign"), ("worker_as_mode", "worker")):
            add(f"invalid_mode_{name}_{label}", profile, mode=mode,
                mode_ok=False, runtime_ok=False, reason="mode is not an accepted regulator mode")

    # Every required field of complete current diag5 and formal v3 is necessary.
    for name, profile in (("diag", diag), ("pre", pre)):
        for key in profile:
            c = copy.deepcopy(profile); c.pop(key)
            bad(f"missing_{name}_{key}", c, "required field absent; defaults are forbidden")
    for name, profile, key in (("diag", diag, "execution_contract_revision"),
                               ("pre", pre, "diagnostic_contract_revision"),
                               ("frozen", frozen, "diagnostic_contract_revision")):
        c = copy.deepcopy(profile); c[key] = 1
        bad(f"mixed_revision_{name}", c, "formal and diagnostic revision sets are disjoint")
    for name, profile in (("diag", diag), ("pre", pre)):
        for key in ("unknown_parameter", "decision_schema_version", "allow_execute"):
            c = copy.deepcopy(profile); c[key] = "unexpected"
            bad(f"unknown_{name}_{key}", c, "additional top-level fields are unsupported")

    # Semantically integer fields reject floats even when numerically equal.
    for key in spec["integer_keys"]:
        profile = diag if key == "diagnostic_contract_revision" else pre
        for label, value in (("bool", True), ("float", float(profile[key])),
                             ("string", str(profile[key])), ("null", None)):
            c = copy.deepcopy(profile); c[key] = value
            bad(f"integer_{key}_{label}", c, "JSON true integer required before numeric comparison")
    for key in ("execution_contract_revision", "resource_contract_revision"):
        for label, value in (("bool", True), ("float", 1.), ("zero", 0), ("next", 2)):
            c = copy.deepcopy(pre); c[key] = value
            bad(f"formal_revision_{key}_{label}", c, "only true integer revision1 supported")
    for key in ("T_ns", "deadline_ns", "hold_ns", "worker_grace_ns", "publish_budget_ns"):
        for label, value in (("zero", 0), ("negative", -1), ("int64_plus", 1 << 63),
                             ("int64_minus", -(1 << 63)-1)):
            c = copy.deepcopy(pre); c[key] = value
            bad(f"time_{key}_{label}", c, "fixed positive time profile and signed int64 domain")
    data = raw(pre)
    bad("raw_time_equal_scientific_float", data.replace(b'"T_ns": 200000000', b'"T_ns": 2e8', 1),
        "2e8 is a JSON float, not a true integer", encoded=True)

    # Resource bounds remain intervals, not exact non-resource baseline values.
    intervals = {"max_path_points": (1, 2048), "max_profile_rows": (1, 2048),
                 "history_capacity": (1, 256), "log_capacity": (1, 512),
                 "max_job_bytes": (6460, 8192), "max_candidate_bytes": (8204, 16384)}
    for name, profile in (("diag", diag), ("pre", pre)):
        for key, (low, high) in intervals.items():
            for edge, value in (("lower", low), ("upper", high)):
                c = copy.deepcopy(profile); c[key] = value
                add(f"valid_resource_{name}_{key}_{edge}", c,
                    reason="declared inclusive typed resource implementation interval; not history qualification")
    for key, (low, high) in intervals.items():
        for edge, value in (("under", low-1), ("over", high+1)):
            c = copy.deepcopy(pre); c[key] = value
            bad(f"resource_{key}_{edge}", c, "outside inclusive supported resource interval")
    for key, fixed in (("dds_depth", 1), ("max_profile_dims", 4),
                       ("max_profile_label_bytes", 64), ("max_path_frame_bytes", 128),
                       ("job_cdr_max_bytes", 6460), ("candidate_cdr_max_bytes", 8204)):
        for label, value in (("minus", fixed-1), ("plus", fixed+1)):
            c = copy.deepcopy(pre); c[key] = value
            bad(f"resource_fixed_{key}_{label}", c, "fixed typed-domain layout declaration changed")
    for key in ("resource_policy", "resource_budget_scope"):
        c = copy.deepcopy(pre); c[key] = "unknown"
        bad(f"resource_{key}_unknown", c, "resource policy and CDR scope are exact supported strings")

    for key in ("Q", "R", "Rd", "activation_tolerance"):
        for label, change in (("short", lambda a: a[:-1]), ("long", lambda a: a+[0]),
                               ("bool", lambda a: [True]+a[1:]), ("null", lambda a: [None]+a[1:]),
                               ("nested", lambda a: [[a[0]]]+a[1:]),
                               ("drift", lambda a: [a[0]+.01]+a[1:])):
            c = copy.deepcopy(pre); c[key] = change(c[key])
            bad(f"array_{key}_{label}", c, "exact array length, finite numeric elements and candidate tuple required")
    c = copy.deepcopy(pre); c["Q"] = [float(v) for v in c["Q"]]
    c["map_scale"] = 1.; c["hydro"]["Xu_dot"] = -2.
    add("valid_real_numeric_equivalent_representation", c,
        reason="real-valued model/weight fields accept equal int or float, never bool")
    for key in diag["hydro"]:
        for label, change in (("missing", None), ("bool", True),
                               ("drift", diag["hydro"][key]+.01)):
            c = copy.deepcopy(pre)
            if label == "missing": c["hydro"].pop(key)
            else: c["hydro"][key] = change
            bad(f"hydro_{key}_{label}", c, "all19 hydro fields and candidate model tuple are fixed")
    for object_key in ("hydro", "input_topics", "output_topics"):
        c = copy.deepcopy(pre); c[object_key]["unknown"] = 0
        bad(f"nested_unknown_{object_key}", c, "nested object field set is exact")
    for key, value in (("schema", "p1-execution-contract-v4"), ("supported_parameter_profile", "foreign"),
                        ("nominal_hash", "0"*64), ("dt", .2+1e-12), ("N", 21),
                        ("T_ns", 210000000), ("deadline_ns", 200000000),
                        ("command_min_n", -30), ("command_max_n", 30), ("map_scale", .5),
                        ("publisher_max_n", 24), ("rho_n_s", 0), ("backend_rate_n_s", 81),
                        ("rtf_low", 1.1), ("rtf_high", .9), ("publish_gap_ns", 1),
                        ("expected_pose_frame", "\U0001f600"*64),
                        ("worker_failure_policy", "retry_same_run"),
                        ("worker_capability_source_freshness_available", True),
                        ("propagation_semantics", "measured plant force")):
        c = copy.deepcopy(pre); c[key] = value
        bad(f"profile_drift_{key}", c, "unsupported fixed non-resource candidate parameter or semantic")
    c = copy.deepcopy(pre); c["output_topics"]["right"] = c["output_topics"]["left"]
    bad("same_left_right_output_topic", c, "fixed distinct physical topic identities required")

    for name, profile in (("diag", diag), ("pre", pre), ("frozen", frozen)):
        for key in ("execute_qualified", "parameters_are_diagnostic_only", "fault_injection_enabled"):
            for label, value in (("integer", 1), ("string", "true"), ("inverted", not profile[key])):
                c = copy.deepcopy(profile); c[key] = value
                bad(f"flag_{name}_{key}_{label}", c, "true bool and exact qualification combination required")
    for key, value in (("pending_final_calibration", []), ("freeze_evidence_sha256", "a"*64),
                        ("qualification", "execution_unknown")):
        c = copy.deepcopy(pre); c[key] = value
        bad(f"pre_marker_{key}", c, "pre_freeze preserves pending list and empty evidence marker")
    for label, value in (("empty", ""), ("uppercase", "A"*64), ("nonhex", "g"*64),
                         ("short", "a"*63), ("integer", 1), ("null", None)):
        c = copy.deepcopy(frozen); c["freeze_evidence_sha256"] = value
        bad(f"frozen_evidence_{label}", c, "structural frozen evidence marker needs64 lowercasehex; not approval")
    c = copy.deepcopy(frozen); c["pending_final_calibration"] = ["rho_n_s"]
    bad("frozen_pending_not_empty", c, "structural frozen qualification requires no pending fields")

    for label, token in (("NaN", b"NaN"), ("Infinity", b"Infinity"),
                         ("minusInfinity", b"-Infinity"), ("overflow", b"1e309")):
        bad(f"raw_nonfinite_{label}", data.replace(b'"dt": 0.2', b'"dt": '+token, 1),
            "nonstandard constant or nonfinite parsed number is forbidden", encoded=True)
    for label, old, replacement in (
        ("schema_same", b'"schema": "p1-execution-contract-v3"',
         b'"schema": "p1-execution-contract-v3", "schema": "p1-execution-contract-v3"'),
        ("flag_same", b'"execute_qualified": false',
         b'"execute_qualified": false, "execute_qualified": false'),
        ("hydro_same", b'"mass": 14.2', b'"mass": 14.2, "mass": 14.2'),
        ("topic_same", b'"left": "/wamv/thrusters/left/thrust"',
         b'"left": "/wamv/thrusters/left/thrust", "left": "/wamv/thrusters/left/thrust"')):
        assert data.count(old) == 1
        bad(f"raw_duplicate_{label}", data.replace(old, replacement, 1),
            "duplicate keys are rejected even when both values equal", encoded=True)
    for label, encoded in (("array", b"[]"), ("null", b"null"), ("boolean", b"true"),
                           ("number", b"20"), ("string", b'"contract"'),
                           ("unclosed", b'{"schema":'), ("utf8_invalid", b'\xff')):
        bad(f"raw_root_{label}", encoded, "root must be complete contract object encoded as UTF-8", encoded=True)
    add("raw_exact_64KiB_valid", data+b" "*(MAX_BYTES-len(data)), encoded=True,
        reason="64KiB is inclusive maximum; trailing JSON whitespace is legal")
    bad("raw_over_64KiB_rejected", data+b" "*(MAX_BYTES+1-len(data)),
        "raw contract exceeds64KiB regardless of semantic profile", encoded=True)
    return cases


def main():
    if (HERE / "manifest.json").exists() or (HERE / "cases").exists():
        raise RuntimeError("create-only corpus already exists")
    generated = build()
    directory = HERE / "cases"; directory.mkdir()
    rows = []
    for case in generated:
        data = case.pop("raw")
        relative = "cases/" + case["id"] + ".json"
        with (HERE/relative).open("xb") as stream: stream.write(data)
        rows.append({**case, "path": relative, "sha256": sha(data), "bytes": len(data)})
    manifest = {"schema": "p1-b0-raw-contract-corpus-v1", "spec_sha256": SPEC_SHA,
                "pre_freeze_profile_sha256": PRE_SHA,
                "expected_outcomes_origin": "manual_declared_B0_semantics_before_validator_execution",
                "structural_frozen_is_qualified_asset": False, "case_count": len(rows), "cases": rows}
    write_json(HERE/"manifest.json", manifest)

    # Only after expectations and raw files are fixed, run the independent rules.
    sys.path.insert(0, str(B/"runtime"))
    import p1_full_contract as validator
    checked = []
    for case in rows:
        data = (HERE/case["path"]).read_bytes()
        assert sha(data) == case["sha256"]
        actual = {}; errors = {}; parsed = None
        try:
            parsed = validator.parse_contract_bytes(data)
            validator.validate_fields(parsed)
            actual["schema_valid"] = True
        except validator.ContractError as exc:
            actual["schema_valid"] = False; errors["schema"] = str(exc)
        for label, call in (("mode_valid", validator.validate_mode),
                            ("runtime_valid", validator.require_runtime_mode)):
            try: call(parsed, case["mode"]); actual[label] = True
            except validator.ContractError as exc:
                actual[label] = False; errors[label] = str(exc)
        matched = all(actual[name] == case["expected_"+name]
                      for name in ("schema_valid", "mode_valid", "runtime_valid"))
        checked.append({"id": case["id"], "sha256": case["sha256"], **actual,
                        "matches_manual_expectation": matched, "errors": errors})
    mismatches = [row for row in checked if not row["matches_manual_expectation"]]
    result = {"schema": "p1-b0-python-raw-corpus-result-v1", "manifest_sha256": sha((HERE/"manifest.json").read_bytes()),
              "spec_sha256": SPEC_SHA, "case_count": len(checked), "passed": not mismatches,
              "mismatch_count": len(mismatches), "mismatches": mismatches, "results": checked,
              "gates_evaluated_independently": True,
              "new_ros_run": False, "remote_execution": False,
              "structural_frozen_is_qualified_asset": False}
    write_json(HERE/"python_result.json", result)
    print(json.dumps({k: result[k] for k in ("case_count", "passed", "mismatch_count", "manifest_sha256")}))
    if mismatches: raise SystemExit(1)


if __name__ == "__main__": main()
