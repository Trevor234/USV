#!/usr/bin/env python3
"""R2 Calibration Evaluation in Phase-Aligned ROS2 (nominal, oracle, r1 GP, r2b Z2-sym GP, matched GP) & R4 lambda_pi sweep."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
import queue
import sys
from typing import Any

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from diagnose_gp_regression import _aggregate_telemetry, _extract_run_telemetry
from eval_fusion_arms import (
    CONTRACT,
    GP_DIR as R1_GP_DIR,
    GP_POOLED as R1_GP_POOLED,
    PROFILE_TO_GP as R1_PROFILE_TO_GP,
    SPLIT_MANIFEST,
    _aggregate_arm,
    _run_episode,
    _strip_traj,
    run_conflict_priority_probe,
)
from gp_model import MultiChannelSparseGP

R2_WORK_ROOT = Path("/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/scheme_A_gp_ppo_20261118_work")
DEFAULT_SOURCE_HASHES = R2_WORK_ROOT / "meta/source_hashes.json"
R2_GP_DIR = R2_WORK_ROOT / "gp_models"


def _run_batch(
    *,
    out_dir: Path,
    tasks: list[tuple[str, dict[str, Any], dict[str, Any]]],
    arm_names: list[str],
    gp_models: dict[str, MultiChannelSparseGP],
    source_hashes: Path,
    workers: int,
    base_domain_id: int,
    stop_decisions: int,
    resume: bool,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, dict[str, Any]]]]:
    domain_q: queue.Queue[int] = queue.Queue()
    for i in range(max(1, workers)):
        domain_q.put(base_domain_id + i)

    runs_by_arm: dict[str, list[dict[str, Any]]] = {k: [] for k in arm_names}
    tel_by_arm: dict[str, dict[str, dict[str, Any]]] = {k: {} for k in arm_names}

    def _worker(arm_name: str, ep: dict[str, Any], spec: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        ep_tag = str(spec.get("tag") or ep["episode_name"])
        ep_dir = out_dir / arm_name / ep_tag
        m = _strip_traj(_run_episode(
            run_dir=ep_dir,
            ep=ep,
            stop_decisions=stop_decisions,
            domain_queue=domain_q,
            gp_models=gp_models,
            gp_snapshot=spec["gp"],
            oracle_plant_file=Path(ep["plant_model_file"]) if spec.get("oracle") else None,
            align_tick_phase=True,
            source_hashes=source_hashes,
            ppo_proposal=bool(spec.get("ppo")),
            lambda_pi=float(spec.get("lambda_pi", 0.0)),
            resume=resume,
        ))
        m["episode_name"] = ep["episode_name"]
        m["ep_tag"] = ep_tag
        tel = _extract_run_telemetry(ep_dir)
        return arm_name, m, tel

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = [pool.submit(_worker, a, ep, spec) for a, ep, spec in tasks]
        total = len(futs)
        for idx, fut in enumerate(futs, 1):
            arm_name, m, tel = fut.result()
            runs_by_arm[arm_name].append(m)
            tel_by_arm[arm_name][m["ep_tag"]] = tel
            print(
                f"[{idx}/{total}] arm={arm_name:20s} ep={m['ep_tag']:50s} "
                f"cte={m['geometric_tracking']['cross_track_rmse_m']:.4f} "
                f"e2e_p95={m['latency_ms']['freeze_to_publish_e2e']['p95']:.2f}ms "
                f"reused={m.get('reused')}",
                flush=True,
            )

    for arm in runs_by_arm:
        runs_by_arm[arm].sort(key=lambda r: r["ep_tag"])
    return runs_by_arm, tel_by_arm


def _load_r2_gps() -> tuple[Path, dict[str, Path]]:
    r2_pooled = R2_GP_DIR / "pooled/gp_snapshot.json"
    r2_matched = {
        prof: R2_GP_DIR / prof / "gp_snapshot.json"
        for prof in ("mass_plus_10pct", "surge_damping_plus_15pct", "yaw_damping_plus_15pct")
    }
    return r2_pooled, r2_matched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["r2", "r4", "conflict", "all"], default="r2")
    parser.add_argument("--out", default=str(R2_WORK_ROOT / "calib_eval"))
    parser.add_argument("--source-hashes", default=str(DEFAULT_SOURCE_HASHES))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--base-domain-id", type=int, default=90)
    parser.add_argument("--decisions", type=int, default=301)
    parser.add_argument("--lambdas", default="0.0,0.001,0.002,0.003,0.005,0.01")
    parser.add_argument("--r4-seeds", default="0,1,2")
    parser.add_argument("--r4-gp", choices=["r1", "r2b"], default="r2b")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = Path(args.source_hashes)
    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    calib_eps = sorted([e for e in manifest["episodes"] if e["split"] == "calibration"], key=lambda e: e["episode_name"])

    r2_pooled, r2_matched = _load_r2_gps()
    gp_paths: list[Path] = [R1_GP_POOLED, *R1_PROFILE_TO_GP.values()]
    if r2_pooled.is_file():
        gp_paths.append(r2_pooled)
    for p in r2_matched.values():
        if p.is_file():
            gp_paths.append(p)
    gp_models: dict[str, MultiChannelSparseGP] = {}
    for p in gp_paths:
        m = MultiChannelSparseGP.load(p)
        gp_models[m.snapshot_sha256] = m

    report: dict[str, Any] = {"schema": "scheme-a-r2-calib-v1", "episodes": len(calib_eps)}

    if args.stage in ("r2", "all"):
        arms_r2 = ["nominal_nmpc", "oracle_nmpc", "gp_nmpc_r1"]
        tasks_r2: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        if r2_pooled.is_file():
            arms_r2.append("gp_nmpc_r2b")
        if all(p.is_file() for p in r2_matched.values()):
            arms_r2.append("gp_nmpc_matched_r2b")

        for ep in calib_eps:
            prof = str(ep["profile"])
            tasks_r2.append(("nominal_nmpc", ep, {"gp": None, "oracle": False}))
            tasks_r2.append(("oracle_nmpc", ep, {"gp": None, "oracle": True}))
            tasks_r2.append(("gp_nmpc_r1", ep, {"gp": R1_GP_POOLED, "oracle": False}))
            if r2_pooled.is_file():
                tasks_r2.append(("gp_nmpc_r2b", ep, {"gp": r2_pooled, "oracle": False}))
            if all(p.is_file() for p in r2_matched.values()):
                tasks_r2.append(("gp_nmpc_matched_r2b", ep, {"gp": r2_matched[prof], "oracle": False}))

        runs_r2, tel_r2 = _run_batch(
            out_dir=out_dir / "r2",
            tasks=tasks_r2,
            arm_names=arms_r2,
            gp_models=gp_models,
            source_hashes=source_hashes,
            workers=int(args.workers),
            base_domain_id=int(args.base_domain_id),
            stop_decisions=int(args.decisions),
            resume=not args.no_resume,
        )
        nom = runs_r2["nominal_nmpc"]
        r2_summary = {
            arm: {
                **_aggregate_arm(runs_r2[arm], nominal_runs=nom if arm != "nominal_nmpc" else None),
                "telemetry": _aggregate_telemetry(runs_r2[arm], tel_r2[arm]),
            }
            for arm in arms_r2
        }
        report["r2"] = {"summary": r2_summary, "runs": runs_r2, "telemetry": tel_r2}

        md = [
            "# R2 Calibration Evaluation (ROS2 Phase-Aligned + SQP_RTI Warmstart)",
            "",
            "| Arm | Eps | CTE RMSE (m) | Δ vs Nom | Heading RMSE | Speed RMSE | Vel Res RMSE | OOD % | Freeze Diff Max | Post NonAcc | E2E P50/P95 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for arm in arms_r2:
            s = r2_summary[arm]
            t = s["telemetry"]
            dnom = s.get("vs_nominal", {}).get("cte_rmse_delta_mean_m", 0.0)
            velr = s["gp_model_vel_rmse"]["mean"] if s["gp_model_vel_rmse"]["mean"] is not None else s["zero_model_vel_rmse"]["mean"]
            fmax = t["freeze_post_diff_max"] if t["freeze_post_diff_max"] is not None else 0.0
            lat = s["latency_ms"]
            md.append(
                f"| `{arm}` | {s['episodes']} | {s['cross_track_rmse_m']['mean']:.4f} | {dnom:+.4f} | "
                f"{s['heading_rmse_rad']['mean']:.4f} | {s['speed_rmse_mps']['mean']:.4f} | {velr:.5f} | "
                f"{100.0 * t['gp_ood_fraction']:.1f}% | {fmax:.5f} | {t['post_warmup_nonacc_gt12']} | "
                f"{lat['e2e_p50_mean']:.2f}/{lat['e2e_p95_mean']:.2f} |"
            )
        (out_dir / "r2_calibration_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    if args.stage in ("r4", "all"):
        lambdas = [float(x.strip()) for x in str(args.lambdas).split(",") if x.strip()]
        seed_offsets = [int(x.strip()) for x in str(args.r4_seeds).split(",") if x.strip()]
        gp_snap = r2_pooled if (args.r4_gp == "r2b" and r2_pooled.is_file()) else R1_GP_POOLED
        arms_r4: list[str] = []
        tasks_r4: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for lam in lambdas:
            lam_tag = f"l{str(lam).replace('.', 'p')}"
            for prefix, use_gp in [("ppo", None), ("gp_ppo", gp_snap)]:
                arm = f"{prefix}_{lam_tag}"
                arms_r4.append(arm)
                for soff in seed_offsets:
                    for ep in calib_eps:
                        ep_s = dict(ep)
                        ep_s["seed"] = int(ep["seed"]) + 10000 * soff
                        tag = f"s{soff}_{ep['episode_name']}"
                        tasks_r4.append((arm, ep_s, {"gp": use_gp, "ppo": lam > 0.0, "lambda_pi": lam, "tag": tag}))

        runs_r4, tel_r4 = _run_batch(
            out_dir=out_dir / "r4",
            tasks=tasks_r4,
            arm_names=arms_r4,
            gp_models=gp_models,
            source_hashes=source_hashes,
            workers=int(args.workers),
            base_domain_id=int(args.base_domain_id),
            stop_decisions=int(args.decisions),
            resume=not args.no_resume,
        )
        base_nom = runs_r4[f"ppo_l{str(lambdas[0]).replace('.', 'p')}"]
        r4_summary = {
            arm: {
                **_aggregate_arm(runs_r4[arm], nominal_runs=base_nom),
                "telemetry": _aggregate_telemetry(runs_r4[arm], tel_r4[arm]),
            }
            for arm in arms_r4
        }
        report["r4"] = {"lambdas": lambdas, "seeds": seed_offsets, "gp": str(gp_snap), "summary": r4_summary, "runs": runs_r4}

        md4 = [
            f"# R4 Calibration Lambda_pi Sweep ({len(seed_offsets)} seeds x {len(calib_eps)} eps = {len(seed_offsets)*len(calib_eps)} eps/arm)",
            "",
            "| Arm | Eps | CTE RMSE (m) | Std | Heading RMSE | Speed RMSE | Override >0.5N % | Post NonAcc |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for arm in arms_r4:
            s = r4_summary[arm]
            t = s["telemetry"]
            ovr = s.get("ppo_override_gt_0p5n_fraction", {}).get("mean")
            ovr_s = f"{100.0 * ovr:.1f}%" if ovr is not None else "0.0%"
            md4.append(
                f"| `{arm}` | {s['episodes']} | {s['cross_track_rmse_m']['mean']:.4f} | "
                f"{s['cross_track_rmse_m']['std']:.4f} | {s['heading_rmse_rad']['mean']:.4f} | "
                f"{s['speed_rmse_mps']['mean']:.4f} | {ovr_s} | {t['post_warmup_nonacc_gt12']} |"
            )
        (out_dir / "r4_calibration_report.md").write_text("\n".join(md4) + "\n", encoding="utf-8")

    if args.stage in ("conflict", "all"):
        gp_snap = r2_pooled if (args.r4_gp == "r2b" and r2_pooled.is_file()) else R1_GP_POOLED
        dq_conf: queue.Queue[int] = queue.Queue()
        dq_conf.put(int(args.base_domain_id))
        conflict_res = run_conflict_priority_probe(
            out_root=out_dir,
            domain_queue=dq_conf,
            gp_models=gp_models,
            resume=not args.no_resume,
            gp_snapshot=gp_snap,
            source_hashes=source_hashes,
            align_tick_phase=True,
        )
        (out_dir / "conflict_probe_report.json").write_text(
            json.dumps(conflict_res, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        report["conflict_probe"] = conflict_res

    out_json = out_dir / f"calib_{args.stage}_report.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "json": str(out_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
