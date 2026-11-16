#!/usr/bin/env python3
# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""方案 A 时钟断档诊断器（只读证据，不改 run/check/source）。

它回答的是**一个可以被证伪的问题**：在同一次 run、同一个 host boot 内，
plant 的 clock 发布与 regulator 的 clock 回调入口，在真实 CLOCK_MONOTONIC
上究竟差多少，以及这段差落在哪个阶段。

三条与本仓库既有误读直接相关的纪律：

1. `mapped = origin + sim` 是**映射时间**，不是现场墙钟。plant 的 50 ms 发布
   间隔是物理子步（T/4），不能由它推断 5 ms poll 被饿死。
2. 真实间隔只能用 `at_ns` 相减；不同 host boot 绝不跨减。
3. 阶段归属只定位**区间**（source_io / state_lock / publisher_call /
   physical_step / executor_busy / delivery_or_executor / receive_catchup），
   不把一次观测直接升级成 CPU、磁盘或 DDS 的唯一根因。

证据不完整（缺 trace、缺 summary、dropped>0、flush=false、摘要不符）时
`evidence_status=incomplete`、`clock_gap_observed=null`、`root_cause=unresolved`：
既不能由保留的前段宣布"没有 gap"，也不能给出因果阶段结论。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SUBSTEP_NS = 50_000_000
ENTRY_GAP_LEAD_NS = 400_000_000
STABLE_PRODUCTION_FIELDS = ("main_pid", "restarts", "active_state", "sub_state",
                            "active_enter", "exec_start", "control_group",
                            "fragment_path", "fragment_sha256", "defaults_sha256",
                            "scheme", "runtime_target", "processes")
PROBLEM_SCHEMA = "scheme-a-clock-gap-diagnosis-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_hex64(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    problems: list[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as error:
                problems.append(f"unparsable:{path.name}:{number}:{error}")
                continue
            if not isinstance(value, dict):
                problems.append(f"not_an_object:{path.name}:{number}")
                continue
            value["__line__"] = number
            rows.append(value)
    return rows, problems


