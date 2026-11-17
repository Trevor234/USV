"""实船调试服务接管的进程级反证。

在隔离域 224 上启动**真实**新 ELF（p1_solver_worker + p1_regulator），fixture 只
发布测试 State/IMU：没有 /clock、没有 plant、没有 recorder，也必须到达 ready。
同时反证：节点实际 publisher 里没有执行话题；发送合法 shape 的 SolveJob 只会得到
commissioning_no_jobs 且 native 入口为 0；SIGTERM/stop 后 8s 内收尾且 summary 完整。

这些 fixture 是测试证据，不是现场证据。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
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
    except Exception:  # noqa: BLE001 - 回退到本地树布局
        pass
    install = os.path.join(os.path.abspath(os.path.join(HERE, "..", "..")), "install")
    return install, os.path.join(
        install, "usv_research_safety_cpp", "lib", "usv_research_safety_cpp")


INSTALL, BIN = _resolve_install_and_bin()
CONTRACT = os.path.join(HERE, "model", "contract_shipboard_commissioning.json")
DRY_RUN_CONTRACT = os.path.join(HERE, "model", "contract_shipboard_dry_run.json")
BASELINE_CONTRACT = os.path.join(HERE, "model", "contract_controlled_sim.json")
PLAN = os.path.join(HERE, "model", "research_model_plan.json")

pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(BIN, "p1_regulator")),
    reason="commissioning binaries not built in this tree")


def sha256_file(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepend(name: str, entries) -> str:
    inherited = [item for item in os.environ.get(name, "").split(":") if item]
    ordered = []
    for entry in list(entries) + inherited:
        if entry and entry not in ordered:
            ordered.append(entry)
    return ":".join(ordered)


def isolated_env(tmp_path) -> dict:
    """隔离域 224；库/前缀沿用 ctest 已绑定的 ROS + 本树两层。"""
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
            os.path.join(INSTALL, "usv_research_safety_cpp", "lib", "python3.12",
                         "site-packages"),
            os.path.join(INSTALL, "usv_research_interfaces", "lib", "python3.12",
                         "site-packages"),
        ]),
    }


def spawn_pair(tmp_path, contract_path=CONTRACT, mode="commissioning"):
    import uuid
    run_id = str(uuid.uuid4())
    boot_id = str(uuid.uuid4())
    contract_sha = sha256_file(contract_path)
    plan_sha = sha256_file(PLAN)
    logs = {}
    worker_argv = [os.path.join(BIN, "p1_solver_worker"), "--ros-args",
                   "-p", f"run_id:={run_id}", "-p", f"boot_id:={boot_id}",
                   "-p", f"contract_file:={contract_path}", "-p", f"contract_hash:={contract_sha}",
                   "-p", f"model_plan_file:={PLAN}", "-p", f"model_plan_sha256:={plan_sha}",
                   "-p", f"mode:={mode}",
                   "-p", f"source_file:={tmp_path}/worker.source.jsonl"]
    logs["worker"] = open(tmp_path / "worker.stdout.txt", "wb")
    worker = subprocess.Popen(worker_argv, env=isolated_env(tmp_path),
                              stdout=logs["worker"], stderr=logs["worker"])
    regulator_argv = [os.path.join(BIN, "p1_regulator"), "--ros-args",
                      "-p", f"run_id:={run_id}", "-p", f"boot_id:={boot_id}",
                      "-p", f"contract_file:={contract_path}", "-p", f"contract_hash:={contract_sha}",
                      "-p", f"model_plan_file:={PLAN}", "-p", f"model_plan_sha256:={plan_sha}",
                      "-p", f"mode:={mode}",
                      "-p", f"source_file:={tmp_path}/regulator.source.jsonl",
                      "-p", f"worker_pid:={worker.pid}"]
    logs["regulator"] = open(tmp_path / "regulator.stdout.txt", "wb")
    regulator = subprocess.Popen(regulator_argv, env=isolated_env(tmp_path),
                                 stdout=logs["regulator"], stderr=logs["regulator"])
    return {"run_id": run_id, "boot_id": boot_id, "contract_sha": contract_sha,
            "plan_sha": plan_sha, "worker": worker, "regulator": regulator, "logs": logs}


def stop_pair(pair, timeout=8.0):
    pair["regulator"].send_signal(signal.SIGTERM)
    try:
        pair["regulator"].wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pair["regulator"].kill()
    pair["worker"].send_signal(signal.SIGTERM)
    try:
        pair["worker"].wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pair["worker"].kill()
    for handle in pair["logs"].values():
        handle.close()


def read_jsonl(path):
    records = []
    if not os.path.isfile(path):
        return records
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except ValueError:
                    pass
    return records


def test_worker_reaches_native_ready_without_any_peer(tmp_path):
    """没有 recorder、没有 regulator candidate 订阅、没有 job peer 也要真实就绪。"""
    import uuid
    run_id = str(uuid.uuid4())
    contract_sha = sha256_file(CONTRACT)
    log = open(tmp_path / "worker.stdout.txt", "wb")
    worker = subprocess.Popen(
        [os.path.join(BIN, "p1_solver_worker"), "--ros-args",
         "-p", f"run_id:={run_id}", "-p", f"boot_id:={uuid.uuid4()}",
         "-p", f"contract_file:={CONTRACT}", "-p", f"contract_hash:={contract_sha}",
         "-p", f"model_plan_file:={PLAN}", "-p", f"model_plan_sha256:={sha256_file(PLAN)}",
         "-p", "mode:=commissioning",
         "-p", f"source_file:={tmp_path}/worker.source.jsonl"],
        env=isolated_env(tmp_path), stdout=log, stderr=log)
    try:
        deadline = time.time() + 30
        ready = False
        while time.time() < deadline:
            if any(record.get("type") == "worker_commissioning_ready"
                   for record in read_jsonl(tmp_path / "worker.source.jsonl")):
                ready = True
                break
            time.sleep(0.2)
        assert ready, "worker never reported native commissioning readiness"
        records = read_jsonl(tmp_path / "worker.source.jsonl")
        ready_record = next(r for r in records if r.get("type") == "worker_commissioning_ready")
        assert ready_record["engine_ready"] is True
        assert ready_record["candidate_publishers"] == 0
        assert not any(r.get("type") == "worker_recording_ready" for r in records)
    finally:
        worker.send_signal(signal.SIGTERM)
        worker.wait(timeout=10)
        log.close()


def test_frozen_contract_execute_is_refused_before_any_publisher(tmp_path):
    """真实 regulator ELF + Frozen 合同 + execute → rc≠0 且 stderr 含 B5/M4。"""
    # contract_controlled_sim.json 就是 candidate_baseline + 受控仿真开关：把它
    # 还原成 v3 正式合同的字段集合（去掉 sim 专属字段与诊断修订号）。
    frozen = json.loads(open(BASELINE_CONTRACT).read())
    frozen.pop("controlled_sim_faults_enabled", None)
    frozen.update({
        "schema": "p1-execution-contract-v3",
        "qualification": "execution_frozen",
        "execute_qualified": True,
        "parameters_are_diagnostic_only": False,
        "fault_injection_enabled": False,
        "pending_final_calibration": [],
        "freeze_evidence_sha256": "a" * 64,
        "execution_contract_revision": 1,
        "resource_contract_revision": 1,
        "supported_parameter_profile": "F5_P1_candidate_20261007_01",
    })
    frozen.pop("diagnostic_contract_revision", None)
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(frozen))
    log = open(tmp_path / "regulator.stdout.txt", "wb")
    proc = subprocess.Popen(
        [os.path.join(BIN, "p1_regulator"), "--ros-args",
         "-p", "run_id:=" + "r" * 8, "-p", f"contract_file:={path}",
         "-p", f"contract_hash:={sha256_file(str(path))}", "-p", "mode:=execute",
         "-p", f"source_file:={tmp_path}/regulator.source.jsonl",
         "-p", "worker_pid:=1"],
        env=isolated_env(tmp_path), stdout=log, stderr=log)
    rc = proc.wait(timeout=30)
    log.close()
    text = (tmp_path / "regulator.stdout.txt").read_text(errors="replace")
    assert rc != 0
    assert "B5/M4" in text


def test_commissioning_rejects_clock_diagnostics(tmp_path):
    """commissioning + 非空 clock_diagnostics_file 必须被拒绝（原文保留）。"""
    log = open(tmp_path / "regulator.stdout.txt", "wb")
    proc = subprocess.Popen(
        [os.path.join(BIN, "p1_regulator"), "--ros-args",
         "-p", "run_id:=" + "r" * 8, "-p", f"contract_file:={CONTRACT}",
         "-p", f"contract_hash:={sha256_file(CONTRACT)}", "-p", "mode:=commissioning",
         "-p", f"model_plan_file:={PLAN}", "-p", f"model_plan_sha256:={sha256_file(PLAN)}",
         "-p", f"source_file:={tmp_path}/regulator.source.jsonl",
         "-p", f"clock_diagnostics_file:={tmp_path}/diag.json", "-p", "worker_pid:=1"],
        env=isolated_env(tmp_path), stdout=log, stderr=log)
    rc = proc.wait(timeout=30)
    log.close()
    text = (tmp_path / "regulator.stdout.txt").read_text(errors="replace")
    assert rc != 0
    assert "clock diagnostics require controlled_sim" in text


def test_pair_reaches_ready_and_publishes_no_execution_topic(tmp_path):
    pair = spawn_pair(tmp_path)
    try:
        topics = subprocess.run(
            ["/usr/bin/python3", "-B", "-c", """
