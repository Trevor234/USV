#!/usr/bin/env python3
"""实船调试服务接管监督器 (research_commissioning 后端唯一入口)。

职责边界（这部分是本次交付的全部承诺）:
  * 在**同一个** usv-system.service 里托管 p1_solver_worker + p1_regulator;
  * 只观测真实输入、只发布 /p1/commissioning_status，不产生任何推力；
  * 任一门失败就在原地有界关闭并说清原因，不自动重启、不自动回退、不自动解锁。

它**不是**航行控制器，也不证明实船闭环：physical_output_enabled / closed_loop_verified
永远是 false。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 1

SUPERVISOR_SCHEMA = "p1-shipboard-supervisor-v1"
STATUS_SCHEMA = "p1-shipboard-commissioning-status-v1"
CAPABILITY_SCHEMA = "p1-worker-capability-v2"
CONTRACT_SCHEMA = "p1-shipboard-commissioning-v1"

STARTUP_DEADLINE_NS = 30 * 1_000_000_000
STATUS_STALE_NS = 2_500_000_000          # ready 之后 status 无新 seq
EVIDENCE_LIMIT_BYTES = 64 * 1024 * 1024
FREE_SPACE_FLOOR_BYTES = 512 * 1024 * 1024
FREE_SPACE_START_BYTES = 1 * 1024 * 1024 * 1024
TERM_GRACE_S = 3.0
KILL_GRACE_S = 1.0
TOTAL_SHUTDOWN_BUDGET_S = 8.0

FORBIDDEN_DOMAIN = 224


class SupervisorFailure(RuntimeError):
    """任何一条落在这个异常上的路径都会走统一的 finally 收尾。"""


def now_ns() -> int:
    return time.monotonic_ns()


def utc_ns() -> int:
    return time.time_ns()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: str) -> dict:
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def proc_starttime(pid: int) -> int:
    with open(f"/proc/{pid}/stat", "rb") as handle:
        fields = handle.read().decode("utf-8", "replace").rsplit(") ", 1)[-1].split()
    # rsplit 之后 fields[0] 是 state，starttime 是原始第 22 字段。
    return int(fields[19])


def proc_exe(pid: int) -> str:
    return os.path.realpath(f"/proc/{pid}/exe")


def proc_identity(pid: int, with_sha: bool) -> dict:
    out = {"pid": pid}
    try:
        out["starttime"] = proc_starttime(pid)
        exe = proc_exe(pid)
        out["actual_exe"] = exe
        out["actual_exe_sha256"] = sha256_file(exe) if with_sha else None
    except OSError:
        out["starttime"] = None
        out["actual_exe"] = None
        out["actual_exe_sha256"] = None
    return out


def tree_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def die(message: str) -> None:
    print(f"supervisor fatal: {message}", file=sys.stderr)
    raise SystemExit(EXIT_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="USV 方案A 实船调试服务接管监督器")
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--underlay", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--plan", required=True)
    return parser.parse_args(argv)


def verify_release_layout(release_root: str, underlay: str) -> dict:
    """发布根的每一项都必须是真实目录/文件：缺一项就停，不去猜。"""
    facts = {}
    for name in ("capsule", "install", "runs", "deploy", "evidence"):
        path = os.path.join(release_root, name)
        if not os.path.isdir(path):
            die(f"release layout missing directory: {path}")
        facts[name] = path
    for name in ("local_setup.bash",):
        path = os.path.join(underlay, name)
        if not os.path.isfile(path):
            die(f"underlay missing {name}: {path}")
    for relative in (
        "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_solver_worker",
        "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_regulator",
        "install/usv_research_safety_cpp/lib/usv_research_safety_cpp/run_shipboard_commissioning.py",
        "install/local_setup.bash",
        "deploy/commission_scheme_a.py",
        "deploy/capture_release_identity.py",
        "evidence/release_artifacts.json",
        "evidence/release_identity.json",
    ):
        path = os.path.join(release_root, relative)
        if not os.path.isfile(path):
            die(f"release artifact missing: {path}")
    return facts


def verify_release_artifacts(release_root: str) -> dict:
    """release_artifacts.json 覆盖的每个文件都必须字节相符。"""
    manifest_path = os.path.join(release_root, "evidence", "release_artifacts.json")
    manifest = read_json(manifest_path)
    records = manifest.get("artifacts")
    if not isinstance(records, list) or not records:
        die("release_artifacts.json has no artifacts")
    for record in records:
        relative = record.get("path")
        digest = record.get("sha256")
        if not relative or not digest:
            die("release_artifacts.json record missing path/sha256")
        path = os.path.join(release_root, relative)
        if not os.path.isfile(path):
            die(f"declared artifact missing: {relative}")
        if sha256_file(path) != digest:
            die(f"declared artifact drifted: {relative}")
    return manifest


def verify_identity_binding(release_root: str, contract_sha: str, plan_sha: str,
                            underlay_identity_sha: str) -> dict:
    """release_identity.json 绑定三份完整摘要；不一致即停。"""
    identity = read_json(os.path.join(release_root, "evidence", "release_identity.json"))
    checks = {
        "source_hashes_sha256": os.path.join(release_root, "evidence", "source_hashes.json"),
        "install_manifest_sha256": os.path.join(release_root, "evidence", "install_manifest.json"),
        "release_artifacts_sha256": os.path.join(release_root, "evidence", "release_artifacts.json"),
    }
    for key, path in checks.items():
        expected = identity.get(key)
        if not expected:
            die(f"release_identity missing {key}")
        if sha256_file(path) != expected:
            die(f"release_identity binding drifted: {key}")
    if identity.get("contract_sha256") not in (None, contract_sha):
        die("release_identity contract binding drifted")
    if identity.get("plan_sha256") not in (None, plan_sha):
        die("release_identity plan binding drifted")
    if identity.get("underlay_identity_sha256") not in (None, underlay_identity_sha):
        die("release_identity underlay binding drifted")
    return identity


def verify_contract(path: str, expected_sha: str) -> dict:
    if not os.path.isfile(path):
        die(f"contract missing: {path}")
    digest = sha256_file(path)
    if digest != expected_sha:
        die(f"contract hash mismatch: {digest} != {expected_sha}")
    contract = read_json(path)
    if contract.get("schema") != CONTRACT_SCHEMA:
        die("contract schema is not the shipboard commissioning profile")
    if contract.get("qualification") != "shipboard_commissioning":
        die("contract qualification is not shipboard_commissioning")
    if contract.get("execute_qualified") is not False:
        die("contract claims execute qualification")
    if contract.get("parameters_are_diagnostic_only") is not True:
        die("contract parameters are not declared diagnostic-only")
    if contract.get("fault_injection_enabled") is not False:
        die("contract enables fault injection")
    return contract


OVERRIDDEN_OR_RESEARCH_PACKAGES = frozenset({
    "usv_acados",
    "usv_nmpc",
    "usv_research_interfaces",
    "usv_research_safety_cpp",
    "usv_bringup",
})


def _underlay_editable_python_paths(underlay: str) -> set[str]:
    """返回宿主 underlay 非研究包 .egg-link 指向的合法 <ws>/build/<pkg>/... 路径集合。"""
    underlay_real = os.path.realpath(underlay)
    ws_build_root = os.path.realpath(os.path.join(os.path.dirname(underlay_real), "build"))
    verified: set[str] = set()
    if not os.path.isdir(underlay_real):
        return verified
    try:
        pkg_names = sorted(os.listdir(underlay_real))
    except OSError:
        return verified
    for pkg in pkg_names:
        if pkg in OVERRIDDEN_OR_RESEARCH_PACKAGES:
            continue
        pkg_dir = os.path.join(underlay_real, pkg)
        if not os.path.isdir(pkg_dir):
            continue
        pkg_build = os.path.realpath(os.path.join(ws_build_root, pkg))
        pattern = os.path.join(pkg_dir, "lib", "python*", "site-packages", "*.egg-link")
        for egg_link in sorted(glob.glob(pattern)):
            try:
                with open(egg_link, "r", encoding="utf-8") as handle:
                    first_line = next((line.strip() for line in handle if line.strip()), "")
            except OSError:
                continue
            if not first_line:
                continue
            target = os.path.realpath(first_line)
            if (target == pkg_build or target.startswith(pkg_build + os.sep)) and os.path.isdir(target):
                verified.add(target)
    return verified


def clean_environment(release_root: str, underlay: str, identity: dict) -> dict:
    """只保留白名单 ROS/DDS 值与两层已绑定前缀；不继承研究域的隔离变量。"""
    env = {
        "HOME": os.environ.get("HOME", "/home/trevor"),
        "USER": os.environ.get("USER", "trevor"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "ACADOS_SOURCE_DIR": os.environ.get("ACADOS_SOURCE_DIR", "/home/trevor/acados"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    domain = identity.get("ros_domain_id")
    if domain is None:
        die("release_identity missing verified ros_domain_id")
    if int(domain) == FORBIDDEN_DOMAIN:
        die("production ros_domain_id must not equal the research domain 224")
    env["ROS_DOMAIN_ID"] = str(int(domain))
    env["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
    env["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "SUBNET"
    for name in ("FASTDDS_DEFAULT_PROFILES_FILE", "FASTRTPS_DEFAULT_PROFILES_FILE"):
        profile = identity.get("dds_profile_path")
        if not profile:
            die("release_identity missing dds_profile_path")
        if sha256_file(profile) != identity.get("dds_profile_sha256"):
            die(f"DDS profile drifted from the production bytes: {name}")
        env[name] = profile
    env.pop("ROS_LOCALHOST_ONLY", None)

    # 两层（旧 install underlay + 新发布 install）之外的前缀一律拒绝。
    acados_real = os.path.realpath("/home/trevor/acados")
    allowed = [
        os.path.realpath("/opt/ros/jazzy"),
        os.path.realpath(underlay),
        os.path.realpath(release_root),
        acados_real,
    ]
    underlay_editable = _underlay_editable_python_paths(underlay)
    for name in ("LD_LIBRARY_PATH", "PYTHONPATH", "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH"):
        inherited = os.environ.get(name, "")
        kept = []
        for entry in [item for item in inherited.split(":") if item]:
            resolved = os.path.realpath(entry)
            if any(resolved == base or resolved.startswith(base + os.sep) for base in allowed):
                kept.append(entry)
            elif name == "PYTHONPATH" and resolved in underlay_editable:
                # 宿主 underlay 非研究包（如 ntrip_client）的 editable 构建路径不传给 C++ 子进程
                continue
            else:
                die(f"{name} entry outside the two bound prefixes: {entry}")
        if name == "LD_LIBRARY_PATH":
            acados_lib = os.path.join(acados_real, "lib")
            if os.path.isdir(acados_lib) and not any(os.path.realpath(item) == acados_lib for item in kept):
                kept.append(acados_lib)
        if kept:
            env[name] = ":".join(kept)
    return env


def check_free_space(path: str, floor: int, where: str) -> int:
    usage = shutil.disk_usage(path)
    if usage.free < floor:
        die(f"{where} free space {usage.free} below floor {floor}")
    return usage.free


class Supervisor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.release_root = os.path.realpath(args.release_root)
        self.underlay = os.path.realpath(args.underlay)
        self.run_root = os.path.realpath(args.run_root)
        self.contract_path = os.path.realpath(args.contract)
        self.plan_path = os.path.realpath(args.plan)
        self.invocation_id = (os.environ.get("INVOCATION_ID") or "").strip()
        self.run_dir = os.path.join(self.run_root, self.invocation_id)
        self.host_boot_id = self._host_boot_id()
        self.boot_id = str(uuid.uuid4())
        self.run_id = str(uuid.uuid4())
        self.started_ns = now_ns()
        self.children: list[tuple[str, subprocess.Popen]] = []
        self.child_identity: dict[str, dict] = {}
        self.node = None
        self.executor = None
        self.log_handle = None
        self.latest_status: dict | None = None
        self.latest_status_ns = 0
        self.latest_capability: dict | None = None
        self.latest_capability_ns = 0
        self.last_seq = -1
        self.ready = False
        self.ready_ns = 0
        self.failure = ""
        self.contract: dict = {}
        self.contract_sha = ""
        self.plan_sha = ""
        self.attestation_sha = ""
        self.attestation_deadline_ns = 0
        self.evidence_closed = False

    # ---------------------------------------------------------------- 基础设施
    @staticmethod
    def _host_boot_id() -> str:
        with open("/proc/sys/kernel/random/boot_id", "rb") as handle:
            return handle.read().decode().strip()

    def record(self, event: str, **fields) -> None:
        if self.log_handle is None:
            return
        doc = {
            "schema": SUPERVISOR_SCHEMA,
            "event": event,
            "invocation_id": self.invocation_id,
            "run_id": self.run_id,
            "boot_id": self.boot_id,
            "host_boot_id": self.host_boot_id,
            "at_ns": now_ns(),
            "at_utc_ns": utc_ns(),
        }
        doc.update(fields)
        self.log_handle.write(json.dumps(doc, sort_keys=False) + "\n")
        self.log_handle.flush()

    def run_path(self, name: str) -> str:
        return os.path.join(self.run_dir, name)

    # ------------------------------------------------------------------ 准备
    def prepare(self) -> None:
        if not self.invocation_id or len(self.invocation_id) > 64 or "/" in self.invocation_id:
            die("a legal systemd INVOCATION_ID is required")
        verify_release_layout(self.release_root, self.underlay)
        if not os.path.isdir(self.run_root):
            die(f"run root missing: {self.run_root}")
        check_free_space(self.run_root, FREE_SPACE_START_BYTES, "run root at startup")
        try:
            os.mkdir(self.run_dir, 0o700)
        except FileExistsError:
            die(f"run directory already exists (refusing to reuse bytes): {self.run_dir}")
        except OSError as error:
            die(f"cannot create run directory: {error}")

        artifacts = verify_release_artifacts(self.release_root)
        self.contract_sha = sha256_file(self.contract_path)
        self.plan_sha = sha256_file(self.plan_path)
        self.contract = verify_contract(self.contract_path, self.contract_sha)
        self.identity = verify_identity_binding(
            self.release_root, self.contract_sha, self.plan_sha,
            artifacts.get("underlay_identity_sha256", ""))
        self.env = clean_environment(self.release_root, self.underlay, self.identity)
        self._verify_attestation()

        # 合同/计划原字节复制进 run，绑定这次运行。
        shutil.copyfile(self.contract_path, self.run_path("contract.json"))
        shutil.copyfile(self.plan_path, self.run_path("plan.json"))
        if sha256_file(self.run_path("contract.json")) != self.contract_sha:
            die("copied contract drifted")
        if sha256_file(self.run_path("plan.json")) != self.plan_sha:
            die("copied plan drifted")

        self.log_handle = open(self.run_path("supervisor.jsonl"), "a", buffering=1,
                               encoding="utf-8")
        self.record("startup",
                    contract_sha256=self.contract_sha, plan_sha256=self.plan_sha,
                    release_root=self.release_root, underlay=self.underlay,
                    ros_domain_id=self.env.get("ROS_DOMAIN_ID"),
                    rmw_implementation=self.env.get("RMW_IMPLEMENTATION"),
                    discovery_range=self.env.get("ROS_AUTOMATIC_DISCOVERY_RANGE"),
                    attestation_sha256=self.attestation_sha,
                    attestation_valid_until_utc_ns=self.attestation_deadline_ns,
                    evidence_limit_bytes=EVIDENCE_LIMIT_BYTES,
                    physical_output_enabled=False,
                    jobs_submitted=0)

    def _verify_attestation(self) -> None:
        path = os.path.join(self.release_root, "evidence", "operator-attestation.json")
        if not os.path.isfile(path):
            die("operator attestation missing: this run has no on-site declaration")
        self.attestation_sha = sha256_file(path)
        declaration = read_json(path)
        deadline = declaration.get("valid_until_utc")
        if deadline is None:
            die("operator attestation has no valid_until_utc")
        self.attestation_deadline_ns = int(deadline)
        if self.attestation_deadline_ns <= utc_ns():
            die("operator attestation already expired")

    # ------------------------------------------------------------- DDS 预检
    def preflight_graph(self) -> None:
        """启动前只读 graph：用独立 rclpy.Context 探测，销毁后不干扰监督器 Context。"""
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node

        ctx = rclpy.Context()
        ctx.init(args=None)
        probe = Node("p1_commissioning_preflight", context=ctx)
        executor = SingleThreadedExecutor(context=ctx)
        executor.add_node(probe)
        deadline = now_ns() + 3 * 1_000_000_000
        offenders: list[str] = []
        try:
            while now_ns() < deadline:
                executor.spin_once(timeout_sec=0.1)
                offenders = [f"{name}/{namespace}"
                             for name, namespace in probe.get_node_names_and_namespaces()
                             if name.startswith("p1_") and name not in ("p1_commissioning_preflight",)]
                if offenders:
                    break
        finally:
            try:
                executor.remove_node(probe)
                probe.destroy_node()
            finally:
                ctx.try_shutdown()
        if offenders:
            die(f"foreign p1 nodes already in the graph: {sorted(set(offenders))}")
        # 预检独立 Context 已销毁；随后的 supervisor 用默认 Context 启动自己的 DDS 参与者。

    # ---------------------------------------------------------------- 子进程
    def spawn(self) -> None:
        binary_dir = os.path.join(
            self.release_root, "install", "usv_research_safety_cpp", "lib",
            "usv_research_safety_cpp")
        worker = os.path.join(binary_dir, "p1_solver_worker")
        regulator = os.path.join(binary_dir, "p1_regulator")
        for path in (worker, regulator):
            if not os.access(path, os.X_OK):
                die(f"missing executable: {path}")
        common = [
            "--ros-args",
            "-p", f"run_id:={self.run_id}",
            "-p", f"boot_id:={self.boot_id}",
            "-p", f"contract_file:={self.run_path('contract.json')}",
            "-p", f"contract_hash:={self.contract_sha}",
            "-p", f"model_plan_file:={self.run_path('plan.json')}",
            "-p", f"model_plan_sha256:={self.plan_sha}",
            "-p", "mode:=commissioning",
        ]
        worker_log = open(self.run_path("worker.stdout.txt"), "ab", buffering=0)
        self._spawn_child("worker", [worker] + common + [
            "-p", f"source_file:={self.run_path('worker.source.jsonl')}"], worker_log)
        # regulator 必须拿到**真实** PID，不能等任何外部进程，也不能用 0。
        regulator_log = open(self.run_path("regulator.stdout.txt"), "ab", buffering=0)
        self._spawn_child("regulator", [regulator] + common + [
            "-p", f"source_file:={self.run_path('regulator.source.jsonl')}",
            "-p", f"worker_pid:={self.children[0][1].pid}"], regulator_log)
        self.record("startup",
                    phase="spawned",
                    processes={name: proc_identity(proc.pid, True)
                               for name, proc in self.children})

    def _spawn_child(self, name: str, argv: list[str], log) -> None:
        proc = subprocess.Popen(argv, env=self.env, stdout=log, stderr=log,
                                start_new_session=False, close_fds=True)
        self.children.append((name, proc))
        self.child_identity[name] = {"pid": proc.pid, "starttime": proc_starttime(proc.pid),
                                     "exe": proc_exe(proc.pid)}

    # ------------------------------------------------------------- DDS 监督器
    def make_node(self) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String
        from usv_research_interfaces.msg import WorkerCapability

        rclpy.init(args=None)
        self.node = Node("p1_commissioning_supervisor")
        qos = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST,
                         reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        # 只订阅不发布：监督器绝不产生执行侧流量。
        self.node.create_subscription(String, "/p1/commissioning_status",
                                      self._on_status, qos)
        self.node.create_subscription(WorkerCapability, "/p1/worker_capability",
                                      self._on_capability, qos)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)

    def _on_status(self, message) -> None:
        try:
            status = json.loads(message.data)
        except ValueError:
            self.failure = "commissioning_status_unparsable"
            return
        self.latest_status = status
        self.latest_status_ns = now_ns()

    def _on_capability(self, message) -> None:
        self.latest_capability = {
            "schema_version": message.schema_version, "run_id": message.run_id,
            "boot_id": message.boot_id, "contract_hash": message.contract_hash,
            "nominal_hash": message.nominal_hash, "worker_instance": message.worker_instance,
            "clock_name": message.clock_name, "backend": message.backend,
            "matrix_layout": message.matrix_layout, "horizon_steps": message.horizon_steps,
            "prediction_dt": message.prediction_dt, "pid": message.pid,
            "startup_ns": message.startup_ns, "completed_jobs": message.completed_jobs,
            "active_job": message.active_job, "pending_count": message.pending_count,
            "fault_injection_enabled": message.fault_injection_enabled,
            "fatal": message.fatal, "reason": message.reason,
            "model_runtime_ready": message.model_runtime_ready,
            "model_plan_sha256": message.model_plan_sha256,
            "applied_generation": message.applied_generation,
        }
        self.latest_capability_ns = now_ns()

    # -------------------------------------------------------------- 监督循环
    def sample(self) -> None:
        now = now_ns()
        if self.failure:
            return
        for name, proc in self.children:
            code = proc.poll()
            if code is not None:
                self.failure = f"commissioning_child_exit:{name}:rc={code}"
                return
        for name, proc in self.children:
            identity = self.child_identity[name]
            try:
                if proc_starttime(proc.pid) != identity["starttime"]:
                    self.failure = f"commissioning_child_identity_changed:{name}"
                    return
                if proc_exe(proc.pid) != identity["exe"]:
                    self.failure = f"commissioning_child_identity_changed:{name}"
                    return
            except OSError:
                self.failure = f"commissioning_child_exit:{name}"
                return
        # 证据上限：先看本 run 体量，再看全盘余量。
        try:
            used = tree_bytes(self.run_dir)
            usage = shutil.disk_usage(self.run_root)
        except OSError as error:
            self.failure = f"commissioning_evidence_unreadable:{error}"
            return
        if used > EVIDENCE_LIMIT_BYTES or usage.free < FREE_SPACE_FLOOR_BYTES:
            self.failure = "commissioning_evidence_limit"
            return
        # 声明到期：运行中不续签。
        if self.attestation_deadline_ns and utc_ns() >= self.attestation_deadline_ns:
            self.failure = "commissioning_authorisation_expired"
            return
        status = self.latest_status
        if status is None:
            if now - self.started_ns > STARTUP_DEADLINE_NS:
                self.failure = "commissioning_startup_timeout"
            return
        if status.get("schema") != STATUS_SCHEMA:
            self.failure = "commissioning_status_schema_mismatch"
            return
        for key, expected in (("run_id", self.run_id), ("boot_id", self.boot_id),
                              ("contract_hash", self.contract_sha),
                              ("plan_sha256", self.plan_sha)):
            if status.get(key) != expected:
                self.failure = f"commissioning_status_identity_mismatch:{key}"
                return
        seq = status.get("seq")
        if not isinstance(seq, int):
            self.failure = "commissioning_status_sequence_invalid"
            return
        if seq != self.last_seq:
            self.last_seq = seq
        if not self.ready:
            capability_ready = bool(self.latest_capability and
                                    self.latest_capability.get("model_runtime_ready"))
            if status.get("phase") == "ready" and capability_ready:
                self.ready = True
                self.ready_ns = now
                self.record("sample", phase="ready", status_received_ns=self.latest_status_ns,
                            worker_capability_received_ns=self.latest_capability_ns,
                            regulator_status=status,
                            processes={name: proc_identity(proc.pid, True)
                                       for name, proc in self.children},
                            full_identity=True)
                return
            if now - self.started_ns > STARTUP_DEADLINE_NS:
                self.failure = "commissioning_startup_timeout"
            return
        if now - self.latest_status_ns > STATUS_STALE_NS:
            self.failure = "commissioning_status_stale"
            return
        self.record("sample", phase=status.get("phase"),
                    status_received_ns=self.latest_status_ns,
                    worker_capability_received_ns=self.latest_capability_ns,
                    regulator_status=status,
                    processes={name: proc_identity(proc.pid, False)
                               for name, proc in self.children})

    # ---------------------------------------------------------------- 收尾
    def shutdown(self) -> None:
        deadline = now_ns() + int(TOTAL_SHUTDOWN_BUDGET_S * 1_000_000_000)
        # 先 regulator 再 worker；每次发信号前核对 PID/starttime/exe。
        for name, proc in reversed(self.children):
            if proc.poll() is not None:
                continue
            identity = self.child_identity[name]
            try:
                if proc_starttime(proc.pid) != identity["starttime"] or \
                        proc_exe(proc.pid) != identity["exe"]:
                    continue  # PID 已被复用：绝不能对陌生进程发信号。
            except OSError:
                continue
            try:
                proc.terminate()
            except OSError:
                continue
            self._wait_exit(proc, min(TERM_GRACE_S, max(0.0, (deadline - now_ns()) / 1e9)))
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
                self._wait_exit(proc, min(KILL_GRACE_S, max(0.0, (deadline - now_ns()) / 1e9)))
        if self.node is not None:
            try:
                self.executor.remove_node(self.node)
                self.node.destroy_node()
            except Exception:
                pass
            self.node = None
            try:
                import rclpy
                rclpy.shutdown()
            except Exception:
                pass

    @staticmethod
    def _wait_exit(proc: subprocess.Popen, seconds: float) -> None:
        try:
            proc.wait(timeout=max(0.0, seconds))
        except subprocess.TimeoutExpired:
            pass

    # ------------------------------------------------------------------ 主循环
    def run(self) -> int:
        self.prepare()
        self.preflight_graph()
        self.make_node()
        self.spawn()
        self.record("sample", phase="supervising",
                    processes={name: proc_identity(proc.pid, True)
                               for name, proc in self.children})
        while not self.failure:
            self.executor.spin_once(timeout_sec=0.2)
            self.sample()
            time.sleep(0.8)
        self.record("failure", reason=self.failure, phase=self.latest_status.get("phase")
                    if self.latest_status else "starting",
                    ready=self.ready, seq=self.last_seq)
        return EXIT_FAIL if self.failure else EXIT_OK


class _CleanStopSignal(BaseException):
    """收到 SIGTERM/SIGINT 时触发有界收尾，不标记为 failure。"""


def _install_stop_handlers() -> None:
    def _handle(signum, _frame):
        # 进入收尾前屏蔽重复信号（例如 systemd SIGTERM 后紧跟 launch SIGINT）。
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise _CleanStopSignal(signum)

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    supervisor = Supervisor(args)
    exit_code = EXIT_FAIL
    _install_stop_handlers()
    try:
        exit_code = supervisor.run()
    except _CleanStopSignal:
        exit_code = EXIT_OK
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001 - 统一 finally 收尾
        supervisor.failure = supervisor.failure or f"commissioning_supervisor_error:{error}"
        print(f"supervisor exception: {error}", file=sys.stderr)
        exit_code = EXIT_FAIL
    finally:
        try:
            supervisor.shutdown()
        finally:
            if supervisor.log_handle is not None:
                supervisor.record(
                    "shutdown", reason=supervisor.failure or "clean_stop",
                    exit_code=exit_code, ready=supervisor.ready,
                    evidence_closed=True,
                    physical_output_enabled=False, jobs_submitted=0)
                supervisor.log_handle.flush()
                supervisor.log_handle.close()
                supervisor.log_handle = None
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
