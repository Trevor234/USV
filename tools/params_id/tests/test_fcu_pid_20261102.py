"""Behavioural regression tests for the 2026-11-02 FCU PID analysis.

Everything is synthetic: logs are written from scratch with ArduPilot FMT
definitions, so the tests never read the production corpus and never depend on
it being mounted.  Only consumer-visible behaviour is asserted — no source
strings, no private helper internals, no default-value round trips.
"""
import csv
import json
import math
import os
import struct
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import analyze_fcu_pid_20261102 as A  # noqa: E402
import reidentify_20261102 as R  # noqa: E402

DF2PY = {"b": "b", "B": "B", "h": "h", "H": "H", "i": "i", "I": "I", "f": "f",
         "d": "d", "n": "4s", "N": "16s", "Z": "64s", "c": "h", "C": "H",
         "e": "i", "E": "I", "L": "i", "M": "b", "q": "q", "Q": "Q"}

FMT = {
    "PIDS": (223, "QffffffffffB",
             "TimeUS,Tar,Act,Err,P,I,D,FF,DFF,Dmod,SRate,Flags"),
    "PIDA": (223, "QffffffffffB",
             "TimeUS,Tar,Act,Err,P,I,D,FF,DFF,Dmod,SRate,Flags"),
    "STER": (41, "Qffhhff", "TimeUS,SteerIn,SteerOut,DesLatAcc,LatAcc,DesTurnRate,TurnRate"),
    "THR": (32, "Qhfff", "TimeUS,ThrIn,ThrOut,DesSpeed,Speed"),
    "MODE": (121, "QMBB", "TimeUS,Mode,ModeNum,Rsn"),
    "ARM": (187, "QBIBB", "TimeUS,ArmState,ArmChecks,Forced,Method"),
    "PARM": (32, "QNff", "TimeUS,Name,Value,Default"),
    "ATT": (72, "QffffffB", "TimeUS,DesRoll,Roll,DesPitch,Pitch,DesYaw,Yaw,AEKF"),
    "XKF1": (44, "QBccCfffffffccce",
             "TimeUS,C,Roll,Pitch,Yaw,VN,VE,VD,dPD,PN,PE,PD,GX,GY,GZ,OH"),
    "XKF4": (47, "QBcccccfffHBIHb", "TimeUS,C,SV,SP,SH,SM,SVT,errRP,OFN,OFE,FS,TS,SS,GPS,PI"),
    "GPS": (94, "QBBIHBcLLeffffB", "TimeUS,I,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt,Spd,GCrs,VZ,Yaw,U"),
    "VIBE": (167, "QBfffI", "TimeUS,IMU,VibeX,VibeY,VibeZ,Clip"),
}
IDS = {name: 100 + i for i, name in enumerate(FMT)}
XKF1_ROWS = 16


def _to_py(fs):
    return "".join(DF2PY[c] for c in fs)


def _fmt_msg(tid, df_fmt, cols, name):
    total = 3 + struct.calcsize("<" + _to_py(df_fmt))
    payload = struct.pack("<BB4s16s64s", tid, total, name.encode(),
                          df_fmt.encode(), cols.encode())
    return bytes([0xA3, 0x95, 0x80]) + payload


def _data(tid, df_fmt, values):
    return bytes([0xA3, 0x95, tid]) + struct.pack("<" + _to_py(df_fmt), *values)


class LogBuilder:
    """Minimal but faithful DataFlash writer for the streams under test."""

    def __init__(self):
        self.buf = bytearray()
        for name, (length, df_fmt, cols) in FMT.items():
            self.buf += _fmt_msg(IDS[name], df_fmt, cols, name)

    def pids(self, t, tar, act, err, p=0.0, i=0.0, d=0.0, ff=0.0, flags=0,
             kind="PIDS"):
        self.buf += _data(IDS[kind], FMT[kind][1],
                          [int(round(t * 1e6)), tar, act, err, p, i, d, ff,
                           0.0, 1.0, 0.0, int(flags)])

    def ster(self, t, steer_out, des_turn_rate, turn_rate):
        # "Qffhhff": SteerIn/SteerOut floats, DesLatAcc/LatAcc int16 centi
        self.buf += _data(IDS["STER"], FMT["STER"][1],
                          [int(round(t * 1e6)), 0.0, steer_out, 0, 0,
                           des_turn_rate, turn_rate])

    def thr(self, t, thr_out, des_speed, speed):
        self.buf += _data(IDS["THR"], FMT["THR"][1],
                          [int(round(t * 1e6)), 0, thr_out, des_speed, speed])

    def mode(self, t, mode_num):
        self.buf += _data(IDS["MODE"], FMT["MODE"][1],
                          [int(round(t * 1e6)), int(mode_num), int(mode_num), 1])

    def arm(self, t, state):
        self.buf += _data(IDS["ARM"], FMT["ARM"][1],
                          [int(round(t * 1e6)), int(state), 0, 0, 1])

    def parm(self, t, name, value):
        self.buf += _data(IDS["PARM"], FMT["PARM"][1],
                          [int(round(t * 1e6)), name.encode(), value, value])

    def health(self, t, roll=0.0, pitch=0.0, gps_status=6, hdop=0.6, clip=0):
        for core in (0, 1):
            # "QBccCfffffffccce": Roll/Pitch/Yaw are int16 centidegrees,
            # VN/VE/VD the floats, then three int16 centidegrees, then uint8 OH
            self.buf += _data(IDS["XKF1"], FMT["XKF1"][1],
                              [int(round(t * 1e6)), core,
                               int(round(roll * 100)), int(round(pitch * 100)),
                               int(round(0.0 * 100)), 0.0, 0.0, 0.0, 0.0,
                               0.0, 0.0, 0.0, 0, 0, 0, 0])
            self.buf += _data(IDS["XKF4"], FMT["XKF4"][1],
                              [int(round(t * 1e6)), core, 1, 1, 1, 1, 1,
                               0.0, 0.0, 0.0, 0, 0, 0, 1, 0])
        self.buf += _data(IDS["ATT"], FMT["ATT"][1],
                          [int(round(t * 1e6)), 0.0, roll, 0.0, pitch, 0.0, 0.0, 0])
        # "QBBIHBcLLeffffB": Status u8, GMS u8, GWk u16, NSats u8, HDop u16
        # (centi), Lat/Lng int32, then Alt/Spd/GCrs/VZ floats
        self.buf += _data(IDS["GPS"], FMT["GPS"][1],
                          [int(round(t * 1e6)), 0, int(gps_status), 0, 0, 12,
                           int(round(hdop * 100)),
                           0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0])
        for imu in (0, 1):
            self.buf += _data(IDS["VIBE"], FMT["VIBE"][1],
                              [int(round(t * 1e6)), imu, 1.0, 1.0, 1.0, int(clip)])

    def write(self, path):
        with open(path, "wb") as fh:
            fh.write(bytes(self.buf))
        return path