import json, time, rclpy
from rclpy.node import Node
rclpy.init(args=None)
node = Node("p1_test_topic_probe")
deadline = time.monotonic() + 10
seen = {}
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.2)
    for name, types in node.get_topic_names_and_types():
        seen[name] = sorted(types)
print(json.dumps(seen))
node.destroy_node()
rclpy.shutdown()
"""], env=isolated_env(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=120)
        publishable = json.loads(topics.stdout.strip().splitlines()[-1])
        # 执行话题的**发布**端只可能来自 regulator；worker 自己订阅 solve_job 并发布
        # candidate 是既有契约，不算物理输出。这里核对的是 regulator 的实际发布面。
        assert "/p1/commissioning_status" in publishable
        for forbidden in ("/mavros/setpoint_velocity/cmd_vel", "/mavros/rc/override",
                          "/wamv/thrusters/left/thrust", "/wamv/thrusters/right/thrust",
                          "/p1/plant_command", "/p1/execution_decision"):
            assert forbidden not in publishable, f"{forbidden} must not be advertised"
        status_records = [r for r in read_jsonl(tmp_path / "regulator.source.jsonl")
                          if r.get("type") == "commissioning_status"]
        assert status_records, "regulator never emitted a commissioning status"
        status = status_records[-1]["status"]
        assert status["schema"] == "p1-shipboard-commissioning-status-v1"
        assert status["physical_output_enabled"] is False
        assert status["jobs_submitted"] == 0
        assert status["closed_loop_verified"] is False
        assert status["inputs"]["state"]["seen"] is False
        assert status["inputs"]["state"]["count"] == 0
        assert status["fcu"]["connected"] is None
    finally:
        stop_pair(pair)


def test_sigterm_closes_within_budget_and_summaries_are_complete(tmp_path):
    pair = spawn_pair(tmp_path)
    try:
        time.sleep(4)
    finally:
        stop_pair(pair)
    deadline = time.time() + 2
    while time.time() < deadline:
        if (tmp_path / "worker.source.jsonl").is_file():
            break
        time.sleep(0.1)
    worker_records = read_jsonl(tmp_path / "worker.source.jsonl")
    regulator_records = read_jsonl(tmp_path / "regulator.source.jsonl")
    summaries = [r for r in worker_records if r.get("type") == "worker_summary"]
    assert len(summaries) == 1
    assert summaries[0]["fatal"] is False
    assert summaries[0]["commissioning_mode"] is True
    assert summaries[0]["completed_jobs"] == 0
    source = [r for r in regulator_records if r.get("type") == "source_summary"]
    assert len(source) == 1
    assert source[0]["generated"] == source[0]["emitted"]
    assert source[0]["dropped"] == 0
    assert not any(r.get("type") == "candidate" for r in worker_records)


def test_supervisor_preflight_then_make_node_and_sigterm_clean_stop(tmp_path):
    """回归：preflight_graph 独立 Context 后再 make_node 不得二次 init 崩溃，SIGTERM 须 clean_stop。"""
    sup_script = os.path.join(HERE, "scripts", "run_shipboard_commissioning.py")
    code = f"""
