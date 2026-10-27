#!/usr/bin/env python3
"""Read the live P0 ROS graph and effective parameters before arming logging.

This helper subscribes for observations only. It never publishes thrust, changes
parameters, touches bag contents, or claims that a DDS subscription is plant ack.
Run with the ROS Jazzy interpreter and the same domain as the pilot.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time


DEFAULT_TYPES = {
    "/wamv/sensors/position/ground_truth_odometry": "nav_msgs/msg/Odometry",
    "/wamv/sensors/imu/imu/data": "sensor_msgs/msg/Imu",
    "/clock": "rosgraph_msgs/msg/Clock",
    "/path/reference": "nav_msgs/msg/Path",
    "/path/reference_profile": "std_msgs/msg/Float64MultiArray",
    "/wamv/thrusters/left/thrust": "std_msgs/msg/Float64",
    "/wamv/thrusters/right/thrust": "std_msgs/msg/Float64",
    "/mpc/status": "std_msgs/msg/String",
    "/mpc/predicted_trajectory": "nav_msgs/msg/Path",
    "/research/state_snapshot": "usv_research_interfaces/msg/StateSnapshot",
    "/research/control/applied": "usv_research_interfaces/msg/AppliedControl",
    "/research/cycle_timing": "usv_research_interfaces/msg/CycleTiming",
}


def endpoint_dict(info):
    qos = info.qos_profile
    return {
        "node_name": info.node_name,
        "node_namespace": info.node_namespace,
        "topic_type": info.topic_type,
        "endpoint_gid_hex": bytes(info.endpoint_gid).hex(),
        "qos": {
            "history": str(qos.history), "depth": qos.depth,
            "reliability": str(qos.reliability), "durability": str(qos.durability),
            "deadline_ns": qos.deadline.nanoseconds,
            "lifespan_ns": qos.lifespan.nanoseconds,
            "liveliness": str(qos.liveliness),
            "liveliness_lease_duration_ns": qos.liveliness_lease_duration.nanoseconds,
        },
    }


def graph_snapshot(node, topics):
    return {
        topic: {
            "expected_type": expected_type,
            "publishers": [endpoint_dict(x) for x in node.get_publishers_info_by_topic(topic)],
            "subscriptions": [endpoint_dict(x) for x in node.get_subscriptions_info_by_topic(topic)],
        }
        for topic, expected_type in topics.items()
    }


def graph_gate(graph, left_topic, right_topic, controller_name):
    reasons = []
    for topic, info in graph.items():
        publishers = info["publishers"]
        if not publishers:
            reasons.append("publisher_missing:" + topic)
        if any(x["topic_type"] != info["expected_type"] for x in publishers):
            reasons.append("unexpected_type:" + topic)
        recorders = [x for x in info["subscriptions"] if "rosbag2_recorder" in x["node_name"]]
        if len(recorders) != 1:
            reasons.append("recorder_subscription_count:" + topic + ":" + str(len(recorders)))
        elif recorders[0]["topic_type"] != info["expected_type"]:
            reasons.append("recorder_type_mismatch:" + topic)
        if topic.startswith("/research/"):
            if len(publishers) != 1 or publishers[0]["node_name"] != controller_name:
                reasons.append("research_publisher_identity:" + topic)
    for topic in (left_topic, right_topic):
        publishers = graph[topic]["publishers"]
        if len(publishers) != 1 or publishers[0]["node_name"] != controller_name:
            reasons.append("physical_publisher_identity:" + topic)
    return reasons


def read_boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return "unknown"


def command_capture(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        return {"command": command, "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "returncode": None, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bag-path", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--controller-name", default="mpc_controller_node")
    parser.add_argument("--wait-timeout", type=float, default=45.0)
    parser.add_argument("--odom-topic", default="/wamv/sensors/position/ground_truth_odometry")
    parser.add_argument("--imu-topic", default="/wamv/sensors/imu/imu/data")
    parser.add_argument("--left-topic", default="/wamv/thrusters/left/thrust")
    parser.add_argument("--right-topic", default="/wamv/thrusters/right/thrust")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    bag = args.bag_path.expanduser().resolve()
    if output.exists():
        parser.error("Refusing to overwrite an existing output")
    if output == bag or bag in output.parents:
        parser.error("Report output must be outside the original bag")
    if not output.parent.is_dir():
        parser.error("Output parent must already be an experiment evidence directory")
    if not 0 < args.wait_timeout <= 60:
        parser.error("wait-timeout must be in (0, 60] seconds")

    import rclpy
    from nav_msgs.msg import Odometry
    from rosgraph_msgs.msg import Clock
    from rclpy.qos import qos_profile_sensor_data

    topics = dict(DEFAULT_TYPES)
    for old, new in (
        ("/wamv/sensors/position/ground_truth_odometry", args.odom_topic),
        ("/wamv/sensors/imu/imu/data", args.imu_topic),
        ("/wamv/thrusters/left/thrust", args.left_topic),
        ("/wamv/thrusters/right/thrust", args.right_topic),
    ):
        topics[new] = topics.pop(old)
    rclpy.init()
    node = rclpy.create_node("p0_runtime_evidence_observer")
    odom_samples = []
    clock_samples = []

    def odom_callback(msg):
        if len(odom_samples) >= 5:
            return
        q = msg.pose.pose.orientation
        linear = msg.twist.twist.linear
        angular = msg.twist.twist.angular
        values = [msg.pose.pose.position.x, msg.pose.pose.position.y,
                  q.x, q.y, q.z, q.w, linear.x, linear.y, linear.z,
                  angular.x, angular.y, angular.z]
        valid = all(math.isfinite(x) for x in values)
        odom_samples.append({
            "stamp_ns": msg.header.stamp.sec * 1000000000 + msg.header.stamp.nanosec,
            "receive_steady_ns": time.monotonic_ns(),
            "frame_id": msg.header.frame_id, "child_frame_id": msg.child_frame_id,
            "pose_xy": values[:2] if valid else None,
            "quaternion_xyzw": values[2:6] if valid else None,
            "twist_linear_xyz": values[6:9] if valid else None,
            "twist_angular_xyz": values[9:12] if valid else None,
            "finite": valid,
            "quaternion_norm": math.sqrt(sum(x * x for x in values[2:6])) if valid else None,
            "twist_semantics_verified_by_this_observer": False,
        })

    def clock_callback(msg):
        if len(clock_samples) < 5:
            clock_samples.append({
                "sim_time_ns": msg.clock.sec * 1000000000 + msg.clock.nanosec,
                "receive_steady_ns": time.monotonic_ns(),
            })

    node.create_subscription(Odometry, args.odom_topic, odom_callback, qos_profile_sensor_data)
    node.create_subscription(Clock, "/clock", clock_callback, qos_profile_sensor_data)
    start = time.monotonic_ns()
    deadline = time.monotonic() + args.wait_timeout
    reasons = ["discovery_pending"]
    graph = {}
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
        graph = graph_snapshot(node, topics)
        reasons = graph_gate(graph, args.left_topic, args.right_topic, args.controller_name)
        if not reasons and len(odom_samples) >= 5 and clock_samples:
            break
    if len(odom_samples) < 5:
        reasons.append("insufficient_observed_odom_samples")
    if not clock_samples:
        reasons.append("clock_not_observed")
    names = [{"name": name, "namespace": namespace} for name, namespace in node.get_node_names_and_namespaces()]
    node.destroy_node()
    rclpy.shutdown()
    parameter_dump = command_capture(["ros2", "param", "dump", "--no-daemon", "--spin-time", "2", "--timeout", "8", "/" + args.controller_name])
    if parameter_dump["returncode"] != 0:
        reasons.append("runtime_parameter_dump_failed")
    parameter_dump["stdout_sha256"] = hashlib.sha256(parameter_dump.get("stdout", "").encode()).hexdigest()
    prefixes = {package: command_capture(["ros2", "pkg", "prefix", package])
                for package in ("usv_mpc_cpp", "usv_bringup", "usv_research_interfaces")}
    result = {
        "schema_version": "p0-runtime-context-v1",
        "run_id": args.run_id, "baseline_id": args.baseline_id,
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "observer_boot_id": read_boot_id(), "observer_pid": os.getpid(),
        "observer_start_steady_ns": start, "observer_end_steady_ns": time.monotonic_ns(),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "default"),
        "gazebo_partition": os.environ.get("GZ_PARTITION", "default"),
        "bag_path": str(bag), "nodes": names, "topics": graph,
        "odom_samples": odom_samples, "clock_samples": clock_samples,
        "effective_parameter_dump": parameter_dump, "installed_package_prefixes": prefixes,
        "recorder_graph_ready": not reasons, "reasons": reasons,
        "runtime_effective_verified": parameter_dump["returncode"] == 0,
        "recorder_data_completeness_verified": False,
        "plant_acceptance_observed": False, "force_measured": False,
        "execution_atomicity_proven": False, "gp_labels_ready": False,
    }
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(output), "recorder_graph_ready": not reasons, "reasons": reasons}))
    return 0 if not reasons else 1


if __name__ == "__main__":
    raise SystemExit(main())
