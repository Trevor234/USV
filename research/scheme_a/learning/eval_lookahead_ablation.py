#!/usr/bin/env python3
"""前瞻距离三臂闭环消融：gp_only vs gp+PPO(SCHEME_A 7.5 m) vs gp+PPO(TRAINING 4.0 m)。

P1.4 的可判定产物：`lookahead_ablation.json` + `lookahead_ablation.md`，
报告里直接给出 `adopt_training` 判定，P2 据此决定 `LOOKAHEAD_M`。

用法（校准集，默认 12 eps x 3 seeds x 3 臂）::

    /usr/bin/python3 eval_lookahead_ablation.py \
        --out /path/to/p1 --source-hashes /path/to/meta/source_hashes.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from eval_fusion_arms import (
    PPO_MANIFEST,
    PPO_MODEL,
    SPLIT_MANIFEST,
    _strip_traj,
)
from eval_r2_calib import DEFAULT_SOURCE_HASHES, R2_WORK_ROOT, _load_r2_gps, _run_batch
from eval_r5_fusion import _summarize_group
from gp_model import MultiChannelSparseGP

SCHEME_A_LOOKAHEAD = (0.4, 0.8, 1.4, 2.2, 3.2, 4.4, 5.8, 7.5)
TRAINING_LOOKAHEAD = (0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0, 4.0)
LAMBDA_PI = 0.0005
REF_ARM = "gp_only"
TIE_EPS = 5e-4          # 0.5 mm：低于此差异视为持平（与 P5/P6 判定门同量级）
DELTA_MARGIN = 5e-4     # adopt_training 的领先裕度


def _la_text(la: tuple[float, ...]) -> str:
    return ",".join(str(v) for v in la)


def default_arms(pooled_gp: Path) -> list[dict[str, Any]]:
    return [
        {"name": "gp_only", "gp": str(pooled_gp), "ppo": False, "lambda_pi": 0.0,
         "lookahead": "", "onnx": "", "manifest": ""},
        {"name": "gp_ppo_la75", "gp": str(pooled_gp), "ppo": True, "lambda_pi": LAMBDA_PI,
         "lookahead": _la_text(SCHEME_A_LOOKAHEAD), "onnx": str(PPO_MODEL),
         "manifest": str(PPO_MANIFEST)},
        {"name": "gp_ppo_la40", "gp": str(pooled_gp), "ppo": True, "lambda_pi": LAMBDA_PI,
         "lookahead": _la_text(TRAINING_LOOKAHEAD), "onnx": str(PPO_MODEL),
         "manifest": str(PPO_MANIFEST)},
    ]


def _split_episodes(split: str) -> list[dict[str, Any]]:
    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    eps = [e for e in manifest["episodes"] if e["split"] == split]
    return sorted(eps, key=lambda e: e["episode_name"])


def _dev_episodes(base: dict[str, Any]) -> list[dict[str, Any]]:
    """校准集缺 straight/left_turn，补两个开发工况（seed 与 final_test 不重叠）。"""
    out: list[dict[str, Any]] = []
    for name, maneuver, seed in (("dev_straight", "straight", 30000),
                                 ("dev_left_turn", "left_turn", 30001)):
        ep = {
            "episode_name": name,
            "maneuver": maneuver,
            "seed": seed,
            "plant_model_file": base["plant_model_file"],
            "profile": base.get("profile"),
            "ep_tag": name,
        }
        if base.get("cruise_speed") is not None:
            ep["cruise_speed"] = base["cruise_speed"]
        out.append(ep)
    return out


def _cte(run: dict[str, Any]) -> float:
    return float(run["geometric_tracking"]["cross_track_rmse_m"])


def _paired_delta(arm_runs: list[dict[str, Any]], ref_runs: list[dict[str, Any]]) -> dict[str, Any]:
    if [r["ep_tag"] for r in arm_runs] != [r["ep_tag"] for r in ref_runs]:
        raise ValueError("配对 episode 顺序不一致")
    diffs = [_cte(a) - _cte(b) for a, b in zip(arm_runs, ref_runs)]
    import numpy as np
    from diagnose_gp_regression import paired_wilcoxon_and_bootstrap

    stats = paired_wilcoxon_and_bootstrap(
        [_cte(r) for r in arm_runs], [_cte(r) for r in ref_runs]
    )
    return {"delta_cte_mean": float(np.mean(diffs)), "stats": stats}


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = Path(args.source_hashes)
    seed_offsets = [int(x.strip()) for x in str(args.seeds).split(",") if x.strip()]

    pooled_gp, _matched = _load_r2_gps()
    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        arms = cfg["arms"]
    else:
        arms = default_arms(pooled_gp)
    arm_names = [a["name"] for a in arms]
    if REF_ARM not in arm_names:
        raise SystemExit(f"arms 定义必须包含参考臂 {REF_ARM!r}")

    gp_models: dict[str, MultiChannelSparseGP] = {}
    for a in arms:
        if a.get("gp"):
            m = MultiChannelSparseGP.load(Path(a["gp"]))
            gp_models[m.snapshot_sha256] = m

    episodes = _split_episodes(args.split)
    if not episodes:
        raise SystemExit(f"split={args.split!r} 没有 episode")
    episodes = episodes + _dev_episodes(episodes[0])

    tasks: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for soff in seed_offsets:
        for base_ep in episodes:
            ep = dict(base_ep)
            base_seed = int(base_ep["seed"])
            ep["seed"] = base_seed + 10000 * soff
            tag = f"s{soff}_{base_ep['episode_name']}"
            for a in arms:
                spec = {
                    "gp": Path(a["gp"]) if a.get("gp") else None,
                    "ppo": bool(a.get("ppo")),
                    "lambda_pi": float(a.get("lambda_pi", 0.0)),
                    "lookahead": str(a.get("lookahead", "") or ""),
                    "onnx": str(a.get("onnx") or ""),
                    "manifest": str(a.get("manifest") or ""),
                    "tag": tag,
                }
                tasks.append((a["name"], ep, spec))

    print(
        f"[P1.4] {len(arms)} arms x {len(seed_offsets)} seeds x {len(episodes)} eps "
        f"= {len(tasks)} runs (split={args.split}, decisions={args.decisions})",
        flush=True,
    )
    runs_by_arm, tel_by_arm = _run_batch(
        out_dir=out_dir / "runs",
        tasks=tasks,
        arm_names=arm_names,
        gp_models=gp_models,
        source_hashes=source_hashes,
        workers=int(args.workers),
        base_domain_id=int(args.base_domain_id),
        stop_decisions=int(args.decisions),
        resume=not args.no_resume,
    )

    agg_all = _summarize_group(runs_by_arm, tel_by_arm, arm_names, ref_arm=REF_ARM)
    maneuvers = sorted({str(r.get("maneuver")) for r in runs_by_arm[REF_ARM]})
    by_maneuver = {
        man: _summarize_group(
            runs_by_arm, None, arm_names, ref_arm=REF_ARM,
            filter_fn=lambda r, m=man: str(r.get("maneuver")) == m,
        )
        for man in maneuvers
    }
    deltas = {
        arm: _paired_delta(runs_by_arm[arm], runs_by_arm[REF_ARM])
        for arm in arm_names if arm != REF_ARM
    }

    d_la40 = deltas.get("gp_ppo_la40", {}).get("delta_cte_mean")
    d_la75 = deltas.get("gp_ppo_la75", {}).get("delta_cte_mean")
    ci40_hi = (deltas.get("gp_ppo_la40", {}).get("stats") or {}).get("bootstrap_ci95_high")
    adopt_training = bool(
        d_la40 is not None and d_la75 is not None and ci40_hi is not None
        and d_la40 <= d_la75 - DELTA_MARGIN and ci40_hi < 0.0
    )
    selected_lookahead = TRAINING_LOOKAHEAD if adopt_training else SCHEME_A_LOOKAHEAD

    doc = {
        "schema": "scheme-a-lookahead-ablation-v1",
        "split": args.split,
        "seeds": seed_offsets,
        "decisions": int(args.decisions),
        "lambda_pi": LAMBDA_PI,
        "arms": arms,
        "episodes_per_arm": len(seed_offsets) * len(episodes),
        "aggregates": agg_all,
        "by_maneuver": by_maneuver,
        "paired_deltas_vs_gp_only": deltas,
        "decision": {
            "rule": ("adopt_training = (Δ_la40 <= Δ_la75 - 0.0005) and (ci95_upper(Δ_la40) < 0.0)"),
            "delta_la40": d_la40,
            "delta_la75": d_la75,
            "ci95_upper_la40": ci40_hi,
            "adopt_training": adopt_training,
            "selected_lookahead_m": list(selected_lookahead),
            "note": ("前瞻距离不是唯一主因" if not adopt_training else "采用训练口径 4.0 m 前瞻"),
        },
        "runs": {arm: [_strip_traj(r) for r in runs_by_arm[arm]] for arm in arm_names},
    }
    (out_dir / "lookahead_ablation.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )

    def _row(arm: str, group: dict[str, Any]) -> str:
        a = group[arm]
        st = (a.get("stats_vs_nominal") or {}).get("full_window")
        act = (a.get("active_cross_track_rmse_m") or {}).get("mean")
        act_s = f"{act:.4f}" if act is not None else "-"
        if st is None:
            d, ci, wtl, p = "0.0000", "-", "-", "-"
        else:
            d = f"{st['mean_diff']:+.5f}"
            ci = f"[{st['bootstrap_ci95_low']:+.5f},{st['bootstrap_ci95_high']:+.5f}]"
            wtl = f"{st['wins']}/{st['ties']}/{st['losses']}"
            p = f"{st['wilcoxon_p']:.2e}"
        return (
            f"| `{arm}` | {a['checker_pass_count']}/{a['episodes']} | "
            f"{a['cross_track_rmse_m']['mean']:.4f} | {act_s} | {d} | {ci} | {p} | {wtl} |"
        )

    lines = [
        "# 前瞻距离三臂闭环消融（P1.4）",
        "",
        f"- split=`{args.split}`  seeds=`{seed_offsets}`  decisions={args.decisions}  lambda_pi={LAMBDA_PI}",
        f"- 每臂 {len(seed_offsets) * len(episodes)} 个 episode（含 dev_straight / dev_left_turn）",
        f"- 配对参考臂：`{REF_ARM}`",
        "",
        "## 总体",
        "| Arm | Pass/Eps | CTE (m) | Active CTE | Δ vs gp_only | 95% CI | Wilcoxon p | W/T/L |",
        "|---|:---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for arm in arm_names:
        lines.append(_row(arm, agg_all))
    lines.extend([
        "",
        "## 逐 maneuver",
        "| Maneuver | Arm | Eps | CTE (m) | Δ vs gp_only | 95% CI | W/T/L |",
        "|---|---|---:|---:|---:|---:|:---:|",
    ])
    for man in maneuvers:
        for arm in arm_names:
            a = by_maneuver[man][arm]
            st = (a.get("stats_vs_nominal") or {}).get("full_window")
            if st is None:
                d, ci, wtl = "0.0000", "-", "-"
            else:
                d = f"{st['mean_diff']:+.5f}"
                ci = f"[{st['bootstrap_ci95_low']:+.5f},{st['bootstrap_ci95_high']:+.5f}]"
                wtl = f"{st['wins']}/{st['ties']}/{st['losses']}"
            lines.append(
                f"| `{man}` | `{arm}` | {a['episodes']} | {a['cross_track_rmse_m']['mean']:.4f} | {d} | {ci} | {wtl} |"
            )
    lines.extend([
        "",
        "## 判定",
        "```",
        f"Δ_la40 = {d_la40}",
        f"Δ_la75 = {d_la75}",
        f"ci95_upper(Δ_la40) = {ci40_hi}",
        f"adopt_training = {adopt_training}",
        f"LOOKAHEAD_M = {list(selected_lookahead)}",
        "```",
        "",
        doc["decision"]["note"],
    ])
    (out_dir / "lookahead_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "json": str(out_dir / "lookahead_ablation.json"),
        "md": str(out_dir / "lookahead_ablation.md"),
        "adopt_training": adopt_training,
        "delta_la40": d_la40,
        "delta_la75": d_la75,
    }, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="arms.json（缺省用内置三臂）")
    parser.add_argument("--split", default="calibration", choices=("calibration", "final_test"))
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--base-domain-id", type=int, default=130)
    parser.add_argument("--decisions", type=int, default=301)
    parser.add_argument("--out", default=str(R2_WORK_ROOT / "p1_lookahead_ablation"))
    parser.add_argument("--source-hashes", default=str(DEFAULT_SOURCE_HASHES))
    parser.add_argument("--no-resume", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
