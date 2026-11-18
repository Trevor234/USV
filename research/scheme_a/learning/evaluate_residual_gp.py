#!/usr/bin/env python3
"""Evaluate trained GP residuals vs Zero, Constant, Simple Refit, and Exact GP baselines (WP4)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np

from dataset_builder import HydroParams, fossen_rk4_step
from gp_model import MultiChannelSparseGP, fit_exact_channel_gp, train_sparse_gp_bundle
from train_residual_gp import compute_regression_metrics


def fit_simple_linear_residual_baseline(Z_train: np.ndarray, Y_train: np.ndarray) -> np.ndarray:
    """Fit simple ridge linear map from [1, u, v, r, T_L, T_R, |u|u, |v|v, |r|r] -> Y (9x3)."""
    Phi = np.column_stack([
        np.ones(len(Z_train)),
        Z_train,
        Z_train[:, 0] * np.abs(Z_train[:, 0]),
        Z_train[:, 1] * np.abs(Z_train[:, 1]),
        Z_train[:, 2] * np.abs(Z_train[:, 2]),
    ])
    reg = 1e-4 * np.eye(Phi.shape[1])
    reg[0, 0] = 0.0
    W = np.linalg.solve(Phi.T @ Phi + reg, Phi.T @ Y_train)
    return W


def predict_simple_linear(Z: np.ndarray, W: np.ndarray) -> np.ndarray:
    Phi = np.column_stack([
        np.ones(len(Z)),
        Z,
        Z[:, 0] * np.abs(Z[:, 0]),
        Z[:, 1] * np.abs(Z[:, 1]),
        Z[:, 2] * np.abs(Z[:, 2]),
    ])
    return Phi @ W


def compute_multistep_rollout_error(
    provenance_rows: list[dict[str, Any]],
    *,
    nominal_hydro: HydroParams,
    model_fn,
    horizon_steps: int = 10,
) -> dict[str, Any]:
    """Compare closed/open-loop 2.0s (10-step) RK4 rollout RMSE with and without GP mean residual."""
    by_ep: dict[str, list[dict[str, Any]]] = {}
    for row in provenance_rows:
        if not row.get("included"):
            continue
        by_ep.setdefault(str(row["episode_id"]), []).append(row)

    pos_errs: list[float] = []
    vel_errs: list[float] = []
    for ep_rows in by_ep.values():
        ep_rows.sort(key=lambda r: int(r["start_sim_ns"]))
        i = 0
        while i + horizon_steps < len(ep_rows):
            # Ensure contiguous 0.2s segment.
            contiguous = all(
                int(ep_rows[i + k + 1]["start_sim_ns"]) == int(ep_rows[i + k]["end_sim_ns"])
                for k in range(horizon_steps)
            )
            if not contiguous:
                i += 1
                continue
            x = np.asarray(ep_rows[i]["x_start"], dtype=np.float64).copy()
            for k in range(horizon_steps):
                q = np.asarray(ep_rows[i + k]["q_exec"], dtype=np.float64)
                z = np.array([x[3], x[4], x[5], q[0], q[1]], dtype=np.float64)
                res_corr = np.asarray(model_fn(z), dtype=np.float64)
                x = fossen_rk4_step(x, q, nominal_hydro)
                x[3:6] += res_corr
            x_true_end = np.asarray(ep_rows[i + horizon_steps - 1]["x_end"], dtype=np.float64)
            pos_errs.append(float(np.hypot(x[0] - x_true_end[0], x[1] - x_true_end[1])))
            vel_errs.append(float(np.linalg.norm(x[3:6] - x_true_end[3:6])))
            i += horizon_steps

    return {
        "segments": len(pos_errs),
        "horizon_s": float(horizon_steps * 0.2),
        "pos_rmse_m": float(np.sqrt(np.mean(np.square(pos_errs)))) if pos_errs else None,
        "vel_rmse": float(np.sqrt(np.mean(np.square(vel_errs)))) if vel_errs else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--nominal-dataset", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    ds_dir = Path(args.dataset).resolve()
    models_dir = Path(args.models_dir).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = json.loads((ds_dir / "dataset_contract.json").read_text(encoding="utf-8"))
    nominal_hydro = HydroParams.from_dict(contract["controller_nominal_hydro"])
    manifest = json.loads(Path(args.split_manifest).read_text(encoding="utf-8"))
    ep_meta = {str(e["run_id"]): e for e in manifest.get("episodes", []) if e.get("run_id")}

    npz = np.load(ds_dir / "dataset.npz", allow_pickle=False)
    Z = npz["Z"]
    Y = npz["Y"]
    splits = npz["splits"]
    ep_ids = npz["episode_ids"]

    prov_rows = [
        json.loads(line)
        for line in (ds_dir / "sample_provenance.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    train_mask = splits == "train"
    cal_mask = splits == "calibration"
    test_mask = splits == "final_test"

    Z_train, Y_train = Z[train_mask], Y[train_mask]
    Z_cal, Y_cal = Z[cal_mask], Y[cal_mask]
    Z_test, Y_test = Z[test_mask], Y[test_mask]

    gp_m32 = MultiChannelSparseGP.load(models_dir / "pooled_gp_sparse_m32.json")
    gp_m64 = MultiChannelSparseGP.load(models_dir / "pooled_gp_sparse_m64.json")
    gp_sel = MultiChannelSparseGP.load(models_dir / "gp_snapshot.json")

    # Fit Exact GP benchmark on normalized train features.
    x_mean = gp_sel.x_mean
    x_std = gp_sel.x_std
    exact_chs = [
        fit_exact_channel_gp((Z_train - x_mean) / x_std, Y_train[:, c], seed=42 + c)
        for c in range(3)
    ]

    def eval_all(Z_eval: np.ndarray, Y_eval: np.ndarray) -> dict[str, Any]:
        y_std_tr = np.maximum(np.std(Y_train, axis=0), 1e-6)
        zero_mu = np.zeros_like(Y_eval)
        const_mu = np.tile(np.mean(Y_train, axis=0), (len(Y_eval), 1))
        lin_W = fit_simple_linear_residual_baseline(Z_train, Y_train)
        lin_mu = predict_simple_linear(Z_eval, lin_W)
        lin_std = np.tile(np.maximum(np.std(Y_train - predict_simple_linear(Z_train, lin_W), axis=0), 1e-6), (len(Y_eval), 1))

        ex_mu = np.zeros_like(Y_eval)
        ex_std = np.zeros_like(Y_eval)
        Z_eval_s = (Z_eval - x_mean) / x_std
        for c in range(3):
            m, v = exact_chs[c].predict(Z_eval_s)
            ex_mu[:, c] = m
            ex_std[:, c] = np.sqrt(np.maximum(v, 1e-12))

        p32 = gp_m32.predict(Z_eval, apply_clip=False, ood_fallback_zero=False)
        p64 = gp_m64.predict(Z_eval, apply_clip=False, ood_fallback_zero=False)

        return {
            "zero_residual": compute_regression_metrics(Y_eval, zero_mu, np.tile(y_std_tr, (len(Y_eval), 1))),
            "constant_residual": compute_regression_metrics(Y_eval, const_mu, np.tile(y_std_tr, (len(Y_eval), 1))),
            "simple_param_refit": compute_regression_metrics(Y_eval, lin_mu, lin_std),
            "exact_gp": compute_regression_metrics(Y_eval, ex_mu, ex_std),
            "sparse_gp_m32": compute_regression_metrics(Y_eval, p32["mean"], p32["std"]),
            "sparse_gp_m64": compute_regression_metrics(Y_eval, p64["mean"], p64["std"]),
        }

    results: dict[str, Any] = {
        "calibration": eval_all(Z_cal, Y_cal),
        "final_test_all": eval_all(Z_test, Y_test),
    }

    # Held-out combination slice vs held-out unseen maneuvers on trained profiles.
    heldout_comb_mask = np.asarray([
        (ep_ids[i] in ep_meta) and (ep_meta[str(ep_ids[i])]["profile"] == "heldout_combination")
        for i in range(len(ep_ids))
    ], dtype=bool) & test_mask
    if np.any(heldout_comb_mask):
        results["final_test_heldout_combination"] = eval_all(Z[heldout_comb_mask], Y[heldout_comb_mask])

    # Per-single-profile unseen maneuver evaluation (surge_damping_plus_15pct / mass_plus_10pct / yaw_damping_plus_15pct).
    per_profile_eval: dict[str, Any] = {}
    for prof in ("mass_plus_10pct", "surge_damping_plus_15pct", "yaw_damping_plus_15pct"):
        p_ids = {eid for eid, m in ep_meta.items() if m["profile"] == prof}
        p_mask = np.asarray([str(eid) in p_ids for eid in ep_ids], dtype=bool)
        tr_p = p_mask & train_mask
        te_p = p_mask & (cal_mask | test_mask)
        if np.any(tr_p) and np.any(te_p):
            single_gp = train_sparse_gp_bundle(
                Z[tr_p], Y[tr_p],
                nominal_model_hash=contract["controller_nominal_hydro_sha256"],
                snapshot_id=f"{prof}_m64",
                M=64,
                seed=7,
            )
            single_gp.save(models_dir / f"{prof}_sparse_m64.json")
            pred_te = single_gp.predict(Z[te_p], apply_clip=False, ood_fallback_zero=False)
            zero_te = compute_regression_metrics(Y[te_p], np.zeros_like(Y[te_p]), np.tile(np.maximum(np.std(Y[tr_p], axis=0), 1e-6), (int(np.sum(te_p)), 1)))
            gp_te = compute_regression_metrics(Y[te_p], pred_te["mean"], pred_te["std"])
            per_profile_eval[prof] = {
                "n_train": int(np.sum(tr_p)),
                "n_eval_unseen_maneuvers": int(np.sum(te_p)),
                "zero_residual": zero_te,
                "sparse_gp_m64": gp_te,
            }
    results["per_profile_heldout_maneuvers"] = per_profile_eval

    # 2.0s open-loop rollout comparison on final_test
    test_prov = [r for r in prov_rows if r.get("split") == "final_test"]
    results["rollout_final_test"] = {
        "zero_residual": compute_multistep_rollout_error(
            test_prov, nominal_hydro=nominal_hydro, model_fn=lambda z: np.zeros(3)
        ),
        "sparse_gp_selected": compute_multistep_rollout_error(
            test_prov, nominal_hydro=nominal_hydro, model_fn=lambda z: gp_sel.predict(z)["mean"]
        ),
    }

    # Nominal zero-residual gate if provided
    if args.nominal_dataset:
        nom_dir = Path(args.nominal_dataset)
        nom_npz = np.load(nom_dir / "dataset.npz", allow_pickle=False)
        nom_Z, nom_Y = nom_npz["Z"], nom_npz["Y"]
        if len(nom_Z) >= 10:
            nom_gp = train_sparse_gp_bundle(
                nom_Z[::2], nom_Y[::2],
                nominal_model_hash=contract["controller_nominal_hydro_sha256"],
                snapshot_id="nominal_zero_gate",
                M=32,
                seed=1,
            )
            nom_pred = nom_gp.predict(nom_Z[1::2], apply_clip=False, ood_fallback_zero=False)
            results["nominal_zero_gate"] = {
                "data_max_abs": float(np.max(np.abs(nom_Y))),
                "gp_pred_max_abs": float(np.max(np.abs(nom_pred["mean"]))),
            }

    (out_dir / "gp_holdout_metrics.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Generate Python-vs-C++ gp_numeric_parity.json artifact against real trained snapshot.
    cli_path = Path(
        "/home/trevor/usv_scheme_a_wt/install/scheme_a/usv_research_safety_cpp/"
        "lib/usv_research_safety_cpp/p1_gp_eval_cli"
    )
    snap_path = models_dir / "gp_snapshot.json"
    if cli_path.is_file() and snap_path.is_file() and len(Z_test) > 0:
        sample_idx = np.linspace(0, len(Z_test) - 1, num=min(32, len(Z_test)), dtype=int)
        q_parity = np.vstack([Z_test[sample_idx], [[5.0, 2.0, 2.0, 40.0, -40.0]]])
        q_json = out_dir / "_parity_queries.json"
        q_json.write_text(json.dumps({"queries": q_parity.tolist()}), encoding="utf-8")
        proc = subprocess.run([str(cli_path), str(snap_path), str(q_json)], capture_output=True, text=True, check=True)
        q_json.unlink(missing_ok=True)
        cout = json.loads(proc.stdout)
        py_out = gp_sel.predict(q_parity)
        c_mu = np.asarray([r["mean"] for r in cout["predictions"]], dtype=np.float64)
        c_std = np.asarray([r["std"] for r in cout["predictions"]], dtype=np.float64)
        parity_doc = {
            "schema": "scheme-a-gp-numeric-parity-v1",
            "snapshot_path": str(snap_path),
            "python_snapshot_sha256": gp_sel.snapshot_sha256,
            "cpp_snapshot_sha256": cout["snapshot_sha256"],
            "sha256_match": gp_sel.snapshot_sha256 == cout["snapshot_sha256"],
            "query_count": int(len(q_parity)),
            "max_abs_mean_diff": float(np.max(np.abs(c_mu - py_out["mean"]))),
            "max_abs_std_diff": float(np.max(np.abs(c_std - py_out["std"]))),
            "ood_flags_exact_match": [r["ood"] for r in cout["predictions"]] == py_out["ood"].tolist(),
        }
        (out_dir / "gp_numeric_parity.json").write_text(
            json.dumps(parity_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    lines = [
        "# GP Residual Holdout & Calibration Evaluation Report (WP4)",
        "",
        "## Held-Out Final Test (`final_test_all`, 12 episodes)",
        "| Model | RMSE Mean | NLPD Mean | 95% Coverage |",
        "| :--- | ---: | ---: | ---: |",
    ]
    for name, m in results["final_test_all"].items():
        lines.append(f"| `{name}` | {m['rmse_mean']:.6f} | {m['nlpd_mean']:.4f} | {m['coverage95_mean']:.3f} |")

    if "final_test_heldout_combination" in results:
        lines.extend([
            "",
            "## Held-Out Combined Plant (`heldout_combination`: +5% mass, +10% Xu, +10% Nr)",
            "| Model | RMSE Mean | NLPD Mean | 95% Coverage |",
            "| :--- | ---: | ---: | ---: |",
        ])
        for name, m in results["final_test_heldout_combination"].items():
            lines.append(f"| `{name}` | {m['rmse_mean']:.6f} | {m['nlpd_mean']:.4f} | {m['coverage95_mean']:.3f} |")

    if per_profile_eval:
        lines.extend([
            "",
            "## Per-Plant Unseen Maneuvers (`right_turn`, `rate_limited_thrust_step`)",
            "| Plant Profile | Zero RMSE | Sparse GP (M=64) RMSE | Zero NLPD | GP NLPD | 95% Cov |",
            "| :--- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for prof, pdict in per_profile_eval.items():
            z0 = pdict["zero_residual"]
            g1 = pdict["sparse_gp_m64"]
            lines.append(
                f"| `{prof}` | {z0['rmse_mean']:.6f} | {g1['rmse_mean']:.6f} | "
                f"{z0['nlpd_mean']:.4f} | {g1['nlpd_mean']:.4f} | {g1['coverage95_mean']:.3f} |"
            )

    lines.extend([
        "",
        "## 2.0 s Multi-Step Rollout on `final_test`",
        f"- Pure Nominal RMSE (pos / vel): `{results['rollout_final_test']['zero_residual']['pos_rmse_m']:.5f} m` / `{results['rollout_final_test']['zero_residual']['vel_rmse']:.5f}`",
        f"- GP-Corrected RMSE (pos / vel): `{results['rollout_final_test']['sparse_gp_selected']['pos_rmse_m']:.5f} m` / `{results['rollout_final_test']['sparse_gp_selected']['vel_rmse']:.5f}`",
    ])
    if "nominal_zero_gate" in results:
        lines.extend([
            "",
            "## Nominal Zero-Residual Gate",
            f"- Nominal data max_abs: `{results['nominal_zero_gate']['data_max_abs']:.3e}`",
            f"- Nominal GP pred max_abs: `{results['nominal_zero_gate']['gp_pred_max_abs']:.3e}`",
        ])

    (out_dir / "gp_holdout_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out_dir), "report": str(out_dir / "gp_holdout_report.md")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
