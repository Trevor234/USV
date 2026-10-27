"""Create-only future C0 normal no_output runner for the dedicated B1 diagnostic.

Run on the authorized Linux ROS host after the build has passed. The invoking
shell must source Jazzy and this workspace's install/setup.bash first.
This entry implements only normal collection with the pause hook set to zero.
It never declares R5 overflow-mechanism success or grants physical execution.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import sys
import time

from owned_process_supervisor import Supervisor, proc_table, sha256_file, boot_id


REQUESTED_STOP = False


def stop_signal(_signum, _frame):
    global REQUESTED_STOP
    REQUESTED_STOP = True


def exclusive_json(path: Path, data: dict, compact: bool = False) -> None:
    with path.open("x") as stream:
        json.dump(data, stream, indent=None if compact else 2, sort_keys=True)
        stream.write("\n")


def load_contract(path: Path, expected: str | None = None) -> tuple[dict, str]:
    from p1_full_contract import ContractError, load_contract as full_load
    c, actual = full_load(path, expected, mode="no_output", runtime=True)
    if (c["schema"] != "p1-execution-contract-v2"
            or c.get("diagnostic_contract_revision") != 5):
        raise ContractError("dedicated B1 diagnostic runner requires complete diag5 contract")
    return c, actual


def validate_normal_parameters(args) -> None:
    """Reject fault and path ambiguity before any create-only run directory."""
    if any(getattr(args, name, 0) for name in (
            "test_delay_ms", "test_native_block_ms", "test_prepare_block_ms",
            "test_tick_block_ms", "test_sink_pause_ms")):
        raise ValueError("C0 normal runner keeps every fault/pause hook off; R5 gate is not implemented")
    if type(args.witness_enabled) is not bool:
        raise ValueError("witness_enabled must be a boolean")
    if args.witness_enabled and args.witness_file is None:
        raise ValueError("enabled witness requires explicit owned witness-file")
    if not args.witness_enabled and args.witness_file is not None:
        raise ValueError("disabled witness cannot have an output path")
    if args.diagnostic_bin is None or args.diagnostic_source is None:
        raise ValueError("explicit diagnostic-bin and diagnostic-source are required")


def owned_witness_path(args, directory: Path) -> Path | None:
    if not args.witness_enabled:
        return None
    value = args.witness_file
    path = (value if value.is_absolute() else directory / value).resolve()
    reserved = {"run_context.json", "runner_summary.json", "host_preflight.json",
                "worker_source.jsonl", "regulator_source.jsonl", "fixture_source.jsonl",
                "fixture_armed.json", "window_start.json", "witness_expected_header.json",
                "witness_check.json", "owned_process_ledger.jsonl", "raw_bag",
                "normal_source_check", "postrun_checks.json",
                "regulator.console.log", "worker.console.log", "fixture.console.log",
                "recorder.console.log"}
    if (path.parent != directory.resolve() or path.name in reserved or path.exists()
            or len(path.name.encode("utf-8")) > 128
            or any(ord(c) < 32 or ord(c) == 127 for c in path.name)):
        raise ValueError("witness-file must be fresh and directly inside the owned run directory")
    return path


def verify_worker_capability(cap, pid: int, args, contract: dict, contract_hash: str,
                             expected_boot: str) -> str:
    if (cap.schema_version != "p1-worker-capability-v1" or cap.run_id != args.run_id
            or cap.contract_hash != contract_hash or cap.boot_id != expected_boot
            or type(cap.pid) is not int or cap.pid != pid or pid <= 0
            or cap.backend != "acados" or cap.fatal
            or cap.clock_name != "CLOCK_MONOTONIC" or cap.horizon_steps != 20
            or cap.prediction_dt != .2 or cap.nominal_hash != contract["nominal_hash"]
            or cap.fault_injection_enabled != contract["fault_injection_enabled"]
            or type(cap.worker_instance) is not str
            or re.fullmatch(r"[0-9a-f]{64}", cap.worker_instance) is None):
        raise RuntimeError("owned worker capability startup mismatch")
    return cap.worker_instance


def independent_witness_header(args, context, binaries, source_hash, instance):
    return {"run_id": args.run_id, "boot_id": context["boot_id"],
            "contract_sha256": context["contract_sha256"], "source_sha256": source_hash,
            "binary_sha256": binaries["regulator"]["sha256"],
            "worker_binary_sha256": binaries["worker"]["sha256"], "worker_instance": instance}


def diagnostic_regulator_command(args, base, pid, source_paths, binaries,
                                 diagnostic_source, diagnostic_source_hash,
                                 witness_path, worker_instance):
    command = [binaries["regulator"]["path"], *base, "-p", "mode:=no_output",
               "-p", "worker_pid:=" + str(pid), "-p", "source_file:=" + str(source_paths["regulator"]),
               "-p", "test_prepare_block_ms:=0", "-p", "test_tick_block_ms:=0",
               "-p", "test_sink_pause_ms:=0", "-p", "witness_enabled:=" +
               ("true" if args.witness_enabled else "false")]
    if args.witness_enabled:
        command += ["-p", "witness_file:=" + str(witness_path),
                    "-p", "diagnostic_source_file:=" + str(diagnostic_source),
                    "-p", "diagnostic_source_sha256:=" + diagnostic_source_hash,
                    "-p", "diagnostic_binary_sha256:=" + binaries["regulator"]["sha256"],
                    "-p", "worker_binary_sha256:=" + binaries["worker"]["sha256"],
                    "-p", "witness_worker_instance:=" + worker_instance]
    return command


def terminal_witness_check(args, directory, witness_path, expected_header):
    """Independent audit only; normal source/bag validation stays a separate gate."""
    if not args.witness_enabled:
        return {"requested": False, "passed": None, "witness_complete": False,
                "witness_output_requested": False, "expected_log_overflow_mechanism_passed": False,
                "normal_contract_complete": False, "execute_qualified": False}
    try:
        from check_p1_witness import analyze, load_json
        expected_path = directory / "witness_expected_header.json"
        stored_expected, expected_digest = load_json(expected_path)
        if stored_expected != expected_header:
            raise ValueError("independently stored expected header changed")
        value, digest = load_json(witness_path)
        report = analyze(value, expected_header)
        report["evidence_sha256"] = {str(witness_path): digest,
                                     str(expected_path): expected_digest}
        if sha256_file(witness_path) != digest or sha256_file(expected_path) != expected_digest:
            raise ValueError("independent witness inputs changed during validation")
        report["checker_sha256"] = sha256_file(Path(__file__).with_name("check_p1_witness.py"))
        report["requested"] = True
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        report = {"schema": "p1-fixed-witness-check-v1", "requested": True,
                  "passed": False, "witness_complete": False,
                  "issues": [{"code": "terminal_witness_unreadable", "detail": str(error)}],
                  "source_join_verified": False, "expected_log_overflow_mechanism_passed": False,
                  "normal_contract_complete": False, "execute_qualified": False}
    try:
        exclusive_json(directory / "witness_check.json", report)
        report["report_write_succeeded"] = True
    except OSError as error:
        report["passed"] = report["witness_complete"] = False
        report["report_write_succeeded"] = False
        report["report_write_error"] = str(error)
    return report


def normal_source_check(args, directory):
    """Invoke the existing strict normal source/typed bag checker unchanged."""
    output = directory / "normal_source_check"
    try:
        import check_p1_execution
        code = check_p1_execution.main([
            "--experiment", str(directory), "--bag", str(directory / "raw_bag"),
            "--contract", str(args.contract.resolve()),
            "--context", str(directory / "run_context.json"), "--output", str(output)])
        report_path = output / "contract_report.json"
        result = json.loads(report_path.read_text())
        return {"passed": code == 0 and result.get("passed") is True,
                "checker_returncode": code, "output_relative_path": output.name,
                "contract_report_sha256": sha256_file(report_path),
                "source_bag_contract_complete": result.get("source_bag_contract_complete", False),
                "diagnostic_complete": result.get("diagnostic_complete", False),
                "normal_contract_complete": False, "execute_qualified": False,
                "expected_log_overflow_mechanism_passed": False}
    except Exception as error:
        return {"passed": False, "output_relative_path": output.name,
                "error": repr(error), "normal_contract_complete": False,
                "execute_qualified": False, "expected_log_overflow_mechanism_passed": False}


def host_preflight() -> dict:
    if sys.platform != "linux":
        raise RuntimeError("this runner requires the Linux ROS host")
    forbidden = {"mpc_node", "p1_regulator", "p1_regulator_r5_diag", "p1_solver_worker", "rl_policy_node",
                 "rl_policy_node.py", "gzserver", "gzclient", "gazebo"}
    found = []
    unreadable = []
    for item in proc_table():
        if item["pid"] == os.getpid() or item["state"] == "Z":
            continue
        try:
            raw = (Path("/proc") / str(item["pid"]) / "cmdline").read_bytes()
            args = [v.decode(errors="replace") for v in raw.split(b"\0") if v]
        except FileNotFoundError:
            continue
        except PermissionError:
            unreadable.append(item["pid"])
            continue
        names = {Path(arg).name for arg in args[:3]}
        is_gz_sim = "gz" in names and "sim" in args[:5]
        prior_fixture = (bool(names & {"run_no_output_calibration.py", "run_formal_no_output_validation.py",
                                     "run_r5_diag_validation.py"})
                         and "--fixture-child" in args)
        if names & forbidden or is_gz_sim or prior_fixture:
            found.append({"pid": item["pid"], "exe": item["exe"],
                          "start_ticks": item["start_ticks"]})
    if found:
        raise RuntimeError("existing controller/Gazebo/fixture prevents startup: "
                           + json.dumps(found, sort_keys=True))
    if unreadable:
        raise RuntimeError("process preflight incomplete; unreadable cmdline PIDs: "
                           + str(unreadable))
    return {"boot_id": boot_id(), "monotonic_ns": time.monotonic_ns(),
            "existing_controller_gazebo_count": 0, "unreadable_cmdline_count": 0}


def fixture_child(args) -> int:
    c, digest = load_contract(args.contract, args.contract_hash)
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rosgraph_msgs.msg import Clock
    from nav_msgs.msg import Odometry, Path as RosPath
    from sensor_msgs.msg import Imu
    from std_msgs.msg import Float64MultiArray, MultiArrayDimension
    from geometry_msgs.msg import PoseStamped
    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)
    node = rclpy.create_node("p1_synthetic_input_fixture")
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
    topics = c["input_topics"]
    publishers = {"clock": node.create_publisher(Clock, "/clock", qos),
                  "odom": node.create_publisher(Odometry, topics["odom"], qos),
                  "imu": node.create_publisher(Imu, topics["imu"], qos),
                  "path": node.create_publisher(RosPath, topics["path"], qos),
                  "profile": node.create_publisher(Float64MultiArray, topics["profile"], qos)}
    # Arm only after this fixture's actual DDS writers have matched both
    # recorder and regulator; type declarations alone do not prove that match.
    arm_deadline = time.monotonic() + 10.
    while True:
        rclpy.spin_once(node, timeout_sec=.02)
        matched = all(pub.get_subscription_count() >= 2 for pub in publishers.values())
        observed = all(any("recorder" in info.node_name
                           for info in node.get_subscriptions_info_by_topic(
                               "/clock" if name == "clock" else topics[name]))
                       and any(info.node_name == "p1_regulator"
                           for info in node.get_subscriptions_info_by_topic(
                               "/clock" if name == "clock" else topics[name]))
                       for name in publishers)
        if matched and observed:
            break
        if REQUESTED_STOP or time.monotonic() >= arm_deadline:
            node.destroy_node()
            rclpy.shutdown()
            raise RuntimeError("fixture actual DDS writers did not arm before first data")
    path = RosPath()
    path.header.frame_id = c["expected_pose_frame"]
    path.header.stamp.sec = 1
    profile = Float64MultiArray()
    for label in ("stamp_sec:1", "stamp_nanosec:0"):
        dim = MultiArrayDimension()
        dim.label = label
        profile.layout.dim.append(dim)
    for i in range(20):
        pose = PoseStamped()
        pose.header = path.header
        pose.pose.position.x = i * .5
        pose.pose.orientation.w = 1.
        path.poses.append(pose)
        profile.data.extend([.6, 0., 0., i * .5 / .6])
    counts = Counter()
    started = time.monotonic_ns()
    arm_path = args.fixture_source.with_name("fixture_armed.json")
    exclusive_json(arm_path, {
        "schema": "p1-synthetic-fixture-arm-v1", "pid": os.getpid(),
        "boot_id": boot_id(), "contract_sha256": digest, "armed_ns": started,
        "actual_dds_writers_matched": True,
        "required_subscribers": ["recorder", "p1_regulator"],
        "publisher_match_counts": {name: pub.get_subscription_count()
                                   for name, pub in publishers.items()},
        "physical_endpoints": 0})
    next_tick = started
    next_reference = started
    error = None
    try:
        while not REQUESTED_STOP:
            now = time.monotonic_ns()
            if now < next_tick:
                time.sleep(min(.005, (next_tick - now) / 1e9))
                continue
            if now - next_tick > 20_000_000:
                counts["skipped_input_slots"] += (now - next_tick) // 20_000_000
            next_tick = now + 20_000_000
            sim = 1_000_000_000 + now - started  # Explicit synthetic RTF=1.
            clock = Clock()
            clock.clock.sec, clock.clock.nanosec = divmod(sim, 1_000_000_000)
            odom = Odometry()
            odom.header.frame_id = c["expected_pose_frame"]
            odom.child_frame_id = c["expected_child_frame"]
            odom.header.stamp = clock.clock
            odom.pose.pose.orientation.w = 1.
            imu = Imu()
            imu.header.stamp = clock.clock
            imu.header.frame_id = c.get("expected_imu_frame", c["expected_child_frame"])
            imu.angular_velocity.z = 0.
            for name, message in (("clock", clock), ("odom", odom), ("imu", imu)):
                publishers[name].publish(message)
                counts[name] += 1
            if now >= next_reference:
                publishers["path"].publish(path)
                publishers["profile"].publish(profile)
                counts["path"] += 1
                counts["profile"] += 1
                next_reference = now + 1_000_000_000
            rclpy.spin_once(node, timeout_sec=0)
    except BaseException as exc:
        error = repr(exc)
    finally:
        exclusive_json(args.fixture_source, {
            "type": "fixture_summary", "schema": "p1-synthetic-fixture-v1",
            "contract_sha256": digest, "pid": os.getpid(), "boot_id": boot_id(),
            "started_ns": started, "finished_ns": time.monotonic_ns(),
            "fixture_armed_relative_path": arm_path.name,
            "fixture_armed_sha256": sha256_file(arm_path),
            "counts": dict(counts), "error": error, "physical_endpoints": 0,
            "sim_semantics": "one-second origin + CLOCK_MONOTONIC elapsed; RTF1",
            "zero_state_static": True, "actual_plant": False,
            "publisher_side_counts_only": True}, compact=True)
        node.destroy_node()
        rclpy.shutdown()
    return 1 if error else 0


def source_observation(path: Path) -> dict:
    observation = {"path": path.name, "exists": path.exists(), "types": {},
                   "parse_errors": [], "summaries": [], "completeness_proven": False}
    if not path.exists():
        return observation
    counts = Counter()
    with path.open(errors="replace") as stream:
        for number, line in enumerate(stream, 1):
            try:
                item = json.loads(line)
                counts[item.get("type", "unknown")] += 1
                if item.get("type") in {"source_summary", "worker_summary", "fixture_summary"}:
                    observation["summaries"].append(item)
            except (json.JSONDecodeError, AttributeError) as error:
                observation["parse_errors"].append({"line": number, "error": str(error)})
    observation["types"] = dict(counts)
    observation["sha256"] = sha256_file(path)
    return observation



def watchdog_observation(active_since, now, decision_reason, decision_ns, watchdog_ns, grace_ns, pending_since=None):
    """External expiry and regulator observation have distinct linearization points."""
    if active_since is None or now-active_since<=watchdog_ns:
        return "idle",None
    pending_since=now if pending_since is None else pending_since
    if now-pending_since>grace_ns:
        return "timeout",pending_since
    if decision_reason=="worker_unusable" and active_since+watchdog_ns<=decision_ns<=now:
        return "confirmed",pending_since
    return "pending",pending_since

def run(args) -> int:
    validate_normal_parameters(args)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,119}", args.run_id):
        raise ValueError("invalid explicit run_id")
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 10:
        raise ValueError("C0 normal duration must be finite in [1,10] seconds")
    c, contract_hash = load_contract(args.contract, args.contract_hash)
    if (args.test_delay_ms or args.test_native_block_ms or args.test_prepare_block_ms or args.test_tick_block_ms) and not c["fault_injection_enabled"]:
        raise RuntimeError("fault injection disabled by contract")
    clock_info = time.get_clock_info("monotonic")
    if ("CLOCK_MONOTONIC" not in clock_info.implementation
            or not clock_info.monotonic or clock_info.adjustable):
        raise RuntimeError("Python monotonic implementation is not the declared native clock")
    directory = args.experiment_root.resolve() / args.run_id
    witness_path = owned_witness_path(args, directory)
    source_paths = {name: directory / (name + "_source.jsonl")
                    for name in ("worker", "regulator", "fixture")}
    # The fixture has one JSON summary, despite the common source filename suffix.
    worker = (args.workspace / "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_solver_worker").resolve(strict=True)
    regulator = args.diagnostic_bin.resolve(strict=True)
    diagnostic_source = args.diagnostic_source.resolve(strict=True)
    if (not regulator.is_file() or regulator.name != "p1_regulator_r5_diag"
            or not diagnostic_source.is_file() or diagnostic_source.name != "regulator_r5_diag.cpp"):
        raise RuntimeError("explicit dedicated diagnostic executable/source identity required")
    diagnostic_source_hash = sha256_file(diagnostic_source)
    if (args.diagnostic_source_sha256 is not None
            and args.diagnostic_source_sha256 != diagnostic_source_hash):
        raise RuntimeError("predeclared diagnostic source hash mismatch")
    python = Path(sys.executable).resolve(strict=True)
    ros2 = Path(shutil.which("ros2") or "").resolve(strict=True)
    if not ros2.is_file() or ros2.name != "ros2":
        raise RuntimeError("source ROS Jazzy and workspace setup before invoking runner")
    binaries = {"worker": {"path": str(worker), "sha256": sha256_file(worker)},
                "regulator": {"path": str(regulator), "sha256": sha256_file(regulator)},
                "python": {"path": str(python), "sha256": sha256_file(python)},
                "ros2_cli": {"path": str(ros2), "sha256": sha256_file(ros2)}}
    for name, expected in (("worker", args.worker_sha256), ("regulator", args.regulator_sha256)):
        if expected and expected.lower() != binaries[name]["sha256"]:
            raise RuntimeError("predeclared executable hash mismatch: " + name)
    directory.mkdir(parents=False, exist_ok=False)
    env = dict(os.environ, ROS_DOMAIN_ID="96", ROS_LOCALHOST_ONLY="1")
    topics = {"inputs": {**c["input_topics"], "clock": "/clock"},
              "p1": {"job": "/p1/solve_job", "candidate": "/p1/solve_candidate",
                     "capability": "/p1/worker_capability", "decision": "/p1/execution_decision",
                     "stop": "/p1/stop"}}
    expected_fault = ("diagnostic_tick_stall" if args.test_tick_block_ms
                      else "diagnostic_preparation_wait" if args.test_prepare_block_ms
                      else "controlled_pre_native_barrier_watchdog" if args.test_native_block_ms
                      else "post_native_result_delay" if args.test_delay_ms else "none")
    context = {"schema": "p1-no-output-calibration-context-v1", "run_id": args.run_id,
               "mode": "no_output", "boot_id": boot_id(), "contract_file": str(args.contract.resolve()),
               "contract_sha256": contract_hash, "source_files": {k: v.name for k, v in source_paths.items()},
               "python_monotonic_clock": {"implementation": clock_info.implementation,
                   "resolution_s": clock_info.resolution, "monotonic": clock_info.monotonic,
                   "adjustable": clock_info.adjustable, "domain": "CLOCK_MONOTONIC"},
               "bag_relative_path": "raw_bag", "topics": topics,
               "fixture_armed_relative_path": "fixture_armed.json",
               "window_start_relative_path": "window_start.json",
               "binaries": binaries, "runner_sha256": sha256_file(Path(__file__)),
               "diagnostic_source": {"path": str(diagnostic_source), "sha256": diagnostic_source_hash},
               "fixed_witness": {"enabled": args.witness_enabled,
                   "file_relative_path": witness_path.name if witness_path is not None else None,
                   "expected_header_relative_path": "witness_expected_header.json",
                   "checker_relative_path": "witness_check.json" if args.witness_enabled else None,
                   "expected_header_origin": "driver-owned capability and independently read assets",
                   "test_sink_pause_ms": 0, "R5_mechanism_gate_implemented": False},
               "supervisor_sha256": sha256_file(Path(__file__).with_name("owned_process_supervisor.py")),
               "ros_environment": {"ROS_DOMAIN_ID": "96", "ROS_LOCALHOST_ONLY": "1"},
               "declaration": {"duration_s": args.duration, "test_delay_ms": args.test_delay_ms,
                               "test_native_block_ms": args.test_native_block_ms,
                               "test_prepare_block_ms": args.test_prepare_block_ms,
                               "test_tick_block_ms": args.test_tick_block_ms,
                               "expected_fault": expected_fault, "execute_qualified": False},
               "normal_contract_complete": False, "plant_acceptance_observed": False,
               "created_ns": time.monotonic_ns()}
    exclusive_json(directory / "run_context.json", context)
    supervisor = Supervisor(directory)
    node = None
    rclpy = None
    cleanup = {}
    failure = None
    stop_reason = "not_started"
    no_endpoints = None
    observations = {"capability_count": 0, "decision_count": 0,
                    "job_count": 0, "candidate_count": 0, "watchdog_seen": False}
    window_start = None
    expected_header = None
    business = {"capability": None, "decision": None,
                "jobs": deque(maxlen=64), "candidates": deque(maxlen=64)}
    latest = {"capability": None, "active_since": None, "active_job": 0, "owned_identity": None, "watchdog_pending": None}
    try:
        preflight = host_preflight()
        exclusive_json(directory / "host_preflight.json", preflight)
        # Domain isolation applies to the driver as well as each owned child.
        os.environ.update(ROS_DOMAIN_ID="96", ROS_LOCALHOST_ONLY="1")
        import rclpy
        from rclpy.signals import SignalHandlerOptions
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from std_msgs.msg import Bool, Float64MultiArray
        from rosgraph_msgs.msg import Clock
        from nav_msgs.msg import Odometry, Path as RosPath
        from sensor_msgs.msg import Imu
        from usv_research_interfaces.msg import WorkerCapability, ExecutionDecision, SolveJob, SolveCandidate
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        signal.signal(signal.SIGINT, stop_signal)
        signal.signal(signal.SIGTERM, stop_signal)
        node = rclpy.create_node("p1_calibration_driver")
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        stop_pub = node.create_publisher(Bool, "/p1/stop", qos)

        def capability(message):
            if (message.run_id != args.run_id or message.contract_hash != contract_hash
                    or message.boot_id != context["boot_id"]):
                return
            identity = latest["owned_identity"]
            if identity is not None and (message.pid, message.worker_instance) != identity:
                return
            observations["capability_count"] += 1
            latest["capability"] = message
            if message.active_job != latest["active_job"]:
                latest["active_since"] = time.monotonic_ns() if message.active_job else None
                latest["active_job"] = message.active_job
            if (message.schema_version == "p1-worker-capability-v1"
                    and message.backend == "acados" and not message.fatal
                    and message.clock_name == "CLOCK_MONOTONIC"
                    and message.horizon_steps == 20 and message.prediction_dt == .2
                    and message.nominal_hash == c["nominal_hash"]
                    and message.fault_injection_enabled == c["fault_injection_enabled"]):
                business["capability"] = {"received_ns": time.monotonic_ns(),
                    "pid": message.pid, "worker_instance": message.worker_instance,
                    "active_job": message.active_job}

        def matching_job(message):
            identity = latest["owned_identity"]
            return (identity is not None and message.run_id == args.run_id
                    and message.boot_id == context["boot_id"]
                    and message.contract_hash == contract_hash
                    and message.nominal_hash == c["nominal_hash"]
                    and message.worker_instance == identity[1]
                    and message.schema_version == "p1-solve-job-v1"
                    and message.horizon_steps == 20 and message.prediction_dt == .2
                    and message.job_id > 0)

        def job(message):
            if matching_job(message):
                observations["job_count"] += 1
                business["jobs"].append({"job_id": message.job_id,
                    "target_tick": message.target_tick, "received_ns": time.monotonic_ns()})

        def candidate(message):
            identity = latest["owned_identity"]
            if (matching_job(message.job) and identity is not None
                    and message.worker_instance == identity[1]
                    and message.backend == "acados" and message.solver_invoked):
                observations["candidate_count"] += 1
                business["candidates"].append({"job_id": message.job.job_id,
                    "received_ns": time.monotonic_ns(), "solver_invoked": True,
                    "success": message.success})

        def decision(message):
            if message.run_id == args.run_id:
                observations["decision_count"] += 1
            identity = latest["owned_identity"]
            if (identity is not None and message.run_id == args.run_id
                    and message.boot_id == context["boot_id"]
                    and message.contract_hash == contract_hash
                    and message.worker_instance == identity[1]
                    and message.schema_version == "p1-execution-decision-v2"
                    and message.activation_odom_sequence > 0
                    and message.activation_odom_receive_ns > 0
                    and message.activation_clock_receive_ns > 0
                    and math.isfinite(message.activation_rtf)
                    and c["rtf_low"] <= message.activation_rtf <= c["rtf_high"]):
                business["decision"] = {"sequence": message.sequence,
                    "received_ns": time.monotonic_ns(), "activation_commit_ns": message.activation_commit_ns,
                    "odom_sequence": message.activation_odom_sequence,
                    "odom_receive_ns": message.activation_odom_receive_ns,
                    "clock_receive_ns": message.activation_clock_receive_ns,
                    "rtf": message.activation_rtf, "reason": message.reason}

        caps_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                              durability=DurabilityPolicy.TRANSIENT_LOCAL)
        node.create_subscription(WorkerCapability, "/p1/worker_capability", capability, caps_qos)
        node.create_subscription(ExecutionDecision, "/p1/execution_decision", decision, qos)
        node.create_subscription(SolveJob, "/p1/solve_job", job, qos)
        node.create_subscription(SolveCandidate, "/p1/solve_candidate", candidate, qos)

        def assert_no_endpoints():
            nonlocal no_endpoints
            counts = {name: node.count_publishers(topic) for name, topic in c["output_topics"].items()}
            if any(counts.values()):
                no_endpoints = False
                raise RuntimeError("physical publisher endpoint detected: " + str(counts))
            if no_endpoints is None:
                no_endpoints = True

        def spin_wait(predicate, timeout):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=.02)
                if REQUESTED_STOP:
                    raise RuntimeError("operator interrupted startup")
                assert_no_endpoints()
                if predicate():
                    return
            raise TimeoutError("bounded ROS startup condition not satisfied")

        # Let discovery run before launch and preserve graph facts.
        discover_end = time.monotonic() + 1.
        while time.monotonic() < discover_end:
            rclpy.spin_once(node, timeout_sec=.02)
            assert_no_endpoints()
        observed_nodes = node.get_node_names_and_namespaces()
        if any(name in {"p1_regulator", "p1_solver_worker", "mpc_node", "p1_synthetic_input_fixture"}
               for name, _namespace in observed_nodes):
            raise RuntimeError("existing ROS controller/fixture in diagnostic domain")
        supervisor.event("ros_graph_preflight", nodes=observed_nodes, physical_endpoints=0)
        bag_topics = list(topics["inputs"].values()) + list(topics["p1"].values())
        # Declare input and typed topics before recording, without publishing data.
        # Otherwise rosbag cannot subscribe to an undiscovered /clock topic.
        declarations = [(Clock, "/clock"), (Odometry, c["input_topics"]["odom"]),
                        (Imu, c["input_topics"]["imu"]), (RosPath, c["input_topics"]["path"]),
                        (Float64MultiArray, c["input_topics"]["profile"]),
                        (SolveJob, "/p1/solve_job"), (SolveCandidate, "/p1/solve_candidate"),
                        (ExecutionDecision, "/p1/execution_decision")]
        declaration_publishers = [node.create_publisher(kind, topic, qos)
                                  for kind, topic in declarations]
        declaration_publishers.append(node.create_publisher(WorkerCapability,
                                      "/p1/worker_capability", caps_qos))
        supervisor.event("topic_types_declared", topics=bag_topics,
                         data_published=False, physical_endpoints=0)
        # Execute the CLI through the verified Python interpreter. ros2 is a
        # Python entrypoint; this removes interpreter/launcher identity ambiguity.
        recorder = supervisor.spawn("recorder", [str(python), str(ros2), "bag", "record",
                    "--storage", "mcap", "--output", str(directory / "raw_bag"), *bag_topics],
                    env, python, binaries["python"]["sha256"])
        spin_wait(lambda: recorder.process.poll() is None
                  and (directory / "raw_bag").is_dir()
                  and all(any("recorder" in info.node_name
                              for info in node.get_subscriptions_info_by_topic(topic))
                          for topic in bag_topics), 10.)
        base = ["--ros-args", "-p", "run_id:=" + args.run_id,
                "-p", "contract_file:=" + str(args.contract.resolve()),
                "-p", "contract_hash:=" + contract_hash]
        worker_child = supervisor.spawn("worker", [str(worker), *base,
                    "-p", "source_file:=" + str(source_paths["worker"]),
                    "-p", "test_delay_ms:=" + str(args.test_delay_ms),
                    "-p", "test_native_block_ms:=" + str(args.test_native_block_ms)],
                    env, worker, binaries["worker"]["sha256"])
        spin_wait(lambda: latest["capability"] is not None, 10.)
        cap = latest["capability"]
        instance = verify_worker_capability(cap, worker_child.process.pid, args, c,
                                            contract_hash, context["boot_id"])
        if worker_child.process.poll() is not None:
            raise RuntimeError("owned worker exited before regulator startup")
        latest["owned_identity"] = (cap.pid, instance)
        expected_header = independent_witness_header(args, context, binaries,
                                                     diagnostic_source_hash, instance)
        exclusive_json(directory / "witness_expected_header.json", expected_header)
        supervisor.event("witness_header_frozen", header=expected_header,
                         header_sha256=sha256_file(directory / "witness_expected_header.json"),
                         witness_enabled=args.witness_enabled, test_sink_pause_ms=0)
        supervisor.event("worker_capability_verified", pid=cap.pid,
                          worker_instance=cap.worker_instance, backend=cap.backend,
                          fault_injection_enabled=cap.fault_injection_enabled)
        regulator_command = diagnostic_regulator_command(args, base, worker_child.process.pid,
                    source_paths, binaries, diagnostic_source, diagnostic_source_hash,
                    witness_path, instance)
        regulator_child = supervisor.spawn("regulator", regulator_command,
                    env, regulator, binaries["regulator"]["sha256"])
        fixture = supervisor.spawn("fixture", [str(python), str(Path(__file__).resolve()),
                    "--fixture-child", "--contract", str(args.contract.resolve()),
                    "--contract-hash", contract_hash, "--fixture-source", str(source_paths["fixture"])],
                    env, python, binaries["python"]["sha256"])
        arm_path = directory / "fixture_armed.json"
        arm_fact = None
        ready_fact = None

        def business_ready():
            nonlocal arm_fact, ready_fact
            if supervisor.evidence_failed:
                raise RuntimeError("supervision ledger IO failure during business readiness")
            for child in (worker_child, regulator_child, recorder, fixture):
                if child.process.poll() is not None:
                    raise RuntimeError("owned child exited before business readiness: " + child.name)
            cap = latest["capability"]
            if cap is not None and cap.fatal:
                raise RuntimeError("worker became fatal before observation window")
            if arm_fact is None:
                if not arm_path.is_file():
                    return False
                if arm_path.stat().st_size > 4096:
                    raise RuntimeError("fixture arm artifact exceeded declared small bound")
                # The create-only writer may have opened the file but not yet
                # closed its small buffered write; an incomplete read is not failure.
                try:
                    arm_fact = json.loads(arm_path.read_text())
                except json.JSONDecodeError:
                    return False
                if (arm_fact.get("schema") != "p1-synthetic-fixture-arm-v1"
                        or arm_fact.get("pid") != fixture.process.pid
                        or arm_fact.get("boot_id") != context["boot_id"]
                        or arm_fact.get("contract_sha256") != contract_hash
                        or arm_fact.get("actual_dds_writers_matched") is not True
                        or not isinstance(arm_fact.get("armed_ns"), int)
                        or arm_fact["armed_ns"] <= 0
                        or arm_fact["armed_ns"] > time.monotonic_ns()
                        or not all(arm_fact.get("publisher_match_counts", {}).get(name, 0) >= 2
                                   for name in ("clock", "odom", "imu", "path", "profile"))):
                    raise RuntimeError("fixture actual arm identity/facts mismatch")
            after = arm_fact["armed_ns"]
            cap_fact, decision_fact = business["capability"], business["decision"]
            if (cap_fact is None or cap_fact["received_ns"] < after
                    or (cap_fact["pid"], cap_fact["worker_instance"]) != latest["owned_identity"]
                    or decision_fact is None or decision_fact["received_ns"] < after
                    or decision_fact["activation_commit_ns"] < after):
                return False
            jobs = [item for item in business["jobs"] if item["received_ns"] >= after]
            if expected_fault in ("none", "diagnostic_tick_stall", "diagnostic_preparation_wait"):
                candidates = [item for item in business["candidates"] if item["received_ns"] >= after]
                pair = next(((j, k) for j in jobs for k in candidates
                             if j["job_id"] == k["job_id"]), None)
                if pair is None:
                    return False
                job_fact, candidate_fact = pair
                policy = "fixture_arm_valid_capability_source_decision_and_same_job_candidate"
            elif expected_fault == "controlled_pre_native_barrier_watchdog":
                job_fact = next((item for item in jobs
                                 if item["job_id"] == cap_fact["active_job"]), None)
                if job_fact is None or cap_fact["active_job"] <= 0:
                    return False
                candidate_fact = None
                policy = "fixture_arm_valid_capability_source_decision_and_active_job"
            else:
                if not jobs:
                    return False
                job_fact, candidate_fact = jobs[0], None
                policy = "fixture_arm_valid_capability_source_decision_and_first_job"
            ready_fact = {"policy": policy, "fixture_arm": arm_fact,
                          "fixture_armed_sha256": sha256_file(arm_path),
                          "capability": cap_fact, "decision": decision_fact,
                          "job": job_fact, "candidate": candidate_fact,
                          "candidate_acceptance_required": False,
                          "actual_plant": False, "physical_endpoints": 0}
            return True

        spin_wait(business_ready, 10.)
        started = time.monotonic_ns()
        window_start = {"schema": "p1-calibration-window-start-v1",
                        "run_id": args.run_id, "started_ns": started,
                        "duration_s": args.duration, "expected_fault": expected_fault,
                        "readiness": ready_fact}
        exclusive_json(directory / "window_start.json", window_start)
        deadline = started + int(args.duration * 1e9)
        supervisor.event("calibration_window_start", planned_duration_s=args.duration,
                          expected_fault=expected_fault, physical_endpoints=0,
                          window_start=window_start,
                          window_start_sha256=sha256_file(directory / "window_start.json"))
        stop_reason = "declared_duration_elapsed"
        while time.monotonic_ns() < deadline:
            rclpy.spin_once(node, timeout_sec=.02)
            assert_no_endpoints()
            if supervisor.evidence_failed:
                raise RuntimeError("supervision ledger IO failure")
            if REQUESTED_STOP:
                stop_reason = "operator_stop"
                break
            for child in (worker_child, regulator_child, recorder, fixture):
                if child.process.poll() is not None:
                    raise RuntimeError("owned child exited during calibration: " + child.name)
            cap = latest["capability"]
            if cap is not None and cap.fatal:
                stop_reason = "worker_fatal"
                if expected_fault == "none":
                    raise RuntimeError("unexpected fatal worker in baseline calibration")
                break
            active_since = latest["active_since"]
            observed_now=time.monotonic_ns()
            if active_since is not None and observed_now-active_since>c["active_watchdog_ns"] and expected_fault=="none":
                raise RuntimeError("unexpected worker watchdog in baseline calibration")
            decision=business["decision"]
            status,latest["watchdog_pending"]=watchdog_observation(active_since,observed_now,
                decision.get("reason", "") if decision else "",decision.get("activation_commit_ns", 0) if decision else 0,
                c["active_watchdog_ns"],c["T_ns"]+c["tick_jitter_ns"],latest["watchdog_pending"])
            if status in ("confirmed","timeout"):
                observations["watchdog_seen"]=status=="confirmed"
                stop_reason="owned_worker_active_watchdog" if status=="confirmed" else "owned_worker_watchdog_observation_timeout"
                supervisor.event("watchdog_observation_result",status=status,active_job=latest["active_job"],
                    external_active_since_ns=active_since,pending_since_ns=latest["watchdog_pending"],
                    original_watchdog_ns=c["active_watchdog_ns"],observation_grace_ns=c["T_ns"]+c["tick_jitter_ns"])
                break
        supervisor.event("calibration_window_end", reason=stop_reason,
                          duration_ns=time.monotonic_ns() - started, observations=observations)
        # The logical stop precedes signals; keep clock/recorder alive for the
        # regulator's shutdown decisions and all worker source/publication tail.
        stop_deadline = time.monotonic() + c["shutdown_grace_ns"] / 1e9
        while regulator_child.process.poll() is None and time.monotonic() < stop_deadline:
            message = Bool()
            message.data = True
            stop_pub.publish(message)
            rclpy.spin_once(node, timeout_sec=.02)
            time.sleep(.03)
        supervisor.event("logical_stop_requested", regulator_exit=regulator_child.process.poll(),
                          shutdown_grace_ns=c["shutdown_grace_ns"])
    except BaseException as error:
        failure = repr(error)
        stop_reason = "startup_or_runtime_exception"
        supervisor.event("run_exception", error=failure)
        # No external/unowned process is stopped on a preflight violation.
    finally:
        for name in ("regulator", "worker", "fixture", "recorder"):
            child = supervisor.owned.get(name)
            if child is None:
                continue
            if name == "recorder":
                # Recorder sees the full source/node shutdown tail before SIGINT.
                time.sleep(.25)
            cleanup[name] = supervisor.stop(child, c["worker_grace_ns"] / 1e9,
                                            c["term_grace_ns"] / 1e9,
                                            c["kill_postcheck_ns"] / 1e9)
        if node is not None:
            node.destroy_node()
        if rclpy is not None and rclpy.ok():
            rclpy.shutdown()
        sources = {}
        for name, path in source_paths.items():
            try:
                sources[name] = source_observation(path)
            except OSError as error:
                sources[name] = {"path": path.name, "read_error": repr(error),
                                 "completeness_proven": False}
        supervisor.close()
        if supervisor.evidence_failed and failure is None:
            failure = "supervision ledger write/close failure"
        summary = {"schema": "p1-no-output-calibration-runner-summary-v1", "run_id": args.run_id,
                   "calibration_status": "cleanup_failed" if supervisor.cleanup_failed
                       else "failed" if failure else "diagnostic_data_collected",
                   "failure": failure, "stop_reason": stop_reason, "expected_fault": expected_fault,
                   "cleanup_complete": not supervisor.cleanup_failed,
                   "cleanup_failed": supervisor.cleanup_failed, "cleanup": cleanup,
                   "supervision_evidence_complete": not supervisor.evidence_failed,
                   "supervision_memory_tail": supervisor.memory_tail if supervisor.evidence_failed else [],
                   "graph_no_physical_publishers": no_endpoints, "observations": observations,
                   "window_start": window_start,
                   "sources": sources, "bag_exists": (directory / "raw_bag").is_dir(),
                   "bag_metadata_exists": (directory / "raw_bag/metadata.yaml").is_file(),
                   "normal_contract_complete": False, "execute_qualified": False,
                   "plant_acceptance_observed": False, "source_completeness_proven": False,
                   "finished_ns": time.monotonic_ns()}
        exclusive_json(directory / "runner_summary.json", summary)
    audit = terminal_witness_check(args, directory, witness_path, expected_header)
    normal_check = normal_source_check(args, directory)
    postrun = {"schema": "p1-C0-independent-checks-v1", "run_id": args.run_id,
               "normal_source_check": normal_check, "fixed_witness_check": audit,
               "passed": normal_check["passed"] and (
                   not args.witness_enabled or audit.get("passed") is True),
               "C0_comparison_performed": False, "R5_mechanism_gate_implemented": False,
               "expected_log_overflow_mechanism_passed": False,
               "normal_contract_complete": False, "execute_qualified": False}
    exclusive_json(directory / "postrun_checks.json", postrun)
    print(json.dumps({"run_id": args.run_id, "directory": str(directory),
                      "status": summary["calibration_status"],
                      "cleanup_failed": summary["cleanup_failed"]}))
    return 2 if supervisor.cleanup_failed or not postrun["passed"] else 1 if failure else 0


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-hash")
    parser.add_argument("--experiment-root", type=Path)
    parser.add_argument("--workspace", type=Path, default=Path("/home/trevor/USV/usv_mpc_ws"))
    parser.add_argument("--run-id")
    parser.add_argument("--duration", type=float, default=10.)
    parser.add_argument("--test-delay-ms", type=int, choices=(0, 50, 150, 250, 400), default=0)
    parser.add_argument("--test-native-block-ms", type=int, default=0)
    parser.add_argument("--test-prepare-block-ms", type=int, default=0)
    parser.add_argument("--test-tick-block-ms", type=int, default=0)
    parser.add_argument("--worker-sha256")
    parser.add_argument("--regulator-sha256")
    parser.add_argument("--diagnostic-bin", type=Path)
    parser.add_argument("--diagnostic-source", type=Path)
    parser.add_argument("--diagnostic-source-sha256")
    parser.add_argument("--witness-enabled", action="store_true")
    parser.add_argument("--witness-file", type=Path)
    parser.add_argument("--test-sink-pause-ms", type=int, default=0,
                        help="C0 normal only: zero; positive pause waits for a dedicated R5 gate")
    parser.add_argument("--fixture-child", action="store_true")
    parser.add_argument("--fixture-source", type=Path)
    return parser


def main(argv=None) -> int:
    parser = argument_parser()
    args = parser.parse_args(argv)
    if not 0 <= args.test_native_block_ms <= 60000:
        parser.error("controlled pre-native barrier must be in [0,60000] ms")
    if not 0 <= args.test_prepare_block_ms <= 3000 or not 0 <= args.test_tick_block_ms <= 3000:
        parser.error("diagnostic preparation/tick barrier must be in [0,3000] ms")
    if sum(bool(v) for v in (args.test_delay_ms,args.test_native_block_ms,args.test_prepare_block_ms,args.test_tick_block_ms)) > 1:
        parser.error("isolate one diagnostic fault mechanism per run")
    if any((args.test_delay_ms, args.test_native_block_ms, args.test_prepare_block_ms,
            args.test_tick_block_ms, args.test_sink_pause_ms)):
        parser.error("C0 normal keeps every fault/pause hook off; R5 gate is not implemented")
    if args.fixture_child:
        if args.fixture_source is None or args.contract_hash is None:
            parser.error("fixture source and frozen contract hash required")
        return fixture_child(args)
    if args.run_id is None or args.experiment_root is None:
        parser.error("explicit create-only run-id and existing experiment-root required")
    try:
        validate_normal_parameters(args)
    except ValueError as error:
        parser.error(str(error))
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