import importlib.util, os, signal, time
spec = importlib.util.spec_from_file_location("sup", {sup_script!r})
sup_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sup_mod)

run_dir = {str(tmp_path / "run")!r}
os.makedirs(run_dir, exist_ok=True)
os.environ["INVOCATION_ID"] = "test-inv-1"
args = sup_mod.parse_args([
    "--release-root", {str(tmp_path)!r},
    "--underlay", {str(tmp_path)!r},
    "--run-root", {str(tmp_path)!r},
    "--contract", {CONTRACT!r},
    "--plan", {PLAN!r},
])
s = sup_mod.Supervisor(args)
s.run_dir = run_dir
s.log_handle = open(os.path.join(run_dir, "supervisor.jsonl"), "a", buffering=1, encoding="utf-8")
sup_mod._install_stop_handlers()
rc = 2
try:
    s.preflight_graph()
    s.make_node()
    s.record("sample", phase="ready")
    os.kill(os.getpid(), signal.SIGTERM)
except sup_mod._CleanStopSignal:
    rc = 0
finally:
    s.shutdown()
    s.record("shutdown", reason=s.failure or "clean_stop", exit_code=rc, ready=True, evidence_closed=True)
    s.log_handle.close()
assert rc == 0, rc
"""
    res = subprocess.run(
        ["/usr/bin/python3", "-B", "-c", code],
        env=isolated_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    rows = read_jsonl(tmp_path / "run" / "supervisor.jsonl")
    assert [r.get("event") for r in rows] == ["sample", "shutdown"]
    assert rows[-1]["reason"] == "clean_stop"
    assert rows[-1]["exit_code"] == 0


def test_shipboard_dry_run_solves_without_physical_output(tmp_path):
    """隔离域 224：真实 worker+regulator dry-run 必须消费 MAVROS 输入并真求解，且零物理执行。"""
    pair = spawn_pair(tmp_path, contract_path=DRY_RUN_CONTRACT, mode="shipboard_dry_run")
    try:
        driver = subprocess.run(
            [sys.executable, "-c", """
