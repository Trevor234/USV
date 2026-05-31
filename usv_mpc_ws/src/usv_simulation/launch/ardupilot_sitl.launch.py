"""ArduPilot SITL only — runs sim_vehicle.py + MAVROS, no Gazebo.

Useful for verifying that the ArduRover firmware boots, accepts the
boat-mode parameters, and exposes a usable MAVLink interface to MAVROS,
independent of any 3D simulation.

Usage:
  ros2 launch usv_simulation ardupilot_sitl.launch.py
  ros2 launch usv_simulation ardupilot_sitl.launch.py mavros:=false
  ros2 launch usv_simulation ardupilot_sitl.launch.py use_gazebo:=true

Verification:
  ros2 topic echo /mavros/state          # connected:true after a few seconds
  mavproxy.py --master=tcp:127.0.0.1:5762 --console
    > mode GUIDED
    > arm throttle
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    sim_share = get_package_share_directory("usv_simulation")
    install_root = os.path.dirname(os.path.dirname(os.path.dirname(sim_share)))
    bringup_share = os.path.join(install_root, "usv_bringup", "share", "usv_bringup")
    run_sitl_path = os.path.join(sim_share, "scripts", "run_sitl.sh")

    # ---- arguments ----
    mavros_arg = DeclareLaunchArgument(
        "mavros", default_value="true",
        description="Whether to also start a MAVROS node",
    )
    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url", default_value="tcp://127.0.0.1:5760",
        description="MAVLink connection URL (sim_vehicle.py exposes 5760)",
    )
    use_gazebo_arg = DeclareLaunchArgument(
        "use_gazebo", default_value="false",
        description="If true, SITL runs with --frame=JSON to talk to Gazebo",
    )
    mavros_delay_arg = DeclareLaunchArgument(
        "mavros_delay", default_value="3.0",
        description="Seconds to wait before starting MAVROS so SITL opens TCP 5760",
    )

    fcu_url = LaunchConfiguration("fcu_url")
    use_gazebo = LaunchConfiguration("use_gazebo")
    mavros_delay = LaunchConfiguration("mavros_delay")

    # ---- ArduPilot SITL: two mutually-exclusive ExecuteProcess actions
    # because launch substitutions can't be used inside additional_env. ----
    sitl_internal = ExecuteProcess(
        cmd=["bash", run_sitl_path],
        output="screen",
        additional_env={"GAZEBO": "0"},
        condition=UnlessCondition(use_gazebo),
    )
    sitl_json = ExecuteProcess(
        cmd=["bash", run_sitl_path],
        output="screen",
        additional_env={"GAZEBO": "1"},
        condition=IfCondition(use_gazebo),
    )

    # ---- MAVROS ----
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="udp://@127.0.0.1:14550",
        description="Optional local GCS forwarding URL for SITL",
    )
    gcs_url = LaunchConfiguration("gcs_url")

    mavros_node = TimerAction(
        period=mavros_delay,
        actions=[Node(
            package="mavros",
            executable="mavros_node",
            output="screen",
            condition=IfCondition(LaunchConfiguration("mavros")),
            parameters=[
                os.path.join(bringup_share, "config", "mavros_config.yaml"),
                {"fcu_url": fcu_url},
                {"gcs_url": gcs_url},
            ],
        )],
    )

    return LaunchDescription([
        mavros_arg, fcu_url_arg, gcs_url_arg, use_gazebo_arg, mavros_delay_arg,
        sitl_internal, sitl_json,
        mavros_node,
    ])
