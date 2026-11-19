#!/usr/bin/env python3
"""WP7 calibration, constraint-priority check, and paired 4-arm closed-loop evaluation."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from closed_loop_metrics import evaluate_closed_loop_run, sha256_file
from gp_model import MultiChannelSparseGP


WORKTREE = Path("/home/trevor/usv_scheme_a_wt")
INSTALL_ROOT = WORKTREE / "install/scheme_a/usv_research_safety_cpp/lib/usv_research_safety_cpp"
RUNNER = WORKTREE / "research/scheme_a/src/usv_research_safety_cpp/scripts/run_scheme_a_closed_loop.py"
CONTRACT = WORKTREE / "research/scheme_a/src/usv_research_safety_cpp/model/contract_controlled_sim.json"
PLAN = WORKTREE / "research/scheme_a/src/usv_research_safety_cpp/model/research_model_plan.json"
WORK_ROOT = Path("/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/scheme_A_gp_ppo_20261117_work")
SOURCE_HASHES = WORK_ROOT / "wp6_baseline_meta/source_hashes.json"
SPLIT_MANIFEST = WORK_ROOT / "full/split_manifest.json"
PLANT_DIR = WORK_ROOT / "full/plant_models"
GP_DIR = WORK_ROOT / "gp_models"
GP_POOLED = GP_DIR / "gp_snapshot.json"
PROFILE_TO_GP = {
    "mass_plus_10pct": GP_DIR / "mass_plus_10pct_sparse_m64.json",
    "surge_damping_plus_15pct": GP_DIR / "surge_damping_plus_15pct_sparse_m64.json",
    "yaw_damping_plus_15pct": GP_DIR / "yaw_damping_plus_15pct_sparse_m64.json",
}
PPO_MODEL = Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx")
PPO_MANIFEST = Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.manifest.json")
USV_RL_PYTHON = Path("/home/trevor/USV/usv_rl/.venv/bin/python")


_SHA_MEMO: dict[str, str] = {}


def _cached_sha256(path: Path) -> str:
    key = str(path)
    if key not in _SHA_MEMO:
        _SHA_MEMO[key] = sha256_file(path)
    return _SHA_MEMO[key]


def _strip_traj(metrics: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in metrics.items() if k not in ("u_exec", "states_end", "decision_ticks")}


def _run_episode(
    *,
    run_dir: Path,
    ep: dict[str, Any],
    stop_decisions: int,
    domain_queue: queue.Queue[int],
    gp_models: dict[str, MultiChannelSparseGP],
    gp_snapshot: Path | None = None,
    oracle_plant_file: Path | None = None,
    align_tick_phase: bool = False,
    source_hashes: Path = SOURCE_HASHES,
    ppo_proposal: bool = False,
    ppo_model: Path = PPO_MODEL,
    ppo_manifest: Path = PPO_MANIFEST,
    lambda_pi: float = 0.0,
    resume: bool = True,
    max_attempts: int = 4,
) -> dict[str, Any]:
    cache_path = run_dir / "eval_cache_v2.json"
    if resume and (run_dir / "run.json").is_file():
        run_doc = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        want_gp = str(gp_snapshot.resolve()) if gp_snapshot else None
        got_gp = run_doc.get("gp_snapshot")
        want_oracle = str(oracle_plant_file.resolve()) if oracle_plant_file else None
        got_oracle = run_doc.get("oracle_plant_file")
        want_align = bool(align_tick_phase)
        got_align = bool(run_doc.get("align_tick_phase", False))
        want_ppo = bool(ppo_proposal)
        got_ppo = bool((run_doc.get("ppo_proposal") or {}).get("enabled", False))
        got_lpi = float((run_doc.get("ppo_proposal") or {}).get("lambda_pi", 0.0))
        cfg_ok = (
            want_gp == got_gp
            and want_oracle == got_oracle
            and want_align == got_align
            and want_ppo == got_ppo
            and (not want_ppo or abs(got_lpi - float(lambda_pi)) < 1e-12)
        )
        src_sha = _cached_sha256(source_hashes)
        run_sha = sha256_file(run_dir / "run.json")
        gp_keys = sorted(gp_models.keys())
        if cfg_ok and cache_path.is_file() and (run_dir / "check.json").is_file():
            try:
                cdoc = json.loads(cache_path.read_text(encoding="utf-8"))
                if (
                    cdoc.get("source_hashes_sha256") == src_sha
                    and cdoc.get("run_json_sha256") == run_sha
                    and cdoc.get("gp_keys") == gp_keys
                    and isinstance(cdoc.get("metrics"), dict)
                    and cdoc["metrics"].get("checker_passed")
                    and cdoc["metrics"].get("decisions_total", 0) >= stop_decisions
                ):
                    m = dict(cdoc["metrics"])
                    m["reused"] = True
                    return m
            except Exception:
                pass
        if cfg_ok:
            m = evaluate_closed_loop_run(
                run_dir,
                source_hashes=source_hashes,
                gp_models_by_sha=gp_models,
                reuse_verified_check_json=True,
            )
            if m["checker_passed"] and m["decisions_total"] >= stop_decisions:
                try:
                    cache_path.write_text(
                        json.dumps({
                            "source_hashes_sha256": src_sha,
                            "run_json_sha256": run_sha,
                            "gp_keys": gp_keys,
                            "metrics": _strip_traj(m),
                        }, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                m["reused"] = True
                return m

    dom = domain_queue.get()
    try:
        last_err = ""
        contract_sha = sha256_file(CONTRACT)
        plan_sha = sha256_file(PLAN)
        for attempt in range(max_attempts):
            use_dom = dom if attempt == 0 else (dom + attempt * 10)
            if run_dir.exists():
                shutil.rmtree(run_dir)
            cmd = [
                "/usr/bin/python3",
                str(RUNNER),
                "--scenario", "pre_switch",
                "--out", str(run_dir),
                "--install-root", str(INSTALL_ROOT),
                "--contract", str(CONTRACT),
                "--contract-hash", contract_sha,
                "--plan", str(PLAN),
                "--plan-sha256", plan_sha,
                "--source-hashes", str(source_hashes),
                "--stop-after-decisions", str(stop_decisions),
                "--maneuver", str(ep["maneuver"]),
                "--maneuver-seed", str(ep["seed"]),
                "--plant-model-file", str(ep["plant_model_file"]),
                "--ros-domain-id", str(use_dom),
            ]
            if ep.get("cruise_speed") is not None:
                cmd.extend(["--cruise-speed", str(ep["cruise_speed"])])
            if oracle_plant_file is not None:
                cmd.extend(["--oracle-plant-file", str(oracle_plant_file)])
            if align_tick_phase:
                cmd.append("--align-tick-phase")
            if gp_snapshot is not None:
                cmd.extend(["--gp-snapshot", str(gp_snapshot), "--gp-snapshot-sha256", sha256_file(gp_snapshot)])
            if ppo_proposal:
                cmd.extend([
                    "--ppo-proposal",
                    "--ppo-model", str(ppo_model),
                    "--ppo-manifest", str(ppo_manifest),
                    "--lambda-pi", str(lambda_pi),
                ])
            env = dict(os.environ)
            env["ROS_DOMAIN_ID"] = str(use_dom)
            env.setdefault("OMP_NUM_THREADS", "1")
            env.setdefault("OPENBLAS_NUM_THREADS", "1")
            env.setdefault("ORT_INTRA_OP_NUM_THREADS", "1")
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                last_err = f"attempt={attempt+1} rc={proc.returncode} err={proc.stderr[-500:]}"
                continue
            m = evaluate_closed_loop_run(run_dir, source_hashes=source_hashes, gp_models_by_sha=gp_models)
            m["attempts"] = attempt + 1
            m["reused"] = False
            if m["checker_passed"]:
                try:
                    cache_path.write_text(
                        json.dumps({
                            "source_hashes_sha256": _cached_sha256(source_hashes),
                            "run_json_sha256": sha256_file(run_dir / "run.json"),
                            "gp_keys": sorted(gp_models.keys()),
                            "metrics": _strip_traj(m),
                        }, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                return m
            last_err = f"attempt={attempt+1} checker_problems={m['checker_problems']}"
        raise RuntimeError(f"Failed episode {ep['episode_name']} -> {run_dir}: {last_err}")
    finally:
        domain_queue.put(dom)


def _create_constant_ppo_onnx(probe_dir: Path, name: str, thrust_lr: tuple[float, float]) -> tuple[Path, Path]:
    """Build a valid constant-output test ONNX model + manifest using usv_rl venv."""
    probe_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = probe_dir / f"{name}.onnx"
    man_path = probe_dir / f"{name}.manifest.json"
    code = f"""
