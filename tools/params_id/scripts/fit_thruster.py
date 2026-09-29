#!/usr/bin/env python3
"""Stage-1 thruster model identification from parsed DataFlash npz files.

- Split ESC telemetry per Instance (dynamic); map instance -> RCOU channel
  (C1=left, C3=right) by correlation of step responses.
- Quasi-steady filter, per-prop PWM->RPM fit (deadband + quadratic).
- Left/right asymmetry quantification (DeltaRPM vs PWM bins + gain ratio CI).
- Outputs: thruster_model.json, plots PNG.
"""
import glob
import json
import os
import sys
import numpy as np

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

PWM_CENTER = 1500.0
RPM_MAX_SANE = 8000.0
RPM_MIN_FWD = 200.0


def interp1(t_src, y_src, t_dst):
    t_src = np.asarray(t_src, float)
    y_src = np.asarray(y_src, float)
    good = np.isfinite(t_src) & np.isfinite(y_src)
    t_src, y_src = t_src[good], y_src[good]
    order = np.argsort(t_src)
    return np.interp(t_dst, t_src[order], y_src[order], left=np.nan, right=np.nan)


def quasi_steady_mask(t, rpm, half=25, thresh=80.0):
    """Points whose RPM is nearly constant within +-half samples (~0.35s @73Hz)."""
    ok = np.zeros(len(t), bool)
    n = len(t)
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        if np.nanmax(rpm[lo:hi]) - np.nanmin(rpm[lo:hi]) < thresh:
            ok[i] = True
    return ok


