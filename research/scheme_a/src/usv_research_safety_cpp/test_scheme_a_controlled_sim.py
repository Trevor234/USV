# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""闭环检查器自身的测试：它必须能拒绝被破坏的证据。

一个只会 PASS 的检查器，和没有检查器没有区别。这里用**完整 v2 形状**的最小
fixture 做正控制，然后每次只改一个语义（并同步 source 摘要），分别断言指定
判据失败。fixture 不是运行证据，只是判据的输入；真实运行由步骤 3 的 runner 产生。
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).with_name("scripts") / "check_scheme_a_closed_loop.py"
PRESERVED = Path("/home/trevor/USV/.sgh-research/experiments/"
                 "scheme_A_execution_remediation_20261115/inputs/failed_runs")

T = 200_000_000
DEADLINE = 150_000_000
ORIGIN = 5_000_000_000
RUN_ID = "fixture-run"
BOOT_ID = "fixture-boot"

PLAN = {
    "activation_plan": [
        {"content": "M0", "first_target_tick": 1, "generation": 1, "last_target_tick": 5},
        {"content": "M1", "first_target_tick": 6, "generation": 2, "last_target_tick": 11},
        {"content": "M0", "first_target_tick": 12, "generation": 3, "last_target_tick": None},
    ],
    "grid": {"clock_epoch_at_table_start": 0,
             "contract_schema": "p1-execution-contract-v3",
             "deadline_ns": DEADLINE, "schedule_generation_at_table_start": 1,
             "tick_period_ns": T},
    "switch_ticks": [6, 12],
}

