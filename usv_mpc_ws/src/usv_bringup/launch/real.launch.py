"""Real USV launch — full system with MicoAir743 hardware.

Launches ALL nodes:
  - MAVROS (UART connection to MicoAir743)
  - MPC controller
  - Path planner
  - Mode manager & safety monitor

Usage:
  ros2 launch usv_bringup real.launch.py
  ros2 launch usv_bringup real.launch.py scheme:=B
  ros2 launch usv_bringup real.launch.py gcs_url:=udp://@<gcs-ip>:14550
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    # Arguments
    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="A",
        description="Control scheme: A (kinematic) or B (dynamic)"
    )
    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url", default_value="/dev/ttyAMA10:921600",
        description="FCU serial connection URL"
    )
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="udp://@10.210.191.110:14550",
        description="Optional MAVLink GCS forwarding URL"
    )
    mavros_odom_topic_arg = DeclareLaunchArgument(
        "mavros_odom_topic", default_value="/mavros/local_position/odom",
        description="MAVROS odometry topic for planner and MPC"
    )
    mavros_state_topic_arg = DeclareLaunchArgument(
        "mavros_state_topic", default_value="/mavros/state",
        description="MAVROS state topic for mode manager and MPC"
    )
    mavros_imu_topic_arg = DeclareLaunchArgument(
        "mavros_imu_topic", default_value="/mavros/imu/data",
        description="MAVROS IMU topic used by the MPC node"
    )
    mavros_velocity_topic_arg = DeclareLaunchArgument(
        "mavros_velocity_topic", default_value="/mavros/setpoint_velocity/cmd_vel",
        description="MAVROS velocity command topic used by Scheme A"
    )
    mavros_rc_override_topic_arg = DeclareLaunchArgument(
        "mavros_rc_override_topic", default_value="/mavros/rc/override",
        description="MAVROS RC override topic used by Scheme B"
    )
    visualize_arg = DeclareLaunchArgument(
        "visualize", default_value="false",
        description="Start the matplotlib runtime visualizer",
    )
    profile_topic_arg = DeclareLaunchArgument(
        "profile_topic", default_value="/path/reference_profile",
        description="Reference speed/curvature/time profile topic used by MPC",
    )

    scheme = LaunchConfiguration("scheme")
    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")
    mavros_odom_topic = LaunchConfiguration("mavros_odom_topic")
    mavros_state_topic = LaunchConfiguration("mavros_state_topic")
    mavros_imu_topic = LaunchConfiguration("mavros_imu_topic")
    mavros_velocity_topic = LaunchConfiguration("mavros_velocity_topic")
    mavros_rc_override_topic = LaunchConfiguration("mavros_rc_override_topic")
    visualize = LaunchConfiguration("visualize")
    profile_topic = LaunchConfiguration("profile_topic")

    # Nodes
    mavros_node = Node(
        package="mavros",
        executable="mavros_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "mavros_config.yaml"),
            {"fcu_url": fcu_url},
            {"gcs_url": gcs_url},
        ],
        arguments=["--ros-args", "--log-level", "warn"],
    )

    safety_node = Node(
        package="usv_safety",
        executable="mode_manager_node",
        name="mode_manager_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "safety_params.yaml"),
            {
                "auto_arm": False,
                "auto_mode_switch": False,
                "state_topic": mavros_state_topic,
                "odom_topic": mavros_odom_topic,
                "battery_topic": "/mavros/battery",
                "path_topic": "/path/reference",
                "set_mode_service": "/mavros/set_mode",
                "arming_service": "/mavros/cmd/arming",
            },
        ],
    )

    planner_node = Node(
        package="usv_planning",
        executable="path_planner_node",
        name="path_planner_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "path_config.yaml"),
            {
                "odom_topic": mavros_odom_topic,
                "path_topic": "/path/reference",
                "profile_topic": profile_topic,
            },
        ],
    )

    mission_bridge_node = Node(
        package="usv_planning",
        executable="mission_bridge_node",
        name="mission_bridge_node",
        output="screen",
        parameters=[{
            "waypoints_topic": "/mavros/mission/waypoints",
            "origin_topic": "/mavros/global_position/gp_origin",
            "output_topic": "/usv/mission/waypoints_local",
            "pull_service": "/mavros/mission/pull",
            "auto_pull": True,
            "pull_interval": 2.0,
            "skip_home": True,
        }],
    )

    mpc_node = Node(
        package="usv_mpc",
        executable="mpc_node",
        name="mpc_controller_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "mpc_params.yaml"),
            os.path.join(bringup_dir, "config", "usv_params.yaml"),
            {
                "scheme": scheme,
                "odom_topic": mavros_odom_topic,
                "imu_topic": mavros_imu_topic,
                "path_topic": "/path/reference",
                "profile_topic": profile_topic,
                "state_topic": mavros_state_topic,
                "velocity_topic": mavros_velocity_topic,
                "rc_override_topic": mavros_rc_override_topic,
            },
        ],
    )

    visualizer_node = Node(
        package="usv_simulation",
        executable="visualizer",
        name="usv_visualizer",
        output="screen",
        condition=IfCondition(visualize),
        parameters=[{
            "odom_topic": mavros_odom_topic,
            "cmd_vel_topic": mavros_velocity_topic,
            "left_thrust_topic": "",
            "right_thrust_topic": "",
        }],
    )

    # Delayed start — let MAVROS connect first
    delayed_mpc = TimerAction(
        period=3.0,
        actions=[mpc_node],
    )

    return LaunchDescription([
        scheme_arg,
        fcu_url_arg,
        gcs_url_arg,
        mavros_odom_topic_arg,
        mavros_state_topic_arg,
        mavros_imu_topic_arg,
        mavros_velocity_topic_arg,
        mavros_rc_override_topic_arg,
        visualize_arg,
        profile_topic_arg,
        mavros_node,
        safety_node,
        planner_node,
        mission_bridge_node,
        delayed_mpc,
        visualizer_node,
    ])
