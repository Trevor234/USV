"""LOS + PD 解析基线控制器 — 训练收敛性的下界参照。

不依赖策略网络，直接从环境内部状态读参考轨迹做 LOS 制导 + 稳态推力逆解。
评估时与 PPO 策略跑完全相同的路径/终止条件/指标（evaluate.py --baseline los）。
"""
from __future__ import annotations

import math

import numpy as np


class LosController:
    """LOS 制导 + 前馈/反馈推力逆解。

    用法（与 env 交互）:
        obs, info = env.reset()
        while True:
            action = los.act(env)
            obs, r, term, trunc, info = env.step(action)
    """

    def __init__(
        self,
        lookahead_m: float = 2.5,
        k_psi: float = 0.8,
        r_d_max: float = 0.35,
        k_u: float = 8.0,
        k_r: float = 3.0,
        u_d_min_frac: float = 0.3,
    ) -> None:
        self.lookahead_m = lookahead_m
        self.k_psi = k_psi
        self.r_d_max = r_d_max
        self.k_u = k_u
        self.k_r = k_r
        self.u_d_min_frac = u_d_min_frac

    def act(self, env) -> np.ndarray:
        ref = env.reference
        x, y, psi, u, v, r = env.state
        p = env.model.params
        d = p.d_thruster
        t_max = env.t_max_thrust

        i_t = env._ref_point_at_time()
        v_ref_t = ref.v_ref[i_t]

        # LOS 目标点：当前投影弧长 + 固定前瞻距离
        s_los = ref.s[env.prog_idx] + self.lookahead_m
        i_los = ref.at_arc(s_los)
        psi_d = math.atan2(ref.ys[i_los] - y, ref.xs[i_los] - x)
        e_psi_d = math.atan2(math.sin(psi_d - psi), math.cos(psi_d - psi))

        # 期望运动
        r_d = float(np.clip(self.k_psi * e_psi_d, -self.r_d_max, self.r_d_max))
        speed_frac = max(self.u_d_min_frac, math.cos(e_psi_d))
        u_d = v_ref_t * speed_frac

        # 纵向推力逆解：阻尼前馈 + 速度误差反馈
        # 阻尼力 = -(Xu + Xuu|u|)·u（Xu/Xuu 为负 → 阻力为正）
        damping_x = -(p.Xu + p.Xuu * abs(u_d)) * u_d
        tau_x = damping_x + self.k_u * (u_d - u)

        # 艏摇力矩逆解
        damping_n = -(p.Nr + p.Nrr * abs(r_d)) * r_d
        tau_n = damping_n + self.k_r * (r_d - r)

        tl = 0.5 * (tau_x - tau_n / d)
        tr = 0.5 * (tau_x + tau_n / d)
        return np.clip(np.array([tl, tr]), -t_max, t_max)
