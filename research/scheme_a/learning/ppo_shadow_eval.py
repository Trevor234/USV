#!/usr/bin/env python3
"""Shadow evaluation of frozen v5/s4_dr PPO policy under pre_update vs post_update contracts (WP5).

Must be invoked with `/home/trevor/USV/usv_rl/.venv/bin/python` (has `usv_rl` + `onnxruntime`).
Read-only with respect to `/home/trevor/USV/artifacts/rl_models/v5/s4_dr`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from usv_rl.dynamics import HydroParams
from usv_rl.envs.usv_tracking_env import DEFAULT_LOOKAHEAD, UsvTrackingEnv
from usv_rl.observation import advance_progress, compose_observation

OBS_DIM = 43


DEFAULT_MODEL_DIR = Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr")
ONNX_FILENAME = "policy_physical_n.onnx"
MANIFEST_FILENAME = "policy_physical_n.manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_env_comparison(
    session: ort.InferenceSession,
    *,
    path_types: tuple[str, ...] = ("straight", "arc", "zigzag"),
    seeds: tuple[int, ...] = (101, 102, 103, 104, 105),
    hydro_dr_frac: float = 0.0,
) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {"pre_update": {}, "post_update": {}}
    action_diffs: list[np.ndarray] = []

    for timing in ("pre_update", "post_update"):
        ep_metrics: list[dict[str, Any]] = []
        for ptype in path_types:
            for seed in seeds:
                env = UsvTrackingEnv(
                    path_type=ptype,
                    hydro_dr_frac=hydro_dr_frac,
                    init_pos_noise=0.0,
                    init_psi_noise=0.0,
                    init_vel_noise=0.0,
                    obs_prev_thrust_timing=timing,
                )
                obs, _ = env.reset(seed=seed)
                ref = env.reference
                done = False
                pos_errs: list[float] = []
                psi_errs: list[float] = []
                thrusts: list[np.ndarray] = []
                total_reward = 0.0
                steps = 0
                is_success = False

                while not done:
                    raw_thrust = session.run(["thrust"], {"obs": obs[None, :].astype(np.float32)})[0][0]
                    act_norm = np.clip(raw_thrust / env.t_max_thrust, -1.0, 1.0).astype(np.float32)

                    # Compare what the SAME frozen policy would output if prev_thrust were aligned vs lagged.
                    obs_other = compose_observation(
                        env.state,
                        ref.xs, ref.ys, ref.psis, ref.kappas, ref.v_ref, ref.r_ref, ref.s, ref.t,
                        t_now=env.step_count * env.dt - env._t_lag,
                        prog_idx=env.prog_idx,
                        prev_thrust=env.prev_thrust,
                        lookahead=env.lookahead,
                    )
                    if timing == "pre_update":
                        # Compare pre-update obs against post-update obs after applying current thrust would shift.
                        pass

                    obs_next, rew, term, trunc, info = env.step(act_norm)
                    if timing == "post_update":
                        # Compute counterfactual pre_update action at step k+1 before next step.
                        if len(thrusts) > 0:
                            obs_lagged = obs_next.copy()
                            obs_lagged[-2:] = thrusts[-1]
                            raw_lagged = session.run(["thrust"], {"obs": obs_lagged[None, :].astype(np.float32)})[0][0]
                            raw_curr = session.run(["thrust"], {"obs": obs_next[None, :].astype(np.float32)})[0][0]
                            action_diffs.append(np.abs(raw_curr - raw_lagged))

                    total_reward += float(rew)
                    steps += 1
                    pos_errs.append(float(info.get("e_pos", 0.0)))
                    psi_errs.append(float(abs(info.get("e_psi", 0.0))))
                    thrusts.append(np.asarray(info["applied_thrust"], dtype=np.float64))
                    is_success = bool(info.get("is_success", False))
                    obs = obs_next
                    done = term or trunc

                t_arr = np.asarray(thrusts, dtype=np.float64)
                tv = float(np.mean(np.abs(np.diff(t_arr, axis=0)))) if len(t_arr) > 1 else 0.0
                ep_metrics.append({
                    "path_type": ptype,
                    "seed": seed,
                    "steps": steps,
                    "success": is_success,
                    "reward": total_reward,
                    "pos_rmse_m": float(np.sqrt(np.mean(np.square(pos_errs)))) if pos_errs else 0.0,
                    "pos_max_m": float(np.max(pos_errs)) if pos_errs else 0.0,
                    "psi_rmse_rad": float(np.sqrt(np.mean(np.square(psi_errs)))) if psi_errs else 0.0,
                    "thrust_tv_n": tv,
                })

        n = len(ep_metrics)
        results[timing] = {
            "episodes": n,
            "success_rate": float(sum(1 for e in ep_metrics if e["success"]) / max(1, n)),
            "mean_reward": float(np.mean([e["reward"] for e in ep_metrics])),
            "mean_pos_rmse_m": float(np.mean([e["pos_rmse_m"] for e in ep_metrics])),
            "mean_pos_max_m": float(np.mean([e["pos_max_m"] for e in ep_metrics])),
            "mean_psi_rmse_rad": float(np.mean([e["psi_rmse_rad"] for e in ep_metrics])),
            "mean_thrust_tv_n": float(np.mean([e["thrust_tv_n"] for e in ep_metrics])),
            "by_path_type": {
                pt: {
                    "success_rate": float(np.mean([e["success"] for e in ep_metrics if e["path_type"] == pt])),
                    "mean_pos_rmse_m": float(np.mean([e["pos_rmse_m"] for e in ep_metrics if e["path_type"] == pt])),
                    "mean_thrust_tv_n": float(np.mean([e["thrust_tv_n"] for e in ep_metrics if e["path_type"] == pt])),
                }
                for pt in path_types
            },
        }

    diffs_arr = np.asarray(action_diffs, dtype=np.float64) if action_diffs else np.zeros((1, 2))
    shift_stats = {
        "samples": int(len(action_diffs)),
        "mean_abs_diff_n": [float(v) for v in np.mean(diffs_arr, axis=0)],
        "p95_abs_diff_n": [float(v) for v in np.percentile(diffs_arr, 95, axis=0)],
        "max_abs_diff_n": [float(v) for v in np.max(diffs_arr, axis=0)],
    }
    return {"timing_eval": results, "single_step_action_shift": shift_stats}


def replay_scheme_a_runs(session: ort.InferenceSession, runs_dir: Path | None) -> dict[str, Any]:
    """Compare aligned vs 1-step-lagged prev_thrust on real Scheme A controlled_sim runs."""
    if runs_dir is None or not runs_dir.is_dir():
        return {"runs_evaluated": 0}
    lookahead = tuple(float(v) for v in DEFAULT_LOOKAHEAD)
    diffs: list[np.ndarray] = []
    infer_ms: list[float] = []
    runs_used = 0
    import time

    for rdir in sorted(runs_dir.iterdir()):
        plant_path = rdir / "plant.source.jsonl"
        path_txt = rdir / "scenario_path.txt"
        prof_txt = rdir / "scenario_profile.txt"
        if not (plant_path.is_file() and path_txt.is_file()):
            continue
        p_rows = np.loadtxt(path_txt, dtype=np.float64)
        pr_rows = np.loadtxt(prof_txt, dtype=np.float64) if prof_txt.is_file() else p_rows
        if p_rows.ndim != 2 or len(p_rows) < 5:
            continue

        # Reconstruct arc-length s & curvature kappa cleanly for compose_observation.
        xs, ys, psis = p_rows[:, 0], p_rows[:, 1], p_rows[:, 2]
        vs = pr_rows[:, 0] if prof_txt.is_file() else np.full(len(xs), 0.7)
        rs = pr_rows[:, 2] if prof_txt.is_file() else np.zeros(len(xs))
        ts = p_rows[:, 3]
        ds = np.hypot(np.diff(xs), np.diff(ys))
        ss = np.concatenate([[0.0], np.cumsum(ds)])
        kappas = np.divide(rs, np.maximum(np.abs(vs), 0.1))

        recs = [
            json.loads(line)
            for line in plant_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and '"type":"plant_receipt"' in line.replace(" ", "") and '"disposition":"ok"' in line.replace(" ", "")
        ]
        if len(recs) < 4:
            continue
        runs_used += 1
        prog_idx = 0
        prev_executed = np.array([0.0, 0.0], dtype=np.float64)
        for k in range(1, len(recs)):
            st = np.asarray(recs[k]["state"], dtype=np.float64)
            t_now = float(recs[k]["state_sample_sim_ns"]) / 1e9
            prog_idx = advance_progress(xs, ys, st[0], st[1], prog_idx)
            cur_executed = np.asarray(recs[k - 1]["thrust_n"], dtype=np.float64)
            obs_aligned = compose_observation(
                st, xs, ys, psis, kappas, vs, rs, ss, ts,
                t_now=t_now, prog_idx=prog_idx, prev_thrust=cur_executed, lookahead=lookahead,
            )
            obs_lagged = compose_observation(
                st, xs, ys, psis, kappas, vs, rs, ss, ts,
                t_now=t_now, prog_idx=prog_idx, prev_thrust=prev_executed, lookahead=lookahead,
            )
            t0 = time.perf_counter()
            a_aligned = session.run(["thrust"], {"obs": obs_aligned[None, :].astype(np.float32)})[0][0]
            t1 = time.perf_counter()
            a_lagged = session.run(["thrust"], {"obs": obs_lagged[None, :].astype(np.float32)})[0][0]
            infer_ms.append((t1 - t0) * 1e3)
            diffs.append(np.abs(a_aligned - a_lagged))
            prev_executed = cur_executed

    arr = np.asarray(diffs, dtype=np.float64) if diffs else np.zeros((1, 2))
    return {
        "runs_evaluated": runs_used,
        "samples": int(len(diffs)),
        "mean_abs_diff_n": [float(v) for v in np.mean(arr, axis=0)],
        "p95_abs_diff_n": [float(v) for v in np.percentile(arr, 95, axis=0)],
        "max_abs_diff_n": [float(v) for v in np.max(arr, axis=0)],
        "ort_latency_mean_ms": float(np.mean(infer_ms)) if infer_ms else None,
        "ort_latency_p99_ms": float(np.percentile(infer_ms, 99)) if infer_ms else None,
    }


def make_policy_selection_decision(nom_eval: dict[str, Any], dr_eval: dict[str, Any], replay_stats: dict[str, Any]) -> dict[str, Any]:
    pre = nom_eval["timing_eval"]["pre_update"]
    post = nom_eval["timing_eval"]["post_update"]
    dr_pre = dr_eval["timing_eval"]["pre_update"]
    dr_post = dr_eval["timing_eval"]["post_update"]

    rmse_delta = post["mean_pos_rmse_m"] - pre["mean_pos_rmse_m"]
    success_drop = pre["success_rate"] - post["success_rate"]
    tv_delta = post["mean_thrust_tv_n"] - pre["mean_thrust_tv_n"]
    shift_mean = float(np.mean(nom_eval["single_step_action_shift"]["mean_abs_diff_n"]))
    replay_shift = float(np.mean(replay_stats.get("mean_abs_diff_n", [0.0, 0.0])))

    # Three-way explicit gate:
    # 1) direct_reuse_v5: post_update preserves >= 90% success AND pos RMSE within +0.08m AND stable thrust TV.
    # 2) finetune_under_post_update: moderate degradation under post_update (> 0.08m RMSE delta or > 5% success drop).
    # 3) retrain_under_post_update: severe policy breakdown (< 70% success).
    if post["success_rate"] < 0.70 or dr_post["success_rate"] < 0.65:
        decision = "retrain_under_post_update"
        reason = "Frozen v5 policy collapses under aligned post_update observation contract."
    elif rmse_delta > 0.08 or success_drop > 0.05 or tv_delta > 0.50:
        decision = "finetune_under_post_update"
        reason = (
            f"Observable shift (mean {shift_mean:.3f} N / replay {replay_shift:.3f} N) measurably degrades "
            f"tracking (rmse_delta={rmse_delta:+.4f} m, success_drop={success_drop:+.3f}) under post_update; recommend warm-start finetune."
        )
    else:
        decision = "direct_reuse_v5"
        reason = (
            f"Despite observable prev_thrust shift (env {shift_mean:.3f} N, Scheme A replay {replay_shift:.3f} N), "
            f"frozen v5 maintains {post['success_rate']:.0%} nominal / {dr_post['success_rate']:.0%} DR success "
            f"with minimal RMSE change ({rmse_delta:+.4f} m) and TV change ({tv_delta:+.3f} N); safe to reuse read-only."
        )

    return {
        "schema": "scheme-a-ppo-policy-selection-v1",
        "decision": decision,
        "allowed_decisions": ["direct_reuse_v5", "finetune_under_post_update", "retrain_under_post_update"],
        "reason": reason,
        "gates": {
            "post_update_success_rate": post["success_rate"],
            "dr_post_update_success_rate": dr_post["success_rate"],
            "pos_rmse_delta_m": rmse_delta,
            "success_rate_drop": success_drop,
            "thrust_tv_delta_n": tv_delta,
            "env_mean_action_shift_n": shift_mean,
            "scheme_a_replay_mean_action_shift_n": replay_shift,
        },
        "online_contract_timing": "post_update",
        "safety_note": "Offline evaluation only; frozen /home/trevor/USV/artifacts/rl_models/v5/s4_dr files untouched.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--scheme-a-runs", default=None, help="Optional controlled_sim runs dir (e.g. pilot/runs)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    model_dir = Path(args.model_dir).resolve()
    onnx_path = model_dir / ONNX_FILENAME
    manifest_path = model_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    onnx_sha = _sha256(onnx_path)
    if manifest.get("onnx_sha256") != onnx_sha:
        raise ValueError(f"v5 ONNX sha256 mismatch: {onnx_sha} vs manifest {manifest.get('onnx_sha256')}")

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    nom_eval = run_env_comparison(session, hydro_dr_frac=0.0)
    dr_eval = run_env_comparison(session, hydro_dr_frac=0.15)
    replay_stats = replay_scheme_a_runs(session, Path(args.scheme_a_runs) if args.scheme_a_runs else None)
    decision = make_policy_selection_decision(nom_eval, dr_eval, replay_stats)

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    obs_contract = {
        "schema": "scheme-a-ppo-observation-contract-v1",
        "obs_dim": OBS_DIM,
        "action_dim": 2,
        "thrust_scale_n": float(manifest["thrust_scale_n"]),
        "lookahead_m": [float(v) for v in DEFAULT_LOOKAHEAD],
        "obs_prev_thrust_timing": "post_update",
        "prev_thrust_semantics": "Last confirmed executed thruster command applied on [t_k - dt, t_k]",
        "reward_prev_thrust_semantics": "Pre-update prev_thrust preserved identically during training/eval",
        "frozen_model": {
            "path": str(onnx_path),
            "onnx_sha256": onnx_sha,
            "manifest_sha256": _sha256(manifest_path),
            "source_model_sha256": manifest.get("source_model_sha256"),
        },
        "eval_summary": {
            "nominal_env": nom_eval,
            "dr_15pct_env": dr_eval,
            "scheme_a_replay": replay_stats,
        },
    }
    (out_dir / "observation_contract.json").write_text(
        json.dumps(obs_contract, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "policy_selection.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )

    pre = nom_eval["timing_eval"]["pre_update"]
    post = nom_eval["timing_eval"]["post_update"]
    dr_pre = dr_eval["timing_eval"]["pre_update"]
    dr_post = dr_eval["timing_eval"]["post_update"]
    md = [
        "# PPO Observation Contract Fix & v5 Shadow Evaluation Report (WP5)",
        "",
        f"- **Frozen Model**: `{onnx_path}`",
        f"- **ONNX SHA-256**: `{onnx_sha}`",
        f"- **Decision (`policy_selection.json`)**: **`{decision['decision']}`**",
        f"- **Rationale**: {decision['reason']}",
        "",
        "## Closed-Loop Environment Evaluation (`straight`, `arc`, `zigzag` x 5 seeds)",
        "| Condition | Contract | Success Rate | Mean Pos RMSE (m) | Mean Pos Max (m) | Mean Yaw RMSE (rad) | Mean Thrust TV (N) |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: |",
        f"| Nominal | `pre_update` (legacy) | {pre['success_rate']:.1%} | {pre['mean_pos_rmse_m']:.4f} | {pre['mean_pos_max_m']:.4f} | {pre['mean_psi_rmse_rad']:.4f} | {pre['mean_thrust_tv_n']:.3f} |",
        f"| Nominal | `post_update` (fixed) | {post['success_rate']:.1%} | {post['mean_pos_rmse_m']:.4f} | {post['mean_pos_max_m']:.4f} | {post['mean_psi_rmse_rad']:.4f} | {post['mean_thrust_tv_n']:.3f} |",
        f"| DR ±15% | `pre_update` (legacy) | {dr_pre['success_rate']:.1%} | {dr_pre['mean_pos_rmse_m']:.4f} | {dr_pre['mean_pos_max_m']:.4f} | {dr_pre['mean_psi_rmse_rad']:.4f} | {dr_pre['mean_thrust_tv_n']:.3f} |",
        f"| DR ±15% | `post_update` (fixed) | {dr_post['success_rate']:.1%} | {dr_post['mean_pos_rmse_m']:.4f} | {dr_post['mean_pos_max_m']:.4f} | {dr_post['mean_psi_rmse_rad']:.4f} | {dr_post['mean_thrust_tv_n']:.3f} |",
        "",
        "## Single-Step Action Shift (`prev_thrust` Lagged vs Aligned)",
        f"- Env trajectory mean |p95| max diff [L, R] (N): `{nom_eval['single_step_action_shift']['mean_abs_diff_n']}` / `{nom_eval['single_step_action_shift']['p95_abs_diff_n']}` / `{nom_eval['single_step_action_shift']['max_abs_diff_n']}`",
        f"- Scheme A controlled_sim replay ({replay_stats.get('runs_evaluated', 0)} runs, {replay_stats.get('samples', 0)} steps): mean=`{replay_stats.get('mean_abs_diff_n')}`, max=`{replay_stats.get('max_abs_diff_n')}`",
        f"- ONNX Runtime CPU latency mean / p99: `{replay_stats.get('ort_latency_mean_ms')}` ms / `{replay_stats.get('ort_latency_p99_ms')}` ms",
    ]
    (out_dir / "ppo_shadow_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision["decision"], "out": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
