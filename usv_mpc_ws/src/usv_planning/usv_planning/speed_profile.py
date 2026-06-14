"""速度/时间层：时间最优速度剖面（TOPP, time-optimal path parameterization）。

给定路径曲率 kappa(s) 与弧长 s，在以下约束下求每点速度 v(s)（确定性两遍扫描）：
  - 巡航/最大速度 u_max；
  - 转艏角速度饱和 r = kappa*v <= r_max  =>  v <= r_max/|kappa|；
  - 侧向加速度 a_lat = kappa*v^2 <= a_lat_max  =>  v <= sqrt(a_lat_max/|kappa|)；
  - 纵向加速 a_acc / 减速 a_dec 限制（前向/后向扫描）；
  - 起点速度 v_start、末端速度 v_end。

由速度剖面积分得到时间参数 t(s)，并给出参考转艏角速度 r = kappa*v。
纯 numpy，O(N)，无优化求解器，<1ms，无实时性风险。
"""

import math
from typing import Tuple

import numpy as np

_EPS = 1e-6


def compute_profile(
    kappas: np.ndarray,
    s: np.ndarray,
    u_max: float,
    r_max: float,
    a_lat_max: float,
    a_acc: float,
    a_dec: float,
    v_start: float,
    v_end: float,
    v_min: float = 0.2,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """计算时间最优速度剖面。

    Returns:
        (vs, rs, ts)
        vs: 每点速度 [m/s]；rs: 参考转艏角速度 = kappa*v [rad/s]；ts: 每点时间戳 [s]。
    """
    n = len(s)
    if n == 0:
        return np.empty(0), np.empty(0), np.empty(0)
    if n == 1:
        return np.array([max(v_min, 0.0)]), np.array([0.0]), np.array([0.0])

    kappa_abs = np.abs(kappas)
    u_max = max(_EPS, float(u_max))
    a_lat_max = max(_EPS, float(a_lat_max))
    a_acc = max(_EPS, float(a_acc))
    a_dec = max(_EPS, float(a_dec))

    # 曲率限速包络
    v_curve = np.full(n, u_max)
    turning = kappa_abs > _EPS
    v_curve[turning] = np.minimum(
        v_curve[turning],
        np.minimum(r_max / kappa_abs[turning],
                   np.sqrt(a_lat_max / kappa_abs[turning])),
    )
    # 不把 v_curve 强行抬到 v_min：v_min 只用于时间积分防除零，不能破坏曲率/转艏约束。
    v_curve = np.maximum(v_curve, 0.0)

    v = v_curve.copy()

    # 起点速度（受当前速度与曲率限速共同约束）
    v[0] = min(v_curve[0], max(float(v_start), 0.0))

    # 前向扫描：受加速度上限 a_acc 约束
    for i in range(1, n):
        ds = max(_EPS, s[i] - s[i - 1])
        v[i] = min(v_curve[i], math.sqrt(v[i - 1] ** 2 + 2.0 * a_acc * ds))

    # 末端速度
    v[n - 1] = min(v[n - 1], max(float(v_end), 0.0))

    # 后向扫描：受减速度上限 a_dec 约束
    for i in range(n - 2, -1, -1):
        ds = max(_EPS, s[i + 1] - s[i])
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2.0 * a_dec * ds))

    # 时间积分（梯形）；分母用 v_min 兜底，避免 v->0 处除零
    ts = np.zeros(n)
    for i in range(1, n):
        ds = s[i] - s[i - 1]
        v_avg = max(0.5 * (v[i - 1] + v[i]), v_min)
        ts[i] = ts[i - 1] + ds / v_avg

    rs = kappas * v
    return v, rs, ts
