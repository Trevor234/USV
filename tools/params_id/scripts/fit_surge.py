#!/usr/bin/env python3
"""Stage-2 surge identification: m_tot*u_dot = K*(nL^2+nR^2) + Xu*u + Xuu*u^2.

Mass anchor m_tot = 14.2 kg (authoritative 7-23 spec) -> absolute (K, Xu, Xuu).
u from EKF velocity projected on heading; u_dot from smoothed derivative
(avoids IMU gravity leak from boat pitch). Steady segments become validation.
Outputs: surge_params.json, plots, sprint open-loop replay.
"""
import glob
import json
import os
import sys
import numpy as np

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

MASS = 14.2          # kg, authoritative anchor
DT_GRID = 0.05       # 20 Hz working grid
RPM_MAX_SANE = 8000.0
U_MIN = 0.3
DYN_THRESH = 0.12    # |u_dot| for dynamic samples
STEADY_THRESH = 0.04


def interp1(t_src, y_src, t_dst):
    t_src = np.asarray(t_src, float)
    y_src = np.asarray(y_src, float)
    good = np.isfinite(t_src) & np.isfinite(y_src)
    t_src, y_src = t_src[good], y_src[good]
    order = np.argsort(t_src)
    return np.interp(t_dst, t_src[order], y_src[order], left=np.nan, right=np.nan)


def moving_avg(x, n):
    if n < 2:
        return x.copy()
    kernel = np.ones(n) / n
    return np.convolve(x, kernel, mode="same")


def load_log(path):
    z = np.load(path, allow_pickle=True)
    return {k: z[k] for k in z.files}


def build_grid(d):
    """Build 20Hz aligned arrays for one log. Returns dict or None.

    Surge velocity comes from POS (EKF fused position, single stream) differenced
    in ENU and projected on ATT yaw — immune to EKF-core mixing in XKF1 and to
    IMU gravity leak. Dock/stationary junk self-eliminates (position does not move).
    """
    t_pos = d.get("POS.TimeUS")
    t_att = d.get("ATT.TimeUS")
    esc_t = d.get("ESC.TimeUS")
    if t_pos is None or len(t_pos) < 500 or t_att is None or esc_t is None:
        return None
    lat = np.radians(d["POS.Lat"])
    lon = np.radians(d["POS.Lng"])
    R = 6378137.0
    lat0, lon0 = lat[0], lon[0]
    dn = R * (lat - lat0)
    de = R * (lon - lon0) * np.cos(lat0)
    t_s = t_pos / 1e6
    vn = np.gradient(dn, t_s)
    ve = np.gradient(de, t_s)
    vn = moving_avg(np.nan_to_num(vn, nan=0.0), 5)
    ve = moving_avg(np.nan_to_num(ve, nan=0.0), 5)
    v_mag = np.hypot(vn, ve)

    yaw = np.unwrap(np.radians(d["ATT.Yaw"]))
    yaw_g = interp1(t_att, yaw, t_pos)   # heading on POS timebase

    # ESC RPM per instance (0=left C1, 2=right C3)
    inst = d["ESC.Instance"].astype(int)
    rpm = d["ESC.RPM"]
    rpm_sane = (rpm > 30) & (rpm < RPM_MAX_SANE)
    nl_tr = esc_t[(inst == 0) & rpm_sane]
    nl = rpm[(inst == 0) & rpm_sane]
    nr_tr = esc_t[(inst == 2) & rpm_sane]
    nr = rpm[(inst == 2) & rpm_sane]
    if len(nl_tr) < 100 or len(nr_tr) < 100:
        return None

    # uniform 20 Hz grid over POS span
    t0, t1 = t_pos[0], t_pos[-1]
    tg = np.arange(t0, t1, DT_GRID * 1e6)
    vng = interp1(t_pos, vn, tg)
    veg = interp1(t_pos, ve, tg)
    # sanitize: kill position-jump velocity spikes, refill by interpolation
    bad = (np.abs(vng) > 4.5) | (np.abs(veg) > 4.5)
    vng[bad] = np.nan
    veg[bad] = np.nan
    vng = interp1(tg[np.isfinite(vng)], vng[np.isfinite(vng)], tg)
    veg = interp1(tg[np.isfinite(veg)], veg[np.isfinite(veg)], tg)
    psi = interp1(t_att, yaw, tg)
    ug = vng * np.cos(psi) + veg * np.sin(psi)
    us = moving_avg(ug, 9)                        # 0.45 s smoothing
    u_dot = np.gradient(us, DT_GRID)
    nl_g = interp1(nl_tr, nl, tg)
    nr_g = interp1(nr_tr, nr, tg)
    S = nl_g ** 2 + nr_g ** 2
    r_g = np.gradient(psi, DT_GRID)

    # pitch-corrected body-x accel as primary u_dot:
    # f_x = u_dot + g*sin(pitch) (NED, nose-up positive) -> u_dot = AccX - g*sin(pitch)
    acc_corr = None
    if (d.get("IMU.TimeUS") is not None and len(d["IMU.TimeUS"]) > 100
            and d.get("ATT.Pitch") is not None and len(d["ATT.Pitch"]) > 100):
        ax = interp1(d["IMU.TimeUS"], d["IMU.AccX"], tg)
        pitch = interp1(t_att, np.radians(d["ATT.Pitch"]), tg)
        acc_corr = moving_avg(ax - 9.81 * np.sin(pitch), 30)

    return {"t": tg, "u": us, "u_raw": ug, "u_dot": u_dot, "S": S,
            "nl": nl_g, "nr": nr_g, "r": r_g, "accx": acc_corr,
            "v_mag": interp1(t_pos, v_mag, tg)}


