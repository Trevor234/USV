"""Real VRX Gazebo Sim + WAM-V + MPC Scheme B validation launch."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
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
    bag_dir_arg = DeclareLaunchArgument("bag_dir", default_value="/home/trevor/USV/usv_vrx_logs")
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
                "path_topic": "/path/reference",
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
                "path_topic": "/path/reference",
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
            "/path/reference",
            "/mpc/status",
            "/mpc/predicted_trajectory",
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
        vrx,
        planner_node,
        mpc_node,
        bag_record,
    ])
