#!/usr/bin/env python3
"""Stage-3 yaw identification: shooting fit on gyro yaw-rate r(t).

Model (body-z):  I_z_eff * r_dot = d*(T_R - T_L) - N_r*r - N_rr*r*|r|
  T_i = K * n_i^2 * sgn(pwm_i - 1500),  K fixed (7-23 assumption @ measured RPM),
  d = 0.25 m (geometry). Unknowns: I_z_eff, N_r, N_rr (all positive via log fit).
r measured by gyro (73 Hz, clean) -> shooting is noise-robust.
"""
import glob
import json
import os
import sys
import numpy as np

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

MASS = 14.2
D_THR = 0.25
K_FIXED = 25.0 / 3900.0 ** 2     # 7-23 assumed T_max @ measured n_max
SEG_MIN_S = 4.0
DT = 0.1


def interp1(t_src, y_src, t_dst):
    t_src = np.asarray(t_src, float)
    y_src = np.asarray(y_src, float)
    good = np.isfinite(t_src) & np.isfinite(y_src)
    t_src, y_src = t_src[good], y_src[good]
    order = np.argsort(t_src)
    return np.interp(t_dst, t_src[order], y_src[order], left=np.nan, right=np.nan)


def movavg(x, n):
    if n < 2:
        return x.copy()
    return np.convolve(x, np.ones(n) / n, mode="same")


def runs_of(mask, min_len, max_gap=10):
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    return [r for r in np.split(idx, np.where(np.diff(idx) > max_gap)[0] + 1)
            if len(r) >= min_len]


def build(d):
    t_imu = d["IMU.TimeUS"]
    if t_imu is None or len(t_imu) < 500:
        return None
    tg = np.arange(t_imu[0], t_imu[-1], DT * 1e6)
    if len(tg) < 200:
        return None
    gyrz = interp1(t_imu, d["IMU.GyrZ"], tg)
    att_t = d["ATT.TimeUS"]
    yaw_u = np.unwrap(np.radians(interp1(att_t, d["ATT.Yaw"], tg)))
    r_att = np.gradient(yaw_u, DT)
    # gyro unit: ArduPilot DataFlash IMU GyrZ is rad/s (verified: max 2.32 rad/s
    # in the log whose report yaw-rate peak is 132.9 deg/s). Only sign-check vs attitude.
    g = np.isfinite(gyrz) & np.isfinite(r_att) & (np.abs(r_att) > 0.05)
    csign = np.sign(np.corrcoef(gyrz[g], r_att[g])[0, 1]) if g.sum() > 10 else 1.0
    if csign == 0:
        csign = 1.0
    r_gyro = gyrz * csign
    # thrusters
    esc_t = d["ESC.TimeUS"]
    inst = d["ESC.Instance"].astype(int)
    rpm = d["ESC.RPM"]
    sane = (rpm > 30) & (rpm < 8000)
    if ((inst == 0) & sane).sum() < 100 or ((inst == 2) & sane).sum() < 100:
        return None
    nl = interp1(esc_t[(inst == 0) & sane], rpm[(inst == 0) & sane], tg)
    nr = interp1(esc_t[(inst == 2) & sane], rpm[(inst == 2) & sane], tg)
    pwm1 = interp1(d["RCOU.TimeUS"], d["RCOU.C1"], tg)
    pwm3 = interp1(d["RCOU.TimeUS"], d["RCOU.C3"], tg)
    # refill edge/gap NaNs so runs are not chopped and sims stay finite
    for arr in (nl, nr, pwm1, pwm3):
        f = np.isfinite(arr)
        if f.sum() > 1:
            arr[~f] = np.interp(tg[~f], tg[f], arr[f])
        else:
            return None
    return {"t": tg, "r": r_gyro, "nl": nl, "nr": nr, "pwm1": pwm1, "pwm3": pwm3,
            "gyro_sign": csign}


