#!/usr/bin/env python3
"""Launch an isolated still-water boat and check real ROS -> GZ thrust / sensors.

Set a private ROS_DOMAIN_ID and GZ_PARTITION before invoking this script.
Requires the ROS, VRX, and USV workspaces to be sourced.
"""

import json
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64


def main():
    if not os.getenv("GZ_PARTITION") or not os.getenv("ROS_DOMAIN_ID"):
        raise RuntimeError("Set isolated GZ_PARTITION and ROS_DOMAIN_ID for this test")
    log_path = Path(os.environ.get("ROS_LOG_DIR", "/tmp/usv_vrx_transport"))
    log_path.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = rclpy.create_node("vrx_transport_check")
    odometry, imu = [], []
    node.create_subscription(Odometry, "/wamv/sensors/position/ground_truth_odometry",
                             odometry.append, qos_profile_sensor_data)
    node.create_subscription(Imu, "/wamv/sensors/imu/imu/data", imu.append, qos_profile_sensor_data)
    left = node.create_publisher(Float64, "/wamv/thrusters/left/thrust", 10)
    right = node.create_publisher(Float64, "/wamv/thrusters/right/thrust", 10)
    log = (log_path / "launch.log").open("w")
    launch = subprocess.Popen([
        "ros2", "launch", "usv_bringup", "vrx.launch.py", "world:=usv_calm",
        "headless:=True", "control_enabled:=false"], stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
    try:
        deadline = time.monotonic()+35
        while (len(odometry) < 30 or len(imu) < 30) and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
            if launch.poll() is not None:
                raise AssertionError(f"Launch exited; see {log_path / 'launch.log'}")
        assert len(odometry) >= 30 and len(imu) >= 30, (len(odometry), len(imu))
        initial = odometry[-1]
        assert abs(initial.pose.pose.position.z) < .02
        assert initial.child_frame_id == "wamv/base_link", initial.child_frame_id

        def thrust(tl, tr, seconds):
            deadline = time.monotonic()+seconds
            while time.monotonic() < deadline:
                left.publish(Float64(data=float(tl)))
                right.publish(Float64(data=float(tr)))
                rclpy.spin_once(node, timeout_sec=.05)
                time.sleep(.02)
            return odometry[-1]

        forward = thrust(5, 5, 12)
        assert .65 < forward.twist.twist.linear.x < 1.0, forward.twist.twist
        turning = thrust(-3, 3, 6)
        assert turning.twist.twist.angular.z > .05, turning.twist.twist
        thrust(0, 0, 1)
        result = {"odom_messages": len(odometry), "imu_messages": len(imu),
                  "initial_z": initial.pose.pose.position.z,
                  "forward_u_5N_each": forward.twist.twist.linear.x,
                  "positive_yaw_r": turning.twist.twist.angular.z,
                  "launch_log": str(log_path / "launch.log")}
        print(json.dumps(result, indent=2))
        (log_path / "result.json").write_text(json.dumps(result, indent=2)+"\n")
    finally:
        left.publish(Float64(data=0.0))
        right.publish(Float64(data=0.0))
        if launch.poll() is None:
            os.killpg(launch.pid, signal.SIGINT)
            try:
                launch.wait(timeout=12)
            except subprocess.TimeoutExpired:
                os.killpg(launch.pid, signal.SIGTERM)
                launch.wait(timeout=5)
        log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
