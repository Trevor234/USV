#!/usr/bin/env python3
"""融合控制器克隆（Python 侧）——逐行复现 C++ 生产路径的输入构造。

**边界**：OCP 求解本身不在这里（见 `fusion_solver.py` 的 C ABI 绑定）。本模块只负责
构造求解器输入，语义必须与以下 C++ 实现逐位一致：

  * `usv_nmpc::build_frozen_reference`  （usv_nmpc/src/p1_input_core.cpp）
  * `usv_mpc::sample_path_profile_at_time` （usv_nmpc/src/utils.cpp）
  * `p1_gp_snap::build_gp_rollout_guess`  （.../src/p1_gp_snapshot.cpp）
  * `p1_gp_snap::evaluate_gp_horizon`     （同上）

正确性由 `verify_fusion_clone.py` 用真实运行记录做回放校验（参考门 / 残差门 /
求解门），不是靠"读起来一样"。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

N_HORIZON = 20
DT = 0.2
RK4_SUBSTEPS = 4
OOD_POS_THRESHOLD_M = 0.75
OOD_YAW_THRESHOLD_RAD = 0.5


def wrap_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _clip(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


# ----------------------------------------------------------------------
# 参考轨迹（build_frozen_reference 的 profile_time 分支）
# ----------------------------------------------------------------------
@dataclass
class ProfileSample:
    x: float
    y: float
    psi: float
    v: float
    r: float
    j: int


def sample_path_profile_at_time(
    path_xypsi: np.ndarray,
    times: np.ndarray,
    vs: np.ndarray,
    rs: np.ndarray,
    tk: float,
    j_hint: int,
) -> ProfileSample:
    """与 C++ 同语义：从 j_hint 起前推定位时间段，再线性插值。"""
    last = len(path_xypsi) - 1
    j = int(j_hint)
    while j < last and times[j + 1] < tk:
        j += 1
    if j >= last:
        p = path_xypsi[last]
        return ProfileSample(float(p[0]), float(p[1]), float(p[2]),
                             float(vs[last]), float(rs[last]), last)
    t_seg = float(times[j + 1] - times[j])
    a = _clip((tk - times[j]) / t_seg, 0.0, 1.0) if t_seg > 1e-9 else 0.0
    x = path_xypsi[j][0] + a * (path_xypsi[j + 1][0] - path_xypsi[j][0])
    y = path_xypsi[j][1] + a * (path_xypsi[j + 1][1] - path_xypsi[j][1])
    dpsi = wrap_angle(float(path_xypsi[j + 1][2] - path_xypsi[j][2]))
    psi = wrap_angle(float(path_xypsi[j][2]) + a * dpsi)
    v = vs[j] + a * (vs[j + 1] - vs[j])
    r = rs[j] + a * (rs[j + 1] - rs[j])
    return ProfileSample(float(x), float(y), float(psi), float(v), float(r), j)


def build_frozen_reference(
    state6: np.ndarray,
    path_xypsi: np.ndarray,
    profile_rows: np.ndarray | None,
    N: int = N_HORIZON,
    dt: float = DT,
    offset: int = 2,
    cruise: float = 0.6,
    projection_mode: str = "discrete_offset",
    lead_s: float | None = None,
) -> np.ndarray:
    """返回 (6, N+1) 参考：行 = [x, y, psi, v, 0, r]。

    profile 与 path 等长时走 profile_time 分支（生产运行器的正常路径）；
    否则退回匀速弧长采样（与 C++ cruise_arc_fallback 一致）。
    """
    if projection_mode not in ("discrete_offset", "polyline_time"):
        raise ValueError(f"unknown reference projection mode: {projection_mode!r}")
    lead = -1.0 if lead_s is None else float(lead_s)
    if not math.isfinite(lead) or (lead < 0.0 and lead != -1.0):
        raise ValueError("reference lead must be nonnegative or -1")

    path = np.asarray(path_xypsi, dtype=np.float64)
    ref = np.zeros((6, N + 1), dtype=np.float64)
    if len(path) == 0:
        return ref
    x0, y0 = float(state6[0]), float(state6[1])
    last = len(path) - 1
    request_projection = projection_mode == "polyline_time"
    synced = profile_rows is not None and len(profile_rows) == len(path)
    if request_projection and last == 0:
        synced = False
    project = request_projection and synced
    if project:
        distances = np.sum((path[:, :2] - (x0, y0)) ** 2, axis=1)
    else:
        distances = np.hypot(path[:, 0] - x0, path[:, 1] - y0)
    nearest = int(np.argmin(distances))
    idx = min(nearest + max(1, int(offset)), last)

    if synced:
        pr = np.asarray(profile_rows, dtype=np.float64)
        times, vs, rs = pr[:, 3], pr[:, 0], pr[:, 2]
        t0 = float(times[idx])
        if project:
            idx, alpha = _project_adjacent_segments(path, nearest, x0, y0)
            t_proj = float(times[idx]) + alpha * (float(times[idx + 1]) - float(times[idx]))
            t0 = t_proj + (lead if lead >= 0.0 else max(1, int(offset)) * dt)
        j = idx
        for k in range(N + 1):
            s = sample_path_profile_at_time(path, times, vs, rs, t0 + k * dt, j)
            ref[0, k], ref[1, k], ref[2, k] = s.x, s.y, s.psi
            ref[3, k], ref[4, k], ref[5, k] = s.v, 0.0, s.r
            j = s.j
        if request_projection:
            _unwrap_reference_heading(ref, float(state6[2]))
        return ref

    # cruise_arc_fallback
    arc = [0.0]
    for i in range(idx, len(path) - 1):
        arc.append(arc[-1] + math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]))
    for k in range(N + 1):
        s_des = cruise * dt * k
        j = 0
        while j < len(arc) - 1 and arc[j + 1] < s_des:
            j += 1
        ii = min(idx + j, len(path) - 1)
        if ii < len(path) - 1 and j < len(arc) - 1:
            seg_len = arc[j + 1] - arc[j]
            if seg_len > 1e-6:
                t = _clip((s_des - arc[j]) / seg_len, 0.0, 1.0)
                ref[0, k] = path[ii][0] + t * (path[ii + 1][0] - path[ii][0])
                ref[1, k] = path[ii][1] + t * (path[ii + 1][1] - path[ii][1])
                dpsi = wrap_angle(float(path[ii + 1][2] - path[ii][2]))
                ref[2, k] = wrap_angle(float(path[ii][2]) + t * dpsi)
            else:
                ref[0, k], ref[1, k], ref[2, k] = path[ii][0], path[ii][1], path[ii][2]
        else:
            ref[0, k], ref[1, k], ref[2, k] = path[ii][0], path[ii][1], path[ii][2]
        ref[3, k], ref[4, k], ref[5, k] = cruise, 0.0, 0.0
    if request_projection:
        _unwrap_reference_heading(ref, float(state6[2]))
    return ref


def _project_adjacent_segments(
    path: np.ndarray, nearest: int, px: float, py: float,
) -> tuple[int, float]:
    first = max(0, nearest - 1)
    best_i, best_alpha, best_d2 = first, 0.0, math.inf
    for i in range(first, min(nearest, len(path) - 2) + 1):
        ax, ay = map(float, path[i, :2])
        bx, by = map(float, path[i + 1, :2])
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 <= 1e-12:
            alpha = 0.0
            ex, ey = px - ax, py - ay
        else:
            alpha = _clip(((px - ax) * dx + (py - ay) * dy) / length2, 0.0, 1.0)
            ex, ey = px - (ax + alpha * dx), py - (ay + alpha * dy)
        d2 = ex * ex + ey * ey
        if i == first or d2 < best_d2:
            best_i, best_alpha, best_d2 = i, alpha, d2
    return best_i, best_alpha


def _unwrap_reference_heading(ref: np.ndarray, heading: float) -> None:
    for k in range(ref.shape[1]):
        heading += wrap_angle(float(ref[2, k]) - heading)
        ref[2, k] = heading


# ----------------------------------------------------------------------
# 初猜 rollout + GP 残差
# ----------------------------------------------------------------------
def build_gp_rollout_guess(
    x0: np.ndarray,
    ref: np.ndarray,
    anchor: np.ndarray,
    hydro,
    gp,
    prev_x: np.ndarray | None = None,
    prev_u: np.ndarray | None = None,
    tick_shift: int = 0,
    dt: float = DT,
    t_min: float = -25.0,
    t_max: float = 25.0,
    dt_max: float = 80.0,
    gp_predict=None,
) -> tuple[np.ndarray, np.ndarray]:
    """返回 (x(6,21), u(2,20))，与 build_gp_rollout_guess 逐位一致。"""
    from usv_rl.dynamics import USVDynamicModel

    out_x = np.zeros((6, N_HORIZON + 1), dtype=np.float64)
    out_u = np.zeros((2, N_HORIZON), dtype=np.float64)
    use_shifted_u = False
    if (
        prev_x is not None and prev_u is not None
        and prev_x.shape == (6, N_HORIZON + 1) and prev_u.shape == (2, N_HORIZON)
        and 1 <= int(tick_shift) <= 4
    ):
        pos_diff = float(np.linalg.norm(np.asarray(x0[:2]) - np.asarray(prev_x[:2, tick_shift])))
        yaw_diff = abs(wrap_angle(float(x0[2]) - float(prev_x[2, tick_shift])))
        use_shifted_u = bool(pos_diff < OOD_POS_THRESHOLD_M and yaw_diff < OOD_YAW_THRESHOLD_RAD)

    dT_step = dt_max * dt
    dyn = USVDynamicModel(dt=dt, rk4_substeps=RK4_SUBSTEPS, params=hydro)
    x = np.asarray(x0, dtype=np.float64).copy()
    u_prev = np.asarray(anchor, dtype=np.float64).copy()
    out_x[:, 0] = x
    d_thruster = max(float(getattr(hydro, "d_thruster", 0.25)), 0.05)

    for k in range(N_HORIZON):
        if use_shifted_u:
            src_k = min(k + int(tick_shift), N_HORIZON - 1)
            u_cand = np.asarray(prev_u[:, src_k], dtype=np.float64).copy()
        else:
            u_ref = float(ref[3, k])
            r_ref = float(ref[5, k])
            psi_err = wrap_angle(float(ref[2, k]) - float(x[2]))
            f_cmd = _clip(12.0 * (u_ref - float(x[3])) + 6.0 * u_ref, -40.0, 40.0)
            tau_cmd = _clip(2.5 * psi_err + 1.2 * (r_ref - float(x[5])), -12.0, 12.0)
            u_cand = np.array([
                0.5 * (f_cmd - tau_cmd / d_thruster),
                0.5 * (f_cmd + tau_cmd / d_thruster),
            ])
        for ch in range(2):
            u_cand[ch] = _clip(u_cand[ch], u_prev[ch] - dT_step, u_prev[ch] + dT_step)
            u_cand[ch] = _clip(u_cand[ch], t_min, t_max)
        out_u[:, k] = u_cand
        x_next = np.asarray(dyn.forward(x, u_cand), dtype=np.float64)
        mean = _gp_mean(gp, gp_predict, [x[3], x[4], x[5], u_cand[0], u_cand[1]])
        x_next[3] += mean[0]
        x_next[4] += mean[1]
        x_next[5] += mean[2]
        x = x_next
        out_x[:, k + 1] = x
        u_prev = u_cand
    return out_x, out_u


def _gp_mean(gp, gp_predict, z: list[float]) -> np.ndarray:
    if gp_predict is not None:
        return np.asarray(gp_predict(z), dtype=np.float64).reshape(3)
    if gp is None:
        return np.zeros(3)
    pred = gp.predict(np.asarray(z, dtype=np.float64).reshape(1, 5))
    return np.asarray(pred["mean"], dtype=np.float64).reshape(3)


def evaluate_gp_horizon_with_ood(gp, x: np.ndarray, u: np.ndarray, gp_predict=None):
    """返回 (residuals(3,N+1), ood_stage_count)。训练环境需要 OOD 作为诊断指标。"""
    res = np.zeros((3, N_HORIZON + 1), dtype=np.float64)
    ood = 0
    for k in range(N_HORIZON):
        z = [x[3, k], x[4, k], x[5, k], u[0, k], u[1, k]]
        if gp_predict is not None:
            res[:, k] = np.asarray(gp_predict(z), dtype=np.float64).reshape(3)
        else:
            pred = gp.predict(np.asarray(z, dtype=np.float64).reshape(1, 5))
            res[:, k] = np.asarray(pred["mean"], dtype=np.float64).reshape(3)
            flags = np.asarray(pred["ood"]).reshape(-1)
            ood += int(flags[0]) if flags.size else 0
    res[:, N_HORIZON] = 0.0
    return res, ood


def evaluate_gp_horizon(gp, x: np.ndarray, u: np.ndarray, gp_predict=None) -> np.ndarray:
    """返回 (3, N+1) 残差；末列显式清零（终端阶段不参与动力学）。"""
    res = np.zeros((3, N_HORIZON + 1), dtype=np.float64)
    for k in range(N_HORIZON):
        res[:, k] = _gp_mean(gp, gp_predict, [x[3, k], x[4, k], x[5, k], u[0, k], u[1, k]])
    res[:, N_HORIZON] = 0.0
    return res


# ----------------------------------------------------------------------
# 控制器封装
# ----------------------------------------------------------------------
class FusionController:
    """把参考/残差/初猜交给 C ABI 求解器，维护热启动链与 anchor。"""

    def __init__(
        self,
        solver,
        gp=None,
        hydro=None,
        *,
        t_min: float = -25.0,
        t_max: float = 25.0,
        dt_max: float = 80.0,
        gp_predict=None,
        cruise: float = 0.6,
        reference_offset: int = 2,
        projection_mode: str = "discrete_offset",
        lead_s: float | None = None,
    ) -> None:
        self.solver = solver
        self.gp = gp
        self.hydro = hydro
        self.t_min = float(t_min)
        self.t_max = float(t_max)
        self.dt_max = float(dt_max)
        self.gp_predict = gp_predict
        self.cruise = float(cruise)
        self.reference_offset = int(reference_offset)
        self.projection_mode = projection_mode
        self.lead_s = lead_s
        self._pending: dict[str, Any] | None = None

    def step(
        self,
        state6: np.ndarray,
        path_xypsi: np.ndarray,
        profile_rows: np.ndarray | None,
        anchors: np.ndarray,
        q_pi,
        lambda_pi: float,
        *,
        prev_x: np.ndarray | None = None,
        prev_u: np.ndarray | None = None,
        tick_shift: int = 0,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        ref = build_frozen_reference(
            state6, path_xypsi, profile_rows,
            N=N_HORIZON, dt=DT, offset=self.reference_offset, cruise=self.cruise,
            projection_mode=self.projection_mode, lead_s=self.lead_s,
        )
        anchor = np.asarray(anchors, dtype=np.float64).reshape(2)
        x_guess, u_guess = build_gp_rollout_guess(
            np.asarray(state6, dtype=np.float64), ref, anchor, self.hydro, self.gp,
            prev_x=prev_x, prev_u=prev_u, tick_shift=int(tick_shift),
            dt=DT, t_min=self.t_min, t_max=self.t_max, dt_max=self.dt_max,
            gp_predict=self.gp_predict,
        )
        resid, ood_count = evaluate_gp_horizon_with_ood(
            self.gp, x_guess, u_guess, gp_predict=self.gp_predict
        )
        u0, solve_ms = self.solver.solve(state6, ref, resid, q_pi, lambda_pi)
        self._pending = {"x": x_guess, "u": u_guess, "u0": u0}
        return u0, {
            "reference": ref,
            "rollout_x": x_guess,
            "rollout_u": u_guess,
            "residuals": resid,
            "solver_ms": solve_ms,
            "gp_ood_stage_count": ood_count,
        }

    def commit(self, executed_anchor) -> None:
        """求解成功后提交：左移热启动链，并把执行推力写成新 anchor。"""
        self.solver.accept(executed_anchor)
        self._pending = None

    def reset_warmstart(self) -> None:
        self.solver.reset_warmstart()
        self._pending = None


def load_pooled_gp(pooled_snapshot: Path):
    """加载冻结 GP（需要 scipy）。"""
    from gp_model import MultiChannelSparseGP

    return MultiChannelSparseGP.load(Path(pooled_snapshot))
