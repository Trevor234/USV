"""MAVROS-only launch — test MAVLink communication with MicoAir743.

Usage:
  ros2 launch usv_bringup mavros.launch.py
  ros2 launch usv_bringup mavros.launch.py gcs_url:=udp://@<gcs-ip>:14550
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url", default_value="/dev/ttyTHS1:921600",
        description="FCU serial connection URL"
    )
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="tcp-l://:14550",
        description="Optional MAVLink GCS forwarding URL"
    )

    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")

    mavros_node = Node(
        package="mavros",
        executable="mavros_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "mavros_config.yaml"),
            {"fcu_url": fcu_url},
            {"gcs_url": gcs_url},
        ],
        arguments=["--ros-args", "--log-level", "info"],
    )

    return LaunchDescription([
        fcu_url_arg,
        gcs_url_arg,
        mavros_node,
    ])
