"""VRX simulation launch — WAM-V + MPC validation, no hardware required.

This wrapper makes the generic simulation entry point use the same VRX stack as
vrx.launch.py. The old in-package dynamics simulator has been retired.

Usage:
  ros2 launch usv_bringup sim.launch.py
  ros2 launch usv_bringup sim.launch.py world:=sydney_regatta headless:=False

注意 (Pi5 实机部署):
  本工作区为树莓派 5 实机部署, 未安装 Gazebo / VRX / ArduPilot SITL。
  本 launch 文件保留自开发工作区 (usv_mpc_ws), 在 Pi 上**无法运行**;
  实机请使用 `real.launch.py`。若需要仿真验证, 请在开发机上执行。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    world_arg = DeclareLaunchArgument("world", default_value="sydney_regatta")
    headless_arg = DeclareLaunchArgument("headless", default_value="False")
    paused_arg = DeclareLaunchArgument("paused", default_value="False")
    waypoints_file_arg = DeclareLaunchArgument("waypoints_file", default_value="")
    visualize_arg = DeclareLaunchArgument(
        "visualize",
        default_value="true",
        description="Start the matplotlib runtime visualizer",
    )
    record_bag_arg = DeclareLaunchArgument("record_bag", default_value="false")
    profile_topic_arg = DeclareLaunchArgument(
        "profile_topic", default_value="/path/reference_profile"
    )
    bag_dir_arg = DeclareLaunchArgument(
        "bag_dir",
        default_value=PathJoinSubstitution([EnvironmentVariable("HOME"), "USV", "usv_vrx_logs"]),
        description="Directory for optional VRX rosbag recordings",
    )
    run_id_arg = DeclareLaunchArgument("run_id", default_value="vrx_scheme_b_run")

    vrx_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("usv_bringup"), "launch", "vrx.launch.py"])
        ),
        launch_arguments={
            "world": LaunchConfiguration("world"),
            "headless": LaunchConfiguration("headless"),
            "paused": LaunchConfiguration("paused"),
            "waypoints_file": LaunchConfiguration("waypoints_file"),
            "visualize": LaunchConfiguration("visualize"),
            "record_bag": LaunchConfiguration("record_bag"),
            "profile_topic": LaunchConfiguration("profile_topic"),
            "bag_dir": LaunchConfiguration("bag_dir"),
            "run_id": LaunchConfiguration("run_id"),
        }.items(),
    )

    return LaunchDescription([
        world_arg,
        headless_arg,
        paused_arg,
        waypoints_file_arg,
        visualize_arg,
        record_bag_arg,
        profile_topic_arg,
        bag_dir_arg,
        run_id_arg,
        vrx_launch,
    ])
