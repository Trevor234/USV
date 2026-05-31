"""Gazebo-only launch — bring up Gazebo Classic with the lake world and
spawn the USV model.  Useful for quickly iterating on the SDF model and
world geometry without ArduPilot or the rest of the ROS 2 stack.

Usage:
  ros2 launch usv_simulation gazebo_only.launch.py
  ros2 launch usv_simulation gazebo_only.launch.py paused:=true gui:=true

What you should see:
  - Gazebo GUI opens with a blue water plane
  - usv_2m model floats roughly at z = 0
  - /usv/imu/data, /usv/gps/fix, /usv/camera/image_raw, /usv/scan topics
    appear once Gazebo is fully loaded
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
    PythonExpression,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    sim_share = get_package_share_directory("usv_simulation")

    paused_arg = DeclareLaunchArgument("paused", default_value="false")
    gui_arg = DeclareLaunchArgument("gui", default_value="true")
    verbose_arg = DeclareLaunchArgument("verbose", default_value="true")
    vrx_enabled_arg = DeclareLaunchArgument(
        "vrx_enabled", default_value="false",
        description=(
            "If true, use lake_vrx.world + model_vrx.sdf which activate the "
            "VRX hydrodynamics + wavefield plugins. Requires VRX plugins on "
            "GAZEBO_PLUGIN_PATH (see external/build_vrx_plugins.sh)."
        ),
    )
    world_arg = DeclareLaunchArgument(
        "world",
        default_value=PythonExpression([
            "'", os.path.join(sim_share, "worlds", "lake_vrx.world"),
            "' if '", LaunchConfiguration("vrx_enabled"),
            "' == 'true' else '",
            os.path.join(sim_share, "worlds", "lake.world"), "'",
        ]),
        description="Absolute path to the .world file",
    )
    model_arg = DeclareLaunchArgument(
        "model",
        default_value=PythonExpression([
            "'", os.path.join(sim_share, "models", "usv_2m", "model_vrx.sdf"),
            "' if '", LaunchConfiguration("vrx_enabled"),
            "' == 'true' else '",
            os.path.join(sim_share, "models", "usv_2m", "model.sdf"), "'",
        ]),
        description="Absolute path to the spawned model SDF",
    )
    spawn_x = DeclareLaunchArgument("x", default_value="0.0")
    spawn_y = DeclareLaunchArgument("y", default_value="0.0")
    spawn_z = DeclareLaunchArgument("z", default_value="0.05")
    spawn_yaw = DeclareLaunchArgument("yaw", default_value="0.0")

    paused = LaunchConfiguration("paused")
    gui = LaunchConfiguration("gui")
    verbose = LaunchConfiguration("verbose")
    world = LaunchConfiguration("world")
    model = LaunchConfiguration("model")

    # Make sure Gazebo can find usv_simulation/models/* via GAZEBO_MODEL_PATH.
    # Also append the VRX models if vrx is in the workspace.
    set_model_path = SetEnvironmentVariable(
        name="GAZEBO_MODEL_PATH",
        value=[
            os.path.join(sim_share, "models"), ":",
            os.environ.get("GAZEBO_MODEL_PATH", ""),
        ],
    )
    ardupilot_plugin_dir_arg = DeclareLaunchArgument(
        "ardupilot_plugin_dir",
        default_value=os.environ.get(
            "ARDUPILOT_GAZEBO_PLUGIN_DIR",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(sim_share))),
                "ardupilot_sitl_gazebo", "lib", "ardupilot_sitl_gazebo", "plugins",
            ),
        ),
        description="Directory containing libArduPilotPlugin.so",
    )
    vrx_plugin_dir_arg = DeclareLaunchArgument(
        "vrx_plugin_dir",
        default_value=os.environ.get(
            "VRX_PLUGIN_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(sim_share))), "vrx_plugins_install", "lib"),
        ),
        description="Directory containing optional VRX Gazebo plugins",
    )
    ardupilot_plugin_dir = LaunchConfiguration("ardupilot_plugin_dir")
    vrx_plugin_dir = LaunchConfiguration("vrx_plugin_dir")

    # Plugin path — prepend ArduPilot Gazebo and optional VRX plugin dirs, then
    # preserve any user-provided GAZEBO_PLUGIN_PATH entries.
    set_plugin_path = SetEnvironmentVariable(
        name="GAZEBO_PLUGIN_PATH",
        value=[
            ardupilot_plugin_dir, ":",
            vrx_plugin_dir, ":",
            os.environ.get("GAZEBO_PLUGIN_PATH", ""),
        ],
    )
    # Gazebo resource path — include system share so shaders/media are found.
    _gazebo_share = "/usr/share/gazebo-11"
    set_resource_path = SetEnvironmentVariable(
        name="GAZEBO_RESOURCE_PATH",
        value=[
            _gazebo_share, ":",
            os.path.join(_gazebo_share, "media"), ":",
            os.environ.get("GAZEBO_RESOURCE_PATH", ""),
        ],
    )

    # ---- Gazebo server + client ----
    gzserver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("gazebo_ros"), "launch", "gzserver.launch.py",
            ])
        ),
        launch_arguments={
            "world": world,
            "verbose": verbose,
            "pause": paused,
        }.items(),
    )

    gzclient = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("gazebo_ros"), "launch", "gzclient.launch.py",
            ])
        ),
        condition=None,  # always start client unless gui:=false (handled by env)
        launch_arguments={"verbose": verbose}.items(),
    )

    # ---- Spawn USV model ----
    spawn_usv = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        name="spawn_usv",
        output="screen",
        arguments=[
            "-entity", "usv_2m",
            "-file", model,
            "-x", LaunchConfiguration("x"),
            "-y", LaunchConfiguration("y"),
            "-z", LaunchConfiguration("z"),
            "-Y", LaunchConfiguration("yaw"),
        ],
    )

    # ---- robot_state_publisher (so /tf has the URDF tree) ----
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
    )

    return LaunchDescription([
        paused_arg, gui_arg, verbose_arg, vrx_enabled_arg, world_arg, model_arg,
        ardupilot_plugin_dir_arg, vrx_plugin_dir_arg,
        spawn_x, spawn_y, spawn_z, spawn_yaw,
        set_model_path, set_plugin_path, set_resource_path,
        gzserver, gzclient,
        spawn_usv,
        rsp,
    ])
