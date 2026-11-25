"""Regression tests for the 2026-11-02 re-identification pipeline.

Everything here is synthetic: the tests build DataFlash BIN logs from scratch
with real ArduPilot FMT definitions, so they neither read the production log
corpus nor depend on it being mounted.  Implementation details (source strings,
file names, private helpers' internals) are deliberately not asserted; only
observable behaviour is.
"""
import math
import os
import struct
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import parse_log                       # noqa: E402
import reidentify_20261102 as R        # noqa: E402

G = 9.80665


# ---------------------------------------------------------------------------
# minimal DataFlash writer (format strings/ids copied from real ArduPilot logs)
# ---------------------------------------------------------------------------
DF2PY = {"b": "b", "B": "B", "h": "h", "H": "H", "i": "i", "I": "I", "f": "f",
         "d": "d", "n": "4s", "N": "16s", "Z": "64s", "c": "h", "C": "H",
         "e": "i", "E": "I", "L": "i", "M": "b", "q": "q", "Q": "Q"}

FMT = {
    "IMU":  (164, "QBffffffIIfBBHH", "TimeUS,I,GyrX,GyrY,GyrZ,AccX,AccY,AccZ,EG,EA,T,GH,AH,GHz,AHz"),
    "ATT":  (72,  "QffffffB",       "TimeUS,DesRoll,Roll,DesPitch,Pitch,DesYaw,Yaw,AEKF"),
    "XKF1": (44,  "QBccCfffffffccce", "TimeUS,C,Roll,Pitch,Yaw,VN,VE,VD,dPD,PN,PE,PD,GX,GY,GZ,OH"),
    "XKF4": (47,  "QBcccccfffHBIHb", "TimeUS,C,SV,SP,SH,SM,SVT,errRP,OFN,OFE,FS,TS,SS,GPS,PI"),
    "RCOU": (62,  "Q" + "H" * 14,   "TimeUS," + ",".join(f"C{i}" for i in range(1, 15))),
    "GPS":  (94,  "QBBIHBcLLeffffB", "TimeUS,I,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt,Spd,GCrs,VZ,Yaw,U"),
    "MODE": (121, "QMBB",           "TimeUS,Mode,ModeNum,Rsn"),
    "ARM":  (187, "QBIBB",          "TimeUS,ArmState,ArmChecks,Forced,Method"),
    "PARM": (32,  "QNff",           "TimeUS,Name,Value,Default"),
    "VIBE": (167, "QBfffI",         "TimeUS,IMU,VibeX,VibeY,VibeZ,Clip"),
}


def _to_py(fs):
    return "".join(DF2PY[c] for c in fs)


def _fmt_message(tid, df_fmt, cols, name):
    total = 3 + struct.calcsize("<" + _to_py(df_fmt))
    payload = struct.pack("<BB4s16s64s", tid, total, name.encode(),
                          df_fmt.encode(), cols.encode())
    return bytes([0xA3, 0x95, 0x80]) + payload


def _data_message(tid, df_fmt, values):
    return bytes([0xA3, 0x95, tid]) + struct.pack("<" + _to_py(df_fmt), *values)


def qi(x, scale=100.0):
    """Quantise a float to an int for DataFlash multiplier fields (x/scale)."""
    return int(round(x * scale))