def fit_deadband_quad(pwm, rpm, pwm_lo=1510.0, pwm_hi=1965.0, robust=True):
    """RPM = a1*x + a2*x^2, x = PWM-1500-db; grid-search db. Excludes the PWM~2000
    saturation band (RPM there is load-dependent). Iterative 3-sigma rejection."""
    base = (pwm >= pwm_lo) & (pwm <= pwm_hi)
    best = None
    for db in np.arange(0, 61, 5):
        x_all = pwm - PWM_CENTER - db
        m = base & (x_all > 0)
        if m.sum() < 30:
            continue
        x, y = x_all[m], rpm[m]
        keep = np.ones(len(x), bool)
        for _ in range(3 if robust else 1):
            A = np.column_stack([x[keep], x[keep] ** 2])
            coef, *_ = np.linalg.lstsq(A, y[keep], rcond=None)
            pred_all = x * coef[0] + x ** 2 * coef[1]
            res = y - pred_all
            sig = np.std(res[keep])
            new_keep = np.abs(res) < 3 * sig
            if new_keep.sum() < 30 or np.array_equal(new_keep, keep):
                keep = new_keep
                break
            keep = new_keep
        ss_res = np.sum((y[keep] - (x[keep] * coef[0] + x[keep] ** 2 * coef[1])) ** 2)
        ss_tot = np.sum((y[keep] - np.mean(y[keep])) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        if best is None or r2 > best["r2"]:
            best = {"db": float(db), "a1": float(coef[0]), "a2": float(coef[1]),
                    "r2": float(r2), "n": int(keep.sum()),
                    "n_rejected": int(len(x) - keep.sum()),
                    "rej_frac": float(1 - keep.sum() / len(x))}
    return best


def main():
    data = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        z = np.load(f, allow_pickle=True)
        data[name] = {k: z[k] for k in z.files}
    print(f"loaded {len(data)} parsed logs")

    acc = {}
    chan_corr = {}
    for name, d in data.items():
        esc_t = d.get("ESC.TimeUS")
        rcou_t = d.get("RCOU.TimeUS")
        if esc_t is None or len(esc_t) == 0 or rcou_t is None or len(rcou_t) == 0:
            continue
        c1 = interp1(rcou_t, d.get("RCOU.C1", []), esc_t)
        c3 = interp1(rcou_t, d.get("RCOU.C3", []), esc_t)
        inst = d["ESC.Instance"].astype(int)
        rpm = d["ESC.RPM"]
        for k in sorted(set(inst.tolist())):
            m = inst == k
            tk, rk = esc_t[m], rpm[m]
            r1 = interp1(esc_t, c1, tk)
            r3 = interp1(esc_t, c3, tk)
            g = np.isfinite(r1) & np.isfinite(r3) & np.isfinite(rk)
            if g.sum() < 100:
                continue
            dr, d1, d3 = np.diff(rk[g]), np.diff(r1[g]), np.diff(r3[g])
            s1 = np.std(d1)
            s3 = np.std(d3)
            c1c = np.corrcoef(dr, d1)[0, 1] if s1 > 0 else 0.0
            c3c = np.corrcoef(dr, d3)[0, 1] if s3 > 0 else 0.0
            chan_corr.setdefault(k, []).append((name, float(c1c), float(c3c)))
            # ArduPilot: ESC Instance == SERVOx channel - 1 (SERVO1=left C1, SERVO3=right C3)
            pwm_k = r1[g] if k == 0 else r3[g]
            # sanity + per-log quasi-steady + forward filter
            sane = (rk[g] > 30) & (rk[g] < RPM_MAX_SANE)
            st = quasi_steady_mask(tk[g][sane], rk[g][sane])
            base = tk[g][sane]
            pwm_k = pwm_k[sane][st]
            rk_s = rk[g][sane][st]
            sel = (pwm_k >= PWM_CENTER) & (pwm_k < 2010) & (rk_s > RPM_MIN_FWD * 0.4)
            a = acc.setdefault(k, {"pwm": [], "rpm": []})
            a["pwm"].append(pwm_k[sel])
            a["rpm"].append(rk_s[sel])
    for k in acc:
        acc[k]["pwm"] = np.concatenate(acc[k]["pwm"])
        acc[k]["rpm"] = np.concatenate(acc[k]["rpm"])
    print("instance->channel correlation (first entries):")
    for k in sorted(chan_corr):
        for name, c1c, c3c in chan_corr[k][:3]:
            print(f"  inst{k} {name}: corr(C1)={c1c:.3f} corr(C3)={c3c:.3f}")

    keys = sorted(acc)
    if len(keys) != 2:
        print(f"WARN: expected 2 thruster instances, got {keys}")

    # ---- per-prop fit + dropout diagnostics ----
    fits = {}
    dropout = {}
    for k in keys:
        pwm, rpm = acc[k]["pwm"], acc[k]["rpm"]
        fit = fit_deadband_quad(pwm, rpm)
        fits[k] = fit
        acc[k]["fit"] = fit
        acc[k]["pwm_f"] = pwm
        acc[k]["rpm_f"] = rpm
        x400 = 400.0
        eff = fit["a1"] * x400 + fit["a2"] * x400 ** 2
        acc[k]["eff400"] = eff
        # dropout candidates: command well above idle but RPM far below prediction
        pred = np.where(pwm - PWM_CENTER - fit["db"] > 0,
                        fit["a1"] * (pwm - PWM_CENTER - fit["db"])
                        + fit["a2"] * (pwm - PWM_CENTER - fit["db"]) ** 2,
                        np.nan)
        dd = (pwm > 1700) & (pwm < 1965) & np.isfinite(pred) & (rpm < 0.6 * pred)
        dropout[k] = {"n": int(dd.sum()), "frac_of_steady": float(dd.sum() / len(pwm)),
                      "rpm_mean": float(np.mean(rpm[dd])) if dd.any() else None,
                      "pwm_mean": float(np.mean(pwm[dd])) if dd.any() else None}
        print(f"inst{k}: n={fit['n']} db={fit['db']}us a1={fit['a1']:.3f} "
              f"a2={fit['a2']:.6f} R2={fit['r2']:.4f} eff@400us={eff:.0f}RPM "
              f"rej={fit['rej_frac']*100:.1f}% dropout_pts={dropout[k]['n']}")

    # ---- asymmetry: same-PWM RPM difference + gain ratio bootstrap CI ----
    pwm_bins = np.arange(1550, 2001, 50)
    asym = []
    if len(keys) == 2:
        kL, kR = keys
        for lo in pwm_bins[:-1]:
            hi = lo + 50
            mL = (acc[kL]["pwm_f"] >= lo) & (acc[kL]["pwm_f"] < hi)
            mR = (acc[kR]["pwm_f"] >= lo) & (acc[kR]["pwm_f"] < hi)
            if mL.sum() > 20 and mR.sum() > 20:
                rL, rR = np.median(acc[kL]["rpm_f"][mL]), np.median(acc[kR]["rpm_f"][mR])
                asym.append({"bin": [int(lo), int(hi)], "rpm_left": float(rL),
                             "rpm_right": float(rR), "delta": float(rR - rL),
                             "pct": float((rR - rL) / rL * 100 if rL else np.nan)})
        ratios = []
        rng = np.random.default_rng(42)
        for _ in range(300):
            coefs = {}
            for k in keys:
                x = acc[k]["pwm_f"] - PWM_CENTER - fits[k]["db"]
                y = acc[k]["rpm_f"]
                idx = rng.integers(0, len(x), len(x))
                x, y = x[idx], y[idx]
                x = x[x > 0]
                if len(x) < 30:
                    continue
                A = np.column_stack([x, x ** 2])
                c, *_ = np.linalg.lstsq(A, y, rcond=None)
                coefs[k] = c[0] * 400 + c[1] * 400 ** 2
            if len(coefs) == 2 and coefs[keys[0]] > 0:
                ratios.append(coefs[keys[1]] / coefs[keys[0]])
        ratio = float(np.median(ratios))
        ci = [float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))]
        print(f"gain ratio inst{keys[1]}/inst{keys[0]} @x=400us: {ratio:.4f} CI95 [{ci[0]:.4f},{ci[1]:.4f}]")
    else:
        ratio, ci = None, None

    # ---- plots ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {keys[0]: "tab:blue", keys[-1]: "tab:red"}
    chan = {}
    for k in keys:
        entries = chan_corr.get(k, [])
        if entries:
            _, c1c, c3c = entries[0]
            chan[k] = "C1/left" if c1c >= c3c else "C3/right"

    fig, ax = plt.subplots(figsize=(11, 7), dpi=130)
    for k in keys:
        ax.scatter(acc[k]["pwm_f"], acc[k]["rpm_f"], s=1.2, alpha=0.15, color=colors[k],
                   label=f"inst{k} ({chan.get(k,'?')}) steady")
        f = acc[k]["fit"]
        x = np.linspace(f["db"] + 1, 500, 100)
        ax.plot(PWM_CENTER + f["db"] + x, f["a1"] * x + f["a2"] * x ** 2, color=colors[k], lw=2,
                label=f"inst{k} fit (db={f['db']:.0f}us R2={f['r2']:.4f})")
    ax.set_xlabel("RCOU PWM (us)")
    ax.set_ylabel("RPM")
    ax.set_title("Per-propeller PWM->RPM quasi-steady fit (2026-09-03, all logs)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "thruster_pwm_rpm_fit.png"))
    plt.close(fig)

    if asym:
        fig, ax = plt.subplots(figsize=(11, 6), dpi=130)
        xs = np.arange(len(asym))
        ax.bar(xs, [a["delta"] for a in asym], color="orange", label="RPM_right-RPM_left (median)")
        ax2 = ax.twinx()
        ax2.plot(xs, [a["pct"] for a in asym], "ro-", label="% difference")
        ax2.set_ylabel("% difference")
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{a['bin'][0]}" for a in asym], rotation=45, ha="right")
        ax.set_xlabel("PWM bin center (us)")
        ax.set_ylabel("RPM difference")
        ax.set_title("Left/right RPM asymmetry vs PWM bin (2026-09-03)")
        ax.legend(loc="upper left")
        ax2.legend(loc="upper right")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "thruster_asymmetry_bins.png"))
        plt.close(fig)

    # ---- outputs ----
    model = {
        "meta": {
            "data": "2026-09-03 5 effective logs",
            "pwm_center_us": PWM_CENTER,
            "note": ("PWM->RPM layer only. Thrust T=K_T*(n/60)^2 identified in stage-2 "
                     "via surge balance. Voltage telemetry absent (ESC.Volt=0)."),
        },
        "instance_channel_map": {str(k): chan.get(k, "?") for k in keys},
        "props": {
            str(k): {
                "deadband_us": fits[k]["db"],
                "a1_rpm_per_us": fits[k]["a1"],
                "a2_rpm_per_us2": fits[k]["a2"],
                "r2": fits[k]["r2"],
                "n_points": fits[k]["n"],
                "rejected_frac": fits[k]["rej_frac"],
                "dropout_candidates": dropout[k],
                "eff_rpm_at_400us": acc[k]["eff400"],
            }
            for k in keys
        },
        "asymmetry_gain_ratio_right_over_left": {"median": ratio, "ci95": ci},
        "asym_bins": asym,
    }
    with open(os.path.join(OUT_DIR, "thruster_model.json"), "w") as f:
        json.dump(model, f, indent=2, ensure_ascii=False)
    print(f"saved thruster_model.json + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
