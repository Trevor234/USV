#!/usr/bin/env python3
"""Batch 68 (T1) orchestrator: build, run, mutation positive controls, evidence.

* Builds tests/test_current_candidate_reference_clock.cpp against the frozen
  67th-batch current_author source (read-only) with the existing seams.
* Failed build/test attempts are kept in build/attemptNN (never overwritten).
* Three targeted mutations of a COPY of the regulator source must be caught by
  the assertions; mutation copies live under evidence/t1_mutations/.
* Emits evidence/t1_wiring/verification_v1.json mapping every gap atom to the
  tests that actually drove it. No ROS graph, no owned run (the gtest process
  initializes rclcpp for the node base only; no DDS participants beyond the
  in-process test publishers created by the existing seam constructors).
"""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

BATCH = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t1_component_wiring_20261024_68")
B67 = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67")
B47 = pathlib.Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47")
AUTHOR = B67 / "implementation/current_author"
REGULATOR = AUTHOR / "observer/src/shadow/regulator_owned_execute.cpp"
FROZEN = B47 / "freeze/p1_execution_contract_v1.json"

ATOM_MAP = {
    "candidate_identity_shape.01": ["T1Wiring.CandidateValidRegistersAndActivates", "T1Wiring.CandidateFailedSolverNotInvoked"],
    "candidate_identity_shape.02": ["T1Wiring.CandidateInvalidShapeAndUnavailable"],
    "candidate_identity_shape.03": ["T1Wiring.CandidateNonFinitePrediction"],
    "candidate_identity_shape.04": ["T1Wiring.CandidateDuplicateRejected"],
    "candidate_identity_shape.05": ["T1Wiring.CandidateOldReorderedJob"],
    "candidate_identity_shape.06": ["T1Wiring.CandidateForeignWorkerAndIdentity"],
    "candidate_identity_shape.07": ["T1Wiring.CandidateForeignWorkerAndIdentity"],
    "candidate_identity_shape.08": ["T1Wiring.CandidateStaleVersionRejected"],
    "task_reference.01": ["T1Wiring.ReferenceClearBeforeFreeze"],
    "task_reference.02": ["T1Wiring.ReferenceSinglePointBeforeFreeze"],
    "task_reference.03": ["T1Wiring.ReferenceClearDuringReadyInvalidates"],
    "task_reference.04": ["T1Wiring.ReferenceReplaceDuringSolve"],
    "task_reference.05": ["T1Wiring.ReferenceSameContentRepublishKeepsTask"],
    "task_reference.06": ["T1Wiring.ReferenceProfilePairMismatch"],
    "task_reference.07": ["T1Wiring.ReferenceOrdinaryNewOdomKeepsEligible"],
    "state_clock.04": ["T1Wiring.ClockPauseInvalidatesSchedule"],
    "state_clock.05": ["T1Wiring.ClockResumeReschedules"],
    "state_clock.06": ["T1Wiring.ClockBackwardResetsEpoch"],
    "state_clock.07": ["T1Wiring.ClockLargeJumpResetsEpoch"],
    "state_clock.08": ["T1Wiring.ClockRtfLowBandInvalid"],
    "state_clock.09": ["T1Wiring.ClockRtfHighBandInvalid"],
    "publication_exit.02": ["T1Wiring.CommittedSubmitClearInvalidates"],
    "publication_exit.03": ["T1Wiring.ShutdownDuringReadyActivation"],
}
COMPANIONS = ["T1Wiring.DelayedTick250msSkipsOnce", "T1Wiring.DelayedTick400msSkipsTwice"]

MUTATIONS = [
    {
        "name": "m1_consumed_candidate_revivable",
        "intent": "remove the candidate reset in the skipped-tick invalidation so a held candidate survives a skipped tick",
        "find": "admission_.invalidate();candidate_.reset();normal_complete_=false;",
        "replace": "admission_.invalidate();normal_complete_=false;",
        "expect_caught_by": ["T1Wiring.DelayedTick250msSkipsOnce"],
    },
    {
        "name": "m2_clock_epoch_no_invalidate",
        "intent": "keep the epoch counter but drop the invalidation on clock epoch change",
        "find": "anchor_.known={false,false};invalidate_locked();}",
        "replace": "anchor_.known={false,false};}",
        "expect_caught_by": ["T1Wiring.ClockBackwardResetsEpoch", "T1Wiring.ClockLargeJumpResetsEpoch"],
    },
    {
        "name": "m3_path_change_no_invalidate",
        "intent": "keep task generation bump but drop the invalidation on path change",
        "find": "version_.task++;path_fingerprint_=fingerprint;invalidate_locked();}",
        "replace": "version_.task++;path_fingerprint_=fingerprint;}",
        "expect_caught_by": ["T1Wiring.ReferenceClearDuringReadyInvalidates", "T1Wiring.ReferenceReplaceDuringSolve"],
    },
]