import json, time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from mavros_msgs.msg import State
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64MultiArray, MultiArrayDimension, String

rclpy.init()
node = Node("test_dry_run_feeder")
sensor_qos = rclpy.qos.qos_profile_sensor_data
p_state = node.create_publisher(State, "/mavros/state", sensor_qos)
p_odom = node.create_publisher(Odometry, "/mavros/local_position/odom", sensor_qos)
p_imu = node.create_publisher(Imu, "/mavros/imu/data", sensor_qos)
p_path = node.create_publisher(Path, "/path/reference", 10)
p_prof = node.create_publisher(Float64MultiArray, "/path/reference_profile", 10)
statuses = []
sub_qos = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST,
                     reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.TRANSIENT_LOCAL)
node.create_subscription(String, "/p1/commissioning_status",
                         lambda m: statuses.append(json.loads(m.data)), sub_qos)

start = time.time()
ready_seen = False
while time.time() - start < 25.0:
    now_t = node.get_clock().now().to_msg()
    st = State()
    st.connected = True
    st.armed = False
    st.mode = "HOLD"
    p_state.publish(st)

    od = Odometry()
    od.header.stamp = now_t
    od.header.frame_id = "map"
    od.child_frame_id = "base_link"
    od.pose.pose.orientation.w = 1.0
    od.twist.twist.linear.x = 0.2
    p_odom.publish(od)

    im = Imu()
    im.header.stamp = now_t
    im.header.frame_id = "base_link"
    im.orientation.w = 1.0
    im.angular_velocity.z = 0.01
    p_imu.publish(im)

    path = Path()
    path.header.stamp = now_t
    path.header.frame_id = "map"
    prof = Float64MultiArray()
    for i in range(12):
        ps = PoseStamped()
        ps.header.stamp = now_t
        ps.header.frame_id = "map"
        ps.pose.position.x = float(i) * 0.5
        ps.pose.orientation.w = 1.0
        path.poses.append(ps)
        prof.data.extend([0.6, 0.0, 0.0, float(i) * 0.8])
    dim0 = MultiArrayDimension(label=f"stamp_sec:{now_t.sec}", size=12, stride=48)
    dim1 = MultiArrayDimension(label=f"stamp_nanosec:{now_t.nanosec}", size=4, stride=4)
    prof.layout.dim = [dim0, dim1]
    p_path.publish(path)
    p_prof.publish(prof)

    rclpy.spin_once(node, timeout_sec=0.05)
    if statuses:
        last = statuses[-1]
        if last.get("phase") == "ready" and last.get("jobs_submitted", 0) >= 3 and last.get("dry_run", {}).get("candidates_accepted", 0) >= 3:
            ready_seen = True
            break
    time.sleep(0.05)

