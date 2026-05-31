"""USV 运行状态实时可视化节点。"""

import json
import math
import os
import sys
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import rclpy
from geometry_msgs.msg import TwistStamped
from mavros_msgs.msg import OverrideRCIn, State
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node
from rclpy.qos import QoSProfile, qos_profile_sensor_data
from std_msgs.msg import String


class USVVisualizer(Node):
    """用 matplotlib 显示 USV 位姿、轨迹、控制输出和话题状态。"""

    def __init__(self):
        super().__init__("usv_visualizer")

        self._declare_parameters()
        self._load_parameters()

        self._history = deque(maxlen=self._history_length)
        self._ref_path: List[Tuple[float, float]] = []
        self._mpc_traj: List[Tuple[float, float]] = []
        self._mission_waypoints: List[Tuple[float, float]] = []

        self._x = 0.0
        self._y = 0.0
        self._psi = 0.0
        self._u = 0.0
        self._v = 0.0
        self._r = 0.0

        self._mavros_connected: Optional[bool] = None
        self._mavros_armed: Optional[bool] = None
        self._mavros_mode = "-"
        self._mpc_status: Dict[str, Any] = {}
        self._cmd_vel: Optional[Tuple[float, float]] = None
        self._rc_channels: List[int] = []

        self._topic_stats: Dict[str, Dict[str, Any]] = {}
        self._init_topic_stats()
        self._init_subscriptions()

        self.get_logger().info(
            "USV visualizer started | "
            f"odom={self._odom_topic} | ref={self._reference_path_topic} | "
            f"mpc={self._mpc_trajectory_topic} | mission={self._mission_waypoints_topic}"
        )

    def _declare_parameters(self):
        self.declare_parameter("odom_topic", "/mavros/mavros/odom")
        self.declare_parameter("reference_path_topic", "/path/reference")
        self.declare_parameter("mpc_trajectory_topic", "/mpc/predicted_trajectory")
        self.declare_parameter("mission_waypoints_topic", "/usv/mission/waypoints_local")
        self.declare_parameter("mpc_status_topic", "/mpc/status")
        self.declare_parameter("mavros_state_topic", "/mavros/state")
        self.declare_parameter("cmd_vel_topic", "/mavros/mavros/cmd_vel")
        self.declare_parameter("rc_override_topic", "/mavros/mavros/override")
        self.declare_parameter("history_length", 10000)
        self.declare_parameter("plot_interval_ms", 200)

    def _load_parameters(self):
        self._odom_topic = self.get_parameter("odom_topic").value
        self._reference_path_topic = self.get_parameter("reference_path_topic").value
        self._mpc_trajectory_topic = self.get_parameter("mpc_trajectory_topic").value
        self._mission_waypoints_topic = self.get_parameter("mission_waypoints_topic").value
        self._mpc_status_topic = self.get_parameter("mpc_status_topic").value
        self._mavros_state_topic = self.get_parameter("mavros_state_topic").value
        self._cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self._rc_override_topic = self.get_parameter("rc_override_topic").value
        self._history_length = max(1, int(self.get_parameter("history_length").value))
        self._plot_interval_ms = max(50, int(self.get_parameter("plot_interval_ms").value))

    def _init_topic_stats(self):
        topics = [
            ("odom", "odom", self._odom_topic, 1.0),
            ("ref", "ref_path", self._reference_path_topic, 5.0),
            ("traj", "mpc_traj", self._mpc_trajectory_topic, 2.0),
            ("mission", "mission_wp", self._mission_waypoints_topic, 60.0),
            ("mpc_status", "mpc_status", self._mpc_status_topic, 2.0),
            ("mavros_state", "mav_state", self._mavros_state_topic, 2.0),
            ("cmd_vel", "cmd_vel", self._cmd_vel_topic, 2.0),
            ("rc_override", "rc_override", self._rc_override_topic, 2.0),
        ]
        for key, label, topic, stale_after in topics:
            self._topic_stats[key] = {
                "label": label,
                "topic": topic,
                "count": 0,
                "last_time": None,
                "stale_after": stale_after,
            }

    def _init_subscriptions(self):
        reliable_qos = QoSProfile(depth=10)
        self.create_subscription(Odometry, self._odom_topic, self._odom_callback, qos_profile_sensor_data)
        self.create_subscription(NavPath, self._reference_path_topic, self._ref_callback, reliable_qos)
        self.create_subscription(NavPath, self._mpc_trajectory_topic, self._traj_callback, reliable_qos)
        self.create_subscription(NavPath, self._mission_waypoints_topic, self._mission_callback, reliable_qos)
        self.create_subscription(String, self._mpc_status_topic, self._mpc_status_callback, reliable_qos)
        self.create_subscription(State, self._mavros_state_topic, self._mavros_state_callback, reliable_qos)
        self.create_subscription(TwistStamped, self._cmd_vel_topic, self._cmd_vel_callback, reliable_qos)
        self.create_subscription(OverrideRCIn, self._rc_override_topic, self._rc_override_callback, reliable_qos)

    def _mark_topic(self, key: str):
        stat = self._topic_stats[key]
        stat["count"] += 1
        stat["last_time"] = time.monotonic()

    def _odom_callback(self, msg: Odometry):
        self._mark_topic("odom")
        self._x = msg.pose.pose.position.x
        self._y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self._psi = math.atan2(siny, cosy)
        self._u = msg.twist.twist.linear.x
        self._v = msg.twist.twist.linear.y
        self._r = msg.twist.twist.angular.z
        self._history.append((self._x, self._y, self._psi))

    def _ref_callback(self, msg: NavPath):
        self._mark_topic("ref")
        self._ref_path = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]

    def _traj_callback(self, msg: NavPath):
        self._mark_topic("traj")
        self._mpc_traj = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]

    def _mission_callback(self, msg: NavPath):
        self._mark_topic("mission")
        self._mission_waypoints = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]

    def _mpc_status_callback(self, msg: String):
        self._mark_topic("mpc_status")
        try:
            payload = json.loads(msg.data)
            self._mpc_status = payload if isinstance(payload, dict) else {"raw": msg.data}
        except json.JSONDecodeError:
            self._mpc_status = {"raw": msg.data}

    def _mavros_state_callback(self, msg: State):
        self._mark_topic("mavros_state")
        self._mavros_connected = msg.connected
        self._mavros_armed = msg.armed
        self._mavros_mode = msg.mode or "-"

    def _cmd_vel_callback(self, msg: TwistStamped):
        self._mark_topic("cmd_vel")
        self._cmd_vel = (msg.twist.linear.x, msg.twist.angular.z)

    def _rc_override_callback(self, msg: OverrideRCIn):
        self._mark_topic("rc_override")
        self._rc_channels = list(msg.channels)

    @property
    def history(self) -> List[Tuple[float, float, float]]:
        return list(self._history)

    @property
    def reference_path(self) -> List[Tuple[float, float]]:
        return self._ref_path

    @property
    def mpc_trajectory(self) -> List[Tuple[float, float]]:
        return self._mpc_traj

    @property
    def mission_waypoints(self) -> List[Tuple[float, float]]:
        return self._mission_waypoints

    @property
    def plot_interval_ms(self) -> int:
        return self._plot_interval_ms

    def _format_bool(self, value: Optional[bool]) -> str:
        if value is None:
            return "-"
        return "yes" if value else "no"

    def _format_topic_line(self, key: str, now: float) -> str:
        stat = self._topic_stats[key]
        label = stat["label"]
        count = stat["count"]
        last_time = stat["last_time"]
        if count == 0 or last_time is None:
            return f"{label:<12} NO DATA  n=0"
        age = now - last_time
        state = "OK" if age <= stat["stale_after"] else "STALE"
        return f"{label:<12} {state:<7} n={count:<5} age={age:4.1f}s"

    def _short_text(self, value: Any, max_len: int = 44) -> str:
        text = str(value)
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def build_info_text(self) -> str:
        mpc_state = self._mpc_status.get("state", "-")
        mpc_scheme = self._mpc_status.get("scheme", "-")
        solve_time = self._mpc_status.get("solve_time_ms", "-")
        fail_count = self._mpc_status.get("fail_count", "-")
        reason = self._mpc_status.get("standby_reason", self._mpc_status.get("error", "-"))
        raw_status = self._mpc_status.get("raw")

        if isinstance(solve_time, (float, int)):
            solve_time_text = f"{float(solve_time):.1f} ms"
        else:
            solve_time_text = str(solve_time)

        if self._cmd_vel is None:
            cmd_text = "u=-, r=-"
        else:
            cmd_text = f"u={self._cmd_vel[0]:.2f}, r={self._cmd_vel[1]:.2f}"

        ch1 = self._rc_channels[0] if len(self._rc_channels) > 0 else "-"
        ch3 = self._rc_channels[2] if len(self._rc_channels) > 2 else "-"
        now = time.monotonic()
        topic_lines = [self._format_topic_line(key, now) for key in self._topic_stats]

        lines = [
            "USV STATE",
            f"  x/y     : {self._x:7.2f} / {self._y:7.2f} m",
            f"  heading : {math.degrees(self._psi):7.1f} deg",
            f"  u/v/r   : {self._u:5.2f} / {self._v:5.2f} / {self._r:5.2f}",
            "",
            "PATH",
            f"  reference points : {len(self._ref_path)}",
            f"  mpc preview pts  : {len(self._mpc_traj)}",
            f"  mission waypoints: {len(self._mission_waypoints)}",
            "",
            "MAVROS",
            f"  connected: {self._format_bool(self._mavros_connected)}",
            f"  armed    : {self._format_bool(self._mavros_armed)}",
            f"  mode     : {self._mavros_mode}",
            "",
            "MPC",
            f"  state    : {mpc_state}",
            f"  scheme   : {mpc_scheme}",
            f"  solve    : {solve_time_text}",
            f"  failures : {fail_count}",
            f"  reason   : {self._short_text(reason)}",
            "",
            "CONTROL OUTPUT",
            f"  cmd_vel  : {cmd_text}",
            f"  RC CH1/3 : {ch1} / {ch3}",
        ]
        if raw_status:
            lines.extend(["", f"RAW MPC: {self._short_text(raw_status)}"])
        lines.extend(["", "TOPIC HEALTH", *topic_lines])
        return "\n".join(lines)