CONTRACT = {
    "schema": "p1-execution-contract-v2-sim",
    "qualification": "controlled_sim",
    "N": 20,
    "dt": 0.2,
    "T_ns": T,
    "deadline_ns": DEADLINE,
    "hold_ns": T,
    "activation_tolerance": [0.25, 0.25, 0.15, 0.3, 0.2, 0.15],
    "command_min_n": -25,
    "command_max_n": 25,
    "fault_injection_enabled": False,
    "controlled_sim_faults_enabled": False,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


CONTRACT_TEXT = json.dumps(CONTRACT, indent=2) + "\n"
CONTRACT_SHA = hashlib.sha256(CONTRACT_TEXT.encode()).hexdigest()


def axes_of(tick: int) -> dict:
    """五轴版本：受控仿真里 task/config/schedule/epoch 恒定，model 随计划。"""
    return {"task_generation": 1, "model_generation": generation_of(tick),
            "config_generation": 1, "schedule_generation": 1, "clock_epoch": 0}


def identity_of() -> dict:
    return {"run_id": RUN_ID, "boot_id": BOOT_ID, "contract_hash": CONTRACT_SHA}


def generation_of(tick: int) -> int:
    return 1 if tick <= 5 else (2 if tick <= 11 else 3)


def thrust_of(tick: int) -> list:
    return [round(6.0 + 0.25 * tick, 6), round(-4.0 + 0.125 * tick, 6)]


class Builder:
    """按事件列表生成一份完整 v2 证据。"""

    def __init__(self, root: Path, *, required=None, stimuli=None) -> None:
        self.root = root
        self.regulator: list[dict] = []
        self.plant: list[dict] = []
        self.worker: list[dict] = []
        self.executed = 0            # 已发生的执行序号
        self.sim = 0
        self.required = required if required is not None else [
            "commands_paired", "single_execution_per_tick", "nonzero_execution",
            "generation_coverage", "anchor_from_receipt", "state_progress",
            "steady_domain_consistent", "no_test_seams",
        ]
        self.stimuli = stimuli or []
        self.job_ids: list[int] = []
        self.anchor_index = 0
        self.anchor_begin = ORIGIN
        self.hold_end = ORIGIN

    # -- 证据片段 --------------------------------------------------------
    def add_bootstrap(self) -> None:
        self.plant.append({
            "type": "bootstrap_receipt", "schema": "p1-plant-receipt-v3",
            "sequence": 0, "tick": 0,
            "disposition": "bootstrap", "reason": "", "execution_index": 0,
            "thrust_n": [0.0, 0.0],
            "state": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "plant_steady_origin_ns": ORIGIN, "sim_ns": 0,
            "state_sample_sim_ns": 0, "planned_window_end_sim_ns": 0,
            "clock_identity": "plant_sim_clock:CLOCK_MONOTONIC",
            "apply_begin_steady_ns": ORIGIN, "apply_end_steady_ns": ORIGIN,
            "executed_begin_steady_ns": ORIGIN, "executed_end_steady_ns": ORIGIN,
            "hold_end_steady_ns": ORIGIN, "receive_steady_ns": ORIGIN,
            "executed_steady_ns": ORIGIN,
            **identity_of(), **axes_of(1),
        })

    def add_startup(self) -> None:
        self.regulator.append({
            "type": "startup", "schema": "p1-regulator-v2",
            "mode": "controlled_sim", "pid": 1234,
            "clock": "CLOCK_MONOTONIC", "anchor_source": "plant_receipt",
            "typed_command_topics": ["/p1/plant_command"],
            "raw_command_topics": [],
            "physical_publisher_endpoints": 0,
            **identity_of(),
        })

    def add_capability(self) -> None:
        self.worker.append({
            "type": "worker_capability", "schema": "p1-worker-capability-v2",
            "pid": 1235, "worker_instance": "w1",
            "horizon_steps": 20, "prediction_dt": 0.2, "fatal": False,
            "fault_injection_enabled": False, "model_runtime_ready": True,
            "model_plan_sha256": "0" * 64, "applied_generation": 1,
            "startup_ns": ORIGIN - 1000, "completed_jobs": 0,
            "active_job": 0, "pending_count": 0, "reason": "",
            "clock_name": "CLOCK_MONOTONIC", "backend": "acados",
            "matrix_layout": "column_major",
            **identity_of(),
        })

    def add_tick(self, tick: int, sequence: int, *, state=None,
                 apply_begin=None, executed_begin=None) -> None:
        """一条被接纳的决策：命令、准入回执、worker 候选、实际执行。

        `executed_begin` 用于 hold 到期后重新 tiling：声明窗口仍在网格上，
        实际执行被对齐到下一个子步边界。
        """
        generation = generation_of(tick)
        thrust = thrust_of(tick)
        if executed_begin is None:
            executed_begin = self.hold_end
        executed_end = executed_begin + T
        declared_begin = apply_begin if apply_begin is not None else executed_begin
        declared_end = declared_begin + T
        self.executed += 1
        execution_index = self.executed
        self.sim = executed_end - ORIGIN
        job_id = len(self.job_ids) + 1
        self.job_ids.append(job_id)
        axes = axes_of(tick)

        self.regulator.append({
            "type": "plant_command", "schema": "p1-plant-command-v2",
            "sequence": sequence, "tick": tick,
            "thrust_n": thrust,
            "apply_begin_steady_ns": declared_begin,
            "apply_end_steady_ns": declared_end,
            "deadline_steady_ns": declared_begin + DEADLINE,
            "regulator_clock_sim_ns": declared_begin - ORIGIN,
            "worker_instance": "w1", "candidate_job_id": job_id,
            **identity_of(), **axes,
        })
        self.regulator.append({
            "type": "plant_receipt_admission", "sequence": sequence,
            "tick": tick, "disposition": "ok", "reason": "",
            "accepted": True, "execution_index": execution_index,
        })
        self.regulator.append({
            "type": "decision", "tick": tick, "job_id": job_id,
            "candidate_accepted": True,
            "final_n": thrust, "reason": "",
            "plant_execution_index": self.anchor_index,
            "anchor_sequence": [self.anchor_index, self.anchor_index],
            "anchor_publish_ns": [self.anchor_begin, self.anchor_begin],
            **identity_of(), **axes,
        })
        job = {"job_id": job_id, "target_tick": tick, **axes}
        self.worker.append({"type": "job_received", "job": job})
        self.worker.append({
            "type": "candidate", "job": job,
            "solver_invoked": True, "success": True,
            "native_solve_entries_this_job": 1,
            "native_solve_entries_before": len(self.job_ids) - 1,
            "native_solve_entries_after": len(self.job_ids),
            "applied_generation": generation, "backend_ms": 1.5,
            "first_control": thrust,
        })
        state = state or [float(tick), float(tick) * 0.5, 0.01 * tick,
                          1.0 - 0.01 * tick, 0.0, 0.0]
        self.plant.append({
            "type": "plant_receipt", "schema": "p1-plant-receipt-v3",
            "sequence": sequence, "tick": tick,
            "disposition": "ok", "reason": "", "execution_index": execution_index,
            "thrust_n": thrust, "state": state,
            "apply_begin_steady_ns": declared_begin,
            "apply_end_steady_ns": declared_end,
            "executed_begin_steady_ns": executed_begin,
            "executed_end_steady_ns": executed_end,
            "hold_end_steady_ns": executed_end,
            "plant_steady_origin_ns": ORIGIN,
            "receive_steady_ns": declared_begin - 1_000_000,
            "executed_steady_ns": executed_end - 500_000,
            "sim_ns": executed_end - ORIGIN,
            "state_sample_sim_ns": executed_begin - ORIGIN,
            "planned_window_end_sim_ns": executed_end - ORIGIN,
            "clock_identity": "plant_sim_clock:CLOCK_MONOTONIC",
            **identity_of(), **axes,
        })
        self.anchor_index = execution_index
        self.anchor_begin = executed_begin
        self.hold_end = executed_end

    def add_rejected(self, tick: int, sequence: int, disposition: str,
                     reason: str) -> None:
        self.regulator.append({
            "type": "plant_command", "schema": "p1-plant-command-v2",
            "sequence": sequence, "tick": tick,
            "thrust_n": thrust_of(tick),
            "apply_begin_steady_ns": self.hold_end,
            "apply_end_steady_ns": self.hold_end + T,
            "deadline_steady_ns": self.hold_end - 1,
            "regulator_clock_sim_ns": self.sim,
            "worker_instance": "w1", "candidate_job_id": 0,
            **identity_of(), **axes_of(tick),
        })
        self.plant.append({
            "type": "plant_receipt", "schema": "p1-plant-receipt-v3",
            "sequence": sequence, "tick": tick,
            "disposition": disposition, "reason": reason, "execution_index": 0,
            "thrust_n": [0.0, 0.0],
            "state": [float(tick), 0.0, 0.0, 1.0, 0.0, 0.0],
            "apply_begin_steady_ns": 0, "apply_end_steady_ns": 0,
            "executed_begin_steady_ns": 0, "executed_end_steady_ns": 0,
            "hold_end_steady_ns": 0, "plant_steady_origin_ns": ORIGIN,
            "receive_steady_ns": self.hold_end + 1_000_000,
            "executed_steady_ns": self.hold_end + 1_100_000,
            "sim_ns": self.sim,
            "state_sample_sim_ns": self.sim,
            "planned_window_end_sim_ns": 0,
            "clock_identity": "plant_sim_clock:CLOCK_MONOTONIC",
            **identity_of(), **axes_of(tick),
        })

    def add_duplicate(self, tick: int, sequence: int) -> None:
        self.plant.append({
            "type": "plant_receipt", "schema": "p1-plant-receipt-v3",
            "sequence": sequence, "tick": tick,
            "disposition": "duplicate", "reason": "same_sequence",
            "execution_index": 0, "thrust_n": [0.0, 0.0],
            "state": [float(tick), 0.0, 0.0, 1.0, 0.0, 0.0],
            "apply_begin_steady_ns": 0, "apply_end_steady_ns": 0,
            "executed_begin_steady_ns": 0, "executed_end_steady_ns": 0,
            "hold_end_steady_ns": 0, "plant_steady_origin_ns": ORIGIN,
            "receive_steady_ns": self.hold_end + 1_000_000,
            "executed_steady_ns": self.hold_end + 1_100_000,
            "sim_ns": self.sim,
            "state_sample_sim_ns": self.sim,
            "planned_window_end_sim_ns": 0,
            "clock_identity": "plant_sim_clock:CLOCK_MONOTONIC",
            **identity_of(), **axes_of(tick),
        })

    def add_hold_close(self, reason: str, close_steady: int,
                       executed_end: int) -> None:
        self.plant.append({
            "type": "plant_hold_close", "schema": "p1-plant-hold-close-v2",
            "execution_index": self.executed,
            "reason": reason, "close_steady_ns": close_steady,
            "close_sim_ns": close_steady - ORIGIN,
            "state_sample_sim_ns": close_steady - ORIGIN,
            "plant_steady_origin_ns": ORIGIN,
            "clock_identity": "plant_sim_clock:CLOCK_MONOTONIC",
            "clock_epoch": 0,
            "executed_end_steady_ns": executed_end,
            "state": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            **identity_of(),
        })

    def add_withheld_decision(self, tick: int) -> None:
        self.regulator.append({
            "type": "plant_command_withheld", "tick": tick,
            "reason": "receipt_pending",
        })
        self.regulator.append({
            "type": "decision", "tick": tick, "job_id": 0,
            "candidate_accepted": False, "final_n": [0.0, 0.0],
            "reason": "plant_command_withheld",
            "plant_execution_index": self.anchor_index,
            "anchor_sequence": [self.anchor_index, self.anchor_index],
            "anchor_publish_ns": [self.anchor_begin, self.anchor_begin],
            **identity_of(), **axes_of(tick),
        })

    def add_clock_and_sensors(self) -> None:
        for step in range(0, max(1, self.sim // (T // 4)) + 1):
            steady = ORIGIN + step * (T // 4)
            self.plant.append({"type": "plant_clock", "sim_ns": step * (T // 4),
                               "steady_ns": steady,
                               "steady_origin_ns": ORIGIN})
            self.plant.append({"type": "plant_sensors", "sim_ns": step * (T // 4),
                               "steady_ns": steady,
                               "state": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0]})

    # -- 收尾 ------------------------------------------------------------
    def finish(self, *, free_evolution_substeps=None) -> None:
        self.regulator.append({
            "type": "regulator_shutdown",
            "normal_contract_complete": True, "plant_hold_end_known": True,
            "finished_ns": ORIGIN + self.sim + 1000,
        })
        self.regulator.append({
            "type": "source_summary", "generated": len(self.regulator),
            "emitted": len(self.regulator), "dropped": 0,
            "normal_source_complete": True,
            "finished_ns": ORIGIN + self.sim + 2000,
        })
        self.worker.append({
            "type": "worker_summary",
            "generated_candidates": len(self.job_ids),
            "published_candidates": len(self.job_ids),
            "completed_jobs": len(self.job_ids), "refused_jobs": 0,
            "cancelled_jobs": 0, "fatal": False,
            "terminal_numerical_failure": False,
            "normal_source_complete": True,
            "finished_ns": ORIGIN + self.sim + 3000,
        })
        receipts = [r for r in self.plant if r.get("type") == "plant_receipt"]
        self.plant.append({
            "type": "plant_summary",
            "receipt_counts": {
                "ok": sum(1 for r in receipts if r["disposition"] == "ok"),
                "rejected": sum(1 for r in receipts if r["disposition"] == "rejected"),
                "late": sum(1 for r in receipts if r["disposition"] == "late"),
                "duplicate": sum(1 for r in receipts if r["disposition"] == "duplicate"),
            },
            "free_evolution_substeps": (free_evolution_substeps
                                        if free_evolution_substeps is not None
                                        else self.sim // (T // 4)),
            "stopped_at_substep": self.sim // (T // 4),
            "flushed": True,
            "final_state": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            "sim_ns_end": self.sim,
        })

    def write(self) -> Path:
        root = self.root
        (root / "nodes").mkdir(parents=True, exist_ok=True)
        (root / "contract.json").write_text(CONTRACT_TEXT)
        (root / "plan.json").write_text(json.dumps(PLAN, indent=2) + "\n")
        for name, rows in (("regulator", self.regulator), ("worker", self.worker),
                           ("plant", self.plant)):
            with open(root / f"{name}.source.jsonl", "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, sort_keys=True) + "\n")
        nodes = {}
        for name, pid in (("regulator", 1234), ("worker", 1235), ("plant", 1236)):
            exe = root / "nodes" / f"{name}.elf"
            exe.write_bytes(f"fixture {name}\n".encode())
            nodes[name] = {
                "pid": pid, "pgid": pid, "exe": str(exe),
                "exe_sha256": sha256(exe), "stop_requested_ns": ORIGIN + 1,
                "rc": 0, "wait_ms": 42, "killed": False, "summary_seen": True,
            }
        manifest = root / "source_hashes.json"
        manifest.write_text(json.dumps(
            {"schema": "scheme-a-execution-closure-baseline-v1", "records": []},
            indent=2) + "\n")
        sources = {}
        for name in ("regulator", "worker", "plant"):
            path = root / f"{name}.source.jsonl"
            sources[name] = {"sha256": sha256(path), "bytes": path.stat().st_size,
                             "lines": len(path.read_text().splitlines())}
        run = {
            "schema": "scheme_A.controlled_sim.run.v2",
            "scenario": "fixture",
            "run_id": "fixture-run",
            "required": self.required,
            "stimuli": self.stimuli,
            "stop_plan": {"stop_after_decisions": 0, "stop_after_s": 0.0},
            "nodes": nodes,
            "sources": sources,
            "scripts": {
                "runner": "1" * 64,
                "checker": sha256(CHECKER),
                "plan": sha256(root / "plan.json"),
                "contract": sha256(root / "contract.json"),
            },
            "binding": {
                "source_hashes_sha256": sha256(manifest),
                "contract_sha256": sha256(root / "contract.json"),
                "plan_sha256": sha256(root / "plan.json"),
            },
            "failure": None,
        }
        (root / "run.json").write_text(
            json.dumps(run, indent=2, sort_keys=True) + "\n")
        return root


def build_standard(root: Path) -> Path:
    b = Builder(root)
    b.add_startup()
    b.add_capability()
    b.add_bootstrap()
    for tick in range(1, 15):
        b.add_tick(tick, sequence=tick)
    b.add_clock_and_sensors()
    b.finish()
    return b.write()


def build_stimulus(root: Path) -> Path:
    b = Builder(root, required=[
        "commands_paired", "single_execution_per_tick", "nonzero_execution",
        "anchor_from_receipt", "state_progress", "steady_domain_consistent",
        "stimulus:late", "stimulus:duplicate", "stimulus:hold_expiry",
        "no_test_seams",
    ], stimuli=[
        {"kind": "late", "sequence": 5, "tick": 5},
        {"kind": "duplicate", "sequence": 7, "tick": 6},
        # fired_ns 必须存在：检查器只认"刺激之后、且不是关机最后一条"的
        # expired 闭合，否则关机时那条天然 expired 会被误当成反证。
        {"kind": "hold_expiry", "tick": 7, "fired_ns": ORIGIN + 5 * T + 1},
    ])
    b.add_startup()
    b.add_capability()
    b.add_bootstrap()
    for tick, sequence in ((1, 1), (2, 2), (3, 3), (4, 4)):
        b.add_tick(tick, sequence=sequence)
    b.add_rejected(5, 5, "late", "deadline_passed_before_execution")
    b.add_tick(5, sequence=6)
    b.add_tick(6, sequence=7)
    b.add_duplicate(6, 7)
    b.add_withheld_decision(7)
    hold_end = b.hold_end
    b.add_hold_close("expired", hold_end, hold_end)
    # 缺口后重新 tiling：声明起点落在上一 hold 末端，实际执行对齐到下一网格。
    b.add_tick(8, sequence=8, apply_begin=hold_end, executed_begin=hold_end + T)
    # 缺口之后还有一拍：保证上面那条 expired 不是源文件里的最后一条闭合。
    b.add_hold_close("superseded", b.hold_end, b.hold_end)
    b.add_tick(10, sequence=10)
    b.add_clock_and_sensors()
    b.finish()
    return b.write()


def _check(run: Path):
    r = subprocess.run(
        [sys.executable, "-B", str(CHECKER), "--run", str(run),
         "--plan", str(run / "plan.json"), "--contract", str(run / "contract.json"),
         "--source-hashes", str(run / "source_hashes.json")],
        capture_output=True, text=True)
    doc = json.loads((run / "check.json").read_text())
    return r.returncode, doc


def _failed(doc):
    return {c["check"] for c in doc["checks"] if not c["ok"]}


def _failure_names(doc):
    return {f["name"] for f in doc.get("failures") or []}


def _rewrite_source(root: Path, name: str, rows: list[dict]) -> None:
    path = root / f"{name}.source.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    run_path = root / "run.json"
    run = json.loads(run_path.read_text())
    run["sources"][name] = {
        "sha256": sha256(path), "bytes": path.stat().st_size,
        "lines": len(path.read_text().splitlines())}
    run_path.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n")


def _mutate(root: Path, name: str, fn) -> None:
    path = root / f"{name}.source.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    fn(rows)
    _rewrite_source(root, name, rows)


# ---------------------------------------------------------------------------
# 正控制
# ---------------------------------------------------------------------------
def test_complete_v2_run_passes():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        rc, doc = _check(run)
        assert rc == 0, (doc["failures"], )
        assert doc["verdict"] == "PASS"
        assert len(doc["checks"]) == 11


def test_stimulus_run_passes_with_refutation():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_stimulus(Path(tmp) / "run")
        rc, doc = _check(run)
        assert rc == 0, doc["failures"]
        assert doc["verdict"] == "PASS"


def test_plant_only_free_evolution_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "run"
        b = Builder(root, required=["no_commands", "free_evolution", "no_test_seams"])
        b.add_startup()
        b.add_capability()
        b.add_bootstrap()
        b.sim = 3_000_000_000
        b.add_clock_and_sensors()
        b.finish(free_evolution_substeps=60)
        run = b.write()
        rc, doc = _check(run)
        assert rc == 0, doc["failures"]


# ---------------------------------------------------------------------------
# 反例：每次只改一个语义
# ---------------------------------------------------------------------------
def test_missing_worker_source_fails_inputs():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        (run / "worker.source.jsonl").unlink()
        rc, doc = _check(run)
        assert rc == 2 and doc["verdict"] == "FAIL"
        assert "inputs_complete" in _failed(doc)


def test_all_generations_one_fails_plan():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "regulator", lambda rows: [
            r.update(model_generation=1) for r in rows
            if r.get("type") in ("decision", "plant_command")])
        _mutate(run, "worker", lambda rows: [
            r.update(applied_generation=1) for r in rows
            if r.get("type") == "candidate"])
        _mutate(run, "worker", lambda rows: [
            r["job"].update(model_generation=1) for r in rows
            if r.get("type") == "candidate"])
        rc, doc = _check(run)
        assert rc == 2
        assert "plan_complete" in _failed(doc)


def test_thrust_override_fails_dispositions():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")

        def mutate(rows):
            for row in rows:
                if row.get("type") == "plant_receipt" and row.get("sequence") == 4:
                    row["thrust_n"] = [25.0, -25.0]
        _mutate(run, "plant", mutate)
        rc, doc = _check(run)
        assert rc == 2
        assert "dispositions" in _failed(doc)


def test_duplicate_ok_fails_receipt_order():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")

        def mutate(rows):
            clone = None
            for row in rows:
                if row.get("type") == "plant_receipt" and row.get("sequence") == 3:
                    clone = dict(row)
            clone["execution_index"] = 13
            rows.append(clone)
        _mutate(run, "plant", mutate)
        rc, doc = _check(run)
        assert rc == 2
        assert "receipt_order" in _failed(doc)


def test_worker_rc_and_failure_fail_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        path = run / "run.json"
        doc = json.loads(path.read_text())
        doc["nodes"]["worker"]["rc"] = 2
        doc["failure"] = "node_rc:worker:2"
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        rc, out = _check(run)
        assert rc == 2
        assert "node_lifecycle" in _failed(out)


def test_no_accepted_decision_fails_plan_and_guard():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "regulator", lambda rows: [
            r.update(candidate_accepted=False) for r in rows
            if r.get("type") == "decision"])
        rc, doc = _check(run)
        assert rc == 2
        failed = _failed(doc)
        assert "plan_complete" in failed
        assert "guard_on_source" in failed


def test_malformed_jsonl_fails_inputs():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        path = run / "regulator.source.jsonl"
        text = path.read_text()
        text += '{"type":"decision","tick":\n'
        path.write_text(text)
        doc_path = run / "run.json"
        doc = json.loads(doc_path.read_text())
        doc["sources"]["regulator"] = {
            "sha256": sha256(path), "bytes": path.stat().st_size,
            "lines": len(text.splitlines())}
        doc_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        rc, out = _check(run)
        assert rc == 2
        assert "inputs_complete" in _failed(out)


def test_dropped_middle_command_fails_typed_only():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "regulator", lambda rows: rows.__delitem__(
            next(i for i, r in enumerate(rows)
                 if r.get("type") == "plant_command" and r.get("sequence") == 6)))
        rc, doc = _check(run)
        assert rc == 2
        assert "typed_only" in _failed(doc)


def test_missing_execution_end_fails_time_domain():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")

        def mutate(rows):
            for row in rows:
                if row.get("type") == "plant_receipt" and row.get("sequence") == 5:
                    row["executed_end_steady_ns"] = 0
        _mutate(run, "plant", mutate)
        rc, doc = _check(run)
        assert rc == 2
        assert "time_domain" in _failed(doc)


def test_forged_zero_native_fails_plan():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "worker", lambda rows: [
            r.update(native_solve_entries_this_job=0) for r in rows
            if r.get("type") == "candidate"])
        rc, doc = _check(run)
        assert rc == 2
        assert "plan_complete" in _failed(doc)


def test_anchor_seeded_fails_guard():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "regulator", lambda rows: rows.insert(
            2, {"type": "anchor_seeded", "source": "plant_odom"}))
        rc, doc = _check(run)
        assert rc == 2
        assert "guard_on_source" in _failed(doc)


def _single_field_failure(source: str, field: str, value, *,
                          check: str) -> None:
    """只改一个字段（并同步 source 摘要），必须由指定判据拒绝。"""
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, source, lambda rows: [
            row.__setitem__(field, value)
            for row in rows
            if row.get("type") == "plant_receipt"
            and row.get("disposition") == "ok"
            and row.get("sequence") == 3])
        rc, doc = _check(run)
        assert rc == 2, (field, doc["failures"])
        assert check in _failed(doc), (field, doc["failures"])
        assert any(field in reason for f in doc["failures"]
                   if f["name"] == check for reason in [f["reason"]]), doc["failures"]


def test_boot_id_mismatch_fails_typed_only():
    _single_field_failure("plant", "boot_id", "other-boot", check="typed_only")


def test_contract_hash_mismatch_fails_typed_only():
    _single_field_failure("plant", "contract_hash", "f" * 64, check="typed_only")


def test_schedule_generation_mismatch_fails_typed_only():
    _single_field_failure("plant", "schedule_generation", 7, check="typed_only")


def test_clock_epoch_mismatch_fails_typed_only():
    _single_field_failure("plant", "clock_epoch", 3, check="typed_only")


def test_tick_mismatch_fails_typed_only():
    _single_field_failure("plant", "tick", 9, check="typed_only")


def test_candidate_job_unknown_fails_typed_only():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "regulator", lambda rows: [
            row.__setitem__("candidate_job_id", 99)
            for row in rows
            if row.get("type") == "plant_command" and row.get("sequence") == 3])
        rc, doc = _check(run)
        assert rc == 2
        assert "typed_only" in _failed(doc)
        assert any("command_candidate_job_unknown" in f["reason"]
                   for f in doc["failures"])


