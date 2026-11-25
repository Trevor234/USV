#!/usr/bin/env python3
"""2026-11-02 joint USV hydrodynamic/thruster re-identification.

Single orchestration entry for the 2026-11-02 water-test data plus the earlier
logs.  Three stages consume only frozen artifacts of the previous stage:

    --stage prepare    inventory + SHA256 + verified copy + parse + segments + split
    --stage fit        layered identification, model selection, bootstrap, inertia sweep
    --stage validate   independent replay, physical gates, parameter package

Never writes to the raw log trees, never touches the live ROS configuration and
never starts a water test.  All derived products go under ``--out``.

Conventions (unchanged from ``scripts/scripts/real_usv_param_id.py``):
  x = East (XKF1.PE), y = North (XKF1.PN), psi = pi/2 - yaw_NED
  u = VN*cos(yaw) + VE*sin(yaw)
  v = VN*sin(yaw) - VE*cos(yaw)      (ROS body FLU: +v to port)
  r = -GyrZ
The plant ODE mirrors ``usv_mpc_cpp/src/usv_model_dynamic.cpp``:
  M = [[m11,0,0],[0,m22,m23],[0,m32,m33]], tau = [TL+TR, 0, d*(TR-TL)]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_log  # noqa: E402

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
GRID_HZ = 20.0
DT = 1.0 / GRID_HZ
LIN_WIN_S = 1.0
PATCH_S = 5.0
REPLAY_WIN_S = 10.0
CTRL_REFRESH_S = 0.2          # 5 Hz MPC outer step, 0.05 s RK4 inside
PWM_MAX_AGE_S = 0.5
PWM_DEADZONE_US = 30.0        # prior, NOT identified
EXCL_PAD_S = 2.0
SWITCH_PAD_S = 1.0
GAP_PAD_S = 1.0
ROLL_LIM_DEG = 10.0
PITCH_LIM_DEG = 15.0
HEADING_RMSE_LIM = math.radians(10.0)
GPS_MIN_STATUS = 3
GPS_MAX_HDOP = 1.0
SPIN_RATE = math.radians(30.0)
STRAIGHT_R_LIM = 0.15
STRAIGHT_V_LIM = 0.2
STRAIGHT_MIN_S = 5.0
COAST_PWM_TOL_US = 30.0
COAST_MIN_S = 4.0
U_SCALE = 0.2                 # m/s
R_SCALE = math.radians(12.0)  # rad/s
BOOTSTRAP_N = 200
BOOTSTRAP_SEED = 42
COND_LIM = 1e6
MOTOR_FUNCTIONS = {73: "left", 74: "right"}

# ArduRover mode numbers -> names
ROVER_MODES = {0: "MANUAL", 1: "ACRO", 3: "STEERING", 4: "HOLD", 5: "LOITER",
               6: "FOLLOW", 7: "SIMPLE", 9: "CIRCLE", 10: "AUTO", 11: "RTL",
               12: "SMART_RTL", 15: "GUIDED", 16: "INITIALISING"}

# role table: (date-directory, basename) -> role
TODAY_TRAIN = "2026-11-02 15-31-04.bin"
TODAY_SELECT = "2026-11-02 16-00-09.bin"
TODAY_BLIND = "2026-11-02 16-19-57.bin"
# Provenance of the holdout.  The frozen split is unchanged, but the blind file
# was already scored once by the superseded run named below, so results from any
# later pass must not be described as an untouched blind test.  No acceptance
# threshold was altered in response to that first look.
HOLDOUT_EXPOSURE = {
    "file": "2026-11-02 16-19-57.bin",
    "status": "reused_after_prior_exposure",
    "prior_run": "reidentification_20261102_v6",
    "prior_verdict": "rejected",
    "note": ("split frozen before fitting and unchanged; only a model-selection "
             "leak in the historical transfer check was fixed, no gate was changed"),
}

# Frozen provenance of the three 2026-11-02 navigation logs (plan verification
# table).  Ingestion must compare against THESE, not merely against its own
# second read, otherwise a silently changed source would be accepted.
EXPECTED_SOURCES = {
    "2026-11-02 15-31-04.bin": (
        "7415f212b32ba8574cb35bdd53bbf3b7f0a3475aa1e84f70ec1ff48e1cacaec2", 27721728),
    "2026-11-02 16-00-09.bin": (
        "6c6c124402ca807a500b11a55c2444e05a1a43e7b836f5929cec54bd5e2d63fd", 31293440),
    "2026-11-02 16-19-57.bin": (
        "d9ea15ece3447354da5e682c13c2e09d9653c57da2e725e0c0f0d9b02815f68e", 21594112),
}

HIST_ROLES = {
    "2026-09-03 15-39-42.bin": "diagnostic",
    "2026-09-03 16-12-04.bin": "history_replay",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def wrap_pi(a):
    return np.arctan2(np.sin(a), np.cos(a))


def sha256_stream(fh, chunk=1 << 22):
    h = hashlib.sha256()
    n = 0
    while True:
        b = fh.read(chunk)
        if not b:
            break
        n += len(b)
        h.update(b)
    return h.hexdigest(), n


def sha256_file(path):
    with open(path, "rb") as fh:
        return sha256_stream(fh)


def trapz(y, dt, axis=-1):
    """Trapezoidal integral along ``axis`` (default: the time axis last).

    Callers that store (time, channel) arrays must pass ``axis=0``; collapsing
    the channel axis instead would give every channel the same integral.
    """
    y = np.moveaxis(np.asarray(y, dtype=float), axis, -1)
    if y.shape[-1] < 2:
        return np.zeros(y.shape[:-1])
    return (0.5 * (y[..., 0] + y[..., -1]) + np.sum(y[..., 1:-1], axis=-1)) * dt


def zoh_lookup(t_src, values, t_dst, max_age=None):
    """Zero-order hold with explicit sample age.  Returns (values, age)."""
    if t_src.size == 0:
        out = np.full(t_dst.shape, np.nan)
        return out, np.full(t_dst.shape, np.inf)
    idx = np.searchsorted(t_src, t_dst, side="right") - 1
    valid = idx >= 0
    idx_c = np.clip(idx, 0, t_src.size - 1)
    out = np.asarray(values[idx_c], dtype=float)
    out[~valid] = np.nan
    age = np.where(valid, t_dst - t_src[idx_c], np.inf)
    if max_age is not None:
        out[age > max_age] = np.nan
    return out, age


def interp_angle(t_src, ang, t_dst):
    """Circular interpolation via sin/cos (handles +-pi wraparound)."""
    if t_src.size < 2:
        return np.full(t_dst.shape, np.nan)
    s = np.interp(t_dst, t_src, np.sin(ang))
    c = np.interp(t_dst, t_src, np.cos(ang))
    return np.arctan2(s, c)


def interp_linear(t_src, v, t_dst):
    if t_src.size < 2:
        return np.full(t_dst.shape, np.nan)
    return np.interp(t_dst, t_src, v)


def interp_linear_gapped(t_src, v, t_dst, max_age):
    """Linear interpolation that refuses to bridge a source gap.

    A value is produced only when ``t_dst`` is bracketed by two source samples
    no further apart than ``max_age``; otherwise NaN.  This keeps a state
    fallback (e.g. POS) from being interpolated across an outage or
    extrapolated past the record.
    """
    t_src = np.asarray(t_src, dtype=float)
    v = np.asarray(v, dtype=float)
    out = np.full(np.shape(t_dst), np.nan)
    if t_src.size < 2:
        return out
    order = np.argsort(t_src)
    t_src, v = t_src[order], v[order]
    left = np.searchsorted(t_src, t_dst, side="right") - 1
    ok = (left >= 0) & (left < t_src.size - 1)
    idx = np.clip(left, 0, t_src.size - 2)
    span = t_src[idx + 1] - t_src[idx]
    ok &= np.isfinite(span) & (span <= max_age)
    if ok.any():
        t0 = t_src[idx[ok]]
        t1 = t_src[idx + 1][ok]
        v0 = v[idx[ok]]
        v1 = v[idx + 1][ok]
        w = np.where(t1 > t0, (t_dst[ok] - t0) / np.maximum(t1 - t0, 1e-12), 0.0)
        out[ok] = v0 + w * (v1 - v0)
    return out


def merge_intervals(iv):
    if not iv:
        return []
    iv = sorted(iv)
    out = [list(iv[0])]
    for a, b in iv[1:]:
        if a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def in_intervals(t, iv):
    m = np.zeros(t.shape, dtype=bool)
    for a, b in iv:
        m |= (t >= a) & (t <= b)
    return m


def runs_of(mask, min_len=1):
    """Yield (start_idx, end_idx_exclusive) of True runs."""
    if mask.size == 0:
        return []
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_len]


def robust_polyfit(x, y, deg=2):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < deg + 3:
        return None
    return np.polyfit(x[ok], y[ok], deg)


# ---------------------------------------------------------------------------
# plant model (mirrors the C++ Fossen implementation)
# ---------------------------------------------------------------------------
HYDRO_KEYS = ["mass", "Iz", "xg", "d_thruster", "Xu_dot", "Yv_dot", "Yr_dot",
              "Nv_dot", "Nr_dot", "Xu", "Yv", "Yr", "Nv", "Nr",
              "Xuu", "Yvv", "Yrr", "Nvv", "Nrr"]


def load_baseline(path):
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    root = doc.get("/**", doc)
    rp = root.get("ros__parameters", root)
    veh = dict(rp.get("vehicle", {}))
    thr = dict(rp.get("thruster", {}))
    missing = [k for k in HYDRO_KEYS if k not in veh]
    if missing:
        raise SystemExit(f"baseline {path} misses vehicle keys: {missing}")
    p = {k: float(veh[k]) for k in HYDRO_KEYS}
    p["thruster"] = {k: float(v) for k, v in thr.items()}
    p["_raw"] = rp
    return p


def hydro_matrix(p):
    m11 = p["mass"] - p["Xu_dot"]
    m22 = p["mass"] - p["Yv_dot"]
    m23 = p["mass"] * p["xg"] - p["Yr_dot"]
    m32 = p["mass"] * p["xg"] - p["Nv_dot"]
    m33 = p["Iz"] - p["Nr_dot"]
    return m11, m22, m23, m32, m33


def deriv(state, tau, p):
    """Continuous Fossen ODE; state (...,6) = [x,y,psi,u,v,r]."""
    psi = state[..., 2]
    u = state[..., 3]
    v = state[..., 4]
    r = state[..., 5]
    m11, m22, m23, m32, m33 = hydro_matrix(p)
    c13 = -m22 * v - m23 * r
    c23 = m11 * u
    cn = np.stack([c13 * r, c23 * r, -c13 * u - c23 * v], axis=-1)
    dn = np.stack([
        (-p["Xu"] - p["Xuu"] * np.abs(u)) * u,
        (-p["Yv"] - p["Yvv"] * np.abs(v)) * v + (-p["Yr"] - p["Yrr"] * np.abs(r)) * r,
        (-p["Nv"] - p["Nvv"] * np.abs(v)) * v + (-p["Nr"] - p["Nrr"] * np.abs(r)) * r,
    ], axis=-1)
    # tau = [TL+TR, 0, d*(TR-TL)] already assembled by the caller
    shape = state.shape
    flat = np.concatenate([state.reshape(-1, 6), tau.reshape(-1, 3)], axis=1)
    M = np.zeros((flat.shape[0], 3, 3))
    M[:, 0, 0] = m11
    M[:, 1, 1] = m22
    M[:, 1, 2] = m23
    M[:, 2, 1] = m32
    M[:, 2, 2] = m33
    rhs = flat[:, 6:9] - cn.reshape(-1, 3) - dn.reshape(-1, 3)
    nu_dot = np.linalg.solve(M, rhs[:, :, None])[:, :, 0]
    cp = np.cos(psi).reshape(-1)
    sp = np.sin(psi).reshape(-1)
    eta_dot = np.stack([cp * u.reshape(-1) - sp * v.reshape(-1),
                        sp * u.reshape(-1) + cp * v.reshape(-1),
                        r.reshape(-1)], axis=-1)
    return np.concatenate([eta_dot, nu_dot], axis=-1).reshape(shape)


def simulate(x0, tau_seq, p, dt=DT):
    """RK4 over a batch of patches.  x0 (N,6), tau_seq (N,K,3) -> (N,K+1,6)."""
    x0 = np.atleast_2d(np.asarray(x0, float))
    tau_seq = np.asarray(tau_seq, float)
    if tau_seq.ndim == 2:
        tau_seq = tau_seq[None, ...]
    n, steps = tau_seq.shape[0], tau_seq.shape[1]
    x = x0.copy()
    out = np.empty((n, steps + 1, 6))
    out[:, 0, :] = x
    for k in range(steps):
        tk = tau_seq[:, k, :]
        k1 = deriv(x, tk, p)
        k2 = deriv(x + 0.5 * dt * k1, tk, p)
        k3 = deriv(x + 0.5 * dt * k2, tk, p)
        k4 = deriv(x + dt * k3, tk, p)
        x = x + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        x[:, 2] = wrap_pi(x[:, 2])
        out[:, k + 1, :] = x
    return out


def thrust_from_q(q, gains):
    """q (...,4) = [L+, L-, R+, R-] magnitudes already direction-split."""
    q = np.asarray(q, float)
    out = np.zeros(q.shape[:-1])
    for i in range(4):
        out = out + gains[i] * q[..., i]
    return out


def tau_from_q(q, gains, d):
    """q (N,K,4) -> tau (N,K,3).  Columns: qL+, qL-, qR+, qR-."""
    tl = gains[0] * q[..., 0] + gains[1] * q[..., 1]
    tr = gains[2] * q[..., 2] + gains[3] * q[..., 3]
    return np.stack([tl + tr, np.zeros_like(tl), d * (tr - tl)], axis=-1)


def direction_split(qn):
    """normalised command (N,K) -> (N,K,4) [pos, neg] per side."""
    qn = np.asarray(qn, float)
    pos = np.maximum(qn, 0.0) ** 2
    neg = np.maximum(-qn, 0.0) ** 2
    return pos, neg


def pwm_to_normalized(pwm, lo, trim, hi, deadzone=PWM_DEADZONE_US):
    pwm = np.asarray(pwm, float)
    n = np.zeros_like(pwm)
    up = pwm > trim + deadzone
    dn = pwm < trim - deadzone
    denom_up = hi - trim - deadzone
    denom_dn = trim - lo - deadzone
    if denom_up > 0:
        n[up] = (pwm[up] - trim - deadzone) / denom_up
    if denom_dn > 0:
        n[dn] = (pwm[dn] - trim + deadzone) / denom_dn
    return np.clip(n, -1.0, 1.0)


def gps_to_local_enu(lat, lon):
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    ok = np.isfinite(lat) & np.isfinite(lon)
    if ok.sum() < 2:
        return np.full(lat.shape, np.nan), np.full(lat.shape, np.nan)
    lat0 = lat[ok][0]
    lon0 = lon[ok][0]
    r = 6371000.0
    north = np.radians(lat - lat0) * r
    east = np.radians(lon - lon0) * r * math.cos(math.radians(lat0))
    return east, north


# ---------------------------------------------------------------------------
# source ingest
# ---------------------------------------------------------------------------
def verified_copy(src, dst, expected_sha=None, opener=None):
    """Sequential-only read of ``src``, verified copy to ``dst``.

    The 2026-11-02 tree rejects seek (ESTALE), so the source is read strictly
    forward; the copy is re-hashed before use.  ``opener`` exists so the
    forward-only property can be exercised against a handle that refuses seek.
    Returns metadata dict.
    """
    opener = open if opener is None else opener
    h = hashlib.sha256()
    n = 0
    with opener(src, "rb") as fh:
        with open(dst, "wb") as out:
            while True:
                b = fh.read(1 << 22)
                if not b:
                    break
                n += len(b)
                h.update(b)
                out.write(b)
    sha = h.hexdigest()
    size = os.path.getsize(src)
    meta = {"source": src, "bytes_read": n, "stat_bytes": size, "sha256": sha}
    if n != size:
        meta["error"] = "stream_interrupted"
        return meta
    if expected_sha is not None and expected_sha != sha:
        meta["error"] = "source_changed"
        return meta
    sha2, n2 = sha256_file(dst)
    if sha2 != sha or n2 != n:
        meta["error"] = "copy_verify_failed"
        return meta
    return meta


def parse_source_to_npz(src, npz_path, expected_sha=None):
    """Copy -> verify -> parse.  Never mutates the source tree."""
    tmpd = tempfile.mkdtemp(prefix="usv-reid-")
    try:
        local = os.path.join(tmpd, "copy.bin")
        meta = verified_copy(src, local, expected_sha=expected_sha)
        if "error" in meta:
            return None, meta
        n_msg, summary, field_report = parse_log.parse(local, npz_path)
        meta["n_msg"] = n_msg
        meta["msg_counts"] = summary
        meta["fields_present"] = {t: [f for f, ok in fs.items() if ok]
                                  for t, fs in field_report.items()}
        return np.load(npz_path, allow_pickle=True), meta
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


# ---------------------------------------------------------------------------
# per-file dataset construction (deterministic: prepare/fit/validate agree)
# ---------------------------------------------------------------------------
def _gap_threshold(t):
    if t.size < 3:
        return 1.0
    d = np.diff(t)
    d = d[d > 0]
    if d.size == 0:
        return 1.0
    return float(min(1.0, max(0.5, 3.0 * np.median(d))))


def _stream_gap_threshold(t):
    """Gap threshold for slow auxiliary streams (GPS health, POS fallback).

    Same relative form, but the 1 s ceiling is never allowed to fall below the
    stream's own three-sample cadence: a 1 Hz GPS legitimately has ~1.07 s
    spacing and that is not missing data.
    """
    t = np.asarray(t, dtype=float)
    if t.size < 3:
        return 1.0
    d = np.diff(t)
    d = d[d > 0]
    if d.size == 0:
        return 1.0
    return float(max(_gap_threshold(t), 3.0 * float(np.median(d))))


def _gaps(t, thr=None):
    iv = []
    if t.size < 2:
        return iv
    d = np.diff(t)
    thr = _gap_threshold(t) if thr is None else thr
    for i in np.where(d > thr)[0]:
        iv.append((float(t[i]), float(t[i + 1])))
    return iv


def _gaps_thr(t, thr):
    """Gaps in ``t`` whose spacing exceeds ``thr`` seconds."""
    if t.size < 2:
        return []
    d = np.diff(t)
    return [(float(t[i]), float(t[i + 1])) for i in np.where(d > thr)[0]]


def _params_dict(z):
    names = list(z["PARM.Name"]) if "PARM.Name" in z else []
    vals = np.asarray(z["PARM.Value"]) if "PARM.Value" in z else np.array([])
    times = np.asarray(z["PARM.TimeUS"]) if "PARM.TimeUS" in z else np.array([])
    hist, cur = [], {}
    for i, nm in enumerate(names):
        v = float(vals[i]) if i < vals.size else float("nan")
        t = float(times[i]) / 1e6 if i < times.size else float("nan")
        hist.append((t, str(nm), v))
        cur[str(nm)] = v
    return cur, hist


VOLATILE_PARM = ("STAT_RUNTIME", "STAT_FLTTIME", "STAT_FLTCNT", "STAT_BOOTCNT",
                 "BARO1_GND_PRESS", "BARO2_GND_PRESS", "BARO_GND_PRESS")


def _parm_changes(hist):
    seen, out = {}, []
    for t, nm, v in hist:
        if nm.startswith(VOLATILE_PARM):
            continue
        if nm in seen and seen[nm] != v:
            out.append({"t_s": round(t, 3), "name": nm, "from": seen[nm], "to": v})
        seen[nm] = v
    return out


def _routing(z, params):
    """Resolve thruster channels from SERVOx_FUNCTION; returns dict or None."""
    left = right = None
    for ch in range(1, 17):
        fn = params.get(f"SERVO{ch}_FUNCTION")
        if fn is None:
            continue
        if int(round(fn)) == 73 and left is None:
            left = ch
        elif int(round(fn)) == 74 and right is None:
            right = ch
    if left is None or right is None:
        return None
    out = {"left_ch": left, "right_ch": right, "conflict": False, "notes": []}
    for side, ch in (("left", left), ("right", right)):
        lo = params.get(f"SERVO{ch}_MIN")
        tr = params.get(f"SERVO{ch}_TRIM")
        hi = params.get(f"SERVO{ch}_MAX")
        rev = params.get(f"SERVO{ch}_REVERSED", 0.0)
        if lo is None or tr is None or hi is None:
            out["conflict"] = True
            out["notes"].append(f"SERVO{ch}_MIN/TRIM/MAX missing")
            continue
        out[f"{side}_min"] = lo
        out[f"{side}_trim"] = tr
        out[f"{side}_max"] = hi
        out[f"{side}_reversed"] = int(round(rev))
    if "left_trim" not in out or "right_trim" not in out:
        out["conflict"] = True
    return out


def _select_imu(z, params):
    """Choose one IMU instance; cross-check it against the ATT heading rate.

    The comparison is deliberately robust (median absolute error): the logs
    contain EKF yaw realignments that produce a handful of huge single-sample
    residuals, which would wreck an RMSE-based gate even when the two sensors
    agree to ~1.6 deg/s everywhere else.  The strict per-run gate lives in
    ``build_dataset``; here we only reject a genuinely inconsistent pair.
    """
    if "IMU.TimeUS" not in z or z["IMU.TimeUS"].size == 0:
        return None, "no_imu"
    t_all = np.asarray(z["IMU.TimeUS"]) / 1e6
    inst = np.asarray(z["IMU.I"])
    att_t = np.asarray(z["ATT.TimeUS"]) / 1e6
    att_yaw = np.radians(np.asarray(z["ATT.Yaw"]))
    ok_att = np.isfinite(att_yaw)
    preferred = params.get("EK3_PRIMARY", 0.0)
    uniq = [u for u in np.unique(inst) if np.isfinite(u)]
    if not uniq:
        return None, "no_imu_instance"
    cands = []
    for u in sorted(uniq):
        m = inst == u
        t = t_all[m]
        gz = np.asarray(z["IMU.GyrZ"])[m]
        if t.size < 50:
            continue
        med, nex = math.inf, 0
        if ok_att.sum() >= 50 and t.size > 10:
            g = np.arange(t[0] + 1.0, t[-1] - 1.0, 0.1)
            if g.size >= 20:
                yaw = interp_angle(att_t[ok_att], att_yaw[ok_att], g)
                gy = interp_linear(t, gz, g)
                dpsi = np.gradient(np.unwrap(yaw), 0.1)
                good = np.isfinite(dpsi) & np.isfinite(gy) & (np.abs(dpsi) > 0.1)
                nex = int(good.sum())
                if nex >= 20:
                    med = float(np.median(np.abs(dpsi[good] - gy[good])))
        cands.append((u, med, nex))
    if not cands:
        return None, "no_imu_instance"
    # prefer the primary instance; among equally consistent ones, keep it.
    cands.sort(key=lambda c: (c[1] > HEADING_RMSE_LIM,
                              c[1] if np.isfinite(c[1]) else math.inf,
                              c[0] != preferred, c[0]))
    u, med, nex = cands[0]
    info = {"instance": u, "median_heading_err": (None if not np.isfinite(med) else med),
            "n_excited": nex,
            "candidates": [{"instance": float(a),
                            "median_heading_err": (None if not np.isfinite(b) else b),
                            "n_excited": int(c)} for a, b, c in cands]}
    if nex < 20:
        # no excitation in this log (idle / bench); not a sensor fault
        info["note"] = "no_heading_excitation"
        return info, None
    if not np.isfinite(med) or med > HEADING_RMSE_LIM:
        return info, f"imu_heading_mismatch(med={med:.4f})"
    return info, None


def _select_core(z):
    """Primary EKF core from XKF4.PI, cut at switches; ATT fallback otherwise."""
    t1 = np.asarray(z["XKF1.TimeUS"]) / 1e6
    c1 = np.asarray(z["XKF1.C"])
    if t1.size == 0:
        return None, "no_xkf1"
    t4 = np.asarray(z["XKF4.TimeUS"]) / 1e6
    pi4 = np.asarray(z["XKF4.PI"]) if "XKF4.PI" in z else np.array([])
    c4 = np.asarray(z["XKF4.C"]) if "XKF4.C" in z else np.array([])
    switches = []
    if pi4.size and np.isfinite(pi4).any():
        # dedupe on TimeUS (each core logs the same PI at the same instant)
        _, first = np.unique(t4, return_index=True)
        first = np.sort(first)
        tt = t4[first]
        pp = pi4[first]
        ok = np.isfinite(pp)
        tt, pp = tt[ok], pp[ok]
        cur = None
        for ti, pi in zip(tt, pp):
            if cur is None or pi != cur:
                if cur is not None:
                    switches.append(float(ti))
                cur = pi
        mode = "xkf4_pi"
    else:
        # fallback: pick the single core closest to ATT yaw
        att_t = np.asarray(z["ATT.TimeUS"]) / 1e6
        att_yaw = np.radians(np.asarray(z["ATT.Yaw"]))
        g = np.arange(max(att_t[0], t1[0]) + 1, min(att_t[-1], t1[-1]) - 1, 0.1)
        ref = interp_angle(att_t, att_yaw, g) if att_t.size > 2 else np.zeros(g.shape)
        best, best_d = None, math.inf
        for c in sorted(set(np.unique(c1))):
            m = c1 == c
            if m.sum() < 50:
                continue
            yaw = np.radians(np.asarray(z["XKF1.Yaw"])[m])
            fit = interp_angle(t1[m], yaw, g)
            d = float(np.median(np.abs(wrap_pi(fit - ref))))
            if d < best_d:
                best, best_d = c, d
        if best is None or best_d > math.radians(5.0):
            return None, f"core_indeterminate(dist={best_d})"
        mode = f"att_fallback(C={best},med={best_d:.4f})"
        c1 = np.where(c1 == best, c1, np.nan)
    return {"mode": mode, "switches": switches, "cores": c1,
            "primary_series": (t4, pi4) if pi4.size else None}, None


def _core_mask(t_grid, primary_series, c1_t, c1_core):
    """Select XKF1 rows whose core equals PI at that instant."""
    t4, pi4 = primary_series
    if t4.size == 0:
        return np.isfinite(c1_core)
    _, first = np.unique(t4, return_index=True)
    first = np.sort(first)
    tt, pp = t4[first], pi4[first]
    idx = np.clip(np.searchsorted(tt, c1_t, side="right") - 1, 0, tt.size - 1)
    want = pp[idx]
    return np.isfinite(c1_core) & np.isfinite(want) & (c1_core == want)


@dataclass
class Segment:
    sid: str
    t0: float
    t1: float
    group: str = ""
    terms: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    t: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    x: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))       # (n,6)
    ui: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))      # (n,4) q pos/neg per side
    pwm: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))     # (n,2)
    rpm: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))     # (n,2) or empty
    mode: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    labels: np.ndarray = field(repr=False, default_factory=lambda: np.array([], dtype=object))
    reason: str = ""

    def __post_init__(self):
        # ``terms`` are the thrust regressors; they live in ``ui`` until a
        # per-group input model replaces them.  Anything that builds a Segment
        # without them would otherwise integrate a 1-D array.
        t = np.asarray(self.terms)
        if t.size == 0:
            self.terms = np.asarray(self.ui)

    def __len__(self):
        return int(self.t.size)


def build_dataset(z, meta, exclusions, cfg):
    """Build 20 Hz masked clean segments for one log.  Pure/deterministic."""
    out = {"file": meta["basename"], "group": meta["group"], "date": meta["date"],
           "role": meta["role"], "segments": [], "reasons": [], "stats": {},
           "mapping_ok": False, "rpm_ok": False, "notes": []}
    if z is None:
        out["reasons"].append("source_unreadable")
        return out
    params, hist = _params_dict(z)
    out["params"] = params
    out["parm_changes"] = _parm_changes(hist)
    out["firmware"] = _firmware(z)
    out["boot_count"] = params.get("STAT_BOOTCNT")

    route = _routing(z, params)
    out["routing"] = route
    if route is None or route["conflict"]:
        out["reasons"].append("mapping_conflict")
        out["notes"].append("SERVOx_FUNCTION 73/74 or MIN/TRIM/MAX unavailable")
    else:
        out["mapping_ok"] = True

    imu, imu_err = _select_imu(z, params)
    out["imu"] = imu
    if imu_err:
        out["reasons"].append(imu_err)
    core, core_err = _select_core(z)
    out["core"] = core if core else None
    if core_err:
        out["reasons"].append(core_err)
    if imu is None or core is None:
        return out

    # ---- stream time bases
    im = np.asarray(z["IMU.I"]) == imu["instance"]
    t_imu = np.asarray(z["IMU.TimeUS"])[im] / 1e6
    gyr = np.asarray(z["IMU.GyrZ"])[im]
    t_att = np.asarray(z["ATT.TimeUS"]) / 1e6
    att_yaw = np.radians(np.asarray(z["ATT.Yaw"]))
    att_roll = np.asarray(z["ATT.Roll"]) if "ATT.Roll" in z else np.full(t_att.shape, np.nan)
    att_pitch = np.asarray(z["ATT.Pitch"])
    t1 = np.asarray(z["XKF1.TimeUS"]) / 1e6
    c1c = np.asarray(z["XKF1.C"])
    if core.get("primary_series") is not None:
        keep_core = _core_mask(None, core["primary_series"], t1, c1c)
    else:
        keep_core = np.isfinite(np.asarray(core["cores"]))
    t_x = t1[keep_core]
    yaw_x = np.radians(np.asarray(z["XKF1.Yaw"])[keep_core])
    vn = np.asarray(z["XKF1.VN"])[keep_core]
    ve = np.asarray(z["XKF1.VE"])[keep_core]
    pe = np.asarray(z["XKF1.PE"])[keep_core] if "XKF1.PE" in z else np.full(t_x.shape, np.nan)
    pn = np.asarray(z["XKF1.PN"])[keep_core] if "XKF1.PN" in z else np.full(t_x.shape, np.nan)
    vacuum = ~np.isfinite(pe) | ~np.isfinite(pn)
    if vacuum.any() and "POS.TimeUS" in z and z["POS.TimeUS"].size:
        pt = np.asarray(z["POS.TimeUS"]) / 1e6
        e_, n_ = gps_to_local_enu(np.asarray(z["POS.Lat"]), np.asarray(z["POS.Lng"]))
        # POS is a state fallback: it must not be interpolated across its own
        # gaps nor extrapolated past either end of its record.
        pos_age = _gap_threshold(pt)
        e_i = interp_linear_gapped(pt, e_, t_x, pos_age)
        n_i = interp_linear_gapped(pt, n_, t_x, pos_age)
        pe = np.where(vacuum, e_i, pe)
        pn = np.where(vacuum, n_i, pn)

    t_rc = np.asarray(z["RCOU.TimeUS"]) / 1e6
    if route is not None and not route["conflict"]:
        pwm_l = np.asarray(z[f"RCOU.C{route['left_ch']}"])
        pwm_r = np.asarray(z[f"RCOU.C{route['right_ch']}"])
    else:
        pwm_l = np.full(t_rc.shape, np.nan)
        pwm_r = np.full(t_rc.shape, np.nan)

    t_mode = np.asarray(z["MODE.TimeUS"]) / 1e6
    mode_num = np.asarray(z["MODE.ModeNum"]) if "MODE.ModeNum" in z else np.array([])
    t_arm = np.asarray(z["ARM.TimeUS"]) / 1e6
    arm_state = np.asarray(z["ARM.ArmState"]) if "ARM.ArmState" in z else np.array([])
    t_vibe = np.asarray(z["VIBE.TimeUS"]) / 1e6
    if "VIBE.IMU" in z and z["VIBE.IMU"].size:
        vm = np.asarray(z["VIBE.IMU"]) == imu["instance"]
        t_vibe, clip = t_vibe[vm], np.asarray(z["VIBE.Clip"])[vm]
    else:
        clip = np.asarray(z["VIBE.Clip"]) if "VIBE.Clip" in z else np.array([])
        if "VIBE.Clip0" in z and clip.size == 0:
            clip = np.asarray(z["VIBE.Clip0"])
    # GPS: prefer the instance with the best fix quality
    gps_status = gps_hdop = gps_yaw = None
    if "GPS.TimeUS" in z and z["GPS.TimeUS"].size:
        gi = np.asarray(z["GPS.I"]) if "GPS.I" in z else np.zeros(z["GPS.TimeUS"].shape)
        best, best_frac = None, -1.0
        for u in np.unique(gi):
            m = gi == u
            st = np.asarray(z["GPS.Status"])[m]
            frac = float(np.mean(st >= GPS_MIN_STATUS)) if st.size else 0.0
            if frac > best_frac:
                best, best_frac = u, frac
        m = gi == best
        gps_status = (np.asarray(z["GPS.TimeUS"])[m] / 1e6, np.asarray(z["GPS.Status"])[m])
        gps_hdop = (np.asarray(z["GPS.TimeUS"])[m] / 1e6, np.asarray(z["GPS.HDop"])[m])

    # ---- RPM availability (evidence only; today has none)
    rpm_series = None
    if "ESC.TimeUS" in z and z["ESC.TimeUS"].size:
        et = np.asarray(z["ESC.TimeUS"]) / 1e6
        ei = np.asarray(z["ESC.Instance"])
        er = np.asarray(z["ESC.RPM"])
        chans = {}
        if route is not None and not route["conflict"]:
            # map ESC instance -> servo channel empirically (correlation)
            cand = {}
            for u in np.unique(ei):
                m = (ei == u) & np.isfinite(er) & (er > 50)
                if m.sum() < 50:
                    continue
                tt, rr = et[m], er[m]
                cl = _corr_with_pwm(tt, rr, t_rc, pwm_l)
                cr = _corr_with_pwm(tt, rr, t_rc, pwm_r)
                if cl is None or cr is None:
                    continue
                cand[u] = (cl, cr)
            for u, (cl, cr) in cand.items():
                if cl > 0.3 and cl > cr:
                    chans.setdefault("left", u)
                elif cr > 0.3 and cr > cl:
                    chans.setdefault("right", u)
            if "left" in chans and "right" in chans and chans["left"] != chans["right"]:
                sup = {}
                for side in ("left", "right"):
                    u = chans[side]
                    m = ei == u
                    tt, rr = et[m], er[m]
                    fin = np.isfinite(rr)
                    sup[side] = {
                        "instance": float(u),
                        "coverage": float(fin.mean()) if fin.size else 0.0,
                        "nonzero_frac": float((rr[fin] > 50).mean()) if fin.any() else 0.0,
                        "rpm_max": float(np.nanmax(rr[fin])) if fin.any() else 0.0,
                        "rpm_std": float(np.nanstd(rr[fin])) if fin.any() else 0.0,
                        "t": tt[fin], "rpm": rr[fin],
                    }
                rpm_series = sup
                out["rpm_evidence"] = {k: {kk: vv for kk, vv in v.items() if kk not in ("t", "rpm")}
                                       for k, v in sup.items()}
                ok = all(s["coverage"] >= 0.90 and s["nonzero_frac"] >= 0.05
                         and s["rpm_std"] > 50 for s in sup.values())
                out["rpm_ok"] = bool(ok)
                if not ok:
                    out["notes"].append("ESC RPM present but fails coverage/variance gate")
            else:
                out["notes"].append("ESC instance->channel mapping not resolvable")

    # ---- block boundaries from every contributing stream
    # Only periodic telemetry streams may cut a block.  ARM/MODE/GPS are logged
    # on state change / at a lower rate; treating their quiet intervals as data
    # gaps would delete whole navigations.  ARM/MODE switch times are handled
    # separately as +/-1 s exclusion pads below.
    gap_iv = []
    for tc in (t_imu, t_att, t_x, t_rc, t_vibe):
        if tc.size > 1:
            gap_iv.extend(_gaps(np.sort(tc)))
    # GPS (health gate) and POS (state fallback) are used sources too: their
    # gaps cut blocks so the +-1 s boundary pads apply, rather than being
    # bridged by a carried-forward value.
    gps_gap_iv, pos_gap_iv = [], []
    if gps_status is not None and np.asarray(gps_status[0]).size > 1:
        gt = np.sort(np.asarray(gps_status[0]))
        gps_gap_iv = _gaps_thr(gt, _stream_gap_threshold(gt))
        gap_iv.extend(gps_gap_iv)
    # POS is only a fallback for missing XKF1 positions: cut on its gaps only
    # when it is actually used, otherwise it would discard valid navigation.
    if vacuum.any() and "POS.TimeUS" in z and z["POS.TimeUS"].size > 1:
        pt = np.sort(np.asarray(z["POS.TimeUS"]) / 1e6)
        pos_gap_iv = _gaps_thr(pt, _stream_gap_threshold(pt))
        gap_iv.extend(pos_gap_iv)
    blocks = merge_intervals(gap_iv)
    t_lo = max(x[0] for x in (t_imu, t_att, t_x) if x.size)
    t_hi = min(x[-1] for x in (t_imu, t_att, t_x) if x.size)
    free = []
    cur = t_lo
    for a, b in blocks:
        if b <= t_lo or a >= t_hi:
            continue
        if a > cur:
            free.append((cur, a))
        cur = max(cur, b)
    if cur < t_hi:
        free.append((cur, t_hi))
    free = [(a, b) for a, b in free if b - a >= 2.0]

    excl = _exclusion_intervals(exclusions.get(meta["basename"], []), t_imu, gyr)
    mode_switches = _switch_times(t_mode, mode_num)
    core_switches = list(core.get("switches") or [])
    yaw_resets = _yaw_resets(t_att, att_yaw)

    n_rec = float(t_imu[-1] - t_imu[0]) if t_imu.size > 1 else 0.0
    n_cont = float(sum(b - a for a, b in free))
    out["stats"].update({"recorded_s": n_rec, "continuous_s": n_cont,
                         "n_blocks": len(free), "n_excl_windows": len(excl)})

    # ---- per-block grid
    segs = []
    seg_idx = 0
    for bi, (a, b) in enumerate(free):
        tg = np.arange(a, b - DT * 0.5, DT)
        if tg.size < 10:
            continue
        # states
        yaw = interp_angle(t_x, yaw_x, tg)
        VN = interp_linear(t_x, vn, tg)
        VE = interp_linear(t_x, ve, tg)
        px = interp_linear(t_x, pe, tg)
        py = interp_linear(t_x, pn, tg)
        roll = interp_linear(t_att, att_roll, tg)
        pitch = interp_linear(t_att, att_pitch, tg)
        gz = interp_linear(t_imu, gyr, tg)
        pw_l, age_l = zoh_lookup(t_rc, pwm_l, tg, PWM_MAX_AGE_S)
        pw_r, age_r = zoh_lookup(t_rc, pwm_r, tg, PWM_MAX_AGE_S)
        if mode_num.size:
            md, _ = zoh_lookup(t_mode, mode_num, tg)
        else:
            md = np.full(tg.shape, np.nan)
        if arm_state.size:
            ar, _ = zoh_lookup(t_arm, arm_state, tg)
        else:
            ar = np.full(tg.shape, np.nan)
        if clip.size:
            cp, _ = zoh_lookup(t_vibe, clip, tg, max_age=_gap_threshold(t_vibe))
        else:
            # no VIBE record is missing evidence, never a fabricated "no clipping"
            cp = np.full(tg.shape, np.nan)
        if gps_status is not None:
            # GPS is periodic telemetry: its health value expires with the same
            # threshold used for gap detection, so an outage cannot inherit the
            # last healthy fix.
            gps_age = _gap_threshold(np.asarray(gps_status[0]))
            gst, _ = zoh_lookup(gps_status[0], gps_status[1], tg, max_age=gps_age)
            ghd, _ = zoh_lookup(gps_hdop[0], gps_hdop[1], tg, max_age=gps_age)
        else:
            gst = ghd = np.full(tg.shape, np.nan)

        u = VN * np.cos(yaw) + VE * np.sin(yaw)
        v = VN * np.sin(yaw) - VE * np.cos(yaw)
        r = -gz
        psi = wrap_pi(math.pi / 2.0 - yaw)
        x = np.stack([px, py, psi, u, v, r], axis=-1)

        # dilation reasons (separate "missing evidence" from "excluded")
        miss = []
        masked = np.ones(tg.shape, dtype=bool)
        if arm_state.size == 0:
            masked[:] = False
            miss.append("missing_armed_state")
        else:
            masked &= (ar == 1)
        if mode_num.size == 0:
            # without MODE events the mandated switch exclusions cannot be applied
            masked[:] = False
            miss.append("missing_mode_events")
        bad = ~np.isfinite(x).all(axis=1)
        if bad.any():
            masked &= ~bad
        core_ok = np.isfinite(yaw) & np.isfinite(VN) & np.isfinite(VE)
        masked &= core_ok
        if gps_status is None:
            # "missing evidence" is a distinct reason and it does NOT pass
            masked[:] = False
            miss.append("missing_gps_health")
        else:
            masked &= np.isfinite(gst) & (gst >= GPS_MIN_STATUS) & np.isfinite(ghd) & (ghd <= GPS_MAX_HDOP)
        masked &= np.isfinite(roll) & (np.abs(roll) <= ROLL_LIM_DEG)
        masked &= np.isfinite(pitch) & (np.abs(pitch) <= PITCH_LIM_DEG)
        masked &= np.isfinite(pw_l) & np.isfinite(pw_r)
        if route is None or route["conflict"]:
            masked[:] = False
            miss.append("mapping_conflict")
        masked &= ~in_intervals(tg, excl)
        # gap / switch padding
        for ga, gb in blocks:
            masked &= ~((tg > ga - GAP_PAD_S) & (tg < gb + GAP_PAD_S))
        for ts in mode_switches + core_switches:
            masked &= np.abs(tg - ts) > SWITCH_PAD_S
        for ts in yaw_resets:
            masked &= np.abs(tg - ts) > 2.0 * SWITCH_PAD_S
        masked &= (tg > a + GAP_PAD_S) & (tg < b - GAP_PAD_S)
        if not clip.size:
            masked[:] = False
            miss.append("missing_vibe_health")
        # clipping events
        if clip.size and np.isfinite(cp).any():
            dclip = np.diff(np.concatenate(([0.0], cp)))
            for i in np.where(dclip > 0)[0]:
                masked &= ~((tg >= tg[i]) & (tg <= tg[i] + 2.0))

        ql = pwm_to_normalized(pw_l, route["left_min"], route["left_trim"], route["left_max"]) \
            if route is not None and not route["conflict"] else np.zeros_like(pw_l)
        qr = pwm_to_normalized(pw_r, route["right_min"], route["right_trim"], route["right_max"]) \
            if route is not None and not route["conflict"] else np.zeros_like(pw_r)
        qlp, qln = direction_split(ql)
        qrp, qrn = direction_split(qr)
        # Q columns carry the direction sign so a positive gain always means
        # "forward thrust for that side/direction".
        ui = np.stack([qlp, -qln, qrp, -qrn], axis=-1)

        if rpm_series is not None:
            rl = interp_linear(rpm_series["left"]["t"], rpm_series["left"]["rpm"], tg)
            rr = interp_linear(rpm_series["right"]["t"], rpm_series["right"]["rpm"], tg)
            rpm = np.stack([rl, rr], axis=-1)
        else:
            rpm = np.zeros((tg.size, 0))

        # per-run heading/gyro consistency, then split into segments
        if miss:
            out["reasons"].extend(f"{m}@block{bi}" for m in miss)
        for s0, s1 in runs_of(masked, min_len=20):
            tt = tg[s0:s1]
            if tt.size < 20:
                continue
            dpsi = np.gradient(np.unwrap(x[s0:s1, 2]), DT)
            r_obs = x[s0:s1, 5]
            rmse = float(np.sqrt(np.mean((dpsi - r_obs) ** 2)))
            if not np.isfinite(rmse) or rmse > HEADING_RMSE_LIM:
                out["reasons"].append(f"heading_gyro_mismatch@block{bi}+{tt[0]:.1f}s(rmse={rmse:.3f})")
                continue
            sl = slice(s0, s1)
            seg = Segment(
                sid=f"{meta['basename']}#{seg_idx}", t0=float(tt[0]), t1=float(tt[-1]),
                group=meta["group"],
                t=tt, x=x[sl], ui=ui[sl], pwm=np.stack([pw_l[sl], pw_r[sl]], axis=-1),
                rpm=rpm[sl] if rpm.size else rpm, mode=md[sl], terms=ui[sl],
                labels=_label_samples(tt, x[sl], np.stack([pw_l[sl], pw_r[sl]], axis=-1)))
            seg_idx += 1
            segs.append(seg)
    out["segments"] = segs
    out["yaw_resets"] = yaw_resets
    out["gps_gaps"] = gps_gap_iv
    out["pos_gaps"] = pos_gap_iv
    out["stats"]["trainable_s"] = float(sum(len(s) for s in segs) * DT)
    return out


def _corr_with_pwm(t_esc, rpm, t_rc, pwm):
    if t_esc.size < 50 or t_rc.size < 10:
        return None
    g = np.arange(max(t_esc[0], t_rc[0]) + 1, min(t_esc[-1], t_rc[-1]) - 1, 0.1)
    if g.size < 50:
        return None
    v = np.interp(g, t_esc, rpm)
    p, _ = zoh_lookup(t_rc, pwm, g)
    ok = np.isfinite(v) & np.isfinite(p) & (np.abs(p - 1500) > 50)
    if ok.sum() < 30:
        return None
    if np.std(v[ok]) < 1e-9 or np.std(p[ok]) < 1e-9:
        return None
    return float(np.corrcoef(v[ok], p[ok])[0, 1])


def _firmware(z):
    if "MSG.Message" not in z:
        return None
    for m in z["MSG.Message"]:
        s = str(m)
        if s.startswith("Ardu") or s.startswith("Rover"):
            return s
    return None


def _yaw_resets(t, yaw_rad, jump_rad=0.5):
    """Times of EKF heading realignments (single-sample yaw jumps).

    The difference is wrapped first: an ordinary +-180 deg wrap-around is not a
    reset and must not be excluded.
    """
    if t.size < 3:
        return []
    d = np.abs(wrap_pi(np.diff(yaw_rad)))
    return [float(t[i + 1]) for i in np.where(d > jump_rad)[0]]


def _switch_times(t, v):
    if v.size < 2:
        return []
    d = np.diff(v)
    return [float(t[i + 1]) for i in np.where((d != 0) & np.isfinite(d))[0]]


def _exclusion_intervals(windows, t_imu, gyr):
    """Spin windows padded +-2 s, extended to the end of the motion they start."""
    out = []
    if not windows or t_imu.size < 10:
        return out
    for w in windows:
        a = float(w.get("start_s", w.get("start", 0.0)))
        b = float(w.get("end_s", w.get("end", 0.0)))
        if b <= a:
            continue
        # extend from the window start to the last sample still spinning
        m = (t_imu >= a) & (np.abs(-gyr) >= SPIN_RATE)
        tail = float(t_imu[m][-1]) if m.any() else b
        out.append((a - EXCL_PAD_S, max(b, tail) + EXCL_PAD_S))
    return merge_intervals(out)


def _label_samples(t, x, pwm):
    """Per-sample maneuver label."""
    n = t.size
    lab = np.full(n, "cruise", dtype=object)
    u = x[:, 3]
    v = x[:, 4]
    r = x[:, 5]
    straight = (np.abs(r) < STRAIGHT_R_LIM) & (np.abs(v) < STRAIGHT_V_LIM)
    for s0, s1 in runs_of(straight, min_len=int(STRAIGHT_MIN_S * GRID_HZ)):
        lab[s0:s1] = "straight"
    turn = np.abs(r) >= STRAIGHT_R_LIM
    lab[turn & (r > 0)] = "turn_left"
    lab[turn & (r < 0)] = "turn_right"
    rev = u < -0.2
    lab[rev] = "reverse"
    sat = ((pwm[:, 0] <= 1005) | (pwm[:, 0] >= 1995) |
           (pwm[:, 1] <= 1005) | (pwm[:, 1] >= 1995))
    idx = np.where(sat)[0]
    for i in idx:
        lab[i] = "saturated_" + str(lab[i])
    # candidate coast: both PWMs near their medians, speed dropping, >= 4 s
    med_l = float(np.median(pwm[:, 0]))
    med_r = float(np.median(pwm[:, 1]))
    flat = (np.abs(pwm[:, 0] - med_l) <= COAST_PWM_TOL_US) & \
           (np.abs(pwm[:, 1] - med_r) <= COAST_PWM_TOL_US)
    speed = np.hypot(u, v)
    decel = np.gradient(speed) / DT < -0.15
    coast = flat & decel & (speed > 0.3)
    for s0, s1 in runs_of(coast, min_len=int(COAST_MIN_S * GRID_HZ)):
        if speed[s0] > 0.8:
            lab[s0:s1] = "candidate_coast"
    return lab


# ---------------------------------------------------------------------------
# discovery / roles
# ---------------------------------------------------------------------------
DATA_DIRS = ("2026-06-08", "2026-06-17", "2026-09-03", "2026-11-02")


def discover_sources(data_root, extra_history):
    found = []
    for d in DATA_DIRS:
        p = os.path.join(data_root, d)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):
            if os.path.splitext(f)[1].lower() != ".bin":
                continue
            found.append((d, os.path.join(p, f), f))
    if extra_history and os.path.isdir(extra_history):
        for f in sorted(os.listdir(extra_history)):
            if os.path.splitext(f)[1].lower() != ".bin":
                continue
            found.append(("2026-06-25", os.path.join(extra_history, f), f))
    return found


def initial_role(date, basename):
    if date == "2026-11-02":
        if basename == TODAY_TRAIN:
            return "train_today", "fixed_role"
        if basename == TODAY_SELECT:
            return "select_today", "fixed_role"
        if basename == TODAY_BLIND:
            return "blind_today", "fixed_role"
        return "inventory_only", "today_non_navigation"
    if basename in HIST_ROLES:
        return HIST_ROLES[basename], "fixed_role"
    return "history_train_candidate", "candidate"


def build_grid(z, meta, exclusions):
    """Reconstruct exactly the segments produced during prepare (pure)."""
    return build_dataset(z, meta, exclusions, {})


def holdout_windows(segments, win_s=REPLAY_WIN_S):
    """Non-overlapping windows fully inside one segment."""
    wins = []
    n = int(round(win_s / DT))
    for seg in segments:
        k = (len(seg) - 1) // n
        for i in range(k):
            wins.append((seg, i * n, (i + 1) * n))
    return wins


def holdout_sufficient(segments):
    """>=3 non-overlapping 10 s windows that together cover straight and turning."""
    wins = holdout_windows(segments)
    straight = turn = 0
    for seg, a, b in wins:
        labs = [str(x).split("_saturated")[0] for x in seg.labels[a:b].tolist()]
        if any(l == "straight" for l in labs):
            straight += 1
        if any(l.startswith("turn") for l in labs):
            turn += 1
    ok = len(wins) >= 3 and straight > 0 and turn > 0
    return ok, {"n_windows": len(wins), "straight_windows": straight,
                "turn_windows": turn}


@dataclass
class SplitEntry:
    key: str
    date: str
    group: str
    role: str
    sha256: str
    segments: list
    status: str = "ok"
    note: str = ""


def build_split(entries):
    """Freeze data roles.  Blind data never influences fitting."""
    today_train = [e for e in entries if e.role == "train_today"]
    today_select = [e for e in entries if e.role == "select_today"]
    today_blind = [e for e in entries if e.role == "blind_today"]

    blind_ok, blind_info = (False, {"n_windows": 0})
    if today_blind:
        blind_ok, blind_info = holdout_sufficient(today_blind[0].segments)
    sel_ok, sel_info = (False, {"n_windows": 0})
    if today_select:
        sel_ok, sel_info = holdout_sufficient(today_select[0].segments)

    decision = "keep"
    if not blind_ok and sel_ok:
        # swap: the select file becomes the blind set, the train file is split
        today_blind[0].role = "blind_today"
        today_select[0].role = "blind_today"
        today_select[0].note = "swapped_to_blind: original blind had insufficient holdout"
        for e in today_train:
            n = len(e.segments)
            if n >= 2:
                cut = max(1, int(math.floor(0.7 * n)))
                cut = min(cut, n - 1)
                train_s = e.segments[:cut]
                val_s = e.segments[cut:]
                e.segments = train_s
                e.role = "train_today"
                dup = SplitEntry(key=e.key + "#validate_split", date=e.date, group=e.group,
                                 role="validate_today", sha256=e.sha256, segments=val_s,
                                 note="70/30 chronological split of the training file")
                entries.append(dup)
                decision = "swapped_70_30"
            else:
                e.status = "insufficient_holdout"
                e.note = "not enough segments for a 70/30 split"
    elif not blind_ok and not sel_ok:
        decision = "insufficient_holdout"

    # historical candidates: chronological 80/20 per date
    hist = [e for e in entries if e.role == "history_train_candidate" and e.status == "ok"
            and len(e.segments) >= 1]
    by_date = {}
    for e in hist:
        by_date.setdefault(e.date, []).append(e)
    hist_train, hist_val = [], []
    for date, group_entries in sorted(by_date.items()):
        segs = []
        for e in group_entries:
            for s in e.segments:
                segs.append((e, s))
        segs.sort(key=lambda p: p[1].t0)
        if len(segs) < 2:
            for e, s in segs:
                e.status = "diagnostic_only"
                e.note = "fewer than two clean segments in this date"
            continue
        cut = max(1, int(math.floor(0.8 * len(segs))))
        cut = min(cut, len(segs) - 1)
        for i, (e, s) in enumerate(segs):
            if i < cut:
                hist_train.append((e, s))
            else:
                hist_val.append((e, s))
    return {
        "holdout_decision": decision,
        "blind_info": blind_info,
        "select_info": sel_info,
        "hist_train": hist_train,
        "hist_val": hist_val,
    }


# ---------------------------------------------------------------------------
# stage: prepare
# ---------------------------------------------------------------------------
STAGE_ORDER = ("prepare", "fit", "validate")
STAGE_DIRS = {"fit": "fit", "prepare": "npz"}


def _ensure_out(out, stage):
    """Sequential stages share one --out; a finished stage is never overwritten.

    Running a stage that already finished (or a later one) is a conflict: the
    operator must pick a fresh --out, so corrected runs never silently replace
    evidence.  Ordinary prepare -> fit -> validate in one directory is allowed.
    """
    if stage in STAGE_ORDER:
        idx = STAGE_ORDER.index(stage)
        for later in STAGE_ORDER[idx:]:
            marker = os.path.join(out, f"{later}_done.json")
            if os.path.exists(marker):
                raise SystemExit(
                    f"conflict: {marker} already exists; this directory already holds a "
                    f"finished '{later}' stage - use a new --out path")
        if idx > 0:
            need = STAGE_ORDER[idx - 1]
            if not os.path.exists(os.path.join(out, f"{need}_done.json")):
                raise SystemExit(
                    f"{stage} requires a completed '{need}' stage in {out}")
        # an interrupted run leaves artifacts without a marker: also a conflict
        for sub in ([STAGE_DIRS[stage]] if stage in STAGE_DIRS else []):
            d = os.path.join(out, sub)
            if os.path.isdir(d) and os.listdir(d):
                raise SystemExit(
                    f"conflict: {d} already contains artifacts but '{stage}_done.json' "
                    f"is missing (interrupted run) - use a new --out path")
    os.makedirs(out, exist_ok=True)


def stage_prepare(args):
    out = args.out
    _ensure_out(out, "prepare")
    npz_dir = os.path.join(out, "npz")
    os.makedirs(npz_dir, exist_ok=True)

    exclusions = {}
    if args.exclusions and os.path.exists(args.exclusions):
        with open(args.exclusions, "r", encoding="utf-8") as fh:
            exclusions = json.load(fh)
    baseline = load_baseline(args.baseline)

    sources = discover_sources(args.data_root, args.extra_history)
    print(f"[prepare] discovered {len(sources)} BIN files")
    manifest, entries = [], []
    for date, path, base in sources:
        role, role_src = initial_role(date, base)
        h = hashlib.sha256()
        n = 0
        try:
            with open(path, "rb") as fh:
                while True:
                    b = fh.read(1 << 22)
                    if not b:
                        break
                    n += len(b)
                    h.update(b)
        except OSError as exc:
            manifest.append({"basename": base, "date": date, "path": path,
                             "error": f"{type(exc).__name__}: {exc}", "role": role})
            print(f"[prepare]  {base}: UNREADABLE ({exc})")
            continue
        sha = h.hexdigest()
        size = os.path.getsize(path)
        exp = EXPECTED_SOURCES.get(base)
        if exp is not None and (sha != exp[0] or size != exp[1]):
            manifest.append({"basename": base, "date": date, "path": path,
                             "size": size, "sha256": sha, "role": role,
                             "error": "source_changed",
                             "expected_sha256": exp[0], "expected_size": exp[1]})
            print(f"[prepare]  {base}: SOURCE CHANGED vs frozen provenance "
                  f"(sha {sha[:16]}… size {size}, expected {exp[0][:16]}… {exp[1]})")
            continue
        npz_path = os.path.join(npz_dir, sha[:20] + ".npz")
        rel = os.path.relpath(npz_path, out)
        z, pmeta = parse_source_to_npz(path, npz_path,
                                       expected_sha=(exp[0] if exp else sha))
        rec = {"basename": base, "date": date, "path": path, "size": size,
               "sha256": sha, "npz": rel, "role": role, "role_source": role_src}
        if z is None:
            rec["error"] = pmeta.get("error", "source_unreadable")
            rec["bytes_read"] = pmeta.get("bytes_read")
            manifest.append(rec)
            print(f"[prepare]  {base}: COPY/PARSE FAILED ({rec['error']})")
            continue
        params, hist = _params_dict(z)
        rec.update({
            "n_msg": pmeta["n_msg"],
            "msg_counts": {k: v for k, v in pmeta["msg_counts"].items() if v},
            "firmware": _firmware(z),
            "boot_count": params.get("STAT_BOOTCNT"),
            "mot_pwm_type": params.get("MOT_PWM_TYPE"),
            "ek3_primary": params.get("EK3_PRIMARY"),
            "servo_functions": {f"SERVO{c}_FUNCTION": params.get(f"SERVO{c}_FUNCTION")
                                for c in (1, 2, 3, 4)},
            "params_sha256": hashlib.sha256(
                json.dumps(params, sort_keys=True, default=str).encode()).hexdigest(),
            "parm_changes": _parm_changes(hist),
            "esc_records": int(pmeta["msg_counts"].get("ESC", 0)),
            "esc_fields": pmeta["fields_present"].get("ESC", []),
            "missing_fields": sorted(
                f for t, fs in (("ATT", ["Roll"]), ("XKF1", ["PN", "PE"]),
                                ("XKF4", ["PI"]), ("VIBE", ["Clip"]),
                                ("GPS", ["Yaw", "Spd", "GCrs", "I"]))
                for f in fs if f not in pmeta["fields_present"].get(t, [])),
        })
        manifest.append(rec)
        entries.append(rec)
        print(f"[prepare]  {base}: {size} B {pmeta['n_msg']} msgs sha={sha[:16]}… "
              f"fw={rec['firmware']} boot={rec['boot_count']} esc={rec['esc_records']}")

    # ---- hardware groups (date + configuration fingerprint)
    fps = {}
    for rec in entries:
        fp = (rec["date"], rec.get("mot_pwm_type"),
              tuple(sorted((k, v) for k, v in (rec.get("servo_functions") or {}).items()
                           if v is not None)),
              (rec.get("firmware") or "").split(" ")[0])
        fps.setdefault(rec["date"], set()).add(fp)
    for rec in entries:
        fp = (rec["date"], rec.get("mot_pwm_type"),
              tuple(sorted((k, v) for k, v in (rec.get("servo_functions") or {}).items()
                           if v is not None)),
              (rec.get("firmware") or "").split(" ")[0])
        rec["group"] = rec["date"] if len(fps[rec["date"]]) == 1 else \
            f"{rec['date']}/cfg{sorted(fps[rec['date']]).index(fp)}"

    # ---- datasets
    split_entries = []
    cov_rows = []
    for rec in entries:
        z = np.load(os.path.join(out, rec["npz"]), allow_pickle=True)
        ds = build_dataset(z, rec, exclusions, {})
        rec["segments_stats"] = ds["stats"]
        rec["reasons"] = ds["reasons"]
        rec["mapping_ok"] = ds["mapping_ok"]
        rec["rpm_ok"] = ds["rpm_ok"]
        rec["rpm_evidence"] = ds.get("rpm_evidence")
        rec["imu"] = ds["imu"]
        rec["core"] = (None if not ds["core"] else
                       {"mode": ds["core"]["mode"], "switches": ds["core"]["switches"]})
        rec["n_clean_segments"] = len(ds["segments"])
        split_entries.append(SplitEntry(key=rec["basename"], date=rec["date"],
                                        group=rec["group"], role=rec["role"],
                                        sha256=rec["sha256"], segments=ds["segments"]))
        st = ds["stats"]
        lab_counts = {}
        for seg in ds["segments"]:
            for l in seg.labels.tolist():
                base_l = str(l).split("_saturated")[0]
                lab_counts[base_l] = lab_counts.get(base_l, 0) + 1
        cov_rows.append({
            "file": rec["basename"], "group": rec["group"], "role": rec["role"],
            "recorded_s": round(st.get("recorded_s", 0.0), 1),
            "continuous_s": round(st.get("continuous_s", 0.0), 1),
            "trainable_s": round(st.get("trainable_s", 0.0), 1),
            "excluded_s": round(st.get("recorded_s", 0.0) - st.get("trainable_s", 0.0), 1),
            "n_segments": len(ds["segments"]),
            "labels_s": {k: round(v * DT, 1) for k, v in sorted(lab_counts.items())},
            "reasons": ";".join(ds["reasons"]),
        })

    split = build_split(split_entries)

    # ---- persist
    with open(os.path.join(out, "source_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"baseline": args.baseline, "data_root": args.data_root,
                   "extra_history": args.extra_history, "files": manifest},
                  fh, ensure_ascii=False, indent=2, default=str)

    rows = []
    for se in split_entries:
        parts = [se]
        if se.role == "validate_today":
            parts = [se]
        for se2 in parts:
            if not se2.segments:
                rows.append({"source_sha256": se2.sha256, "hardware_group": se2.group,
                             "file": se2.key, "role": se2.role, "segment_id": "",
                             "start_TimeUS": "", "end_TimeUS": "", "use": "unused",
                             "reason": se2.note or "no_clean_segment"})
            for seg in se2.segments:
                rows.append({
                    "source_sha256": se2.sha256, "hardware_group": se2.group,
                    "file": se2.key, "role": se2.role, "segment_id": seg.sid,
                    "start_TimeUS": int(round(seg.t0 * 1e6)),
                    "end_TimeUS": int(round(seg.t1 * 1e6)),
                    "duration_s": round(float(seg.t1 - seg.t0), 3),
                    "use": "fit" if se2.role.startswith("train") else
                           ("blind" if se2.role.startswith("blind") else
                            ("validate" if se2.role.startswith("validate")
                             or se2.role.startswith("select") else se2.role)),
                    "reason": se2.note or "",
                    "labels": ",".join(sorted(set(str(x).split("_saturated")[0]
                                                  for x in seg.labels.tolist()))),
                })
    _write_csv(os.path.join(out, "segments.csv"), rows)
    _write_csv(os.path.join(out, "coverage.csv"), cov_rows)

    split_doc = {
        "holdout_decision": split["holdout_decision"],
        "blind_info": split["blind_info"],
        "select_info": split["select_info"],
        "roles": [{"file": e.key, "date": e.date, "group": e.group, "role": e.role,
                   "sha256": e.sha256, "status": e.status, "note": e.note,
                   "n_segments": len(e.segments),
                   "t_ranges": [[round(float(s.t0), 3), round(float(s.t1), 3)]
                                for s in e.segments]} for e in split_entries],
        "history_train": [[e.key, s.sid] for e, s in split["hist_train"]],
        "history_validate": [[e.key, s.sid] for e, s in split["hist_val"]],
        "exclusions": exclusions,
        "rules": {
            "grid_hz": GRID_HZ, "excl_pad_s": EXCL_PAD_S, "switch_pad_s": SWITCH_PAD_S,
            "gap_pad_s": GAP_PAD_S, "roll_lim_deg": ROLL_LIM_DEG,
            "pitch_lim_deg": PITCH_LIM_DEG,
            "heading_rmse_lim_degps": math.degrees(HEADING_RMSE_LIM),
            "pwm_deadzone_us_prior": PWM_DEADZONE_US, "pwm_max_age_s": PWM_MAX_AGE_S,
        },
    }
    split_doc["sha256"] = hashlib.sha256(
        json.dumps(split_doc, sort_keys=True, default=str).encode()).hexdigest()
    with open(os.path.join(out, "split_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(split_doc, fh, ensure_ascii=False, indent=2, default=str)

    with open(os.path.join(out, "prepare_done.json"), "w", encoding="utf-8") as fh:
        json.dump({"split_hash": split_doc["sha256"], "n_files": len(manifest)},
                  fh, indent=2)

    # ---- observed summary (not just "files exist")
    print("\n[prepare] mapping / input availability")
    for rec in entries:
        if rec.get("error"):
            print(f"  {rec['basename']}: {rec['error']}")
            continue
        print(f"  {rec['basename']}: mapping_ok={rec['mapping_ok']} rpm_ok={rec['rpm_ok']} "
              f"imu={rec['imu']} core={rec['core']} clean_segments={rec['n_clean_segments']}")
    print("\n[prepare] coverage")
    for r in cov_rows:
        print(f"  {r['file'][:28]:28s} role={r['role'][:22]:22s} "
              f"rec={r['recorded_s']:7.1f}s cont={r['continuous_s']:7.1f}s "
              f"use={r['trainable_s']:7.1f}s nseg={r['n_segments']:2d} {r['reasons']}")
    print(f"\n[prepare] holdout decision: {split['holdout_decision']} "
          f"blind={split['blind_info']} select={split['select_info']}")
    print(f"[prepare] history train segments: {len(split['hist_train'])}, "
          f"validate segments: {len(split['hist_val'])}")
    # no train/blind intersection
    def _rng(e, seg):
        return (e.sha256, round(float(seg.t0), 3), round(float(seg.t1), 3))
    tr = {_rng(e, s) for e in split_entries if e.role.startswith("train") for s in e.segments}
    bl = {_rng(e, s) for e in split_entries if e.role.startswith("blind") for s in e.segments}
    print(f"[prepare] train/blind source+range overlap: {len(tr & bl)} (must be 0)")
    print(f"[prepare] wrote {out}\n")


def _write_csv(path, rows):
    if not rows:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n")
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        import csv
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items()})


# ---------------------------------------------------------------------------
# fitting structures
# ---------------------------------------------------------------------------
GAIN_COLS = ["ALp", "ALn", "ARp", "ARn"]
DAMP_KEYS = [("a1", "Xu", 0), ("a2", "Xuu", 1), ("n1", "Nr", 2), ("n2", "Nrr", 3)]


@dataclass
class GroupModel:
    name: str
    tie_fwd: bool = False
    tie_rev: bool = False
    no_reverse: bool = False


def gain_layout(gm: GroupModel):
    """-> (params, fixed) where params = [(label, [(col, w), ...]), ...]."""
    fixed = {}
    if gm.no_reverse:
        fixed[1] = 0.0
        fixed[3] = 0.0
    params = []
    if gm.tie_fwd:
        params.append(("A_sym_fwd", [(0, 1.0), (2, 1.0)]))
    else:
        params.append(("A_L_fwd", [(0, 1.0)]))
        params.append(("A_R_fwd", [(2, 1.0)]))
    if not gm.no_reverse:
        if gm.tie_rev:
            params.append(("A_sym_rev", [(1, 1.0), (3, 1.0)]))
        else:
            params.append(("A_L_rev", [(1, 1.0)]))
            params.append(("A_R_rev", [(3, 1.0)]))
    return params, fixed


@dataclass
class RegRow:
    group: str
    s: np.ndarray     # 8 coefficients
    y: float
    w: float
    label: str
    sid: str = ""


def regression_rows(segments_by_group, p_base):
    m11, m22, m23, m32, m33 = hydro_matrix(p_base)
    d = p_base["d_thruster"]
    L = int(round(LIN_WIN_S / DT))
    rows = []
    for gname, segs in segments_by_group.items():
        if not segs:
            continue
        nw_tot = sum(max(0, (len(s) - 1) // L) for s in segs)
        for seg in segs:
            nw = (len(seg) - 1) // L
            if nw <= 0:
                continue
            u, v, r = seg.x[:, 3], seg.x[:, 4], seg.x[:, 5]
            c1 = (-m22 * v - m23 * r) * r
            c3 = (m22 * v + m23 * r) * u - m11 * u * v
            w = 1.0 / max(1, nw_tot)
            for k in range(nw):
                a, b = k * L, (k + 1) * L
                sl = slice(a, b + 1)
                Iu = trapz(u[sl], DT)
                Iu2 = trapz(np.abs(u[sl]) * u[sl], DT)
                Ir = trapz(r[sl], DT)
                Irr = trapz(np.abs(r[sl]) * r[sl], DT)
                I1 = trapz(c1[sl], DT)
                I3 = trapz(c3[sl], DT)
                if not np.isfinite(seg.terms[sl]).all():
                    continue                      # missing RPM evidence: drop the window
                IQ = trapz(seg.terms[sl], DT, axis=0)   # (4,) thrust terms
                du = u[b] - u[a]
                dr = r[b] - r[a]
                dv = v[b] - v[a]
                rows.append(RegRow(gname,
                                   np.array([Iu, Iu2, 0.0, 0.0, -IQ[0], -IQ[1], -IQ[2], -IQ[3]]),
                                   -(m11 * du + I1), w, str(seg.labels[a]), seg.sid))
                rows.append(RegRow(gname,
                                   np.array([0.0, 0.0, Ir, Irr, d * IQ[0], d * IQ[1],
                                             -d * IQ[2], -d * IQ[3]]),
                                   -(m32 * dv + m33 * dr + I3), w, str(seg.labels[a]), seg.sid))
    return rows


@dataclass
class ModelSpec:
    damp_free: list
    damp_fixed: dict
    groups: list
    reductions: list = field(default_factory=list)

    def theta_names(self):
        names = [k for k in ("a1", "a2", "n1", "n2") if k in self.damp_free]
        for gm in self.groups:
            params, _ = gain_layout(gm)
            names.extend(f"{gm.name}:{p[0]}" for p in params)
        return names


def build_design(rows, spec):
    """Assemble the weighted design matrix and RHS with the chosen structure."""
    n = len(rows)
    if n == 0:
        return None, None, None
    gs = np.array([r.group for r in rows])
    S = np.stack([r.s for r in rows])
    y = np.array([r.y for r in rows], dtype=float)
    damp_idx = [i for k, _, i in DAMP_KEYS if k in spec.damp_free]
    ycorr = y.copy()
    for k, _, i in DAMP_KEYS:
        if k in spec.damp_fixed:
            ycorr = ycorr - S[:, i] * spec.damp_fixed[k]
    blocks = [S[:, damp_idx] if damp_idx else np.zeros((n, 0))]
    for gm in spec.groups:
        m = gs == gm.name
        if not m.any():
            continue
        params, fixed = gain_layout(gm)
        gS = S[m][:, 4:]
        for col, val in fixed.items():
            ycorr[m] = ycorr[m] - gS[:, col] * val
        cols = [sum(gS[:, c] * wt for c, wt in combo) for _, combo in params]
        blk = np.stack(cols, axis=1) if cols else np.zeros((int(m.sum()), 0))
        full = np.zeros((n, blk.shape[1]))
        full[m] = blk
        blocks.append(full)
    A = np.concatenate(blocks, axis=1)
    w = np.sqrt(np.array([r.w for r in rows], dtype=float))
    return A, ycorr, w


def spectrum_summary(A, w):
    if A is None or A.shape[1] == 0:
        return {"rank": 0, "n_cols": 0, "cond": None}
    As = A * w[:, None]
    norms = np.linalg.norm(As, axis=0)
    norms[norms == 0] = 1.0
    s = np.linalg.svd(As / norms, compute_uv=False)
    tol = (s[0] * max(A.shape) * 1e-12) if s.size else 0.0
    rank = int((s > tol).sum())
    cond = float(s[0] / s[-1]) if s.size and s[-1] > 0 else math.inf
    return {"rank": rank, "n_cols": int(A.shape[1]), "cond": cond}


def choose_spec(rows, p_base, group_names):
    """Prescribed reduction ladder until the design is identifiable."""
    a1b = -p_base["Xu"]
    n2b = -p_base["Nrr"]
    rev_exc = fwd_exc = 0.0
    for r in rows:
        fwd_exc += abs(r.s[4]) + abs(r.s[6])
        rev_exc += abs(r.s[5]) + abs(r.s[7])
    no_rev = rev_exc < 1e-6 * max(fwd_exc, 1e-12)
    groups = [GroupModel(g, no_reverse=no_rev) for g in group_names]
    spec = ModelSpec(damp_free=["a1", "a2", "n1", "n2"], damp_fixed={}, groups=groups)
    if no_rev:
        spec.reductions.append("no_reverse_excitation:reverse_gains_not_estimated")

    def info():
        A, b, w = build_design(rows, spec)
        return spectrum_summary(A, w)

    steps = [
        ("lr_asymmetry_not_identifiable:gains_tied", _tie_all),
        ("xu_xuu_not_separable:Xu_fixed_to_baseline",
         lambda sp: sp.damp_fixed.__setitem__("a1", a1b)),
        ("nr_nrr_not_separable:Nrr_fixed_to_baseline",
         lambda sp: sp.damp_fixed.__setitem__("n2", n2b)),
        ("xuu_not_identifiable", lambda sp: sp.damp_free.remove("a2") if "a2" in sp.damp_free else None),
        ("nr_not_identifiable", lambda sp: sp.damp_free.remove("n1") if "n1" in sp.damp_free else None),
    ]
    cur = info()
    for name, act in steps:
        if cur["rank"] == cur["n_cols"] and cur["cond"] is not None and cur["cond"] <= COND_LIM:
            break
        act(spec)
        spec.reductions.append(name)
        cur = info()
    return spec, cur


def _tie_all(spec):
    for gm in spec.groups:
        gm.tie_fwd = True
        gm.tie_rev = True


def solve_linear(rows, spec, p_base):
    from scipy.optimize import lsq_linear
    A, b, w = build_design(rows, spec)
    if A is None or A.shape[1] == 0:
        return None, {"status": "empty_design"}
    As = A * w[:, None]
    bs = b * w
    norms = np.linalg.norm(As, axis=0)
    norms[norms == 0] = 1.0
    _lb, ub = theta_bounds(spec, p_base)
    res = lsq_linear(As / norms, bs, bounds=(0.0, ub * norms), method="bvls")
    x = res.x / norms
    return x, {"cost": float(res.cost), "status": int(res.status),
               "hit_upper": [bool(v > 0.999 * u) for v, u in zip(x, ub)]}


def expand_theta(x, spec, p_base):
    """theta -> (hydro params, gains per group)."""
    defaults = {"a1": -p_base["Xu"], "a2": -p_base["Xuu"],
                "n1": -p_base["Nr"], "n2": -p_base["Nrr"]}
    damp, j = {}, 0
    for k in ("a1", "a2", "n1", "n2"):
        if k in spec.damp_free:
            damp[k] = float(x[j])
            j += 1
        else:
            damp[k] = float(spec.damp_fixed.get(k, defaults[k]))
    hydro = dict(p_base)
    hydro.update({"Xu": -damp["a1"], "Xuu": -damp["a2"],
                  "Nr": -damp["n1"], "Nrr": -damp["n2"]})
    gains = {}
    for gm in spec.groups:
        params, fixed = gain_layout(gm)
        g = [0.0, 0.0, 0.0, 0.0]
        for col, val in fixed.items():
            g[col] = val
        for _, combo in params:
            v = float(x[j])
            j += 1
            for col, _wt in combo:
                g[col] = v
        gains[gm.name] = g
    return hydro, gains


# ---------------------------------------------------------------------------
# patches / shooting
# ---------------------------------------------------------------------------
def segment_patches(seg, patch_s=PATCH_S, max_per_segment=12):
    n = int(round(patch_s / DT))
    # (len-1)//n keeps a[b+1] in range: obs is x[a:b+1] and needs b < len
    k = (len(seg) - 1) // n
    if k <= 0:
        return []
    idx = list(range(k))
    if k > max_per_segment:
        idx = sorted(set(np.linspace(0, k - 1, max_per_segment).round().astype(int).tolist()))
    out = []
    for i in idx:
        a, b = i * n, (i + 1) * n
        if not np.isfinite(seg.terms[a:b]).all():
            continue                          # missing RPM evidence: drop the patch
        out.append({"x0": seg.x[a], "q": seg.terms[a:b], "obs": seg.x[a:b + 1],
                    "label": str(seg.labels[a]),
                    "mode": float(seg.mode[a]) if seg.mode.size else float("nan"),
                    "sid": seg.sid, "t0": float(seg.t[a]), "group": None})
    return out


def stack_patches(patches):
    X0 = np.stack([p["x0"] for p in patches])
    Q = np.stack([p["q"] for p in patches])
    OBS = np.stack([p["obs"] for p in patches])
    return X0, Q, OBS


DIVERGED_COST = 1.0e3


def _simulate_guarded(X0, Q, gains, gorder, gidx, hydro, d):
    tau = np.empty((Q.shape[0], Q.shape[1], 3))
    for gi, gname in enumerate(gorder):
        m = gidx == gi
        if not m.any():
            continue
        tau[m] = tau_from_q(Q[m], gains[gname], d)
    with np.errstate(all="ignore"):
        sim = simulate(X0, tau, hydro)
    return sim


def residual_vector(theta, spec, p_base, X0, Q, OBS, gidx, gorder):
    hydro, gains = expand_theta(theta, spec, p_base)
    sim = _simulate_guarded(X0, Q, gains, gorder, gidx, hydro, p_base["d_thruster"])
    ru = (sim[:, :, 3] - OBS[:, :, 3]) / U_SCALE
    rr = (sim[:, :, 5] - OBS[:, :, 5]) / R_SCALE
    out = np.concatenate([ru.ravel(), rr.ravel()])
    bad = ~np.isfinite(out)
    if bad.any():
        # a diverging parameter set must look uniformly bad, not NaN
        out[bad] = DIVERGED_COST
    return out


GAIN_UB = 120.0          # N at |q| = 1
DAMP_BOUND_FACTOR = 10.0  # damping magnitude search box, relative to the prior


def damping_upper(p_base):
    """Per-parameter damping box: 10x the documented prior magnitude.

    A box is a modelling choice, not a tolerance: landing on it means the data
    cannot pin the parameter, which is reported as a boundary hit rather than
    silently shipped as an estimate.
    """
    return {"a1": DAMP_BOUND_FACTOR * max(abs(p_base["Xu"]), 1e-3),
            "a2": DAMP_BOUND_FACTOR * max(abs(p_base["Xuu"]), 1e-3),
            "n1": DAMP_BOUND_FACTOR * max(abs(p_base["Nr"]), 1e-3),
            "n2": DAMP_BOUND_FACTOR * max(abs(p_base["Nrr"]), 0.1)}


def theta_bounds(spec, p_base):
    du = damping_upper(p_base)
    ub = [du[k] for k in ("a1", "a2", "n1", "n2") if k in spec.damp_free]
    ub += [GAIN_UB] * sum(len(gain_layout(g)[0]) for g in spec.groups)
    return np.zeros(len(ub)), np.asarray(ub, dtype=float)


def boundary_hits(theta, spec, p_base):
    _lb, ub = theta_bounds(spec, p_base)
    names = spec.theta_names()
    return {nm: float(v / u) for nm, v, u in zip(names, theta, ub) if u > 0 and v >= 0.99 * u}


def shooting_fit(theta0, spec, p_base, X0, Q, OBS, gidx, gorder):
    from scipy.optimize import least_squares
    lb, ub = theta_bounds(spec, p_base)
    theta0 = np.clip(theta0, lb, ub)
    res = least_squares(residual_vector, theta0, bounds=(lb, ub), loss="soft_l1",
                        f_scale=1.0, max_nfev=200,
                        args=(spec, p_base, X0, Q, OBS, gidx, gorder))
    return res.x, {"status": int(res.status), "cost": float(res.cost),
                   "nfev": int(res.nfev), "theta0": theta0.tolist()}


def evaluate_patches(theta, spec, p_base, X0, Q, OBS, gidx, gorder):
    hydro, gains = expand_theta(theta, spec, p_base)
    sim = _simulate_guarded(X0, Q, gains, gorder, gidx, hydro, p_base["d_thruster"])
    eu = sim[:, :, 3] - OBS[:, :, 3]
    er = sim[:, :, 5] - OBS[:, :, 5]
    return {
        "u_rmse": float(np.sqrt(np.mean(eu ** 2))),
        "r_rmse": float(np.sqrt(np.mean(er ** 2))),
        "u_rmse_by_patch": np.sqrt(np.mean(eu ** 2, axis=1)),
        "r_rmse_by_patch": np.sqrt(np.mean(er ** 2, axis=1)),
        "composite": float(np.sqrt(np.mean((eu / U_SCALE) ** 2 + (er / R_SCALE) ** 2))),
        "sim": sim,
    }


def model_dict(hydro, gains, kind, input_models=None):
    return {"kind": kind,
            "hydro": {k: float(hydro[k]) for k in HYDRO_KEYS},
            "gains": {g: [float(v) for v in gv] for g, gv in gains.items()},
            "input_models": {g: (dict(v) if isinstance(v, dict) else v)
                             for g, v in (input_models or {}).items()}}


def prior_gain_vector(p_base):
    """M0 thrust gains from the current config.

    T_i = A_fwd*max(q,0)^2 - A_rev*max(-q,0)^2.  The YAML keeps one number per
    direction, so this is exactly the documented prior when forward == reverse.
    """
    thr = p_base.get("thruster", {})
    a_fwd = float(thr.get("T_max_forward", 25.0))
    a_rev = float(thr.get("T_max_reverse", a_fwd))
    return [a_fwd, a_rev, a_fwd, a_rev]


def prior_model(p_base, group_names):
    g = prior_gain_vector(p_base)
    gains = {name: list(g) for name in group_names}
    ims = {name: {"model": "pwm_equivalent", "unit": "N at |q| = 1"}
           for name in group_names}
    return model_dict(p_base, gains, "baseline_prior", ims)


def replay_windows(segments, model, win_s=REPLAY_WIN_S):
    """Independent replay; only the first state is taken from data.

    Each window is replayed with the SAME per-group input model that was used to
    fit that group (RPM^2 vs equivalent PWM).  A segment whose hardware group has
    no gains in this model is skipped and reported as not_evaluable: borrowing
    another group's thrust parameters would silently transplant a thruster model
    across the 2026-09-08 replacement.
    """
    n = int(round(win_s / DT))
    hold = max(1, int(round(CTRL_REFRESH_S / DT)))
    gains = model.get("gains") or {}
    ims = model.get("input_models") or {}
    hydro = dict(model["hydro"])
    d = hydro["d_thruster"]

    segs, starts, ends, gnames = [], [], [], []
    q_blocks, x0_blocks, obs_blocks = [], [], []
    skipped = {}
    for seg in segments:
        gm = seg.group if seg.group in gains else None
        if gm is None:
            skipped.setdefault(seg.group or "unknown", []).append(seg.sid)
            continue
        mode = (ims.get(gm) or {}).get("model", "pwm_equivalent")
        if mode == "rpm_squared":
            terms, _cov = rpm_terms(seg)
            if terms is None or not np.isfinite(terms).all():
                skipped.setdefault(gm, []).append(seg.sid)
                continue
        else:
            terms = seg.ui
        k = (len(seg) - 1) // n
        for i in range(k):
            a, b = i * n, (i + 1) * n
            segs.append(seg)
            starts.append(a)
            ends.append(b)
            gnames.append(gm)
            q_blocks.append(terms[a:b])
            x0_blocks.append(seg.x[a])
            obs_blocks.append(seg.x[a:b + 1])
    if not segs:
        return None

    X0 = np.stack(x0_blocks)
    OBS = np.stack(obs_blocks)
    Q = np.stack(q_blocks)
    idx = (np.arange(n) // hold) * hold
    Q = Q[:, idx, :]
    tau = np.empty((len(segs), n, 3))
    for i, gm in enumerate(gnames):
        tau[i:i + 1] = tau_from_q(Q[i:i + 1], gains[gm], d)
    sim = simulate(X0, tau, hydro)
    return {"segments": segs, "starts": starts, "ends": ends, "sim": sim,
            "obs": OBS, "Q": Q, "groups": gnames,
            "skipped_by_group": skipped,
            "not_evaluable_segments": sum(len(v) for v in skipped.values())}


def _group_of_segment(seg, gains):
    """No fallback: an unmatched group has no usable propulsion model."""
    return seg.group if seg.group in gains else None


def replay_metrics(res, name="model"):
    segs = res["segments"]
    sim = res["sim"]
    obs = res["obs"]
    out = {"name": name, "n_windows": len(segs),
           "not_evaluable_segments": res.get("not_evaluable_segments", 0),
           "skipped_by_group": res.get("skipped_by_group", {}),
           "by_label": {}, "per_window": []}
    us, rs = [], []
    for i, seg in enumerate(segs):
        a, b = res["starts"][i], res["ends"][i]
        eu = sim[i, :, 3] - obs[i, :, 3]
        er = wrap_pi(sim[i, :, 5] - obs[i, :, 5])
        ex = sim[i, :, 0] - obs[i, :, 0]
        ey = sim[i, :, 1] - obs[i, :, 1]
        epsi = wrap_pi(sim[i, :, 2] - obs[i, :, 2])
        u_rmse = float(np.sqrt(np.mean(eu ** 2)))
        r_rmse = float(np.sqrt(np.mean(er ** 2)))
        pos_rmse = float(np.sqrt(np.mean(ex ** 2 + ey ** 2)))
        final_pos = float(math.hypot(ex[-1], ey[-1]))
        yaw_err = float(abs(epsi[-1]))
        # steady-state segments (last 3 s)
        tail = slice(-int(round(3.0 / DT)), None)
        u_obs_t = obs[i, tail, 3]
        r_obs_t = obs[i, tail, 5]
        steady_u = steady_r = None
        if np.std(u_obs_t) < 0.1 and abs(np.mean(u_obs_t)) > 0.5:
            steady_u = float((np.mean(sim[i, tail, 3]) - np.mean(u_obs_t)) / abs(np.mean(u_obs_t)))
        if np.std(r_obs_t) < 0.05 and abs(np.mean(r_obs_t)) > 0.2:
            steady_r = float((np.mean(sim[i, tail, 5]) - np.mean(r_obs_t)) / abs(np.mean(r_obs_t)))
        lab = set(str(x).split("_saturated")[0] for x in seg.labels[a:b].tolist())
        rec = {"window": f"{seg.sid}@{a}", "u_rmse": u_rmse, "r_rmse": r_rmse,
               "pos_rmse": pos_rmse, "final_pos": final_pos, "yaw_err_rad": yaw_err,
               "steady_u_rel": steady_u, "steady_r_rel": steady_r,
               "labels": sorted(lab),
               "saturated": bool(any(str(x).startswith("saturated")
                                     for x in seg.labels[a:b].tolist()))}
        out["per_window"].append(rec)
        us.append(u_rmse)
        rs.append(r_rmse)
        for l in lab:
            out["by_label"].setdefault(l, {"n": 0, "u": [], "r": []})
            out["by_label"][l]["n"] += 1
            out["by_label"][l]["u"].append(u_rmse)
            out["by_label"][l]["r"].append(r_rmse)
    out["u_rmse"] = float(np.mean(us)) if us else None
    out["r_rmse"] = float(np.mean(rs)) if rs else None
    out["r_rmse_median_degps"] = float(math.degrees(np.median(rs))) if rs else None
    out["pos_rmse"] = float(np.mean([w["pos_rmse"] for w in out["per_window"]])) if segs else None
    out["composite"] = float(np.mean([w["u_rmse"] / U_SCALE for w in out["per_window"]])) if False else None
    eu = np.concatenate([(sim[i, :, 3] - obs[i, :, 3]) / U_SCALE for i in range(len(segs))])
    er = np.concatenate([wrap_pi(sim[i, :, 5] - obs[i, :, 5]) / R_SCALE for i in range(len(segs))])
    out["composite"] = float(np.sqrt(np.mean(eu ** 2 + er ** 2)))
    su = [w["steady_u_rel"] for w in out["per_window"] if w["steady_u_rel"] is not None]
    sr = [w["steady_r_rel"] for w in out["per_window"] if w["steady_r_rel"] is not None]
    out["steady_u_rel"] = float(np.mean(np.abs(su))) if su else None
    out["steady_u_n"] = len(su)
    out["steady_r_rel"] = float(np.mean(np.abs(sr))) if sr else None
    out["steady_r_n"] = len(sr)
    return out


def physical_checks(p, obs):
    m11, m22, m23, m32, m33 = hydro_matrix(p)
    M = np.array([[m11, 0, 0], [0, m22, m23], [0, m32, m33]])
    sym = 0.5 * (M + M.T)
    eigM = np.linalg.eigvalsh(sym)
    minv = np.linalg.inv(M)
    ug = np.linspace(obs["u"][0], obs["u"][1], 11)
    vg = np.linspace(obs["v"][0], obs["v"][1], 11)
    rg = np.linspace(obs["r"][0], obs["r"][1], 11)
    worst = -np.inf
    worst_pt = None
    dmin_sym = np.inf
    jac_worst = -np.inf
    for u in ug:
        for v in vg:
            for r in rg:
                D = np.array([
                    [(-p["Xu"] - p["Xuu"] * abs(u)), 0.0, 0.0],
                    [0.0, (-p["Yv"] - p["Yvv"] * abs(v)), (-p["Yr"] - p["Yrr"] * abs(r))],
                    [0.0, (-p["Nv"] - p["Nvv"] * abs(v)), (-p["Nr"] - p["Nrr"] * abs(r))],
                ])
                dmin_sym = min(dmin_sym, float(np.min(np.linalg.eigvalsh(0.5 * (D + D.T)))))
                A = -minv @ D
                ev = np.linalg.eigvals(A)
                mr = float(np.max(ev.real))
                if mr > worst:
                    worst, worst_pt = mr, (float(u), float(v), float(r))
                # numeric Jacobian of the velocity subsystem at zero thrust
                nu0 = np.array([u, v, r])
                J = np.zeros((3, 3))
                h = 1e-4
                for k in range(3):
                    e = np.zeros(3)
                    e[k] = h
                    for sgn in (1, -1):
                        nu = nu0 + sgn * e
                        st = np.concatenate([[0.0, 0.0, 0.0], nu])[None, :]
                        dd = deriv(st, np.zeros((1, 3)), p)[0, 3:]
                        J[:, k] += sgn * dd / (2 * h)
                jw = float(np.max(np.linalg.eigvals(J).real))
                jac_worst = max(jac_worst, jw)
    return {
        "M_symmetric_part_positive_definite": bool(np.all(eigM > 0)),
        "M_eigenvalues": eigM.tolist(),
        "M_condition": float(np.linalg.cond(M)),
        "M_invertible": bool(abs(np.linalg.det(M)) > 1e-12),
        "min_eig_D_symmetric": dmin_sym,
        "D_symmetric_part_nonnegative": bool(dmin_sym >= -1e-9),
        "max_real_eig_minus_MinvD": worst,
        "worst_point_u_v_r": worst_pt,
        "stable": bool(worst < 0),
        "max_real_eig_velocity_jacobian": jac_worst,
        "no_new_unstable_operating_point": bool(jac_worst < 0),
    }


# ---------------------------------------------------------------------------
# shared stage plumbing
# ---------------------------------------------------------------------------
def load_stage_inputs(args):
    out = args.out
    with open(os.path.join(out, "split_manifest.json"), "r", encoding="utf-8") as fh:
        split = json.load(fh)
    with open(os.path.join(out, "source_manifest.json"), "r", encoding="utf-8") as fh:
        man = json.load(fh)
    role_map = {r["file"]: r for r in split["roles"]}
    groups = {}
    entries = []
    for rec in man["files"]:
        if rec.get("error") or "npz" not in rec:
            continue
        z = np.load(os.path.join(out, rec["npz"]), allow_pickle=True)
        meta = dict(rec)
        meta["group"] = (role_map.get(rec["basename"], {}).get("group") or rec.get("group")
                         or rec["date"])
        role_info = role_map.get(rec["basename"], {})
        meta["role"] = role_info.get("role", rec.get("role"))
        ds = build_dataset(z, meta, split.get("exclusions", {}), {})
        # integrity: segments must match the frozen split ranges
        frozen = role_info.get("t_ranges") or []
        got = [[round(float(s.t0), 3), round(float(s.t1), 3)] for s in ds["segments"]]
        if frozen and frozen != got:
            raise SystemExit(
                f"frozen artifact mismatch for {rec['basename']}: split manifest "
                f"has {len(frozen)} ranges, rebuilt {len(got)}")
        entries.append({"key": rec["basename"], "date": rec["date"],
                        "group": meta["group"], "role": meta["role"],
                        "sha256": rec["sha256"], "segments": ds["segments"]})
        groups.setdefault(meta["group"], [])

    by_key = {e["key"]: e for e in entries}
    sets = {"train": [], "select": [], "validate": [], "blind": [],
            "history_replay": [], "diagnostic": [], "inventory_only": []}
    for e in entries:
        r = e["role"] or ""
        if r.startswith("train"):
            sets["train"].extend(e["segments"])
        elif r.startswith("select"):
            sets["select"].extend(e["segments"])
        elif r.startswith("validate"):
            sets["validate"].extend(e["segments"])
        elif r.startswith("blind"):
            sets["blind"].extend(e["segments"])
        elif r == "history_replay":
            sets["history_replay"].extend(e["segments"])
        elif r == "diagnostic":
            sets["diagnostic"].extend(e["segments"])
        else:
            sets["inventory_only"].extend(e["segments"])
    hist_train, hist_val = [], []
    for key, sid in split.get("history_train", []):
        e = by_key.get(key)
        if e:
            hist_train.extend([s for s in e["segments"] if s.sid == sid])
    for key, sid in split.get("history_validate", []):
        e = by_key.get(key)
        if e:
            hist_val.extend([s for s in e["segments"] if s.sid == sid])
    return split, man, entries, sets, hist_train, hist_val


def group_segments(segments):
    out = {}
    for s in segments:
        out.setdefault(s.group, []).append(s)
    return out


def cap_patches(patches, per_group=250):
    if not patches:
        return patches
    by = {}
    for p in patches:
        by.setdefault(p["group"], []).append(p)
    out = []
    for g, ps in by.items():
        if len(ps) > per_group:
            idx = sorted(set(np.linspace(0, len(ps) - 1, per_group).round().astype(int).tolist()))
            ps = [ps[i] for i in idx]
        out.extend(ps)
    return out


RPM_MIN_TRAIN_COVERAGE = 0.90


def rpm_terms(seg):
    """Thrust regressors from measured RPM: T_i = K_{i,dir} * sign * RPM^2.

    Returns (terms, coverage).  Samples whose RPM is missing keep ``NaN`` so the
    caller can drop them; they are never silently turned into zero thrust.
    """
    if seg.rpm.ndim != 2 or seg.rpm.shape[1] != 2 or seg.terms.size == 0:
        return None, 0.0
    rl = seg.rpm[:, 0]
    rr = seg.rpm[:, 1]
    ok = np.isfinite(rl) & np.isfinite(rr)
    cov = float(ok.mean())
    fwd_l = seg.terms[:, 0] > 0
    rev_l = seg.terms[:, 1] < 0
    fwd_r = seg.terms[:, 2] > 0
    rev_r = seg.terms[:, 3] < 0
    with np.errstate(invalid="ignore"):
        sq_l = np.where(ok, rl, np.nan) ** 2
        sq_r = np.where(ok, rr, np.nan) ** 2
        terms = np.stack([
            np.where(fwd_l, sq_l, np.where(np.isnan(sq_l), np.nan, 0.0)),
            np.where(rev_l, -sq_l, np.where(np.isnan(sq_l), np.nan, 0.0)),
            np.where(fwd_r, sq_r, np.where(np.isnan(sq_r), np.nan, 0.0)),
            np.where(rev_r, -sq_r, np.where(np.isnan(sq_r), np.nan, 0.0)),
        ], axis=-1)
    return terms, cov


RPM_MIN_NONZERO_FRAC = 0.05
RPM_MIN_STD = 50.0


def _rpm_eligible(segs):
    """Decide the group's input model BEFORE mutating anything.

    Finite coverage is not sufficient: the telemetry must also be mapped to the
    two paddles and must actually vary with the output.  A constant-zero or
    unmapped RPM series would otherwise be selected and silently produce a
    zero-thrust model.
    """
    if not segs:
        return False, 0.0, "no_segments"
    covs = []
    for seg in segs:
        if seg.rpm.ndim != 2 or seg.rpm.shape[1] != 2 or seg.rpm.size == 0:
            return False, 0.0, "rpm_to_paddle_mapping_unresolved"
        rl, rr = seg.rpm[:, 0], seg.rpm[:, 1]
        fin = np.isfinite(rl) & np.isfinite(rr)
        cov = float(fin.mean())
        covs.append(cov)
        if cov < RPM_MIN_TRAIN_COVERAGE:
            return False, cov, "coverage_below_90pct"
        if int(fin.sum()) < 50:
            return False, cov, "too_few_rpm_samples"
        nz = min(float(np.mean(rl[fin] > 50.0)), float(np.mean(rr[fin] > 50.0)))
        if nz < RPM_MIN_NONZERO_FRAC:
            return False, cov, "rpm_does_not_vary_with_output"
        if max(float(np.std(rl[fin])), float(np.std(rr[fin]))) < RPM_MIN_STD:
            return False, cov, "rpm_constant"
    return True, min(covs), None


def apply_input_model(segments_by_group):
    """Frozen per-group input model: RPM^2 where RPM qualifies, else equivalent PWM.

    The decision is made for the whole group first and applied atomically; a
    partially converted group would mix two thrust units.
    """
    decision = {}
    for g, segs in segments_by_group.items():
        eligible, cov, why = _rpm_eligible(segs)
        if eligible:
            for seg in segs:
                terms, _c = rpm_terms(seg)
                seg.terms = terms
            decision[g] = {"model": "rpm_squared", "unit": "N per RPM^2",
                           "min_coverage": float(cov)}
        else:
            decision[g] = {"model": "pwm_equivalent", "unit": "N at |q| = 1",
                           "min_coverage": float(cov), "reason": why}
    return decision


def fit_model(segments_by_group, p_base, label):
    input_models = apply_input_model(segments_by_group)
    rows = regression_rows(segments_by_group, p_base)
    if not rows:
        return {"label": label, "status": "no_rows"}
    gnames = sorted({r.group for r in rows})
    spec, info = choose_spec(rows, p_base, gnames)
    x0, opt = solve_linear(rows, spec, p_base)
    if x0 is None:
        return {"label": label, "status": "no_design"}
    patches = []
    for g in gnames:
        for seg in segments_by_group.get(g, []):
            for pt in segment_patches(seg):
                pt["group"] = g
                patches.append(pt)
    patches = cap_patches(patches)
    gidx = np.array([gnames.index(p["group"]) for p in patches])
    X0, Q, OBS = stack_patches(patches)
    theta, shot = shooting_fit(x0, spec, p_base, X0, Q, OBS, gidx, gnames)
    hydro, gains = expand_theta(theta, spec, p_base)
    ev = evaluate_patches(theta, spec, p_base, X0, Q, OBS, gidx, gnames)
    train_rmse_u = float(ev["u_rmse"])
    train_rmse_r = float(ev["r_rmse"])
    by_label = {}
    for i, pt in enumerate(patches):
        lab = str(pt["label"]).split("_saturated")[0]
        d = by_label.setdefault(lab, {"n": 0, "u": [], "r": []})
        d["n"] += 1
        d["u"].append(float(ev["u_rmse_by_patch"][i]))
        d["r"].append(float(ev["r_rmse_by_patch"][i]))
    label_metrics = {k: {"n": v["n"],
                         "u_rmse": float(np.mean(v["u"])),
                         "r_rmse_degps": float(math.degrees(np.mean(v["r"])))}
                     for k, v in by_label.items()}
    return {
        "label": label, "status": "ok",
        "spec": spec, "gnames": gnames, "rows": rows, "input_models": input_models,
        "theta": theta, "theta_linear": x0,
        "hydro": hydro, "gains": gains,
        "diag": {"rank": info.get("rank"), "n_cols": info.get("n_cols"),
                 "cond": info.get("cond"), "reductions": spec.reductions,
                 "boundary_hits": boundary_hits(theta, spec, p_base),
                 "theta_names": spec.theta_names(),
                 "linear_status": opt, "shoot": shot,
                 "n_rows": len(rows), "n_patches": len(patches),
                 "n_segments": sum(len(v) for v in segments_by_group.values())},
        "train_metrics": {"u_rmse": train_rmse_u, "r_rmse": train_rmse_r,
                          "composite": float(ev["composite"]),
                          "r_rmse_median_degps": float(math.degrees(np.median(ev["r_rmse_by_patch"]))),
                          "u_rmse_p90": float(np.percentile(ev["u_rmse_by_patch"], 90)),
                          "by_label": label_metrics},
        "patches": patches,
        "model": model_dict(hydro, gains, "identified", input_models),
    }


def _solve_weighted(A, b, w, ub):
    from scipy.optimize import lsq_linear
    As = A * w[:, None]
    bs = b * w
    norms = np.linalg.norm(As, axis=0)
    norms[norms == 0] = 1.0
    res = lsq_linear(As / norms, bs, bounds=(0.0, ub * norms), method="bvls")
    return res.x / norms


def bootstrap_ci(rows, p_base, spec, seed=BOOTSTRAP_SEED, n=BOOTSTRAP_N):
    """Segment-level bootstrap.  The design matrix is built once; each draw only
    reweights rows, which keeps this affordable for the pooled model."""
    idx_by_seg = {}
    for i, r in enumerate(rows):
        idx_by_seg.setdefault(r.sid, []).append(i)
    segs = sorted(idx_by_seg)
    meta = {"n_segments": len(segs), "n_boot": n, "seed": seed,
            "estimator": "linear_integral_regression_initializer",
            "not_the_final_estimate": True,
            "ci_conditioning": "conditional_on_fixed_inertia_and_input_model",
            "note": ("intervals describe the LINEAR INITIALIZER only; the reported "
                     "parameters come from the 5 s single-shooting fit, for which no "
                     "confidence interval is computed (status: not_evaluable)")}
    if len(segs) < 5:
        meta["reason"] = "fewer_than_5_independent_segments"
        return None, meta
    A, b, _w = build_design(rows, spec)
    if A is None or A.shape[1] == 0:
        meta["reason"] = "empty_design"
        return None, meta
    _lb, ub = theta_bounds(spec, p_base)
    names = spec.theta_names()
    if len(names) != A.shape[1]:
        meta["reason"] = f"theta/design mismatch ({len(names)} vs {A.shape[1]})"
        return None, meta
    rng = np.random.default_rng(seed)
    draws = {nm: [] for nm in names}
    failures = 0
    for _ in range(n):
        pick = rng.integers(0, len(segs), len(segs))
        w = np.zeros(len(rows))
        for j in pick:
            idx = idx_by_seg[segs[j]]
            w[idx] += 1.0 / len(idx)
        try:
            x = _solve_weighted(A, b, np.sqrt(w), ub)
        except Exception:
            failures += 1
            continue
        for nm, v in zip(names, x):
            draws[nm].append(float(v))
    meta["failures"] = failures
    out = {}
    for nm, vals in draws.items():
        if len(vals) < max(20, n // 2):
            out[nm] = {"n": len(vals), "status": "insufficient"}
            continue
        v = np.asarray(vals)
        out[nm] = {"n": int(v.size), "median": float(np.median(v)),
                   "ci95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))],
                   "status": "ok"}
    return out, meta


def scaled_hydro(p, s):
    m11, m22, _m23, _m32, m33 = hydro_matrix(p)
    q = dict(p)
    q["Xu_dot"] = p["mass"] - s * m11
    q["Yv_dot"] = p["mass"] - s * m22
    q["Nr_dot"] = p["Iz"] - s * m33
    return q


def replay_summary(segments, model, name):
    res = replay_windows(segments, model)
    if res is None:
        return {"name": name, "n_windows": 0, "not_evaluable": "no_10s_window"}
    return replay_metrics(res, name)


# ---------------------------------------------------------------------------
# stage: fit
# ---------------------------------------------------------------------------
def stage_fit(args):
    out = args.out
    _ensure_out(out, "fit")
    fit_dir = os.path.join(out, "fit")
    os.makedirs(fit_dir, exist_ok=True)
    p_base = load_baseline(args.baseline)
    split, man, entries, sets, hist_train, hist_val = load_stage_inputs(args)
    print(f"[fit] split hash {split['sha256'][:16]}…  holdout={split['holdout_decision']}")
    print(f"[fit] today train {len(sets['train'])} segs | select {len(sets['select'])} | "
          f"validate {len(sets['validate'])} | blind {len(sets['blind'])}")
    print(f"[fit] history train {len(hist_train)} segs | history validate {len(hist_val)}")

    # ---- M1: today only
    m1 = fit_model(group_segments(sets["train"]), p_base, "M1_today_only")
    if m1.get("status") != "ok":
        raise SystemExit(f"M1 fit failed: {m1}")
    print(f"[fit] M1 rows={m1['diag']['n_rows']} patches={m1['diag']['n_patches']} "
          f"cond={m1['diag']['cond']:.3g} reductions={m1['diag']['reductions']}")
    _print_fit_quality("M1", m1)

    # ---- M2: today + qualified history (shared hull, per-date thruster gains)
    pooled = group_segments(sets["train"] + hist_train)
    m2 = fit_model(pooled, p_base, "M2_joint") if len(pooled) > 1 else {
        "label": "M2_joint", "status": "not_available"}
    if m2.get("status") == "ok":
        print(f"[fit] M2 rows={m2['diag']['n_rows']} patches={m2['diag']['n_patches']} "
              f"cond={m2['diag']['cond']:.3g} reductions={m2['diag']['reductions']}")
        _print_fit_quality("M2", m2)
    else:
        print(f"[fit] M2 unavailable: {m2.get('status')}")

    # ---- M0: current baseline + 25 N symmetric prior
    all_groups = sorted({s.group for s in sets["train"] + hist_train + sets["select"]})
    m0 = prior_model(p_base, all_groups)

    # ---- model selection on today's held-out select set
    eval_segs = sets["select"] or sets["validate"]
    eval_kind = "select" if sets["select"] else "validate"
    r0 = replay_summary(eval_segs, m0, "M0") if eval_segs else {"n_windows": 0}
    r1 = replay_summary(eval_segs, m1["model"], "M1") if eval_segs else {"n_windows": 0}
    r2 = replay_summary(eval_segs, m2["model"], "M2") if (m2.get("status") == "ok" and eval_segs) else {
        "n_windows": 0}
    reason = []
    choose_m2 = False
    if r2.get("n_windows") and r1.get("n_windows"):
        ok_u = r2["u_rmse"] <= 1.05 * r1["u_rmse"]
        ok_r = r2["r_rmse"] <= 1.05 * r1["r_rmse"]
        ok_c = r2["composite"] < r1["composite"]
        choose_m2 = bool(ok_u and ok_r and ok_c)
        reason.append(f"u {r2['u_rmse']:.4f} vs {r1['u_rmse']:.4f} (<=1.05x: {ok_u})")
        reason.append(f"r {math.degrees(r2['r_rmse']):.2f} vs "
                      f"{math.degrees(r1['r_rmse']):.2f} deg/s (<=1.05x: {ok_r})")
        reason.append(f"composite {r2['composite']:.4f} vs {r1['composite']:.4f} (lower: {ok_c})")
    else:
        reason.append("no holdout windows for M1/M2 comparison")

    # Per-history-date negative-transfer check.
    # The diagnostic baseline is fitted on that date's HISTORY TRAIN segments and
    # scored on its HISTORY VALIDATE segments - never on the same data it was
    # fitted on, and a non-verifiable date fails closed.
    hist_check = {}
    for date in sorted({s.group for s in hist_val}):
        hval = [s for s in hist_val if s.group == date]
        htra = [s for s in hist_train if s.group == date]
        if not hval:
            continue
        if not htra:
            hist_check[date] = {"status": "no_history_train_segments_for_diagnostic",
                                "verified": False}
            if choose_m2:
                choose_m2 = False
                reason.append(f"{date}: transfer check not verifiable "
                              f"(no independent training segments) -> refuse sharing")
            continue
        diag = fit_model(group_segments(htra), p_base, f"diag_{date}")
        if diag.get("status") != "ok":
            hist_check[date] = {"status": "diagnostic_fit_failed", "verified": False}
            if choose_m2:
                choose_m2 = False
                reason.append(f"{date}: diagnostic fit failed -> refuse sharing")
            continue
        rd = replay_summary(hval, diag["model"], "diag")
        rj = (replay_summary(hval, m2["model"], "joint")
              if m2.get("status") == "ok" else {"n_windows": 0})
        dc, jc = rd.get("composite"), rj.get("composite")
        finite = (dc is not None and jc is not None
                  and math.isfinite(float(dc)) and math.isfinite(float(jc))
                  and float(dc) > 0.0)
        if not (rd.get("n_windows") and rj.get("n_windows") and finite):
            hist_check[date] = {"diag_composite": dc, "joint_composite": jc,
                                "n_windows": rd.get("n_windows", 0),
                                "verified": False,
                                "status": "not_verifiable_nonfinite_or_no_windows"}
            if choose_m2:
                choose_m2 = False
                reason.append(f"{date}: transfer check not verifiable "
                              f"(non-finite/absent composite) -> refuse sharing")
            continue
        worse = float(jc) > 1.10 * float(dc)
        hist_check[date] = {"diag_composite": float(dc), "joint_composite": float(jc),
                            "ratio_joint_over_diag": float(jc) / float(dc),
                            "joint_worse_gt_10pct": bool(worse),
                            "n_windows": rd.get("n_windows", 0), "verified": True,
                            "diagnostic_fitted_on": "history_train",
                            "scored_on": "history_validate"}
        if choose_m2 and worse:
            choose_m2 = False
            reason.append(f"{date}: joint model degrades >10% vs independent "
                          f"diagnostic -> refuse sharing")
    selected_name = "M2" if choose_m2 else "M1"
    selected = m2 if choose_m2 else m1
    print(f"[fit] model selection ({eval_kind}): {selected_name}")
    for r in reason:
        print(f"[fit]   {r}")

    # ---- bootstrap (conditional on fixed inertia / input model)
    boot, boot_info = bootstrap_ci(selected["rows"], p_base, selected["spec"])
    if boot:
        rel = [f"{k} {v['ci95'][0]:.4g}..{v['ci95'][1]:.4g}" for k, v in boot.items()
               if v.get("status") == "ok"]
        print(f"[fit] bootstrap n={boot_info['n_boot']} failures={boot_info['failures']} "
              f"-> {len(rel)} params with CI")
    else:
        print(f"[fit] bootstrap not reported: {boot_info.get('reason')}")

    # ---- inertia sensitivity (report only, never written back)
    sweep = []
    for s in (0.8, 1.0, 1.2):
        hp = scaled_hydro(selected["hydro"], s)
        mdl = dict(selected["model"])
        mdl = {"kind": "identified", "hydro": {k: float(hp[k]) for k in HYDRO_KEYS},
               "gains": selected["model"]["gains"]}
        rr = replay_summary(eval_segs, mdl, f"s={s}") if eval_segs else {"n_windows": 0}
        sweep.append({"scale": s,
                      "Xu_dot": hp["Xu_dot"], "Yv_dot": hp["Yv_dot"], "Nr_dot": hp["Nr_dot"],
                      "m11": hp["mass"] - hp["Xu_dot"],
                      "m22": hp["mass"] - hp["Yv_dot"],
                      "m33": hp["Iz"] - hp["Nr_dot"],
                      "u_rmse": rr.get("u_rmse"), "r_rmse": rr.get("r_rmse"),
                      "composite": rr.get("composite")})
        print(f"[fit] inertia sweep s={s}: Xu_dot={hp['Xu_dot']:.3f} "
              f"Nr_dot={hp['Nr_dot']:.3f} composite={rr.get('composite')}")

    # ---- smoke test: one real 5 s train patch, fit -> replay
    smoke = {}
    first = sets["train"][0] if sets["train"] else None
    if first is not None and len(first) >= int(PATCH_S / DT):
        pt = segment_patches(first, patch_s=PATCH_S, max_per_segment=1)[0]
        X0, Q, OBS = stack_patches([pt])
        ev = evaluate_patches(selected["theta"], selected["spec"], p_base, X0, Q, OBS,
                              np.array([0]), [first.group])
        smoke = {"segment": first.sid, "t0": float(first.t0), "duration_s": PATCH_S,
                 "u_rmse": ev["u_rmse"], "r_rmse_degps": math.degrees(ev["r_rmse"]),
                 "u_pred_head": [float(v) for v in ev["sim"][0, :6, 3].tolist()],
                 "u_obs_head": [float(v) for v in OBS[0, :6, 3].tolist()],
                 "r_pred_head": [float(v) for v in ev["sim"][0, :6, 5].tolist()],
                 "r_obs_head": [float(v) for v in OBS[0, :6, 5].tolist()]}
        print(f"[fit] smoke ({first.sid} @ {first.t0:.1f}s): "
              f"u_rmse={smoke['u_rmse']:.4f} m/s r_rmse={smoke['r_rmse_degps']:.2f} deg/s")

    # ---- persist
    payload = {
        "baseline": p_base["_raw"],
        "split_hash": split["sha256"],
        "selected": selected_name,
        "selection_reason": reason,
        "eval_set": eval_kind,
        "models": {"M0": m0, "M1": m1["model"],
                   "M2": (m2["model"] if m2.get("status") == "ok" else None)},
        "specs": {"M1": _spec_doc(m1),
                  "M2": (_spec_doc(m2) if m2.get("status") == "ok" else None)},
        "input_models": {"M1": m1.get("input_models"),
                         "M2": (m2.get("input_models") if m2.get("status") == "ok" else None)},
        "diagnostics": {"M1": m1["diag"],
                        "M2": (m2["diag"] if m2.get("status") == "ok" else None)},
        "train_metrics": {"M1": m1["train_metrics"],
                          "M2": (m2["train_metrics"] if m2.get("status") == "ok" else None)},
        "holdout_metrics": {"M0": r0, "M1": r1, "M2": r2},
        "history_transfer_check": hist_check,
        "bootstrap": {"values": boot, "meta": boot_info},
        "inertia_sweep": sweep,
        "smoke": smoke,
        "versions": _versions(),
    }
    with open(os.path.join(fit_dir, "params.json"), "w", encoding="utf-8") as fh:
        json.dump(_clean(payload), fh, ensure_ascii=False, indent=2, default=_json_default)
    _fit_figures(fit_dir, payload, sets, p_base)
    with open(os.path.join(out, "fit_done.json"), "w", encoding="utf-8") as fh:
        json.dump({"selected": selected_name, "split_hash": split["sha256"]}, fh, indent=2)
    print(f"[fit] wrote {fit_dir}\n")


def _print_fit_quality(tag, m):
    tm = m["train_metrics"]
    print(f"[fit] {tag} train u_rmse={tm['u_rmse']:.4f} m/s "
          f"r_rmse={math.degrees(tm['r_rmse']):.2f} deg/s "
          f"(median {tm['r_rmse_median_degps']:.2f} deg/s, u p90 {tm['u_rmse_p90']:.4f})")
    for lab, d in sorted(tm.get("by_label", {}).items(), key=lambda kv: -kv[1]["n"]):
        print(f"[fit]   {tag} {lab:16s} n={d['n']:3d} u={d['u_rmse']:.4f} m/s "
              f"r={d['r_rmse_degps']:.2f} deg/s")
    for g, im in (m.get("input_models") or {}).items():
        print(f"[fit]   {tag} input[{g}] = {im['model']} ({im['unit']})")
    red = m["diag"]["reductions"]
    if red:
        print(f"[fit]   {tag} reductions: {red}")
    hits = m["diag"].get("boundary_hits") or {}
    if hits:
        print(f"[fit]   {tag} BOUNDARY HITS (parameter not pinned by the data): "
              + ", ".join(f"{k}={v:.2f} of bound" for k, v in hits.items()))


def _spec_doc(m):
    if m.get("status") != "ok":
        return {"status": m.get("status")}
    sp = m["spec"]
    return {"damp_free": sp.damp_free, "damp_fixed": sp.damp_fixed,
            "reductions": sp.reductions,
            "groups": [{"name": g.name, "tie_fwd": g.tie_fwd, "tie_rev": g.tie_rev,
                        "no_reverse": g.no_reverse} for g in sp.groups],
            "theta_names": sp.theta_names(),
            "theta": [float(v) for v in m["theta"]]}


def _clean(o):
    """Replace non-finite floats with None so the JSON stays valid."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return v if math.isfinite(v) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return o


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def _versions():
    import matplotlib
    import pymavlink
    import scipy
    import yaml
    return {"python": sys.version.split()[0], "numpy": np.__version__,
            "scipy": scipy.__version__, "pymavlink": pymavlink.__version__,
            "matplotlib": matplotlib.__version__, "pyyaml": yaml.__version__,
            "seed": BOOTSTRAP_SEED}


