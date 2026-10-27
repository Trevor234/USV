#!/usr/bin/env python3
"""Batch 68 (T1) finalization: T2 handoff, final verification, MPC mirror.

* Re-verifies every frozen input SHA and the git porcelain baseline.
* Mirrors the whole batch to /home/trevor/MPC/<batch> (create-only, never
  overwrites a prior delivery) and verifies the mirror by per-file SHA
  read-back. No ROS graph, no owned run.
"""
import datetime
import hashlib
import json
import pathlib
import shutil
import subprocess

BATCH = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t1_component_wiring_20261024_68")
MIRROR = pathlib.Path("/home/trevor/MPC/scheme_A_M4_t1_component_wiring_20261024_68")
PROD = "/home/trevor/USV"

T2_HANDOFF = {
    "schema": "scheme-A-t1-batch68-t2-handoff-v1",
    "created": None,  # filled at runtime
    "principle": "只执行已经由T1证明需要owned的最小case清单；每次独立Source/Stored/API/退出对账，不预定九组各一次长run",
    "component_layer_now_covers": "all 23 wiring atoms (see evidence/t1_wiring/verification_v1.json)",
    "minimal_owned_cases": [
        {
            "id": "T2-A",
            "atoms": ["state_clock.04", "state_clock.05"],
            "scenario": "clock pause >400ms then resume via the REAL Fixture clock writer cross-process",
            "fixture_action_table_entries": [
                "clock:hold(silent) duration_ms=600 at step N",
                "clock:resume(advance +100ms) at step M",
            ],
            "why_owned": "pause detection lives in the running tick against a real /clock stream; component shell proved the wiring, not the delivery",
            "shared_with": "any W-case run that already drives the clock writer (no dedicated run if one exists)",
        },
        {
            "id": "T2-B",
            "atoms": ["task_reference.03", "task_reference.04"],
            "scenario": "path clear / replacement delivered by the REAL Fixture path writer while a solve is in flight",
            "fixture_action_table_entries": [
                "path:clear at trigger=candidate_received(job_id=K)",
                "path:replace(points=5, fingerprint!=initial) at trigger=candidate_received(job_id=K)",
            ],
            "why_owned": "writer->callback delivery interleaving with an in-flight job is cross-process by definition",
        },
        {
            "id": "T2-C",
            "atoms": ["publication_exit.03"],
            "scenario": "driver-driven shutdown request interleaved between ready and activation of a real owned run",
            "fixture_action_table_entries": [
                "driver:shutdown_request at trigger=ready_registered(job_id=K)",
            ],
            "why_owned": "shutdown authority and process exit facts are Driver-owned; the component layer only proved the in-process rejection reason",
        },
    ],
    "explicitly_not_promoted": [
        "candidate_identity_shape.01-.08 (fully covered component-side; the owned layer already carries W1/W3/W4 evidence)",
        "task_reference.01/.02/.05/.06/.07",
        "state_clock.06-.09 (reset/jump/RTF are callback-side and covered)",
        "publication_exit.02",
        "delayed-tick shells 250/400ms (time_boundaries companion, covered)",
    ],
    "constraints": [
        "create-only fixed action table in a derived synthetic_source_m4.cpp; normal .05 default behaviour unchanged",
        "actions executed by the existing fixture path/profile/odom/imu/clock writers only; no foreign publisher",
        "candidate forgeries stay out of the Fixture (diagnostic worker / source-linked callback component only)",
        "after code change: re-bundle -> Driver SHA -> real ELF -> registry/registration -> shared pre-check",
        "per-case limited runs, automatic_retries=0",
    ],
}


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    now = datetime.datetime.now().astimezone().isoformat()
    init = json.load(open(BATCH / "evidence/init_inputs_v1.json"))
    verification = json.load(open(BATCH / "evidence/t1_wiring/verification_v1.json"))

    # 1. T2 handoff document
    T2_HANDOFF["created"] = now
    (BATCH / "postrun/t1_handoff_to_t2_v1.json").write_text(
        json.dumps(T2_HANDOFF, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Final verification: frozen inputs unchanged
    inputs_ok = True
    input_report = {}
    for path, meta in init["key_inputs"].items():
        p = pathlib.Path(path)
        ok = p.is_file() and sha256(p) == meta.get("sha256")
        input_report[path] = ok
        inputs_ok = inputs_ok and ok
    author = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/implementation/current_author")
    files = sorted(q for q in author.rglob("*") if q.is_file())
    lines = []
    for q in files:
        lines.append(f"{sha256(q)}  {q.relative_to(author)}")
    bundle_now = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    bundle_ok = bundle_now == init["current_author_bundle"]["bundle_sha256"] and len(files) == init["current_author_bundle"]["file_count"]

    porcelain = subprocess.run(["git", "-C", PROD, "status", "--porcelain"],
                               capture_output=True, text=True, check=True)
    porcelain_ok = hashlib.sha256(porcelain.stdout.encode()).hexdigest() == init["git_porcelain_baseline"]["sha256"]

    nominal_ok = verification["nominal_run"]["all_passed"] and not verification["atoms_missing"]
    mutations_ok = all(m.get("applied") and m.get("expected_all_caught") for m in verification["mutations"])

    report = {
        "schema": "scheme-A-t1-batch68-final-verification-v1",
        "created": now,
        "claims": {
            "t1_nominal_25_tests_passed": nominal_ok,
            "all_23_atoms_covered": not verification["atoms_missing"],
            "mutations_applied_and_caught": mutations_ok,
            "frozen_inputs_unchanged": inputs_ok and bundle_ok,
            "production_git_porcelain_unchanged": porcelain_ok,
            "current_owned_run_count": 0,
            "new_ros_graph": 0,
            "production_tree_writes": 0,
        },
        "inputs_detail": input_report,
        "current_author_bundle_matches": bundle_ok,
        "failed_attempts_kept": sorted(p.name for p in (BATCH / "build").iterdir() if p.is_dir()),
        "scope_note": "component-level synthetic inputs only; no owned four-role qualification, no cross-process delivery claimed",
    }
    (BATCH / "evidence/final_verification_v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    # 3. Mirror (create-only, build artifacts excluded per delivery convention)
    # with per-file SHA read-back
    if MIRROR.exists():
        print(f"[finalize] mirror already exists, NOT overwriting: {MIRROR}")
        mirror_ok = False
    else:
        shutil.copytree(BATCH, MIRROR, ignore=shutil.ignore_patterns("build"))
        mirror_ok = True
        mismatches = []
        for q in sorted(MIRROR.rglob("*")):
            if q.is_file():
                rel = q.relative_to(MIRROR)
                src = BATCH / rel
                if not src.is_file() or sha256(src) != sha256(q):
                    mismatches.append(str(rel))
        report["mirror"] = {
            "path": str(MIRROR),
            "excludes": ["build"],
            "files": sum(1 for q in MIRROR.rglob("*") if q.is_file()),
            "read_back_mismatches": mismatches,
        }
        (BATCH / "evidence/final_verification_v1.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        (MIRROR / "evidence/final_verification_v1.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        mirror_ok = not mismatches

    ok = nominal_ok and mutations_ok and inputs_ok and bundle_ok and porcelain_ok and mirror_ok
    print(json.dumps({
        "nominal_ok": nominal_ok, "mutations_ok": mutations_ok, "inputs_ok": inputs_ok,
        "bundle_ok": bundle_ok, "porcelain_ok": porcelain_ok, "mirror_ok": mirror_ok,
        "all_green": ok,
    }, indent=2))


if __name__ == "__main__":
    main()
