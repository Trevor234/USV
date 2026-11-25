"""观测构建单一真源 — 训练环境与 ROS 部署节点共用。

usv_rl_ros/rl_policy_node 与 research/scheme_a/learning/ppo_proposal_node.py 不重写
观测逻辑，而是按这里导出的语义组装与训练完全一致的 43 维观测。
`tests/test_obs_equivalence.py` 锁死本模块与 `UsvTrackingEnv._get_obs` 的等价性，
`tests/test_obs_contract_parity.py` 锁死部署侧副本与本模块的逐位一致，
防止训练/部署观测漂移。

观测布局（与 usv_tracking_env.py 文档一致）:
  [u, v, r, sin(psi), cos(psi),
   sin(e_psi_p), cos(e_psi_p), v_ref_p, r_ref_p,        # 进度索引参考（非时间索引）
   K × (dx_b, dy_b, kappa_k, v_ref_k),                   # 空间前瞻（弧长偏移）
   T_L_prev, T_R_prev]

参考点索引语义 (`ppo-obs-v2`)：e_psi / v_ref / r_ref 三个通道一律取 `prog_idx`
（单调推进的最近路径点），不再取时间轴上"此刻应在的位置"。时间索引在两处失真：
落后时参考点跑到船前方（e_psi 恒为负、v_ref 恒大于实际），超前时相反；
且 rebase 平移量本身就是一个未进入观测的隐藏状态。
"""
from __future__ import annotations

import math

import numpy as np

OBS_CONTRACT_VERSION = "ppo-obs-v2"

# 前瞻弧长偏移（m）。训练与部署必须一致 —— 部署节点用同值副本，
# 并在 manifest 的 observation_contract 里做绑定校验。
#
# 取值来自 P1.4 三臂闭环消融（36 eps/arm + 2 dev eps，calibration，λπ=5e-4）：
#   gp_only        CTE 0.07582
#   gp_ppo_la40    Δ=-0.00031 [-0.00287,+0.00146] p=0.44   （v5 训练口径 4.0 m）
#   gp_ppo_la75    Δ=+0.00120 [-0.00096,+0.00274] p=6.5e-4 （方案 A 部署口径 7.5 m）
# 判定 adopt_training=False（ci95 上界 > 0），即"前瞻距离不是唯一主因"。
# 按计划该情形取方案 A 元组：训练与部署仍必须严格一致，不能为"跟 v5 一致"而
# 保留 4.0 m —— 一致性比历史权重重要。
LOOKAHEAD_M = (0.4, 0.8, 1.4, 2.2, 3.2, 4.4, 5.8, 7.5)

# 进度搜索窗口（点）：每步最多前进 8 点 = 4 m；船每步物理位移 <= 0.2 m。
# 窗口挡住"跳到 15 m 外的路径点"，避免抄近道时进度飞跳。
PROGRESS_WINDOW = 8
# 距离门限（m）：窗口内最近点若仍远于该值，进度保持不变。
# 窗口与门限各司其职：窗口挡纵向跳变，门限挡"远离航线时照样记进度"。
PROGRESS_GATE_M = 1.0


def advance_progress(
    ref_xs: np.ndarray,
    ref_ys: np.ndarray,
    x: float,
    y: float,
    prev_idx: int,
    window: int = PROGRESS_WINDOW,
    gate_m: float = PROGRESS_GATE_M,
) -> int:
    """最近点单调推进搜索（与 env._update_progress 一致）。"""
    n = len(ref_xs)
    if n == 0:
        return 0
    prev_idx = int(min(max(int(prev_idx), 0), n - 1))
    hi = min(prev_idx + window, n - 1)
    idxs = np.arange(prev_idx, hi + 1)
    d2 = (ref_xs[idxs] - x) ** 2 + (ref_ys[idxs] - y) ** 2
    k = int(np.argmin(d2))
    if gate_m > 0.0 and float(d2[k]) > gate_m * gate_m:
        return prev_idx
    return int(idxs[k])


def compose_observation(
    state6: np.ndarray,
    ref_xs: np.ndarray,
    ref_ys: np.ndarray,
    ref_psis: np.ndarray,
    ref_kappas: np.ndarray,
    ref_v: np.ndarray,
    ref_r: np.ndarray,
    ref_s: np.ndarray,
    prog_idx: int,
    prev_thrust: np.ndarray,
    lookahead=LOOKAHEAD_M,
    obs_noise_vel: float = 0.0,
    obs_noise_pos: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """组装 43 维观测。state6 = [x, y, psi, u, v, r]。

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

    i_p = int(np.clip(prog_idx, 0, len(ref_psis) - 1))
    e_psi = math.atan2(math.sin(psi - ref_psis[i_p]), math.cos(psi - ref_psis[i_p]))
    cos_p, sin_p = math.cos(psi), math.sin(psi)

    obs = [
        u_o, v_o, r_o, sin_p, cos_p,
        math.sin(e_psi), math.cos(e_psi), ref_v[i_p], ref_r[i_p],
    ]

    s0 = ref_s[i_p]
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
