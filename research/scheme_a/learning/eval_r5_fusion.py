#!/usr/bin/env python3
"""R5 Final-Test Multi-Seed Paired Evaluation (6 arms x 3 seeds = 36 eps/arm) & Statistical Report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from closed_loop_metrics import sha256_file
from diagnose_gp_regression import (
    _aggregate_telemetry,
    paired_wilcoxon_and_bootstrap,
)
from eval_fusion_arms import (
    PLANT_DIR,
    PPO_MANIFEST,
    PPO_MODEL,
    SPLIT_MANIFEST,
    _aggregate_arm,
    _calibration_score,
)
from eval_r2_calib import DEFAULT_SOURCE_HASHES, R2_GP_DIR, R2_WORK_ROOT, _load_r2_gps, _run_batch
from gp_model import MultiChannelSparseGP


def _paired_arm_stats(
    arm_runs: list[dict[str, Any]],
    ref_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    if [r.get("ep_tag") for r in arm_runs] != [r.get("ep_tag") for r in ref_runs]:
        raise ValueError("Paired episode tag mismatch between arms")
    full = paired_wilcoxon_and_bootstrap(
        [r["geometric_tracking"]["cross_track_rmse_m"] for r in arm_runs],
        [r["geometric_tracking"]["cross_track_rmse_m"] for r in ref_runs],
    )
    res: dict[str, Any] = {"full_window": full}
    if all(isinstance(r.get("active_geometric_tracking"), dict) for r in arm_runs + ref_runs):
        res["active_only"] = paired_wilcoxon_and_bootstrap(
            [r["active_geometric_tracking"]["cross_track_rmse_m"] for r in arm_runs],
            [r["active_geometric_tracking"]["cross_track_rmse_m"] for r in ref_runs],
        )
    return res


def _summarize_group(
    runs_by_arm: dict[str, list[dict[str, Any]]],
    tel_by_arm: dict[str, dict[str, dict[str, Any]]] | None,
    arms: list[str],
    ref_arm: str = "nominal_nmpc",
    filter_fn=None,
) -> dict[str, Any]:
    filtered = {
        arm: ([r for r in runs_by_arm[arm] if filter_fn(r)] if filter_fn else list(runs_by_arm[arm]))
        for arm in arms
    }
    nom_runs = filtered[ref_arm]
    out: dict[str, Any] = {}
    for arm in arms:
        runs = filtered[arm]
        agg = _aggregate_arm(runs, nominal_runs=nom_runs if arm != ref_arm else None)
        if arm != ref_arm and runs:
            agg["stats_vs_nominal"] = _paired_arm_stats(runs, nom_runs)
            if "oracle_nmpc" in filtered and arm != "oracle_nmpc" and len(filtered["oracle_nmpc"]) == len(runs):
                agg["stats_vs_oracle"] = _paired_arm_stats(runs, filtered["oracle_nmpc"])
        if tel_by_arm is not None and arm in tel_by_arm and runs:
            agg["telemetry"] = _aggregate_telemetry(runs, tel_by_arm[arm])
        out[arm] = agg
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(R2_WORK_ROOT / "fusion_eval"))
    parser.add_argument("--calib-report", default=str(R2_WORK_ROOT / "calib_eval/calib_r4_report.json"))
    parser.add_argument("--conflict-report", default=str(R2_WORK_ROOT / "calib_eval/conflict_probe_report.json"))
    parser.add_argument("--source-hashes", default=str(DEFAULT_SOURCE_HASHES))
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--decisions", type=int, default=301)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--base-domain-id", type=int, default=110)
    parser.add_argument("--lambda-pi", type=float, default=None, help="Override selected positive lambda_pi from calib report.")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = Path(args.source_hashes)
    seed_offsets = [int(x.strip()) for x in str(args.seeds).split(",") if x.strip()]

    calib_doc = json.loads(Path(args.calib_report).read_text(encoding="utf-8"))["r4"]
    conflict_res = json.loads(Path(args.conflict_report).read_text(encoding="utf-8"))
    overall_best_lam = float(calib_doc["overall_best_lambda_pi"])
    selected_pos_lam = float(calib_doc["selected_positive_lambda_pi"])
    active_lambda = float(args.lambda_pi) if args.lambda_pi is not None else selected_pos_lam

    r2_pooled, r2_matched = _load_r2_gps()
    assert r2_pooled.is_file(), f"Missing pooled GP snapshot: {r2_pooled}"
    for prof, p in r2_matched.items():
        assert p.is_file(), f"Missing matched GP snapshot for {prof}: {p}"

    gp_models: dict[str, MultiChannelSparseGP] = {}
    for p in [r2_pooled, *r2_matched.values()]:
        m = MultiChannelSparseGP.load(p)
        gp_models[m.snapshot_sha256] = m

    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    test_eps = sorted([e for e in manifest["episodes"] if e["split"] == "final_test"], key=lambda e: e["episode_name"])
    heldout_names = {e["episode_name"] for e in test_eps if e["profile"] == "heldout_combination"}
    single_names = {e["episode_name"] for e in test_eps if e["profile"] != "heldout_combination"}
    maneuvers = sorted({str(e["maneuver"]) for e in test_eps})

    full_arms = ["nominal_nmpc", "oracle_nmpc", "gp_nmpc_r2b", "ppo_guided_nmpc", "gp_ppo_nmpc_r2b"]
    all_arms = [*full_arms, "gp_nmpc_matched_r2b"]
    arm_specs: dict[str, dict[str, Any]] = {
        "nominal_nmpc": {"gp": None, "ppo": False, "lambda_pi": 0.0, "oracle": False},
        "oracle_nmpc": {"gp": None, "ppo": False, "lambda_pi": 0.0, "oracle": True},
        "gp_nmpc_r2b": {"gp": r2_pooled, "ppo": False, "lambda_pi": 0.0, "oracle": False},
        "ppo_guided_nmpc": {"gp": None, "ppo": True, "lambda_pi": active_lambda, "oracle": False},
        "gp_ppo_nmpc_r2b": {"gp": r2_pooled, "ppo": True, "lambda_pi": active_lambda, "oracle": False},
    }

    tasks: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for arm in full_arms:
        spec = arm_specs[arm]
        for soff in seed_offsets:
            for ep in test_eps:
                ep_s = dict(ep)
                ep_s["seed"] = int(ep["seed"]) + 10000 * soff
                tag = f"s{soff}_{ep['episode_name']}"
                tasks.append((arm, ep_s, {**spec, "tag": tag}))

    for soff in seed_offsets:
        for ep in test_eps:
            prof = str(ep.get("profile") or "")
            if prof not in r2_matched:
                continue
            ep_s = dict(ep)
            ep_s["seed"] = int(ep["seed"]) + 10000 * soff
            tag = f"s{soff}_{ep['episode_name']}"
            tasks.append(("gp_nmpc_matched_r2b", ep_s, {"gp": r2_matched[prof], "ppo": False, "lambda_pi": 0.0, "oracle": False, "tag": tag}))

    print(
        f"[R5] Running final_test: {len(full_arms)} full arms x {len(seed_offsets)} seeds x {len(test_eps)} eps "
        f"+ gp_nmpc_matched_r2b x {len(single_names)} eps = {len(tasks)} runs (lambda_pi={active_lambda})...",
        flush=True,
    )
    runs_by_arm, tel_by_arm = _run_batch(
        out_dir=out_dir / "final_test",
        tasks=tasks,
        arm_names=all_arms,
        gp_models=gp_models,
        source_hashes=source_hashes,
        workers=int(args.workers),
        base_domain_id=int(args.base_domain_id),
        stop_decisions=int(args.decisions),
        resume=not args.no_resume,
    )

    selected_cfg = {
        "schema": "scheme-a-wp7-selected-config-v2",
        "gp_snapshot_pooled": str(r2_pooled),
        "gp_snapshot_pooled_sha256": sha256_file(r2_pooled),
        "gp_snapshots_per_profile": {
            k: {"path": str(v), "sha256": sha256_file(v)}
            for k, v in sorted(r2_matched.items())
        },
        "ppo_model_onnx": str(PPO_MODEL),
        "ppo_model_manifest": str(PPO_MANIFEST),
        "ppo_model_sha256": sha256_file(PPO_MODEL),
        "calibration_candidates": calib_doc["lambdas"],
        "calibration_seeds": calib_doc["seeds"],
        "calibration_decisions_per_episode": 301,
        "calibration_overall_best_lambda_pi": overall_best_lam,
        "selected_positive_lambda_pi": active_lambda,
        "selection_metric": "cross_track_rmse_mean + 0.1*heading_rmse_mean + 0.05*speed_rmse_mean + 0.005*tv_per_step_mean",
        "r2c_decision": "skipped_not_justified (r2b pooled Z2 M64 already -22.7% vs nominal on 36-ep calibration, 36/36 wins)",
        "source_hashes": str(source_hashes),
        "source_hashes_sha256": sha256_file(source_hashes),
    }

    agg_all = _summarize_group(runs_by_arm, tel_by_arm, full_arms)
    agg_heldout = _summarize_group(
        runs_by_arm, tel_by_arm, full_arms,
        filter_fn=lambda r: r["episode_name"] in heldout_names,
    )
    agg_single_all = _summarize_group(
        runs_by_arm, tel_by_arm, [*full_arms, "gp_nmpc_matched_r2b"],
        filter_fn=lambda r: r["episode_name"] in single_names,
    )
    by_maneuver = {
        man: _summarize_group(
            runs_by_arm, None, full_arms,
            filter_fn=lambda r, m=man: str(r.get("maneuver")) == m,
        )
        for man in maneuvers
    }
    gp_ppo_vs_gp_only = _paired_arm_stats(runs_by_arm["gp_ppo_nmpc_r2b"], runs_by_arm["gp_nmpc_r2b"])

    # Compatibility aliases for WP8 packager + full R5 keys.
    agg_all_compat = {
        **agg_all,
        "gp_nmpc": agg_all["gp_nmpc_r2b"],
        "gp_ppo_nmpc": agg_all["gp_ppo_nmpc_r2b"],
    }
    agg_held_compat = {
        **agg_heldout,
        "gp_nmpc": agg_heldout["gp_nmpc_r2b"],
        "gp_ppo_nmpc": agg_heldout["gp_ppo_nmpc_r2b"],
    }

    (out_dir / "selected_configuration.json").write_text(
        json.dumps(selected_cfg, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "calibration_summary.json").write_text(
        json.dumps(calib_doc["summary"], indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "conflict_probe_summary.json").write_text(
        json.dumps(conflict_res, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )

    eval_doc = {
        "schema": "scheme-a-wp7-four-arm-evaluation-v2",
        "seeds": seed_offsets,
        "episodes_per_full_arm": len(seed_offsets) * len(test_eps),
        "episodes_per_matched_arm": len(seed_offsets) * len(single_names),
        "selected_configuration": selected_cfg,
        "conflict_priority_probe": conflict_res,
        "calibration_summary": calib_doc["summary"],
        "final_test_aggregates_all12": agg_all_compat,
        "final_test_aggregates_all": agg_all,
        "final_test_aggregates_heldout6": agg_held_compat,
        "final_test_aggregates_heldout": agg_heldout,
        "final_test_aggregates_single": agg_single_all,
        "final_test_gp_nmpc_matched_single6": agg_single_all["gp_nmpc_matched_r2b"],
        "final_test_by_maneuver": by_maneuver,
        "gp_ppo_vs_gp_only_paired_stats": gp_ppo_vs_gp_only,
        "final_test_episodes": {arm: runs_by_arm[arm] for arm in full_arms},
        "final_test_matched_single_episodes": runs_by_arm["gp_nmpc_matched_r2b"],
    }
    eval_path = out_dir / "four_arm_evaluation.json"
    eval_path.write_text(json.dumps(eval_doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # Render decision-grade markdown report.
    lines = [
        "# Scheme A R5 Multi-Seed GP+PPO Closed-Loop Evaluation Report (`r2`)",
        "",
        "## 1. Selected Configuration & Constraint-Priority Probe",
        f"- Pooled $Z_2$-Symmetric GP (`M=64`): `{r2_pooled}` (`sha256={selected_cfg['gp_snapshot_pooled_sha256']}`)",
        f"- Frozen PPO Policy (`v5/s4_dr`): `{PPO_MODEL}` (`sha256={selected_cfg['ppo_model_sha256']}`)",
        f"- Calibration `lambda_pi` Sweep (`{len(calib_doc['seeds'])} seeds x 12 eps = {len(calib_doc['seeds'])*12} eps/arm`): `{calib_doc['lambdas']}`",
        f"- Overall lowest `gp_ppo` calibration score: `lambda_pi={overall_best_lam}`; Selected positive `lambda_pi`: `{active_lambda}`",
        "",
        "| Constraint Probe | Requested q_pi | Passed | Max |u| (N) | Max Step |Δu| (N) | First Step (N) | Override >0.5N |",
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
        f"## 2. Calibration Split Summary ({len(calib_doc['seeds'])*12} eps/arm)",
        "| Arm | Eps | CTE (m) | Active CTE | Δ vs Nom [95% CI] | W/T/L | Head | Speed | TV | Score |",
        "|---|---:|---:|---:|---:|:---:|---:|---:|---:|---:|",
    ])
    for arm, s in calib_doc["summary"].items():
        sn = s["stats_vs_nominal"]
        act_m = (s.get("active_cross_track_rmse_m") or {}).get("mean")
        act_s = f"{act_m:.4f}" if act_m is not None else "-"
        lines.append(
            f"| `{arm}` | {s['episodes']} | {s['cross_track_rmse_m']['mean']:.4f} | {act_s} | "
            f"{sn['mean_diff']:+.4f} [{sn['bootstrap_ci95_low']:+.4f},{sn['bootstrap_ci95_high']:+.4f}] | "
            f"{sn['wins']}/{sn['ties']}/{sn['losses']} | {s['heading_rmse_rad']['mean']:.4f} | "
            f"{s['speed_rmse_mps']['mean']:.4f} | {s['control_tv_per_step']['mean']:.3f} | {s['calibration_score']:.4f} |"
        )

    def _emit_arm_table(title: str, group: dict[str, Any], arms_order: list[str]) -> None:
        lines.extend([
            "",
            f"## {title}",
            "| Arm | Pass/Succ | CTE (m) | Active CTE | Δ vs Nom [95% CI] | Wilcoxon p | W/T/L | Head | Speed | Vel Res | E2E P50/P95/Max (ms) |",
            "|---|:---:|---:|---:|---:|---:|:---:|---:|---:|---:|---:|",
        ])
        for arm in arms_order:
            a = group[arm]
            act_m = (a.get("active_cross_track_rmse_m") or {}).get("mean")
            act_s = f"{act_m:.4f}" if act_m is not None else "-"
            sn = (a.get("stats_vs_nominal") or {}).get("full_window")
            if sn:
                d_str = f"{sn['mean_diff']:+.4f} [{sn['bootstrap_ci95_low']:+.4f},{sn['bootstrap_ci95_high']:+.4f}]"
                p_str = f"{sn['wilcoxon_p']:.2e}"
                wtl = f"{sn['wins']}/{sn['ties']}/{sn['losses']}"
            else:
                d_str, p_str, wtl = "0.0000", "-", "-"
            res_v = a["gp_model_vel_rmse"]["mean"] if a["gp_model_vel_rmse"]["mean"] is not None else a["zero_model_vel_rmse"]["mean"]
            lat = a["latency_ms"]
            lines.append(
                f"| `{arm}` | {a['checker_pass_count']}/{a['episodes']} ({a['success_count']}) | "
                f"{a['cross_track_rmse_m']['mean']:.4f} | {act_s} | {d_str} | {p_str} | {wtl} | "
                f"{a['heading_rmse_rad']['mean']:.4f} | {a['speed_rmse_mps']['mean']:.4f} | {res_v:.5f} | "
                f"{lat['e2e_p50_mean']:.2f} / {lat['e2e_p95_mean']:.2f} / {lat['e2e_max']:.2f} |"
            )

    _emit_arm_table(
        f"3. Held-Out `final_test` Overall ({len(seed_offsets)} seeds x {len(test_eps)} eps = {len(seed_offsets)*len(test_eps)} eps/arm)",
        agg_all,
        full_arms,
    )
    gp_vs_gpppo = gp_ppo_vs_gp_only["full_window"]
    lines.extend([
        "",
        f"- Paired `gp_ppo_nmpc_r2b` (`lambda_pi={active_lambda}`) vs `gp_nmpc_r2b` (`lambda_pi=0.0`): "
        f"ΔCTE=`{gp_vs_gpppo['mean_diff']:+.5f} m` (`[{gp_vs_gpppo['bootstrap_ci95_low']:+.5f}, {gp_vs_gpppo['bootstrap_ci95_high']:+.5f}]`), "
        f"Wilcoxon `p={gp_vs_gpppo['wilcoxon_p']:.3e}`, W/T/L=`{gp_vs_gpppo['wins']}/{gp_vs_gpppo['ties']}/{gp_vs_gpppo['losses']}`.",
    ])
    _emit_arm_table(
        f"4. Subgroup: Unseen `heldout_combination` ({len(seed_offsets)*len(heldout_names)} eps/arm)",
        agg_heldout,
        full_arms,
    )
    _emit_arm_table(
        f"5. Subgroup: Known-Profile Single-Plant + Matched Specialist GP ({len(seed_offsets)*len(single_names)} eps/arm)",
        agg_single_all,
        [*full_arms, "gp_nmpc_matched_r2b"],
    )

    lines.extend([
        "",
        "## 6. Per-Maneuver CTE Breakdown (`final_test` All Seeds)",
        "| Maneuver | Eps/Arm | Nominal | Oracle | GP `r2b` | PPO Guided | GP+PPO `r2b` | Δ(GP - Nom) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for man in maneuvers:
        mg = by_maneuver[man]
        d_gp = mg["gp_nmpc_r2b"]["cross_track_rmse_m"]["mean"] - mg["nominal_nmpc"]["cross_track_rmse_m"]["mean"]
        lines.append(
            f"| `{man}` | {mg['nominal_nmpc']['episodes']} | "
            f"{mg['nominal_nmpc']['cross_track_rmse_m']['mean']:.4f} | "
            f"{mg['oracle_nmpc']['cross_track_rmse_m']['mean']:.4f} | "
            f"{mg['gp_nmpc_r2b']['cross_track_rmse_m']['mean']:.4f} | "
            f"{mg['ppo_guided_nmpc']['cross_track_rmse_m']['mean']:.4f} | "
            f"{mg['gp_ppo_nmpc_r2b']['cross_track_rmse_m']['mean']:.4f} | {d_gp:+.4f} |"
        )

    lines.extend([
        "",
        "## 7. Telemetry & Active-Window (`reason != 'shutdown'`) Comparison",
        "| Arm | Active CTE (m) | Active Δ vs Nom | Wilcoxon p (Active) | Freeze Diff Mean/Max | OOD % | Post NonAcc |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for arm in full_arms:
        a = agg_all[arm]
        t = a["telemetry"]
        sa = (a.get("stats_vs_nominal") or {}).get("active_only")
        d_a = f"{sa['mean_diff']:+.4f}" if sa else "0.0000"
        p_a = f"{sa['wilcoxon_p']:.2e}" if sa else "-"
        fmean = t["freeze_post_diff_mean"]
        fmax = t["freeze_post_diff_max"]
        lines.append(
            f"| `{arm}` | {a['active_cross_track_rmse_m']['mean']:.4f} | {d_a} | {p_a} | "
            f"{(f'{fmean:.5f}' if fmean is not None else '-')} / {(f'{fmax:.5f}' if fmax is not None else '-')} | "
            f"{100.0 * t['gp_ood_fraction']:.2f}% | {t['post_warmup_nonacc_gt12']} |"
        )

    report_path = out_dir / "fusion_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "eval_json": str(eval_path), "report_md": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
