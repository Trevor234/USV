"""Gazebo Sim only launch for ROS 2 Jazzy / ros_gz_sim."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    sim_share = get_package_share_directory("usv_simulation")

    world_arg = DeclareLaunchArgument(
        "world",
        default_value=os.path.join(sim_share, "worlds", "lake_gz.sdf"),
        description="Gazebo Sim world SDF",
    )
    model_arg = DeclareLaunchArgument(
        "model",
        default_value=os.path.join(sim_share, "models", "usv_2m", "model_gz.sdf"),
        description="Gazebo Sim USV model SDF",
    )
    bridge_config_arg = DeclareLaunchArgument(
        "bridge_config",
        default_value=os.path.join(sim_share, "config", "ros_gz_bridge_gz_sim.yaml"),
    )
    entity_name_arg = DeclareLaunchArgument("entity_name", default_value="usv_2m")
    x_arg = DeclareLaunchArgument("x", default_value="0.0")
    y_arg = DeclareLaunchArgument("y", default_value="0.0")
    z_arg = DeclareLaunchArgument("z", default_value="0.2")
    yaw_arg = DeclareLaunchArgument("yaw", default_value="0.0")
    paused_arg = DeclareLaunchArgument("paused", default_value="false")
    headless_arg = DeclareLaunchArgument("headless", default_value="false")
    verbose_arg = DeclareLaunchArgument("verbose", default_value="4")
    bridge_arg = DeclareLaunchArgument("bridge", default_value="true")
    rsp_arg = DeclareLaunchArgument("robot_state_publisher", default_value="true")

    world = LaunchConfiguration("world")
    model = LaunchConfiguration("model")
    bridge_config = LaunchConfiguration("bridge_config")
    entity_name = LaunchConfiguration("entity_name")
    paused = LaunchConfiguration("paused")
    headless = LaunchConfiguration("headless")
    verbose = LaunchConfiguration("verbose")

    set_resource_path = SetEnvironmentVariable(
        name="GZ_SIM_RESOURCE_PATH",
        value=[
            sim_share, ":",
            os.path.join(sim_share, "models"), ":",
            os.environ.get("GZ_SIM_RESOURCE_PATH", ""),
        ],
    )

    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("ros_gz_sim"), "launch", "gz_sim.launch.py"])
        ),
        launch_arguments={
            "gz_args": [
                "-v ", verbose, " ",
                PythonExpression(["'-s ' if '", headless, "' == 'true' else ''"]),
                PythonExpression(["'-r ' if '", paused, "' == 'false' else ''"]),
                world,
            ],
            "on_exit_shutdown": "true",
        }.items(),
    )

    spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("ros_gz_sim"), "launch", "gz_spawn_model.launch.py"])
        ),
        launch_arguments={
            "world": "lake_gz",
            "file": model,
            "entity_name": entity_name,
            "x": LaunchConfiguration("x"),
            "y": LaunchConfiguration("y"),
            "z": LaunchConfiguration("z"),
            "Y": LaunchConfiguration("yaw"),
        }.items(),
    )

    bridge = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("ros_gz_bridge"), "launch", "ros_gz_bridge.launch.py"])
        ),
        launch_arguments={
            "bridge_name": "ros_gz_bridge",
            "config_file": bridge_config,
            "use_composition": "False",
        }.items(),
        condition=IfCondition(LaunchConfiguration("bridge")),
    )

    urdf_xacro = os.path.join(sim_share, "urdf", "usv_2m.urdf.xacro")
    rsp = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="usv_state_publisher",
        output="screen",
        parameters=[{
            "robot_description": ParameterValue(
                Command([FindExecutable(name="xacro"), " ", urdf_xacro]),
                value_type=str,
            ),
        }],
        condition=IfCondition(LaunchConfiguration("robot_state_publisher")),
    )

    return LaunchDescription([
        world_arg, model_arg, bridge_config_arg, entity_name_arg,
        x_arg, y_arg, z_arg, yaw_arg, paused_arg, headless_arg, verbose_arg, bridge_arg, rsp_arg,
        set_resource_path,
        gz_sim,
        spawn,
        bridge,
        rsp,
    ])
