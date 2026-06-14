"""轨迹几何层：G1 圆弧倒角（fillet）平滑。

把折线航点序列平滑成"直线段 + 最小转弯半径圆弧"的可行路径，并**解析地**给出
每点的航向 psi、曲率 kappa 与累积弧长 s（不用数值微分，避免拼接处尖刺）。

设计要点（见 plans/silly-crunching-dolphin.md）：
  - 航向从相邻航段方向自动推导，不使用航点自带 heading（避免 Dubins 短航段绕圈）。
  - 在每个拐角插入半径 >= turn_radius 的圆弧；当相邻航段过短时按 R_eff < R 裁剪并告警。
  - psi 连续累积（不在内部 wrap），曲率 kappa 在直线段=0、圆弧段=±1/R_eff。

可选的最小曲率精修 `refine_min_curvature` 默认不调用（path_planner 用开关控制）。
"""

import math
from typing import List, Sequence, Tuple

import numpy as np


def _unit(dx: float, dy: float) -> Tuple[float, float, float]:
    """返回 (ux, uy, length)；零向量返回 (0,0,0)。"""
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0, 0.0
    return dx / length, dy / length, length


def _signed_turn(uin: Tuple[float, float], uout: Tuple[float, float]) -> float:
    """从入方向到出方向的有符号转角（左正右负），范围 [-pi, pi]。"""
    cross = uin[0] * uout[1] - uin[1] * uout[0]
    dot = uin[0] * uout[0] + uin[1] * uout[1]
    return math.atan2(cross, dot)