ENV_SETUP = "source /opt/ros/jazzy/setup.bash && source /home/trevor/USV/usv_mpc_ws/install/setup.bash"


def bundle_sha256() -> str:
    manifest = json.load(open(BATCH / "evidence/init_inputs_v1.json"))
    return manifest["current_author_bundle"]["bundle_sha256"]


def next_attempt(prefix: str) -> pathlib.Path:
    n = 1
    while (BATCH / "build" / f"{prefix}{n:02d}").exists():
        n += 1
    p = BATCH / "build" / f"{prefix}{n:02d}"
    p.mkdir(parents=True)
    return p


def run(cmd: list, cwd=None, log=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if log is not None:
        pathlib.Path(log).write_text(
            f"$ {' '.join(cmd)}\nrc={proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
    return proc


def configure_and_build(build_dir: pathlib.Path, mutated_source: str = "") -> tuple:
    log = build_dir / "build.log"
    cmd = ["bash", "-c",
           f'{ENV_SETUP} && cmake {BATCH}/implementation -B {build_dir} '
           f'-DT1_AUTHOR_DIR={AUTHOR} -DP1_FROZEN_CONTRACT={FROZEN} '
           f'-DP1_OWNED_SOURCE_BUNDLE_SHA256={bundle_sha256()} '
           + (f'-DT1_MUTATED_SOURCE={mutated_source} ' if mutated_source else "")
           + f'&& cmake --build {build_dir} -j2']
    proc = run(cmd, log=log)
    return proc, log


def next_dir(parent: pathlib.Path, prefix: str) -> pathlib.Path:
    parent.mkdir(parents=True, exist_ok=True)
    n = 1
    while (parent / f"{prefix}{n:02d}").exists():
        n += 1
    p = parent / f"{prefix}{n:02d}"
    p.mkdir(parents=True)
    return p


def run_gtest(binary: pathlib.Path, output_dir: pathlib.Path) -> tuple:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "gtest.json"
    wrapped = (f'{ENV_SETUP} && exec {binary} "--gtest_output=json:{json_path}"')
    env = dict(os.environ)
    env["P1_T1_TEST_OUTPUT"] = str(output_dir / "cases")
    proc = subprocess.run(["bash", "-c", wrapped], capture_output=True, text=True, env=env, timeout=900)
    (output_dir / "run.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
    results = {}
    if json_path.exists():
        doc = json.load(open(json_path))
        for suite in doc.get("testsuites", []):
            for case in suite.get("testsuite", []):
                results[f'{suite["name"]}.{case["name"]}'] = {
                    "status": case.get("status"),
                    "failures": [f.get("failure") for f in case.get("failures", [])],
                }
    return proc.returncode, results, output_dir


def main() -> int:
    print("[t1] attempt 1: configure + build against frozen current_author")
    build = next_attempt("attempt")
    proc, log = configure_and_build(build)
    if proc.returncode != 0:
        print(f"[t1] BUILD FAILED (kept at {build}); see {log}")
        return 3
    binary = build / "test_current_candidate_reference_clock"
    rc, results, outdir = run_gtest(binary, next_dir(BATCH / "evidence/t1_wiring", "run"))
    failed = {k: v for k, v in results.items() if v["failures"] or v["status"] not in ("RUN",)}
    expected = [t for ts in ATOM_MAP.values() for t in ts] + COMPANIONS
    missing = [t for t in expected if t not in results]
    if rc != 0 or failed or missing:
        print(f"[t1] TEST FAILURES rc={rc} kept at {outdir}; failures={list(failed)}; missing={missing}")
        return 4
    print(f"[t1] nominal run: {len(results)} tests passed")

    mutations = []
    for m in MUTATIONS:
        mdir = BATCH / "evidence/t1_mutations" / m["name"]
        mdir.mkdir(parents=True, exist_ok=True)
        mutated = mdir / "regulator_owned_execute.cpp"
        text = REGULATOR.read_text(encoding="utf-8")
        occurrences = text.count(m["find"])
        mutated.write_text(text.replace(m["find"], m["replace"]), encoding="utf-8")
        record = {"name": m["name"], "intent": m["intent"], "find": m["find"],
                  "replace": m["replace"], "occurrences_in_original": occurrences,
                  "mutated_sha256": hashlib.sha256(mutated.read_bytes()).hexdigest(),
                  "original_sha256": hashlib.sha256(REGULATOR.read_bytes()).hexdigest()}
        if occurrences != 1:
            record["applied"] = False
            record["error"] = f"expected exactly one occurrence, found {occurrences}; mutation NOT applied"
            mutations.append(record)
            continue
        mbuild = BATCH / "build" / f"mut_{m['name']}"
        if mbuild.exists():
            shutil.rmtree(mbuild)
        mbuild.mkdir(parents=True)
        proc, log = configure_and_build(mbuild, str(mutated))
        record["build_log"] = str(log)
        if proc.returncode != 0:
            record["applied"] = False
            record["error"] = "mutation build failed"
            mutations.append(record)
            continue
        mrc, mresults, moutdir = run_gtest(mbuild / "test_current_candidate_reference_clock", next_dir(mdir, "run"))
        caught = sorted(k for k, v in mresults.items() if v["failures"] or v["status"] not in ("RUN",))
        record.update({
            "applied": True,
            "mutation_test_exit": mrc,
            "caught_by": caught,
            "expected_subset": m["expect_caught_by"],
            "expected_all_caught": all(any(e.startswith(c) for c in caught) for e in m["expect_caught_by"]),
            "run_dir": str(moutdir),
        })
        mutations.append(record)
        print(f"[t1] mutation {m['name']}: exit={mrc} caught_by={caught}")

    verification = {
        "schema": "scheme-A-t1-batch68-verification-v1",
        "created": datetime.datetime.now().astimezone().isoformat(),
        "source_under_test": {
            "regulator": str(REGULATOR),
            "regulator_sha256": hashlib.sha256(REGULATOR.read_bytes()).hexdigest(),
            "current_author_bundle_sha256": bundle_sha256(),
            "seam_mode": "P1_SHADOW_ENTRY_TEST + P1_C33_MATRIX_TEST via P1_REGULATOR_SOURCE (unmodified source include)",
        },
        "claims": {
            "component_level_synthetic_inputs": True,
            "owned_four_role_qualification": False,
            "control_DataWriter_created": False,
            "new_ros_graph_or_owned_runs": 0,
            "cross_process_delivery_claimed": False,
        },
        "nominal_run": {
            "build_dir": str(build),
            "run_dir": str(outdir),
            "test_count": len(results),
            "all_passed": True,
            "results": results,
        },
        "atom_coverage": {},
        "companion_tests": {name: results[name]["status"] for name in COMPANIONS if name in results},
        "mutations": mutations,
        "t2_handoff_needed": sorted({
            "state_clock.04": "cross-process pause/resume delivery via Fixture clock writer",
            "state_clock.05": "cross-process resume delivery via Fixture clock writer",
            "task_reference.03": "cross-process clear during in-flight solve (Fixture path writer action)",
            "task_reference.04": "cross-process replacement during in-flight solve (Fixture path writer action)",
            "publication_exit.03": "driver-driven shutdown interleave against a real owned run",
        }.items()),
    }
    for atom, tests in ATOM_MAP.items():
        verification["atom_coverage"][atom] = {
            "tests": tests,
            "statuses": {t: results.get(t, {}).get("status", "MISSING") for t in tests},
            "all_passed": all(results.get(t, {}).get("status") == "RUN" for t in tests),
            "driven_real_code": "regulator_owned_execute.cpp candidate()/path()/profile()/clock()/tick_loop()/activate_candidate() via friend seam",
        }
    missing = [a for a, c in verification["atom_coverage"].items() if not c["all_passed"]]
    verification["atoms_missing"] = missing
    out = BATCH / "evidence/t1_wiring/verification_v1.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(verification, f, indent=2, sort_keys=True)
    print(json.dumps({"written": str(out), "atoms_total": len(ATOM_MAP), "atoms_missing": missing,
                      "mutations_all_caught": all(m.get("expected_all_caught", False) and m.get("applied") for m in mutations)}, indent=2))
    return 0 if not missing else 5


if __name__ == "__main__":
    sys.exit(main())
