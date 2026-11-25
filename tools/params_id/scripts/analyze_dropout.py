#!/usr/bin/env python3
"""Dropout event forensics: left-prop RPM collapse (PWM 1700-1965, RPM<0.6*pred).

Finds all dropout samples/events, extracts +-2 s context (RPM both props, PWM
both channels, ESC current, Err/RawRPM), classifies each event:
  command_dip   : raw RCOU C1 dipped <=1560 us within +-0.3 s (interp artifact)
  esc_err       : ESC.Err != 0 on the left instance during the event
  curr_collapse : left current < 25% of window baseline (motor electrically off)
  curr_spike    : left current > 2x baseline (stall/blocked prop)
  right_anomaly : right RPM collapsed >50% in the same window (common cause)
Outputs: events csv/json + timeline & zoom plots.
"""
import glob
import json
import os
import sys
import numpy as np

PARSED_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT_DIR, exist_ok=True)

A1, A2 = 10.540, -0.009177   # stage-1 left-prop fit (RPM vs x=PWM-1500)


def pred_rpm(pwm):
    x = np.maximum(pwm - 1500.0, 0.0)
    return A1 * x + A2 * x ** 2


def interp1(t_src, y_src, t_dst):
    g = np.isfinite(t_src) & np.isfinite(y_src)
    t_src, y_src = t_src[g], y_src[g]
    o = np.argsort(t_src)
    return np.interp(t_dst, t_src[o], y_src[o], left=np.nan, right=np.nan)


def load(name_path):
    z = np.load(name_path, allow_pickle=True)
    return {k: z[k] for k in z.files}