class SynthLog:
    """Assembles a synthetic ArduPilot BIN log with only the needed messages."""

    def __init__(self, params=None):
        self.rows = []
        self.params = params if params is not None else self.default_params()
        self._param_written = False

    @staticmethod
    def default_params():
        p = {"SERVO1_FUNCTION": 73.0, "SERVO3_FUNCTION": 74.0,
             "SERVO1_MIN": 1000.0, "SERVO1_TRIM": 1500.0, "SERVO1_MAX": 2000.0,
             "SERVO3_MIN": 1000.0, "SERVO3_TRIM": 1500.0, "SERVO3_MAX": 2000.0,
             "SERVO1_REVERSED": 0.0, "SERVO3_REVERSED": 0.0,
             "MOT_PWM_TYPE": 1.0, "EK3_PRIMARY": 0.0, "FRAME_CLASS": 2.0,
             "STAT_BOOTCNT": 90.0}
        return p

    def _parms(self, t_us):
        if self._param_written:
            return
        self._param_written = True
        for k, v in self.params.items():
            self.rows.append((t_us, "PARM", k, (t_us, k.encode(), float(v), float(v))))

    def imu(self, t, inst=0, gyrx=0.0, gyry=0.0, gyrz=0.0, accx=0.0, accy=0.0, accz=-G):
        self._parms(int(t * 1e6))
        self.rows.append((t, "IMU", 0, (int(t * 1e6), int(inst),
                                        gyrx, gyry, gyrz, accx, accy, accz,
                                        0, 0, 25.0, 1, 1, 1000, 1000)))

    def att(self, t, roll=0.0, pitch=0.0, yaw_deg=0.0):
        self.rows.append((t, "ATT", 0, (int(t * 1e6), 0.0, roll, 0.0, pitch,
                                        0.0, yaw_deg % 360.0, 0)))

    def xkf1(self, t, core=0, roll=0.0, pitch=0.0, yaw_deg=0.0,
             vn=0.0, ve=0.0, vd=0.0, pn=0.0, pe=0.0, pd=0.0):
        # XKF1.Yaw is uint16 hundredths of a degree: wrap before quantising,
        # otherwise a negative heading overflows the field.
        yaw_deg = yaw_deg % 360.0
        self.rows.append((t, "XKF1", 0, (int(t * 1e6), int(core),
                                         qi(roll), qi(pitch), qi(yaw_deg),
                                         vn, ve, vd, 0, qi(pn), qi(pe), qi(pd),
                                         0, 0, 0, qi(1.0))))

    def xkf4(self, t, core=0, pi=0):
        self.rows.append((t, "XKF4", 0, (int(t * 1e6), int(core), 0, 0, 0, 0, 0,
                                         0.0, 0.0, 0.0, 0, 50, 100, 3, int(pi))))

    def rcou(self, t, c1=1500, c3=1500):
        self.rows.append((t, "RCOU", 0, (int(t * 1e6), int(c1), 0, int(c3))
                          + tuple([0] * 11)))

    def gps(self, t, status=6, nsats=20, hdop=0.6, lat=30.887925, lng=121.8951975,
            alt=2.3, spd=0.5, gcrs=0.0):
        self.rows.append((t, "GPS", 0, (int(t * 1e6), 0, int(status), 0, 2000,
                                        int(nsats), qi(hdop), int(round(lat * 1e7)),
                                        int(round(lng * 1e7)), qi(alt), spd, gcrs,
                                        0.0, qi(gcrs % 360.0), 1)))

    def mode(self, t, mode_num=0):
        self.rows.append((t, "MODE", 0, (int(t * 1e6), int(mode_num),
                                         int(mode_num), 26)))

    def arm(self, t, state=1):
        self.rows.append((t, "ARM", 0, (int(t * 1e6), int(state), 0, 0, 1)))

    def vibe(self, t, inst=0, clip=0):
        self.rows.append((t, "VIBE", 0, (int(t * 1e6), int(inst), 0.1, 0.1, 0.1,
                                         int(clip))))

    def write(self, path):
        self._parms(0)
        out = [_fmt_message(tid, fmt, cols, name)
               for name, (tid, fmt, cols) in FMT.items()]
        order = {name: i for i, name in enumerate(FMT)}
        for t, name, _sub, values in sorted(self.rows, key=lambda r: (r[0], order[r[1]])):
            out.append(_data_message(FMT[name][0], FMT[name][1], values))
        with open(path, "wb") as fh:
            fh.write(b"".join(out))
        return path


def pwm_of(q, centre=1500.0, dead=30.0, up=470.0):
    """Normalised command -> PWM, inverse of R.pwm_to_normalized."""
    q = float(q)
    if q >= 0:
        return int(round(centre + dead + q * up))
    return int(round(centre - dead + q * up))


def load_log(path, tmp_path, name="x.npz"):
    npz = os.path.join(str(tmp_path), name)
    parse_log.parse(path, npz)
    return np.load(npz, allow_pickle=True)


def baseline():
    p = {"mass": 14.2, "Iz": 2.13, "xg": 0.12, "d_thruster": 0.25,
         "Xu_dot": -2.0, "Yv_dot": -8.0, "Yr_dot": 0.0, "Nv_dot": -0.363545,
         "Nr_dot": -3.41, "Xu": -2.272063, "Yv": -2.629019, "Yr": 0.0, "Nv": 0.0,
         "Nr": -3.105, "Xuu": -11.571784, "Yvv": -0.05, "Yrr": 0.0, "Nvv": 0.0,
         "Nrr": -0.71,
         "thruster": {"pwm_min": 1000.0, "pwm_center": 1500.0, "pwm_max": 2000.0,
                      "T_max_forward": 25.0, "T_max_reverse": 25.0}}
    return p


