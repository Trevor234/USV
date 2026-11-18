#!/usr/bin/env python3
"""WP6 closed-loop GP-NMPC + PPO transport verification suite."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
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
PLANT_DIR = WORK_ROOT / "full/plant_models"
GP_DIR = WORK_ROOT / "gp_models"
PPO_MODEL = Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx")
PPO_MANIFEST = Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.manifest.json")


def _base_cmd(
    *,
    out_dir: Path,
    stop_decisions: int,
    maneuver: str,
    seed: int,
    cruise_speed: float | None,
    plant_file: Path,
    ros_domain_id: int,
    gp_snapshot: Path | None = None,
    gp_schedule: Path | None = None,
    ppo_proposal: bool = False,
    lambda_pi: float = 0.0,
    source_hashes: Path = SOURCE_HASHES,
    align_tick_phase: bool = False,
) -> list[str]:
    cmd = [
        "/usr/bin/python3",
        str(RUNNER),
        "--scenario", "pre_switch",
        "--out", str(out_dir),
        "--install-root", str(INSTALL_ROOT),
        "--contract", str(CONTRACT),
        "--contract-hash", sha256_file(CONTRACT),
        "--plan", str(PLAN),
        "--plan-sha256", sha256_file(PLAN),
        "--source-hashes", str(source_hashes),
        "--stop-after-decisions", str(stop_decisions),
        "--maneuver", maneuver,
        "--maneuver-seed", str(seed),
        "--plant-model-file", str(plant_file),
        "--ros-domain-id", str(ros_domain_id),
    ]
    if cruise_speed is not None:
        cmd.extend(["--cruise-speed", str(cruise_speed)])
    if gp_snapshot is not None:
        cmd.extend(["--gp-snapshot", str(gp_snapshot), "--gp-snapshot-sha256", sha256_file(gp_snapshot)])
    if gp_schedule is not None:
        cmd.extend(["--gp-schedule", str(gp_schedule), "--gp-schedule-sha256", sha256_file(gp_schedule)])
    if ppo_proposal:
        cmd.extend([
            "--ppo-proposal",
            "--ppo-model", str(PPO_MODEL),
            "--ppo-manifest", str(PPO_MANIFEST),
            "--lambda-pi", str(lambda_pi),
        ])
    if align_tick_phase:
        cmd.append("--align-tick-phase")
    return cmd


def _run_verified_sync(
    *,
    run_dir: Path,
    dom: int,
    gp_models: dict[str, MultiChannelSparseGP],
    source_hashes: Path = SOURCE_HASHES,
    max_attempts: int = 2,
    reuse_existing: bool = False,
    **cmd_kwargs: Any,
) -> tuple[dict[str, Any], int]:
    import shutil

    if reuse_existing and (run_dir / "run.json").is_file():
        metrics = evaluate_closed_loop_run(
            run_dir, source_hashes=source_hashes, gp_models_by_sha=gp_models
        )
        if metrics["checker_passed"]:
            return metrics, dom + 1

    last_err = ""
    for attempt in range(max_attempts):
        if run_dir.exists():
            shutil.rmtree(run_dir)
        cmd = _base_cmd(out_dir=run_dir, ros_domain_id=dom, source_hashes=source_hashes, **cmd_kwargs)
        env = dict(os.environ)
        env["ROS_DOMAIN_ID"] = str(dom)
        dom += 1
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            last_err = f"attempt={attempt + 1} rc={proc.returncode} stdout={proc.stdout} stderr={proc.stderr}"
            continue
        metrics = evaluate_closed_loop_run(
            run_dir, source_hashes=source_hashes, gp_models_by_sha=gp_models
        )
        metrics["attempts"] = attempt + 1
        if metrics["checker_passed"]:
            return metrics, dom
        last_err = f"attempt={attempt + 1} checker_problems={metrics['checker_problems']}"
    raise RuntimeError(f"Verified closed-loop run failed for {run_dir}: {last_err}")


def _find_child_ppo_pids(parent_pid: int) -> list[int]:
    pids: list[int] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="ignore")
            rparen = stat.rfind(")")
            ppid = int(stat[rparen + 2 :].split()[1])
            if ppid != parent_pid:
                continue
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", errors="ignore")
            if "ppo_proposal_node.py" in cmdline:
                pids.append(pid)
        except OSError:
            continue
    return pids


def _run_with_ppo_kill(cmd: list[str], ros_domain_id: int, run_dir: Path) -> dict[str, Any]:
    if run_dir.exists():
        import shutil
        shutil.rmtree(run_dir)
    env = dict(os.environ)
    env["ROS_DOMAIN_ID"] = str(ros_domain_id)
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    reg_jsonl = run_dir / "regulator.source.jsonl"
    killed_pids: list[int] = []
    kill_at_tick: int | None = None
    seen_used = 0
    deadline = time.monotonic() + 90.0

    while proc.poll() is None and time.monotonic() < deadline:
        if reg_jsonl.is_file() and not killed_pids:
            used_ticks = []
            for line in reg_jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("type") == "decision" and row.get("ppo_proposal_used") is True:
                    used_ticks.append(int(row.get("tick") or 0))
            seen_used = len(used_ticks)
            if seen_used >= 12 and max(used_ticks) >= 18:
                child_pids = _find_child_ppo_pids(proc.pid)
                if child_pids:
                    kill_at_tick = max(used_ticks)
                    for cpid in child_pids:
                        os.kill(cpid, signal.SIGKILL)
                        killed_pids.append(cpid)
        time.sleep(0.25)

    stdout, stderr = proc.communicate(timeout=40)
    if proc.returncode != 0:
        raise RuntimeError(f"PPO kill run failed rc={proc.returncode}:\n{stdout}\n{stderr}")
    if not killed_pids:
        raise RuntimeError(f"Never located/killed ppo_proposal_node.py mid-run (seen_used={seen_used})")
    return {"killed_pids": killed_pids, "kill_observed_at_tick": kill_at_tick, "seen_used_before_kill": seen_used}


def _strip_traj(metrics: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in metrics.items() if k not in ("u_exec", "states_end", "decision_ticks")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(WORK_ROOT / "gp_nmpc_regression"))
    parser.add_argument("--source-hashes", default=str(SOURCE_HASHES))
    parser.add_argument("--plant-dir", default=str(PLANT_DIR))
    parser.add_argument("--gp-dir", default=str(GP_DIR))
    parser.add_argument("--align-tick-phase", action="store_true")
    parser.add_argument("--base-domain-id", type=int, default=31)
    parser.add_argument("--reuse-existing", action="store_true")
    args = parser.parse_args(argv)
    reuse = bool(args.reuse_existing)
    source_hashes = Path(args.source_hashes)
    plant_dir = Path(args.plant_dir)
    gp_dir = Path(args.gp_dir)
    align_phase = bool(args.align_tick_phase)
    sync_cfg = {"source_hashes": source_hashes, "align_tick_phase": align_phase}

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    dom = int(args.base_domain_id)

    gp_surge = gp_dir / "surge_damping_plus_15pct_sparse_m64.json"
    gp_mass = gp_dir / "mass_plus_10pct_sparse_m64.json"
    gp_pooled = gp_dir / "gp_snapshot.json"
    gp_models = {
        m.snapshot_sha256: m
        for m in (
            MultiChannelSparseGP.load(gp_surge),
            MultiChannelSparseGP.load(gp_mass),
            MultiChannelSparseGP.load(gp_pooled),
        )
    }

    # Schedules.
    sched_zero = out_root / "schedule_explicit_zero.json"
    sched_zero.write_text(
        json.dumps(
            {
                "schema": "scheme-a-gp-schedule-v1",
                "entries": [{"generation": 1, "first_target_tick": 1, "last_target_tick": None, "kind": "zero"}],
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    sched_hotswap = out_root / "schedule_hotswap.json"
    sched_hotswap.write_text(
        json.dumps(
            {
                "schema": "scheme-a-gp-schedule-v1",
                "entries": [
                    {"generation": 1, "first_target_tick": 1, "last_target_tick": 20, "kind": "zero"},
                    {"generation": 2, "first_target_tick": 21, "last_target_tick": 40, "kind": "file", "path": str(gp_surge), "sha256": sha256_file(gp_surge)},
                    {"generation": 3, "first_target_tick": 41, "last_target_tick": 60, "kind": "file", "path": str(gp_mass), "sha256": sha256_file(gp_mass)},
                    {"generation": 4, "first_target_tick": 61, "last_target_tick": None, "kind": "zero"},
                ],
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    results: dict[str, Any] = {}

    # (a) Nominal default vs explicit zero schedule.
    nom_default_dir = out_root / "a_nominal_default_zero"
    nom_explicit_dir = out_root / "a_nominal_explicit_zero"
    m_def, dom = _run_verified_sync(
        run_dir=nom_default_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=60, maneuver="straight", seed=1000, cruise_speed=0.72,
        plant_file=plant_dir / "nominal.json", **sync_cfg,
    )
    m_exp, dom = _run_verified_sync(
        run_dir=nom_explicit_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=60, maneuver="straight", seed=1000, cruise_speed=0.72,
        plant_file=plant_dir / "nominal.json", gp_schedule=sched_zero, **sync_cfg,
    )
    u0_def = np.asarray(m_def["first_candidate"]["first_control"], dtype=np.float64)
    u0_exp = np.asarray(m_exp["first_candidate"]["first_control"], dtype=np.float64)
    tt3_u_diff_a = float(np.max(np.abs(u0_def - u0_exp)))
    cte_diff_a = abs(
        m_def["geometric_tracking"]["cross_track_rmse_m"]
        - m_exp["geometric_tracking"]["cross_track_rmse_m"]
    )
    u_rmse_diff_a = abs(
        m_def["reference_tracking"]["u_rmse_mps"]
        - m_exp["reference_tracking"]["u_rmse_mps"]
    )
    a_ok = (
        m_def["checker_passed"] and m_exp["checker_passed"]
        and m_def["stage_residuals_max_abs"] == 0.0
        and m_exp["stage_residuals_max_abs"] == 0.0
        and m_def["first_candidate"]["gp_snapshot_sha256"] == m_exp["first_candidate"]["gp_snapshot_sha256"]
        and tt3_u_diff_a <= 1e-9
        and cte_diff_a <= 0.02
        and u_rmse_diff_a <= 0.02
    )
    assert a_ok, f"nominal zero equiv failed: tt3={tt3_u_diff_a}, cte={cte_diff_a}, u={u_rmse_diff_a}"
    results["a_nominal_zero_equivalence"] = {
        "passed": a_ok,
        "first_candidate_max_abs_u_diff": tt3_u_diff_a,
        "closed_loop_cte_rmse_diff_m": cte_diff_a,
        "closed_loop_u_rmse_diff_mps": u_rmse_diff_a,
        "default": _strip_traj(m_def),
        "explicit_zero": _strip_traj(m_exp),
    }

    # (b1) Single-plant mismatch surge_damping_plus_15pct (straight high-speed surge): Nominal NMPC vs GP-NMPC.
    surge_nom_dir = out_root / "b1_surge_nominal_nmpc"
    surge_gp_dir = out_root / "b1_surge_gp_nmpc"
    m_snom, dom = _run_verified_sync(
        run_dir=surge_nom_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=80, maneuver="straight", seed=1002, cruise_speed=0.88,
        plant_file=plant_dir / "surge_damping_plus_15pct.json", **sync_cfg,
    )
    m_sgp, dom = _run_verified_sync(
        run_dir=surge_gp_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=80, maneuver="straight", seed=1002, cruise_speed=0.88,
        plant_file=plant_dir / "surge_damping_plus_15pct.json", gp_snapshot=gp_surge, **sync_cfg,
    )
    assert m_sgp["gp_telemetry"]["local_approx_max_diff"] is not None
    results["b1_surge_mismatch_gp_vs_nominal"] = {
        "passed": bool(
            m_sgp["checker_passed"]
            and m_sgp["residual_accuracy"]["gp_model_vel_rmse"] < m_snom["residual_accuracy"]["zero_model_vel_rmse"]
            and m_sgp["geometric_tracking"]["along_track_progress_m"] > m_snom["geometric_tracking"]["along_track_progress_m"]
        ),
        "nominal_nmpc": _strip_traj(m_snom),
        "gp_nmpc": _strip_traj(m_sgp),
    }

    # (b2) Heldout combination mismatch: Nominal NMPC vs pooled gp_snapshot.json.
    held_nom_dir = out_root / "b2_heldout_nominal_nmpc"
    held_gp_dir = out_root / "b2_heldout_pooled_gp_nmpc"
    m_hnom, dom = _run_verified_sync(
        run_dir=held_nom_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=80, maneuver="right_turn", seed=3020, cruise_speed=0.7,
        plant_file=plant_dir / "heldout_combination.json", **sync_cfg,
    )
    m_hgp, dom = _run_verified_sync(
        run_dir=held_gp_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=80, maneuver="right_turn", seed=3020, cruise_speed=0.7,
        plant_file=plant_dir / "heldout_combination.json", gp_snapshot=gp_pooled, **sync_cfg,
    )
    assert m_hgp["gp_telemetry"]["local_approx_max_diff"] is not None
    results["b2_heldout_pooled_gp_vs_nominal"] = {
        "passed": bool(
            m_hgp["residual_accuracy"]["gp_model_vel_rmse"] < m_hnom["residual_accuracy"]["zero_model_vel_rmse"]
        ),
        "nominal_nmpc": _strip_traj(m_hnom),
        "pooled_gp_nmpc": _strip_traj(m_hgp),
    }

    # (c) Finite GP schedule hot-swap (zero -> GP1 -> GP2 -> zero).
    hotswap_dir = out_root / "c_gp_hotswap"
    m_hot, dom = _run_verified_sync(
        run_dir=hotswap_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=80, maneuver="right_turn", seed=3600, cruise_speed=0.8,
        plant_file=plant_dir / "surge_damping_plus_15pct.json", gp_schedule=sched_hotswap, **sync_cfg,
    )
    timeline = m_hot["gp_telemetry"]["generation_timeline"]
    gens = [e["generation"] for e in timeline]
    shas = [e["sha256"] for e in timeline]
    hotswap_ok = (
        m_hot["checker_passed"]
        and gens == [1, 2, 3, 4]
        and shas[0] == shas[3]
        and shas[1] != shas[0]
        and shas[2] != shas[0]
        and shas[1] != shas[2]
        and timeline[0]["last_tick"] <= 20
        and timeline[1]["first_tick"] == 21 and timeline[1]["last_tick"] == 40
        and timeline[2]["first_tick"] == 41 and timeline[2]["last_tick"] == 60
        and timeline[3]["first_tick"] == 61
    )
    assert hotswap_ok, f"hotswap timeline invalid: {timeline}"
    results["c_gp_hotswap_schedule"] = {
        "passed": hotswap_ok,
        "timeline": timeline,
        "run": _strip_traj(m_hot),
    }

    # (d1) PPO proposal enabled with lambda_pi = 0.0 matches GP-NMPC.
    ppo_zero_dir = out_root / "d1_ppo_lambda0_identity"
    m_pzero, dom = _run_verified_sync(
        run_dir=ppo_zero_dir, dom=dom, gp_models=gp_models, reuse_existing=reuse,
        stop_decisions=80, maneuver="straight", seed=1002, cruise_speed=0.88,
        plant_file=plant_dir / "surge_damping_plus_15pct.json", gp_snapshot=gp_surge,
        ppo_proposal=True, lambda_pi=0.0, **sync_cfg,
    )
    u0_sgp = np.asarray(m_sgp["first_candidate"]["first_control"], dtype=np.float64)
    u0_pzero = np.asarray(m_pzero["first_candidate"]["first_control"], dtype=np.float64)
    tt3_u_diff_d1 = float(np.max(np.abs(u0_pzero - u0_sgp)))
    cte_diff_d1 = abs(
        m_pzero["geometric_tracking"]["cross_track_rmse_m"]
        - m_sgp["geometric_tracking"]["cross_track_rmse_m"]
    )
    u_rmse_diff_d1 = abs(
        m_pzero["reference_tracking"]["u_rmse_mps"]
        - m_sgp["reference_tracking"]["u_rmse_mps"]
    )
    d1_ok = (
        m_pzero["checker_passed"]
        and m_pzero["ppo_telemetry"]["used_ticks_count"] >= 70
        and tt3_u_diff_d1 <= 1e-8
        and cte_diff_d1 <= 0.04
        and u_rmse_diff_d1 <= 0.04
    )
    assert d1_ok, f"d1 lambda=0 identity failed: tt3={tt3_u_diff_d1}, cte={cte_diff_d1}, used={m_pzero['ppo_telemetry']}"
    results["d1_ppo_lambda0_identity"] = {
        "passed": d1_ok,
        "first_candidate_max_abs_u_diff": tt3_u_diff_d1,
        "closed_loop_cte_rmse_diff_m": cte_diff_d1,
        "closed_loop_u_rmse_diff_mps": u_rmse_diff_d1,
        "run": _strip_traj(m_pzero),
    }

    # (d2) PPO proposal killed mid-run fault tolerance.
    ppo_kill_dir = out_root / "d2_ppo_kill_fault_tolerance"
    if reuse and (ppo_kill_dir / "run.json").is_file():
        kill_meta = {"reused_from_disk": True}
    else:
        kill_meta = _run_with_ppo_kill(
            _base_cmd(out_dir=ppo_kill_dir, stop_decisions=60, maneuver="right_turn", seed=3600, cruise_speed=0.8, plant_file=plant_dir / "surge_damping_plus_15pct.json", ros_domain_id=dom, gp_snapshot=gp_surge, ppo_proposal=True, lambda_pi=0.15, source_hashes=source_hashes, align_tick_phase=align_phase),
            dom,
            ppo_kill_dir,
        )
    dom += 1
    m_kill = evaluate_closed_loop_run(ppo_kill_dir, source_hashes=source_hashes, gp_models_by_sha=gp_models)
    rej = m_kill["ppo_telemetry"]["reject_reason_counts"]
    post_kill_candidate_ticks = sum(
        1 for d in (json.loads(l) for l in (ppo_kill_dir / "regulator.source.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
        if d.get("type") == "decision"
        and int(d.get("tick") or 0) > int(m_kill["ppo_telemetry"]["used_last_tick"] or 0)
        and d.get("control_source") == "candidate"
    )
    d2_ok = (
        m_kill["checker_passed"]
        and m_kill["skipped_ticks_total"] == 0
        and m_kill["ppo_telemetry"]["used_ticks_count"] >= 12
        and len(rej) > 0
        and ("ppo_steady_stale" in rej or "ppo_missing" in rej)
        and post_kill_candidate_ticks >= 25
        and m_kill["ppo_telemetry"]["used_last_tick"] < m_kill["decisions_total"] - 5
    )
    assert d2_ok, f"d2 ppo kill fault tolerance failed: post_kill={post_kill_candidate_ticks}, {m_kill['ppo_telemetry']}"
    results["d2_ppo_kill_fault_tolerance"] = {
        "passed": d2_ok,
        "post_kill_candidate_ticks": post_kill_candidate_ticks,
        "kill_meta": kill_meta,
        "run": _strip_traj(m_kill),
    }

    all_passed = all(bool(v.get("passed")) for v in results.values())
    report = {
        "schema": "scheme-a-wp6-regression-v1",
        "all_passed": all_passed,
        "results": results,
    }
    report_path = out_root / "wp6_regression_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": all_passed, "report": str(report_path)}, ensure_ascii=False))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
