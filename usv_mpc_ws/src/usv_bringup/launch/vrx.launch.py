"""Real VRX Gazebo Sim + WAM-V + MPC Scheme B validation launch."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bringup_share = get_package_share_directory("usv_bringup")
    vrx_urdf_share = get_package_share_directory("wamv_gazebo")

    world_arg = DeclareLaunchArgument("world", default_value="sydney_regatta")
    headless_arg = DeclareLaunchArgument("headless", default_value="False")
    paused_arg = DeclareLaunchArgument("paused", default_value="False")
    waypoints_file_arg = DeclareLaunchArgument("waypoints_file", default_value="")
    record_bag_arg = DeclareLaunchArgument("record_bag", default_value="false")
    bag_dir_arg = DeclareLaunchArgument(
        "bag_dir",
        default_value=PathJoinSubstitution([EnvironmentVariable("HOME"), "usv_vrx_logs"]),
        description="Directory for optional VRX rosbag recordings",
    )
    run_id_arg = DeclareLaunchArgument("run_id", default_value="vrx_scheme_b_run")

    odom_topic_arg = DeclareLaunchArgument(
        "odom_topic", default_value="/wamv/sensors/position/ground_truth_odometry"
    )
    imu_topic_arg = DeclareLaunchArgument(
        "imu_topic", default_value="/wamv/sensors/imu/imu/data"
    )
    left_thrust_topic_arg = DeclareLaunchArgument(
        "left_thrust_topic", default_value="/wamv/thrusters/left/thrust"
    )
    right_thrust_topic_arg = DeclareLaunchArgument(
        "right_thrust_topic", default_value="/wamv/thrusters/right/thrust"
    )
    path_topic_arg = DeclareLaunchArgument("path_topic", default_value="/path/reference")
    mpc_status_topic_arg = DeclareLaunchArgument("mpc_status_topic", default_value="/mpc/status")
    predicted_trajectory_topic_arg = DeclareLaunchArgument(
        "predicted_trajectory_topic", default_value="/mpc/predicted_trajectory"
    )
    dynamic_waypoints_topic_arg = DeclareLaunchArgument(
        "dynamic_waypoints_topic", default_value="/usv/mission/waypoints_local"
    )
    path_frame_arg = DeclareLaunchArgument("path_frame", default_value="map")
    body_frame_arg = DeclareLaunchArgument("body_frame", default_value="base_link")

    world = LaunchConfiguration("world")
    headless = LaunchConfiguration("headless")
    paused = LaunchConfiguration("paused")
    waypoints_file = LaunchConfiguration("waypoints_file")
    record_bag = LaunchConfiguration("record_bag")
    bag_dir = LaunchConfiguration("bag_dir")
    run_id = LaunchConfiguration("run_id")
    odom_topic = LaunchConfiguration("odom_topic")
    imu_topic = LaunchConfiguration("imu_topic")
    left_thrust_topic = LaunchConfiguration("left_thrust_topic")
    right_thrust_topic = LaunchConfiguration("right_thrust_topic")
    path_topic = LaunchConfiguration("path_topic")
    mpc_status_topic = LaunchConfiguration("mpc_status_topic")
    predicted_trajectory_topic = LaunchConfiguration("predicted_trajectory_topic")
    dynamic_waypoints_topic = LaunchConfiguration("dynamic_waypoints_topic")
    path_frame = LaunchConfiguration("path_frame")
    body_frame = LaunchConfiguration("body_frame")

    wamv_urdf = os.path.join(vrx_urdf_share, "urdf", "wamv_gazebo.urdf.xacro")

    vrx = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("vrx_gz"), "launch", "competition.launch.py"])
        ),
        launch_arguments={
            "world": world,
            "sim_mode": "full",
            "bridge_competition_topics": "True",
            "name": "wamv",
            "model": "wam-v",
            "urdf": wamv_urdf,
            "headless": headless,
            "paused": paused,
        }.items(),
    )

    mpc_params = os.path.join(bringup_share, "config", "mpc_params.yaml")
    mpc_overlay = os.path.join(bringup_share, "config", "mpc_params_vrx_scheme_b.yaml")
    usv_params = os.path.join(bringup_share, "config", "usv_params.yaml")
    path_params = os.path.join(bringup_share, "config", "path_config.yaml")

    planner_node = TimerAction(
        period=8.0,
        actions=[Node(
            package="usv_planning",
            executable="path_planner_node",
            name="path_planner_node",
            output="screen",
            parameters=[path_params, {
                "odom_topic": odom_topic,
                "path_topic": path_topic,
                "dynamic_waypoints_topic": dynamic_waypoints_topic,
                "waypoints_file": waypoints_file,
            }],
        )],
    )

    mpc_node = TimerAction(
        period=9.0,
        actions=[Node(
            package="usv_mpc",
            executable="mpc_node",
            name="mpc_controller_node",
            output="screen",
            parameters=[mpc_params, usv_params, mpc_overlay, {
                "scheme": "B",
                "control_mode": "dynamic",
                "output_mode": "vrx_thrust",
                "require_fcu_state": False,
                "odom_topic": odom_topic,
                "imu_topic": imu_topic,
                "path_topic": path_topic,
                "status_topic": mpc_status_topic,
                "predicted_trajectory_topic": predicted_trajectory_topic,
                "path_frame": path_frame,
                "body_frame": body_frame,
                "vrx_left_thrust_topic": left_thrust_topic,
                "vrx_right_thrust_topic": right_thrust_topic,
            }],
        )],
    )

    bag_record = ExecuteProcess(
        cmd=[
            "ros2", "bag", "record",
            "-o", PathJoinSubstitution([bag_dir, run_id]),
            odom_topic,
            imu_topic,
            left_thrust_topic,
            right_thrust_topic,
            path_topic,
            mpc_status_topic,
            predicted_trajectory_topic,
        ],
        output="screen",
        condition=IfCondition(record_bag),
    )

    return LaunchDescription([
        world_arg,
        headless_arg,
        paused_arg,
        waypoints_file_arg,
        record_bag_arg,
        bag_dir_arg,
        run_id_arg,
        odom_topic_arg,
        imu_topic_arg,
        left_thrust_topic_arg,
        right_thrust_topic_arg,
        path_topic_arg,
        mpc_status_topic_arg,
        predicted_trajectory_topic_arg,
        dynamic_waypoints_topic_arg,
        path_frame_arg,
        body_frame_arg,
        vrx,
        planner_node,
        mpc_node,
        bag_record,
    ])