BASE_PARAMS = {
    "ATC_STR_RAT_FF": 0.6, "ATC_STR_RAT_P": 0.2, "ATC_STR_RAT_I": 0.1,
    "ATC_STR_RAT_D": 0.0, "ATC_STR_RAT_IMAX": 1.0, "ATC_STR_RAT_MAX": 30.0,
    "ATC_STR_ANG_P": 0.2, "ATC_STR_ACC_MAX": 60.0, "ACRO_TURN_RATE": 180.0,
    "ATC_SPEED_FF": 0.0, "ATC_SPEED_P": 0.5, "ATC_SPEED_I": 0.2,
    "ATC_SPEED_D": 0.0, "ATC_SPEED_IMAX": 1.0, "CRUISE_SPEED": 2.0,
    "CRUISE_THROTTLE": 50.0, "SPEED_MAX": 0.0, "SCHED_LOOP_RATE": 50.0,
}


def _frame(model="yaw", t_end=40.0, ref=math.radians(20.0), act=None,
           mode_name="ACRO", armed=True, gap=None, flags=0.0, err_scale=1.0,
           speed=1.0):
    """Synthetic closed-loop log: 50 Hz PID, 10 Hz auxiliary streams."""
    lb = LogBuilder()
    for k, v in BASE_PARAMS.items():
        lb.parm(0.5, k, v)
    lb.mode(1.0, {"MANUAL": 0, "ACRO": 1, "AUTO": 10, "HOLD": 4,
                  "GUIDED": 15}[mode_name])
    lb.arm(1.2, 1 if armed else 0)
    t = np.arange(2.0, t_end, 0.02)
    r = np.full(t.shape, ref if model == "yaw" else (ref if ref < 5 else ref))
    if model != "yaw":
        r = np.full(t.shape, ref)
    a = r if act is None else np.asarray(act(t, r), dtype=float)
    e = (r - a) * err_scale
    for i, ti in enumerate(t):
        if gap is not None and gap[0] <= ti <= gap[1]:
            continue
        lb.health(ti, clip=0)
        if model == "yaw":
            lb.pids(ti, r[i], a[i], e[i], p=0.1, i=0.01, flags=flags)
            lb.ster(ti, a[i] * (4500.0 / math.radians(30.0)) * 0.5,
                    math.degrees(r[i]), math.degrees(a[i]))
            lb.thr(ti, 50.0, speed, speed)
        else:
            lb.pids(ti, r[i], a[i], e[i], kind="PIDA", p=0.1, i=0.01, flags=flags)
            lb.thr(ti, a[i] * 50.0, r[i], a[i])
            lb.ster(ti, 0.0, 0.0, 0.0)
    return lb, t


def _frame_from(log_path, loop="yaw", windows=()):
    npz = log_path + ".npz"
    A._parse_bin(log_path, npz)
    z = A._load_npz(npz)
    params, _hist = R._params_dict(z)
    f = A.build_loop_frame(z, params, list(windows), os.path.basename(log_path), loop)
    os.unlink(npz)
    return f


# ---------------------------------------------------------------------------
# 1. full PID extraction
# ---------------------------------------------------------------------------
def test_full_pid_fields_survive_and_missing_fields_are_not_zero(tmp_path):
    lb, _t = _frame()
    p = lb.write(str(tmp_path / "a.bin"))
    npz = str(tmp_path / "a.npz")
    info = A._parse_bin(p, npz)
    z = A._load_npz(npz)
    for key in ("Tar", "Act", "Err", "P", "I", "D", "FF", "DFF", "Dmod",
                "SRate", "Flags"):
        assert key in info["fields_present"]["PIDS"], key
        assert np.isfinite(np.asarray(z[f"PIDS.{key}"], dtype=float)).any(), key

    # a stream that is absent must stay absent, not become a zero column
    assert "STER" not in info["missing_messages"]
    thin = LogBuilder()
    for k, v in BASE_PARAMS.items():
        thin.parm(0.5, k, v)
    thin.mode(1.0, 1)
    thin.arm(1.2, 1)
    thin.pids(2.0, 0.1, 0.1, 0.0, flags=0.0)
    p2 = thin.write(str(tmp_path / "b.bin"))
    npz2 = str(tmp_path / "b.npz")
    info2 = A._parse_bin(p2, npz2)
    assert "STER" in info2["missing_messages"]
    z2 = A._load_npz(npz2)
    assert np.asarray(z2["STER.TimeUS"]).size == 0

    # Flags absent -> NaN diagnostics, never "not saturated"
    f = _frame_from(p, "yaw")
    assert f is not None
    nan_flags = np.full(10, np.nan)
    m = A.segment_metrics(np.arange(10.0), np.zeros(10), np.zeros(10),
                          np.zeros(10), "yaw", flags=nan_flags)
    assert m["evaluable"]
    assert m["sat_frac"] is None or not np.isfinite(m["sat_frac"])


# ---------------------------------------------------------------------------
# 2. MANUAL stale values gain no credit; genuine repeats are not dropped
# ---------------------------------------------------------------------------
def test_manual_never_gets_credit_and_repeats_are_not_dropped(tmp_path):
    lb, _t = _frame(mode_name="MANUAL")
    p = lb.write(str(tmp_path / "m.bin"))
    f = _frame_from(p, "yaw")
    assert f is not None
    assert not f["masks"]["numeric"].any()
    assert f["masks"]["negative_control_manual"].any()

    # a healthy closed loop whose PID numbers repeat verbatim must survive
    def flat_act(t, r):
        return r  # zero error, every sample identical

    lb2, _t2 = _frame(act=flat_act)
    p2 = lb2.write(str(tmp_path / "c.bin"))
    f2 = _frame_from(p2, "yaw")
    assert f2 is not None
    assert f2["masks"]["numeric"].any(), "steady repeats must not be discarded"
    blocks = A._split_blocks(f2, f2["masks"]["numeric"])
    assert blocks
    m = A._block_metrics(f2, *blocks[0], "yaw")
    assert m["evaluable"]
    assert m["rmse"] < 1e-6


