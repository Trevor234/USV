#!/usr/bin/env python3
"""Create-only VRX shadow/execute runs; no hot switching or implicit qualification.

Only the invoking owner may start a run after sourcing Jazzy and the workspace.
The frozen F5 legacy executable supplies shadow physical outputs. Execute is
refused unless an explicitly hashed non-diagnostic contract is qualified.
Every process is owned, every failed run is retained, and no checker pass is
inferred from successful process startup or a collected bag.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

from owned_process_supervisor import Supervisor, boot_id, proc_identity, proc_table, sha256_file
from run_no_output_calibration import exclusive_json, host_preflight, source_observation


F5 = "F5_20261005_atomic_freeze_01"
F5_NODE_SHA = "bc753aa81d27e16e7df2570539e6bc66d34a3bc973afbee18fbf232ea85d41bc"
F5_SOURCE_SHA = "2f1b457ce9644d6ceff722e4ce328fa6a5de23a2cb94f8470c022e0bd70f2dd8"
F5_REFERENCE_SHA = "7294a7cb0813516433ebf7608eebf6d9420295443a2d1546918ead1d95061c9a"
REQUESTED_STOP = False
P1_TYPES = {
    "/p1/solve_job": "usv_research_interfaces/msg/SolveJob",
    "/p1/solve_candidate": "usv_research_interfaces/msg/SolveCandidate",
    "/p1/worker_capability": "usv_research_interfaces/msg/WorkerCapability",
    "/p1/execution_decision": "usv_research_interfaces/msg/ExecutionDecision",
}
LEGACY_TYPES = {
    "/research/state_snapshot": "usv_research_interfaces/msg/StateSnapshot",
    "/research/control/applied": "usv_research_interfaces/msg/AppliedControl",
    "/research/cycle_timing": "usv_research_interfaces/msg/CycleTiming",
    "/research/reference_prediction": "usv_research_interfaces/msg/ReferencePrediction",
}


def stopped(_signum, _frame):
    global REQUESTED_STOP
    REQUESTED_STOP = True


def expect_sha(path: Path, expected: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256_file(path) != expected:
        raise RuntimeError("actual file identity differs from declared SHA: " + str(path))


def read_contract(path: Path, expected: str, mode: str) -> tuple[dict, str]:
    expect_sha(path, expected)
    def nonfinite(value):
        raise ValueError("nonfinite contract JSON constant: " + value)
    c = json.loads(path.read_text(), parse_constant=nonfinite)
    if (c.get("schema") != "p1-execution-contract-v2" or c.get("diagnostic_contract_revision") != 2
            or c.get("clock") != "CLOCK_MONOTONIC"):
        raise ValueError("unsupported contract/schema/clock")
    if c.get("N") != 20 or c.get("dt") != .2 or c.get("T_ns") != 200_000_000 or c.get("deadline_ns") != 150_000_000:
        raise ValueError("this validation runner requires the unchanged F5 N20/dt0.2 capability")
    if mode == "execute" and (c.get("execute_qualified") is not True
                               or c.get("parameters_are_diagnostic_only") is not False):
        raise RuntimeError("execute prohibited: M0b has not qualified this exact contract")
    if mode == "shadow" and (c.get("execute_qualified") is not False
                              or c.get("parameters_are_diagnostic_only") is not True):
        raise RuntimeError("shadow requires the explicit diagnostic contract, not an execute contract")
    for key in ("worker_grace_ns", "term_grace_ns", "kill_postcheck_ns",
                "shutdown_grace_ns", "active_watchdog_ns", "recording_ready_timeout_ns"):
        value = c.get(key)
        if type(value) is not int or not 0 < value <= 60_000_000_000:
            raise ValueError("finite cleanup/watchdog contract bound missing: " + key)
    if not isinstance(c.get("expected_imu_frame"), str) or not c["expected_imu_frame"]:
        raise ValueError("the actual VRX IMU frame requires its own explicit contract field")
    for key in ("odom_sim_lag_ns", "imu_sim_lag_ns", "source_future_slack_ns", "mixed_skew_ns"):
        if type(c.get(key)) is not int or c[key] <= 0:
            raise ValueError("the v2 contract requires an explicit positive source-time bound: " + key)
    if set(c.get("input_topics", {})) != {"odom", "imu", "path", "profile"} or set(c.get("output_topics", {})) != {"left", "right"}:
        raise ValueError("input/output channel keys differ from the fixed platform")
    named_topics = [*c["input_topics"].values(), *c["output_topics"].values(), "/clock", *P1_TYPES, *LEGACY_TYPES]
    if len(named_topics) != len(set(named_topics)) or not all(isinstance(t, str) and t.startswith("/") for t in named_topics):
        raise ValueError("declared topic names must be unique absolute ROS names")
    return c, expected


def fixed_f5_assets(root: Path, workspace: Path, c: dict) -> dict:
    """Verify preserved snapshots and mathematical inputs; never demand old live code."""
    import yaml
    base = root / ".sgh-research/baselines" / F5
    manifest = json.loads((base / "baseline_manifest.json").read_text())
    if manifest.get("baseline_id") != F5 or manifest.get("integrity", {}).get("frozen_baseline_verified") is not True:
        raise RuntimeError("F5 immutable baseline was not verified")
    installed = json.loads((base / "installed_hashes.json").read_text())
    rows = installed["files"] if isinstance(installed, dict) else installed
    records = {r["path"]: r for r in rows if r.get("sha256")}
    prefix = "usv_mpc_ws/install/"
    needed = {
        "legacy": prefix + "usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node",
        "planner": prefix + "usv_planning_cpp/lib/usv_planning_cpp/path_planner_node",
        "path_config": prefix + "usv_bringup/share/usv_bringup/config/path_config.yaml",
    }
    selected = {}
    for name, rel in needed.items():
        if rel not in records:
            raise RuntimeError("F5 installed inventory lacks required immutable asset: " + rel)
        p = base / "installed_snapshot" / rel
        expect_sha(p, records[rel]["sha256"])
        if name in ("legacy", "planner") and not os.access(p, os.X_OK):
            raise RuntimeError("immutable native snapshot lacks its original executable permission: " + str(p))
        selected[name] = {"path": str(p), "sha256": records[rel]["sha256"]}
    if selected["legacy"]["sha256"] != F5_NODE_SHA:
        raise RuntimeError("unexpected F5 legacy executable")
    legacy_source = base / "source_snapshot/usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp"
    expect_sha(legacy_source, F5_SOURCE_SHA)
    historical = root / ".sgh-research/experiments/p1_f5_atomic_baseline_20261005_02"
    launch_context = json.loads((historical / "launch_context.json").read_text())
    graph = json.loads((historical / "topic_graph.json").read_text())
    dump = graph["effective_parameter_dump"]["stdout"]
    if hashlib.sha256(dump.encode()).hexdigest() != graph["effective_parameter_dump"]["stdout_sha256"]:
        raise RuntimeError("historical actual F5 parameter dump digest differs")
    doc = yaml.safe_load(dump)
    params = (doc.get("/mpc_controller_node") or doc.get("mpc_controller_node"))["ros__parameters"]
    fixed = {}
    for raw, digest in launch_context["config_inputs"].items():
        p = Path(raw)
        expect_sha(p, digest)
        fixed[str(p)] = digest
    reference = root / ".sgh-research/experiments/p1_atomic_freeze_20261005_01/references/straight.yaml"
    expect_sha(reference, F5_REFERENCE_SHA)
    if c["nominal_hash"] != params["research_nominal_config_hash"]:
        raise RuntimeError("contract model identity differs from actual F5 nominal model")
    if c["hydro"] != params["vehicle"]:
        raise RuntimeError("contract hydro differs from the unchanged actual F5 nominal parameters")
    for key, actual in (("Q", params["dynamic"]["Q"]), ("R", params["dynamic"]["R"]),
                        ("Rd", params["dynamic"]["Rd"]), ("Qf_scale", params["dynamic"]["Qf_scale"]),
                        ("backend_rate_n_s", params["dynamic"]["dT_max"]),
                        ("command_min_n", params["dynamic"]["T_min"]),
                        ("command_max_n", params["dynamic"]["T_max"]),
                        ("map_scale", params["vrx_thrust_scale"]),
                        ("publisher_max_n", params["vrx_thrust_cmd_max"]),
                        ("reference_start_offset", params["reference_start_offset"]),
                        ("cruise_speed", params["cruise_speed"])):
        if c[key] != actual:
            raise RuntimeError("declared experiment changes a fixed F5 mathematical parameter: " + key)
    if c["input_topics"] != {k: params[k + "_topic"] for k in ("odom", "imu", "path", "profile")}:
        raise RuntimeError("contract input topics differ from the F5 platform")
    if c["output_topics"] != {"left": params["vrx_left_thrust_topic"], "right": params["vrx_right_thrust_topic"]}:
        raise RuntimeError("contract physical output topics differ from F5")
    return {"baseline_id": F5, "manifest_sha256": sha256_file(base / "baseline_manifest.json"),
            "selected_immutable_installed_assets": selected, "source_snapshot_sha256": F5_SOURCE_SHA,
            "source_snapshot": str(legacy_source), "reference": str(reference),
            "reference_sha256": F5_REFERENCE_SHA, "fixed_input_sha256": fixed,
            "f5_actual_parameters": params, "f5_parameter_dump_sha256": hashlib.sha256(dump.encode()).hexdigest(),
            "f5_actual_parameter_evidence": str(historical / "topic_graph.json"),
            "workspace": str(workspace), "old_live_source_install_required": False}


def expected_assets(path: Path) -> dict[str, str]:
    """Owner supplies a full current source/install manifest; no silent subset selection."""
    raw = json.loads(path.read_text())
    files = raw.get("files") if isinstance(raw, dict) else raw
    if not isinstance(files, list) or not files:
        raise ValueError("expected-assets must contain a nonempty files list of absolute path/sha256")
    answer = {}
    for item in files:
        p = Path(item["path"])
        if not p.is_absolute() or str(p) in answer:
            raise ValueError("expected assets paths must be absolute and unique")
        expect_sha(p, item["sha256"])
        answer[str(p)] = item["sha256"]
    return answer


class OwnedTree:
    """Capture actual ancestry, including descendants that create a new process group.

    Environment/partition alone never grants signal ownership. Untracked matching
    leftovers are reported and make cleanup fail; they are never killed.
    """
    def __init__(self, supervisor: Supervisor, env: dict):
        self.supervisor = supervisor
        self.env = env
        self.tracked: dict[int, dict] = {}
        self.root_pids = set()
        # Exact pre-existing identities never grant ownership. Their inaccessible
        # environments stay explicitly unknown; a new or tracked PID is not exempt.
        self.preexisting_unreadable = {}
        for item in proc_table():
            pid = item["pid"]
            if item["state"] == "Z" or pid == os.getpid():
                continue
            proc = Path("/proc") / str(pid)
            try:
                if proc.stat().st_uid != os.getuid():
                    continue
                (proc / "environ").read_bytes()
            except PermissionError:
                command_hash = hashlib.sha256((proc / "cmdline").read_bytes()).hexdigest()
                self.preexisting_unreadable[pid] = {**item, "uid": os.getuid(), "cmdline_sha256": command_hash}
            except (FileNotFoundError, ProcessLookupError):
                continue
        if len(self.preexisting_unreadable) > 256:
            raise RuntimeError("preexisting environment observation exceeds finite bound")
        self.supervisor.event("preexisting_environment_unreadable", processes=list(self.preexisting_unreadable.values()),
                              ownership_granted=False, environment_scope_known=False,
                              reason="pre-existing process exact identity exclusion; never signalled")

    def preexisting_unreadable_matches(self, pid: int) -> bool:
        old = self.preexisting_unreadable.get(pid)
        if old is None or pid in self.tracked:
            return False
        now = proc_identity(pid, hash_exe=False)
        if now is None or any(now.get(k) != old.get(k) for k in ("pid", "start_ticks", "ppid", "pgid", "sid")):
            return False
        proc = Path("/proc") / str(pid)
        return proc.stat().st_uid == old["uid"] and hashlib.sha256((proc / "cmdline").read_bytes()).hexdigest() == old["cmdline_sha256"]

    def scoped(self, pid: int) -> bool:
        try:
            values = (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
            return all((key + "=" + self.env[key]).encode() in values
                       for key in ("ROS_DOMAIN_ID", "GZ_PARTITION"))
        except PermissionError:
            # /proc environs of another UID are normally unreadable. Those
            # processes never receive ownership or a signal from this runner.
            # A new or owned unreadable same-UID environment still fails.
            if (Path("/proc") / str(pid)).stat().st_uid != os.getuid():
                return False
            if self.preexisting_unreadable_matches(pid):
                return False  # observation-only, environment scope unknown
            raise
        except (FileNotFoundError, ProcessLookupError):
            return False

    def capture(self) -> None:
        table = {i["pid"]: i for i in proc_table()}
        for child in self.supervisor.owned.values():
            self.root_pids.add(child.process.pid)
            self.tracked.setdefault(child.process.pid, {**child.identity, "owned_root": child.name})
        for pid, item in table.items():
            if pid in self.tracked and item["start_ticks"] != self.tracked[pid]["start_ticks"] and self.scoped(pid):
                raise RuntimeError("scoped PID was reused after its recorded ownership; refusing to infer ownership")
        changed = True
        while changed:
            changed = False
            for pid, item in table.items():
                if pid in self.tracked or item["ppid"] not in self.tracked:
                    continue
                parent = self.tracked[item["ppid"]]
                actual_parent = table.get(item["ppid"])
                if actual_parent is None or actual_parent["start_ticks"] != parent["start_ticks"]:
                    continue
                if not self.scoped(pid):
                    raise RuntimeError("owned descendant changed declared domain/partition")
                identity = proc_identity(pid)
                if identity is None:
                    continue
                self.tracked[pid] = {**identity, "observed_parent": item["ppid"],
                                     "observed_parent_start_ticks": parent["start_ticks"],
                                     "owned_root": parent["owned_root"]}
                self.supervisor.event("owned_tree_descendant_observed", identity=self.tracked[pid])
                changed = True

    def remaining(self) -> list[dict]:
        answer = []
        for pid, old in self.tracked.items():
            now = proc_identity(pid, hash_exe=False)
            if now and now["start_ticks"] == old["start_ticks"] and now["state"] != "Z":
                answer.append({**now, "owned_root": old["owned_root"]})
        return answer

    def stop_separate_descendants(self, grace: float, term: float, postkill: float,
                                  preserve_roots=()) -> dict:
        def remaining():
            return [i for i in self.remaining() if i["owned_root"] not in preserve_roots]
        signals = []
        for sig, duration in ((signal.SIGINT, grace), (signal.SIGTERM, term), (signal.SIGKILL, postkill)):
            for item in remaining():
                if item["pid"] in self.root_pids:
                    continue  # Supervisor exclusively handles its direct groups.
                if boot_id() != self.supervisor.boot or not self.scoped(item["pid"]):
                    raise RuntimeError("owned descendant identity/boot/scope changed before signal")
                actual = proc_identity(item["pid"], hash_exe=False)
                if actual is None or actual["start_ticks"] != item["start_ticks"]:
                    continue
                try:
                    os.kill(item["pid"], sig)
                    signals.append({"pid": item["pid"], "start_ticks": item["start_ticks"], "signal": int(sig)})
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + duration
            while remaining() and time.monotonic() < deadline:
                time.sleep(.05)
            if not remaining():
                break
        unknown = []
        for item in proc_table():
            if item["pid"] == os.getpid() or item["state"] == "Z":
                continue
            old = self.tracked.get(item["pid"])
            if self.scoped(item["pid"]) and (old is None or old["start_ticks"] != item["start_ticks"]):
                unknown.append(item)
        result = {"cleanup_complete": not remaining() and not unknown,
                  "remaining_owned": remaining(), "unverified_matching_scope": unknown,
                  "scope_scan_uid": os.getuid(), "preserved_roots": list(preserve_roots),
                  "preexisting_environment_unreadable": list(self.preexisting_unreadable.values()),
                  "global_environment_scope_audit_complete": not self.preexisting_unreadable,
                  "cleanup_scope": "owned descendants and readable matching environment; exact pre-existing unreadable identities excluded without ownership",
                  "signals": signals, "unverified_processes_signalled": False}
        self.supervisor.cleanup_failed |= not result["cleanup_complete"]
        self.supervisor.event("owned_tree_cleanup_result", **result)
        return result


def run(args) -> int:
    import yaml
    if sys.platform != "linux" or Path(sys.executable).resolve() != Path("/usr/bin/python3").resolve():
        raise RuntimeError("run with the system ROS /usr/bin/python3 after sourcing Jazzy/workspace")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,103}", args.run_id):
        raise ValueError("an explicit unique path-safe run_id is required")
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 300:
        raise ValueError("duration must be finite and in [1,300] seconds")
    c, contract_hash = read_contract(args.contract, args.contract_hash, args.mode)
    if (args.test_delay_ms or args.test_native_block_ms) and c.get("fault_injection_enabled") is not True:
        raise ValueError("fault injection is not authorized by this contract")
    clock = time.get_clock_info("monotonic")
    if "CLOCK_MONOTONIC" not in clock.implementation or not clock.monotonic or clock.adjustable:
        raise RuntimeError("native and driver clocks must explicitly share CLOCK_MONOTONIC")
    directory = args.experiment_root.resolve(strict=True) / args.run_id
    directory.mkdir(exist_ok=False)
    args._created_directory = directory
    root, ws = args.workspace.resolve().parent, args.workspace.resolve()
    partition = "usv_" + args.run_id
    domain = str(args.ros_domain)
    env = dict(os.environ, ROS_DOMAIN_ID=domain, ROS_LOCALHOST_ONLY="1", GZ_PARTITION=partition)
    os.environ.update(ROS_DOMAIN_ID=domain, ROS_LOCALHOST_ONLY="1", GZ_PARTITION=partition)
    env["ACADOS_SOURCE_DIR"] = str(root.parent / "acados")
    env["LD_LIBRARY_PATH"] = str(root.parent / "acados/lib") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    fixed = fixed_f5_assets(root, ws, c)
    current_assets = expected_assets(args.expected_assets)
    binaries = {}
    for name, filename, digest in (("worker", "p1_solver_worker", args.worker_sha256),
                                   ("regulator", "p1_regulator", args.regulator_sha256)):
        p = (ws / "install/usv_research_safety_cpp/lib/usv_research_safety_cpp" / filename).resolve(strict=True)
        expect_sha(p, digest)
        binaries[name] = {"path": str(p), "sha256": digest}
    binaries.update({k: v for k, v in fixed["selected_immutable_installed_assets"].items()
                     if k in ("legacy", "planner")})
    python = Path(sys.executable).resolve(strict=True)
    ros2 = Path(shutil.which("ros2") or "").resolve(strict=True)
    if not ros2.is_file() or ros2.name != "ros2":
        raise RuntimeError("ROS CLI unavailable; source the declared overlays")
    binaries["python"] = {"path": str(python), "sha256": sha256_file(python)}
    binaries["ros2_cli"] = {"path": str(ros2), "sha256": sha256_file(ros2)}
    sources = {k: directory / (k + "_source.jsonl") for k in ("worker", "regulator")}
    reference = directory / "straight.yaml"
    reference.write_bytes(Path(fixed["reference"]).read_bytes())
    legacy_run = args.run_id + "_legacy"
    mathematical_params = fixed["f5_actual_parameters"]
    legacy_params = json.loads(json.dumps(mathematical_params))
    identity_fields = {"research_run_id": legacy_run, "research_output_dir": str(directory / "legacy_source"),
                       "research_config_hash": hashlib.sha256(json.dumps(fixed["fixed_input_sha256"], sort_keys=True).encode()).hexdigest(),
                       "research_logging_armed": False}
    legacy_params.update(identity_fields)
    legacy_yaml = directory / "legacy_parameters.yaml"
    legacy_yaml.write_text(yaml.safe_dump({"/mpc_controller_node": {"ros__parameters": legacy_params}}, sort_keys=False))
    from usv_bringup.research_config_sources import prepare_config_sources
    config = prepare_config_sources(str(ws / "src/usv_bringup/config/p0_nominal_f3.yaml"),
                                    str(ws / "src/usv_bringup/config/p0_plant_f3.yaml"),
                                    str(ws / "src/usv_simulation/config/vrx_model.yaml"), str(directory / "config"))
    if config["nominal_effective_sha256"] != c["nominal_hash"]:
        raise RuntimeError("prepared nominal YAML identity differs from contract")
    raw_types = {"/clock": "rosgraph_msgs/msg/Clock", c["input_topics"]["odom"]: "nav_msgs/msg/Odometry",
                 c["input_topics"]["imu"]: "sensor_msgs/msg/Imu", c["input_topics"]["path"]: "nav_msgs/msg/Path",
                 c["input_topics"]["profile"]: "std_msgs/msg/Float64MultiArray",
                 **{topic: "std_msgs/msg/Float64" for topic in c["output_topics"].values()},
                 "/mpc/status": "std_msgs/msg/String", "/mpc/predicted_trajectory": "nav_msgs/msg/Path",
                 "/p1/stop": "std_msgs/msg/Bool"}
    topic_types = {**raw_types, **P1_TYPES, **LEGACY_TYPES}
    # Raw sensor streams may be best effort; typed observation streams remain
    # reliable with a declared recorder depth. Bag timestamps are receive time.
    qos_config = {topic: {"reliability": "best_effort" if topic in ("/clock", c["input_topics"]["odom"], c["input_topics"]["imu"]) else "reliable",
                           "durability": "transient_local" if topic == "/p1/worker_capability" else "volatile",
                           "history": "keep_last", "depth": 1024} for topic in topic_types}
    qos_path = directory / "recorder_qos.yaml"
    qos_path.write_text(yaml.safe_dump(qos_config, sort_keys=True))
    fault = ("controlled_pre_native_barrier_watchdog" if args.test_native_block_ms
             else "post_native_result_delay" if args.test_delay_ms else "none")
    context = {"schema": "p1-vrx-validation-context-v1", "run_id": args.run_id, "mode": args.mode,
               "boot_id": boot_id(), "contract_file": str(args.contract.resolve()), "contract_sha256": contract_hash,
               "source_files": {k: v.name for k, v in sources.items()}, "binaries": binaries,
               "bag_relative_path": "raw_bag", "topics": {"typed": P1_TYPES, "legacy": LEGACY_TYPES, "raw": raw_types},
               "recorder_topic_types": topic_types, "recorder_qos_sha256": sha256_file(qos_path),
               "bag_time_domain": "system_receive", "source_time_domain": "CLOCK_MONOTONIC and explicit message sim fields",
               "python_monotonic_clock": {"implementation": clock.implementation, "resolution_s": clock.resolution,
                   "monotonic": clock.monotonic, "adjustable": clock.adjustable, "domain": "CLOCK_MONOTONIC"},
               "runner_sha256": sha256_file(Path(__file__)),
               "supervisor_sha256": sha256_file(Path(__file__).with_name("owned_process_supervisor.py")),
               "ros_environment": {"ROS_DOMAIN_ID": domain, "ROS_LOCALHOST_ONLY": "1", "GZ_PARTITION": partition},
               "declaration": {"duration_s": args.duration, "test_delay_ms": args.test_delay_ms,
                   "test_native_block_ms": args.test_native_block_ms, "expected_fault": fault,
                   "execute_qualified": c["execute_qualified"], "legacy_run_id": legacy_run if args.mode == "shadow" else ""},
               "legacy_f5_provenance": fixed, "legacy_parameters_sha256": sha256_file(legacy_yaml),
               "legacy_allowed_identity_overrides": identity_fields,
               "current_asset_manifest_sha256": sha256_file(args.expected_assets), "current_assets": current_assets,
               "recording_scope": {"typed_new_streams": "whole-source identity sets require independent checker; never trimmed to the window",
                   "raw_inputs": "real VRX publisher counts unavailable; whole-run raw prefix/suffix completeness unknown",
                   "legacy_streams": "logging arm after recorder graph readiness; independent source/bag reconciliation still required",
                   "physical_graph": "startup gates and one-second samples; no continuous graph or plant-acceptance proof"},
               "normal_contract_complete": False, "plant_acceptance_observed": False,
               "force_measured": False, "execution_atomicity_proven": False, "gp_labels_ready": False,
               "created_ns": time.monotonic_ns()}
    exclusive_json(directory / "run_context.json", context)
    supervisor = Supervisor(directory)
    args._supervisor_created = True
    tree = OwnedTree(supervisor, env)
    node = rclpy = None
    failure, stop_reason = None, "not_started"
    cleanup = {}
    physical_verified = None
    physical_owner = "mpc_controller_node" if args.mode == "shadow" else "p1_regulator"
    owner_counts = None
    latest = {"capability": None, "active_job": 0, "active_since": None, "odom": None,
              "imu": None, "path": None, "clock": None, "applied": None}
    counts = Counter()
    observations = {"capability_count": 0, "decision_count": 0, "watchdog_seen": False}
    graph_events, cpu, params_dumps = [], {}, {}
    summaries = {}
    try:
        exclusive_json(directory / "host_preflight.json", host_preflight())
        import rclpy
        from rclpy.signals import SignalHandlerOptions
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rclpy.parameter import Parameter
        from rclpy.parameter_client import AsyncParameterClient
        from rosidl_runtime_py.utilities import get_message
        from std_msgs.msg import Bool
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        signal.signal(signal.SIGINT, stopped)
        signal.signal(signal.SIGTERM, stopped)
        node = rclpy.create_node("p1_vrx_validation_driver")
        reliable = QoSProfile(depth=32, reliability=ReliabilityPolicy.RELIABLE)
        best = QoSProfile(depth=32, reliability=ReliabilityPolicy.BEST_EFFORT)
        capq = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        stop_pub = node.create_publisher(Bool, "/p1/stop", reliable)

        def receive(topic, msg):
            counts[topic] += 1
            if topic == c["input_topics"]["odom"]:
                latest["odom"] = msg
            elif topic == c["input_topics"]["imu"]:
                latest["imu"] = msg
            elif topic == c["input_topics"]["path"]:
                latest["path"] = msg
            elif topic == "/clock":
                latest["clock"] = msg
            elif topic == "/research/control/applied" and msg.run_id == legacy_run:
                latest["applied"] = msg
            elif topic == "/p1/worker_capability" and (msg.run_id == args.run_id and msg.contract_hash == contract_hash and msg.boot_id == context["boot_id"]):
                observations["capability_count"] += 1
                latest["capability"] = msg
                if msg.active_job != latest["active_job"]:
                    latest["active_job"] = msg.active_job
                    latest["active_since"] = time.monotonic_ns() if msg.active_job else None
            elif topic == "/p1/execution_decision" and msg.run_id == args.run_id:
                observations["decision_count"] += 1

        # Subscription declarations expose type names for recorder discovery;
        # the driver creates no physical publisher, even during recorder setup.
        subscriptions = []
        for topic, typename in topic_types.items():
            qos = capq if topic == "/p1/worker_capability" else best if topic in ("/clock", c["input_topics"]["odom"], c["input_topics"]["imu"]) else reliable
            subscriptions.append(node.create_subscription(get_message(typename), topic,
                lambda msg, topic=topic: receive(topic, msg), qos))

        def pump():
            rclpy.spin_once(node, timeout_sec=.02)
            tree.capture()
            if REQUESTED_STOP:
                raise RuntimeError("operator interrupted the owned run")
            if supervisor.evidence_failed:
                raise RuntimeError("supervision ledger IO failed")

        def wait(predicate, seconds, description):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                pump()
                if predicate():
                    return
            raise TimeoutError(description)

        def graph(owner=None, persist=False):
            nonlocal physical_verified, owner_counts
            endpoints = {}
            for key, topic in c["output_topics"].items():
                endpoints[key] = [{"node_name": i.node_name, "node_namespace": i.node_namespace,
                                   "topic_type": i.topic_type, "gid": list(i.endpoint_gid)}
                                  for i in node.get_publishers_info_by_topic(topic)]
                if owner is None and endpoints[key]:
                    raise RuntimeError("physical publisher existed before owned controller startup")
                if owner is not None and (len(endpoints[key]) != 1 or endpoints[key][0]["node_name"] != owner):
                    physical_verified = False
                    raise RuntimeError("physical ownership graph mismatch: " + json.dumps(endpoints))
                if any(e["node_name"] in {"p1_solver_worker", "p1_regulator"} for e in endpoints[key]) and args.mode == "shadow":
                    physical_verified = False
                    raise RuntimeError("new shadow processes created physical publisher endpoints")
            item = {"monotonic_ns": time.monotonic_ns(), "physical_owner": owner,
                    "physical_endpoints": endpoints, "nodes": node.get_node_names_and_namespaces()}
            if persist:
                graph_events.append(item)
                supervisor.event("physical_graph_gate", **item)
            if owner is not None:
                physical_verified = True
                owner_counts = {k: len(v) for k, v in endpoints.items()}
            return item

        def command(name, arguments, timeout=15):
            child = supervisor.spawn(name, [str(python), str(ros2), *arguments], env,
                                     python, binaries["python"]["sha256"])
            end = time.monotonic() + timeout
            while child.process.poll() is None and time.monotonic() < end:
                pump()
            if child.process.poll() is None:
                supervisor.stop(child, .5, 1., 1.)
                raise TimeoutError("bounded ROS CLI command: " + name)
            supervisor.stop(child, .1, .5, .5)
            text = (directory / (name + ".console.log")).read_text()
            if child.process.returncode != 0:
                raise RuntimeError("ROS command failed: " + name)
            return text

        # Let discovery run before spawning any process, retain the actual graph.
        discovery_end = time.monotonic() + 1.0
        while time.monotonic() < discovery_end:
            pump(); graph()
        forbidden_nodes = {"mpc_controller_node", "p1_regulator", "p1_solver_worker", "path_planner_node"}
        if any(n in forbidden_nodes for n, _ in node.get_node_names_and_namespaces()):
            raise RuntimeError("existing controller/planner in the isolated domain")
        graph(persist=True)
        for package in ("usv_bringup", "usv_simulation", "usv_planning_cpp", "usv_research_interfaces", "usv_research_safety_cpp"):
            actual = command("prefix_" + package, ["pkg", "prefix", package]).strip()
            if Path(actual).resolve() != (ws / "install" / package).resolve():
                raise RuntimeError("actual ROS package prefix outside declared overlay: " + package)
        # rosbag discovers publisher types. Announce nonphysical types without
        # data; only the actual owned controller may create physical endpoints.
        announced_topics = [t for t in topic_types if t not in c["output_topics"].values()]
        declaration_publishers = [node.create_publisher(get_message(topic_types[t]), t,
            capq if t == "/p1/worker_capability" else best if t in ("/clock", c["input_topics"]["odom"], c["input_topics"]["imu"]) else reliable)
            for t in announced_topics if t != "/p1/stop"]
        supervisor.event("nonphysical_topic_types_announced", topics=announced_topics,
                         data_published=False, physical_publisher_endpoints=0)
        recorder = supervisor.spawn("recorder", [str(python), str(ros2), "bag", "record", "--storage", "mcap",
            "--output", str(directory / "raw_bag"), "--qos-profile-overrides-path", str(qos_path), *topic_types],
            env, python, binaries["python"]["sha256"])
        wait(lambda: recorder.process.poll() is None and (directory / "raw_bag").is_dir()
             and all(any("recorder" in i.node_name for i in node.get_subscriptions_info_by_topic(t))
                     for t in announced_topics), 15, "recorder did not subscribe to all announced nonphysical topics")
        supervisor.event("recorder_nonphysical_ready", topics=announced_topics,
                         physical_topics_deferred_until_owned_controller=True)
        sim_command = [str(python), str(ros2), "launch", "usv_bringup", "vrx.launch.py",
            "scheme:=B", "control_enabled:=false", "record_bag:=false", "headless:=true", "visualize:=false", "paused:=false",
            "waypoints_file:=" + str(reference), "model_output_dir:=" + str(directory / "model"),
            "vehicle_config:=" + config["snapshot_paths"]["plant_input"],
            "simulation_config:=" + config["snapshot_paths"]["simulation_input"],
            "controller_vehicle:=" + config["snapshot_paths"]["nominal_effective"],
            "controller_tmax:=25.0", "controller_tmin:=-25.0"]
        vrx = supervisor.spawn("vrx", sim_command, env, python, binaries["python"]["sha256"])
        supervisor.event("vrx_owned_launch", command=sim_command,
            controller_enabled=False, planner_enabled=False, physics_assets="unchanged F5 plant input")
        wait(lambda: vrx.process.poll() is None and counts["/clock"] >= 3
             and counts[c["input_topics"]["odom"]] >= 3 and counts[c["input_topics"]["imu"]] >= 1,
             45, "real VRX sensor streams not ready")
        odom = latest["odom"]
        if odom.header.frame_id != c["expected_pose_frame"] or odom.child_frame_id != c["expected_child_frame"]:
            raise RuntimeError("actual VRX odom frame contract differs")
        if latest["imu"].header.frame_id != c["expected_imu_frame"]:
            raise RuntimeError("actual VRX IMU frame differs from its separate contract field")
        graph(persist=True)
        planner_path = Path(binaries["planner"]["path"])
        planner = supervisor.spawn("planner", [str(planner_path), "--ros-args", "-r", "__node:=path_planner_node",
            "--params-file", fixed["selected_immutable_installed_assets"]["path_config"]["path"],
            "-p", "use_sim_time:=true", "-p", "waypoints_file:=" + str(reference),
            "-p", "odom_topic:=" + c["input_topics"]["odom"], "-p", "path_topic:=" + c["input_topics"]["path"],
            "-p", "profile_topic:=" + c["input_topics"]["profile"],
            "-p", "dynamic_waypoints_topic:=/usv/mission/waypoints_local"], env,
            planner_path, binaries["planner"]["sha256"])
        wait(lambda: planner.process.poll() is None and counts[c["input_topics"]["path"]] >= 1
             and counts[c["input_topics"]["profile"]] >= 1, 20, "frozen planner path/profile not ready")
        if latest["path"].header.frame_id != c["expected_pose_frame"]:
            raise RuntimeError("actual frozen planner path pose frame differs")
        params_dumps["planner"] = command("parameters_planner", ["param", "dump", "/path_planner_node", "--no-daemon", "--spin-time", "3", "--timeout", "10"], 20)
        base = ["--ros-args", "-p", "run_id:=" + args.run_id, "-p", "contract_file:=" + str(args.contract.resolve()),
                "-p", "contract_hash:=" + contract_hash]
        if args.mode == "shadow":
            legacy = supervisor.spawn("legacy", [binaries["legacy"]["path"], "--ros-args", "-r",
                "__node:=mpc_controller_node", "--params-file", str(legacy_yaml)], env,
                Path(binaries["legacy"]["path"]), F5_NODE_SHA)
            def legacy_physical_identity_ready():
                if legacy.process.poll() is not None:
                    raise RuntimeError("owned legacy exited before physical identity discovery")
                ready = True
                for topic in c["output_topics"].values():
                    endpoints = node.get_publishers_info_by_topic(topic)
                    if len(endpoints) > 1:
                        raise RuntimeError("multiple physical publishers during owned legacy startup")
                    for info in endpoints:
                        if info.node_name not in (physical_owner, "_NODE_NAME_UNKNOWN_"):
                            raise RuntimeError("foreign physical publisher during owned legacy startup")
                        if info.topic_type != "std_msgs/msg/Float64":
                            raise RuntimeError("unexpected physical command type")
                    ready &= len(endpoints) == 1 and endpoints[0].node_name == physical_owner
                return ready
            wait(legacy_physical_identity_ready,
                 10, "F5 physical controller identity discovery not complete")
            graph(physical_owner, persist=True)
            params_dumps["legacy_prearm"] = command("parameters_legacy_prearm", ["param", "dump", "/mpc_controller_node", "--no-daemon", "--spin-time", "3", "--timeout", "10"], 20)
            parsed = yaml.safe_load(params_dumps["legacy_prearm"])
            actual = (parsed.get("/mpc_controller_node") or parsed.get("mpc_controller_node"))["ros__parameters"]
            if actual != legacy_params:
                raise RuntimeError("actual frozen F5 parameter dump differs from exact prepared parameters")
            wait(lambda: all(any(i.node_name == "mpc_controller_node" for i in node.get_publishers_info_by_topic(t))
                             and any("recorder" in i.node_name for i in node.get_subscriptions_info_by_topic(t))
                             for t in LEGACY_TYPES), c["recording_ready_timeout_ns"] / 1e9,
                 "legacy research writer/recorder graph not ready before source logging arm")
            supervisor.event("legacy_logging_arm_preflight",
                recorder_subscriptions_observed=True, writer_graph_observed=True,
                remote_DDS_writer_match_count_unavailable=True,
                whole_raw_prefix_completeness_proven=False)
            wait(lambda: all(any("recorder" in i.node_name for i in node.get_subscriptions_info_by_topic(t))
                             for t in c["output_topics"].values()),
                 10, "recorder physical subscriptions missing after owned legacy startup")
            supervisor.event("recorder_physical_ready", topics=list(c["output_topics"].values()),
                             whole_run_raw_prefix_complete=False)
            client = AsyncParameterClient(node, "/mpc_controller_node")
            wait(lambda: client.services_are_ready(), 10, "legacy parameter service unavailable")
            future = client.set_parameters([Parameter("research_logging_armed", Parameter.Type.BOOL, True)])
            wait(lambda: future.done(), 10, "legacy research log arm timed out")
            if future.exception() or not all(i.successful for i in future.result().results):
                raise RuntimeError("legacy research logging arm rejected")
            wait(lambda: latest["applied"] is not None, 10, "real legacy AppliedControl anchor missing")
            supervisor.event("legacy_f5_armed", run_id=legacy_run,
                producer_instance_id=latest["applied"].producer_instance_id, physical_owner=physical_owner,
                executable_sha256=F5_NODE_SHA, source_snapshot_sha256=F5_SOURCE_SHA)
        # Finish all shadow legacy readiness/arm work before the worker
        # starts its finite wait for the regulator candidate subscriber.
        # Execute skips the legacy branch and keeps worker -> regulator.
        worker = supervisor.spawn("worker", [binaries["worker"]["path"], *base,
            "-p", "source_file:=" + str(sources["worker"]), "-p", "test_delay_ms:=" + str(args.test_delay_ms),
            "-p", "test_native_block_ms:=" + str(args.test_native_block_ms)], env,
            Path(binaries["worker"]["path"]), binaries["worker"]["sha256"])
        wait(lambda: latest["capability"] is not None, 10, "worker startup capability missing")
        cap = latest["capability"]
        if (cap.pid != worker.process.pid or cap.backend != "acados" or cap.fatal or cap.clock_name != "CLOCK_MONOTONIC"
                or cap.horizon_steps != 20 or cap.prediction_dt != .2 or cap.nominal_hash != c["nominal_hash"]
                or cap.fault_injection_enabled != c["fault_injection_enabled"]):
            raise RuntimeError("actual worker capability differs from declared static contract")
        supervisor.event("worker_capability_verified", pid=cap.pid, worker_instance=cap.worker_instance,
                         backend=cap.backend, fault_injection_enabled=cap.fault_injection_enabled)
        regulator = supervisor.spawn("regulator", [binaries["regulator"]["path"], *base,
            "-p", "mode:=" + args.mode, "-p", "worker_pid:=" + str(worker.process.pid),
            "-p", "legacy_run_id:=" + (legacy_run if args.mode == "shadow" else ""),
            "-p", "recording_observer_node:=p1_vrx_validation_driver",
            "-p", "source_file:=" + str(sources["regulator"])], env,
            Path(binaries["regulator"]["path"]), binaries["regulator"]["sha256"])
        wait(lambda: regulator.process.poll() is None and observations["decision_count"] >= 1
             and all(node.count_publishers(t) >= 1 for t in c["output_topics"].values()),
             c["recording_ready_timeout_ns"] / 1e9 + 5.,
             "regulator initial decisions/output graph not ready")
        graph(physical_owner, persist=True)
        for name in ("worker", "regulator"):
            params_dumps[name] = command("parameters_" + name, ["param", "dump", "/p1_solver_worker" if name == "worker" else "/p1_regulator", "--no-daemon", "--spin-time", "3", "--timeout", "10"], 20)
        for name, key in (("worker", "/p1_solver_worker"), ("regulator", "/p1_regulator")):
            parsed = yaml.safe_load(params_dumps[name])
            p = (parsed.get(key) or parsed.get(key[1:]))["ros__parameters"]
            if p["run_id"] != args.run_id or p["contract_hash"] != contract_hash or Path(p["contract_file"]).resolve() != args.contract.resolve():
                raise RuntimeError("native actual parameter identity mismatch: " + name)
            if name == "regulator" and (p["mode"] != args.mode or p["worker_pid"] != worker.process.pid):
                raise RuntimeError("regulator actual mode/worker PID mismatch")
            if name == "regulator" and p["recording_observer_node"] != "p1_vrx_validation_driver":
                raise RuntimeError("regulator actual recording observer node mismatch")
        exclusive_json(directory / "actual_parameter_dumps.json", {
            k: {"stdout": v, "stdout_sha256": hashlib.sha256(v.encode()).hexdigest()} for k, v in params_dumps.items()})
        started = time.monotonic_ns()
        cpu_seed = {}
        for name in ("worker", "regulator", "legacy", "planner"):
            child = supervisor.owned.get(name)
            if child:
                fields = (Path("/proc") / str(child.process.pid) / "stat").read_text().split()
                cpu_seed[name] = (int(fields[13]) + int(fields[14]), time.monotonic_ns(), child.identity["start_ticks"])
        supervisor.event("validation_window_start", requested_duration_s=args.duration,
                         mode=args.mode, expected_fault=fault, physical_owner_node=physical_owner)
        end = started + int(args.duration * 1e9)
        next_graph = started
        stop_reason = "declared_duration_elapsed"
        while time.monotonic_ns() < end:
            pump()
            now = time.monotonic_ns()
            if now >= next_graph:
                graph(physical_owner, persist=True)
                next_graph = now + 1_000_000_000
            for name in ("worker", "regulator", "recorder", "planner", "vrx", "legacy"):
                child = supervisor.owned.get(name)
                if child and child.process.poll() is not None:
                    raise RuntimeError("owned process exited during validation: " + name)
            cap = latest["capability"]
            if cap is not None and cap.fatal:
                stop_reason = "worker_fatal"
                if fault == "none":
                    raise RuntimeError("unexpected worker fatal status")
                break
            if latest["active_since"] is not None and now - latest["active_since"] > c["active_watchdog_ns"]:
                observations["watchdog_seen"] = True
                stop_reason = "owned_worker_active_watchdog"
                if fault == "none":
                    raise RuntimeError("unexpected native-owned worker watchdog")
                break
        ended = time.monotonic_ns()
        for name, (ticks, begin, identity) in cpu_seed.items():
            child = supervisor.owned[name]
            actual = proc_identity(child.process.pid, hash_exe=False)
            if actual is None or actual["start_ticks"] != identity:
                cpu[name] = {"available": False, "reason": "process no longer has sampled identity"}
            else:
                fields = (Path("/proc") / str(child.process.pid) / "stat").read_text().split()
                sample_end = time.monotonic_ns()
                cpu_seconds = (int(fields[13]) + int(fields[14]) - ticks) / os.sysconf("SC_CLK_TCK")
                wall = (sample_end - begin) / 1e9
                cpu[name] = {"available": True, "cpu_seconds": cpu_seconds, "sample_wall_s": wall,
                             "one_core_percent": 100 * cpu_seconds / wall, "start_ticks": identity}
        supervisor.event("validation_window_end", reason=stop_reason, mode=args.mode,
                         duration_ns=ended - started, observations=observations)
        if fault == "none" and (counts["/p1/solve_job"] == 0 or counts["/p1/solve_candidate"] == 0):
            raise RuntimeError("baseline never exercised actual job/candidate chain; retained as failed")
        stop_end = time.monotonic() + c["shutdown_grace_ns"] / 1e9
        while regulator.process.poll() is None and time.monotonic() < stop_end:
            message = Bool(); message.data = True; stop_pub.publish(message)
            rclpy.spin_once(node, timeout_sec=.02); tree.capture()
        supervisor.event("logical_stop_requested", regulator_exit=regulator.process.poll(),
                         shutdown_grace_ns=c["shutdown_grace_ns"])
    except BaseException as error:
        failure = repr(error)
        stop_reason = "startup_or_runtime_exception"
        supervisor.event("run_exception", error=failure)
    finally:
        # Physical F5 stays alive through shadow regulator shutdown; sensors and
        # recorder stay alive through all source/output shutdown tail.
        for name in ("regulator", "worker", "legacy", "planner", "vrx", "recorder"):
            child = supervisor.owned.get(name)
            if child is None:
                continue
            try:
                tree.capture()
            except BaseException as error:
                supervisor.cleanup_failed = True
                supervisor.event("owned_tree_capture_failed", error=repr(error))
            if name == "recorder":
                # Gazebo may create a separate process group. Stop only its
                # observed descendants before closing the recorder, preserving
                # the recorder root and any of its own observed descendants.
                try:
                    cleanup["separate_descendants_pre_recorder"] = tree.stop_separate_descendants(
                        c["worker_grace_ns"] / 1e9, c["term_grace_ns"] / 1e9,
                        c["kill_postcheck_ns"] / 1e9, preserve_roots=("recorder",))
                except BaseException as error:
                    supervisor.cleanup_failed = True
                    cleanup["separate_descendants_pre_recorder"] = {"cleanup_complete": False, "error": repr(error)}
                time.sleep(.25)
            try:
                cleanup[name] = supervisor.stop(child, c["worker_grace_ns"] / 1e9,
                    c["term_grace_ns"] / 1e9, c["kill_postcheck_ns"] / 1e9)
            except BaseException as error:
                # One failed identity/group check must not skip cleanup of
                # other independently owned children. No signal is guessed.
                supervisor.cleanup_failed = True
                cleanup[name] = {"cleanup_complete": False, "error": repr(error)}
                supervisor.event("owned_child_cleanup_exception", name=name, error=repr(error))
        try:
            cleanup["separate_descendants"] = tree.stop_separate_descendants(
                c["worker_grace_ns"] / 1e9, c["term_grace_ns"] / 1e9, c["kill_postcheck_ns"] / 1e9)
        except BaseException as error:
            supervisor.cleanup_failed = True
            cleanup["separate_descendants"] = {"cleanup_complete": False, "error": repr(error)}
        if node is not None:
            try:
                final_graph = {k: node.count_publishers(t) for k, t in c["output_topics"].items()}
                graph_events.append({"monotonic_ns": time.monotonic_ns(), "postcleanup_physical_counts": final_graph})
                node.destroy_node()
            except BaseException as error:
                failure = (failure + "; " if failure else "") + "driver graph/node shutdown failed: " + repr(error)
        if rclpy is not None:
            try:
                if rclpy.ok():
                    rclpy.shutdown()
            except BaseException as error:
                failure = (failure + "; " if failure else "") + "ROS driver shutdown failed: " + repr(error)
        for name, p in sources.items():
            try:
                summaries[name] = source_observation(p)
            except OSError as error:
                summaries[name] = {"read_error": repr(error), "completeness_proven": False}
        legacy_summary = directory / "legacy_source/session_summary.json"
        if legacy_summary.is_file():
            try:
                summaries["legacy"] = {"sha256": sha256_file(legacy_summary), "summary": json.loads(legacy_summary.read_text())}
            except BaseException as error:
                summaries["legacy"] = {"read_error": repr(error), "completeness_proven": False}
                failure = (failure + "; " if failure else "") + "legacy terminal summary unreadable: " + repr(error)
        try:
            changed = [p for p, digest in current_assets.items() if not Path(p).is_file() or sha256_file(Path(p)) != digest]
            for frozen in fixed["selected_immutable_installed_assets"].values():
                expect_sha(Path(frozen["path"]), frozen["sha256"])
            expect_sha(Path(fixed["source_snapshot"]), F5_SOURCE_SHA)
            for p, digest in fixed["fixed_input_sha256"].items():
                expect_sha(Path(p), digest)
            expect_sha(args.contract, contract_hash)
            if changed:
                failure = (failure + "; " if failure else "") + "source/install asset changed during run: " + str(changed)
            exclusive_json(directory / "asset_after_gate.json", {"changed": changed,
                "current_assets_verified": not changed, "frozen_F5_binary_verified": True,
                "selected_F5_assets_verified": True, "fixed_F5_mathematical_inputs_verified": True,
                "contract_sha256_verified": True})
        except BaseException as error:
            failure = (failure + "; " if failure else "") + "after-asset gate failed: " + repr(error)
        exclusive_json(directory / "topic_graph_observations.json", {"schema": "p1-vrx-graph-observations-v1", "observations": graph_events})
        supervisor.close()
        if supervisor.evidence_failed:
            failure = (failure + "; " if failure else "") + "supervision ledger write/close failure"
        summary = {"schema": "p1-vrx-validation-runner-summary-v1", "run_id": args.run_id, "mode": args.mode,
            "calibration_status": "cleanup_failed" if supervisor.cleanup_failed else "failed" if failure else "runtime_data_collected_pending_checker",
            "failure": failure, "stop_reason": stop_reason, "expected_fault": fault,
            "cleanup_complete": not supervisor.cleanup_failed, "cleanup_failed": supervisor.cleanup_failed, "cleanup": cleanup,
            "supervision_evidence_complete": not supervisor.evidence_failed,
            "supervision_memory_tail": supervisor.memory_tail if supervisor.evidence_failed else [],
            "graph_no_physical_publishers": False if physical_verified else None,
            "graph_new_physical_publishers_zero": physical_verified if args.mode == "shadow" else False,
            "graph_sole_physical_owner_verified": physical_verified, "graph_physical_owner_node": physical_owner,
            "graph_physical_publishers_per_channel": owner_counts, "observations": observations,
            "driver_receive_counts": dict(counts), "sources": summaries, "cpu": cpu,
            "bag_exists": (directory / "raw_bag").is_dir(), "bag_metadata_exists": (directory / "raw_bag/metadata.yaml").is_file(),
            "normal_contract_complete": False, "source_completeness_proven": False,
            "raw_input_recording_complete": None,
            "raw_input_recording_scope": "unknown whole-run real VRX raw prefix/suffix; no publisher-side raw counters",
            "legacy_source_bag_contract_complete": None,
            "execute_qualified": c["execute_qualified"], "plant_acceptance_observed": False,
            "force_measured": False, "execution_atomicity_proven": False, "gp_labels_ready": False,
            "preexisting_environment_unreadable": list(tree.preexisting_unreadable.values()),
            "global_environment_scope_audit_complete": not tree.preexisting_unreadable,
            "finished_ns": time.monotonic_ns()}
        exclusive_json(directory / "runner_summary.json", summary)
    print(json.dumps({"run_id": args.run_id, "directory": str(directory),
                      "status": summary["calibration_status"], "cleanup_failed": supervisor.cleanup_failed}))
    return 2 if supervisor.cleanup_failed else 1 if failure else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("shadow", "execute"), required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-hash", required=True)
    parser.add_argument("--expected-assets", type=Path, required=True)
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path("/home/trevor/USV/usv_mpc_ws"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--ros-domain", type=int, default=97)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--regulator-sha256", required=True)
    parser.add_argument("--test-delay-ms", type=int, choices=(0, 50, 150, 250, 400), default=0)
    parser.add_argument("--test-native-block-ms", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.ros_domain <= 232 or not 0 <= args.test_native_block_ms <= 60000:
        parser.error("ROS domain or controlled pre-native barrier outside finite bounds")
    try:
        return run(args)
    except BaseException as error:
        # Preserve partial assets from a fresh directory even if the initial
        # hash/configuration preflight failed before supervision existed.
        # Never write into a reused directory rejected by mkdir(exist_ok=False).
        created = getattr(args, "_created_directory", None)
        failure = {"run_id": args.run_id, "mode": args.mode, "status": "failed",
                   "error": repr(error), "directory": str(created) if created else None,
                   "supervisor_created": getattr(args, "_supervisor_created", False),
                   "normal_contract_complete": False}
        if created is not None:
            try:
                exclusive_json(created / "runner_outer_failure.json", failure)
            except OSError as write_error:
                failure["failure_report_write_error"] = repr(write_error)
        print(json.dumps(failure), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
