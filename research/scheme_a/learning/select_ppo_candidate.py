#!/usr/bin/env python3
"""按闭环指标选 PPO 候选模型（P6）。

对每个候选跑 `gp_only` 与 `gp+candidate` 两臂，算逐 episode 配对 ΔCTE，
按预先声明的门判定：
    selected 条件：delta_cte_mean <= -0.0005 且 ci95_upper < 0
同分（都达标）时取 `tv_per_step` 更小者；无候选达标 → `selected: null`。

产物 `selection.json`：
  {"ranking": [{"name","delta_cte_mean","ci95","wins","losses","tv_per_step"}],
   "selected": "<name>" 或 null, "reason": "..."}

用法::

    /usr/bin/python3 select_ppo_candidate.py --candidates cand.json --out <dir>/p6
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from closed_loop_metrics import sha256_file
from eval_fusion_arms import CONTRACT, PPO_MANIFEST, PPO_MODEL, SPLIT_MANIFEST, _strip_traj
from eval_r2_calib import DEFAULT_SOURCE_HASHES, R2_WORK_ROOT, _load_r2_gps, _run_batch
from diagnose_gp_regression import paired_wilcoxon_and_bootstrap
from gp_model import MultiChannelSparseGP
from ppo_proposal_node import GATE_DEFAULTS

REF_ARM = "gp_only"
DELTA_GATE = -5e-4
CI_UPPER_GATE = 0.0


def _cte(run: dict[str, Any]) -> float:
    return float(run["geometric_tracking"]["cross_track_rmse_m"])


def _tv(run: dict[str, Any]) -> float:
    return float(run["control_effort"]["tv_per_step"])


def _mean_metric(runs: list[dict[str, Any]], section: str, key: str) -> float | None:
    values = [(run.get(section) or {}).get(key) for run in runs]
    if not values or any(value is None or not math.isfinite(value) for value in values):
        return None
    return math.fsum(values) / len(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True,
                        help="cand.json：{\"candidates\": [{name, onnx, manifest, lambda_pi, lookahead}]}")
    parser.add_argument("--split", default="calibration", choices=("calibration", "final_test"))
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--decisions", type=int, default=301)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--base-domain-id", type=int, default=150)
    parser.add_argument("--source-hashes", default=str(DEFAULT_SOURCE_HASHES))
    parser.add_argument("--contract", default=str(CONTRACT))
    parser.add_argument("--out", default=str(R2_WORK_ROOT / "p6_selection"))
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--max-delta-e-per-m", type=float, default=None,
                        help="相对 gp_only 的平均单位进度推力平方积分增量上限（N²·s/m）")
    parser.add_argument("--min-progress-ratio", type=float, default=None,
                        help="候选平均进度与 gp_only 平均进度之比的下限")
    args = parser.parse_args(argv)

    contract_path = Path(args.contract).resolve()
    contract_sha256 = sha256_file(contract_path)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))["candidates"]
    if not cands:
        raise SystemExit("candidates 为空")
    seed_offsets = [int(x.strip()) for x in str(args.seeds).split(",") if x.strip()]

    pooled, _ = _load_r2_gps()
    gp_models: dict[str, MultiChannelSparseGP] = {}
    m = MultiChannelSparseGP.load(pooled)
    gp_models[m.snapshot_sha256] = m

    manifest = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    eps = sorted([e for e in manifest["episodes"] if e["split"] == args.split],
                 key=lambda e: e["episode_name"])

    arms = [REF_ARM] + [f"gp_{c['name']}" for c in cands]
    tasks: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for soff in seed_offsets:
        for base in eps:
            ep = dict(base)
            ep["seed"] = int(base["seed"]) + 10000 * soff
            tag = f"s{soff}_{base['episode_name']}"
            tasks.append((REF_ARM, ep, {"gp": pooled, "ppo": False, "lambda_pi": 0.0,
                                        "lookahead": "", "tag": tag}))
            for c in cands:
                tasks.append((f"gp_{c['name']}", ep, {
                    "gp": pooled, "ppo": True,
                    "lambda_pi": float(c.get("lambda_pi", 0.0005)),
                    "lookahead": str(c.get("lookahead", "") or ""),
                    "onnx": str(c.get("onnx") or ""),
                    "manifest": str(c.get("manifest") or ""),
                    "tag": tag,
                    **{name: c[name] for name in GATE_DEFAULTS if name in c},
                }))

    print(f"[P6] {len(cands)} candidates + {REF_ARM} x {len(seed_offsets)} seeds x {len(eps)} eps "
          f"= {len(tasks)} runs", flush=True)
    runs_by_arm, _tel = _run_batch(
        out_dir=out_dir / "runs", tasks=tasks, arm_names=arms, gp_models=gp_models,
        source_hashes=Path(args.source_hashes), workers=int(args.workers),
        base_domain_id=int(args.base_domain_id), stop_decisions=int(args.decisions),
        resume=not args.no_resume, contract_path=contract_path,
    )

    ref_runs = runs_by_arm[REF_ARM]
    ref_tags = [r["ep_tag"] for r in ref_runs]
    ref_e_per_m = _mean_metric(ref_runs, "control_effort", "energy_per_meter")
    ref_progress = _mean_metric(ref_runs, "geometric_tracking", "along_track_progress_m")
    ranking: list[dict[str, Any]] = []
    for c in cands:
        arm = f"gp_{c['name']}"
        runs = runs_by_arm[arm]
        if [r["ep_tag"] for r in runs] != ref_tags:
            raise ValueError(f"{arm} 的 episode 配对顺序与 {REF_ARM} 不一致")
        stats = paired_wilcoxon_and_bootstrap([_cte(r) for r in runs],
                                             [_cte(r) for r in ref_runs])
        energy_per_meter_mean = _mean_metric(runs, "control_effort", "energy_per_meter")
        progress_m_mean = _mean_metric(runs, "geometric_tracking", "along_track_progress_m")
        ranking.append({
            "name": c["name"],
            "arm": arm,
            "episodes": len(runs),
            "delta_cte_mean": float(stats["mean_diff"]),
            "ci95": [float(stats["bootstrap_ci95_low"]), float(stats["bootstrap_ci95_high"])],
            "ci95_upper": float(stats["bootstrap_ci95_high"]),
            "wilcoxon_p": float(stats["wilcoxon_p"]),
            "wins": int(stats["wins"]),
            "ties": int(stats["ties"]),
            "losses": int(stats["losses"]),
            "cte_mean": float(sum(_cte(r) for r in runs) / len(runs)),
            "tv_per_step": float(sum(_tv(r) for r in runs) / len(runs)),
            "checker_pass": sum(1 for r in runs if r["checker_passed"]),
            "energy_mean": _mean_metric(runs, "control_effort", "thrust_l2_dt"),
            "energy_per_meter_mean": energy_per_meter_mean,
            "delta_e_per_m_mean": (energy_per_meter_mean - ref_e_per_m
                                   if energy_per_meter_mean is not None and ref_e_per_m is not None else None),
            "progress_m_mean": progress_m_mean,
            "progress_ratio": (progress_m_mean / ref_progress
                               if progress_m_mean is not None and ref_progress is not None and ref_progress > 0.0
                               else None),
        })

    cte_passing = [r for r in ranking
                   if r["delta_cte_mean"] <= DELTA_GATE and r["ci95_upper"] < CI_UPPER_GATE]
    passing = [
        r for r in cte_passing
        if (args.max_delta_e_per_m is None or (
            r["delta_e_per_m_mean"] is not None and r["delta_e_per_m_mean"] <= args.max_delta_e_per_m
        ))
        and (args.min_progress_ratio is None or (
            r["progress_ratio"] is not None and r["progress_ratio"] >= args.min_progress_ratio
        ))
    ]
    if passing:
        best = min(passing, key=lambda r: (r["tv_per_step"], r["delta_cte_mean"]))
        selected: str | None = best["name"]
        reason = (f"{best['name']} 在 {best['episodes']} 个 {args.split} episode 上配对 "
                  f"ΔCTE={best['delta_cte_mean']:+.5f} m（95% CI 上界 {best['ci95_upper']:+.5f} < 0），"
                  f"W/T/L={best['wins']}/{best['ties']}/{best['losses']}")
    elif cte_passing:
        selected = None
        reason = "通过 ΔCTE 与 95% CI 门槛的候选均未满足启用的单位进度推力平方积分或进度门槛"
    else:
        selected = None
        closest = min(ranking, key=lambda r: r["delta_cte_mean"])
        reason = ("无候选带来可重复增益：最接近者 "
                  f"{closest['name']} ΔCTE={closest['delta_cte_mean']:+.5f} m "
                  f"（95% CI [{closest['ci95'][0]:+.5f},{closest['ci95'][1]:+.5f}]），"
                  f"未同时满足 Δ<= {DELTA_GATE} 与 CI 上界 < 0")

    gates = {"delta_cte_mean_max": DELTA_GATE, "ci95_upper_max": CI_UPPER_GATE}
    if args.max_delta_e_per_m is not None:
        gates["max_delta_e_per_m"] = args.max_delta_e_per_m
    if args.min_progress_ratio is not None:
        gates["min_progress_ratio"] = args.min_progress_ratio
    doc = {
        "schema": "scheme-a-ppo-candidate-selection-v1",
        "split": args.split,
        "seeds": seed_offsets,
        "decisions": int(args.decisions),
        "reference_arm": REF_ARM,
        "gp_snapshot": str(pooled),
        "contract": str(contract_path),
        "contract_sha256": contract_sha256,
        "gates": gates,
        "ranking": ranking,
        "selected": selected,
        "reason": reason,
    }
    (out_dir / "selection.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    if selected is not None:
        src = next(c for c in cands if c["name"] == selected)
        dst = out_dir / "selected"
        dst.mkdir(exist_ok=True)
        import shutil

        for key in ("onnx", "manifest", "model", "vecnormalize"):
            if src.get(key):
                p = Path(src[key])
                if p.is_file():
                    shutil.copy2(p, dst / p.name)
        (dst / "selection.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False,
                                                       sort_keys=True) + "\n", encoding="utf-8")

    lines = [f"# P6 候选选择（split={args.split}，{len(seed_offsets)} seeds x {len(eps)} eps）", "",
             f"仿真契约 `{contract_path.name}`", "",
             "| 候选 | ΔCTE (m) | 95% CI | CI 上界 | Wilcoxon p | W/T/L | CTE | TV/step | checker | "
             "推力平方积分 (N²·s) | 单位进度推力平方积分 (N²·s/m) | Δ单位进度推力平方积分 (N²·s/m) | 进度 (m) | 进度比 |",
             "|---|---:|---:|---:|---:|:---:|---:|---:|:---:|---:|---:|---:|---:|---:|"]
    for r in sorted(ranking, key=lambda x: x["delta_cte_mean"]):
        energy_cells = ["—" if r[key] is None else format(r[key], ".6g") for key in (
            "energy_mean", "energy_per_meter_mean", "delta_e_per_m_mean", "progress_m_mean", "progress_ratio",
        )]
        lines.append(
            f"| `{r['name']}` | {r['delta_cte_mean']:+.5f} | "
            f"[{r['ci95'][0]:+.5f},{r['ci95'][1]:+.5f}] | {r['ci95_upper']:+.5f} | "
            f"{r['wilcoxon_p']:.2e} | {r['wins']}/{r['ties']}/{r['losses']} | "
            f"{r['cte_mean']:.5f} | {r['tv_per_step']:.4f} | {r['checker_pass']}/{r['episodes']} | "
            + " | ".join(energy_cells) + " |")
    lines += ["", f"**selected**: `{selected}`", "", reason]
    if args.max_delta_e_per_m is not None:
        lines += ["", f"单位进度推力平方积分增量上限为 {args.max_delta_e_per_m} N²·s/m。"]
    if args.min_progress_ratio is not None:
        lines += ["", f"进度比下限为 {args.min_progress_ratio}。"]
    (out_dir / "selection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"selected": selected, "reason": reason,
                      "json": str(out_dir / "selection.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