def main():
    events = []
    right_events = []
    per_log = {}
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        d = load(f)
        if d.get("ESC.TimeUS") is None:
            continue
        t_esc = d["ESC.TimeUS"]
        inst = d["ESC.Instance"].astype(int)
        rpm = d["ESC.RPM"]
        raw = d.get("ESC.RawRPM", np.full_like(rpm, np.nan))
        err = d.get("ESC.Err", np.zeros_like(rpm))
        curr = d["ESC.Curr"]
        rcou_t = d["RCOU.TimeUS"]
        c1 = d["RCOU.C1"]
        c3 = d["RCOU.C3"]

        res = {}
        for k, ki, chan in (("L", 0, c1), ("R", 2, c3)):
            m = inst == ki
            tk, rk = t_esc[m], rpm[m]
            ck = curr[m]
            ek = err[m]
            rwk = raw[m]
            pk = np.interp(tk, rcou_t, chan, left=np.nan, right=np.nan)
            pk_raw_min = np.minimum.accumulate  # placeholder
            pred = pred_rpm(pk)
            # dropout on forward command 1700..1965
            dm = (pk >= 1700) & (pk <= 1965) & np.isfinite(rk) & (rk > 20) & (rk < 0.6 * pred)
            # group into events: consecutive samples (gap <= 0.25 s)
            idx = np.flatnonzero(dm)
            if len(idx) == 0:
                res[k] = []
                continue
            groups = np.split(idx, np.where(np.diff(idx) > int(0.25 / 0.0137))[0] + 1)
            evs = []
            for gp in groups:
                if len(gp) < 1:
                    continue
                i0, i1 = gp[0], gp[-1]
                w = (tk >= tk[i0] - 2e6) & (tk <= tk[i1] + 2e6)
                # raw RCOU command dip check (not interpolated): +-0.3 s around event
                cw = (rcou_t >= tk[i0] - 0.3e6) & (rcou_t <= tk[i1] + 0.3e6)
                cmd_min = float(np.min(chan[cw])) if cw.any() else np.nan
                base_curr = np.nanmedian(ck[w & ~dm]) if (w & ~dm).sum() else np.nan
                ev_curr = ck[gp]
                ev = {
                    "log": name[-9:], "t_start_us": float(tk[i0]), "t_end_us": float(tk[i1]),
                    "dur_s": float((tk[i1] - tk[i0]) / 1e6 + 0.0137),
                    "n_samp": int(len(gp)),
                    "pwm_min": float(np.min(pk[gp])), "pwm_max": float(np.max(pk[gp])),
                    "rpm_min": float(np.min(rk[gp])), "rpm_mean": float(np.mean(rk[gp])),
                    "raw_rpm_mean": float(np.nanmean(rwk[gp])),
                    "err_any": int(np.nansum(ek[gp] != 0)),
                    "cmd_min_0p3s": cmd_min,
                    "curr_mean": float(np.nanmean(ev_curr)),
                    "curr_base": float(base_curr) if np.isfinite(base_curr) else None,
                    "ctx": (tk[gp][0], tk[gp][-1], w),
                    "idx_all": gp, "mask_w": w,
                }
                # classification (NED throttle semantics: <=1560 means command
                # dipped toward neutral/reverse -> prop slowdown is CORRECT response)
                cls = []
                if np.isfinite(cmd_min):
                    if cmd_min <= 1450:
                        cls.append("reverse_pulse")
                    elif cmd_min <= 1620:
                        cls.append("neutral_dip")
                    else:
                        cls.append("no_command_dip")
                else:
                    cls.append("no_command_dip")
                if ev["err_any"] > 0:
                    cls.append("esc_err")
                bc = ev["curr_base"]
                if bc and bc > 1 and ev["curr_mean"] < 0.25 * bc:
                    cls.append("curr_collapse")
                if bc and bc > 1 and ev["curr_mean"] > 2.0 * bc:
                    cls.append("curr_spike")
                ev["class"] = cls
                evs.append(ev)
            res[k] = evs
        per_log[name] = res
        L = res.get("L", [])
        R = res.get("R", [])
        for ev in L:
            events.append(ev)
        for ev in R:
            right_events.append(ev)

    print(f"left dropout events: {len(events)}, right: {len(right_events)}")
    tot_samples = sum(e["n_samp"] for e in events)
    tot_dur = sum(e["dur_s"] for e in events)
    print(f"left total: {tot_samples} samples, {tot_dur:.1f} s")
    cls_count = {}
    for e in events:
        for c in e["class"]:
            cls_count[c] = cls_count.get(c, 0) + 1
    no_class = sum(1 for e in events if not e["class"])
    print("classification:", cls_count, "unclassified:", no_class)
    for e in sorted(events, key=lambda x: x["t_start_us"]):
        print(f"  {e['log']} pwm[{e['pwm_min']:.0f}-{e['pwm_max']:.0f}] "
              f"dur={e['dur_s']:.2f}s rpm~{e['rpm_mean']:.0f} raw~{e['raw_rpm_mean']:.0f} "
              f"curr={e['curr_mean']:.1f}A(base {e['curr_base']}) cmd_min={e['cmd_min_0p3s']:.0f} "
              f"err={e['err_any']} class={e['class']}")

    # right anomaly cross-check: right rpm drop during left events
    n_right_anom = 0
    for f in sorted(glob.glob(os.path.join(PARSED_DIR, "*.npz"))):
        name = os.path.basename(f).replace(".npz", "")
        d = load(f)
        t_esc = d["ESC.TimeUS"]
        inst = d["ESC.Instance"].astype(int)
        rpm = d["ESC.RPM"]
        m2 = inst == 2
        tk2, rk2 = t_esc[m2], rpm[m2]
        for e in [e for e in events if e["log"] == name[-9:]]:
            w = (tk2 >= e["t_start_us"] - 1e6) & (tk2 <= e["t_end_us"] + 1e6)
            if w.sum() < 10:
                continue
            base_r = np.nanmedian(rk2[w])
            ev_w = (tk2 >= e["t_start_us"]) & (tk2 <= e["t_end_us"])
            if ev_w.any():
                ev_r = np.nanmedian(rk2[ev_w])
                if ev_r < 0.6 * base_r:
                    n_right_anom += 1
    print(f"events with simultaneous right-prop collapse: {n_right_anom}/{len(events)}")

    # ---- save json/csv ----
    slim = []
    for e in events:
        slim.append({k: v for k, v in e.items() if k not in ("ctx", "idx_all", "mask_w")})
    with open(os.path.join(OUT_DIR, "dropout_events.json"), "w") as f:
        json.dump({"left_events": slim, "n_right_anom": n_right_anom,
                   "class_counts": cls_count}, f, indent=2, ensure_ascii=False)
    try:
        import csv
        with open(os.path.join(OUT_DIR, "dropout_events.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(slim[0].keys()))
            w.writeheader()
            for e in slim:
                w.writerow(e)
    except Exception as e:
        print("csv skipped:", e)

    # ---- plots ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # timeline strip: one panel per log, y clipped to 6 kRPM (spike-proof)
    log_names = sorted({e["log"] for e in events})
    fig, axs = plt.subplots(len(log_names), 1,
                            figsize=(12, 2.8 * len(log_names)), dpi=130)
    axs = np.atleast_1d(axs)
    for ax, nm in zip(axs, log_names):
        d = load(os.path.join(PARSED_DIR, [f for f in os.listdir(PARSED_DIR)
                                           if f.endswith(nm + ".npz")][0]))
        t_esc = d["ESC.TimeUS"]
        m = (d["ESC.Instance"].astype(int) == 0) & (d["ESC.RPM"] > 100)
        tt = (t_esc[m] - t_esc[m][0]) / 1e6
        rr = d["ESC.RPM"][m] / 1000.0
        keep = rr <= 6.0
        ax.plot(tt[keep], rr[keep], color="0.75", lw=0.5, zorder=1)
        for e in [e for e in events if e["log"] == nm]:
            t0 = (e["t_start_us"] - t_esc[m][0]) / 1e6
            ax.axvspan(t0, t0 + e["dur_s"], color="red", alpha=0.6, zorder=2)
        ax.set_ylim(0, 6)
        ax.set_ylabel(f"{nm}\nRPM k", fontsize=8)
        ax.grid(alpha=0.2)
    axs[-1].set_xlabel("time within each log (s)")
    ax.set_title(f"Left-prop dropout events (red): {len(events)} events, {tot_dur:.1f}s total",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "dropout_timeline.png"))
    plt.close(fig)

    # zoomed windows: pick up to 4 largest events
    big = sorted(events, key=lambda e: -e["dur_s"])[:4]
    fig, axs = plt.subplots(len(big), 1, figsize=(12, 3.2 * len(big)), dpi=130)
    axs = np.atleast_1d(axs)
    for ax, e in zip(axs, big):
        d = load(os.path.join(PARSED_DIR,
                 [f for f in os.listdir(PARSED_DIR) if f.endswith(e["log"] + ".npz")][0]))
        t_esc = d["ESC.TimeUS"]
        inst = d["ESC.Instance"].astype(int)
        w = (t_esc >= e["t_start_us"] - 2e6) & (t_esc <= e["t_end_us"] + 2e6)
        tt = (t_esc[w] - t_esc[w][0]) / 1e6
        m0 = inst == 0
        m2 = inst == 2
        nl = interp1(t_esc[m0], d["ESC.RPM"][m0], t_esc[w])
        nr = interp1(t_esc[m2], d["ESC.RPM"][m2], t_esc[w])
        rcou_t = d["RCOU.TimeUS"]
        p1 = interp1(rcou_t, d["RCOU.C1"], t_esc[w])
        p3 = interp1(rcou_t, d["RCOU.C3"], t_esc[w])
        cu0 = interp1(t_esc[m0], d["ESC.Curr"][m0], t_esc[w])
        cu2 = interp1(t_esc[m2], d["ESC.Curr"][m2], t_esc[w])
        ax.plot(tt, nl, label="nL RPM", color="tab:blue")
        ax.plot(tt, nr, label="nR RPM", color="tab:red")
        ax.plot(tt, p1 * 2, label="C1 PWM x2", color="tab:cyan", lw=0.9)
        ax.plot(tt, p3 * 2, label="C3 PWM x2", color="tab:green", lw=0.9)
        ax.set_title(f"{e['log']} pwm[{e['pwm_min']:.0f}-{e['pwm_max']:.0f}] "
                     f"dur={e['dur_s']:.2f}s class={e['class']}")
        ax.set_ylabel("RPM / PWMx2")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", fontsize=7, ncol=2)
        ax3 = ax.twinx()
        ax3.plot(tt, cu0, color="tab:purple", lw=0.8, label="currL A")
        ax3.plot(tt, cu2, color="tab:pink", lw=0.8, label="currR A")
        ax3.set_ylabel("ESC current (A)")
        ax3.legend(loc="lower right", fontsize=7)
    axs[-1].set_xlabel("t (s)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "dropout_zoom.png"))
    plt.close(fig)
    print(f"saved dropout_events.json/csv + plots in {OUT_DIR}")


if __name__ == "__main__":
    main()