def _fit_figures(fit_dir, payload, sets, p_base):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sel = payload["models"][payload["selected"]]
    segs = sets["select"] or sets["validate"]
    if segs:
        res = replay_windows(segs, sel)
        if res is not None:
            fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
            k = min(3, len(res["segments"]))
            for i in range(k):
                t = np.arange(res["sim"].shape[1]) * DT
                ax[0].plot(t, res["obs"][i, :, 3], color=f"C{i}", lw=1.0,
                           label=f"obs {res['segments'][i].sid[-6:]}")
                ax[0].plot(t, res["sim"][i, :, 3], color=f"C{i}", ls="--", lw=1.0)
                ax[1].plot(t, np.degrees(res["obs"][i, :, 5]), color=f"C{i}", lw=1.0)
                ax[1].plot(t, np.degrees(res["sim"][i, :, 5]), color=f"C{i}", ls="--", lw=1.0)
            ax[0].set_ylabel("u [m/s]")
            ax[1].set_ylabel("r [deg/s]")
            ax[1].set_xlabel("replay time [s]")
            ax[0].set_title(f"open-loop replay, {payload['selected']} (solid=measured, dashed=model)")
            fig.tight_layout()
            fig.savefig(os.path.join(fit_dir, "replay_parity.png"), dpi=130)
            plt.close(fig)
    # thruster gains
    gains = sel["gains"]
    names = list(gains.keys())
    fig, ax = plt.subplots(figsize=(max(5, 1.6 * len(names)), 3.2))
    xs = np.arange(len(names))
    for j, (lab, col) in enumerate(zip(["L fwd", "L rev", "R fwd", "R rev"], range(4))):
        ax.bar(xs + (j - 1.5) * 0.2, [gains[n][col] for n in names], width=0.2, label=lab)
    ax.set_xticks(xs)
    ax.set_xticklabels(names, rotation=20, ha="right")
    ax.set_ylabel("equivalent thrust scale at |q|=1 [N]")
    ax.set_title("per-thruster, per-direction equivalent gains (conditional on the prior)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(fit_dir, "thruster_gains.png"), dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
# stage: validate
# ---------------------------------------------------------------------------
GATES = {
    "min_blind_windows": 3,
    "u_rmse_max": 0.2,
    "r_rmse_median_max_degps": 12.0,
    "pos_rmse_max": 1.5,
    "steady_u_rel_max": 0.05,
    "steady_r_rel_max": 0.10,
    "worsen_vs_M0_max": 1.05,
    "composite_improve_min": 0.10,
}


def _holdout_verdict_cap(verdict, exposure):
    """An accepted result needs a FRESH independent holdout.

    A holdout that was already scored by an earlier pass cannot license
    `accepted`, however good the numbers look; the replay metrics are kept but
    the verdict is capped (§6: fresh independent blind test required).
    """
    if verdict == "accepted" and (exposure or {}).get("status") == \
            "reused_after_prior_exposure":
        return "insufficient_holdout"
    return verdict


def _gate(name, value, ok):
    return {"gate": name, "value": value, "pass": (None if ok is None else bool(ok))}


def stage_validate(args):
    out = args.out
    _ensure_out(out, "validate")
    fit_dir = os.path.join(out, "fit")
    with open(os.path.join(fit_dir, "params.json"), "r", encoding="utf-8") as fh:
        fit = json.load(fh)
    p_base = load_baseline(args.baseline)
    split, man, entries, sets, hist_train, hist_val = load_stage_inputs(args)
    if split["sha256"] != fit["split_hash"]:
        raise SystemExit("frozen split hash does not match the fitted manifest")
    selected = fit["selected"]
    model = fit["models"][selected]
    m0 = fit["models"]["M0"]

    blind = sets["blind"]
    ok_hold, hold_info = holdout_sufficient(blind) if blind else (False, {"n_windows": 0})
    rb = replay_summary(blind, model, selected) if blind else {"n_windows": 0}
    rb0 = replay_summary(blind, m0, "M0") if blind else {"n_windows": 0}
    rh = replay_summary(sets["history_replay"], model, selected) if sets["history_replay"] else {"n_windows": 0}
    rh0 = replay_summary(sets["history_replay"], m0, "M0") if sets["history_replay"] else {"n_windows": 0}

    gates = []
    nwin = rb.get("n_windows", 0)
    gates.append(_gate("blind_windows>=%d" % GATES["min_blind_windows"], nwin,
                       nwin >= GATES["min_blind_windows"]))
    labels = set(rb.get("by_label", {}).keys())
    has_straight = any(l.startswith("straight") for l in labels)
    has_turn = any(l.startswith("turn") for l in labels)
    gates.append(_gate("blind_covers_straight", has_straight, has_straight or None))
    gates.append(_gate("blind_covers_turn", has_turn, has_turn or None))
    gates.append(_gate("u_rmse<=0.2", rb.get("u_rmse"),
                       None if rb.get("u_rmse") is None else rb["u_rmse"] <= GATES["u_rmse_max"]))
    gates.append(_gate("r_median_rmse<12degps", rb.get("r_rmse_median_degps"),
                       None if rb.get("r_rmse_median_degps") is None
                       else rb["r_rmse_median_degps"] < GATES["r_rmse_median_max_degps"]))
    gates.append(_gate("pos_rmse<1.5m", rb.get("pos_rmse"),
                       None if rb.get("pos_rmse") is None else rb["pos_rmse"] < GATES["pos_rmse_max"]))
    gates.append(_gate("steady_straight_u_rel<5%", rb.get("steady_u_rel"),
                       None if rb.get("steady_u_rel") is None
                       else rb["steady_u_rel"] < GATES["steady_u_rel_max"]))
    gates.append(_gate("steady_turn_r_rel<10%", rb.get("steady_r_rel"),
                       None if rb.get("steady_r_rel") is None
                       else rb["steady_r_rel"] < GATES["steady_r_rel_max"]))
    if rb0.get("n_windows") and rb.get("n_windows"):
        gates.append(_gate("u_not_worse_than_M0_5%",
                           [rb["u_rmse"], rb0["u_rmse"]],
                           rb["u_rmse"] <= GATES["worsen_vs_M0_max"] * rb0["u_rmse"]))
        gates.append(_gate("r_not_worse_than_M0_5%",
                           [rb["r_rmse"], rb0["r_rmse"]],
                           rb["r_rmse"] <= GATES["worsen_vs_M0_max"] * rb0["r_rmse"]))
        gates.append(_gate("composite_improved>=10%",
                           [rb["composite"], rb0["composite"]],
                           rb["composite"] <= (1.0 - GATES["composite_improve_min"]) * rb0["composite"]))
    else:
        for g in ("u_not_worse_than_M0_5%", "r_not_worse_than_M0_5%",
                  "composite_improved>=10%"):
            gates.append(_gate(g, None, None))

    # physical admissibility
    obs_all = _observed_envelope(sets["train"] + blind)
    phys = physical_checks(model["hydro"], obs_all)
    gates.append(_gate("M_symmetric_positive_definite", phys["M_eigenvalues"],
                       phys["M_symmetric_part_positive_definite"]))
    gates.append(_gate("M_invertible", phys["M_condition"], phys["M_invertible"]))
    gates.append(_gate("D_symmetric_part_nonnegative", phys["min_eig_D_symmetric"],
                       phys["D_symmetric_part_nonnegative"]))
    gates.append(_gate("max_Re_eig(-M^-1 D)<0", phys["max_real_eig_minus_MinvD"],
                       phys["stable"]))
    gates.append(_gate("velocity_jacobian_stable", phys["max_real_eig_velocity_jacobian"],
                       phys["no_new_unstable_operating_point"]))

    failed = [g["gate"] for g in gates if g["pass"] is False]
    sources_bad = [r["basename"] for r in man["files"]
                   if r.get("error") and r.get("date") == "2026-11-02"]
    if sources_bad:
        verdict = "source_unreadable"
    elif nwin < GATES["min_blind_windows"] or not (has_straight and has_turn):
        verdict = "insufficient_holdout"
    elif failed:
        verdict = "rejected"
    else:
        verdict = "accepted"
    gates.append(_gate("fresh_independent_holdout", HOLDOUT_EXPOSURE.get("status"),
                       HOLDOUT_EXPOSURE.get("status") != "reused_after_prior_exposure"))
    verdict = _holdout_verdict_cap(verdict, HOLDOUT_EXPOSURE)
    if verdict == "insufficient_holdout":
        failed = failed or ["fresh_independent_holdout"]

    print("\n[validate] gates")
    for g in gates:
        v = g["value"]
        if isinstance(v, list):
            v = "[" + ", ".join(f"{x:.4g}" for x in v) + "]"
        elif isinstance(v, float):
            v = f"{v:.4g}"
        print(f"  {'PASS' if g['pass'] else ('FAIL' if g['pass'] is False else 'N/A ')} "
              f"{g['gate']:38s} {v}")
    print(f"[validate] physical: {json.dumps({k: phys[k] for k in ('M_eigenvalues','min_eig_D_symmetric','max_real_eig_minus_MinvD','max_real_eig_velocity_jacobian')}, default=_json_default)}")
    print(f"[validate] blind {selected}: u_rmse={rb.get('u_rmse')} "
          f"r_med={rb.get('r_rmse_median_degps')} pos={rb.get('pos_rmse')} "
          f"composite={rb.get('composite')}")
    print(f"[validate] blind M0: u_rmse={rb0.get('u_rmse')} "
          f"r_med={rb0.get('r_rmse_median_degps')} pos={rb0.get('pos_rmse')} "
          f"composite={rb0.get('composite')}")
    print(f"[validate] holdout provenance: {HOLDOUT_EXPOSURE['status']} "
          f"(first opened by {HOLDOUT_EXPOSURE['prior_run']}, "
          f"verdict {HOLDOUT_EXPOSURE['prior_verdict']}) - not an untouched blind test")
    print(f"[validate] verdict: {verdict}")

    metrics_doc = {
        "verdict": verdict, "selected_model": selected,
        "split_hash": split["sha256"],
        "holdout": hold_info,
        "holdout_exposure": HOLDOUT_EXPOSURE,
        "blind": rb, "blind_M0": rb0,
        "history_replay": rh, "history_replay_M0": rh0,
        "history_transfer_check": fit["history_transfer_check"],
        "gates": gates, "failed_gates": failed,
        "physical": phys,
        "observed_envelope": obs_all,
        "model_selection": {"selected": selected, "reason": fit["selection_reason"]},
        "inertia_sweep": fit["inertia_sweep"],
        "bootstrap": fit["bootstrap"],
        "versions": fit["versions"],
        "limitations": [
            "No live weighing, effective-inertia or bollard-pull calibration for 2026-11-02; "
            "mass/Iz/added mass are the current baseline and every force-scale parameter is "
            "conditional_on_prior.",
            "ESC telemetry is absent for all 2026-11-02 logs, so no PWM->RPM model and no "
            "K_T in N/RPM^2 is reported; only an equivalent PWM->force model is identified.",
            "Thrusters were replaced on 2026-09-08, so no thruster curve, gain, deadband, delay "
            "or voltage correction is shared across that boundary.",
            "No water-current measurement: the result is an equivalent model for this water "
            "body / operating envelope, not a current-compensated one.",
            "The RCOU channels are post-mixing motor outputs; the controller consumes "
            "steering/throttle RC input. Per-thruster curves are not deployable by editing "
            "T_max alone.",
            "PWM neutral (1500 us) is NOT verified to produce zero thrust: no thrust "
            "measurement, no ESC telemetry and no verified ESC-to-prop mapping exist for "
            "2026-11-02. Logged PWM is a command proxy, not a measured force; no conclusion "
            "about the actual propulsion response is drawn from it.",
            "The logs show a sustained yaw rate while logged RCOU sits at 1500, with ARM/MODE "
            "transitions recorded normally and long recording gaps. This is an anomaly that "
            "warrants hardware investigation: the logs record only what the flight controller "
            "emitted, not what the ESCs received, so neither the mechanism nor a "
            "command-versus-response mismatch is established here. Diagnosis (ESC mid-point "
            "calibration, signal integrity, supply/thermal) and a verified safe-disarm are "
            "required before any further water test.",
        ],
    }
    _write_report(out, args, fit, metrics_doc, entries, man, split, sets, rb, rb0, rh, rh0)
    _write_param_package(out, args, fit, metrics_doc, entry_meta=man, split=split)
    _validate_figures(out, fit, model, m0, blind, rb, rb0)
    with open(os.path.join(out, "validation_metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(_strip_heavy(metrics_doc), fh, ensure_ascii=False, indent=2, default=_json_default)
    with open(os.path.join(out, "validate_done.json"), "w", encoding="utf-8") as fh:
        json.dump({"verdict": verdict, "split_hash": split["sha256"]}, fh, indent=2)
    print(f"[validate] wrote {out}\n")
    return verdict


def _observed_envelope(segments):
    if not segments:
        return {"u": [0.0, 1.5], "v": [-0.5, 0.5], "r": [-0.4, 0.4]}
    X = np.concatenate([s.x for s in segments], axis=0)
    def rng(col, pad=0.0):
        v = X[:, col]
        v = v[np.isfinite(v)]
        if v.size == 0:
            return [-1e-3, 1e-3]
        return [float(np.min(v) - pad), float(np.max(v) + pad)]
    return {"u": rng(3), "v": rng(4), "r": rng(5), "n_samples": int(X.shape[0])}


def _strip_heavy(doc):
    """Drop per-window arrays that would bloat the JSON."""
    d = dict(doc)
    for k in ("blind", "blind_M0", "history_replay", "history_replay_M0"):
        if isinstance(d.get(k), dict) and d[k].get("per_window"):
            d[k] = dict(d[k])
            d[k]["per_window_head"] = d[k]["per_window"][:5]
            d[k].pop("per_window", None)
    return d


def _validate_figures(out, fit, model, m0, blind, rb, rb0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if blind:
        fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
        names = ["M0", fit["selected"]]
        com = [rb0.get("composite"), rb.get("composite")]
        ur = [rb0.get("u_rmse"), rb.get("u_rmse")]
        rr = [math.degrees(rb0.get("r_rmse")) if rb0.get("r_rmse") else np.nan,
              math.degrees(rb.get("r_rmse")) if rb.get("r_rmse") else np.nan]
        ax[0].bar(names, ur)
        ax[0].set_ylabel("u RMSE [m/s]")
        ax[0].set_title("blind replay")
        ax[1].bar(names, rr)
        ax[1].set_ylabel("r RMSE [deg/s]")
        ax[1].set_title(f"composite: {com[0]:.3f} -> {com[1]:.3f}")
        fig.tight_layout()
        fig.savefig(os.path.join(out, "validation_blind_compare.png"), dpi=130)
        plt.close(fig)
        # same-window u/r trace comparison
        res0 = replay_windows(blind, m0)
        resn = replay_windows(blind, model)
        if res0 is not None and resn is not None:
            i = 0
            t = np.arange(resn["sim"].shape[1]) * DT
            fig, ax = plt.subplots(2, 1, figsize=(9, 5), sharex=True)
            ax[0].plot(t, resn["obs"][i, :, 3], color="k", lw=1.2, label="measured")
            ax[0].plot(t, res0["sim"][i, :, 3], color="C3", lw=1.0, label="M0")
            ax[0].plot(t, resn["sim"][i, :, 3], color="C2", lw=1.2, label=fit["selected"])
            ax[0].set_ylabel("u [m/s]")
            ax[1].plot(t, np.degrees(resn["obs"][i, :, 5]), color="k", lw=1.2)
            ax[1].plot(t, np.degrees(res0["sim"][i, :, 5]), color="C3", lw=1.0)
            ax[1].plot(t, np.degrees(resn["sim"][i, :, 5]), color="C2", lw=1.2)
            ax[1].set_ylabel("r [deg/s]")
            ax[1].set_xlabel("replay time [s]")
            ax[0].legend(fontsize=8, ncol=3)
            ax[0].set_title("same blind window, M0 vs candidate")
            fig.tight_layout()
            fig.savefig(os.path.join(out, "validation_same_window.png"), dpi=130)
            plt.close(fig)


# ---------------------------------------------------------------------------
# parameter package
# ---------------------------------------------------------------------------
def _write_param_package(out, args, fit, metrics, entry_meta, split):
    import yaml
    sel = fit["selected"]
    model = fit["models"][sel]
    hydro = model["hydro"]
    gains = model["gains"]
    base = load_baseline(args.baseline)
    boot = (fit["bootstrap"] or {}).get("values") or {}
    groups = fit["specs"][sel]["groups"]
    theta_names = fit["specs"][sel]["theta_names"]
    theta = fit["specs"][sel]["theta"]

    # --- surge_params.json
    surge = {
        "method": "1 s integral-window regression + 5 s single-shooting fit; "
                  "shared hull damping, per-group per-thruster equivalent PWM gains",
        "mass_anchor_kg": hydro["mass"],
        "effective_surge_mass_m11_kg": hydro["mass"] - hydro["Xu_dot"],
        "Xu_N_per_mps": hydro["Xu"],
        "Xuu_N_per_mps2": hydro["Xuu"],
        "normalised_minus_Xu_over_m11_per_s": -hydro["Xu"] / (hydro["mass"] - hydro["Xu_dot"]),
        "normalised_minus_Xuu_over_m11_per_m": -hydro["Xuu"] / (hydro["mass"] - hydro["Xu_dot"]),
        "sign_convention": "Fossen signed; D_11 = -Xu - Xuu*|u|",
        "status": _damping_status(fit, sel, "a1", abs(hydro["Xu"]),
                                  damping_upper(base)["a1"], base["Xu"], boot),
        "status_Xuu": _damping_status(fit, sel, "a2", abs(hydro["Xuu"]),
                                      damping_upper(base)["a2"], base["Xuu"], boot),
        "boundary_hits": (fit["diagnostics"][sel] or {}).get("boundary_hits"),
        "T_max_N": None,
        "T_max_note": "not identified: free-running logs cannot certify T_max without a "
                      "bollard pull / RPM-calibrated thrust chain",
        "prior_0723": {"Xu": base["Xu"], "Xuu": base["Xuu"]},
        "ci_final_estimate": "not_evaluable",
        "ci_final_note": ("no confidence interval is computed for the shooting "
                          "estimate; the intervals below belong to the linear "
                          "initializer"),
        "ci_linear_initializer": {k: boot.get(k) for k in boot
                                  if k.endswith(("a1", "a2"))},
        "groups": {g: dict(_group_gain_doc(gains[g]),
                           paddle_ratio_diagnostic=_gain_ratio_diagnostic(gains[g]))
                   for g in gains},
        "reductions": fit["specs"][sel]["reductions"],
    }
    with open(os.path.join(out, "surge_params.json"), "w", encoding="utf-8") as fh:
        json.dump(surge, fh, ensure_ascii=False, indent=2, default=_json_default)

    # --- yaw_params.json
    yaw = {
        "method": "shared hull damping via the same regression/shooting pass; d = "
                  f"{hydro['d_thruster']} m taken from the baseline geometry",
        "Iz_kgm2_fixed": hydro["Iz"],
        "Iz_eff_kgm2": hydro["Iz"] - hydro["Nr_dot"],
        "Nr_Nms_per_rad_magnitude": -hydro["Nr"],
        "Nrr_Nms2_per_rad2_magnitude": -hydro["Nrr"],
        "Nr_signed": hydro["Nr"],
        "Nrr_signed": hydro["Nrr"],
        "normalised_minus_Nr_over_m33": -hydro["Nr"] / (hydro["Iz"] - hydro["Nr_dot"]),
        "normalised_minus_Nrr_over_m33": -hydro["Nrr"] / (hydro["Iz"] - hydro["Nr_dot"]),
        "d_thruster_m": hydro["d_thruster"],
        "sign_convention": "Nr/Nrr reported as positive damping magnitudes (as in the "
                           "2026-09-03 product); signed values are given alongside",
        "Nv_Nvv_Yr_Yrr": "held at baseline (weakly observed cross terms, not opened)",
        "status": _damping_status(fit, sel, "n1", abs(hydro["Nr"]),
                                  damping_upper(base)["n1"], base["Nr"], boot),
        "status_Nrr": _damping_status(fit, sel, "n2", abs(hydro["Nrr"]),
                                      damping_upper(base)["n2"], base["Nrr"], boot),
        "boundary_hits": (fit["diagnostics"][sel] or {}).get("boundary_hits"),
        "prior": {"Nr": base["Nr"], "Nrr": base["Nrr"], "Nr_dot": base["Nr_dot"]},
        "ci_final_estimate": "not_evaluable",
        "ci_final_note": ("no confidence interval is computed for the shooting "
                          "estimate; the intervals below belong to the linear "
                          "initializer"),
        "ci_linear_initializer": {k: boot.get(k) for k in boot
                                  if k.endswith(("n1", "n2"))},
    }
    with open(os.path.join(out, "yaw_params.json"), "w", encoding="utf-8") as fh:
        json.dump(yaw, fh, ensure_ascii=False, indent=2, default=_json_default)

    # --- thruster_model.json
    rpm_any = any(e.get("rpm_ok") and e.get("date") == "2026-11-02" for e in entry_meta["files"])
    thr = {
        "meta": {
            "data": "2026-11-02 15-31-04 training, 16-00-09 selection, 16-19-57 blind",
            "rpm_available": bool(rpm_any),
            "rpm_note": ("no ESC.RPM records exist in any 2026-11-02 log; a PWM->RPM model and "
                         "K_T in N/RPM^2 are therefore NOT reported for this group"
                         if not rpm_any else
                         "RPM telemetry present for at least one historical group; that group "
                         "is fitted with T = K*RPM^2 and its gains are in N per RPM^2"),
            "pwm_center_us": 1500.0,
            "deadband_us": PWM_DEADZONE_US,
            "deadband_note": "fixed 30 us PRIOR, not identified",
            "model_form": "T_i = A_i+ * max(q_i,0)^2 - A_i- * max(-q_i,0)^2, "
                          "q from SERVOx MIN/TRIM/MAX with the 30 us deadband prior",
            "delay_note": None,
        },
        "instance_channel_map": None,
        "channel_map_note": "no ESC telemetry; channels resolved from SERVO1_FUNCTION=73 "
                            "(left) and SERVO3_FUNCTION=74 (right) and cross-checked against "
                            "the sign of diff-PWM vs ENU yaw rate",
        "per_group_thrust_model": {
            g: dict(_group_gain_doc(gains[g]),
                    input_model=(fit.get("input_models", {}).get(sel, {})
                                 .get(g, {}).get("model", "pwm_equivalent")),
                    unit=(fit.get("input_models", {}).get(sel, {})
                          .get(g, {}).get("unit", "N at |q| = 1")))
            for g in gains
        },
        "asymmetry_gain_ratio_right_over_left": _asym_ratio(gains),
        "reductions": fit["specs"][sel]["reductions"],
    }
    with open(os.path.join(out, "thruster_model.json"), "w", encoding="utf-8") as fh:
        json.dump(thr, fh, ensure_ascii=False, indent=2, default=_json_default)

    ims = (fit.get("input_models") or {}).get(sel, {})

    # --- parameter_comparison.csv
    rows = []

    def add(name, unit, old, new, status, src, note=""):
        rows.append({"parameter": name, "unit": unit, "current_value": old,
                     "candidate_value": new, "status": status, "source": src, "note": note})

    du = damping_upper(base)
    add("vehicle.Xu", "N/(m/s)", base["Xu"], hydro["Xu"],
        _damping_status(fit, sel, "a1", abs(hydro["Xu"]), du["a1"], base["Xu"], boot),
        f"{sel} surge row", "negative damping")
    add("vehicle.Xuu", "N/(m/s)^2", base["Xuu"], hydro["Xuu"],
        _damping_status(fit, sel, "a2", abs(hydro["Xuu"]), du["a2"], base["Xuu"], boot),
        f"{sel} surge row", "negative damping")
    add("vehicle.Nr", "N*m*s/rad", base["Nr"], hydro["Nr"],
        _damping_status(fit, sel, "n1", abs(hydro["Nr"]), du["n1"], base["Nr"], boot),
        f"{sel} yaw row", "negative damping")
    add("vehicle.Nrr", "N*m*s^2/rad^2", base["Nrr"], hydro["Nrr"],
        _damping_status(fit, sel, "n2", abs(hydro["Nrr"]), du["n2"], base["Nrr"], boot),
        f"{sel} yaw row", "negative damping")
    for k in ("mass", "Iz", "xg", "Xu_dot", "Yv_dot", "Yr_dot", "Nv_dot", "Nr_dot",
              "Yv", "Yr", "Nv", "Yvv", "Yrr", "Nvv"):
        add(f"vehicle.{k}", "-", base[k], base[k], "retained_prior",
            "baseline", "held fixed / not identified in this pass")
    add("thruster.T_max_forward", "N", base["thruster"].get("T_max_forward"),
        base["thruster"].get("T_max_forward"), "not_evaluable", "baseline",
        "cannot be certified from free-running logs without bollard pull or RPM")
    add("thruster.T_max_reverse", "N", base["thruster"].get("T_max_reverse"),
        base["thruster"].get("T_max_reverse"), "not_evaluable", "baseline",
        "reverse thrust not identified")
    if groups and groups[0]["tie_fwd"]:
        add("thruster.gain_L_vs_R", "N", None, None, "not_identifiable", sel,
            "left/right asymmetry not separable; gains constrained equal")
    for g in gains:
        for i, lbl in enumerate(("A_L_fwd", "A_L_rev", "A_R_fwd", "A_R_rev")):
            add(f"thruster.{g}.{lbl}", ims.get(g, {}).get("unit", "N at |q|=1"),
                None, gains[g][i], _gain_status(gains[g], i), f"{sel} ({g})",
                "equivalent scale; absolute N depends on the fixed mass/inertia prior")
    _write_csv(os.path.join(out, "parameter_comparison.csv"), rows)

    # --- candidate YAML (only when the gates passed)
    if metrics["verdict"] != "accepted":
        print(f"[validate] candidate YAML not generated (verdict={metrics['verdict']})")
        return
    cand = _candidate_yaml(base, hydro, fit, sel)
    path = os.path.join(out, "usv_params_candidate.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(cand)
    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    assert doc["/**"]["ros__parameters"]["vehicle"]["Xu"] == hydro["Xu"]
    print(f"[validate] wrote {path} (yaml.safe_load ok)")


def _group_gain_doc(g):
    return {"A_L_fwd_N": g[0], "A_L_rev_N": g[1], "A_R_fwd_N": g[2], "A_R_rev_N": g[3]}


def _asym_ratio(gains):
    """Right/left forward-gain ratio as a DIAGNOSTIC only.

    When one side's gain is near zero the ratio explodes and says nothing about
    the hardware; it is withheld in that case rather than published as a value.
    """
    ratios, degenerate = [], []
    for g, v in gains.items():
        lo = min(abs(v[0]), abs(v[2]))
        hi = max(abs(v[0]), abs(v[2]))
        if hi <= 1e-9:
            degenerate.append(g)
            continue
        if lo < 0.05 * hi:
            degenerate.append(g)
            continue
        ratios.append(abs(v[2]) / abs(v[0]))
    if not ratios:
        return {"median": None, "range": None,
                "status": "withheld_side_gain_near_zero",
                "degenerate_groups": degenerate,
                "note": ("a near-zero gain on one side makes the ratio meaningless; "
                         "no asymmetry value is reported")}
    r = np.asarray(ratios)
    return {"median": float(np.median(r)),
            "range": [float(r.min()), float(r.max())],
            "status": "diagnostic_only",
            "degenerate_groups": degenerate,
            "note": ("diagnostic only; usability depends on the regression design "
                     "actually separating left/right gains")}


def _param_status(key, fit):
    """Coarse status used by the report table."""
    sel = fit["selected"]
    spec = fit["specs"][sel]
    if key in (spec.get("damp_fixed") or {}):
        return "retained_prior"
    if key not in (spec.get("theta_names") or []):
        return "retained_prior"
    if any("not_identifiable" in r for r in (spec.get("reductions") or [])):
        return "not_identifiable"
    return "conditional_on_prior"


def _damping_status(fit, sel, key, value, bound, prior, boot):
    """Qualification of one estimated damping magnitude, using ONLY conditions
    that are valid for the shooting estimator.

    The bootstrap intervals describe the linear initializer, so they must not be
    used to accept or reject the shooting estimate.  What IS valid for the
    shooting estimate is where it landed relative to its search box; that is
    reported as a diagnostic.  The estimate's own uncertainty is `not_evaluable`
    (no interval is computed for it), and per the plan such a parameter is not a
    reliable update.
    """
    spec = fit["specs"][sel]
    if key in (spec.get("damp_fixed") or {}):
        return "retained_prior"
    if key not in (spec.get("theta_names") or []):
        return "retained_prior"
    # Only the plan's vocabulary is returned here.  Bound hits / near-zero
    # values are published as separate diagnostic fields, and the shooting
    # estimate's own uncertainty is `not_evaluable`, so such a parameter is
    # simply not a usable update.
    if bound > 0 and value >= 0.99 * bound:
        return "not_identifiable"
    if abs(prior) > 1e-9 and value <= 0.01 * abs(prior):
        return "not_identifiable"
    return "conditional_on_prior"


def _gain_status(gains, gi):
    """Qualification of one effective thrust scale.

    No identifiability claim is made: left/right separability is decided by the
    regression design, never by a magnitude threshold.  Ratios are diagnostics.
    """
    return "conditional_on_prior"


def _gain_ratio_diagnostic(gains):
    """Paddle/direction ratios, published as diagnostics (no verdict attached)."""
    fwd_ref = max(abs(gains[0]), abs(gains[2]), 1e-12)
    rev_ref = max(abs(gains[1]), abs(gains[3]), 1e-12)
    return {"A_L_fwd_over_max_fwd": abs(gains[0]) / fwd_ref,
            "A_R_fwd_over_max_fwd": abs(gains[2]) / fwd_ref,
            "A_L_rev_over_max_rev": abs(gains[1]) / rev_ref,
            "A_R_rev_over_max_rev": abs(gains[3]) / rev_ref,
            "note": ("ratios are diagnostics only; left/right separability is "
                     "decided by the regression design, not by these numbers")}


def _candidate_yaml(base, hydro, fit, sel):
    lines = [
        "# CANDIDATE parameter file - 2026-11-02 re-identification.",
        "# NOT deployed. Generated offline; validate before any use on the real boat.",
        "#",
        "# Only parameters that passed the independent-replay gates are replaced.",
        "# Every force-scale value is conditional on the fixed mass/inertia prior:",
        "# there is no 2026-11-02 weighing, effective-inertia or bollard-pull",
        "# calibration, so these are equivalent-model numbers, not absolute",
        "# measured thrust calibration.",
        "#",
        "# Retained (fixed, not re-identified): mass, Iz, xg, Xu_dot, Yv_dot, Yr_dot,",
        "# Nv_dot, Nr_dot, Yv, Yr, Nv, Yvv, Yrr, Nvv.",
        "# Not identified at all: T_max_forward / T_max_reverse (see",
        "# parameter_comparison.csv), reverse thrust, thrust slew rate, voltage",
        "# compensation, per-thruster curves (kept in thruster_model.json).",
        "",
        "/**:",
        "  ros__parameters:",
        "    vehicle:",
        f"      mass: {base['mass']!r}          # retained prior",
        f"      Iz: {base['Iz']!r}            # retained prior",
        f"      xg: {base['xg']!r}            # retained prior",
        f"      d_thruster: {base['d_thruster']!r}    # retained geometry",
        f"      length: {base['_raw']['vehicle'].get('length', 1.2)!r}",
        f"      beam: {base['_raw']['vehicle'].get('beam', 0.6)!r}",
        f"      draft: {base['_raw']['vehicle'].get('draft', 0.1)!r}",
        f"      height: {base['_raw']['vehicle'].get('height', 0.3)!r}",
        f"      Xu_dot: {base['Xu_dot']!r}",
        f"      Yv_dot: {base['Yv_dot']!r}",
        f"      Yr_dot: {base['Yr_dot']!r}",
        f"      Nv_dot: {base['Nv_dot']!r}",
        f"      Nr_dot: {base['Nr_dot']!r}",
        f"      # re-identified ({sel}), conditional_on_prior",
        f"      Xu: {hydro['Xu']!r}",
        f"      Xuu: {hydro['Xuu']!r}",
        f"      Nr: {hydro['Nr']!r}",
        f"      Nrr: {hydro['Nrr']!r}",
        f"      Yv: {base['Yv']!r}",
        f"      Yr: {base['Yr']!r}",
        f"      Nv: {base['Nv']!r}",
        f"      Yvv: {base['Yvv']!r}",
        f"      Yrr: {base['Yrr']!r}",
        f"      Nvv: {base['Nvv']!r}",
        "",
        "    thruster:",
        f"      pwm_min: {base['thruster'].get('pwm_min', 1000)!r}",
        f"      pwm_center: {base['thruster'].get('pwm_center', 1500)!r}",
        f"      pwm_max: {base['thruster'].get('pwm_max', 2000)!r}",
        f"      T_max_forward: {base['thruster'].get('T_max_forward', 25.0)!r}"
        "   # retained: not certifiable from these logs",
        f"      T_max_reverse: {base['thruster'].get('T_max_reverse', 25.0)!r}"
        "   # retained: not identified",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def _write_report(out, args, fit, metrics, entries, man, split, sets, rb, rb0, rh, rh0):
    sel = fit["selected"]
    model = fit["models"][sel]
    hydro = model["hydro"]
    base = fit["baseline"]["vehicle"]
    lines = []
    A = lines.append
    A("# 2026-11-02 参数重辨识报告")
    A("")
    A(f"- 数据根：`{args.data_root}`")
    A(f"- 历史补充：`{args.extra_history}`")
    A(f"- 基线：`{args.baseline}`（只读，未修改）")
    A(f"- 排除清单：`{args.exclusions}`")
    A(f"- 产出：`{out}`")
    A(f"- 清单 hash：`{split['sha256']}`")
    A(f"- 结论：**{metrics['verdict']}**；选用模型 **{sel}**")
    A("")
    A("## 1. 执行命令")
    A("")
    A("```bash")
    A("export PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg")
    A(f"python3 scripts/reidentify_20261102.py --data-root '{args.data_root}' \\")
    A(f"  --extra-history '{args.extra_history}' --baseline '{args.baseline}' \\")
    A(f"  --exclusions '{args.exclusions}' --out '{args.out}' --stage prepare")
    A("# 同一组五个路径参数，依次 --stage fit、--stage validate")
    A("```")
    A("")
    A("依赖：" + ", ".join(f"{k}={v}" for k, v in metrics["versions"].items()))
    A("")
    A("## 2. 数据清点与角色")
    A("")
    A("| 文件 | 日期 | 硬件组 | 角色 | 字节 | SHA256 | 固件 | boot | 干净段 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for rec in man["files"]:
        if rec.get("error"):
            A(f"| `{rec['basename']}` | {rec['date']} | - | {rec.get('role')} | - | - | - | - | "
              f"不可读: {rec['error']} |")
            continue
        A(f"| `{rec['basename']}` | {rec['date']} | {rec.get('group')} | {rec.get('role')} | "
          f"{rec['size']} | `{rec['sha256'][:16]}…` | {rec.get('firmware')} | "
          f"{rec.get('boot_count')} | {rec.get('n_clean_segments')} |")
    A("")
    A(f"盲测/训练划分决策：`{split['holdout_decision']}`；盲测窗口统计 "
      f"{split['blind_info']}；选择集 {split['select_info']}。")
    A("")
    A(f"**盲测暴露声明**：`{HOLDOUT_EXPOSURE['file']}` 已被 `{HOLDOUT_EXPOSURE['prior_run']}` "
      f"评分过一次（结论 `{HOLDOUT_EXPOSURE['prior_verdict']}`）。"
      f"本次沿用同一冻结划分，未因该次结果更换盲测文件或修改任何门槛，"
      f"但因此本次结果属于 **复用盲测**，不是一次性盲测。")
    A("")
    A("## 3. 输入与坐标口径")
    A("")
    A("- `psi = π/2 − yaw_NED`，`u = VN·cos(yaw)+VE·sin(yaw)`，"
      "`v = VN·sin(yaw)−VE·cos(yaw)`，`r = −GyrZ`（与既有 ROS 约定一致）。")
    A("- 推力通道由 `SERVO1_FUNCTION=73`（左）/`SERVO3_FUNCTION=74`（右）解析，"
      "并用『差动 PWM 与 ENU 艏摇率同号』交叉验证，未沿用任何旧的 C1/C3 假设。")
    A("- 今日三份航行日志 **ESC 记录为 0**，因此不存在 PWM→RPM 模型，也不报告 "
      "N/RPM² 的 K_T；只给出等效 PWM→力模型。")
    A("")
    A("## 4. 噪声、缺口与排除")
    A("")
    excl = split.get("exclusions", {})
    for rec in man["files"]:
        w = excl.get(rec["basename"]) or []
        if w:
            A(f"- `{rec['basename']}`：{len(w)} 个异常窗，按 `TimeUS = 秒×1e6` 应用，"
              f"前后各扩 {EXCL_PAD_S:g} s，并延伸到该次连续运动结束；**不读取旧 verdict**。")
    A("")
    A("其余排除规则：未解锁/解锁未知、系泊台架、GPS `Status<3` 或 `HDop>1.0`、"
      "`|Roll|>10°`、`|Pitch|>15°`、裁剪计数增加、缺口两侧 1 s、模式/主核切换两侧 1 s、"
      "映射变化窗、航向微分与 `−GyrZ` 的 RMSE>10°/s。缺健康字段记为『缺证据』，"
      "不当作通过。")
    A("")
    A("## 5. 模型与可辨识性")
    A("")
    A("固定：`mass`、`Iz`、`xg`、附加质量、`Yv/Yr/Nv/Yvv/Yrr/Nvv` 维持基线；")
    A("估计：`Xu`、`Xuu`、`Nr`、`Nrr` 的负阻尼幅值，以及每硬件组、每桨、每方向的非负推力增益。")
    A("")
    A("| 项 | M1（仅今日） | M2（历史+今日） |")
    A("|---|---|---|")
    d1 = fit["diagnostics"]["M1"] or {}
    d2 = fit["diagnostics"].get("M2") or {}
    A(f"| 行数 | {d1.get('n_rows')} | {d2.get('n_rows')} |")
    A(f"| 段数 | {d1.get('n_segments')} | {d2.get('n_segments')} |")
    A(f"| 设计矩阵秩/列 | {d1.get('rank')}/{d1.get('n_cols')} | {d2.get('rank')}/{d2.get('n_cols')} |")
    A(f"| 条件数 | {_fmt(d1.get('cond'))} | {_fmt(d2.get('cond'))} |")
    A(f"| 降阶 | {d1.get('reductions')} | {d2.get('reductions')} |")
    A("")
    A("模型选择依据：")
    for r in fit["selection_reason"]:
        A(f"- {r}")
    A("")
    A("## 6. 结果")
    A("")
    A("| 参数 | 现用值 | 新估计 | 单位 | 状态 |")
    A("|---|---|---|---|---|")
    du = damping_upper(base)
    boot_v = fit["bootstrap"]["values"]
    for name, key, tkey in (("Xu", "Xu", "a1"), ("Xuu", "Xuu", "a2"),
                            ("Nr", "Nr", "n1"), ("Nrr", "Nrr", "n2")):
        A(f"| {name} | {base[key]:.4f} | {hydro[key]:.4f} | - | "
          f"{_damping_status(fit, sel, tkey, abs(hydro[key]), du[tkey], base[key], boot_v)} |")
    A("")
    A(f"归一化系数：`−Xu/m11 = {-hydro['Xu']/(hydro['mass']-hydro['Xu_dot']):.4f} 1/s`，"
      f"`−Xuu/m11 = {-hydro['Xuu']/(hydro['mass']-hydro['Xu_dot']):.4f} 1/m`，"
      f"`−Nr/m33 = {-hydro['Nr']/(hydro['Iz']-hydro['Nr_dot']):.4f} 1/s`，"
      f"`−Nrr/m33 = {-hydro['Nrr']/(hydro['Iz']-hydro['Nr_dot']):.4f} 1/m`。")
    A("")
    A("推力增益（**条件于先验**；单位按每组的输入模型区分）：")
    A("")
    A("| 组 | 输入模型 | 单位 | L fwd | L rev | R fwd | R rev |")
    A("|---|---|---|---|---|---|---|")
    ims = (fit.get("input_models") or {}).get(sel, {})
    for g, v in model["gains"].items():
        im = ims.get(g, {})
        A(f"| {g} | {im.get('model', 'pwm_equivalent')} | {im.get('unit', 'N at |q|=1')} | "
          f"{v[0]:.4g} | {v[1]:.4g} | {v[2]:.4g} | {v[3]:.4g} |")
    A("")
    boot = fit["bootstrap"]["values"]
    if boot:
        A("Bootstrap（200 次，seed=42，条件于固定惯量与输入模型）。"
          "**这些区间只属于线性积分回归初值；正文参数来自 5 s 单次打靶拟合，"
          "其置信区间状态为 `not_evaluable`：**")
        A("")
        A("| 初值参数 | 中位 | 95% CI |")
        A("|---|---|---|")
        for k, v in boot.items():
            if v.get("status") == "ok":
                A(f"| {k} | {v['median']:.4g} | [{v['ci95'][0]:.4g}, {v['ci95'][1]:.4g}] |")
        A("")
    else:
        A(f"Bootstrap 未报告：{fit['bootstrap']['meta'].get('reason')}")
        A("")
    A("惯性敏感性（只报告，不回写）：")
    A("")
    A("| s | Xu_dot | Yv_dot | Nr_dot | u RMSE | composite |")
    A("|---|---|---|---|---|---|")
    for s in fit["inertia_sweep"]:
        A(f"| {s['scale']} | {s['Xu_dot']:.4f} | {s['Yv_dot']:.4f} | {s['Nr_dot']:.4f} | "
          f"{_fmt(s['u_rmse'])} | {_fmt(s['composite'])} |")
    A("")
    A("## 7. 独立回放与门槛")
    A("")
    A("每个 10 s 窗只用窗首状态初始化，此后只喂记录输入（5 Hz 外环、0.05 s RK4）。")
    A("")
    A("| 指标 | M0（现用+25 N 先验） | 新候选 |")
    A("|---|---|---|")
    A(f"| 盲测窗数 | {rb0.get('n_windows')} | {rb.get('n_windows')} |")
    A(f"| u RMSE [m/s] | {_fmt(rb0.get('u_rmse'))} | {_fmt(rb.get('u_rmse'))} |")
    A(f"| r 中位 RMSE [°/s] | {_fmt(rb0.get('r_rmse_median_degps'))} | "
      f"{_fmt(rb.get('r_rmse_median_degps'))} |")
    A(f"| 水平位置 RMSE [m] | {_fmt(rb0.get('pos_rmse'))} | {_fmt(rb.get('pos_rmse'))} |")
    A(f"| 合成标准化误差 | {_fmt(rb0.get('composite'))} | {_fmt(rb.get('composite'))} |")
    A(f"| 稳定直航相对误差 | {_fmt(rb0.get('steady_u_rel'))} | {_fmt(rb.get('steady_u_rel'))} |")
    A(f"| 稳定转向相对误差 | {_fmt(rb0.get('steady_r_rel'))} | {_fmt(rb.get('steady_r_rel'))} |")
    A("")
    A("| 门槛 | 实测 | 结论 |")
    A("|---|---|---|")
    for g in metrics["gates"]:
        A(f"| {g['gate']} | {_fmt(g['value'])} | "
          f"{'通过' if g['pass'] else ('失败' if g['pass'] is False else 'not_evaluable')} |")
    A("")
    ph = metrics["physical"]
    A(f"物理门槛：M 对称部分正定={ph['M_symmetric_part_positive_definite']}，"
      f"特征值={_fmt(ph['M_eigenvalues'])}；D 对称部分最小特征值="
      f"{ph['min_eig_D_symmetric']:.4g}；`max Re eig(−M⁻¹D)`={ph['max_real_eig_minus_MinvD']:.4g}；"
      f"速度子系统数值 Jacobian 最大实部={ph['max_real_eig_velocity_jacobian']:.4g}。")
    A("")
    A("## 8. 适用边界")
    A("")
    for l in metrics["limitations"]:
        A(f"- {l}")
    A("")
    A("旧基线不是实测真值：`K_T` 自 2026-07-23 起一直是假设值（"
      "`assumed_or_bollard_pull_calibration_required`），旧验证状态为 `not_independent`。"
      "因此『今天是否改善』与『跨日是否共享』是两项独立结论。")
    A("")
    A("## 9. 若要补齐绝对标度")
    A("")
    A("需要（按既有《参数辨识指南_换推进器版》）M1 四档定油门往返、M2 三次不同初速滑行、"
      "M3 50%/70% 油门 Z 字；台架需真实测力与可靠转速。所有新增采集必须在既有失控问题"
      "完成硬件排查、停机保护验证后另行授权，本次未执行。")
    A("")
    with open(os.path.join(out, "identification_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _fmt(v):
    if v is None:
        return "not_evaluable"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return f"{float(v):.4g}"
    # gate values may legitimately be categorical (e.g. holdout provenance)
    return str(v)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--extra-history", default=None)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--exclusions", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage", default="all",
                    choices=["prepare", "fit", "validate", "all"])
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.stage in ("prepare", "all"):
        stage_prepare(args)
    if args.stage in ("fit", "all"):
        stage_fit(args)
    if args.stage in ("validate", "all"):
        return stage_validate(args)
    return None


if __name__ == "__main__":
    sys.exit(0 if main() != "rejected" else 0)