def _has_display() -> bool:
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def main(args=None):
    if not _has_display():
        print(
            "无法启动 USV 可视化界面：当前环境没有 DISPLAY/WAYLAND_DISPLAY。"
            "请在有图形界面的地面站运行 ros2 run usv_simulation visualizer。",
            file=sys.stderr,
        )
        return

    try:
        import matplotlib
        matplotlib.use("TkAgg")
        import matplotlib.animation as animation
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"无法加载 matplotlib TkAgg 后端：{exc}", file=sys.stderr)
        return

    rclpy.init(args=args)
    node: Optional[USVVisualizer] = None
    try:
        node = USVVisualizer()
        fig, (ax_track, ax_data) = plt.subplots(
            1,
            2,
            figsize=(16, 8),
            gridspec_kw={"width_ratios": [2.0, 1.15]},
        )

        view_locked = False
        follow_usv = False
        manual_xlim = None
        manual_ylim = None

        def capture_view():
            nonlocal manual_xlim, manual_ylim
            manual_xlim = ax_track.get_xlim()
            manual_ylim = ax_track.get_ylim()

        def zoom_view(factor: float):
            nonlocal view_locked, follow_usv, manual_xlim, manual_ylim
            xlim = manual_xlim if manual_xlim is not None else ax_track.get_xlim()
            ylim = manual_ylim if manual_ylim is not None else ax_track.get_ylim()
            cx = 0.5 * (xlim[0] + xlim[1])
            cy = 0.5 * (ylim[0] + ylim[1])
            half_w = 0.5 * (xlim[1] - xlim[0]) * factor
            half_h = 0.5 * (ylim[1] - ylim[0]) * factor
            manual_xlim = (cx - half_w, cx + half_w)
            manual_ylim = (cy - half_h, cy + half_h)
            view_locked = True
            follow_usv = False

        def on_key(event):
            nonlocal view_locked, follow_usv, manual_xlim, manual_ylim
            if event.key in ["+", "="]:
                capture_view()
                zoom_view(0.8)
            elif event.key in ["-", "_"]:
                capture_view()
                zoom_view(1.25)
            elif event.key == "r":
                view_locked = False
                follow_usv = False
                manual_xlim = None
                manual_ylim = None
            elif event.key == "l":
                capture_view()
                view_locked = not view_locked
                follow_usv = False
            elif event.key == "f":
                follow_usv = not follow_usv
                view_locked = follow_usv

        fig.canvas.mpl_connect("key_press_event", on_key)

        def update_plot(_frame):
            nonlocal manual_xlim, manual_ylim
            rclpy.spin_once(node, timeout_sec=0.01)

            if view_locked and manual_xlim is None:
                capture_view()

            ax_track.clear()
            ax_track.set_xlabel("East x (m)")
            ax_track.set_ylabel("North y (m)")
            ax_track.set_title("USV Trajectory")
            ax_track.grid(True)

            ref = node.reference_path
            if ref:
                rx, ry = zip(*ref)
                ax_track.plot(rx, ry, "b--", linewidth=1.2, alpha=0.8, label="Reference path")

            traj = node.mpc_trajectory
            if traj:
                tx, ty = zip(*traj)
                ax_track.plot(tx, ty, "g-", linewidth=1.4, alpha=0.65, label="MPC preview")

            mission = node.mission_waypoints
            if mission:
                mx, my = zip(*mission)
                ax_track.plot(mx, my, "o", color="orange", markersize=6, label="Mission waypoints")

            hist = node.history
            if hist:
                hx, hy, _ = zip(*hist)
                ax_track.plot(hx, hy, "r-", linewidth=2.0, label="Actual track")
                x, y, psi = node._x, node._y, node._psi
                ax_track.arrow(
                    x,
                    y,
                    2.0 * math.cos(psi),
                    2.0 * math.sin(psi),
                    head_width=0.5,
                    head_length=0.5,
                    fc="r",
                    ec="r",
                )
            else:
                ax_track.text(
                    0.5,
                    0.5,
                    "Waiting for odometry/path data...",
                    transform=ax_track.transAxes,
                    ha="center",
                    va="center",
                )

            ax_track.set_aspect("equal", adjustable="datalim")
            if follow_usv and hist:
                span_x = 30.0
                span_y = 30.0
                manual_xlim = (node._x - span_x / 2.0, node._x + span_x / 2.0)
                manual_ylim = (node._y - span_y / 2.0, node._y + span_y / 2.0)
            if view_locked and manual_xlim is not None and manual_ylim is not None:
                ax_track.set_xlim(manual_xlim)
                ax_track.set_ylim(manual_ylim)
            ax_track.text(
                0.01,
                0.99,
                "Keys: +/- zoom  l lock  f follow  r reset",
                transform=ax_track.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                color="0.35",
            )
            handles, labels = ax_track.get_legend_handles_labels()
            if handles:
                ax_track.legend(handles, labels, loc="upper right")

            ax_data.clear()
            ax_data.axis("off")
            ax_data.set_title("Runtime Data")
            ax_data.text(
                0.02,
                0.98,
                node.build_info_text(),
                fontsize=9,
                fontfamily="monospace",
                va="top",
            )
            return ax_track, ax_data

        ani = animation.FuncAnimation(
            fig,
            update_plot,
            interval=node.plot_interval_ms,
            blit=False,
            cache_frame_data=False,
        )
        fig._usv_visualizer_animation = ani
        plt.show()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        if node is not None:
            node.get_logger().error(f"USV visualizer stopped: {exc}")
        else:
            print(f"USV visualizer stopped: {exc}", file=sys.stderr)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
