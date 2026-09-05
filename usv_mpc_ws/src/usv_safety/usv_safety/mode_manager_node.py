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
from rclpy.executors import ExternalShutdownException
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
        # 每条 /mpc/status 递增; 监控循环据此只消费"新"状态
        self._mpc_status_seq: int = 0
        self._last_status_seq_used: int = -1
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
        self._last_battery_rx: float = 0.0
        # 人工接管检测: FCU 模式发生变化的时刻; 冷却期内 auto_mode_switch
        # 不自动拉回, 给操作手留出控制窗口
        self._prev_mavros_mode: str = ""
        self._last_mode_change: float = 0.0

        self._battery_timeout_s: float = float(
            self.get_parameter("battery_timeout_s").value)
        self._takeover_cooldown_s: float = float(
            self.get_parameter("manual_takeover_cooldown_s").value)
        self._max_rtl_retries: int = int(
            self.get_parameter("max_rtl_retries").value)
        self._rtl_attempts: int = 0

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
        self.declare_parameter("mpc_status_timeout_s", 1.0)
        # 电池遥测看门狗: 话题断流仅 WARNING (低电量检测失效需人工知晓),
        # 不触发 RTL —— 缺失遥测导致的意外 RTL 本身就是危险。
        self.declare_parameter("battery_timeout_s", 10.0)
        # 人工接管冷却: 检测到 FCU 模式被外部改变后, 该时长内 auto_mode_switch
        # 不拉回 GUIDED。failsafe RTL 不受此限制。
        self.declare_parameter("manual_takeover_cooldown_s", 10.0)
        # FAILSAFE RTL 重发上限: 达到后停止指令洪水 (链路断/飞控拒绝时无限
        # 重发毫无意义), 保持 failsafe 状态并节流告警, 等待人工介入。
        self.declare_parameter("max_rtl_retries", 10)
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
            mpc_status_timeout_s=self.get_parameter("mpc_status_timeout_s").value,
        )

    def _state_callback(self, msg: MavrosState):
        if msg.mode != self._current_mavros_mode:
            # 记录外部/我方模式切换时刻 (人工接管冷却的起点)
            self._last_mode_change = time.monotonic()
        self._current_mavros_mode = msg.mode
        self._armed = msg.armed

    def _mpc_status_callback(self, msg: String):
        """Parse structured status from mpc_node.

        Expected JSON payload: {"state": str, "success": bool, "fail_count": int,
        "solve_time_ms": float, "hold": bool,
        "error": str (optional), "standby_reason": str (optional)}.
        Falls back to substring match for backwards compatibility if JSON
        parsing fails.
        """
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                # e.g. "null" / "123" / "[...]" parses fine but has no fields —
                # treat like any other malformed payload (legacy fallback below)
                # instead of crashing this node with AttributeError.
                raise ValueError("mpc status payload is not a JSON object")
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
        self._last_mpc_status_time = time.monotonic()
        self._safety.mark_mpc_status(self._last_mpc_status_time)
        self._mpc_status_seq += 1

    def _odom_callback(self, msg: Odometry):
        """Feed live pose/speed into geofence and speed-limit checks."""
        self._x = msg.pose.pose.position.x
        self._y = msg.pose.pose.position.y
        self._speed = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)
        self._odom_received = True
        self._last_odom_rx = time.monotonic()
        self._safety.update_odom(
            self._x, self._y, 0.0, self._speed, self._last_odom_rx
        )

    def _battery_callback(self, msg: BatteryState):
        """Cache battery voltage; ignore NaN / invalid readings.

        Voltage goes through update_battery(), NOT update_odom(): refreshing
        the odom watchdog from the battery topic would keep the odom failsafe
        alive after GPS/EKF loss.
        """
        v = msg.voltage
        if not math.isnan(v) and v > 0.0:
            self._voltage = float(v)
            self._battery_received = True
            self._last_battery_rx = time.monotonic()
            self._safety.update_battery(self._voltage, self._last_battery_rx)

    def _path_callback(self, msg: NavPath):
        """Mark a fresh reference path so the path watchdog can detect stalls."""
        self._path_ever_received = True
        self._safety.update_path(received=True, timestamp=time.monotonic())

    def _monitor_loop(self):
        """Periodic safety monitoring and mode management."""
        now = time.monotonic()

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
        #
        # Feed update_solver() ONLY when a fresh /mpc/status arrived since the
        # last tick: re-feeding the same stale failure at the 2 Hz monitor
        # rate inflates the fail count (real 2 consecutive failures can hit
        # max_solver_failures before the MPC's own HOLD buffer engages).
        if self._mpc_state in ("ACTIVE", "HOLD"):
            if self._mpc_status_seq != self._last_status_seq_used:
                self._last_status_seq_used = self._mpc_status_seq
                if self._mpc_fail_count > self._safety.solver_fail_count:
                    self._safety.set_solver_fail_count(self._mpc_fail_count)
                self._safety.update_solver(
                    self._mpc_ok, self._mpc_solve_time_ms, now
                )
        else:
            # STANDBY / UNKNOWN: keep safety in sync but do not accumulate
            # solver failures while MPC is intentionally not solving.
            self._last_status_seq_used = self._mpc_status_seq
            self._safety.set_solver_fail_count(self._mpc_fail_count)
            self._safety.clear_solver_flags(now)

        # /mpc/status freshness watchdog. If the MPC node dies while ACTIVE or
        # HOLD, _mpc_state freezes at its last value and the FCU keeps latching
        # the last velocity command (GUIDED has no setpoint timeout) — that is
        # exactly when this failsafe must fire. Disarmed: not armed yet (dock
        # testing) — do not enforce, same policy as the odom watchdog.
        if self._armed and self._mpc_state in ("ACTIVE", "HOLD"):
            if self._safety.check_mpc_status_timeout(now):
                dt = now - self._last_mpc_status_time
                self._safety.set_mpc_status_watchdog(
                    f"MPC status timeout: {dt:.1f}s", now
                )
            else:
                self._safety.set_mpc_status_watchdog(None, now)
        else:
            self._safety.set_mpc_status_watchdog(None, now)

        # Path-update watchdog. Enforced only while armed (aligned with the
        # odom watchdog): 2026-09-03 实测中 mavros 未连接、armed=False, 但空路径
        # 流让看门狗武装, 规划器一次停发即 FAILSAFE → RTL 0.5s 无限重发。
        # 未解锁时规划器停发不应拉响 failsafe。
        if self._armed and self._path_ever_received:
            self._safety.update_path(received=False, timestamp=now)

        # 电池遥测看门狗 (WARNING 级): 曾收到过电池话题但已断流, 意味着低电量
        # failsafe 变盲。只提醒不 RTL —— 意外 RTL 本身就是一种危险。
        if self._battery_received and (
            now - self._last_battery_rx
        ) > self._battery_timeout_s:
            self._safety.set_battery_watchdog(
                f"No battery telemetry for {now - self._last_battery_rx:.1f}s",
                now,
            )
        else:
            self._safety.set_battery_watchdog(None, now)

        # Check for failsafe trigger
        if self._safety.failsafe_active:
            if self._current_mavros_mode != "RTL":
                if self._rtl_attempts < self._max_rtl_retries:
                    flags = self._safety.active_flags
                    self.get_logger().error(
                        f"FAILSAFE triggered! Flags: {flags}"
                    )
                    self._switch_mode("RTL")
                    self._rtl_attempts += 1
                else:
                    # 2026-09-03 实测教训: FCU 链路断时 set_mode 永远无效、
                    # mode 永远变不成 RTL, 无限重发只是指令洪水。达到上限后
                    # 停止重发, 保持 failsafe 状态并节流告警, 等待人工介入。
                    self.get_logger().error(
                        f"FAILSAFE 持续, 但 RTL 已连发 {self._rtl_attempts} 次"
                        "仍未生效 — 检查 FCU 链路与 home 设置, 已停止重发",
                        throttle_duration_sec=5.0,
                    )
            return
        # failsafe 解除后重置重试计数, 下次 failsafe 仍能正常发起 RTL
        self._rtl_attempts = 0

        # Auto mode switching
        # 触发条件:armed 且不在 GUIDED,且 MPC 有意愿解算——
        #   (1) 当前正在成功解算(legacy 行为),或
        #   (2) MPC 因 wrong_mode 进入 STANDBY(没切到 GUIDED 之前永远不会
        #       success,需要由 mode_manager 主动切过去打破死锁)
        # 人工接管冷却: 模式刚被改变(如操作手切 MANUAL)后的冷却期内不拉回,
        # 给操作手留控制窗口; failsafe RTL 在上方已 return, 不受冷却影响。
        auto_switch = self.get_parameter("auto_mode_switch").value
        in_takeover_cooldown = (
            now - self._last_mode_change
        ) < self._takeover_cooldown_s
        if in_takeover_cooldown and self._current_mavros_mode != "GUIDED":
            self.get_logger().info(
                "人工接管冷却期内, 暂停自动切回 GUIDED",
                throttle_duration_sec=5.0,
            )
        if not in_takeover_cooldown and auto_switch and self._armed \
                and self._current_mavros_mode != "GUIDED":
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
                self.get_logger().warn(
                    f"Safety: {flag}", throttle_duration_sec=5.0
                )

    def request_arm(self, arm: bool = True) -> bool:
        """Request arming/disarming."""
        if not self._cmd_arming_cli.service_is_ready():
            self.get_logger().error("Arming service not ready")
            return False

        req = CommandBool.Request()
        req.value = arm
        future = self._cmd_arming_cli.call_async(req)
        future.add_done_callback(self._on_arm_result)
        return True

    def _on_arm_result(self, future):
        try:
            resp = future.result()
        except Exception:
            return
        if resp is not None and not getattr(resp, "success", False):
            self.get_logger().error(
                f"Arming 请求被飞控拒绝 (result={getattr(resp, 'result', 'n/a')})"
            )

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
        future.add_done_callback(self._on_set_mode_result)
        self.get_logger().info(f"Switching mode: {self._current_mavros_mode} → {mode}")
        return True

    def _on_set_mode_result(self, future):
        try:
            resp = future.result()
        except Exception:
            return
        if resp is not None and not getattr(resp, "mode_sent", True):
            self.get_logger().error(
                "SetMode 请求被拒绝 (mode_sent=False): "
                "failsafe 重试由监控循环继续发起, 请检查 FCU 模式表"
            )

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
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
