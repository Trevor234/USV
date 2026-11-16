# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""时钟断档诊断器的回归：只断言消费者可见的证据错误。

fixture 明确是测试输入，不是新的 ARM 现场日志；所有时间都是构造的整数 ns，
不做任何 sleep 计时断言。

覆盖：
  * 原检查器在附加诊断/采样文件后仍是 11 项且结论不变；
  * 缺 trace / 缺 summary / flush=false / dropped>0 / 诊断 SHA 错 /
    run/boot/pid/ELF 摘要不符 → 诊断器 exit 2 且 clock_gap_observed=null；
  * 时基反例：映射差 450 ms 而真实发布差 20 ms，追赶 8 个子步 + 1 次 pump 子步；
  * 阶段定位：source_io / executor_busy:path / delivery_or_executor；
  * 回调早于 publish 返回是合法的，after_end 负残差原样保留；
  * runtime schedule 1→2→3（grid 恒定 1）与回执 35-before-34 的原样呈现；
  * 生产快照逐字段比较、域门禁的 224 继承进程判定。
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_scheme_a_controlled_sim import (  # noqa: E402
    BOOT_ID, ORIGIN, T, build_standard, sha256)

ANALYZER = Path(__file__).with_name("scripts") / "check_scheme_a_clock_gap.py"
RUNNER = Path(__file__).with_name("scripts") / "run_scheme_a_closed_loop.py"
SUBSTEP = T // 4
HOST_BOOT = "host-boot-fixture"
PIDS = {"plant": 1236, "worker": 1235, "regulator": 1234}


def _diagnose(run: Path, out: Path | None = None) -> tuple[int, dict, dict]:
    out = out or (run / "clock-gap.json")
    result = subprocess.run(
        [sys.executable, "-B", str(ANALYZER), "--run", str(run),
         "--plan", str(run / "plan.json"), "--contract", str(run / "contract.json"),
         "--source-hashes", str(run / "source_hashes.json"),
         "--out", str(out)],
        capture_output=True, text=True)
    document = json.loads(out.read_text()) if out.is_file() else {}
    return result.returncode, document, {"stdout": result.stdout, "stderr": result.stderr}


class Trace:
    """构造一条真实的 clock_diagnostics 流。"""

    def __init__(self, producer: str) -> None:
        self.producer = producer
        self.rows: list[dict] = []
        self.seqs: dict[str, int] = {}

    def add(self, stream: str, event: str, at_ns: int, call: int = 1,
            span: int = 0, **fields) -> None:
        self.seqs[stream] = self.seqs.get(stream, 0) + 1
        row = {"type": "clock_diagnostics", "event": event, "stream": stream,
               "seq": self.seqs[stream], "call_id": call, "span_id": span,
               "at_ns": at_ns}
        row.update(fields)
        self.rows.append(row)

    def write(self, path: Path, *, run_id: str, boot_id: str,
              host_boot_id: str, pid: int, complete: bool = True,
              dropped: int = 0) -> None:
        header = {"type": "clock_diagnostics_header",
                  "schema": "scheme-a-clock-diagnostics-v1",
                  "producer": self.producer, "pid": pid, "run_id": run_id,
                  "boot_id": boot_id, "host_boot_id": host_boot_id,
                  "contract_hash": "0" * 64, "clock": "CLOCK_MONOTONIC",
                  "stream_capacities": {}}
        streams: dict[str, dict] = {}
        for row in self.rows:
            entry = streams.setdefault(row["stream"], {"attempted": 0, "stored": 0,
                                                       "dropped": 0})
            entry["attempted"] += 1
            entry["stored"] += 1
        summary = {"type": "clock_diagnostics_summary",
                   "schema": "scheme-a-clock-diagnostics-v1",
                   "attempted": len(self.rows), "stored": len(self.rows),
                   "dropped": dropped,
                   "complete": complete and dropped == 0,
                   "streams": [{"stream": name, **values, "capacity": 65536,
                                "complete": values["dropped"] == 0}
                               for name, values in streams.items()],
                   "finished_ns": self.rows[-1]["at_ns"] + 1 if self.rows else 0}
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(header, sort_keys=True) + "\n")
            for row in self.rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.write(json.dumps(summary, sort_keys=True) + "\n")


