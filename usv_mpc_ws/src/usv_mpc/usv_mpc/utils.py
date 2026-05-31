"""Coordinate transforms and math utilities for USV MPC."""

import math
import numpy as np


def normalize_angle(angle: float) -> float:
    """将角度归一化到 [-pi, pi] 范围内。"""
    return math.atan2(math.sin(angle), math.cos(angle))


def quaternion_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    """
    将四元数 (x,y,z,w) 从 ENU (东北天) 坐标系转换为 NED (北东地) 坐标系下的偏航角 (yaw/航向角)。
    返回值单位为弧度 [rad]。
    """
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


def body_to_ned(u: float, v: float, psi: float) -> tuple[float, float]:
    """
    将机体坐标系 (Body-frame) 下的速度转换为 NED (北东地) 坐标系下的速度。
    :param u: 机体纵向速度 (前进速度)
    :param v: 机体横向速度 (侧向速度)
    :param psi: 当前偏航角 (航向角)
    :return: (vn, ve) 分别对应北向速度和东向速度
    """
    vn = u * math.cos(psi) - v * math.sin(psi)
    ve = u * math.sin(psi) + v * math.cos(psi)
    return vn, ve


def ned_to_body(vn: float, ve: float, psi: float) -> tuple[float, float]:
    """
    将 NED (北东地) 坐标系下的速度转换为机体坐标系 (Body-frame) 下的速度。
    :param vn: 北向速度
    :param ve: 东向速度
    :param psi: 当前偏航角 (航向角)
    :return: (u, v) 分别对应机体纵向速度和横向速度
    """
    u = vn * math.cos(psi) + ve * math.sin(psi)
    v = -vn * math.sin(psi) + ve * math.cos(psi)
    return u, v


def cross_track_error(x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """
    计算从当前点 (x,y) 到线段 (x1,y1)-(x2,y2) 的有向横向跟踪误差 (Cross-track error)。
    误差的符号表示当前点在线段的左侧还是右侧。
    """
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    return ((x - x1) * dy - (y - y1) * dx) / math.hypot(dx, dy)


def along_track_distance(x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """
    计算当前点 (x,y) 投影到线段 (x1,y1)-(x2,y2) 上后，距离起点 (x1,y1) 的纵向距离。
    返回值被限制在 [0, 线段长度] 之间。
    """
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return 0.0
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / seg_len_sq))
    return t * math.sqrt(seg_len_sq)


def calc_curvature(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """
    使用有限差分法计算由 (x,y) 离散点组成的路径在各点处的曲率 (Curvature)。
    """
    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)
    curvature = (dx * ddy - dy * ddx) / (dx**2 + dy**2 + 1e-8) ** 1.5
    return curvature


def arc_length_parameterize(path_x: np.ndarray, path_y: np.ndarray) -> np.ndarray:
    """
    计算路径的累积弧长 (Cumulative arc length)。
    将由离散点组成的路径按照各点之间的直线距离进行积分，得到每个点到起点的弧长。
    """
    s = np.zeros(len(path_x))
    for i in range(1, len(path_x)):
        s[i] = s[i - 1] + math.hypot(path_x[i] - path_x[i - 1], path_y[i] - path_y[i - 1])
    return s