topics_with_pub = {
    name: [info.node_name for info in node.get_publishers_info_by_topic(name)]
    for name in (
        "/p1/commissioning_status", "/p1/solve_job",
        "/mavros/setpoint_velocity/cmd_vel", "/mavros/rc/override",
        "/wamv/thrusters/left/thrust", "/wamv/thrusters/right/thrust",
        "/p1/plant_command", "/p1/execution_decision",
    )
}
print(json.dumps({"ready_seen": ready_seen, "last": statuses[-1] if statuses else None, "pubs": topics_with_pub}))
rclpy.shutdown()
"""], env=isolated_env(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45)
        assert driver.returncode == 0, driver.stderr
        payload = json.loads(driver.stdout.strip().splitlines()[-1])
        assert payload["ready_seen"], payload
        last = payload["last"]
        assert last["mode"] == "shipboard_dry_run"
        assert last["physical_output_enabled"] is False
        assert last["closed_loop_verified"] is False
        assert last["anchor_known"] is False
        assert last["jobs_submitted"] >= 3
        assert last["worker"]["completed_jobs"] >= 3
        assert last["dry_run"]["candidates_accepted"] >= 3
        assert "/p1/commissioning_status" in [k for k, v in payload["pubs"].items() if v]
        assert "/p1/solve_job" in [k for k, v in payload["pubs"].items() if v]
        for forbidden in ("/mavros/setpoint_velocity/cmd_vel", "/mavros/rc/override",
                          "/wamv/thrusters/left/thrust", "/wamv/thrusters/right/thrust",
                          "/p1/plant_command", "/p1/execution_decision"):
            assert payload["pubs"][forbidden] == [], f"{forbidden} must have no publishers: {payload['pubs'][forbidden]}"
    finally:
        stop_pair(pair)
    worker_records = read_jsonl(tmp_path / "worker.source.jsonl")
    regulator_records = read_jsonl(tmp_path / "regulator.source.jsonl")
    summaries = [r for r in worker_records if r.get("type") == "worker_summary"]
    assert len(summaries) == 1
    assert summaries[0]["fatal"] is False
    assert summaries[0]["dry_run_mode"] is True
    assert summaries[0]["completed_jobs"] >= 3
    source = [r for r in regulator_records if r.get("type") == "source_summary"]
    assert len(source) == 1
    assert source[0]["generated"] == source[0]["emitted"]
    assert source[0]["dropped"] == 0
