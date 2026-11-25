#!/usr/bin/env python3
# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""方案 A 受控仿真闭环运行器（v2）。

它是**唯一的场景权威**：每个场景显式声明停止条件、故障开关、刺激与必须出现的
证据，不用"名字 + 默认时长"这种只能当标签用的表。

启动顺序是门控的，不是 sleep 猜的：
    plant → plant_ready → worker → 读 worker pid → regulator(worker_pid) →
    worker_recording_ready → regulator

刺激只走**真实类型化通道**（PlantCommand），不改任何节点日志；刺激行单独写进
stimulus.source.jsonl，节点自己的 source 保持无缝。

停机按 regulator → worker → plant 依次 SIGTERM，超时才 SIGKILL；写 run.json 之前
先过排空门（各 source 末行必须是该节点 summary 且完整结束事实成立）。
"""
from __future__ import annotations

import argparse
import hashlib
import math
import random
import threading
import uuid
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

T_NS = 200_000_000
DEADLINE_NS = 150_000_000

# 机动生成器与机动名清单已抽到 learning/maneuver_reference.py（场景权威唯一副本；
# 训练侧 usv_rl.reference.make_maneuver_reference 按路径加载同一文件）。
# 运行器用 `python3 <path>` 启动，sys.path[0] 是本 scripts 目录，故显式加入 learning。
_LEARNING_DIR = Path(__file__).resolve().parents[3] / "learning"
if not (_LEARNING_DIR / "maneuver_reference.py").is_file():
    raise SystemExit(f"缺少机动生成器: {_LEARNING_DIR / 'maneuver_reference.py'}")
if str(_LEARNING_DIR) not in sys.path:
    sys.path.insert(0, str(_LEARNING_DIR))
from maneuver_reference import (  # noqa: E402
    MANEUVER_TYPES,
    _smooth_step,
    generate_maneuver_path_and_profile,
)
from ppo_proposal_node import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    DEFAULT_MODEL_PATH,
    GATE_DEFAULTS,
    add_gate_arguments,
    gate_cli_args,
)

# 场景：停止条件 / 故障 / 刺激 / 必须出现的证据。required 词表由检查器解释。
def as_int(value):
    """证据字段一律按整数解析；非整数一律返回 None，绝不猜。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


SCENARIOS = {
    "pre_switch": {
        # 5 拍不足以越过 activation_tolerance 的位移门槛（会误判"状态没变"）；
        # 12 拍仍完全在模型切换之前，判据本身不变。
        "stop_criterion": {"decisions": 12},
        "faults": False,
        "stimuli": [],
        "required": ["commands_paired", "single_execution_per_tick",
                     "nonzero_execution", "anchor_from_receipt",
                     "state_progress", "steady_domain_consistent", "no_test_seams"],
    },
    "model_switch": {
        "stop_criterion": {"decisions": 60},
        "faults": False,
        "stimuli": [],
        "required": ["commands_paired", "single_execution_per_tick",
                     "nonzero_execution", "generation_coverage",
                     "anchor_from_receipt", "state_progress",
                     "steady_domain_consistent", "no_test_seams"],
    },
    "late_command": {
        "stop_criterion": {"decisions": 25},
        "faults": True,
        "stimuli": ["late"],
        "required": ["commands_paired", "single_execution_per_tick",
                     "nonzero_execution", "anchor_from_receipt",
                     "state_progress", "steady_domain_consistent",
                     "stimulus:late", "no_test_seams"],
    },
    "duplicate_command": {
        "stop_criterion": {"decisions": 25},
        "faults": True,
        "stimuli": ["duplicate"],
        "required": ["commands_paired", "single_execution_per_tick",
                     "nonzero_execution", "anchor_from_receipt",
                     "state_progress", "steady_domain_consistent",
                     "stimulus:duplicate", "no_test_seams"],
    },
    "hold_expiry": {
        "stop_criterion": {"decisions": 25},
        "faults": True,
        "stimuli": ["hold_expiry"],
        "required": ["commands_paired", "single_execution_per_tick",
                     "nonzero_execution", "anchor_from_receipt",
                     "state_progress", "steady_domain_consistent",
                     "stimulus:hold_expiry", "no_test_seams"],
    },
    "worker_expiry": {
        "stop_criterion": {"decisions": 25},
        "faults": True,
        "stimuli": [],
        "required": ["commands_paired", "single_execution_per_tick",
                     "nonzero_execution", "anchor_from_receipt",
                     "job_refused_nonterminal", "state_progress",
                     "steady_domain_consistent", "no_test_seams"],
    },
    "stop_truncation": {
        "stop_criterion": {"decisions": 12},
        "faults": True,
        "stimuli": [],
        "stop_mode": "regulator_mid_window",
        "required": ["commands_paired", "single_execution_per_tick",
                     "nonzero_execution", "anchor_from_receipt",
                     "stop_hold_close", "steady_domain_consistent", "no_test_seams"],
    },
    "no_command_free_evolution": {
        "stop_criterion": {"seconds": 3.0},
        "faults": False,
        "stimuli": [],
        "nodes": "plant_only",
        "required": ["no_commands", "free_evolution", "no_test_seams"],
    },
}

