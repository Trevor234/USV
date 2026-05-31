"""无人船任务航点管理。

加载、存储并管理一组有序航点。
"""

import math
import os
from typing import List, Tuple


class Waypoint:
    """包含位置和到达半径的单个航点。"""

    def __init__(self, x: float, y: float, radius: float = 2.0,
                 heading: float = 0.0, stay_time: float = 0.0):
        self.x = x
        self.y = y
        self.radius = radius
        self.heading = heading  # 航点处期望航向角（rad）
        self.stay_time = stay_time  # 到达后停留时间（秒）

    def __repr__(self):
        return f"Waypoint(x={self.x:.1f}, y={self.y:.1f}, r={self.radius:.1f})"


class WaypointManager:
    """管理由有序航点组成的任务。"""

    def __init__(self):
        self._waypoints: List[Waypoint] = []
        self._current_idx: int = 0
        self._mission_complete: bool = False

    def load_from_yaml(self, config: dict):
        """从 YAML 配置字典加载航点。"""
        self._waypoints.clear()
        for wp_data in config.get("waypoints", []):
            self._waypoints.append(Waypoint(
                x=wp_data.get("x", 0.0),
                y=wp_data.get("y", 0.0),
                radius=wp_data.get("radius", 2.0),
                heading=math.radians(wp_data.get("heading_deg", 0.0)),
                stay_time=wp_data.get("stay_time", 0.0),
            ))
        self._current_idx = 0
        self._mission_complete = False

    def add_waypoint(self, wp: Waypoint):
        self._waypoints.append(wp)

    def clear(self):
        self._waypoints.clear()
        self._current_idx = 0
        self._mission_complete = False

    @property
    def waypoints(self) -> List[Waypoint]:
        return self._waypoints

    @property
    def current_index(self) -> int:
        return self._current_idx

    @property
    def mission_complete(self) -> bool:
        return self._mission_complete

    @property
    def current_waypoint(self) -> Waypoint:
        if self._mission_complete:
            return self._waypoints[-1]
        return self._waypoints[self._current_idx]

    def update_progress(self, x: float, y: float) -> bool:
        """检查是否到达当前航点，若已到达则推进到下一个航点。

        如果到达当前航点则返回 True。
        """
        if self._mission_complete or not self._waypoints:
            return False

        wp = self._waypoints[self._current_idx]
        dist = math.hypot(x - wp.x, y - wp.y)
        if dist < wp.radius:
            self._current_idx += 1
            if self._current_idx >= len(self._waypoints):
                self._mission_complete = True
            return True
        return False

    def get_active_waypoints(self, lookahead: int = 3) -> List[Waypoint]:
        """返回包含当前航点在内的后续航点。"""
        if self._mission_complete:
            return self._waypoints[-1:]
        end = min(self._current_idx + lookahead, len(self._waypoints))
        return self._waypoints[self._current_idx:end]
