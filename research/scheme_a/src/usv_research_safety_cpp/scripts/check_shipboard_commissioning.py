#!/usr/bin/env python3
"""实船调试服务接管的服务级验收判据。

用法:
  check_shipboard_commissioning.py --release-root R --underlay U --run RUN \
      --proc-snapshot SNAPSHOT.json --out NEW.json [--baseline PREVIOUS.json] \
      [--expect-active]

退出码语义是**窄**的:
  0 —— 本计划声明的"服务级验收"通过(接管在位、真实输入被观测、零求解零物理输出);
  2 —— 失败或证据缺失。

它不评估航行控制资格: physical_control_authorised / closed_loop_verified 恒为
false，且即使所有检查通过也不会被改成 true。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

EXIT_PASS = 0
EXIT_FAIL = 2
EXIT_USAGE = 1

STATUS_SCHEMA = "p1-shipboard-commissioning-status-v1"
SUPERVISOR_SCHEMA = "p1-shipboard-supervisor-v1"
CONTRACT_SCHEMA = "p1-shipboard-commissioning-v1"

INPUT_KEYS = ("state", "odom", "imu", "path", "profile")
STATUS_TOP = ("schema", "run_id", "boot_id", "host_boot_id", "contract_hash", "plan_sha256",
              "mode", "seq", "at_ns", "phase", "failure_reason", "physical_output_enabled",
              "jobs_submitted", "anchor_known", "control_inputs_verified",
              "closed_loop_verified", "worker", "fcu", "inputs", "source")
WORKER_KEYS = ("pid", "instance", "model_runtime_ready", "capability_age_ns",
               "completed_jobs", "active_job", "pending_count")
INPUT_FIELDS = ("seen", "count", "receipt_age_ns", "source_stamp_ns", "frame", "child_frame",
                "truncated", "finite", "resource_valid")
SOURCE_KEYS = ("generated", "emitted", "dropped", "failed")

# 执行侧话题：本 run 一个都不允许出现。
EXECUTION_TOPICS = (
    "/p1/solve_job", "/p1/plant_command", "/p1/execution_decision",
    "/p1/plant_receipt", "/p1/plant_hold_close",
    "/mavros/setpoint_velocity/cmd_vel", "/mavros/rc/override",
    "/wamv/thrusters/left/thrust", "/wamv/thrusters/right/thrust",
)
ALLOWED_STATUS_PUBLISHERS = {"/p1/commissioning_status"}
RESEARCH_NODES = ("p1_regulator", "p1_solver_worker", "p1_commissioning_supervisor")


class Checker:
    def __init__(self, release_root: str, underlay: str, run_dir: str,
                 proc_snapshot: str, expect_active: bool = False) -> None:
        self.release_root = os.path.realpath(release_root)
        self.underlay = os.path.realpath(underlay)
        self.run_dir = os.path.realpath(run_dir)
        self.proc_snapshot_path = os.path.realpath(proc_snapshot)
        self.expect_active = bool(expect_active)
        self.checks: list[dict] = []
        self.errors: list[str] = []
        self.capture = self._load_capture()

    # ------------------------------------------------------------ 基础工具
    def _load_capture(self):
        """只从冻结在 R/deploy 的固定文件加载原语，不动态 import 可变线上目录。"""
        path = os.path.join(self.release_root, "deploy", "capture_release_identity.py")
        if not os.path.isfile(path):
            self.fail("capture_primitive_missing", path)
            return None
        spec = importlib.util.spec_from_file_location("p1_capture_release_identity", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fail(self, name: str, detail: str = "") -> None:
        self.errors.append(f"{name}: {detail}" if detail else name)

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        self.checks.append({"name": name, "ok": bool(condition),
                            "detail": "" if condition else detail})
        if not condition:
            self.errors.append(f"{name}: {detail}" if detail else name)
        return condition

    @staticmethod
    def read_json(path: str):
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))

    @staticmethod
    def read_jsonl(path: str) -> list[dict]:
        out = []
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out

    # ------------------------------------------------------------ 运行软件集合
    def resolve_install_expectations(self) -> dict:
        """install manifest 的相对 path 规范化成 R/install 下的绝对路径。"""
        manifest = self.read_json(os.path.join(self.release_root, "evidence",
                                              "install_manifest.json"))
        expected = {}
        for record in manifest.get("records", []):
            relative = record.get("path")
            digest = record.get("sha256")
            resolved = record.get("resolved_path") or relative
            if not relative or not digest:
                self.fail("install_manifest_record_incomplete", str(record)[:160])
                continue
            absolute = os.path.join(self.release_root, "install", relative)
            expected[os.path.realpath(absolute)] = {
                "sha256": digest, "path": relative,
                "recorded_resolved": os.path.realpath(resolved),
            }
        if not expected:
            self.fail("install_manifest_empty")
        return expected

    def evaluate_processes(self, snapshot: dict, expected: dict) -> None:
        processes = snapshot.get("processes") or []
        names: dict[str, list[dict]] = {}
        for record in processes:
            cmdline = record.get("cmdline") or []
            target = record.get("exe_target") or ""
            name = ""
            if cmdline:
                name = os.path.basename(cmdline[0])
            if name in ("p1_regulator", "p1_solver_worker", "p1_commissioning_supervisor"):
                names.setdefault(name, []).append(record)
            elif any(token.endswith("run_shipboard_commissioning.py") for token in cmdline):
                names.setdefault("p1_commissioning_supervisor", []).append(record)
            elif target.startswith(os.path.join(self.release_root, "install")):
                self.fail("unknown_overlay_process", target)
        for node in RESEARCH_NODES:
            self.check(f"process_present:{node}", len(names.get(node, [])) == 1,
                       f"observed {len(names.get(node, []))}")
        for record in processes:
            self.check("process_exe_not_deleted", not record.get("exe_deleted"),
                       record.get("exe_target", ""))
        # 研究双节点必须是新 R 下的实际 ELF，且磁盘字节 == 进程映像。
        for node in ("p1_regulator", "p1_solver_worker"):
            for record in names.get(node, []):
                target = record.get("exe_target") or ""
                self.check(f"{node}:under_release", target.startswith(
                    os.path.join(self.release_root, "install") + os.sep), target)
                self.check(f"{node}:live_sha_matches_disk",
                           record.get("exe_sha256") is not None and
                           record.get("exe_sha256") == record.get("disk_sha256"),
                           f"{record.get('exe_sha256')} != {record.get('disk_sha256')}")
                expectation = expected.get(os.path.realpath(target))
                self.check(f"{node}:install_manifest_matches",
                           expectation is not None and
                           expectation["sha256"] == record.get("exe_sha256"),
                           f"expected={expectation}")
                for library in record.get("external_libraries") or []:
                    path = library.get("path", "")
                    allowed = (path.startswith(os.path.join(self.release_root, "install") + os.sep)
                               or path.startswith(self.underlay + os.sep)
                               or path.startswith("/opt/ros/jazzy/")
                               or path.startswith("/home/trevor/acados/")
                               or path.startswith("/lib/")
                               or path.startswith("/usr/lib/"))
                    self.check(f"{node}:library_binding", allowed, path)
        # Python 监督器: 核解释器 + cmdline 脚本路径 + 完整 SHA。
        for record in names.get("p1_commissioning_supervisor", []):
            cmdline = record.get("cmdline") or []
            script = next((token for token in cmdline
                           if token.endswith("run_shipboard_commissioning.py")), "")
            self.check("supervisor:script_under_release", script.startswith(
                os.path.join(self.release_root, "install") + os.sep), script)
            expectation = expected.get(os.path.realpath(script)) if script else None
            self.check("supervisor:script_manifest_matches", expectation is not None and
                       os.path.isfile(script) and
                       self.capture.sha256_bytes(open(script, "rb").read()) == expectation["sha256"],
                       f"expected={expectation}")
            self.check("supervisor:interpreter",
                       record.get("interpreter") is True, record.get("exe_target", ""))
        # 唯一 MAVROS，且唯独它持有飞控串口。
        mavros = [record for record in processes
                  if os.path.basename(record.get("exe_target") or "") == "mavros_node"]
        self.check("mavros_unique", len(mavros) == 1, f"observed {len(mavros)}")
        holders = snapshot.get("serial_holders") or {}
        for device in ("/dev/ttyAMA10", "/dev/ttyAMA4"):
            pids = holders.get(device) or []
            self.check(f"serial_holder_count:{device}", len(pids) <= 1, f"{pids}")
        if mavros:
            fcu_pids = set(holders.get("/dev/ttyAMA10") or [])
            self.check("fcu_serial_held_by_mavros",
                       fcu_pids == {mavros[0]["pid"]}, f"{fcu_pids} vs {mavros[0]['pid']}")
        # 明确禁止的进程类型
        for record in processes:
            base = os.path.basename(record.get("exe_target") or "")
            cmdline = record.get("cmdline") or []
            self.check("no_legacy_mpc_node", base != "mpc_node", base)
            self.check("no_sim_plant", base != "p1_x86_plant", base)
            self.check("no_raw_console",
                       not any(token in cmdline for token in ("ros2 bag record",)), "")

    # ------------------------------------------------------------ 记录与状态
    def evaluate_supervisor_log(self) -> tuple[dict | None, list[dict], bool]:
        path = os.path.join(self.run_dir, "supervisor.jsonl")
        if not os.path.isfile(path):
            self.fail("supervisor_log_missing", path)
            return None, [], False
        records = self.read_jsonl(path)
        if not records:
            self.fail("supervisor_log_empty", path)
            return None, [], False
        for record in records:
            if record.get("schema") != SUPERVISOR_SCHEMA:
                self.fail("supervisor_log_schema", str(record.get("schema")))
                break
        for field in ("invocation_id", "run_id", "boot_id", "host_boot_id", "at_ns", "event"):
            self.check(f"supervisor_field:{field}",
                       all(field in record for record in records), field)
        events = {record.get("event") for record in records}
        self.check("supervisor_saw_startup", "startup" in events, str(sorted(events)))
        self.check("supervisor_no_failure_event", "failure" not in events, str(sorted(events)))
        samples = [record for record in records if record.get("event") == "sample"]
        self.check("supervisor_samples_present", len(samples) >= 2, f"{len(samples)}")
        for sample in samples:
            status = sample.get("regulator_status")
            if status is None:
                continue
            for field in ("status_received_ns", "worker_capability_received_ns", "processes"):
                self.check(f"sample_field:{field}", field in sample, field)
        shutdown = [record for record in records if record.get("event") == "shutdown"]
        finished = len(shutdown) > 0
        if self.expect_active:
            self.check("supervisor_active_no_shutdown", len(shutdown) == 0,
                       f"shutdown_count={len(shutdown)}")
        elif finished:
            self.check("supervisor_shutdown_once", len(shutdown) == 1, f"{len(shutdown)}")
        else:
            self.check("supervisor_active_no_shutdown", True, "")
        terminal = shutdown[0] if shutdown else None
        return terminal, samples, finished

    def evaluate_status(self, status: dict, label: str) -> None:
        if status.get("schema") != STATUS_SCHEMA:
            self.fail(f"{label}:status_schema", str(status.get("schema")))
            return
        for key in STATUS_TOP:
            self.check(f"{label}:status_field:{key}", key in status, key)
        # 三把锁: 永远为 false / 0。
        self.check(f"{label}:physical_output_disabled",
                   status.get("physical_output_enabled") is False, "")
        self.check(f"{label}:jobs_submitted_zero", status.get("jobs_submitted") == 0, "")
        self.check(f"{label}:anchor_unknown", status.get("anchor_known") is False, "")
        self.check(f"{label}:closed_loop_false",
                   status.get("closed_loop_verified") is False, "")
        self.check(f"{label}:mode", status.get("mode") == "commissioning",
                   str(status.get("mode")))
        self.check(f"{label}:phase_allowed",
                   status.get("phase") in ("starting", "ready", "failed", "stopping"),
                   str(status.get("phase")))
        worker = status.get("worker") or {}
        for key in WORKER_KEYS:
            self.check(f"{label}:worker_field:{key}", key in worker, key)
        self.check(f"{label}:worker_completed_jobs_zero",
                   worker.get("completed_jobs") == 0, str(worker.get("completed_jobs")))
        self.check(f"{label}:worker_active_job_zero",
                   worker.get("active_job") == 0, str(worker.get("active_job")))
        self.check(f"{label}:worker_pending_zero",
                   worker.get("pending_count") == 0, str(worker.get("pending_count")))
        fcu = status.get("fcu") or {}
        self.check(f"{label}:fcu_field_seen", "seen" in fcu, "")
        inputs = status.get("inputs") or {}
        for key in INPUT_KEYS:
            self.check(f"{label}:input_present:{key}", key in inputs, key)
            entry = inputs.get(key) or {}
            for field in INPUT_FIELDS:
                self.check(f"{label}:input_field:{key}:{field}", field in entry, field)
            if not entry.get("seen", False):
                self.check(f"{label}:unseen_input_not_zeroed:{key}",
                           entry.get("count") == 0 and entry.get("receipt_age_ns") is None
                           and entry.get("source_stamp_ns") is None, str(entry)[:160])
        source = status.get("source") or {}
        for key in SOURCE_KEYS:
            self.check(f"{label}:source_field:{key}", key in source, key)
        self.check(f"{label}:source_not_failed", source.get("failed") is False, "")
        self.check(f"{label}:source_no_dropped", source.get("dropped") == 0,
                   str(source.get("dropped")))
        generated = source.get("generated")
        emitted = source.get("emitted")
        if isinstance(generated, int) and isinstance(emitted, int):
            self.check(f"{label}:source_emitted_le_generated", emitted <= generated, "")
        # 控制输入是否被验证: 只由"五路真实输入齐备且有限"决定, 且这里不因通过而放宽。
        if status.get("control_inputs_verified") is True:
            for key in INPUT_KEYS:
                entry = inputs.get(key) or {}
                self.check(f"{label}:verified_requires_input:{key}",
                           entry.get("seen") is True, key)

    def evaluate_run(self) -> dict:
        expected = self.resolve_install_expectations()
        snapshot_ok = os.path.isfile(self.proc_snapshot_path)
        self.check("proc_snapshot_present", snapshot_ok, self.proc_snapshot_path)
        if snapshot_ok:
            snapshot = self.read_json(self.proc_snapshot_path)
            if self.capture is not None:
                self.evaluate_processes(snapshot, expected)
        terminal, samples, finished = self.evaluate_supervisor_log()

        # 是否已结束完全由 supervisor.jsonl 是否出现 shutdown 事件判定；
        # 活动 run 仅校验观测快照，已结束 run 额外要求关闭 summary。
        latest_status = None
        for sample in reversed(samples):
            candidate = sample.get("regulator_status")
            if isinstance(candidate, dict):
                latest_status = candidate
                break
        self.check("status_snapshot_available", isinstance(latest_status, dict), "")
        if isinstance(latest_status, dict):
            self.evaluate_status(latest_status, "active" if not finished else "final")
            if not finished:
                self.check("active_run_ready",
                           latest_status.get("phase") == "ready",
                           str(latest_status.get("phase")))
                self.check("active_run_no_failure_reason",
                           latest_status.get("failure_reason", "") == "",
                           str(latest_status.get("failure_reason")))
        if finished:
            for name in ("worker.source.jsonl", "regulator.source.jsonl"):
                path = os.path.join(self.run_dir, name)
                if not os.path.isfile(path):
                    self.fail(f"closed_summary_missing:{name}")
                    continue
                summary = [record for record in self.read_jsonl(path)
                           if record.get("type") in ("source_summary", "worker_summary")]
                self.check(f"closed_summary_present:{name}", len(summary) == 1,
                           f"{len(summary)}")
                for record in summary:
                    if record.get("type") == "source_summary":
                        self.check(f"closed_summary_complete:{name}",
                                   record.get("generated") == record.get("emitted"), str(record))
                    else:
                        self.check(f"closed_summary_no_fatal:{name}",
                                   record.get("fatal") is False, str(record))
        else:
            self.check("active_run_source_still_open", True,
                       "active run: no permanent SHA is bound to a still-written log")

        # 本 run 不得出现候选/完成 job。
        for name in ("worker.source.jsonl", "regulator.source.jsonl"):
            path = os.path.join(self.run_dir, name)
            if not os.path.isfile(path):
                continue
            for record in self.read_jsonl(path):
                kind = record.get("type")
                if kind == "candidate":
                    self.fail("candidate_published_in_commissioning", name)
                    break
                if kind == "job_refused":
                    self.check("job_refused_reason",
                               record.get("reason") == "commissioning_no_jobs",
                               str(record.get("reason")))
                    self.check("job_refused_no_native",
                               record.get("native_solve_entries_this_job") == 0, "")
        return {
            "finished": finished,
            "terminal_event": terminal,
            "status": latest_status,
            "samples": len(samples),
        }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="方案A 实船调试服务接管服务级验收")
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--underlay", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--proc-snapshot", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--expect-active", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.run):
        print(f"checker fatal: run directory missing: {args.run}", file=sys.stderr)
        return EXIT_FAIL
    checker = Checker(args.release_root, args.underlay, args.run,
                      args.proc_snapshot, expect_active=args.expect_active)
    try:
        run_facts = checker.evaluate_run()
    except Exception as error:  # noqa: BLE001 - 判据自身出错也必须 exit 2
        checker.fail("checker_exception", repr(error))
        run_facts = {}

    baseline = None
    if args.baseline:
        try:
            baseline = Checker.read_json(args.baseline)
        except (OSError, ValueError) as error:
            checker.fail("baseline_unreadable", str(error))

    verdict = "PASS" if not checker.errors else "FAIL"
    document = {
        "schema": "p1-shipboard-commissioning-check-v1",
        "release_root": checker.release_root,
        "underlay": checker.underlay,
        "run": checker.run_dir,
        "verdict": verdict,
        "exit_code": EXIT_PASS if verdict == "PASS" else EXIT_FAIL,
        "checks": checker.checks,
        "checks_total": len(checker.checks),
        "checks_failed": sum(1 for item in checker.checks if not item["ok"]),
        "errors": checker.errors,
        "run_facts": run_facts,
        # 分开交付：服务接管 / 执行资格 是两件事。
        "commissioning_service_takeover_passed": verdict == "PASS",
        "physical_control_authorised": False,
        "physical_output_enabled": False,
        "closed_loop_verified": False,
        "control_inputs_verified": bool(
            (run_facts.get("status") or {}).get("control_inputs_verified") is True),
        "baseline_present": baseline is not None,
    }
    try:
        with open(args.out, "x", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError:
        print(f"checker fatal: output exists (exclusive): {args.out}", file=sys.stderr)
        return EXIT_FAIL
    except OSError as error:
        print(f"checker fatal: cannot write output: {error}", file=sys.stderr)
        return EXIT_FAIL
    print(f"verdict={verdict} checks={document['checks_total']} "
          f"failed={document['checks_failed']}")
    for error in checker.errors[:40]:
        print(f"  - {error}")
    return document["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
