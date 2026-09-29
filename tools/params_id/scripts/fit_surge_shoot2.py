#!/usr/bin/env python3
"""Stage-2 v6: shooting fit of drag (Xu, Xuu) with K fixed by the 7-23 thrust
assumption (T_max=25 N per thruster at measured full-throttle RPM).

Rationale: the 2026-09-03 dataset has no coast-down/neutral-throttle segments and
no constant-throttle straight runs, so the absolute thrust scale (K) is not
observable. We keep the 7-23 assumed thrust scale, transfer it to the MEASURED
RPM domain (K = 25 / n_max_per_prop^2), and refit the drag shape on this data.
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
SEG_MIN_S = 3.5
N_MAX_PROP = 3900.0     # measured clean per-prop max RPM (stage 1)
T_MAX_ASSUMED = 25.0    # 7-23 assumed per-thruster max thrust (N)
K_FIXED = T_MAX_ASSUMED / N_MAX_PROP ** 2


def runs_of(mask, min_len, max_gap=10):
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    return [r for r in np.split(idx, np.where(np.diff(idx) > max_gap)[0] + 1)
            if len(r) >= min_len]


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


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build_grid(np.load(f, allow_pickle=True))
        if g is not None:
            sl = slice(None, None, 2)
            logs[name] = {k: v[sl] for k, v in g.items()}
    for name, g in logs.items():
        z = np.load(os.path.join(PARSED_DIR, name + ".npz"), allow_pickle=True)
        d = {k: z[k] for k in z.files}
        g["pwm1"] = np.interp(g["t"], d["RCOU.TimeUS"], d["RCOU.C1"],
                              left=np.nan, right=np.nan)
        g["pwm3"] = np.interp(g["t"], d["RCOU.TimeUS"], d["RCOU.C3"],
                              left=np.nan, right=np.nan)

    segs = []
    for name, g in logs.items():
        acc = g["accx"] if g["accx"] is not None else np.zeros(len(g["t"]))
        m = (np.isfinite(g["u"]) & np.isfinite(g["S"]) & (g["u"] > 0.3)
             & (np.abs(g["r"]) < 0.5) & (g["S"] > 1e6) & (g["S"] < 8e7)
             & (g["v_mag"] > 0.2) & (g["v_mag"] < 4.5)
             & (g["pwm1"] < 1965) & (g["pwm3"] < 1965))
        for run in runs_of(m, int(SEG_MIN_S / 0.1)):
            segs.append((name, run))
    print(f"segments: {len(segs)}")
    if len(segs) > 100:
        idx = np.linspace(0, len(segs) - 1, 100).astype(int)
        segs = [segs[i] for i in idx]

    def cost(p):
        lx, lz = p
        x, z = np.exp(lx), np.exp(lz)
        if not np.isfinite(x * z):
            return 1e9
        total, cnt = 0.0, 0
        for name, chunk in segs:
            g = logs[name]
            u_meas = g["u"][chunk]
            u_sim = simulate(g["t"][chunk], g["S"][chunk], u_meas[0], K_FIXED, x, z)
            total += np.sum((u_sim - u_meas) ** 2)
            cnt += len(chunk)
        return total / max(cnt, 1)

    def nelder_mead(f, x0, step, iters=400):
        n = len(x0)
        simplex = [np.array(x0, float)]
        for i in range(n):
            p = np.array(x0, float)
            p[i] += step[i]
            simplex.append(p)
        vals = [f(p) for p in simplex]
        for it in range(iters):
            order = np.argsort(vals)
            simplex = [simplex[i] for i in order]
            vals = [vals[i] for i in order]
            cen = np.mean(simplex[:-1], axis=0)
            xr = cen + (cen - simplex[-1])
            fr = f(xr)
            if fr < vals[0]:
                xe = cen + 2 * (cen - simplex[-1])
                fe = f(xe)
                simplex[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
            elif fr < vals[-2]:
                simplex[-1], vals[-1] = xr, fr
            else:
                xc = cen + 0.5 * (simplex[-1] - cen)
                fc = f(xc)
                if fc < vals[-1]:
                    simplex[-1], vals[-1] = xc, fc
                else:
                    for i in range(1, n + 1):
                        simplex[i] = simplex[0] + 0.5 * (simplex[i] - simplex[0])
                        vals[i] = f(simplex[i])
        i = int(np.argmin(vals))
        return simplex[i], vals[i]

    p_opt, c_opt = nelder_mead(cost, [np.log(2.27), np.log(11.57)],
                               [0.5, 0.5], iters=300)
    Xu, Xuu = -np.exp(p_opt[0]), -np.exp(p_opt[1])
    print(f"\nfit (K fixed={K_FIXED:.4e}): Xu={Xu:.4f} (prior -2.2721)  "
          f"Xuu={Xuu:.4f} (prior -11.5718)  cost={c_opt:.5f}")

    rmses = []
    for name, chunk in segs:
        g = logs[name]
        u_sim = simulate(g["t"][chunk], g["S"][chunk], g["u"][chunk][0],
                         K_FIXED, -Xu, -Xuu)
        rmses.append(float(np.sqrt(np.mean((u_sim - g["u"][chunk]) ** 2))))
    rmses = np.array(rmses)
    print(f"segment RMSE: median={np.median(rmses):.3f} "
          f"p25={np.percentile(rmses,25):.3f} p75={np.percentile(rmses,75):.3f} "
          f"p90={np.percentile(rmses,90):.3f} m/s")

    # top-3 worst + median segments plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    order = np.argsort(rmses)
    picks = [order[0], order[len(order) // 2], order[-1]]
    fig, axs = plt.subplots(3, 1, figsize=(11, 9), dpi=130)
    for ax, pi in zip(axs, picks):
        name, chunk = segs[pi]
        g = logs[name]
        u_sim = simulate(g["t"][chunk], g["S"][chunk], g["u"][chunk][0],
                         K_FIXED, -Xu, -Xuu)
        tt = (g["t"][chunk] - g["t"][chunk][0]) / 1e6
        ax.plot(tt, g["u"][chunk], label="measured")
        ax.plot(tt, u_sim, "--", label="sim")
        ax.set_title(f"{name}  RMSE={rmses[pi]:.3f} m/s")
        ax.legend()
        ax.grid(alpha=0.3)
        ax.set_ylabel("u (m/s)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "surge_shooting_segments.png"))
    plt.close(fig)

    out = {
        "mass_anchor_kg": MASS,
        "method": ("shooting fit of drag (Xu,Xuu) with K fixed by 7-23 thrust "
                   "assumption transferred to measured RPM"),
        "K_N_per_rpm2_fixed": K_FIXED,
        "K_assumption": f"T_max={T_MAX_ASSUMED}N per thruster at {N_MAX_PROP} RPM (7-23 assumed)",
        "Xu_N_per_mps": Xu,
        "Xuu_N_per_mps2": Xuu,
        "n_segments": len(segs),
        "seg_rmse_median_mps": float(np.median(rmses)),
        "seg_rmse_p90_mps": float(np.percentile(rmses, 90)),
        "T_max_N": T_MAX_ASSUMED,
        "prior_0723": {"Xu": -2.272063, "Xuu": -11.571784},
    }
    with open(os.path.join(OUT_DIR, "surge_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved surge_params.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
