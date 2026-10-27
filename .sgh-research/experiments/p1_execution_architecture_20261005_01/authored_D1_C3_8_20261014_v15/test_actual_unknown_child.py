#!/usr/bin/python3
"""Actual non-ROS fork test: resource reclamation is separate from qualification."""
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
PREREGISTER = Path("/home/trevor/MPC/scheme_A_prepare_close_20261010_02/preregister/plan_v3.json")
DEFAULT_OUTPUT = Path("/home/trevor/MPC/scheme_A_prepare_close_20261010_02/validation/unknown_child_01")
PYTHON = Path("/usr/bin/python3").resolve(strict=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def stat_identity(pid: int) -> dict | None:
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text()
        row = raw[raw.rindex(")") + 2:].split()
        return {"pid": pid, "state": row[0], "ppid": int(row[1]),
                "pgid": int(row[2]), "sid": int(row[3]), "start_ticks": int(row[19])}
    except (FileNotFoundError, ProcessLookupError):
        return None


def fixture(mode: str, directory: Path) -> None:
    # All descendants have an independent self-exit budget if the runner fails.
    stop_requested = False
    def requested(_sig, _frame):
        nonlocal stop_requested
        stop_requested = True
    signal.signal(signal.SIGINT, requested)
    signal.signal(signal.SIGTERM, requested)
    deadline = time.monotonic() + 8.0
    child = None
    if mode == "fork":
        child = os.fork()
        if child == 0:
            while not stop_requested and time.monotonic() < deadline:
                time.sleep(.01)
            os._exit(0)
    parent_identity = stat_identity(os.getpid())
    child_identity = stat_identity(child) if child else None
    save(directory / "fixture_ready.json", {
        "mode": mode, "parent": parent_identity, "child": child_identity,
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "self_exit_seconds": 8.0, "ROS_imported": False,
    })
    while not stop_requested and time.monotonic() < deadline:
        time.sleep(.01)
    if child:
        # The group signal reaches the real fork child; its parent reaps it.
        # No test code signals arbitrary PID or discovers a foreign PGID.
        while time.monotonic() < deadline + .5:
            reaped, _status = os.waitpid(child, os.WNOHANG)
            if reaped == child:
                break
            time.sleep(.01)
        else:
            raise RuntimeError("fixture child not reaped within its own budget")


def load_supervisor():
    spec = importlib.util.spec_from_file_location("owned_unknown_child_test_supervisor", SUPERVISOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wait_ready(path: Path, module, item, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
        if item.process.poll() is not None:
            raise RuntimeError("fixture exited before readiness")
        time.sleep(.01)
    raise RuntimeError("fixture readiness deadline")


def case(module, output: Path, mode: str) -> dict:
    output.mkdir()
    supervisor = module.Supervisor(output)
    item = None
    result = {"case": mode, "passed": False}
    started = time.monotonic()
    try:
        # Minimal environment and -I -S avoid ambient Python/user ROS startup.
        env = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1", "LANG": "C.UTF-8"}
        argv = [str(PYTHON), "-I", "-S", str(Path(__file__).resolve()),
                "--fixture", mode, "--output", str(output)]
        item = supervisor.spawn(mode, argv, env, PYTHON, sha(PYTHON), cwd=output)
        ready = wait_ready(output / "fixture_ready.json", module, item)
        parent = ready["parent"]
        if parent["pid"] != item.process.pid or parent["start_ticks"] != item.identity["start_ticks"]:
            raise AssertionError("actual leader identity changed")
        if parent["pgid"] != parent["pid"] or parent["sid"] != parent["pid"]:
            raise AssertionError("fixture was not in its owned new session")
        before = supervisor.members(item)
        child = ready["child"]
        if mode == "fork":
            if not child or child["ppid"] != parent["pid"] or child["pgid"] != parent["pid"] or child["sid"] != parent["pid"]:
                raise AssertionError("actual fork child ancestry/session mismatch")
            if {r["pid"] for r in before} != {parent["pid"], child["pid"]}:
                raise AssertionError("Supervisor did not observe actual parent and fork child")
        elif child is not None or {r["pid"] for r in before} != {parent["pid"]}:
            raise AssertionError("normal fixture was not a single process")
        cleanup = supervisor.stop(item, grace=.5, term_grace=.5, kill_postcheck=1.0,
                                  first_signal=signal.SIGINT, natural_grace=0)
        pids = [parent["pid"]] + ([child["pid"]] if child else [])
        final = [{"pid": pid, "original_start_ticks": parent["start_ticks"] if pid == parent["pid"] else child["start_ticks"],
                  "current": stat_identity(pid), "proc_path_exists": (Path("/proc") / str(pid)).exists()} for pid in pids]
        if any(row["current"] is not None or row["proc_path_exists"] for row in final):
            raise AssertionError("original parent/child /proc identity still exists after cleanup")
        if not cleanup["cleanup_complete"] or not cleanup["resource_cleanup_complete"] or cleanup["remaining_members"]:
            raise AssertionError("owned resources were not fully reclaimed")
        expected_qualification = mode == "normal"
        if cleanup["qualification_clean"] is not expected_qualification:
            raise AssertionError("resource cleanup was confused with unknown-child qualification")
        unexpected = cleanup["unexpected_descendants"]
        if mode == "fork":
            if len(unexpected) != 1 or unexpected[0]["identity"]["pid"] != child["pid"] or unexpected[0]["identity"]["start_ticks"] != child["start_ticks"]:
                raise AssertionError("actual unknown child was not retained in qualification evidence")
        elif unexpected:
            raise AssertionError("normal leader was misclassified as an unknown child")
        result.update(passed=True, ready=ready, observed_members=before, cleanup=cleanup,
                      final_proc_absence=final, qualification_expected=expected_qualification)
    except BaseException as error:
        result["error"] = repr(error)
    finally:
        if item is not None and item.cleanup is None:
            result["exception_cleanup"] = supervisor.stop(item, .5, .5, 1.0)
        supervisor.close()
        result["elapsed_seconds"] = time.monotonic() - started
        result["supervisor_evidence_failed"] = supervisor.evidence_failed
        result["supervisor_cleanup_failed"] = supervisor.cleanup_failed
        save(output / "result.json", result)
    return result


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
    plan_raw = PREREGISTER.read_bytes()
    plan = json.loads(plan_raw)
    actual_supervisor_sha = sha(SUPERVISOR)
    expected_supervisor_sha = plan["files"][str(SUPERVISOR)]
    if actual_supervisor_sha != expected_supervisor_sha:
        raise RuntimeError("preregistered Supervisor source identity mismatch")
    module = load_supervisor()
    save(output / "test_manifest.json", {
        "schema": "actual-unknown-child-test-manifest/v1", "test_path": str(Path(__file__).resolve()),
        "test_sha256": sha(Path(__file__).resolve()), "supervisor_path": str(SUPERVISOR),
        "supervisor_sha256": actual_supervisor_sha, "preregister_path": str(PREREGISTER),
        "preregister_sha256": hashlib.sha256(plan_raw).hexdigest(), "python": str(PYTHON),
        "python_sha256": sha(PYTHON), "overall_budget_seconds": 12.0,
        "case_ready_budget_seconds": 2.0, "case_cleanup_budget_seconds": 2.0,
        "ROS_initialized": False, "signals_only_supervisor_created_PGID": True,
    })
    started = time.monotonic()
    # Test-body alarm causes Python unwinding through the owned cleanup finally.
    def alarm(_sig, _frame):
        raise TimeoutError("test overall budget expired")
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, 12.0)
    results = []
    try:
        results.append(case(module, output / "actual_fork_negative", "fork"))
        results.append(case(module, output / "single_process_positive", "normal"))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    summary = {"schema": "actual-unknown-child-validation/v1", "cases": results,
               "passed": len(results) == 2 and all(row["passed"] for row in results),
               "elapsed_seconds": time.monotonic() - started,
               "source_before_sha256": actual_supervisor_sha,
               "source_after_sha256": sha(SUPERVISOR), "ROS_initialized": False,
               "stage_qualified": False, "execute_qualified": False}
    if summary["source_before_sha256"] != summary["source_after_sha256"]:
        summary["passed"] = False
        summary["source_changed_during_validation"] = True
    save(output / "summary.json", summary)
    print(json.dumps({"passed": summary["passed"], "elapsed_seconds": summary["elapsed_seconds"],
                      "cases": [{"case": r["case"], "passed": r["passed"], "error": r.get("error"),
                                 "cleanup": r.get("cleanup")} for r in results]}, ensure_ascii=False))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", choices=("fork", "normal"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.fixture:
        fixture(args.fixture, args.output)
    else:
        sys.exit(run(args.output))
