#!/usr/bin/env python3
"""Shared metrics and trajectory evaluation helpers for Scheme A closed-loop runs."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

from dataset_builder import DT_S, extract_run, wrap_angle
from gp_model import MultiChannelSparseGP


CHECKER_SCRIPT = Path(
    "/home/trevor/usv_scheme_a_wt/research/scheme_a/src/"
    "usv_research_safety_cpp/scripts/check_scheme_a_closed_loop.py"
)
DEFAULT_PLAN = Path(
    "/home/trevor/usv_scheme_a_wt/research/scheme_a/src/"
    "usv_research_safety_cpp/model/research_model_plan.json"
)
DEFAULT_CONTRACT = Path(
    "/home/trevor/usv_scheme_a_wt/research/scheme_a/src/"
    "usv_research_safety_cpp/model/contract_controlled_sim.json"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            blk = f.read(65536)
            if not blk:
                break
            h.update(blk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def load_xy_psi_t(path: Path) -> np.ndarray:
    rows: list[list[float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        vals = [float(v) for v in s.split()]
        if len(vals) >= 4:
            rows.append(vals[:4])
    return np.asarray(rows, dtype=np.float64)


def run_checker(
    run_dir: Path,
    source_hashes: Path,
    *,
    plan_path: Path | None = None,
    contract_path: Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Run check_scheme_a_closed_loop.py on a completed closed-loop run dir."""
    check_path = run_dir / "check.json"
    cmd = [
        "/usr/bin/python3",
        str(CHECKER_SCRIPT),
        "--run",
        str(run_dir),
        "--plan",
        str(plan_path or DEFAULT_PLAN),
        "--contract",
        str(contract_path or DEFAULT_CONTRACT),
        "--source-hashes",
        str(source_hashes),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    doc = (
        json.loads(check_path.read_text(encoding="utf-8"))
        if check_path.is_file()
        else {"verdict": "FAIL", "failures": [{"name": "check_json_missing", "reason": proc.stderr.strip()}]}
    )
    passed = (proc.returncode == 0) and (doc.get("verdict") == "PASS")
    return passed, doc


def path_polyline_metrics(
    states: np.ndarray,
    path_xy_psi: np.ndarray,
    profile_uvr: np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute geometric cross-track error, heading error, speed RMSE, and progress."""
    if len(states) == 0 or len(path_xy_psi) < 2:
        return {
            "samples": 0,
            "cross_track_rmse_m": float("nan"),
            "cross_track_max_m": float("nan"),
            "heading_rmse_rad": float("nan"),
            "heading_max_rad": float("nan"),
            "speed_rmse_mps": float("nan"),
            "along_track_progress_m": 0.0,
            "path_length_m": 0.0,
            "completion_ratio": 0.0,
        }

    pts = path_xy_psi[:, :2]
    segs = pts[1:] - pts[:-1]
    seg_len_sq = np.sum(segs ** 2, axis=1)
    seg_len = np.sqrt(np.maximum(seg_len_sq, 0.0))
    cum_s = np.concatenate([[0.0], np.cumsum(seg_len)])
    total_len = float(cum_s[-1])

    ctes: list[float] = []
    herrs: list[float] = []
    u_errs: list[float] = []
    s_vals: list[float] = []

    for st in states:
        p = st[:2]
        psi = float(st[2])
        u = float(st[3])
        best_d2 = float("inf")
        best_s = 0.0
        best_psi = float(path_xy_psi[0, 2])
        best_idx = 0
        for i in range(len(segs)):
            L2 = float(seg_len_sq[i])
            if L2 <= 1e-12:
                tau = 0.0
            else:
                tau = float(np.clip(np.dot(p - pts[i], segs[i]) / L2, 0.0, 1.0))
            proj = pts[i] + tau * segs[i]
            d2 = float(np.sum((p - proj) ** 2))
            if d2 < best_d2:
                best_d2 = d2
                best_s = float(cum_s[i] + tau * seg_len[i])
                if L2 > 1e-12:
                    best_psi = math.atan2(float(segs[i, 1]), float(segs[i, 0]))
                else:
                    best_psi = float(path_xy_psi[i, 2])
                best_idx = i if tau < 0.5 else min(i + 1, len(path_xy_psi) - 1)
        ctes.append(math.sqrt(best_d2))
        herrs.append(abs(wrap_angle(psi - best_psi)))
        s_vals.append(best_s)
        if profile_uvr is not None and len(profile_uvr) > best_idx:
            u_errs.append(u - float(profile_uvr[best_idx, 0]))

    cte_arr = np.asarray(ctes, dtype=np.float64)
    herr_arr = np.asarray(herrs, dtype=np.float64)
    progress_m = max(s_vals) if s_vals else 0.0
    comp = (progress_m / total_len) if total_len > 1e-6 else 1.0
    return {
        "samples": int(len(states)),
        "cross_track_rmse_m": float(np.sqrt(np.mean(cte_arr ** 2))),
        "cross_track_max_m": float(np.max(cte_arr)),
        "heading_rmse_rad": float(np.sqrt(np.mean(herr_arr ** 2))),
        "heading_max_rad": float(np.max(herr_arr)),
        "speed_rmse_mps": (
            float(np.sqrt(np.mean(np.asarray(u_errs, dtype=np.float64) ** 2)))
            if u_errs
            else float("nan")
        ),
        "along_track_progress_m": float(progress_m),
        "path_length_m": float(total_len),
        "completion_ratio": float(comp),
    }


def _percentiles(vals: list[float]) -> dict[str, float | None]:
    if not vals:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    arr = np.asarray(vals, dtype=np.float64)
    return {
        "count": int(arr.size),
        "mean": float(np.mean(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "max": float(np.max(arr)),
    }


def evaluate_closed_loop_run(
    run_dir: Path,
    *,
    source_hashes: Path | None = None,
    gp_models_by_sha: dict[str, MultiChannelSparseGP] | None = None,
    reuse_verified_check_json: bool = False,
) -> dict[str, Any]:
    """Extract comprehensive tracking, control, GP, PPO, and latency metrics."""
    run_doc = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    check_path = run_dir / "check.json"
    reused_check = False
    if reuse_verified_check_json and check_path.is_file():
        try:
            check_doc = json.loads(check_path.read_text(encoding="utf-8"))
            want_sh = sha256_file(source_hashes) if source_hashes is not None else None
            got_sh = (run_doc.get("binding") or {}).get("source_hashes_sha256")
            if (
                check_doc.get("verdict") == "PASS"
                and check_doc.get("run_id") == run_doc.get("run_id")
                and (want_sh is None or got_sh == want_sh)
            ):
                checker_passed = True
                reused_check = True
        except Exception:
            reused_check = False
    if not reused_check:
        if source_hashes is not None:
            checker_passed, check_doc = run_checker(run_dir, source_hashes)
        elif check_path.is_file():
            check_doc = json.loads(check_path.read_text(encoding="utf-8"))
            checker_passed = check_doc.get("verdict") == "PASS"
        else:
            check_doc = {}
            checker_passed = False

    reg_rows = load_jsonl(run_dir / "regulator.source.jsonl")
    worker_rows = load_jsonl(run_dir / "worker.source.jsonl")

    decisions = [r for r in reg_rows if r.get("type") == "decision"]
    decisions.sort(key=lambda r: int(r.get("tick") or 0))
    candidates = [r for r in worker_rows if r.get("type") == "candidate"]
    candidates_by_target_tick = {
        int((c.get("job") or {}).get("target_tick") or -1): c
        for c in candidates
        if (c.get("job") or {}).get("target_tick") is not None
    }

    extraction = extract_run(run_dir, split="eval")
    admitted = extraction.admitted
    admitted.sort(key=lambda r: int(r.get("tick") or 0))

    path_arr = load_xy_psi_t(run_dir / "scenario_path.txt")
    profile_arr = load_xy_psi_t(run_dir / "scenario_profile.txt")
    states_end = (
        np.asarray([a["x_end"] for a in admitted], dtype=np.float64)
        if admitted
        else np.zeros((0, 6), dtype=np.float64)
    )
    geom = path_polyline_metrics(states_end, path_arr, profile_arr)
    shutdown_ticks = {
        int(d["tick"])
        for d in decisions
        if str(d.get("reason") or "") == "shutdown" and d.get("tick") is not None
    }
    active_states_end = (
        np.asarray([a["x_end"] for a in admitted if int(a["tick"]) not in shutdown_ticks], dtype=np.float64)
        if admitted
        else np.zeros((0, 6), dtype=np.float64)
    )
    active_geom = path_polyline_metrics(active_states_end, path_arr, profile_arr)

    # Time-indexed tracking vs solver's stage-0/stage-1 reference.
    ref_pos_sq: list[float] = []
    ref_herr_sq: list[float] = []
    ref_u_sq: list[float] = []
    ref_v_sq: list[float] = []
    ref_r_sq: list[float] = []
    zero_res_sq: list[float] = []
    gp_res_sq: list[float] = []
    gp_res_count = 0

    for a in admitted:
        t = int(a["tick"])
        x_start = np.asarray(a["x_start"], dtype=np.float64)
        x_end = np.asarray(a["x_end"], dtype=np.float64)
        y_k = np.asarray(a["y_k"], dtype=np.float64)
        z_k = np.asarray(a["z_k"], dtype=np.float64)
        zero_res_sq.append(float(np.mean(y_k ** 2)))

        cand = candidates_by_target_tick.get(t)
        if cand is not None:
            ref = (cand.get("job") or {}).get("reference") or []
            if len(ref) >= 12:
                # Compare x_end against horizon stage k=1 reference.
                r1 = np.asarray(ref[6:12], dtype=np.float64)
                ref_pos_sq.append(float((x_end[0] - r1[0]) ** 2 + (x_end[1] - r1[1]) ** 2))
                ref_herr_sq.append(float(wrap_angle(float(x_end[2] - r1[2])) ** 2))
                ref_u_sq.append(float((x_end[3] - r1[3]) ** 2))
                ref_v_sq.append(float((x_end[4] - r1[4]) ** 2))
                ref_r_sq.append(float((x_end[5] - r1[5]) ** 2))
            elif len(ref) >= 6:
                r0 = np.asarray(ref[:6], dtype=np.float64)
                ref_pos_sq.append(float((x_start[0] - r0[0]) ** 2 + (x_start[1] - r0[1]) ** 2))
                ref_herr_sq.append(float(wrap_angle(float(x_start[2] - r0[2])) ** 2))
                ref_u_sq.append(float((x_start[3] - r0[3]) ** 2))
                ref_v_sq.append(float((x_start[4] - r0[4]) ** 2))
                ref_r_sq.append(float((x_start[5] - r0[5]) ** 2))

            gp_sha = str((cand.get("job") or {}).get("gp_snapshot_sha256") or "")
            if gp_models_by_sha and gp_sha in gp_models_by_sha:
                pred = gp_models_by_sha[gp_sha].predict(z_k)["mean"]
                gp_res_sq.append(float(np.mean((y_k - pred) ** 2)))
                gp_res_count += 1

    # Control smoothness and effort across admitted ticks.
    u_exec = (
        np.asarray([a["q_exec"] for a in admitted], dtype=np.float64)
        if admitted
        else np.zeros((0, 2), dtype=np.float64)
    )
    if len(u_exec) >= 2:
        du = np.diff(u_exec, axis=0)
        tv_per_step = float(np.mean(np.sum(np.abs(du), axis=1)))
        tv_total = float(np.sum(np.abs(du)))
    else:
        tv_per_step = 0.0
        tv_total = 0.0
    effort_int = float(np.sum(np.sum(u_exec ** 2, axis=1)) * DT_S) if len(u_exec) else 0.0

    # Decision telemetry: control source, GP schedule, PPO usage/modification, skipped ticks.
    ctrl_counts: dict[str, int] = {}
    ppo_reject_counts: dict[str, int] = {}
    gp_gen_runs: list[dict[str, Any]] = []
    ppo_used_ticks: list[int] = []
    ppo_mod_norms: list[float] = []
    gp_max_diffs: list[float] = []
    gp_ood_ticks = 0
    post_warmup_unaccepted = 0
    skipped_ticks_total = 0

    for d in decisions:
        t = int(d.get("tick") or 0)
        src = str(d.get("control_source") or "unknown")
        ctrl_counts[src] = ctrl_counts.get(src, 0) + 1
        skipped = int(d.get("skipped_ticks") or 0)
        skipped_ticks_total += skipped
        if t >= 3 and not bool(d.get("candidate_accepted")) and not bool(d.get("stopping")):
            # Exclude final ramp-down tick(s) if stopping.
            if src != "ramp_zero" or t < (decisions[-1].get("tick", 0) - 2):
                post_warmup_unaccepted += 1

        gp_gen = int(d.get("gp_generation") or 0)
        gp_sha = str(d.get("gp_snapshot_sha256") or "")
        gp_id = str(d.get("gp_snapshot_id") or "")
        if gp_gen > 0 or gp_sha:
            if not gp_gen_runs or gp_gen_runs[-1]["generation"] != gp_gen or gp_gen_runs[-1]["sha256"] != gp_sha:
                gp_gen_runs.append(
                    {
                        "generation": gp_gen,
                        "snapshot_id": gp_id,
                        "sha256": gp_sha,
                        "first_tick": t,
                        "last_tick": t,
                        "count": 1,
                    }
                )
            else:
                gp_gen_runs[-1]["last_tick"] = t
                gp_gen_runs[-1]["count"] += 1

        if "gp_local_approx_max_diff" in d and d.get("gp_local_approx_max_diff") is not None:
            gp_max_diffs.append(float(d["gp_local_approx_max_diff"]))
        if bool(d.get("gp_ood_detected")):
            gp_ood_ticks += 1

        rej = str(d.get("ppo_reject_reason") or "")
        if rej:
            ppo_reject_counts[rej] = ppo_reject_counts.get(rej, 0) + 1

        if bool(d.get("ppo_proposal_used")):
            ppo_used_ticks.append(t)
            q_pi = d.get("ppo_q_pi")
            u_fin = d.get("final_n")
            if isinstance(q_pi, list) and len(q_pi) == 2 and isinstance(u_fin, list) and len(u_fin) == 2:
                diff = math.hypot(float(u_fin[0]) - float(q_pi[0]), float(u_fin[1]) - float(q_pi[1]))
                ppo_mod_norms.append(diff)

    # Worker latencies (solve + freeze-to-publish e2e) and stage residual bounds.
    backend_ms = [float(c["backend_ms"]) for c in candidates if c.get("backend_ms") is not None]
    e2e_worker_ms = []
    stage_res_max_abs = 0.0
    first_candidate_info = None
    for c in sorted(candidates, key=lambda item: int((item.get("job") or {}).get("target_tick") or 0)):
        job = c.get("job") or {}
        if first_candidate_info is None and c.get("first_control"):
            first_candidate_info = {
                "target_tick": job.get("target_tick"),
                "first_control": list(c["first_control"]),
                "gp_snapshot_sha256": job.get("gp_snapshot_sha256"),
                "ppo_proposal_used": job.get("ppo_proposal_used"),
            }
        sr = job.get("stage_residuals") or []
        if sr:
            stage_res_max_abs = max(stage_res_max_abs, float(np.max(np.abs(np.asarray(sr, dtype=np.float64)))))
        f_ns = job.get("freeze_ns")
        p_ns = c.get("publish_start_ns")
        if f_ns is not None and p_ns is not None and int(p_ns) >= int(f_ns):
            e2e_worker_ms.append((int(p_ns) - int(f_ns)) / 1e6)

    dead_150_misses = sum(1 for v in e2e_worker_ms if v > 150.0)
    dead_200_misses = sum(1 for v in e2e_worker_ms if v > 200.0)

    cte_max = geom["cross_track_max_m"]
    all_finite = bool(len(states_end) > 0 and np.all(np.isfinite(states_end)))
    success = bool(
        checker_passed
        and (run_doc.get("failure") is None)
        and all_finite
        and (not math.isnan(cte_max) and cte_max < 3.0)
    )

    return {
        "run_dir": str(run_dir),
        "run_id": run_doc.get("run_id"),
        "maneuver": (run_doc.get("maneuver") or {}).get("name"),
        "seed": (run_doc.get("maneuver") or {}).get("seed"),
        "checker_passed": checker_passed,
        "checker_problems": [
            f"{f.get('name')}:{f.get('reason')}" for f in check_doc.get("failures", [])
        ],
        "run_failure": run_doc.get("failure"),
        "first_candidate": first_candidate_info,
        "stage_residuals_max_abs": stage_res_max_abs,
        "success": success,
        "decisions_total": len(decisions),
        "admitted_windows": len(admitted),
        "control_source_counts": ctrl_counts,
        "post_warmup_unaccepted": post_warmup_unaccepted,
        "skipped_ticks_total": skipped_ticks_total,
        "geometric_tracking": geom,
        "active_geometric_tracking": active_geom,
        "reference_tracking": {
            "count": len(ref_pos_sq),
            "pos_rmse_m": float(math.sqrt(np.mean(ref_pos_sq))) if ref_pos_sq else float("nan"),
            "heading_rmse_rad": float(math.sqrt(np.mean(ref_herr_sq))) if ref_herr_sq else float("nan"),
            "u_rmse_mps": float(math.sqrt(np.mean(ref_u_sq))) if ref_u_sq else float("nan"),
            "v_rmse_mps": float(math.sqrt(np.mean(ref_v_sq))) if ref_v_sq else float("nan"),
            "r_rmse_rps": float(math.sqrt(np.mean(ref_r_sq))) if ref_r_sq else float("nan"),
        },
        "residual_accuracy": {
            "zero_model_vel_rmse": float(math.sqrt(np.mean(zero_res_sq))) if zero_res_sq else float("nan"),
            "gp_model_vel_rmse": float(math.sqrt(np.mean(gp_res_sq))) if gp_res_sq else None,
            "gp_eval_count": gp_res_count,
        },
        "control_effort": {
            "tv_per_step": tv_per_step,
            "tv_total": tv_total,
            "thrust_l2_dt": effort_int,
        },
        "gp_telemetry": {
            "generation_timeline": gp_gen_runs,
            "local_approx_max_diff": float(max(gp_max_diffs)) if gp_max_diffs else None,
            "local_approx_mean_diff": float(np.mean(gp_max_diffs)) if gp_max_diffs else None,
            "ood_detected_ticks": gp_ood_ticks,
        },
        "ppo_telemetry": {
            "used_ticks_count": len(ppo_used_ticks),
            "used_first_tick": min(ppo_used_ticks) if ppo_used_ticks else None,
            "used_last_tick": max(ppo_used_ticks) if ppo_used_ticks else None,
            "reject_reason_counts": ppo_reject_counts,
            "nmpc_override_norm": _percentiles(ppo_mod_norms),
            "override_gt_0p5n_fraction": (
                float(np.mean(np.asarray(ppo_mod_norms) > 0.5)) if ppo_mod_norms else None
            ),
        },
        "latency_ms": {
            "solver_backend": _percentiles(backend_ms),
            "freeze_to_publish_e2e": _percentiles(e2e_worker_ms),
            "deadline_150ms_misses": dead_150_misses,
            "deadline_200ms_misses": dead_200_misses,
        },
        "u_exec": u_exec.tolist(),
        "states_end": states_end.tolist(),
        "decision_ticks": [int(d.get("tick") or 0) for d in decisions],
    }