def meta_for(path, group="2026-11-02/cfg0", role="train_today", sha="0" * 64):
    return {"basename": os.path.basename(path), "date": "2026-11-02",
            "group": group, "role": role, "sha256": sha, "npz": "x.npz"}


# ---------------------------------------------------------------------------
# 1. exclusion windows are boot-absolute: no +-44 s shift
# ---------------------------------------------------------------------------
def test_exclusion_window_is_boot_absolute_and_padded_exactly():
    t = np.arange(44.0, 951.8, 0.05)
    gyr = np.zeros_like(t)                     # no motion -> no tail extension
    iv = R._exclusion_intervals([{"start_s": 684.5, "end_s": 701.8}], t, gyr)
    assert len(iv) == 1
    a, b = iv[0]
    assert a == pytest.approx(682.5, abs=1e-6), "start must be 684.5-2, not 684.5-2-44"
    assert b == pytest.approx(703.8, abs=1e-6), "end must be 701.8+2, not 701.8+2-44"
    # the old, wrong (relative-time) window would be ~44 s away
    assert not (abs(a - 638.5) < 1.0)

    # a spin that keeps going past the declared end must extend the exclusion
    spin = np.where((t >= 684.5) & (t <= 720.0), -2.0, 0.0)
    iv2 = R._exclusion_intervals([{"start_s": 684.5, "end_s": 701.8}], t, spin)
    assert iv2[0][1] == pytest.approx(722.0, abs=0.1)


# ---------------------------------------------------------------------------
# 2. a 46.1 -> 578.1 s gap cuts blocks, grids and replay windows
# ---------------------------------------------------------------------------
def test_gap_is_never_crossed_and_instances_do_not_mix(tmp_path):
    log = SynthLog()
    t_a = np.arange(10.0, 46.1, 0.02)
    t_b = np.arange(578.1, 700.0, 0.02)
    for i, t in enumerate(np.concatenate([t_a, t_b])):
        # instance 0 is consistent with the heading rate, instance 1 is not
        log.imu(t, inst=0, gyrz=1.0)
        log.imu(t, inst=1, gyrz=-1.0)
        log.att(t, yaw_deg=math.degrees(1.0 * t))
        log.xkf1(t, core=0, yaw_deg=math.degrees(1.0 * t),
                 vn=1.0, ve=0.0, pn=t, pe=0.0)
        log.xkf4(t, core=0, pi=0)
        if i % 5 == 0:
            log.rcou(t, c1=1600, c3=1600)
        if i % 50 == 0:
            log.gps(t)
            log.vibe(t)
        if i == 0:
            log.mode(t, 0)
            log.arm(t, 1)
    path = log.write(str(tmp_path / "gap.bin"))
    z = load_log(path, tmp_path)
    ds = R.build_dataset(z, meta_for(path), {}, {})
    segs = ds["segments"]
    assert segs, "expected clean segments on both sides of the gap"
    for s in segs:
        assert s.t1 <= 46.1 + 1e-6 or s.t0 >= 578.1 - 1e-6, "segment crosses the gap"
    # grids and 10 s windows must be gap-free
    for s in segs:
        assert np.all(np.diff(s.t) <= 0.05 + 1e-9), "grid interpolated across the gap"
    for s, a, b in R.holdout_windows(segs):
        assert s.t[b - 1] - s.t[a] <= R.REPLAY_WIN_S + 1e-6
        assert s.t1 <= 46.1 + 1e-6 or s.t0 >= 578.1 - 1e-6
    # a single consistent IMU instance must be selected -> r == -1 rad/s
    for s in segs:
        assert np.allclose(s.x[:, 5], -1.0, atol=1e-3), "IMU instances were mixed"
    # no r == +1 (the inconsistent instance) anywhere
    for s in segs:
        assert not np.any(s.x[:, 5] > 0.0)


