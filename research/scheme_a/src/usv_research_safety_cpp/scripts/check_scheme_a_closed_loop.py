#!/usr/bin/env python3
# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""方案 A 受控仿真的闭环检查器（v2 证据，严格判据）。

它只从**节点自己的 source 原文**判定，不采信任何"运行成功"的汇总行：
一条闭环证据必须能逐条对账到具体行，否则它就只是三个进程都退出了而已。

该检查器先冻结判据，再要求生产者补齐事实。因此它拒绝 v1 证据、拒绝缺失输入、
拒绝空人口，并且**不提供兼容 PASS 分支**：一旦证据形状不足，就整体失败。

11 项判据（每项独立给结论，不合并）:
  inputs_complete      —— 必需输入齐全、可解析、摘要自洽、绑定自洽；
  node_lifecycle       —— 三节点零退出、未被 SIGKILL、末行为 summary、完整结束事实；
  typed_only           —— 执行输入只有类型化 PlantCommand，命令与决策一一对应；
  receipt_order        —— 回执严格递增、每 sequence 至多一个 ok、执行序号连续；
  dispositions         —— ok 真执行、非 ok 零执行、原因在词表内；
  guard_on_source      —— 锚点只来自 plant 回执的实际执行起点（逐决策联合核对）；
  plan_complete        —— 逐 tick 唯一模型代、每代都有真实求解/接纳/执行；
  progress             —— 决策 tick 严格递增、首末状态确有变化、持续进度；
  time_domain          —— 物理时间契约：区间长度、hold 末端、原点与回执一致；
  stimulus_refutation  —— 声明的刺激确有反证（零执行 + 反事实恰好一次）；
  no_test_seams        —— 证据里不含测试接缝，且故障标志与合同一致。

证据形状不足（v1 run/命令/回执/关闭事件/capability）以 `evidence_schema_insufficient`
整体失败，不降级解析。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

T_NS = 200_000_000
DEADLINE_NS = 150_000_000

EVIDENCE = {
    "run": "scheme_A.controlled_sim.run.v2",
    "command": "p1-plant-command-v2",
    "receipt": "p1-plant-receipt-v3",
    "hold_close": "p1-plant-hold-close-v2",
    "capability": "p1-worker-capability-v2",
}

# disposition -> 允许的 reason 词表（固定，不接受自造原因）
REASON_VOCABULARY = {
    "ok": {""},
    "bootstrap": {""},
    "rejected": {
        "schema", "foreign_run", "reordered", "invalid_window",
        "thrust_range", "tick_already_executed", "command_pending",
        "window_overlap",
    },
    "late": {"deadline_passed_before_execution", "window_closed"},
    "duplicate": {"same_sequence"},
}

HOLD_CLOSE_REASONS = {"expired", "superseded", "stop"}

# 运行身份与五轴版本：命令、回执、候选、决策必须逐项相等，缺一项就只是
# "同一序列号恰好出现两次"，那不是对账。
IDENTITY_FIELDS = ("run_id", "boot_id", "contract_hash")
AXES_FIELDS = ("task_generation", "model_generation", "config_generation",
               "schedule_generation", "clock_epoch")

# 每个节点 source 的末行事件类型与"完整结束"字段
NODE_END = {
    "regulator": {"event": "source_summary", "flag": "normal_source_complete"},
    "worker": {"event": "worker_summary", "flag": "normal_source_complete"},
    "plant": {"event": "plant_summary", "flag": "flushed"},
}

# required 词表 -> 归属判据。未声明的 required 视为输入不完整。
REQUIRED_OWNER = {
    "commands_paired": "typed_only",
    "no_commands": "typed_only",
    "single_execution_per_tick": "receipt_order",
    "nonzero_execution": "dispositions",
    "job_refused_nonterminal": "dispositions",
    "stop_hold_close": "dispositions",
    "generation_coverage": "plan_complete",
    "anchor_from_receipt": "guard_on_source",
    "state_progress": "progress",
    "free_evolution": "progress",
    "steady_domain_consistent": "time_domain",
    "stimulus:late": "stimulus_refutation",
    "stimulus:duplicate": "stimulus_refutation",
    "stimulus:hold_expiry": "stimulus_refutation",
    "no_test_seams": "no_test_seams",
}

CHECK_NAMES = (
    "inputs_complete", "node_lifecycle", "typed_only", "receipt_order",
    "dispositions", "guard_on_source", "plan_complete", "progress",
    "time_domain", "stimulus_refutation", "no_test_seams",
)


class Problems:
    """收集**全部**失败原因，不用首个错误掩盖后面的语义反例。"""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, reason: str) -> None:
        self.items.append(reason)

    def require(self, condition: bool, reason: str) -> bool:
        if not condition:
            self.add(reason)
        return bool(condition)

    def __bool__(self) -> bool:  # 有任何问题时为真（便于 `if p:` 读作"有问题"）
        return bool(self.items)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Unparsable(str):
    pass


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                rows.append({"type": "__unparsable__", "line": number,
                             "error": str(exc), "raw": stripped[:200]})
                continue
            if not isinstance(value, dict):
                rows.append({"type": "__unparsable__", "line": number,
                             "error": "not_an_object", "raw": stripped[:200]})
                continue
            rows.append(value)
    return rows


