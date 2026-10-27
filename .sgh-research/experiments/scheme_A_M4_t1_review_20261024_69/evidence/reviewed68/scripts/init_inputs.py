#!/usr/bin/env python3
"""Batch 68 (T1) input freeze and path check.

Freezes and SHA256-records every input this batch reads, takes the git
porcelain baseline of the production tree, and verifies the T1 code targets
from next_implementation_plan_v1 exist. Read-only with respect to every input;
writes only inside this batch directory. No ROS graph, no owned run.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import datetime

BATCH = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t1_component_wiring_20261024_68")
B67 = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67")
B47 = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47")
B66 = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66")
PROD = pathlib.Path("/home/trevor/USV")

KEY_FILES = [
    B67 / "postrun/next_implementation_plan_v1.json",
    B67 / "postrun/case_applicability_v1.json",
    B67 / "postrun/case_applicability_v1.md",
    B47 / "freeze/M4_fault_matrix_v1.json",
    B47 / "freeze/p1_execution_contract_v1.json",
    B66 / "evidence/owned_audit_v1.json",
]

# T1 code_targets from next_implementation_plan_v1 (existence + seam check).
PATH_CHECKS = [
    B67 / "implementation/current_author/observer/src/shadow/regulator_owned_execute.cpp",
    B67 / "implementation/current_author/observer/src/shadow/owned_execution_policy_native_v1.hpp",
    B67 / "implementation/current_author/observer/tests/test_reference_activation_alignment.cpp",
    B67 / "implementation/current_author/observer/tests/test_reference_pair_callbacks.cpp",
    B67 / "evidence/core_components_attempt02/verification_v1.json",
    B67 / "evidence/policy92_replay/current_entry_probe.cpp",
]


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    BATCH.mkdir(parents=True, exist_ok=True)
    evidence = BATCH / "evidence"
    evidence.mkdir(exist_ok=True)
    report = {
        "schema": "scheme-A-t1-batch68-init-inputs-v1",
        "created": datetime.datetime.now().astimezone().isoformat(),
        "new_ros_or_owned_runs": 0,
        "production_tree_writes": 0,
        "key_inputs": {},
        "current_author_bundle": {},
        "path_check": {},
        "seam_check": {},
        "git_porcelain_baseline": None,
    }
    for p in KEY_FILES:
        report["key_inputs"][str(p)] = {"exists": p.is_file()}
        if p.is_file():
            report["key_inputs"][str(p)]["sha256"] = sha256(p)

    author = B67 / "implementation/current_author"
    files = sorted(q for q in author.rglob("*") if q.is_file())
    bundle_lines = []
    per_file = {}
    for q in files:
        digest = sha256(q)
        per_file[str(q.relative_to(author))] = digest
        bundle_lines.append(f"{digest}  {q.relative_to(author)}")
    bundle_sha = hashlib.sha256("\n".join(bundle_lines).encode()).hexdigest()
    report["current_author_bundle"] = {
        "definition": "sha256 over sorted 'per-file-sha256  relative-path' lines of the 67th batch current_author tree",
        "file_count": len(files),
        "bundle_sha256": bundle_sha,
        "files": per_file,
    }

    for p in PATH_CHECKS:
        report["path_check"][str(p)] = {"exists": p.is_file()}
        if p.is_file():
            report["path_check"][str(p)]["sha256"] = sha256(p)
    seams = {}
    regulator = author / "observer/src/shadow/regulator_owned_execute.cpp"
    if regulator.is_file():
        text = regulator.read_text(encoding="utf-8", errors="replace")
        for token in ("P1_SHADOW_ENTRY_TEST", "ShadowTestTag", "P1_C33_MATRIX_TEST",
                      "friend class C33MatrixAccess", "candidate_registration",
                      "scheduler_skipped_ticks", "P1_OWNED_SOURCE_BUNDLE_SHA256"):
            seams[token] = token in text
    report["seam_check"] = {"file": str(regulator), "tokens_present": seams}

    porcelain = subprocess.run(["git", "-C", str(PROD), "status", "--porcelain"],
                               capture_output=True, text=True, check=True)
    report["git_porcelain_baseline"] = {
        "command": "git -C /home/trevor/USV status --porcelain",
        "line_count": len([l for l in porcelain.stdout.splitlines() if l.strip()]),
        "sha256": hashlib.sha256(porcelain.stdout.encode()).hexdigest(),
        "stdout": porcelain.stdout,
    }
    out = evidence / "init_inputs_v1.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({
        "written": str(out),
        "key_inputs_ok": all(v.get("exists") for v in report["key_inputs"].values()),
        "path_check_ok": all(v.get("exists") for v in report["path_check"].values()),
        "seams_all_present": all(seams.values()),
        "current_author_files": len(files),
        "bundle_sha256": bundle_sha,
        "git_porcelain_lines": report["git_porcelain_baseline"]["line_count"],
    }, indent=2))


if __name__ == "__main__":
    main()
