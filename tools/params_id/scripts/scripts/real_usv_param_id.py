#!/usr/bin/env python3
"""Real-boat USV parameter identification from ArduPilot DataFlash logs.

This script is intentionally self-contained: it only needs numpy/pandas plus
the pymavlink source tree that already exists in the ArduPilot checkout.

Coordinate conventions:
  DataFlash ATT/GyrZ are ArduPilot NED/FRD style (heading clockwise from North,
  gyro z positive clockwise/down). The ROS2 NMPC model uses an ENU-style local
  map and base_link yaw positive counter-clockwise/up. We therefore convert:
    x = East, y = North
    psi = pi/2 - heading_ned
    r = -GyrZ
    v_ros = -v_ned_body
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Real boat constants confirmed by the user.
# ---------------------------------------------------------------------------
BOAT_MASS = 14.2
BOAT_LENGTH = 1.2
BOAT_BEAM = 0.6
CG_FROM_STERN = 0.48
X_G = BOAT_LENGTH / 2.0 - CG_FROM_STERN
IZ_EST = (1.0 / 12.0) * BOAT_MASS * (BOAT_LENGTH**2 + BOAT_BEAM**2)
THRUSTER_SEPARATION = 0.50
D_THRUSTER = THRUSTER_SEPARATION / 2.0

PWM_CENTER = 1500.0
PWM_MIN = 1000.0
PWM_MAX = 2000.0
PWM_DEADZONE = 30.0
RESAMPLE_HZ = 10.0


def wrap_pi(a: np.ndarray | float) -> np.ndarray | float:
    return np.arctan2(np.sin(a), np.cos(a))


def moving_average(x: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average with edge padding."""
    x = np.asarray(x, dtype=float)
    if window <= 1 or len(x) < 3:
        return x.copy()
    window = int(window)
    if window % 2 == 0:
        window += 1
    pad = window // 2
    padded = np.pad(x, (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(padded, kernel, mode="valid")


def smooth_numeric_columns(df: pd.DataFrame, dt: float) -> pd.DataFrame:
    """Light smoothing and derivative generation without scipy."""
    out = df.copy()
    # 0.7 s smoothing for measured states, 1.1 s for differentiated signals.
    state_window = max(3, int(round(0.7 / dt)))
    deriv_window = max(5, int(round(1.1 / dt)))
    for col in ("u", "v", "r", "x", "y"):
        if col in out:
            out[col] = moving_average(out[col].to_numpy(), state_window)
    for col in ("u", "v", "r"):
        vals = out[col].to_numpy()
        out[f"{col}_dot"] = moving_average(np.gradient(vals, dt), deriv_window)
    return out


def pwm_to_normalized(pwm: np.ndarray, deadzone: float = PWM_DEADZONE) -> np.ndarray:
    pwm = np.asarray(pwm, dtype=float)
    n = np.zeros_like(pwm)
    fwd = pwm > PWM_CENTER + deadzone
    rev = pwm < PWM_CENTER - deadzone
    n[fwd] = (pwm[fwd] - PWM_CENTER - deadzone) / (PWM_MAX - PWM_CENTER - deadzone)
    n[rev] = (pwm[rev] - PWM_CENTER + deadzone) / (PWM_CENTER - PWM_MIN - deadzone)
    return np.clip(n, -1.0, 1.0)


def phi_from_pwm(pwm: np.ndarray) -> np.ndarray:
    n = pwm_to_normalized(pwm)
    return np.sign(n) * n * n


def gps_to_local_enu(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    lat0 = lat[np.isfinite(lat)][0]
    lon0 = lon[np.isfinite(lon)][0]
    earth_r = 6371000.0
    d_lat = np.radians(lat - lat0)
    d_lon = np.radians(lon - lon0)
    north = d_lat * earth_r
    east = d_lon * earth_r * math.cos(math.radians(lat0))
    return east, north


def interp_angle(t_src: np.ndarray, angle: np.ndarray, t_dst: np.ndarray) -> np.ndarray:
    s = np.interp(t_dst, t_src, np.sin(angle))
    c = np.interp(t_dst, t_src, np.cos(angle))
    return np.arctan2(s, c)


def interp_zoh(t_src: np.ndarray, values: np.ndarray, t_dst: np.ndarray, fill: float) -> np.ndarray:
    idx = np.searchsorted(t_src, t_dst, side="right") - 1
    valid = (idx >= 0) & (idx < len(values))
    out = np.full(len(t_dst), fill, dtype=float)
    out[valid] = values[idx[valid]]
    return out


def sort_clean(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)


def parse_bin_files(log_dir: Path, bins: Iterable[Path]) -> dict[str, pd.DataFrame]:
    from pymavlink import mavutil

    records: dict[str, list[dict]] = {
        "ATT": [],
        "GPS": [],
        "RCOU": [],
        "IMU": [],
        "XKF1": [],
        "NKF1": [],
    }

    for path in bins:
        print(f"[parse] {path.name} ({path.stat().st_size / 1024 / 1024:.1f} MiB)")
        mlog = mavutil.mavlink_connection(str(path))
        count = 0
        while True:
            msg = mlog.recv_match()
            if msg is None:
                break
            typ = msg.get_type()
            count += 1
            ts = getattr(msg, "_timestamp", None)
            if ts is None:
                time_us = getattr(msg, "TimeUS", None)
                ts = float(time_us) * 1e-6 if time_us is not None else np.nan
            try:
                if typ == "ATT":
                    records["ATT"].append(
                        {
                            "timestamp": ts,
                            "Yaw": getattr(msg, "Yaw", np.nan),
                            "DesYaw": getattr(msg, "DesYaw", np.nan),
                        }
                    )
                elif typ == "GPS" and getattr(msg, "Status", 0) >= 3:
                    records["GPS"].append(
                        {
                            "timestamp": ts,
                            "Lat": getattr(msg, "Lat", np.nan),
                            "Lng": getattr(msg, "Lng", np.nan),
                            "Spd": getattr(msg, "Spd", np.nan),
                            "GCrs": getattr(msg, "GCrs", np.nan),
                            "NSats": getattr(msg, "NSats", np.nan),
                            "HDop": getattr(msg, "HDop", np.nan),
                        }
                    )
                elif typ == "RCOU":
                    records["RCOU"].append(
                        {
                            "timestamp": ts,
                            "C1": getattr(msg, "C1", np.nan),
                            "C3": getattr(msg, "C3", np.nan),
                        }
                    )
                elif typ == "IMU":
                    records["IMU"].append(
                        {
                            "timestamp": ts,
                            "GyrZ": getattr(msg, "GyrZ", np.nan),
                            "AccX": getattr(msg, "AccX", np.nan),
                            "AccY": getattr(msg, "AccY", np.nan),
                        }
                    )
                elif typ in ("XKF1", "NKF1"):
                    records[typ].append(
                        {
                            "timestamp": ts,
                            "VN": getattr(msg, "VN", np.nan),
                            "VE": getattr(msg, "VE", np.nan),
                            "VD": getattr(msg, "VD", np.nan),
                        }
                    )
            except Exception:
                continue
        print(f"[parse]   messages={count}")

    dfs = {name: sort_clean(rows) for name, rows in records.items() if rows}
    for name, df in dfs.items():
        if not df.empty:
            duration = df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]
            hz = len(df) / duration if duration > 0 else 0.0
            print(f"[parse]   {name:<5s} rows={len(df):>7d}, duration={duration:8.1f}s, {hz:5.1f} Hz")
    return dfs


def merge_resample(dfs: dict[str, pd.DataFrame], hz: float = RESAMPLE_HZ) -> pd.DataFrame:
    required = ["ATT", "GPS", "RCOU", "IMU"]
    missing = [k for k in required if k not in dfs or dfs[k].empty]
    if missing:
        raise RuntimeError(f"missing required message types: {missing}")

    ekf_key = "XKF1" if "XKF1" in dfs and len(dfs["XKF1"]) > 10 else "NKF1"
    if ekf_key not in dfs or dfs[ekf_key].empty:
        ekf_key = ""

    keys_for_range = required + ([ekf_key] if ekf_key else [])
    t_start = max(float(dfs[k]["timestamp"].iloc[0]) for k in keys_for_range)
    t_end = min(float(dfs[k]["timestamp"].iloc[-1]) for k in keys_for_range)
    dt = 1.0 / hz
    t = np.arange(t_start + 1.0, t_end - 1.0, dt)
    if len(t) < 50:
        raise RuntimeError(f"not enough overlapping samples: {len(t)}")

    out = pd.DataFrame({"timestamp": t, "time": t - t[0]})

    att = dfs["ATT"]
    yaw_ned = np.radians(att["Yaw"].to_numpy(dtype=float))
    psi_ros = wrap_pi(math.pi / 2.0 - interp_angle(att["timestamp"].to_numpy(), yaw_ned, t))
    out["psi"] = psi_ros

    if "DesYaw" in att:
        des = att["DesYaw"].to_numpy(dtype=float)
        if np.isfinite(des).sum() > 10:
            out["psi_des"] = wrap_pi(
                math.pi / 2.0 - interp_angle(att["timestamp"].to_numpy(), np.radians(des), t)
            )

    gps = dfs["GPS"]
    gps_t = gps["timestamp"].to_numpy()
    east, north = gps_to_local_enu(gps["Lat"].to_numpy(), gps["Lng"].to_numpy())
    out["x"] = np.interp(t, gps_t, east)
    out["y"] = np.interp(t, gps_t, north)
    out["gps_speed"] = np.interp(t, gps_t, gps["Spd"].to_numpy(dtype=float))
    if "GCrs" in gps:
        course = np.radians(gps["GCrs"].to_numpy(dtype=float))
        out["gps_course_psi"] = wrap_pi(math.pi / 2.0 - interp_angle(gps_t, course, t))

    rcou = dfs["RCOU"]
    rc_t = rcou["timestamp"].to_numpy()
    out["pwm_left"] = interp_zoh(rc_t, rcou["C1"].to_numpy(dtype=float), t, PWM_CENTER)
    out["pwm_right"] = interp_zoh(rc_t, rcou["C3"].to_numpy(dtype=float), t, PWM_CENTER)
    out["phi_left"] = phi_from_pwm(out["pwm_left"].to_numpy())
    out["phi_right"] = phi_from_pwm(out["pwm_right"].to_numpy())
    out["phi_X"] = out["phi_left"] + out["phi_right"]
    out["phi_N"] = D_THRUSTER * (out["phi_right"] - out["phi_left"])

    imu = dfs["IMU"]
    imu_t = imu["timestamp"].to_numpy()
    out["r"] = -np.interp(  # DataFlash GyrZ is positive clockwise/down.
        t, imu_t, imu["GyrZ"].to_numpy(dtype=float)
    )
    out["acc_x_raw"] = np.interp(t, imu_t, imu["AccX"].to_numpy(dtype=float))
    out["acc_y_raw"] = np.interp(t, imu_t, imu["AccY"].to_numpy(dtype=float))

    if ekf_key:
        ekf = dfs[ekf_key]
        ekf_t = ekf["timestamp"].to_numpy()
        vn = np.interp(t, ekf_t, ekf["VN"].to_numpy(dtype=float))
        ve = np.interp(t, ekf_t, ekf["VE"].to_numpy(dtype=float))
    else:
        vn = np.gradient(out["y"].to_numpy(), dt)
        ve = np.gradient(out["x"].to_numpy(), dt)
    out["v_north"] = vn
    out["v_east"] = ve

    psi = out["psi"].to_numpy()
    out["u"] = ve * np.cos(psi) + vn * np.sin(psi)
    out["v"] = -ve * np.sin(psi) + vn * np.cos(psi)

    out = smooth_numeric_columns(out, dt)
    out["n_left"] = pwm_to_normalized(out["pwm_left"].to_numpy())
    out["n_right"] = pwm_to_normalized(out["pwm_right"].to_numpy())
    return out


def convert_existing_processed_csv(path: Path) -> pd.DataFrame:
    """Convert the previous NED-style processed_data.csv to ROS/NMPC convention."""
    df = pd.read_csv(path)
    out = pd.DataFrame()
    out["timestamp"] = df["timestamp"]
    out["time"] = df["time"]
    out["x"] = df["y_e"]
    out["y"] = df["x_n"]
    out["psi"] = wrap_pi(math.pi / 2.0 - df["psi"].to_numpy())
    if "psi_des" in df:
        out["psi_des"] = wrap_pi(math.pi / 2.0 - df["psi_des"].to_numpy())
    out["gps_speed"] = df["gps_speed"]
    out["pwm_left"] = df["pwm_left"]
    out["pwm_right"] = df["pwm_right"]
    out["phi_left"] = phi_from_pwm(out["pwm_left"].to_numpy())
    out["phi_right"] = phi_from_pwm(out["pwm_right"].to_numpy())
    out["phi_X"] = out["phi_left"] + out["phi_right"]
    out["phi_N"] = D_THRUSTER * (out["phi_right"] - out["phi_left"])
    out["v_north"] = df["v_north"]
    out["v_east"] = df["v_east"]
    out["u"] = df["u"]
    out["v"] = -df["v"]
    out["r"] = -df["r"]
    dt = float(df["time"].diff().median())
    out = smooth_numeric_columns(out, dt)
    out["n_left"] = pwm_to_normalized(out["pwm_left"].to_numpy())
    out["n_right"] = pwm_to_normalized(out["pwm_right"].to_numpy())
    return out


def bounded_lstsq(
    A: np.ndarray,
    y: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    ridge: float = 1e-6,
) -> np.ndarray:
    """Small active-set bounded least squares for low-dimensional problems."""
    A = np.asarray(A, dtype=float)
    y = np.asarray(y, dtype=float)
    lb = np.asarray(lb, dtype=float)
    ub = np.asarray(ub, dtype=float)
    col_scale = np.maximum(np.sqrt(np.mean(A * A, axis=0)), 1e-9)
    As = A / col_scale
    lb_s = lb * col_scale
    ub_s = ub * col_scale

    fixed = np.zeros(A.shape[1], dtype=bool)
    x = np.zeros(A.shape[1], dtype=float)
    for _ in range(A.shape[1] + 3):
        free = ~fixed
        residual = y - As[:, fixed] @ x[fixed] if fixed.any() else y
        if free.any():
            Af = As[:, free]
            lhs = Af.T @ Af + ridge * np.eye(Af.shape[1])
            rhs = Af.T @ residual
            x[free] = np.linalg.solve(lhs, rhs)
        x_old = x.copy()
        below = x < lb_s
        above = x > ub_s
        x[below] = lb_s[below]
        x[above] = ub_s[above]
        fixed = below | above
        if np.allclose(x, x_old, rtol=1e-7, atol=1e-9):
            break
    return x / col_scale


def fit_r2(y: np.ndarray, yhat: np.ndarray) -> float:
    y = np.asarray(y)
    yhat = np.asarray(yhat)
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0


@dataclass
class IdentificationResult:
    params: dict[str, float]
    metrics: dict[str, float]
    counts: dict[str, int]


def identify_parameters(df: pd.DataFrame, assumed_k_t: float = 25.0) -> IdentificationResult:
    dt = float(df["time"].diff().median())
    valid = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["u", "v", "r", "u_dot", "v_dot", "r_dot", "gps_speed", "phi_X", "phi_N"]
    )

    moving = valid["gps_speed"].to_numpy() > 0.12
    active = (np.abs(valid["n_left"].to_numpy()) > 0.02) | (
        np.abs(valid["n_right"].to_numpy()) > 0.02
    )
    straight_forward = (
        moving
        & (valid["u"].to_numpy() > 0.05)
        & (np.abs(valid["r"].to_numpy()) < 0.35)
        & (np.abs(valid["v"].to_numpy()) < 0.75)
        & ((np.abs(valid["phi_X"].to_numpy()) > 0.03) | (np.abs(valid["u"].to_numpy()) > 0.20))
    )
    turning = moving & (
        (np.abs(valid["r"].to_numpy()) > 0.04) | (np.abs(valid["phi_N"].to_numpy()) > 0.015)
    )

    surge_df = valid.loc[straight_forward].copy()
    yaw_df = valid.loc[turning & (valid["u"].to_numpy() > 0.05)].copy()
    sway_df = valid.loc[moving & active & (valid["u"].to_numpy() > 0.05)].copy()

    # Surge with an assumed thrust calibration. Without bollard-pull data the
    # absolute thrust scale and damping scale are not separately observable from
    # this free-running log, so K_T is an explicit assumption.
    K_T = float(assumed_k_t)
    A_surge = np.column_stack(
        [
            surge_df["u"].to_numpy(),
            np.abs(surge_df["u"].to_numpy()) * surge_df["u"].to_numpy(),
        ]
    )
    y_surge = BOAT_MASS * surge_df["u_dot"].to_numpy() - K_T * surge_df["phi_X"].to_numpy()
    x_surge = bounded_lstsq(
        A_surge,
        y_surge,
        lb=np.array([-120.0, -300.0]),
        ub=np.array([-0.01, -0.01]),
        ridge=1e-3,
    )
    Xu, Xuu = [float(v) for v in x_surge]

    # Added mass is weakly observable in the available logs. Use conservative
    # first-pass values scaled to the 14.2 kg / 1.2 m boat and let future forced
    # acceleration / tow tests refine them.
    Xu_dot = -2.0
    Yv_dot = -8.0
    Yr_dot = 0.0

    # Sway: low-confidence GPS-derived lateral channel. Use it mainly for order
    # of magnitude and keep added-mass terms fixed above.
    u = sway_df["u"].to_numpy()
    v = sway_df["v"].to_numpy()
    r = sway_df["r"].to_numpy()
    v_dot = sway_df["v_dot"].to_numpy()
    r_dot = sway_df["r_dot"].to_numpy()
    y_sway = BOAT_MASS * v_dot + BOAT_MASS * X_G * r_dot + (BOAT_MASS - Xu_dot) * u * r
    A_sway = np.column_stack([v, np.abs(v) * v, r])
    x_sway = bounded_lstsq(
        A_sway,
        y_sway,
        lb=np.array([-120.0, -250.0, -40.0]),
        ub=np.array([-0.05, -0.05, 40.0]),
        ridge=1e-3,
    )
    Yv, Yvv, Yr = [float(v) for v in x_sway]
    Yrr = -0.5

    # Yaw with K_T fixed from surge. Coriolis is estimated with current mass terms.
    u = yaw_df["u"].to_numpy()
    v = yaw_df["v"].to_numpy()
    r = yaw_df["r"].to_numpy()
    v_dot = yaw_df["v_dot"].to_numpy()
    r_dot = yaw_df["r_dot"].to_numpy()
    tau_N = K_T * yaw_df["phi_N"].to_numpy()
    m11 = BOAT_MASS - Xu_dot
    m22 = BOAT_MASS - Yv_dot
    m23 = BOAT_MASS * X_G - Yr_dot
    C_N = (m22 - m11) * u * v + m23 * u * r
    y_yaw = BOAT_MASS * X_G * v_dot + IZ_EST * r_dot - tau_N + C_N
    A_yaw = np.column_stack([v_dot, r_dot, v, np.abs(v) * v, r, np.abs(r) * r])
    x_yaw = bounded_lstsq(
        A_yaw,
        y_yaw,
        lb=np.array([-40.0, -20.0, -80.0, -150.0, -80.0, -150.0]),
        ub=np.array([40.0, -0.02, 80.0, 150.0, -0.02, -0.001]),
        ridge=1e-3,
    )
    Nv_dot, Nr_dot, Nv, Nvv, Nr, Nrr = [float(v) for v in x_yaw]

    params = {
        "mass": BOAT_MASS,
        "length": BOAT_LENGTH,
        "beam": BOAT_BEAM,
        "xg": X_G,
        "Iz": IZ_EST,
        "d_thruster": D_THRUSTER,
        "thruster_separation": THRUSTER_SEPARATION,
        "K_T": K_T,
        "Xu_dot": Xu_dot,
        "Yv_dot": Yv_dot,
        "Yr_dot": Yr_dot,
        "Nv_dot": Nv_dot,
        "Nr_dot": Nr_dot,
        "Xu": Xu,
        "Yv": Yv,
        "Yr": Yr,
        "Nv": Nv,
        "Nr": Nr,
        "Xuu": Xuu,
        "Yvv": Yvv,
        "Yrr": Yrr,
        "Nvv": Nvv,
        "Nrr": Nrr,
    }

    metrics = {
        "dt_s": dt,
        "duration_s": float(df["time"].iloc[-1] - df["time"].iloc[0]),
        "surge_r2": fit_r2(y_surge, A_surge @ x_surge),
        "sway_r2": fit_r2(y_sway, A_sway @ x_sway),
        "yaw_r2": fit_r2(y_yaw, A_yaw @ x_yaw),
        "corr_r_phiN_ros": float(np.corrcoef(valid["r"], valid["phi_N"])[0, 1]),
        "corr_u_phiX": float(np.corrcoef(valid["u"], valid["phi_X"])[0, 1]),
        "assumed_K_T_N": K_T,
        "K_T_source": "assumed_or_bollard_pull_calibration_required",
    }
    counts = {
        "all_samples": int(len(df)),
        "valid_samples": int(len(valid)),
        "moving_samples": int(np.sum(moving)),
        "active_samples": int(np.sum(active)),
        "surge_samples": int(len(surge_df)),
        "sway_samples": int(len(sway_df)),
        "yaw_samples": int(len(yaw_df)),
    }
    return IdentificationResult(params=params, metrics=metrics, counts=counts)


def model_acceleration(df: pd.DataFrame, p: dict[str, float]) -> np.ndarray:
    u = df["u"].to_numpy()
    v = df["v"].to_numpy()
    r = df["r"].to_numpy()
    TL = p["K_T"] * df["phi_left"].to_numpy()
    TR = p["K_T"] * df["phi_right"].to_numpy()
    tau = np.vstack([TL + TR, np.zeros_like(TL), p["d_thruster"] * (TR - TL)]).T

    m11 = p["mass"] - p["Xu_dot"]
    m22 = p["mass"] - p["Yv_dot"]
    m23 = p["mass"] * p["xg"] - p["Yr_dot"]
    m32 = p["mass"] * p["xg"] - p["Nv_dot"]
    m33 = p["Iz"] - p["Nr_dot"]
    M = np.array([[m11, 0.0, 0.0], [0.0, m22, m23], [0.0, m32, m33]])
    Minv = np.linalg.inv(M)

    acc = np.zeros((len(df), 3))
    for i, (ui, vi, ri) in enumerate(zip(u, v, r)):
        C = np.array(
            [
                [0.0, 0.0, -m22 * vi - m23 * ri],
                [0.0, 0.0, m11 * ui],
                [m22 * vi + m23 * ri, -m11 * ui, 0.0],
            ]
        )
        D = np.array(
            [
                [-p["Xu"] - p["Xuu"] * abs(ui), 0.0, 0.0],
                [0.0, -p["Yv"] - p["Yvv"] * abs(vi), -p["Yr"] - p["Yrr"] * abs(ri)],
                [0.0, -p["Nv"] - p["Nvv"] * abs(vi), -p["Nr"] - p["Nrr"] * abs(ri)],
            ]
        )
        nu = np.array([ui, vi, ri])
        acc[i] = Minv @ (tau[i] - C @ nu - D @ nu)
    return acc


def validation_metrics(df: pd.DataFrame, p: dict[str, float]) -> dict[str, object]:
    return {
        "status": "not_independent",
        "reason": (
            "The available logs are used for fitting and contain mixed manual "
            "forward, reverse, and turning maneuvers. Use a held-out straight "
            "acceleration/deceleration run plus held-out steady turns for real validation."
        ),
    }


def write_outputs(df: pd.DataFrame, result: IdentificationResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data_path = out_dir / "processed_data_ros.csv"
    json_path = out_dir / "identified_params_real.json"
    yaml_path = out_dir / "usv_params_real.yaml"
    report_path = out_dir / "identification_report.txt"

    df.to_csv(data_path, index=False)
    payload = {
        "params": result.params,
        "metrics": result.metrics,
        "validation": validation_metrics(df, result.params),
        "counts": result.counts,
        "notes": [
            "Real boat constants: mass=14.2 kg, length=1.2 m, beam=0.6 m.",
            "DataFlash NED/FRD yaw and gyro are converted to ROS/NMPC ENU/base_link convention.",
            "K_T is assumed from the prior script; replace with bench/bollard-pull calibration when available.",
            "Sway/coupled parameters are lower-confidence because they come from GPS/EKF lateral velocity.",
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    p = result.params
    yaml_text = f"""# Real USV parameters for usv_mpc Dynamic NMPC.
# Generated from ArduPilot DataFlash logs.
# Coordinate convention: ROS ENU map + base_link yaw positive CCW.
/**:
  ros__parameters:
    vehicle:
      mass: {p['mass']:.6f}
      Iz: {p['Iz']:.6f}
      xg: {p['xg']:.6f}
      d_thruster: {p['d_thruster']:.6f}
      length: {p['length']:.6f}
      beam: {p['beam']:.6f}
      Xu_dot: {p['Xu_dot']:.6f}
      Yv_dot: {p['Yv_dot']:.6f}
      Yr_dot: {p['Yr_dot']:.6f}
      Nv_dot: {p['Nv_dot']:.6f}
      Nr_dot: {p['Nr_dot']:.6f}
      Xu: {p['Xu']:.6f}
      Yv: {p['Yv']:.6f}
      Yr: {p['Yr']:.6f}
      Nv: {p['Nv']:.6f}
      Nr: {p['Nr']:.6f}
      Xuu: {p['Xuu']:.6f}
      Yvv: {p['Yvv']:.6f}
      Yrr: {p['Yrr']:.6f}
      Nvv: {p['Nvv']:.6f}
      Nrr: {p['Nrr']:.6f}
    thruster:
      pwm_min: {PWM_MIN:.0f}
      pwm_center: {PWM_CENTER:.0f}
      pwm_max: {PWM_MAX:.0f}
      pwm_deadzone: {PWM_DEADZONE:.0f}
      K_T: {p['K_T']:.6f}
      T_max_forward: {max(p['K_T'], 1.0):.6f}
      T_max_reverse: {max(p['K_T'], 1.0):.6f}
      separation: {p['thruster_separation']:.6f}
"""
    yaml_path.write_text(yaml_text, encoding="utf-8")

    lines = [
        "Real USV Parameter Identification",
        "=================================",
        "",
        f"samples: {result.counts}",
        f"metrics: {result.metrics}",
        f"validation: {payload['validation']}",
        "",
        "NMPC vehicle parameters:",
    ]
    for key in (
        "mass",
        "Iz",
        "xg",
        "d_thruster",
        "K_T",
        "Xu_dot",
        "Yv_dot",
        "Yr_dot",
        "Nv_dot",
        "Nr_dot",
        "Xu",
        "Yv",
        "Yr",
        "Nv",
        "Nr",
        "Xuu",
        "Yvv",
        "Yrr",
        "Nvv",
        "Nrr",
    ):
        lines.append(f"  {key:>12s}: {p[key]: .6f}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[out] {data_path}")
    print(f"[out] {json_path}")
    print(f"[out] {yaml_path}")
    print(f"[out] {report_path}")


def ensure_pymavlink_path(root: Path) -> None:
    """Add a local pymavlink source tree to sys.path if available."""
    if (root / "pymavlink" / "mavutil.py").exists():
        sys.path.insert(0, str(root))
        return
    candidates = [
        root / "ardupilot" / "modules" / "mavlink",
        root / "ardurover-argus" / "modules" / "mavlink",
    ]
    for c in candidates:
        if (c / "pymavlink" / "mavutil.py").exists():
            sys.path.insert(0, str(c))
            return


def default_bins(log_dir: Path) -> list[Path]:
    bins = sorted(log_dir.glob("2026-06-25*.bin"))
    return bins if bins else sorted(log_dir.glob("*.bin"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"G:\仿真环境\USV", help="USV repository root")
    ap.add_argument("--log-dir", default=r"G:\仿真环境\USV\usv_mpc_ws\参数识别")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--from-existing-csv", action="store_true")
    ap.add_argument("--existing-csv", default=None)
    ap.add_argument(
        "--assumed-K-T",
        type=float,
        default=25.0,
        help="Assumed max thrust per motor in N for |normalized PWM|=1. "
        "Replace with bollard-pull calibration when available.",
    )
    args = ap.parse_args()

    root = Path(args.root)
    log_dir = Path(args.log_dir)
    out_dir = Path(args.out_dir) if args.out_dir else log_dir / "results" / "real_identification"

    if args.from_existing_csv:
        csv_path = Path(args.existing_csv) if args.existing_csv else log_dir / "data" / "processed_data.csv"
        print(f"[load] converting existing CSV: {csv_path}")
        df = convert_existing_processed_csv(csv_path)
    else:
        ensure_pymavlink_path(root)
        bins = default_bins(log_dir)
        if not bins:
            raise RuntimeError(f"no .bin files found in {log_dir}")
        dfs = parse_bin_files(log_dir, bins)
        df = merge_resample(dfs, RESAMPLE_HZ)

    result = identify_parameters(df, assumed_k_t=args.assumed_K_T)
    print("[id] counts", result.counts)
    print("[id] metrics", result.metrics)
    print("[id] params")
    for k, v in result.params.items():
        print(f"  {k:>16s}: {v: .6f}")
    write_outputs(df, result, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
