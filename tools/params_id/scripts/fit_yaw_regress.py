#!/usr/bin/env python3
"""Stage-3 v2: yaw identification by angular-acceleration regression.

r_dot = (tau - Nr*r - Nrr*r*|r|) / Iz,  tau = d*K*(TR-TL), K fixed by 7-23
assumption, d=0.25 geometry. r from gyro (rad/s, clean); r_dot from smoothed
gyro derivative. Linear LS over (1/Iz, Nr/Iz, Nrr/Iz) with sign constraints.
Auto-checks: prop mapping (normal vs swapped) and time shift (-0.4..+0.4 s).
"""
import glob
import json
import os
import sys
import numpy as np

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

D_THR = 0.25
K_FIXED = 25.0 / 3900.0 ** 2
DT = 0.05
SMOOTH_N = 7   # ~0.35 s smoothing on r before derivative


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


def build(d, swap, shift_us):
    t_imu = d["IMU.TimeUS"]
    if t_imu is None or len(t_imu) < 500:
        return None
    tg = np.arange(t_imu[0], t_imu[-1], DT * 1e6)
    if len(tg) < 400:
        return None
    r = interp1(t_imu, d["IMU.GyrZ"], tg)          # rad/s
    att_t = d["ATT.TimeUS"] + shift_us
    psi = np.unwrap(np.radians(interp1(att_t, d["ATT.Yaw"], tg)))
    r_att = np.gradient(psi, DT)
    g = np.isfinite(r) & np.isfinite(r_att) & (np.abs(r_att) > 0.05)
    if g.sum() < 100 or np.corrcoef(r[g], r_att[g])[0, 1] < 0:
        return None
    esc_t = d["ESC.TimeUS"]
    inst = d["ESC.Instance"].astype(int)
    rpm = d["ESC.RPM"]
    sane = (rpm > 30) & (rpm < 8000)
    m0 = (inst == 0) & sane
    m2 = (inst == 2) & sane
    if m0.sum() < 100 or m2.sum() < 100:
        return None
    n0 = interp1(esc_t[m0], rpm[m0], tg)
    n2 = interp1(esc_t[m2], rpm[m2], tg)
    pwm1 = interp1(d["RCOU.TimeUS"] + shift_us, d["RCOU.C1"], tg)
    pwm3 = interp1(d["RCOU.TimeUS"] + shift_us, d["RCOU.C3"], tg)
    for arr in (n0, n2, pwm1, pwm3):
        f = np.isfinite(arr)
        if f.sum() > 1:
            arr[~f] = np.interp(tg[~f], tg[f], arr[f])
        else:
            return None
    # thrust differential with mapping choice.
    # NED body frame (x fwd, y right, z down): tau_z = -y*F -> left(y=-d) forward
    # thrust gives +tau; hence tau = d*(T_L - T_R).
    if not swap:
        sL, sR, nL, nR = np.sign(pwm1 - 1500), np.sign(pwm3 - 1500), n0, n2
    else:
        sL, sR, nL, nR = np.sign(pwm3 - 1500), np.sign(pwm1 - 1500), n2, n0
    tau = D_THR * K_FIXED * (nL ** 2 * sL - nR ** 2 * sR)
    rs = movavg(r, SMOOTH_N)
    rdot = np.gradient(rs, DT)
    ok = np.isfinite(tau) & np.isfinite(rdot) & (np.abs(r) < 3.5)
    return {"t": tg, "r": r, "rdot": rdot, "tau": tau, "ok": ok}


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        for swap in (False, True):
            g = build(np.load(f, allow_pickle=True), swap, 0)
            if g is not None:
                tau = g["tau"][g["ok"]]
                rd = g["rdot"][g["ok"]]
                if len(tau) > 200:
                    c = np.corrcoef(tau, rd)[0, 1]
                    logs[(name, swap)] = g
                    print(f"{name} swap={swap}: corr(tau, rdot)={c:.3f} n={len(tau)}")
    # pick mapping by pooled |corr| (higher = correct)
    sums = {False: 0.0, True: 0.0}
    for (name, swap), g in logs.items():
        tau = g["tau"][g["ok"]]
        rd = g["rdot"][g["ok"]]
        sums[swap] += abs(np.corrcoef(tau, rd)[0, 1])
    swap_choice = max(sums, key=sums.get)
    print(f"mapping choice: swap={swap_choice} (pooled |corr| {sums[False]:.3f} vs {sums[True]:.3f})")

    # time shift scan on chosen mapping
    best_shift = 0
    best_c = -9
    for shift in (-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4):
        cc = []
        for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
            name = os.path.basename(f).replace(".npz", "")
            g = build(np.load(f, allow_pickle=True), swap_choice, int(shift * 1e6))
            if g is None:
                continue
            tau = g["tau"][g["ok"]]
            rd = g["rdot"][g["ok"]]
            if len(tau) > 200:
                cc.append(np.corrcoef(tau, rd)[0, 1])
        c = np.mean(cc) if cc else -9
        print(f"  shift {shift:+.1f}s: mean corr={c:.3f}")
        if c > best_c:
            best_c, best_shift = c, shift
    print(f"best shift: {best_shift:+.1f}s (corr={best_c:.3f})")

    # ---- pooled regression with chosen mapping + shift ----
    tau_all, r_all, rd_all = [], [], []
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build(np.load(f, allow_pickle=True), swap_choice, int(best_shift * 1e6))
        if g is None:
            continue
        tau_all.append(g["tau"][g["ok"]])
        r_all.append(g["r"][g["ok"]])
        rd_all.append(g["rdot"][g["ok"]])
    tau_all = np.concatenate(tau_all)
    r_all = np.concatenate(r_all)
    rd_all = np.concatenate(rd_all)
    A = np.column_stack([tau_all, -r_all, -r_all * np.abs(r_all)])
    y = rd_all
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    inv_Iz, NrIz, NrrIz = coef
    if inv_Iz <= 0:
        print("WARN: 1/Iz negative — signs inconsistent")
        return
    Iz = 1.0 / inv_Iz
    Nr = NrIz / inv_Iz
    Nrr = NrrIz / inv_Iz
    pred = A @ coef
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - np.mean(y)) ** 2)
    print(f"\nregression (n={len(y)}): R2={r2:.4f}")
    print(f"  I_z_eff = {Iz:.3f} kg·m^2 (prior 3.75)")
    print(f"  Nr      = {Nr:.3f} N·m/(rad/s) (prior 4.286)")
    print(f"  Nrr     = {Nrr:.4f} N·m/(rad/s)^2 (prior 0.001)")
    print(f"  implied steady r at tau=6.25N·m (full diff): {6.25/Nr:.2f} rad/s"
          f" = {np.degrees(6.25/Nr):.0f} deg/s")

    # ---- shooting validation on holdout-style full segments ----
    def simulate(g, run, Iz, Nr, Nrr):
        tau = g["tau"][run]
        rr = g["r"][run]
        r_sim = np.zeros(len(run))
        r_sim[0] = rr[0]
        for j in range(1, len(run)):
            k1 = (tau[j - 1] - Nr * r_sim[j - 1] - Nrr * r_sim[j - 1] * abs(r_sim[j - 1])) / Iz
            tau_m = 0.5 * (tau[j - 1] + tau[j])
            r_m = r_sim[j - 1] + 0.5 * DT * k1
            k2 = (tau_m - Nr * r_m - Nrr * r_m * abs(r_m)) / Iz
            r_sim[j] = r_sim[j - 1] + DT * k2
        return r_sim

    seg_rmses = []
    for (name, swap), g in logs.items():
        if swap != swap_choice:
            continue
        valid = g["ok"] & np.isfinite(g["r"])
        idx = np.flatnonzero(valid)
        if len(idx) == 0:
            continue
        for run in [r for r in np.split(idx, np.where(np.diff(idx) > 20)[0] + 1)
                    if len(r) >= 80][:4]:
            r_sim = simulate(g, run, Iz, Nr, Nrr)
            seg_rmses.append((name, run, float(np.sqrt(np.mean((r_sim - g["r"][run]) ** 2))), g))
    if seg_rmses:
        med = np.median([s[2] for s in seg_rmses])
        print(f"shooting validation on {len(seg_rmses)} full segments: "
              f"median RMSE={np.degrees(med):.1f} deg/s")

    # plots: best/worst segment
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if seg_rmses:
        seg_rmses.sort(key=lambda s: s[2])
        picks = [seg_rmses[0], seg_rmses[len(seg_rmses) // 2], seg_rmses[-1]]
        fig, axs = plt.subplots(3, 1, figsize=(11, 9), dpi=130)
        for ax, (name, run, rm, g) in zip(axs, picks):
            tt = (g["t"][run] - g["t"][run[0]]) / 1e6
            r_sim = simulate(g, run, Iz, Nr, Nrr)
            ax.plot(tt, np.degrees(g["r"][run]), label="measured r")
            ax.plot(tt, np.degrees(r_sim), "--", label="sim")
            if "pwm3" in g and "pwm1" in g:
                ax2 = ax.twinx()
                ax2.plot(tt, (g["pwm3"][run] - g["pwm1"][run]), color="tab:orange",
                         alpha=0.4, label="dPWM")
                ax2.set_ylabel("dPWM (us)")
                ax2.legend(loc="lower right")
            ax.set_title(f"{name} RMSE={np.degrees(rm):.1f} deg/s")
            ax.set_ylabel("r (deg/s)")
            ax.grid(alpha=0.3)
            ax.legend(loc="upper left")
        axs[-1].set_xlabel("t (s)")
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "yaw_segments.png"))
        plt.close(fig)

    out = {
        "method": "yaw angular-acceleration regression, K fixed (7-23), d=0.25",
        "swap_mapping": bool(swap_choice),
        "time_shift_s": best_shift,
        "Iz_eff_kgm2": Iz,
        "Nr_Nms_per_rad": Nr,
        "Nrr_Nms2_per_rad2": Nrr,
        "regression_r2": r2,
        "n_samples": int(len(y)),
        "steady_r_at_full_diff_degps": float(np.degrees(6.25 / Nr)),
        "shooting_median_rmse_degps": float(np.degrees(med)) if seg_rmses else None,
        "prior_0723": {"Iz_eff": 3.75, "Nr": 4.286144, "Nrr": 0.001},
    }
    with open(os.path.join(OUT_DIR, "yaw_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved yaw_params.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
