"""Full Gazebo + ArduPilot SITL + MAVROS + USV nodes integration launch.

This is the end-to-end workflow described in the implementation plan §八.3.5.
On launch, you should see (in order):

  1. Gazebo Classic GUI with the lake world and the usv_2m model floating
  2. sim_vehicle.py (ArduRover) booting and connecting to Gazebo over UDP
     ports 9002/9003 (JSON FDM)
  3. MAVROS connecting to SITL on tcp://127.0.0.1:5760
  4. mpc_node, path_planner_node, mode_manager_node coming up

Once /mavros/state shows connected:true and mode:MANUAL, switch to GUIDED:

  ros2 service call /mavros/set_mode mavros_msgs/srv/SetMode \\
       "{custom_mode: 'GUIDED'}"
  ros2 service call /mavros/cmd/arming mavros_msgs/srv/CommandBool \\
       "{value: true}"

The boat should start tracking the path published by path_planner_node.

Usage:
  ros2 launch usv_simulation gazebo_sitl_full.launch.py
  ros2 launch usv_simulation gazebo_sitl_full.launch.py scheme:=B  # NMPC
  ros2 launch usv_simulation gazebo_sitl_full.launch.py vrx_enabled:=true

Arguments:
  scheme       A | B | both                (default A)
  gui          true | false                 (default true)
  paused       true | false                 (default false; set true to inspect)
  vrx_enabled  true | false                 (default false; requires VRX plugins
               built via external/build_vrx_plugins.sh — when true, switches
               to lake_vrx.world + model_vrx.sdf which activate
               libusv_gazebo_dynamics_plugin and the Wavefield plugins)
  world        override path to .world file
  model        override path to model .sdf file
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
    PythonExpression,
)
from launch.conditions import IfCondition
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    sim_share = get_package_share_directory("usv_simulation")
    install_root = os.path.dirname(os.path.dirname(os.path.dirname(sim_share)))
    bringup_share = os.path.join(install_root, "usv_bringup", "share", "usv_bringup")

    # ----------------------- Arguments -----------------------
    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="A",
        description="MPC scheme: A (kinematic) | B (dynamic) | both",
    )
    gui_arg = DeclareLaunchArgument("gui", default_value="true")
    paused_arg = DeclareLaunchArgument("paused", default_value="false")
    verbose_arg = DeclareLaunchArgument("verbose", default_value="true")
    vrx_enabled_arg = DeclareLaunchArgument(
        "vrx_enabled", default_value="false",
        description=(
            "If true, spawn lake_vrx.world + model_vrx.sdf which activate "
            "libusv_gazebo_dynamics_plugin (Fossen) and Wavefield plugins. "
            "Requires VRX plugins on GAZEBO_PLUGIN_PATH (see "
            "external/build_vrx_plugins.sh)."
        ),
    )
    # If user does not override `world`/`model`, derive them from vrx_enabled
    # via PythonExpression below. Explicit overrides still win.
    world_arg = DeclareLaunchArgument(
        "world",
        default_value=PythonExpression([
            "'", os.path.join(sim_share, "worlds", "lake_vrx.world"),
            "' if '", LaunchConfiguration("vrx_enabled"),
            "' == 'true' else '",
            os.path.join(sim_share, "worlds", "lake.world"), "'",
        ]),
    )
    model_arg = DeclareLaunchArgument(
        "model",
        default_value=PythonExpression([
            "'", os.path.join(sim_share, "models", "usv_2m", "model_vrx.sdf"),
            "' if '", LaunchConfiguration("vrx_enabled"),
            "' == 'true' else '",
            os.path.join(sim_share, "models", "usv_2m", "model.sdf"), "'",
        ]),
    )
    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url", default_value="tcp://127.0.0.1:5760",
    )
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="udp://@127.0.0.1:14550",
        description="Optional local GCS forwarding URL for SITL",
    )
    auto_arm_arg = DeclareLaunchArgument(
        "auto_arm", default_value="false",
        description="Have mode_manager auto-arm and switch to GUIDED on boot",
    )
    visualize_arg = DeclareLaunchArgument(
        "visualize", default_value="true",
        description="Start the matplotlib runtime visualizer",
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
    mavros_rc_out_topic_arg = DeclareLaunchArgument(
        "mavros_rc_out_topic", default_value="/mavros/rc/out",
        description="MAVROS RC output topic used by thrust bridge",
    )
    force_topic_arg = DeclareLaunchArgument(
        "force_topic", default_value="/usv/cmd_force",
        description="Gazebo Wrench topic consumed by libgazebo_ros_force.so",
    )

    scheme = LaunchConfiguration("scheme")
    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")
    paused = LaunchConfiguration("paused")
    verbose = LaunchConfiguration("verbose")
    world = LaunchConfiguration("world")
    model = LaunchConfiguration("model")
    visualize = LaunchConfiguration("visualize")
    mavros_odom_topic = LaunchConfiguration("mavros_odom_topic")
    mavros_state_topic = LaunchConfiguration("mavros_state_topic")
    mavros_imu_topic = LaunchConfiguration("mavros_imu_topic")
    mavros_velocity_topic = LaunchConfiguration("mavros_velocity_topic")
    mavros_rc_override_topic = LaunchConfiguration("mavros_rc_override_topic")
    mavros_rc_out_topic = LaunchConfiguration("mavros_rc_out_topic")
    force_topic = LaunchConfiguration("force_topic")

    # ----------------------- Environment -----------------------
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

    # Plugin path — prepend the ArduPilot Gazebo plugin and optional VRX plugin
    # directory, then preserve any user-provided GAZEBO_PLUGIN_PATH entries.
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

    # ----------------------- Gazebo -----------------------
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
        launch_arguments={"verbose": verbose}.items(),
    )

    spawn_usv = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        name="spawn_usv",
        output="screen",
        arguments=[
            "-entity", "usv_2m",
            "-file", model,
            "-x", "0", "-y", "0", "-z", "0.05",
            "-Y", "0",
        ],
    )

    # ----------------------- TF / robot_state_publisher -----------------------
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

    # ----------------------- ArduPilot SITL -----------------------
    # Started with a small delay so Gazebo+ArduPilot plugin is ready to
    # receive the JSON FDM connection on port 9002.
    run_sitl_path = os.path.join(sim_share, "scripts", "run_sitl.sh")
    sitl_proc = TimerAction(
        period=4.0,
        actions=[ExecuteProcess(
            cmd=["bash", run_sitl_path],
            output="screen",
            additional_env={"GAZEBO": "1"},
        )],
    )

    # ----------------------- MAVROS -----------------------
    # Wait until SITL has had time to come up (~6s).
    mavros_node = TimerAction(
        period=8.0,
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

    # ----------------------- Thrust bridge -----------------------
    # Converts /mavros/rc/out PWM into /usv/cmd_force (Wrench), consumed by
    # libgazebo_ros_force.so in model.sdf.
    thrust_bridge = TimerAction(
        period=9.0,
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

    # ----------------------- USV nodes (existing, unchanged) -----------------------
    mpc_params = os.path.join(bringup_share, "config", "mpc_params.yaml")
    usv_params = os.path.join(bringup_share, "config", "usv_params.yaml")
    path_params = os.path.join(bringup_share, "config", "path_config.yaml")

    mpc_node = TimerAction(
        period=10.0,
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
        period=10.0,
        actions=[Node(
            package="usv_planning",
            executable="path_planner_node",
            name="path_planner_node",
            output="screen",
            parameters=[path_params, {
                "odom_topic": mavros_odom_topic,
                "path_topic": "/path/reference",
            }],
        )],
    )

    safety_node = TimerAction(
        period=10.0,
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
        period=12.0,
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
        # args
        scheme_arg, gui_arg, paused_arg, verbose_arg, vrx_enabled_arg,
        world_arg, model_arg, fcu_url_arg, gcs_url_arg, auto_arm_arg, visualize_arg,
        mavros_odom_topic_arg, mavros_state_topic_arg, mavros_imu_topic_arg,
        mavros_velocity_topic_arg, mavros_rc_override_topic_arg,
        mavros_rc_out_topic_arg, force_topic_arg,
        ardupilot_plugin_dir_arg, vrx_plugin_dir_arg,
        # env
        set_model_path, set_plugin_path, set_resource_path,
        # gazebo
        gzserver, gzclient, spawn_usv, rsp,
        # ArduPilot
        sitl_proc,
        # ROS 2 nodes
        mavros_node, thrust_bridge, mpc_node, planner_node, safety_node, visualizer_node,
    ])
