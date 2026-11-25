"""Opt-in dynamic B recording with independent nominal and plant sources.

Nominal input bypasses the physical renderer. The existing renderer receives
only the separate plant snapshot. Reference/prediction logging is observational.
"""

import os
import re

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from usv_bringup.research_config_sources import prepare_config_sources


def _absolute(value):
    return os.path.abspath(os.path.expanduser(value))


def _setup(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    for name in ("research_run_id", "research_baseline_id"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value(name)):
            raise RuntimeError(name + " must be a unique path-safe identifier")
    if not re.fullmatch(r"[0-9a-f]{64}", value("research_config_hash")):
        raise RuntimeError("research_config_hash must bind all declared configuration inputs")
    for name in ("bag_path", "research_output_dir", "model_output_dir", "config_output_dir"):
        if not value(name):
            raise RuntimeError("Explicit fresh " + name + " is required")
    directories = {name: _absolute(value(name)) for name in (
        "bag_path", "research_output_dir", "model_output_dir", "config_output_dir")}
    for name, path in directories.items():
        if os.path.lexists(path):
            raise RuntimeError("Refusing existing " + name + ": " + path)
        if not os.path.isdir(os.path.dirname(path)):
            raise RuntimeError("Create the experiment parent before launching: " + path)
    paths = list(directories.values())
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            if os.path.commonpath([a, b]) in (a, b):
                raise RuntimeError("Bag/source/model/config output directories must be separate siblings")
    reference = _absolute(value("waypoints_file"))
    if not os.path.isfile(reference):
        raise RuntimeError("An existing frozen waypoints_file is required")
    enable_reference = value("enable_reference_prediction_logging").lower()
    if enable_reference not in ("true", "false"):
        raise RuntimeError("enable_reference_prediction_logging must be true or false")
    report = prepare_config_sources(
        value("nominal_vehicle_config"), value("plant_vehicle_config"),
        value("simulation_config"), directories["config_output_dir"])
    nominal_hash = report["nominal_effective_sha256"]
    requested_hash = value("research_nominal_config_hash")
    if requested_hash and requested_hash != nominal_hash:
        raise RuntimeError("research_nominal_config_hash does not match frozen nominal effective YAML")
    share = get_package_share_directory("usv_bringup")
    forwarded = (
        "world", "headless", "paused", "waypoints_file", "odom_topic", "imu_topic",
        "left_thrust_topic", "right_thrust_topic", "path_topic", "profile_topic",
        "mpc_status_topic", "predicted_trajectory_topic", "path_frame",
        "research_run_id", "research_baseline_id", "research_config_hash",
        "research_expected_pose_frame", "research_expected_child_frame",
        "research_frame_contract_verified",
    )
    launch_args = {name: value(name) for name in forwarded}
    launch_args.update({
        "scheme": "B", "control_enabled": "true", "visualize": "false",
        "record_bag": "false", "enable_research_logging": "true",
        "research_logging_armed": "false",
        "research_output_dir": directories["research_output_dir"],
        "model_output_dir": directories["model_output_dir"],
        "vehicle_config": report["snapshot_paths"]["plant_input"],
        "simulation_config": report["snapshot_paths"]["simulation_input"],
        "controller_vehicle": report["snapshot_paths"]["nominal_effective"],
        "controller_tmax": str(report["solver_input_constraints"]["T_max"]),
        "controller_tmin": str(report["solver_input_constraints"]["T_min"]),
        "enable_reference_prediction_logging": enable_reference,
        "research_nominal_config_hash": nominal_hash,
    })
    include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, "launch", "vrx.launch.py")),
        launch_arguments=launch_args.items())
    topics = [value(name) for name in (
        "odom_topic", "imu_topic", "left_thrust_topic", "right_thrust_topic",
        "path_topic", "profile_topic", "mpc_status_topic", "predicted_trajectory_topic",
    )] + ["/clock", "/research/state_snapshot", "/research/control/applied",
          "/research/cycle_timing", "/research/reference_prediction"]
    recorder = ExecuteProcess(
        cmd=["ros2", "bag", "record", "--storage", "mcap", "-o", directories["bag_path"]] + topics,
        output="screen", sigterm_timeout="15", sigkill_timeout="15")
    return [recorder, include]


def generate_launch_description():
    share = get_package_share_directory("usv_bringup")
    simulation_share = get_package_share_directory("usv_simulation")
    defaults = {
        "world": "sydney_regatta", "headless": "true", "paused": "false",
        "nominal_vehicle_config": os.path.join(share, "config", "p0_nominal_f3.yaml"),
        "plant_vehicle_config": os.path.join(share, "config", "p0_plant_f3.yaml"),
        "simulation_config": os.path.join(simulation_share, "config", "vrx_model.yaml"),
        "model_output_dir": "", "config_output_dir": "", "waypoints_file": "",
        "bag_path": "", "research_output_dir": "", "research_run_id": "",
        "research_baseline_id": "", "research_config_hash": "",
        "research_nominal_config_hash": "", "enable_reference_prediction_logging": "true",
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
