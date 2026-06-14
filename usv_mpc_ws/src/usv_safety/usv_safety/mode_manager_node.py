"""
Mode Manager ROS 2 Node.

Manages flight mode transitions (MANUAL ↔ GUIDED ↔ HOLD ↔ RTL),
arming/disarming, and safety monitoring integration.
"""

import json
import math
import time
from enum import Enum

import rclpy
from mavros_msgs.msg import State as MavrosState
from mavros_msgs.srv import CommandBool, SetMode
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState
from std_msgs.msg import String

from .safety_monitor import SafetyMonitor, SafetyConfig, SafetyLevel


class USVMode(Enum):
    MANUAL = "MANUAL"
    GUIDED = "GUIDED"
    HOLD = "HOLD"
    RTL = "RTL"
    AUTO = "AUTO"


class ModeManagerNode(Node):
    """Handles mode switching and safety failsafe for the USV."""

    def __init__(self):
        super().__init__("mode_manager_node")

        self._declare_parameters()
        self._load_config()

        self._safety = SafetyMonitor(self._safety_config)
        self._current_mavros_mode: str = "MANUAL"
        self._armed: bool = False
        self._mpc_ok: bool = True  # Default to True until we receive an actual error
        self._mpc_fail_count: int = 0
        self._mpc_solve_time_ms: float = 0.0
        self._mpc_hold: bool = False
        self._mpc_state: str = "UNKNOWN"  # ACTIVE / HOLD / STANDBY / UNKNOWN
        self._mpc_standby_reason: str = ""
        self._last_mpc_status_time: float = 0.0
        self._x: float = 0.0
        self._y: float = 0.0
        self._speed: float = 0.0
        # Safe sentinel: missing battery telemetry must NOT trip the low/critical
        # battery failsafe (a surprise RTL mid-mission is itself a hazard).
        self._voltage: float = 99.0
        self._battery_received: bool = False
        self._odom_received: bool = False
        self._last_odom_rx: float = 0.0
        self._path_ever_received: bool = False

        # Subscribers
        state_topic = self.get_parameter("state_topic").value
        self._state_sub = self.create_subscription(
            MavrosState, state_topic, self._state_callback, 10
        )
        mpc_status_topic = self.get_parameter("mpc_status_topic").value
        self._mpc_status_sub = self.create_subscription(
            String, mpc_status_topic, self._mpc_status_callback, 10
        )
        # Live telemetry feeds for the safety monitor (geofence / speed / battery
        # / path watchdog). These were previously hard-coded, leaving every check
        # inert; now they are driven by real data.
        odom_topic = self.get_parameter("odom_topic").value
        self._odom_sub = self.create_subscription(
            Odometry, odom_topic, self._odom_callback, qos_profile_sensor_data
        )
        path_topic = self.get_parameter("path_topic").value
        self._path_sub = self.create_subscription(
            NavPath, path_topic, self._path_callback, 10
        )
        battery_topic = self.get_parameter("battery_topic").value
        self._battery_sub = None
        if battery_topic:
            self._battery_sub = self.create_subscription(
                BatteryState, battery_topic, self._battery_callback, qos_profile_sensor_data
            )

        # Service clients
        set_mode_service = self.get_parameter("set_mode_service").value
        arming_service = self.get_parameter("arming_service").value
        self._set_mode_cli = self.create_client(SetMode, set_mode_service)
        self._cmd_arming_cli = self.create_client(CommandBool, arming_service)

        # Timer
        self._timer = self.create_timer(0.5, self._monitor_loop)

        self.get_logger().info("Mode Manager started | safety monitoring active")

    def _declare_parameters(self):
        self.declare_parameter("auto_arm", False)
        self.declare_parameter("auto_mode_switch", True)
        self.declare_parameter("geofence_radius", 200.0)
        self.declare_parameter("geofence_center_x", 0.0)
        self.declare_parameter("geofence_center_y", 0.0)
        self.declare_parameter("low_battery_v", 10.5)
        self.declare_parameter("critical_battery_v", 10.0)
        self.declare_parameter("max_solver_failures", 5)
        self.declare_parameter("odom_timeout_s", 1.0)
        self.declare_parameter("max_path_timeout_s", 5.0)
        self.declare_parameter("max_speed_mps", 3.0)
        self.declare_parameter("state_topic", "/mavros/state")
        self.declare_parameter("mpc_status_topic", "/mpc/status")
        self.declare_parameter("path_topic", "/path/reference")
        self.declare_parameter("odom_topic", "/mavros/local_position/odom")
        self.declare_parameter("battery_topic", "/mavros/battery")
        self.declare_parameter("set_mode_service", "/mavros/set_mode")
        self.declare_parameter("arming_service", "/mavros/cmd/arming")

    def _load_config(self):
        self._safety_config = SafetyConfig(
            geofence_radius_m=self.get_parameter("geofence_radius").value,
            geofence_center=(
                self.get_parameter("geofence_center_x").value,
                self.get_parameter("geofence_center_y").value,
            ),
            low_battery_v=self.get_parameter("low_battery_v").value,
            critical_battery_v=self.get_parameter("critical_battery_v").value,
            max_solver_failures=self.get_parameter("max_solver_failures").value,
            max_odom_timeout_s=self.get_parameter("odom_timeout_s").value,
            max_path_timeout_s=self.get_parameter("max_path_timeout_s").value,
            max_speed_mps=self.get_parameter("max_speed_mps").value,
        )

    def _state_callback(self, msg: MavrosState):
        self._current_mavros_mode = msg.mode
        self._armed = msg.armed

    def _mpc_status_callback(self, msg: String):
        """Parse structured status from mpc_node.

        Expected JSON payload: {"state": str, "success": bool, "fail_count": int,
        "solve_time_ms": float, "hold": bool, "scheme": str,
        "error": str (optional), "standby_reason": str (optional)}.
        Falls back to substring match for backwards compatibility if JSON
        parsing fails.
        """
        try:
            payload = json.loads(msg.data)
            self._mpc_ok = bool(payload.get("success", False))
            self._mpc_fail_count = int(payload.get("fail_count", 0))
            self._mpc_solve_time_ms = float(payload.get("solve_time_ms", 0.0))
            self._mpc_hold = bool(payload.get("hold", False))
            self._mpc_state = str(payload.get("state", "UNKNOWN"))
            self._mpc_standby_reason = str(payload.get("standby_reason", ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            # Legacy: any "error" substring marks failure
            self._mpc_ok = "error" not in msg.data.lower()
            self._mpc_hold = False
            self._mpc_state = "UNKNOWN"
            self._mpc_standby_reason = ""
        self._last_mpc_status_time = time.time()

    def _odom_callback(self, msg: Odometry):
        """Feed live pose/speed into geofence and speed-limit checks."""
        self._x = msg.pose.pose.position.x
        self._y = msg.pose.pose.position.y
        self._speed = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)
        self._odom_received = True
        self._last_odom_rx = time.time()
        self._safety.update_odom(
            self._x, self._y, 0.0, self._speed, self._voltage, self._last_odom_rx
        )

    def _battery_callback(self, msg: BatteryState):
        """Cache battery voltage; ignore NaN / invalid readings."""
        v = msg.voltage
        if not math.isnan(v) and v > 0.0:
            self._voltage = float(v)
            self._battery_received = True
            if self._odom_received:
                self._safety.update_odom(
                    self._x, self._y, 0.0, self._speed, self._voltage, time.time()
                )

    def _path_callback(self, msg: NavPath):
        """Mark a fresh reference path so the path watchdog can detect stalls."""
        self._path_ever_received = True
        self._safety.update_path(received=True, timestamp=time.time())

    def _monitor_loop(self):
        """Periodic safety monitoring and mode management."""
        now = time.time()

        # Odometry watchdog: update_odom() is called ONLY from the real odom
        # callback so check_odom_timeout() reflects sensor freshness. Do not
        # refresh it here, or this watchdog would be self-resetting.
        if not self._armed:
            # Before arming, MAVROS/EKF may still be starting up. Do not switch
            # modes just because odometry is not available yet; start enforcing
            # the watchdog once the vehicle is armed.
            self._safety.set_odom_watchdog(None, now)
        elif not self._odom_received:
            self._safety.set_odom_watchdog("No odometry received", now)
        elif self._safety.check_odom_timeout(now):
            dt = now - self._last_odom_rx
            self._safety.set_odom_watchdog(f"Odometry timeout: {dt:.1f}s", now)
        else:
            self._safety.set_odom_watchdog(None, now)

        # MPC solver health is only meaningful when MPC is ACTIVE or HOLD.
        # STANDBY/UNKNOWN means MPC isn't even trying to solve (e.g. wrong
        # FCU mode, disarmed, no path) — counting those as "solver failures"
        # would falsely trip failsafe at ~2 Hz. In those states, mirror the
        # MPC's reported fail_count (always 0 in STANDBY) and skip the
        # incremental update.
        if self._mpc_state in ("ACTIVE", "HOLD"):
            if self._mpc_fail_count > self._safety.solver_fail_count:
                self._safety.set_solver_fail_count(self._mpc_fail_count)
            self._safety.update_solver(
                self._mpc_ok, self._mpc_solve_time_ms, now
            )
        else:
            # STANDBY / UNKNOWN: keep safety in sync but do not accumulate
            # solver failures while MPC is intentionally not solving.
            self._safety.set_solver_fail_count(self._mpc_fail_count)
            self._safety.clear_solver_flags(now)

        # Path-update watchdog. Armed only after the first path has been seen so
        # that pre-mission absence of a path does not trip a failsafe.
        if self._path_ever_received:
            self._safety.update_path(received=False, timestamp=now)

        # Check for failsafe trigger
        if self._safety.failsafe_active:
            if self._current_mavros_mode != "RTL":
                flags = self._safety.active_flags
                self.get_logger().error(
                    f"FAILSAFE triggered! Flags: {flags}"
                )
                self._switch_mode("RTL")
            return

        # Auto mode switching
        # 触发条件:armed 且不在 GUIDED,且 MPC 有意愿解算——
        #   (1) 当前正在成功解算(legacy 行为),或
        #   (2) MPC 因 wrong_mode 进入 STANDBY(没切到 GUIDED 之前永远不会
        #       success,需要由 mode_manager 主动切过去打破死锁)
        auto_switch = self.get_parameter("auto_mode_switch").value
        if auto_switch and self._armed and self._current_mavros_mode != "GUIDED":
            needs_guided = (
                self._mpc_ok
                or (self._mpc_state == "STANDBY"
                    and self._mpc_standby_reason.startswith("wrong_mode"))
            )
            if needs_guided:
                self._switch_mode("GUIDED")

        # Log warnings
        flags = self._safety.active_flags
        if self._safety.warning_active and flags:
            for flag in flags:
                self.get_logger().warn(f"Safety: {flag}")

    def request_arm(self, arm: bool = True) -> bool:
        """Request arming/disarming."""
        if not self._cmd_arming_cli.service_is_ready():
            self.get_logger().error("Arming service not ready")
            return False

        req = CommandBool.Request()
        req.value = arm
        future = self._cmd_arming_cli.call_async(req)
        # Spin until complete (with timeout handled by the caller)
        return True

    def _switch_mode(self, mode: str) -> bool:
        """Switch to a flight mode."""
        if self._current_mavros_mode == mode:
            return True

        if not self._set_mode_cli.service_is_ready():
            self.get_logger().error("SetMode service not ready")
            return False

        req = SetMode.Request()
        req.custom_mode = mode
        future = self._set_mode_cli.call_async(req)
        self.get_logger().info(f"Switching mode: {self._current_mavros_mode} → {mode}")
        return True

    def switch_to_guided(self) -> bool:
        return self._switch_mode("GUIDED")

    def switch_to_manual(self) -> bool:
        return self._switch_mode("MANUAL")

    def switch_to_rtl(self) -> bool:
        return self._switch_mode("RTL")

    def switch_to_hold(self) -> bool:
        return self._switch_mode("HOLD")


def main(args=None):
    rclpy.init(args=args)
    node = ModeManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
