#!/usr/bin/env python3
"""Exact GP & Titsias Sparse Variational GP (ARD-RBF) for Scheme A residuals."""
from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import cho_factor, cho_solve, solve_triangular
from scipy.optimize import minimize

from dataset_builder import (
    DT_S,
    FEATURE_NAMES,
    FEATURE_UNITS,
    OUTPUT_NAMES,
    OUTPUT_UNITS,
    RK4_SUBSTEPS,
)

GP_SNAPSHOT_SCHEMA = "gp-snapshot-v1"
CODEGEN_LAYOUT_VERSION = "usv_dyn_nmpc_np12_ny13_v1"
INPUT_DIM = 5
OUTPUT_DIM = 3
DEFAULT_CLIP_BOUNDS = [
    [-0.35, 0.35],  # delta_u [m/s]
    [-0.35, 0.35],  # delta_v [m/s]
    [-0.35, 0.35],  # delta_r [rad/s]
]


def _ard_sq_dist(X1: np.ndarray, X2: np.ndarray, lengthscales: np.ndarray) -> np.ndarray:
    """Compute scaled squared Euclidean distances between rows of X1 and X2."""
    ls = np.maximum(np.asarray(lengthscales, dtype=np.float64), 1e-6)
    X1s = X1 / ls[None, :]
    X2s = X2 / ls[None, :]
    n1 = np.sum(X1s * X1s, axis=1, keepdims=True)
    n2 = np.sum(X2s * X2s, axis=1, keepdims=True).T
    d2 = n1 + n2 - 2.0 * (X1s @ X2s.T)
    return np.maximum(d2, 0.0)


def _ard_rbf_kernel(
    X1: np.ndarray,
    X2: np.ndarray,
    signal_std: float,
    lengthscales: np.ndarray,
) -> np.ndarray:
    d2 = _ard_sq_dist(X1, X2, lengthscales)
    return (signal_std ** 2) * np.exp(-0.5 * d2)


def _cholesky_with_jitter(mat: np.ndarray, base_jitter: float = 1e-7) -> np.ndarray:
    """Compute lower Cholesky factor L with geometric jitter escalation."""
    n = mat.shape[0]
    eye = np.eye(n, dtype=np.float64)
    jitter = float(base_jitter)
    for _ in range(8):
        try:
            return np.linalg.cholesky(0.5 * (mat + mat.T) + jitter * eye)
        except np.linalg.LinAlgError:
            jitter *= 10.0
    eigvals, eigvecs = np.linalg.eigh(0.5 * (mat + mat.T))
    eigvals = np.maximum(eigvals, 1e-8)
    repaired = (eigvecs * eigvals) @ eigvecs.T
    return np.linalg.cholesky(repaired + 1e-7 * eye)


def select_inducing_kmeans(Z_std: np.ndarray, M: int, seed: int = 0) -> np.ndarray:
    """Deterministic k-means++ seeding + Lloyd refinement in 5D standardized space."""
    N = Z_std.shape[0]
    if N <= M:
        if N == M:
            return Z_std.copy()
        reps = int(math.ceil(M / max(1, N)))
        return np.tile(Z_std, (reps, 1))[:M].copy()

    rng = np.random.default_rng(seed)
    centers = np.empty((M, Z_std.shape[1]), dtype=np.float64)
    first = int(rng.integers(0, N))
    centers[0] = Z_std[first]
    d2 = np.sum((Z_std - centers[0]) ** 2, axis=1)
    for m in range(1, M):
        probs = d2 / max(float(np.sum(d2)), 1e-12)
        nxt = int(rng.choice(N, p=probs))
        centers[m] = Z_std[nxt]
        d2 = np.minimum(d2, np.sum((Z_std - centers[m]) ** 2, axis=1))

    for _ in range(15):
        # Assign to nearest centroid in vectorized batches.
        c2 = np.sum(centers ** 2, axis=1)[None, :]
        z2 = np.sum(Z_std ** 2, axis=1, keepdims=True)
        dists = np.maximum(z2 + c2 - 2.0 * (Z_std @ centers.T), 0.0)
        labels = np.argmin(dists, axis=1)
        new_centers = centers.copy()
        for m in range(M):
            mask = labels == m
            if np.any(mask):
                new_centers[m] = np.mean(Z_std[mask], axis=0)
        if np.max(np.abs(new_centers - centers)) < 1e-5:
            centers = new_centers
            break
        centers = new_centers
    return centers