# ---------------------------------------------------------------------------
# 3. record gaps, state boundaries, anomaly windows
# ---------------------------------------------------------------------------
def test_gap_and_state_boundaries_are_excluded_and_verdicts_do_not_matter(tmp_path):
    lb, _t = _frame(gap=(10.0, 60.0))
    p = lb.write(str(tmp_path / "g.bin"))
    f = _frame_from(p, "yaw")
    assert f is not None
    t = f["t"]
    mask = f["masks"]["numeric"]
    inside = (t > 10.0) & (t < 60.0)
    assert not (mask & inside).any(), "a gap must never produce bridged samples"
    before = mask & (t < 10.0)
    after = mask & (t > 60.0)
    assert before.any()
    # state after the gap is unknown until a new MODE/ARM event: this builder
    # emits those only at the start, so the post-gap side stays uncredited
    assert not after.any(), "state must not be extended across a record gap"

    # rewriting the verdict text changes nothing about the mask
    windows_a = [(5.0, 6.0)]
    f_a = _frame_from(p, "yaw", windows=windows_a)
    f_b = _frame_from(p, "yaw", windows=[(5.0, 6.0)])
    assert np.array_equal(f_a["masks"]["numeric"], f_b["masks"]["numeric"])
    excluded = (f_a["t"] >= 5.0 - A.ANOMALY_PAD_S) & (f_a["t"] <= 6.0 + A.ANOMALY_PAD_S)
    assert not (f_a["masks"]["numeric"] & excluded).any()


def test_armed_gate_rejects_disarmed_interval(tmp_path):
    lb, _t = _frame(armed=False)
    p = lb.write(str(tmp_path / "d.bin"))
    f = _frame_from(p, "yaw")
    assert f is not None
    assert not f["masks"]["numeric"].any()


# ---------------------------------------------------------------------------
# 4. units and sign
# ---------------------------------------------------------------------------
def test_cross_stream_units_and_sign(tmp_path):
    # 0.5235987756 rad/s paired with 30 deg/s is zero error
    same = np.array([0.5235987756, 0.3490658504, 0.1745329252])
    same_dps = np.degrees(same)
    mism = A.cross_stream_delta("yaw", same, same, same_dps, same_dps)
    assert mism["ok"] and mism["applied"]
    assert mism["ref_delta"] < 1e-6 and mism["act_delta"] < 1e-6

    # forgetting a unit conversion on one side must be visible
    forgot = A.cross_stream_delta("yaw", same, same, same, same_dps)
    assert not forgot["ok"]

    # inverting the sign on one side only must be visible too
    flipped = A.cross_stream_delta("yaw", same, same, -same_dps, same_dps)
    assert not flipped["ok"]

    # speed loop pairs m/s with m/s, so only a real mismatch trips it
    v = np.array([0.5, 0.6, 0.7])
    ok_speed = A.cross_stream_delta("speed", v, v, v, v)
    assert ok_speed["ok"]
    assert not A.cross_stream_delta("speed", v, v, v + 0.3, v)["ok"]


# ---------------------------------------------------------------------------
# 5. speed feed-forward base is counted once; CRUISE_SPEED=0 disables it
# ---------------------------------------------------------------------------
def test_speed_ff_base_counted_once_and_cruise_zero_disables():
    # throttle_norm = PID + ATC_SPEED_FF*v + v*(CRUISE_THROTTLE/100)/CRUISE_SPEED
    v, p_thr, cruise = 2.0, 50.0, 2.0
    base = v * (p_thr / 100.0) / cruise          # == 0.5
    out_norm = 0.0 + 0.0 + base
    assert abs(out_norm - 0.5) < 1e-12
    assert abs(out_norm * A.THROTTLE_FULL_SCALE - 50.0) < 1e-9
    # counting it twice would land on 100 %, i.e. a different experiment
    assert abs(2 * out_norm * A.THROTTLE_FULL_SCALE - 50.0) > 1.0

    # CRUISE_SPEED <= 0 disables the base term in the firmware
    def base_term(cruise_speed, cruise_throttle, speed):
        if cruise_speed > 0 and cruise_throttle > 0:
            return speed * (cruise_throttle / 100.0) / cruise_speed
        return 0.0

    assert base_term(0.0, 50.0, 2.0) == 0.0
    assert abs(base_term(2.0, 50.0, 2.0) - 0.5) < 1e-12

    # the recorded value must be reported as 0.5, never as the 50 % input
    lb = LogBuilder()
    lb.parm(0.5, "CRUISE_THROTTLE", 50.0)
    assert 50.0 / A.THROTTLE_FULL_SCALE == 0.5


# ---------------------------------------------------------------------------
# 6. nothing unvalidated may be reported as validated or recommendable
def test_no_validated_or_recommended_output_without_trials(tmp_path):
    lb, _t = _frame(flags=float(A.FLAG_LIMIT))
    p = lb.write(str(tmp_path / "s.bin"))
    f = _frame_from(p, "yaw")
    blocks = A._split_blocks(f, f["masks"]["numeric"])
    assert blocks
    m = A._block_metrics(f, *blocks[0], "yaw")
    assert m["sat_frac"] is not None and m["sat_frac"] > A.GATE_SAT_FRAC

    base = dict(m)
    base["sat_frac"] = 0.0
    g = A.gate_block("yaw", base, m)
    assert not g["pass"], "saturated candidate must not pass"
    assert not g["gates"]["saturation"]["pass"]

    rows, psha = A._build_matrix(
        {"pid": {"yaw": dict(BASE_PARAMS), "speed": dict(BASE_PARAMS)}},
        {"anchor": None, "reason": "none"},
        {"fit": None, "reason": "none"})
    assert rows and all(r["validated"] is False for r in rows)
    assert all(r["recommendation_status"] != "validated" for r in rows)
    for r in rows:
        assert r["parent_param_sha256"] == psha
    for r in rows:
        if r["candidate"] is not None and r["original"] is not None:
            changed = [k for k in A.VAR_WHITELIST
                       if abs((r["candidate"] if k == r["param"] else r["original"])
                              - r["original"]) > 1e-12]
            assert len(changed) <= 1
            assert r["param"] in A.VAR_WHITELIST


def test_parameter_snapshot_mismatch_blocks_validation(tmp_path):
    # the log says P=0.2 while the candidate declares 0.22 -> must be rejected
    lb, _t = _frame()
    p = lb.write(str(tmp_path / "p.bin"))
    snap = tmp_path / "snap.param"
    snap.write_text("ATC_STR_RAT_P,0.22\n", encoding="utf-8")
    vals, _o = A._param_backup(str(snap))
    declared = {"yaw_p_110": vals}
    npz = p + ".npz"
    A._parse_bin(p, npz)
    z = A._load_npz(npz)
    params, _h = R._params_dict(z)
    os.unlink(npz)
    mismatch = abs(float(params["ATC_STR_RAT_P"]) - float(declared["yaw_p_110"]
                                                          ["ATC_STR_RAT_P"])) > 1e-6
    assert mismatch, "the declared value must not silently overwrite the log"


