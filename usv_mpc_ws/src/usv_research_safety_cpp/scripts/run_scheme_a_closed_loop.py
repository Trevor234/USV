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
    return p


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.out = Path(args.out).resolve()
        self.scenario = SCENARIOS[args.scenario]
        self.names = (("plant",) if (args.nodes == "plant_only" or
                                     self.scenario.get("nodes") == "plant_only")
                      else NODE_ORDER)
        self.procs: dict[str, subprocess.Popen] = {}
        self.nodes: dict[str, dict] = {}
        self.failure: str | None = None
        self.stimuli: list[dict] = []
        self.offsets: dict[str, int] = {}
        self.log: list[dict] = []
        self.startup_waits: dict[str, float] = {}

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
        rows = []
        seconds = float(args.stop_after_s or 0) + 8.0
        if args.stop_after_decisions:
            seconds = args.stop_after_decisions * 0.2 + 8.0
        for i in range(0, int(seconds * 5) + 2):
            t_s = i * 0.2
            rows.append(f"{t_s * 0.5:.6f} 0.000000 0.000000 {t_s:.6f}")
        scenario_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        base = self.scenario_params()
        self.spawn("plant", executables["plant"],
                   {**base, "source_file": str(self.out / "plant.source.jsonl"),
                    "scenario_path_file": str(scenario_path)})
        if not self.wait_for("plant", lambda rows: any(
                r.get("type") == "plant_ready" for r in rows),
                args.startup_timeout_s):
            return False

        if "worker" in self.names:
            worker_params = {**base,
                             "source_file": str(self.out / "worker.source.jsonl"),
                             "mode": "controlled_sim"}
            if args.worker_block_ms:
                worker_params["test_native_block_ms"] = args.worker_block_ms
            self.spawn("worker", executables["worker"], worker_params)
            if not self.wait_for("worker", lambda rows: any(
                    r.get("type") == "worker_recording_ready" for r in rows),
                    args.startup_timeout_s):
                return False

        if "regulator" in self.names:
            params = {**base,
                      "source_file": str(self.out / "regulator.source.jsonl"),
                      "mode": "controlled_sim",
                      "worker_pid": self.nodes["worker"]["pid"],
                      "recording_observer_node": "p1_x86_plant"}
            if args.stimulus == "hold_expiry" or "hold_expiry" in self.scenario.get("stimuli", []):
                params["test_skip_tick"] = args.stimulus_at_tick
            self.spawn("regulator", executables["regulator"], params)
            if not self.wait_for("regulator", lambda rows: any(
                    r.get("type") == "recording_ready" for r in rows),
                    args.startup_timeout_s):
                return False
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
    def stop_all(self) -> None:
        grace = self.args.grace_s
        for name in STOP_ORDER:
            proc = self.procs.get(name)
            if proc is None or proc.poll() is not None:
                continue
            self.nodes[name]["stop_requested_ns"] = time.monotonic_ns()
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            start = time.monotonic()
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
        for name, proc in self.procs.items():
            if self.nodes[name]["rc"] is None:
                self.nodes[name]["rc"] = proc.returncode
            elif proc.returncode is not None:
                self.nodes[name]["rc"] = proc.returncode

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


def main() -> int:
    args = build_parser().parse_args()
    out = Path(args.out).resolve()
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
    if not runner.launch():
        runner.stop_all()
        runner.drain_gate()

    def stop_hook() -> bool:
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

    try:
        if runner.failure is None:
            while not stop_hook():
                if time.monotonic() - start > (args.stop_after_s or 0) + 120.0 \
                        and not args.stop_after_s:
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
                    if abs(phase - target) < margin // 2:
                        break
                    runner.stopped_at_phase_ns = phase
                    time.sleep(max(0.0, (target - phase) % T_NS) / 1e9)
        runner.stop_all()

    runner.drain_gate()
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
    (out / "run.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({"scenario": args.scenario, "run_id": run_id,
                      "failure": runner.failure, "out": str(out)},
                     ensure_ascii=False))
    return 0 if runner.failure is None else 2


if __name__ == "__main__":
    sys.exit(main())
