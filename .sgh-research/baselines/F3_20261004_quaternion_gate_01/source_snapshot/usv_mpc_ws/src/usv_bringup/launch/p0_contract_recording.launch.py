"""Opt-in P0 publisher contract recording around the existing Scheme B launch.

The recorder remains alive when the controller exits. The runner must stop the
controller first, verify the source session summary, then stop this launch.
"""

import os
import re

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    run_id = value("research_run_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
        raise RuntimeError("research_run_id must be a unique path-safe identifier")
    baseline_id = value("research_baseline_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", baseline_id):
        raise RuntimeError("research_baseline_id must identify a frozen manifest")
    if not re.fullmatch(r"[0-9a-f]{64}", value("research_config_hash")):
        raise RuntimeError("research_config_hash must be a SHA256 of declared configuration inputs")
    if not value("bag_path") or not value("research_output_dir"):
        raise RuntimeError("Explicit fresh bag_path and research_output_dir are required")
    bag_path = os.path.abspath(os.path.expanduser(value("bag_path")))
    output_dir = os.path.abspath(os.path.expanduser(value("research_output_dir")))
    if os.path.lexists(bag_path):
        raise RuntimeError("Refusing existing bag path: " + bag_path)
    if os.path.lexists(output_dir):
        raise RuntimeError("Refusing existing research output directory: " + output_dir)
    if os.path.commonpath([bag_path, output_dir]) in (bag_path, output_dir):
        raise RuntimeError("Bag and research output directory must be separate siblings")
    reference = os.path.abspath(os.path.expanduser(value("waypoints_file")))
    if not os.path.isfile(reference):
        raise RuntimeError("An existing, frozen waypoints_file is required")
    share = get_package_share_directory("usv_bringup")
    forwarded = (
        "world", "headless", "paused", "vehicle_config", "simulation_config",
        "model_output_dir", "waypoints_file", "odom_topic", "imu_topic",
        "left_thrust_topic", "right_thrust_topic", "path_topic", "profile_topic",
        "mpc_status_topic", "predicted_trajectory_topic", "path_frame",
        "research_run_id", "research_baseline_id", "research_config_hash",
        "research_expected_pose_frame", "research_expected_child_frame",
        "research_frame_contract_verified",
    )
    launch_args = {name: value(name) for name in forwarded}
    # These arguments are deliberately fixed; this entry point records dynamic B.
    launch_args.update({
        "scheme": "B", "control_enabled": "true", "visualize": "false",
        "record_bag": "false", "enable_research_logging": "true",
        "research_logging_armed": "false",
        "research_output_dir": output_dir,
    })
    include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, "launch", "vrx.launch.py")),
        launch_arguments=launch_args.items(),
    )
    topics = [value(name) for name in (
        "odom_topic", "imu_topic", "left_thrust_topic", "right_thrust_topic",
        "path_topic", "profile_topic", "mpc_status_topic", "predicted_trajectory_topic",
    )] + ["/clock", "/research/state_snapshot", "/research/control/applied", "/research/cycle_timing"]
    recorder = ExecuteProcess(
        cmd=["ros2", "bag", "record", "--storage", "mcap", "-o", bag_path] + topics,
        output="screen",
        sigterm_timeout="15", sigkill_timeout="15",
    )
    # No on-exit hook tears down the recorder when mpc_node stops. This permits
    # controller shutdown events and the observation queue to reach rosbag first.
    return [recorder, include]


def generate_launch_description():
    share = get_package_share_directory("usv_bringup")
    simulation_share = get_package_share_directory("usv_simulation")
    defaults = {
        "world": "sydney_regatta", "headless": "true", "paused": "false",
        "vehicle_config": os.path.join(share, "config", "usv_params_sim.yaml"),
        "simulation_config": os.path.join(simulation_share, "config", "vrx_model.yaml"),
        "model_output_dir": "", "waypoints_file": "",
        "bag_path": "", "research_output_dir": "", "research_run_id": "",
        "research_baseline_id": "", "research_config_hash": "",
        "research_expected_pose_frame": "", "research_expected_child_frame": "",
        "research_frame_contract_verified": "false",
        "odom_topic": "/wamv/sensors/position/ground_truth_odometry",
        "imu_topic": "/wamv/sensors/imu/imu/data",
        "left_thrust_topic": "/wamv/thrusters/left/thrust",
        "right_thrust_topic": "/wamv/thrusters/right/thrust",
        "path_topic": "/path/reference", "profile_topic": "/path/reference_profile",
        "mpc_status_topic": "/mpc/status",
        "predicted_trajectory_topic": "/mpc/predicted_trajectory", "path_frame": "map",
    }
    args = [DeclareLaunchArgument(name, default_value=default) for name, default in defaults.items()]
    return LaunchDescription(args + [OpaqueFunction(function=_setup)])
