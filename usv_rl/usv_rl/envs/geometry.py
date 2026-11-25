"""路径几何原语 — 环境奖励、（P5）融合克隆与指标共用同一套投影口径。

约定：
- `e_ct` 带符号：以投影段航向的左法线（-sin, cos）为正方向，左偏为正。
- 投影只在给定段窗口内搜索（`[lo, hi]` 为段索引，段 i 连接点 i 与 i+1），
  不做全局最近点搜索——全局搜索会在近道/回头段上给出错误投影。
"""
from __future__ import annotations

import math

import numpy as np


def project_to_polyline(
    x: float,
    y: float,
    xs: np.ndarray,
    ys: np.ndarray,
    lo: int,
    hi: int,
) -> tuple[float, float, int]:
    """点 (x, y) 在折线段 [lo, hi] 上的最近投影。

    返回 (e_ct, psi_seg, seg_idx)：
    - e_ct: 带符号横向误差（m），左法线为正
    - psi_seg: 投影所在段的航向（rad，已归一化到 (-pi, pi]）
    - seg_idx: 投影所在段起点索引
    """
    n = len(xs)
    if n < 2:
        return 0.0, 0.0, 0
    lo = max(0, min(int(lo), n - 2))
    hi = max(lo, min(int(hi), n - 2))

    best_d2 = math.inf
    best_i = lo
    best_t = 0.0
    for i in range(lo, hi + 1):
        ax, ay = float(xs[i]), float(ys[i])
        bx, by = float(xs[i + 1]), float(ys[i + 1])
        ex, ey = bx - ax, by - ay
        seg2 = ex * ex + ey * ey
        if seg2 <= 0.0:
            t = 0.0
        else:
            t = ((x - ax) * ex + (y - ay) * ey) / seg2
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        px, py = ax + t * ex, ay + t * ey
        d2 = (x - px) ** 2 + (y - py) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best_i = i
            best_t = t

    ax, ay = float(xs[best_i]), float(ys[best_i])
    bx, by = float(xs[best_i + 1]), float(ys[best_i + 1])
    psi_seg = math.atan2(by - ay, bx - ax)
    px = ax + best_t * (bx - ax)
    py = ay + best_t * (by - ay)
    nx, ny = -math.sin(psi_seg), math.cos(psi_seg)
    e_ct = (x - px) * nx + (y - py) * ny
    return float(e_ct), float(psi_seg), int(best_i)


def cte_penalty(e_ct: float, linear_m: float) -> float:
    """横向误差惩罚：|e| <= linear_m 时平方，超出后线性续接（保证梯度不消失）。"""
    a = abs(float(e_ct))
    if a <= linear_m:
        return a * a
    return float(linear_m * (2.0 * a - linear_m))
