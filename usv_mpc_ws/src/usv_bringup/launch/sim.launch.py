"""Pure simulation launch — no hardware required.

Launches:
  - usv_sim_node (6-DOF dynamics simulator)
  - mpc_controller_node (MPC solver)
  - path_planner_node (waypoint-to-path)
  - usv_visualizer (matplotlib display)

Usage:
  ros2 launch usv_bringup sim.launch.py
  ros2 launch usv_bringup sim.launch.py scheme:=B
"""

import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="A",
        description="Control scheme: A (kinematic) or B (dynamic)"
    )
    visualize_arg = DeclareLaunchArgument(
        "visualize", default_value="true",
        description="Start the matplotlib runtime visualizer",
    )

    scheme = LaunchConfiguration("scheme")
    visualize = LaunchConfiguration("visualize")

    sim_node = Node(
        package="usv_simulation",
        executable="sim_node",
        name="usv_sim_node",
        output="screen",
        parameters=[
            {"dt": 0.05},
            {"publish_rate": 20.0},
            {"add_noise": True},
            {"noise_scale_pos": 0.05},
            {"x_init": 0.0, "y_init": 0.0, "psi_init": 0.0},
            {"u_init": 0.0, "v_init": 0.0, "r_init": 0.0},
        ],
    )

    mpc_node = Node(
        package="usv_mpc",
        executable="mpc_node",
        name="mpc_controller_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "mpc_params.yaml"),
            os.path.join(bringup_dir, "config", "usv_params.yaml"),
            {"scheme": scheme},
        ],
    )

    path_config_file = os.path.join(bringup_dir, "config", "path_config.yaml")
    with open(path_config_file, 'r') as f:
        path_config = yaml.safe_load(f)

    planner_node = Node(
        package="usv_planning",
        executable="path_planner_node",
        name="path_planner_node",
        output="screen",
        parameters=[
            path_config_file
        ],
    )

    visualizer_node = Node(
        package="usv_simulation",
        executable="visualizer",
        name="usv_visualizer",
        output="screen",
        condition=IfCondition(visualize),
    )

    return LaunchDescription([
        scheme_arg,
        visualize_arg,
        sim_node,
        mpc_node,
        planner_node,
        visualizer_node,
    ])
