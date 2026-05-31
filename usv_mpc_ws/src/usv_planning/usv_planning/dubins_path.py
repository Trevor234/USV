"""Dubins path generator for USV.

Dubins curves connect two poses with minimum-length paths composed of straight
segments and constant-curvature arcs (L=left turn, R=right turn, S=straight).
"""

import math
from enum import Enum
from typing import List, Tuple, Optional

import numpy as np


class DubinsPathType(Enum):
    LSL = 0
    LSR = 1
    RSL = 2
    RSR = 3
    RLR = 4
    LRL = 5


def mod2pi(theta: float) -> float:
    """Wrap angle to [0, 2*pi)."""
    return theta - 2.0 * math.pi * math.floor(theta / (2.0 * math.pi))


class DubinsPath:
    """A single Dubins path segment."""

    def __init__(self):
        self.type: Optional[DubinsPathType] = None
        self.lengths = [0.0, 0.0, 0.0]  # seg1, seg2, seg3
        self.total_length = 0.0

    def sample(self, start_x: float, start_y: float, start_psi: float,
               radius: float, step_size: float) -> List[Tuple[float, float, float]]:
        """Sample points along the Dubins path."""
        if self.type is None:
            return []

        points = []
        x, y, psi = start_x, start_y, start_psi
        points.append((x, y, psi))

        for seg_idx in range(3):
            seg_len = self.lengths[seg_idx]
            motion = self._seg_motion(self.type, seg_idx)
            steps = max(1, int(seg_len / step_size))
            d = seg_len / steps

            for _ in range(steps):
                if motion == "L":
                    # Turn left
                    dpsi = d / radius
                    psi += dpsi
                    x += radius * (-math.sin(psi - dpsi) + math.sin(psi))
                    y += radius * (math.cos(psi - dpsi) - math.cos(psi))
                elif motion == "R":
                    # Turn right
                    dpsi = d / radius
                    psi -= dpsi
                    x += radius * (math.sin(psi + dpsi) - math.sin(psi))
                    y += radius * (-math.cos(psi + dpsi) + math.cos(psi))
                else:  # "S"
                    x += d * math.cos(psi)
                    y += d * math.sin(psi)
                psi = mod2pi(psi)
                points.append((x, y, psi))

        return points

    @staticmethod
    def _seg_motion(path_type: DubinsPathType, seg_idx: int) -> str:
        """Return 'L', 'R', or 'S' for a segment."""
        name = path_type.name  # e.g. 'LSL'
        return name[seg_idx]


def dubins_path_length(start: Tuple[float, float, float],
                       end: Tuple[float, float, float],
                       radius: float) -> float:
    """Calculate minimum Dubins path length."""
    path = plan_dubins(start, end, radius)
    if path is None:
        return float("inf")
    return path.total_length