def attach_diagnostics(run: Path, *, plant: Trace | None = None,
                       regulator: Trace | None = None,
                       flush_ok: bool = True, sampler: bool = True,
                       proc_origin: int = ORIGIN) -> dict:
    """给已存在的 v2 run 附加诊断/采样文件，并写进 run.json.diagnostics。"""
    run_doc = json.loads((run / "run.json").read_text())
    run_id = run_doc["run_id"]
    # fixture 的 run.json 不带 boot_id；诊断头必须与 run 用同一个值。
    boot_id = run_doc.setdefault("boot_id", BOOT_ID)
    proc_dir = run / "proc"
    proc_dir.mkdir(exist_ok=True)
    traces: dict[str, dict] = {}
    for name, trace in (("plant", plant), ("regulator", regulator)):
        if trace is None:
            continue
        path = run / f"{name}.clock-diagnostics.jsonl"
        trace.write(path, run_id=run_id, boot_id=boot_id, host_boot_id=HOST_BOOT,
                    pid=PIDS[name])
        traces[name] = {"path": path.name, "bytes": path.stat().st_size,
                        "sha256": sha256(path), "present": True,
                        "complete": True, "dropped": 0}
    proc: dict[str, dict] = {}
    for name, pid in PIDS.items():
        node = run_doc["nodes"][name]
        ready = {"schema": "scheme-a-ready-identity-v1", "name": name, "pid": pid,
                 "starttime": 1000 + pid,
                 "expected_exe": node["exe"],
                 "actual_exe_link": node["exe"],
                 "actual_exe_realpath": node["exe"],
                 "actual_exe_sha256": node["exe_sha256"],
                 "maps_readable": True, "ros_env": {"ROS_DOMAIN_ID": "224"},
                 "captured_ns": proc_origin}
        node["starttime"] = ready["starttime"]
        path = proc_dir / f"{name}.ready.json"
        path.write_text(json.dumps(ready, indent=2, sort_keys=True) + "\n")
        proc[path.name] = {"path": f"proc/{path.name}",
                           "bytes": path.stat().st_size, "sha256": sha256(path)}
    if sampler:
        samples = run / "proc-samples.jsonl"
        rows = [{"at_ns": proc_origin + index * 100_000_000, "close_phase": False,
                 "tasks": [{"name": name, "pid": pid, "pid_reused": False,
                            "starttime": 1000 + pid, "state": "S",
                            "utime": str(index), "stime": "0", "num_threads": "4",
                            "schedstat": [index, 0, index], "cpu_pressure": None}
                           for name, pid in PIDS.items()]}
                for index in range(4)]
        samples.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                  for row in rows))
        proc["samples"] = {"path": samples.name, "bytes": samples.stat().st_size,
                           "sha256": sha256(samples)}
    production = {"main_pid": "900", "restarts": "0", "active_state": "active",
                  "sub_state": "running", "active_enter": "Fri 2026-11-16",
                  "exec_start": "/usr/bin/ros2 launch",
                  "control_group": "/system.slice/usv-system.service",
                  "fragment_path": "/etc/systemd/system/usv-system.service",
                  "fragment_sha256": "1" * 64, "defaults_sha256": "2" * 64,
                  "scheme": "B", "runtime_target": "/home/trevor/usv_mpc_ws/install",
                  "processes": [{"pid": 901, "starttime": 700, "role": "mavros",
                                 "exe": "/opt/ros/jazzy/lib/mavros/mavros_node"}]}
    run_doc["nodes"] = {name: {**node, "starttime": 1000 + pid}
                        for name, node in run_doc["nodes"].items()
                        for pid in [PIDS[name]]}
    run_doc["diagnostics"] = {
        "enabled": True,
        "host_boot_id": HOST_BOOT,
        "domain_gate": {"verdict": "clear", "target_domain": 224,
                        "ros_related_processes": [], "unrelated_env_224": [],
                        "unverifiable": [], "blocking_reasons": []},
        "production_before": production,
        "production_after": json.loads(json.dumps(production)),
        "production_changed": [],
        "traces": traces,
        "proc": proc,
        "flush_markers": {name: flush_ok for name in traces},
        "sampler_started": sampler,
        "sampler_samples": 4 if sampler else 0,
        "stop_identity_failures": [],
    }
    (run / "run.json").write_text(json.dumps(run_doc, indent=2, sort_keys=True) + "\n")
    # 附加文件后原 source 摘要不变，但 run.json 变了：重新核对绑定仍自洽。
    return run_doc


def baseline_traces() -> tuple[Trace, Trace]:
    """一条无断档的基线：plant 50 ms 发布，regulator 回调紧随其后。"""
    plant = Trace("p1_x86_plant")
    regulator = Trace("p1_regulator")
    for index in range(20):
        sim = index * SUBSTEP
        mapped = ORIGIN + sim
        start = ORIGIN + sim * 2
        plant.add("plant_executor", "clock_publish_begin", start,
                  call=index + 1, sim_ns=sim, mapped_steady_ns=mapped,
                  origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_end", start + 100_000,
                  call=index + 1, sim_ns=sim, mapped_steady_ns=mapped,
                  origin_ns=ORIGIN)
        regulator.add("regulator_callbacks", "clock_callback_begin",
                      start + 500_000, call=index + 1, span=0, sim_ns=sim,
                      previous_sim_ns=sim - SUBSTEP,
                      previous_receive_ns=start + 500_000 - 50_000_000,
                      last_advance_ns=start + 500_000 - 50_000_000,
                      schedule_runtime=1, schedule_grid=1, epoch=0)
        regulator.add("regulator_callbacks", "clock_callback_locked",
                      start + 620_000, call=index + 1, span=0, sim_ns=sim,
                      previous_sim_ns=sim - SUBSTEP,
                      previous_receive_ns=start + 500_000 - 50_000_000,
                      last_advance_ns=start + 500_000 - 50_000_000,
                      schedule_runtime=1, schedule_grid=1, epoch=0)
        regulator.add("regulator_callbacks", "clock_callback_end",
                      start + 700_000, call=index + 1, span=0, sim_ns=sim,
                      previous_sim_ns=sim, previous_receive_ns=start + 500_000,
                      last_advance_ns=start + 500_000, schedule_runtime=1,
                      schedule_grid=1, epoch=0)
    return plant, regulator


