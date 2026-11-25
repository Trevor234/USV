#!/usr/bin/env python3
"""Evaluate Scheme A energy contracts against the archived P6 runs."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import statistics
from typing import Any

from closed_loop_metrics import evaluate_closed_loop_run, sha256_file
from diagnose_gp_regression import paired_wilcoxon_and_bootstrap
from eval_fusion_arms import CONTRACT, PPO_MANIFEST, PPO_MODEL, SPLIT_MANIFEST
from eval_r2_calib import _load_r2_gps, _run_batch
from gp_model import MultiChannelSparseGP


WORK_ROOT = SPLIT_MANIFEST.parents[2] / "scheme_A_energy_opt_20261122_work"
HISTORY_ROOT = WORK_ROOT.parent / "scheme_A_ppo_fusion_opt_work"
HISTORY_ARMS = {"gp_only": "gp_only", "gp_ppo_v5_v2": "gp_v5_s4_dr"}
CANDIDATES = ("E2_optA_lead01", "E1_lead02", "E3_lead00")
LAMBDA_PI = 0.0005
LOOKAHEAD = "0.4,0.8,1.4,2.2,3.2,4.4,5.8,7.5"
COUNT_METRICS = ("checker_pass", "deadline_150ms_misses", "deadline_200ms_misses")
METRICS = {
    "cte_m": ("geometric_tracking", "cross_track_rmse_m"),
    "progress_m": ("geometric_tracking", "along_track_progress_m"),
    "speed_rmse_mps": ("geometric_tracking", "speed_rmse_mps"),
    **{key: ("control_effort", key) for key in (
        "thrust_l2_dt", "energy_per_meter", "common_mode_l2_dt", "diff_mode_l2_dt",
        "diff_mode_fraction", "opposing_thrust_fraction", "tv_per_step",
    )},
    **{key: ("latency_ms", key) for key in COUNT_METRICS[1:]},
}
METRIC_KEYS = (*METRICS, "checker_pass")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _episode_pairs(split: str, seed_offsets: list[int]) -> dict[str, dict[str, Any]]:
    episodes = sorted(
        (ep for ep in _read_json(SPLIT_MANIFEST)["episodes"] if ep["split"] == split),
        key=lambda ep: ep["episode_name"],
    )
    pairs = {
        f"s{offset}_{ep['episode_name']}": dict(ep, seed=int(ep["seed"]) + 10000 * offset)
        for offset in seed_offsets
        for ep in episodes
    }
    if len(episodes) != 12 or len(pairs) != 12 * len(seed_offsets):
        raise ValueError(f"Expected 12 unique manifest episodes for {split}")
    return pairs


def _metric_row(run: dict[str, Any], ep: dict[str, Any]) -> dict[str, Any]:
    if run["seed"] != ep["seed"] or run["maneuver"] != ep["maneuver"]:
        raise ValueError(f"Episode identity mismatch in {run['run_dir']}")
    if run["decisions_total"] < ep["stop_after_decisions"]:
        raise ValueError(f"Incomplete run in {run['run_dir']}")
    metrics = {key: run[section][field] for key, (section, field) in METRICS.items()}
    if any(not math.isfinite(value) for value in metrics.values()):
        raise ValueError(f"Non-finite metrics in {run['run_dir']}")
    return {
        **metrics,
        "checker_pass": int(run["checker_passed"]),
        "run_dir": run["run_dir"],
        "run_id": run["run_id"],
        "seed": run["seed"],
        "maneuver": run["maneuver"],
        "decisions_total": run["decisions_total"],
        "admitted_windows": run["admitted_windows"],
        "ppo_used_ticks": run["ppo_telemetry"]["used_ticks_count"],
    }


def _historical_runs(
    split: str, episodes: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    stage = "p6" if split == "calibration" else "p6_final_test"
    history = HISTORY_ROOT / stage / "runs"
    base_sha = sha256_file(CONTRACT)

    def read_run(arm: str, tag: str) -> dict[str, Any]:
        run_dir = history / HISTORY_ARMS[arm] / tag
        run_doc = _read_json(run_dir / "run.json")
        check = _read_json(run_dir / "check.json")
        if not run_doc.get("run_id") or check.get("run_id") != run_doc["run_id"]:
            raise ValueError(f"Historical checker identity mismatch in {run_dir}")
        if sha256_file(run_dir / "contract.json") != base_sha:
            raise ValueError(f"Historical E0 contract mismatch in {run_dir}")
        run = evaluate_closed_loop_run(run_dir, source_hashes=None, reuse_verified_check_json=True)
        return _metric_row(run, episodes[tag])

    print(f"Reading {len(episodes) * len(HISTORY_ARMS)} historical runs from {stage}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {
            arm: {tag: pool.submit(read_run, arm, tag) for tag in episodes}
            for arm in HISTORY_ARMS
        }
        return {
            f"E0_base/{arm}": {tag: future.result() for tag, future in runs.items()}
            for arm, runs in pending.items()
        }


def _aggregate(runs: dict[str, Any]) -> dict[str, Any]:
    summary = {key: statistics.mean(row[key] for row in runs.values()) for key in METRIC_KEYS}
    summary.update({key: sum(row[key] for row in runs.values()) for key in COUNT_METRICS})
    counts = [row["decisions_total"] for row in runs.values()]
    return {"runs": len(runs), "decisions_min": min(counts), "decisions_max": max(counts), **summary}


def _paired(runs: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    if runs.keys() != ref.keys():
        raise ValueError("Paired arms must cover the same episode and seed tags")
    paired = {
        key: paired_wilcoxon_and_bootstrap(
            [runs[tag][key] for tag in runs], [ref[tag][key] for tag in runs]
        )
        for key in METRIC_KEYS
    }
    for key in ("progress_m", "checker_pass"):
        stats = paired[key]
        stats["wins"], stats["losses"] = stats["losses"], stats["wins"]
    return paired


def _write_report(out: Path, report: dict[str, Any]) -> None:
    calib = report["mode"] == "calib"
    stem = "calib_report" if calib else "phase1_report"
    lines = [
        "# Scheme A energy calibration" if calib else "# Scheme A final test",
        "",
        "Values are episode means, with checker passes and deadline misses reported as counts.",
        "E is the integral of squared thrust. E/m is the mean of the per-run ratios.",
        "",
        "| Contract / arm | Runs | CTE (m) | Progress (m) | Speed RMSE (m/s) | E (N²·s) | E/m |"
        " CM (N²·s) | DM (N²·s) | DM share | Opposing | TV/step (N) | Checker | >150 / >200 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm, row in report["summary"].items():
        lines.append(
            f"| {arm} | {row['runs']} | {row['cte_m']:.5f} | {row['progress_m']:.3f} |"
            f" {row['speed_rmse_mps']:.5f} | {row['thrust_l2_dt']:.2f} | {row['energy_per_meter']:.3f} |"
            f" {row['common_mode_l2_dt']:.2f} | {row['diff_mode_l2_dt']:.2f} | {row['diff_mode_fraction']:.2%} |"
            f" {row['opposing_thrust_fraction']:.2%} | {row['tv_per_step']:.4f} |"
            f" {row['checker_pass']}/{row['runs']} |"
            f" {row['deadline_150ms_misses']} / {row['deadline_200ms_misses']} |"
        )
    lines += [
        "", "## Paired differences", "",
        "Values are candidate minus reference, with percentile-bootstrap 95% confidence intervals."
        " The JSON includes the two-sided Wilcoxon results and all paired metrics.",
        "",
        "| Candidate vs reference | ΔCTE (m) | Δprogress (m) | Δspeed RMSE (m/s) | ΔE/m |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for comparison, metrics in report["paired"].items():
        cells = []
        for key in ("cte_m", "progress_m", "speed_rmse_mps", "energy_per_meter"):
            stats = metrics[key]
            cells.append(
                f"{stats['mean_diff']:+.5f} [{stats['bootstrap_ci95_low']:+.5f},"
                f" {stats['bootstrap_ci95_high']:+.5f}]"
            )
        lines.append(f"| {comparison} | " + " | ".join(cells) + " |")
    lines += ["", "## Deadline checks", ""]
    misses = report["deadline_retries"]
    if misses:
        lines.append("Affected calibration runs were repeated with four workers. Initial counts and both run paths are in the JSON.")
        lines += ["", "| Arm | Episode / seed | Initial >150 / >200 ms | Rerun >150 / >200 ms |",
                  "| --- | --- | ---: | ---: |"]
        for retry in misses:
            before, after = retry["initial"], retry["rerun"]
            lines.append(
                f"| {retry['arm']} | {retry['tag']} |"
                f" {before['deadline_150ms_misses']} / {before['deadline_200ms_misses']} |"
                f" {after['deadline_150ms_misses']} / {after['deadline_200ms_misses']} |"
            )
    else:
        lines.append("No calibration deadline reruns were needed." if calib else
                     "Final-test deadline counts are reported in the summary table.")
    (out / f"{stem}.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (out / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("calib", "final"))
    parser.add_argument("--contracts", nargs="+", type=Path, help="Calibration contract JSON files.")
    parser.add_argument("--contract", type=Path, help="Frozen final-test contract JSON file.")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--source-hashes", type=Path, default=WORK_ROOT / "meta/source_hashes.json")
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--base-domain-id", type=int, default=150)
    args = parser.parse_args(argv)

    calib = args.mode == "calib"
    split = "calibration" if calib else "final_test"
    if (calib and args.contract) or (not calib and (not args.contract or args.contracts)):
        parser.error("Use --contracts for calibration or --contract for final test")
    try:
        seeds = sorted(int(seed) for seed in args.seeds.split(","))
    except ValueError:
        parser.error("--seeds requires comma-separated integer offsets")
    if min(seeds) < 0 or len(seeds) != len(set(seeds)):
        parser.error("--seeds requires distinct nonnegative offsets")
    if args.workers < 1:
        parser.error("--workers must be positive")

    root = WORK_ROOT.resolve()
    out = (args.out or root / split).resolve()
    if not out.is_relative_to(root):
        parser.error("--out must be inside the energy workspace")
    # The inherited runner writes caches beside the run logs. Reject output
    # symlinks so it cannot follow one into the archived P6 workspaces.
    for directory, dirs, files in os.walk(out):
        if any((Path(directory) / name).is_symlink() for name in (*dirs, *files)):
            parser.error(f"Symlink in output tree: {directory}")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["ROS_LOG_DIR"] = str(out / "ros_logs")

    if calib:
        paths = args.contracts or [root / "contracts" / f"{name}.json" for name in CANDIDATES]
    else:
        paths = [args.contract]
    contracts = {path.stem: path.resolve(strict=True) for path in paths}
    if len(contracts) != len(paths) or "E0_base" in contracts:
        parser.error("Contract files must have unique stems distinct from E0_base")
    source_hashes = args.source_hashes.resolve(strict=True)
    episodes = _episode_pairs(split, seeds)
    stop_decisions, = {int(ep["stop_after_decisions"]) for ep in episodes.values()}
    pooled, _ = _load_r2_gps()
    model = MultiChannelSparseGP.load(pooled)
    ppo_settings = {"ppo": True, "lambda_pi": LAMBDA_PI, "lookahead": LOOKAHEAD,
                    "onnx": PPO_MODEL, "manifest": PPO_MANIFEST}
    if calib:
        arms = {
            f"{name}/{arm}": {"contract": contract, "gp": pooled,
                             **(ppo_settings if arm == "gp_ppo_v5_v2" else {})}
            for name, contract in contracts.items()
            for arm in HISTORY_ARMS
        }
    else:
        contract, = contracts.values()
        arms = {
            "nominal_energy": {"contract": contract, "gp": None},
            "gp_only_energy": {"contract": contract, "gp": pooled},
            "gp_ppo_v5_v2_energy": {"contract": contract, "gp": pooled, **ppo_settings},
        }
    tasks = [(arm, ep, dict(spec, tag=tag)) for tag, ep in episodes.items() for arm, spec in arms.items()]
    runs = _historical_runs(split, episodes)
    batch_args = dict(
        gp_models={model.snapshot_sha256: model}, source_hashes=source_hashes,
        base_domain_id=args.base_domain_id, stop_decisions=stop_decisions, resume=True,
    )
    print(f"Running {len(tasks)} {split} episodes across {len(arms)} arms with {args.workers} workers", flush=True)
    batch, _ = _run_batch(out_dir=out / "runs", tasks=tasks, arm_names=list(arms),
                          workers=args.workers, **batch_args)
    for arm, rows in batch.items():
        runs[arm] = {row["ep_tag"]: _metric_row(row, episodes[row["ep_tag"]]) for row in rows}

    retries = []
    if calib:
        affected = [task for task in tasks if runs[task[0]][task[2]["tag"]]["deadline_150ms_misses"]]
        if affected:
            print(f"Rerunning {len(affected)} deadline-affected episodes with four workers", flush=True)
            repeat, _ = _run_batch(out_dir=out / "deadline_reruns", tasks=affected,
                                   arm_names=list(arms), workers=4, **batch_args)
            for arm, rows in repeat.items():
                for row in rows:
                    tag = row["ep_tag"]
                    rerun = _metric_row(row, episodes[tag])
                    retries.append({"arm": arm, "tag": tag, "initial": runs[arm][tag], "rerun": rerun})
                    runs[arm][tag] = rerun

    if calib:
        comparisons = [(f"{name}/{arm}", f"E0_base/{arm}") for name in contracts for arm in HISTORY_ARMS]
        comparisons += [(f"{name}/gp_ppo_v5_v2", f"{name}/gp_only") for name in ("E0_base", *contracts)]
        if CANDIDATES[0] in contracts:
            comparisons += [
                (f"{CANDIDATES[0]}/{arm}", f"{name}/{arm}")
                for name in contracts if name != CANDIDATES[0] for arm in HISTORY_ARMS
            ]
    else:
        comparisons = [(f"{arm}_energy", f"E0_base/{arm}") for arm in HISTORY_ARMS]
        comparisons += [("gp_ppo_v5_v2_energy", "gp_only_energy")]
        comparisons += [(f"{arm}_energy", "nominal_energy") for arm in HISTORY_ARMS]

    report = {
        "schema": "scheme-a-energy-evaluation-v1",
        "mode": args.mode, "split": split, "seed_offsets": seeds,
        "workers": args.workers, "base_domain_id": args.base_domain_id,
        "stop_decisions": stop_decisions, "source_hashes": str(source_hashes),
        "source_hashes_sha256": sha256_file(source_hashes),
        "split_manifest": str(SPLIT_MANIFEST), "split_manifest_sha256": sha256_file(SPLIT_MANIFEST),
        "contracts": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in {"E0_base": CONTRACT, **contracts}.items()
        },
        "gp_snapshot": str(pooled), "gp_snapshot_sha256": sha256_file(pooled),
        "ppo": {"model": str(PPO_MODEL), "model_sha256": sha256_file(PPO_MODEL),
                "manifest": str(PPO_MANIFEST), "manifest_sha256": sha256_file(PPO_MANIFEST),
                "lambda_pi": LAMBDA_PI, "lookahead_m": [float(value) for value in LOOKAHEAD.split(",")]},
        "summary": {arm: _aggregate(rows) for arm, rows in runs.items()},
        "paired": {f"{arm} vs {ref}": _paired(runs[arm], runs[ref]) for arm, ref in comparisons},
        "deadline_retries": retries,
        "runs": runs,
    }
    _write_report(out, report)
    return int(any(row["checker_pass"] != row["runs"] or row["deadline_150ms_misses"]
                   for arm, row in report["summary"].items() if arm in arms))


if __name__ == "__main__":
    raise SystemExit(main())
