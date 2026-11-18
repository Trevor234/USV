#!/usr/bin/env python3
"""Tests for Scheme A velocity-residual dataset builder (WP2)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from dataset_builder import (
    DT_S,
    HYDRO_KEYS,
    TICK_NS,
    HydroParams,
    build_dataset,
    extract_run,
    fossen_rk4_step,
)

NOV16_RUNS_ROOT = Path(
    "/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/"
    "scheme-a-8scenarios-20261116T131548Z-arm-results/runs"
)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )


def _make_synthetic_v3_run(
    run_dir: Path,
    *,
    bias_nu: tuple[float, float, float] = (0.0, 0.0, 0.0),
    hold_reason_last: str = "expired",
    drop_last_hold_close: bool = False,
    duplicate_exec_idx: bool = False,
    mismatch_endpoint: bool = False,
    include_resync: bool = False,
    include_cross_input: bool = False,
    qualification: str = "controlled_sim",
    dataset_source: str | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    hydro = HydroParams()
    contract = {
        "schema": "usv-research-contract-v1",
        "qualification": qualification,
        "hydro": hydro.to_dict(),
    }
    run_doc: dict[str, Any] = {
        "schema": "usv-scheme-a-run-v1",
        "run_id": run_dir.name,
        "scenario": "nominal_hold",
    }
    if dataset_source is not None:
        run_doc["dataset_source"] = dataset_source
    (run_dir / "contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    (run_dir / "run.json").write_text(json.dumps(run_doc, indent=2), encoding="utf-8")

    boot_origin = 1_000_000_000
    boot_id = "boot-test-1"
    clk_id = "plant_sim_clock:CLOCK_MONOTONIC"
    c_hash = "contract-hash-test"

    plant_rows: list[dict[str, Any]] = [
        {
            "type": "plant_ready",
            "run_id": run_dir.name,
            "boot": boot_id,
            "contract_hash": c_hash,
            "clock": "CLOCK_MONOTONIC",
            "clock_identity": clk_id,
            "steady_origin_ns": boot_origin,
        },
        {
            "type": "bootstrap_receipt",
            "schema": "p1-plant-receipt-v3",
            "run_id": run_dir.name,
            "boot_id": boot_id,
            "contract_hash": c_hash,
            "disposition": "bootstrap",
            "sequence": 0,
            "tick": 0,
            "execution_index": 0,
            "clock_epoch": 1,
            "clock_identity": clk_id,
            "plant_steady_origin_ns": boot_origin,
            "state_sample_sim_ns": 0,
            "planned_window_end_sim_ns": 0,
            "executed_begin_steady_ns": boot_origin,
            "hold_end_steady_ns": boot_origin,
            "state": [0.0, 0.0, 0.0, 0.4, 0.0, 0.0],
            "thrust_n": [0.0, 0.0],
        },
    ]
    reg_rows: list[dict[str, Any]] = []

    x = np.array([0.0, 0.0, 0.1, 0.5, -0.04, 0.08], dtype=np.float64)
    q = np.array([18.0, 12.0], dtype=np.float64)
    du, dv, dr = bias_nu

    n_windows = 3
    for idx in range(1, n_windows + 1):
        t_start = idx * TICK_NS
        t_end = t_start + TICK_NS
        reg_rows.append(
            {
                "type": "plant_command",
                "sequence": idx,
                "tick": idx,
                "thrust_n": q.tolist(),
            }
        )
        plant_rows.append(
            {
                "type": "plant_receipt",
                "schema": "p1-plant-receipt-v3",
                "run_id": run_dir.name,
                "boot_id": boot_id,
                "contract_hash": c_hash,
                "disposition": "ok",
                "sequence": idx,
                "tick": idx,
                "execution_index": idx,
                "clock_epoch": 1,
                "clock_identity": clk_id,
                "plant_steady_origin_ns": boot_origin,
                "state_sample_sim_ns": t_start,
                "planned_window_end_sim_ns": t_end,
                "executed_begin_steady_ns": boot_origin + t_start,
                "hold_end_steady_ns": boot_origin + t_end,
                "state": x.tolist(),
                "thrust_n": q.tolist(),
            }
        )
        if duplicate_exec_idx and idx == 2:
            plant_rows.append(dict(plant_rows[-1]))

        x_next = fossen_rk4_step(x, q, hydro, DT_S, 4)
        x_next_actual = x_next.copy()
        x_next_actual[3] += du
        x_next_actual[4] += dv
        x_next_actual[5] += dr

        if not (drop_last_hold_close and idx == n_windows):
            end_sample = t_end + (10_000_000 if (mismatch_endpoint and idx == 1) else 0)
            reason = hold_reason_last if idx == n_windows else "expired"
            plant_rows.append(
                {
                    "type": "plant_hold_close",
                    "schema": "p1-plant-hold-close-v2",
                    "boot_id": boot_id,
                    "plant_steady_origin_ns": boot_origin,
                    "execution_index": idx,
                    "clock_epoch": 1,
                    "clock_identity": clk_id,
                    "close_sim_ns": t_end,
                    "state_sample_sim_ns": end_sample,
                    "executed_end_steady_ns": boot_origin + t_end,
                    "reason": reason,
                    "state": x_next_actual.tolist(),
                }
            )

        if include_resync and idx == 2:
            plant_rows.append(
                {
                    "type": "plant_clock_resync",
                    "sim_ns": t_start + 50_000_000,
                }
            )
        if include_cross_input and idx == 2:
            plant_rows.append(
                {
                    "type": "plant_receipt",
                    "schema": "p1-plant-receipt-v3",
                    "run_id": run_dir.name,
                    "boot_id": boot_id,
                    "contract_hash": c_hash,
                    "disposition": "ok",
                    "sequence": 99,
                    "tick": 99,
                    "execution_index": 99,
                    "clock_epoch": 1,
                    "clock_identity": clk_id,
                    "plant_steady_origin_ns": boot_origin,
                    "state_sample_sim_ns": t_start + 100_000_000,
                    "planned_window_end_sim_ns": t_start + 100_000_000 + TICK_NS,
                    "executed_begin_steady_ns": boot_origin + t_start + 100_000_000,
                    "hold_end_steady_ns": boot_origin + t_start + 100_000_000 + TICK_NS,
                    "state": x.tolist(),
                    "thrust_n": q.tolist(),
                }
            )
            plant_rows.append(
                {
                    "type": "plant_hold_close",
                    "schema": "p1-plant-hold-close-v2",
                    "boot_id": boot_id,
                    "plant_steady_origin_ns": boot_origin,
                    "execution_index": 99,
                    "clock_epoch": 1,
                    "clock_identity": clk_id,
                    "close_sim_ns": t_start + 100_000_000 + TICK_NS,
                    "state_sample_sim_ns": t_start + 100_000_000 + TICK_NS,
                    "executed_end_steady_ns": boot_origin + t_start + 100_000_000 + TICK_NS,
                    "reason": "expired",
                    "state": x_next.tolist(),
                }
            )
        x = x_next_actual

    _write_jsonl(run_dir / "plant.source.jsonl", plant_rows)
    _write_jsonl(run_dir / "regulator.source.jsonl", reg_rows)


def _make_synthetic_v2_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    hydro = HydroParams()
    (run_dir / "contract.json").write_text(
        json.dumps({"schema": "usv-research-contract-v1", "qualification": "controlled_sim", "hydro": hydro.to_dict()}),
        encoding="utf-8",
    )
    (run_dir / "run.json").write_text(
        json.dumps({"schema": "usv-scheme-a-run-v1", "run_id": run_dir.name, "scenario": "legacy_v2_test"}),
        encoding="utf-8",
    )
    boot_origin = 2_000_000_000
    x0 = np.array([1.0, -0.5, 0.2, 0.7, 0.02, -0.05], dtype=np.float64)
    q0 = np.array([14.0, 18.0], dtype=np.float64)
    x1 = fossen_rk4_step(x0, q0, hydro, DT_S, 4)
    plant_rows = [
        {
            "type": "bootstrap_receipt",
            "schema": "p1-plant-receipt-v2",
            "run_id": run_dir.name,
            "boot_id": "boot-v2",
            "contract_hash": "hash-v2",
            "disposition": "bootstrap",
            "sequence": 0,
            "tick": 0,
            "execution_index": 0,
            "clock_epoch": 1,
            "plant_steady_origin_ns": boot_origin,
            "executed_begin_steady_ns": boot_origin,
            "hold_end_steady_ns": boot_origin,
            "state": x0.tolist(),
            "thrust_n": [0.0, 0.0],
        },
        {
            "type": "plant_sensors",
            "sim_ns": TICK_NS,
            "state": x0.tolist(),
        },
        {
            "type": "plant_receipt",
            "schema": "p1-plant-receipt-v2",
            "run_id": run_dir.name,
            "boot_id": "boot-v2",
            "contract_hash": "hash-v2",
            "disposition": "ok",
            "sequence": 1,
            "tick": 1,
            "execution_index": 1,
            "clock_epoch": 1,
            "plant_steady_origin_ns": boot_origin,
            "executed_begin_steady_ns": boot_origin + TICK_NS,
            "hold_end_steady_ns": boot_origin + 2 * TICK_NS,
            "state": x0.tolist(),
            "thrust_n": q0.tolist(),
        },
        {
            "type": "plant_hold_close",
            "schema": "p1-plant-hold-close-v1",
            "execution_index": 1,
            "close_sim_ns": 2 * TICK_NS,
            "executed_end_steady_ns": boot_origin + 2 * TICK_NS,
            "reason": "expired",
            "state": x1.tolist(),
        },
    ]
    _write_jsonl(run_dir / "plant.source.jsonl", plant_rows)
    _write_jsonl(run_dir / "regulator.source.jsonl", [{"type": "plant_command", "sequence": 1, "tick": 1, "thrust_n": q0.tolist()}])


def test_fossen_rk4_step_properties_and_substep_accuracy() -> None:
    hydro = HydroParams()
    x0 = np.array([0.0, 0.0, 3.1, 0.6, -0.05, 0.3], dtype=np.float64)
    q = np.array([20.0, 10.0], dtype=np.float64)
    x_4 = fossen_rk4_step(x0, q, hydro, DT_S, 4)
    x_40 = fossen_rk4_step(x0, q, hydro, DT_S, 40)
    assert np.all(np.isfinite(x_4))
    assert -np.pi <= x_4[2] <= np.pi
    assert np.max(np.abs(x_4[3:] - x_40[3:])) < 1e-6
    assert len(HYDRO_KEYS) == 19


def test_v3_zero_residual_and_known_bias_recovery(tmp_path: Path) -> None:
    zero_dir = tmp_path / "run_zero"
    bias_dir = tmp_path / "run_bias"
    _make_synthetic_v3_run(zero_dir, bias_nu=(0.0, 0.0, 0.0))
    _make_synthetic_v3_run(bias_dir, bias_nu=(0.035, -0.012, 0.025))

    q_zero = build_dataset([(zero_dir, "train")], tmp_path / "out_zero")
    assert q_zero["totals"]["admitted_windows"] == 3
    assert q_zero["totals"]["excluded_windows"] == 0
    for name in ("delta_u_residual", "delta_v_residual", "delta_r_residual"):
        assert q_zero["residual_stats"][name]["max_abs"] < 1e-12

    q_bias = build_dataset([(bias_dir, "calib")], tmp_path / "out_bias")
    assert q_bias["totals"]["admitted_windows"] == 3
    npz = np.load(tmp_path / "out_bias" / "dataset.npz")
    assert npz["Z"].shape == (3, 5)
    assert npz["Y"].shape == (3, 3)
    assert np.allclose(npz["Y"], np.array([0.035, -0.012, 0.025]), atol=1e-12)
    prov_lines = [
        json.loads(line)
        for line in (tmp_path / "out_bias" / "sample_provenance.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(prov_lines) == 3
    assert all(p["included"] and p["conversion_mode"] == "native_v3_receipt_and_hold_close" for p in prov_lines)
    assert all(p["receipt_line"] is not None and p["hold_close_line"] is not None and p["command_line"] is not None for p in prov_lines)


def test_quality_exclusions_and_dry_run_guard(tmp_path: Path) -> None:
    r_stop = tmp_path / "r_stop"
    r_miss = tmp_path / "r_miss"
    r_dup = tmp_path / "r_dup"
    r_end = tmp_path / "r_end"
    r_resync = tmp_path / "r_resync"
    r_cross = tmp_path / "r_cross"
    r_dry = tmp_path / "r_dry"

    _make_synthetic_v3_run(r_stop, hold_reason_last="stop")
    _make_synthetic_v3_run(r_miss, drop_last_hold_close=True)
    _make_synthetic_v3_run(r_dup, duplicate_exec_idx=True)
    _make_synthetic_v3_run(r_end, mismatch_endpoint=True)
    _make_synthetic_v3_run(r_resync, include_resync=True)
    _make_synthetic_v3_run(r_cross, include_cross_input=True)
    _make_synthetic_v3_run(r_dry, qualification="shipboard_dry_run")

    assert extract_run(r_stop).stats["excluded_by_reason"]["stop_truncation"] == 1
    assert extract_run(r_miss).stats["excluded_by_reason"]["missing_hold_close"] == 1
    assert extract_run(r_dup).stats["excluded_by_reason"]["duplicate_execution_index"] == 2
    assert extract_run(r_end).stats["excluded_by_reason"]["endpoint_time_mismatch"] == 1
    assert extract_run(r_resync).stats["excluded_by_reason"]["clock_resync_across_window"] == 1
    cross_stats = extract_run(r_cross).stats
    assert cross_stats["excluded_by_reason"]["cross_input_window"] == 2

    dry_ext = extract_run(r_dry)
    assert dry_ext.stats["run_rejected_reason"] == "dry_run_not_executable_truth"
    assert len(dry_ext.admitted) == 0

    q_all = build_dataset(
        [(r_stop, "train"), (r_dry, "train")],
        tmp_path / "out_mixed",
    )
    assert q_all["totals"]["runs_rejected"] == 1
    assert q_all["totals"]["admitted_windows"] == 2
    assert q_all["totals"]["excluded_by_reason"]["stop_truncation"] == 1


def test_legacy_v2_disallowed_by_default_and_allowed_explicitly(tmp_path: Path) -> None:
    v2_dir = tmp_path / "run_v2"
    _make_synthetic_v2_run(v2_dir)

    ext_default = extract_run(v2_dir, allow_legacy_v2=False)
    assert ext_default.stats["run_rejected_reason"] == "legacy_v2_disallowed"
    assert len(ext_default.admitted) == 0

    ext_allowed = extract_run(v2_dir, allow_legacy_v2=True)
    assert ext_allowed.stats["run_rejected_reason"] is None
    assert len(ext_allowed.admitted) == 1
    assert ext_allowed.admitted[0]["conversion_mode"] == "legacy_v2_sensor_and_hold_close_join"
    assert ext_allowed.admitted[0]["sensor_line"] is not None
    assert max(abs(v) for v in ext_allowed.admitted[0]["y_k"]) < 1e-12


@pytest.mark.skipif(not NOV16_RUNS_ROOT.is_dir(), reason="Historical Nov 16 evidence directory not present")
def test_historical_nov16_evidence_replay_arm_runs(tmp_path: Path) -> None:
    p4_dirs = sorted(p for p in NOV16_RUNS_ROOT.glob("p4_*") if p.is_dir())
    assert len(p4_dirs) == 8

    # Must be rejected when allow_legacy_v2=False
    q_strict = build_dataset([(p, "audit") for p in p4_dirs], tmp_path / "strict", allow_legacy_v2=False)
    assert q_strict["totals"]["runs_rejected"] == 8
    assert q_strict["totals"]["admitted_windows"] == 0

    # Must replay all 208 full windows (excluding 5 stop_truncation) at machine-epsilon residual when allow_legacy_v2=True
    q_v2 = build_dataset([(p, "audit") for p in p4_dirs], tmp_path / "v2_replay", allow_legacy_v2=True)
    assert q_v2["totals"]["runs_accepted"] == 8
    assert q_v2["totals"]["ok_receipts"] == 213
    assert q_v2["totals"]["admitted_windows"] == 208
    assert q_v2["totals"]["excluded_by_reason"].get("stop_truncation") == 5
    for name in ("delta_u_residual", "delta_v_residual", "delta_r_residual"):
        assert q_v2["residual_stats"][name]["max_abs"] < 1e-12
