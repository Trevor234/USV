#!/usr/bin/env python3
"""只读 FCU 与台架遥测状态采样探针。

由维护 driver 以 trevor 身份、绑定后的生产 DDS 环境调用；只订阅
/mavros/state（及可选 `--check-nav` 诊断话题），不发任何服务请求、
不发布话题、不写文件。

输出（stdout, 单行 JSON）:
  {"ok": bool, "samples": n, "connected": bool|null, "armed": bool|null,
   "mode": str|null, "modes": [...], "elapsed_ns": int, ...}

`safe_hold` 只有在"采到样本 + 全程 connected + 全程未解锁 + 全程 HOLD"时才为 true。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time


def summarize_nav(nav: dict) -> dict:
    missing = []
    if nav["imu_count"] == 0:
        missing.append("imu")
    if nav["odom_count"] == 0:
        missing.append("odom")
    if not nav["gp_origin_seen"]:
        missing.append("gp_origin")
    if nav["path_count"] == 0:
        missing.append("path")
    if nav["profile_count"] == 0:
        missing.append("profile")
    out = dict(nav)
    out["missing"] = missing
    out["nav_ready"] = bool(
        nav["imu_count"] > 0 and nav["imu_finite"]
        and nav["odom_count"] > 0 and nav["odom_finite"]
        and nav["path_count"] > 0 and nav["profile_count"] > 0
    )
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--topic", default="/mavros/state")
    parser.add_argument("--check-nav", action="store_true",
                        help="同时只读采样 IMU / Odom / gp_origin / Path / Profile，用于排查 EKF 与航线就绪条件")
    args = parser.parse_args(argv)

    try:
        import rclpy
        from mavros_msgs.msg import State
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    except Exception as error:  # noqa: BLE001 - 缺依赖必须显式失败
        print(json.dumps({"ok": False, "error": f"import:{error}"}))
        return 2

    rclpy.init(args=None)
    node = Node("p1_fcu_state_probe")
    facts = {"ok": True, "samples": 0, "connected": None, "armed": None,
             "mode": None, "modes": []}
    start = time.monotonic_ns()

    def on_state(message) -> None:
        facts["samples"] += 1
        facts["connected"] = bool(message.connected) if facts["connected"] is None \
            else (facts["connected"] and bool(message.connected))
        facts["armed"] = bool(message.armed) if facts["armed"] is None \
            else (facts["armed"] or bool(message.armed))
        facts["mode"] = message.mode
        if message.mode not in facts["modes"]:
            facts["modes"].append(message.mode)

    node.create_subscription(State, args.topic, on_state, 10)

    nav_state = None
    if args.check_nav:
        from geographic_msgs.msg import GeoPointStamped
        from nav_msgs.msg import Odometry, Path
        from sensor_msgs.msg import Imu
        from std_msgs.msg import Float64MultiArray

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=10,
        )
        nav_state = {
            "imu_count": 0,
            "imu_frame": None,
            "imu_finite": True,
            "odom_count": 0,
            "odom_frame": None,
            "odom_child_frame": None,
            "odom_finite": True,
            "gp_origin_seen": False,
            "gp_origin_count": 0,
            "path_count": 0,
            "path_points": 0,
            "profile_count": 0,
            "profile_size": 0,
        }

        def on_imu(msg) -> None:
            nav_state["imu_count"] += 1
            nav_state["imu_frame"] = msg.header.frame_id
            vals = (
                msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w,
                msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z,
            )
            if not all(math.isfinite(float(v)) for v in vals):
                nav_state["imu_finite"] = False

        def on_odom(msg) -> None:
            nav_state["odom_count"] += 1
            nav_state["odom_frame"] = msg.header.frame_id
            nav_state["odom_child_frame"] = msg.child_frame_id
            vals = (
                msg.pose.pose.position.x, msg.pose.pose.position.y,
                msg.twist.twist.linear.x, msg.twist.twist.linear.y, msg.twist.twist.angular.z,
            )
            if not all(math.isfinite(float(v)) for v in vals):
                nav_state["odom_finite"] = False

        def on_gp_origin(_msg) -> None:
            nav_state["gp_origin_seen"] = True
            nav_state["gp_origin_count"] += 1

        def on_path(msg) -> None:
            nav_state["path_count"] += 1
            nav_state["path_points"] = len(msg.poses)

        def on_profile(msg) -> None:
            nav_state["profile_count"] += 1
            nav_state["profile_size"] = len(msg.data)

        node.create_subscription(Imu, "/mavros/imu/data", on_imu, sensor_qos)
        node.create_subscription(Odometry, "/mavros/local_position/odom", on_odom, sensor_qos)
        node.create_subscription(GeoPointStamped, "/mavros/global_position/gp_origin", on_gp_origin, 10)
        node.create_subscription(Path, "/path/reference", on_path, 10)
        node.create_subscription(Float64MultiArray, "/path/reference_profile", on_profile, 10)

    deadline = start + int(args.seconds * 1e9)
    while rclpy.ok() and time.monotonic_ns() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()

    facts["elapsed_ns"] = time.monotonic_ns() - start
    facts["safe_hold"] = bool(
        facts["samples"] > 0 and facts["connected"] is True and
        facts["armed"] is False and facts["modes"] == ["HOLD"])
    if nav_state is not None:
        facts["nav"] = summarize_nav(nav_state)
    print(json.dumps(facts))
    return 0 if facts["samples"] > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
