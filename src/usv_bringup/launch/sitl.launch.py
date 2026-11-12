"""External ArduRover SITL launch — MAVROS + MPC without Gazebo bring-up.

Gazebo-based project simulation has been retired in favor of VRX/WAM-V. Use
`ros2 launch usv_bringup sim.launch.py` or `vrx.launch.py` for simulation.

Prerequisites:
  Start ArduRover SITL externally and expose a MAVLink TCP endpoint.

Usage:
  ros2 launch usv_bringup sitl.launch.py                # scheme A (运动学, Python)
  ros2 launch usv_bringup sitl.launch.py scheme:=B      # scheme B (C++ NMPC, RC override)

注意 (Pi5 实机部署):
  本工作区为树莓派 5 实机部署, 未安装 Gazebo / VRX / ArduPilot SITL。
  本 launch 文件保留自开发工作区 (usv_mpc_ws), 在 Pi 上**无法运行**;
  实机请使用 `real.launch.py`。若需要仿真验证, 请在开发机上执行。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="A",
        description="Control scheme: A (kinematic) or B (dynamic)",
    )
    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url",
        default_value="tcp://127.0.0.1:5760",
        description="External SITL MAVLink endpoint for MAVROS",
    )
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="udp://@127.0.0.1:14550",
        description="Optional local GCS forwarding URL for SITL",
    )
    visualize_arg = DeclareLaunchArgument(
        "visualize", default_value="true",
        description="Start the matplotlib runtime visualizer",
    )
    auto_mode_switch_arg = DeclareLaunchArgument(
        "auto_mode_switch", default_value="false",
        description="Automatically switch the FCU to the mode the MPC requires "
                    "(A=GUIDED, B=MANUAL). Keep false for Scheme B RC override tests.",
    )

    mavros_odom_topic_arg = DeclareLaunchArgument(
        "mavros_odom_topic", default_value="/mavros/local_position/odom",
        description="MAVROS odometry topic for planner and MPC",
    )
    mavros_state_topic_arg = DeclareLaunchArgument(
        "mavros_state_topic", default_value="/mavros/state",
        description="MAVROS state topic for mode manager and MPC",
    )
    mavros_imu_topic_arg = DeclareLaunchArgument(
        "mavros_imu_topic", default_value="/mavros/imu/data",
        description="MAVROS IMU topic used by the MPC node",
    )
    mavros_velocity_topic_arg = DeclareLaunchArgument(
        "mavros_velocity_topic", default_value="/mavros/setpoint_velocity/cmd_vel",
        description="MAVROS velocity command topic used by Scheme A",
    )
    mavros_rc_override_topic_arg = DeclareLaunchArgument(
        "mavros_rc_override_topic", default_value="/mavros/rc/override",
        description="MAVROS RC override topic used by Scheme B",
    )
    profile_topic_arg = DeclareLaunchArgument(
        "profile_topic", default_value="/path/reference_profile",
        description="Reference speed/curvature/time profile topic used by MPC",
    )

    scheme = LaunchConfiguration("scheme")
    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")
    visualize = LaunchConfiguration("visualize")
    auto_mode_switch = LaunchConfiguration("auto_mode_switch")
    mavros_odom_topic = LaunchConfiguration("mavros_odom_topic")
    mavros_state_topic = LaunchConfiguration("mavros_state_topic")
    mavros_imu_topic = LaunchConfiguration("mavros_imu_topic")
    mavros_velocity_topic = LaunchConfiguration("mavros_velocity_topic")
    mavros_rc_override_topic = LaunchConfiguration("mavros_rc_override_topic")
    profile_topic = LaunchConfiguration("profile_topic")

    mavros_node = Node(
        package="mavros",
        executable="mavros_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "mavros_config.yaml"),
            {"fcu_url": fcu_url},
            {"gcs_url": gcs_url},
        ],
    )

    # 方案 A: C++ 运动学 MPC (usv_mpc_kinematic_cpp, mpc_params_A.yaml);
    # 方案 B: C++ 动力学 NMPC (usv_mpc_cpp, mpc_params_B.yaml + 仿真船参数)。
    # 与 real.launch.py 的 scheme 映射保持一致, 便于 SITL 预演实机行为。
    # (Python 方案 A 包 usv_mpc 已于 2026-09-06 删除, 方案 A 恒为 C++。)
    mpc_node_a = Node(
        package="usv_mpc_kinematic_cpp",
        executable="mpc_node",
        name="mpc_controller_node",
        output="screen",
        condition=IfCondition(PythonExpression(["'", scheme, "' == 'A'"])),
        parameters=[
            os.path.join(bringup_dir, "config", "mpc_params_A.yaml"),
            {
                "scheme": "A",
                "control_mode": "kinematic",
                "odom_topic": mavros_odom_topic,
                "imu_topic": mavros_imu_topic,
                "path_topic": "/path/reference",
                "profile_topic": profile_topic,
                "state_topic": mavros_state_topic,
                "velocity_topic": mavros_velocity_topic,
            },
        ],
    )

    mpc_node_b = Node(
        package="usv_mpc_cpp",
        executable="mpc_node",
        name="mpc_controller_node",
        output="screen",
        condition=IfCondition(PythonExpression(["'", scheme, "' == 'B'"])),
        parameters=[
            os.path.join(bringup_dir, "config", "mpc_params_B.yaml"),
            os.path.join(bringup_dir, "config", "usv_params_sim.yaml"),
            {
                "control_mode": "dynamic",
                "odom_topic": mavros_odom_topic,
                "imu_topic": mavros_imu_topic,
                "path_topic": "/path/reference",
                "profile_topic": profile_topic,
                "state_topic": mavros_state_topic,
                "rc_override_topic": mavros_rc_override_topic,
            },
        ],
    )

    planner_node = Node(
        package="usv_planning_cpp",
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

    safety_node = Node(
        package="usv_safety_cpp",
        executable="mode_manager_node",
        name="mode_manager_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "safety_params.yaml"),
            {
                "auto_arm": False,
                "auto_mode_switch": auto_mode_switch,
                "state_topic": mavros_state_topic,
                "odom_topic": mavros_odom_topic,
                "battery_topic": "/mavros/battery",
                "path_topic": "/path/reference",
                "set_mode_service": "/mavros/set_mode",
                "arming_service": "/mavros/cmd/arming",
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

    return LaunchDescription([
        scheme_arg,
        fcu_url_arg,
        gcs_url_arg,
        visualize_arg,
        auto_mode_switch_arg,
        mavros_odom_topic_arg,
        mavros_state_topic_arg,
        mavros_imu_topic_arg,
        mavros_velocity_topic_arg,
        mavros_rc_override_topic_arg,
        profile_topic_arg,
        mavros_node,
        mpc_node_a,
        mpc_node_b,
        planner_node,
        safety_node,
        visualizer_node,
    ])