def thrust_diff(g, K):
    """d*(T_R - T_L) in N·m."""
    s1 = np.sign(g["pwm1"] - 1500)
    s3 = np.sign(g["pwm3"] - 1500)
    TL = K * g["nl"] ** 2 * s1
    TR = K * g["nr"] ** 2 * s3
    return D_THR * (TR - TL), TL, TR


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build(np.load(f, allow_pickle=True))
        if g is not None:
            logs[name] = g
            print(f"{name}: gyro_sign={g['gyro_sign']:+.0f} (GyrZ verified rad/s)")

    segs = []
    for name, g in logs.items():
        valid = (np.isfinite(g["r"]) & np.isfinite(g["nl"]) & np.isfinite(g["nr"])
                 & (np.abs(g["r"]) < 3.5))
        for run in runs_of(valid, int(SEG_MIN_S / DT)):
            # split long runs into <=25 s chunks
            max_len = int(25.0 / DT)
            for s in range(0, max(1, len(run) - max_len + 1), max_len // 2):
                chunk = run[s:s + max_len]
                if len(chunk) >= int(SEG_MIN_S / DT):
                    segs.append((name, chunk))
    print(f"segments: {len(segs)}")
    if len(segs) > 80:
        idx = np.linspace(0, len(segs) - 1, 80).astype(int)
        segs = [segs[i] for i in idx]

    def cost(p):
        lI, ln, lnrr = p
        Iz, Nr, Nrr = np.exp(lI), np.exp(ln), np.exp(lnrr)
        if not np.isfinite(Iz * Nr * Nrr) or not (0.3 < Iz < 200 and 0.02 < Nr < 300
                                                  and 0 <= Nrr < 100):
            return 1e9
        total, cnt = 0.0, 0
        for name, run in segs:
            g = logs[name]
            tau, _, _ = thrust_diff(g, K_FIXED)
            tau = tau[run]
            rr = g["r"][run]
            r_sim = np.zeros(len(run))
            r_sim[0] = rr[0]
            for j in range(1, len(run)):
                k1 = (tau[j - 1] - Nr * r_sim[j - 1] - Nrr * r_sim[j - 1] * abs(r_sim[j - 1])) / Iz
                tau_m = 0.5 * (tau[j - 1] + tau[j])
                r_m = r_sim[j - 1] + 0.5 * DT * k1
                k2 = (tau_m - Nr * r_m - Nrr * r_m * abs(r_m)) / Iz
                r_sim[j] = r_sim[j - 1] + DT * k2
            seg_cost = np.sum((r_sim - rr) ** 2)
            if not np.isfinite(seg_cost):
                return 1e9
            total += seg_cost
            cnt += len(run)
        return total / max(cnt, 1)

    p_opt, c_opt = None, None
    best = None
    # multi-start: init from prior and from a "small damping" guess
    for init in ([np.log(3.75), np.log(4.29), np.log(0.001)],
                 [np.log(3.75), np.log(1.0), np.log(0.05)],
                 [np.log(3.75), np.log(8.0), np.log(0.5)]):
        # simple coordinate NM (reuse pattern)
        def nm(f, x0, step, iters=250):
            n = len(x0)
            simplex = [np.array(x0, float)]
            for i in range(n):
                p = np.array(x0, float)
                p[i] += step[i]
                simplex.append(p)
            vals = [f(p) for p in simplex]
            for _ in range(iters):
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
        p, c = nm(cost, init, [0.4, 0.5, 1.0])
        print(f"  start {init}: cost={c:.5f} -> Iz={np.exp(p[0]):.3f} "
              f"Nr={np.exp(p[1]):.3f} Nrr={np.exp(p[2]):.4f}")
        if best is None or c < best[1]:
            best = (p, c)
    p_opt, c_opt = best
    Iz = float(np.exp(p_opt[0]))
    Nr = float(np.exp(p_opt[1]))
    Nrr = float(np.exp(p_opt[2]))
    print(f"\nFINAL: I_z_eff={Iz:.3f} kg·m^2 (prior 3.75)  Nr={Nr:.3f} (prior 4.286)  "
          f"Nrr={Nrr:.4f} (prior 0.001)  cost={c_opt:.5f}")

    rmses = []
    for name, run in segs:
        g = logs[name]
        tau, _, _ = thrust_diff(g, K_FIXED)
        tau_r = tau[run]
        rr = g["r"][run]
        r_sim = np.zeros(len(run))
        r_sim[0] = rr[0]
        for j in range(1, len(run)):
            k1 = (tau_r[j - 1] - Nr * r_sim[j - 1] - Nrr * r_sim[j - 1] * abs(r_sim[j - 1])) / Iz
            tau_m = 0.5 * (tau_r[j - 1] + tau_r[j])
            r_m = r_sim[j - 1] + 0.5 * DT * k1
            k2 = (tau_m - Nr * r_m - Nrr * r_m * abs(r_m)) / Iz
            r_sim[j] = r_sim[j - 1] + DT * k2
        rmses.append(float(np.sqrt(np.mean((r_sim - rr) ** 2))))
    rmses = np.array(rmses)
    print(f"segment RMSE: median={np.median(rmses):.4f} p75={np.percentile(rmses,75):.4f} "
          f"p90={np.percentile(rmses,90):.4f} rad/s")

    # plots
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    order = np.argsort(rmses)
    picks = [order[0], order[len(order) // 2], order[-1]]
    fig, axs = plt.subplots(3, 1, figsize=(11, 9), dpi=130)
    for ax, pi in zip(axs, picks):
        name, run = segs[pi]
        g = logs[name]
        tau, TL, TR = thrust_diff(g, K_FIXED)
        tau_r = tau[run]
        rr = g["r"][run]
        r_sim = np.zeros(len(run))
        r_sim[0] = rr[0]
        for j in range(1, len(run)):
            k1 = (tau_r[j - 1] - Nr * r_sim[j - 1] - Nrr * r_sim[j - 1] * abs(r_sim[j - 1])) / Iz
            tau_m = 0.5 * (tau_r[j - 1] + tau_r[j])
            r_m = r_sim[j - 1] + 0.5 * DT * k1
            k2 = (tau_m - Nr * r_m - Nrr * r_m * abs(r_m)) / Iz
            r_sim[j] = r_sim[j - 1] + DT * k2
        tt = (g["t"][run] - g["t"][run[0]]) / 1e6
        ax.plot(tt, np.degrees(rr), label="measured r (gyro)")
        ax.plot(tt, np.degrees(r_sim), "--", label="sim")
        ax2 = ax.twinx()
        ax2.plot(tt, (g["pwm3"][run] - g["pwm1"][run]), color="tab:orange", alpha=0.4,
                 label="dPWM (C3-C1)")
        ax2.set_ylabel("dPWM (us)")
        ax.set_title(f"{name}  RMSE={np.degrees(rmses[pi]):.1f} deg/s")
        ax.set_ylabel("r (deg/s)")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left")
        ax2.legend(loc="lower right")
    axs[-1].set_xlabel("t (s)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "yaw_shooting_segments.png"))
    plt.close(fig)

    out = {
        "mass_anchor_kg": MASS,
        "method": "yaw shooting on gyro r, K fixed by 7-23 assumption, d=0.25 geometry",
        "K_N_per_rpm2_fixed": K_FIXED,
        "Iz_eff_kgm2": Iz,
        "Nr_Nms_per_rad": Nr,
        "Nrr_Nms2_per_rad2": Nrr,
        "n_segments": len(segs),
        "seg_rmse_median_degps": float(np.degrees(np.median(rmses))),
        "seg_rmse_p90_degps": float(np.degrees(np.percentile(rmses, 90))),
        "prior_0723": {"Iz_eff": 3.75, "Nr": 4.286144, "Nrr": 0.001},
    }
    with open(os.path.join(OUT_DIR, "yaw_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved yaw_params.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
