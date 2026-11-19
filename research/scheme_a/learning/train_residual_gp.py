#!/usr/bin/env python3
"""Train Exact GP and Titsias Sparse GPs (M=32, M=64) strictly on training split."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from gp_model import (
    INPUT_DIM,
    OUTPUT_DIM,
    ExactChannelGP,
    MultiChannelSparseGP,
    fit_exact_channel_gp,
    train_sparse_gp_bundle,
)


def compute_regression_metrics(y_true: np.ndarray, mu: np.ndarray, std: np.ndarray) -> dict[str, Any]:
    err = y_true - mu
    rmse = np.sqrt(np.mean(err ** 2, axis=0))
    mae = np.mean(np.abs(err), axis=0)
    var = np.maximum(std ** 2, 1e-12)
    nlpd = 0.5 * np.mean(np.log(2.0 * np.pi * var) + (err ** 2) / var, axis=0)
    cov95 = np.mean(np.abs(err) <= 1.959963984540054 * std, axis=0)
    return {
        "rmse_per_channel": [float(v) for v in rmse],
        "rmse_mean": float(np.sqrt(np.mean(err ** 2))),
        "mae_per_channel": [float(v) for v in mae],
        "nlpd_per_channel": [float(v) for v in nlpd],
        "nlpd_mean": float(np.mean(nlpd)),
        "coverage95_per_channel": [float(v) for v in cov95],
        "coverage95_mean": float(np.mean(cov95)),
    }


def augment_z2_symmetry(Z: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mirror port-starboard state/control/residual pairs via Fossen Z2 reflection symmetry."""
    Z_flip = np.asarray(Z, dtype=np.float64).copy()
    Z_flip[:, 1] = -Z[:, 1]
    Z_flip[:, 2] = -Z[:, 2]
    Z_flip[:, 3] = Z[:, 4]
    Z_flip[:, 4] = Z[:, 3]
    Y_flip = np.asarray(Y, dtype=np.float64).copy()
    Y_flip[:, 1] = -Y[:, 1]
    Y_flip[:, 2] = -Y[:, 2]
    return np.vstack([Z, Z_flip]), np.vstack([Y, Y_flip])


