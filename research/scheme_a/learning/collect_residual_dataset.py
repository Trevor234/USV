#!/usr/bin/env python3
"""Generate plant/maneuver episode manifests and run Scheme A residual collection (WP3)."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from dataset_builder import HYDRO_KEYS, HydroParams, build_dataset


WORKTREE_ROOT = Path("/home/trevor/usv_scheme_a_wt")
DEFAULT_INSTALL_ROOT = WORKTREE_ROOT / "install/scheme_a/usv_research_safety_cpp/lib/usv_research_safety_cpp"
DEFAULT_CONTRACT = WORKTREE_ROOT / "research/scheme_a/src/usv_research_safety_cpp/model/contract_controlled_sim.json"
DEFAULT_PLAN = WORKTREE_ROOT / "research/scheme_a/src/usv_research_safety_cpp/model/research_model_plan.json"
RUNNER_SCRIPT = WORKTREE_ROOT / "research/scheme_a/src/usv_research_safety_cpp/scripts/run_scheme_a_closed_loop.py"
CHECKER_SCRIPT = WORKTREE_ROOT / "research/scheme_a/src/usv_research_safety_cpp/scripts/check_scheme_a_closed_loop.py"
BASELINE_SCRIPT = WORKTREE_ROOT / "research/scheme_a/scripts/capture_research_baseline.py"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plant_profile_files(scenarios: dict[str, Any], out_models_dir: Path) -> dict[str, Path]:
    """Materialize validated `plant_actual` JSON files for every configured profile."""
    out_models_dir.mkdir(parents=True, exist_ok=True)
    base = scenarios["base_nominal"]
    paths: dict[str, Path] = {}
    for name, cfg in scenarios["plant_profiles"].items():
        merged = dict(base)
        merged.update(cfg.get("overrides", {}))
        # Validate finiteness & keys via HydroParams before running plant binary.
        hydro = HydroParams.from_dict(merged)
        doc = {
            "schema": "scheme-a-plant-actual-v1",
            "profile_name": name,
            "description": cfg.get("description", ""),
            "plant_actual": hydro.to_dict(),
        }
        p = out_models_dir / f"{name}.json"
        p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths[name] = p
    return paths


def build_episode_plan(scenarios: dict[str, Any], mode: str) -> dict[str, list[dict[str, Any]]]:
    """Construct deterministic episode lists (`episodes` + optional `nominal_gate`)."""
    if mode == "pilot":
        stop_decisions = int(scenarios["pilot"]["stop_after_decisions"])
        mismatch_eps = []
        nom_eps = []
        for entry in scenarios["pilot"]["episodes"]:
            item = dict(entry, stop_after_decisions=stop_decisions)
            if item["split"] == "nominal_gate":
                nom_eps.append(item)
            else:
                mismatch_eps.append(item)
        return {"episodes": mismatch_eps, "nominal_gate": nom_eps}

    if mode != "full":
        raise ValueError(f"unsupported collection mode: {mode}")

    full_cfg = scenarios["full"]
    stop_decisions = int(full_cfg["stop_after_decisions"])
    train_profiles: list[str] = list(full_cfg["train_profiles"])
    train_maneuvers: list[str] = list(full_cfg["train_maneuvers"])
    cal_maneuvers: list[str] = list(full_cfg["calibration_maneuvers"])
    all_maneuvers: list[str] = list(scenarios["maneuvers"])

    mismatch_eps: list[dict[str, Any]] = []
    # Train: 36 episodes = 3 profiles * 4 maneuvers * 3 cruise/seed variations
    cruise_grid = [0.55, 0.72, 0.88]
    idx = 1
    for p_idx, profile in enumerate(train_profiles):
        for m_idx, maneuver in enumerate(train_maneuvers):
            for rep in range(3):
                seed = 1000 + p_idx * 100 + m_idx * 10 + rep
                cruise = None if maneuver == "speed_transition" else cruise_grid[rep]
                mismatch_eps.append({
                    "episode_name": f"ep_{idx:02d}_train_{profile}_{maneuver}_{rep}",
                    "split": "train",
                    "profile": profile,
                    "maneuver": maneuver,
                    "seed": seed,
                    "cruise_speed": cruise,
                    "stop_after_decisions": stop_decisions,
                })
                idx += 1

    # Calibration: 12 episodes = 3 profiles * 4 maneuvers (includes unseen right_turn & rate_limited_thrust_step)
    for p_idx, profile in enumerate(train_profiles):
        for m_idx, maneuver in enumerate(cal_maneuvers):
            seed = 2000 + p_idx * 100 + m_idx * 10
            cruise = None if maneuver in ("speed_transition", "rate_limited_thrust_step") else 0.75
            mismatch_eps.append({
                "episode_name": f"ep_{idx:02d}_calib_{profile}_{maneuver}",
                "split": "calibration",
                "profile": profile,
                "maneuver": maneuver,
                "seed": seed,
                "cruise_speed": cruise,
                "stop_after_decisions": stop_decisions,
            })
            idx += 1

    # Final Test: 12 episodes = 6 heldout_combination (all 6 maneuvers) + 6 heldout profile unseen maneuvers
    for m_idx, maneuver in enumerate(all_maneuvers):
        cruise = None if maneuver in ("speed_transition", "rate_limited_thrust_step") else 0.70
        mismatch_eps.append({
            "episode_name": f"ep_{idx:02d}_test_heldout_combination_{maneuver}",
            "split": "final_test",
            "profile": "heldout_combination",
            "maneuver": maneuver,
            "seed": 3000 + m_idx * 10,
            "cruise_speed": cruise,
            "stop_after_decisions": stop_decisions,
        })
        idx += 1

    for p_idx, profile in enumerate(train_profiles):
        for m_idx, maneuver in enumerate(("right_turn", "rate_limited_thrust_step")):
            cruise = None if maneuver == "rate_limited_thrust_step" else 0.80
            mismatch_eps.append({
                "episode_name": f"ep_{idx:02d}_test_{profile}_{maneuver}",
                "split": "final_test",
                "profile": profile,
                "maneuver": maneuver,
                "seed": 3500 + p_idx * 100 + m_idx * 10,
                "cruise_speed": cruise,
                "stop_after_decisions": stop_decisions,
            })
            idx += 1

    # Dedicated nominal zero-residual audit episodes (all 6 maneuvers)
    nom_eps: list[dict[str, Any]] = []
    for m_idx, maneuver in enumerate(all_maneuvers):
        cruise = None if maneuver in ("speed_transition", "rate_limited_thrust_step") else 0.70
        nom_eps.append({
            "episode_name": f"nom_{m_idx+1:02d}_{maneuver}",
            "split": "nominal_gate",
            "profile": "nominal",
            "maneuver": maneuver,
            "seed": 4000 + m_idx * 10,
            "cruise_speed": cruise,
            "stop_after_decisions": stop_decisions,
        })

    # Verify invariants: strict episode split & heldout_combination exclusive to final_test.
    assert sum(1 for e in mismatch_eps if e["split"] == "train") == 36
    assert sum(1 for e in mismatch_eps if e["split"] == "calibration") == 12
    assert sum(1 for e in mismatch_eps if e["split"] == "final_test") == 12
    assert all(e["split"] == "final_test" for e in mismatch_eps if e["profile"] == "heldout_combination")
    assert all(e["profile"] != "nominal" for e in mismatch_eps)
    return {"episodes": mismatch_eps, "nominal_gate": nom_eps}


def _run_one_episode(
    ep: dict[str, Any],
    *,
    run_dir: Path,
    plant_model_path: Path,
    install_root: Path,
    contract_path: Path,
    contract_hash: str,
    plan_path: Path,
    plan_hash: str,
    source_hashes_path: Path,
    ros_domain_id: int,
    max_attempts: int = 2,
) -> dict[str, Any]:
    import shutil

    env = dict(os.environ)
    env.setdefault("ROS_LOCALHOST_ONLY", "1")
    last_error = ""
    for attempt in range(max(1, max_attempts)):
        if run_dir.exists():
            shutil.rmtree(run_dir)
        domain = ros_domain_id + (17 if attempt > 0 else 0)
        cmd = [
            "/usr/bin/python3",
            str(RUNNER_SCRIPT),
            "--scenario", "pre_switch",
            "--out", str(run_dir),
            "--install-root", str(install_root),
            "--contract", str(contract_path),
            "--contract-hash", contract_hash,
            "--plan", str(plan_path),
            "--plan-sha256", plan_hash,
            "--source-hashes", str(source_hashes_path),
            "--stop-after-decisions", str(ep["stop_after_decisions"]),
            "--maneuver", str(ep["maneuver"]),
            "--maneuver-seed", str(ep["seed"]),
            "--dataset-source", "controlled_sim_actual",
            "--ros-domain-id", str(domain),
        ]
        if ep["profile"] != "nominal":
            cmd.extend(["--plant-model-file", str(plant_model_path)])
        if ep.get("cruise_speed") is not None:
            cmd.extend(["--cruise-speed", str(ep["cruise_speed"])])

        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            last_error = (
                f"Episode {ep['episode_name']} attempt {attempt+1} runner failed (rc={proc.returncode}): "
                f"stdout={proc.stdout[-500:]!r} stderr={proc.stderr[-500:]!r}"
            )
            continue

        chk = subprocess.run(
            [
                "/usr/bin/python3",
                str(CHECKER_SCRIPT),
                "--run", str(run_dir),
                "--plan", str(plan_path),
                "--contract", str(contract_path),
                "--source-hashes", str(source_hashes_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if chk.returncode == 0:
            run_doc = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            return {
                **ep,
                "run_dir": str(run_dir),
                "run_id": run_doc.get("run_id"),
                "plant_model_file": str(plant_model_path) if ep["profile"] != "nominal" else "",
                "checker_passed": True,
                "attempts": attempt + 1,
                "dataset_source": run_doc.get("dataset_source", "controlled_sim_actual"),
            }
        last_error = (
            f"Checker failed for {ep['episode_name']} attempt {attempt+1} (rc={chk.returncode}): "
            f"stdout={chk.stdout[-500:]!r} stderr={chk.stderr[-500:]!r}"
        )
    raise RuntimeError(last_error)


def _write_data_quality_report(
    out_dir: Path,
    mode: str,
    quality_mismatch: dict[str, Any],
    quality_nominal: dict[str, Any] | None,
) -> None:
    lines = [
        f"# Scheme A Residual Dataset Quality Report (`{mode}`)",
        "",
        "## Mismatch Dataset Totals",
        f"- Runs total: `{quality_mismatch['totals']['runs_total']}`, accepted: `{quality_mismatch['totals']['runs_accepted']}`, rejected: `{quality_mismatch['totals']['runs_rejected']}`",
        f"- OK receipts: `{quality_mismatch['totals']['ok_receipts']}`",
        f"- Admitted 0.2s windows: `{quality_mismatch['totals']['admitted_windows']}`",
        f"- Excluded windows: `{quality_mismatch['totals']['excluded_windows']}` (`{json.dumps(quality_mismatch['totals']['excluded_by_reason'], sort_keys=True)}`)",
        f"- Clock resync events: `{quality_mismatch['totals']['clock_resync_events']}`",
        "",
        "### Feature Coverage",
    ]
    for name, st in sorted(quality_mismatch.get("feature_coverage", {}).items()):
        lines.append(f"- `{name}` [{st['unit']}]: min={st['min']:.4f}, max={st['max']:.4f}, std={st['std']:.4f}")
    lines.append("")
    lines.append("### Mismatch Residual Statistics")
    for name, st in sorted(quality_mismatch.get("residual_stats", {}).items()):
        lines.append(
            f"- `{name}` [{st['unit']}]: rms={st['rms']:.6f}, max_abs={st['max_abs']:.6f}, mean={st['mean']:.6f}"
        )

    if quality_nominal is not None:
        lines.extend([
            "",
            "## Nominal Zero-Residual Gate",
            f"- Admitted windows: `{quality_nominal['totals']['admitted_windows']}` (excluded: `{quality_nominal['totals']['excluded_windows']}`)",
        ])
        for name, st in sorted(quality_nominal.get("residual_stats", {}).items()):
            lines.append(f"- `{name}` [{st['unit']}]: max_abs={st['max_abs']:.3e}")

    (out_dir / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("pilot", "full"))
    parser.add_argument("--out", required=True, help="Output directory for collected batch.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--base-domain-id", type=int, default=30)
    parser.add_argument("--resume", action="store_true", help="Reuse already PASS-checked episode dirs under --out/runs.")
    parser.add_argument("--install-root", default=str(DEFAULT_INSTALL_ROOT))
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--scenarios", default=str(SCENARIOS_PATH))
    args = parser.parse_args(argv)

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    plant_models = build_plant_profile_files(scenarios, out_dir / "plant_models")
    plan = build_episode_plan(scenarios, args.mode)

    # Capture current source_hashes matching active worktree before launching runs.
    meta_dir = out_dir / "baseline_meta"
    source_hashes_path = meta_dir / "source_hashes.json"
    if not (args.resume and source_hashes_path.is_file()):
        subprocess.run(
            [
                "/usr/bin/python3",
                str(BASELINE_SCRIPT),
                "--out", str(meta_dir),
                "--build-base", str(WORKTREE_ROOT / "build/scheme_a"),
                "--install-base", str(WORKTREE_ROOT / "install/scheme_a"),
            ],
            check=True,
        )
    contract_path = Path(args.contract).resolve()
    plan_path = Path(args.plan).resolve()
    install_root = Path(args.install_root).resolve()
    contract_hash = _sha256(contract_path)
    plan_hash = _sha256(plan_path)

    all_eps = list(plan["episodes"]) + list(plan["nominal_gate"])
    runs_root = out_dir / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    results_by_name: dict[str, dict[str, Any]] = {}
    pending_eps: list[tuple[int, dict[str, Any]]] = []
    if args.resume:
        for i, ep in enumerate(all_eps):
            rdir = runs_root / ep["episode_name"]
            if (rdir / "run.json").is_file():
                chk = subprocess.run(
                    [
                        "/usr/bin/python3",
                        str(CHECKER_SCRIPT),
                        "--run", str(rdir),
                        "--plan", str(plan_path),
                        "--contract", str(contract_path),
                        "--source-hashes", str(source_hashes_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if chk.returncode == 0:
                    run_doc = json.loads((rdir / "run.json").read_text(encoding="utf-8"))
                    plant_model_path = plant_models[ep["profile"]]
                    results_by_name[ep["episode_name"]] = {
                        **ep,
                        "run_dir": str(rdir),
                        "run_id": run_doc.get("run_id"),
                        "plant_model_file": str(plant_model_path) if ep["profile"] != "nominal" else "",
                        "checker_passed": True,
                        "attempts": 1,
                        "dataset_source": run_doc.get("dataset_source", "controlled_sim_actual"),
                    }
                    continue
            pending_eps.append((i, ep))
        print(
            f"[resume] reused {len(results_by_name)}/{len(all_eps)} passed runs; "
            f"re-running {len(pending_eps)} episodes",
            flush=True,
        )
    else:
        pending_eps = list(enumerate(all_eps))

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        futs = {}
        for i, ep in pending_eps:
            rdir = runs_root / ep["episode_name"]
            domain_id = args.base_domain_id + (i % 16)
            fut = pool.submit(
                _run_one_episode,
                ep,
                run_dir=rdir,
                plant_model_path=plant_models[ep["profile"]],
                install_root=install_root,
                contract_path=contract_path,
                contract_hash=contract_hash,
                plan_path=plan_path,
                plan_hash=plan_hash,
                source_hashes_path=source_hashes_path,
                ros_domain_id=domain_id,
            )
            futs[fut] = ep["episode_name"]

        for fut in as_completed(futs):
            name = futs[fut]
            res = fut.result()
            results_by_name[name] = res
            print(f"[collected] {name} -> {res['run_id']}", flush=True)

    mismatch_records = [results_by_name[ep["episode_name"]] for ep in plan["episodes"]]
    nominal_records = [results_by_name[ep["episode_name"]] for ep in plan["nominal_gate"]]

    ep_manifest = {
        "schema": "scheme-a-episode-manifest-v1",
        "mode": args.mode,
        "mismatch_episode_count": len(mismatch_records),
        "nominal_gate_episode_count": len(nominal_records),
        "episodes": mismatch_records + nominal_records,
    }
    (out_dir / "episode_manifest.json").write_text(
        json.dumps(ep_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    split_manifest = {
        "schema": "scheme-a-split-manifest-v1",
        "mode": args.mode,
        "split_counts": {
            s: sum(1 for r in mismatch_records if r["split"] == s)
            for s in sorted({r["split"] for r in mismatch_records})
        },
        "episodes": mismatch_records,
    }
    (out_dir / "split_manifest.json").write_text(
        json.dumps(split_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    nom_manifest = {
        "schema": "scheme-a-split-manifest-v1",
        "mode": f"{args.mode}_nominal_gate",
        "episodes": nominal_records,
    }
    (out_dir / "nominal_manifest.json").write_text(
        json.dumps(nom_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    quality_mismatch = build_dataset(
        [(Path(r["run_dir"]), r["split"]) for r in mismatch_records],
        out_dir / "dataset_mismatch",
        allow_legacy_v2=False,
    )
    quality_nominal = None
    if nominal_records:
        quality_nominal = build_dataset(
            [(Path(r["run_dir"]), "nominal_gate") for r in nominal_records],
            out_dir / "dataset_nominal",
            allow_legacy_v2=False,
        )

    _write_data_quality_report(out_dir, args.mode, quality_mismatch, quality_nominal)
    print(json.dumps({
        "mode": args.mode,
        "out": str(out_dir),
        "mismatch_admitted": quality_mismatch["totals"]["admitted_windows"],
        "nominal_admitted": quality_nominal["totals"]["admitted_windows"] if quality_nominal else 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
