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
from mavros_msgs.msg import GPSRAW, RTCM
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node
from rclpy.qos import QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import Float64, String


class USVVisualizer(Node):
    """用 matplotlib 显示 USV 位姿、轨迹、控制输出和话题状态。"""

    def __init__(self):
        super().__init__("usv_visualizer")

        self._declare_parameters()
        self._load_parameters()

        self._history = deque(maxlen=self._history_length)
        # 绝对累计计数 (单调递增): snapshot 的 track_since 是绝对游标,
        # deque 环绕后需用它换算相对索引, 否则增量轨迹永久截断为空。
        self._history_total = 0
        self._ref_path: List[Tuple[float, float]] = []
        self._mpc_traj: List[Tuple[float, float]] = []
        self._mission_waypoints: List[Tuple[float, float]] = []

        self._x = 0.0
        self._y = 0.0
        self._psi = 0.0
        self._u = 0.0
        self._v = 0.0
        self._r = 0.0

        self._mpc_status: Dict[str, Any] = {}
        self._cmd_vel: Optional[Tuple[float, float]] = None
        self._left_thrust: Optional[float] = None
        self._right_thrust: Optional[float] = None
        self._rtcm_last_size = 0
        self._rtcm_total_bytes = 0
        self._rtcm_rate_window: deque[Tuple[float, int]] = deque(maxlen=200)
        self._gps_fix_status: Optional[int] = None
        self._gps_fix_llh: Optional[Tuple[float, float, float]] = None
        self._gps_raw: Optional[Dict[str, Any]] = None

        self._topic_stats: Dict[str, Dict[str, Any]] = {}
        self._init_topic_stats()
        self._init_subscriptions()

        self.get_logger().info(
            "USV visualizer started | "
            f"odom={self._odom_topic} | ref={self._reference_path_topic} | "
            f"mpc={self._mpc_trajectory_topic} | mission={self._mission_waypoints_topic} | "
            f"thrust=({self._left_thrust_topic}, {self._right_thrust_topic})"
        )

    def _declare_parameters(self):
        # 默认值面向实机方案A（运动学 MPC, cmd_vel 输出, 无推力话题）。
        # VRX/WAM-V 仿真请通过 launch 参数覆盖 odom/thrust 话题。
        self.declare_parameter("odom_topic", "/mavros/local_position/odom")
        self.declare_parameter("reference_path_topic", "/path/reference")
        self.declare_parameter("path_topic", "/path/reference")
        self.declare_parameter("mpc_trajectory_topic", "/mpc/predicted_trajectory")
        self.declare_parameter("predicted_trajectory_topic", "/mpc/predicted_trajectory")
        self.declare_parameter("mission_waypoints_topic", "/usv/mission/waypoints_local")
        self.declare_parameter("mpc_status_topic", "/mpc/status")
        self.declare_parameter("cmd_vel_topic", "/mavros/setpoint_velocity/cmd_vel")
        self.declare_parameter("left_thrust_topic", "")
        self.declare_parameter("right_thrust_topic", "")
        self.declare_parameter("rtcm_topic", "/mavros/gps_rtk/send_rtcm")
        self.declare_parameter("gps_fix_topic", "/mavros/global_position/raw/fix")
        self.declare_parameter("gps_raw_topic", "/mavros/gpsstatus/gps1/raw")
        self.declare_parameter("history_length", 10000)
        self.declare_parameter("plot_interval_ms", 200)

    def _load_parameters(self):
        self._odom_topic = self.get_parameter("odom_topic").value
        self._reference_path_topic = self.get_parameter("path_topic").value
        self._mpc_trajectory_topic = self.get_parameter("predicted_trajectory_topic").value
        self._mission_waypoints_topic = self.get_parameter("mission_waypoints_topic").value
        self._mpc_status_topic = self.get_parameter("mpc_status_topic").value
        self._cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self._left_thrust_topic = self.get_parameter("left_thrust_topic").value
        self._right_thrust_topic = self.get_parameter("right_thrust_topic").value
        self._rtcm_topic = self.get_parameter("rtcm_topic").value
        self._gps_fix_topic = self.get_parameter("gps_fix_topic").value
        self._gps_raw_topic = self.get_parameter("gps_raw_topic").value
        self._history_length = max(1, int(self.get_parameter("history_length").value))
        self._plot_interval_ms = max(50, int(self.get_parameter("plot_interval_ms").value))

    def _init_topic_stats(self):
        topics = [
            ("odom", "odom", self._odom_topic, 1.0),
            ("ref", "ref_path", self._reference_path_topic, 5.0),
            ("traj", "mpc_traj", self._mpc_trajectory_topic, 2.0),
            ("mission", "mission_wp", self._mission_waypoints_topic, 60.0),
            ("mpc_status", "mpc_status", self._mpc_status_topic, 2.0),
            ("rtcm", "rtcm_inject", self._rtcm_topic, 3.0),
            ("gps_fix", "gps_fix", self._gps_fix_topic, 3.0),
            ("gps_raw", "gps_raw", self._gps_raw_topic, 3.0),
        ]
        if self._left_thrust_topic:
            topics.append(("left_thrust", "left_thrust", self._left_thrust_topic, 2.0))
        if self._right_thrust_topic:
            topics.append(("right_thrust", "right_thrust", self._right_thrust_topic, 2.0))
        if self._cmd_vel_topic:
            topics.append(("cmd_vel", "cmd_vel", self._cmd_vel_topic, 2.0))

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
        if self._left_thrust_topic:
            self.create_subscription(Float64, self._left_thrust_topic, self._left_thrust_callback, reliable_qos)
        if self._right_thrust_topic:
            self.create_subscription(Float64, self._right_thrust_topic, self._right_thrust_callback, reliable_qos)
        if self._cmd_vel_topic:
            self.create_subscription(TwistStamped, self._cmd_vel_topic, self._cmd_vel_callback, reliable_qos)
        if self._rtcm_topic:
            self.create_subscription(RTCM, self._rtcm_topic, self._rtcm_callback, reliable_qos)
        if self._gps_fix_topic:
            self.create_subscription(NavSatFix, self._gps_fix_topic, self._gps_fix_callback, qos_profile_sensor_data)
        if self._gps_raw_topic:
            self.create_subscription(GPSRAW, self._gps_raw_topic, self._gps_raw_callback, qos_profile_sensor_data)

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
        self._history_total += 1

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

    def _cmd_vel_callback(self, msg: TwistStamped):
        self._mark_topic("cmd_vel")
        self._cmd_vel = (msg.twist.linear.x, msg.twist.angular.z)

    def _left_thrust_callback(self, msg: Float64):
        self._mark_topic("left_thrust")
        self._left_thrust = msg.data

    def _right_thrust_callback(self, msg: Float64):
        self._mark_topic("right_thrust")
        self._right_thrust = msg.data

    def _rtcm_callback(self, msg: RTCM):
        self._mark_topic("rtcm")
        now = time.monotonic()
        self._rtcm_last_size = len(msg.data)
        self._rtcm_total_bytes += self._rtcm_last_size
        self._rtcm_rate_window.append((now, self._rtcm_last_size))

    def _gps_fix_callback(self, msg: NavSatFix):
        self._mark_topic("gps_fix")
        self._gps_fix_status = msg.status.status
        self._gps_fix_llh = (msg.latitude, msg.longitude, msg.altitude)

    def _gps_raw_callback(self, msg: GPSRAW):
        self._mark_topic("gps_raw")
        self._gps_raw = {
            "fix_type": msg.fix_type,
            "satellites_visible": msg.satellites_visible,
            "eph": msg.eph,
            "epv": msg.epv,
            "h_acc": msg.h_acc,
            "v_acc": msg.v_acc,
            "dgps_age": msg.dgps_age,
            "dgps_numch": msg.dgps_numch,
        }

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

    def _rtcm_rate_bps(self, now: float) -> float:
        while self._rtcm_rate_window and now - self._rtcm_rate_window[0][0] > 5.0:
            self._rtcm_rate_window.popleft()
        if len(self._rtcm_rate_window) < 2:
            return 0.0
        duration = max(1e-3, self._rtcm_rate_window[-1][0] - self._rtcm_rate_window[0][0])
        return sum(size for _, size in self._rtcm_rate_window) / duration

    def _fix_type_text(self) -> str:
        if not self._gps_raw:
            return "-"
        names = {
            0: "NO_GPS",
            1: "NO_FIX",
            2: "2D",
            3: "3D",
            4: "DGPS",
            5: "RTK_FLOAT",
            6: "RTK_FIXED",
            7: "STATIC",
            8: "PPP",
        }
        fix_type = int(self._gps_raw.get("fix_type", 0))
        return f"{fix_type} {names.get(fix_type, 'UNKNOWN')}"

    def _navsat_status_text(self) -> str:
        if self._gps_fix_status is None:
            return "-"
        names = {-2: "UNKNOWN", -1: "NO_FIX", 0: "FIX", 1: "SBAS", 2: "GBAS"}
        return f"{self._gps_fix_status} {names.get(self._gps_fix_status, 'UNKNOWN')}"

    def _format_age(self, key: str, now: float) -> str:
        stat = self._topic_stats.get(key)
        if not stat or stat["last_time"] is None:
            return "-"
        return f"{now - stat['last_time']:.1f}s"

    def build_info_text(self) -> str:
        mpc_state = self._mpc_status.get("state", "-")
        solve_time = self._mpc_status.get("solve_time_ms", "-")
        fail_count = self._mpc_status.get("fail_count", "-")
        reason = self._mpc_status.get("standby_reason", self._mpc_status.get("error", "-"))
        raw_status = self._mpc_status.get("raw")

        if isinstance(solve_time, (float, int)):
            solve_time_text = f"{float(solve_time):.1f} ms"
        else:
            solve_time_text = str(solve_time)

        if self._cmd_vel is None:
            cmd_text = "disabled"
        else:
            cmd_text = f"u={self._cmd_vel[0]:.2f}, r={self._cmd_vel[1]:.2f}"

        # 推力优先从 /mpc/status 诊断 JSON 解析 (tl_n/tr_n, 单位 N);
        # 仅当未配置状态字段时才回退到独立的 Float64 推力话题。
        status_tl = self._mpc_status.get("tl_n")
        status_tr = self._mpc_status.get("tr_n")
        if isinstance(status_tl, (int, float)):
            left_text = f"{float(status_tl):.2f}"
            thrust_src = "status"
        elif self._left_thrust is not None:
            left_text = f"{self._left_thrust:.2f}"
            thrust_src = "topic"
        else:
            left_text = "-"
            thrust_src = "none"
        if isinstance(status_tr, (int, float)):
            right_text = f"{float(status_tr):.2f}"
        elif self._right_thrust is not None:
            right_text = f"{self._right_thrust:.2f}"
        else:
            right_text = "-"

        # RC PWM (若 /mpc/status 提供)。
        steering_pwm = self._mpc_status.get("steering_pwm")
        throttle_pwm = self._mpc_status.get("throttle_pwm")
        if isinstance(steering_pwm, (int, float)) and isinstance(throttle_pwm, (int, float)):
            rc_text = f"steer={int(steering_pwm)} throttle={int(throttle_pwm)}"
        else:
            rc_text = "-"
        now = time.monotonic()
        topic_lines = [self._format_topic_line(key, now) for key in self._topic_stats]
        rtcm_age = self._format_age("rtcm", now)
        rtcm_rate = self._rtcm_rate_bps(now)
        gps_raw = self._gps_raw or {}
        gps_h_acc = gps_raw.get("h_acc", 0)
        gps_h_acc_text = "-" if not gps_h_acc or gps_h_acc == 0xFFFFFFFF else f"{gps_h_acc / 1000.0:.2f} m"
        dgps_age = gps_raw.get("dgps_age", 0)
        dgps_age_text = "-" if not dgps_age or dgps_age == 0xFFFFFFFF else f"{dgps_age / 1000.0:.1f}s"

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
            "MPC",
            f"  state    : {mpc_state}",
            f"  solve    : {solve_time_text}",
            f"  failures : {fail_count}",
            f"  reason   : {self._short_text(reason)}",
            "",
            "CONTROL OUTPUT",
            f"  thrust L/R: {left_text} / {right_text} N  (src={thrust_src})",
            f"  rc pwm    : {rc_text}",
            f"  cmd_vel   : {cmd_text}",
            "",
            "RTK / NTRIP",
            f"  rtcm topic : {self._short_text(self._rtcm_topic)}",
            f"  rtcm age   : {rtcm_age}",
            f"  rtcm bytes : last={self._rtcm_last_size} total={self._rtcm_total_bytes}",
            f"  rtcm rate  : {rtcm_rate:.0f} B/s",
            f"  fix input  : {self._navsat_status_text()} age={self._format_age('gps_fix', now)}",
            f"  gps raw    : {self._fix_type_text()} sats={gps_raw.get('satellites_visible', '-')}",
            f"  accuracy   : h_acc={gps_h_acc_text} dgps_age={dgps_age_text}",
        ]
        if raw_status:
            lines.extend(["", f"RAW MPC: {self._short_text(raw_status)}"])
        lines.extend(["", "TOPIC HEALTH", *topic_lines])
        return "\n".join(lines)

    def snapshot(self, track_since: int = 0) -> Dict[str, Any]:
        """导出结构化状态快照，供遥测桥接打包发送。

        track_since 是累计样本数的绝对游标; 返回仍保留的后续点。
        track.next 是本次快照的下一游标, 不等于本次 append 长度。
        缓冲区已逐出的点无法恢复。返回字典与地面站 usv_gcs 契约对齐。
        """
        now = time.monotonic()

        state = {
            "x": self._x, "y": self._y, "psi": self._psi,
            "u": self._u, "v": self._v, "r": self._r,
        }

        mpc: Dict[str, Any] = {}
        if self._mpc_status:
            for k in ("state", "solve_time_ms", "fail_count",
                      "tl_n", "tr_n", "steering_pwm", "throttle_pwm"):
                if k in self._mpc_status:
                    mpc[k] = self._mpc_status[k]
            reason = (self._mpc_status.get("standby_reason")
                      or self._mpc_status.get("error"))
            if reason:
                mpc["reason"] = reason

        gps: Dict[str, Any] = {}
        raw = self._gps_raw or {}
        if "fix_type" in raw:
            gps["fix_type"] = raw["fix_type"]
        if "satellites_visible" in raw:
            gps["sats"] = raw["satellites_visible"]
        h_acc = raw.get("h_acc", 0)
        if h_acc and h_acc != 0xFFFFFFFF:
            gps["h_acc_m"] = h_acc / 1000.0
        v_acc = raw.get("v_acc", 0)
        if v_acc and v_acc != 0xFFFFFFFF:
            gps["v_acc_m"] = v_acc / 1000.0
        dgps = raw.get("dgps_age", 0)
        if dgps and dgps != 0xFFFFFFFF:
            gps["dgps_age"] = dgps / 1000.0
        if self._gps_fix_status is not None:
            gps["status"] = self._gps_fix_status
        if self._gps_fix_llh is not None:
            gps["lat"], gps["lon"], gps["alt"] = self._gps_fix_llh

        rtcm: Dict[str, Any] = {
            "last_bytes": self._rtcm_last_size,
            "total_bytes": self._rtcm_total_bytes,
            "rate_bps": self._rtcm_rate_bps(now),
        }
        rtcm_stat = self._topic_stats.get("rtcm")
        if rtcm_stat and rtcm_stat["last_time"] is not None:
            rtcm["age_s"] = now - rtcm_stat["last_time"]

        topics: Dict[str, Any] = {}
        for key, stat in self._topic_stats.items():
            age = -1.0
            if stat["last_time"] is not None:
                age = now - stat["last_time"]
            if stat["count"] == 0:
                st = "NO DATA"
            elif age <= stat["stale_after"]:
                st = "OK"
            else:
                st = "STALE"
            topics[key] = {
                "label": stat["label"],
                "topic": stat["topic"],
                "st": st,
                "n": stat["count"],
                "age": round(age, 2),
            }

        paths: Dict[str, Any] = {
            "ref":     {"pts": [[x, y] for x, y in self._ref_path]},
            "mpc":     {"pts": [[x, y] for x, y in self._mpc_traj]},
            "mission": {"pts": [[x, y] for x, y in self._mission_waypoints]},
        }

        hist = list(self._history)
        history_total = self._history_total
        # track_since 是绝对游标 (历史累计总数); deque 有界环绕会逐出旧点,
        # 换算相对索引: 已逐出数 = 累计总数 - 当前长度。环绕后 (约
        # history_length 个样本) 未换算的游标会恒大于 len(hist), 增量轨迹
        # 永久截断为空 —— GCS 轨迹显示停止更新。clamp 到 [0, len]。
        evicted = max(0, history_total - len(hist))
        since = min(max(track_since - evicted, 0), len(hist))
        track_append = [[p[0], p[1], p[2]] for p in hist[since:]]

        if self._cmd_vel is not None:
            cmd_vel = f"u={self._cmd_vel[0]:.2f}, r={self._cmd_vel[1]:.2f}"
        else:
            cmd_vel = "disabled"

        return {
            "v": 1,
            "state": state,
            "mpc": mpc,
            "gps": gps,
            "rtcm": rtcm,
            "cmd_vel": cmd_vel,
            "topics": topics,
            "paths": paths,
            "track": {"append": track_append, "next": history_total},
        }


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
