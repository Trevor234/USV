"""Coordinate transforms and math utilities for USV MPC.

Runtime frames follow ROS conventions: planar position/yaw are in a local
`map` frame (ENU-style x/y plane), while body velocities are in `base_link`.
Some function names keep legacy `ned` wording for compatibility; their
semantics are local-map/body-frame rotations used by the current ROS graph.
"""

import math
import numpy as np


def normalize_angle(angle: float) -> float:
    """将角度归一化到 [-pi, pi] 范围内。"""
    return math.atan2(math.sin(angle), math.cos(angle))


def quaternion_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    """Extract ROS yaw from quaternion (x, y, z, w), in radians.

    This does not perform a frame conversion; it returns the yaw angle used
    with the local `map` frame and `base_link` convention in this project.
    """
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


def body_to_ned(u: float, v: float, psi: float) -> tuple[float, float]:
    """Legacy name: rotate body-frame velocity into the local map frame.

    :param u: body-frame surge velocity
    :param v: body-frame sway velocity
    :param psi: yaw angle in the local map frame
    :return: local-frame velocity components (vx, vy)
    """
    vx = u * math.cos(psi) - v * math.sin(psi)
    vy = u * math.sin(psi) + v * math.cos(psi)
    return vx, vy


def ned_to_body(vn: float, ve: float, psi: float) -> tuple[float, float]:
    """Legacy name: rotate local map-frame velocity into body frame.

    :param vn: local x velocity component (legacy parameter name)
    :param ve: local y velocity component (legacy parameter name)
    :param psi: yaw angle in the local map frame
    :return: body-frame velocity components (u, v)
    """
    u = vn * math.cos(psi) + ve * math.sin(psi)
    v = -vn * math.sin(psi) + ve * math.cos(psi)
    return u, v


def cross_track_error(x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """计算从当前点 (x,y) 到线段 (x1,y1)-(x2,y2) 的有向横向跟踪误差。"""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    return ((x - x1) * dy - (y - y1) * dx) / math.hypot(dx, dy)


def along_track_distance(x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """计算当前点在线段上的投影距离起点的纵向距离，限制在段长范围内。"""
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return 0.0
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / seg_len_sq))
    return t * math.sqrt(seg_len_sq)


def calc_curvature(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """使用有限差分法计算由 (x,y) 离散点组成的路径曲率。"""
    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)
    curvature = (dx * ddy - dy * ddx) / (dx**2 + dy**2 + 1e-8) ** 1.5
    return curvature


def arc_length_parameterize(path_x: np.ndarray, path_y: np.ndarray) -> np.ndarray:
    """计算离散路径的累积弧长。"""
    s = np.zeros(len(path_x))
    for i in range(1, len(path_x)):
        s[i] = s[i - 1] + math.hypot(path_x[i] - path_x[i - 1], path_y[i] - path_y[i - 1])
    return s


def parse_profile_stamp(layout) -> tuple[int, int] | None:
    """Parse profile stamp metadata from Float64MultiArray.layout-like objects."""
    sec = None
    nanosec = None
    for dim in layout.dim:
        label = str(dim.label)
        if label.startswith("stamp_sec:"):
            try:
                sec = int(label.split(":", 1)[1])
            except ValueError:
                return None
        elif label.startswith("stamp_nanosec:"):
            try:
                nanosec = int(label.split(":", 1)[1])
            except ValueError:
                return None
    if sec is None or nanosec is None:
        return None
    return sec, nanosec


def profile_sync_state(path_len: int, profile_len: int | None,
                       path_stamp, profile_stamp) -> tuple[bool, str]:
    """Return whether path/profile are synchronized and the reason string."""
    if profile_len is None:
        return False, "no_profile"
    if path_len < 2:
        return False, "path_too_short"
    if profile_len != path_len:
        return False, "length_mismatch"
    if profile_stamp is None:
        return True, "legacy_no_profile_stamp"
    if path_stamp is None:
        return False, "missing_path_stamp"
    if profile_stamp != path_stamp:
        return False, "stamp_mismatch"
    return True, "stamp_match"


def sample_path_profile_at_time(path, times, vs, rs, tk, j_hint):
    """Interpolate (path, profile) at time tk.

    Returns (x, y, psi, v, r, j), where j is the segment index useful as the
    next search hint.
    """
    last = len(path) - 1
    j = j_hint
    while j < last and times[j + 1] < tk:
        j += 1
    if j >= last:
        p = path[last]
        return p[0], p[1], p[2], vs[last], rs[last], last
    t_seg = times[j + 1] - times[j]
    a = max(0.0, min(1.0, (tk - times[j]) / t_seg)) if t_seg > 1e-9 else 0.0
    x = path[j][0] + a * (path[j + 1][0] - path[j][0])
    y = path[j][1] + a * (path[j + 1][1] - path[j][1])
    dpsi = normalize_angle(path[j + 1][2] - path[j][2])
    psi = normalize_angle(path[j][2] + a * dpsi)
    v = vs[j] + a * (vs[j + 1] - vs[j])
    r = rs[j] + a * (rs[j + 1] - rs[j])
    return x, y, psi, v, r, j