def main():
    logs = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        g = build_grid(load_log(f))
        if g is not None:
            logs[name] = g
            print(f"{name}: grid {len(g['t'])} samples, u_max={np.nanmax(g['u']):.2f}, "
                  f"gs_max={np.nanmax(g['v_mag']):.2f}")
    if not logs:
        print("no usable logs")
        return

    # ---- pooled regression sets (u_dot from pitch-corrected IMU accel) ----
    dyn_A, dyn_y, dyn_tag = [], [], []
    ste_u, ste_S, ste_tag = [], [], []
    accx_check = []
    for name, g in logs.items():
        if g["accx"] is None:
            continue
        base = (np.isfinite(g["u"]) & np.isfinite(g["S"]) & np.isfinite(g["accx"])
                & (g["u"] > U_MIN) & (g["S"] > 1e6) & (np.abs(g["r"]) < 0.3)
                & (g["v_mag"] < 4.5) & (g["v_mag"] > 0.2))
        dyn = base & (np.abs(g["accx"]) > DYN_THRESH)
        ste = base & (np.abs(g["accx"]) < STEADY_THRESH)
        S_d = g["S"][dyn]
        A = np.column_stack([S_d, g["u"][dyn], g["u"][dyn] ** 2])
        y = MASS * g["accx"][dyn]
        dyn_A.append(A)
        dyn_y.append(y)
        dyn_tag += [name] * len(y)
        ste_u.append(g["u"][ste])
        ste_S.append(g["S"][ste])
        ste_tag += [name] * int(ste.sum())
        m_x = dyn & np.isfinite(g["u_dot"])
        if m_x.sum() > 50:
            c = np.corrcoef(g["accx"][m_x], g["u_dot"][m_x])[0, 1]
            accx_check.append((g["accx"][m_x], g["u_dot"][m_x], name, c))
    A = np.vstack(dyn_A)
    y = np.concatenate(dyn_y)
    coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
    K, Xu, Xuu = coef
    pred = A @ coef
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot
    print(f"\nsurge regression (n={len(y)} dyn samples):")
    print(f"  K   = {K:.4e} N/RPM^2  -> T_max @ n_max")
    print(f"  Xu  = {Xu:.4f} N/(m/s)   (prior -2.2721)")
    print(f"  Xuu = {Xuu:.4f} N/(m/s)^2 (prior -11.5718)")
    print(f"  R2  = {r2:.4f}")
    for a, yy, name, c in accx_check[:6]:
        print(f"  acc_corr vs du/dt(pos) {name}: corr={c:.3f} (n={len(a)})")

    # accel sanity: sign + magnitude of K
    n_max = max(np.nanmax(g["S"]) ** 0.5 for g in logs.values())
    T_max = K * n_max ** 2
    print(f"  n_max(clean) = {n_max:.0f} RPM -> T_max = {T_max:.1f} N (prior assumed 25 N)")

    # ---- steady validation: predict equilibrium speed from S ----
    ste_u = np.concatenate(ste_u)
    ste_S = np.concatenate(ste_S)
    u_eq = np.full(len(ste_S), np.nan)
    if 4 * Xuu * K * 1 > 0 or True:
        disc = Xu ** 2 - 4 * Xuu * K * ste_S
        ok = disc >= 0
        # 0 = K*S + Xu*u + Xuu*u^2 -> positive root
        u_eq[ok] = (-Xu - np.sqrt(disc[ok])) / (2 * Xuu)
    vok = ok & np.isfinite(ste_u) & (u_eq > 0.2) & (u_eq < 5)
    err = ste_u[vok] - u_eq[vok]
    print(f"\nsteady validation (n={vok.sum()}): mean err={np.mean(err):+.3f} m/s, "
          f"RMSE={np.sqrt(np.mean(err**2)):.3f} m/s, median |err|={np.median(np.abs(err)):.3f}")

    # ---- sprint open-loop replay (largest accel event in any log) ----
    best = None
    for name, g in logs.items():
        if g["accx"] is None:
            continue
        base = (np.isfinite(g["u"]) & np.isfinite(g["S"]) & np.isfinite(g["accx"])
                & (np.abs(g["r"]) < 0.3) & (g["v_mag"] < 4.5) & (g["v_mag"] > 0.2))
        acc_mask = base & (g["accx"] > 0.15) & (g["u"] > 0.3)
        # longest run of consecutive True
        idx = np.flatnonzero(acc_mask)
        if len(idx) == 0:
            continue
        splits = np.split(idx, np.where(np.diff(idx) > 5)[0] + 1)
        for seg in splits:
            if len(seg) < 100:
                continue
            du = g["u"][seg[-1]] - g["u"][seg[0]]
            if best is None or du > best["du"]:
                best = {"name": name, "seg": seg, "du": float(du)}
    if best is not None:
        name, seg = best["name"], best["seg"]
        g = logs[name]
        i0, i1 = seg[0], seg[-1]
        # simulate from measured u0 with measured S(t)
        t_seg = g["t"][i0:i1 + 1]
        S_seg = g["S"][i0:i1 + 1]
        u_sim = np.zeros(len(t_seg))
        u_sim[0] = g["u"][i0]
        for j in range(1, len(t_seg)):
            k1 = (K * S_seg[j - 1] + Xu * u_sim[j - 1] + Xuu * u_sim[j - 1] ** 2) / MASS
            k2 = (K * 0.5 * (S_seg[j - 1] + S_seg[j]) + Xu * (u_sim[j - 1] + 0.5 * DT_GRID * k1)
                  + Xuu * (u_sim[j - 1] + 0.5 * DT_GRID * k1) ** 2) / MASS
            u_sim[j] = u_sim[j - 1] + DT_GRID * k2
        meas = g["u"][i0:i1 + 1]
        rmse = np.sqrt(np.mean((u_sim - meas) ** 2))
        dur = (t_seg[-1] - t_seg[0]) / 1e6
        print(f"\nsprint replay {name}: {dur:.1f}s, u {meas[0]:.2f}->{meas[-1]:.2f} m/s, "
              f"sim end {u_sim[-1]:.2f}, RMSE={rmse:.3f} m/s")

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axs = plt.subplots(2, 1, figsize=(11, 8), dpi=130, sharex=True)
        tt = (t_seg - t_seg[0]) / 1e6
        axs[0].plot(tt, meas, label="measured u (EKF)")
        axs[0].plot(tt, u_sim, "--", label="open-loop sim (identified params)")
        axs[0].set_ylabel("u (m/s)")
        axs[0].legend()
        axs[0].grid(alpha=0.3)
        axs[0].set_title(f"Sprint open-loop replay: {name}")
        axs[1].plot(tt, np.sqrt(S_seg) / 60, color="tab:red")
        axs[1].set_ylabel("mean prop speed (kRPM)")
        axs[1].set_xlabel("time (s)")
        axs[1].grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "surge_sprint_replay.png"))
        plt.close(fig)
        p_replay = "surge_sprint_replay.png"
    else:
        p_replay, rmse, dur = None, None, None

    # steady curve plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=130)
    ax.scatter(np.sqrt(ste_S[vok]) / 60, ste_u[vok], s=2, alpha=0.15, label="measured steady points")
    nn = np.linspace(1000, n_max, 100)
    S_nn = (nn * 60) ** 2
    disc = Xu ** 2 - 4 * Xuu * K * S_nn
    okp = disc >= 0
    u_pred = (-Xu - np.sqrt(disc[okp])) / (2 * Xuu)
    ax.plot(nn[okp], u_pred, "r-", lw=2, label="equilibrium u (identified params)")
    ax.set_xlabel("mean prop speed (kRPM)")
    ax.set_ylabel("steady surge speed u (m/s)")
    ax.set_title(f"Steady-state thrust balance  (K={K:.3e}, Xu={Xu:.3f}, Xuu={Xuu:.3f})")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "surge_steady_curve.png"))
    plt.close(fig)

    out = {
        "mass_anchor_kg": MASS,
        "K_N_per_rpm2": K,
        "Xu_N_per_mps": Xu,
        "Xuu_N_per_mps2": Xuu,
        "r2_dynamic": r2,
        "n_dyn_samples": int(len(y)),
        "n_max_rpm_clean": float(n_max),
        "T_max_N_at_n_max": float(T_max),
        "steady_validation": {"n": int(vok.sum()), "mean_err": float(np.mean(err)),
                              "rmse": float(np.sqrt(np.mean(err ** 2))),
                              "median_abs_err": float(np.median(np.abs(err)))},
        "sprint_replay": {"log": best["name"] if best else None,
                          "duration_s": dur, "rmse_mps": rmse},
        "prior_0723": {"Xu": -2.272063, "Xuu": -11.571784, "assumed_K_T_N": 25.0},
    }
    with open(os.path.join(OUT_DIR, "surge_params.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved surge_params.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
