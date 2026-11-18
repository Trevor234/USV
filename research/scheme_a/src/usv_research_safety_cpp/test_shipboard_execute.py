"""Process-level integration tests for Phase C shipboard_execute bridge (Domain 224)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def _resolve_install_and_bin() -> tuple[str, str]:
    override = os.environ.get("USV_COMMISSIONING_INSTALL_BASE")
    if override:
        install = os.path.abspath(override)
        return install, os.path.join(
            install, "usv_research_safety_cpp", "lib", "usv_research_safety_cpp")
    try:
        from ament_index_python.packages import get_package_prefix
        pkg_prefix = get_package_prefix("usv_research_safety_cpp")
        candidate_bin = os.path.join(pkg_prefix, "lib", "usv_research_safety_cpp")
        if os.path.isfile(os.path.join(candidate_bin, "p1_regulator")):
            return os.path.dirname(pkg_prefix), candidate_bin
    except Exception:  # noqa: BLE001
        pass
    install = os.path.join(os.path.abspath(os.path.join(HERE, "..", "..")), "install")
    return install, os.path.join(
        install, "usv_research_safety_cpp", "lib", "usv_research_safety_cpp")


INSTALL, BIN = _resolve_install_and_bin()
EXECUTE_CONTRACT = os.path.join(HERE, "model", "contract_shipboard_execute.json")
PLAN = os.path.join(HERE, "model", "research_model_plan.json")

pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(BIN, "p1_regulator")),
    reason="shipboard execute binaries not built in this tree")


def _sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _prepend(name: str, entries) -> str:
    inherited = [item for item in os.environ.get(name, "").split(":") if item]
    ordered = []
    for entry in list(entries) + inherited:
        if entry and entry not in ordered:
            ordered.append(entry)
    return ":".join(ordered)


def isolated_env() -> dict:
    return {
        "HOME": os.environ.get("HOME", "/home/trevor"),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "ROS_DOMAIN_ID": "224",
        "ROS_LOCALHOST_ONLY": "1",
        "ROS_AUTOMATIC_DISCOVERY_RANGE": "LOCALHOST",
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ACADOS_SOURCE_DIR": "/home/trevor/acados",
        "LD_LIBRARY_PATH": _prepend("LD_LIBRARY_PATH", [
            os.path.join(INSTALL, "usv_acados", "lib"),
            os.path.join(INSTALL, "usv_nmpc", "lib"),
            os.path.join(INSTALL, "usv_research_interfaces", "lib"),
            "/home/trevor/acados/lib",
        ]),
        "AMENT_PREFIX_PATH": _prepend("AMENT_PREFIX_PATH", [
            os.path.join(INSTALL, "usv_research_safety_cpp"),
            os.path.join(INSTALL, "usv_research_interfaces"),
            os.path.join(INSTALL, "usv_nmpc"),
            os.path.join(INSTALL, "usv_acados"),
            INSTALL,
        ]),
        "PYTHONPATH": _prepend("PYTHONPATH", [
            os.path.join(INSTALL, "usv_research_safety_cpp", "lib", "python3.12", "site-packages"),
            os.path.join(INSTALL, "usv_research_interfaces", "lib", "python3.12", "site-packages"),
        ]),
    }


def spawn_pair(tmp_path):
    import uuid
    run_id = str(uuid.uuid4())
    boot_id = str(uuid.uuid4())
    contract_sha = _sha256(EXECUTE_CONTRACT)
    plan_sha = _sha256(PLAN)
    worker_log = open(tmp_path / "worker.stdout.txt", "wb")
    worker = subprocess.Popen(
        [os.path.join(BIN, "p1_solver_worker"), "--ros-args",
         "-p", f"run_id:={run_id}", "-p", f"boot_id:={boot_id}",
         "-p", f"contract_file:={EXECUTE_CONTRACT}", "-p", f"contract_hash:={contract_sha}",
         "-p", f"model_plan_file:={PLAN}", "-p", f"model_plan_sha256:={plan_sha}",
         "-p", "mode:=shipboard_execute",
         "-p", f"source_file:={tmp_path}/worker.source.jsonl"],
        env=isolated_env(), stdout=worker_log, stderr=worker_log)
    reg_log = open(tmp_path / "regulator.stdout.txt", "wb")
    regulator = subprocess.Popen(
        [os.path.join(BIN, "p1_regulator"), "--ros-args",
         "-p", f"run_id:={run_id}", "-p", f"boot_id:={boot_id}",
         "-p", f"contract_file:={EXECUTE_CONTRACT}", "-p", f"contract_hash:={contract_sha}",
         "-p", f"model_plan_file:={PLAN}", "-p", f"model_plan_sha256:={plan_sha}",
         "-p", "mode:=shipboard_execute",
         "-p", f"source_file:={tmp_path}/regulator.source.jsonl",
         "-p", f"worker_pid:={worker.pid}"],
        env=isolated_env(), stdout=reg_log, stderr=reg_log)
    return {"worker": worker, "regulator": regulator, "logs": (worker_log, reg_log)}


def stop_pair(pair):
    pair["regulator"].send_signal(signal.SIGTERM)
    try:
        pair["regulator"].wait(timeout=8.0)
    except subprocess.TimeoutExpired:
        pair["regulator"].kill()
    pair["worker"].send_signal(signal.SIGTERM)
    try:
        pair["worker"].wait(timeout=8.0)
    except subprocess.TimeoutExpired:
        pair["worker"].kill()
    for h in pair["logs"]:
        h.close()


def read_jsonl(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


_DRIVER_PREAMBLE = r"""
import json, time, rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data
from mavros_msgs.msg import State, OverrideRCIn
from mavros_msgs.srv import SetMode
from nav_msgs.msg import Odometry, Path
from sensor_msgs.msg import Imu
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Bool, Float64MultiArray, MultiArrayDimension, String

