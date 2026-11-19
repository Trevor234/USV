#!/usr/bin/env python3
"""R1 Diagnosis: Phase-aligned ROS2 ablations (incl. Oracle) + Offline AcadosBackend p_global/offset ablations."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
from pathlib import Path
import queue
import subprocess
import sys
from typing import Any

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = Path("/home/trevor/usv_scheme_a_wt/research/scheme_a/src/usv_research_safety_cpp/scripts")
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from closed_loop_metrics import path_polyline_metrics
from eval_fusion_arms import (
    CONTRACT,
    GP_DIR,
    GP_POOLED,
    PROFILE_TO_GP,
    SPLIT_MANIFEST,
    _aggregate_arm,
    _run_episode,
    _strip_traj,
)
from gp_model import MultiChannelSparseGP
from run_scheme_a_closed_loop import generate_maneuver_path_and_profile


R1_WORK_ROOT = Path("/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/scheme_A_gp_ppo_20261117_work")
R1_ARCH_FUSION = Path("/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/scheme_A_gp_ppo_20261117_r1/wp7_fusion/four_arm_evaluation.json")
R2_WORK_ROOT = Path("/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/scheme_A_gp_ppo_20261118_work")
OFFLINE_BIN = R2_WORK_ROOT / "tools/offline_acados_eval"
DEFAULT_SOURCE_HASHES = R2_WORK_ROOT / "meta/source_hashes.json"


def _pct_summary(vals: list[float]) -> dict[str, float | None]:
    clean = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
    if not clean:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    arr = np.asarray(clean, dtype=np.float64)
    return {
        "count": int(len(arr)),
        "mean": float(np.mean(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
    }


def _extract_run_telemetry(run_dir: Path) -> dict[str, Any]:
    """Extract per-stage latencies, freeze-vs-post diffs, OOD counts, and non-accepted counts."""
    reg_file = run_dir / "regulator.source.jsonl"
    wrk_file = run_dir / "worker.source.jsonl"
    reg_rows = [json.loads(l) for l in reg_file.read_text(encoding="utf-8").splitlines() if l.strip()] if reg_file.is_file() else []
    wrk_rows = [json.loads(l) for l in wrk_file.read_text(encoding="utf-8").splitlines() if l.strip()] if wrk_file.is_file() else []

    reg_prep_wall = []
    prep_timing: dict[str, list[float]] = {}
    for r in reg_rows:
        if r.get("type") != "job":
            continue
        j = r["job"]
        if isinstance(j.get("freeze_ns"), int) and isinstance(r.get("submit_commit_ns"), int):
            reg_prep_wall.append((r["submit_commit_ns"] - j["freeze_ns"]) / 1e6)
        pt = r.get("prep_timing_ms")
        if isinstance(pt, dict):
            for k, v in pt.items():
                if isinstance(v, (int, float)):
                    prep_timing.setdefault(k, []).append(float(v))

    w_post_wall = []
    w_solve_wall = []
    wrk_timing: dict[str, list[float]] = {}
    cand_diffs: list[float] = []
    ood_cands = 0
    cand_count = 0
    for r in wrk_rows:
        if r.get("type") != "candidate":
            continue
        cand_count += 1
        if isinstance(r.get("solve_start_ns"), int) and isinstance(r.get("solve_end_ns"), int):
            w_solve_wall.append((r["solve_end_ns"] - r["solve_start_ns"]) / 1e6)
        if isinstance(r.get("solve_end_ns"), int) and isinstance(r.get("publish_start_ns"), int):
            w_post_wall.append((r["publish_start_ns"] - r["solve_end_ns"]) / 1e6)
        wt = r.get("worker_timing_ms")
        if isinstance(wt, dict):
            for k, v in wt.items():
                if isinstance(v, (int, float)):
                    wrk_timing.setdefault(k, []).append(float(v))
        if r.get("gp_local_approx_max_diff") is not None:
            cand_diffs.append(float(r["gp_local_approx_max_diff"]))
        if r.get("gp_ood_detected"):
            ood_cands += 1

    nonacc_reasons: dict[str, int] = {}
    post_warmup_nonacc = 0
    for r in reg_rows:
        if r.get("type") != "decision":
            continue
        reason = str(r.get("reason") or "")
        if reason == "shutdown":
            continue
        if not r.get("accepted"):
            nonacc_reasons[reason] = nonacc_reasons.get(reason, 0) + 1
            if int(r.get("tick") or 0) > 12:
                post_warmup_nonacc += 1

    return {
        "reg_prep_wall_ms": _pct_summary(reg_prep_wall),
        "w_solve_wall_ms": _pct_summary(w_solve_wall),
        "w_post_wall_ms": _pct_summary(w_post_wall),
        "prep_timing_ms": {k: _pct_summary(v) for k, v in sorted(prep_timing.items())},
        "worker_timing_ms": {k: _pct_summary(v) for k, v in sorted(wrk_timing.items())},
        "gp_local_approx_max_diff": _pct_summary(cand_diffs),
        "gp_ood_candidate_count": ood_cands,
        "candidate_count": cand_count,
        "nonacc_pre_shutdown": nonacc_reasons,
        "post_warmup_nonacc_gt12": post_warmup_nonacc,
    }


def _aggregate_telemetry(runs: list[dict[str, Any]], tel_by_ep: dict[str, dict[str, Any]]) -> dict[str, Any]:
    reg_p50 = [tel_by_ep[r["episode_name"]]["reg_prep_wall_ms"]["p50"] for r in runs]
    reg_p95 = [tel_by_ep[r["episode_name"]]["reg_prep_wall_ms"]["p95"] for r in runs]
    wpost_p50 = [tel_by_ep[r["episode_name"]]["w_post_wall_ms"]["p50"] for r in runs]
    wpost_p95 = [tel_by_ep[r["episode_name"]]["w_post_wall_ms"]["p95"] for r in runs]
    fdiff_mean = [tel_by_ep[r["episode_name"]]["gp_local_approx_max_diff"]["mean"] for r in runs if tel_by_ep[r["episode_name"]]["gp_local_approx_max_diff"]["count"] > 0]
    fdiff_max = [tel_by_ep[r["episode_name"]]["gp_local_approx_max_diff"]["max"] for r in runs if tel_by_ep[r["episode_name"]]["gp_local_approx_max_diff"]["count"] > 0]
    post_nonacc = sum(tel_by_ep[r["episode_name"]]["post_warmup_nonacc_gt12"] for r in runs)
    total_ood = sum(tel_by_ep[r["episode_name"]]["gp_ood_candidate_count"] for r in runs)
    total_cand = sum(tel_by_ep[r["episode_name"]]["candidate_count"] for r in runs)
    reasons: dict[str, int] = {}
    for r in runs:
        for k, v in tel_by_ep[r["episode_name"]]["nonacc_pre_shutdown"].items():
            reasons[k] = reasons.get(k, 0) + int(v)
    return {
        "reg_prep_p50_mean_ms": float(np.mean([x for x in reg_p50 if x is not None])) if any(x is not None for x in reg_p50) else None,
        "reg_prep_p95_mean_ms": float(np.mean([x for x in reg_p95 if x is not None])) if any(x is not None for x in reg_p95) else None,
        "w_post_p50_mean_ms": float(np.mean([x for x in wpost_p50 if x is not None])) if any(x is not None for x in wpost_p50) else None,
        "w_post_p95_mean_ms": float(np.mean([x for x in wpost_p95 if x is not None])) if any(x is not None for x in wpost_p95) else None,
        "freeze_post_diff_mean": float(np.mean(fdiff_mean)) if fdiff_mean else None,
        "freeze_post_diff_max": float(np.max(fdiff_max)) if fdiff_max else None,
        "gp_ood_fraction": (total_ood / total_cand) if total_cand else 0.0,
        "post_warmup_nonacc_gt12": post_nonacc,
        "nonacc_pre_shutdown_reasons": reasons,
    }


def _run_offline_suite(out_dir: Path, test_eps: list[dict[str, Any]], steps: int = 300) -> dict[str, Any]:
    """Run offline_acados_eval across final_test episodes for solver/oracle/offset ablations."""
    if not OFFLINE_BIN.is_file():
        raise FileNotFoundError(f"Missing offline binary: {OFFLINE_BIN}")
    off_dir = out_dir / "offline_acados"
    off_dir.mkdir(parents=True, exist_ok=True)
    seconds = steps * 0.2 + 10.0

    # Prepare scenarios once.
    scenarios: dict[str, tuple[Path, Path, np.ndarray, np.ndarray]] = {}
    for ep in test_eps:
        ename = ep["episode_name"]
        ep_sdir = off_dir / "scenarios" / ename
        ep_sdir.mkdir(parents=True, exist_ok=True)
        pfile = ep_sdir / "path.txt"
        qfile = ep_sdir / "profile.txt"
        prows, qrows = generate_maneuver_path_and_profile(
            str(ep["maneuver"]), seconds, seed=int(ep["seed"]), cruise_speed=ep.get("cruise_speed")
        )
        pfile.write_text("\n".join(prows) + "\n", encoding="utf-8")
        qfile.write_text("\n".join(qrows) + "\n", encoding="utf-8")
        path_arr = np.asarray([[float(v) for v in l.split()[:3]] for l in prows], dtype=np.float64)
        prof_arr = np.asarray([[float(v) for v in l.split()[:4]] for l in qrows], dtype=np.float64)
        scenarios[ename] = (pfile, qfile, path_arr, prof_arr)

    configs: list[tuple[str, str, int, bool]] = [
        ("nominal", "nominal", 2, False),
        ("oracle_stage", "oracle_stage", 2, False),
        ("oracle_two_pass", "oracle_two_pass", 2, False),
        ("oracle_pglobal", "oracle_pglobal", 2, False),
        ("gp_pooled_1pass", "gp_stage", 2, False),
        ("gp_pooled_2pass", "gp_two_pass", 2, False),
        ("gp_matched_1pass", "gp_stage", 2, True),
        ("gp_matched_2pass", "gp_two_pass", 2, True),
        ("nominal_off0", "nominal", 0, False),
        ("nominal_off1", "nominal", 1, False),
        ("nominal_off3", "nominal", 3, False),
        ("oracle_stage_off0", "oracle_stage", 0, False),
        ("oracle_stage_off1", "oracle_stage", 1, False),
        ("oracle_stage_off3", "oracle_stage", 3, False),
        ("oracle_pglobal_off0", "oracle_pglobal", 0, False),
        ("oracle_pglobal_off1", "oracle_pglobal", 1, False),
        ("oracle_pglobal_off3", "oracle_pglobal", 3, False),
    ]

    results: dict[str, Any] = {}
    for label, mode, ref_off, use_matched in configs:
        ep_metrics: list[dict[str, Any]] = []
        for ep in test_eps:
            ename = ep["episode_name"]
            prof = str(ep.get("profile") or "")
            if use_matched and prof not in PROFILE_TO_GP:
                continue
            gp_file = PROFILE_TO_GP[prof] if use_matched else (GP_POOLED if "gp_" in mode else None)
            pfile, qfile, path_arr, prof_arr = scenarios[ename]
            raw_json = off_dir / f"{label}_{ename}.json"
            cmd = [
                str(OFFLINE_BIN),
                "--contract", str(CONTRACT),
                "--plant", str(ep["plant_model_file"]),
                "--path", str(pfile),
                "--profile", str(qfile),
                "--mode", mode,
                "--steps", str(steps),
                "--ref-offset", str(ref_off),
                "--out-json", str(raw_json),
            ]
            if gp_file is not None:
                cmd.extend(["--gp-snapshot", str(gp_file)])
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise RuntimeError(f"offline_acados_eval failed {label}/{ename}: {proc.stderr}")
            traj = json.loads(raw_json.read_text(encoding="utf-8"))["trajectory"]
            states = np.asarray([r["x"] for r in traj], dtype=np.float64)
            u_arr = np.asarray([r["u"] for r in traj], dtype=np.float64)
            exact_res = np.asarray([r["exact_vel_res0"] for r in traj], dtype=np.float64)
            applied_res = np.asarray([r["applied_res0"] for r in traj], dtype=np.float64)
            geom = path_polyline_metrics(states, path_arr, prof_arr)
            zero_res_rmse = float(np.sqrt(np.mean(exact_res ** 2)))
            model_res_rmse = float(np.sqrt(np.mean((exact_res - applied_res) ** 2)))
            tv = float(np.mean(np.sum(np.abs(np.diff(u_arr, axis=0)), axis=1)))
            ep_metrics.append({
                "episode_name": ename,
                "maneuver": ep["maneuver"],
                "profile": prof,
                **geom,
                "tv_per_step": tv,
                "zero_res_rmse": zero_res_rmse,
                "model_res_rmse": model_res_rmse,
                "freeze_post_diff_max": float(max(r["freeze_post_diff"] for r in traj)),
                "ood_fraction": float(np.mean([1.0 if r["ood"] else 0.0 for r in traj])),
                "solve_ms_mean": float(np.mean([r["solve_ms"] for r in traj])),
            })
        results[label] = {
            "episodes": len(ep_metrics),
            "cte_rmse_mean": float(np.mean([e["cross_track_rmse_m"] for e in ep_metrics])),
            "cte_max_mean": float(np.mean([e["cross_track_max_m"] for e in ep_metrics])),
            "heading_rmse_mean": float(np.mean([e["heading_rmse_rad"] for e in ep_metrics])),
            "speed_rmse_mean": float(np.mean([e["speed_rmse_mps"] for e in ep_metrics])),
            "progress_mean_m": float(np.mean([e["along_track_progress_m"] for e in ep_metrics])),
            "tv_mean": float(np.mean([e["tv_per_step"] for e in ep_metrics])),
            "model_res_rmse_mean": float(np.mean([e["model_res_rmse"] for e in ep_metrics])),
            "zero_res_rmse_mean": float(np.mean([e["zero_res_rmse"] for e in ep_metrics])),
            "freeze_post_diff_max": float(np.max([e["freeze_post_diff_max"] for e in ep_metrics])),
            "ood_fraction_mean": float(np.mean([e["ood_fraction"] for e in ep_metrics])),
            "solve_ms_mean": float(np.mean([e["solve_ms_mean"] for e in ep_metrics])),
            "per_episode": ep_metrics,
        }
    return results


def _run_ros2_ablations(
    out_dir: Path,
    test_eps: list[dict[str, Any]],
    source_hashes: Path,
    gp_models: dict[str, MultiChannelSparseGP],
    workers: int,
    base_domain_id: int,
    stop_decisions: int,
    lambda_pi: float,
    resume: bool,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, dict[str, Any]]]]:
    domain_q: queue.Queue[int] = queue.Queue()
    for i in range(max(1, workers)):
        domain_q.put(base_domain_id + i)

    tasks: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    arm_configs = {
        "nominal_nmpc": {"gp": None, "oracle": False, "ppo": False, "lambda_pi": 0.0},
        "oracle_nmpc": {"gp": None, "oracle": True, "ppo": False, "lambda_pi": 0.0},
        "gp_nmpc": {"gp": GP_POOLED, "oracle": False, "ppo": False, "lambda_pi": 0.0},
        "ppo_guided_nmpc": {"gp": None, "oracle": False, "ppo": True, "lambda_pi": lambda_pi},
        "gp_ppo_nmpc": {"gp": GP_POOLED, "oracle": False, "ppo": True, "lambda_pi": lambda_pi},
    }
    for arm_name, spec in arm_configs.items():
        for ep in test_eps:
            tasks.append((arm_name, ep, spec))
    for ep in test_eps:
        prof = str(ep.get("profile") or "")
        if prof in PROFILE_TO_GP:
            tasks.append(("gp_nmpc_matched", ep, {"gp": PROFILE_TO_GP[prof], "oracle": False, "ppo": False, "lambda_pi": 0.0}))

    runs_by_arm: dict[str, list[dict[str, Any]]] = {k: [] for k in (*arm_configs.keys(), "gp_nmpc_matched")}
    tel_by_arm: dict[str, dict[str, dict[str, Any]]] = {k: {} for k in runs_by_arm}

    def _worker_task(arm_name: str, ep: dict[str, Any], spec: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        ep_dir = out_dir / "ros2_phase_aligned" / arm_name / ep["episode_name"]
        m = _strip_traj(_run_episode(
            run_dir=ep_dir,
            ep=ep,
            stop_decisions=stop_decisions,
            domain_queue=domain_q,
            gp_models=gp_models,
            gp_snapshot=spec["gp"],
            oracle_plant_file=Path(ep["plant_model_file"]) if spec["oracle"] else None,
            align_tick_phase=True,
            source_hashes=source_hashes,
            ppo_proposal=spec["ppo"],
            lambda_pi=spec["lambda_pi"],
            resume=resume,
        ))
        m["episode_name"] = ep["episode_name"]
        tel = _extract_run_telemetry(ep_dir)
        return arm_name, m, tel

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = [pool.submit(_worker_task, arm_name, ep, spec) for arm_name, ep, spec in tasks]
        total = len(futs)
        for idx, fut in enumerate(futs, 1):
            arm_name, m, tel = fut.result()
            runs_by_arm[arm_name].append(m)
            tel_by_arm[arm_name][m["episode_name"]] = tel
            print(
                f"[R1 {idx}/{total}] arm={arm_name:16s} ep={m['episode_name']:48s} "
                f"cte={m['geometric_tracking']['cross_track_rmse_m']:.4f} "
                f"e2e_p95={m['latency_ms']['freeze_to_publish_e2e']['p95']:.2f}ms "
                f"reused={m.get('reused')}",
                flush=True,
            )

    for arm in runs_by_arm:
        runs_by_arm[arm].sort(key=lambda r: r["episode_name"])
    return runs_by_arm, tel_by_arm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(R2_WORK_ROOT / "diagnosis"))
    parser.add_argument("--source-hashes", default=str(DEFAULT_SOURCE_HASHES))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--base-domain-id", type=int, default=80)
    parser.add_argument("--test-decisions", type=int, default=301)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--offline-only", action="store_true")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = Path(args.source_hashes)
    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    test_eps = sorted([e for e in manifest["episodes"] if e["split"] == "final_test"], key=lambda e: e["episode_name"])
    single_names = {e["episode_name"] for e in test_eps if str(e.get("profile") or "") in PROFILE_TO_GP}
    heldout_names = {e["episode_name"] for e in test_eps if e["episode_name"] not in single_names}

    r1_doc = json.loads(R1_ARCH_FUSION.read_text(encoding="utf-8"))
    active_lambda = float(r1_doc["selected_configuration"]["selected_positive_lambda_pi"])

    off_cache = out_dir / "offline_acados_diagnosis.json"
    if not args.no_resume and not args.offline_only and off_cache.is_file():
        print(f"[R1] Reusing cached offline diagnosis from {off_cache}", flush=True)
        offline_res = json.loads(off_cache.read_text(encoding="utf-8"))["offline_acados"]
    else:
        print("[R1] Running offline AcadosBackend p_global + stage residual + ref_offset ablations...", flush=True)
        offline_res = _run_offline_suite(out_dir, test_eps, steps=max(1, int(args.test_decisions) - 1))

    diag_doc: dict[str, Any] = {
        "schema": "scheme-a-r1-diagnosis-v1",
        "offline_acados": offline_res,
    }

    if args.offline_only:
        off_path = out_dir / "offline_acados_diagnosis.json"
        off_path.write_text(json.dumps(diag_doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "offline_only_ok", "json": str(off_path)}, ensure_ascii=False))
        return 0

    gp_models: dict[str, MultiChannelSparseGP] = {}
    for p in (GP_POOLED, *PROFILE_TO_GP.values()):
        m = MultiChannelSparseGP.load(p)
        gp_models[m.snapshot_sha256] = m

    print(f"[R1] Running Phase-Aligned ROS2 closed-loop ablations (workers={args.workers}, lambda_pi={active_lambda})...", flush=True)
    runs_by_arm, tel_by_arm = _run_ros2_ablations(
        out_dir=out_dir,
        test_eps=test_eps,
        source_hashes=source_hashes,
        gp_models=gp_models,
        workers=int(args.workers),
        base_domain_id=int(args.base_domain_id),
        stop_decisions=int(args.test_decisions),
        lambda_pi=active_lambda,
        resume=not args.no_resume,
    )

    nom12 = runs_by_arm["nominal_nmpc"]
    nom_single = [r for r in nom12 if r["episode_name"] in single_names]
    nom_held = [r for r in nom12 if r["episode_name"] in heldout_names]

    r2_agg12 = {
        arm: {
            **_aggregate_arm(runs, nominal_runs=nom12 if arm != "nominal_nmpc" else None),
            "telemetry": _aggregate_telemetry(runs, tel_by_arm[arm]),
        }
        for arm, runs in runs_by_arm.items()
        if len(runs) == len(test_eps)
    }
    r2_agg_single6 = {
        arm: {
            **_aggregate_arm([r for r in runs if r["episode_name"] in single_names], nominal_runs=nom_single if arm != "nominal_nmpc" else None),
            "telemetry": _aggregate_telemetry([r for r in runs if r["episode_name"] in single_names], tel_by_arm[arm]),
        }
        for arm, runs in runs_by_arm.items()
        if len([r for r in runs if r["episode_name"] in single_names]) == len(single_names)
    }
    r2_agg_held6 = {
        arm: {
            **_aggregate_arm([r for r in runs if r["episode_name"] in heldout_names], nominal_runs=nom_held if arm != "nominal_nmpc" else None),
            "telemetry": _aggregate_telemetry([r for r in runs if r["episode_name"] in heldout_names], tel_by_arm[arm]),
        }
        for arm, runs in runs_by_arm.items()
        if len([r for r in runs if r["episode_name"] in heldout_names]) == len(heldout_names)
    }

    # Extract R1 telemetry directly from 20261117_work/fusion_eval/final_test logs for side-by-side latency & nonacc diff.
    r1_tel: dict[str, dict[str, Any]] = {}
    r1_agg_tel: dict[str, Any] = {}
    r1_runs_all = {
        **r1_doc["final_test_episodes"],
        "gp_nmpc_matched": r1_doc["final_test_matched_single_episodes"],
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as r1_pool:
        r1_futs = []
        for arm, runs in r1_runs_all.items():
            r1_tel[arm] = {}
            for r in runs:
                ename = r["episode_name"]
                r1_dir = R1_WORK_ROOT / "fusion_eval/final_test" / arm / ename
                r1_futs.append((arm, ename, r1_pool.submit(_extract_run_telemetry, r1_dir)))
        for arm, ename, rf in r1_futs:
            r1_tel[arm][ename] = rf.result()
    for arm, runs in r1_runs_all.items():
        r1_agg_tel[arm] = _aggregate_telemetry(runs, r1_tel[arm])

    # Group freeze_post_diff & OOD by maneuver for gp_nmpc and gp_nmpc_matched.
    by_maneuver: dict[str, dict[str, Any]] = {}
    for arm in ("gp_nmpc", "gp_nmpc_matched", "oracle_nmpc"):
        man_groups: dict[str, list[dict[str, Any]]] = {}
        for r in runs_by_arm[arm]:
            man_groups.setdefault(str(r["maneuver"]), []).append({
                "ep": r["episode_name"],
                **tel_by_arm[arm][r["episode_name"]],
                "cte": r["geometric_tracking"]["cross_track_rmse_m"],
            })
        by_maneuver[arm] = {
            man: {
                "episodes": len(items),
                "cte_mean": float(np.mean([x["cte"] for x in items])),
                "freeze_post_diff_mean": float(np.mean([x["gp_local_approx_max_diff"]["mean"] for x in items if x["gp_local_approx_max_diff"]["mean"] is not None])),
                "freeze_post_diff_p95": float(np.mean([x["gp_local_approx_max_diff"]["p95"] for x in items if x["gp_local_approx_max_diff"]["p95"] is not None])),
                "freeze_post_diff_max": float(np.max([x["gp_local_approx_max_diff"]["max"] for x in items if x["gp_local_approx_max_diff"]["max"] is not None])),
                "ood_fraction": float(sum(x["gp_ood_candidate_count"] for x in items) / max(1, sum(x["candidate_count"] for x in items))),
            }
            for man, items in sorted(man_groups.items())
        }

    diag_doc.update({
        "active_lambda_pi": active_lambda,
        "r1_aggregates_all12": r1_doc["final_test_aggregates_all12"],
        "r1_aggregates_held6": r1_doc["final_test_aggregates_heldout6"],
        "r1_gp_nmpc_matched_single6": r1_doc["final_test_gp_nmpc_matched_single6"],
        "r1_telemetry": r1_agg_tel,
        "r2_aggregates_all12": r2_agg12,
        "r2_aggregates_single6": r2_agg_single6,
        "r2_aggregates_held6": r2_agg_held6,
        "r2_runs_by_arm": runs_by_arm,
        "r2_telemetry_by_arm": tel_by_arm,
        "by_maneuver_freeze_diff": by_maneuver,
    })

    json_path = out_dir / "gp_regression_diagnosis.json"
    json_path.write_text(json.dumps(diag_doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # Write clean human-readable diagnosis markdown.
    md_lines = [
        "# R1 Root-Cause Diagnosis Report (Phase-Aligned ROS2 + Oracle + Offline AcadosBackend)",
        "",
        "## (a) Bug-Fix Impact (`r1` Unaligned/Buggy vs `r2` Bug-Fixed & Phase-Aligned on `final_test`)",
        "| Arm / Subset | r1 CTE (m) | r2 CTE (m) | ΔCTE (r2-r1) | r1 Post-Warmup NonAcc | r2 Post-Warmup NonAcc | r1 E2E P95 (ms) | r2 E2E P95 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, r1_a, r2_a, r1_t in [
        ("nominal_nmpc (12)", r1_doc["final_test_aggregates_all12"]["nominal_nmpc"], r2_agg12["nominal_nmpc"], r1_agg_tel["nominal_nmpc"]),
        ("gp_nmpc pooled (12)", r1_doc["final_test_aggregates_all12"]["gp_nmpc"], r2_agg12["gp_nmpc"], r1_agg_tel["gp_nmpc"]),
        ("ppo_guided_nmpc (12)", r1_doc["final_test_aggregates_all12"]["ppo_guided_nmpc"], r2_agg12["ppo_guided_nmpc"], r1_agg_tel["ppo_guided_nmpc"]),
        ("gp_ppo_nmpc (12)", r1_doc["final_test_aggregates_all12"]["gp_ppo_nmpc"], r2_agg12["gp_ppo_nmpc"], r1_agg_tel["gp_ppo_nmpc"]),
        ("gp_nmpc_matched (6)", r1_doc["final_test_gp_nmpc_matched_single6"], r2_agg_single6["gp_nmpc_matched"], r1_agg_tel["gp_nmpc_matched"]),
    ]:
        c1 = r1_a["cross_track_rmse_m"]["mean"]
        c2 = r2_a["cross_track_rmse_m"]["mean"]
        e1 = r1_a["latency_ms"]["e2e_p95_mean"]
        e2 = r2_a["latency_ms"]["e2e_p95_mean"]
        na1 = r1_t["post_warmup_nonacc_gt12"]
        na2 = r2_a["telemetry"]["post_warmup_nonacc_gt12"]
        md_lines.append(f"| `{arm}` | {c1:.4f} | {c2:.4f} | {c2 - c1:+.4f} | {na1} | {na2} | {e1:.2f} | {e2:.2f} |")

    md_lines.extend([
        "",
        "## (b) Oracle Upper Bound vs GP vs Nominal Gap (ROS2 Closed-Loop, Phase-Aligned)",
        "### All 12 `final_test` Episodes",
        "| Arm | CTE RMSE (m) | Δ vs Nom | Heading RMSE | Speed RMSE | Progress (m) | Vel Res RMSE | E2E P50 / P95 / Max (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for arm in ("nominal_nmpc", "oracle_nmpc", "gp_nmpc", "ppo_guided_nmpc", "gp_ppo_nmpc"):
        a = r2_agg12[arm]
        dnom = a.get("vs_nominal", {}).get("cte_rmse_delta_mean_m", 0.0)
        resv = a["gp_model_vel_rmse"]["mean"] if a["gp_model_vel_rmse"]["mean"] is not None else a["zero_model_vel_rmse"]["mean"]
        lat = a["latency_ms"]
        md_lines.append(
            f"| `{arm}` | {a['cross_track_rmse_m']['mean']:.4f} | {dnom:+.4f} | {a['heading_rmse_rad']['mean']:.4f} | "
            f"{a['speed_rmse_mps']['mean']:.4f} | {a['along_track_progress_m']['mean']:.2f} | {resv:.5f} | "
            f"{lat['e2e_p50_mean']:.2f} / {lat['e2e_p95_mean']:.2f} / {lat['e2e_max']:.2f} |"
        )

    md_lines.extend([
        "",
        "### Known-Profile Single-Plant 6 Episodes (`mass+10%`, `Xu+15%`, `Nr+15%`)",
        "| Arm | CTE RMSE (m) | Δ vs Nom | Vel Res RMSE |",
        "|---|---:|---:|---:|",
    ])
    for arm in ("nominal_nmpc", "oracle_nmpc", "gp_nmpc_matched", "gp_nmpc"):
        a = r2_agg_single6[arm]
        dnom = a.get("vs_nominal", {}).get("cte_rmse_delta_mean_m", 0.0)
        resv = a["gp_model_vel_rmse"]["mean"] if a["gp_model_vel_rmse"]["mean"] is not None else a["zero_model_vel_rmse"]["mean"]
        md_lines.append(f"| `{arm}` | {a['cross_track_rmse_m']['mean']:.4f} | {dnom:+.4f} | {resv:.5f} |")

    md_lines.extend([
        "",
        "### Offline `AcadosBackend` Exact `oracle_pglobal` vs Stage Residual & `reference_start_offset` (12 Episodes)",
        "| Offline Mode / Offset | Eps | CTE RMSE (m) | Δ vs Nom(off=2) | Heading RMSE | Vel Res RMSE | Freeze-Post Diff Max | OOD % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    nom_off2 = offline_res["nominal"]["cte_rmse_mean"]
    for key in (
        "nominal", "oracle_stage", "oracle_two_pass", "oracle_pglobal",
        "gp_pooled_1pass", "gp_pooled_2pass", "gp_matched_1pass", "gp_matched_2pass",
        "nominal_off0", "nominal_off1", "nominal_off3",
        "oracle_stage_off0", "oracle_stage_off1", "oracle_stage_off3",
        "oracle_pglobal_off0", "oracle_pglobal_off1", "oracle_pglobal_off3",
    ):
        v = offline_res[key]
        md_lines.append(
            f"| `{key}` | {v['episodes']} | {v['cte_rmse_mean']:.5f} | {v['cte_rmse_mean'] - nom_off2:+.5f} | "
            f"{v['heading_rmse_mean']:.5f} | {v['model_res_rmse_mean']:.5f} | {v['freeze_post_diff_max']:.5f} | "
            f"{100.0 * v['ood_fraction_mean']:.1f}% |"
        )

    md_lines.extend([
        "",
        "## (c) Freeze-vs-Post-Solve Residual Diff (`gp_local_approx_max_diff`) & OOD by Maneuver (ROS2)",
        "| Arm | Maneuver | Eps | CTE (m) | Mean Diff | P95 Diff | Max Diff | OOD Frac |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for arm in ("oracle_nmpc", "gp_nmpc", "gp_nmpc_matched"):
        for man, mv in by_maneuver[arm].items():
            md_lines.append(
                f"| `{arm}` | `{man}` | {mv['episodes']} | {mv['cte_mean']:.4f} | "
                f"{mv['freeze_post_diff_mean']:.5f} | {mv['freeze_post_diff_p95']:.5f} | "
                f"{mv['freeze_post_diff_max']:.5f} | {100.0 * mv['ood_fraction']:.1f}% |"
            )

    md_lines.extend([
        "",
        "## (d) Latency Breakdown Speedup (`r1 -O0 + alloc + var` vs `r2 -O3 + stack + mean-only`)",
        "| Arm | r1 reg_prep P50/P95 | r2 reg_prep P50/P95 | r1 w_post P50/P95 | r2 w_post P50/P95 | r1 E2E P50/P95 | r2 E2E P50/P95 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for arm, r1_a, r2_a, r1_t in [
        ("nominal_nmpc", r1_doc["final_test_aggregates_all12"]["nominal_nmpc"], r2_agg12["nominal_nmpc"], r1_agg_tel["nominal_nmpc"]),
        ("oracle_nmpc", None, r2_agg12["oracle_nmpc"], None),
        ("gp_nmpc", r1_doc["final_test_aggregates_all12"]["gp_nmpc"], r2_agg12["gp_nmpc"], r1_agg_tel["gp_nmpc"]),
        ("gp_nmpc_matched", r1_doc["final_test_gp_nmpc_matched_single6"], r2_agg_single6["gp_nmpc_matched"], r1_agg_tel["gp_nmpc_matched"]),
    ]:
        t2 = r2_a["telemetry"]
        l2 = r2_a["latency_ms"]
        r1_rp = f"{r1_t['reg_prep_p50_mean_ms']:.2f}/{r1_t['reg_prep_p95_mean_ms']:.2f}" if r1_t else "-"
        r1_wp = f"{r1_t['w_post_p50_mean_ms']:.2f}/{r1_t['w_post_p95_mean_ms']:.2f}" if r1_t else "-"
        r1_e = f"{r1_a['latency_ms']['e2e_p50_mean']:.2f}/{r1_a['latency_ms']['e2e_p95_mean']:.2f}" if r1_a else "-"
        r2_rp = f"{t2['reg_prep_p50_mean_ms']:.3f}/{t2['reg_prep_p95_mean_ms']:.3f}"
        r2_wp = f"{t2['w_post_p50_mean_ms']:.3f}/{t2['w_post_p95_mean_ms']:.3f}"
        r2_e = f"{l2['e2e_p50_mean']:.2f}/{l2['e2e_p95_mean']:.2f}"
        md_lines.append(f"| `{arm}` | {r1_rp} | {r2_rp} | {r1_wp} | {r2_wp} | {r1_e} | {r2_e} |")

    md_lines.extend([
        "",
        "## Per-Episode Paired CTE (ROS2 Phase-Aligned `final_test`)",
        "| Episode | r1 Nom | r2 Nom | r2 Oracle | r1 GP | r2 GP | r2 GP Match | r2 GP+PPO |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    r1_ep_nom = {r["episode_name"]: r for r in r1_doc["final_test_episodes"]["nominal_nmpc"]}
    r1_ep_gp = {r["episode_name"]: r for r in r1_doc["final_test_episodes"]["gp_nmpc"]}
    by_ep = {arm: {r["episode_name"]: r for r in runs} for arm, runs in runs_by_arm.items()}
    for ep in test_eps:
        en = ep["episode_name"]
        c_r1n = r1_ep_nom[en]["geometric_tracking"]["cross_track_rmse_m"]
        c_r2n = by_ep["nominal_nmpc"][en]["geometric_tracking"]["cross_track_rmse_m"]
        c_r2o = by_ep["oracle_nmpc"][en]["geometric_tracking"]["cross_track_rmse_m"]
        c_r1g = r1_ep_gp[en]["geometric_tracking"]["cross_track_rmse_m"]
        c_r2g = by_ep["gp_nmpc"][en]["geometric_tracking"]["cross_track_rmse_m"]
        c_r2gm = by_ep["gp_nmpc_matched"][en]["geometric_tracking"]["cross_track_rmse_m"] if en in by_ep["gp_nmpc_matched"] else None
        c_r2gp = by_ep["gp_ppo_nmpc"][en]["geometric_tracking"]["cross_track_rmse_m"]
        gm_str = f"{c_r2gm:.4f}" if c_r2gm is not None else "-"
        md_lines.append(f"| `{en}` | {c_r1n:.4f} | {c_r2n:.4f} | {c_r2o:.4f} | {c_r1g:.4f} | {c_r2g:.4f} | {gm_str} | {c_r2gp:.4f} |")

    md_path = out_dir / "gp_regression_diagnosis.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "json": str(json_path), "md": str(md_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
