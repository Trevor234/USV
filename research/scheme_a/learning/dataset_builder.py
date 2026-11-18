#!/usr/bin/env python3
"""Build verifiable, provenance-tracked 0.2 s velocity-residual datasets.

Consumes controlled-simulation runs (native `p1-plant-receipt-v3` +
`p1-plant-hold-close-v2`, or explicit `--allow-legacy-v2` runs verified via
`plant_sensors` + `PlantHoldClose`), computes exact 4-substep RK4 Fossen nominal
predictions, and emits:
  - `dataset_contract.json`
  - `sample_provenance.jsonl`
  - `data_quality.json`
  - `dataset.npz` (when admitted samples > 0 or always empty-safe arrays)
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

DT_S = 0.2
TICK_NS = 200_000_000
RK4_SUBSTEPS = 4
DATASET_CONTRACT_SCHEMA = "scheme-a-residual-dataset-contract-v1"
DATA_QUALITY_SCHEMA = "scheme-a-residual-data-quality-v1"

HYDRO_KEYS = (
    "mass", "Iz", "xg", "d_thruster",
    "Xu_dot", "Yv_dot", "Yr_dot", "Nv_dot", "Nr_dot",
    "Xu", "Yv", "Yr", "Nv", "Nr",
    "Xuu", "Yvv", "Yrr", "Nvv", "Nrr",
)
FEATURE_NAMES = ["u", "v", "r", "T_L_executed", "T_R_executed"]
FEATURE_UNITS = ["m/s", "m/s", "rad/s", "N", "N"]
OUTPUT_NAMES = [
    "delta_u_residual",
    "delta_v_residual",
    "delta_r_residual",
]
OUTPUT_UNITS = ["m/s", "m/s", "rad/s"]


@dataclass(frozen=True)
class HydroParams:
    """19-dim Fossen hydrodynamic parameters matching C++ `usv_mpc::HydroParams`."""

    mass: float = 14.2
    Iz: float = 2.13
    xg: float = 0.12
    d_thruster: float = 0.25
    Xu_dot: float = -2.0
    Yv_dot: float = -8.0
    Yr_dot: float = 0.0
    Nv_dot: float = -0.363545
    Nr_dot: float = -1.621220
    Xu: float = -2.272063
    Yv: float = -2.629019
    Yr: float = 0.0
    Nv: float = 0.0
    Nr: float = -4.286144
    Xuu: float = -11.571784
    Yvv: float = -0.05
    Yrr: float = 0.0
    Nvv: float = 0.0
    Nrr: float = -0.001

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HydroParams":
        missing = [k for k in HYDRO_KEYS if k not in data]
        if missing:
            raise KeyError(f"hydro dictionary missing keys: {missing}")
        vals = {k: float(data[k]) for k in HYDRO_KEYS}
        for k, v in vals.items():
            if not math.isfinite(v):
                raise ValueError(f"non-finite hydro parameter {k}={v!r}")
        return cls(**vals)

    def to_dict(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in HYDRO_KEYS}

    def canonical_sha256(self, dt_s: float = DT_S, rk4_substeps: int = RK4_SUBSTEPS) -> str:
        payload = {
            "hydro": self.to_dict(),
            "dt_s": float(dt_s),
            "rk4_substeps": int(rk4_substeps),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def wrap_angle(psi: float) -> float:
    return math.atan2(math.sin(psi), math.cos(psi))


def fossen_continuous_ode(state: np.ndarray, control: np.ndarray, p: HydroParams) -> np.ndarray:
    """Exact match to C++ `usv_mpc::USVDynamicModel::continuous_ode`."""
    psi_s = float(state[2])
    u_s, v_s, r_s = float(state[3]), float(state[4]), float(state[5])
    t_l, t_r = float(control[0]), float(control[1])

    m11 = p.mass - p.Xu_dot
    m22 = p.mass - p.Yv_dot
    m23 = p.mass * p.xg - p.Yr_dot
    m32 = p.mass * p.xg - p.Nv_dot
    m33 = p.Iz - p.Nr_dot

    M = np.array([
        [m11, 0.0, 0.0],
        [0.0, m22, m23],
        [0.0, m32, m33],
    ], dtype=np.float64)

    c13 = -m22 * v_s - m23 * r_s
    c23 = m11 * u_s
    C = np.array([
        [0.0, 0.0, c13],
        [0.0, 0.0, c23],
        [-c13, -c23, 0.0],
    ], dtype=np.float64)

    d00 = -p.Xu - p.Xuu * abs(u_s)
    d11 = -p.Yv - p.Yvv * abs(v_s)
    d12 = -p.Yr - p.Yrr * abs(r_s)
    d21 = -p.Nv - p.Nvv * abs(v_s)
    d22 = -p.Nr - p.Nrr * abs(r_s)
    D = np.array([
        [d00, 0.0, 0.0],
        [0.0, d11, d12],
        [0.0, d21, d22],
    ], dtype=np.float64)

    tau = np.array([t_l + t_r, 0.0, p.d_thruster * (t_r - t_l)], dtype=np.float64)
    nu = np.array([u_s, v_s, r_s], dtype=np.float64)

    cos_psi = math.cos(psi_s)
    sin_psi = math.sin(psi_s)
    eta_dot = np.array([
        cos_psi * u_s - sin_psi * v_s,
        sin_psi * u_s + cos_psi * v_s,
        r_s,
    ], dtype=np.float64)
    rhs_nu = np.linalg.solve(M, tau - C @ nu - D @ nu)
    return np.concatenate([eta_dot, rhs_nu])


def fossen_rk4_step(
    state: np.ndarray,
    control: np.ndarray,
    p: HydroParams,
    dt_s: float = DT_S,
    rk4_substeps: int = RK4_SUBSTEPS,
) -> np.ndarray:
    """Exact match to C++ `usv_mpc::USVDynamicModel::forward`."""
    x = np.asarray(state, dtype=np.float64).copy()
    u = np.asarray(control, dtype=np.float64)
    h = float(dt_s) / float(rk4_substeps)
    for _ in range(rk4_substeps):
        k1 = fossen_continuous_ode(x, u, p)
        k2 = fossen_continuous_ode(x + 0.5 * h * k1, u, p)
        k3 = fossen_continuous_ode(x + 0.5 * h * k2, u, p)
        k4 = fossen_continuous_ode(x + h * k3, u, p)
        x = x + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    x[2] = wrap_angle(float(x[2]))
    return x


def _read_jsonl_with_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            s = raw.strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                obj["__line"] = line_no
                rows.append(obj)
    return rows


def _is_finite_seq(vals: Any, n: int) -> bool:
    if not isinstance(vals, (list, tuple, np.ndarray)) or len(vals) != n:
        return False
    return all(
        not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(float(v))
        for v in vals
    )


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v


def _extract_controller_nominal(contract: dict[str, Any]) -> HydroParams:
    if "controller_nominal" in contract and isinstance(contract["controller_nominal"], dict):
        cn = contract["controller_nominal"]
        if "hydro" in cn:
            return HydroParams.from_dict(cn["hydro"])
        return HydroParams.from_dict(cn)
    return HydroParams.from_dict(contract["hydro"])


def _extract_plant_actual(contract: dict[str, Any], plant_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in plant_rows:
        if row.get("type") == "plant_ready" and isinstance(row.get("plant_actual"), dict):
            return row["plant_actual"]
    if isinstance(contract.get("plant_actual"), dict):
        return contract["plant_actual"]
    return None


@dataclass
class RunExtraction:
    episode_id: str
    run_dir: str
    scenario: str
    dataset_source: str
    admitted: list[dict[str, Any]]
    provenance_rows: list[dict[str, Any]]
    stats: dict[str, Any]


def extract_run(
    run_dir: Path,
    *,
    allow_legacy_v2: bool = False,
    expected_nominal_hash: str | None = None,
    split: str = "unspecified",
) -> RunExtraction:
    """Extract aligned 0.2 s windows and exclusions from a single run directory."""
    run_path = run_dir / "run.json"
    contract_path = run_dir / "contract.json"
    plant_path = run_dir / "plant.source.jsonl"
    reg_path = run_dir / "regulator.source.jsonl"

    run_doc = json.loads(run_path.read_text(encoding="utf-8")) if run_path.is_file() else {}
    contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.is_file() else {}

    episode_id = str(run_doc.get("run_id") or run_dir.name)
    scenario = str(run_doc.get("scenario") or "unknown")
    qualification = str(contract.get("qualification") or "")
    dataset_source = str(
        run_doc.get("dataset_source")
        or ("dry_run_nominal" if qualification in ("shipboard_dry_run", "shipboard_commissioning") else "controlled_sim_actual")
    )

    stats: dict[str, Any] = {
        "episode_id": episode_id,
        "run_dir": str(run_dir),
        "scenario": scenario,
        "dataset_source": dataset_source,
        "split": split,
        "run_rejected_reason": None,
        "commands_entered": 0,
        "receipt_counts": {"bootstrap": 0, "ok": 0, "rejected": 0, "late": 0, "duplicate": 0, "other": 0},
        "ok_receipts": 0,
        "admitted_windows": 0,
        "excluded_windows": 0,
        "excluded_by_reason": {},
        "clock_resync_events": 0,
        "schema_mode": None,
    }

    def excl(reason: str) -> None:
        stats["excluded_windows"] += 1
        d = stats["excluded_by_reason"]
        d[reason] = d.get(reason, 0) + 1

    # Hard guard: dry-run nominal inputs NEVER become residual training labels.
    if qualification in ("shipboard_dry_run", "shipboard_commissioning") or dataset_source == "dry_run_nominal":
        stats["run_rejected_reason"] = "dry_run_not_executable_truth"
        return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)

    if not plant_path.is_file() or not contract:
        stats["run_rejected_reason"] = "missing_plant_or_contract"
        return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)

    nominal_hydro = _extract_controller_nominal(contract)
    nominal_hydro_sha = nominal_hydro.canonical_sha256(DT_S, RK4_SUBSTEPS)
    if expected_nominal_hash is not None and nominal_hydro_sha != expected_nominal_hash:
        stats["run_rejected_reason"] = "nominal_hydro_hash_mismatch"
        return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)

    plant_rows = _read_jsonl_with_lines(plant_path)
    reg_rows = _read_jsonl_with_lines(reg_path)
    plant_actual = _extract_plant_actual(contract, plant_rows)

    commands_by_seq: dict[int, dict[str, Any]] = {}
    for row in reg_rows:
        if row.get("type") == "plant_command":
            stats["commands_entered"] += 1
            seq = _as_int(row.get("sequence"))
            if seq is not None:
                commands_by_seq[seq] = row

    bootstraps = [r for r in plant_rows if r.get("type") == "bootstrap_receipt"]
    receipts = [r for r in plant_rows if r.get("type") == "plant_receipt"]
    hold_closes = [r for r in plant_rows if r.get("type") == "plant_hold_close"]
    sensors = [r for r in plant_rows if r.get("type") == "plant_sensors"]
    resyncs = [r for r in plant_rows if r.get("type") == "plant_clock_resync"]
    stats["clock_resync_events"] = len(resyncs)

    for b in bootstraps:
        stats["receipt_counts"]["bootstrap"] += 1
    for r in receipts:
        disp = str(r.get("disposition") or "other")
        if disp in stats["receipt_counts"]:
            stats["receipt_counts"][disp] += 1
        else:
            stats["receipt_counts"]["other"] += 1

    ok_list = [r for r in receipts if r.get("disposition") == "ok"]
    stats["ok_receipts"] = len(ok_list)

    if len(bootstraps) != 1:
        stats["run_rejected_reason"] = "missing_or_multiple_bootstrap"
        return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)
    boot = bootstraps[0]
    boot_origin = _as_int(boot.get("plant_steady_origin_ns"))
    boot_id = boot.get("boot_id")

    receipt_schemas = {str(r.get("schema") or "") for r in bootstraps + receipts}
    hold_schemas = {str(r.get("schema") or "") for r in hold_closes}

    if "p1-plant-receipt-v3" in receipt_schemas and "p1-plant-receipt-v2" in receipt_schemas:
        stats["run_rejected_reason"] = "mixed_receipt_schema"
        return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)

    if receipt_schemas == {"p1-plant-receipt-v3"}:
        if hold_closes and hold_schemas != {"p1-plant-hold-close-v2"}:
            stats["run_rejected_reason"] = "hold_close_schema_mismatch_for_v3"
            return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)
        schema_mode = "native_v3"
    elif receipt_schemas <= {"p1-plant-receipt-v2"} and (not hold_closes or hold_schemas <= {"p1-plant-hold-close-v1"}):
        if not allow_legacy_v2:
            stats["run_rejected_reason"] = "legacy_v2_disallowed"
            return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)
        schema_mode = "legacy_v2"
    else:
        stats["run_rejected_reason"] = f"unsupported_receipt_schema:{sorted(receipt_schemas)}"
        return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, [], [], stats)

    stats["schema_mode"] = schema_mode

    # Index sensors by sim_ns for legacy_v2 start-time verification & audit.
    sensors_by_sim: dict[int, list[dict[str, Any]]] = {}
    for srow in sensors:
        s_ns = _as_int(srow.get("sim_ns"))
        if s_ns is not None:
            sensors_by_sim.setdefault(s_ns, []).append(srow)

    # Index hold_closes by execution_index.
    hc_by_exec: dict[int, list[dict[str, Any]]] = {}
    for hc in hold_closes:
        eidx = _as_int(hc.get("execution_index"))
        if eidx is not None:
            hc_by_exec.setdefault(eidx, []).append(hc)

    # Index ok receipts by execution_index to detect duplicates.
    ok_by_exec: dict[int, list[dict[str, Any]]] = {}
    for r in ok_list:
        eidx = _as_int(r.get("execution_index"))
        if eidx is not None:
            ok_by_exec.setdefault(eidx, []).append(r)

    # Resync intervals (sim_ns at which steady_origin_ns changed).
    resync_sims = [_as_int(r.get("sim_ns")) for r in resyncs]
    resync_sims = [v for v in resync_sims if v is not None]

    # Precollect start sim times of all ok receipts to detect overlapping windows.
    ok_interval_starts: list[tuple[int, int]] = []
    for r in ok_list:
        eidx = _as_int(r.get("execution_index"))
        if eidx is None:
            continue
        if schema_mode == "native_v3":
            ts = _as_int(r.get("state_sample_sim_ns"))
        else:
            eb = _as_int(r.get("executed_begin_steady_ns"))
            ro = _as_int(r.get("plant_steady_origin_ns"))
            ts = (eb - ro) if (eb is not None and ro is not None) else None
        if ts is not None:
            ok_interval_starts.append((eidx, ts))

    admitted: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []

    def record_excluded(
        receipt: dict[str, Any],
        hold_close: dict[str, Any] | None,
        reason: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        excl(reason)
        prov = {
            "episode_id": episode_id,
            "scenario": scenario,
            "split": split,
            "dataset_source": dataset_source,
            "run_id": receipt.get("run_id") or episode_id,
            "boot_id": receipt.get("boot_id") or boot_id,
            "sequence": receipt.get("sequence"),
            "tick": receipt.get("tick"),
            "execution_index": receipt.get("execution_index"),
            "clock_epoch": receipt.get("clock_epoch"),
            "receipt_line": receipt.get("__line"),
            "hold_close_line": hold_close.get("__line") if hold_close else None,
            "conversion_mode": schema_mode,
            "controller_nominal_hydro_sha256": nominal_hydro_sha,
            "included": False,
            "exclusion_reason": reason,
        }
        if extra:
            prov.update(extra)
        provenance_rows.append(prov)

    for rec in ok_list:
        eidx = _as_int(rec.get("execution_index"))
        seq = _as_int(rec.get("sequence"))
        tick = _as_int(rec.get("tick"))

        if eidx is None or eidx <= 0:
            record_excluded(rec, None, "invalid_execution_index")
            continue
        if len(ok_by_exec.get(eidx, [])) > 1:
            record_excluded(rec, None, "duplicate_execution_index")
            continue

        hcs = hc_by_exec.get(eidx, [])
        if not hcs:
            record_excluded(rec, None, "missing_hold_close")
            continue
        if len(hcs) > 1:
            record_excluded(rec, hcs[0], "duplicate_hold_close")
            continue
        hc = hcs[0]

        if str(hc.get("reason")) == "stop":
            record_excluded(rec, hc, "stop_truncation")
            continue
        if str(hc.get("reason")) not in ("expired", "superseded"):
            record_excluded(rec, hc, f"unsupported_hold_close_reason:{hc.get('reason')}")
            continue

        r_origin = _as_int(rec.get("plant_steady_origin_ns"))
        if boot_origin is None or r_origin is None or r_origin != boot_origin:
            record_excluded(rec, hc, "steady_origin_mismatch")
            continue

        r_epoch = _as_int(rec.get("clock_epoch"))
        r_run_id = rec.get("run_id")
        r_boot_id = rec.get("boot_id")
        r_contract = rec.get("contract_hash")
        if r_run_id != boot.get("run_id") or r_boot_id != boot_id or r_contract != boot.get("contract_hash"):
            record_excluded(rec, hc, "identity_mismatch")
            continue

        sensor_line = None
        conversion_basis = "native_v3_receipt_and_hold_close"
        if schema_mode == "native_v3":
            boot_clk = boot.get("clock_identity")
            rec_clk = rec.get("clock_identity")
            hc_clk = hc.get("clock_identity")
            if not boot_clk or rec_clk != boot_clk or hc_clk != boot_clk:
                record_excluded(rec, hc, "clock_identity_mismatch")
                continue
            if hc.get("boot_id") != boot_id or _as_int(hc.get("plant_steady_origin_ns")) != boot_origin:
                record_excluded(rec, hc, "hold_close_identity_or_origin_mismatch")
                continue
            if _as_int(hc.get("clock_epoch")) != r_epoch:
                record_excluded(rec, hc, "clock_epoch_mismatch")
                continue
            t_start = _as_int(rec.get("state_sample_sim_ns"))
            t_planned = _as_int(rec.get("planned_window_end_sim_ns"))
            t_end = _as_int(hc.get("state_sample_sim_ns"))
            t_close = _as_int(hc.get("close_sim_ns"))
            exec_begin = _as_int(rec.get("executed_begin_steady_ns"))
            hold_end = _as_int(rec.get("hold_end_steady_ns"))
            if None in (t_start, t_planned, t_end, t_close, exec_begin, hold_end):
                record_excluded(rec, hc, "missing_v3_timestamp")
                continue
            if t_start != exec_begin - boot_origin:
                record_excluded(rec, hc, "state_sample_sim_mismatch")
                continue
            if t_planned != hold_end - boot_origin or t_end != t_close:
                record_excluded(rec, hc, "endpoint_time_mismatch")
                continue
            if t_end != t_planned or (t_end - t_start) != TICK_NS:
                record_excluded(rec, hc, "incomplete_or_mismatched_window")
                continue
        else:
            # Explicit legacy v2 conversion: verify receipt.state timestamp using plant_sensors & hold_close.
            exec_begin = _as_int(rec.get("executed_begin_steady_ns"))
            hold_end = _as_int(rec.get("hold_end_steady_ns"))
            t_close = _as_int(hc.get("close_sim_ns"))
            hc_exec_end = _as_int(hc.get("executed_end_steady_ns"))
            if None in (exec_begin, hold_end, t_close, hc_exec_end):
                record_excluded(rec, hc, "missing_v2_timestamp")
                continue
            t_start = exec_begin - boot_origin
            t_planned = hold_end - boot_origin
            t_end = t_close
            if t_end != t_planned or hc_exec_end != hold_end or (t_end - t_start) != TICK_NS:
                record_excluded(rec, hc, "incomplete_or_mismatched_window")
                continue
            matching_sensors = [
                s for s in sensors_by_sim.get(t_start, [])
                if _is_finite_seq(s.get("state"), 6)
                and np.max(np.abs(np.asarray(s["state"], dtype=np.float64) - np.asarray(rec["state"], dtype=np.float64))) <= 1e-12
            ]
            if not matching_sensors:
                record_excluded(rec, hc, "legacy_v2_unverified_start_time")
                continue
            sensor_line = matching_sensors[0].get("__line")
            conversion_basis = "legacy_v2_sensor_and_hold_close_join"

        # Check clock resync inside (t_start, t_end]
        if any(t_start <= rs <= t_end for rs in resync_sims):
            record_excluded(rec, hc, "clock_resync_across_window")
            continue

        # Check multi-input overlap strictly inside (t_start, t_end)
        if any(oe != eidx and t_start < ots < t_end for oe, ots in ok_interval_starts):
            record_excluded(rec, hc, "cross_input_window")
            continue

        if not (_is_finite_seq(rec.get("state"), 6) and _is_finite_seq(hc.get("state"), 6) and _is_finite_seq(rec.get("thrust_n"), 2)):
            record_excluded(rec, hc, "nonfinite_state_or_thrust")
            continue

        x_start = np.asarray(rec["state"], dtype=np.float64)
        q_exec = np.asarray(rec["thrust_n"], dtype=np.float64)
        x_end = np.asarray(hc["state"], dtype=np.float64)

        x_nom_next = fossen_rk4_step(x_start, q_exec, nominal_hydro, DT_S, RK4_SUBSTEPS)
        z_k = np.array([x_start[3], x_start[4], x_start[5], q_exec[0], q_exec[1]], dtype=np.float64)
        y_k = x_end[3:6] - x_nom_next[3:6]

        cmd = commands_by_seq.get(seq) if seq is not None else None
        cmd_line = cmd.get("__line") if cmd else None
        stats["admitted_windows"] += 1

        prov = {
            "episode_id": episode_id,
            "scenario": scenario,
            "split": split,
            "dataset_source": dataset_source,
            "run_id": r_run_id,
            "boot_id": boot_id,
            "sequence": seq,
            "tick": tick,
            "execution_index": eidx,
            "clock_epoch": r_epoch,
            "clock_identity": rec.get("clock_identity") or boot.get("clock_identity") or "legacy_v2",
            "plant_steady_origin_ns": boot_origin,
            "receipt_line": rec.get("__line"),
            "hold_close_line": hc.get("__line"),
            "command_line": cmd_line,
            "sensor_line": sensor_line,
            "conversion_mode": conversion_basis,
            "start_sim_ns": int(t_start),
            "end_sim_ns": int(t_end),
            "dt_s": DT_S,
            "controller_nominal_hydro_sha256": nominal_hydro_sha,
            "plant_actual_present": plant_actual is not None,
            "z_k": z_k.tolist(),
            "q_exec": q_exec.tolist(),
            "x_start": x_start.tolist(),
            "x_end": x_end.tolist(),
            "x_nom_next": x_nom_next.tolist(),
            "y_k": y_k.tolist(),
            "included": True,
            "exclusion_reason": None,
        }
        provenance_rows.append(prov)
        admitted.append(prov)

    return RunExtraction(episode_id, str(run_dir), scenario, dataset_source, admitted, provenance_rows, stats)


def build_dataset(
    run_specs: list[tuple[Path, str]],
    out_dir: Path,
    *,
    allow_legacy_v2: bool = False,
) -> dict[str, Any]:
    """Build full residual dataset, contract, provenance log, and quality summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    all_admitted: list[dict[str, Any]] = []
    all_provenance: list[dict[str, Any]] = []
    run_summaries: list[dict[str, Any]] = []

    expected_nominal_hash: str | None = None
    nominal_hydro_dict: dict[str, float] | None = None

    # First locate canonical nominal hydro from first valid non-dry-run contract.
    for rdir, _ in run_specs:
        cpath = rdir / "contract.json"
        if not cpath.is_file():
            continue
        cdoc = json.loads(cpath.read_text(encoding="utf-8"))
        if str(cdoc.get("qualification") or "") in ("shipboard_dry_run", "shipboard_commissioning"):
            continue
        nh = _extract_controller_nominal(cdoc)
        expected_nominal_hash = nh.canonical_sha256(DT_S, RK4_SUBSTEPS)
        nominal_hydro_dict = nh.to_dict()
        break

    totals = {
        "runs_total": len(run_specs),
        "runs_accepted": 0,
        "runs_rejected": 0,
        "commands_entered": 0,
        "receipt_counts": {"bootstrap": 0, "ok": 0, "rejected": 0, "late": 0, "duplicate": 0, "other": 0},
        "ok_receipts": 0,
        "admitted_windows": 0,
        "excluded_windows": 0,
        "excluded_by_reason": {},
        "clock_resync_events": 0,
    }

    for rdir, split in run_specs:
        ext = extract_run(
            rdir,
            allow_legacy_v2=allow_legacy_v2,
            expected_nominal_hash=expected_nominal_hash,
            split=split,
        )
        run_summaries.append(ext.stats)
        if ext.stats["run_rejected_reason"] is not None:
            totals["runs_rejected"] += 1
        else:
            totals["runs_accepted"] += 1
        totals["commands_entered"] += ext.stats["commands_entered"]
        for k, v in ext.stats["receipt_counts"].items():
            totals["receipt_counts"][k] += v
        totals["ok_receipts"] += ext.stats["ok_receipts"]
        totals["admitted_windows"] += ext.stats["admitted_windows"]
        totals["excluded_windows"] += ext.stats["excluded_windows"]
        totals["clock_resync_events"] += ext.stats["clock_resync_events"]
        for k, v in ext.stats["excluded_by_reason"].items():
            totals["excluded_by_reason"][k] = totals["excluded_by_reason"].get(k, 0) + v
        all_admitted.extend(ext.admitted)
        all_provenance.extend(ext.provenance_rows)

    if all_admitted:
        Z = np.asarray([row["z_k"] for row in all_admitted], dtype=np.float64)
        Y = np.asarray([row["y_k"] for row in all_admitted], dtype=np.float64)
        X_start = np.asarray([row["x_start"] for row in all_admitted], dtype=np.float64)
        X_end = np.asarray([row["x_end"] for row in all_admitted], dtype=np.float64)
        X_nom = np.asarray([row["x_nom_next"] for row in all_admitted], dtype=np.float64)
        splits = np.asarray([row["split"] for row in all_admitted])
        ep_ids = np.asarray([row["episode_id"] for row in all_admitted])
    else:
        Z = np.zeros((0, 5), dtype=np.float64)
        Y = np.zeros((0, 3), dtype=np.float64)
        X_start = np.zeros((0, 6), dtype=np.float64)
        X_end = np.zeros((0, 6), dtype=np.float64)
        X_nom = np.zeros((0, 6), dtype=np.float64)
        splits = np.asarray([], dtype=str)
        ep_ids = np.asarray([], dtype=str)

    npz_path = out_dir / "dataset.npz"
    np.savez(
        npz_path,
        Z=Z,
        Y=Y,
        X_start=X_start,
        X_end=X_end,
        X_nom_next=X_nom,
        splits=splits,
        episode_ids=ep_ids,
    )

    prov_path = out_dir / "sample_provenance.jsonl"
    with prov_path.open("w", encoding="utf-8") as handle:
        for row in all_provenance:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    contract_doc = {
        "schema": DATASET_CONTRACT_SCHEMA,
        "dt_s": DT_S,
        "tick_ns": TICK_NS,
        "rk4_substeps": RK4_SUBSTEPS,
        "allow_legacy_v2": bool(allow_legacy_v2),
        "feature_names": FEATURE_NAMES,
        "feature_units": FEATURE_UNITS,
        "output_names": OUTPUT_NAMES,
        "output_units": OUTPUT_UNITS,
        "residual_definition": "nu_{k+1} - [F_0(x_k, q_exec_k; 0.2)]_nu",
        "controller_nominal_hydro": nominal_hydro_dict,
        "controller_nominal_hydro_sha256": expected_nominal_hash,
    }
    (out_dir / "dataset_contract.json").write_text(
        json.dumps(contract_doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    residual_stats: dict[str, Any] = {}
    feature_coverage: dict[str, Any] = {}
    if len(Y) > 0:
        for i, (name, unit) in enumerate(zip(OUTPUT_NAMES, OUTPUT_UNITS)):
            col = Y[:, i]
            residual_stats[name] = {
                "unit": unit,
                "min": float(np.min(col)),
                "max": float(np.max(col)),
                "max_abs": float(np.max(np.abs(col))),
                "rms": float(np.sqrt(np.mean(col ** 2))),
                "mean": float(np.mean(col)),
                "std": float(np.std(col)),
            }
        for i, (name, unit) in enumerate(zip(FEATURE_NAMES, FEATURE_UNITS)):
            col = Z[:, i]
            feature_coverage[name] = {
                "unit": unit,
                "min": float(np.min(col)),
                "max": float(np.max(col)),
                "std": float(np.std(col)),
            }

    quality_doc = {
        "schema": DATA_QUALITY_SCHEMA,
        "totals": totals,
        "residual_stats": residual_stats,
        "feature_coverage": feature_coverage,
        "runs": run_summaries,
        "dataset_contract_sha256": hashlib.sha256((out_dir / "dataset_contract.json").read_bytes()).hexdigest(),
        "sample_provenance_sha256": hashlib.sha256(prov_path.read_bytes()).hexdigest(),
        "dataset_npz_sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest(),
    }
    (out_dir / "data_quality.json").write_text(
        json.dumps(quality_doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return quality_doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="*", default=[], help="One or more run directories.")
    parser.add_argument("--split-manifest", default=None, help="JSON split manifest listing episodes and splits.")
    parser.add_argument("--out", required=True, help="Output directory for dataset artifacts.")
    parser.add_argument("--allow-legacy-v2", action="store_true", help="Allow v2 logs with sensor-verified start times.")
    args = parser.parse_args(argv)

    run_specs: list[tuple[Path, str]] = []
    if args.split_manifest:
        doc = json.loads(Path(args.split_manifest).read_text(encoding="utf-8"))
        for entry in doc.get("episodes", []):
            run_specs.append((Path(entry["run_dir"]), str(entry.get("split") or "unspecified")))
    for r in args.runs:
        run_specs.append((Path(r), "unspecified"))

    if not run_specs:
        parser.error("Provide --runs or --split-manifest")

    quality = build_dataset(run_specs, Path(args.out), allow_legacy_v2=args.allow_legacy_v2)
    print(json.dumps(quality["totals"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
