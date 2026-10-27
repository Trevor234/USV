#!/usr/bin/python3
"""Actual process/ENOSPC fixtures, without ROS or source modifications."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parent
SUPERVISOR = ROOT / "runtime/owned_process_supervisor.py"
DRIVER = ROOT / "prepare_fixture.py"
OUTPUT = Path("/home/trevor/MPC/scheme_A_prepare_close_20261010_02/validation/supervision_failure_01")
PYTHON = Path("/usr/bin/python3").resolve(strict=True)
SLEEP = Path("/usr/bin/sleep").resolve(strict=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def load_supervisor():
    spec = importlib.util.spec_from_file_location("supervision_failure_test_supervisor", SUPERVISOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def final_absence(module, original):
    current = module.proc_identity(original["pid"], hash_exe=False)
    path_exists = (Path("/proc") / str(original["pid"])).exists()
    result = {"pid": original["pid"], "original_start_ticks": original["start_ticks"],
              "current_identity": current, "proc_path_exists": path_exists,
              "original_process_absent": current is None and not path_exists}
    if not result["original_process_absent"]:
        raise AssertionError("original child remains or PID is reused at final absence check")
    return result


def actual_case(module, root, name):
    directory = root / name
    directory.mkdir()
    supervisor = module.Supervisor(directory)
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    result = {"name": name, "passed": False, "ROS_initialized": False,
              "case_budget_seconds": 5.0, "signals_only_supervisor_owned_PGID": True,
              "evidence_qualification_clean": False}
    started = time.monotonic()
    try:
        if name == "registered_actual_exe_mismatch":
            caught = None
            try:
                # Deliberate authentication failure after a real sleep executable
                # has started in Supervisor's own newly minted process group.
                supervisor.spawn("mismatched", [str(SLEEP), "4"], env,
                                 PYTHON, sha(PYTHON), cwd=directory)
            except RuntimeError as error:
                caught = str(error)
            if not caught or "actual executable identity mismatch" not in caught:
                raise AssertionError("actual executable mismatch did not raise after launch")
            if set(supervisor.owned) != {"mismatched"}:
                raise AssertionError("registered failed-launch process was lost from registry")
            item = supervisor.owned["mismatched"]
            actual = module.proc_identity(item.process.pid)
            if actual is None or actual["start_ticks"] != item.identity["start_ticks"]:
                raise AssertionError("registered real process identity unavailable")
            if Path(actual["exe"]).resolve() != SLEEP or actual["exe_sha256"] != sha(SLEEP):
                raise AssertionError("fixture did not run the real declared mismatching executable")
            if actual["pgid"] != actual["pid"] or actual["sid"] != actual["pid"]:
                raise AssertionError("mismatch fixture was not in Supervisor's own session")
            result.update(expected_exception=caught, actual_identity=actual,
                          trusted_executable_verified=False,
                          registry_preserved_after_exception=True,
                          limitation="This checks registry reclamation. Driver must keep the launch-authentication error disqualifying even if a resource cleanup field is true.")
        else:
            item = supervisor.spawn("ledger_child", [str(SLEEP), "4"], env,
                                    SLEEP, sha(SLEEP), cwd=directory)
            actual = module.proc_identity(item.process.pid)
            if actual is None or actual["start_ticks"] != item.identity["start_ticks"]:
                raise AssertionError("ledger-failure fixture identity unavailable")
            # Close the real successful launch ledger, then use a real kernel
            # ENOSPC sink. No Supervisor method, process identity, or source is mocked.
            supervisor.ledger.close()
            supervisor.ledger = Path("/dev/full").open("w")
            supervisor.event("intentional_real_ENOSPC_ledger_write")
            if not supervisor.evidence_failed:
                raise AssertionError("real failing ledger write was not recorded")
            before_registry = set(supervisor.owned)
            rejected = None
            try:
                supervisor.spawn("must_not_start", [str(SLEEP), "4"], env,
                                 SLEEP, sha(SLEEP), cwd=directory)
            except RuntimeError as error:
                rejected = str(error)
            if not rejected or "supervision ledger failed" not in rejected:
                raise AssertionError("new spawn was not refused after failed evidence write")
            if set(supervisor.owned) != before_registry or (directory / "must_not_start.console.log").exists():
                raise AssertionError("ledger failure allowed another launch side effect")
            result.update(actual_identity=actual, ledger_fault="real /dev/full ENOSPC on flush",
                          evidence_failed_before_stop=True, new_launch_refused=rejected)
        cleanup = supervisor.stop(item, grace=.4, term_grace=.4, kill_postcheck=.6,
                                  first_signal=signal.SIGINT, natural_grace=0)
        if not cleanup["resource_cleanup_complete"] or not cleanup["cleanup_complete"] or cleanup["remaining_members"]:
            raise AssertionError("real registered child was not fully reclaimed")
        if name == "ledger_failure_resource_cleanup" and cleanup["qualification_clean"] is not False:
            raise AssertionError("failed ledger was incorrectly qualified clean")
        result.update(cleanup=cleanup, final_proc_absence=final_absence(module, actual),
                      passed=True)
    except BaseException as error:
        result["error"] = repr(error)
    finally:
        # Harvest registered processes even when spawn never returned an Owned.
        for registered in supervisor.owned.values():
            if registered.cleanup is None:
                result.setdefault("exception_cleanup", []).append(
                    supervisor.stop(registered, .4, .4, .6))
        supervisor.close()
        result["elapsed_seconds"] = time.monotonic() - started
        result["evidence_failed_after_close"] = supervisor.evidence_failed
        result["cleanup_failed_after_close"] = supervisor.cleanup_failed
        result["supervisor_memory_events"] = supervisor.memory_tail
        if result["elapsed_seconds"] > 5.0:
            result["passed"] = False
            result["case_budget_exceeded"] = True
        if name == "ledger_failure_resource_cleanup" and not supervisor.evidence_failed:
            result["passed"] = False
        save(directory / "result.json", result)
    return result


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    source_before = {str(path): sha(path) for path in (SUPERVISOR, DRIVER)}
    prereg = {"schema": "supervision-failure-preregister/v1", "cases": {
        "registered_actual_exe_mismatch": "Actual sleep starts with deliberately wrong expected Python identity; spawn must raise while registry still permits finite owned reclamation.",
        "ledger_failure_resource_cleanup": "Actual sleep plus real /dev/full ledger ENOSPC; evidence_failed must refuse further spawns but owned stop must reclaim resources and qualification_clean remain false."},
        "source_pins": source_before, "test_path": str(Path(__file__).resolve()),
        "test_sha256": sha(Path(__file__).resolve()), "python_path": str(PYTHON),
        "python_sha256": sha(PYTHON), "sleep_path": str(SLEEP), "sleep_sha256": sha(SLEEP),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "case_budget_seconds": 5.0, "overall_budget_seconds": 10.0,
        "cleanup_seconds_per_case": 1.4, "process_natural_exit_seconds": 4,
        "output_budget_bytes": 4194304, "ROS_initialized": False,
        "signals_only_supervisor_new_session_PGID": True,
        "command_argv": ["/usr/bin/python3", "-I", "-S", "-B", str(Path(__file__).resolve())],
        "cwd": "/home/trevor/USV", "stage_qualified": False}
    save(output / "preregister.json", prereg)
    module = load_supervisor()
    started = time.monotonic()
    results = []
    for name in prereg["cases"]:
        if time.monotonic() - started >= 5.0 and not results[-1]["passed"]:
            break
        def alarm(_sig, _frame):
            raise TimeoutError("case 5-second execution deadline")
        previous = signal.signal(signal.SIGALRM, alarm)
        signal.setitimer(signal.ITIMER_REAL, 3.5)
        try:
            results.append(actual_case(module, output, name))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    after = {str(path): sha(path) for path in (SUPERVISOR, DRIVER)}
    summary = {"schema": "supervision-failure-validation/v1", "cases": results,
               "passed": len(results) == 2 and all(row["passed"] for row in results),
               "elapsed_seconds": time.monotonic() - started,
               "source_before_sha256": source_before, "source_after_sha256": after,
               "sources_unchanged": before_equal if (before_equal := source_before == after) else False,
               "ROS_initialized": False, "stage_qualified": False, "execute_qualified": False}
    if not summary["sources_unchanged"] or summary["elapsed_seconds"] > 10.0:
        summary["passed"] = False
    save(output / "summary.json", summary)
    print(json.dumps({"passed": summary["passed"], "elapsed_seconds": summary["elapsed_seconds"],
                      "cases": [{"name": r["name"], "passed": r["passed"], "error": r.get("error"),
                                 "cleanup": r.get("cleanup"), "final_proc_absence": r.get("final_proc_absence")} for r in results]}, ensure_ascii=False))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    sys.exit(run(args.output))
