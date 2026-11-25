"""跟踪代价/奖励单一真源 — 训练环境（方案C）与融合闭环环境（方案A, P5）共用。

代价与 `mpc_params.yaml` 的 dynamic Q/R/Rd 同量纲，但位置项用**路径几何**横向误差
（`e_ct`，带平方-线性过渡）而不是世界系 (dx, dy)：世界系项会随参考点前进而把
"沿迹滞后"和"横向偏离"混在一起，v4 的 13.6 m 横向冲线就是这么来的。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from usv_rl.envs.geometry import cte_penalty


@dataclass(frozen=True)
class TrackingCostParams:
    q_ct: float = 100.0
    q_psi: float = 50.0
    q_u: float = 8.0
    q_v: float = 1.0
    q_r: float = 8.0
    r_thrust: float = 0.05
    r_dthrust: float = 0.2
    reward_scale: float = 0.2
    w_progress: float = 15.0
    ct_linear_m: float = 1.0
    use_mode_energy: bool = False
    r_cm: float = 0.05
    r_dm: float = 0.05
    drag_ff_gain: float = 0.0
    ff_xu: float = -2.272063
    ff_xuu: float = -11.571784


def tracking_cost(
    state6: np.ndarray,
    applied: np.ndarray,
    prev_applied: np.ndarray,
    v_ref: float,
    r_ref: float,
    e_ct: float,
    e_psi: float,
    ds_prog: float,
    p: TrackingCostParams,
) -> float:
    """单步奖励 = -reward_scale * 跟踪/控制代价 + w_progress * 弧长进度。"""
    _, _, _, u, v, r = (float(v_) for v_ in state6)
    if p.use_mode_energy:
        tl, tr = float(applied[0]), float(applied[1])
        t_cm = 0.5 * (tl + tr)
        t_dm = 0.5 * (tr - tl)
        v_ref_float = float(v_ref)
        t_cm_ff = 0.5 * p.drag_ff_gain * (-p.ff_xu - p.ff_xuu * abs(v_ref_float)) * v_ref_float
        thrust_cost = 2.0 * p.r_cm * ((t_cm - t_cm_ff) ** 2) + 2.0 * p.r_dm * (t_dm ** 2)
    else:
        thrust_cost = p.r_thrust * float(np.sum(np.square(applied)))
    return float(
        -p.reward_scale
        * (
            p.q_ct * cte_penalty(e_ct, p.ct_linear_m)
            + p.q_psi * e_psi ** 2
            + p.q_u * (u - v_ref) ** 2
            + p.q_v * v ** 2
            + p.q_r * (r - r_ref) ** 2
            + thrust_cost
            + p.r_dthrust * float(np.sum(np.square(np.asarray(applied) - np.asarray(prev_applied))))
        )
        + p.w_progress * float(ds_prog)
    )
