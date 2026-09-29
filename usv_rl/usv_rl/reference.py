"""参考轨迹生成 — 对标 usv_planning_cpp 的输出形式。

规划器链路：路径点 → G1 圆弧倒角 → 稠密路径(xs, ys, psis, kappas, s)
          → TOPP 速度剖面 [v, kappa, r, t]。
训练环境无法直接消费 ROS 话题，这里用曲率剖面法生成同约束的随机路径：
- 逐段常值曲率积分得到 G1 连续路径（曲率有界，天然无倒角计算）
- 简化 TOPP：曲率限速(v ≤ sqrt(a_lat/|κ|) 且 v ≤ r_max/|κ|) + 前向加速/反向减速两遍扫描
- 剖面输出 [v, kappa, r, t]，与 /path/reference_profile 的 4 列契约对齐
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ReferenceTrajectory:
    xs: np.ndarray          # (M,) 位置
    ys: np.ndarray
    psis: np.ndarray        # (M,) 连续累积航向（不 wrap）
    kappas: np.ndarray      # (M,) 曲率
    s: np.ndarray           # (M,) 累积弧长，s[0]=0
    v_ref: np.ndarray       # (M,) 速度剖面
    r_ref: np.ndarray       # (M,) 艏摇角速度剖面 r = kappa * v
    t: np.ndarray           # (M,) 时间戳（时间参数化参考，MPC 同款）

    @property
    def total_length(self) -> float:
        return float(self.s[-1])

    @property
    def total_time(self) -> float:
        return float(self.t[-1])

    def at_time(self, time: float) -> int:
        """时间参数化参考点索引（与 MPC build_reference_ 的插值语义近似）。"""
        return int(np.clip(np.searchsorted(self.t, time, side="right") - 1, 0, len(self.t) - 1))

    def at_arc(self, arc: float) -> int:
        """弧长位置索引。"""
        return int(np.clip(np.searchsorted(self.s, arc, side="right") - 1, 0, len(self.s) - 1))


def path_from_curvature_profile(
    kappa_segments: list[float],
    seg_lengths: list[float],
    ds: float = 0.5,
    start: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[np.ndarray, ...]:
    """逐段常值曲率积分生成 G1 路径。

    kappa_segments: 每段曲率 (1/m)；seg_lengths: 每段弧长 (m)。
    返回 (xs, ys, psis, kappas, s)，psis 为连续累积航向（不 wrap）。
    """
    xs, ys, psis, kappas, ss = [start[0]], [start[1]], [start[2]], [0.0], [0.0]
    x, y, psi = start
    for kappa, seg_len in zip(kappa_segments, seg_lengths):
        n = max(1, int(round(seg_len / ds)))
        step = seg_len / n
        for _ in range(n):
            # 弧长中点法积分（圆弧的精确离散化）
            psi_mid = psi + 0.5 * kappa * step
            x += step * np.cos(psi_mid)
            y += step * np.sin(psi_mid)
            psi += kappa * step
            xs.append(x)
            ys.append(y)
            psis.append(psi)
            kappas.append(kappa)
            ss.append(ss[-1] + step)
    return (
        np.asarray(xs), np.asarray(ys), np.asarray(psis),
        np.asarray(kappas), np.asarray(ss),
    )


def speed_profile(
    kappas: np.ndarray,
    ds: float,
    v_max: float = 0.8,
    a_lat_max: float = 0.12,
    r_max: float = 0.18,
    accel_max: float = 0.18,
    decel_max: float = 0.25,
    v_start: float = 0.0,
    v_end: float = 0.0,
    v_eps: float = 0.05,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """简化 TOPP：曲率限速 + 前向加速/反向减速扫描。

    返回 (v_ref, r_ref, t)，与 path_from_curvature_profile 输出等长。
    """
    n = len(kappas)
    abs_k = np.abs(kappas)
    with np.errstate(divide="ignore"):
        v_curve = np.where(
            abs_k > 1e-6,
            np.minimum(np.sqrt(a_lat_max / abs_k), r_max / abs_k),
            v_max,
        )
    v = np.minimum(v_curve, v_max)
    v[0] = min(v[0], max(v_start, v_eps))
    v[-1] = min(v[-1], max(v_end, v_eps))

    # 反向扫描（减速限制，从终点往回）
    for i in range(n - 2, -1, -1):
        v[i] = min(v[i], np.sqrt(v[i + 1] ** 2 + 2.0 * decel_max * ds))
    # 前向扫描（加速限制，从起点往后）
    for i in range(1, n):
        v[i] = min(v[i], np.sqrt(v[i - 1] ** 2 + 2.0 * accel_max * ds))
    v = np.maximum(v, v_eps)

    r = kappas * v
    t = np.zeros(n)
    t[1:] = np.cumsum(ds / v[1:])
    return v, r, t


def make_reference(
    kappa_segments: list[float],
    seg_lengths: list[float],
    ds: float = 0.5,
    start: tuple[float, float, float] = (0.0, 0.0, 0.0),
    profile_kwargs: dict | None = None,
) -> ReferenceTrajectory:
    xs, ys, psis, kappas, s = path_from_curvature_profile(
        kappa_segments, seg_lengths, ds=ds, start=start
    )
    v, r, t = speed_profile(kappas, ds, **(profile_kwargs or {}))
    return ReferenceTrajectory(
        xs=xs, ys=ys, psis=psis, kappas=kappas, s=s, v_ref=v, r_ref=r, t=t
    )


def sample_kappa_segments(
    rng: np.random.Generator,
    path_type: str = "random",
    n_segments: int | None = None,
) -> tuple[list[float], list[float]]:
    """按课程阶段采样曲率段。

    straight: 全直线；arc: 单圆弧；zigzag: 左右交替；
    random: 随机曲率段（含直线段），总长约 36 m（60 s @ 0.6 m/s）。
    """
    if path_type == "straight":
        return [0.0], [36.0]
    if path_type == "arc":
        kappa = rng.uniform(0.08, 0.25) * rng.choice([-1.0, 1.0])
        length = 36.0
        return [kappa], [length]
    if path_type == "zigzag":
        n = n_segments or 6
        seg_len = 36.0 / n
        kappas, lengths = [], []
        sign = 1.0
        for i in range(n):
            k = rng.uniform(0.1, 0.25) * sign
            if i < n - 1:
                kappas += [k, 0.0]
                lengths += [seg_len / 2, seg_len / 2]
            else:
                kappas.append(k)
                lengths.append(seg_len)
            sign = -sign
        return kappas, lengths
    # random
    n = n_segments or int(rng.integers(4, 8))
    kappas, lengths = [], []
    for i in range(n):
        if rng.random() < 0.35:
            k = 0.0
        else:
            k = rng.uniform(0.05, 0.25) * rng.choice([-1.0, 1.0])
        kappas.append(k)
        lengths.append(float(rng.uniform(3.0, 9.0)))
    # 末尾接直线，让减速段有收敛空间
    kappas.append(0.0)
    lengths.append(6.0)
    return kappas, lengths
