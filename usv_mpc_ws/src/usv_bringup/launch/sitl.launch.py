"""SITL (Software In The Loop) launch — ArduRover SITL + MAVROS + MPC.

By default this assumes ArduRover SITL is **already running** and just connects
to it via TCP (the original behaviour). Set `use_gazebo:=true` to instead
delegate the SITL + Gazebo bring-up to usv_simulation/gazebo_sitl_full.launch.py
so a single command starts everything (Gazebo + sim_vehicle.py + MAVROS + MPC).

Prerequisites (when use_gazebo:=false):
  ros2 launch usv_simulation ardupilot_sitl.launch.py use_gazebo:=false mavros:=false
  # The project wrapper starts sim_vehicle.py with --no-mavproxy, so MAVROS
  # connects directly to tcp://127.0.0.1:5760. If you instead start a manual
  # sim_vehicle.py session with MAVProxy, override fcu_url:=tcp://127.0.0.1:5762.

Usage:
  ros2 launch usv_bringup sitl.launch.py                     # external SITL
  ros2 launch usv_bringup sitl.launch.py use_gazebo:=true    # full Gazebo stack
  ros2 launch usv_bringup sitl.launch.py scheme:=B
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="A",
        description="Control scheme: A (kinematic) or B (dynamic)"
    )
    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url", default_value="tcp://127.0.0.1:5760",
        description="SITL MAVLink endpoint. The project run_sitl.sh uses "
                    "--no-mavproxy, so MAVROS connects directly to 5760. "
                    "Use tcp://127.0.0.1:5762 only for an external MAVProxy setup."
    )
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="udp://@127.0.0.1:14550",
        description="Optional local GCS forwarding URL for SITL"
    )
    use_gazebo_arg = DeclareLaunchArgument(
        "use_gazebo", default_value="false",
        description="If true, also launch Gazebo + sim_vehicle.py via "
                    "usv_simulation/gazebo_sitl_full.launch.py",
    )
    visualize_arg = DeclareLaunchArgument(
        "visualize", default_value="true",
        description="Start the matplotlib runtime visualizer",
    )
    auto_mode_switch_arg = DeclareLaunchArgument(
        "auto_mode_switch", default_value="false",
        description="Automatically switch the FCU to GUIDED. Keep false for Scheme B RC override tests.",
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
        description="MAVROS RC output topic used by thrust bridge and visualizer",
    )

    scheme = LaunchConfiguration("scheme")
    fcu_url = LaunchConfiguration("fcu_url")
    gcs_url = LaunchConfiguration("gcs_url")
    use_gazebo = LaunchConfiguration("use_gazebo")
    visualize = LaunchConfiguration("visualize")
    auto_mode_switch = LaunchConfiguration("auto_mode_switch")
    mavros_odom_topic = LaunchConfiguration("mavros_odom_topic")
    mavros_state_topic = LaunchConfiguration("mavros_state_topic")
    mavros_imu_topic = LaunchConfiguration("mavros_imu_topic")
    mavros_velocity_topic = LaunchConfiguration("mavros_velocity_topic")
    mavros_rc_override_topic = LaunchConfiguration("mavros_rc_override_topic")
    mavros_rc_out_topic = LaunchConfiguration("mavros_rc_out_topic")

    # ===== Path A: external SITL — start MAVROS + nodes only =====
    mavros_node = Node(
        package="mavros",
        executable="mavros_node",
        output="screen",
        condition=UnlessCondition(use_gazebo),
        parameters=[
            os.path.join(bringup_dir, "config", "mavros_config.yaml"),
            {"fcu_url": fcu_url},
            {"gcs_url": gcs_url},
        ],
    )

    mpc_node = Node(
        package="usv_mpc",
        executable="mpc_node",
        name="mpc_controller_node",
        output="screen",
        condition=UnlessCondition(use_gazebo),
        parameters=[
            os.path.join(bringup_dir, "config", "mpc_params.yaml"),
            os.path.join(bringup_dir, "config", "usv_params.yaml"),
            {
                "scheme": scheme,
                "control_mode": PythonExpression(["'dynamic' if '", scheme, "' == 'B' else 'kinematic'"]),
                "allowed_fcu_modes": PythonExpression(["['MANUAL'] if '", scheme, "' == 'B' else ['GUIDED']"]),
                "odom_topic": mavros_odom_topic,
                "imu_topic": mavros_imu_topic,
                "path_topic": "/path/reference",
                "state_topic": mavros_state_topic,
                "velocity_topic": mavros_velocity_topic,
                "rc_override_topic": mavros_rc_override_topic,
            },
        ],
    )

    planner_node = Node(
        package="usv_planning",
        executable="path_planner_node",
        name="path_planner_node",
        output="screen",
        condition=UnlessCondition(use_gazebo),
        parameters=[
            os.path.join(bringup_dir, "config", "path_config.yaml"),
            {
                "odom_topic": mavros_odom_topic,
                "path_topic": "/path/reference",
            },
        ],
    )

    safety_node = Node(
        package="usv_safety",
        executable="mode_manager_node",
        name="mode_manager_node",
        output="screen",
        condition=UnlessCondition(use_gazebo),
        parameters=[{
            "auto_arm": False,
            "auto_mode_switch": auto_mode_switch,
            "state_topic": mavros_state_topic,
            "set_mode_service": "/mavros/set_mode",
            "arming_service": "/mavros/cmd/arming",
        }],
    )

    visualizer_node = Node(
        package="usv_simulation",
        executable="visualizer",
        name="usv_visualizer",
        output="screen",
        condition=IfCondition(PythonExpression([
            "'", visualize, "' == 'true' and '", use_gazebo, "' == 'false'"
        ])),
        parameters=[{
            "odom_topic": mavros_odom_topic,
            "mavros_state_topic": mavros_state_topic,
            "cmd_vel_topic": mavros_velocity_topic,
            "rc_override_topic": mavros_rc_override_topic,
        }],
    )

    # ===== Path B: full Gazebo stack — delegate to usv_simulation =====
    gazebo_full = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("usv_simulation"),
                "launch",
                "gazebo_sitl_full.launch.py",
            ])
        ),
        launch_arguments={
            "scheme": scheme,
            "fcu_url": fcu_url,
            "gcs_url": gcs_url,
            "visualize": visualize,
            "mavros_odom_topic": mavros_odom_topic,
            "mavros_state_topic": mavros_state_topic,
            "mavros_imu_topic": mavros_imu_topic,
            "mavros_velocity_topic": mavros_velocity_topic,
            "mavros_rc_override_topic": mavros_rc_override_topic,
            "mavros_rc_out_topic": mavros_rc_out_topic,
        }.items(),
        condition=IfCondition(use_gazebo),
    )

    return LaunchDescription([
        scheme_arg,
        fcu_url_arg,
        gcs_url_arg,
        use_gazebo_arg,
        visualize_arg,
        auto_mode_switch_arg,
        mavros_odom_topic_arg,
        mavros_state_topic_arg,
        mavros_imu_topic_arg,
        mavros_velocity_topic_arg,
        mavros_rc_override_topic_arg,
        mavros_rc_out_topic_arg,
        # Path A (external SITL)
        mavros_node,
        mpc_node,
        planner_node,
        safety_node,
        visualizer_node,
        # Path B (Gazebo full stack)
        gazebo_full,
    ])
