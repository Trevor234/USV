#!/usr/bin/env python3
"""方案 A 机动参考生成器 — 场景权威的唯一副本。

从 `usv_research_safety_cpp/scripts/run_scheme_a_closed_loop.py` 原样搬出，
运行器改为从这里 import（同目录脚本，`python3 <path>` 启动，无需 package），
训练侧 `usv_rl.reference.make_maneuver_reference` 用 importlib 按路径加载同一文件。

任何对生成语义的改动都会同时改变受控仿真场景与训练分布 —— 改动前先证明
`tests/test_reference_maneuvers.py` 与运行器字节等价性检查仍然通过。
"""
from __future__ import annotations

import math
import random

MANEUVER_TYPES = (
    "straight",
    "left_turn",
    "right_turn",
    "s_turn",
    "rate_limited_thrust_step",
    "speed_transition",
)


def _smooth_step(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 0.5 * (1.0 - math.cos(math.pi * x))


def generate_maneuver_path_and_profile(
    maneuver: str,
    seconds: float,
    seed: int = 0,
    cruise_speed: float | None = None,
) -> tuple[list[str], list[str]]:
    """Generate aligned, trackable, non-self-intersecting (path_rows, profile_rows)."""
    rng = random.Random(seed)
    n_steps = int(seconds * 5) + 2
    dt = 0.2
    u0 = float(cruise_speed) if cruise_speed is not None else rng.uniform(0.55, 0.85)
    x = 0.0
    y = 0.0
    psi = 0.0
    path_rows: list[str] = []
    profile_rows: list[str] = []

    # Turn arc capped well below pi (~100 deg max) so path NEVER self-intersects.
    turn_rate = rng.uniform(0.15, 0.20)
    turn_start = 4.0
    turn_hold_end = 13.0
    s_amp = rng.uniform(0.14, 0.22)
    s_period = rng.uniform(14.0, 18.0)
    s_phase = rng.uniform(-0.25, 0.25)

    for i in range(n_steps):
        t_s = i * dt
        v_d = u0 * (0.25 + 0.75 * _smooth_step(t_s / 3.0))
        r_d = 0.0

        if maneuver == "straight":
            v_d = max(0.35, min(0.95, u0 * (0.30 + 0.70 * _smooth_step(t_s / 3.0))))
            r_d = (rng.uniform(-0.015, 0.015) * math.sin(0.25 * t_s)) if seed > 0 else 0.0
        elif maneuver == "left_turn":
            env = _smooth_step((t_s - turn_start) / 2.5) * (1.0 - _smooth_step((t_s - turn_hold_end) / 2.5))
            r_d = turn_rate * env
        elif maneuver == "right_turn":
            env = _smooth_step((t_s - turn_start) / 2.5) * (1.0 - _smooth_step((t_s - turn_hold_end) / 2.5))
            r_d = -turn_rate * env
        elif maneuver == "s_turn":
            gate = _smooth_step((t_s - 2.0) / 2.5)
            r_d = gate * s_amp * math.sin(2.0 * math.pi * (t_s - 2.0) / s_period + s_phase)
        elif maneuver == "rate_limited_thrust_step":
            # Crisp 0.8s speed transitions + bounded alternating heading pulses (no loop-back).
            seg = 6.0
            blk = int(t_s // seg)
            tau = t_s - blk * seg
            v_prev = 0.85 if ((blk - 1) % 2 == 0 and blk > 0) else 0.42
            v_next = 0.85 if (blk % 2 == 0) else 0.42
            v_d = v_prev + (v_next - v_prev) * _smooth_step(tau / 0.8) if blk > 0 else 0.42 + 0.43 * _smooth_step(t_s / 1.5)
            turn_sign = 1.0 if (blk % 2 == 1) else -1.0
            if blk == 0:
                r_d = 0.0
            else:
                r_d = 0.16 * turn_sign * _smooth_step(tau / 0.6) * (1.0 - _smooth_step((tau - 3.6) / 0.6))
        elif maneuver == "speed_transition":
            levels = (0.42, 0.85, 0.50, 0.92, 0.45, 0.78)
            seg = 7.0
            blk = int(t_s // seg)
            tau = t_s - blk * seg
            v_prev = levels[max(0, (blk - 1)) % len(levels)]
            v_curr = levels[blk % len(levels)]
            v_d = v_prev + (v_curr - v_prev) * _smooth_step(tau / 2.0) if blk > 0 else levels[0] * (0.4 + 0.6 * _smooth_step(t_s / 2.0))
            r_d = 0.08 * _smooth_step((t_s - 2.0) / 2.0) * math.sin(0.30 * t_s + s_phase)
        else:
            raise ValueError(f"unsupported maneuver: {maneuver}")

        path_rows.append(f"{x:.6f} {y:.6f} {psi:.6f} {t_s:.6f}")
        profile_rows.append(f"{v_d:.6f} 0.000000 {r_d:.6f} {t_s:.6f}")
        psi_mid = psi + 0.5 * r_d * dt
        x += v_d * math.cos(psi_mid) * dt
        y += v_d * math.sin(psi_mid) * dt
        psi = math.atan2(math.sin(psi + r_d * dt), math.cos(psi + r_d * dt))

    return path_rows, profile_rows
