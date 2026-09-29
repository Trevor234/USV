"""观测构建单一真源 — 训练环境与 ROS 部署节点共用。

usv_rl_ros/rl_policy_node 不重写观测逻辑，而是用这里导出的
advance_progress / compose_observation 组装与训练完全一致的 43 维观测。
tests/test_obs_equivalence.py 锁死本模块与 UsvTrackingEnv._get_obs 的等价性，
防止训练/部署观测漂移。

观测布局（与 usv_tracking_env.py 文档一致）:
  [u, v, r, sin(psi), cos(psi),
   sin(e_psi_ref_t), cos(e_psi_ref_t), v_ref_t, r_ref_t,   # 时间参考（调度）
   K × (dx_b, dy_b, kappa_k, v_ref_k),                     # 空间前瞻
   T_L_prev, T_R_prev]
"""
from __future__ import annotations

import math

import numpy as np


def advance_progress(
    ref_xs: np.ndarray,
    ref_ys: np.ndarray,
    x: float,
    y: float,
    prev_idx: int,
    window: int = 40,
) -> int:
    """最近点单调推进搜索（与 env._update_progress 一致）。

    从 prev_idx 起向前看 window 个点取最近；允许贴着参考线横向波动，
    抄近道由外部终止/监控约束处理。
    """
    n = len(ref_xs)
    hi = min(prev_idx + window, n - 1)
    idxs = np.arange(prev_idx, hi + 1)
    d2 = (ref_xs[idxs] - x) ** 2 + (ref_ys[idxs] - y) ** 2
    return int(idxs[int(np.argmin(d2))])


def compose_observation(
    state6: np.ndarray,
    ref_xs: np.ndarray,
    ref_ys: np.ndarray,
    ref_psis: np.ndarray,
    ref_kappas: np.ndarray,
    ref_v: np.ndarray,
    ref_r: np.ndarray,
    ref_s: np.ndarray,
    ref_time: np.ndarray,
    t_now: float,
    prog_idx: int,
    prev_thrust: np.ndarray,
    lookahead,
    obs_noise_vel: float = 0.0,
    obs_noise_pos: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """组装 43 维观测。state6 = [x, y, psi, u, v, r]。

    t_now 为当前调度时刻：env 传 step_count*dt，ROS 节点传 (now - path_stamp)。
    空间前瞻从 ref_s[prog_idx] 起按 lookahead 弧长偏移取点。
    """
    x_s, y_s, psi, u, v, r = state6

    def _noise(sigma: float) -> float:
        if sigma > 0.0 and rng is not None:
            return float(rng.normal(0.0, sigma))
        return 0.0

    u_o = u + _noise(obs_noise_vel)
    v_o = v + _noise(obs_noise_vel)
    r_o = r + _noise(obs_noise_vel)
    x_o = x_s + _noise(obs_noise_pos)
    y_o = y_s + _noise(obs_noise_pos)

    # 时间参考点（调度）
    i_t = int(np.clip(np.searchsorted(ref_time, t_now, side="right") - 1, 0, len(ref_time) - 1))
    e_psi = math.atan2(math.sin(psi - ref_psis[i_t]), math.cos(psi - ref_psis[i_t]))
    cos_p, sin_p = math.cos(psi), math.sin(psi)

    obs = [
        u_o, v_o, r_o, sin_p, cos_p,
        math.sin(e_psi), math.cos(e_psi), ref_v[i_t], ref_r[i_t],
    ]

    s0 = ref_s[prog_idx]
    for off in lookahead:
        arc = s0 + off
        i_k = int(np.clip(np.searchsorted(ref_s, arc, side="right") - 1, 0, len(ref_s) - 1))
        dx_w = ref_xs[i_k] - x_o
        dy_w = ref_ys[i_k] - y_o
        obs += [
            cos_p * dx_w + sin_p * dy_w,
            -sin_p * dx_w + cos_p * dy_w,
            ref_kappas[i_k],
            ref_v[i_k],
        ]

    obs += [prev_thrust[0], prev_thrust[1]]
    return np.asarray(obs, dtype=np.float32)


def apply_thrust_limits(
    prev_thrust: np.ndarray,
    raw: np.ndarray,
    t_max: float,
    d_t_max: float,
    dt: float,
) -> tuple[np.ndarray, np.ndarray]:
    """推力限幅 + 变化率限制。返回 (applied, target)。

    与 env.step 的执行语义一致：先按 dT_max*dt 把 prev 拉向 raw，再 clamp。
    """
    raw = np.clip(np.asarray(raw, dtype=np.float64), -t_max, t_max)
    max_delta = d_t_max * dt
    target = np.clip(
        prev_thrust + np.clip(raw - prev_thrust, -max_delta, max_delta),
        -t_max, t_max,
    )
    return target.copy(), target