NODE_ORDER = ("plant", "worker", "regulator")
STOP_ORDER = ("regulator", "worker", "plant")
SOURCE_SUMMARY = {
    "regulator": "source_summary",
    "worker": "worker_summary",
    "plant": "plant_summary",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 取证开关：只在显式 --clock-diagnostics 下启用；默认路径与原版完全一致。
# ---------------------------------------------------------------------------

PID1_CGROUP = "/system.slice/usv-system.service"
PROD_UNIT = "usv-system.service"
PROD_DEFAULTS = Path("/etc/default/usv-system")
RUNTIME_LINK = Path("/home/trevor/usv_runtime")
ROS_IMAGE_MARKERS = ("librclcpp.so", "librcl.so", "librmw", "librmw_fastrtps",
                     "librmw_cyclonedds", "libfastrtps", "libddsc")
ROS_NODE_NAMES = {"p1_regulator", "p1_x86_plant", "p1_solver_worker", "mavros_node",
                  "ros2", "controller_manager", "nav2_controller", "ekf_node"}


def host_boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


def proc_field(pid: int, index: int) -> str | None:
    """读取 /proc/<pid>/stat 的 1-based 字段（comm 可含空格与括号）。"""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    rest = raw[close + 2:].split()
    # stat 的第 3 个字段就是 comm 之后的第一项，故 index-3 是偏移。
    pos = index - 3
    if pos < 0 or pos >= len(rest):
        return None
    return rest[pos]


def proc_starttime(pid: int) -> int | None:
    value = proc_field(pid, 22)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def proc_exe(pid: int) -> str | None:
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def proc_cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def proc_cgroup(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cgroup").read_text()
    except OSError:
        return ""


def proc_environ(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for part in raw.split(b"\0"):
        if b"=" in part:
            key, _, value = part.partition(b"=")
            out[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return out


def proc_maps(pid: int) -> list[str] | None:
    try:
        return Path(f"/proc/{pid}/maps").read_text().splitlines()
    except OSError:
        return None


def ancestors_of(pid: int) -> set[int]:
    seen: set[int] = set()
    current = pid
    for _ in range(64):
        parent = proc_field(current, 4)
        if parent is None:
            break
        try:
            current = int(parent)
        except ValueError:
            break
        if current <= 1 or current in seen:
            break
        seen.add(current)
    return seen


def domain_from(env: dict[str, str], cmdline: list[str]) -> int | None:
    for key in ("ROS_DOMAIN_ID",):
        if key in env:
            try:
                return int(env[key])
            except ValueError:
                return None
    for i, token in enumerate(cmdline):
        if token == "--ros-domain-id" and i + 1 < len(cmdline):
            try:
                return int(cmdline[i + 1])
            except ValueError:
                return None
        if token.startswith("--ros-domain-id="):
            try:
                return int(token.split("=", 1)[1])
            except ValueError:
                return None
    return None


def is_ros_process(maps: list[str] | None, exe: str | None, cmdline: list[str]) -> bool:
    if maps:
        for line in maps:
            if any(marker in line for marker in ROS_IMAGE_MARKERS):
                return True
    if exe and Path(exe).name in ROS_NODE_NAMES:
        return True
    return any(Path(token).name in ROS_NODE_NAMES for token in cmdline if token)


def scan_domain_gate(domain: int, own_pid: int, own_children: set[int],
                     ignore_cgroup: str) -> dict:
    """只读扫描 /proc，判定目标域是否被别的 ROS 进程占用。

    承认局限：/proc 扫描不能证明所有程序化 DDS 配置的域，也无法枚举容器内
    进程；因此这里只做**保守拒绝**，不用 /dev/shm 文件名猜域。
    """
    related: list[dict] = []
    unrelated: list[dict] = []
    unverifiable: list[dict] = []
    blocked: list[str] = []
    skip = {own_pid} | ancestors_of(own_pid) | set(own_children)
    for entry in sorted(os.listdir("/proc")):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in skip or pid <= 1:
            continue
        cgroup = proc_cgroup(pid)
        cmdline = proc_cmdline(pid)
        exe = proc_exe(pid)
        env = proc_environ(pid)
        maps = proc_maps(pid)
        production = ignore_cgroup and ignore_cgroup in cgroup
        ros = is_ros_process(maps, exe, cmdline)
        observed = domain_from(env, cmdline)
        record = {"pid": pid, "exe": exe, "command": cmdline[:6],
                  "domain": observed, "production": production,
                  "ros_related": ros,
                  "starttime": proc_starttime(pid)}
        if production:
            related.append(record)
            if observed == domain:
                blocked.append(f"production_process_on_target_domain:{pid}")
            continue
        if env is None and maps is None and not cmdline:
            unverifiable.append(record)
            continue
        if ros:
            related.append(record)
            if observed is None:
                blocked.append(f"ros_process_domain_unknown:{pid}")
            elif observed == domain:
                blocked.append(f"ros_process_on_target_domain:{pid}")
            continue
        if observed == domain:
            unrelated.append(record)
    verdict = "blocked" if blocked else "clear"
    return {"schema": "scheme-a-domain-gate-v1", "target_domain": domain,
            "verdict": verdict, "blocking_reasons": blocked,
            "ros_related_processes": related,
            "unrelated_env_224": unrelated,
            "unverifiable": unverifiable,
            "limitations": ["/proc scan cannot prove programmatic DDS domain settings",
                            "container-internal processes are not enumerated",
                            "/dev/shm file names are not used to infer the domain"]}


def file_digest(path: Path) -> str | None:
    try:
        return sha256(path)
    except OSError:
        return None


def systemctl_show(unit: str, timeout: float = 1.0) -> dict[str, str]:
    props = ("MainPID", "NRestarts", "ActiveState", "SubState",
             "ActiveEnterTimestamp", "ExecStart", "ControlGroup", "FragmentPath",
             "LoadState")
    cmd = ["systemctl", "show", unit] + [f"--property={p}" for p in props]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return {"__error__": "systemctl show timeout or unavailable"}
    if result.returncode != 0:
        return {"__error__": f"systemctl show rc={result.returncode}"}
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key] = value
    return out


def production_snapshot(unit: str = PROD_UNIT) -> dict:
    """生产身份的稳定快照：不含采样时间与负载，便于恒等比较。"""
    props = systemctl_show(unit)
    control_group = props.get("ControlGroup", "")
    pids: list[dict] = []
    if control_group and "__error__" not in props:
        for entry in sorted(os.listdir("/proc")):
            if not entry.isdigit():
                continue
            pid = int(entry)
            cgroup = proc_cgroup(pid)
            if control_group not in cgroup:
                continue
            exe = proc_exe(pid)
            cmdline = proc_cmdline(pid)
            joined = " ".join(cmdline)
            role = ("mavros" if "mavros" in joined or (exe and "mavros" in exe)
                    else "controller" if "controller" in joined or
                    (exe and "controller" in exe) else "other")
            pids.append({"pid": pid, "starttime": proc_starttime(pid),
                         "exe": exe, "role": role})
    runtime_link = None
    runtime_target = None
    try:
        runtime_link = os.readlink(RUNTIME_LINK)
        runtime_target = str(RUNTIME_LINK.resolve())
    except OSError:
        pass
    return {
        "schema": "scheme-a-production-snapshot-v1",
        "unit": unit,
        "systemctl_error": props.get("__error__"),
        "main_pid": props.get("MainPID"),
        "restarts": props.get("NRestarts"),
        "active_state": props.get("ActiveState"),
        "sub_state": props.get("SubState"),
        "active_enter": props.get("ActiveEnterTimestamp"),
        "exec_start": props.get("ExecStart"),
        "control_group": control_group,
        "fragment_path": props.get("FragmentPath"),
        "fragment_sha256": file_digest(Path(props["FragmentPath"]))
        if props.get("FragmentPath") else None,
        "defaults_sha256": file_digest(PROD_DEFAULTS),
        "scheme": os.environ.get("SCHEME"),
        "runtime_link": runtime_link,
        "runtime_target": runtime_target,
        "processes": pids,
    }


PRODUCTION_STABLE_FIELDS = ("main_pid", "restarts", "active_state", "sub_state",
                            "active_enter", "exec_start", "control_group",
                            "fragment_path", "fragment_sha256", "defaults_sha256",
                            "scheme", "runtime_target", "processes")


def production_diff(before: dict, after: dict) -> list[str]:
    changed = []
    for field in PRODUCTION_STABLE_FIELDS:
        if before.get(field) != after.get(field):
            changed.append(field)
    return changed


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    p.add_argument("--out", required=True)
    p.add_argument("--install-root", required=True)
    p.add_argument("--contract", required=True)
    p.add_argument("--contract-hash", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--plan-sha256", required=True)
    p.add_argument("--source-hashes", required=True)
    p.add_argument("--nodes", default="closed_loop",
                   choices=("closed_loop", "plant_only"))
    p.add_argument("--stop-after-decisions", type=int, default=None)
    p.add_argument("--stop-after-s", type=float, default=None)
    p.add_argument("--stimulus", default="none",
                   choices=("none", "late", "duplicate", "hold_expiry"))
    p.add_argument("--stimulus-at-tick", type=int, default=12)
    p.add_argument("--worker-block-ms", type=int, default=0, choices=(0, 250, 400))
    p.add_argument("--stop-mode", default="none",
                   choices=("none", "regulator_mid_window"))
    p.add_argument("--faults", default="off", choices=("off", "on"))
    p.add_argument("--ros-domain-id", type=int, default=224)
    p.add_argument("--keep-partial", action="store_true")
    p.add_argument("--run-id", default=None)
    p.add_argument("--startup-timeout-s", type=float, default=30.0)
    p.add_argument("--grace-s", type=float, default=12.0)
    # 取证开关：默认关闭时保持原行为（含原 run_id 选项字典）。
    p.add_argument("--clock-diagnostics", action="store_true")
    p.add_argument("--candidate-root", default=None)
    p.add_argument("--maneuver", default=None, choices=MANEUVER_TYPES)
    p.add_argument("--maneuver-seed", type=int, default=0)
    p.add_argument("--cruise-speed", type=float, default=None)
    p.add_argument("--plant-model-file", default=None)
    p.add_argument("--dataset-source", default=None)
    p.add_argument("--gp-snapshot", default=None)
    p.add_argument("--gp-snapshot-sha256", default="")
    p.add_argument("--gp-schedule", default=None)
    p.add_argument("--gp-schedule-sha256", default="")
    p.add_argument("--ppo-proposal", action="store_true")
    p.add_argument("--ppo-model", default=str(DEFAULT_MODEL_PATH))
    p.add_argument("--ppo-manifest", default=str(DEFAULT_MANIFEST_PATH))
    p.add_argument("--ppo-lookahead", default="",
                   help="8 个逗号分隔的前瞻弧长偏移（m），透传给 PPO 节点；空 = 节点默认")
    add_gate_arguments(p, prefix="ppo-")
    p.add_argument("--lambda-pi", type=float, default=0.0)
    p.add_argument("--oracle-plant-file", default=None)
    p.add_argument("--align-tick-phase", action="store_true")
    return p


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.ppo_gate = ({name: getattr(args, f"ppo_{name}") for name in GATE_DEFAULTS}
                         if args.ppo_proposal and args.ppo_gate_mode != "none" else {})
        self.out = Path(args.out).resolve()
        self.scenario = SCENARIOS[args.scenario]
        self.names = (("plant",) if (args.nodes == "plant_only" or
                                     self.scenario.get("nodes") == "plant_only")
                      else NODE_ORDER)
        self.procs: dict[str, subprocess.Popen] = {}
        self.ppo_proc: subprocess.Popen | None = None
        self.nodes: dict[str, dict] = {}
        self.failure: str | None = None
        self.stimuli: list[dict] = []
        self.offsets: dict[str, int] = {}
        self.log: list[dict] = []
        self.startup_waits: dict[str, float] = {}
        # --clock-diagnostics 专用状态；关闭时全部保持 None/空。
        self.diag = bool(getattr(args, "clock_diagnostics", False))
        self.candidate_root = (Path(args.candidate_root).resolve()
                               if getattr(args, "candidate_root", None) else None)
        self.domain_gate: dict | None = None
        self.production_before: dict | None = None
        self.production_after: dict | None = None
        self.production_stop = threading.Event()
        self.production_changes: list[str] = []
        self.monitor_thread: threading.Thread | None = None
        self.sampler_thread: threading.Thread | None = None
        self.sampler_stop = threading.Event()
        self.sampler_registry: tuple[tuple[str, int, int], ...] = ()
        self.sampler_samples: list[dict] = []
        self.sampler_error: str | None = None
        self.sampler_started = False
        self.close_phase = False
        self.spawn_evidence: dict[str, dict] = {}
        self.diag_files: dict[str, dict] = {}
        self.stop_identity_failures: list[str] = []

    # -- 基础 ------------------------------------------------------------
    def record(self, kind: str, **fields) -> None:
        row = {"type": kind, **fields}
        self.log.append(row)

    def write_stimulus(self, row: dict) -> None:
        self.stimuli.append(row)
        with open(self.out / "stimulus.source.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    def fail(self, reason: str) -> None:
        if self.failure is None:
            self.failure = reason

    def tail_source(self, name: str, limit: int = 2000) -> list[dict]:
        """增量读取：只解析上次之后新增的行。

        激励器需要 ~1 ms 级响应，而完整读一遍 3 万行要 ~10 ms，正好错过 plant
        释放 pending 槽位的窗口（实测 ~7 ms）。
        """
        path = self.out / f"{name}.source.jsonl"
        if not path.is_file():
            return []
        offset = self.offsets.get(name, 0)
        size = path.stat().st_size
        if size <= offset:
            return []
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read()
        # 只消费到最后一个完整行，残行留到下次。
        cut = chunk.rfind(b"\n")
        if cut < 0:
            return []
        self.offsets[name] = offset + cut + 1
        rows = []
        for line in chunk[:cut].decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"type": "__unparsable__"})
        return rows

    def read_source(self, name: str) -> list[dict]:
        path = self.out / f"{name}.source.jsonl"
        rows: list[dict] = []
        if not path.is_file():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"type": "__unparsable__"})
        return rows

    def wait_for(self, name: str, predicate, timeout: float) -> bool:
        start = time.monotonic()
        while time.monotonic() - start <= timeout:
            if predicate(self.read_source(name)):
                self.startup_waits[name] = round(time.monotonic() - start, 3)
                return True
            if self.procs.get(name) is not None and self.procs[name].poll() is not None:
                self.fail(f"startup_gate:{name}")
                return False
            time.sleep(0.05)
        self.fail(f"startup_gate:{name}")
        return False

    # -- 启动 ------------------------------------------------------------
    def spawn(self, name: str, exe: Path, params: dict) -> None:
        yaml = self.out / f"{name}.params.yaml"
        body = [f"{exe.name}:", "  ros__parameters:"]
        for key, value in params.items():
            body.append(f"    {key}: {json.dumps(value)}")
        yaml.write_text("\n".join(body) + "\n", encoding="utf-8")
        log = self.out / f"{name}.stdout.txt"
        self.procs[name] = subprocess.Popen(
            [str(exe), "--ros-args", "--params-file", str(yaml)],
            stdout=open(log, "w"), stderr=subprocess.STDOUT,
            start_new_session=True)
        self.nodes[name] = {"pid": self.procs[name].pid,
                            "pgid": os.getpgid(self.procs[name].pid),
                            "exe": str(exe), "exe_sha256": sha256(exe),
                            "stop_requested_ns": 0, "rc": None,
                            "wait_ms": 0, "killed": False,
                            "summary_seen": False}
        if self.diag:
            self.nodes[name]["starttime"] = proc_starttime(self.nodes[name]["pid"])
            self.nodes[name]["expected_exe"] = str(exe.resolve())
            self.capture_spawn(name)

    # -- 取证：进程/生产/采样/身份 ---------------------------------------
    def proc_dir(self) -> Path:
        path = self.out / "proc"
        path.mkdir(exist_ok=True)
        return path

    def capture_spawn(self, name: str) -> None:
        node = self.nodes[name]
        record = {
            "schema": "scheme-a-spawn-identity-v1",
            "name": name,
            "pid": node["pid"],
            "popen_pid": self.procs[name].pid,
            "pgid": node["pgid"],
            "starttime": node.get("starttime"),
            "exe": node["exe"],
            "exe_sha256": node["exe_sha256"],
            "host_boot_id": host_boot_id(),
            "captured_ns": time.monotonic_ns(),
        }
        path = self.proc_dir() / f"{name}.spawn.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        self.spawn_evidence.setdefault(name, {})["spawn"] = record

    def expected_shared_sha(self) -> dict[str, str]:
        """安装清单是节点 ELF 摘要的权威来源；缺失即门禁失败。"""
        if not self.candidate_root:
            return {}
        manifest = self.candidate_root / "evidence" / "install_manifest.json"
        if not manifest.is_file():
            self.fail("install_manifest_missing")
            return {}
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.fail("install_manifest_unparsable")
            return {}
        # 清单同时包含普通文件与符号链接项；只有普通文件带 sha256。
        return {entry["path"]: entry["sha256"]
                for entry in document.get("files", [])
                if entry.get("sha256")}

    def capture_ready(self, name: str) -> None:
        """ready 门之后、仍存活时抓取实际 exe、maps 与 ROS/RMW 环境。"""
        node = self.nodes[name]
        pid = node["pid"]
        exe_link = proc_exe(pid)
        maps = proc_maps(pid)
        env = proc_environ(pid)
        keep = {key: value for key, value in env.items()
                if key.startswith(("ROS_", "RMW_", "LD_LIBRARY_PATH", "AMENT_",
                                   "FASTDDS_", "CYCLONEDDS_")) or key == "PATH"}
        actual_sha = file_digest(Path(exe_link)) if exe_link else None
        record = {
            "schema": "scheme-a-ready-identity-v1",
            "name": name,
            "pid": pid,
            "starttime": node.get("starttime"),
            "expected_exe": node.get("expected_exe"),
            "actual_exe_link": exe_link,
            "actual_exe_realpath": str(Path(exe_link).resolve()) if exe_link else None,
            "actual_exe_sha256": actual_sha,
            "maps_readable": maps is not None,
            "ros_env": keep,
            "captured_ns": time.monotonic_ns(),
        }
        if maps is not None:
            (self.proc_dir() / f"{name}.maps.txt").write_text(
                "\n".join(maps) + "\n", encoding="utf-8")
        if exe_link is None:
            self.fail(f"node_exe_unreadable:{name}")
        elif not self.within_candidate(exe_link):
            self.fail(f"node_exe_outside_candidate:{name}")
        elif actual_sha != node["exe_sha256"]:
            self.fail(f"node_exe_sha_mismatch:{name}")
        if maps is None:
            self.fail(f"node_maps_unreadable:{name}")
        else:
            for line in maps:
                parts = line.split()
                if len(parts) < 6:
                    continue
                path = parts[-1]
                if not path.startswith("/"):
                    continue
                if ("usv" in Path(path).name or "/usv_" in path) and "acados" not in path:
                    if not self.allowed_library_path(path):
                        self.fail(f"foreign_usv_library:{name}:{path}")
        expected = self.expected_shared_sha().get(
            str(Path(node["expected_exe"])) if node.get("expected_exe") else "")
        if expected and actual_sha and expected != actual_sha:
            self.fail(f"node_exe_install_manifest_mismatch:{name}")
        (self.proc_dir() / f"{name}.ready.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.spawn_evidence.setdefault(name, {})["ready"] = record

    def within_candidate(self, path: str) -> bool:
        if not self.candidate_root:
            return False
        try:
            resolved = Path(path).resolve()
        except OSError:
            return False
        return self.candidate_root == resolved or             self.candidate_root in resolved.parents

    def allowed_library_path(self, path: str) -> bool:
        if not self.candidate_root:
            return False
        try:
            resolved = Path(path).resolve()
        except OSError:
            return False
        install = self.candidate_root / "install"
        build = self.candidate_root / "build"
        return install == resolved or install in resolved.parents or \
            build in resolved.parents

    def start_proc_sampler(self) -> None:
        registry = tuple(sorted(
            (name, node["pid"], int(node.get("starttime") or -1))
            for name, node in self.nodes.items() if node.get("pid")))
        self.sampler_registry = registry
        self.sampler_started = True
        self.sampler_thread = threading.Thread(target=self.sample_proc, daemon=True)
        self.sampler_thread.start()

    def sample_proc(self) -> None:
        try:
            self._sample_proc()
        except Exception as error:  # 采样线程不得拖垮 runner
            self.sampler_error = f"{type(error).__name__}:{error}"

    def _sample_proc(self) -> None:
        pressure_path = Path("/proc/pressure/cpu")
        for _ in range(4096):
            if self.sampler_stop.is_set():
                break
            at = time.monotonic_ns()
            sample = {"at_ns": at, "close_phase": self.close_phase, "tasks": []}
            for name, pid, starttime in self.sampler_registry:
                current = proc_starttime(pid)
                if current is None:
                    sample["tasks"].append({"name": name, "pid": pid,
                                            "gone": True, "pid_reused": False})
                    continue
                task = {"name": name, "pid": pid,
                        "pid_reused": starttime != current,
                        "starttime": current}
                for field, index in (("state", 3), ("utime", 14), ("stime", 15),
                                     ("num_threads", 20)):
                    task[field] = proc_field(pid, index)
                schedstat = Path(f"/proc/{pid}/schedstat")
                try:
                    parts = schedstat.read_text().split()
                    task["schedstat"] = [int(parts[0]), int(parts[1]), int(parts[2])]
                except (OSError, IndexError, ValueError):
                    task["schedstat"] = None
                try:
                    pressure = pressure_path.read_text().strip()
                except OSError:
                    pressure = None
                task["cpu_pressure"] = pressure
                sample["tasks"].append(task)
            self.sampler_samples.append(sample)
            if self.sampler_stop.wait(0.1):
                break
            if len(self.sampler_samples) >= 4096:
                break

    def start_production_monitor(self) -> None:
        self.monitor_thread = threading.Thread(target=self.monitor_production,
                                               daemon=True)
        self.monitor_thread.start()

    def monitor_production(self) -> None:
        baseline = self.production_before or {}
        while not self.sampler_stop.is_set() and not self.production_stop.is_set():
            current = production_snapshot()
            for field in production_diff(baseline, current):
                self.production_changes.append(f"{field}")
                self.record("production_changed", field=field,
                            observed_ns=time.monotonic_ns())
                self.production_stop.set()
                return
            if self.sampler_stop.wait(1.0):
                return

    def join_threads(self) -> None:
        """先停信号，再有界 join；超时即 runner fail，绝不挂住解释器。"""
        self.production_stop.set()
        self.sampler_stop.set()
        for thread, label in ((self.monitor_thread, "monitor_join"),
                              (self.sampler_thread, "proc_sampler_join")):
            if thread is None:
                continue
            thread.join(timeout=2.0)
            if thread.is_alive():
                self.fail(label)

    def write_proc_samples(self) -> None:
        path = self.out / "proc-samples.jsonl"
        if not self.sampler_started:
            self.record("proc_sampler_absent", observed_ns=time.monotonic_ns())
            return
        if self.sampler_error:
            self.fail(f"proc_sampler_error:{self.sampler_error}")
        with open(path, "w", encoding="utf-8") as handle:
            for sample in self.sampler_samples:
                handle.write(json.dumps(sample, sort_keys=True) + "\n")

    def scenario_params(self) -> dict:
        args = self.args
        return {
            "run_id": args.run_id,
            # 一次启动 = 一个 boot_id，三个节点共用；各自生成会让身份 join 失配。
            "boot_id": args.boot_id,
            "contract_file": str(self.out / "contract.json"),
            "contract_hash": args.contract_hash,
            "model_plan_file": str(self.out / "plan.json"),
            "model_plan_sha256": args.plan_sha256,
        }

    def launch(self) -> bool:
        args = self.args
        root = Path(args.install_root).resolve()
        executables = {"plant": root / "p1_x86_plant",
                       "worker": root / "p1_solver_worker",
                       "regulator": root / "p1_regulator"}
        for name in self.names:
            exe = executables[name]
            if not exe.is_file():
                raise SystemExit(f"missing executable for {name}: {exe}")

        scenario_path = self.out / "scenario_path.txt"
        scenario_profile = self.out / "scenario_profile.txt"
        seconds = float(args.stop_after_s or 0) + 8.0
        if args.stop_after_decisions:
            seconds = args.stop_after_decisions * 0.2 + 8.0
        if args.maneuver:
            path_rows, profile_rows = generate_maneuver_path_and_profile(
                args.maneuver, seconds + 2.0, seed=args.maneuver_seed,
                cruise_speed=args.cruise_speed)
            scenario_path.write_text("\n".join(path_rows) + "\n", encoding="utf-8")
            scenario_profile.write_text("\n".join(profile_rows) + "\n", encoding="utf-8")
        else:
            rows = []
            for i in range(0, int(seconds * 5) + 2):
                t_s = i * 0.2
                rows.append(f"{t_s * 0.5:.6f} 0.000000 0.000000 {t_s:.6f}")
            scenario_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        base = self.scenario_params()
        plant_params = {**base, "source_file": str(self.out / "plant.source.jsonl"),
                        "scenario_path_file": str(scenario_path)}
        if args.maneuver:
            plant_params["scenario_profile_file"] = str(scenario_profile)
        if args.plant_model_file:
            plant_params["plant_model_file"] = str(Path(args.plant_model_file).resolve())
        worker_params_extra = {}
        regulator_params_extra = {}
        if args.oracle_plant_file:
            if args.gp_snapshot or args.gp_schedule:
                raise SystemExit("--oracle-plant-file cannot be combined with --gp-snapshot or --gp-schedule")
            oracle_path = str(Path(args.oracle_plant_file).resolve())
            worker_params_extra["oracle_plant_file"] = oracle_path
            regulator_params_extra["oracle_plant_file"] = oracle_path
        if args.align_tick_phase:
            regulator_params_extra["align_tick_to_plant_origin"] = True
        if args.gp_snapshot:
            gp_path = str(Path(args.gp_snapshot).resolve())
            gp_sha = args.gp_snapshot_sha256 or sha256(Path(gp_path))
            worker_params_extra["gp_snapshot_file"] = gp_path
            worker_params_extra["gp_snapshot_sha256"] = gp_sha
            regulator_params_extra["gp_snapshot_file"] = gp_path
            regulator_params_extra["gp_snapshot_sha256"] = gp_sha
        if args.gp_schedule:
            sched_path = str(Path(args.gp_schedule).resolve())
            sched_sha = args.gp_schedule_sha256 or sha256(Path(sched_path))
            worker_params_extra["gp_schedule_file"] = sched_path
            worker_params_extra["gp_schedule_sha256"] = sched_sha
            regulator_params_extra["gp_schedule_file"] = sched_path
            regulator_params_extra["gp_schedule_sha256"] = sched_sha
        if args.ppo_proposal:
            ppo_man = json.loads(Path(args.ppo_manifest).read_text(encoding="utf-8"))
            regulator_params_extra["ppo_enabled"] = True
            regulator_params_extra["ppo_lambda_pi"] = float(args.lambda_pi)
            regulator_params_extra["ppo_expected_policy_sha256"] = str(ppo_man["onnx_sha256"])
            ppo_script = Path(__file__).resolve().parents[3] / "learning" / "ppo_proposal_node.py"
            if not ppo_script.is_file():
                ppo_script = Path("/home/trevor/usv_scheme_a_wt/research/scheme_a/learning/ppo_proposal_node.py")
            if not ppo_script.is_file():
                raise SystemExit(f"missing ppo_proposal_node.py: {ppo_script}")
            ppo_log = self.out / "ppo_proposal.stdout.txt"
            ppo_jsonl = self.out / "ppo_proposal.jsonl"
            ppo_env = dict(os.environ)
            ppo_env["ROS_DOMAIN_ID"] = str(args.ros_domain_id)
            ppo_env.setdefault("ROS_LOCALHOST_ONLY", "1")
            ppo_env.setdefault("OMP_NUM_THREADS", "1")
            ppo_env.setdefault("OPENBLAS_NUM_THREADS", "1")
            ppo_env.setdefault("ORT_INTRA_OP_NUM_THREADS", "1")
            self.ppo_proc = subprocess.Popen(
                [
                    "/usr/bin/python3",
                    "-u",
                    str(ppo_script),
                    "--run-id", args.run_id,
                    "--boot-id", args.boot_id,
                    "--model", str(Path(args.ppo_model).resolve()),
                    "--manifest", str(Path(args.ppo_manifest).resolve()),
                    "--rate-hz", "20.0",
                    "--log-file", str(ppo_jsonl),
                ] + (["--lookahead", args.ppo_lookahead] if args.ppo_lookahead else [])
                + gate_cli_args(self.ppo_gate),
                env=ppo_env,
                stdin=subprocess.DEVNULL,
                stdout=open(ppo_log, "w"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            ppo_deadline = time.monotonic() + min(12.0, float(args.startup_timeout_s))
            while time.monotonic() < ppo_deadline:
                if self.ppo_proc.poll() is not None:
                    self.fail(f"startup_gate:ppo_proposal_exited_{self.ppo_proc.returncode}")
                    return False
                if ppo_jsonl.is_file() and ppo_jsonl.stat().st_size > 0:
                    break
                time.sleep(0.05)
            else:
                self.fail("startup_gate:ppo_proposal_timeout")
                return False
        if self.diag:
            plant_params["clock_diagnostics_file"] = str(
                self.out / "plant.clock-diagnostics.jsonl")
            worker_params_extra.clear()
            regulator_params_extra["clock_diagnostics_file"] = str(
                self.out / "regulator.clock-diagnostics.jsonl")
        self.spawn("plant", executables["plant"], plant_params)
        if not self.wait_for("plant", lambda rows: any(
                r.get("type") == "plant_ready" for r in rows),
                args.startup_timeout_s):
            return False
        if self.diag:
            self.capture_ready("plant")

        if "worker" in self.names:
            worker_params = {**base,
                             "source_file": str(self.out / "worker.source.jsonl"),
                             "mode": "controlled_sim", **worker_params_extra}
            if args.worker_block_ms:
                worker_params["test_native_block_ms"] = args.worker_block_ms
            self.spawn("worker", executables["worker"], worker_params)
            if not self.wait_for("worker", lambda rows: any(
                    r.get("type") == "worker_recording_ready" for r in rows),
                    args.startup_timeout_s):
                return False
            if self.diag:
                self.capture_ready("worker")

        if "regulator" in self.names:
            params = {**base,
                      "source_file": str(self.out / "regulator.source.jsonl"),
                      "mode": "controlled_sim",
                      "worker_pid": self.nodes["worker"]["pid"],
                      "recording_observer_node": "p1_x86_plant",
                      **regulator_params_extra}
            if args.stimulus == "hold_expiry" or "hold_expiry" in self.scenario.get("stimuli", []):
                params["test_skip_tick"] = args.stimulus_at_tick
            self.spawn("regulator", executables["regulator"], params)
            if not self.wait_for("regulator", lambda rows: any(
                    r.get("type") == "recording_ready" for r in rows),
                    args.startup_timeout_s):
                return False
            if self.diag:
                self.capture_ready("regulator")
        if self.diag:
            self.start_proc_sampler()
        return True

    # -- 刺激 ------------------------------------------------------------
    def run_stimuli(self, stop_hook) -> None:
        """刺激只通过真实类型化通道注入；不使用任何节点日志捷径。"""
        args = self.args
        if args.stimulus == "none":
            return
        if args.faults != "on":
            raise SystemExit("stimuli require --faults on (contract must declare them)")
        controller = StimulusController(self)
        controller.run(stop_hook)

    # -- 停止与排空 ------------------------------------------------------
    def stop_all(self, simultaneous: bool = False) -> None:
        grace = self.args.grace_s
        targets = []
        for name in STOP_ORDER:
            proc = self.procs.get(name)
            if proc is None or proc.poll() is not None:
                continue
            if not self.identity_matches(name, proc):
                continue
            targets.append((name, proc))

        def _send_term(name: str, proc: subprocess.Popen) -> float:
            self.nodes[name]["stop_requested_ns"] = time.monotonic_ns()
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            return time.monotonic()

        def _reap(name: str, proc: subprocess.Popen, start: float) -> None:
            while time.monotonic() - start < grace:
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.nodes[name]["killed"] = True
                self.fail(f"node_undead:{name}")
            proc.wait(timeout=10)
            self.nodes[name]["wait_ms"] = int((time.monotonic() - start) * 1000)

        if simultaneous:
            started = [(name, proc, _send_term(name, proc)) for name, proc in targets]
            for name, proc, start in started:
                _reap(name, proc, start)
        else:
            for name, proc in targets:
                start = _send_term(name, proc)
                _reap(name, proc, start)

        for name, proc in self.procs.items():
            if self.nodes[name]["rc"] is None:
                self.nodes[name]["rc"] = proc.returncode
            elif proc.returncode is not None:
                self.nodes[name]["rc"] = proc.returncode

        if self.ppo_proc is not None:
            if self.ppo_proc.poll() is None:
                try:
                    os.killpg(os.getpgid(self.ppo_proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.ppo_proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(self.ppo_proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.ppo_proc.wait(timeout=2)

    def identity_matches(self, name: str, proc: subprocess.Popen) -> bool:
        """发信号前核对 PID 仍是该 Popen、starttime/PGID 一致、exe 仍在候选内。"""
        if not self.diag:
            return True
        node = self.nodes[name]
        pid = node.get("pid")
        reasons: list[str] = []
        if pid is None or proc.pid != pid:
            reasons.append("popen_pid_changed")
        if pid is not None:
            current = proc_starttime(pid)
            if node.get("starttime") is None or current != node.get("starttime"):
                reasons.append("starttime_changed")
            try:
                if os.getpgid(pid) != node.get("pgid"):
                    reasons.append("pgid_changed")
            except OSError:
                reasons.append("pgid_unreadable")
            exe = proc_exe(pid)
            if exe is None:
                reasons.append("exe_unreadable")
            elif not self.within_candidate(exe):
                reasons.append("exe_outside_candidate")
            elif node.get("expected_exe") and \
                    str(Path(exe).resolve()) != node["expected_exe"]:
                reasons.append("exe_changed")
        if reasons:
            self.stop_identity_failures.append(f"{name}:{','.join(reasons)}")
            self.fail(f"stop_identity_mismatch:{name}:{reasons[0]}")
            self.record("stop_identity_mismatch", node=name, reasons=reasons,
                        observed_ns=time.monotonic_ns())
            return False
        return True

    def trace_files(self) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        if "plant" in self.names:
            paths["plant"] = self.out / "plant.clock-diagnostics.jsonl"
        if "regulator" in self.names:
            paths["regulator"] = self.out / "regulator.clock-diagnostics.jsonl"
        return paths

    def check_trace(self, name: str, path: Path) -> dict:
        """缺 summary / dropped>0 / flush=false 都算诊断失败，但不改执行分支。"""
        record = {"path": path.name, "present": path.is_file()}
        header = None
        summary = None
        if not path.is_file():
            self.fail(f"clock_diagnostics_missing:{name}")
            record["complete"] = False
            return record
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    self.fail(f"clock_diagnostics_unparsable:{name}")
                    record["complete"] = False
                    return record
                kind = row.get("type")
                if kind == "clock_diagnostics_header":
                    header = row
                elif kind == "clock_diagnostics_summary":
                    summary = row
        record["header_found"] = header is not None
        record["summary_found"] = summary is not None
        if header is not None:
            record["producer"] = header.get("producer")
            record["run_id"] = header.get("run_id")
            record["boot_id"] = header.get("boot_id")
            record["host_boot_id"] = header.get("host_boot_id")
            record["pid"] = header.get("pid")
            record["bootstrap_steady_origin_ns"] = header.get(
                "bootstrap_steady_origin_ns")
        if summary is None:
            self.fail(f"clock_diagnostics_incomplete:{name}")
            record["complete"] = False
            return record
        record.update({"attempted": summary.get("attempted"),
                       "stored": summary.get("stored"),
                       "dropped": summary.get("dropped"),
                       "complete": bool(summary.get("complete")),
                       "streams": summary.get("streams")})
        if not summary.get("complete"):
            self.fail(f"clock_diagnostics_incomplete:{name}")
        if header is not None:
            if header.get("run_id") != self.args.run_id:
                self.fail(f"clock_diagnostics_run_id_mismatch:{name}")
            if header.get("boot_id") != self.args.boot_id:
                self.fail(f"clock_diagnostics_boot_id_mismatch:{name}")
            node = self.nodes.get(name) or {}
            if node.get("pid") is not None and header.get("pid") != node["pid"]:
                self.fail(f"clock_diagnostics_pid_mismatch:{name}")
        return record

    def collect_diagnostics(self) -> dict:
        """所有文件关闭后才哈希；否则会把还在写的字节绑进 run.json。"""
        traces: dict[str, dict] = {}
        for name, path in self.trace_files().items():
            record = self.check_trace(name, path)
            if path.is_file():
                record.update({"bytes": path.stat().st_size, "sha256": sha256(path)})
            traces[name] = record
        proc: dict[str, dict] = {}
        samples = self.out / "proc-samples.jsonl"
        if samples.is_file():
            proc["samples"] = {"path": samples.name,
                               "bytes": samples.stat().st_size,
                               "sha256": sha256(samples)}
        for path in sorted((self.out / "proc").glob("*")) if (self.out / "proc").is_dir() else []:
            proc[path.name] = {"path": f"proc/{path.name}",
                               "bytes": path.stat().st_size,
                               "sha256": sha256(path)}
        markers: dict[str, bool] = {}
        for name in ("plant", "regulator"):
            if name not in self.names:
                continue
            text = ""
            log = self.out / f"{name}.stdout.txt"
            if log.is_file():
                text = log.read_text(encoding="utf-8", errors="replace")
            marker = [line for line in text.splitlines()
                      if line.startswith("CLOCK_DIAGNOSTICS_FLUSH_SUCCESS=")]
            markers[name] = marker[-1].endswith("true") if marker else False
            if not markers[name]:
                self.fail(f"clock_diagnostics_flush_marker:{name}")
        return {
            "enabled": True,
            "host_boot_id": host_boot_id(),
            "domain_gate": self.domain_gate,
            "production_before": self.production_before,
            "production_after": self.production_after,
            "production_changed": self.production_changes,
            "traces": traces,
            "proc": proc,
            "flush_markers": markers,
            "sampler_started": self.sampler_started,
            "sampler_samples": len(self.sampler_samples),
            "stop_identity_failures": self.stop_identity_failures,
        }

    def drain_gate(self) -> None:
        """写 run.json 之前：每个 source 末行必须是该节点 summary。"""
        for name in self.names:
            path = self.out / f"{name}.source.jsonl"
            if not path.is_file() or path.stat().st_size == 0:
                self.fail(f"source_missing:{name}")
                continue
            rows = self.read_source(name)
            if not rows:
                self.fail(f"source_empty:{name}")
                continue
            if any(r.get("type") == "__unparsable__" for r in rows):
                self.fail(f"source_unparsable:{name}")
                continue
            last = rows[-1]
            expected = SOURCE_SUMMARY[name]
            if last.get("type") != expected:
                self.fail(f"source_summary_missing:{name}")
                continue
            self.nodes[name]["summary_seen"] = True
            if name == "plant":
                if last.get("flushed") is not True:
                    self.fail("plant_summary_not_flushed")
            elif last.get("normal_source_complete") is not True:
                self.fail(f"source_incomplete:{name}")
            if name == "regulator":
                shutdown = [r for r in rows if r.get("type") == "regulator_shutdown"]
                if not shutdown:
                    self.fail("regulator_shutdown_missing")
                elif shutdown[-1].get("normal_contract_complete") is not True:
                    self.fail("regulator_shutdown_incomplete")


class StimulusController:
    """用 rclpy 在真实类型化通道上注入刺激。

    late      —— 目标为尚未执行的未来 tick，deadline 已过 → plant 必须 late 且零执行；
    duplicate —— 把 regulator 已发出的同一条命令再发一次 → 必须 duplicate 且不重复执行；
    hold_expiry —— 发一条窗口更靠后的命令占用 pending，使 regulator 下一拍无法合法
                   声明窗口（receipt_pending），从而让 plant 的 hold 自然到期。
    """

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.last_decision: dict | None = None
        self.last_command: dict | None = None
        self.last_ok_begin: int | None = None
        self.claimed_begin: int | None = None
        self.fired = False

    def _latest(self, name: str, kind: str) -> dict | None:
        rows = [r for r in self.runner.read_source(name) if r.get("type") == kind]
        return rows[-1] if rows else None

    def run(self, stop_hook) -> None:
        args = self.runner.args
        target = args.stimulus_at_tick

        if self.runner.args.stimulus == "hold_expiry":
            # hold_expiry 由 regulator 的 test_skip_tick 参数原生扣发，无需外部 DDS 注入。
            # 监视 regulator 日志，在检测到 plant_command_withheld(tick=target) 时记录刺激元数据；
            # 其 processed_ns 严格先于 plant 对应 hold 的到期时刻（close_steady_ns），满足检查器要求。
            while not stop_hook() and not self.fired:
                for row in self.runner.tail_source("regulator"):
                    if row.get("type") == "plant_command_withheld" and row.get("tick") == target:
                        fired_ns = int(row.get("processed_ns") or time.monotonic_ns())
                        self.runner.write_stimulus({
                            "kind": "hold_expiry",
                            "sequence": 0,
                            "tick": target,
                            "fired_at_tick": target,
                            "fired_ns": fired_ns,
                        })
                        self.fired = True
                        return
                time.sleep(0.002)
            if not self.fired:
                for row in self.runner.read_source("regulator"):
                    if row.get("type") == "plant_command_withheld" and row.get("tick") == target:
                        fired_ns = int(row.get("processed_ns") or time.monotonic_ns())
                        self.runner.write_stimulus({
                            "kind": "hold_expiry",
                            "sequence": 0,
                            "tick": target,
                            "fired_at_tick": target,
                            "fired_ns": fired_ns,
                        })
                        self.fired = True
                        return
            return

        import rclpy
        from rclpy.node import Node
        from usv_research_interfaces.msg import ExecutionDecision, PlantCommand

        # 独立 context + 独立 executor：不能复用全局 executor（它可能已在别处 spin，
        # 复用会直接抛 "Executor is already spinning"）。
        context = rclpy.Context()
        rclpy.init(context=context)
        node = Node("p1_stimulus_injector", context=context)
        executor = rclpy.executors.SingleThreadedExecutor(context=context)
        executor.add_node(node)
        publisher = node.create_publisher(PlantCommand, "/p1/plant_command", 1)

        def on_decision(message: ExecutionDecision) -> None:
            self.last_decision = {
                "tick": int(message.tick),
                "accepted": bool(message.candidate_accepted),
                "final_n": [float(message.final_n[0]), float(message.final_n[1])],
                "model_generation": int(message.model_generation),
                "task_generation": int(message.task_generation),
                "config_generation": int(message.config_generation),
                "schedule_generation": int(message.schedule_generation),
                "clock_epoch": int(message.clock_epoch),
                "commit_ns": int(message.activation_commit_ns),
            }

        node.create_subscription(ExecutionDecision, "/p1/execution_decision",
                                 on_decision, 10)

        # 槽位空窗只有 ~7 ms（plant 在边界写 ok 回执，regulator 在下一拍开头
        # 立刻占住），20 ms 轮询必然落空。改成 200 µs 轮询 + 以文件时间为准。
        while not stop_hook() and not self.fired:
            executor.spin_once(timeout_sec=0.0005)
            decision = self.last_decision
            if decision is None or not decision["accepted"]:
                continue
            if decision["tick"] < target:
                continue
            if self.runner.args.stimulus == "duplicate":
                # 重复必须是"同一条**已执行**命令再发一次"。用 regulator 的日志行
                # 会与 DDS 实际投递赛跑，可能把"重复"送到原件之前 —— 那样 plant 的
                # 第一条反而是 duplicate，ok 就永远不出现。以 plant 已执行的回执为准。
                executed = {as_int(r.get("sequence")) for r in self.runner.read_source("plant")
                            if r.get("type") == "plant_receipt"
                            and r.get("disposition") == "ok"}
                command = next((c for c in reversed(self.runner.read_source("regulator"))
                                if c.get("type") == "plant_command"
                                and as_int(c.get("sequence")) in executed), None)
            else:
                command = self._latest("regulator", "plant_command")
            if command is None:
                continue
            self.last_command = command
            # 先置位再注入：注入本身可能触发回调重入，导致同一条刺激发两次。
            self.fired = True
            self.inject(node, publisher, PlantCommand, decision, command)

        executor.remove_node(node)
        node.destroy_node()
        rclpy.shutdown(context=context)

    def inject(self, node, publisher, PlantCommand, decision, command) -> None:
        now = time.monotonic_ns()
        axes = command if self.runner.args.stimulus == "duplicate" else decision
        base = {
            "schema_version": "p1-plant-command-v2",
            "run_id": command["run_id"],
            "boot_id": command["boot_id"],
            "contract_hash": command["contract_hash"],
            "producer_instance_id": "stimulus",
            "task_generation": axes["task_generation"],
            "model_generation": axes["model_generation"],
            "config_generation": axes["config_generation"],
            "schedule_generation": axes["schedule_generation"],
            "clock_epoch": axes["clock_epoch"],
        }
        if self.runner.args.stimulus == "late":
            # 序号必须是 regulator 下一条真正要用的那个：伪造一个远大的序号会让
            # 之后每条真实命令都被判 reordered，整条链断掉。
            begin = int(command["apply_end_steady_ns"])
            message = PlantCommand()
            message.sequence = int(command["sequence"]) + 1000
            message.tick = int(decision["tick"]) + 1
            message.apply_begin_steady_ns = begin
            message.apply_end_steady_ns = begin + T_NS
            message.deadline_steady_ns = now - 1
            message.regulator_clock_sim_ns = 0
            message.thrust_n = decision["final_n"]
            self._fill(message, base)
            publisher.publish(message)
            self.runner.write_stimulus({
                "kind": "late", "sequence": message.sequence,
                "tick": message.tick, "deadline_steady_ns": message.deadline_steady_ns,
                "fired_at_tick": decision["tick"], "fired_ns": now})
        elif self.runner.args.stimulus == "duplicate":
            message = PlantCommand()
            message.sequence = int(command["sequence"])
            message.tick = int(command["tick"])
            message.apply_begin_steady_ns = int(command["apply_begin_steady_ns"])
            message.apply_end_steady_ns = int(command["apply_end_steady_ns"])
            message.deadline_steady_ns = int(command["deadline_steady_ns"])
            message.regulator_clock_sim_ns = int(command.get("regulator_clock_sim_ns") or 0)
            message.thrust_n = list(command["thrust_n"])
            self._fill(message, base)
            publisher.publish(message)   # 第二次发送：plant 必须判 duplicate
            self.runner.write_stimulus({
                "kind": "duplicate", "sequence": message.sequence,
                "tick": message.tick, "fired_at_tick": decision["tick"],
                "fired_ns": now})
        else:  # hold_expiry：跳过一拍占住 pending，制造真正的到期缺口
            # command 是 plant 的 ok 回执（已执行窗口），起点必须由**实际执行结束**
            # 推出来；用 apply_end 会取到声明值，与实际网格差一拍。
            begin = int(command["executed_end_steady_ns"]) + T_NS
            message = PlantCommand()
            message.sequence = int(command["sequence"]) + 2000
            message.tick = int(decision["tick"]) + 2
            message.apply_begin_steady_ns = begin
            message.apply_end_steady_ns = begin + T_NS
            message.deadline_steady_ns = begin + DEADLINE_NS
            message.regulator_clock_sim_ns = 0
            message.thrust_n = decision["final_n"]
            self._fill(message, base)
            publisher.publish(message)
            self.runner.write_stimulus({
                "kind": "hold_expiry", "sequence": message.sequence,
                "tick": message.tick, "fired_at_tick": decision["tick"],
                "fired_ns": now})

    @staticmethod
    def _fill(message, base: dict) -> None:
        for key, value in base.items():
            setattr(message, key, value)


def candidate_preflight(args: argparse.Namespace, out: Path, root: Path) -> dict:
    """预检：候选/输出归属、输入摘要、域、生产 before。失败不创建 out。"""
    problems: list[str] = []
    try:
        out.relative_to(root / "runs")
    except ValueError:
        problems.append(f"out_not_under_candidate_runs:{out}")
    if out.exists():
        problems.append(f"out_exists:{out}")
    capsule = root / "capsule"
    if not capsule.is_dir():
        problems.append("candidate_capsule_missing")
    install = root / "install"
    install_root = Path(args.install_root).resolve()
    try:
        install_root.relative_to(install)
    except ValueError:
        problems.append(f"install_root_not_under_candidate:{install_root}")
    hashes: dict[str, str | None] = {}
    for label, path in (("plan", Path(args.plan)), ("contract", Path(args.contract)),
                        ("source_hashes", Path(args.source_hashes))):
        if not path.is_file():
            problems.append(f"input_missing:{label}")
            hashes[label] = None
            continue
        digest = sha256(path)
        hashes[label] = digest
        declared = {"plan": args.plan_sha256, "contract": args.contract_hash}.get(label)
        if declared and declared != digest:
            problems.append(f"input_digest_mismatch:{label}")
    gate = scan_domain_gate(args.ros_domain_id, os.getpid(), set(),
                            PID1_CGROUP)
    if gate["verdict"] != "clear":
        problems.extend(gate["blocking_reasons"])
    production = production_snapshot()
    if production.get("systemctl_error"):
        problems.append("production_snapshot_unavailable")
    if production.get("fragment_sha256") is None:
        problems.append("production_unit_unreadable")
    if production.get("defaults_sha256") is None:
        problems.append("production_defaults_unreadable")
    result = {
        "schema": "scheme-a-clock-diagnostics-preflight-v1",
        "scenario": args.scenario,
        "candidate_root": str(root),
        "out": str(out),
        "install_root": str(install_root),
        "ok": not problems,
        "problems": problems,
        "input_sha256": hashes,
        "domain_gate": gate,
        "production_before": production,
        "captured_ns": time.monotonic_ns(),
    }
    return result


def main() -> int:
    args = build_parser().parse_args()
    out = Path(args.out).resolve()
    preflight = None
    if args.clock_diagnostics:
        if not args.candidate_root:
            raise SystemExit("--candidate-root is required with --clock-diagnostics")
        root = Path(args.candidate_root).resolve()
        preflight = candidate_preflight(args, out, root)
        if not preflight["ok"]:
            receipt = root / "evidence" / f"preflight-{args.scenario}.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
            print(json.dumps({"scenario": args.scenario, "preflight": "failed",
                              "problems": preflight["problems"],
                              "receipt": str(receipt)}, ensure_ascii=False))
            return 3
    if out.exists():
        raise SystemExit(f"refusing to reuse an existing evidence directory: {out}")
    out.mkdir(parents=True)

    # 输入身份先核对：让节点自己发现不一致只会得到三个各自拒绝。
    plan_sha = sha256(Path(args.plan))
    if plan_sha != args.plan_sha256:
        raise SystemExit("plan hash differs from the declared value")
    contract_sha = sha256(Path(args.contract))
    if contract_sha != args.contract_hash:
        raise SystemExit("contract hash differs from the declared value")
    source_hashes = Path(args.source_hashes)
    if not source_hashes.is_file():
        raise SystemExit("--source-hashes manifest is required")
    manifest_sha = sha256(source_hashes)

    # 运行根内保留被引用的输入副本（检查器只认根内副本）。
    (out / "contract.json").write_bytes(Path(args.contract).read_bytes())
    (out / "plan.json").write_bytes(Path(args.plan).read_bytes())
    (out / "source_hashes.json").write_bytes(source_hashes.read_bytes())

    scenario = SCENARIOS[args.scenario]
    if args.stimulus == "none" and scenario["stimuli"]:
        args.stimulus = scenario["stimuli"][0]
    if scenario["faults"] and args.faults != "on":
        raise SystemExit(f"scenario {args.scenario} requires --faults on")
    if scenario.get("stop_mode") and args.stop_mode == "none":
        args.stop_mode = scenario["stop_mode"]
    if args.scenario == "worker_expiry" and not args.worker_block_ms:
        args.worker_block_ms = 250
    options = {
        "scenario": args.scenario, "nodes": args.nodes,
        "stop_after_decisions": args.stop_after_decisions,
        "stop_after_s": args.stop_after_s, "stimulus": args.stimulus,
        "stimulus_at_tick": args.stimulus_at_tick,
        "worker_block_ms": args.worker_block_ms, "stop_mode": args.stop_mode,
        "faults": args.faults,
    }
    # 只有开启诊断/机动/植物覆盖时才加入新键：默认路径的 run_id 输入保持不变。
    if args.clock_diagnostics:
        options["clock_diagnostics"] = True
    if args.maneuver:
        options["maneuver"] = args.maneuver
        options["maneuver_seed"] = args.maneuver_seed
        if args.cruise_speed is not None:
            options["cruise_speed"] = float(args.cruise_speed)
    if args.plant_model_file:
        options["plant_model_file_sha256"] = sha256(Path(args.plant_model_file))
    if args.dataset_source:
        options["dataset_source"] = args.dataset_source
    if args.oracle_plant_file:
        options["oracle_plant_file_sha256"] = sha256(Path(args.oracle_plant_file))
    if args.align_tick_phase:
        options["align_tick_phase"] = True
    run_id = args.run_id or hashlib.sha256(json.dumps(
        [args.scenario, plan_sha, contract_sha, manifest_sha, options],
        sort_keys=True).encode()).hexdigest()[:24]
    # DDS 域必须由 runner 统一钉死：子进程与注入器（同一进程内的 rclpy 节点）
    # 必须落在同一个域，否则注入的命令根本到不了 plant。
    os.environ["ROS_DOMAIN_ID"] = str(args.ros_domain_id)
    os.environ.setdefault("ROS_LOCALHOST_ONLY", "1")
    args.run_id = run_id
    # boot 身份由 runner 统一分配并写进 run.json；节点不自行生成。
    args.boot_id = uuid.uuid4().hex

    runner = Runner(args)
    launched = False
    if runner.diag:
        runner.domain_gate = preflight["domain_gate"]
        runner.production_before = preflight["production_before"]
        runner.record("preflight_ok", out=str(out),
                      candidate_root=str(runner.candidate_root),
                      observed_ns=time.monotonic_ns())
        runner.record("domain_gate", verdict=runner.domain_gate["verdict"],
                      ros_related=len(runner.domain_gate["ros_related_processes"]),
                      unrelated_env_224=len(runner.domain_gate["unrelated_env_224"]),
                      unverifiable=len(runner.domain_gate["unverifiable"]))
        runner.start_production_monitor()
    def stop_hook() -> bool:
        if runner.diag and runner.production_stop.is_set():
            return True
        if args.stop_after_s:
            return time.monotonic() - start >= args.stop_after_s
        criterion = scenario["stop_criterion"]
        if "seconds" in criterion:   # 纯 plant 场景没有决策可数
            return time.monotonic() - start >= float(criterion["seconds"])
        wanted = args.stop_after_decisions or criterion["decisions"]
        rows = runner.read_source("regulator")
        decisions = [r for r in rows if r.get("type") == "decision"]
        return len(decisions) >= wanted

    start = time.monotonic()
    stimulus_thread = None
    if runner.failure is None and args.stimulus != "none":
        stimulus_thread = threading.Thread(
            target=runner.run_stimuli, args=(stop_hook,), daemon=True)
        stimulus_thread.start()

    criterion_met = False
    try:
        # launch 的异常也必须走同一条收尾：先停节点、再停采样、再比生产快照。
        launched = runner.launch()
        if not launched:
            runner.stop_all()
            runner.drain_gate()
        if runner.failure is None:
            while True:
                if stop_hook():
                    criterion_met = True
                    if runner.diag and runner.production_stop.is_set():
                        for field in runner.production_changes:
                            runner.fail(f"production_changed:{field}")
                    break
                if time.monotonic() - start > (args.stop_after_s or 0) + 120.0 \
                        and not args.stop_after_s:
                    # 到上限仍未达到原停止条件：不能把 break 当成功。
                    if runner.diag:
                        runner.fail("scenario_stop_criterion_unmet")
                    break
                healthy = all(runner.procs[n].poll() in (None, 0)
                              for n in runner.names)
                if not healthy:
                    for n in runner.names:
                        rc = runner.procs[n].poll()
                        if rc not in (None, 0):
                            runner.fail(f"node_rc:{n}:{rc}")
                    break
                time.sleep(0.05)
    finally:
        runner.close_phase = True
        # 1) 先停生产监控并 join：它只置 Event，绝不与 stop_all 并发发信号。
        runner.production_stop.set()
        if runner.monitor_thread is not None:
            runner.monitor_thread.join(timeout=2.0)
            if runner.monitor_thread.is_alive():
                runner.fail("monitor_join")
        # stop_truncation 要证明"停止把正在执行的窗口截断"，所以必须落在窗口
        # 中段发起 SIGTERM；否则大概率停在边界上，hold 已闭合，什么也截不断。
        if args.stop_mode == "regulator_mid_window":
            origin = next((as_int(r.get("steady_origin_ns"))
                           for r in runner.read_source("plant")
                           if r.get("type") == "plant_ready"), None)
            if origin:
                # 目标相位用 1/4..3/4 区间的中点，并留出 10 ms 余量：
                # 正好停在边界上时 hold 已闭合，截断就无从发生。
                target = T_NS // 2
                margin = 10_000_000
                for _ in range(4):
                    phase = (time.monotonic_ns() - origin) % T_NS
                    runner.stopped_at_phase_ns = phase
                    if abs(phase - target) < margin // 2:
                        break
                    time.sleep(max(0.0, (target - phase) % T_NS) / 1e9)
                runner.stopped_at_phase_ns = (time.monotonic_ns() - origin) % T_NS
        runner.stop_all(simultaneous=(args.stop_mode == "regulator_mid_window"))
        # 2) 停止节点之后才停采样：close phase 内的进程消失属于正常收尾。
        runner.sampler_stop.set()
        if runner.sampler_thread is not None:
            runner.sampler_thread.join(timeout=2.0)
            if runner.sampler_thread.is_alive():
                runner.fail("proc_sampler_join")
        if runner.diag:
            runner.write_proc_samples()

    runner.drain_gate()
    if runner.diag:
        runner.production_after = production_snapshot()
        changed = production_diff(runner.production_before or {},
                                  runner.production_after)
        for field in changed:
            runner.fail(f"production_changed:{field}")
        runner.record("production_after", changed=changed,
                      observed_ns=time.monotonic_ns())
    for name in runner.names:
        node = runner.nodes.get(name)
        if node is None:
            # 启动门失败时该节点从未启动：这是显式失败，不是"没有要求"。
            runner.fail(f"startup_gate:{name}")
            continue
        if node.get("killed"):
            continue
        rc = node.get("rc")
        if rc not in (0, None):
            runner.fail(f"node_rc:{name}:{rc}")

    sources = {}
    for name in runner.names:
        path = out / f"{name}.source.jsonl"
        if path.is_file():
            sources[name] = {"sha256": sha256(path),
                             "bytes": path.stat().st_size,
                             "lines": len(path.read_text().splitlines())}
    scripts = {
        "runner": sha256(Path(__file__).resolve()),
        "checker": sha256(Path(__file__).with_name("check_scheme_a_closed_loop.py")),
        "plan": sha256(out / "plan.json"),
        "contract": sha256(out / "contract.json"),
    }
    for name in runner.names:
        runner.nodes.setdefault(name, {"pid": None, "pgid": None, "exe": None,
                                       "exe_sha256": None, "stop_requested_ns": 0,
                                       "rc": None, "wait_ms": 0, "killed": False,
                                       "summary_seen": False})
    if runner.diag:
        for name in runner.names:
            node = runner.nodes.get(name) or {}
            if node.get("rc") == 0 and not criterion_met:
                runner.fail(f"node_exit_before_criterion:{name}")
    document = {
        "schema": "scheme_A.controlled_sim.run.v2",
        "scenario": args.scenario,
        "run_id": run_id,
        "boot_id": args.boot_id,
        "nodes": runner.nodes,
        "sources": sources,
        "scripts": scripts,
        "stimuli": runner.stimuli,
        "stop_plan": {"criterion": scenario["stop_criterion"],
                      "stop_mode": args.stop_mode,
                      "faults": args.faults,
                      "startup_waits_s": runner.startup_waits},
        "required": scenario["required"],
        "options": options,
        "binding": {"source_hashes_sha256": manifest_sha,
                    "contract_sha256": contract_sha,
                    "plan_sha256": plan_sha},
        "events": runner.log,
        "failure": runner.failure,
    }
    if runner.diag:
        document["diagnostics"] = runner.collect_diagnostics()
    if args.dataset_source:
        document["dataset_source"] = args.dataset_source
    if args.maneuver:
        document["maneuver"] = {
            "name": args.maneuver,
            "seed": args.maneuver_seed,
            "cruise_speed": args.cruise_speed,
        }
    if args.plant_model_file:
        document["plant_model_file"] = str(Path(args.plant_model_file).resolve())
    if args.oracle_plant_file:
        document["oracle_plant_file"] = str(Path(args.oracle_plant_file).resolve())
    if args.align_tick_phase:
        document["align_tick_phase"] = True
    if args.gp_snapshot:
        document["gp_snapshot"] = str(Path(args.gp_snapshot).resolve())
    if args.gp_schedule:
        document["gp_schedule"] = str(Path(args.gp_schedule).resolve())
    if args.ppo_proposal:
        document["ppo_proposal"] = {
            "enabled": True,
            "lambda_pi": float(args.lambda_pi),
            "model": str(Path(args.ppo_model).resolve()),
            "lookahead": ([float(x) for x in args.ppo_lookahead.split(",")]
                          if args.ppo_lookahead else []),
        }
        if runner.ppo_gate:
            document["ppo_proposal"]["gate"] = runner.ppo_gate
    (out / "run.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({"scenario": args.scenario, "run_id": run_id,
                      "failure": runner.failure, "out": str(out)},
                     ensure_ascii=False))
    return 0 if runner.failure is None else 2


if __name__ == "__main__":
    sys.exit(main())