rclpy.init(args=None)
node = Node("p1_exec_test_driver")

p_state = node.create_publisher(State, "/mavros/state", qos_profile_sensor_data)
p_odom = node.create_publisher(Odometry, "/mavros/local_position/odom", qos_profile_sensor_data)
p_imu = node.create_publisher(Imu, "/mavros/imu/data", qos_profile_sensor_data)
p_path = node.create_publisher(Path, "/path/reference", 10)
p_prof = node.create_publisher(Float64MultiArray, "/path/reference_profile", 10)
p_stop = node.create_publisher(Bool, "/p1/stop", 10)

rc_events = []
mpc_statuses = []
set_mode_calls = []
comm_statuses = []

def on_rc(msg):
    rc_events.append((time.monotonic_ns(), int(msg.channels[0]), int(msg.channels[2])))

def on_mpc(msg):
    try:
        mpc_statuses.append(json.loads(msg.data))
    except ValueError:
        pass

def on_set_mode(req, resp):
    set_mode_calls.append((time.monotonic_ns(), req.custom_mode))
    resp.mode_sent = True
    return resp

def on_comm(msg):
    try:
        comm_statuses.append(json.loads(msg.data))
    except ValueError:
        pass

node.create_subscription(OverrideRCIn, "/mavros/rc/override", on_rc, 10)
node.create_subscription(String, "/mpc/status", on_mpc, 10)
node.create_service(SetMode, "/mavros/set_mode", on_set_mode)
node.create_subscription(
    String, "/p1/commissioning_status", on_comm,
    QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL),
)

def publish_inputs(armed, mode, send_odom=True):
    now_t = node.get_clock().now().to_msg()
    st = State()
    st.connected = True
    st.armed = armed
    st.mode = mode
    p_state.publish(st)

    im = Imu()
    im.header.stamp = now_t
    im.header.frame_id = "base_link"
    im.orientation.w = 1.0
    im.angular_velocity.z = 0.02
    p_imu.publish(im)

    if send_odom:
        od = Odometry()
        od.header.stamp = now_t
        od.header.frame_id = "map"
        od.child_frame_id = "base_link"
        od.pose.pose.position.x = 0.0
        od.pose.pose.position.y = 0.0
        od.pose.pose.orientation.w = 1.0
        od.twist.twist.linear.x = 0.2
        p_odom.publish(od)

    path = Path()
    path.header.stamp = now_t
    path.header.frame_id = "map"
    prof = Float64MultiArray()
    for i in range(12):
        ps = PoseStamped()
        ps.header.stamp = now_t
        ps.header.frame_id = "map"
        ps.pose.position.x = 2.0 + float(i) * 0.5
        ps.pose.position.y = 1.5
        ps.pose.orientation.w = 1.0
        path.poses.append(ps)
        prof.data.extend([0.6, 0.0, 0.0, float(i) * 0.8])
    prof.layout.dim = [
        MultiArrayDimension(label=f"stamp_sec:{now_t.sec}", size=12, stride=48),
        MultiArrayDimension(label=f"stamp_nanosec:{now_t.nanosec}", size=4, stride=4),
    ]
    p_path.publish(path)
    p_prof.publish(prof)

def spin_for(sec, armed, mode, send_odom=True):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        publish_inputs(armed, mode, send_odom=send_odom)
        rclpy.spin_once(node, timeout_sec=0.05)

