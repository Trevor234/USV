#!/usr/bin/env python3
"""Stage-2 surge identification v2: multi-segment shooting fit.

Model (straight runs, |r|<0.3):  m_tot * u_dot = K*S(t) - x*u - z*u^2
with S(t)=nL^2+nR^2 measured, m_tot=14.2 kg (anchor), x=-Xu>0, z=-Xuu>0.
Per segment: integrate from measured u0 with measured S(t), cost = mean((u_sim-u_meas)^2).
Nelder-Mead over (log K, log x, log z) -> signs guaranteed.
"""
import glob
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_surge import build_grid, DT_GRID  # reuse grid builder

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

MASS = 14.2
SEG_MIN_S = 3.5
SEG_MAX_S = 25.0
INTEG_DT = 0.1  # integration step (s), decimated from 20 Hz grid


def segments(g, min_len):
    base = (np.isfinite(g["u"]) & np.isfinite(g["S"]) & (g["u"] > 0.3)
            & (np.abs(g["r"]) < 0.5) & (g["S"] > 1e6) & (g["S"] < 8e7)
            & (g["v_mag"] < 4.5) & (g["v_mag"] > 0.2))
    idx = np.flatnonzero(base)
    if len(idx) == 0:
        return []
    out = []
    for grp in np.split(idx, np.where(np.diff(idx) > 5)[0] + 1):
        if len(grp) < min_len:
            continue
        for s in range(0, len(grp) - min_len + 1, min_len // 2):
            out.append(grp[s:s + min_len])
    return out


def simulate(t_us, S, u0, K, x, z, m=MASS):
    """Integrate m*udot = K*S - x*u - z*u^2 on the segment's time base."""
    dt = np.diff(t_us) / 1e6
    u = np.zeros(len(t_us))
    u[0] = u0
    for j in range(1, len(t_us)):
        h = dt[j - 1]
        s_mid = 0.5 * (S[j - 1] + S[j])
        k1 = (K * S[j - 1] - x * u[j - 1] - z * u[j - 1] ** 2) / m
        k2 = (K * s_mid - x * (u[j - 1] + 0.5 * h * k1)
              - z * (u[j - 1] + 0.5 * h * k1) ** 2) / m
        u[j] = u[j - 1] + h * k2
    return u


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
        if it % 50 == 0:
            print(f"  NM iter {it}: cost={vals[0]:.5f}")
    i = int(np.argmin(vals))
    return simplex[i], vals[i]


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build_grid(load := np.load(f, allow_pickle=True))
        if g is None:
            continue
        d = {k: g[k] for k in g}
        # decimate to ~10 Hz for integration
        sl = slice(None, None, 2)
        logs[name] = {kk: vv[sl] for kk, vv in d.items()}
        print(f"{name}: grid {len(g['t'])} -> {len(logs[name]['t'])} @10Hz, "
              f"u_max={np.nanmax(g['u']):.2f}")

    segs = []
    for name, g in logs.items():
        min_len = int(SEG_MIN_S / DT_GRID / 2)
        max_len = int(SEG_MAX_S / DT_GRID / 2)
        for grp in segments(g, min_len):
            for s in range(0, max(1, len(grp) - max_len + 1), max_len):
                chunk = grp[s:s + max_len]
                if len(chunk) >= min_len:
                    segs.append((name, chunk))
    print(f"segments: {len(segs)}")
    if len(segs) > 80:
        idx = np.linspace(0, len(segs) - 1, 80).astype(int)
        segs = [segs[i] for i in idx]
        print(f"  capped to {len(segs)} segments for optimization")
    if not segs:
        return

    def cost(p):
        logK, lx, lz = p
        K, x, z = np.exp(logK), np.exp(lx), np.exp(lz)
        if not np.isfinite(K * x * z):
            return 1e9
        total, cnt = 0.0, 0
        for name, chunk in segs:
            g = logs[name]
            u_meas = g["u"][chunk]
            u_sim = simulate(g["t"][chunk], g["S"][chunk], u_meas[0], K, x, z)
            total += np.sum((u_sim - u_meas) ** 2)
            cnt += len(chunk)
        return total / max(cnt, 1)

    p0 = [np.log(2.6e-7), np.log(2.27), np.log(11.57)]
    p_opt, c_opt = nelder_mead(cost, p0, [0.4, 0.4, 0.4], iters=500)
    K, Xu, Xuu = np.exp(p_opt[0]), -np.exp(p_opt[1]), -np.exp(p_opt[2])
    print(f"\nshooting fit: K={K:.4e}  Xu={Xu:.4f} (prior -2.2721)  "
          f"Xuu={Xuu:.4f} (prior -11.5718)  cost={c_opt:.5f}")

    # per-segment RMSEs
    rmses = []
    for name, chunk in segs:
        g = logs[name]
        u_sim = simulate(g["t"][chunk], g["S"][chunk], g["u"][chunk][0], K, -Xu, -Xuu)
        rmses.append((name, float(np.sqrt(np.mean((u_sim - g["u"][chunk]) ** 2))),
                      float(g["u"][chunk][-1])))
    rmses.sort(key=lambda t: -t[1])
    print("worst segments:")
    for name, r, ue in rmses[:5]:
        print(f"  {name} RMSE={r:.3f} (u_end={ue:.2f})")
    all_r = [r for _, r, _ in rmses]
    print(f"segment RMSE: median={np.median(all_r):.3f} p90={np.percentile(all_r, 90):.3f} m/s")

    n_max = max(np.nanmax(g["S"]) ** 0.5 for g in logs.values())
    T_max = K * n_max ** 2
    print(f"n_max(clean sum)={n_max:.0f} -> T_max = K*S_max = {T_max:.1f} N (prior assumed 25 N)")

    # plots: best/worst/median segment + steady curve
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    order = sorted(range(len(segs)), key=lambda i: rmses[i][1])
    picks = [order[0], order[len(order) // 2], order[-1]]
    fig, axs = plt.subplots(len(picks), 1, figsize=(11, 3 * len(picks)), dpi=130)
    for ax, pi in zip(np.atleast_1d(axs), picks):
        name, chunk = segs[pi]
        g = logs[name]
        u_sim = simulate(g["t"][chunk], g["S"][chunk], g["u"][chunk][0], K, -Xu, -Xuu)
        tt = (g["t"][chunk] - g["t"][chunk][0]) / 1e6
        ax.plot(tt, g["u"][chunk], label="measured")
        ax.plot(tt, u_sim, "--", label="sim")
        ax.set_title(f"{name}  RMSE={rmses[pi][1]:.3f} m/s")
        ax.legend()
        ax.grid(alpha=0.3)
        ax.set_ylabel("u (m/s)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "surge_shooting_segments.png"))
    plt.close(fig)

    out = {
        "mass_anchor_kg": MASS,
        "K_N_per_rpm2": K,
        "Xu_N_per_mps": Xu,
        "Xuu_N_per_mps2": Xuu,
        "method": "multi-segment shooting, Nelder-Mead, straight segments |r|<0.3",
        "n_segments": len(segs),
        "seg_rmse_median_mps": float(np.median(all_r)),
        "seg_rmse_p90_mps": float(np.percentile(all_r, 90)),
        "n_max_sqrt_sum_rpm": float(n_max),
        "T_max_N": float(T_max),
        "prior_0723": {"Xu": -2.272063, "Xuu": -11.571784, "assumed_K_T_N": 25.0},
    }
    with open(os.path.join(OUT_DIR, "surge_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved surge_params.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