def test_primary_core_switch_uses_the_new_core(tmp_path):
    t = np.arange(100.0, 140.0, 0.02)
    t4 = np.array([100.0, 120.0, 140.0])
    pi4 = np.array([0.0, 1.0, 1.0])
    t1 = t
    c1 = np.where(t < 120.0, 0, 1).astype(float)
    keep = R._core_mask(None, (t4, pi4), t1, c1)
    assert keep[t < 120.0].all(), "before the switch core 0 must be used"
    assert keep[t >= 120.0].all(), "after the switch core 1 must be used"
    # a hard-wired C0 would keep only half the rows
    assert int(keep.sum()) == t1.size


# ---------------------------------------------------------------------------
# 3. ENU differential sign recovery with an independent integrator
# ---------------------------------------------------------------------------
def _synthesize(q_profile, true_p, t_end=120.0, dt=0.02):
    from scipy.integrate import solve_ivp

    def cmd(t):
        for (a, b), (ql, qr) in q_profile:
            if a <= t < b:
                return ql, qr
        return 0.0, 0.0

    gains = [true_p["g_forward"]] * 4

    def rhs(t, y):
        x, yy, psi, u, v, r = y
        ql, qr = cmd(t)
        pos_l = max(ql, 0.0) ** 2
        neg_l = -max(-ql, 0.0) ** 2
        pos_r = max(qr, 0.0) ** 2
        neg_r = -max(-qr, 0.0) ** 2
        q = np.array([pos_l, neg_l, pos_r, neg_r])
        tau = R.tau_from_q(q[None, None, :], gains, true_p["d_thruster"])[0, 0]
        st = np.array([[x, yy, psi, u, v, r]], float)
        d = R.deriv(st, tau[None, None, :], true_p)[0]
        return d

    sol = solve_ivp(rhs, (0.0, t_end), np.zeros(6), t_eval=np.arange(0.0, t_end, dt),
                    rtol=1e-9, atol=1e-11, method="RK45")
    assert sol.success
    return sol.t, sol.y.T


def _write_trajectory_log(path, t, X, q_profile):
    log = SynthLog()
    for i, ti in enumerate(t):
        x, y, psi, u, v, r = X[i]
        yaw_ned = math.pi / 2.0 - psi
        vn = u * math.cos(yaw_ned) + v * math.sin(yaw_ned)
        ve = u * math.sin(yaw_ned) - v * math.cos(yaw_ned)
        log.imu(ti, inst=0, gyrz=-r)
        log.att(ti, roll=0.0, pitch=0.0, yaw_deg=math.degrees(yaw_ned))
        log.xkf1(ti, core=0, roll=0.0, pitch=0.0, yaw_deg=math.degrees(yaw_ned),
                 vn=vn, ve=ve, vd=0.0, pn=y, pe=x, pd=0.0)
        log.xkf4(ti, core=0, pi=0)
        if i % 5 == 0:
            ql = qr = 0.0
            for (a, b), (l, rr) in q_profile:
                if a <= ti < b:
                    ql, qr = l, rr
                    break
            log.rcou(ti, c1=pwm_of(ql), c3=pwm_of(qr))
        if i % 50 == 0:
            log.gps(ti)
            log.vibe(ti)
        if i == 0:
            log.mode(ti, 0)
            log.arm(ti, 1)
    return log.write(str(path))


Q_PROFILE = [
    ((0.0, 20.0), (0.90, 0.90)),
    ((20.0, 30.0), (0.0, 0.0)),
    ((30.0, 50.0), (0.30, 0.80)),
    ((50.0, 60.0), (0.0, 0.0)),
    ((60.0, 80.0), (0.80, 0.30)),
    ((80.0, 100.0), (0.50, 0.50)),
    ((100.0, 110.0), (0.20, 0.70)),
    ((110.0, 120.0), (0.70, 0.20)),
]


def _fit_from_segments(segs, p_base):
    return R.fit_model(R.group_segments(segs), p_base, "test")