def is_hex64(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def finite_pair(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return False
        if item != item or item in (float("inf"), float("-inf")):
            return False
    return True


def as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def rows_of(rows: list[dict], kind: str) -> list[dict]:
    return [r for r in rows if r.get("type") == kind]


def expected_generation(plan: dict, tick: int) -> int | None:
    for row in plan.get("activation_plan") or []:
        first = row.get("first_target_tick")
        last = row.get("last_target_tick")
        if not isinstance(first, int):
            continue
        if tick >= first and (last is None or tick <= last):
            generation = row.get("generation")
            return generation if isinstance(generation, int) else None
    return None


def covered_generations(plan: dict, ticks: list[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for tick in ticks:
        generation = expected_generation(plan, tick)
        if generation is not None:
            out.setdefault(generation, []).append(tick)
    return out


class Evidence:
    """已解析的输入；解析失败时留下 problems，不抛异常。"""

    def __init__(self, run_root: Path, plan_path: Path, contract_path: Path | None,
                 source_hashes: Path | None) -> None:
        self.root = run_root
        self.problems = Problems()
        self.run_doc: dict = {}
        self.plan: dict = {}
        self.contract: dict = {}
        self.regulator: list[dict] = []
        self.worker: list[dict] = []
        self.plant: list[dict] = []
        self.stimulus: list[dict] = []
        self.source_hashes_path = source_hashes
        self.schema_insufficient: list[str] = []
        self._load(plan_path, contract_path)

    # -- 输入 ------------------------------------------------------------
    def _inside(self, path: Path, label: str) -> Path | None:
        try:
            resolved = path.resolve()
        except OSError:
            self.problems.add(f"input_unresolvable:{label}")
            return None
        if not resolved.is_file():
            self.problems.add(f"input_missing:{label}")
            return None
        if self.root.resolve() not in resolved.parents:
            self.problems.add(f"input_outside_run_root:{label}")
            return None
        return resolved

    def _load_json(self, path: Path, label: str) -> dict:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.problems.add(f"json_unparsable:{label}:{type(exc).__name__}")
            return {}
        if not isinstance(doc, dict):
            self.problems.add(f"json_not_object:{label}")
            return {}
        return doc

    def _load(self, plan_path: Path, contract_path: Path | None) -> None:
        run_file = self._inside(self.root / "run.json", "run.json")
        if run_file:
            self.run_doc = self._load_json(run_file, "run.json")

        self.plant_only = "no_commands" in (self.run_doc.get("required") or [])
        for label, path in (
            ("contract.json", self.root / "contract.json"),
            ("plan.json", self.root / "plan.json"),
            *(() if self.plant_only else (
                ("regulator.source.jsonl", self.root / "regulator.source.jsonl"),
                ("worker.source.jsonl", self.root / "worker.source.jsonl"))),
            ("plant.source.jsonl", self.root / "plant.source.jsonl"),
            ("stimulus.source.jsonl", self.root / "stimulus.source.jsonl"),
        ):
            if not path.exists() and label.startswith("stimulus"):
                continue
            if self._inside(path, label) is None:
                continue
            if label.endswith(".json"):
                doc = self._load_json(self.root / label, label)
                if label == "contract.json":
                    self.contract = doc
                else:
                    self.plan = doc
                continue
            rows = read_jsonl(self.root / label)
            bad = [r for r in rows if r.get("type") == "__unparsable__"]
            if bad:
                self.problems.add(f"jsonl_unparsable:{label}:{len(bad)}")
            if not rows:
                self.problems.add(f"source_empty:{label}")
            if label.startswith("regulator"):
                self.regulator = rows
            elif label.startswith("worker"):
                self.worker = rows
            elif label.startswith("stimulus"):
                self.stimulus = rows
            else:
                self.plant = rows

        # 外部 --plan/--contract 只用于核对：运行根内必须同时有副本。
        for label, external, in_root in (
            ("plan", plan_path, self.root / "plan.json"),
            ("contract", contract_path, self.root / "contract.json"),
        ):
            if external is None:
                continue
            if not external.is_file():
                self.problems.add(f"input_missing:{label}")
                continue
            if in_root.is_file() and sha256_file(external) != sha256_file(in_root):
                self.problems.add(f"external_{label}_differs_from_run_copy")

        self._check_binding()

    def _check_binding(self) -> None:
        run = self.run_doc
        if run.get("schema") != EVIDENCE["run"]:
            self.schema_insufficient.append(
                f"run_schema:{run.get('schema')!r}")
        scripts = run.get("scripts")
        if not isinstance(scripts, dict):
            self.problems.add("scripts_missing")
            return
        for key in ("runner", "checker", "plan", "contract"):
            if not is_hex64(scripts.get(key)):
                self.problems.add(f"scripts_not_sha256:{key}")
        own = Path(__file__).resolve()
        if own.is_file() and is_hex64(scripts.get("checker")):
            if sha256_file(own) != scripts["checker"]:
                self.problems.add("checker_sha256_differs_from_declared")
        for key, path in (("plan", self.root / "plan.json"),
                          ("contract", self.root / "contract.json")):
            if path.is_file() and is_hex64(scripts.get(key)):
                if sha256_file(path) != scripts[key]:
                    self.problems.add(f"scripts_{key}_sha256_differs_from_run_copy")

        binding = run.get("binding")
        if not isinstance(binding, dict):
            self.problems.add("binding_missing")
            return
        in_root_manifest = self.root / "source_hashes.json"
        for key, path, sha_key in (
            ("plan_sha256", self.root / "plan.json", "plan"),
            ("contract_sha256", self.root / "contract.json", "contract"),
        ):
            if not is_hex64(binding.get(key)):
                self.problems.add(f"binding_not_sha256:{key}")
            elif path.is_file() and binding[key] != sha256_file(path):
                self.problems.add(f"binding_{key}_differs_from_run_copy")
            elif is_hex64(scripts.get(sha_key)) and binding[key] != scripts[sha_key]:
                self.problems.add(f"binding_{key}_differs_from_scripts")
        if not is_hex64(binding.get("source_hashes_sha256")):
            self.problems.add("binding_not_sha256:source_hashes_sha256")
        else:
            if in_root_manifest.is_file():
                if sha256_file(in_root_manifest) != binding["source_hashes_sha256"]:
                    self.problems.add("binding_source_hashes_differs_from_run_copy")
            else:
                self.problems.add("input_missing:source_hashes.json")
            if self.source_hashes_path is None:
                self.problems.add("source_hashes_argument_required")
            elif not self.source_hashes_path.is_file():
                self.problems.add("input_missing:--source-hashes")
            elif sha256_file(self.source_hashes_path) != binding["source_hashes_sha256"]:
                self.problems.add("source_hashes_sha256_differs_from_binding")

        sources = run.get("sources")
        if not isinstance(sources, dict):
            self.problems.add("sources_missing")
            return
        for name in (("plant",) if self.plant_only else ("regulator", "worker", "plant")):
            record = sources.get(name)
            path = self.root / f"{name}.source.jsonl"
            if not isinstance(record, dict):
                self.problems.add(f"sources_missing:{name}")
                continue
            if not path.is_file():
                continue
            if record.get("sha256") != sha256_file(path):
                self.problems.add(f"source_sha256_mismatch:{name}")
            if record.get("bytes") != path.stat().st_size:
                self.problems.add(f"source_bytes_mismatch:{name}")
            if record.get("lines") != len(
                    path.read_text(encoding="utf-8").splitlines()):
                self.problems.add(f"source_lines_mismatch:{name}")

    # -- 形状门 ----------------------------------------------------------
    def check_shape(self, plant_only: bool = False) -> list[str]:
        problems: list[str] = []
        for row in rows_of(self.regulator, "plant_command"):
            if row.get("schema") != EVIDENCE["command"]:
                problems.append(f"command_schema:{row.get('schema')!r}")
                break
        for row in rows_of(self.plant, "bootstrap_receipt"):
            if row.get("schema") != EVIDENCE["receipt"]:
                problems.append(f"bootstrap_schema:{row.get('schema')!r}")
                break
        for row in rows_of(self.plant, "plant_receipt"):
            if row.get("schema") != EVIDENCE["receipt"]:
                problems.append(f"receipt_schema:{row.get('schema')!r}")
                break
        for row in rows_of(self.plant, "plant_hold_close"):
            if row.get("schema") != EVIDENCE["hold_close"]:
                problems.append(f"hold_close_schema:{row.get('schema')!r}")
                break
        if plant_only:
            # 自由演化场景没有 worker/regulator：没有命令、也没有能力证据。
            return problems
        capabilities = rows_of(self.worker, "worker_capability")
        for row in capabilities:
            if row.get("schema") != EVIDENCE["capability"]:
                problems.append(f"capability_schema:{row.get('schema')!r}")
                break
        if not capabilities:
            problems.append("capability_missing")
        return problems


# ---------------------------------------------------------------------------
# 判据
# ---------------------------------------------------------------------------
def ok_receipts(plant: list[dict]) -> list[dict]:
    return [r for r in rows_of(plant, "plant_receipt")
            if r.get("disposition") == "ok"]


def node_lifecycle(ev: Evidence, p: Problems) -> dict:
    run = ev.run_doc
    detail: dict = {"nodes": {}, "failure": run.get("failure")}
    if run.get("failure") is not None:
        p.add(f"run_failure:{run.get('failure')}")
    nodes = run.get("nodes")
    if not isinstance(nodes, dict):
        p.add("nodes_missing")
        return detail
    # 运行形态决定节点集合：纯 plant 场景不存在 regulator/worker。
    for name in (("plant",) if ev.plant_only else ("regulator", "worker", "plant")):
        node = nodes.get(name)
        if not isinstance(node, dict):
            p.add(f"node_missing:{name}")
            continue
        entry = {
            "rc": node.get("rc"), "killed": node.get("killed"),
            "summary_seen": node.get("summary_seen"),
            "wait_ms": node.get("wait_ms"),
        }
        detail["nodes"][name] = entry
        p.require(node.get("rc") == 0, f"node_rc:{name}:{node.get('rc')}")
        p.require(node.get("killed") is False, f"node_killed:{name}")
        p.require(node.get("pgid") is not None, f"node_pgid_missing:{name}")
        wait_ms = node.get("wait_ms")
        p.require(isinstance(wait_ms, int) and wait_ms >= 0, f"node_wait_missing:{name}")
        stop_ns = node.get("stop_requested_ns")
        p.require(isinstance(stop_ns, int) and stop_ns > 0,
                  f"node_stop_request_missing:{name}")
        p.require(node.get("summary_seen") is True, f"node_summary_missing:{name}")
        exe = node.get("exe")
        exe_sha = node.get("exe_sha256")
        p.require(is_hex64(exe_sha), f"node_exe_sha256_invalid:{name}")
        if isinstance(exe, str) and Path(exe).is_file() and is_hex64(exe_sha):
            if sha256_file(Path(exe)) != exe_sha:
                p.add(f"node_exe_sha256_mismatch:{name}")
        elif isinstance(exe, str) and Path(exe).is_file():
            pass
        elif isinstance(exe, str) and not Path(exe).is_file():
            p.add(f"node_exe_missing:{name}")

    for name, spec in NODE_END.items():
        rows = {"regulator": ev.regulator, "worker": ev.worker,
                "plant": ev.plant}[name]
        if not rows:
            continue
        last = rows[-1]
        detail[f"{name}_last"] = last.get("type")
        if last.get("type") != spec["event"]:
            p.add(f"node_summary_not_last:{name}:{last.get('type')}")
            continue
        if last.get(spec["flag"]) is not True:
            p.add(f"node_end_incomplete:{name}:{spec['flag']}")

    shutdown = rows_of(ev.regulator, "regulator_shutdown")
    if not shutdown:
        if not ev.plant_only:
            p.add("regulator_shutdown_missing")
    else:
        row = shutdown[-1]
        detail["plant_hold_end_known"] = row.get("plant_hold_end_known")
        p.require(row.get("normal_contract_complete") is True,
                  "regulator_shutdown_normal_contract_incomplete")
        if row.get("plant_hold_end_known") is not True:
            p.add("regulator_shutdown_plant_hold_end_unknown")

    summary = rows_of(ev.plant, "plant_summary")
    if summary:
        row = summary[-1]
        detail["free_evolution_substeps"] = row.get("free_evolution_substeps")
        p.require(row.get("flushed") is True, "plant_summary_not_flushed")
        p.require(isinstance(row.get("stopped_at_substep"), int),
                  "plant_summary_stopped_at_substep_missing")
    return detail


def typed_only(ev: Evidence, p: Problems, required: set[str]) -> dict:
    startup = rows_of(ev.regulator, "startup")
    commands = rows_of(ev.regulator, "plant_command")
    decisions = rows_of(ev.regulator, "decision")
    receipts = rows_of(ev.plant, "plant_receipt")
    detail: dict = {"commands": len(commands), "decisions": len(decisions)}
    if not startup and not ev.plant_only:
        p.add("startup_missing")
    elif startup:
        row = startup[-1]
        detail["typed_command_topics"] = row.get("typed_command_topics")
        p.require(row.get("raw_command_topics") == [],
                  "startup_raw_command_topics_present")
        p.require(row.get("typed_command_topics") == ["/p1/plant_command"],
                  "startup_typed_topic_undeclared")

    if not commands and "no_commands" not in required:
        p.add("commands_missing")

    sequences: list[int] = []
    by_sequence: dict[int, dict] = {}
    for index, row in enumerate(commands):
        sequence = as_int(row.get("sequence"))
        tick = as_int(row.get("tick"))
        if sequence is None or sequence <= 0:
            p.add(f"command_sequence_invalid:{index}")
            continue
        if tick is None or tick <= 0:
            p.add(f"command_tick_invalid:{sequence}")
        if not finite_pair(row.get("thrust_n")):
            p.add(f"command_thrust_invalid:{sequence}")
        for key in ("apply_begin_steady_ns", "apply_end_steady_ns",
                    "deadline_steady_ns"):
            if as_int(row.get(key)) is None:
                p.add(f"command_field_missing:{key}:{sequence}")
        if sequence in by_sequence:
            p.add(f"command_sequence_repeated:{sequence}")
        by_sequence[sequence] = row
        sequences.append(sequence)
    if sequences != sorted(sequences):
        p.add("command_sequence_not_increasing")
    detail["sequence_span"] = [sequences[0], sequences[-1]] if sequences else []

    # 命令 <-> 决策 一一对应：每台被接纳决策必须有一条同 tick、同推力的命令。
    accepted = [d for d in decisions
                if d.get("candidate_accepted") is True and as_int(d.get("job_id"))]
    command_by_tick = {}
    for row in commands:
        tick = as_int(row.get("tick"))
        if tick is not None:
            command_by_tick.setdefault(tick, []).append(row)
    paired = 0
    for decision in accepted:
        tick = as_int(decision.get("tick"))
        candidates = command_by_tick.get(tick) or []
        if not candidates:
            p.add(f"accepted_decision_without_command:{tick}")
            continue
        final_n = decision.get("final_n")
        if not any(finite_pair(row.get("thrust_n"))
                   and list(row["thrust_n"]) == list(final_n or [])
                   for row in candidates):
            p.add(f"command_thrust_differs_from_decision:{tick}")
            continue
        paired += 1
    detail["paired_commands"] = paired
    if accepted and paired != len(accepted):
        p.add("command_pairs_incomplete")

    # 双向：每条 ok 回执都必须有一条可追溯命令；除尾部外每条命令都要有回执。
    receipt_sequences = {as_int(r.get("sequence")) for r in receipts}
    orphans = sorted(s for s in by_sequence if s not in receipt_sequences)
    tail_ok = len(orphans) <= 1 and (not orphans or orphans == [max(by_sequence)])
    if not tail_ok:
        p.add("command_without_receipt")
    injected = stimulus_sequences(ev)
    orphan_receipts = sorted(s for s in receipt_sequences
                             if s not in by_sequence and s not in injected)
    if orphan_receipts:
        p.add(f"receipt_without_command:{orphan_receipts[:3]}")
    detail["unanswered"] = orphans[:5]

    withheld = rows_of(ev.regulator, "plant_command_withheld")
    detail["withheld"] = len(withheld)
    ticks = [as_int(d.get("tick")) for d in decisions]
    if ticks != sorted(t for t in ticks if t is not None) or len(set(ticks)) != len(ticks):
        p.add("decision_ticks_not_strictly_increasing")

    # ---- 运行身份 / 五轴 / deadline / 候选 Job 的联合核对 ---------------
    identity = {}
    if startup:
        identity = {key: startup[-1].get(key) for key in IDENTITY_FIELDS}
        p.require(startup[-1].get("run_id") == ev.run_doc.get("run_id"),
                  "startup_run_id_differs_from_run_json")
        p.require(all(isinstance(identity[key], str) and identity[key]
                      for key in IDENTITY_FIELDS),
                  "startup_identity_incomplete")
    candidate_jobs = {}
    for row in rows_of(ev.worker, "candidate"):
        job = row.get("job") or {}
        job_id = as_int(job.get("job_id"))
        if job_id is not None:
            candidate_jobs[job_id] = job
    deadline_ns = as_int(ev.contract.get("deadline_ns"))
    detail["identity_joined"] = 0
    receipt_by_sequence = {}
    for row in receipts:
        sequence = as_int(row.get("sequence"))
        if sequence is not None:
            receipt_by_sequence.setdefault(sequence, row)
    for sequence, command in by_sequence.items():
        if command.get("schema") != EVIDENCE["command"]:
            p.add(f"command_schema_row:{sequence}:{command.get('schema')!r}")
        for key in IDENTITY_FIELDS:
            if identity and command.get(key) != identity[key]:
                p.add(f"command_identity_differs:{key}:{sequence}")
        for key in AXES_FIELDS:
            if as_int(command.get(key)) is None:
                p.add(f"command_axis_missing:{key}:{sequence}")
        begin = as_int(command.get("apply_begin_steady_ns"))
        end = as_int(command.get("apply_end_steady_ns"))
        deadline = as_int(command.get("deadline_steady_ns"))
        receipt = receipt_by_sequence.get(sequence)
        executed = receipt is not None and receipt.get("disposition") == "ok"
        if None not in (begin, end, deadline) and executed:
            # 只有 regulator 发出的 ok 命令必须满足合同的窗口/期限关系；
            # 故障刺激（late/duplicate）故意违反其中之一，那是被检验的对象。
            p.require(end - begin == T_NS, f"command_window_length:{sequence}")
            if deadline_ns is not None:
                p.require(deadline == begin + deadline_ns,
                          f"command_deadline_off_contract:{sequence}")
        job_id = as_int(command.get("candidate_job_id"))
        if job_id:
            job = candidate_jobs.get(job_id)
            if job is None:
                p.add(f"command_candidate_job_unknown:{sequence}:{job_id}")
            else:
                if as_int(job.get("target_tick")) != as_int(command.get("tick")):
                    p.add(f"command_candidate_tick_differs:{sequence}")
                for key in AXES_FIELDS:
                    if as_int(job.get(key)) != as_int(command.get(key)):
                        p.add(f"command_candidate_axis_differs:{key}:{sequence}")

        receipt = receipt_by_sequence.get(sequence)
        if receipt is None or receipt.get("disposition") != "ok":
            continue
        if receipt.get("schema") != EVIDENCE["receipt"]:
            p.add(f"receipt_schema_row:{sequence}:{receipt.get('schema')!r}")
        for key in IDENTITY_FIELDS:
            if identity and receipt.get(key) != identity[key]:
                p.add(f"receipt_identity_differs:{key}:{sequence}")
        for key in AXES_FIELDS + ("tick",):
            if receipt.get(key) != command.get(key):
                p.add(f"receipt_command_differs:{key}:{sequence}")
        receive = as_int(receipt.get("receive_steady_ns"))
        executed_begin = as_int(receipt.get("executed_begin_steady_ns"))
        if receive is not None and deadline is not None:
            p.require(receive <= deadline,
                      f"receipt_received_after_deadline:{sequence}")
        if executed_begin is not None and begin is not None:
            p.require(executed_begin >= begin,
                      f"receipt_executed_before_declared_window:{sequence}")
        detail["identity_joined"] += 1
    return detail


def receipt_order(ev: Evidence, p: Problems) -> dict:
    receipts = rows_of(ev.plant, "plant_receipt")
    detail: dict = {"receipts": len(receipts)}
    sequences: list[int] = []
    ok_sequences: list[int] = []
    execution_indices: list[int] = []
    seen_ok: set[int] = set()
    for row in receipts:
        disposition = row.get("disposition")
        sequence = as_int(row.get("sequence"))
        if sequence is None:
            p.add("receipt_sequence_invalid")
            continue
        sequences.append(sequence)
        if disposition == "ok":
            if sequence in seen_ok:
                p.add(f"receipt_duplicate_ok:{sequence}")
            seen_ok.add(sequence)
            ok_sequences.append(sequence)
            execution_index = as_int(row.get("execution_index"))
            if execution_index is None:
                p.add(f"receipt_execution_index_missing:{sequence}")
            else:
                execution_indices.append(execution_index)
    injected = stimulus_sequences(ev)
    owned = [value for value, row in
             ((as_int(r.get("sequence")), r) for r in receipts)
             if value is not None and value not in injected]
    if owned != sorted(owned):
        p.add("receipt_sequence_not_increasing")
    for sequence in set(sequences):
        rows = [r for r in receipts if as_int(r.get("sequence")) == sequence]
        if len(rows) > 2:
            p.add(f"receipt_sequence_repeated:{sequence}")
        if len(rows) > 1:
            extra = [r.get("disposition") for r in rows[1:]]
            if extra != ["duplicate"]:
                p.add(f"receipt_repeat_not_duplicate:{sequence}:{extra}")
    # 同一 tick 只能被真实施加一次
    ok_ticks = [as_int(r.get("tick")) for r in receipts
                if r.get("disposition") == "ok"]
    ok_ticks = [t for t in ok_ticks if t is not None]
    if len(ok_ticks) != len(set(ok_ticks)):
        p.add("tick_executed_twice")
    if execution_indices:
        expected = list(range(1, len(execution_indices) + 1))
        if execution_indices != expected:
            p.add(f"execution_index_not_contiguous:{execution_indices[:6]}")
    bootstrap = rows_of(ev.plant, "bootstrap_receipt")
    detail["bootstrap"] = len(bootstrap)
    if len(bootstrap) != 1:
        p.add(f"bootstrap_receipt_count:{len(bootstrap)}")
    else:
        row = bootstrap[0]
        p.require(row.get("execution_index") == 0, "bootstrap_execution_index")
        p.require(as_int(row.get("plant_steady_origin_ns")) not in (None, 0),
                  "bootstrap_origin_missing")
    detail["ok"] = len(ok_sequences)
    return detail


def dispositions(ev: Evidence, p: Problems, required: set[str]) -> dict:
    receipts = rows_of(ev.plant, "plant_receipt")
    commands = {as_int(r.get("sequence")): r
                for r in rows_of(ev.regulator, "plant_command")}
    counts: dict[str, int] = {}
    detail: dict = {}
    if not receipts and "no_commands" not in required:
        p.add("no_receipts")
    for row in receipts:
        disposition = row.get("disposition")
        counts[str(disposition)] = counts.get(str(disposition), 0) + 1
        sequence = as_int(row.get("sequence"))
        reason = row.get("reason")
        allowed = REASON_VOCABULARY.get(str(disposition))
        if allowed is None:
            p.add(f"disposition_unknown:{disposition}")
            continue
        if reason not in allowed:
            p.add(f"reason_outside_vocabulary:{disposition}:{reason}")
        thrust = row.get("thrust_n")
        if not finite_pair(thrust):
            p.add(f"receipt_thrust_invalid:{sequence}")
            continue
        begin = as_int(row.get("executed_begin_steady_ns"))
        end = as_int(row.get("executed_end_steady_ns"))
        if disposition == "ok":
            command = commands.get(sequence)
            if command is None:
                p.add(f"ok_without_command:{sequence}")
            elif list(thrust) != list(command.get("thrust_n") or []):
                p.add(f"ok_thrust_differs_from_command:{sequence}")
            if begin is None or end is None or end <= begin:
                p.add(f"ok_execution_window_invalid:{sequence}")
        else:
            if thrust != [0.0, 0.0]:
                p.add(f"non_ok_execution_nonzero:{sequence}:{thrust}")
            if begin not in (None, 0) or end not in (None, 0):
                p.add(f"non_ok_execution_window_present:{sequence}")
            if as_int(row.get("execution_index")) not in (0, None):
                p.add(f"non_ok_execution_index:{sequence}")

    detail["counts"] = counts
    by_sequence = {as_int(r.get("sequence")): r for r in receipts}

    if "nonzero_execution" in required:
        nonzero = [r for r in receipts
                   if r.get("disposition") == "ok"
                   and finite_pair(r.get("thrust_n"))
                   and any(abs(v) > 1e-9 for v in r["thrust_n"])]
        detail["nonzero_execution"] = len(nonzero)
        p.require(bool(nonzero), "no_nonzero_execution")

    if "job_refused_nonterminal" in required:
        refused = rows_of(ev.worker, "job_refused")
        non_terminal = [r for r in refused if r.get("terminal") is False]
        detail["job_refused"] = len(refused)
        detail["job_refused_non_terminal"] = len(non_terminal)
        p.require(bool(non_terminal), "job_refused_missing")
        for row in non_terminal:
            p.require(row.get("native_solve_entries_this_job") == 0,
                      f"job_refused_native_nonzero:{row.get('job_id')}")
            p.require(row.get("reason_not_terminal") is True
                      or row.get("terminal") is False,
                      f"job_refused_terminal_flag:{row.get('job_id')}")
        terminal = rows_of(ev.worker, "terminal_numerical_failure")
        p.require(not terminal, "terminal_numerical_failure_present")
        # 后继 Job 必须真的求解：拒绝不是整轮终点。
        job_ids = sorted({as_int(r.get("job_id")) for r in refused
                          if as_int(r.get("job_id")) is not None})
        if job_ids:
            later = [c for c in rows_of(ev.worker, "candidate")
                     if as_int((c.get("job") or {}).get("job_id")) is not None
                     and (c.get("job") or {}).get("job_id") > max(job_ids)
                     and c.get("native_solve_entries_this_job") == 1]
            detail["successor_solved"] = len(later)
            p.require(bool(later), "no_successor_job_after_refusal")

    if "stop_hold_close" in required:
        closes = [r for r in rows_of(ev.plant, "plant_hold_close")
                  if r.get("reason") == "stop"]
        detail["stop_hold_close"] = len(closes)
        p.require(bool(closes), "stop_hold_close_missing")
        for row in closes:
            close_ns = as_int(row.get("close_steady_ns"))
            executed_end = as_int(row.get("executed_end_steady_ns"))
            p.require(close_ns is not None and executed_end is not None
                      and close_ns < executed_end, "stop_hold_close_not_truncating")
    return detail


def guard_on_source(ev: Evidence, p: Problems, required: set[str]) -> dict:
    startup = rows_of(ev.regulator, "startup")
    decisions = rows_of(ev.regulator, "decision")
    accepted = [d for d in decisions
                if d.get("candidate_accepted") is True and as_int(d.get("job_id"))]
    receipts = {as_int(r.get("execution_index")): r
                for r in rows_of(ev.plant, "plant_receipt")
                if r.get("disposition") == "ok"}
    for row in rows_of(ev.plant, "bootstrap_receipt"):
        receipts[0] = row
    detail: dict = {"accepted": len(accepted), "anchors": {}}
    if startup:
        p.require(startup[-1].get("anchor_source") == "plant_receipt",
                  "anchor_source_not_plant_receipt")
    seeded = rows_of(ev.regulator, "anchor_seeded")
    detail["anchor_seeded"] = len(seeded)
    p.require(not seeded, "anchor_seeded_present")
    if not accepted and "no_commands" in required:
        detail["no_commands"] = True
        return detail
    if not accepted:
        p.add("no_accepted_decision_to_guard")
        return detail

    last_index = -1
    for decision in accepted:
        tick = decision.get("tick")
        execution_index = as_int(decision.get("plant_execution_index"))
        anchor_sequence = decision.get("anchor_sequence") or []
        anchor_time = decision.get("anchor_publish_ns") or []
        if execution_index is None:
            p.add(f"decision_execution_index_missing:{tick}")
            continue
        if execution_index < last_index:
            p.add(f"anchor_regressed:{tick}")
        last_index = execution_index
        if not (len(anchor_sequence) == 2 and anchor_sequence[0] == anchor_sequence[1]
                == execution_index):
            p.add(f"anchor_sequence_not_execution_index:{tick}:{anchor_sequence}")
        receipt = receipts.get(execution_index)
        if receipt is None:
            p.add(f"anchor_execution_index_unknown:{tick}:{execution_index}")
            continue
        executed_begin = as_int(receipt.get("executed_begin_steady_ns"))
        if not (isinstance(anchor_time, list) and len(anchor_time) == 2
                and anchor_time[0] == anchor_time[1] == executed_begin):
            p.add(f"anchor_publish_not_receipt_begin:{tick}:{anchor_time}")
    detail["anchors"] = {"count": len(accepted), "last_index": last_index}
    if "anchor_from_receipt" in required and len(accepted) < 2:
        p.add("anchor_continuity_unproven")
    return detail


def plan_complete(ev: Evidence, p: Problems, required: set[str]) -> dict:
    decisions = rows_of(ev.regulator, "decision")
    accepted = [d for d in decisions
                if d.get("candidate_accepted") is True and as_int(d.get("job_id"))]
    candidates = {}
    for row in rows_of(ev.worker, "candidate"):
        job_id = as_int((row.get("job") or {}).get("job_id"))
        if job_id is not None:
            candidates[job_id] = row
    execution_ticks = {as_int(r.get("tick")): as_int(r.get("execution_index"))
                      for r in ok_receipts(ev.plant)}
    detail: dict = {"accepted": len(accepted),
                    "declared": [row.get("generation")
                                 for row in ev.plan.get("activation_plan") or []]}
    if not accepted and "no_commands" in required:
        detail["no_commands"] = True
        return detail
    p.require(bool(accepted), "no_accepted_decision")

    used = {as_int(d.get("model_generation")) for d in accepted}
    declared = {row.get("generation") for row in ev.plan.get("activation_plan") or []
                if isinstance(row.get("generation"), int)}
    detail["used"] = sorted(u for u in used if u is not None)
    if used - declared:
        p.add(f"generation_not_declared:{sorted(used - declared)}")

    mismatched = []
    per_generation: dict[int, int] = {}
    for decision in accepted:
        tick = as_int(decision.get("tick"))
        job_id = as_int(decision.get("job_id"))
        if tick is None or job_id is None:
            p.add("accepted_decision_missing_job")
            continue
        expected = expected_generation(ev.plan, tick)
        generation = as_int(decision.get("model_generation"))
        if expected is None:
            p.add(f"tick_outside_plan:{tick}")
        elif generation != expected:
            mismatched.append({"tick": tick, "expected": expected, "actual": generation})
            p.add(f"tick_generation_mismatch:{tick}:{expected}!={generation}")
        candidate = candidates.get(job_id)
        if candidate is None:
            p.add(f"accepted_decision_without_candidate:{job_id}")
            continue
        if candidate.get("solver_invoked") is not True:
            p.add(f"candidate_not_solved:{job_id}")
        if candidate.get("native_solve_entries_this_job") != 1:
            p.add(f"candidate_native_entries:{job_id}:"
                  f"{candidate.get('native_solve_entries_this_job')}")
        if as_int(candidate.get("applied_generation")) != generation:
            p.add(f"candidate_applied_generation:{job_id}")
        if (candidate.get("job") or {}).get("model_generation") != generation:
            p.add(f"candidate_generation_echo:{job_id}")
        for key in AXES_FIELDS:
            if (candidate.get("job") or {}).get(key) != decision.get(key):
                p.add(f"candidate_decision_axis_differs:{key}:{job_id}")
        if as_int((candidate.get("job") or {}).get("target_tick")) != tick:
            p.add(f"candidate_decision_tick_differs:{job_id}")
        if tick not in execution_ticks:
            p.add(f"accepted_decision_without_execution:{tick}")
            continue
        per_generation[generation] = per_generation.get(generation, 0) + 1

    detail["per_generation"] = per_generation
    detail["mismatched"] = mismatched[:5]

    if "generation_coverage" in required:
        ticks = [as_int(d.get("tick")) for d in accepted if as_int(d.get("tick"))]
        covered = covered_generations(ev.plan, ticks) if ticks else {}
        missing = [generation for generation in covered
                   if per_generation.get(generation, 0) < 1]
        detail["covered"] = sorted(covered)
        detail["missing"] = sorted(missing)
        if missing:
            p.add(f"generation_without_acceptance:{sorted(missing)}")
    return detail


def progress(ev: Evidence, p: Problems, required: set[str]) -> dict:
    if "no_commands" in required:
        return free_evolution_detail(ev, p, required)
    receipts = ok_receipts(ev.plant)
    tolerance = ev.contract.get("activation_tolerance") or [0.25, 0.25, 0.15, 0.3, 0.2, 0.15]
    detail: dict = {"ok_receipts": len(receipts)}
    if not receipts:
        p.add("no_ok_receipt")
        return detail
    states = [r.get("state") for r in receipts]
    first, last = states[0], states[-1]
    if not (isinstance(first, list) and len(first) == 6
            and isinstance(last, list) and len(last) == 6):
        p.add("receipt_state_invalid")
        return detail
    deltas = [abs(float(b) - float(a)) for a, b in zip(first, last)]
    changed = any(delta > float(tol) for delta, tol in zip(deltas, tolerance))
    detail["delta"] = deltas
    p.require(changed, "state_did_not_change")

    accepted = [d for d in rows_of(ev.regulator, "decision")
                if d.get("candidate_accepted") is True and as_int(d.get("job_id"))]
    if "state_progress" in required:
        p.require(len(accepted) >= 2, "insufficient_accepted_decisions")
        if len(accepted) >= 2:
            p.require(accepted[-1].get("tick") > accepted[0].get("tick"),
                      "accepted_ticks_do_not_advance")

    return detail


def free_evolution_detail(ev: Evidence, p: Problems, required: set[str]) -> dict:
    detail: dict = {"no_commands": True}
    if "free_evolution" in required:
        summary = rows_of(ev.plant, "plant_summary")
        substeps = as_int(summary[-1].get("free_evolution_substeps")) if summary else None
        detail["free_evolution_substeps"] = substeps
        p.require(substeps is not None and substeps > 0, "free_evolution_absent")
        clocks = [as_int(r.get("sim_ns")) for r in rows_of(ev.plant, "plant_clock")]
        clocks = [c for c in clocks if c is not None]
        detail["clock_samples"] = len(clocks)
        p.require(len(clocks) >= 2, "clock_samples_missing")
        p.require(all(b > a for a, b in zip(clocks, clocks[1:])),
                  "clock_not_strictly_increasing")
        sensors = [as_int(r.get("sim_ns")) for r in rows_of(ev.plant, "plant_sensors")]
        sensors = [s for s in sensors if s is not None]
        detail["sensor_samples"] = len(sensors)
        p.require(len(sensors) >= 2, "sensor_samples_missing")
        p.require(all(b > a for a, b in zip(sensors, sensors[1:])),
                  "sensor_not_strictly_increasing")
        p.require(not rows_of(ev.plant, "plant_receipt"),
                  "free_evolution_has_receipts")
    return detail


def time_domain(ev: Evidence, p: Problems, required: set[str]) -> dict:
    receipts = ok_receipts(ev.plant)
    detail: dict = {"ok_receipts": len(receipts)}
    if not receipts and "no_commands" not in required:
        p.add("no_ok_receipt")
    bootstrap = rows_of(ev.plant, "bootstrap_receipt")
    origin = as_int(bootstrap[0].get("plant_steady_origin_ns")) if bootstrap else None
    boot_id = bootstrap[0].get("boot_id") if bootstrap else None
    clock_identity = bootstrap[0].get("clock_identity") if bootstrap else None
    if origin is None:
        p.add("steady_origin_missing")
    if bootstrap and (not isinstance(clock_identity, str) or not clock_identity):
        p.add("clock_identity_missing")
    if bootstrap and as_int(bootstrap[0].get("state_sample_sim_ns")) != 0:
        p.add("bootstrap_state_sample_sim_invalid")
    previous_hold_end = None
    previous_sample_sim = None
    ok_by_exec_idx: dict[int, dict] = {}
    for row in receipts:
        sequence = row.get("sequence")
        exec_idx = as_int(row.get("execution_index"))
        if exec_idx is not None:
            ok_by_exec_idx[exec_idx] = row
        begin = as_int(row.get("apply_begin_steady_ns"))
        end = as_int(row.get("apply_end_steady_ns"))
        executed_begin = as_int(row.get("executed_begin_steady_ns"))
        executed_end = as_int(row.get("executed_end_steady_ns"))
        hold_end = as_int(row.get("hold_end_steady_ns"))
        receive = as_int(row.get("receive_steady_ns"))
        executed = as_int(row.get("executed_steady_ns"))
        sim_ns = as_int(row.get("sim_ns"))
        state_sample_sim_ns = as_int(row.get("state_sample_sim_ns"))
        planned_end_sim_ns = as_int(row.get("planned_window_end_sim_ns"))
        row_clock_id = row.get("clock_identity")
        if None in (begin, end, executed_begin, executed_end, hold_end,
                    receive, executed, sim_ns, state_sample_sim_ns,
                    planned_end_sim_ns):
            p.add(f"receipt_window_field_missing:{sequence}")
            continue
        p.require(isinstance(row_clock_id, str) and row_clock_id == clock_identity,
                  f"receipt_clock_identity_mismatch:{sequence}")
        p.require(end - begin == T_NS, f"apply_window_length:{sequence}")
        p.require(hold_end == executed_begin + T_NS, f"hold_end_off_grid:{sequence}")
        p.require(executed_begin < executed_end, f"execution_window_empty:{sequence}")
        p.require(executed_end - executed_begin <= T_NS,
                  f"execution_longer_than_tick:{sequence}")
        p.require(receive <= executed_begin, f"receive_after_execution:{sequence}")
        p.require(executed_begin <= executed, f"executed_before_begin:{sequence}")
        p.require(row.get("plant_steady_origin_ns") == origin,
                  f"steady_origin_changed:{sequence}")
        if origin is not None:
            p.require(sim_ns == executed_end - origin,
                      f"sim_ns_not_derived_from_origin:{sequence}")
            p.require(state_sample_sim_ns == executed_begin - origin,
                      f"state_sample_sim_mismatch:{sequence}")
            p.require(planned_end_sim_ns == hold_end - origin,
                      f"planned_window_end_sim_mismatch:{sequence}")
        if previous_sample_sim is not None:
            p.require(state_sample_sim_ns > previous_sample_sim,
                      f"state_sample_sim_not_increasing:{sequence}")
        previous_sample_sim = state_sample_sim_ns
        if previous_hold_end is not None:
            p.require(executed_begin >= previous_hold_end,
                      f"execution_window_overlaps:{sequence}")
        previous_hold_end = hold_end
        p.require(executed_begin <= hold_end, f"hold_before_execution:{sequence}")

    closes = rows_of(ev.plant, "plant_hold_close")
    detail["hold_closes"] = len(closes)
    for row in closes:
        reason = row.get("reason")
        if reason not in HOLD_CLOSE_REASONS:
            p.add(f"hold_close_reason:{reason}")
        close_ns = as_int(row.get("close_steady_ns"))
        close_sim = as_int(row.get("close_sim_ns"))
        hc_sample_sim = as_int(row.get("state_sample_sim_ns"))
        hc_origin = as_int(row.get("plant_steady_origin_ns"))
        hc_exec_end = as_int(row.get("executed_end_steady_ns"))
        hc_exec_idx = as_int(row.get("execution_index"))
        hc_clock_id = row.get("clock_identity")
        if None in (close_ns, close_sim, hc_sample_sim, hc_origin, hc_exec_end, hc_exec_idx) or as_int(row.get("clock_epoch")) is None:
            p.add("hold_close_time_missing")
            continue
        p.require(isinstance(hc_clock_id, str) and hc_clock_id == clock_identity,
                  "hold_close_clock_identity_mismatch")
        if boot_id is not None:
            p.require(row.get("boot_id") == boot_id, "hold_close_boot_id_mismatch")
        if origin is not None:
            p.require(hc_origin == origin, "hold_close_steady_origin_mismatch")
            p.require(close_sim == close_ns - origin, "hold_close_sim_not_derived")
            p.require(hc_sample_sim == close_sim, "hold_close_state_sample_sim_mismatch")
            if reason in ("expired", "superseded"):
                p.require(close_sim == hc_exec_end - origin,
                          f"hold_close_full_window_end_mismatch:{hc_exec_idx}")
        if receipts and hc_exec_idx not in ok_by_exec_idx:
            p.add(f"hold_close_execution_index_unknown:{hc_exec_idx}")

    clocks = rows_of(ev.plant, "plant_clock")
    for row in clocks:
        steady = as_int(row.get("steady_ns"))
        sim = as_int(row.get("sim_ns"))
        if steady is None or sim is None or origin is None:
            p.add("plant_clock_field_missing")
            break
        if sim != steady - origin:
            p.add("plant_clock_sim_not_derived")
            break

    sensors = rows_of(ev.plant, "plant_sensors")
    stamps = [as_int(r.get("sim_ns")) for r in sensors]
    stamps = [s for s in stamps if s is not None]
    if len(stamps) >= 2 and not all(b > a for a, b in zip(stamps, stamps[1:])):
        p.add("sensor_sim_not_increasing")
    return detail


def stimulus_sequences(ev: "Evidence") -> set[int]:
    """stimulus.source.jsonl / run.json 里声明的注入序号。

    注入器是独立生产者（序号自成一套），因此这些序号不参与 regulator 命令流
    的连续性判定，也不需要出现在 regulator 的命令日志里。
    """
    declared = ev.run_doc.get("stimuli")
    sequences: set[int] = set()
    if isinstance(declared, list):
        for row in declared:
            sequence = as_int(row.get("sequence"))
            if sequence is not None:
                sequences.add(sequence)
    for row in rows_of(ev.stimulus, "stimulus"):
        sequence = as_int(row.get("sequence"))
        if sequence is not None:
            sequences.add(sequence)
    return sequences


def stimulus_refutation(ev: Evidence, p: Problems, required: set[str]) -> dict:
    stimuli = ev.run_doc.get("stimuli")
    detail: dict = {"declared": len(stimuli) if isinstance(stimuli, list) else 0}
    if not isinstance(stimuli, list):
        if any(item.startswith("stimulus:") for item in required):
            p.add("stimuli_missing")
        return detail
    receipts = {as_int(r.get("sequence")): r for r in rows_of(ev.plant, "plant_receipt")}
    execution_by_tick: dict[int, list[int]] = {}
    for row in ok_receipts(ev.plant):
        tick = as_int(row.get("tick"))
        if tick is not None:
            execution_by_tick.setdefault(tick, []).append(
                as_int(row.get("execution_index")))
    closes = rows_of(ev.plant, "plant_hold_close")
    commands = rows_of(ev.regulator, "plant_command")

    kinds: dict[str, int] = {}
    for stimulus in stimuli:
        kind = stimulus.get("kind")
        kinds[kind] = kinds.get(kind, 0) + 1
        sequence = as_int(stimulus.get("sequence"))
        tick = as_int(stimulus.get("tick"))
        if kind == "late":
            row = receipts.get(sequence)
            if row is None:
                p.add(f"late_receipt_missing:{sequence}")
                continue
            if row.get("disposition") != "late":
                p.add(f"late_disposition:{sequence}:{row.get('disposition')}")
            if row.get("reason") != "deadline_passed_before_execution":
                p.add(f"late_reason:{sequence}:{row.get('reason')}")
            if row.get("thrust_n") != [0.0, 0.0]:
                p.add(f"late_executed:{sequence}")
            if as_int(row.get("execution_index")) not in (0, None):
                p.add(f"late_execution_index:{sequence}")
            counterfactual = execution_by_tick.get(tick) or []
            if len(counterfactual) != 1:
                p.add(f"late_counterfactual_count:{tick}:{len(counterfactual)}")
        elif kind == "duplicate":
            rows = [r for r in rows_of(ev.plant, "plant_receipt")
                    if as_int(r.get("sequence")) == sequence]
            dispositions = [r.get("disposition") for r in rows]
            if dispositions.count("ok") != 1 or dispositions.count("duplicate") != 1:
                p.add(f"duplicate_dispositions:{sequence}:{dispositions}")
            ok_rows = [r for r in rows if r.get("disposition") == "ok"]
            indices = {as_int(r.get("execution_index")) for r in ok_rows}
            if len(indices) != 1:
                p.add(f"duplicate_executed_twice:{sequence}")
            if tick is not None and len(execution_by_tick.get(tick) or []) != 1:
                p.add(f"duplicate_tick_executions:{tick}")
        elif kind == "hold_expiry":
            fired_ns = as_int(stimulus.get("fired_ns"))
            # 只认**刺激之后、且不是关机最后一条**的到期闭合：关机时最后一拍
            # 天然没有后继，那条 expired 与刺激无关，不能拿来充当反证。
            last_close = closes[-1] if closes else None
            window_closes = [r for r in closes
                             if r.get("reason") == "expired"
                             and r is not last_close
                             and (fired_ns is None
                                  or (as_int(r.get("close_steady_ns")) or 0) > fired_ns)]
            if not window_closes:
                p.add("hold_expiry_close_missing")
            for row in window_closes:
                if as_int(row.get("close_steady_ns")) is None:
                    p.add("hold_expiry_close_time_missing")
            # 缺口内不得有推力：tick 之后到下一次 ok 执行之间不能有非零 ok。
            later = [r for r in ok_receipts(ev.plant)
                     if tick is not None and as_int(r.get("tick")) == tick + 1]
            for row in later:
                if row.get("thrust_n") != [0.0, 0.0] and not any(
                        as_int(c.get("tick")) == tick + 1 for c in commands):
                    p.add(f"hold_expiry_thrust_continues:{row.get('sequence')}")
        else:
            p.add(f"stimulus_kind_unknown:{kind}")

    if "stimulus:late" in required:
        p.require(kinds.get("late", 0) == 1, "stimulus_late_not_exactly_once")
    if "stimulus:duplicate" in required:
        p.require(kinds.get("duplicate", 0) == 1, "stimulus_duplicate_not_exactly_once")
    if "stimulus:hold_expiry" in required:
        p.require(kinds.get("hold_expiry", 0) == 1, "stimulus_hold_expiry_not_exactly_once")
    detail["kinds"] = kinds
    return detail


def no_test_seams(ev: Evidence, p: Problems, required: set[str]) -> dict:
    seams = []
    for name, rows in (("regulator", ev.regulator), ("worker", ev.worker),
                       ("plant", ev.plant)):
        for row in rows:
            text = json.dumps(row, ensure_ascii=False)
            if "test_seam" in text or "test_fault" in text:
                seams.append({"source": name, "type": row.get("type")})
    detail: dict = {"seam_rows": seams[:5], "count": len(seams)}
    p.require(not seams, "test_seam_rows_present")

    faults_enabled = bool(ev.contract.get("controlled_sim_faults_enabled"))
    detail["contract_faults_enabled"] = faults_enabled
    capabilities = rows_of(ev.worker, "worker_capability")
    for row in capabilities:
        if bool(row.get("fault_injection_enabled")) and not faults_enabled:
            p.add("worker_fault_flag_without_contract")
            break
    barriers = [row for row in ev.regulator
                if "barrier" in str(row.get("type"))]
    detail["barrier_rows"] = len(barriers)
    if barriers and not faults_enabled:
        p.add("barrier_rows_without_contract_faults")
    if "no_test_seams" in required:
        p.require(not barriers, "barrier_rows_in_required_clean_run")
    return detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="the run directory written by the runner")
    ap.add_argument("--plan", required=True, help="the model plan actually used")
    ap.add_argument("--contract", default=None, help="the contract actually used")
    ap.add_argument("--source-hashes", default=None,
                    help="frozen source manifest the run is bound to")
    args = ap.parse_args()

    run = Path(args.run)
    ev = Evidence(run, Path(args.plan),
                  Path(args.contract) if args.contract else None,
                  Path(args.source_hashes) if args.source_hashes else None)

    required_rows = ev.run_doc.get("required")
    required: set[str] = set()
    if not isinstance(required_rows, list) or not required_rows:
        ev.problems.add("required_missing")
    else:
        for item in required_rows:
            if not isinstance(item, str) or item not in REQUIRED_OWNER:
                ev.problems.add(f"required_unknown:{item}")
            else:
                required.add(item)

    checks: list[dict] = []
    failures: list[dict] = []

    def record(name: str, problems: Problems, detail: dict) -> None:
        checks.append({"check": name, "ok": not problems,
                       "detail": detail, "problems": list(problems.items)})

    # 形状门：证据版本不足时整体失败，不降级解析。
    shape = ev.check_shape(ev.plant_only) if ev.plant or ev.worker or ev.regulator else []
    for item in shape:
        ev.schema_insufficient.append(item)

    if ev.schema_insufficient:
        for item in ev.schema_insufficient:
            failures.append({"name": "evidence_schema_insufficient", "reason": item})

    inputs = ev.problems
    record("inputs_complete", inputs, {
        "missing_or_unbound": list(inputs.items)[:10],
        "schema_insufficient": ev.schema_insufficient,
    })

    for name, fn in (
        ("node_lifecycle", lambda p: node_lifecycle(ev, p)),
        ("typed_only", lambda p: typed_only(ev, p, required)),
        ("receipt_order", lambda p: receipt_order(ev, p)),
        ("dispositions", lambda p: dispositions(ev, p, required)),
        ("guard_on_source", lambda p: guard_on_source(ev, p, required)),
        ("plan_complete", lambda p: plan_complete(ev, p, required)),
        ("progress", lambda p: progress(ev, p, required)),
        ("time_domain", lambda p: time_domain(ev, p, required)),
        ("stimulus_refutation", lambda p: stimulus_refutation(ev, p, required)),
        ("no_test_seams", lambda p: no_test_seams(ev, p, required)),
    ):
        problems = Problems()
        try:
            detail = fn(problems)
        except Exception as exc:  # 检查器自身不得因输入形状而崩溃
            problems.add(f"check_error:{type(exc).__name__}:{exc}")
            detail = {}
        record(name, problems, detail)

    for check in checks:
        for problem in check["problems"]:
            failures.append({"name": check["check"], "reason": problem})
    ok = all(check["ok"] for check in checks) and not ev.schema_insufficient
    doc = {
        "schema": "scheme_A.controlled_sim.check.v2",
        "run": str(run.resolve()),
        "scenario": ev.run_doc.get("scenario"),
        "run_id": ev.run_doc.get("run_id"),
        "checks": checks,
        "failures": failures,
        "verdict": "PASS" if ok else "FAIL",
    }
    (run / "check.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for check in checks:
        print(f"{'ok  ' if check['ok'] else 'FAIL'} {check['check']} "
              f"{json.dumps(check['detail'], ensure_ascii=False)}")
        if not check["ok"]:
            print(f"     problems: {json.dumps(check['problems'], ensure_ascii=False)}")
    for failure in failures:
        if failure["name"] == "evidence_schema_insufficient":
            print(f"FAIL evidence_schema_insufficient {failure['reason']}")
    print(json.dumps({"verdict": doc["verdict"], "checks": len(checks),
                      "failures": len(failures)}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