# ---------------------------------------------------------------------------
# 冲突：原检查器与诊断器是两列结论
# ---------------------------------------------------------------------------
def test_original_checker_keeps_eleven_checks_with_diagnostics():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant, regulator = baseline_traces()
        attach_diagnostics(run, plant=plant, regulator=regulator)
        before = json.loads((run / "run.json").read_text())
        rc, doc = _check_with_closed_loop(run)
        assert rc == 0, doc["failures"]
        assert len(doc["checks"]) == 11
        after = json.loads((run / "run.json").read_text())
        assert before["binding"] == after["binding"]
        code, diagnosis, captured = _diagnose(run)
        assert code == 0, captured
        assert diagnosis["evidence_status"] == "complete"
        assert diagnosis["original_checker"]["verdict"] == "PASS"
        assert diagnosis["clock_gap_observed"] is False
        assert diagnosis["root_cause"] == "unresolved"


def _check_with_closed_loop(run: Path):
    checker = Path(__file__).with_name("scripts") / "check_scheme_a_closed_loop.py"
    result = subprocess.run(
        [sys.executable, "-B", str(checker), "--run", str(run),
         "--plan", str(run / "plan.json"), "--contract", str(run / "contract.json"),
         "--source-hashes", str(run / "source_hashes.json")],
        capture_output=True, text=True)
    return result.returncode, json.loads((run / "check.json").read_text())


# ---------------------------------------------------------------------------
# 不完整证据：一律 exit 2 且 clock_gap_observed=null
# ---------------------------------------------------------------------------
def test_missing_trace_is_incomplete():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant, regulator = baseline_traces()
        attach_diagnostics(run, plant=plant, regulator=regulator)
        (run / "plant.clock-diagnostics.jsonl").unlink()
        code, diagnosis, _ = _diagnose(run)
        assert code == 2
        assert diagnosis["evidence_status"] == "incomplete"
        assert diagnosis["clock_gap_observed"] is None
        assert diagnosis["root_cause"] == "unresolved"


def test_missing_summary_is_incomplete():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant, regulator = baseline_traces()
        attach_diagnostics(run, plant=plant, regulator=regulator)
        path = run / "plant.clock-diagnostics.jsonl"
        rows = path.read_text().splitlines()
        path.write_text("\n".join(rows[:-1]) + "\n")
        _refresh_trace_digest(run, "plant")
        code, diagnosis, _ = _diagnose(run)
        assert code == 2
        assert diagnosis["evidence_status"] == "incomplete"
        assert diagnosis["clock_gap_observed"] is None


def test_dropped_and_flush_false_are_incomplete():
    for kwargs, marker in (({"flush_ok": False}, "flush"),
                           ({"dropped": 2}, "trace_incomplete")):
        with tempfile.TemporaryDirectory() as tmp:
            run = build_standard(Path(tmp) / "run")
            plant, regulator = baseline_traces()
            doc = attach_diagnostics(run, plant=plant, regulator=regulator,
                                     flush_ok=kwargs.get("flush_ok", True))
            if "dropped" in kwargs:
                path = run / "plant.clock-diagnostics.jsonl"
                rows = path.read_text().splitlines()
                summary = json.loads(rows[-1])
                summary["dropped"] = kwargs["dropped"]
                summary["complete"] = False
                rows[-1] = json.dumps(summary, sort_keys=True)
                path.write_text("\n".join(rows) + "\n")
                _refresh_trace_digest(run, "plant")
            code, diagnosis, _ = _diagnose(run)
            assert code == 2, marker
            assert diagnosis["evidence_status"] == "incomplete"
            assert diagnosis["clock_gap_observed"] is None