def wait_ready(timeout_s=20.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        publish_inputs(False, "HOLD", send_odom=True)
        rclpy.spin_once(node, timeout_sec=0.05)
        if comm_statuses and comm_statuses[-1].get("phase") == "ready" and (
            comm_statuses[-1].get("worker") or {}).get("model_runtime_ready"):
            return True
        time.sleep(0.05)
    return False
"""


def _run_driver(scenario_code: str, timeout: float = 60.0) -> dict:
    driver = subprocess.run(
        ["/usr/bin/python3", "-B", "-c", _DRIVER_PREAMBLE + "\n" + scenario_code],
        env=isolated_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout,
    )
    assert driver.returncode == 0, driver.stderr
    return json.loads(driver.stdout.strip().splitlines()[-1])


def test_shipboard_execute_actuation_preemption_and_odom_failsafe(tmp_path):
    """End-to-end test: STANDBY -> ACTIVE (PWM) -> HOLD preempt (<=0.2s) -> odom stale (1500+HOLD)."""
    pair = spawn_pair(tmp_path)
    try:
        data = _run_driver(r"""
ready_seen = wait_ready()
spin_for(0.6, False, "HOLD", True)
standby_nonzero = [e for e in rc_events if e[1] != 0 or e[2] != 0]

rc_before_active = len(rc_events)
spin_for(2.5, True, "MANUAL", True)
active_events = rc_events[rc_before_active:]
active_pwm = [e for e in active_events if 1100 <= e[1] <= 1900 and 1100 <= e[2] <= 1900 and (e[1] != 1500 or e[2] != 1500)]
active_mpc = [s for s in mpc_statuses if s.get("state") == "ACTIVE"]

rc_before_preempt = len(rc_events)
t_preempt_pub = time.monotonic_ns()
spin_for(1.0, True, "HOLD", True)
preempt_releases = [e for e in rc_events[rc_before_preempt:] if e[1] == 0 and e[2] == 0]
preempt_latency_ms = (preempt_releases[0][0] - t_preempt_pub) / 1e6 if preempt_releases else -1.0

spin_for(1.5, True, "MANUAL", True)
rc_before_fault = len(rc_events)
calls_before_fault = len(set_mode_calls)
spin_for(2.0, True, "MANUAL", send_odom=False)
fault_neutrals = [e for e in rc_events[rc_before_fault:] if e[1] == 1500 and e[2] == 1500]
fault_holds = [c for c in set_mode_calls[calls_before_fault:] if c[1] == "HOLD"]
hold_mpc = [s for s in mpc_statuses if s.get("state") == "HOLD" and s.get("hold") is True]

last_active = active_mpc[-1] if active_mpc else {}
print(json.dumps({
    "ready_seen": ready_seen,
    "standby_nonzero": len(standby_nonzero),
    "active_pwm_count": len(active_pwm),
    "active_mpc_count": len(active_mpc),
    "preempt_release_count": len(preempt_releases),
    "preempt_latency_ms": preempt_latency_ms,
    "fault_neutral_count": len(fault_neutrals),
    "fault_hold_count": len(fault_holds),
    "hold_mpc_count": len(hold_mpc),
    "allowed_modes": last_active.get("allowed_fcu_modes"),
    "anchor_source": last_active.get("actuation_anchor_source"),
    "anchor_modeled": last_active.get("anchor_modeled"),
    "hardware_receipt_verified": last_active.get("hardware_receipt_verified"),
}))
rclpy.shutdown()
""")
        assert data["ready_seen"] is True, data
        assert data["standby_nonzero"] == 0, data
        assert data["active_pwm_count"] >= 3, data
        assert data["active_mpc_count"] >= 3, data
        assert data["allowed_modes"] == ["MANUAL"], data
        assert data["anchor_source"] == "rc_override_quantized_eff", data
        assert data["anchor_modeled"] is True and data["hardware_receipt_verified"] is False, data
        assert data["preempt_release_count"] >= 1, data
        assert 0.0 <= data["preempt_latency_ms"] <= 200.0, data
        assert data["fault_neutral_count"] >= 1, data
        assert data["fault_hold_count"] >= 1, data
        assert data["hold_mpc_count"] >= 1, data
    finally:
        stop_pair(pair)

    worker_records = read_jsonl(tmp_path / "worker.source.jsonl")
    regulator_records = read_jsonl(tmp_path / "regulator.source.jsonl")
    ws = [r for r in worker_records if r.get("type") == "worker_summary"]
    assert len(ws) == 1 and ws[0]["fatal"] is False and ws[0]["shipboard_execute_mode"] is True
    rs = [r for r in regulator_records if r.get("type") == "source_summary"]
    assert len(rs) == 1 and rs[0]["dropped"] == 0 and rs[0]["generated"] == rs[0]["emitted"]
    decs = [r for r in regulator_records if r.get("type") == "execute_decision" and r.get("accepted")]
    assert len(decs) >= 3
    assert all(d["anchor_modeled"] is True and d["hardware_receipt_verified"] is False for d in decs)


def test_shipboard_execute_worker_kill_triggers_failsafe(tmp_path):
    """Killing solver worker while ACTIVE must emit 1500 neutral + SetMode(HOLD) + release on HOLD."""
    pair = spawn_pair(tmp_path)
    try:
        driver = subprocess.Popen(
            ["/usr/bin/python3", "-B", "-c", _DRIVER_PREAMBLE + r"""
import os, sys
flag_file = sys.argv[1]
assert wait_ready()
# Phase 1: Reach ACTIVE with real PWM output, then signal parent pytest process to SIGKILL worker.
spin_for(2.0, True, "MANUAL", True)
with open(flag_file, "w") as fh:
    fh.write("active")
# Keep MANUAL active until neutral failsafe fires, then mimic FCU transitioning to HOLD.
deadline = time.monotonic() + 5.0
saw_hold_mpc = False
while time.monotonic() < deadline:
    publish_inputs(True, "MANUAL", send_odom=True)
    rclpy.spin_once(node, timeout_sec=0.05)
    if any(s.get("state") == "HOLD" and s.get("hold") is True for s in mpc_statuses):
        saw_hold_mpc = True
        break
spin_for(0.8, True, "HOLD", True)
print(json.dumps({
    "saw_hold_mpc": saw_hold_mpc,
    "neutral_events": len([e for e in rc_events if e[1] == 1500 and e[2] == 1500]),
    "hold_calls": len([c for c in set_mode_calls if c[1] == "HOLD"]),
    "final_release": rc_events[-1] if rc_events else None,
}))
rclpy.shutdown()
""", str(tmp_path / "active.flag")],
            env=isolated_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline and not (tmp_path / "active.flag").exists():
            time.sleep(0.1)
        assert (tmp_path / "active.flag").exists(), "never reached ACTIVE before worker kill"
        pair["worker"].kill()
        out, err = driver.communicate(timeout=20)
        assert driver.returncode == 0, err
        data = json.loads(out.strip().splitlines()[-1])
        assert data["saw_hold_mpc"] is True, data
        assert data["neutral_events"] >= 1, data
        assert data["hold_calls"] >= 1, data
        assert data["final_release"] is not None and tuple(data["final_release"][1:]) == (0, 0), data
        reg_rc = pair["regulator"].wait(timeout=10.0)
        assert reg_rc == 2
    finally:
        stop_pair(pair)

    regulator_records = read_jsonl(tmp_path / "regulator.source.jsonl")
    failures = [r for r in regulator_records if r.get("type") == "commissioning_failure"]
    assert failures and failures[-1]["execution_endpoint_enabled"] is True


def test_shipboard_execute_operator_stop_neutral_drain(tmp_path):
    """Sending /p1/stop while ACTIVE in MANUAL must emit 1500+HOLD first, then 0/0 release."""
    pair = spawn_pair(tmp_path)
    try:
        data = _run_driver(r"""
assert wait_ready()
spin_for(2.0, True, "MANUAL", True)
rc_before_stop = len(rc_events)
calls_before_stop = len(set_mode_calls)
p_stop.publish(Bool(data=True))
spin_for(0.9, True, "MANUAL", True)
tail_rc = rc_events[rc_before_stop:]
tail_calls = [c[1] for c in set_mode_calls[calls_before_stop:]]
print(json.dumps({
    "active_seen": any(s.get("state") == "ACTIVE" for s in mpc_statuses),
    "tail_rc": [(c1, c3) for _, c1, c3 in tail_rc],
    "tail_calls": tail_calls,
}))
rclpy.shutdown()
""")
        assert data["active_seen"] is True, data
        assert "HOLD" in data["tail_calls"], data
        pairs = [tuple(p) for p in data["tail_rc"]]
        assert (1500, 1500) in pairs and (0, 0) in pairs, data
        assert pairs.index((1500, 1500)) < pairs.index((0, 0)), data
        assert pair["regulator"].wait(timeout=10.0) == 0
    finally:
        stop_pair(pair)

    regulator_records = read_jsonl(tmp_path / "regulator.source.jsonl")
    acts = [r for r in regulator_records if r.get("type") == "execute_actuation"]
    directives = [a["directive"] for a in acts]
    assert "neutral_pwm" in directives and directives[-1] == "release"
    stops = [r for r in regulator_records if r.get("type") == "commissioning_stop"]
    assert len(stops) == 1 and stops[0]["exit_code"] == 0
