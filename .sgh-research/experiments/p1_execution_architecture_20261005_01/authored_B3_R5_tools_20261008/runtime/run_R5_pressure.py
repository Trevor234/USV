"""Independent finite R5 no_output pressure collection for the fixed B1 diagnostic.

Run on the authorized Linux ROS host after the build has passed. The invoking
shell must source Jazzy and this workspace's install/setup.bash first.
Independent R5 collection: one 5000ms pause after two accepted native chains; 15s maximum from arm.
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
            or cap.clock_name != "CLOCK_MONOTONIC" or cap.matrix_layout != "column_major"
            or type(cap.startup_ns) is not int or not 0 < cap.startup_ns <= (1 << 63) - 1
            or cap.horizon_steps != 20
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
               "-p", "test_sink_pause_ms:=" + str(args.test_sink_pause_ms), "-p", "witness_enabled:=" +
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


def normal_window_completion(window_start, stop_reason, finished_ns):
    """A normal window must actually finish its declared measurement interval."""
    window = window_start if type(window_start) is dict else {}
    started = window.get("started_ns")
    duration = window.get("duration_s")
    duration_valid = (type(duration) in (int, float) and 1 <= duration <= 10
                      and math.isfinite(duration))
    times_valid = (type(started) is int and type(finished_ns) is int
                   and 0 < started <= finished_ns <= (1 << 63) - 1)
    required = int(duration * 1e9) if duration_valid else None
    observed = finished_ns - started if times_valid else None
    complete = (stop_reason == "declared_duration_elapsed" and window.get("expected_fault") == "none"
                and times_valid and duration_valid and observed >= required)
    return {"normal_window_complete": complete, "stop_reason": stop_reason,
            "window_started_ns": started if type(started) is int else None,
            "window_finished_ns": finished_ns if type(finished_ns) is int else None,
            "required_duration_ns": required, "observed_duration_ns": observed}


def normal_collection_passed(source_check, audit, witness_enabled, window_completion,
                             *, run_error_free, cleanup_complete, supervision_evidence_complete):
    """Keep source and witness gates independent from whole-window completion."""
    return (source_check.get("passed") is True
            and (not witness_enabled or audit.get("passed") is True)
            and window_completion.get("normal_window_complete") is True
            and run_error_free is True and cleanup_complete is True
            and supervision_evidence_complete is True)


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
                                     "run_r5_diag_validation.py", "run_R5_pressure.py"})
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
    # Exact 15s maximum and all pressure options were validated before creation.
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
                     "stop": "/p1/stop", "sink_pause_arm": ARM_TOPIC}}
    expected_fault = "sink_logger_pause_overflow"
    context = {"schema": "p1-R5-pressure-context-v1", "run_id": args.run_id,
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
                   "test_sink_pause_ms": args.test_sink_pause_ms, "R5_mechanism_gate_implemented": False},
               "supervisor_sha256": sha256_file(Path(__file__).with_name("owned_process_supervisor.py")),
               "ros_environment": {"ROS_DOMAIN_ID": "96", "ROS_LOCALHOST_ONLY": "1"},
               "declaration": {"duration_s": args.duration, "test_delay_ms": args.test_delay_ms,
                               "test_native_block_ms": args.test_native_block_ms,
                               "test_prepare_block_ms": args.test_prepare_block_ms,
                               "test_tick_block_ms": args.test_tick_block_ms,
                               "expected_fault": expected_fault, "test_sink_pause_ms": args.test_sink_pause_ms,
                               "pressure_window_origin": "arm_publish_start_ns", "maximum_duration_ns": MAX_PRESSURE_NS,
                               "arm_required_native_accepted_chains": 2, "execute_qualified": False},
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
    window_completion = None
    expected_header = None
    pressure_arm = None
    arm_state = {"attempted": False}
    observed_regulator_exit = None
    stop_release_ns = None
    release_requested_ns = None
    release_kind = None
    business = {"capability": None, "decision": None,
                "jobs": deque(maxlen=64), "candidates": deque(maxlen=64), "accepted_decisions": deque(maxlen=64)}
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
        pause_pub = node.create_publisher(Bool, ARM_TOPIC, qos)

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
                    "success": message.success, "prediction_available": message.prediction_available})

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
                if message.candidate_accepted:
                    business["accepted_decisions"].append({**business["decision"],"job_id":message.job_id,"tick":message.tick,
                        "accepted":message.candidate_accepted,"ready_commit_ns":message.candidate_ready_commit_ns,
                        "task_generation":message.task_generation,"model_generation":message.model_generation,
                        "config_generation":message.config_generation,"schedule_generation":message.schedule_generation,
                        "clock_epoch":message.clock_epoch})

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
                         witness_enabled=args.witness_enabled, test_sink_pause_ms=args.test_sink_pause_ms)
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
            if expected_fault in ("none", "diagnostic_tick_stall", "diagnostic_preparation_wait", "sink_logger_pause_overflow"):
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
        native_chains=[];source_prefixes={}
        def pressure_ready():
            nonlocal native_chains,source_prefixes
            if not business_ready():return False
            if not any(info.node_name=="p1_regulator" for info in node.get_subscriptions_info_by_topic(ARM_TOPIC)) or pause_pub.get_subscription_count()<2:return False
            reg_rows,reg_prefix=read_complete_prefix(source_paths["regulator"])
            worker_rows,worker_prefix=read_complete_prefix(source_paths["worker"])
            native_chains=accepted_native_chains(reg_rows,worker_rows,expected_header,c["nominal_hash"],
                list(business["accepted_decisions"]),arm_fact["armed_ns"],time.monotonic_ns())
            source_prefixes={"regulator":reg_prefix,"worker":worker_prefix}
            return len(native_chains)>=2
        spin_wait(pressure_ready,10.)
        assert_no_endpoints()
        pressure_arm=publish_pressure_arm(pause_pub,Bool,arm_state,directory,supervisor,context,ready_fact,native_chains,source_prefixes)
        started=pressure_arm["publish_start_ns"]
        window_start = {"schema": "p1-R5-pressure-window-start-v1",
                        "run_id": args.run_id, "started_ns": started,
                        "duration_s": args.duration, "expected_fault": expected_fault,
                        "readiness": ready_fact, "pressure_arm_relative_path":"pressure_arm.json",
                        "maximum_duration_ns":MAX_PRESSURE_NS, "window_origin":"arm_publish_start_ns"}
        exclusive_json(directory / "window_start.json", window_start)
        deadline = started + int(args.duration * 1e9)
        supervisor.event("calibration_window_start", planned_duration_s=args.duration,
                          expected_fault=expected_fault, physical_endpoints=0,
                          window_start=window_start,
                          window_start_sha256=sha256_file(directory / "window_start.json"))
        stop_reason="pressure_window_max_elapsed"
        while time.monotonic_ns()<deadline:
            rclpy.spin_once(node,timeout_sec=.02)
            assert_no_endpoints()
            if supervisor.evidence_failed:raise RuntimeError("supervision ledger IO failure")
            if REQUESTED_STOP:
                stop_reason="operator_stop";break
            for child in (worker_child,recorder,fixture):
                code=child.process.poll()
                if code is not None:
                    stop_reason="unexpected_owned_child_exit:"+child.name
                    raise RuntimeError(stop_reason+":"+str(code))
            code=regulator_child.process.poll()
            if code is not None:
                stop_release_ns=time.monotonic_ns()
                observed_regulator_exit={"returncode":code,"observed_ns":stop_release_ns,"natural":True}
                release_kind="natural_failure_exit"
                stop_reason="expected_sink_failure_exit" if type(code) is int and code==2 else "unexpected_regulator_exit"
                supervisor.event("R5_regulator_natural_exit",**observed_regulator_exit,stop_reason=stop_reason)
                if code!=2:raise RuntimeError("unexpected regulator exit during pressure: "+str(code))
                break
            cap=latest["capability"]
            if cap is not None and cap.fatal:
                stop_reason="unexpected_worker_fatal";raise RuntimeError("worker fatal during Sink-only pressure")
        window_finished_ns = time.monotonic_ns()
        window_completion = normal_window_completion(window_start, stop_reason, window_finished_ns)
        supervisor.event("calibration_window_end", reason=stop_reason,
                          duration_ns=window_finished_ns - started, observations=observations,
                          normal_window_complete=window_completion["normal_window_complete"],
                          window_completion=window_completion)
        # The logical stop precedes signals; keep clock/recorder alive for the
        # regulator's shutdown decisions and all worker source/publication tail.
        stop_deadline = time.monotonic() + c["shutdown_grace_ns"] / 1e9
        while regulator_child.process.poll() is None and time.monotonic() < stop_deadline:
            message = Bool()
            message.data = True
            if release_requested_ns is None:
                release_requested_ns=time.monotonic_ns();stop_release_ns=release_requested_ns;release_kind="logical_stop_publish"
            stop_pub.publish(message)
            rclpy.spin_once(node, timeout_sec=.02)
            time.sleep(.03)
        supervisor.event("logical_stop_requested", regulator_exit=regulator_child.process.poll(),
                          shutdown_grace_ns=c["shutdown_grace_ns"])
    except BaseException as error:
        failure = repr(error)
        if stop_reason in ("not_started","pressure_window_max_elapsed"):
            stop_reason = "startup_or_runtime_exception"
        if window_completion is None:
            window_completion = normal_window_completion(window_start, stop_reason, time.monotonic_ns())
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
        summary = {"schema": "p1-R5-pressure-runner-summary-v1", "run_id": args.run_id,
                   "calibration_status": "cleanup_failed" if supervisor.cleanup_failed
                       else "failed" if failure else "diagnostic_data_collected",
                   "failure": failure, "stop_reason": stop_reason, "expected_fault": expected_fault,
                   "cleanup_complete": not supervisor.cleanup_failed,
                   "cleanup_failed": supervisor.cleanup_failed, "cleanup": cleanup,
                   "supervision_evidence_complete": not supervisor.evidence_failed,
                   "supervision_memory_tail": supervisor.memory_tail if supervisor.evidence_failed else [],
                   "graph_no_physical_publishers": no_endpoints, "observations": observations,
                   "window_start": window_start,
                   "window_completion": window_completion,
                   "normal_window_complete": window_completion is not None
                       and window_completion["normal_window_complete"],
                   "pressure_arm":pressure_arm or arm_state.get("fact"),"arm_attempts":int(arm_state["attempted"]),
                   "actual_returncodes":{name:item.get("returncode") for name,item in cleanup.items()},
                   "observed_regulator_exit":observed_regulator_exit,"stop_release_ns":stop_release_ns,
                   "release_requested_ns":release_requested_ns,"release_kind":release_kind,"R5_complete":False,
                   "physical_execute_release_enabled":False,
                   "sources": sources, "bag_exists": (directory / "raw_bag").is_dir(),
                   "bag_metadata_exists": (directory / "raw_bag/metadata.yaml").is_file(),
                   "normal_contract_complete": False, "execute_qualified": False,
                   "plant_acceptance_observed": False, "source_completeness_proven": False,
                   "finished_ns": time.monotonic_ns()}
        exclusive_json(directory / "runner_summary.json", summary)
    audit = terminal_witness_check(args, directory, witness_path, expected_header)
    normal_check = normal_source_check(args, directory)
    delivery_check=terminal_application_delivery(directory)
    collection=pressure_collection_complete(summary,audit)
    postrun={"schema":"p1-R5-pressure-independent-checks-v1","run_id":args.run_id,
             "normal_source_check":normal_check,"strict_application_delivery":delivery_check,"fixed_witness_check":audit,
             "window_completion":window_completion,"pressure_collection_complete":collection,"passed":False,
             "normal_window_complete":False,"R5_mechanism_gate_implemented":False,"R5_complete":False,
             "expected_log_overflow_mechanism_passed":False,"normal_contract_complete":False,
             "execute_qualified":False,"physical_execute_release_enabled":False}
    exclusive_json(directory/"postrun_checks.json",postrun)
    print(json.dumps({"run_id":args.run_id,"directory":str(directory),"pressure_collection_complete":collection,
                      "R5_complete":False,"stop_reason":stop_reason,"regulator_returncode":summary["actual_returncodes"].get("regulator")}))
    return 2 if supervisor.cleanup_failed or not collection else 0



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



# R5_HELPERS_BEGIN
BASE_RUNNER_SHA256 = 'c8bc0141e3ad7b37ff07b1e3ce440c47b01e4386b90bf9f362beda1922ea0766'
ARM_TOPIC = '/p1/diag/arm_sink_pause'
MAX_PRESSURE_NS = 15000000000


def validate_pressure_parameters(args):
    for name in ('test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms'):
        if type(getattr(args,name,None)) is not int or getattr(args,name) != 0:
            raise ValueError('R5 unrelated hooks must be true integer zero: '+name)
    if type(args.test_sink_pause_ms) is not int or args.test_sink_pause_ms != 5000:
        raise ValueError('R5 Sink pause must be true integer 5000ms')
    if type(args.duration) not in (int,float) or not math.isfinite(args.duration) or args.duration != 15:
        raise ValueError('R5 duration must be exactly the finite 15s maximum')
    if args.witness_enabled is not True or args.witness_file != Path('fixed_witness.json'):
        raise ValueError('R5 requires Witness enabled and fixed_witness.json')
    if args.diagnostic_bin is None or args.diagnostic_source is None:
        raise ValueError('explicit diagnostic binary/source required')
    for name in ('contract_hash','worker_sha256','regulator_sha256','diagnostic_source_sha256'):
        value=getattr(args,name,None)
        if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}',value) is None:
            raise ValueError('independent lowercase hash required: '+name)


_base_load_contract = load_contract
def load_contract(path, expected=None):
    contract,digest=_base_load_contract(path,expected)
    if (contract.get('fault_injection_enabled') is not True
            or type(contract.get('log_capacity')) is not int or contract['log_capacity'] != 512):
        raise ValueError('R5 requires fault-enabled diag5 and fixed capacity 512')
    return contract,digest


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate source JSON key')
        result[key]=value
    return result


def _finite(value):
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1
        if count>100000 or depth>12:raise ValueError('source JSON shape exceeded')
        if type(item) is float and not math.isfinite(item):raise ValueError('nonfinite source JSON')
        if type(item) is dict:pending.extend((v,depth+1) for v in item.values())
        elif type(item) is list:pending.extend((v,depth+1) for v in item)


def read_complete_prefix(path):
    """Only visible complete lines authorize readiness; the caller waits <=10s."""
    if not path.exists():raw=b''
    else:
        with path.open('rb') as stream:raw=stream.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('source prefix exceeds bounded bytes')
    end=raw.rfind(b'\n')+1;complete=raw[:end];rows=[]
    for line in complete.decode('utf-8',errors='strict').splitlines():
        if not line or len(line.encode('utf-8'))>256*1024:raise ValueError('source prefix invalid line')
        row=json.loads(line,object_pairs_hook=_pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
        _finite(row)
        if type(row) is not dict or type(row.get('type')) is not str:raise ValueError('source event object/type required')
        rows.append(row)
    if len(rows)>10000:raise ValueError('source prefix row bound')
    return rows,{'path':str(path),'complete_bytes':end,'rows':len(rows),
                 'sha256':hashlib.sha256(complete).hexdigest(),'tail_bytes':len(raw)-end}


def _positive(value,name):
    if type(value) is not int or not 0<value<=(1<<63)-1:raise ValueError('invalid integer '+name)
    return value


def _vector(value,size,name):
    if (type(value) is not list or len(value)!=size or any(type(x) not in (int,float) or not math.isfinite(x) for x in value)):
        raise ValueError('native finite vector shape mismatch: '+name)


def strict_equal(left,right):
    if type(left) is not type(right):return False
    if type(left) is dict:return set(left)==set(right) and all(strict_equal(left[k],right[k]) for k in left)
    if type(left) is list:return len(left)==len(right) and all(strict_equal(a,b) for a,b in zip(left,right))
    return left==right


def accepted_native_chains(regulator_rows,worker_rows,header,nominal_hash,typed_decisions,after_ns,observed_ns):
    """Join real native successful candidates to matching source and typed accepts."""
    expected={'run_id':header['run_id'],'boot_id':header['boot_id'],'contract_hash':header['contract_sha256'],
              'worker_instance':header['worker_instance'],'nominal_hash':nominal_hash}
    def job_id(job):
        if (type(job) is not dict or job.get('schema')!='p1-solve-job-v1'
                or any(job.get(k)!=v for k,v in expected.items())
                or type(job.get('N')) is not int or job['N']!=20
                or type(job.get('dt')) not in (int,float) or job['dt']!=.2):raise ValueError('native job identity mismatch')
        _positive(job.get('target_tick'),'target_tick')
        for key in ('task_generation','model_generation','config_generation','schedule_generation'):_positive(job.get(key),key)
        if type(job.get('clock_epoch')) is not int or job['clock_epoch']<0:raise ValueError('invalid Job clock_epoch')
        return _positive(job.get('job_id'),'job_id')
    def index(rows,kind,nested=False):
        result={}
        for row in rows:
            if row.get('type')!=kind:continue
            jid=job_id(row.get('job')) if nested else _positive(row.get('job_id'),kind+'.job_id')
            if jid in result:raise ValueError('duplicate pre-arm '+kind)
            result[jid]=row
        return result
    jobs=index(regulator_rows,'job',True);registrations=index(regulator_rows,'candidate_registration',True)
    received=index(worker_rows,'job_received',True);candidates=index(worker_rows,'candidate',True)
    published=index(worker_rows,'candidate_publish_result')
    result=[];seen_job=set();seen_seq=set();seen_tick=set()
    for d in regulator_rows:
        if d.get('type')!='decision' or d.get('accepted') is not True:continue
        if (d.get('schema')!='p1-execution-decision-v2' or d.get('mode')!='no_output'
                or d.get('diagnostic_only') is not True or d.get('reason')!=''
                or any(d.get(k)!=expected[k] for k in ('run_id','boot_id','contract_hash','worker_instance'))):raise ValueError('accepted Decision identity mismatch')
        jid=_positive(d.get('job_id'),'Decision.job_id');seq=_positive(d.get('sequence'),'Decision.sequence')
        tick=_positive(d.get('tick'),'Decision.tick');schedule=_positive(d.get('schedule_generation'),'Decision.schedule')
        if jid in seen_job or seq in seen_seq or (schedule,tick) in seen_tick:raise ValueError('duplicate accepted chain')
        seen_job.add(jid);seen_seq.add(seq);seen_tick.add((schedule,tick))
        if any(jid not in table for table in (jobs,registrations,received,candidates,published)):continue
        j=jobs[jid];registration=registrations[jid];receive=received[jid];candidate=candidates[jid];publication=published[jid];job=j['job']
        if any(not strict_equal(row['job'],job) for row in (registration,receive,candidate)):raise ValueError('native chain job payload mismatch')
        if (any(row.get('worker_instance')!=expected['worker_instance'] for row in (candidate,publication,receive,registration))
                or candidate.get('backend')!='acados' or candidate.get('solver_invoked') is not True
                or candidate.get('success') is not True or candidate.get('prediction_available') is not True
                or type(candidate.get('reason')) is not str or registration.get('reason')!=''
                or publication.get('success') is not True or registration.get('accepted_registration') is not True):raise ValueError('chain lacks real successful native Candidate')
        for field,size in (('first_control',2),('X',126),('U',40)):_vector(candidate.get(field),size,field)
        versions=('task_generation','model_generation','config_generation','schedule_generation')
        if job['target_tick']!=tick or any(d.get(k)!=job.get(k) for k in versions) or d.get('epoch')!=job.get('clock_epoch'):raise ValueError('Decision version/tick differs from native Job')
        ready=_positive(d.get('ready_commit_ns'),'ready_commit_ns');commit=_positive(d.get('activation_commit_ns'),'activation_commit_ns')
        times=[_positive(job.get('freeze_ns'),'freeze_ns'),_positive(j.get('publish_start_ns'),'Job.publish_start_ns'),
               _positive(receive.get('receive_ns'),'worker.receive_ns'),_positive(receive.get('commit_ns'),'worker.commit_ns'),_positive(candidate.get('solve_start_ns'),'solve_start_ns'),
               _positive(candidate.get('solve_end_ns'),'solve_end_ns'),_positive(candidate.get('publish_start_ns'),'Candidate.publish_start_ns'),ready,commit]
        if times!=sorted(times) or ready!=_positive(registration.get('ready_commit_ns'),'registration.ready_commit_ns') or not after_ns<=commit<=observed_ns:raise ValueError('native chain chronology mismatch')
        if (any(type(registration.get(k)) is not int or registration[k]!=candidate[k] for k in ('solve_start_ns','solve_end_ns'))
                or not strict_equal(registration.get('first_control'),candidate['first_control'])):raise ValueError('registration/native result identity mismatch')
        if candidate.get('receive_ns')!=receive['receive_ns'] or type(candidate.get('receive_ns')) is not int:raise ValueError('native Candidate receive identity mismatch')
        submit=_positive(j.get('submit_commit_ns'),'Job.submit_commit_ns')
        pub_start=_positive(publication.get('publish_start_ns'),'Candidate result.publish_start_ns')
        pub_end=_positive(publication.get('publish_end_ns'),'Candidate result.publish_end_ns')
        if not submit<=j['publish_start_ns'] or not candidate['publish_start_ns']<=pub_start<=pub_end<=observed_ns:raise ValueError('native publication time identity mismatch')
        if any(publication.get(k)!=candidate[k] for k in ('solve_start_ns','solve_end_ns')):raise ValueError('native publication identity mismatch')
        typed=next((r for r in typed_decisions if r.get('job_id')==jid and r.get('sequence')==seq),None)
        if typed is None:continue
        exact={'tick':tick,'activation_commit_ns':commit,'ready_commit_ns':ready,'accepted':True,'reason':'',
               **{k:d[k] for k in versions},'clock_epoch':d['epoch']}
        if any(typed.get(k)!=v or type(typed.get(k)) is not type(v) for k,v in exact.items()) or not max(after_ns,commit)<=_positive(typed.get('received_ns'),'typed.received_ns')<=observed_ns:raise ValueError('source/typed accepted Decision differs')
        result.append({'job_id':jid,'tick':tick,'sequence':seq,'schedule_generation':schedule,'ready_commit_ns':ready,
                       'activation_commit_ns':commit,'typed_received_ns':typed['received_ns'],
                       'native_solver_invoked':True,'native_success':True,'prediction_available':True,
                       'job':job,'source_decision':d,'worker_candidate':candidate,'candidate_registration':registration,
                       'candidate_publish_result':publication})
    return sorted(result,key=lambda row:row['activation_commit_ns'])


def publish_pressure_arm(publisher,bool_type,state,directory,supervisor,context,readiness,chains,prefixes,clock=time.monotonic_ns):
    if state.get('attempted') is not False or len(chains)<2:raise RuntimeError('one arm requires two complete accepted native chains')
    if (len({(row.get('job_id'),row.get('schedule_generation'),row.get('tick')) for row in chains[:2]})!=2
            or any(row.get('native_solver_invoked') is not True or row.get('native_success') is not True or row.get('prediction_available') is not True for row in chains[:2])):
        raise RuntimeError('arm chain identities must be distinct actual native successes')
    state['attempted']=True
    intent={'schema':'p1-R5-pressure-arm-intent-v1','run_id':context['run_id'],'boot_id':context['boot_id'],
            'contract_sha256':context['contract_sha256'],'arm_attempts':1,'created_ns':clock(),'topic':ARM_TOPIC,'data':True,
            'accepted_chains':chains[:2],'source_prefixes':prefixes,'readiness':readiness,'execute_qualified':False}
    exclusive_json(directory/'pressure_arm_intent.json',intent)
    supervisor.event('R5_arm_intent',intent=intent,intent_sha256=sha256_file(directory/'pressure_arm_intent.json'))
    if supervisor.evidence_failed:raise RuntimeError('arm intent ledger failed')
    message=bool_type();message.data=True;started=clock();publisher.publish(message);ended=clock()
    fact={**intent,'schema':'p1-R5-pressure-arm-v1','publish_start_ns':started,'publish_end_ns':ended,'publish_success':True,
          'arm_delivery_known':False,'arm_sink_acceptance_known':False,'R5_complete':False,'expected_log_overflow_mechanism_passed':False}
    state['fact']=fact
    exclusive_json(directory/'pressure_arm.json',fact)
    supervisor.event('R5_arm_published',pressure_arm=fact,arm_sha256=sha256_file(directory/'pressure_arm.json'))
    if supervisor.evidence_failed:raise RuntimeError('arm published ledger failed')
    return fact


def pressure_window_completion(window_start,stop_reason,finished_ns):
    window=window_start if type(window_start) is dict else {};started=window.get('started_ns')
    valid=type(started) is int and type(finished_ns) is int and 0<started<=finished_ns
    return {'normal_window_complete':False,'pressure_window_bounded':valid and finished_ns-started<=MAX_PRESSURE_NS,
            'stop_reason':stop_reason,'window_started_ns':started if type(started) is int else None,
            'window_finished_ns':finished_ns if type(finished_ns) is int else None,
            'observed_duration_ns':finished_ns-started if valid else None,'maximum_duration_ns':MAX_PRESSURE_NS,
            'window_origin':'arm_publish_start_ns','R5_complete':False}


def pressure_collection_complete(summary,audit):
    arm=summary.get('pressure_arm') or {}
    return (summary.get('failure') is None and summary.get('cleanup_complete') is True
            and summary.get('supervision_evidence_complete') is True and summary.get('graph_no_physical_publishers') is True
            and arm.get('publish_success') is True and type(arm.get('arm_attempts')) is int and arm['arm_attempts']==1
            and summary.get('stop_reason')=='expected_sink_failure_exit'
            and type(summary.get('actual_returncodes',{}).get('regulator')) is int and summary['actual_returncodes']['regulator']==2
            and (summary.get('window_completion') or {}).get('pressure_window_bounded') is True
            and audit.get('passed') is True and audit.get('report_write_succeeded') is True)


def terminal_application_delivery(directory):
    output=directory/'strict_application_delivery'
    try:
        import check_resource_delivery
        # The frozen delivery entry exposes main() and reads sys.argv directly.
        # Preserve that exact interface and restore the runner's argv even on failure.
        original_argv=sys.argv
        sys.argv=[str(Path(check_resource_delivery.__file__).resolve()),str(directory),
                  '--base-report',str(directory/'normal_source_check/contract_report.json'),'--output',str(output)]
        try:code=check_resource_delivery.main()
        finally:sys.argv=original_argv
        path=output/'resource_delivery_check.json';value=json.loads(path.read_text())
        return {'checker_returncode':code,'report_relative_path':str(path.relative_to(directory)),'report_sha256':sha256_file(path),
                'passed':code==0 and value.get('passed') is True,'R5_complete':False,'execute_qualified':False}
    except Exception as error:
        value={'checker_returncode':None,'passed':False,'error':repr(error),'R5_complete':False,'execute_qualified':False}
        exclusive_json(directory/'strict_application_delivery_error.json',value)
        return value


validate_normal_parameters=validate_pressure_parameters
normal_window_completion=pressure_window_completion
_base_argument_parser=argument_parser
def argument_parser():
    parser=_base_argument_parser();parser.set_defaults(duration=15.,test_sink_pause_ms=None)
    for action in parser._actions:
        if action.dest=='test_sink_pause_ms':action.help='R5 explicit exactly 5000ms; internal fixture leaves unset'
    return parser


def main(argv=None):
    parser=argument_parser();args=parser.parse_args(argv)
    if args.fixture_child:
        if (args.fixture_source is None or args.contract_hash is None
                or any((args.test_delay_ms,args.test_native_block_ms,args.test_prepare_block_ms,args.test_tick_block_ms))
                or args.test_sink_pause_ms not in (None,0) or args.witness_enabled or args.witness_file is not None):
            parser.error('internal fixture requires source/hash, zero hooks and no witness')
        return fixture_child(args)
    if args.run_id is None or args.experiment_root is None:parser.error('explicit run-id/experiment-root required')
    try:validate_pressure_parameters(args)
    except ValueError as error:parser.error(str(error))
    return run(args)
# R5_HELPERS_END

if __name__=="__main__":
    raise SystemExit(main())