import numpy as np, onnx
from onnx import helper, TensorProto, numpy_helper
X = helper.make_tensor_value_info("obs", TensorProto.FLOAT, [1, 43])
Y = helper.make_tensor_value_info("thrust", TensorProto.FLOAT, [1, 2])
zero_w = numpy_helper.from_array(np.zeros((43, 2), dtype=np.float32), name="W")
bias = numpy_helper.from_array(np.array([{float(thrust_lr[0])}, {float(thrust_lr[1])}], dtype=np.float32), name="B")
mm = helper.make_node("MatMul", inputs=["obs", "W"], outputs=["zw"])
add = helper.make_node("Add", inputs=["zw", "B"], outputs=["thrust"])
graph = helper.make_graph([mm, add], "{name}", [X], [Y], initializer=[zero_w, bias])
model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
model.ir_version = 8
onnx.checker.check_model(model)
onnx.save(model, {str(onnx_path)!r})
"""
    proc = subprocess.run([str(USV_RL_PYTHON), "-c", code], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed building test ONNX {name}: {proc.stderr}")
    sha = sha256_file(onnx_path)
    manifest = {
        "contract_version": 1,
        "output_unit": "N",
        "action_order": ["T_L", "T_R"],
        "input_name": "obs",
        "input_dim": 43,
        "output_name": "thrust",
        "output_dim": 2,
        "thrust_scale_n": 25.0,
        "physical_low_n": [-25.0, -25.0],
        "physical_high_n": [25.0, 25.0],
        "normalization_embedded": True,
        "onnx_sha256": sha,
    }
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return onnx_path, man_path


def run_conflict_priority_probe(
    out_root: Path,
    domain_queue: queue.Queue[int],
    gp_models: dict[str, MultiChannelSparseGP],
    resume: bool,
    gp_snapshot: Path = GP_POOLED,
    source_hashes: Path = SOURCE_HASHES,
    align_tick_phase: bool = False,
) -> dict[str, Any]:
    """Verify NMPC enforces thrust bounds and slew limits when PPO requests extreme thrust."""
    probe_dir = out_root / "conflict_probe"
    ep = {
        "episode_name": "conflict_surge_right_turn",
        "maneuver": "right_turn",
        "seed": 3600,
        "cruise_speed": 0.8,
        "plant_model_file": str(PLANT_DIR / "surge_damping_plus_15pct.json"),
        "profile": "surge_damping_plus_15pct",
    }
    results: dict[str, Any] = {}
    for label, vals in (("max_forward", (25.0, 25.0)), ("max_reverse", (-25.0, -25.0))):
        onnx_p, man_p = _create_constant_ppo_onnx(probe_dir, label, vals)
        m = _run_episode(
            run_dir=probe_dir / label,
            ep=ep,
            stop_decisions=40,
            domain_queue=domain_queue,
            gp_models=gp_models,
            gp_snapshot=gp_snapshot,
            align_tick_phase=align_tick_phase,
            source_hashes=source_hashes,
            ppo_proposal=True,
            ppo_model=onnx_p,
            ppo_manifest=man_p,
            lambda_pi=0.5,
            resume=resume,
        )
        u_arr = np.asarray(m["u_exec"], dtype=np.float64)
        max_abs_u = float(np.max(np.abs(u_arr)))
        max_step_du = float(np.max(np.abs(np.diff(u_arr, axis=0)))) if len(u_arr) >= 2 else 0.0
        first_nonzero_idx = next((i for i in range(len(u_arr)) if np.max(np.abs(u_arr[i])) > 1e-6), None)
        first_step_from_zero = float(np.max(np.abs(u_arr[first_nonzero_idx]))) if first_nonzero_idx is not None else 0.0
        ok = (
            m["checker_passed"]
            and m["ppo_telemetry"]["used_ticks_count"] >= 30
            and max_abs_u <= 25.0 + 1e-6
            and max_step_du <= 16.0 + 1e-3
            and first_step_from_zero <= 16.0 + 1e-3
            and (m["ppo_telemetry"]["override_gt_0p5n_fraction"] or 0.0) > 0.5
        )
        assert ok, f"conflict probe {label} failed: max_u={max_abs_u}, max_du={max_step_du}, ppo={m['ppo_telemetry']}"
        results[label] = {
            "passed": ok,
            "requested_constant_q_pi": list(vals),
            "lambda_pi": 0.5,
            "max_abs_executed_thrust_n": max_abs_u,
            "max_consecutive_step_delta_n": max_step_du,
            "first_nonzero_step_from_zero_n": first_step_from_zero,
            "metrics": _strip_traj(m),
        }
    return results


def _aggregate_arm(runs: list[dict[str, Any]], nominal_runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    def _mean(vals: list[float]) -> float | None:
        clean = [float(v) for v in vals if v is not None and not math.isnan(float(v))]
        return float(np.mean(clean)) if clean else None

    def _std(vals: list[float]) -> float | None:
        clean = [float(v) for v in vals if v is not None and not math.isnan(float(v))]
        return float(np.std(clean)) if clean else None

    cte = [r["geometric_tracking"]["cross_track_rmse_m"] for r in runs]
    act_cte = [
        r["active_geometric_tracking"]["cross_track_rmse_m"]
        for r in runs
        if isinstance(r.get("active_geometric_tracking"), dict)
    ]
    cte_max = [r["geometric_tracking"]["cross_track_max_m"] for r in runs]
    herr = [r["geometric_tracking"]["heading_rmse_rad"] for r in runs]
    u_err = [r["geometric_tracking"]["speed_rmse_mps"] for r in runs]
    prog = [r["geometric_tracking"]["along_track_progress_m"] for r in runs]
    comp = [r["geometric_tracking"]["completion_ratio"] for r in runs]
    tv = [r["control_effort"]["tv_per_step"] for r in runs]
    eff = [r["control_effort"]["thrust_l2_dt"] for r in runs]
    zero_res = [r["residual_accuracy"]["zero_model_vel_rmse"] for r in runs]
    gp_res = [r["residual_accuracy"]["gp_model_vel_rmse"] for r in runs if r["residual_accuracy"]["gp_model_vel_rmse"] is not None]
    e2e_p50 = [r["latency_ms"]["freeze_to_publish_e2e"]["p50"] for r in runs if r["latency_ms"]["freeze_to_publish_e2e"]["p50"] is not None]
    e2e_p95 = [r["latency_ms"]["freeze_to_publish_e2e"]["p95"] for r in runs if r["latency_ms"]["freeze_to_publish_e2e"]["p95"] is not None]
    e2e_p99 = [r["latency_ms"]["freeze_to_publish_e2e"]["p99"] for r in runs if r["latency_ms"]["freeze_to_publish_e2e"]["p99"] is not None]
    e2e_max = [r["latency_ms"]["freeze_to_publish_e2e"]["max"] for r in runs if r["latency_ms"]["freeze_to_publish_e2e"]["max"] is not None]
    solve_mean = [r["latency_ms"]["solver_backend"]["mean"] for r in runs if r["latency_ms"]["solver_backend"]["mean"] is not None]
    solve_max = [r["latency_ms"]["solver_backend"]["max"] for r in runs if r["latency_ms"]["solver_backend"]["max"] is not None]
    d150 = sum(int(r["latency_ms"]["deadline_150ms_misses"]) for r in runs)
    d200 = sum(int(r["latency_ms"]["deadline_200ms_misses"]) for r in runs)
    ppo_used = sum(int(r["ppo_telemetry"]["used_ticks_count"]) for r in runs)
    ppo_mod_mean = [r["ppo_telemetry"]["nmpc_override_norm"]["mean"] for r in runs if r["ppo_telemetry"]["nmpc_override_norm"]["mean"] is not None]
    ppo_ovr_frac = [r["ppo_telemetry"]["override_gt_0p5n_fraction"] for r in runs if r["ppo_telemetry"]["override_gt_0p5n_fraction"] is not None]

    out: dict[str, Any] = {
        "episodes": len(runs),
        "checker_pass_count": sum(1 for r in runs if r["checker_passed"]),
        "success_count": sum(1 for r in runs if r["success"]),
        "success_rate": float(np.mean([1.0 if r["success"] else 0.0 for r in runs])),
        "skipped_ticks_total": sum(int(r["skipped_ticks_total"]) for r in runs),
        "cross_track_rmse_m": {"mean": _mean(cte), "std": _std(cte)},
        "active_cross_track_rmse_m": {"mean": _mean(act_cte), "std": _std(act_cte)},
        "cross_track_max_m": {"mean": _mean(cte_max), "max": float(np.max(cte_max)) if cte_max else None},
        "heading_rmse_rad": {"mean": _mean(herr), "std": _std(herr)},
        "speed_rmse_mps": {"mean": _mean(u_err), "std": _std(u_err)},
        "along_track_progress_m": {"mean": _mean(prog)},
        "completion_ratio": {"mean": _mean(comp)},
        "control_tv_per_step": {"mean": _mean(tv), "std": _std(tv)},
        "thrust_l2_dt": {"mean": _mean(eff)},
        "zero_model_vel_rmse": {"mean": _mean(zero_res)},
        "gp_model_vel_rmse": {"mean": _mean(gp_res)},
        "ppo_used_ticks_total": ppo_used,
        "ppo_nmpc_override_norm_mean": _mean(ppo_mod_mean),
        "ppo_override_gt_0p5n_fraction": _mean(ppo_ovr_frac),
        "latency_ms": {
            "solver_backend_mean": _mean(solve_mean),
            "solver_backend_max": float(np.max(solve_max)) if solve_max else None,
            "e2e_p50_mean": _mean(e2e_p50),
            "e2e_p95_mean": _mean(e2e_p95),
            "e2e_p99_max": float(np.max(e2e_p99)) if e2e_p99 else None,
            "e2e_max": float(np.max(e2e_max)) if e2e_max else None,
            "deadline_150ms_misses": d150,
            "deadline_200ms_misses": d200,
        },
    }
    if nominal_runs is not None and len(nominal_runs) == len(runs):
        deltas = [
            r["geometric_tracking"]["cross_track_rmse_m"] - nr["geometric_tracking"]["cross_track_rmse_m"]
            for r, nr in zip(runs, nominal_runs)
        ]
        wins = sum(1 for d in deltas if d < -1e-4)
        losses = sum(1 for d in deltas if d > 1e-4)
        ties = len(deltas) - wins - losses
        out["vs_nominal"] = {
            "cte_rmse_delta_mean_m": float(np.mean(deltas)),
            "cte_wins": wins,
            "cte_ties": ties,
            "cte_losses": losses,
        }
        if len(act_cte) == len(runs) and all(isinstance(nr.get("active_geometric_tracking"), dict) for nr in nominal_runs):
            act_deltas = [
                r["active_geometric_tracking"]["cross_track_rmse_m"]
                - nr["active_geometric_tracking"]["cross_track_rmse_m"]
                for r, nr in zip(runs, nominal_runs)
            ]
            out["vs_nominal"]["active_cte_delta_mean_m"] = float(np.mean(act_deltas))
    return out


def _calibration_score(agg: dict[str, Any]) -> float:
    return (
        float(agg["cross_track_rmse_m"]["mean"] or 99.0)
        + 0.1 * float(agg["heading_rmse_rad"]["mean"] or 99.0)
        + 0.05 * float(agg["speed_rmse_mps"]["mean"] or 99.0)
        + 0.005 * float(agg["control_tv_per_step"]["mean"] or 99.0)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(WORK_ROOT / "fusion_eval"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--base-domain-id", type=int, default=30)
    parser.add_argument("--calib-decisions", type=int, default=151)
    parser.add_argument("--test-decisions", type=int, default=301)
    parser.add_argument("--lambdas", default="0.0,0.005,0.015,0.04,0.10")
    parser.add_argument("--stage", choices=("all", "conflict", "calib", "test"), default="all")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    resume = not args.no_resume
    lambdas = [float(x.strip()) for x in args.lambdas.split(",") if x.strip()]

    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    calib_eps = [e for e in manifest["episodes"] if e["split"] == "calibration"]
    test_eps = [e for e in manifest["episodes"] if e["split"] == "final_test"]

    gp_models: dict[str, MultiChannelSparseGP] = {}
    for p in (GP_POOLED, *PROFILE_TO_GP.values()):
        m = MultiChannelSparseGP.load(p)
        gp_models[m.snapshot_sha256] = m

    domain_q: queue.Queue[int] = queue.Queue()
    for i in range(max(1, args.workers)):
        domain_q.put(int(args.base_domain_id) + i)

    conflict_summary_path = out_root / "conflict_probe_summary.json"
    if args.stage in ("all", "conflict"):
        print("[WP7] Running constraint-priority conflict probe...", flush=True)
        conflict_res = run_conflict_priority_probe(out_root, domain_q, gp_models, resume=resume)
        conflict_summary_path.write_text(
            json.dumps(conflict_res, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[WP7] Conflict probe passed: {list(conflict_res.keys())}", flush=True)
        if args.stage == "conflict":
            return 0
    else:
        conflict_res = json.loads(conflict_summary_path.read_text(encoding="utf-8"))

    calib_summary_path = out_root / "calibration_summary.json"
    selected_cfg_path = out_root / "selected_configuration.json"
    if args.stage in ("all", "calib"):
        print(f"[WP7] Calibrating lambda_pi in {lambdas} across {len(calib_eps)} calibration episodes ({args.calib_decisions} ticks, workers={args.workers})...", flush=True)
        calib_runs: dict[str, list[dict[str, Any]]] = {str(l): [] for l in lambdas}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = []
            for lval in lambdas:
                ltag = f"lambda_{lval:.4f}".replace(".", "p")
                for ep in calib_eps:
                    ep_dir = out_root / "calibration" / ltag / ep["episode_name"]
                    fut = pool.submit(
                        _run_episode,
                        run_dir=ep_dir,
                        ep=ep,
                        stop_decisions=int(args.calib_decisions),
                        domain_queue=domain_q,
                        gp_models=gp_models,
                        gp_snapshot=GP_POOLED,
                        ppo_proposal=(lval > 0.0),
                        lambda_pi=lval,
                        resume=resume,
                    )
                    futures.append((str(lval), ep["episode_name"], fut))
            total_c = len(futures)
            for idx, (lkey, ename, fut) in enumerate(futures, 1):
                m = fut.result()
                calib_runs[lkey].append(_strip_traj(m))
                print(f"[WP7 calib {idx}/{total_c}] lambda={lkey} ep={ename} cte={m['geometric_tracking']['cross_track_rmse_m']:.4f} reused={m.get('reused')}", flush=True)

        calib_summary: dict[str, Any] = {}
        for lval in lambdas:
            runs = sorted(calib_runs[str(lval)], key=lambda r: Path(r["run_dir"]).name)
            agg = _aggregate_arm(runs, nominal_runs=sorted(calib_runs[str(lambdas[0])], key=lambda r: Path(r["run_dir"]).name) if lval != lambdas[0] else None)
            agg["calibration_score"] = _calibration_score(agg)
            calib_summary[str(lval)] = {"lambda_pi": lval, "aggregate": agg, "episodes": runs}

        valid_positive = [
            (lval, calib_summary[str(lval)]["aggregate"])
            for lval in lambdas
            if lval > 0.0
            and calib_summary[str(lval)]["aggregate"]["checker_pass_count"] == len(calib_eps)
            and calib_summary[str(lval)]["aggregate"]["success_count"] == len(calib_eps)
            and calib_summary[str(lval)]["aggregate"]["latency_ms"]["deadline_200ms_misses"] == 0
        ]
        if not valid_positive:
            raise RuntimeError("No positive lambda_pi passed all calibration safety & deadline gates")
        best_pos_lambda, _ = min(valid_positive, key=lambda kv: kv[1]["calibration_score"])
        overall_best_lambda, _ = min(
            ((l, calib_summary[str(l)]["aggregate"]) for l in lambdas),
            key=lambda kv: kv[1]["calibration_score"],
        )

        selected_cfg = {
            "schema": "scheme-a-wp7-selected-config-v1",
            "gp_snapshot_pooled": str(GP_POOLED),
            "gp_snapshot_pooled_sha256": sha256_file(GP_POOLED),
            "gp_snapshots_per_profile": {k: {"path": str(v), "sha256": sha256_file(v)} for k, v in PROFILE_TO_GP.items()},
            "ppo_model_onnx": str(PPO_MODEL),
            "ppo_model_manifest": str(PPO_MANIFEST),
            "ppo_model_sha256": json.loads(PPO_MANIFEST.read_text(encoding="utf-8"))["onnx_sha256"],
            "calibration_candidates": lambdas,
            "calibration_decisions_per_episode": int(args.calib_decisions),
            "selected_positive_lambda_pi": float(best_pos_lambda),
            "calibration_overall_best_lambda_pi": float(overall_best_lambda),
            "selection_metric": "cross_track_rmse_mean + 0.1*heading_rmse_mean + 0.05*speed_rmse_mean + 0.005*tv_per_step_mean",
        }
        calib_summary_path.write_text(
            json.dumps(calib_summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        selected_cfg_path.write_text(
            json.dumps(selected_cfg, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[WP7] Calibration done: overall={overall_best_lambda}, selected_positive={best_pos_lambda}", flush=True)
        if args.stage == "calib":
            return 0
    else:
        calib_summary = json.loads(calib_summary_path.read_text(encoding="utf-8"))
        selected_cfg = json.loads(selected_cfg_path.read_text(encoding="utf-8"))
        lambdas = [float(x) for x in selected_cfg["calibration_candidates"]]
        best_pos_lambda = float(selected_cfg["selected_positive_lambda_pi"])
        overall_best_lambda = float(selected_cfg["calibration_overall_best_lambda_pi"])

    active_lambda = float(best_pos_lambda)
    print(f"[WP7] Running 4-arm paired final_test ({len(test_eps)} episodes x {args.test_decisions} ticks, lambda_pi={active_lambda})...", flush=True)

    arm_specs = {
        "nominal_nmpc": {"gp": None, "ppo": False, "lambda_pi": 0.0},
        "gp_nmpc": {"gp": GP_POOLED, "ppo": False, "lambda_pi": 0.0},
        "ppo_guided_nmpc": {"gp": None, "ppo": True, "lambda_pi": active_lambda},
        "gp_ppo_nmpc": {"gp": GP_POOLED, "ppo": True, "lambda_pi": active_lambda},
    }
    test_results: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arm_specs}
    specialist_runs: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = []
        for arm_name, spec in arm_specs.items():
            for ep in test_eps:
                ep_dir = out_root / "final_test" / arm_name / ep["episode_name"]
                fut = pool.submit(
                    _run_episode,
                    run_dir=ep_dir,
                    ep=ep,
                    stop_decisions=int(args.test_decisions),
                    domain_queue=domain_q,
                    gp_models=gp_models,
                    gp_snapshot=spec["gp"],
                    ppo_proposal=spec["ppo"],
                    lambda_pi=spec["lambda_pi"],
                    resume=resume,
                )
                futs.append((arm_name, ep["episode_name"], fut))
        for ep in test_eps:
            prof = str(ep.get("profile") or "")
            if prof in PROFILE_TO_GP:
                ep_dir = out_root / "final_test" / "gp_nmpc_matched" / ep["episode_name"]
                fut = pool.submit(
                    _run_episode,
                    run_dir=ep_dir,
                    ep=ep,
                    stop_decisions=int(args.test_decisions),
                    domain_queue=domain_q,
                    gp_models=gp_models,
                    gp_snapshot=PROFILE_TO_GP[prof],
                    ppo_proposal=False,
                    lambda_pi=0.0,
                    resume=resume,
                )
                futs.append(("gp_nmpc_matched", ep["episode_name"], fut))

        total_t = len(futs)
        for idx, (arm_name, ename, fut) in enumerate(futs, 1):
            m = _strip_traj(fut.result())
            m["episode_name"] = ename
            if arm_name == "gp_nmpc_matched":
                specialist_runs.append(m)
            else:
                test_results[arm_name].append(m)
            print(f"[WP7 test {idx}/{total_t}] arm={arm_name} ep={ename} cte={m['geometric_tracking']['cross_track_rmse_m']:.4f} reused={m.get('reused')}", flush=True)

    for arm in test_results:
        test_results[arm].sort(key=lambda r: r["episode_name"])
    specialist_runs.sort(key=lambda r: r["episode_name"])

    nom_all = test_results["nominal_nmpc"]
    aggregates = {
        arm: _aggregate_arm(runs, nominal_runs=nom_all if arm != "nominal_nmpc" else None)
        for arm, runs in test_results.items()
    }
    heldout_names = {e["episode_name"] for e in test_eps if e["profile"] == "heldout_combination"}
    single_names = {e["episode_name"] for e in test_eps if e["profile"] != "heldout_combination"}

    aggregates_heldout = {
        arm: _aggregate_arm(
            [r for r in runs if r["episode_name"] in heldout_names],
            nominal_runs=[r for r in nom_all if r["episode_name"] in heldout_names] if arm != "nominal_nmpc" else None,
        )
        for arm, runs in test_results.items()
    }
    nom_single = [r for r in nom_all if r["episode_name"] in single_names]
    specialist_agg = _aggregate_arm(specialist_runs, nominal_runs=nom_single)

    eval_doc = {
        "schema": "scheme-a-wp7-four-arm-evaluation-v1",
        "selected_configuration": selected_cfg,
        "conflict_priority_probe": conflict_res,
        "calibration_summary": {k: v["aggregate"] for k, v in calib_summary.items()},
        "final_test_aggregates_all12": aggregates,
        "final_test_aggregates_heldout6": aggregates_heldout,
        "final_test_gp_nmpc_matched_single6": specialist_agg,
        "final_test_episodes": test_results,
        "final_test_matched_single_episodes": specialist_runs,
    }
    eval_path = out_root / "four_arm_evaluation.json"
    eval_path.write_text(json.dumps(eval_doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # Emit concise human-readable markdown report directly from eval_doc.
    lines = [
        "# Scheme A WP7 Four-Arm GP+PPO Fusion Evaluation Report",
        "",
        "## 1. Selected Configuration & Constraint-Priority Probe",
        f"- Pooled GP snapshot: `{GP_POOLED.name}` (`{selected_cfg['gp_snapshot_pooled_sha256']}`)",
        f"- Frozen PPO policy: `{PPO_MODEL}` (`{selected_cfg['ppo_model_sha256']}`)",
        f"- Calibration `lambda_pi` sweep ({args.calib_decisions} ticks x {len(calib_eps)} episodes): `{lambdas}`",
        f"- Selected positive `lambda_pi`: `{active_lambda}` (overall lowest-score on calibration: `{overall_best_lambda}`)",
        "",
        "| Constraint Probe | Requested q_pi | Passed | Max |u| (N) | Max Step |Δu| (N) | First Step (N) | Override Fraction |",
        "|---|---:|:---:|---:|---:|---:|---:|",
    ]
    for pname, pres in conflict_res.items():
        lines.append(
            f"| `{pname}` | `{pres['requested_constant_q_pi']}` | {pres['passed']} | "
            f"{pres['max_abs_executed_thrust_n']:.3f} | {pres['max_consecutive_step_delta_n']:.3f} | "
            f"{pres['first_nonzero_step_from_zero_n']:.3f} | "
            f"{pres['metrics']['ppo_telemetry']['override_gt_0p5n_fraction']:.3f} |"
        )

    lines.extend([
        "",
        "## 2. Calibration Split (`lambda_pi` Sweep, Pooled GP)",
        "| lambda_pi | Pass/Success | CTE RMSE (m) | Heading RMSE (rad) | Speed RMSE (m/s) | TV/step (N) | E2E P95 (ms) | Deadlines >200ms | Score |",
        "|---:|:---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for lval in lambdas:
        a = calib_summary[str(lval)]["aggregate"]
        lines.append(
            f"| {lval:.3f} | {a['checker_pass_count']}/{a['episodes']} ({a['success_count']}) | "
            f"{a['cross_track_rmse_m']['mean']:.4f} | {a['heading_rmse_rad']['mean']:.4f} | "
            f"{a['speed_rmse_mps']['mean']:.4f} | {a['control_tv_per_step']['mean']:.3f} | "
            f"{a['latency_ms']['e2e_p95_mean']:.3f} | {a['latency_ms']['deadline_200ms_misses']} | "
            f"{a['calibration_score']:.4f} |"
        )

    lines.extend([
        "",
        f"## 3. Held-Out `final_test` Split (12 Episodes x {args.test_decisions} Ticks)",
        "| Arm | Pass/Succ | CTE RMSE (m) | ΔCTE vs Nom | Wins/Ties/Loss | Heading RMSE | Speed RMSE | TV/step | Vel Res RMSE | E2E P95 / Max (ms) | >200ms |",
        "|---|:---:|---:|---:|:---:|---:|---:|---:|---:|---:|---:|",
    ])
    for arm in ("nominal_nmpc", "gp_nmpc", "ppo_guided_nmpc", "gp_ppo_nmpc"):
        a = aggregates[arm]
        vs = a.get("vs_nominal")
        d_str = f"{vs['cte_rmse_delta_mean_m']:+.4f}" if vs else "0.0000"
        wtl = f"{vs['cte_wins']}/{vs['cte_ties']}/{vs['cte_losses']}" if vs else "-"
        res_v = a["gp_model_vel_rmse"]["mean"] if a["gp_model_vel_rmse"]["mean"] is not None else a["zero_model_vel_rmse"]["mean"]
        lines.append(
            f"| `{arm}` | {a['checker_pass_count']}/{a['episodes']} ({a['success_count']}) | "
            f"{a['cross_track_rmse_m']['mean']:.4f} | {d_str} | {wtl} | "
            f"{a['heading_rmse_rad']['mean']:.4f} | {a['speed_rmse_mps']['mean']:.4f} | "
            f"{a['control_tv_per_step']['mean']:.3f} | {res_v:.5f} | "
            f"{a['latency_ms']['e2e_p95_mean']:.3f} / {a['latency_ms']['e2e_max']:.3f} | "
            f"{a['latency_ms']['deadline_200ms_misses']} |"
        )

    lines.extend([
        "",
        "## 4. Subgroup Breakdown (`heldout_combination` 6 eps vs Matched Single-Plant GP 6 eps)",
        f"- Unseen `heldout_combination` (6 eps): nominal CTE={aggregates_heldout['nominal_nmpc']['cross_track_rmse_m']['mean']:.4f}m, "
        f"gp_nmpc={aggregates_heldout['gp_nmpc']['cross_track_rmse_m']['mean']:.4f}m, "
        f"ppo_guided={aggregates_heldout['ppo_guided_nmpc']['cross_track_rmse_m']['mean']:.4f}m, "
        f"gp_ppo={aggregates_heldout['gp_ppo_nmpc']['cross_track_rmse_m']['mean']:.4f}m "
        f"(GP vel RMSE={aggregates_heldout['gp_nmpc']['gp_model_vel_rmse']['mean']:.5f} vs nominal={aggregates_heldout['nominal_nmpc']['zero_model_vel_rmse']['mean']:.5f}).",
        f"- Known-profile single-plant specialist GP (6 eps): nominal CTE={_aggregate_arm(nom_single)['cross_track_rmse_m']['mean']:.4f}m vs matched GP CTE={specialist_agg['cross_track_rmse_m']['mean']:.4f}m, "
        f"GP vel RMSE={specialist_agg['gp_model_vel_rmse']['mean']:.5f} vs nominal={_aggregate_arm(nom_single)['zero_model_vel_rmse']['mean']:.5f}.",
        "",
        "## 5. Per-Episode Paired Comparison (`final_test`)",
        "| Episode | Nom CTE | GP CTE | PPO CTE | GP+PPO CTE | Nom Res | GP Res | GP+PPO MaxE2E (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    by_arm_ep = {arm: {r["episode_name"]: r for r in runs} for arm, runs in test_results.items()}
    for ep in test_eps:
        en = ep["episode_name"]
        r0 = by_arm_ep["nominal_nmpc"][en]
        r1 = by_arm_ep["gp_nmpc"][en]
        r2 = by_arm_ep["ppo_guided_nmpc"][en]
        r3 = by_arm_ep["gp_ppo_nmpc"][en]
        lines.append(
            f"| `{en}` | {r0['geometric_tracking']['cross_track_rmse_m']:.4f} | "
            f"{r1['geometric_tracking']['cross_track_rmse_m']:.4f} | "
            f"{r2['geometric_tracking']['cross_track_rmse_m']:.4f} | "
            f"{r3['geometric_tracking']['cross_track_rmse_m']:.4f} | "
            f"{r0['residual_accuracy']['zero_model_vel_rmse']:.5f} | "
            f"{r1['residual_accuracy']['gp_model_vel_rmse']:.5f} | "
            f"{r3['latency_ms']['freeze_to_publish_e2e']['max']:.3f} |"
        )

    report_path = out_root / "fusion_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "eval_json": str(eval_path),
        "report_md": str(report_path),
        "selected_config": str(out_root / "selected_configuration.json"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