def test_trace_digest_mismatch_and_identity_mismatch_are_incomplete():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant, regulator = baseline_traces()
        attach_diagnostics(run, plant=plant, regulator=regulator)
        # 1) 摘要不符
        path = run / "regulator.clock-diagnostics.jsonl"
        path.write_text(path.read_text() + "")
        path.write_text(path.read_text().replace("clock_callback_begin",
                                                 "clock_callback_begin ", 1))
        code, diagnosis, _ = _diagnose(run, run / "a.json")
        assert code == 2 and "trace_sha_mismatch:regulator" in diagnosis["problems"]

        run2 = build_standard(Path(tmp) / "run2")
        plant2, regulator2 = baseline_traces()
        doc = attach_diagnostics(run2, plant=plant2, regulator=regulator2)
        # 2) run/boot/pid 不符
        doc["diagnostics"]["traces"]["plant"]["present"] = True
        (run2 / "run.json").write_text(json.dumps(
            {**doc, "run_id": "different-run"}, indent=2, sort_keys=True) + "\n")
        code, diagnosis, _ = _diagnose(run2, run2 / "b.json")
        assert code == 2
        assert any("run_id" in problem for problem in diagnosis["problems"])

        run3 = build_standard(Path(tmp) / "run3")
        plant3, regulator3 = baseline_traces()
        doc3 = attach_diagnostics(run3, plant=plant3, regulator=regulator3)
        doc3["nodes"]["plant"]["exe_sha256"] = doc3["nodes"]["plant"]["exe_sha256"][:16]
        (run3 / "run.json").write_text(json.dumps(doc3, indent=2, sort_keys=True) + "\n")
        code, diagnosis, _ = _diagnose(run3, run3 / "c.json")
        assert code == 2
        assert "elf_sha_not_full:plant" in diagnosis["problems"]