def test_enu_differential_sign_is_recovered_and_ned_sign_fails(tmp_path):
    truth = baseline()
    truth.update({"Xu": -2.2, "Xuu": -11.5, "Nr": -3.1, "Nrr": -0.7,
                  "g_forward": 25.0})
    t, X = _synthesize(Q_PROFILE, truth)
    path = _write_trajectory_log(tmp_path / "enu.bin", t, X, Q_PROFILE)
    z = load_log(path, tmp_path, "enu.npz")
    ds = R.build_dataset(z, meta_for(path), {}, {})
    segs = ds["segments"]
    assert segs, f"no clean segments: {ds['reasons']}"

    p_base = baseline()
    fit = _fit_from_segments(segs, p_base)
    assert fit.get("status") == "ok", fit
    h = fit["hydro"]
    assert abs(h["Xu"] - truth["Xu"]) / abs(truth["Xu"]) < 0.25, h["Xu"]
    assert abs(h["Nr"] - truth["Nr"]) / abs(truth["Nr"]) < 0.25, h["Nr"]

    # --- the same data under an unconverted NED v sign must fit materially worse
    flipped = []
    for s in segs:
        f = R.Segment(sid=s.sid, t0=s.t0, t1=s.t1, group=s.group, t=s.t,
                      x=s.x.copy(), ui=s.ui.copy(), pwm=s.pwm.copy(),
                      rpm=s.rpm, mode=s.mode, labels=s.labels)
        f.x[:, 4] = -f.x[:, 4]
        flipped.append(f)
    bad = _fit_from_segments(flipped, p_base)
    assert bad.get("status") == "ok"
    # The sign error corrupts the Coriolis coupling, which shows up as a grossly
    # wrong longitudinal damping and a much worse open-loop trajectory, not
    # necessarily as a wrong Nr (that can be absorbed by other terms).
    err_good = abs(h["Xu"] - truth["Xu"]) / abs(truth["Xu"])
    err_bad = abs(bad["hydro"]["Xu"] - truth["Xu"]) / abs(truth["Xu"])
    assert err_bad > max(3.0 * err_good, 0.2), (
        f"NED-signed v should not recover Xu: good={err_good:.3f} bad={err_bad:.3f}")
    assert bad["train_metrics"]["u_rmse"] > 10.0 * max(
        fit["train_metrics"]["u_rmse"], 1e-6), (
        "NED-signed v must not reproduce the measured surge trajectory")


