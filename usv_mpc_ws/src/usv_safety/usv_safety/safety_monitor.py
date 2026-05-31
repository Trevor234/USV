"""Safety monitor for USV autonomous operation.

Monitors communication health, solver status, geofence, and system state.
Triggers failsafe actions when anomalies are detected.
"""

import math
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class SafetyLevel(IntEnum):
    NOMINAL = 0       # All systems nominal
    WARNING = 1       # Degraded but recoverable
    CAUTION = 2       # Action required — reduce speed, hold position
    FAILSAFE = 3      # Immediate RTL or HOLD


@dataclass
class SafetyConfig:
    """Configurable safety thresholds."""
    max_solver_failures: int = 5
    max_odom_timeout_s: float = 1.0
    max_path_timeout_s: float = 5.0
    max_solve_time_ms: float = 500.0
    geofence_radius_m: float = 200.0
    geofence_center: tuple = (0.0, 0.0)
    max_crosstrack_error_m: float = 10.0
    low_battery_v: float = 10.5
    critical_battery_v: float = 10.0
    max_speed_mps: float = 3.0


@dataclass
class SafetyState:
    """Current safety assessment."""
    level: SafetyLevel = SafetyLevel.NOMINAL
    active_flags: list = field(default_factory=list)
    recommended_action: str = ""
    timestamp: float = field(default_factory=time.time)


class SafetyMonitor:
    """Monitors system health and triggers failsafe when needed."""

    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._last_odom_time: float = 0.0
        self._last_path_time: float = 0.0
        self._solver_fail_count: int = 0
        self._last_solve_time_ms: float = 0.0
        self._current_state: SafetyState = SafetyState()

    def update_odom(self, x: float, y: float, psi: float, speed: float,
                    voltage: float = 12.0, timestamp: Optional[float] = None):
        """Update with latest odometry."""
        ts = timestamp or time.time()
        self._last_odom_time = ts

        flags = []
        level = SafetyLevel.NOMINAL

        # Geofence check
        dist = math.hypot(x - self.config.geofence_center[0],
                          y - self.config.geofence_center[1])
        if dist > self.config.geofence_radius_m * 0.9:
            flags.append(f"Approaching geofence boundary: {dist:.1f}m")
            level = SafetyLevel.WARNING
        if dist > self.config.geofence_radius_m:
            flags.append(f"GEOFENCE VIOLATION: {dist:.1f}m")
            level = SafetyLevel.FAILSAFE

        # Speed limit
        if speed > self.config.max_speed_mps:
            flags.append(f"Speed limit exceeded: {speed:.2f} m/s")
            level = max(level, SafetyLevel.WARNING)

        # Battery check
        if voltage < self.config.critical_battery_v:
            flags.append(f"CRITICAL battery: {voltage:.1f}V")
            level = SafetyLevel.FAILSAFE
        elif voltage < self.config.low_battery_v:
            flags.append(f"Low battery: {voltage:.1f}V")
            level = max(level, SafetyLevel.WARNING)

        self._current_state = SafetyState(
            level=level,
            active_flags=flags,
            recommended_action=self._get_action(level),
            timestamp=ts,
        )

    def update_solver(self, success: bool, solve_time_ms: float,
                      timestamp: Optional[float] = None):
        """Update with solver status."""
        ts = timestamp or time.time()
        self._last_solve_time_ms = solve_time_ms

        if success:
            self._solver_fail_count = 0
        else:
            self._solver_fail_count += 1

        flags = list(self._current_state.active_flags)
        level = self._current_state.level

        if self._solver_fail_count >= self.config.max_solver_failures:
            flags.append(f"Solver failed {self._solver_fail_count} consecutive times")
            level = max(level, SafetyLevel.FAILSAFE)
        elif self._solver_fail_count >= 3:
            flags.append(f"Solver failures: {self._solver_fail_count}")
            level = max(level, SafetyLevel.WARNING)

        if solve_time_ms > self.config.max_solve_time_ms:
            flags.append(f"Slow solve: {solve_time_ms:.0f}ms")
            level = max(level, SafetyLevel.WARNING)

        self._current_state = SafetyState(
            level=level,
            active_flags=flags,
            recommended_action=self._get_action(level),
            timestamp=ts,
        )

    def update_path(self, received: bool, timestamp: Optional[float] = None):
        """Update with path planner status."""
        ts = timestamp or time.time()
        flags = list(self._current_state.active_flags)
        level = self._current_state.level

        if received:
            self._last_path_time = ts
        else:
            dt = ts - self._last_path_time
            if dt > self.config.max_path_timeout_s:
                flags.append(f"No path update for {dt:.1f}s")
                level = max(level, SafetyLevel.FAILSAFE)

        self._current_state = SafetyState(
            level=level,
            active_flags=flags,
            recommended_action=self._get_action(level),
            timestamp=ts,
        )

    def check_odom_timeout(self, timestamp: Optional[float] = None) -> bool:
        """Returns True if odometry has timed out."""
        ts = timestamp or time.time()
        return (ts - self._last_odom_time) > self.config.max_odom_timeout_s

    @property
    def state(self) -> SafetyState:
        return self._current_state

    @property
    def ok(self) -> bool:
        return self._current_state.level.value < SafetyLevel.FAILSAFE.value

    @property
    def warning_active(self) -> bool:
        return self._current_state.level == SafetyLevel.WARNING

    @property
    def failsafe_active(self) -> bool:
        return self._current_state.level == SafetyLevel.FAILSAFE

    @staticmethod
    def _get_action(level: SafetyLevel) -> str:
        if level == SafetyLevel.FAILSAFE:
            return "RTL"
        elif level == SafetyLevel.CAUTION:
            return "HOLD"
        elif level == SafetyLevel.WARNING:
            return "REDUCE_SPEED"
        return "NONE"

    def reset(self):
        self._solver_fail_count = 0
        self._current_state = SafetyState()
