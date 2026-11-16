"""仅启动 MAVROS — 用于测试与 AET-H743-AIR-PRO 飞控的 MAVLink 通信。

用法:
  ros2 launch usv_bringup mavros.launch.py
  ros2 launch usv_bringup mavros.launch.py gcs_url:=udp://@<gcs-ip>:14550
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from usv_bringup.launch_guard import create_launch_guard_action


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url", default_value="/dev/ttyAMA10:921600",
        description="FCU serial connection URL"
    )
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="",
        description="Optional MAVLink GCS forwarding URL"
    )
    configure_rates_arg = DeclareLaunchArgument(
        "configure_rates", default_value="true",
        description="自动启动 MAVLink 消息流频动态配置节点 (IMU 20Hz, Odom 10Hz)",
        choices=["true", "false"],
    )
    force_arg = DeclareLaunchArgument(
        "force", default_value="false",
        description="强制忽略防重复启动与串口占用检查 (高风险，仅供排障)",
        choices=["true", "false"],
    )

    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")
    configure_rates = LaunchConfiguration("configure_rates")

    guard_action = create_launch_guard_action(
        fcu_url_config_name="fcu_url",
        force_config_name="force",
        service_name="usv-system.service",
        lock_name="usv_mavros",
    )

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

    rate_configurator_node = Node(
        package="usv_bringup",
        executable="mavros_rate_configurator",
        name="mavros_rate_configurator",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "mavros_rates.yaml"),
        ],
        condition=IfCondition(configure_rates),
    )

    return LaunchDescription([
        fcu_url_arg,
        gcs_url_arg,
        configure_rates_arg,
        force_arg,
        guard_action,
        mavros_node,
        rate_configurator_node,
    ])
