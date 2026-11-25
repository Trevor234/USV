#!/usr/bin/env python3
"""Stage-2 surge identification v3: steady-curve + phase-averaged anchor.

Step 1 (robust, no accel noise): quasi-steady balance K*S = x*u + z*u^2 gives
        S = a*u + b*u^2 with a=x/K, b=z/K  -> linear LS through origin.
Step 2 (anchor): per accel/decel phase, mean-acceleration balance
        K = m*u_dot_avg / (S_avg - a*u_avg - b*u_avg^2), median over phases.
Outputs Xu=-a*K, Xuu=-b*K, T_max=K*S_max, validation, plots.
"""
import glob
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_surge import build_grid  # grid builder (POS-based u, ATT heading)

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

MASS = 14.2
PHASE_MIN_S = 4.0
PHASE_MIN_LEN = int(PHASE_MIN_S / 0.1)  # 10 Hz decimated grid


def phases(g, sign, min_len=PHASE_MIN_LEN):
    """Consecutive runs where smoothed accel has consistent `sign` (>0 or <0)."""
    a = g["accx"]
    if a is None:
        return []
    m = np.isfinite(a) & (sign * a > 0.25) & (np.abs(g["r"]) < 0.5) \
        & (g["v_mag"] < 4.5) & (g["v_mag"] > 0.2) & np.isfinite(g["S"])
    idx = np.flatnonzero(m)
    if len(idx) == 0:
        return []
    runs = np.split(idx, np.where(np.diff(idx) > 10)[0] + 1)
    return [r for r in runs if len(r) >= min_len]


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build_grid(np.load(f, allow_pickle=True))
        if g is not None:
            sl = slice(None, None, 2)  # 10 Hz
            logs[name] = {k: v[sl] for k, v in g.items()}

    # ---- step 1: quasi-steady (S, u) cloud ----
    S_all, u_all, tag = [], [], []
    for name, g in logs.items():
        a = g["accx"]
        if a is None:
            continue
        m = (np.isfinite(a) & np.isfinite(g["S"]) & np.isfinite(g["u"])
             & (np.abs(a) < 0.08) & (np.abs(g["r"]) < 0.5)
             & (g["u"] > 0.3) & (g["u"] < 4.0)
             & (g["S"] > 1e6) & (g["S"] < 8e7) & (g["v_mag"] < 4.5))
        S_all.append(g["S"][m])
        u_all.append(g["u"][m])
        tag += [name] * int(m.sum())
    S_all = np.concatenate(S_all)
    u_all = np.concatenate(u_all)
    A = np.column_stack([u_all, u_all ** 2])
    coef, *_ = np.linalg.lstsq(A, S_all, rcond=None)
    a_, b_ = float(coef[0]), float(coef[1])
    pred = A @ coef
    r2 = 1 - np.sum((S_all - pred) ** 2) / np.sum((S_all - np.mean(S_all)) ** 2)
    print(f"step1 steady curve: S = {a_:.1f}*u + {b_:.1f}*u^2   (R2={r2:.4f}, n={len(S_all)})")
    if b_ < 0:
        A0 = u_all.reshape(-1, 1)
        a_, *_ = np.linalg.lstsq(A0, S_all, rcond=None)
        a_, b_ = float(a_[0]), 0.0
        print(f"  b clipped to 0; refit a={a_:.1f}")

    # ---- step 2: phase-averaged K anchor ----
    Ks = []
    phase_info = []
    for name, g in logs.items():
        for sign in (+1, -1):
            for run in phases(g, sign):
                i0, i1 = run[0], run[-1]
                T = (g["t"][i1] - g["t"][i0]) / 1e6
                if T < PHASE_MIN_S:
                    continue
                u_dot_avg = (g["u"][i1] - g["u"][i0]) / T
                S_avg = float(np.mean(g["S"][run]))
                u_avg = float(np.mean(g["u"][run]))
                u2_avg = float(np.mean(g["u"][run] ** 2))
                denom = S_avg - a_ * u_avg - b_ * u2_avg
                if denom <= 0.05 * S_avg:
                    continue
                K_i = MASS * u_dot_avg / denom
                if 1e-8 < K_i < 1e-5:
                    Ks.append(K_i)
                    phase_info.append({"log": name, "sign": int(sign), "T_s": float(T),
                                       "u_dot_avg": float(u_dot_avg), "K": float(K_i)})
    K = float(np.median(Ks)) if Ks else None
    K_lo = float(np.percentile(Ks, 25)) if Ks else None
    K_hi = float(np.percentile(Ks, 75)) if Ks else None
    print(f"step2 anchor: {len(Ks)} phases -> K median={K:.3e}  IQR [{K_lo:.3e},{K_hi:.3e}]")
    for p in phase_info[:10]:
        print(f"  {p['log'][-9:]} sign={p['sign']:+d} T={p['T_s']:.1f}s "
              f"udot={p['u_dot_avg']:+.2f} K={p['K']:.3e}")

    if K is None:
        print("no valid anchor phases; abort")
        return

    Xu = -a_ * K
    Xuu = -b_ * K
    n_max = max(np.nanmax(g["S"]) ** 0.5 for g in logs.values())
    T_max = K * n_max ** 2
    print(f"\nFINAL: K={K:.4e} N/RPM^2  Xu={Xu:.3f} (prior -2.2721)  "
          f"Xuu={Xuu:.3f} (prior -11.5718)")
    print(f"S_max -> sqrt={n_max:.0f} RPM-sum, T_max={T_max:.1f} N (prior assumed 25 N)")

    # ---- steady validation: predicted u_eq from S ----
    errs = []
    S_val, u_val = [], []
    for name, g in logs.items():
        a = g["accx"]
        if a is None:
            continue
        m = (np.isfinite(a) & np.isfinite(g["S"]) & np.isfinite(g["u"])
             & (np.abs(a) < 0.08) & (np.abs(g["r"]) < 0.5)
             & (g["u"] > 0.3) & (g["u"] < 4.0) & (g["S"] > 1e6) & (g["v_mag"] < 4.5))
        S_v, u_v = g["S"][m], g["u"][m]
        if b_ > 0:
            u_eq = (-a_ + np.sqrt(a_ ** 2 + 4 * b_ * S_v)) / (2 * b_)
        else:
            u_eq = S_v / a_
        ok = np.isfinite(u_eq)
        errs.append(u_v[ok] - u_eq[ok])
        S_val.append(S_v[ok])
        u_val.append(u_v[ok])
    errs = np.concatenate(errs)
    S_val = np.concatenate(S_val)
    u_val = np.concatenate(u_val)
    print(f"steady validation (n={len(errs)}): mean={np.mean(errs):+.3f} "
          f"RMSE={np.sqrt(np.mean(errs**2)):.3f} median|e|={np.median(np.abs(errs)):.3f} m/s")

    # ---- plots ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=130)
    ax.scatter(np.sqrt(S_val) / 60, u_val, s=2, alpha=0.15, label="quasi-steady points")
    nn = np.linspace(800, n_max / np.sqrt(2) / 60, 120)
    S_nn = (nn * 60) ** 2
    if b_ > 0:
        u_pred = (-a_ + np.sqrt(a_ ** 2 + 4 * b_ * S_nn)) / (2 * b_)
    else:
        u_pred = S_nn / a_
    ax.plot(nn, u_pred, "r-", lw=2,
            label=f"identified balance (a={a_:.0f}, b={b_:.1f})")
    ax.set_xlabel("mean prop speed sqrt(nL^2+nR^2) (kRPM)")
    ax.set_ylabel("steady surge speed u (m/s)")
    ax.set_title(f"Steady thrust balance, R2={r2:.4f}")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "surge_steady_curve.png"))
    plt.close(fig)

    out = {
        "mass_anchor_kg": MASS,
        "steady_curve": {"a_mps_per_rpm2": a_, "b_per_rpm2": b_, "r2": r2, "n": int(len(S_all))},
        "K_N_per_rpm2": K,
        "K_iqr": [K_lo, K_hi],
        "n_phases": len(Ks),
        "Xu_N_per_mps": Xu,
        "Xuu_N_per_mps2": Xuu,
        "n_max_sqrt_sum_rpm": float(n_max),
        "T_max_N": float(T_max),
        "steady_validation": {"n": int(len(errs)), "mean_err": float(np.mean(errs)),
                              "rmse": float(np.sqrt(np.mean(errs ** 2))),
                              "median_abs_err": float(np.median(np.abs(errs)))},
        "prior_0723": {"Xu": -2.272063, "Xuu": -11.571784, "assumed_K_T_N": 25.0},
    }
    with open(os.path.join(OUT_DIR, "surge_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved surge_params.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
