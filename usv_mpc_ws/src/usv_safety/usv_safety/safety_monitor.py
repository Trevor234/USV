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
    mpc_status_timeout_s: float = 1.0


@dataclass
class SafetyState:
    """Current safety assessment."""
    level: SafetyLevel = SafetyLevel.NOMINAL
    active_flags: list = field(default_factory=list)
    recommended_action: str = ""
    timestamp: float = field(default_factory=time.time)


class SafetyMonitor:
    """Monitors system health and triggers failsafe when needed.

    Each update method owns one monitoring domain (odom/geofence/battery,
    solver, path, or odometry watchdog). Updating one domain must not clear
    active flags from another domain; otherwise a new odom sample could mask a
    solver/path failsafe. `_replace_flags` enforces that separation.
    """

    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._last_odom_time: float = 0.0
        self._last_path_time: float = 0.0
        self._last_mpc_status_time: float = 0.0
        self._solver_fail_count: int = 0
        self._last_solve_time_ms: float = 0.0
        self._current_state: SafetyState = SafetyState()

    def _replace_flags(self, prefixes: tuple, new_flags: list, timestamp: float):
        """Replace one monitoring domain's flags without clearing others."""
        flags = [
            flag for flag in self._current_state.active_flags
            if not any(flag.startswith(prefix) for prefix in prefixes)
        ]
        flags.extend(new_flags)
        level = self._level_from_flags(flags)
        self._current_state = SafetyState(
            level=level,
            active_flags=flags,
            recommended_action=self._get_action(level),
            timestamp=timestamp,
        )

    @staticmethod
    def _level_from_flags(flags: list) -> SafetyLevel:
        """Derive aggregate severity from active flag messages."""
        level = SafetyLevel.NOMINAL
        for flag in flags:
            if flag.startswith((
                "GEOFENCE VIOLATION",
                "CRITICAL battery",
                "Solver failed",
                "No path update",
                "No odometry received",
                "Odometry timeout",
                "No MPC status",
                "MPC status timeout",
            )):
                return SafetyLevel.FAILSAFE
            if flag.startswith((
                "Approaching geofence boundary",
                "Speed limit exceeded",
                "Low battery",
                "Solver failures",
                "Slow solve",
                "No battery telemetry",
            )):
                level = max(level, SafetyLevel.WARNING)
        return level

    def set_odom_watchdog(self, flag: Optional[str], timestamp: Optional[float] = None):
        """Set or clear the odometry watchdog flag."""
        self._replace_flags(
            ("No odometry received", "Odometry timeout"),
            [flag] if flag else [],
            timestamp or time.monotonic(),
        )

    def mark_mpc_status(self, timestamp: Optional[float] = None):
        """Record arrival time of /mpc/status (freshness watchdog seed)."""
        self._last_mpc_status_time = timestamp or time.monotonic()

    def set_mpc_status_watchdog(self, flag: Optional[str],
                                timestamp: Optional[float] = None):
        """Set or clear the /mpc/status freshness watchdog flag."""
        self._replace_flags(
            ("No MPC status", "MPC status timeout"),
            [flag] if flag else [],
            timestamp or time.monotonic(),
        )

    def set_battery_watchdog(self, flag: Optional[str],
                             timestamp: Optional[float] = None):
        """Set or clear the battery-telemetry watchdog flag (WARNING level).

        电池遥测断流意味着低电量 failsafe 变盲, 但缺失遥测不应触发 RTL
        (意外 RTL 本身是危险), 因此该域固定为 WARNING。
        """
        self._replace_flags(
            ("No battery telemetry",),
            [flag] if flag else [],
            timestamp or time.monotonic(),
        )

    def check_mpc_status_timeout(self, timestamp: Optional[float] = None) -> bool:
        """Returns True if /mpc/status has gone stale."""
        ts = timestamp or time.monotonic()
        return (ts - self._last_mpc_status_time) > self.config.mpc_status_timeout_s

    def set_solver_fail_count(self, fail_count: int):
        """Synchronize solver failure counter without adding a new failure."""
        self._solver_fail_count = max(0, int(fail_count))

    def clear_solver_flags(self, timestamp: Optional[float] = None):
        """Clear stale solver warning/failsafe flags."""
        self._replace_flags(
            ("Solver failed", "Solver failures", "Slow solve"),
            [],
            timestamp or time.monotonic(),
        )

    def update_odom(self, x: float, y: float, psi: float, speed: float,
                    timestamp: Optional[float] = None):
        """Update geofence and speed checks from latest odometry.

        MUST only be called from the real odom callback: the timestamp seeds
        the odom watchdog. Battery voltage has its own domain in
        update_battery(); feeding it through here would refresh the odom
        watchdog from the battery topic and blind the odom failsafe.
        """
        ts = timestamp or time.monotonic()
        self._last_odom_time = ts

        flags = []

        dist = math.hypot(x - self.config.geofence_center[0],
                          y - self.config.geofence_center[1])
        if dist > self.config.geofence_radius_m:
            flags.append(f"GEOFENCE VIOLATION: {dist:.1f}m")
        elif dist > self.config.geofence_radius_m * 0.9:
            flags.append(f"Approaching geofence boundary: {dist:.1f}m")

        if speed > self.config.max_speed_mps:
            flags.append(f"Speed limit exceeded: {speed:.2f} m/s")

        self._replace_flags(
            (
                "Approaching geofence boundary",
                "GEOFENCE VIOLATION",
                "Speed limit exceeded",
            ),
            flags,
            ts,
        )

    def update_battery(self, voltage: float,
                       timestamp: Optional[float] = None):
        """Update battery checks. Owns the Low/CRITICAL battery flag domain."""
        ts = timestamp or time.monotonic()

        flags = []
        if voltage < self.config.critical_battery_v:
            flags.append(f"CRITICAL battery: {voltage:.1f}V")
        elif voltage < self.config.low_battery_v:
            flags.append(f"Low battery: {voltage:.1f}V")

        self._replace_flags(("Low battery", "CRITICAL battery"), flags, ts)

    def update_solver(self, success: bool, solve_time_ms: float,
                      timestamp: Optional[float] = None):
        """Update with solver status."""
        ts = timestamp or time.monotonic()
        self._last_solve_time_ms = solve_time_ms

        if success:
            self._solver_fail_count = 0
        else:
            self._solver_fail_count += 1

        flags = []
        if self._solver_fail_count >= self.config.max_solver_failures:
            flags.append(f"Solver failed {self._solver_fail_count} consecutive times")
        elif self._solver_fail_count >= 3:
            flags.append(f"Solver failures: {self._solver_fail_count}")

        if solve_time_ms > self.config.max_solve_time_ms:
            flags.append(f"Slow solve: {solve_time_ms:.0f}ms")

        self._replace_flags(
            ("Solver failed", "Solver failures", "Slow solve"),
            flags,
            ts,
        )

    def update_path(self, received: bool, timestamp: Optional[float] = None):
        """Update with path planner status."""
        ts = timestamp or time.monotonic()

        if received:
            self._last_path_time = ts
            self._replace_flags(("No path update",), [], ts)
        elif self._last_path_time > 0.0:
            # Only watch for timeouts once a path has actually been received;
            # pre-mission absence of a path must not trip a failsafe.
            dt = ts - self._last_path_time
            flag = f"No path update for {dt:.1f}s" if dt > self.config.max_path_timeout_s else None
            self._replace_flags(("No path update",), [flag] if flag else [], ts)

    def check_odom_timeout(self, timestamp: Optional[float] = None) -> bool:
        """Returns True if odometry has timed out."""
        ts = timestamp or time.monotonic()
        return (ts - self._last_odom_time) > self.config.max_odom_timeout_s

    @property
    def state(self) -> SafetyState:
        """Return a defensive snapshot of the current safety state."""
        return SafetyState(
            level=self._current_state.level,
            active_flags=list(self._current_state.active_flags),
            recommended_action=self._current_state.recommended_action,
            timestamp=self._current_state.timestamp,
        )

    @property
    def level(self) -> SafetyLevel:
        return self._current_state.level

    @property
    def active_flags(self) -> tuple[str, ...]:
        return tuple(self._current_state.active_flags)

    @property
    def recommended_action(self) -> str:
        return self._current_state.recommended_action

    @property
    def solver_fail_count(self) -> int:
        return self._solver_fail_count

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
