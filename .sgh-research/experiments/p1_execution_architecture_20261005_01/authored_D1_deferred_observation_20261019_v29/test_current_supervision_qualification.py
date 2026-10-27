#!/usr/bin/python3
"""Bounded non-ROS regressions against the preregistered current qualifier."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parent
DOCS = Path("/home/trevor/MPC/scheme_A_prepare_close_20261010_02")
QUALIFIER = DOCS / "preregister/qualifier_revision_v3.json"
ARTIFACT = DOCS / "validation/supervision_failure_01"
OUTPUT = ARTIFACT / "current_qualification_regression_02"
SUPERVISOR = ROOT / "runtime/owned_process_supervisor.py"
DRIVER = ROOT / "prepare_fixture.py"
FIXTURE_TEST = ROOT / "test_actual_unknown_child.py"
FAILURE_TEST = ROOT / "test_supervision_failure_paths.py"
PYTHON = Path("/usr/bin/python3").resolve(strict=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run() -> int:
    OUTPUT.mkdir(parents=False, exist_ok=False)
    qualifier_raw = QUALIFIER.read_bytes()
    qualifier = json.loads(qualifier_raw)
    expected_supervisor = qualifier["supervisor_sha256"]
    if qualifier["supervisor"] != str(SUPERVISOR) or sha(SUPERVISOR) != expected_supervisor:
        raise RuntimeError("current preregistered Supervisor identity mismatch")
    source_paths = [SUPERVISOR, DRIVER, FIXTURE_TEST, FAILURE_TEST]
    before = {str(path): sha(path) for path in source_paths}
    failures_raw = (ARTIFACT / "summary.json").read_bytes()
    failures = json.loads(failures_raw)
    if not failures["passed"] or len(failures["cases"]) != 2:
        raise RuntimeError("two actual failure cases are not completed")
    if not failures["sources_unchanged"] or failures["source_before_sha256"] != failures["source_after_sha256"]:
        raise RuntimeError("failure validation source changed")
    for path in (SUPERVISOR,):
        if failures["source_before_sha256"][str(path)] != before[str(path)]:
            raise RuntimeError("failure cases did not use current source")
    save(OUTPUT / "preregister.json", {
        "schema": "current-supervision-qualification-preregister/v1",
        "test_path": str(Path(__file__).resolve()), "test_sha256": sha(Path(__file__).resolve()),
        "source_sha256": before, "qualifier_path": str(QUALIFIER),
        "qualifier_sha256": hashlib.sha256(qualifier_raw).hexdigest(),
        "existing_failure_summary_path": str(ARTIFACT / "summary.json"),
        "existing_failure_summary_sha256": hashlib.sha256(failures_raw).hexdigest(),
        "python_path": str(PYTHON), "python_sha256": sha(PYTHON),
        "command": [str(PYTHON), "-I", "-S", "-B", str(Path(__file__).resolve())],
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "case_budget_seconds": 5.0, "case_body_alarm_seconds": 2.6,
        "exception_cleanup_budget_seconds": 2.0, "overall_budget_seconds": 10.0,
        "cases": [{"mode": "normal", "expected_exit": 0, "qualification_clean": True},
                  {"mode": "fork", "expected_exit": 0, "qualification_clean": False,
                   "unexpected_descendant_count": 1}],
        "signals_only_supervisor_created_PGID": True, "ROS_initialized": False,
        "stage_qualified": False, "execute_qualified": False,
        "prior_unknown_child_01_preserved": True,
        "driver_executed": False,
        "failure_cases_observed_driver_sha256": failures["source_before_sha256"][str(DRIVER)],
        "driver_identity_scope": "observed source only; all cases call Supervisor directly",
    })
    supervisor_module = load(SUPERVISOR, "owned_current_qualification_supervisor")
    fixture_module = load(FIXTURE_TEST, "owned_current_qualification_fixture")
    started = time.monotonic()
    results = []
    def alarm(_signal, _frame):
        raise TimeoutError("current qualification case body budget expired")
    previous_handler = signal.signal(signal.SIGALRM, alarm)
    try:
        for mode, directory in (("normal", "single_process_zero_exit"),
                                ("fork", "actual_fork_zero_exit_unknown_child")):
            signal.setitimer(signal.ITIMER_REAL, 2.6)
            try:
                result = fixture_module.case(supervisor_module, OUTPUT / directory, mode)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            cleanup = result.get("cleanup", {})
            if cleanup.get("returncode") != 0:
                result["passed"] = False
                result["exit_assertion_error"] = "fixture must actually exit with code zero"
            if result["elapsed_seconds"] > 5.0:
                result["passed"] = False
                result["case_budget_exceeded"] = True
            results.append(result)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    after = {str(path): sha(path) for path in source_paths}
    summary = {
        "schema": "current-supervision-qualification-validation/v1", "cases": results,
        "passed": len(results) == 2 and all(row["passed"] for row in results) and before == after,
        "source_before_sha256": before, "source_after_sha256": after,
        "sources_unchanged": before == after, "elapsed_seconds": time.monotonic() - started,
        "ROS_initialized": False, "stage_qualified": False, "execute_qualified": False,
    }
    if summary["elapsed_seconds"] > 10.0:
        summary["passed"] = False
        summary["overall_budget_exceeded"] = True
    save(OUTPUT / "summary.json", summary)
    combined = {
        "schema": "current-four-supervision-cases/v1",
        "passed": bool(failures["passed"] and summary["passed"]),
        "qualifier_path": str(QUALIFIER), "qualifier_sha256": hashlib.sha256(qualifier_raw).hexdigest(),
        "supervisor_sha256": before[str(SUPERVISOR)],
        "driver_executed": False,
        "observed_driver_sha256_by_batch": {
            "failure_cases": failures["source_before_sha256"][str(DRIVER)],
            "qualification_regression": before[str(DRIVER)],
        },
        "actual_cases": failures["cases"] + results,
        "source_reports": [{"path": str(ARTIFACT / "summary.json"),
                            "sha256": hashlib.sha256(failures_raw).hexdigest()},
                           {"path": str(OUTPUT / "summary.json"),
                            "sha256": sha(OUTPUT / "summary.json")}],
        "case_count": 4, "ROS_initialized": False, "stage_qualified": False,
        "execute_qualified": False, "research_conclusion": None,
        "scope": "Actual process ownership, bounded reclamation and disqualifying evidence at component level",
    }
    save(ARTIFACT / "summary_current_four_cases.json", combined)
    print(json.dumps({"passed": combined["passed"], "case_count": 4,
                      "new_elapsed_seconds": summary["elapsed_seconds"],
                      "new_cases": [{"case": row["case"], "passed": row["passed"],
                                     "cleanup": row.get("cleanup"),
                                     "final_proc_absence": row.get("final_proc_absence")}
                                    for row in results]}, ensure_ascii=False))
    return 0 if combined["passed"] else 1


if __name__ == "__main__":
    sys.exit(run())