@dataclass
class ExactChannelGP:
    signal_std: float
    lengthscales: np.ndarray
    noise_std: float
    X_std: np.ndarray
    L: np.ndarray
    alpha: np.ndarray
    y_std_scale: float
    neg_log_marginal_likelihood: float

    def predict(self, Z_std: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.y_std_scale <= 1e-11:
            n = Z_std.shape[0]
            return np.zeros(n, dtype=np.float64), np.full(n, 1e-12, dtype=np.float64)
        k_star = _ard_rbf_kernel(self.X_std, Z_std, self.signal_std, self.lengthscales)
        mu_s = k_star.T @ self.alpha
        v = solve_triangular(self.L, k_star, lower=True)
        var_lat = np.maximum(0.0, (self.signal_std ** 2) - np.sum(v * v, axis=0))
        var_pred = var_lat + (self.noise_std ** 2)
        return mu_s * self.y_std_scale, var_pred * (self.y_std_scale ** 2)


@dataclass
class SparseChannelGP:
    M: int
    Z_m_std: np.ndarray
    signal_std: float
    lengthscales: np.ndarray
    noise_std: float
    y_std_scale: float
    alpha_mu_phys: np.ndarray  # shape (M,), directly gives mu_phys = k_*^T alpha_mu_phys
    L_m_inv: np.ndarray        # shape (M, M), inverse lower Cholesky of K_mm
    L_B_inv: np.ndarray        # shape (M, M), inverse lower Cholesky of B = I + A A^T
    elbo: float

    def predict(self, Z_std: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (mean_phys, total_var_phys, latent_var_phys)."""
        if self.y_std_scale <= 1e-11:
            n = Z_std.shape[0]
            z = np.zeros(n, dtype=np.float64)
            v = np.full(n, 1e-24, dtype=np.float64)
            return z, v, v
        k_star = _ard_rbf_kernel(self.Z_m_std, Z_std, self.signal_std, self.lengthscales)  # (M, Q)
        mu_phys = k_star.T @ self.alpha_mu_phys
        v = self.L_m_inv @ k_star  # (M, Q)
        w = self.L_B_inv @ v       # (M, Q)
        var_lat_std = np.maximum(
            0.0,
            (self.signal_std ** 2) - np.sum(v * v, axis=0) + np.sum(w * w, axis=0),
        )
        var_tot_std = var_lat_std + (self.noise_std ** 2)
        s2 = self.y_std_scale ** 2
        return mu_phys, var_tot_std * s2, var_lat_std * s2


def fit_exact_channel_gp(
    Z_std: np.ndarray,
    y: np.ndarray,
    *,
    max_exact_n: int = 1000,
    seed: int = 0,
) -> ExactChannelGP:
    """Fit exact Cholesky GP on standardized inputs (analytic gradient L-BFGS-B)."""
    y = np.asarray(y, dtype=np.float64)
    max_abs = float(np.max(np.abs(y))) if len(y) else 0.0
    if max_abs < 1e-9:
        idx = np.arange(min(len(y), 32))
        X_sub = Z_std[idx].copy()
        return ExactChannelGP(
            signal_std=1e-12,
            lengthscales=np.ones(INPUT_DIM, dtype=np.float64),
            noise_std=1e-12,
            X_std=X_sub,
            L=np.eye(len(idx), dtype=np.float64),
            alpha=np.zeros(len(idx), dtype=np.float64),
            y_std_scale=0.0,
            neg_log_marginal_likelihood=0.0,
        )

    if len(y) > max_exact_n:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(len(y), size=max_exact_n, replace=False))
        X_sub = Z_std[idx].copy()
        y_sub = y[idx].copy()
    else:
        X_sub = Z_std.copy()
        y_sub = y.copy()

    y_scale = max(float(np.std(y_sub)), 1e-4)
    y_norm = y_sub / y_scale
    N = len(y_norm)
    d2_mats = [((X_sub[:, [d]] - X_sub[:, [d]].T) ** 2) for d in range(INPUT_DIM)]

    def nlml_and_grad(theta: np.ndarray) -> tuple[float, np.ndarray]:
        sf = math.exp(float(theta[0]))
        ls = np.exp(theta[1 : 1 + INPUT_DIM])
        sn = math.exp(float(theta[1 + INPUT_DIM]))
        scaled = np.zeros((N, N), dtype=np.float64)
        for d in range(INPUT_DIM):
            scaled += d2_mats[d] / (ls[d] ** 2)
        Kf = (sf ** 2) * np.exp(-0.5 * scaled)
        K = Kf.copy()
        K[np.diag_indices(N)] += (sn ** 2) + 1e-7
        try:
            L = np.linalg.cholesky(K)
        except np.linalg.LinAlgError:
            return 1e12, np.zeros_like(theta)
        alpha = solve_triangular(L.T, solve_triangular(L, y_norm, lower=True), lower=False)
        logdet = 2.0 * float(np.sum(np.log(np.diag(L))))
        nll = 0.5 * float(y_norm @ alpha) + 0.5 * logdet + 0.5 * N * math.log(2.0 * math.pi)
        if not math.isfinite(nll):
            return 1e12, np.zeros_like(theta)

        Linv = solve_triangular(L, np.eye(N, dtype=np.float64), lower=True)
        Kinv = Linv.T @ Linv
        W = Kinv - np.outer(alpha, alpha)
        W_Kf = W * Kf
        grad = np.empty_like(theta)
        grad[0] = float(np.sum(W_Kf))
        for d in range(INPUT_DIM):
            grad[1 + d] = 0.5 * float(np.sum(W_Kf * (d2_mats[d] / (ls[d] ** 2))))
        grad[1 + INPUT_DIM] = (sn ** 2) * float(np.trace(W))
        return nll, grad

    bounds = [
        (math.log(1e-3), math.log(10.0)),
        *[(math.log(0.15), math.log(40.0)) for _ in range(INPUT_DIM)],
        (math.log(1e-4), math.log(2.0)),
    ]
    best_res = None
    inits = [
        np.array([0.0, *([0.4] * INPUT_DIM), math.log(0.15)], dtype=np.float64),
        np.array([math.log(0.7), *([1.2] * INPUT_DIM), math.log(0.05)], dtype=np.float64),
    ]
    for init in inits:
        res = minimize(
            nlml_and_grad, init, jac=True, method="L-BFGS-B",
            bounds=bounds, options={"maxiter": 60},
        )
        if best_res is None or res.fun < best_res.fun:
            best_res = res

    opt = best_res.x
    sf = math.exp(float(opt[0]))
    ls = np.exp(opt[1 : 1 + INPUT_DIM])
    sn = math.exp(float(opt[1 + INPUT_DIM]))
    K = _ard_rbf_kernel(X_sub, X_sub, sf, ls)
    K[np.diag_indices(N)] += (sn ** 2) + 1e-7
    L = _cholesky_with_jitter(K)
    alpha = cho_solve((L, True), y_norm)
    return ExactChannelGP(
        signal_std=sf,
        lengthscales=ls,
        noise_std=sn,
        X_std=X_sub,
        L=L,
        alpha=alpha,
        y_std_scale=y_scale,
        neg_log_marginal_likelihood=float(best_res.fun),
    )


def fit_sparse_channel_gp(
    Z_std: np.ndarray,
    y: np.ndarray,
    *,
    M: int = 64,
    seed: int = 0,
    maxiter: int = 80,
) -> SparseChannelGP:
    """Fit collapsed Titsias (2009) Sparse Variational GP on full dataset."""
    y = np.asarray(y, dtype=np.float64)
    Z_m = select_inducing_kmeans(Z_std, M=M, seed=seed)
    max_abs = float(np.max(np.abs(y))) if len(y) else 0.0
    if max_abs < 1e-9:
        M_eff = Z_m.shape[0]
        return SparseChannelGP(
            M=M_eff,
            Z_m_std=Z_m,
            signal_std=1e-12,
            lengthscales=np.ones(INPUT_DIM, dtype=np.float64),
            noise_std=1e-12,
            y_std_scale=0.0,
            alpha_mu_phys=np.zeros(M_eff, dtype=np.float64),
            L_m_inv=np.eye(M_eff, dtype=np.float64),
            L_B_inv=np.eye(M_eff, dtype=np.float64),
            elbo=0.0,
        )

    y_scale = max(float(np.std(y)), 1e-4)
    y_norm = y / y_scale
    N = len(y_norm)
    y_norm2 = float(np.dot(y_norm, y_norm))
    M_eff = Z_m.shape[0]

    # Precompute per-dimension squared differences to accelerate ELBO optimization.
    d2_mm = [((Z_m[:, [d]] - Z_m[:, [d]].T) ** 2) for d in range(INPUT_DIM)]
    d2_mn = [((Z_m[:, [d]] - Z_std[:, [d]].T) ** 2) for d in range(INPUT_DIM)]

    def neg_elbo(theta: np.ndarray) -> float:
        sf = math.exp(float(theta[0]))
        ls = np.exp(theta[1 : 1 + INPUT_DIM])
        sn = math.exp(float(theta[1 + INPUT_DIM]))
        sf2 = sf * sf
        sn2 = sn * sn

        s_mm = np.zeros((M_eff, M_eff), dtype=np.float64)
        s_mn = np.zeros((M_eff, N), dtype=np.float64)
        for d in range(INPUT_DIM):
            inv_l2 = 1.0 / (ls[d] * ls[d])
            s_mm += d2_mm[d] * inv_l2
            s_mn += d2_mn[d] * inv_l2

        K_mm = sf2 * np.exp(-0.5 * s_mm)
        K_mm[np.diag_indices(M_eff)] += 1e-6 * max(sf2, 1.0)
        K_mn = sf2 * np.exp(-0.5 * s_mn)

        try:
            L_m = np.linalg.cholesky(0.5 * (K_mm + K_mm.T))
        except np.linalg.LinAlgError:
            return 1e12

        A = solve_triangular(L_m, K_mn, lower=True) / sn  # (M, N)
        B = np.eye(M_eff, dtype=np.float64) + A @ A.T
        try:
            L_B = np.linalg.cholesky(0.5 * (B + B.T))
        except np.linalg.LinAlgError:
            return 1e12

        Ay = A @ y_norm
        c = solve_triangular(L_B, Ay, lower=True)

        logdet_B = float(np.sum(np.log(np.diag(L_B))))
        quad = (y_norm2 - float(np.dot(c, c))) / sn2
        tr_diff = (N * sf2 - float(np.sum(A * A)) * sn2) / sn2
        elbo_val = (
            -0.5 * N * math.log(2.0 * math.pi)
            - 0.5 * N * math.log(sn2)
            - logdet_B
            - 0.5 * quad
            - 0.5 * tr_diff
        )
        return -elbo_val if math.isfinite(elbo_val) else 1e12

    bounds = [
        (math.log(1e-3), math.log(10.0)),
        *[(math.log(0.15), math.log(40.0)) for _ in range(INPUT_DIM)],
        (math.log(1e-4), math.log(2.0)),
    ]
    inits = [
        np.array([0.0, *([0.5] * INPUT_DIM), math.log(0.15)], dtype=np.float64),
        np.array([math.log(0.7), *([1.2] * INPUT_DIM), math.log(0.05)], dtype=np.float64),
        np.array([math.log(0.3), *([2.5] * INPUT_DIM), math.log(0.25)], dtype=np.float64),
    ]
    best_res = None
    for init in inits:
        res = minimize(neg_elbo, init, method="L-BFGS-B", bounds=bounds, options={"maxiter": maxiter})
        if best_res is None or res.fun < best_res.fun:
            best_res = res

    opt = best_res.x
    sf = math.exp(float(opt[0]))
    ls = np.exp(opt[1 : 1 + INPUT_DIM])
    sn = math.exp(float(opt[1 + INPUT_DIM]))
    sf2 = sf * sf

    K_mm = _ard_rbf_kernel(Z_m, Z_m, sf, ls)
    K_mm[np.diag_indices(M_eff)] += 1e-6 * max(sf2, 1.0)
    K_mn = _ard_rbf_kernel(Z_m, Z_std, sf, ls)
    L_m = _cholesky_with_jitter(K_mm, base_jitter=1e-6)
    A = solve_triangular(L_m, K_mn, lower=True) / sn
    B = np.eye(M_eff, dtype=np.float64) + A @ A.T
    L_B = _cholesky_with_jitter(B, base_jitter=1e-9)

    Ay = A @ y_norm
    c = solve_triangular(L_B, Ay, lower=True)
    rhs = solve_triangular(L_B.T, c, lower=False) / sn
    alpha_std = solve_triangular(L_m.T, rhs, lower=False)
    alpha_phys = alpha_std * y_scale

    eye_m = np.eye(M_eff, dtype=np.float64)
    L_m_inv = solve_triangular(L_m, eye_m, lower=True)
    L_B_inv = solve_triangular(L_B, eye_m, lower=True)

    return SparseChannelGP(
        M=M_eff,
        Z_m_std=Z_m,
        signal_std=sf,
        lengthscales=ls,
        noise_std=sn,
        y_std_scale=y_scale,
        alpha_mu_phys=alpha_phys,
        L_m_inv=L_m_inv,
        L_B_inv=L_B_inv,
        elbo=float(-best_res.fun),
    )


def compute_canonical_binary_sha256(doc: dict[str, Any]) -> str:
    """Cross-language IEEE-754 little-endian SHA-256 shared identically with C++."""
    h = hashlib.sha256()
    for key in ("schema", "snapshot_id", "nominal_model_hash", "codegen_layout_version"):
        h.update(str(doc[key]).encode("utf-8"))
        h.update(b"\x00")
    dt_val = float(doc["dt_s"])
    if dt_val == 0.0:
        dt_val = 0.0
    h.update(struct.pack("<IIId", int(doc["input_dim"]), int(doc["output_dim"]), int(doc["rk4_substeps"]), dt_val))

    def pack_arr(vals: Any) -> None:
        arr = np.asarray(vals, dtype=np.float64).ravel()
        arr = np.where(arr == 0.0, 0.0, arr)
        h.update(arr.astype("<f8", copy=False).tobytes())

    pack_arr(doc["x_mean"])
    pack_arr(doc["x_std"])
    env = doc["envelope"]
    pack_arr(env["feature_min"])
    pack_arr(env["feature_max"])
    pack_arr([env["ood_max_nearest_std_dist"]])
    pack_arr(doc["residual_clip_bounds"])
    for ch in doc["channels"]:
        h.update(struct.pack("<I", int(ch["M"])))
        pack_arr([ch["signal_std"], ch["noise_std"], ch["y_std_scale"]])
        pack_arr(ch["lengthscales"])
        pack_arr(ch["Z_m_std"])
        pack_arr(ch["alpha_mu_phys"])
        pack_arr(ch["L_m_inv"])
        pack_arr(ch["L_B_inv"])
    return h.hexdigest()


@dataclass
class MultiChannelSparseGP:
    """3-channel Sparse Variational GP model + standardization + OOD envelope."""

    snapshot_id: str
    nominal_model_hash: str
    x_mean: np.ndarray
    x_std: np.ndarray
    feature_min: np.ndarray
    feature_max: np.ndarray
    feature_q01: np.ndarray
    feature_q99: np.ndarray
    ood_max_nearest_std_dist: float
    residual_clip_bounds: np.ndarray
    channels: list[SparseChannelGP]
    offline_metrics: dict[str, Any]
    snapshot_sha256: str = ""

    def standardize(self, Z: np.ndarray) -> np.ndarray:
        Z = np.asarray(Z, dtype=np.float64)
        return (Z - self.x_mean[None, :]) / self.x_std[None, :]

    def predict(self, Z: np.ndarray, *, apply_clip: bool = True, ood_fallback_zero: bool = True) -> dict[str, np.ndarray]:
        Z = np.asarray(Z, dtype=np.float64)
        single = Z.ndim == 1
        if single:
            Z = Z[None, :]
        Q = Z.shape[0]
        Z_std = self.standardize(Z)

        mean = np.zeros((Q, OUTPUT_DIM), dtype=np.float64)
        std = np.zeros((Q, OUTPUT_DIM), dtype=np.float64)
        latent_std = np.zeros((Q, OUTPUT_DIM), dtype=np.float64)
        min_std_dist = np.full(Q, np.inf, dtype=np.float64)

        for c, ch in enumerate(self.channels):
            mu_c, var_tot_c, var_lat_c = ch.predict(Z_std)
            mean[:, c] = mu_c
            std[:, c] = np.sqrt(np.maximum(var_tot_c, 0.0))
            latent_std[:, c] = np.sqrt(np.maximum(var_lat_c, 0.0))
            d2 = np.sum((Z_std[:, None, :] - ch.Z_m_std[None, :, :]) ** 2, axis=2)
            d_c = np.sqrt(np.min(d2, axis=1))
            min_std_dist = np.minimum(min_std_dist, d_c)

        margin = 0.25 * (self.feature_max - self.feature_min)
        box_ood = np.any((Z < (self.feature_min - margin)) | (Z > (self.feature_max + margin)), axis=1)
        dist_ood = min_std_dist > self.ood_max_nearest_std_dist
        ood = (~np.all(np.isfinite(Z), axis=1)) | box_ood | dist_ood

        raw_mean = mean.copy()
        if apply_clip:
            lo = self.residual_clip_bounds[:, 0][None, :]
            hi = self.residual_clip_bounds[:, 1][None, :]
            clipped = np.any((mean < lo) | (mean > hi), axis=1)
            mean = np.clip(mean, lo, hi)
        else:
            clipped = np.zeros(Q, dtype=bool)

        if ood_fallback_zero:
            mean = np.where(ood[:, None], 0.0, mean)

        if single:
            return {
                "mean": mean[0],
                "raw_mean": raw_mean[0],
                "std": std[0],
                "latent_std": latent_std[0],
                "ood": bool(ood[0]),
                "clipped": bool(clipped[0]),
                "nearest_std_dist": float(min_std_dist[0]),
            }
        return {
            "mean": mean,
            "raw_mean": raw_mean,
            "std": std,
            "latent_std": latent_std,
            "ood": ood,
            "clipped": clipped,
            "nearest_std_dist": min_std_dist,
        }

    def to_snapshot_dict(self) -> dict[str, Any]:
        payload = {
            "schema": GP_SNAPSHOT_SCHEMA,
            "snapshot_id": self.snapshot_id,
            "nominal_model_hash": self.nominal_model_hash,
            "codegen_layout_version": CODEGEN_LAYOUT_VERSION,
            "dt_s": DT_S,
            "rk4_substeps": RK4_SUBSTEPS,
            "input_dim": INPUT_DIM,
            "output_dim": OUTPUT_DIM,
            "feature_names": list(FEATURE_NAMES),
            "feature_units": list(FEATURE_UNITS),
            "output_names": list(OUTPUT_NAMES),
            "output_units": list(OUTPUT_UNITS),
            "inducing_points_count": [ch.M for ch in self.channels],
            "x_mean": self.x_mean.tolist(),
            "x_std": self.x_std.tolist(),
            "envelope": {
                "feature_min": self.feature_min.tolist(),
                "feature_max": self.feature_max.tolist(),
                "feature_q01": self.feature_q01.tolist(),
                "feature_q99": self.feature_q99.tolist(),
                "ood_max_nearest_std_dist": float(self.ood_max_nearest_std_dist),
            },
            "residual_clip_bounds": self.residual_clip_bounds.tolist(),
            "channels": [
                {
                    "output_name": OUTPUT_NAMES[c],
                    "output_unit": OUTPUT_UNITS[c],
                    "M": int(ch.M),
                    "signal_std": float(ch.signal_std),
                    "lengthscales": ch.lengthscales.tolist(),
                    "noise_std": float(ch.noise_std),
                    "y_std_scale": float(ch.y_std_scale),
                    "elbo": float(ch.elbo),
                    "Z_m_std": ch.Z_m_std.tolist(),
                    "alpha_mu_phys": ch.alpha_mu_phys.tolist(),
                    "L_m_inv": ch.L_m_inv.tolist(),
                    "L_B_inv": ch.L_B_inv.tolist(),
                }
                for c, ch in enumerate(self.channels)
            ],
            "offline_metrics": self.offline_metrics,
        }
        digest = compute_canonical_binary_sha256(payload)
        payload["snapshot_sha256"] = digest
        self.snapshot_sha256 = digest
        return payload

    def save(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = self.to_snapshot_dict()
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return doc["snapshot_sha256"]

    @classmethod
    def from_snapshot_dict(cls, doc: dict[str, Any]) -> "MultiChannelSparseGP":
        if doc.get("schema") != GP_SNAPSHOT_SCHEMA:
            raise ValueError(f"unsupported gp snapshot schema: {doc.get('schema')!r}")
        declared = str(doc.get("snapshot_sha256") or "")
        computed = compute_canonical_binary_sha256(doc)
        if declared and declared != computed:
            raise ValueError(f"gp snapshot sha256 mismatch: declared={declared} computed={computed}")

        env = doc["envelope"]
        channels: list[SparseChannelGP] = []
        for ch in doc["channels"]:
            channels.append(
                SparseChannelGP(
                    M=int(ch["M"]),
                    Z_m_std=np.asarray(ch["Z_m_std"], dtype=np.float64),
                    signal_std=float(ch["signal_std"]),
                    lengthscales=np.asarray(ch["lengthscales"], dtype=np.float64),
                    noise_std=float(ch["noise_std"]),
                    y_std_scale=float(ch["y_std_scale"]),
                    alpha_mu_phys=np.asarray(ch["alpha_mu_phys"], dtype=np.float64),
                    L_m_inv=np.asarray(ch["L_m_inv"], dtype=np.float64),
                    L_B_inv=np.asarray(ch["L_B_inv"], dtype=np.float64),
                    elbo=float(ch.get("elbo", 0.0)),
                )
            )
        return cls(
            snapshot_id=str(doc["snapshot_id"]),
            nominal_model_hash=str(doc["nominal_model_hash"]),
            x_mean=np.asarray(doc["x_mean"], dtype=np.float64),
            x_std=np.asarray(doc["x_std"], dtype=np.float64),
            feature_min=np.asarray(env["feature_min"], dtype=np.float64),
            feature_max=np.asarray(env["feature_max"], dtype=np.float64),
            feature_q01=np.asarray(env["feature_q01"], dtype=np.float64),
            feature_q99=np.asarray(env["feature_q99"], dtype=np.float64),
            ood_max_nearest_std_dist=float(env["ood_max_nearest_std_dist"]),
            residual_clip_bounds=np.asarray(doc["residual_clip_bounds"], dtype=np.float64),
            channels=channels,
            offline_metrics=dict(doc.get("offline_metrics", {})),
            snapshot_sha256=computed,
        )

    @classmethod
    def load(cls, path: Path) -> "MultiChannelSparseGP":
        return cls.from_snapshot_dict(json.loads(path.read_text(encoding="utf-8")))


def train_sparse_gp_bundle(
    Z_train: np.ndarray,
    Y_train: np.ndarray,
    *,
    nominal_model_hash: str,
    snapshot_id: str,
    M: int = 64,
    seed: int = 0,
    ood_max_nearest_std_dist: float = 4.5,
    residual_clip_bounds: list[list[float]] | None = None,
    offline_metrics: dict[str, Any] | None = None,
) -> MultiChannelSparseGP:
    """Fit input scaler + 3 independent Titsias Sparse GPs strictly on train data."""
    Z_train = np.asarray(Z_train, dtype=np.float64)
    Y_train = np.asarray(Y_train, dtype=np.float64)
    if Z_train.ndim != 2 or Z_train.shape[1] != INPUT_DIM:
        raise ValueError(f"Expected Z shape (N, 5), got {Z_train.shape}")
    if Y_train.shape != (Z_train.shape[0], OUTPUT_DIM):
        raise ValueError(f"Expected Y shape ({Z_train.shape[0]}, 3), got {Y_train.shape}")

    x_mean = np.mean(Z_train, axis=0)
    x_std = np.maximum(np.std(Z_train, axis=0), 1e-3)
    Z_std = (Z_train - x_mean[None, :]) / x_std[None, :]

    channels = [
        fit_sparse_channel_gp(Z_std, Y_train[:, c], M=M, seed=seed + c)
        for c in range(OUTPUT_DIM)
    ]
    clips = np.asarray(
        residual_clip_bounds if residual_clip_bounds is not None else DEFAULT_CLIP_BOUNDS,
        dtype=np.float64,
    )
    return MultiChannelSparseGP(
        snapshot_id=snapshot_id,
        nominal_model_hash=nominal_model_hash,
        x_mean=x_mean,
        x_std=x_std,
        feature_min=np.min(Z_train, axis=0),
        feature_max=np.max(Z_train, axis=0),
        feature_q01=np.quantile(Z_train, 0.01, axis=0),
        feature_q99=np.quantile(Z_train, 0.99, axis=0),
        ood_max_nearest_std_dist=float(ood_max_nearest_std_dist),
        residual_clip_bounds=clips,
        channels=channels,
        offline_metrics=dict(offline_metrics or {}),
    )