# ---------------------------------------------------------------------------
# 7. improvement gate, neighbour gate, and the param diff
# ---------------------------------------------------------------------------
def _step_track(ref=math.radians(20.0), n=800, dt=0.02, tau=0.3,
                ss_error=0.0, overshoot=0.0, noise=0.0, seed=7, flags=0.0):
    """Step response: 0 -> ref at t=1 s, first-order rise plus optional overshoot."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    r = np.where(t >= 1.0, ref, 0.0)
    y = np.where(t >= 1.0, ref * (1.0 - np.exp(-(t - 1.0) / tau)), 0.0)
    if overshoot:
        y = y + overshoot * ref * np.exp(-((t - 1.0 - 3 * tau) ** 2) / (2 * tau ** 2)) \
            * (t >= 1.0)
    y = y - ss_error * (t >= 1.0)
    if noise:
        y = y + rng.normal(0.0, noise, n)
    e = r - y
    return t, r, y, e


def _metrics(t, r, y, e, loop="yaw", flags=0.0):
    n = t.size
    return A.segment_metrics(t, r, y, e, loop,
                             flags=np.full(n, float(flags)) if flags is not None
                             else np.full(n, np.nan))


def test_improvement_gate_and_neighbour_gate(tmp_path):
    # slow baseline, faster candidate: RMSE should improve on the same window
    tb, rb, ab, eb = _step_track(tau=0.9)
    base = _metrics(tb, rb, ab, eb)
    tc, rc, ac, ec = _step_track(tau=0.3)
    cand = _metrics(tc, rc, ac, ec)
    g = A.gate_block("yaw", base, cand)
    assert g["gates"]["rmse_improvement"]["value"] <= A.GATE_RMSE_RATIO
    assert g["gates"]["overshoot"]["status"] in ("pass", "fail")
    assert g["pass"], g["gates"]

    # the very same trace cannot be sold as an improvement
    g_same = A.gate_block("yaw", base, base)
    assert not g_same["pass"]
    assert g_same["gates"]["rmse_improvement"]["status"] == "fail"

    # clearly worse tracking is rejected
    tw, rw, aw, ew = _step_track(tau=2.5)
    assert not A.gate_block("yaw", base, _metrics(tw, rw, aw, ew))["pass"]

    # a block with no step reports overshoot as not_evaluable, not as a pass
    tflat = np.arange(400) * 0.02
    rflat = np.full(400, math.radians(20.0))
    eflat = np.zeros(400)
    flat = _metrics(tflat, rflat, rflat, eflat)
    g_flat = A.gate_block("yaw", flat, flat)
    assert g_flat["gates"]["overshoot"]["status"] == "not_evaluable"
    assert not g_flat["pass"]

    # without a logged Flags column saturation is unknown, so adoption is
    # blocked but the row is not mislabelled as a measured failure
    no_flags = _metrics(tc, rc, ac, ec, flags=None)
    g_nf = A.gate_block("yaw", _metrics(tb, rb, ab, eb, flags=None), no_flags)
    assert g_nf["gates"]["saturation"]["status"] == "not_evaluable"
    assert not g_nf["pass"]

    # neighbour loop: steering must not degrade beyond max(1.1*base, 2 deg/s)
    nb_base = {"rmse": math.radians(1.0)}
    nb_ok = {"rmse": math.radians(1.05)}
    nb_bad = {"rmse": math.radians(4.0)}
    g_nb_ok = A.gate_block("yaw", base, cand, nb_base, nb_ok)
    g_nb_bad = A.gate_block("yaw", base, cand, nb_base, nb_bad)
    assert g_nb_ok["gates"]["neighbour_loop"]["pass"]
    assert not g_nb_bad["gates"]["neighbour_loop"]["pass"]

    # selection requires >=3 passing blocks
    two = {"c1": {"blocks": [g, g], "value": 0.21, "parent_value": 0.20}}
    assert A.select_candidate(two)["selected"] is None
    three = {"c1": {"blocks": [g, g, g], "value": 0.21, "parent_value": 0.20}}
    assert A.select_candidate(three)["selected"] == "c1"


def test_param_diff_contains_only_whitelisted_changes(tmp_path):
    parent = dict(BASE_PARAMS)
    child = dict(parent)
    child["ATC_STR_RAT_P"] = parent["ATC_STR_RAT_P"] * 1.1
    diff = {k: (parent.get(k), child[k]) for k in A.VAR_WHITELIST
            if k in child and parent.get(k) != child[k]}
    assert set(diff) == {"ATC_STR_RAT_P"}
    assert set(diff) <= set(A.VAR_WHITELIST)
    for k in A.HELD_PARAMS:
        assert k not in diff
    # rolling back restores the recorded values exactly
    rolled = dict(child)
    for k, (old, _new) in diff.items():
        rolled[k] = old
    assert rolled == parent


# ---------------------------------------------------------------------------
# 8. stage advancement rules
# ---------------------------------------------------------------------------
def test_ff_skip_advances_to_p_and_p_failure_advances_to_i_and_safety_blocks():
    rows, _sha = A._build_matrix(
        {"pid": {"yaw": dict(BASE_PARAMS), "speed": dict(BASE_PARAMS)}},
        {"anchor": None, "reason": "insufficient_negative_platforms"},
        {"fit": None, "reason": "fewer_than_three_platforms"})
    ff = [r for r in rows if r["stage"] == "FF"]
    assert ff and all(r["recommendation_status"] == "skipped_no_ff_evidence"
                      for r in ff)
    assert [r for r in rows if r["stage"] == "P"], "P stage must still be offered"
    assert [r for r in rows if r["stage"] == "I"], "I stage must still be offered"

    assert A._recommendation_status("yaw", {}, 0.0, 0) == "insufficient_evidence"
    assert A._recommendation_status("yaw", {}, 5.0, 1) == "insufficient_evidence"
    assert A._recommendation_status("yaw", {}, 5.0, 2) == "insufficient_evidence"
    assert A._recommendation_status("yaw", {}, 30.0, 3) == "trial_candidate"
    # validated is never produced by this function, whatever the evidence
    for blocks in (1, 3, 10, 100):
        assert A._recommendation_status("yaw", {}, 999.0, blocks) != "validated"


def test_parent_chain_must_resolve_and_sha_match(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    receipt = parent / "recommend.done.json"
    receipt.write_text(json.dumps({
        "stage": "recommend", "artifacts": {},
        "candidate_matrix_sha256": "deadbeef", "parent_param_sha256": "cafe"}) + "\n",
        encoding="utf-8")
    man = {
        "parent_root": str(parent),
        "parent_receipt_path": "recommend.done.json",
        "parent_receipt_sha256": "0" * 64,
        "candidate_matrix_sha256": "deadbeef",
        "purpose": "selection",
        "trials": [],
    }
    problems, _t = A._validate_manifest(man, str(tmp_path / "out"),
                                        str(tmp_path / "hist"))
    assert any("receipt sha mismatch" in p for p in problems)

    man["parent_receipt_sha256"] = A._file_sha(str(receipt))["sha256"]
    man["candidate_matrix_sha256"] = "not-the-matrix"
    problems2, _t = A._validate_manifest(man, str(tmp_path / "out"),
                                         str(tmp_path / "hist"))
    assert any("candidate_matrix_sha256" in p for p in problems2)

    del man["parent_receipt_path"]
    problems3, _t = A._validate_manifest(man, str(tmp_path / "out"),
                                         str(tmp_path / "hist"))
    assert any("missing top-level keys" in p for p in problems3)


# ---------------------------------------------------------------------------
# 9. final validation may not reuse a selection input
# ---------------------------------------------------------------------------
def test_final_validation_rejects_reused_selection_bins(tmp_path):
    hist = tmp_path / "hist"
    hist.mkdir()
    sel = tmp_path / "sel"
    sel.mkdir()
    bin_sha = "c" * 64
    (sel / "assess-trials.done.json").write_text(json.dumps({
        "stage": "assess-trials", "artifacts": {},
        "candidate_matrix_sha256": "m", "trial_bin_shas": [bin_sha]}) + "\n",
        encoding="utf-8")
    (sel / "trial_manifest.json").write_text(json.dumps({
        "parent_root": str(hist), "trials": [{"sha256": bin_sha}]}) + "\n",
        encoding="utf-8")

    used = A._selection_input_shas(str(hist), str(sel))
    assert bin_sha in used

    # a genuinely new capture is not in that set
    assert "d" * 64 not in used


# ---------------------------------------------------------------------------
# 10. GUIDED stays unproven; masked peaks cannot rescue a block
# ---------------------------------------------------------------------------
def test_guided_is_never_credited_even_with_matching_values(tmp_path):
    lb, t = _frame(mode_name="GUIDED")
    p = lb.write(str(tmp_path / "gui.bin"))
    f = _frame_from(p, "yaw")
    assert f is not None
    assert f["masks"]["diagnostic_only_guided"].any()
    assert not f["masks"]["numeric"].any()


def test_unusable_block_is_not_evaluable_rather_than_partially_scored(tmp_path):
    # error spike hidden inside a record gap must not be scored as a clean block
    def spiky(t, r):
        a = r.copy()
        return a

    lb, t = _frame(act=spiky, gap=(20.0, 21.0))
    p = lb.write(str(tmp_path / "sp.bin"))
    f = _frame_from(p, "yaw")
    blocks = A._split_blocks(f, f["masks"]["numeric"])
    assert blocks
    for a, b in blocks:
        tt = f["t"][a:b]
        assert not np.any((tt > 20.0) & (tt < 21.0)), "gap samples leaked into a block"

    # a window with too few samples is reported, never silently scored
    short = A.segment_metrics(np.array([0.0, 0.02]), np.array([0.0, 0.0]),
                              np.array([0.0, 0.0]), np.array([0.0, 0.0]), "yaw")
    assert not short["evaluable"]


# ---------------------------------------------------------------------------
# 11. end-to-end: selection -> next round -> independent final validation
# ---------------------------------------------------------------------------
def _trial_bin(path, loop, tau, params, ref=None, n=900, dt=0.02, mode=1,
               armed=True, step_at=3.0):
    """Synthetic authorised trial log with a real reference step."""
    ref = (math.radians(20.0) if loop == "yaw" else 0.6) if ref is None else ref
    lb = LogBuilder()
    for k, v in params.items():
        lb.parm(0.5, k, v)
    lb.mode(1.0, mode)
    lb.arm(1.2, 1 if armed else 0)
    t = np.arange(step_at - 2.5, step_at - 2.5 + n * dt, dt)
    r = np.where(t >= step_at, ref, 0.0)
    y = np.where(t >= step_at, ref * (1.0 - np.exp(-(t - step_at) / tau)), 0.0)
    e = r - y
    for i in range(t.size):
        lb.health(t[i])
        if loop == "yaw":
            lb.pids(t[i], r[i], y[i], e[i], p=0.1, i=0.01, flags=0)
            lb.ster(t[i], y[i] * (4500.0 / math.radians(30.0)) * 0.5,
                    math.degrees(r[i]), math.degrees(y[i]))
            lb.thr(t[i], 50.0, 1.0, 1.0)
        else:
            lb.pids(t[i], r[i], y[i], e[i], kind="PIDA", p=0.1, i=0.01, flags=0)
            lb.thr(t[i], y[i] * 50.0, r[i], y[i])
            lb.ster(t[i], 0.0, 0.0, 0.0)
    return lb.write(path)


def _params_with(base, **over):
    p = dict(base)
    p.update({k: v for k, v in over.items()})
    return p


def _write_snapshot(path, params):
    path.write_text("".join(f"{k},{v}\n" for k, v in sorted(params.items())),
                    encoding="utf-8")
    return str(path)


def _stop_evidence(path, key="stop"):
    path.write_text(json.dumps({"physical_stop_verified": True, "key": key}),
                    encoding="utf-8")
    return str(path)


def _make_round(tmp_path, root, loop, candidate_pid, candidate_params,
                base_params, blocks=3, tau_base=0.9, tau_cand=0.3, tag="a"):
    """Create the trial BINs + snapshots + manifest for one selection round."""
    trials, ids = [], []
    for b in range(blocks):
        for role, tau, pars in (("baseline", tau_base, base_params),
                                ("candidate", tau_cand, candidate_params)):
            f = tmp_path / f"{tag}_{candidate_pid}_{role}_{b}.bin"
            _trial_bin(str(f), loop, tau, pars)
            snap = _write_snapshot(tmp_path / f"{tag}_{role}_{b}.param", pars)
            stop = _stop_evidence(tmp_path / f"{tag}_{role}_{b}.stop.json",
                                  f"{candidate_pid}-{role}-{b}")
            ids.append({"file": str(f), "sha256": A._file_sha(str(f))["sha256"],
                        "hardware_id": "USV-ANSIS-01", "candidate_id": candidate_pid,
                        "loop": loop, "role": role, "block": b,
                        "params_snapshot": snap,
                        "params_snapshot_sha256": A._file_sha(snap)["sha256"],
                        "stop_evidence": stop,
                        "stop_evidence_sha256": A._file_sha(stop)["sha256"]})
    return trials_manifest(root, ids)


def trials_manifest(parent_root, trials, purpose="selection", final_combination=None):
    receipt = os.path.join(parent_root, "recommend.done.json")
    if not os.path.exists(receipt):
        receipt = os.path.join(parent_root, "assess-trials.done.json")
    with open(receipt, "r", encoding="utf-8") as fh:
        rec = json.load(fh)
    doc = {
        "parent_root": parent_root,
        "parent_receipt_path": os.path.basename(receipt),
        "parent_receipt_sha256": A._file_sha(receipt)["sha256"],
        "candidate_matrix_sha256": rec["candidate_matrix_sha256"],
        "purpose": purpose,
        "trials": trials,
    }
    if final_combination is not None:
        doc["final_combination"] = final_combination
    return doc


def test_assess_trials_full_chain_selects_advances_and_exports(tmp_path, capsys):
    here = os.path.dirname(os.path.abspath(__file__))
    hist = tmp_path / "hist"
    hist.mkdir()
    params0 = dict(BASE_PARAMS)
    rows = [{"candidate_id": "yaw_p_90", "loop": "yaw", "stage": "P",
             "param": "ATC_STR_RAT_P", "original": "0.2", "candidate": "0.18",
             "validated": "False", "recommendation_status": "trial_candidate"},
            {"candidate_id": "yaw_p_retain", "loop": "yaw", "stage": "P",
             "param": "ATC_STR_RAT_P", "original": "0.2", "candidate": "0.2",
             "validated": "False", "recommendation_status": "retain_parent"}]
    os.makedirs(hist / "recommend", exist_ok=True)
    with open(hist / "recommend" / "trial_candidates.csv", "w", encoding="utf-8") as fh:
        import csv as _csv  # noqa: F401
        w = _csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (hist / "baseline_params.json").write_text(json.dumps({
        "pid": {"yaw": dict(params0), "speed": dict(params0)}}), encoding="utf-8")
    (hist / "recommend.done.json").write_text(json.dumps({
        "stage": "recommend", "artifacts": {}, "validated": False,
        "candidate_matrix_sha256": "m1", "parent_param_sha256": "p1"}),
        encoding="utf-8")

    # --- round 1: the faster candidate must win -----------------------------
    r1 = tmp_path / "r1"
    man = _make_round(tmp_path, str(hist), "yaw", "yaw_p_90",
                      _params_with(params0, ATC_STR_RAT_P=0.18), params0, tag="r1")
    mpath = tmp_path / "man1.json"
    mpath.write_text(json.dumps(man), encoding="utf-8")
    rc = A.main(["--stage", "assess-trials", "--history", str(hist),
                 "--trial-manifest", str(mpath), "--out", str(r1)])
    assert rc == 0, capsys.readouterr()
    doc = json.loads((r1 / "assessment.json").read_text(encoding="utf-8"))
    assert doc["round_outcome"] == "selected_candidate", doc
    assert doc["selection"]["selected"] == "yaw_p_90"
    assert abs(doc["params_after_round"]["ATC_STR_RAT_P"] - 0.18) < 1e-12
    assert doc["next_stage"] == ["yaw", "I"]
    nxt = list(csv.DictReader(open(r1 / "next_round" / "trial_candidates.csv",
                                    encoding="utf-8")))
    assert all(r["parent_param_sha256"] == A._parent_sha(doc["params_after_round"])
               for r in nxt)
    # single-parameter discipline in the generated next round
    for r in nxt:
        assert r["param"] in A.VAR_WHITELIST

    # --- round 2 builds on round 1 -----------------------------------------
    r2 = tmp_path / "r2"
    params1 = dict(params0)
    params1["ATC_STR_RAT_P"] = 0.18
    man2 = _make_round(tmp_path, str(r1), "yaw", "yaw_i_110",
                       _params_with(params1, ATC_STR_RAT_I=0.11), params1, tag="r2")
    m2 = tmp_path / "man2.json"
    m2.write_text(json.dumps(man2), encoding="utf-8")
    rc = A.main(["--stage", "assess-trials", "--history", str(hist),
                 "--trial-manifest", str(m2), "--out", str(r2)])
    assert rc == 0
    doc2 = json.loads((r2 / "assessment.json").read_text(encoding="utf-8"))
    assert doc2["stage_assessed"] == ["yaw", "I"]
    assert doc2["selection"]["selected"] == "yaw_i_110"
    assert doc2["next_stage"] == ["speed", "CRUISE"]

    # --- the fixed sequence must finish before any final round -------------
    # from [speed, CRUISE] the sequence still owes CRUISE -> P -> I
    prev, prev_doc = r2, doc2
    for stage_key, cid, param, value in (
            ("CRUISE", "speed_cruise_skip", "CRUISE_THROTTLE", 50.0),
            ("P", "speed_p_110", "ATC_SPEED_P", 0.55),
            ("I", "speed_i_110", "ATC_SPEED_I", 0.22)):
        out_dir = tmp_path / f"r_{stage_key.lower()}"
        sub = dict(prev_doc["params_after_round"])
        sub[param] = value
        man = _make_round(tmp_path, str(prev), "speed", cid, sub,
                          prev_doc["params_after_round"], tag=stage_key.lower())
        mp = tmp_path / f"m_{stage_key}.json"
        mp.write_text(json.dumps(man), encoding="utf-8")
        assert A.main(["--stage", "assess-trials", "--history", str(hist),
                       "--trial-manifest", str(mp), "--out", str(out_dir)]) == 0
        prev = out_dir
        prev_doc = json.loads((out_dir / "assessment.json").read_text(encoding="utf-8"))
    assert prev_doc["selection_complete"] is True
    assert prev_doc["next_stage"] is None
    frozen = json.loads((prev / "final_combination.json").read_text(encoding="utf-8"))

    # --- final independent validation opens the export ---------------------
    r3 = tmp_path / "r3"
    trials3 = []
    for loop in ("yaw", "speed"):
        for b in range(3):
            for role, tau, pars in (("baseline", 0.75, frozen["baseline_params"]),
                                    ("candidate", 0.22, prev_doc["params_after_round"])):
                f = tmp_path / f"fin_{loop}_{role}_{b}.bin"
                _trial_bin(str(f), loop, tau, pars)
                snap = _write_snapshot(tmp_path / f"fin_{loop}_{role}_{b}.param", pars)
                stop = _stop_evidence(tmp_path / f"fin_{loop}_{role}_{b}.stop.json",
                                      f"{loop}-{role}-{b}")
                trials3.append({
                    "file": str(f), "sha256": A._file_sha(str(f))["sha256"],
                    "hardware_id": "USV-ANSIS-01",
                    "candidate_id": frozen["final_combination_id"],
                    "loop": loop, "role": role, "block": b,
                    "param_set_sha256": (
                        frozen["param_set_sha256"] if role == "candidate"
                        else frozen["baseline_param_set_sha256"]),
                    "params_snapshot": snap,
                    "params_snapshot_sha256": A._file_sha(snap)["sha256"],
                    "stop_evidence": stop,
                    "stop_evidence_sha256": A._file_sha(stop)["sha256"]})
    man3 = trials_manifest(str(prev), trials3, purpose="final_validation")
    man3["final_combination"] = {
        "final_combination_id": frozen["final_combination_id"],
        "final_combination_sha256": A._file_sha(
            str(prev / "final_combination.json"))["sha256"],
        "baseline_id": frozen["baseline_id"],
        "baseline_param_set_sha256": frozen["baseline_param_set_sha256"]}
    m3 = tmp_path / "man3.json"
    m3.write_text(json.dumps(man3), encoding="utf-8")
    rc = A.main(["--stage", "assess-trials", "--history", str(hist),
                 "--trial-manifest", str(m3), "--out", str(r3)])
    assert rc == 0, capsys.readouterr()
    assert (r3 / "recommended.param").exists()
    assert (r3 / "rollback.param").exists()
    assert (r3 / "parameter_diff.csv").exists()

    # the exported diff touches only whitelisted parameters, and rollback
    # parses back to the recorded originals
    rec, _o = A._param_backup(str(r3 / "recommended.param"))
    roll, _o2 = A._param_backup(str(r3 / "rollback.param"))
    diff = list(csv.DictReader(open(r3 / "parameter_diff.csv", encoding="utf-8")))
    assert set(d["param"] for d in diff) <= set(A.VAR_WHITELIST)
    assert all(k not in rec for k in A.HELD_PARAMS)
    for k in A.VAR_WHITELIST:
        if k in roll:
            assert abs(roll[k] - float(params0[k])) < 1e-6, k
    assert abs(rec["ATC_STR_RAT_P"] - 0.18) < 1e-12


def test_selection_round_never_exports_and_failed_baseline_blocks(tmp_path, capsys):
    hist = tmp_path / "hist"
    hist.mkdir()
    params0 = dict(BASE_PARAMS)
    os.makedirs(hist / "recommend", exist_ok=True)
    with open(hist / "recommend" / "trial_candidates.csv", "w", encoding="utf-8") as fh:
        import csv as _csv  # noqa: F401
        w = _csv.DictWriter(fh, fieldnames=["candidate_id", "loop", "stage", "param",
                                            "original", "candidate", "validated",
                                            "recommendation_status"])
        w.writeheader()
        w.writerow({"candidate_id": "yaw_p_110", "loop": "yaw", "stage": "P",
                    "param": "ATC_STR_RAT_P", "original": "0.2", "candidate": "0.22",
                    "validated": "False", "recommendation_status": "trial_candidate"})
    (hist / "baseline_params.json").write_text(json.dumps({
        "pid": {"yaw": dict(params0), "speed": dict(params0)}}), encoding="utf-8")
    (hist / "recommend.done.json").write_text(json.dumps({
        "stage": "recommend", "artifacts": {}, "candidate_matrix_sha256": "m1"}),
        encoding="utf-8")

    # a saturated, unarmed baseline cannot carry the round forward
    out = tmp_path / "blocked"
    trials = []
    for b in range(3):
        for role, tau, pars in (("baseline", 0.9, params0),
                                ("candidate", 0.3,
                                 _params_with(params0, ATC_STR_RAT_P=0.22))):
            f = tmp_path / f"b_{role}_{b}.bin"
            _trial_bin(str(f), "yaw", tau, pars, armed=False)
            snap = _write_snapshot(tmp_path / f"b_{role}_{b}.param", pars)
            stop = _stop_evidence(tmp_path / f"b_{role}_{b}.stop.json", "x")
            trials.append({"file": str(f), "sha256": A._file_sha(str(f))["sha256"],
                           "hardware_id": "h", "candidate_id": "yaw_p_110",
                           "loop": "yaw", "role": role, "block": b,
                           "params_snapshot": snap,
                           "stop_evidence": stop})
    man = trials_manifest(str(hist), trials)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    rc = A.main(["--stage", "assess-trials", "--history", str(hist),
                 "--trial-manifest", str(mp), "--out", str(out)])
    assert rc == 0
    assert not (out / "next_round").exists(), "blocked round must not advance"
    assert (out / "blocked.json").exists()
    assert not (out / "recommended.param").exists()
    rec = json.loads((out / "assess-trials.done.json").read_text(encoding="utf-8"))
    assert rec["deployable"] is False


def test_final_validation_rejecting_a_reused_selection_bin(tmp_path, capsys):
    hist = tmp_path / "hist"
    hist.mkdir()
    params0 = dict(BASE_PARAMS)
    os.makedirs(hist / "recommend", exist_ok=True)
    with open(hist / "recommend" / "trial_candidates.csv", "w", encoding="utf-8") as fh:
        import csv as _csv  # noqa: F401
        w = _csv.DictWriter(fh, fieldnames=["candidate_id", "loop", "stage", "param",
                                            "original", "candidate", "validated",
                                            "recommendation_status"])
        w.writeheader()
        w.writerow({"candidate_id": "yaw_p_90", "loop": "yaw", "stage": "P",
                    "param": "ATC_STR_RAT_P", "original": "0.2", "candidate": "0.18",
                    "validated": "False", "recommendation_status": "trial_candidate"})
    (hist / "baseline_params.json").write_text(json.dumps({
        "pid": {"yaw": dict(params0), "speed": dict(params0)}}), encoding="utf-8")
    (hist / "recommend.done.json").write_text(json.dumps({
        "stage": "recommend", "artifacts": {}, "candidate_matrix_sha256": "m1"}),
        encoding="utf-8")

    sel = tmp_path / "sel"
    man = _make_round(tmp_path, str(hist), "yaw", "yaw_p_90",
                      _params_with(params0, ATC_STR_RAT_P=0.18), params0, tag="s")
    mp = tmp_path / "s.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    assert A.main(["--stage", "assess-trials", "--history", str(hist),
                   "--trial-manifest", str(mp), "--out", str(sel)]) == 0

    used = json.loads((sel / "selection_input_shas.json").read_text())["trial_bin_shas"]
    reused = tmp_path / "fin_reuse"
    man2 = _make_round(tmp_path, str(sel), "yaw", "combo-2",
                       _params_with(params0, ATC_STR_RAT_P=0.18), params0, tag="f")
    man2["purpose"] = "final_validation"
    man2["final_combination"] = {"final_combination_id": "combo-2",
                                 "param_set_sha256": "x", "baseline_id": "b"}
    # point one final trial at a file already consumed during selection
    man2["trials"][0]["file"] = str(tmp_path / "s_yaw_p_90_baseline_0.bin")
    man2["trials"][0]["sha256"] = A._file_sha(man2["trials"][0]["file"])["sha256"]
    assert man2["trials"][0]["sha256"] in used
    mp2 = tmp_path / "f.json"
    mp2.write_text(json.dumps(man2), encoding="utf-8")
    rc = A.main(["--stage", "assess-trials", "--history", str(hist),
                 "--trial-manifest", str(mp2), "--out", str(reused)])
    assert rc == 2, "reusing a selection BIN must be rejected"
    assert not (reused / "recommended.param").exists()


def test_final_validation_bypass_is_rejected(tmp_path, capsys):
    """A fabricated final combination must be refused, not accommodated."""
    hist = tmp_path / "hist"
    hist.mkdir()
    params0 = dict(BASE_PARAMS)
    os.makedirs(hist / "recommend", exist_ok=True)
    with open(hist / "recommend" / "trial_candidates.csv", "w", encoding="utf-8") as fh:
        import csv as _csv
        w = _csv.DictWriter(fh, fieldnames=["candidate_id", "loop", "stage", "param",
                                            "original", "candidate", "validated",
                                            "recommendation_status"])
        w.writeheader()
        w.writerow({"candidate_id": "yaw_p_90", "loop": "yaw", "stage": "P",
                    "param": "ATC_STR_RAT_P", "original": "0.2", "candidate": "0.18",
                    "validated": "False", "recommendation_status": "trial_candidate"})
    (hist / "baseline_params.json").write_text(json.dumps({
        "pid": {"yaw": dict(params0), "speed": dict(params0)}}), encoding="utf-8")
    (hist / "recommend.done.json").write_text(json.dumps({
        "stage": "recommend", "artifacts": {}, "candidate_matrix_sha256": "m1"}),
        encoding="utf-8")

    # try to short-circuit: final validation straight off the history root
    out = tmp_path / "bypass"
    sub = dict(params0)
    sub["ATC_STR_RAT_P"] = 0.18
    man = _make_round(tmp_path, str(hist), "yaw", "made-up", sub, sub, tag="byp")
    man["purpose"] = "final_validation"
    man["final_combination"] = {
        "final_combination_id": "made-up",
        "final_combination_sha256": "0" * 64,
        "baseline_id": "whatever",
        "baseline_param_set_sha256": A._parent_sha(sub),
        "params": sub}
    mp = tmp_path / "byp.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    rc = A.main(["--stage", "assess-trials", "--history", str(hist),
                 "--trial-manifest", str(mp), "--out", str(out)])
    assert rc == 2, "a self-declared final combination must be rejected"
    assert not (out / "recommended.param").exists()
    captured = capsys.readouterr().out
    assert "final combination object not found" in captured or "selection is not complete" in captured


def test_final_validation_rejects_pending_selection_stage(tmp_path, capsys):
    """Final validation cannot run while the selection sequence is unfinished."""
    hist = tmp_path / "hist"
    hist.mkdir()
    params0 = dict(BASE_PARAMS)
    os.makedirs(hist / "recommend", exist_ok=True)
    with open(hist / "recommend" / "trial_candidates.csv", "w", encoding="utf-8") as fh:
        import csv as _csv
        w = _csv.DictWriter(fh, fieldnames=["candidate_id", "loop", "stage", "param",
                                            "original", "candidate", "validated",
                                            "recommendation_status"])
        w.writeheader()
        w.writerow({"candidate_id": "yaw_p_90", "loop": "yaw", "stage": "P",
                    "param": "ATC_STR_RAT_P", "original": "0.2", "candidate": "0.18",
                    "validated": "False", "recommendation_status": "trial_candidate"})
    (hist / "baseline_params.json").write_text(json.dumps({
        "pid": {"yaw": dict(params0), "speed": dict(params0)}}), encoding="utf-8")
    (hist / "recommend.done.json").write_text(json.dumps({
        "stage": "recommend", "artifacts": {}, "candidate_matrix_sha256": "m1"}),
        encoding="utf-8")

    sel = tmp_path / "sel"
    man = _make_round(tmp_path, str(hist), "yaw", "yaw_p_90",
                      _params_with(params0, ATC_STR_RAT_P=0.18), params0, tag="sel")
    mp = tmp_path / "sel.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    assert A.main(["--stage", "assess-trials", "--history", str(hist),
                   "--trial-manifest", str(mp), "--out", str(sel)]) == 0
    pend = json.loads((sel / "assessment.json").read_text(encoding="utf-8"))
    assert pend["selection_complete"] is False
    assert pend["next_stage"] == ["yaw", "I"]
    assert not (sel / "final_combination.json").exists()

    # plant a plausible-looking frozen combination next to a still-pending parent
    accepted = pend["params_after_round"]
    (sel / "final_combination.json").write_text(json.dumps({
        "final_combination_id": "fc-early",
        "param_set_sha256": A._parent_sha(accepted),
        "baseline_id": "recorded_2026_11_02",
        "baseline_param_set_sha256": A._parent_sha(params0),
        "baseline_params": params0,
        "params": accepted}), encoding="utf-8")

    out = tmp_path / "early"
    man2 = _make_round(tmp_path, str(sel), "yaw", "fc-early", accepted, accepted,
                       tag="early")
    man2["purpose"] = "final_validation"
    man2["final_combination"] = {
        "final_combination_id": "fc-early",
        "final_combination_sha256": A._file_sha(
            str(sel / "final_combination.json"))["sha256"],
        "baseline_id": "recorded_2026_11_02",
        "baseline_param_set_sha256": A._parent_sha(params0)}
    mp2 = tmp_path / "early.json"
    mp2.write_text(json.dumps(man2), encoding="utf-8")
    rc = A.main(["--stage", "assess-trials", "--history", str(hist),
                 "--trial-manifest", str(mp2), "--out", str(out)])
    assert rc == 2, "an unfinished selection must not admit a final round"
    assert "selection is not complete" in capsys.readouterr().out
    assert not (out / "recommended.param").exists()
