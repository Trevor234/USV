"""Gazebo Sim + SITL + MAVROS + USV nodes fallback launch for ROS 2 Jazzy.

This is a Gazebo Sim mirror/fallback stack. ArduPilot SITL still runs its
internal rover-skid physics (GAZEBO=0); Gazebo Sim visualizes a separate USV
model and receives mirrored force commands from /usv/cmd_force.
"""

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
    sim_share = get_package_share_directory("usv_simulation")
    install_root = os.path.dirname(os.path.dirname(os.path.dirname(sim_share)))
    bringup_share = os.path.join(install_root, "usv_bringup", "share", "usv_bringup")

    scheme_arg = DeclareLaunchArgument("scheme", default_value="B")
    fcu_url_arg = DeclareLaunchArgument("fcu_url", default_value="tcp://127.0.0.1:5760")
    gcs_url_arg = DeclareLaunchArgument("gcs_url", default_value="udp://@127.0.0.1:14550")
    auto_arm_arg = DeclareLaunchArgument("auto_arm", default_value="false")
    visualize_arg = DeclareLaunchArgument("visualize", default_value="true")
    headless_arg = DeclareLaunchArgument("headless", default_value="false")
    mavros_delay_arg = DeclareLaunchArgument("mavros_delay", default_value="8.0")
    nodes_delay_arg = DeclareLaunchArgument("nodes_delay", default_value="10.0")

    mavros_odom_topic_arg = DeclareLaunchArgument("mavros_odom_topic", default_value="/mavros/local_position/odom")
    mavros_state_topic_arg = DeclareLaunchArgument("mavros_state_topic", default_value="/mavros/state")
    mavros_imu_topic_arg = DeclareLaunchArgument("mavros_imu_topic", default_value="/mavros/imu/data")
    mavros_velocity_topic_arg = DeclareLaunchArgument("mavros_velocity_topic", default_value="/mavros/setpoint_velocity/cmd_vel")
    mavros_rc_override_topic_arg = DeclareLaunchArgument("mavros_rc_override_topic", default_value="/mavros/rc/override")
    mavros_rc_out_topic_arg = DeclareLaunchArgument("mavros_rc_out_topic", default_value="/mavros/rc/out")
    force_topic_arg = DeclareLaunchArgument("force_topic", default_value="/usv/cmd_force")
    entity_wrench_topic_arg = DeclareLaunchArgument("entity_wrench_topic", default_value="/world/lake_gz/wrench")
    gz_odom_topic_arg = DeclareLaunchArgument("gz_odom_topic", default_value="/model/usv_2m/odometry")

    scheme = LaunchConfiguration("scheme")
    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")
    visualize = LaunchConfiguration("visualize")
    mavros_delay = LaunchConfiguration("mavros_delay")
    nodes_delay = LaunchConfiguration("nodes_delay")
    mavros_odom_topic = LaunchConfiguration("mavros_odom_topic")
    mavros_state_topic = LaunchConfiguration("mavros_state_topic")
    mavros_imu_topic = LaunchConfiguration("mavros_imu_topic")
    mavros_velocity_topic = LaunchConfiguration("mavros_velocity_topic")
    mavros_rc_override_topic = LaunchConfiguration("mavros_rc_override_topic")
    mavros_rc_out_topic = LaunchConfiguration("mavros_rc_out_topic")
    force_topic = LaunchConfiguration("force_topic")
    entity_wrench_topic = LaunchConfiguration("entity_wrench_topic")
    gz_odom_topic = LaunchConfiguration("gz_odom_topic")

    gz_only = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("usv_simulation"), "launch", "gz_only.launch.py"])
        ),
        launch_arguments={"headless": LaunchConfiguration("headless")}.items(),
    )

    run_sitl_path = os.path.join(sim_share, "scripts", "run_sitl.sh")
    sitl_proc = ExecuteProcess(
        cmd=["bash", run_sitl_path],
        output="screen",
        additional_env={"GAZEBO": "0"},
    )

    mavros_node = TimerAction(
        period=mavros_delay,
        actions=[Node(
            package="mavros",
            executable="mavros_node",
            output="screen",
            parameters=[
                os.path.join(bringup_share, "config", "mavros_config.yaml"),
                {"fcu_url": fcu_url},
                {"gcs_url": gcs_url},
            ],
        )],
    )

    thrust_bridge = TimerAction(
        period=nodes_delay,
        actions=[Node(
            package="usv_simulation",
            executable="thrust_bridge",
            name="usv_thrust_bridge",
            output="screen",
            parameters=[{
                "rc_out_topic": mavros_rc_out_topic,
                "force_topic": force_topic,
                "left_channel": 0,
                "right_channel": 1,
            }],
        )],
    )

    force_to_wrench = TimerAction(
        period=nodes_delay,
        actions=[Node(
            package="usv_simulation",
            executable="cmd_force_to_entity_wrench",
            name="cmd_force_to_entity_wrench",
            output="screen",
            parameters=[{
                "cmd_force_topic": force_topic,
                "entity_wrench_topic": entity_wrench_topic,
                "entity_name": "usv_2m::base_link",
                "odom_topic": gz_odom_topic,
                "use_body_frame": True,
            }],
        )],
    )

    mpc_params = os.path.join(bringup_share, "config", "mpc_params.yaml")
    usv_params = os.path.join(bringup_share, "config", "usv_params.yaml")
    path_params = os.path.join(bringup_share, "config", "path_config.yaml")

    mpc_node = TimerAction(
        period=nodes_delay,
        actions=[Node(
            package="usv_mpc",
            executable="mpc_node",
            name="mpc_controller_node",
            output="screen",
            parameters=[mpc_params, usv_params, {
                "scheme": scheme,
                "odom_topic": mavros_odom_topic,
                "imu_topic": mavros_imu_topic,
                "path_topic": "/path/reference",
                "state_topic": mavros_state_topic,
                "velocity_topic": mavros_velocity_topic,
                "rc_override_topic": mavros_rc_override_topic,
            }],
        )],
    )

    planner_node = TimerAction(
        period=nodes_delay,
        actions=[Node(
            package="usv_planning",
            executable="path_planner_node",
            name="path_planner_node",
            output="screen",
            parameters=[path_params, {"odom_topic": mavros_odom_topic, "path_topic": "/path/reference"}],
        )],
    )

    safety_node = TimerAction(
        period=nodes_delay,
        actions=[Node(
            package="usv_safety",
            executable="mode_manager_node",
            name="mode_manager_node",
            output="screen",
            parameters=[{
                "auto_arm": LaunchConfiguration("auto_arm"),
                "auto_mode_switch": True,
                "state_topic": mavros_state_topic,
                "set_mode_service": "/mavros/set_mode",
                "arming_service": "/mavros/cmd/arming",
            }],
        )],
    )

    visualizer_node = TimerAction(
        period=nodes_delay,
        actions=[Node(
            package="usv_simulation",
            executable="visualizer",
            name="usv_visualizer",
            output="screen",
            condition=IfCondition(visualize),
            parameters=[{
                "odom_topic": mavros_odom_topic,
                "mavros_state_topic": mavros_state_topic,
                "cmd_vel_topic": mavros_velocity_topic,
                "rc_override_topic": mavros_rc_override_topic,
            }],
        )],
    )

    return LaunchDescription([
        scheme_arg, fcu_url_arg, gcs_url_arg, auto_arm_arg, visualize_arg, headless_arg,
        mavros_delay_arg, nodes_delay_arg,
        mavros_odom_topic_arg, mavros_state_topic_arg, mavros_imu_topic_arg,
        mavros_velocity_topic_arg, mavros_rc_override_topic_arg, mavros_rc_out_topic_arg,
        force_topic_arg, entity_wrench_topic_arg, gz_odom_topic_arg,
        gz_only,
        sitl_proc,
        mavros_node,
        thrust_bridge,
        force_to_wrench,
        mpc_node,
        planner_node,
        safety_node,
        visualizer_node,
    ])
