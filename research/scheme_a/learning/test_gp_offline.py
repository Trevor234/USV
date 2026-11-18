#!/usr/bin/env python3
"""Offline WP4 tests: zero-residual gate, Exact vs Sparse GP generalization, snapshot integrity."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import casadi as ca
import numpy as np
import pytest

from dataset_builder import FEATURE_NAMES, OUTPUT_NAMES, HydroParams
from gp_model import (
    GP_SNAPSHOT_SCHEMA,
    MultiChannelSparseGP,
    fit_exact_channel_gp,
    train_sparse_gp_bundle,
)
from train_residual_gp import compute_regression_metrics


def _synthetic_residual_fn(Z: np.ndarray) -> np.ndarray:
    """Physically realistic nonlinear 5D -> 3D velocity residual over (u, v, r, T_L, T_R)."""
    u, v, r, tl, tr = Z[:, 0], Z[:, 1], Z[:, 2], Z[:, 3], Z[:, 4]
    du = -0.025 * u - 0.04 * u * np.abs(u) + 0.0015 * (tl + tr) - 0.008 * v * r
    dv = -0.015 * v + 0.012 * u * r
    dr = -0.03 * r - 0.002 * r * np.abs(r) + 0.001 * (tr - tl)
    return np.column_stack([du, dv, dr])


def test_nominal_zero_residual_collapses_to_numerical_zero(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    Z = rng.uniform([-0.1, -0.3, -0.4, -10.0, -10.0], [1.1, 0.3, 0.4, 20.0, 20.0], size=(200, 5))
    Y = np.zeros((200, 3), dtype=np.float64)
    model = train_sparse_gp_bundle(
        Z, Y,
        nominal_model_hash=HydroParams().canonical_sha256(),
        snapshot_id="zero_gate",
        M=32,
        seed=0,
    )
    Z_test = rng.uniform([-0.1, -0.3, -0.4, -10.0, -10.0], [1.1, 0.3, 0.4, 20.0, 20.0], size=(40, 5))
    pred = model.predict(Z_test, apply_clip=False, ood_fallback_zero=False)
    assert np.max(np.abs(pred["mean"])) < 1e-12
    assert np.max(pred["std"]) < 1e-10


def test_sparse_gp_outperforms_nominal_and_matches_exact_gp(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    # Train on restricted maneuver manifold (u in [0.2, 0.9], modest turns)
    Z_train = np.column_stack([
        rng.uniform(0.2, 0.9, 600),
        rng.uniform(-0.25, 0.25, 600),
        rng.uniform(-0.25, 0.25, 600),
        rng.uniform(0.0, 14.0, 600),
        rng.uniform(0.0, 14.0, 600),
    ])
    Y_train = _synthetic_residual_fn(Z_train) + rng.normal(0.0, 1e-3, size=(600, 3))

    # Held-out test points (unseen combination / reverse turns within manifold)
    Z_test = np.column_stack([
        rng.uniform(0.25, 0.85, 200),
        rng.uniform(-0.2, 0.2, 200),
        rng.uniform(-0.22, 0.22, 200),
        rng.uniform(1.0, 13.0, 200),
        rng.uniform(1.0, 13.0, 200),
    ])
    Y_test = _synthetic_residual_fn(Z_test)

    nom_hash = HydroParams().canonical_sha256()
    m32 = train_sparse_gp_bundle(Z_train, Y_train, nominal_model_hash=nom_hash, snapshot_id="m32", M=32, seed=2)
    m64 = train_sparse_gp_bundle(Z_train, Y_train, nominal_model_hash=nom_hash, snapshot_id="m64", M=64, seed=2)

    p32 = m32.predict(Z_test, apply_clip=False, ood_fallback_zero=False)
    p64 = m64.predict(Z_test, apply_clip=False, ood_fallback_zero=False)
    zero_metrics = compute_regression_metrics(Y_test, np.zeros_like(Y_test), np.ones_like(Y_test) * 0.05)
    m32_metrics = compute_regression_metrics(Y_test, p32["mean"], p32["std"])
    m64_metrics = compute_regression_metrics(Y_test, p64["mean"], p64["std"])

    # Exact GP benchmark
    ex_mu = np.zeros_like(Y_test)
    ex_std = np.zeros_like(Y_test)
    Z_tr_s = (Z_train - m64.x_mean) / m64.x_std
    Z_te_s = (Z_test - m64.x_mean) / m64.x_std
    for c in range(3):
        ex = fit_exact_channel_gp(Z_tr_s, Y_train[:, c], seed=2 + c)
        mu_c, var_c = ex.predict(Z_te_s)
        ex_mu[:, c] = mu_c
        ex_std[:, c] = np.sqrt(var_c)
    ex_metrics = compute_regression_metrics(Y_test, ex_mu, ex_std)

    assert m64_metrics["rmse_mean"] < 0.15 * zero_metrics["rmse_mean"]
    assert m32_metrics["rmse_mean"] < 0.20 * zero_metrics["rmse_mean"]
    assert abs(m64_metrics["rmse_mean"] - ex_metrics["rmse_mean"]) < 5e-3
    assert 0.85 <= m64_metrics["coverage95_mean"] <= 1.0


def test_snapshot_roundtrip_casadi_parity_and_ood_guard(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    Z_train = rng.uniform([0.1, -0.2, -0.2, 0.0, 0.0], [1.0, 0.2, 0.2, 15.0, 15.0], size=(240, 5))
    Y_train = _synthetic_residual_fn(Z_train)
    snap_path = tmp_path / "gp_snapshot.json"
    model = train_sparse_gp_bundle(
        Z_train,
        Y_train,
        nominal_model_hash="abc123",
        snapshot_id="test_snap",
        M=32,
        seed=5,
    )
    sha = model.save(snap_path)
    loaded = MultiChannelSparseGP.load(snap_path)
    assert loaded.snapshot_sha256 == sha
    doc = json.loads(snap_path.read_text(encoding="utf-8"))
    assert doc["schema"] == GP_SNAPSHOT_SCHEMA
    assert doc["feature_names"] == FEATURE_NAMES
    assert doc["output_names"] == OUTPUT_NAMES

    # Tampering must be detected.
    bad_doc = dict(doc)
    bad_doc["snapshot_id"] = "tampered"
    with pytest.raises(ValueError, match="sha256 mismatch"):
        MultiChannelSparseGP.from_snapshot_dict(bad_doc)

    # Verify independent CasADi symbolic formula matches Python inference to < 1e-12.
    q = Z_train[:8]
    pred = loaded.predict(q, apply_clip=False, ood_fallback_zero=False)
    z_sym = ca.SX.sym("z", 5)
    z_std_sym = (z_sym - ca.DM(loaded.x_mean)) / ca.DM(loaded.x_std)
    mu_sym = []
    for ch in loaded.channels:
        sf2 = float(ch.signal_std ** 2)
        Zm = ca.DM(ch.Z_m_std)
        ls2 = ca.DM(ch.lengthscales ** 2)
        alpha = ca.DM(ch.alpha_mu_phys)
        k_vec = ca.SX.zeros(ch.M, 1)
        for m in range(ch.M):
            diff = z_std_sym - Zm[m, :].T
            k_vec[m] = sf2 * ca.exp(-0.5 * ca.sum1((diff * diff) / ls2))
        mu_sym.append(ca.dot(k_vec, alpha))
    fn = ca.Function("gp_mean", [z_sym], [ca.vertcat(*mu_sym)])
    for i in range(len(q)):
        ca_val = np.asarray(fn(q[i])).ravel()
        np.testing.assert_allclose(ca_val, pred["mean"][i], atol=1e-12)

    # Verify Python vs C++ p1_gp_eval_cli parity (< 1e-12) when built executable exists.
    cli = Path("/home/trevor/usv_scheme_a_wt/install/scheme_a/usv_research_safety_cpp/lib/usv_research_safety_cpp/p1_gp_eval_cli")
    if cli.is_file():
        q_all = np.vstack([Z_train[:10], [[5.0, 2.0, 2.0, 40.0, -40.0]]])
        q_file = tmp_path / "cpp_queries.json"
        q_file.write_text(json.dumps({"queries": q_all.tolist()}), encoding="utf-8")
        res = subprocess.run([str(cli), str(snap_path), str(q_file)], capture_output=True, text=True, check=True)
        cout = json.loads(res.stdout)
        assert cout["snapshot_sha256"] == sha
        py_all = loaded.predict(q_all)
        c_mu = np.array([r["mean"] for r in cout["predictions"]])
        c_std = np.array([r["std"] for r in cout["predictions"]])
        assert float(np.max(np.abs(c_mu - py_all["mean"]))) < 1e-12
        assert float(np.max(np.abs(c_std - py_all["std"]))) < 1e-12
        assert [r["ood"] for r in cout["predictions"]] == py_all["ood"].tolist()

    # OOD query far outside training envelope must flag ood=True and fallback to 0.
    z_ood = np.array([[5.0, 2.0, 2.0, 40.0, -40.0]], dtype=np.float64)
    ood_pred = loaded.predict(z_ood)
    assert bool(ood_pred["ood"][0]) is True
    np.testing.assert_allclose(ood_pred["mean"][0], [0.0, 0.0, 0.0], atol=1e-12)
