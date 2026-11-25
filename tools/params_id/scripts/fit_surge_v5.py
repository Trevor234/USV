#!/usr/bin/env python3
"""Stage-2 v5: operating-range balance curve + sprint-phase K anchor.

1. Balance cluster (u>1.2, quasi-steady, non-saturated PWM): S = a*u + b*u^2.
2. K anchor: per sustained accel phase, u_dot_avg=(u1-u0)/T (position endpoints),
   K = m*u_dot_avg / (S_avg - a*u_avg - b*u2_avg); median over phases.
3. Xu=-a*K, Xuu=-b*K, T_max=K*S_max, sprint replay validation.
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
PHASE_MIN_S = 3.0


def runs_of(mask, min_len, max_gap=10):
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    return [r for r in np.split(idx, np.where(np.diff(idx) > max_gap)[0] + 1)
            if len(r) >= min_len]


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build_grid(np.load(f, allow_pickle=True))
        if g is not None:
            sl = slice(None, None, 2)  # 10 Hz
            logs[name] = {k: v[sl] for k, v in g.items()}

    # need RCOU PWM on grid for saturation exclusion
    for name, g in logs.items():
        z = np.load(os.path.join(PARSED_DIR, name + ".npz"), allow_pickle=True)
        d = {k: z[k] for k in z.files}
        g["pwm1"] = np.interp(g["t"], d["RCOU.TimeUS"], d["RCOU.C1"],
                              left=np.nan, right=np.nan)
        g["pwm3"] = np.interp(g["t"], d["RCOU.TimeUS"], d["RCOU.C3"],
                              left=np.nan, right=np.nan)

    # ---- 1. balance cluster ----
    bal_u, bal_S, bal_tag = [], [], []
    for name, g in logs.items():
        acc = g["accx"] if g["accx"] is not None else np.full(len(g["t"]), np.nan)
        m = (np.isfinite(acc) & np.isfinite(g["S"]) & np.isfinite(g["u"])
             & (np.abs(acc) < 0.15) & (np.abs(g["r"]) < 0.6)
             & (g["u"] > 1.2) & (g["u"] < 3.6)
             & (g["S"] > 4e6) & (g["S"] < 8e7)
             & (g["v_mag"] > 0.5) & (g["v_mag"] < 4.5)
             & (g["pwm1"] < 1965) & (g["pwm3"] < 1965))
        bal_u.append(g["u"][m])
        bal_S.append(g["S"][m])
        bal_tag += [name] * int(m.sum())
    bal_u = np.concatenate(bal_u)
    bal_S = np.concatenate(bal_S)
    A = np.column_stack([bal_u, bal_u ** 2])
    coef, *_ = np.linalg.lstsq(A, bal_S, rcond=None)
    a_, b_ = float(coef[0]), float(max(coef[1], 0.0))
    if b_ != coef[1]:
        c0, *_ = np.linalg.lstsq(bal_u.reshape(-1, 1), bal_S, rcond=None)
        a_, b_ = float(c0[0]), 0.0
        A = bal_u.reshape(-1, 1)
    pred = A @ [a_, b_] if b_ > 0 else A * a_
    r2 = 1 - np.sum((bal_S - pred) ** 2) / np.sum((bal_S - np.mean(bal_S)) ** 2)
    print(f"balance cluster: n={len(bal_u)}  S = {a_:.0f}*u + {b_:.1f}*u^2  (R2={r2:.4f})")

    # ---- 2. accel phases -> K ----
    Ks, phase_info = [], []
    for name, g in logs.items():
        acc = g["accx"] if g["accx"] is not None else np.full(len(g["t"]), np.nan)
        m = (np.isfinite(acc) & np.isfinite(g["S"]) & np.isfinite(g["u"])
             & (acc > 0.25) & (np.abs(g["r"]) < 0.6)
             & (g["u"] > 0.8) & (g["u"] < 3.4)
             & (g["v_mag"] > 0.5) & (g["v_mag"] < 4.5)
             & (g["pwm1"] > 1650) & (g["pwm3"] > 1650))
        for run in runs_of(m, int(PHASE_MIN_S / 0.1)):
            i0, i1 = run[0], run[-1]
            T = (g["t"][i1] - g["t"][i0]) / 1e6
            if T < PHASE_MIN_S:
                continue
            u_dot_avg = (g["u"][i1] - g["u"][i0]) / T
            S_avg = float(np.mean(g["S"][run]))
            u_avg = float(np.mean(g["u"][run]))
            u2_avg = float(np.mean(g["u"][run] ** 2))
            denom = S_avg - a_ * u_avg - b_ * u2_avg
            if denom <= 0.05 * S_avg or u_dot_avg <= 0.02:
                continue
            K_i = MASS * u_dot_avg / denom
            if 1e-8 < K_i < 1e-5:
                Ks.append(K_i)
                phase_info.append({"log": name[-9:], "T": float(T),
                                   "u_dot_avg": float(u_dot_avg),
                                   "S_avg": S_avg, "u_avg": u_avg,
                                   "K": float(K_i)})
    K = float(np.median(Ks)) if Ks else None
    print(f"K anchor: {len(Ks)} phases")
    for p in phase_info:
        print(f"  {p['log']} T={p['T']:.1f}s udot={p['u_dot_avg']:+.2f} "
              f"S={p['S_avg']:.2e} u={p['u_avg']:.2f} -> K={p['K']:.3e}")
    if K is None:
        print("no anchor phases; abort")
        return
    K_lo = float(np.percentile(Ks, 25))
    K_hi = float(np.percentile(Ks, 75))

    Xu = -a_ * K
    Xuu = -b_ * K
    n_max = max(np.nanmax(g["S"]) ** 0.5 for g in logs.values())
    T_max = K * n_max ** 2
    print(f"\nFINAL: K={K:.4e} N/RPM^2  Xu={Xu:.3f} (prior -2.2721)  "
          f"Xuu={Xuu:.3f} (prior -11.5718)")
    print(f"T_max={T_max:.1f} N at sqrt(S_max)={n_max:.0f} (prior assumed 25 N)")

    # ---- 3. sprint replay validation (best accel phase, integrated) ----
    def simulate(t_us, S, u0, K, x, z):
        dt = np.diff(t_us) / 1e6
        u = np.zeros(len(t_us))
        u[0] = u0
        for j in range(1, len(t_us)):
            h = dt[j - 1]
            k1 = (K * S[j - 1] - x * u[j - 1] - z * u[j - 1] ** 2) / MASS
            s_mid = 0.5 * (S[j - 1] + S[j])
            k2 = (K * s_mid - x * (u[j - 1] + 0.5 * h * k1)
                  - z * (u[j - 1] + 0.5 * h * k1) ** 2) / MASS
            u[j] = u[j - 1] + h * k2
        return u

    best = None
    for name, g in logs.items():
        acc = g["accx"] if g["accx"] is not None else np.full(len(g["t"]), np.nan)
        m = (np.isfinite(acc) & np.isfinite(g["S"]) & np.isfinite(g["u"])
             & (acc > 0.1) & (np.abs(g["r"]) < 0.6) & (g["u"] > 0.6)
             & (g["v_mag"] > 0.5) & (g["v_mag"] < 4.5))
        for run in runs_of(m, int(4.0 / 0.1)):
            i0, i1 = run[0], run[-1]
            T = (g["t"][i1] - g["t"][i0]) / 1e6
            du = g["u"][i1] - g["u"][i0]
            if du < 0.5:
                continue
            u_sim = simulate(g["t"][run], g["S"][run], g["u"][i0], K, -Xu, -Xuu)
            rmse = float(np.sqrt(np.mean((u_sim - g["u"][run]) ** 2)))
            if best is None or rmse < best["rmse"]:
                best = {"name": name, "run": run, "rmse": rmse, "T": T, "du": float(du)}
    if best:
        g = logs[best["name"]]
        run = best["run"]
        print(f"sprint replay: {best['name']} T={best['T']:.1f}s du={best['du']:.2f} "
              f"RMSE={best['rmse']:.3f} m/s")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 5.5), dpi=130)
        tt = (g["t"][run] - g["t"][run[0]]) / 1e6
        ax.plot(tt, g["u"][run], label="measured u")
        ax.plot(tt, simulate(g["t"][run], g["S"][run], g["u"][run[0]], K, -Xu, -Xuu),
                "--", label="sim (identified)")
        ax2 = ax.twinx()
        ax2.plot(tt, np.sqrt(g["S"][run]) / 1000, color="tab:red", alpha=0.6,
                 label="mean prop kRPM")
        ax2.set_ylabel("kRPM")
        ax.set_xlabel("t (s)")
        ax.set_ylabel("u (m/s)")
        ax.set_title(f"Sprint replay ({best['name']}), RMSE={best['rmse']:.3f} m/s")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left")
        ax2.legend(loc="lower right")
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "surge_sprint_replay.png"))
        plt.close(fig)

    # steady curve plot
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=130)
    ax.scatter(np.sqrt(bal_S) / 60, bal_u, s=3, alpha=0.25, label="balance cluster")
    nn = np.linspace(1000, n_max / np.sqrt(2) / 60, 120)
    S_nn = (nn * 60) ** 2
    u_pred = ((-a_ + np.sqrt(a_ ** 2 + 4 * b_ * S_nn)) / (2 * b_)) if b_ > 0 else S_nn / a_
    ax.plot(nn, u_pred, "r-", lw=2, label=f"identified balance (a={a_:.0f}, b={b_:.0f})")
    ax.set_xlabel("mean prop speed sqrt(nL^2+nR^2) (kRPM)")
    ax.set_ylabel("steady u (m/s)")
    ax.set_title(f"Operating-range thrust balance, R2={r2:.4f}")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "surge_steady_curve.png"))
    plt.close(fig)

    out = {
        "mass_anchor_kg": MASS,
        "method": "operating-range balance curve + sprint-phase K anchor",
        "balance_curve": {"a": a_, "b": b_, "r2": r2, "n": int(len(bal_u))},
        "K_N_per_rpm2": K,
        "K_iqr": [K_lo, K_hi],
        "n_anchor_phases": len(Ks),
        "Xu_N_per_mps": Xu,
        "Xuu_N_per_mps2": Xuu,
        "T_max_N": float(T_max),
        "sprint_replay": {k: best[k] for k in ("name", "rmse", "T", "du")} if best else None,
        "prior_0723": {"Xu": -2.272063, "Xuu": -11.571784, "assumed_K_T_N": 25.0},
    }
    with open(os.path.join(OUT_DIR, "surge_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved surge_params.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
