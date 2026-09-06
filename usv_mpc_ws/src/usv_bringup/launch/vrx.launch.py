"""VRX Gazebo Sim + MPC Scheme B (C++ 动力学 NMPC) validation launch.

MPC 节点为 usv_mpc_cpp (C++ NMPC, output_mode=vrx_thrust 直接发布推力),
参数 = mpc_params.yaml (基础) + usv_params_sim.yaml (30 kg 仿真船) +
mpc_params_vrx.yaml (VRX overlay)。实机参数 (usv_params.yaml) 不用于仿真。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bringup_share = get_package_share_directory("usv_bringup")
    vrx_urdf_share = get_package_share_directory("wamv_gazebo")

    world_arg = DeclareLaunchArgument("world", default_value="sydney_regatta")
    headless_arg = DeclareLaunchArgument("headless", default_value="False")
    paused_arg = DeclareLaunchArgument("paused", default_value="False")
    waypoints_file_arg = DeclareLaunchArgument("waypoints_file", default_value="")
    visualize_arg = DeclareLaunchArgument(
        "visualize",
        default_value="false",
        description="Start the matplotlib runtime visualizer",
    )
    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="B", choices=["A", "B"],
        description="A=运动学 MPC(cmd_vel→推力转换) B=动力学 NMPC(直接推力)")
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
    profile_topic_arg = DeclareLaunchArgument(
        "profile_topic", default_value="/path/reference_profile"
    )
    mpc_status_topic_arg = DeclareLaunchArgument("mpc_status_topic", default_value="/mpc/status")
    predicted_trajectory_topic_arg = DeclareLaunchArgument(
        "predicted_trajectory_topic", default_value="/mpc/predicted_trajectory"
    )
    dynamic_waypoints_topic_arg = DeclareLaunchArgument(
        "dynamic_waypoints_topic", default_value="/usv/mission/waypoints_local"
    )
    path_frame_arg = DeclareLaunchArgument("path_frame", default_value="map")

    world = LaunchConfiguration("world")
    headless = LaunchConfiguration("headless")
    paused = LaunchConfiguration("paused")
    waypoints_file = LaunchConfiguration("waypoints_file")
    visualize = LaunchConfiguration("visualize")
    record_bag = LaunchConfiguration("record_bag")
    bag_dir = LaunchConfiguration("bag_dir")
    run_id = LaunchConfiguration("run_id")
    scheme = LaunchConfiguration("scheme")
    odom_topic = LaunchConfiguration("odom_topic")
    imu_topic = LaunchConfiguration("imu_topic")
    left_thrust_topic = LaunchConfiguration("left_thrust_topic")
    right_thrust_topic = LaunchConfiguration("right_thrust_topic")
    path_topic = LaunchConfiguration("path_topic")
    profile_topic = LaunchConfiguration("profile_topic")
    mpc_status_topic = LaunchConfiguration("mpc_status_topic")
    predicted_trajectory_topic = LaunchConfiguration("predicted_trajectory_topic")
    dynamic_waypoints_topic = LaunchConfiguration("dynamic_waypoints_topic")
    path_frame = LaunchConfiguration("path_frame")

    # Single-hull USV model. It reuses the WAM-V thruster/sensor/buoyancy
    # plugins via xacro includes (so /wamv/... topics are unchanged) but spawns
    # one hull instead of the catamaran. vrx_urdf_share is kept above so the
    # wamv_gazebo macros it includes are guaranteed on the package path.
    wamv_urdf = os.path.join(
        get_package_share_directory("usv_simulation"), "urdf", "usv_mono.urdf.xacro"
    )

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
    mpc_params_a = os.path.join(bringup_share, "config", "mpc_params_A.yaml")
    usv_params_sim = os.path.join(bringup_share, "config", "usv_params_sim.yaml")
    mpc_overlay = os.path.join(bringup_share, "config", "mpc_params_vrx.yaml")
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
                "profile_topic": profile_topic,
                "dynamic_waypoints_topic": dynamic_waypoints_topic,
                "waypoints_file": waypoints_file,
            }],
        )],
    )

    is_scheme_a = PythonExpression(["'", scheme, "' == 'A'"])
    is_scheme_b = PythonExpression(["'", scheme, "' == 'B'"])

    # 方案 B: 动力学 NMPC, 推力 1:1 直发 (现有路径)
    mpc_node_b = TimerAction(
        period=9.0,
        actions=[Node(
            package="usv_mpc_cpp",
            executable="mpc_node",
            name="mpc_controller_node",
            output="screen",
            condition=IfCondition(is_scheme_b),
            parameters=[mpc_params, usv_params_sim, mpc_overlay, {
                "odom_topic": odom_topic,
                "imu_topic": imu_topic,
                "path_topic": path_topic,
                "profile_topic": profile_topic,
                "status_topic": mpc_status_topic,
                "predicted_trajectory_topic": predicted_trajectory_topic,
                "path_frame": path_frame,
                "vrx_left_thrust_topic": left_thrust_topic,
                "vrx_right_thrust_topic": right_thrust_topic,
            }],
        )],
    )

    # 方案 A: 运动学 MPC (cmd_vel) + cmdvel→推力转换内环
    # (转换节点用辨识参数做逆模型: drag/yaw 前馈 + 速率反馈, 50Hz)
    kin_node = TimerAction(
        period=9.0,
        actions=[Node(
            package="usv_mpc_kinematic_cpp",
            executable="mpc_node",
            name="mpc_controller_node",
            output="screen",
            condition=IfCondition(is_scheme_a),
            parameters=[mpc_params_a, {
                "scheme": "A",
                "control_mode": "kinematic",
                "require_fcu_state": False,
                "odom_topic": odom_topic,
                "imu_topic": imu_topic,
                "path_topic": path_topic,
                "profile_topic": profile_topic,
                "status_topic": mpc_status_topic,
                "predicted_trajectory_topic": predicted_trajectory_topic,
                "path_frame": path_frame,
                "velocity_topic": "/usv/cmd_vel",
            }],
        ),
        Node(
            package="usv_simulation",
            executable="cmdvel_to_thrust",
            name="cmdvel_to_thrust",
            output="screen",
            condition=IfCondition(is_scheme_a),
            parameters=[{
                "cmd_vel_topic": "/usv/cmd_vel",
                "odom_topic": odom_topic,
                "left_thrust_topic": left_thrust_topic,
                "right_thrust_topic": right_thrust_topic,
                "d_thruster": 0.25,
                "xu": 2.272, "xuu": 11.572,
                "nr": 3.105, "nrr": 0.71,
                "t_max": 25.0,
            }],
        )],
    )

    visualizer_node = TimerAction(
        period=10.0,
        actions=[Node(
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
                "left_thrust_topic": left_thrust_topic,
                "right_thrust_topic": right_thrust_topic,
                # 方案 A 的 u/r 指令显示 (方案 B 不发布 cmd_vel, 显示 NO DATA)
                "cmd_vel_topic": "/usv/cmd_vel",
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
            profile_topic,
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
        visualize_arg,
        record_bag_arg,
        bag_dir_arg,
        run_id_arg,
        odom_topic_arg,
        imu_topic_arg,
        left_thrust_topic_arg,
        right_thrust_topic_arg,
        path_topic_arg,
        profile_topic_arg,
        mpc_status_topic_arg,
        predicted_trajectory_topic_arg,
        dynamic_waypoints_topic_arg,
        path_frame_arg,
        vrx,
        scheme_arg,
        planner_node,
        mpc_node_b,
        kin_node,
        visualizer_node,
        bag_record,
    ])