def test_candidate_axis_mismatch_fails_plan():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "worker", lambda rows: [
            row["job"].__setitem__("config_generation", 5)
            for row in rows
            if row.get("type") == "candidate"
            and row["job"].get("job_id") == 3])
        rc, doc = _check(run)
        assert rc == 2
        assert "plan_complete" in _failed(doc)
        assert any("candidate_decision_axis_differs" in f["reason"]
                   for f in doc["failures"])


def test_v1_legacy_runs_fail_on_schema():
    for name in ("sim33", "sim4_no_odom"):
        source = PRESERVED / name
        if not source.is_dir():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            shutil.copytree(source, run)
            # 只读取证目录本身是只读的；复制出来的副本必须可写，检查器要在其中
            # 落 check.json（真实运行目录本来就是可写的）。
            for path in [run, *run.rglob("*")]:
                path.chmod(path.stat().st_mode | 0o200)
            rc, doc = _check(run)
            assert rc == 2, name
            assert "evidence_schema_insufficient" in _failure_names(doc), name
            failed = _failed(doc)
            assert "node_lifecycle" in failed, name
            assert "guard_on_source" in failed, name
            assert "plan_complete" in failed, name
            assert "time_domain" in failed, name


def test_legacy_v2_receipt_fails_on_schema():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "plant", lambda rows: [
            r.__setitem__("schema", "p1-plant-receipt-v2")
            for r in rows if r.get("type") == "plant_receipt" and r.get("sequence") == 2])
        rc, doc = _check(run)
        assert rc == 2
        assert "evidence_schema_insufficient" in _failure_names(doc)


def test_state_sample_sim_mismatch_fails_time_domain():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "plant", lambda rows: [
            r.__setitem__("state_sample_sim_ns", int(r["state_sample_sim_ns"]) + 1000)
            for r in rows if r.get("type") == "plant_receipt" and r.get("sequence") == 2])
        rc, doc = _check(run)
        assert rc == 2
        assert "time_domain" in _failed(doc)


def test_clock_identity_mismatch_fails_time_domain():
    with tempfile.TemporaryDirectory() as tmp:
        run = build_standard(Path(tmp) / "run")
        _mutate(run, "plant", lambda rows: [
            r.__setitem__("clock_identity", "other_clock")
            for r in rows if r.get("type") == "plant_receipt" and r.get("sequence") == 2])
        rc, doc = _check(run)
        assert rc == 2
        assert "time_domain" in _failed(doc)
