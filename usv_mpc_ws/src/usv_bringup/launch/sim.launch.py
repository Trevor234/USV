"""Pure simulation launch — no hardware required.

Launches:
  - usv_sim_node (6-DOF dynamics simulator)
  - mpc_controller_node (MPC solver)
  - path_planner_node (waypoint-to-path)
  - usv_visualizer (matplotlib display)

Usage:
  ros2 launch usv_bringup sim.launch.py
  ros2 launch usv_bringup sim.launch.py scheme:=B
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="A",
        description="Control scheme: A (kinematic) or B (dynamic)"
    )
    visualize_arg = DeclareLaunchArgument(
        "visualize", default_value="true",
        description="Start the matplotlib runtime visualizer",
    )
    odom_topic_arg = DeclareLaunchArgument(
        "odom_topic",
        default_value="/mavros/local_position/odom",
        description="Odometry topic published by the pure simulator and consumed by planner/MPC",
    )
    imu_topic_arg = DeclareLaunchArgument(
        "imu_topic",
        default_value="/mavros/imu/data",
        description="IMU topic published by the pure simulator and consumed by MPC",
    )
    state_topic_arg = DeclareLaunchArgument(
        "state_topic",
        default_value="/mavros/state",
        description="Simulated MAVROS state topic consumed by MPC and visualizer",
    )
    velocity_topic_arg = DeclareLaunchArgument(
        "velocity_topic",
        default_value="/mavros/setpoint_velocity/cmd_vel",
        description="Scheme A velocity command topic consumed by the pure simulator",
    )
    rc_override_topic_arg = DeclareLaunchArgument(
        "rc_override_topic",
        default_value="/mavros/rc/override",
        description="Scheme B RC override topic consumed by the pure simulator",
    )
    path_topic_arg = DeclareLaunchArgument(
        "path_topic",
        default_value="/path/reference",
        description="Reference path topic published by planner and consumed by MPC/visualizer",
    )
    mpc_status_topic_arg = DeclareLaunchArgument(
        "mpc_status_topic",
        default_value="/mpc/status",
        description="MPC status/diagnostic topic consumed by visualizer",
    )
    predicted_trajectory_topic_arg = DeclareLaunchArgument(
        "predicted_trajectory_topic",
        default_value="/mpc/predicted_trajectory",
        description="MPC predicted trajectory topic consumed by visualizer",
    )
    dynamic_waypoints_topic_arg = DeclareLaunchArgument(
        "dynamic_waypoints_topic",
        default_value="/usv/mission/waypoints_local",
        description="Dynamic waypoint path topic consumed by planner and visualizer",
    )
    path_frame_arg = DeclareLaunchArgument(
        "path_frame",
        default_value="map",
        description="Global frame used for odometry, reference paths, and MPC predictions",
    )
    body_frame_arg = DeclareLaunchArgument(
        "body_frame",
        default_value="base_link",
        description="USV body frame used for simulated odometry and IMU messages",
    )

    scheme = LaunchConfiguration("scheme")
    visualize = LaunchConfiguration("visualize")
    odom_topic = LaunchConfiguration("odom_topic")
    imu_topic = LaunchConfiguration("imu_topic")
    state_topic = LaunchConfiguration("state_topic")
    velocity_topic = LaunchConfiguration("velocity_topic")
    rc_override_topic = LaunchConfiguration("rc_override_topic")
    path_topic = LaunchConfiguration("path_topic")
    mpc_status_topic = LaunchConfiguration("mpc_status_topic")
    predicted_trajectory_topic = LaunchConfiguration("predicted_trajectory_topic")
    dynamic_waypoints_topic = LaunchConfiguration("dynamic_waypoints_topic")
    path_frame = LaunchConfiguration("path_frame")
    body_frame = LaunchConfiguration("body_frame")

    sim_node = Node(
        package="usv_simulation",
        executable="sim_node",
        name="usv_sim_node",
        output="screen",
        parameters=[
            {"dt": 0.05},
            {"publish_rate": 20.0},
            {"add_noise": True},
            {"noise_scale_pos": 0.05},
            {"x_init": 0.0, "y_init": 0.0, "psi_init": 0.0},
            {"u_init": 0.0, "v_init": 0.0, "r_init": 0.0},
            {
                "odom_topic": odom_topic,
                "imu_topic": imu_topic,
                "state_topic": state_topic,
                "velocity_topic": velocity_topic,
                "rc_override_topic": rc_override_topic,
                "map_frame": path_frame,
                "body_frame": body_frame,
            },
        ],
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
                "odom_topic": odom_topic,
                "imu_topic": imu_topic,
                "path_topic": path_topic,
                "state_topic": state_topic,
                "velocity_topic": velocity_topic,
                "rc_override_topic": rc_override_topic,
                "status_topic": mpc_status_topic,
                "predicted_trajectory_topic": predicted_trajectory_topic,
                "path_frame": path_frame,
                "body_frame": body_frame,
            },
        ],
    )

    path_config_file = os.path.join(bringup_dir, "config", "path_config.yaml")

    planner_node = Node(
        package="usv_planning",
        executable="path_planner_node",
        name="path_planner_node",
        output="screen",
        parameters=[
            path_config_file,
            {
                "odom_topic": odom_topic,
                "path_topic": path_topic,
                "dynamic_waypoints_topic": dynamic_waypoints_topic,
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
            "odom_topic": odom_topic,
            "path_topic": path_topic,
            "predicted_trajectory_topic": predicted_trajectory_topic,
            "mission_waypoints_topic": dynamic_waypoints_topic,
            "mpc_status_topic": mpc_status_topic,
            "mavros_state_topic": state_topic,
            "cmd_vel_topic": velocity_topic,
            "rc_override_topic": rc_override_topic,
        }],
    )

    return LaunchDescription([
        scheme_arg,
        visualize_arg,
        odom_topic_arg,
        imu_topic_arg,
        state_topic_arg,
        velocity_topic_arg,
        rc_override_topic_arg,
        path_topic_arg,
        mpc_status_topic_arg,
        predicted_trajectory_topic_arg,
        dynamic_waypoints_topic_arg,
        path_frame_arg,
        body_frame_arg,
        sim_node,
        mpc_node,
        planner_node,
        visualizer_node,
    ])
