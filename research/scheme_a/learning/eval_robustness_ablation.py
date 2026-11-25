#!/usr/bin/env python3
"""Evaluate frozen Scheme A controllers under paired wrench and navigation noise."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from functools import cache
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
from typing import Any

import numpy as np

from closed_loop_metrics import path_polyline_metrics, sha256_file
from diagnose_gp_regression import paired_wilcoxon_and_bootstrap
from eval_fusion_arms import SPLIT_MANIFEST, WORKTREE
from eval_r2_calib import R2_GP_DIR
from fusion_controller import FusionController, load_pooled_gp
from fusion_solver import DEFAULT_LIB_PATH, FusionSolver, FusionSolverError
from maneuver_reference import generate_maneuver_path_and_profile
from ppo_proposal_node import GATE_DEFAULTS, SCHEME_A_LOOKAHEAD, TICK_NS, ProposalEngine
from usv_rl.dynamics import HydroParams, USVDynamicModel, wrap_angle
from usv_rl.observation import apply_thrust_limits

CONTRACT = WORKTREE / "research/scheme_a/src/usv_research_safety_cpp/model/contract_controlled_sim_energy.json"
GP_POOLED = R2_GP_DIR / "pooled/gp_snapshot.json"
POLICY_ROOT = Path("/home/trevor/USV/artifacts/rl_models")
DT = TICK_NS / 1e9
DEFAULT_TICKS = 301
THRUST_LIMIT = 25.0
THRUST_RATE = 80.0
CTE_SUCCESS_LIMIT = 3.0
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 42

WRENCH_PRESETS = {
    "W0": dict(name="none", F0=0.0, F1=0.0, F2=0.0, w1=0.0, w2=0.0,
               b_r_abs=0.0, M1=0.0, M2=0.0, wr1=0.0, wr2=0.0),
    "W1": dict(name="mod", F0=1.2, F1=0.8, F2=0.6, w1=0.35, w2=1.25,
               b_r_abs=0.08, M1=0.12, M2=0.10, wr1=0.40, wr2=1.30),
    "W2": dict(name="strong", F0=2.2, F1=1.4, F2=1.0, w1=0.35, w2=1.25,
               b_r_abs=0.15, M1=0.22, M2=0.18, wr1=0.40, wr2=1.30),
}
NOISE_PRESETS = {
    "N0": ("none", (0.0,) * 6),
    "N1": ("rtk", (0.015, 0.015, math.radians(0.5), 0.02, 0.02, 0.01)),
    "N2": ("degraded", (0.030, 0.030, math.radians(1.0), 0.04, 0.04, 0.02)),
}
REGIMES = {
    "R0_clean": ("W0", "N0"),
    "R1_wrench_mod": ("W1", "N0"),
    "R2_wrench_strong": ("W2", "N0"),
    "R3_noise_rtk": ("W0", "N1"),
    "R4_combined_nominal": ("W1", "N1"),
    "R5_combined_harsh": ("W2", "N2"),
}


@dataclass(frozen=True)
class Arm:
    label: str
    gp: bool = True
    onnx: Path | None = None
    lambda_pi: float = 0.0
    gate_mode: str = "none"
    lookahead: tuple[float, ...] = SCHEME_A_LOOKAHEAD

    @property
    def manifest(self) -> Path | None:
        return self.onnx.with_suffix(".manifest.json") if self.onnx is not None else None


V7_ONNX = POLICY_ROOT / "v7_fusion_v6/s4_dr/policy_physical_n.onnx"
ARMS = {
    "nominal_nmpc": Arm("Nominal NMPC", gp=False),
    "gp_only": Arm("GP only"),
    "gp_v6_fusion_direct_best_001": Arm(
        "GP + v6", onnx=POLICY_ROOT / "v6_fusion_direct/best/policy_physical_n.onnx",
        lambda_pi=0.001,
    ),
    "gp_v7_v6_s4dr_l005_curv": Arm(
        "GP + v7 (curv)", onnx=V7_ONNX, lambda_pi=0.005, gate_mode="curv_err",
    ),
    "gp_v7_v6_s4dr_l005_none": Arm("GP + v7 (none)", onnx=V7_ONNX, lambda_pi=0.005),
}


def _paired_rng(kind: str, level: str, episode_seed: int) -> np.random.Generator:
    digest = hashlib.sha256(f"{kind}:{level}:{int(episode_seed)}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest, "big"))


@dataclass(frozen=True)
class ExternalWrenchProfile:
    theta0: float
    theta1: float
    theta2: float
    phi1: float
    phi2: float
    b_r: float
    M1: float
    M2: float
    wr1: float
    wr2: float
    phir1: float
    phir2: float
    F0: float
    F1: float
    F2: float
    w1: float
    w2: float

    @classmethod
    def from_preset(cls, level: str, episode_seed: int) -> ExternalWrenchProfile:
        preset = WRENCH_PRESETS[level].copy()
        preset.pop("name")
        rng = _paired_rng("wrench", level, episode_seed)
        theta0, theta1, theta2 = rng.uniform(-math.pi, math.pi, size=3)
        phi1, phi2, phir1, phir2 = rng.uniform(0.0, math.tau, size=4)
        yaw_bias = rng.choice([-1.0, 1.0]) * preset.pop("b_r_abs")
        return cls(
            theta0=theta0, theta1=theta1, theta2=theta2, phi1=phi1, phi2=phi2,
            phir1=phir1, phir2=phir2, b_r=yaw_bias, **preset,
        )

    def world_force(self, t_s: float) -> tuple[float, float]:
        f1 = self.F1 * math.sin(self.w1 * t_s + self.phi1)
        f2 = self.F2 * math.sin(self.w2 * t_s + self.phi2)
        return (
            self.F0 * math.cos(self.theta0) + f1 * math.cos(self.theta1) + f2 * math.cos(self.theta2),
            self.F0 * math.sin(self.theta0) + f1 * math.sin(self.theta1) + f2 * math.sin(self.theta2),
        )

    def yaw_moment(self, t_s: float) -> float:
        return (self.b_r + self.M1 * math.sin(self.wr1 * t_s + self.phir1)
                + self.M2 * math.sin(self.wr2 * t_s + self.phir2))

    def body_wrench(self, t_s: float, psi: float) -> np.ndarray:
        fx, fy = self.world_force(t_s)
        cos_psi, sin_psi = math.cos(psi), math.sin(psi)
        return np.array([cos_psi * fx + sin_psi * fy, -sin_psi * fx + cos_psi * fy,
                         self.yaw_moment(t_s)], dtype=np.float64)

    def mirrored(self) -> ExternalWrenchProfile:
        return replace(
            self, theta0=-self.theta0, theta1=-self.theta1, theta2=-self.theta2,
            b_r=-self.b_r, M1=-self.M1, M2=-self.M2,
        )


@dataclass(frozen=True)
class NavigationNoiseModel:
    eta_sequence: np.ndarray

    @classmethod
    def from_preset(
        cls, level: str, episode_seed: int, ticks: int = DEFAULT_TICKS,
    ) -> NavigationNoiseModel:
        _, sigmas = NOISE_PRESETS[level]
        rng = _paired_rng("noise", level, episode_seed)
        eta = rng.normal(scale=sigmas, size=(ticks, 6))
        eta.setflags(write=False)
        return cls(eta)

    def corrupt(self, state6: np.ndarray, tick: int) -> np.ndarray:
        state = np.asarray(state6, dtype=np.float64) + self.eta_sequence[tick]
        heading = wrap_angle(float(state[2]))
        state[2] = math.pi if heading == -math.pi else heading
        return state


def forward_with_wrench(
    dyn: USVDynamicModel,
    state6: np.ndarray,
    control2: np.ndarray,
    wrench: ExternalWrenchProfile | None,
    t0_s: float,
) -> np.ndarray:
    """Advance the plant with the wrench evaluated at each RK4 stage."""
    if wrench is None:
        return dyn.forward(state6, control2)

    p = dyn.params
    m11 = p.mass - p.Xu_dot
    m22 = p.mass - p.Yv_dot
    m23 = p.mass * p.xg - p.Yr_dot
    m32 = p.mass * p.xg - p.Nv_dot
    m33 = p.Iz - p.Nr_dot
    det2 = m22 * m33 - m23 * m32
    left, right = control2
    tau_x = left + right
    tau_n = p.d_thruster * (right - left)

    def ode(s: np.ndarray, t_s: float) -> np.ndarray:
        # Same operation order as USVDynamicModel.continuous_ode, with an added body wrench.
        psi, u, v, r = s[2:]
        c13 = -m22 * v - m23 * r
        c23 = m11 * u
        d00 = -p.Xu - p.Xuu * abs(u)
        d11 = -p.Yv - p.Yvv * abs(v)
        d12 = -p.Yr - p.Yrr * abs(r)
        d21 = -p.Nv - p.Nvv * abs(v)
        d22 = -p.Nr - p.Nrr * abs(r)
        ext_u, ext_v, ext_r = wrench.body_wrench(t_s, psi)
        rhs_x = tau_x - c13 * r - d00 * u + ext_u
        rhs_y = -c23 * r - (d11 * v + d12 * r) + ext_v
        rhs_n = tau_n + c13 * u + c23 * v - (d21 * v + d22 * r) + ext_r
        cos_psi, sin_psi = math.cos(psi), math.sin(psi)
        return np.array([
            cos_psi * u - sin_psi * v, sin_psi * u + cos_psi * v, r,
            rhs_x / m11, (m33 * rhs_y - m23 * rhs_n) / det2,
            (-m32 * rhs_y + m22 * rhs_n) / det2,
        ], dtype=np.float64)

    x = np.asarray(state6, dtype=np.float64).copy()
    h = dyn.dt / dyn.rk4_substeps
    for substep in range(dyn.rk4_substeps):
        t = t0_s + substep * h
        k1 = ode(x, t)
        k2 = ode(x + 0.5 * h * k1, t + 0.5 * h)
        k3 = ode(x + 0.5 * h * k2, t + 0.5 * h)
        k4 = ode(x + h * k3, t + h)
        x = x + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    x[2] = wrap_angle(x[2])
    return x


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _pooled_gp(path: Path):
    return load_pooled_gp(path)


def _zero_residual(_features: list[float]) -> tuple[float, float, float]:
    return 0.0, 0.0, 0.0


def _reference(ep: dict[str, Any], ticks: int) -> tuple[np.ndarray, np.ndarray]:
    path, profile = generate_maneuver_path_and_profile(
        ep["maneuver"], seconds=max(ticks, DEFAULT_TICKS) * DT + 10.0,
        seed=ep["seed"], cruise_speed=ep["cruise_speed"],
    )
    path_xypsi = np.array([row.split()[:3] for row in path], dtype=np.float64)
    profile_rows = np.array([row.split() for row in profile], dtype=np.float64)
    return path_xypsi, profile_rows


def _update_native_solver(operation, *args) -> None:
    try:
        operation(*args)
    except FusionSolverError as exc:
        # The C ABI retains its thread-local solve error across successful void calls.
        # A failure in reset, anchor, or accept sets its own operation-specific error.
        if not str(exc).startswith("p1_fusion_solve:"):
            raise


TRACKING_METRICS = {
    "cross_track_rmse_m": "CTE RMSE (m)",
    "cross_track_max_m": "Max CTE (m)",
    "heading_rmse_rad": "Heading RMSE (rad)",
    "speed_rmse_mps": "Speed RMSE (m/s)",
    "along_track_progress_m": "Progress (m)",
}
EFFORT_METRICS = {
    "thrust_l2_dt": "Thrust² integral (N² s)",
    "energy_per_meter": "Thrust² per meter (N² s/m)",
    "common_mode_l2_dt": "Common-mode integral (N² s)",
    "diff_mode_l2_dt": "Differential integral (N² s)",
    "opposing_thrust_fraction": "Opposing thrust fraction",
    "tv_per_step": "TV per tick (N)",
}
RUNTIME_METRICS = {
    "ppo_active_pct": "PPO active (%)",
    "solver_ms_mean": "Mean solve (ms)",
    "solver_ms_max": "Max solve (ms)",
    "solver_failures": "Solver failures",
}
PAIRED_METRICS = (
    "cross_track_rmse_m", "heading_rmse_rad", "speed_rmse_mps", "along_track_progress_m",
    "energy_per_meter", "tv_per_step",
)
METRICS = TRACKING_METRICS | EFFORT_METRICS | RUNTIME_METRICS
BASELINES = ("gp_only", "nominal_nmpc")


def _control_effort(u_exec: np.ndarray, progress_m: float | None) -> dict[str, float]:
    thrust_l2_dt = float(np.sum(np.sum(u_exec ** 2, axis=1)) * DT)
    left, right = u_exec.T
    return {
        "thrust_l2_dt": thrust_l2_dt,
        "energy_per_meter": thrust_l2_dt / max(progress_m or 0.0, 1e-6),
        "common_mode_l2_dt": float(np.sum(2.0 * (0.5 * (left + right)) ** 2) * DT),
        "diff_mode_l2_dt": float(np.sum(2.0 * (0.5 * (right - left)) ** 2) * DT),
        "opposing_thrust_fraction": float(np.mean(left * right < 0.0)),
        "tv_per_step": float(np.mean(np.sum(np.abs(np.diff(u_exec, axis=0)), axis=1)))
        if len(u_exec) >= 2 else 0.0,
    }


def run_robustness_episode(
    ep: dict[str, Any],
    arm_name: str,
    regime_id: str,
    *,
    ticks: int = DEFAULT_TICKS,
    wrench: ExternalWrenchProfile | None = None,
    keep_trajectory: bool = False,
) -> dict[str, Any]:
    """Run one delayed-control episode with isolated plant and observation paths."""
    if ticks < 1:
        raise ValueError("ticks must be positive")
    arm = ARMS[arm_name]
    wrench_level, noise_level = REGIMES[regime_id]
    if wrench is None:
        wrench = ExternalWrenchProfile.from_preset(wrench_level, ep["seed"])
    noise = NavigationNoiseModel.from_preset(noise_level, ep["seed"], ticks)
    contract = _read_json(CONTRACT)
    nominal_hydro = HydroParams(**contract["hydro"])
    actual_hydro = HydroParams(**_read_json(Path(ep["plant_model_file"]))["plant_actual"])
    nominal_dyn = USVDynamicModel(dt=DT, params=nominal_hydro)
    plant_dyn = USVDynamicModel(dt=DT, params=actual_hydro)
    path_xypsi, profile_rows = _reference(ep, ticks)

    engine = None
    if arm.onnx is not None:
        gate = {**GATE_DEFAULTS, "gate_mode": arm.gate_mode}
        engine = ProposalEngine(
            onnx_path=arm.onnx, manifest_path=arm.manifest, lookahead=arm.lookahead, **gate,
        )
        engine.on_reference(path_xypsi, profile_rows)

    x_true = np.zeros(6)
    u_held = np.zeros(2)
    states_end, u_exec, solver_ms = [], [], []
    active_ppo_ticks = solver_failures = 0
    first_solver_error = None
    with FusionSolver.from_contract(CONTRACT) as solver:
        controller = FusionController(
            solver, gp=_pooled_gp(GP_POOLED) if arm.gp else None, hydro=nominal_hydro,
            # The controller's horizon diagnostics use the callback for nominal residuals.
            gp_predict=None if arm.gp else _zero_residual,
            t_min=-THRUST_LIMIT, t_max=THRUST_LIMIT, dt_max=THRUST_RATE,
            cruise=contract["cruise_speed"], reference_offset=contract["reference_start_offset"],
            projection_mode=contract["reference_projection_mode"], lead_s=contract["reference_lead_s"],
        )
        for tick in range(ticks):
            sim_ns = tick * TICK_NS
            x_obs = noise.corrupt(x_true, tick)
            q_pi, lambda_pi = (0.0, 0.0), 0.0
            if engine is not None:
                engine.on_clock(sim_ns)
                engine.on_odom(sim_ns, x_obs)
                if tick:
                    # u_held starts at sim_ns. The receipt closes the preceding hold.
                    engine.on_plant_receipt(
                        schema_version="p1-plant-receipt-v3", disposition="ok", execution_index=tick,
                        state_sample_sim_ns=sim_ns - TICK_NS, planned_window_end_sim_ns=sim_ns,
                        thrust_n=u_exec[-1], clock_epoch=0,
                    )
                proposal = engine.evaluate(steady_now_ns=sim_ns)
                if proposal.valid:
                    q_pi, lambda_pi = proposal.q_pi, arm.lambda_pi
                    active_ppo_ticks += 1

            target_state = nominal_dyn.forward(x_obs, u_held)
            try:
                # Rebuild the GP's PD rollout from the current reference each tick.
                # Shifting the pre-solve guess repeats its tail. Commit keeps the native warmstart.
                u_raw, diag = controller.step(
                    target_state, path_xypsi, profile_rows, anchors=u_held, q_pi=q_pi,
                    lambda_pi=lambda_pi, prev_x=None, prev_u=None, tick_shift=0,
                )
            except FusionSolverError as exc:
                solver_failures += 1
                if first_solver_error is None:
                    first_solver_error = str(exc)
                _update_native_solver(controller.reset_warmstart)
                u_next, _ = apply_thrust_limits(u_held, np.zeros(2), THRUST_LIMIT, THRUST_RATE, DT)
                _update_native_solver(solver.set_anchor, u_next)
            else:
                u_next, _ = apply_thrust_limits(u_held, u_raw, THRUST_LIMIT, THRUST_RATE, DT)
                _update_native_solver(controller.commit, u_next)
                solver_ms.append(diag["solver_ms"])

            x_true = forward_with_wrench(plant_dyn, x_true, u_held, wrench, t0_s=tick * DT)
            states_end.append(x_true)
            u_exec.append(u_held)
            u_held = u_next
            if not np.all(np.isfinite(x_true)):
                break

    states_end = np.asarray(states_end, dtype=np.float64)
    u_exec = np.asarray(u_exec, dtype=np.float64)
    all_finite = bool(np.all(np.isfinite(states_end)) and np.all(np.isfinite(u_exec)))
    tracking = dict.fromkeys(TRACKING_METRICS)
    if all_finite:
        geom = path_polyline_metrics(states_end, path_xypsi, profile_rows[:, :3])
        tracking = {key: geom[key] for key in TRACKING_METRICS}
    result = {
        "episode_name": ep["episode_name"],
        "seed": ep["seed"],
        "seed_offset": ep.get("seed_offset", 0),
        "maneuver": ep["maneuver"],
        "cruise_speed": ep["cruise_speed"],
        "plant_profile": ep.get("profile"),
        "plant_model_file": ep["plant_model_file"],
        "arm": arm_name,
        "regime": regime_id,
        "ticks": ticks,
        "ticks_executed": len(u_exec),
        **tracking,
        **_control_effort(u_exec, tracking["along_track_progress_m"]),
        "ppo_active_pct": 100.0 * active_ppo_ticks / ticks,
        "solver_ms_mean": float(np.mean(solver_ms)) if solver_ms else None,
        "solver_ms_max": float(max(solver_ms)) if solver_ms else None,
        "solver_failures": solver_failures,
        "first_solver_error": first_solver_error,
        "all_finite": all_finite,
        "success": all_finite and solver_failures == 0 and tracking["cross_track_max_m"] < CTE_SUCCESS_LIMIT,
    }
    if keep_trajectory:
        result.update(states_end=states_end, u_exec=u_exec)
    return result


def _run_task(task: tuple[dict[str, Any], str, str, int]) -> dict[str, Any]:
    ep, arm_name, regime_id, ticks = task
    try:
        return run_robustness_episode(ep, arm_name, regime_id, ticks=ticks)
    except Exception as exc:
        raise RuntimeError(f"{regime_id}/{arm_name}/{ep['episode_name']} seed {ep['seed']}: {exc}") from exc


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {"episodes": len(runs), "successful_episodes": sum(run["success"] for run in runs)}
    summary["success_pct"] = 100.0 * summary["successful_episodes"] / len(runs)
    summary["solver_failure_ticks"] = sum(run["solver_failures"] for run in runs)
    for key in METRICS:
        values = [run[key] for run in runs if run[key] is not None]
        summary[key] = math.fsum(values) / len(values) if values else None
    return summary


def _paired_stats(arm_runs: list[dict[str, Any]], ref_runs: list[dict[str, Any]]) -> dict[str, Any]:
    ref_by_episode = {(run["episode_name"], run["seed"]): run for run in ref_runs}
    pairs = [(run, ref_by_episode[(run["episode_name"], run["seed"])]) for run in arm_runs]
    comparisons = {}
    for metric in PAIRED_METRICS:
        usable = [(a[metric], b[metric]) for a, b in pairs if a[metric] is not None and b[metric] is not None]
        stats = {"n": 0}
        if usable:
            arm_values, ref_values = zip(*usable)
            stats = paired_wilcoxon_and_bootstrap(
                arm_values, ref_values, n_boot=BOOTSTRAP_SAMPLES, seed=BOOTSTRAP_SEED,
            )
            if metric == "along_track_progress_m":
                stats["wins"], stats["losses"] = stats["losses"], stats["wins"]
        comparisons[metric] = {"matched_episodes": len(pairs), **stats}
    return comparisons


def _artifact(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def _metadata(args, seeds: list[int], episodes: list[dict], arms: list[str]) -> dict[str, Any]:
    artifacts = {
        "script": _artifact(Path(__file__).resolve()),
        "contract": _artifact(CONTRACT),
        "split_manifest": _artifact(SPLIT_MANIFEST),
        "solver_library": _artifact(Path(DEFAULT_LIB_PATH)),
        "plants": {path: _artifact(Path(path)) for path in sorted({ep["plant_model_file"] for ep in episodes})},
        "policies": {},
    }
    if any(ARMS[name].gp for name in arms):
        artifacts["gp_snapshot"] = _artifact(GP_POOLED)
    policies = {}
    for name in arms:
        arm = ARMS[name]
        if arm.onnx is not None and arm.onnx not in policies:
            policies[arm.onnx] = {"onnx": _artifact(arm.onnx), "manifest": _artifact(arm.manifest)}
        if arm.onnx is not None:
            artifacts["policies"][name] = policies[arm.onnx]

    return {
        "split": args.split, "seed_offsets": seeds, "seed_stride": 10000,
        "ticks": args.ticks, "dt_s": DT, "rk4_substeps": 4, "episodes_per_arm_regime": len(episodes),
        "workers_requested": args.workers, "smoke": args.smoke,
        "thrust_limit_n": THRUST_LIMIT, "thrust_rate_limit_n_s": THRUST_RATE,
        "success_cross_track_max_lt_m": CTE_SUCCESS_LIMIT,
        "bootstrap_samples": BOOTSTRAP_SAMPLES, "bootstrap_seed": BOOTSTRAP_SEED,
        "artifacts": artifacts,
        "arms": {
            name: {
                **asdict(ARMS[name]),
                "onnx": str(ARMS[name].onnx) if ARMS[name].onnx is not None else None,
                "gate": {**GATE_DEFAULTS, "gate_mode": ARMS[name].gate_mode},
            }
            for name in arms
        },
    }


def _summarize(
    metadata: dict[str, Any], regimes: list[str], arms: list[str], runs: list[dict],
) -> dict[str, Any]:
    summaries, comparisons, maneuver_breakdown = {}, {}, {}
    for regime in regimes:
        by_arm = {arm: [r for r in runs if r["regime"] == regime and r["arm"] == arm] for arm in arms}
        summaries[regime] = {arm: _aggregate(arm_runs) for arm, arm_runs in by_arm.items()}
        comparisons[regime] = {
            arm: {
                baseline: _paired_stats(arm_runs, by_arm[baseline])
                for baseline in BASELINES if baseline in by_arm and baseline != arm
            }
            for arm, arm_runs in by_arm.items()
        }
        if regime == "R4_combined_nominal":
            for maneuver in sorted({r["maneuver"] for r in by_arm[arms[0]]}):
                maneuver_breakdown[maneuver] = {
                    arm: _aggregate([r for r in arm_runs if r["maneuver"] == maneuver])
                    for arm, arm_runs in by_arm.items()
                }
    return {
        "metadata": metadata,
        "regimes": {regime: {"wrench": wrench, "noise": noise} for regime, (wrench, noise) in REGIMES.items()},
        "wrench_presets": WRENCH_PRESETS,
        "noise_presets": {level: {"name": name, "sigmas": sigmas} for level, (name, sigmas) in NOISE_PRESETS.items()},
        "summary": summaries,
        "paired_stats": comparisons,
        "r4_per_maneuver": maneuver_breakdown,
        "runs": runs,
    }


def _fmt(value: float | None, digits: int = 4, missing: str = "—") -> str:
    return f"{value:.{digits}f}" if value is not None else missing


def _md_table(headers, rows) -> str:
    return "\n".join(
        "| " + " | ".join(row) + " |" for row in [headers, ["---"] * len(headers), *rows]
    )


def _summary_tables(rows: list[tuple[str, str, dict]]) -> list[str]:
    tables = []
    for heading, metrics in (("Tracking", TRACKING_METRICS), ("Control effort", EFFORT_METRICS),
                             ("Solver and policy", RUNTIME_METRICS)):
        headers = ["Group", "Arm", "Episodes", *metrics.values()]
        if heading == "Tracking":
            headers.append("Success (%)")
        if heading == "Solver and policy":
            headers.append("Total failed solves")
        table_rows = []
        for group, arm, stats in rows:
            row = [group, ARMS[arm].label, str(stats["episodes"])]
            row.extend(_fmt(stats[key]) for key in metrics)
            if heading == "Tracking":
                row.append(_fmt(stats["success_pct"], 1))
            if heading == "Solver and policy":
                row.append(str(stats["solver_failure_ticks"]))
            table_rows.append(row)
        tables.extend([f"### {heading}", _md_table(headers, table_rows)])
    return tables


def _render_report(doc: dict[str, Any]) -> str:
    meta = doc["metadata"]
    episode_count = meta["episodes_per_arm_regime"]
    episode_label = "episode" if episode_count == 1 else "episodes"
    sections = [
        "# Zero-retrain closed-loop robustness",
        f"The `{meta['split']}` split contributed {episode_count} paired {episode_label} per "
        f"regime and arm. Each episode used {meta['ticks']} ticks at {meta['dt_s']:.1f} s per tick. "
        "Tracking metrics use true end-of-hold states. Success requires finite states and controls, "
        f"zero solver failures, and maximum cross-track error below {CTE_SUCCESS_LIMIT:g} m.",
        "Entries are means of episode-level metrics unless labeled as totals. "
        "The thrust-squared integral measures control effort. PPO activity counts valid proposals. "
        "Solve times measure the native solver under this run's worker load.",
        _md_table(["Regime", "Wrench", "Navigation noise"], [
            [regime, doc["regimes"][regime]["wrench"], doc["regimes"][regime]["noise"]]
            for regime in doc["summary"]
        ]),
        "## Regime results",
        *_summary_tables([
            (regime, arm, stats)
            for regime, arms in doc["summary"].items() for arm, stats in arms.items()
        ]),
    ]
    if doc["r4_per_maneuver"]:
        sections.extend(["## R4 combined nominal by maneuver", *_summary_tables([
            (maneuver, arm, stats)
            for maneuver, arms in doc["r4_per_maneuver"].items() for arm, stats in arms.items()
        ])])
    sections.extend([
        "## Paired comparisons",
        "Differences are arm minus baseline on matched episode seeds. Intervals are pointwise 95% "
        "paired-bootstrap intervals. Wilcoxon p-values are two-sided and unadjusted. "
        "Wins favor larger progress and smaller values for the other metrics. "
        "Rows use finite paired metrics, including available measurements from unsuccessful episodes.",
    ])
    if episode_count == 1:
        sections.append("A single paired episode checks the evaluation pipeline. Its bootstrap interval "
                        "collapses to the observed difference.")
    comparisons_shown = False
    for regime, arms in doc["paired_stats"].items():
        rows = []
        for arm, baselines in arms.items():
            for baseline, metrics in baselines.items():
                for key, stat in metrics.items():
                    ci = "—"
                    wtl = "—"
                    if stat["n"]:
                        ci = f"[{_fmt(stat['bootstrap_ci95_low'])}, {_fmt(stat['bootstrap_ci95_high'])}]"
                        wtl = f"{stat['wins']}/{stat['ties']}/{stat['losses']}"
                    rows.append([ARMS[arm].label, ARMS[baseline].label, METRICS[key],
                                 f"{stat['n']}/{stat['matched_episodes']}", _fmt(stat.get("mean_diff")),
                                 ci, wtl, _fmt(stat.get("wilcoxon_p"), 6)])
        if rows:
            comparisons_shown = True
            sections.extend([f"### {regime}", _md_table(
                ["Arm", "Baseline", "Metric", "Pairs used", "Mean Δ", "95% CI", "W/T/L", "p"], rows,
            )])
    if not comparisons_shown:
        sections.append("No baseline comparisons were available for the selected arms.")
    sections.append("Episode results and artifact SHA-256 hashes are in `robustness_summary.json`.")
    return "\n\n".join(sections) + "\n"


def _render_tex(doc: dict[str, Any]) -> str:
    meta = doc["metadata"]
    episode_count = meta["episodes_per_arm_regime"]
    run_label = "held-out run" if meta["split"] == "final_test" else "run"
    if episode_count != 1:
        run_label += "s"
    rows = [
        r"% Requires \usepackage{booktabs}",
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Zero-retrain closed-loop robustness. "
        f"Entries summarize {episode_count} paired {run_label} per regime and arm. "
        r"CTE is cross-track RMSE, and $\Delta$CTE is the paired mean difference versus GP only. "
        r"PPO is the percentage of ticks with valid proposals. "
        r"Stars mark two-sided Wilcoxon signed-rank significance versus GP only "
        r"($^{*}p < 0.05$, $^{**}p < 0.01$, $^{***}p < 0.001$).}",
        r"\label{tab:closed-loop-robustness}",
        r"\small",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{lrrrrrrrr}",
        r"\toprule",
        r"Arm & CTE (mm) & $\Delta$CTE (mm) & Max CTE (m) & Progress (m) & "
        r"$E/m$ (N$^2\cdot$s/m) & TV/step (N) & PPO (\%) & Succ. (\%) \\",
        r"\midrule",
    ]
    for regime, arms in doc["summary"].items():
        name = regime.replace("_", " ")
        rows.append(rf"\multicolumn{{9}}{{l}}{{\textbf{{{name}}}}} \\")
        regime_pairs = doc["paired_stats"].get(regime, {})
        for arm, stats in arms.items():
            cte = stats["cross_track_rmse_m"]
            cte_mm = _fmt(1000.0 * cte if cte is not None else None, 2, "--")
            delta_cte = "--"
            paired_cte = regime_pairs.get(arm, {}).get("gp_only", {}).get("cross_track_rmse_m", {})
            mean_diff = paired_cte.get("mean_diff")
            if arm != "gp_only" and mean_diff is not None:
                p_value = paired_cte.get("wilcoxon_p")
                stars = ""
                for threshold, marker in ((0.001, "***"), (0.01, "**"), (0.05, "*")):
                    if p_value is not None and p_value < threshold:
                        stars = f"^{{{marker}}}"
                        break
                delta_cte = f"${1000.0 * mean_diff:+.2f}{stars}$"
            metrics = [_fmt(stats[key], digits, "--") for key, digits in (
                ("cross_track_max_m", 3), ("along_track_progress_m", 2),
                ("energy_per_meter", 2), ("tv_per_step", 3), ("ppo_active_pct", 1), ("success_pct", 1),
            )]
            rows.append(" & ".join([ARMS[arm].label, cte_mm, delta_cte, *metrics]) + r" \\")
        rows.append(r"\addlinespace")
    rows.extend([r"\bottomrule", r"\end{tabular}", r"\end{table*}"])
    return "\n".join(rows) + "\n"


def _selection(raw: str, available: dict) -> list[str]:
    if raw.strip() == "all":
        return list(available)
    names = [name.strip() for name in raw.split(",")]
    if len(set(names)) != len(names) or any(name not in available for name in names):
        raise ValueError(f"invalid or repeated selections {raw!r}; choices: all, {', '.join(available)}")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split", default="final_test")
    parser.add_argument("--seeds", default="0,1,2", help="comma-separated seed offsets")
    parser.add_argument("--regimes", help="comma-separated regime IDs or all (default)")
    parser.add_argument("--arms", default="all", help="comma-separated arm IDs or all")
    parser.add_argument("--workers", default=12, type=int)
    parser.add_argument("--smoke", action="store_true", help="one matched episode; defaults to R0 only")
    parser.add_argument("--ticks", default=DEFAULT_TICKS, type=int)
    args = parser.parse_args(argv)
    try:
        regimes = _selection(args.regimes or ("R0_clean" if args.smoke else "all"), REGIMES)
        arms = _selection(args.arms, ARMS)
        seeds = [int(value) for value in args.seeds.split(",")]
        if len(set(seeds)) != len(seeds):
            raise ValueError("seed offsets must be unique")
        if args.ticks < 1 or args.workers < 1:
            raise ValueError("ticks and workers must be positive")
    except ValueError as exc:
        parser.error(str(exc))

    base_episodes = sorted(
        (ep for ep in _read_json(SPLIT_MANIFEST)["episodes"] if ep["split"] == args.split),
        key=lambda ep: ep["episode_name"],
    )
    if not base_episodes:
        parser.error(f"split {args.split!r} has no episodes in {SPLIT_MANIFEST}")
    if args.smoke:
        base_episodes, seeds = base_episodes[:1], seeds[:1]
    episodes = [
        {**base, "seed": int(base["seed"]) + 10000 * offset, "seed_offset": offset}
        for offset in seeds for base in base_episodes
    ]
    tasks = [(ep, arm, regime, args.ticks) for regime in regimes for arm in arms for ep in episodes]
    metadata = _metadata(args, seeds, episodes, arms)
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    workers = min(args.workers, len(tasks))
    print(f"Evaluating {len(tasks)} runs ({len(episodes)} paired episodes, {workers} workers)", flush=True)
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        runs = list(pool.map(_run_task, tasks))

    result = _summarize(metadata, regimes, arms, runs)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "robustness_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8",
    )
    (args.out / "robustness_report.md").write_text(_render_report(result), encoding="utf-8")
    (args.out / "paper_table_robustness.tex").write_text(_render_tex(result), encoding="utf-8")
    print(f"Wrote robustness results to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