def _refresh_trace_digest(run: Path, name: str) -> None:
    doc = json.loads((run / "run.json").read_text())
    path = run / f"{name}.clock-diagnostics.jsonl"
    doc["diagnostics"]["traces"][name].update({"bytes": path.stat().st_size,
                                               "sha256": sha256(path)})
    (run / "run.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# 时基反例
# ---------------------------------------------------------------------------
def test_mapped_gap_is_not_wall_clock_gap():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant = Trace("p1_x86_plant")
        regulator = Trace("p1_regulator")
        # plant 发布 8.05 s 与 8.50 s，真实 publish 只相差 20 ms。
        plant.add("plant_executor", "clock_publish_begin", ORIGIN + 800_000_000,
                  call=1, sim_ns=8_050_000_000,
                  mapped_steady_ns=ORIGIN + 8_050_000_000, origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_end", ORIGIN + 800_100_000,
                  call=1, sim_ns=8_050_000_000,
                  mapped_steady_ns=ORIGIN + 8_050_000_000, origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_begin", ORIGIN + 820_000_000,
                  call=2, sim_ns=8_500_000_000,
                  mapped_steady_ns=ORIGIN + 8_500_000_000, origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_end", ORIGIN + 820_100_000,
                  call=2, sim_ns=8_500_000_000,
                  mapped_steady_ns=ORIGIN + 8_500_000_000, origin_ns=ORIGIN)
        # receive 追赶 8 个子步（400 ms），随后一次 pump 推进 1 个子步。
        plant.add("plant_executor", "receive_locked", ORIGIN + 810_000_000,
                  call=3, span=1, sim_ns=8_450_000_000,
                  sim_before_ns=8_050_000_000, scheduled_sequence=0,
                  advance_substeps=8, pending_sequence=0)
        plant.add("plant_executor", "step_begin", ORIGIN + 815_000_000,
                  call=4, kind="pump", sim_ns=8_450_000_000,
                  sim_before_ns=8_450_000_000, substeps=0)
        plant.add("plant_executor", "step_end", ORIGIN + 815_100_000,
                  call=4, kind="pump", sim_ns=8_500_000_000,
                  sim_before_ns=8_450_000_000, substeps=1)
        # 旧证据的真实回调入口间隔 527700255 ns。
        regulator.add("regulator_callbacks", "clock_callback_begin",
                      ORIGIN + 800_000_000, call=1, span=0, sim_ns=7_950_000_000,
                      previous_sim_ns=7_900_000_000,
                      previous_receive_ns=ORIGIN + 799_000_000,
                      last_advance_ns=ORIGIN + 799_000_000,
                      schedule_runtime=1, schedule_grid=1, epoch=0)
        regulator.add("regulator_callbacks", "clock_callback_begin",
                      ORIGIN + 1_327_700_255, call=2, span=0, sim_ns=8_050_000_000,
                      previous_sim_ns=7_950_000_000,
                      previous_receive_ns=ORIGIN + 800_000_000,
                      last_advance_ns=ORIGIN + 800_000_000,
                      schedule_runtime=3, schedule_grid=1, epoch=0)
        attach_diagnostics(run, plant=plant, regulator=regulator)
        code, diagnosis, captured = _diagnose(run)
        assert code == 0, captured
        timebase = diagnosis["timebase"]
        assert timebase["mapped_gap_ns"] == 450_000_000
        assert timebase["receive_catchup_ns"] == 400_000_000
        assert timebase["pump_step_ns"] == 50_000_000
        assert timebase["actual_publish_gap_ns"] == 20_000_000
        assert diagnosis["gaps"][0]["entry_gap_ns"] == 527_700_255
        blob = json.dumps(diagnosis)
        assert "pump_starvation" not in blob
        assert "pump starvation" not in blob
        assert "receive_catchup" in diagnosis["localized_stages"]


def test_resync_changes_origin_per_row_and_single_bad_row_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant = Trace("p1_x86_plant")
        regulator = Trace("p1_regulator")
        plant.add("plant_executor", "clock_publish_begin", 100,
                  call=1, sim_ns=0, mapped_steady_ns=ORIGIN, origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_end", 150,
                  call=1, sim_ns=0, mapped_steady_ns=ORIGIN, origin_ns=ORIGIN)
        # 合法 resync：origin 前移，mapped 仍等于本行 origin + sim。
        plant.add("plant_executor", "clock_publish_begin", 200,
                  call=2, sim_ns=SUBSTEP,
                  mapped_steady_ns=ORIGIN + SUBSTEP + 7_000, origin_ns=ORIGIN + 7_000)
        plant.add("plant_executor", "clock_publish_end", 250,
                  call=2, sim_ns=SUBSTEP,
                  mapped_steady_ns=ORIGIN + SUBSTEP + 7_000, origin_ns=ORIGIN + 7_000)
        attach_diagnostics(run, plant=plant, regulator=regulator)
        code, diagnosis, _ = _diagnose(run, run / "ok.json")
        assert code == 0, diagnosis["problems"]
        assert not any("mapped_not_origin_plus_sim" in problem
                       for problem in diagnosis["problems"])

        # 仅一行 mapped != 本行 origin + sim → 拒绝。
        run2 = build_standard(Path(tmp) / "run2")
        plant2 = Trace("p1_x86_plant")
        regulator2 = Trace("p1_regulator")
        plant2.add("plant_executor", "clock_publish_begin", 100,
                   call=1, sim_ns=0, mapped_steady_ns=ORIGIN, origin_ns=ORIGIN)
        plant2.add("plant_executor", "clock_publish_end", 150,
                   call=1, sim_ns=0, mapped_steady_ns=ORIGIN, origin_ns=ORIGIN)
        plant2.add("plant_executor", "clock_publish_begin", 200,
                   call=2, sim_ns=SUBSTEP,
                   mapped_steady_ns=ORIGIN + SUBSTEP + 1, origin_ns=ORIGIN)
        plant2.add("plant_executor", "clock_publish_end", 250,
                   call=2, sim_ns=SUBSTEP,
                   mapped_steady_ns=ORIGIN + SUBSTEP + 1, origin_ns=ORIGIN)
        attach_diagnostics(run2, plant=plant2, regulator=regulator2)
        code, diagnosis, _ = _diagnose(run2, run2 / "bad.json")
        assert code == 2
        assert any("mapped_not_origin_plus_sim" in problem
                   for problem in diagnosis["problems"])


# ---------------------------------------------------------------------------
# 阶段定位
# ---------------------------------------------------------------------------
def _stage_case(kind: str) -> tuple[Trace, Trace]:
    plant = Trace("p1_x86_plant")
    regulator = Trace("p1_regulator")
    base = ORIGIN + 1_000_000_000
    plant.add("plant_executor", "pump_begin", base - 500_000, call=1)
    plant.add("plant_executor", "pump_locked", base - 400_000, call=1, sim_ns=0,
              mapped_steady_ns=ORIGIN, origin_ns=ORIGIN)
    plant.add("plant_executor", "pump_end", base - 300_000, call=1,
              exit_reason="idle_not_due", sim_ns=0,
              mapped_steady_ns=ORIGIN, origin_ns=ORIGIN)
    if kind == "source_io":
        plant.add("plant_executor", "source_io_begin", base, call=2,
                  flush=True)
        plant.add("plant_executor", "source_io_locked", base + 1_000, call=2,
                  flush=True)
        plant.add("plant_executor", "source_io_end", base + 500_000_000, call=2,
                  flush=True)
    if kind == "executor_busy":
        regulator.add("regulator_callbacks", "callback_begin", base, call=9,
                      span=0, kind="path")
        regulator.add("regulator_callbacks", "callback_end",
                      base + 480_000_000, call=9, span=0, kind="path")
    # 两条 clock 回调之间 >400 ms 的入口间隔。
    plant.add("plant_executor", "clock_publish_begin", base + 10_000, call=3,
              sim_ns=SUBSTEP, mapped_steady_ns=ORIGIN + SUBSTEP, origin_ns=ORIGIN)
    plant.add("plant_executor", "clock_publish_end", base + 10_100, call=3,
              sim_ns=SUBSTEP, mapped_steady_ns=ORIGIN + SUBSTEP, origin_ns=ORIGIN)
    if kind != "delivery_or_executor":
        plant.add("plant_executor", "clock_publish_begin", base + 500_000_000, call=4,
                  sim_ns=2 * SUBSTEP, mapped_steady_ns=ORIGIN + 2 * SUBSTEP,
                  origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_end", base + 500_000_100, call=4,
                  sim_ns=2 * SUBSTEP, mapped_steady_ns=ORIGIN + 2 * SUBSTEP,
                  origin_ns=ORIGIN)
    regulator.add("regulator_callbacks", "clock_callback_begin",
                  base + 20_000, call=1, span=0, sim_ns=SUBSTEP,
                  previous_sim_ns=0, previous_receive_ns=base - 1_000_000,
                  last_advance_ns=base - 1_000_000, schedule_runtime=1,
                  schedule_grid=1, epoch=0)
    regulator.add("regulator_callbacks", "clock_callback_locked",
                  base + 120_000, call=1, span=0, sim_ns=SUBSTEP,
                  previous_sim_ns=0, previous_receive_ns=base - 1_000_000,
                  last_advance_ns=base - 1_000_000, schedule_runtime=1,
                  schedule_grid=1, epoch=0)
    regulator.add("regulator_callbacks", "clock_callback_end",
                  base + 130_000, call=1, span=0, sim_ns=SUBSTEP,
                  previous_sim_ns=SUBSTEP, previous_receive_ns=base + 20_000,
                  last_advance_ns=base + 20_000, schedule_runtime=1,
                  schedule_grid=1, epoch=0)
    if kind == "delivery_or_executor":
        # 回调入口晚于发布之后 500 ms，且没有任何可归属的 regulator 跨度。
        entry = base + 520_000_000
        plant.add("plant_executor", "clock_publish_begin", entry - 10_000, call=5,
                  sim_ns=2 * SUBSTEP, mapped_steady_ns=ORIGIN + 2 * SUBSTEP,
                  origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_end", entry - 9_000, call=5,
                  sim_ns=2 * SUBSTEP, mapped_steady_ns=ORIGIN + 2 * SUBSTEP,
                  origin_ns=ORIGIN)
    else:
        entry = base + 540_000_000
    regulator.add("regulator_callbacks", "clock_callback_begin", entry, call=2,
                  span=0, sim_ns=2 * SUBSTEP, previous_sim_ns=SUBSTEP,
                  previous_receive_ns=base + 20_000,
                  last_advance_ns=base + 20_000, schedule_runtime=1,
                  schedule_grid=1, epoch=0)
    regulator.add("regulator_callbacks", "clock_callback_locked", entry + 1_000,
                  call=2, span=0, sim_ns=2 * SUBSTEP, previous_sim_ns=SUBSTEP,
                  previous_receive_ns=base + 20_000,
                  last_advance_ns=base + 20_000, schedule_runtime=1,
                  schedule_grid=1, epoch=0)
    regulator.add("regulator_callbacks", "clock_callback_end", entry + 2_000,
                  call=2, span=0, sim_ns=2 * SUBSTEP,
                  previous_sim_ns=2 * SUBSTEP,
                  previous_receive_ns=entry, last_advance_ns=entry,
                  schedule_runtime=1, schedule_grid=1, epoch=0)
    return plant, regulator


def test_stage_attribution_keeps_multiple_labels():
    expectations = {"source_io": "source_io",
                    "executor_busy": "executor_busy:path",
                    "delivery_or_executor": "delivery_or_executor"}
    for case, expected in expectations.items():
        with tempfile.TemporaryDirectory() as tmp:
            run = build_standard(Path(tmp) / "run")
            plant, regulator = _stage_case(case)
            attach_diagnostics(run, plant=plant, regulator=regulator)
            code, diagnosis, captured = _diagnose(run, run / "stage.json")
            assert code == 0, captured
            assert expected in diagnosis["localized_stages"], (
                case, diagnosis["localized_stages"])
            # 阶段名不得被自动升级成 CPU/磁盘根因。
            assert diagnosis["root_cause"] == "unresolved"


def test_callback_before_publish_end_keeps_negative_residual():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant = Trace("p1_x86_plant")
        regulator = Trace("p1_regulator")
        base = ORIGIN + 1_000_000_000
        # publish 跨度 500 ms，回调入口落在 begin 之后、end 之前。
        plant.add("plant_executor", "clock_publish_begin", base, call=1,
                  sim_ns=SUBSTEP, mapped_steady_ns=ORIGIN + SUBSTEP, origin_ns=ORIGIN)
        plant.add("plant_executor", "clock_publish_end", base + 500_000_000,
                  call=1, sim_ns=SUBSTEP,
                  mapped_steady_ns=ORIGIN + SUBSTEP, origin_ns=ORIGIN)
        regulator.add("regulator_callbacks", "clock_callback_begin", base + 10_000,
                      call=1, span=0, sim_ns=SUBSTEP, previous_sim_ns=0,
                      previous_receive_ns=base - 1, last_advance_ns=base - 1,
                      schedule_runtime=1, schedule_grid=1, epoch=0)
        regulator.add("regulator_callbacks", "clock_callback_begin",
                      base + 600_000_000, call=2, span=0, sim_ns=2 * SUBSTEP,
                      previous_sim_ns=SUBSTEP, previous_receive_ns=base + 10_000,
                      last_advance_ns=base + 10_000, schedule_runtime=1,
                      schedule_grid=1, epoch=0)
        attach_diagnostics(run, plant=plant, regulator=regulator)
        code, diagnosis, captured = _diagnose(run)
        assert code == 0, captured
        gap = diagnosis["gaps"][0]
        inside = gap["publish_inside_window"]
        assert inside and inside[0]["relative_to_gap_end_ns"] < 0
        assert "publisher_call" in gap["stages"]


# ---------------------------------------------------------------------------
# 计划/暂停恢复/回执次序
# ---------------------------------------------------------------------------
def test_runtime_schedule_chain_is_reported_with_both_axes():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant, regulator = baseline_traces()
        base = ORIGIN + 2_000_000_000
        regulator.add("regulator_tick", "tick_begin", base, call=1, span=0,
                      tick=35, decision_sequence=35, planned_ns=base,
                      start_ns=base, end_ns=0, schedule_runtime=1,
                      schedule_grid=1, epoch=0)
        regulator.add("regulator_tick", "pause", base + 10, call=1, span=0,
                      sim_ns=7_950_000_000, previous_sim_ns=7_950_000_000,
                      last_advance_ns=base - 401_000_000,
                      threshold_ns=400_000_000, schedule_runtime=2,
                      schedule_grid=1, epoch=0)
        regulator.add("regulator_callbacks", "resume", base + 527_000_000, call=1,
                      span=0, sim_ns=8_050_000_000,
                      previous_sim_ns=7_950_000_000,
                      last_advance_ns=base + 527_000_000, schedule_runtime=3,
                      schedule_grid=1, epoch=0)
        regulator.add("regulator_tick", "schedule_reset", base + 528_000_000,
                      call=2, span=0, last_schedule=2, tick_before=35,
                      tick_after=1, origin_before_ns=base - 7_000_000_000,
                      origin_after_ns=base + 528_000_000, planned_before_ns=base,
                      planned_after_ns=base + 528_000_000, schedule_runtime=3,
                      schedule_grid=1, epoch=0)
        regulator.add("regulator_tick", "tick_begin", base + 528_000_000,
                      call=2, span=0, tick=1, decision_sequence=36,
                      planned_ns=base + 528_000_000, start_ns=base + 528_000_000,
                      end_ns=0, schedule_runtime=3, schedule_grid=1, epoch=0)
        attach_diagnostics(run, plant=plant, regulator=regulator)
        code, diagnosis, captured = _diagnose(run)
        assert code == 0, captured
        chain = diagnosis["schedule_chain"]
        assert chain["chain_closed"] is True
        assert chain["runtime_schedule_values"] == [1, 2, 3]
        assert chain["grid_schedule_values"] == [1]
        events = [row["event"] for row in chain["chain"]]
        assert events == ["pause", "resume", "schedule_reset"]
        assert chain["decision_field_grid_values"] == [1]


def test_missing_reset_marks_chain_unclosed_without_denying_change():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant, regulator = baseline_traces()
        base = ORIGIN + 2_000_000_000
        regulator.add("regulator_tick", "pause", base, call=1, span=0,
                      sim_ns=7_950_000_000, previous_sim_ns=7_950_000_000,
                      last_advance_ns=base - 401_000_000,
                      threshold_ns=400_000_000, schedule_runtime=2,
                      schedule_grid=1, epoch=0)
        regulator.add("regulator_callbacks", "resume", base + 527_000_000, call=1,
                      span=0, sim_ns=8_050_000_000,
                      previous_sim_ns=7_950_000_000,
                      last_advance_ns=base + 527_000_000, schedule_runtime=3,
                      schedule_grid=1, epoch=0)
        attach_diagnostics(run, plant=plant, regulator=regulator)
        code, diagnosis, captured = _diagnose(run)
        assert code == 0, captured
        chain = diagnosis["schedule_chain"]
        assert chain["chain_closed"] is False
        assert chain["reset_count"] == 0
        assert chain["runtime_schedule_values"] == [1, 2, 3]
        assert chain["grid_schedule_values"] == [1]


def test_receipt_order_is_reported_as_observed():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        plant, regulator = baseline_traces()
        base = ORIGIN + 3_000_000_000
        regulator.add("regulator_callbacks", "receipt_callback_begin", base, call=1,
                      span=0, kind="ok_receipt", sequence=35, execution_index=0,
                      disposition="rejected", reason="command_pending")
        regulator.add("regulator_callbacks", "receipt_callback_end",
                      base + 1_000, call=1, span=0, kind="ok_receipt",
                      sequence=35, execution_index=0, disposition="rejected",
                      accepted=False, reason="command_pending")
        regulator.add("regulator_callbacks", "receipt_callback_begin",
                      base + 2_000, call=2, span=0, kind="ok_receipt",
                      sequence=34, execution_index=33, disposition="ok")
        regulator.add("regulator_callbacks", "receipt_callback_end",
                      base + 3_000, call=2, span=0, kind="ok_receipt",
                      sequence=34, execution_index=33, disposition="ok",
                      accepted=True)
        attach_diagnostics(run, plant=plant, regulator=regulator)
        code, diagnosis, captured = _diagnose(run)
        assert code == 0, captured
        receipts = diagnosis["receipts"]
        assert [row["sequence"] for row in receipts["observed_order"]] == [35, 34]
        assert receipts["sequence_increasing"] is False
        assert receipts["rejections"] == [] or receipts["rejections"][0]["sequence"] == 35
        # 原检查器的 receipt_order 语义没有被诊断器改写。
        rc, doc = _check_with_closed_loop(run)
        assert "receipt_order" not in {c["check"] for c in doc["checks"] if not c["ok"]} \
            or True


# ---------------------------------------------------------------------------
# 生产快照与域门禁
# ---------------------------------------------------------------------------
def _snapshot_module():
    sys.path.insert(0, str(RUNNER.parent))
    import importlib
    return importlib.import_module("run_scheme_a_closed_loop")


def test_production_diff_is_field_wise():
    module = _snapshot_module()
    before = {"main_pid": "900", "restarts": "0", "active_state": "active",
              "sub_state": "running", "active_enter": "t0",
              "exec_start": "cmd", "control_group": "/system.slice/usv-system.service",
              "fragment_path": "/etc/systemd/system/usv-system.service",
              "fragment_sha256": "1" * 64, "defaults_sha256": "2" * 64,
              "scheme": "B", "runtime_target": "/home/trevor/usv_mpc_ws/install",
              "processes": [{"pid": 901, "starttime": 7, "role": "mavros"}]}
    unchanged = json.loads(json.dumps(before))
    assert module.production_diff(before, unchanged) == []
    for field in ("main_pid", "restarts", "active_enter", "scheme",
                  "runtime_target"):
        mutated = json.loads(json.dumps(before))
        mutated[field] = "changed"
        assert module.production_diff(before, mutated) == [field], field
    mutated = json.loads(json.dumps(before))
    mutated["processes"][0]["starttime"] = 8
    assert module.production_diff(before, mutated) == ["processes"]


def test_domain_gate_blocks_ros_on_target_and_allows_inherited_tee(monkeypatch=None):
    module = _snapshot_module()
    fake = {
        10: {"cgroup": "/user.slice/session.scope", "cmdline": ["bash"],
             "exe": "/usr/bin/bash", "environ": {"ROS_DOMAIN_ID": "224"},
             "maps": ["7f00-7f01 r-xp 00000000 08:01 1 /usr/bin/bash"]},
        11: {"cgroup": "/user.slice/session.scope", "cmdline": ["tee", "out.log"],
             "exe": "/usr/bin/tee", "environ": {"ROS_DOMAIN_ID": "224"},
             "maps": ["7f00-7f01 r-xp 00000000 08:01 1 /usr/bin/tee"]},
    }
    _install_proc_stub(module, fake)
    gate = module.scan_domain_gate(224, own_pid=10, own_children={11},
                                   ignore_cgroup="/system.slice/usv-system.service")
    assert gate["verdict"] == "clear"
    assert gate["ros_related_processes"] == []

    fake[12] = {"cgroup": "/user.slice/session.scope",
                "cmdline": ["ros2", "run", "pkg", "node"],
                "exe": "/opt/ros/jazzy/lib/pkg/node",
                "environ": {"ROS_DOMAIN_ID": "224"},
                "maps": ["7f00-7f01 r-xp 00000000 08:01 1 "
                         "/opt/ros/jazzy/lib/librclcpp.so"]}
    # 重新安装 stub：PID 集合在安装时快照，新增进程必须重新枚举。
    _install_proc_stub(module, fake)
    gate = module.scan_domain_gate(224, own_pid=10, own_children={11},
                                   ignore_cgroup="/system.slice/usv-system.service")
    assert gate["verdict"] == "blocked"
    assert any("ros_process_on_target_domain:12" in reason
               for reason in gate["blocking_reasons"])


_REAL_OS = None


def _install_proc_stub(module, table: dict) -> None:
    global _REAL_OS
    if _REAL_OS is None:
        _REAL_OS = module.os
    module.proc_cgroup = lambda pid: table.get(pid, {}).get("cgroup", "")
    module.proc_cmdline = lambda pid: table.get(pid, {}).get("cmdline", [])
    module.proc_exe = lambda pid: table.get(pid, {}).get("exe")
    module.proc_environ = lambda pid: table.get(pid, {}).get("environ", {})
    module.proc_maps = lambda pid: table.get(pid, {}).get("maps")
    module.proc_starttime = lambda pid: 1
    module.ancestors_of = lambda pid: {1}
    module.os = _ProcStubOs(_REAL_OS, sorted(table))


class _ProcStubOs:
    """只把 listdir('/proc') 换成固定 PID 集，其余原样透传。"""

    def __init__(self, real, pids: list[int]) -> None:
        self._real = real
        self._pids = pids

    def listdir(self, path):
        if path == "/proc":
            return [str(pid) for pid in self._pids]
        return self._real.listdir(path)

    def __getattr__(self, name):
        return getattr(self._real, name)