class Diagnosis:
    def __init__(self, run: Path, plan: Path, contract: Path, sources: Path) -> None:
        self.run = run
        self.plan = plan
        self.contract = contract
        self.sources = sources
        self.problems: list[str] = []
        self.run_doc: dict = {}
        self.diagnostics: dict = {}
        self.traces: dict[str, list[dict]] = {}
        self.trace_meta: dict[str, dict] = {}
        self.spawn: dict[str, dict] = {}
        self.proc_samples: list[dict] = []
        self.proc_meta: dict[str, dict] = {}
        self.source_rows: dict[str, list[dict]] = {}

    # -- 载入与身份 ------------------------------------------------------
    def load(self) -> None:
        run_path = self.run / "run.json"
        if not run_path.is_file():
            self.problems.append("run_json_missing")
            return
        try:
            self.run_doc = json.loads(run_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            self.problems.append(f"run_json_unparsable:{error}")
            return
        if self.run_doc.get("schema") != "scheme_A.controlled_sim.run.v2":
            self.problems.append("run_schema_unsupported")
        self.diagnostics = self.run_doc.get("diagnostics") or {}
        if not self.diagnostics:
            self.problems.append("diagnostics_block_missing")
        elif not self.diagnostics.get("enabled"):
            self.problems.append("diagnostics_disabled")
        self.check_binding()
        # proc 身份必须先载入：trace 头里的 pid/ELF/starttime 要与之对照。
        self.load_proc()
        self.load_traces()
        self.load_sources()

    def check_binding(self) -> None:
        binding = self.run_doc.get("binding")
        if not isinstance(binding, dict):
            self.problems.append("binding_missing")
            return
        pairs = (("contract_sha256", "contract.json"),
                 ("plan_sha256", "plan.json"),
                 ("source_hashes_sha256", "source_hashes.json"))
        for key, filename in pairs:
            value = binding.get(key)
            if not is_hex64(value):
                self.problems.append(f"binding_not_full_sha256:{key}")
                continue
            copy = self.run / filename
            if not copy.is_file():
                self.problems.append(f"run_copy_missing:{filename}")
                continue
            if sha256_file(copy) != value:
                self.problems.append(f"binding_differs_from_run_copy:{key}")
        for label, path in (("plan", self.plan), ("contract", self.contract),
                            ("source_hashes", self.sources)):
            if path is None or not Path(path).is_file():
                self.problems.append(f"input_missing:{label}")
                continue
            expected = {"plan": "plan_sha256", "contract": "contract_sha256",
                        "source_hashes": "source_hashes_sha256"}[label]
            if binding.get(expected) != sha256_file(Path(path)):
                self.problems.append(f"binding_differs_from_input:{label}")

    def trace_paths(self) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        for name in ("plant", "regulator"):
            entry = (self.diagnostics.get("traces") or {}).get(name)
            if not isinstance(entry, dict):
                continue
            if not entry.get("present"):
                self.problems.append(f"trace_missing:{name}")
                continue
            path = self.run / entry["path"]
            if not path.is_file():
                self.problems.append(f"trace_file_missing:{name}")
                continue
            paths[name] = path
        return paths

    def load_traces(self) -> None:
        recorded = self.diagnostics.get("traces") or {}
        for name, path in self.trace_paths().items():
            entry = recorded.get(name, {})
            if entry.get("sha256") and sha256_file(path) != entry["sha256"]:
                self.problems.append(f"trace_sha_mismatch:{name}")
            if entry.get("bytes") is not None and path.stat().st_size != entry["bytes"]:
                self.problems.append(f"trace_bytes_mismatch:{name}")
            rows, problems = read_jsonl(path)
            self.problems.extend(f"{name}:{problem}" for problem in problems)
            self.traces[name] = [row for row in rows
                                 if row.get("type") == "clock_diagnostics"]
            self.trace_meta[name] = {
                "header": next((row for row in rows
                                if row.get("type") == "clock_diagnostics_header"), None),
                "summary": next((row for row in rows
                                 if row.get("type") == "clock_diagnostics_summary"), None),
                "path": str(path),
            }
            self.check_trace_identity(name)
            self.check_trace_integrity(name)

    def check_trace_identity(self, name: str) -> None:
        meta = self.trace_meta[name]
        header = meta.get("header")
        if header is None:
            self.problems.append(f"trace_header_missing:{name}")
            return
        if header.get("schema") != "scheme-a-clock-diagnostics-v1":
            self.problems.append(f"trace_schema_mismatch:{name}")
        if header.get("run_id") != self.run_doc.get("run_id"):
            self.problems.append(f"trace_run_id_mismatch:{name}")
        if header.get("boot_id") != self.run_doc.get("boot_id"):
            self.problems.append(f"trace_boot_id_mismatch:{name}")
        host_boot = self.diagnostics.get("host_boot_id")
        if not host_boot or header.get("host_boot_id") != host_boot:
            self.problems.append(f"trace_host_boot_mismatch:{name}")
        node = (self.run_doc.get("nodes") or {}).get(name) or {}
        if node.get("pid") != header.get("pid"):
            self.problems.append(f"trace_pid_mismatch:{name}")
        elf = node.get("exe_sha256")
        if not is_hex64(elf):
            self.problems.append(f"elf_sha_not_full:{name}")
        ready = self.spawn.get(name) or {}
        if ready.get("actual_exe_sha256") and elf and ready["actual_exe_sha256"] != elf:
            self.problems.append(f"elf_sha_differs_from_proc:{name}")
        if ready.get("starttime") is None or node.get("starttime") is None:
            self.problems.append(f"starttime_missing:{name}")
        elif ready["starttime"] != node["starttime"]:
            self.problems.append(f"starttime_differs_from_proc:{name}")
        if ready.get("pid") not in (None, node.get("pid")):
            self.problems.append(f"proc_pid_differs:{name}")

    def check_trace_integrity(self, name: str) -> None:
        meta = self.trace_meta[name]
        summary = meta.get("summary")
        if summary is None:
            self.problems.append(f"trace_summary_missing:{name}")
        else:
            if not summary.get("complete"):
                self.problems.append(f"trace_incomplete:{name}")
            if summary.get("dropped"):
                self.problems.append(f"trace_dropped:{name}:{summary.get('dropped')}")
        markers = self.diagnostics.get("flush_markers") or {}
        if name in markers and not markers[name]:
            self.problems.append(f"flush_marker_false:{name}")
        flows: dict[str, list[dict]] = {}
        for row in self.traces[name]:
            flows.setdefault(row.get("stream"), []).append(row)
        for stream, rows in flows.items():
            expected = 1
            for row in rows:
                if row.get("seq") != expected:
                    self.problems.append(
                        f"trace_sequence_broken:{name}:{stream}:"
                        f"{row.get('seq')}!={expected}")
                    break
                expected += 1
        self.check_timebase(name)

    def check_timebase(self, name: str) -> None:
        """按行校验 mapped = origin + sim；resync 合法改变 origin。"""
        for row in self.traces[name]:
            if "mapped_steady_ns" not in row:
                continue
            origin = row.get("origin_ns")
            sim = row.get("sim_ns")
            mapped = row.get("mapped_steady_ns")
            if origin is None or sim is None or mapped is None:
                self.problems.append(f"mapped_row_missing_origin:{name}:{row.get('seq')}")
                continue
            if origin + sim != mapped:
                self.problems.append(f"mapped_not_origin_plus_sim:{name}:{row.get('seq')}")

    def load_proc(self) -> None:
        proc_dir = self.run / "proc"
        recorded = self.diagnostics.get("proc") or {}
        for name in ("plant", "worker", "regulator"):
            path = proc_dir / f"{name}.ready.json"
            if not path.is_file():
                continue
            if recorded:
                entry = recorded.get(f"{name}.ready.json") or {}
                if entry.get("sha256") and sha256_file(path) != entry["sha256"]:
                    self.problems.append(f"proc_sha_mismatch:{name}")
            try:
                self.spawn[name] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.problems.append(f"proc_unparsable:{name}")
        samples = self.run / "proc-samples.jsonl"
        if samples.is_file():
            entry = recorded.get("samples") or {}
            if entry.get("sha256") and sha256_file(samples) != entry["sha256"]:
                self.problems.append("proc_samples_sha_mismatch")
            rows, problems = read_jsonl(samples)
            self.problems.extend(problems)
            self.proc_samples = rows
        elif self.diagnostics.get("sampler_started"):
            self.problems.append("proc_samples_missing")
        self.proc_meta = {"samples": len(self.proc_samples),
                          "nodes": sorted(self.spawn)}

    def load_sources(self) -> None:
        for name in ("plant", "regulator", "worker"):
            path = self.run / f"{name}.source.jsonl"
            if not path.is_file():
                continue
            rows, problems = read_jsonl(path)
            self.problems.extend(f"{name}:{problem}" for problem in problems)
            self.source_rows[name] = rows

    # -- 时间线 ----------------------------------------------------------
    def rows(self, node: str, event: str) -> list[dict]:
        return [row for row in self.traces.get(node, []) if row.get("event") == event]

    def spans(self, node: str, begin_event: str, end_event: str) -> list[dict]:
        opens: dict[tuple, dict] = {}
        out: list[dict] = []
        for row in self.traces.get(node, []):
            key = (row.get("stream"), row.get("call_id"), row.get("span_id"))
            if row.get("event") == begin_event:
                opens.setdefault(key, row)
            elif row.get("event") == end_event and key in opens:
                start = opens.pop(key)
                out.append({"begin": start, "end": row,
                            "start_ns": start.get("at_ns"),
                            "end_ns": row.get("at_ns"),
                            "duration_ns": (row.get("at_ns") or 0) - (start.get("at_ns") or 0),
                            "kind": row.get("kind"),
                            "sim_ns": start.get("sim_ns")})
        for key, start in opens.items():
            self.problems.append(f"span_unpaired:{node}:{begin_event}:{key}")
        return out

    def clock_publishes(self) -> list[dict]:
        return self.spans("plant", "clock_publish_begin", "clock_publish_end")

    def clock_entries(self) -> list[dict]:
        return [row for row in self.rows("regulator", "clock_callback_begin")]

    def callback_kinds(self) -> list[dict]:
        return self.spans("regulator", "callback_begin", "callback_end")

    def analyse(self) -> dict:
        publishes = self.clock_publishes()
        entries = self.clock_entries()
        callback_spans = self.callback_kinds()
        result: dict = {
            "schema": PROBLEM_SCHEMA,
            "run": str(self.run),
            "scenario": self.run_doc.get("scenario"),
            "run_id": self.run_doc.get("run_id"),
            "host_boot_id": self.diagnostics.get("host_boot_id"),
            "identity": {
                "binding": self.run_doc.get("binding"),
                "elf": {name: ((self.run_doc.get("nodes") or {}).get(name) or {}).get("exe_sha256")
                        for name in (self.run_doc.get("nodes") or {})},
                "trace_headers": {name: (meta.get("header") or {}).get("producer")
                                  for name, meta in self.trace_meta.items()},
                "proc": self.proc_meta,
            },
            "original_checker": self.original_checker(),
            "clock_publishes": len(publishes),
            "clock_entries": len(entries),
            "gaps": [],
            "mapped_gaps": self.mapped_gaps(publishes),
            "timebase": self.timebase(publishes),
            "receive_catchup": self.receive_catchup(),
            "schedule_chain": self.schedule_chain(),
            "receipts": self.receipts(),
            "localized_stages": [],
            "publish_links": self.publish_links(entries, publishes),
            "proc_sampling": self.proc_sampling(),
            "production": self.production(),
            "root_cause": "unresolved",
            "problems": self.problems,
        }
        result["gaps"] = self.entry_gaps(entries, publishes)
        stages: list[str] = []
        for gap in result["gaps"]:
            for stage in gap["stages"]:
                if stage not in stages:
                    stages.append(stage)
        result["localized_stages"] = stages
        complete = not self.problems
        result["evidence_status"] = "complete" if complete else "incomplete"
        if not complete:
            result["clock_gap_observed"] = None
            result["gaps"] = result["gaps"] if result["gaps"] else []
        elif result["gaps"]:
            result["clock_gap_observed"] = True
        else:
            result["clock_gap_observed"] = False
            result["conclusion"] = "not reproduced in this run"
        return result

    def original_checker(self) -> dict:
        path = self.run / "check.json"
        if not path.is_file():
            return {"present": False, "verdict": None, "failures": []}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"present": True, "verdict": None, "failures": ["unparsable"]}
        return {"present": True, "verdict": document.get("verdict"),
                "failures": document.get("failures", []),
                "checks": [{"check": row.get("check"), "ok": row.get("ok")}
                           for row in document.get("checks", [])]}

    def mapped_gaps(self, publishes: list[dict]) -> list[dict]:
        out: list[dict] = []
        for previous, current in zip(publishes, publishes[1:]):
            before = previous["begin"].get("sim_ns")
            after = current["begin"].get("sim_ns")
            if before is None or after is None:
                continue
            gap = after - before
            if gap <= SUBSTEP_NS:
                continue
            out.append({"from_sim_ns": before, "to_sim_ns": after,
                        "mapped_gap_ns": gap,
                        "from_line": previous["begin"].get("__line__"),
                        "to_line": current["begin"].get("__line__"),
                        "mapped_steady_ns": current["begin"].get("mapped_steady_ns")})
        return out

    def timebase(self, publishes: list[dict]) -> dict:
        """把映射差、追赶子步、单次 pump 子步、真实发布差分开呈现。"""
        mapped = self.mapped_gaps(publishes)
        catch_up = self.receive_catchup()
        pump_steps = [span for span in self.spans("plant", "step_begin", "step_end")
                      if span.get("kind") == "pump"]
        actual = None
        if publishes:
            actuals = [span["start_ns"] for span in publishes]
            if len(publishes) >= 2:
                actual = actuals[-1] - actuals[-2]
        biggest = max(mapped, key=lambda row: row["mapped_gap_ns"]) if mapped else None
        catch_up_ns = sum(row["catch_up_substeps"] for row in catch_up) * SUBSTEP_NS
        pump_ns = len(pump_steps) * SUBSTEP_NS
        return {
            "mapped_gap_ns": biggest["mapped_gap_ns"] if biggest else 0,
            "mapped_gap_from_sim_ns": biggest["from_sim_ns"] if biggest else None,
            "mapped_gap_to_sim_ns": biggest["to_sim_ns"] if biggest else None,
            "receive_catchup_ns": catch_up_ns,
            "receive_catchup_substeps": sum(row["catch_up_substeps"] for row in catch_up),
            "pump_step_ns": pump_ns,
            "pump_step_count": len(pump_steps),
            "actual_publish_gap_ns": actual,
            "note": ("mapped=origin+sim is simulated time; the 50 ms publish spacing "
                     "is the physical substep (T/4), not a 5 ms poll deficit"),
        }

    def receive_catchup(self) -> list[dict]:
        out: list[dict] = []
        for row in self.rows("plant", "receive_locked"):
            if row.get("span_id") != 1:
                continue
            subtotal = row.get("advance_substeps") or 0
            if subtotal <= 0:
                continue
            out.append({"line": row.get("__line__"), "at_ns": row.get("at_ns"),
                        "sim_before_ns": row.get("sim_before_ns"),
                        "sim_ns": row.get("sim_ns"),
                        "catch_up_substeps": subtotal,
                        "call_id": row.get("call_id")})
        return out

    def entry_gaps(self, entries: list[dict], publishes: list[dict]) -> list[dict]:
        gaps: list[dict] = []
        ordered = sorted(entries, key=lambda row: row.get("at_ns") or 0)
        publishes_sorted = sorted(publishes, key=lambda span: span["start_ns"] or 0)
        for previous, current in zip(ordered, ordered[1:]):
            gap = (current.get("at_ns") or 0) - (previous.get("at_ns") or 0)
            if gap < ENTRY_GAP_LEAD_NS:
                continue
            window = (previous.get("at_ns"), current.get("at_ns"))
            gaps.append({
                "kind": "callback_entry",
                "entry_gap_ns": gap,
                "from_ns": previous.get("at_ns"),
                "to_ns": current.get("at_ns"),
                "from_sim_ns": previous.get("sim_ns"),
                "to_sim_ns": current.get("sim_ns"),
                "from_line": previous.get("__line__"),
                "to_line": current.get("__line__"),
                "stages": self.stages_for(window, publishes_sorted),
                # 覆盖或落在窗口内的发布都列出：入口可能早于 publish 返回，
                # 因此相对 publish_end 的负残差是合法事实，原样保留。
                "publish_inside_window": [
                    {"sim_ns": span["begin"].get("sim_ns"),
                     "start_ns": span["start_ns"],
                     "end_ns": span["end_ns"],
                     "duration_ns": span["duration_ns"],
                     "relative_to_gap_start_ns": (span["start_ns"] or 0) - window[0],
                     "relative_to_gap_end_ns": (span["start_ns"] or 0) - window[1]}
                    for span in publishes_sorted
                    if (span["start_ns"] or 0) <= window[1] and
                    (span["end_ns"] or 0) >= window[0]],
            })
        return gaps

    @staticmethod
    def _dominant(span: dict, window: tuple[int, int]) -> bool:
        """区间占这段断档的一半以上才算"覆盖"，否则只是恰好落在旁边。"""
        start, end = window
        overlap = min(span["end_ns"], end) - max(span["start_ns"], start)
        width = max(1, end - start)
        return overlap > 0 and overlap * 2 >= width

    def stages_for(self, window: tuple[int, int], publishes: list[dict]) -> list[str]:
        """按 span 覆盖定位阶段；可同时保留多个标签，绝不硬选唯一原因。"""
        stages: list[str] = []
        for span in self.spans("plant", "source_io_begin", "source_io_end"):
            if self._dominant(span, window):
                stages.append("source_io")
        for span in self.spans("plant", "step_begin", "step_end"):
            if self._dominant(span, window):
                stages.append("physical_step")
        for event_pair in (("publish_begin", "publish_end"),
                           ("clock_publish_begin", "clock_publish_end")):
            for span in self.spans("plant", *event_pair):
                if self._dominant(span, window) and "publisher_call" not in stages:
                    stages.append("publisher_call")
        # pump 入口到获得状态锁的调度延迟：这是 timer/executor 唯一的直接证据。
        for span in self.pump_waits():
            if self._dominant(span, window):
                stages.append("timer_or_executor")
        for span in self.spans("regulator", "callback_begin", "callback_end"):
            if self._dominant(span, window):
                label = f"executor_busy:{span.get('kind')}"
                if label not in stages:
                    stages.append(label)
        for span in self.clock_lock_spans():
            if self._dominant(span, window):
                stages.append("state_lock")
        start, end = window
        catch_up = [row for row in self.receive_catchup()
                    if start <= (row.get("at_ns") or 0) <= end]
        if catch_up:
            stages.append("receive_catchup")
        published = [span for span in publishes if start <= (span["start_ns"] or 0) <= end]
        if published and not stages:
            stages.append("delivery_or_executor")
        if not stages:
            stages.append("unattributed")
        return stages

    def publish_links(self, entries: list[dict], publishes: list[dict]) -> list[dict]:
        """入场与发布按 sim 配对；publish_end 的负残差原样保留，不判时基错误。"""
        by_sim: dict[int, list[dict]] = {}
        for span in publishes:
            sim = span["begin"].get("sim_ns")
            if sim is None:
                continue
            by_sim.setdefault(sim, []).append(span)
        links: list[dict] = []
        for entry in entries:
            sim = entry.get("sim_ns")
            candidates = by_sim.get(sim) or []
            record = {"sim_ns": sim,
                      "entry_ns": entry.get("at_ns"),
                      "entry_line": entry.get("__line__"),
                      "candidate_publishes": len(candidates)}
            if len(candidates) == 1:
                span = candidates[0]
                record.update({
                    "publish_begin_ns": span["start_ns"],
                    "publish_end_ns": span["end_ns"],
                    "entry_minus_publish_begin_ns": entry.get("at_ns") - span["start_ns"],
                    "entry_minus_publish_end_ns": entry.get("at_ns") - span["end_ns"],
                    "ambiguous": False,
                })
                if record["entry_minus_publish_begin_ns"] < 0:
                    # 入口早于发布开始：这只可能是时基/归属错误，必须留痕。
                    self.problems.append(
                        f"entry_before_publish_begin:{entry.get('__line__')}")
            elif len(candidates) > 1:
                record["ambiguous"] = True
                self.problems.append(f"ambiguous_publish_link:{sim}")
            else:
                record["ambiguous"] = False
            links.append(record)
        return links

    def pump_waits(self) -> list[dict]:
        out: list[dict] = []
        opens: dict[tuple, dict] = {}
        for row in self.traces.get("plant", []):
            key = (row.get("stream"), row.get("call_id"), row.get("span_id"))
            if row.get("event") == "pump_begin":
                opens[key] = row
            elif row.get("event") == "pump_locked" and key in opens:
                start = opens.pop(key)
                out.append({"begin": start, "end": row,
                            "start_ns": start.get("at_ns"),
                            "end_ns": row.get("at_ns"),
                            "duration_ns": (row.get("at_ns") or 0) - (start.get("at_ns") or 0)})
        return out

    def clock_lock_spans(self) -> list[dict]:
        """回调入口到获得状态锁之间的等待，是唯一可归因的锁跨度。"""
        out: list[dict] = []
        opens: dict[tuple, dict] = {}
        for row in self.traces.get("regulator", []):
            key = (row.get("stream"), row.get("call_id"), row.get("span_id"))
            if row.get("event") == "clock_callback_begin":
                opens[key] = row
            elif row.get("event") == "clock_callback_locked" and key in opens:
                start = opens.pop(key)
                out.append({"begin": start, "end": row,
                            "start_ns": start.get("at_ns"),
                            "end_ns": row.get("at_ns"),
                            "duration_ns": (row.get("at_ns") or 0) - (start.get("at_ns") or 0)})
        return out

    def schedule_chain(self) -> dict:
        rows = [row for row in self.traces.get("regulator", [])
                if row.get("event") in ("pause", "resume", "clock_epoch_change",
                                        "schedule_reset")]
        rows.sort(key=lambda row: row.get("at_ns") or 0)
        chain = []
        for row in rows:
            chain.append({"event": row.get("event"),
                          "at_ns": row.get("at_ns"),
                          "sim_ns": row.get("sim_ns"),
                          "schedule_runtime": row.get("schedule_runtime"),
                          "schedule_grid": row.get("schedule_grid"),
                          "epoch": row.get("epoch"),
                          "line": row.get("__line__"),
                          "detail": {key: row[key] for key in
                                     ("previous_sim_ns", "last_advance_ns", "threshold_ns",
                                      "last_schedule", "tick_before", "tick_after",
                                      "origin_before_ns", "origin_after_ns")
                                     if key in row}})
        resets = [row for row in chain if row["event"] == "schedule_reset"]
        pauses = [row for row in chain if row["event"] == "pause"]
        resumes = [row for row in chain if row["event"] == "resume"]
        # 内部 runtime schedule 与冻结 grid 轴必须分别呈现；旧 decision.schedule
        # 字段只反映 grid，不能用来否认 runtime 变化。
        rows_with_axes = [row for row in self.traces.get("regulator", [])
                          if row.get("schedule_grid") is not None
                          or row.get("schedule_runtime") is not None]
        decision_grid = sorted({row.get("schedule_grid") for row in rows_with_axes
                                if row.get("schedule_grid") is not None})
        runtime_axes = sorted({row.get("schedule_runtime") for row in rows_with_axes
                               if row.get("schedule_runtime") is not None})
        # 旧 decision 行的 schedule_generation 序列化的是 grid_.schedule_generation。
        decision_rows_grid = sorted({row.get("schedule_generation")
                                     for row in self.source_rows.get("regulator", [])
                                     if row.get("type") == "decision"
                                     and row.get("schedule_generation") is not None})
        closed = bool(pauses and resumes and resets)
        return {
            "chain": chain,
            "runtime_schedule_values": runtime_axes,
            "grid_schedule_values": decision_grid,
            "decision_field_grid_values": decision_rows_grid,
            "chain_closed": closed,
            "reset_count": len(resets),
            "note": ("runtime schedule lives on version_.schedule; the frozen grid axis "
                     "stays at the plan value and does not describe runtime changes"),
        }

    def receipts(self) -> dict:
        rows = [row for row in self.traces.get("regulator", [])
                if row.get("event") in ("receipt_callback_begin",
                                        "receipt_callback_locked",
                                        "receipt_callback_end")]
        entries = [row for row in rows if row.get("event") == "receipt_callback_begin"]
        entries.sort(key=lambda row: row.get("at_ns") or 0)
        order = []
        for row in entries:
            order.append({"sequence": row.get("sequence"),
                          "execution_index": row.get("execution_index"),
                          "at_ns": row.get("at_ns"),
                          "line": row.get("__line__")})
        sequences = [row.get("sequence") for row in entries]
        increasing = all((a or 0) <= (b or 0) for a, b in zip(sequences, sequences[1:]))
        source = [row for row in self.source_rows.get("regulator", [])
                  if row.get("type") == "plant_receipt_admission"]
        gaps = [row for row in source if row.get("sequence_gap") or row.get("bootstrap_required")]
        rejects = [row for row in source if row.get("disposition") == "rejected"]
        holds = [row for row in self.source_rows.get("regulator", [])
                 if row.get("type") == "plant_hold_close_admission"]
        return {
            "observed_order": order,
            "sequence_increasing": increasing,
            "source_sequence_gaps": [{"sequence": row.get("sequence"),
                                      "sequence_gap": row.get("sequence_gap"),
                                      "bootstrap_required": row.get("bootstrap_required")}
                                     for row in gaps],
            "rejections": [{"sequence": row.get("sequence"),
                            "reason": row.get("admission_reason") or row.get("reason"),
                            "accepted": row.get("accepted"),
                            "line": row.get("__line__")} for row in rejects],
            "hold_closes": [{"execution_index": row.get("execution_index"),
                             "reason": row.get("reason"),
                             "truncated": row.get("truncated"),
                             "line": row.get("__line__")} for row in holds[-5:]],
            "note": ("order is reported as observed; a rejected receipt published before "
                     "an ok receipt is not re-sorted into a PASS"),
        }

    def proc_sampling(self) -> dict:
        if not self.proc_samples:
            return {"supported": [], "reason": "no samples"}
        per_node: dict[str, dict] = {}
        for sample in self.proc_samples:
            for task in sample.get("tasks", []):
                name = task.get("name")
                record = per_node.setdefault(name, {"samples": 0, "gone": 0,
                                                    "pid_reused": 0,
                                                    "schedstat": None,
                                                    "cpu": [None, None],
                                                    "pressure": None})
                record["samples"] += 1
                if task.get("gone"):
                    record["gone"] += 1
                    continue
                if task.get("pid_reused"):
                    record["pid_reused"] += 1
                counters = task.get("schedstat")
                if isinstance(counters, list) and len(counters) == 3:
                    record["schedstat"] = counters
                if task.get("cpu_pressure"):
                    record["pressure"] = task["cpu_pressure"]
        supported = []
        for name, record in per_node.items():
            if record["schedstat"] is not None:
                supported.append(f"{name}:schedstat_runqueue_ns")
            if record["pressure"]:
                supported.append(f"{name}:cpu_pressure")
        return {"nodes": per_node, "supported": supported,
                "sample_count": len(self.proc_samples),
                "note": ("cumulative counters are supportive only; without a usable "
                         "runqueue metric this run does not rank CPU versus DDS causes")}

    def production(self) -> dict:
        before = self.diagnostics.get("production_before") or {}
        after = self.diagnostics.get("production_after") or {}
        changed = [field for field in STABLE_PRODUCTION_FIELDS
                   if before.get(field) != after.get(field)]
        recorded = self.diagnostics.get("production_changed") or []
        return {"before_changed": recorded, "after_changed": changed,
                "unchanged": not changed and not recorded,
                "monitor_events": [row for row in self.run_doc.get("events", [])
                                   if row.get("type") == "production_changed"][:5]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--contract", default=None)
    parser.add_argument("--source-hashes", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists():
        print(json.dumps({"error": "refusing to overwrite an existing diagnosis",
                          "out": str(out)}))
        return 2
    diagnosis = Diagnosis(Path(args.run), Path(args.plan),
                          Path(args.contract) if args.contract else None,
                          Path(args.source_hashes) if args.source_hashes else None)
    diagnosis.load()
    document = diagnosis.analyse()
    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with open(out, "x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError:
        print(json.dumps({"error": "out appeared concurrently", "out": str(out)}))
        return 2
    summary = {"evidence_status": document["evidence_status"],
               "clock_gap_observed": document["clock_gap_observed"],
               "root_cause": document["root_cause"],
               "localized_stages": document["localized_stages"],
               "original_checker": (document["original_checker"] or {}).get("verdict"),
               "entry_gap_ns": max((gap["entry_gap_ns"] for gap in document["gaps"]),
                                   default=None),
               "out": str(out)}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if document["evidence_status"] == "complete" else 2


if __name__ == "__main__":
    sys.exit(main())
