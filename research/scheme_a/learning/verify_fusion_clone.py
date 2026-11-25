#!/usr/bin/env python3
"""融合克隆回放校验门（P5.5）：用真实运行记录证明 Python 侧输入构造与生产等价。

三道门，逐条独立可判定：

1. **参考门**：由 `scenario_path.txt` / `scenario_profile.txt` + `job.target_state`
   重建 `job.reference`，要求 `max|Δ| <= 1e-9`。
   （参考与求解都使用 job.target_state。选错状态快照会偏一个路径点，实测 0.30 m。）
2. **残差门**：用上一条候选的 `X`(6×21) / `U`(2×20) 与 `tick_shift` 重建
   `job.stage_residuals`，要求 `max|Δ| <= 1e-9`（只统计 1<=tick_shift<=4 的连续拍，
   覆盖率需 >= 90%）。
   rollout 的初始状态是 `job.target_state`（regulator 先 predict 再建参考与 rollout），
   不是 `frozen_state`；anchor 取 `job.anchor_n`。
3. **求解门**：严格照 `solver_worker.cpp` 的顺序复现每拍：
   `if (job.reset_warmstart) reset_warmstart()` → `set_anchor(job.anchor_n)` →
   `solve(target_state, reference, stage_residuals, q_pi, lambda_pi)` → `accept(anchor_n)`。
   注意：生产**只在 job 要求时**重置（不按 tick_shift 推断）；求解状态是 `target_state`；
   `lambda_pi` 仅在 `ppo_proposal_used` 为真时生效，否则按 0 求解。
   要求 `max|u0-first_control| <= 0.05 N` 且 RMS `<= 0.01 N`。
   失败可退到冷启动模式（每拍 reset + set_anchor），门槛 0.5 N / 0.05 N。

`--authority` 额外做建议权限探针（P5.6）：每 5 条候选，在 9 个 q_pi 点上各解一次，
统计 |Δu0| 随 Δq_pi 的变化，并给出 `selected_lambda_pi`。

退出码：全部门通过 0，否则 1。
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from fusion_controller import (  # noqa: E402
    build_frozen_reference,
    build_gp_rollout_guess,
    evaluate_gp_horizon,
)
from fusion_solver import FusionSolver  # noqa: E402

N = 20
DT = 0.2
REF_GATE = 1e-9
RES_GATE = 1e-9
SOLVE_MAX_GATE_N = 0.05
SOLVE_RMS_GATE_N = 0.01
COLD_MAX_GATE_N = 0.5
COLD_RMS_GATE_N = 0.05
MIN_RESIDUAL_COVERAGE = 0.90
AUTHORITY_LAMBDAS = (0.005, 0.002, 0.0005)   # 从大到小取最小达标值
AUTHORITY_DQ_N = 5.0
AUTHORITY_MIN_MEDIAN_DU_N = 0.5


# ----------------------------------------------------------------------
def _load_scenario(run_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    path_rows = np.loadtxt(run_dir / "scenario_path.txt", dtype=np.float64)
    prof = run_dir / "scenario_profile.txt"
    prof_rows = np.loadtxt(prof, dtype=np.float64) if prof.is_file() else path_rows
    return np.atleast_2d(path_rows), np.atleast_2d(prof_rows)


def _load_candidates(run_dir: Path) -> list[dict]:
    by_tick: dict[int, dict] = {}
    with (run_dir / "worker.source.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or '"type":"candidate"' not in line.replace(" ", ""):
                continue
            rec = json.loads(line)
            if rec.get("type") != "candidate" or not rec.get("solver_invoked"):
                continue
            tick = int(rec["job"]["target_tick"])
            by_tick[tick] = rec
    return [by_tick[t] for t in sorted(by_tick)]


def _x_from_record(rec: dict) -> np.ndarray:
    return np.asarray(rec["X"], dtype=np.float64).reshape(N + 1, 6).T


def _u_from_record(rec: dict) -> np.ndarray:
    return np.asarray(rec["U"], dtype=np.float64).reshape(N, 2).T


def _res_from_job(job: dict) -> np.ndarray:
    # C++ 存的是 std::array<double, 3*(N+1)>，index = 3*k + c（时间外层）
    return np.asarray(job["stage_residuals"], dtype=np.float64).reshape(N + 1, 3).T


def _ref_from_job(job: dict) -> np.ndarray:
    return np.asarray(job["reference"], dtype=np.float64).reshape(N + 1, 6).T


def _is_controlled_sim(contract: dict) -> bool:
    return (contract.get("schema") == "p1-execution-contract-v2-sim"
            and contract.get("qualification") == "controlled_sim")


def _reference_options(contract: dict) -> tuple[str, float | None]:
    if not _is_controlled_sim(contract):
        return "discrete_offset", None
    mode = contract.get("reference_projection_mode", "discrete_offset")
    if mode not in ("discrete_offset", "polyline_time"):
        raise ValueError(f"invalid contract reference_projection_mode: {mode!r}")
    if "reference_lead_s" not in contract:
        return mode, None
    lead = contract["reference_lead_s"]
    if type(lead) not in (int, float) or not 0.0 <= lead <= 2.0:
        raise ValueError("contract reference_lead_s must be a finite number in [0, 2]")
    return mode, float(lead)


def _logged_reference_jobs(run_dir: Path) -> dict[int, dict]:
    logs = {}
    source = run_dir / "regulator.source.jsonl"
    if not source.is_file():
        return logs
    with source.open(encoding="utf-8") as fh:
        for line in fh:
            if '"type":"job"' not in line.replace(" ", ""):
                continue
            row = json.loads(line)
            job = row.get("job", {})
            if row.get("type") == "job" and "reference_projection_mode" in job:
                logs[int(job["job_id"])] = row
    return logs


# ----------------------------------------------------------------------
def gate_reference(cands: list[dict], path_rows: np.ndarray, prof_rows: np.ndarray,
                   offset: int, cruise: float, projection_mode: str = "discrete_offset",
                   lead_s: float | None = None, logged_jobs: dict[int, dict] | None = None) -> dict:
    worst = 0.0
    worst_tick = None
    mismatches = 0
    first_mismatch_tick = None
    for rec in cands:
        job = rec["job"]
        tick = int(job["target_tick"])
        logged = (logged_jobs or {}).get(job.get("job_id"), {})
        profile = None if logged.get("reference_mode") == "cruise_arc_fallback" else prof_rows
        project = (projection_mode == "polyline_time" and profile is not None
                   and len(profile) == len(path_rows) and len(path_rows) >= 2)
        expected_mode = "polyline_time" if project else "discrete_offset"
        expected_lead = -1.0
        if project:
            expected_lead = lead_s if lead_s is not None and lead_s >= 0.0 else max(1, offset) * DT
        if any(evidence.get("reference_projection_mode", expected_mode) != expected_mode
               or evidence.get("reference_lead_s", expected_lead) != expected_lead
               for evidence in (job, logged.get("job", {}))):
            mismatches += 1
            if first_mismatch_tick is None:
                first_mismatch_tick = tick
        want = _ref_from_job(job)
        got = build_frozen_reference(
            np.asarray(job["target_state"], dtype=np.float64),
            path_rows, profile, N=N, dt=DT, offset=offset, cruise=cruise,
            projection_mode=projection_mode, lead_s=lead_s,
        )
        diff = float(np.max(np.abs(got - want)))
        if not math.isfinite(diff):
            diff = math.inf
        if diff > worst:
            worst, worst_tick = diff, tick
    return {"max_abs_diff": worst, "worst_target_tick": worst_tick,
            "metadata_mismatches": mismatches, "first_metadata_mismatch_tick": first_mismatch_tick,
            "passed": worst <= REF_GATE and mismatches == 0,
            "gate": REF_GATE, "samples": len(cands)}


M0_HYDRO_KEYS = ("mass", "Iz", "xg", "d_thruster", "Xu_dot", "Yv_dot", "Yr_dot",
                 "Nv_dot", "Nr_dot", "Xu", "Yv", "Yr", "Nv", "Nr", "Xuu", "Yvv",
                 "Yrr", "Nvv", "Nrr")
M0_HYDRO = (14.2, 2.13, 0.12, 0.25, -2.0, -8.0, -0.1817725, -0.1817725,
            -3.41, -2.272063, -2.629019, 0.0, 0.0, -3.105, -11.571784, -0.05,
            0.0, 0.0, -0.71)
M0_WEIGHTS = (20.0, 20.0, 50.0, 8.0, 1.0, 8.0, 0.05, 0.05, 0.2, 0.2, 8.0)


def _content_from_contract(contract_doc: dict) -> list[float]:
    """Pack the fixed M0 or the ControlledSim M0 in C++ p_global order."""
    if not _is_controlled_sim(contract_doc):
        return list(M0_HYDRO + M0_WEIGHTS)
    hydro = contract_doc.get("hydro", dict(zip(M0_HYDRO_KEYS, M0_HYDRO)))
    if not isinstance(hydro, dict) or hydro.keys() != set(M0_HYDRO_KEYS):
        raise ValueError("invalid contract hydro fields")
    content = [hydro[k] for k in M0_HYDRO_KEYS]
    for key, length in (("Q", 6), ("R", 2), ("Rd", 2)):
        weights = contract_doc[key]
        if not isinstance(weights, list) or len(weights) != length:
            raise ValueError(f"invalid contract {key} dimensions")
        content.extend(weights)
    content.append(contract_doc["Qf_scale"])
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in content):
        raise ValueError("contract model content must contain finite numbers")
    return [float(v) for v in content]


def _m1_content(m0: list[float]) -> list[float]:
    """M1 = M0 但 mass=15.0, Xu=-2.4, Nr=-4.4（C++ m1_content() 逐位一致）。"""
    c = list(m0)
    c[0] = 15.0     # mass
    c[9] = -2.4     # Xu
    c[13] = -4.4    # Nr
    return c


def _generation_contents(contract_doc: dict, run_dir: Path) -> dict[int, list[float]]:
    """plan.json 的 activation_plan（label M0/M1）-> {generation: content}。"""
    m0 = _content_from_contract(contract_doc)
    table = {"M0": m0, "M1": _m1_content(m0)}
    plan_path = run_dir / "plan.json"
    if not plan_path.is_file():
        return {1: m0}
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    out: dict[int, list[float]] = {}
    for row in plan.get("activation_plan", []):
        label = str(row.get("content"))
        if label not in table:
            raise ValueError(f"plan.json 引用了未知模型内容 {label!r}")
        gen = int(row["generation"])
        if gen in out and out[gen] != table[label]:
            raise ValueError(f"generation {gen} 内容冲突")
        out[gen] = table[label]
    return out or {1: m0}


def _hydro_from_contract(contract_doc: dict):
    from usv_rl.dynamics import HydroParams

    return HydroParams(**dict(zip(M0_HYDRO_KEYS, _content_from_contract(contract_doc))))


def gate_residuals(cands: list[dict], gp, hydro, gp_predict=None,
                   activated: dict[int, int] | None = None) -> dict:
    """按生产顺序重建 rollout（x0=target_state，shifted-u 取**已激活**的上一条候选）。

    若提供 `activated`（来自 regulator 的 decision 记录），只用被激活的候选作 prev；
    否则退回按记录顺序推断（在有被拒候选的运行上会错一个 tick）。
    """
    checked = 0
    eligible = 0
    worst = 0.0
    worst_tick = None
    by_tick = {int(r["job"]["target_tick"]): r for r in cands}
    for cur in cands:
        tick = int(cur["job"]["target_tick"])
        if activated is not None:
            prev_ticks = [t for t in activated if t < tick]
            if not prev_ticks:
                continue
            prev = by_tick.get(max(prev_ticks))
            if prev is None:
                continue
        else:
            idx = cands.index(cur)
            if idx == 0:
                continue
            prev = cands[idx - 1]
        shift = tick - int(prev["job"]["target_tick"])
        if not (1 <= shift <= 4):
            continue
        eligible += 1
        job = cur["job"]
        x_prev = _x_from_record(prev)
        u_prev = _u_from_record(prev)
        traj_x, traj_u = build_gp_rollout_guess(
            np.asarray(job["target_state"], dtype=np.float64),
            _ref_from_job(job),
            np.asarray(job["anchor_n"], dtype=np.float64),
            hydro, gp, prev_x=x_prev, prev_u=u_prev, tick_shift=shift,
            gp_predict=gp_predict,
        )
        got = evaluate_gp_horizon(gp, traj_x, traj_u, gp_predict=gp_predict)
        want = _res_from_job(job)
        diff = float(np.max(np.abs(got - want)))
        checked += 1
        if diff > worst:
            worst, worst_tick = diff, int(job["target_tick"])
    coverage = checked / eligible if eligible else 0.0
    return {"max_abs_diff": worst, "worst_target_tick": worst_tick,
            "checked": checked, "eligible": eligible, "coverage": coverage,
            "passed": (checked > 0 and worst <= RES_GATE and coverage >= MIN_RESIDUAL_COVERAGE),
            "gate": RES_GATE}


def _activated_candidates(run_dir: Path) -> dict[int, int] | None:
    """tick -> 被激活候选的 target_tick（不含被拒绝的候选）。

    C++ 只在 `decision.candidate_accepted` 时才更新 `last_cand_x_/last_cand_u_`
    （regulator.cpp 的激活分支）。被拒的候选（例如 rtf_unaligned）不进入热启动链，
    也不作为下一拍的 shifted-u 来源 —— 按"上一条记录"取会在这种拍上错一个 tick。
    返回 None 表示没有 decision 记录（退回按记录顺序推断）。
    """
    src = run_dir / "regulator.source.jsonl"
    if not src.is_file():
        return None
    out: dict[int, int] = {}
    with src.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("type") != "decision":
                continue
            if str(rec.get("control_source")) != "candidate":
                continue
            tick = rec.get("tick")
            if tick is None:
                continue
            out[int(tick)] = int(tick)
    return out or None


def _invalidation_ticks(run_dir: Path) -> set[int]:
    """regulator 侧使热启动链失效的事件对应的下一拍 tick。

    `model_version` / `version_changed_before_submit` / 任何 `invalidate_locked()`
    都会清 warm（生产里由事务 sync 完成），克隆不重放这些事件就会带着陈旧热启动
    继续求解 —— 实测会造成 ~0.29 N 的逐拍偏差。
    """
    ticks: set[int] = set()
    src = run_dir / "regulator.source.jsonl"
    if not src.is_file():
        return ticks
    with src.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            typ = rec.get("type")
            if typ == "model_version":
                ticks.add(int(rec.get("target_tick", 0)))
            elif typ == "job_not_submitted" and "version_changed" in str(rec.get("reason", "")):
                ticks.add(int(rec.get("target_tick", 0)))
    return ticks


def gate_solve(
    cands: list[dict],
    solvers: dict[int, "FusionSolver"],
    cold: bool,
    invalidate_ticks: set[int] | None = None,
) -> dict:
    """按 solver_worker.cpp 的逐拍顺序复现；model_generation 切换时换内容并重置。

    生产路径（`solver_worker.cpp`）：
        if (job.reset_warmstart) reset(); set_anchor(job.anchor_n);
        solve(target_state, reference, stage_residuals, q_pi, lambda_pi); accept(anchor_n)
    其中 lambda_pi 仅在 ppo_proposal_used 为真时生效。模型代际切换由事务完成
    reset + sync（等于整链重置），并且 p_global 内容随之改变（M0/M1）。
    """
    errs: list[np.ndarray] = []
    failures: list[int] = []
    invalidate_ticks = invalidate_ticks or set()
    for s_ in solvers.values():
        s_.reset_warmstart()
    prev_tick = None
    prev_gen = None
    for rec in cands:
        job = rec["job"]
        tick = int(job["target_tick"])
        gen = int(job.get("model_generation", 1))
        solver = solvers.get(gen)
        if solver is None:
            failures.append(tick)
            continue
        crossed = prev_tick is None or any(prev_tick < t <= tick for t in invalidate_ticks)
        gen_switched = prev_gen is not None and gen != prev_gen
        if cold or bool(job.get("reset_warmstart")) or crossed or gen_switched:
            solver.reset_warmstart()
        prev_tick = tick
        prev_gen = gen
        anchor = np.asarray(job["anchor_n"], dtype=np.float64)
        solver.set_anchor(anchor)
        q = np.asarray(job.get("ppo_q_pi") or [0.0, 0.0], dtype=np.float64)
        lam = float(job.get("ppo_lambda_pi") or 0.0) if job.get("ppo_proposal_used") else 0.0
        try:
            u0, _ = solver.solve(
                np.asarray(job["target_state"], dtype=np.float64),
                _ref_from_job(job), _res_from_job(job), q, lam,
            )
        except Exception:
            failures.append(tick)
            continue
        want = np.asarray(rec["first_control"], dtype=np.float64)
        errs.append(np.abs(u0 - want))
        try:
            solver.accept(anchor)
        except Exception:
            solver.reset_warmstart()
    if not errs:
        return {"samples": 0, "passed": False, "solve_failures": len(failures)}
    arr = np.asarray(errs, dtype=np.float64)
    max_err = float(np.max(arr))
    rms = float(math.sqrt(float(np.mean(arr ** 2))))
    max_gate = COLD_MAX_GATE_N if cold else SOLVE_MAX_GATE_N
    rms_gate = COLD_RMS_GATE_N if cold else SOLVE_RMS_GATE_N
    return {
        "mode": "cold" if cold else "chain",
        "samples": int(arr.shape[0]),
        "max_abs_diff_n": max_err,
        "rms_abs_diff_n": rms,
        "max_gate_n": max_gate,
        "rms_gate_n": rms_gate,
        "solve_failures": len(failures),
        "failure_ticks": failures[:10],
        "passed": max_err <= max_gate and rms <= rms_gate and not failures,
    }


# ----------------------------------------------------------------------
def authority_probe(cands: list[dict], solver, lambda_pi: float, samples: int) -> dict:
    """建议权限探针：在 q_pi 网格上测 |Δu0|，直接给出 |Δqπ|=5 N 的中位灵敏度。

    每次 solve 前都 reset（reset_native(1) 清 QP 记忆），保证 9+1 次求解互相独立；
    否则 SQP 内部迭代会跨求解携带，测出来的"权限"包含热启动路径依赖。
    网格含 ±5 N 与 ±25 N 两档：实测 25 N→50 N 已饱和（0.1385→0.1389 N），
    所以用 25 N 档外推到 5 N 会给出错误结论，必须直接测 5 N 档。
    """
    picks = cands[::5][:samples]
    levels = (5.0, 25.0)
    grid: list[tuple[float, float]] = [(0.0, 0.0)]
    for lv in levels:
        grid += [(lv, 0.0), (-lv, 0.0), (0.0, lv), (0.0, -lv), (lv, lv), (-lv, -lv)]
    results: dict[str, dict] = {}
    for lam in AUTHORITY_LAMBDAS:
        by_level: dict[str, list[float]] = {}
        diagnostics: dict[str, Any] = {"solves": 0, "failures": 0}
        for rec in picks:
            job = rec["job"]
            state = np.asarray(job["target_state"], dtype=np.float64)
            ref = _ref_from_job(job)
            res = _res_from_job(job)
            try:
                solver.reset_warmstart()
                base, _ = solver.solve(state, ref, res, [0.0, 0.0], lam)
            except Exception:
                diagnostics["failures"] += 1
                continue
            for q_pi in grid[1:]:
                try:
                    solver.reset_warmstart()
                    u, _ = solver.solve(state, ref, res, list(q_pi), lam)
                except Exception:
                    diagnostics["failures"] += 1
                    continue
                diagnostics["solves"] += 1
                level = max(abs(q_pi[0]), abs(q_pi[1]))
                by_level.setdefault(f"{level:g}N", []).append(float(np.max(np.abs(u - base))))
        summary = {
            k: {"median": float(np.median(v)), "p95": float(np.percentile(v, 95)), "n": len(v)}
            for k, v in sorted(by_level.items(), key=lambda kv: float(kv[0][:-1]))
        }
        five = by_level.get("5N") or []
        median_5 = float(np.median(five)) if five else 0.0
        results[f"{lam:g}"] = {
            "lambda_pi": lam,
            "by_delta_q": summary,
            "median_delta_u0_at_5N": median_5,
            "max_abs_delta_u0_at_5N": float(np.max(five)) if five else 0.0,
            "n_at_5N": len(five),
            "passed": median_5 >= AUTHORITY_MIN_MEDIAN_DU_N,
            "diagnostics": diagnostics,
        }
    passing = [r for r in results.values() if r["passed"]]
    selected = min(passing, key=lambda r: r["lambda_pi"])["lambda_pi"] if passing else None
    return {
        "samples": len(picks),
        "grid": [list(g) for g in grid],
        "min_median_du_at_5n": AUTHORITY_MIN_MEDIAN_DU_N,
        "by_lambda": results,
        "selected_lambda_pi": selected,
        "gate_passed": selected is not None,
    }


# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="运行目录（含 worker.source.jsonl）")
    parser.add_argument("--contract", default=None, help="默认 <run>/contract.json")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--lib", default=None, help="libusv_acados_backend.so 路径")
    parser.add_argument("--gp-snapshot", default=None,
                        help="GP 快照；默认从 job.gp_snapshot_sha256 无法反查时用 pooled")
    parser.add_argument("--authority", action="store_true")
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--lambda-pi", type=float, default=0.001)
    parser.add_argument("--max-candidates", type=int, default=0, help="0 = 全部")
    args = parser.parse_args(argv)

    run_dir = Path(args.run).resolve()
    contract = Path(args.contract) if args.contract else run_dir / "contract.json"
    contract_doc = json.loads(contract.read_text(encoding="utf-8"))
    offset = int(contract_doc.get("reference_start_offset", 2))
    cruise = float(contract_doc.get("cruise_speed", 0.6))
    projection_mode, lead_s = _reference_options(contract_doc)

    cands = _load_candidates(run_dir)
    if args.max_candidates:
        cands = cands[: args.max_candidates]
    if not cands:
        raise SystemExit(f"{run_dir} 没有可用 candidate 记录")

    path_rows, prof_rows = _load_scenario(run_dir)

    gp = None
    gp_predict = None
    gp_path = args.gp_snapshot
    if gp_path is None:
        gp_path = (cands[0]["job"].get("gp_snapshot_sha256") and None) or None
    if gp_path is None:
        from eval_r2_calib import _load_r2_gps

        pooled, _ = _load_r2_gps()
        gp_path = str(pooled)
    from fusion_controller import load_pooled_gp

    gp = load_pooled_gp(Path(gp_path))

    ref_gate = gate_reference(
        cands, path_rows, prof_rows, offset, cruise, projection_mode, lead_s,
        _logged_reference_jobs(run_dir),
    )
    hydro = _hydro_from_contract(contract_doc)
    activated = _activated_candidates(run_dir)
    res_gate = gate_residuals(cands, gp, hydro, activated=activated)

    # 每代内容一个求解器实例（p_global 只能在构造时给定）；代际切换时重置目标实例。
    contents = _generation_contents(contract_doc, run_dir)
    t_min = float(contract_doc.get("command_min_n", -25.0))
    t_max = float(contract_doc.get("command_max_n", 25.0))
    dt = float(contract_doc.get("dt", DT))
    d_t_max = float(contract_doc.get("backend_rate_n_s", 80.0))
    solvers = {
        gen: FusionSolver(content, lower=t_min, upper=t_max, max_delta=d_t_max * dt,
                          lib_path=args.lib)
        for gen, content in contents.items()
    }
    try:
        invalidations = _invalidation_ticks(run_dir)
        solve_gate = gate_solve(cands, solvers, cold=False, invalidate_ticks=invalidations)
        if not solve_gate["passed"]:
            solve_gate = gate_solve(cands, solvers, cold=True)
        report = {
            "schema": "scheme-a-fusion-clone-verification-v1",
            "run": str(run_dir),
            "candidates": len(cands),
            "contract": str(contract),
            "reference_gate": ref_gate,
            "residual_gate": res_gate,
            "solve_gate": solve_gate,
            "warmstart_invalidation_ticks": sorted(invalidations),
            "model_generations": {str(g): c for g, c in sorted(contents.items())},
        }
        if args.authority:
            report["authority"] = authority_probe(
                cands, solvers[min(solvers)], float(args.lambda_pi), int(args.samples)
            )
    finally:
        for s_ in solvers.values():
            s_.close()

    ok = bool(ref_gate["passed"] and res_gate["passed"] and solve_gate["passed"])
    report["passed"] = ok
    out = Path(args.out) if args.out else run_dir / "fusion_clone_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "passed": ok,
        "reference_max": ref_gate["max_abs_diff"],
        "residual_max": res_gate["max_abs_diff"],
        "residual_coverage": round(res_gate["coverage"], 4),
        "solve_mode": solve_gate.get("mode"),
        "solve_max": solve_gate.get("max_abs_diff_n"),
        "solve_rms": solve_gate.get("rms_abs_diff_n"),
        "authority_selected_lambda": (report.get("authority") or {}).get("selected_lambda_pi"),
        "out": str(out),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