def plan_dubins(start: Tuple[float, float, float],
                end: Tuple[float, float, float],
                radius: float) -> Optional[DubinsPath]:
    """Plan the shortest Dubins path between two poses.

    Args:
        start: (x, y, psi) start pose in NED [m, m, rad]
        end: (x, y, psi) end pose in NED [m, m, rad]
        radius: minimum turn radius [m]

    Returns:
        DubinsPath object or None if no path found.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    # Transform to start-frame coordinates
    th = start[2]
    sin_th = math.sin(th)
    cos_th = math.cos(th)
    dx_local = cos_th * dx + sin_th * dy
    dy_local = -sin_th * dx + cos_th * dy
    # Normalize to radius=1
    d = math.hypot(dx_local, dy_local) / radius
    if d < 1e-6:
        return None

    theta = mod2pi(math.atan2(dy_local, dx_local))
    alpha = mod2pi(-theta)
    beta = mod2pi(end[2] - th - theta)

    best_path = None
    best_len = float("inf")

    for path_type in DubinsPathType:
        segs = _dubins_word(alpha, beta, d, path_type)
        if segs is None:
            continue
        total = sum(segs) * radius
        if total < best_len:
            best_len = total
            best_path = DubinsPath()
            best_path.type = path_type
            best_path.lengths = [s * radius for s in segs]
            best_path.total_length = total

    return best_path


def _dubins_word(alpha: float, beta: float, d: float,
                 path_type: DubinsPathType) -> Optional[List[float]]:
    """Compute Dubins path segment lengths for a given word type.

    All outputs are normalized by turn radius. Returns None if infeasible.
    """
    if path_type == DubinsPathType.LSL:
        tmp0 = d + math.sin(alpha) - math.sin(beta)
        tmp1 = math.atan2(math.cos(beta) - math.cos(alpha), tmp0)
        t = mod2pi(-alpha + tmp1 + math.pi / 2)
        p_sq = 2 + d * d - 2 * math.cos(alpha - beta) + 2 * d * (math.sin(alpha) - math.sin(beta))
        if p_sq < 0:
            return None
        p = math.sqrt(p_sq)
        q = mod2pi(beta - math.atan2(math.cos(beta) - math.cos(alpha), tmp0) + math.pi / 2)
        return [t, p, q]

    elif path_type == DubinsPathType.LSR:
        tmp0 = d - math.sin(alpha) + math.sin(beta)
        p_sq = -2 + d * d + 2 * math.cos(alpha - beta) + 2 * d * (math.sin(alpha) - math.sin(beta))
        if p_sq < 0:
            return None
        p = math.sqrt(p_sq)
        t = mod2pi(-alpha + math.atan2(math.cos(beta) - math.cos(alpha), tmp0) - math.atan2(-2, p))
        q = mod2pi(-beta + math.atan2(math.cos(beta) - math.cos(alpha), tmp0) - math.atan2(-2, p))
        return [t, p, q]

    elif path_type == DubinsPathType.RSL:
        tmp0 = d + math.sin(alpha) - math.sin(beta)
        p_sq = -2 + d * d + 2 * math.cos(alpha - beta) - 2 * d * (math.sin(alpha) - math.sin(beta))
        if p_sq < 0:
            return None
        p = math.sqrt(p_sq)
        t = mod2pi(alpha - math.atan2(math.cos(beta) - math.cos(alpha), tmp0) + math.atan2(2, p))
        q = mod2pi(beta - math.atan2(math.cos(beta) - math.cos(alpha), tmp0) + math.atan2(2, p))
        return [t, p, q]

    elif path_type == DubinsPathType.RSR:
        tmp0 = d - math.sin(alpha) + math.sin(beta)
        tmp1 = math.atan2(math.cos(alpha) - math.cos(beta), tmp0)
        t = mod2pi(alpha - tmp1 + math.pi / 2)
        p_sq = 2 + d * d - 2 * math.cos(alpha - beta) - 2 * d * (math.sin(alpha) - math.sin(beta))
        if p_sq < 0:
            return None
        p = math.sqrt(p_sq)
        q = mod2pi(-beta + tmp1 + math.pi / 2)
        return [t, p, q]

    elif path_type == DubinsPathType.RLR:
        tmp0 = (6 - d * d + 2 * math.cos(alpha - beta) + 2 * d * (math.sin(alpha) - math.sin(beta))) / 8
        if abs(tmp0) > 1:
            return None
        p = mod2pi(2 * math.pi - math.acos(tmp0))
        t = mod2pi(alpha - math.atan2(math.cos(alpha) - math.cos(beta), d - math.sin(alpha) + math.sin(beta)) + p / 2)
        q = mod2pi(alpha - beta - t + p)
        return [t, p, q]

    elif path_type == DubinsPathType.LRL:
        tmp0 = (6 - d * d + 2 * math.cos(alpha - beta) - 2 * d * (math.sin(alpha) - math.sin(beta))) / 8
        if abs(tmp0) > 1:
            return None
        p = mod2pi(2 * math.pi - math.acos(tmp0))
        t = mod2pi(-alpha + math.atan2(math.cos(alpha) - math.cos(beta), d + math.sin(alpha) - math.sin(beta)) + p / 2)
        q = mod2pi(beta - alpha - t + p)
        return [t, p, q]

    return None