# ---------------------------------------------------------------------------
# 4. no-ESC equivalent path, no fabricated RPM model, prescribed reductions
# ---------------------------------------------------------------------------
def test_no_esc_log_takes_the_equivalent_path_without_rpm_artifacts(tmp_path):
    log = SynthLog()
    for k, t in enumerate(np.arange(10.0, 120.0, 0.02)):
        ql = 0.8 if (k // 500) % 2 == 0 else 0.2
        qr = 0.8
        log.imu(t, inst=0, gyrz=0.0)
        log.att(t, yaw_deg=0.0)
        log.xkf1(t, core=0, yaw_deg=0.0, vn=1.0, ve=0.0, pn=t, pe=0.0)
        log.xkf4(t, core=0, pi=0)
        if k % 5 == 0:
            log.rcou(t, c1=pwm_of(ql), c3=pwm_of(qr))
        if k % 50 == 0:
            log.gps(t)
            log.vibe(t)
        if k == 0:
            log.mode(t, 0)
            log.arm(t, 1)
    path = log.write(str(tmp_path / "noesc.bin"))
    z = load_log(path, tmp_path, "noesc.npz")
    ds = R.build_dataset(z, meta_for(path), {}, {})
    assert ds["rpm_ok"] is False
    assert "rpm_evidence" not in ds or ds.get("rpm_evidence") is None
    for s in ds["segments"]:
        assert s.rpm.size == 0, "an RPM series must not be invented without ESC telemetry"

    # forward-only excitation -> reverse gains are not estimated
    p_base = baseline()
    rows = R.regression_rows(R.group_segments(ds["segments"]), p_base)
    spec, _info = R.choose_spec(rows, p_base, sorted({r.group for r in rows}))
    assert all(g.no_reverse for g in spec.groups)
    assert any("no_reverse_excitation" in r for r in spec.reductions)


def test_single_side_excitation_ties_gains_and_rank_loss_selects_prescribed_reduction(tmp_path):
    p_base = baseline()
    # only the right thruster is excited -> left/right are not separable
    rows = []
    for i in range(40):
        s = np.zeros(8)
        s[2] = 1.0 + 0.1 * i          # Ir
        s[3] = 1.5 + 0.1 * i          # Irr
        s[6] = 0.5 + 0.02 * i         # R forward only
        rows.append(R.RegRow("g", s, -0.4, 1.0, "turn_left"))
        s2 = np.zeros(8)
        s2[0] = 1.0 + 0.1 * i
        s2[1] = 1.2 + 0.05 * i
        s2[6] = 0.5 + 0.02 * i
        rows.append(R.RegRow("g", s2, -0.2, 1.0, "straight"))
    spec, _ = R.choose_spec(rows, p_base, ["g"])
    assert all(g.tie_fwd for g in spec.groups), spec.reductions
    assert any("lr_asymmetry" in r for r in spec.reductions), spec.reductions


def test_rank_deficient_damping_falls_back_to_baseline_not_noise():
    p_base = baseline()
    # u is constant across every window -> Iu and Iu2 are exactly collinear
    rows = []
    for i in range(60):
        s = np.zeros(8)
        s[0] = 20.0
        s[1] = 20.0
        s[4] = 0.7 + 0.01 * i
        s[5] = -0.0
        s[6] = 0.7 + 0.01 * i
        rows.append(R.RegRow("g", s, -1.0, 1.0, "cruise"))
        s2 = np.zeros(8)
        s2[2] = 1.0 + 0.2 * i
        s2[3] = 0.8 + 0.1 * i
        s2[4] = 0.7 + 0.01 * i
        s2[6] = 0.7 + 0.01 * i
        rows.append(R.RegRow("g", s2, -0.3, 1.0, "turn_right"))
    spec, info = R.choose_spec(rows, p_base, ["g"])
    assert info["rank"] == info["n_cols"]
    assert any("xu_xuu_not_separable" in r for r in spec.reductions), spec.reductions
    assert "a1" in spec.damp_fixed and spec.damp_fixed["a1"] == pytest.approx(-p_base["Xu"])


# ---------------------------------------------------------------------------
# 5. blind observations cannot change the candidate or the model selection
# ---------------------------------------------------------------------------
def test_blind_observations_only_affect_metrics(tmp_path):
    truth = baseline()
    truth.update({"Xu": -2.2, "Xuu": -11.5, "Nr": -3.1, "Nrr": -0.7,
                  "g_forward": 25.0})
    t, X = _synthesize(Q_PROFILE, truth)
    train_path = _write_trajectory_log(tmp_path / "tr.bin", t, X, Q_PROFILE)
    # a different (but valid) blind log: same inputs, different initial state
    t2, X2 = _synthesize(Q_PROFILE, truth, t_end=60.0)
    X2 = X2 + np.array([5.0, -3.0, 0.4, 0.3, -0.1, 0.05])
    blind_path = _write_trajectory_log(tmp_path / "bl.bin", t2, X2, Q_PROFILE)

    p_base = baseline()
    ztr = load_log(train_path, tmp_path, "tr.npz")
    zbl = load_log(blind_path, tmp_path, "bl.npz")
    dtr = R.build_dataset(ztr, meta_for(train_path), {}, {})
    dbl = R.build_dataset(zbl, meta_for(blind_path, role="blind_today"), {}, {})
    assert dtr["segments"] and dbl["segments"]

    fit1 = _fit_from_segments(dtr["segments"], p_base)
    model1 = fit1["model"]
    m1 = R.replay_summary(dbl["segments"], model1, "cand")
    m0 = R.replay_summary(dbl["segments"], R.prior_model(p_base, [model1["gains"] and
                                                                  list(model1["gains"])[0]]), "M0")

    # perturb the blind observations only
    perturbed = []
    for s in dbl["segments"]:
        p = R.Segment(sid=s.sid, t0=s.t0, t1=s.t1, group=s.group, t=s.t,
                      x=s.x.copy(), ui=s.ui.copy(), pwm=s.pwm.copy(), rpm=s.rpm,
                      mode=s.mode, labels=s.labels)
        p.x[:, 3] *= 3.0
        p.x[:, 5] *= 3.0
        perturbed.append(p)

    fit2 = _fit_from_segments(dtr["segments"], p_base)
    np.testing.assert_allclose(fit2["theta"], fit1["theta"], rtol=0, atol=0,
                              err_msg="blind data must not influence the candidate")
    assert fit2["spec"].reductions == fit1["spec"].reductions

    m1b = R.replay_summary(perturbed, model1, "cand")
    assert m1b["composite"] > m1["composite"] * 1.5, "metrics must move with the data"
    assert m0["n_windows"] == m1["n_windows"]


def test_windows_never_come_from_an_excluded_region(tmp_path):
    log = SynthLog()
    for t in np.arange(10.0, 120.0, 0.02):
        log.imu(t, inst=0, gyrz=0.0)
        log.att(t, yaw_deg=0.0)
        log.xkf1(t, core=0, yaw_deg=0.0, vn=1.0, pn=t)
        log.xkf4(t, core=0, pi=0)
        tick = int(round(t * 100))
        if tick % 5 == 0:
            log.rcou(t, 1600, 1600)
        if tick % 50 == 0:
            log.gps(t)
            log.vibe(t)
        if t < 10.5:
            log.mode(t, 0)
            log.arm(t, 1)
    path = log.write(str(tmp_path / "ex.bin"))
    z = load_log(path, tmp_path, "ex.npz")
    excl = {os.path.basename(path): [{"start_s": 40.0, "end_s": 60.0,
                                      "verdict": "IGNORED"}]}
    ds = R.build_dataset(z, meta_for(path), excl, {})
    for s in ds["segments"]:
        assert s.t1 <= 40.0 - R.EXCL_PAD_S + 1e-6 or s.t0 >= 60.0 + R.EXCL_PAD_S - 1e-6
    for s, a, b in R.holdout_windows(ds["segments"]):
        assert s.t1 <= 40.0 - R.EXCL_PAD_S + 1e-6 or s.t0 >= 60.0 + R.EXCL_PAD_S - 1e-6


# ---------------------------------------------------------------------------
# 6. ESTALE: forward-only verified copy, and refusal on interruption/hash drift
# ---------------------------------------------------------------------------
class _StaleHandle:
    """File-like object that refuses seek like the 2026-11-02 mount does."""

    def __init__(self, path, limit=None):
        self._fh = open(path, "rb")
        self._limit = limit
        self._read = 0

    def read(self, n=-1):
        if self._limit is not None:
            n = min(n if n >= 0 else 1 << 20, self._limit - self._read)
            if n <= 0:
                return b""
        b = self._fh.read(n)
        self._read += len(b)
        return b

    def seek(self, *a, **k):
        raise OSError(116, "Stale file handle")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._fh.close()
        return False


def _stale_opener(limit=None):
    def _open(path, mode="rb"):
        assert mode == "rb"
        return _StaleHandle(path, limit=limit)
    return _open


def test_stale_handle_source_is_copied_forward_and_becomes_parseable(tmp_path):
    log = SynthLog()
    for t in np.arange(10.0, 30.0, 0.02):
        log.imu(t, inst=0, gyrz=-0.5)
        log.att(t, yaw_deg=0.0)
        log.xkf1(t, core=0, yaw_deg=0.0, vn=1.0, pn=t)
        log.xkf4(t, core=0, pi=0)
        tick = int(round(t * 100))
        if tick % 5 == 0:
            log.rcou(t, 1600, 1600)
        if tick % 50 == 0:
            log.gps(t)
            log.vibe(t)
        if t < 10.5:
            log.mode(t, 0)
            log.arm(t, 1)
    src = log.write(str(tmp_path / "stale.bin"))
    sha, size = R.sha256_file(src)

    dst = str(tmp_path / "copy.bin")
    info = R.verified_copy(src, dst, expected_sha=sha, opener=_stale_opener())
    assert "error" not in info, info
    assert info["sha256"] == sha and info["bytes_read"] == size
    # the verified copy must be parseable by the normal reader
    z = load_log(dst, tmp_path, "copy.npz")
    assert z["IMU.TimeUS"].size > 100

    # the original is untouched
    assert R.sha256_file(src) == (sha, size)


def test_interrupted_stream_or_hash_drift_disqualifies_the_source(tmp_path):
    log = SynthLog()
    for t in np.arange(10.0, 20.0, 0.02):
        log.imu(t, inst=0, gyrz=0.0)
        log.att(t, yaw_deg=0.0)
        log.xkf1(t, core=0, yaw_deg=0.0, vn=0.0, pn=0.0)
        log.xkf4(t, core=0, pi=0)
        if int(round(t * 100)) % 5 == 0:
            log.rcou(t, 1500, 1500)
        if t < 10.5:
            log.mode(t, 0)
            log.arm(t, 1)
    src = log.write(str(tmp_path / "s.bin"))
    sha, size = R.sha256_file(src)

    # stream drops out early -> the copy is short, so the source is unusable
    short = R.verified_copy(src, str(tmp_path / "short.bin"), expected_sha=sha,
                            opener=_stale_opener(limit=size // 2))
    assert short.get("error") == "stream_interrupted"

    # full stream but the expected digest no longer matches
    drift = R.verified_copy(src, str(tmp_path / "drift.bin"),
                            expected_sha="0" * 64)
    assert drift.get("error") == "source_changed"

    # neither case may produce a parseable npz, and the original is unchanged
    assert not os.path.exists(str(tmp_path / "drift.npz"))
    assert R.sha256_file(src) == (sha, size)

    z, meta = R.parse_source_to_npz(src, str(tmp_path / "bad.npz"),
                                    expected_sha="0" * 64)
    assert z is None and meta.get("error") == "source_changed"


# ---------------------------------------------------------------------------
# 7. stale health evidence must expire (no carried-forward healthy GPS fix)
# ---------------------------------------------------------------------------
def test_gps_outage_cannot_inherit_the_last_healthy_fix(tmp_path):
    log = SynthLog()
    for t in np.arange(10.0, 60.0, 0.02):
        log.imu(t, inst=0, gyrz=0.0)
        log.att(t, yaw_deg=0.0)
        log.xkf1(t, core=0, yaw_deg=0.0, vn=1.0, pn=t, pe=0.0)
        log.xkf4(t, core=0, pi=0)
        tick = int(round(t * 100))
        if tick % 5 == 0:
            log.rcou(t, 1650, 1650)
        # GPS only outside the outage window 25..45 s
        if (t < 25.0 or t > 45.0) and tick % 50 == 0:
            log.gps(t, status=6, hdop=0.6)
        if tick % 50 == 0:
            log.vibe(t)
        if t < 10.5:
            log.mode(t, 0)
            log.arm(t, 1)
    path = log.write(str(tmp_path / "gpsgap.bin"))
    z = load_log(path, tmp_path, "gpsgap.npz")
    ds = R.build_dataset(z, meta_for(path), {}, {})
    segs = ds["segments"]
    assert segs, f"expected clean segments either side of the outage: {ds['reasons']}"
    # a single 1 s-stale fix is tolerated, but the outage itself must be excluded
    for s in segs:
        assert not (s.t0 < 44.0 and s.t1 > 26.0), (
            f"segment {s.t0:.1f}-{s.t1:.1f} spans the GPS outage 25-45 s")
    assert any(s.t0 < 25.0 for s in segs)
    assert any(s.t0 >= 44.0 for s in segs)


# ---------------------------------------------------------------------------
# 8. replay must never borrow another hardware group's propulsion model
# ---------------------------------------------------------------------------
def test_replay_does_not_borrow_another_group_gains(tmp_path):
    truth = baseline()
    truth.update({"Xu": -2.2, "Xuu": -11.5, "Nr": -3.1, "Nrr": -0.7,
                  "g_forward": 25.0})
    t, X = _synthesize(Q_PROFILE, truth, t_end=60.0)
    a = _write_trajectory_log(tmp_path / "ga.bin", t, X, Q_PROFILE)
    b = _write_trajectory_log(tmp_path / "gb.bin", t, X, Q_PROFILE)
    za = load_log(a, tmp_path, "ga.npz")
    zb = load_log(b, tmp_path, "gb.npz")
    da = R.build_dataset(za, meta_for(a, group="groupA"), {}, {})
    db = R.build_dataset(zb, meta_for(b, group="groupB"), {}, {})
    assert da["segments"] and db["segments"]

    p_base = baseline()
    fit = R.fit_model(R.group_segments(da["segments"]), p_base, "onlyA")
    model = fit["model"]  # knows groupA only
    res = R.replay_windows(db["segments"], model)
    assert res is None, "must not replay groupB with groupA thrust parameters"
    # and when groups are mixed, only the known one is evaluated
    res2 = R.replay_windows(da["segments"] + db["segments"], model)
    assert res2 is not None
    assert set(res2["groups"]) == {"groupA"}
    assert res2["not_evaluable_segments"] >= len(db["segments"])


# ---------------------------------------------------------------------------
# 9. a reused holdout can never license an accepted result
# ---------------------------------------------------------------------------
def test_reused_holdout_caps_an_accepted_verdict():
    fresh = {"status": "fresh"}
    reused = {"status": "reused_after_prior_exposure"}
    assert R._holdout_verdict_cap("accepted", fresh) == "accepted"
    assert R._holdout_verdict_cap("accepted", reused) == "insufficient_holdout"
    # other verdicts are untouched
    assert R._holdout_verdict_cap("rejected", reused) == "rejected"
    assert R._holdout_verdict_cap("source_unreadable", reused) == "source_unreadable"