def fillet_path(
    waypoints: Sequence[Tuple[float, float]],
    turn_radius: float,
    resolution: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """对折线航点做圆弧倒角，返回稠密采样的可行路径。

    Args:
        waypoints: [(x, y), ...] 顺序航点（ROS local map 平面）。
        turn_radius: 期望最小转弯半径 R [m]。
        resolution: 采样间距 [m]。

    Returns:
        (xs, ys, psis, kappas, s, warnings)
        xs, ys: 位置；psis: **连续累积**航向 [rad]；kappas: 有符号曲率 [1/m]；
        s: 累积弧长 [m]；warnings: 需要上层 log 的告警字符串列表。
    """
    warnings: List[str] = []
    pts = [(float(x), float(y)) for x, y in waypoints]
    n = len(pts)
    if n < 2:
        return (np.empty(0), np.empty(0), np.empty(0), np.empty(0), np.empty(0), warnings)

    res = max(1e-3, float(resolution))
    R = max(1e-3, float(turn_radius))

    xs: List[float] = []
    ys: List[float] = []
    psis: List[float] = []
    kappas: List[float] = []

    # 连续累积航向：以第一段方向为起点
    ux0, uy0, _ = _unit(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
    psi_cont = math.atan2(uy0, ux0)

    # 当前"游标"位置（上一圆弧出口 / 起点）
    cx, cy = pts[0]
    xs.append(cx)
    ys.append(cy)
    psis.append(psi_cont)
    kappas.append(0.0)

    for i in range(1, n - 1):
        A, B, C = pts[i - 1], pts[i], pts[i + 1]
        uin_x, uin_y, _ = _unit(B[0] - A[0], B[1] - A[1])
        uout_x, uout_y, len_out = _unit(C[0] - B[0], C[1] - B[1])
        if (uin_x, uin_y) == (0.0, 0.0) or (uout_x, uout_y) == (0.0, 0.0):
            continue  # 退化（重合点），跳过该顶点

        delta = _signed_turn((uin_x, uin_y), (uout_x, uout_y))
        if abs(delta) < 1e-4:
            continue  # 近似共线：无需倒角，留给直线段

        # 切线缩进 T = R * tan(|delta|/2)，按相邻航段长度的一半裁剪以防自交/重叠
        len_in = math.hypot(B[0] - cx, B[1] - cy)  # 从当前游标到 B 的可用长度
        tan_half = math.tan(abs(delta) / 2.0)
        t_desired = R * tan_half
        t_max_geom = 0.5 * min(len_in, len_out)
        T = min(t_desired, t_max_geom)
        if T < 1e-6:
            continue
        r_eff = T / tan_half  # 反解可行半径
        if r_eff < R - 1e-3:
            warnings.append(
                f"航点#{i} 处航段过短，转弯半径被裁剪 R_eff={r_eff:.2f}m < turn_radius={R:.2f}m"
            )

        # 入切点：从 B 沿入方向回退 T
        tp_in_x = B[0] - uin_x * T
        tp_in_y = B[1] - uin_y * T

        # 1) 直线段：游标 -> 入切点（航向保持 psi_cont）
        _sample_straight(cx, cy, tp_in_x, tp_in_y, psi_cont, res, xs, ys, psis, kappas)
        cx, cy = tp_in_x, tp_in_y

        # 2) 圆弧段：曲率 kappa = sign(delta)/r_eff，弧长 = r_eff*|delta|
        kappa = math.copysign(1.0 / r_eff, delta)
        arc_len = r_eff * abs(delta)
        cx, cy, psi_cont = _sample_arc(
            cx, cy, psi_cont, kappa, arc_len, res, xs, ys, psis, kappas
        )

    # 3) 末段直线：游标 -> 终点航点
    end = pts[n - 1]
    _sample_straight(cx, cy, end[0], end[1], psi_cont, res, xs, ys, psis, kappas)

    xs_a = np.asarray(xs)
    ys_a = np.asarray(ys)
    s = _arc_length(xs_a, ys_a)
    return xs_a, ys_a, np.asarray(psis), np.asarray(kappas), s, warnings


def _sample_straight(x0, y0, x1, y1, psi, res, xs, ys, psis, kappas) -> None:
    """对直线段按 res 采样（不含起点，避免与上一段重复）。"""
    seg_len = math.hypot(x1 - x0, y1 - y0)
    if seg_len < 1e-6:
        return
    n_steps = max(1, int(round(seg_len / res)))
    for k in range(1, n_steps + 1):
        t = k / n_steps
        xs.append(x0 + t * (x1 - x0))
        ys.append(y0 + t * (y1 - y0))
        psis.append(psi)
        kappas.append(0.0)


def _sample_arc(x0, y0, psi0, kappa, arc_len, res, xs, ys, psis, kappas):
    """对常曲率圆弧精确积分采样（不含起点）。返回 (x_end, y_end, psi_end)。

    单车模型 dx/ds=cos psi, dy/ds=sin psi, dpsi/ds=kappa，常 kappa 下的解析积分。
    """
    n_steps = max(1, int(round(arc_len / res)))
    ds = arc_len / n_steps
    x, y, psi = x0, y0, psi0
    for _ in range(n_steps):
        psi_next = psi + kappa * ds
        if abs(kappa) > 1e-9:
            x += (math.sin(psi_next) - math.sin(psi)) / kappa
            y += (math.cos(psi) - math.cos(psi_next)) / kappa
        else:
            x += ds * math.cos(psi)
            y += ds * math.sin(psi)
        psi = psi_next
        xs.append(x)
        ys.append(y)
        psis.append(psi)
        kappas.append(kappa)
    return x, y, psi


def _arc_length(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """累积弧长（本地实现，避免跨包依赖 usv_mpc.utils）。"""
    s = np.zeros(len(xs))
    for i in range(1, len(xs)):
        s[i] = s[i - 1] + math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])
    return s


def refine_min_curvature(
    xs: np.ndarray,
    ys: np.ndarray,
    corridor: float,
    turn_radius: float,
    max_iter: int = 40,
):
    """可选：最小曲率精修（最小化二阶差分能量，端点固定，逐点限制在走廊内）。

    这是一个小规模 QP（决策为各点 x,y），用 CasADi/IPOPT 求解。默认 **不** 被
    path_planner 调用（enable_curvature_opt=false）；失败/超时由调用方回退 fillet。

    Returns:
        (xs_opt, ys_opt) 或在不可用/失败时返回 None。
    """
    try:
        import casadi as ca
    except Exception:
        return None

    n = len(xs)
    if n < 5:
        return None

    opti = ca.Opti()
    X = opti.variable(n)
    Y = opti.variable(n)

    cost = 0
    for i in range(1, n - 1):
        ddx = X[i - 1] - 2 * X[i] + X[i + 1]
        ddy = Y[i - 1] - 2 * Y[i] + Y[i + 1]
        cost += ddx * ddx + ddy * ddy
    opti.minimize(cost)

    # 端点固定
    opti.subject_to(X[0] == float(xs[0]))
    opti.subject_to(Y[0] == float(ys[0]))
    opti.subject_to(X[n - 1] == float(xs[n - 1]))
    opti.subject_to(Y[n - 1] == float(ys[n - 1]))
    # 走廊约束：每点不偏离 fillet 结果超过 corridor
    c = max(1e-3, float(corridor))
    for i in range(1, n - 1):
        opti.subject_to(opti.bounded(float(xs[i]) - c, X[i], float(xs[i]) + c))
        opti.subject_to(opti.bounded(float(ys[i]) - c, Y[i], float(ys[i]) + c))

    opti.set_initial(X, xs)
    opti.set_initial(Y, ys)
    opti.solver("ipopt", {"print_time": 0},
                {"print_level": 0, "max_iter": int(max_iter),
                 "tol": 1e-3, "acceptable_tol": 1e-2, "acceptable_iter": 5})
    try:
        sol = opti.solve()
        return np.asarray(sol.value(X)).flatten(), np.asarray(sol.value(Y)).flatten()
    except Exception:
        return None


def recompute_geometry(
    xs: np.ndarray, ys: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """从离散点数值重算 (psi_continuous, kappa, s)。

    供 `refine_min_curvature` 改动点位后重新导出航向/曲率使用。航向以累积
    unwrap 保持连续（供曲率差分），曲率用有限差分。
    """
    n = len(xs)
    s = _arc_length(xs, ys)
    if n < 2:
        return np.zeros(n), np.zeros(n), s

    dx = np.gradient(xs)
    dy = np.gradient(ys)
    psi = np.unwrap(np.arctan2(dy, dx))
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)
    kappa = (dx * ddy - dy * ddx) / np.power(dx * dx + dy * dy + 1e-8, 1.5)
    return psi, kappa, s
