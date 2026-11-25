#!/usr/bin/env python3
"""Stage-2 v4: coast-down drag identification + cruise-balance K anchor.

Coast-down: both throttles near neutral (thrust~0) -> m*|u_dot| = |Xu|*u + |Xuu|*u^2.
Phase-averaged regression on coast segments gives |Xu|, |Xuu| (absolute, m anchored).
Then K from cruise balance points: K = (|Xu|*u + |Xuu|*u^2)/S  (median).
"""
import glob
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_surge import build_grid

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

MASS = 14.2
COAST_MIN_S = 4.0
PHASE_MIN_S = 4.0


def runs_of(mask, min_len):
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    return [r for r in np.split(idx, np.where(np.diff(idx) > 10)[0] + 1)
            if len(r) >= min_len]


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build_grid(np.load(f, allow_pickle=True))
        if g is not None:
            sl = slice(None, None, 2)  # 10 Hz
            logs[name] = {k: v[sl] for k, v in g.items()}

    # need RCOU on the 10Hz grid for neutrality test
    coast_phases = []
    cruise_pts = []
    for name, g0 in logs.items():
        g = g0
        t = g["t"]
        z = np.load(os.path.join(PARSED_DIR, name + ".npz"), allow_pickle=True)
        d = {k: z[k] for k in z.files}
        c1 = np.interp(t, d["RCOU.TimeUS"], d["RCOU.C1"], left=np.nan, right=np.nan)
        c3 = np.interp(t, d["RCOU.TimeUS"], d["RCOU.C3"], left=np.nan, right=np.nan)
        neutral = (np.abs(c1 - 1500) < 70) & (np.abs(c3 - 1500) < 70)
        moving = (g["v_mag"] > 0.8) & (g["v_mag"] < 4.5)
        acc_finite = np.isfinite(g["accx"]) if g["accx"] is not None else np.zeros(len(t), bool)
        coast = neutral & moving & (np.abs(g["r"]) < 0.4) & acc_finite
        runs = runs_of(coast, int(COAST_MIN_S / 0.1))
        print(f"{name}: coast runs={len(runs)}", end=" ")
        for r in runs:
            T = (t[r[-1]] - t[r[0]]) / 1e6
            if T < COAST_MIN_S:
                continue
            u0, u1 = g["u"][r[0]], g["u"][r[-1]]
            u_dot_avg = (u1 - u0) / T
            if u_dot_avg >= -0.02 or u0 < 0.8:
                continue
            u_avg = float(np.mean(g["u"][r]))
            u2_avg = float(np.mean(g["u"][r] ** 2))
            dec = float(-u_dot_avg)
            coast_phases.append({"log": name[-9:], "T": float(T), "u0": float(u0),
                                 "u1": float(u1), "u_avg": u_avg, "u2_avg": u2_avg,
                                 "dec": dec})
        print(f"phases={len(coast_phases)}")

        # cruise balance points (forward, moderate pwm, quasi-steady accel)
        m = (acc_finite & (np.abs(g["accx"]) < 0.08) & (np.abs(g["r"]) < 0.4)
             & (g["u"] > 0.6) & (g["u"] < 3.6) & (g["S"] > 2e6) & (g["S"] < 8e7)
             & (g["v_mag"] < 4.5) & (np.abs(c1 - 1500) > 60) & (c1 < 1965) & (c3 < 1965))
        for ui, Si in zip(g["u"][m], g["S"][m]):
            cruise_pts.append((float(ui), float(Si), name[-9:]))
    print(f"total: {len(coast_phases)} coast phases, {len(cruise_pts)} cruise points")

    # ---- coast regression: dec = (|Xu|*u + |Xuu|*u^2)/m ----
    if len(coast_phases) < 5:
        print("WARN: too few coast phases")
    A = np.array([[p["u_avg"], p["u2_avg"]] for p in coast_phases])
    y = np.array([p["dec"] for p in coast_phases]) * MASS
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    Xu_abs, Xuu_abs = float(max(coef[0], 0.0)), float(max(coef[1], 0.0))
    pred = A @ [Xu_abs, Xuu_abs]
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - np.mean(y)) ** 2)
    Xu, Xuu = -Xu_abs, -Xuu_abs
    print(f"coast fit: |Xu|={Xu_abs:.3f} |Xuu|={Xuu_abs:.3f} (R2={r2:.3f}, "
          f"n={len(coast_phases)}) -> Xu={Xu:.3f} Xuu={Xuu:.3f} (priors -2.272/-11.572)")

    # ---- K anchor from cruise balance ----
    Ks = []
    for u, S, src in cruise_pts:
        drag = Xu_abs * u + Xuu_abs * u ** 2
        if drag > 0.5:
            Ks.append(drag / S)
    K = float(np.median(Ks))
    K_lo = float(np.percentile(Ks, 25))
    K_hi = float(np.percentile(Ks, 75))
    print(f"K anchor: median={K:.4e} IQR[{K_lo:.4e},{K_hi:.4e}] (n={len(Ks)})")

    n_max = 9535.0
    S_max = n_max ** 2
    T_max = K * S_max
    u_max_pred = None
    # predicted top speed at S_max: K*S_max = |Xu|*u + |Xuu|*u^2
    disc = Xu_abs ** 2 + 4 * Xuu_abs * K * S_max
    if disc >= 0 and Xuu_abs > 0:
        u_max_pred = (-Xu_abs + np.sqrt(disc)) / (2 * Xuu_abs)
    print(f"T_max={T_max:.1f} N; predicted top speed at S_max: {u_max_pred:.2f} m/s "
          f"(measured 3.34)")

    # ---- plots ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(14, 6), dpi=130)
    axs[0].scatter([p["u_avg"] for p in coast_phases],
                   [p["dec"] for p in coast_phases], s=40, color="tab:blue")
    uu = np.linspace(0.5, 3.5, 50)
    axs[0].plot(uu, (Xu_abs * uu + Xuu_abs * uu ** 2) / MASS, "r-",
                label=f"fit: |Xu|={Xu_abs:.2f} |Xuu|={Xuu_abs:.2f}")
    axs[0].set_xlabel("u_avg (m/s)")
    axs[0].set_ylabel("deceleration (m/s^2)")
    axs[0].set_title(f"Coast-down drag (n={len(coast_phases)} phases, R2={r2:.3f})")
    axs[0].grid(alpha=0.3)
    axs[0].legend()
    us = np.array([p[0] for p in cruise_pts])
    Ss = np.array([p[1] for p in cruise_pts])
    axs[1].scatter(us, np.sqrt(Ss) / 1000, s=2, alpha=0.15, color="green",
                   label="cruise points")
    drag = Xu_abs * us + Xuu_abs * us ** 2
    axs[1].scatter(us, np.sqrt(drag / K) / 1000, s=2, alpha=0.15, color="red",
                   label="implied RPM from drag")
    axs[1].set_xlabel("u (m/s)")
    axs[1].set_ylabel("sqrt(S) (kRPM)")
    axs[1].set_title(f"Cruise balance check, K={K:.3e}")
    axs[1].grid(alpha=0.3)
    axs[1].legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "surge_coast_fit.png"))
    plt.close(fig)

    out = {
        "mass_anchor_kg": MASS,
        "method": "coast-down drag + cruise-balance K anchor",
        "Xu_N_per_mps": Xu,
        "Xuu_N_per_mps2": Xuu,
        "coast_fit_r2": r2,
        "n_coast_phases": len(coast_phases),
        "K_N_per_rpm2": K,
        "K_iqr": [K_lo, K_hi],
        "n_cruise_points": len(cruise_pts),
        "T_max_N": float(T_max),
        "u_max_predicted_mps": None if u_max_pred is None else float(u_max_pred),
        "coast_phases": coast_phases,
        "prior_0723": {"Xu": -2.272063, "Xuu": -11.571784, "assumed_K_T_N": 25.0},
    }
    with open(os.path.join(OUT_DIR, "surge_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved surge_params.json + surge_coast_fit.png in {OUT_DIR}")


if __name__ == "__main__":
    main()