def _train_and_compare_one_dataset(
    Z_train: np.ndarray,
    Y_train: np.ndarray,
    Z_cal: np.ndarray,
    Y_cal: np.ndarray,
    *,
    nominal_hash: str,
    prefix: str,
    out_dir: Path,
    seed: int = 0,
    force_m: int = 0,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    x_mean = np.mean(Z_train, axis=0)
    x_std = np.maximum(np.std(Z_train, axis=0), 1e-3)
    Z_train_std = (Z_train - x_mean[None, :]) / x_std[None, :]
    Z_cal_std = (Z_cal - x_mean[None, :]) / x_std[None, :] if len(Z_cal) else np.zeros((0, INPUT_DIM))

    exact_channels: list[ExactChannelGP] = [
        fit_exact_channel_gp(Z_train_std, Y_train[:, c], seed=seed + c)
        for c in range(OUTPUT_DIM)
    ]

    exact_cal_metrics = None
    if len(Z_cal):
        ex_mu = np.zeros_like(Y_cal)
        ex_std = np.zeros_like(Y_cal)
        for c in range(OUTPUT_DIM):
            m, v = exact_channels[c].predict(Z_cal_std)
            ex_mu[:, c] = m
            ex_std[:, c] = np.sqrt(np.maximum(v, 1e-12))
        exact_cal_metrics = compute_regression_metrics(Y_cal, ex_mu, ex_std)

    sparse_models: dict[int, MultiChannelSparseGP] = {}
    sparse_cal_metrics: dict[str, Any] = {}
    for M in (32, 64):
        bundle = train_sparse_gp_bundle(
            Z_train,
            Y_train,
            nominal_model_hash=nominal_hash,
            snapshot_id=f"{prefix}_sparse_m{M}",
            M=M,
            seed=seed,
        )
        if len(Z_cal):
            pred = bundle.predict(Z_cal, apply_clip=False, ood_fallback_zero=False)
            m_dict = compute_regression_metrics(Y_cal, pred["mean"], pred["std"])
            bundle.offline_metrics = {"calibration": m_dict, "exact_calibration": exact_cal_metrics}
            sparse_cal_metrics[f"M{M}"] = m_dict
        bundle.save(out_dir / f"{prefix}_sparse_m{M}.json")
        sparse_models[M] = bundle

    # Select M=64 if strictly better or close on NLPD/RMSE, else M=32 (unless forced).
    if force_m in sparse_models:
        selected_M = force_m
    else:
        selected_M = 64
        if len(Z_cal):
            if sparse_cal_metrics["M32"]["nlpd_mean"] + 1e-3 < sparse_cal_metrics["M64"]["nlpd_mean"]:
                selected_M = 32
    selected = sparse_models[selected_M]
    selected.snapshot_id = f"{prefix}_selected_m{selected_M}"
    sha = selected.save(out_dir / "gp_snapshot.json")

    return {
        "prefix": prefix,
        "selected_M": selected_M,
        "snapshot_sha256": sha,
        "snapshot_path": str(out_dir / "gp_snapshot.json"),
        "n_train": int(len(Z_train)),
        "n_calibration": int(len(Z_cal)),
        "exact_calibration": exact_cal_metrics,
        "sparse_calibration": sparse_cal_metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Directory containing dataset.npz and dataset_contract.json")
    parser.add_argument("--out", required=True, help="Output directory for trained GP models & gp_snapshot.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--symmetrize-z2", action="store_true", help="Augment training split with Fossen Z2 port-starboard reflection")
    parser.add_argument("--force-m", type=int, default=0, help="Force inducing count (e.g. 64) instead of NLPD auto-select")
    parser.add_argument("--profile", default="", help="Optional single-profile filter via split_manifest")
    parser.add_argument("--split-manifest", default="", help="Path to split_manifest.json when --profile is set")
    args = parser.parse_args(argv)

    ds_dir = Path(args.dataset).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = json.loads((ds_dir / "dataset_contract.json").read_text(encoding="utf-8"))
    nominal_hash = str(contract["controller_nominal_hydro_sha256"])
    npz = np.load(ds_dir / "dataset.npz", allow_pickle=False)
    Z = npz["Z"]
    Y = npz["Y"]
    splits = npz["splits"]

    train_mask = splits == "train"
    cal_mask = splits == "calibration"
    if args.profile:
        if not args.split_manifest:
            raise SystemExit("--split-manifest is required when --profile is set")
        manifest = json.loads(Path(args.split_manifest).read_text(encoding="utf-8"))
        ep_to_prof = {e["run_id"]: e.get("profile", "") for e in manifest["episodes"]}
        ep_ids = npz["episode_ids"]
        prof_mask = np.array([ep_to_prof.get(str(eid), "") == args.profile for eid in ep_ids], dtype=bool)
        train_mask = train_mask & prof_mask
        cal_mask = cal_mask & prof_mask
    if not np.any(train_mask):
        raise SystemExit("No training samples with split=='train' found in dataset.npz")

    Z_train, Y_train = Z[train_mask], Y[train_mask]
    if args.symmetrize_z2:
        Z_train, Y_train = augment_z2_symmetry(Z_train, Y_train)
    Z_cal, Y_cal = Z[cal_mask], Y[cal_mask]
    prefix = args.profile if args.profile else "pooled_gp"

    summary = _train_and_compare_one_dataset(
        Z_train,
        Y_train,
        Z_cal,
        Y_cal,
        nominal_hash=nominal_hash,
        prefix=prefix,
        out_dir=out_dir,
        seed=args.seed,
        force_m=int(args.force_m),
    )
    (out_dir / "train_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
