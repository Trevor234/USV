"""VRX Gazebo Sim + MPC Scheme B (C++ 动力学 NMPC) validation launch.

MPC 节点为 usv_mpc_cpp (C++ NMPC, output_mode=vrx_thrust 直接发布推力),
船体和 MPC 共用 vehicle_config。生成的 SDF 使用 DART 原生附加质量；
非对称辨识交叉项的仿真处理记录在 effective_vehicle.yaml 中。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from usv_simulation.vrx_spawn import launch_vrx


def generate_launch_description():
    bringup_share = get_package_share_directory("usv_bringup")
    simulation_share = get_package_share_directory("usv_simulation")

    world_arg = DeclareLaunchArgument("world", default_value="sydney_regatta")
    headless_arg = DeclareLaunchArgument("headless", default_value="False")
    paused_arg = DeclareLaunchArgument("paused", default_value="False")
    vehicle_config_arg = DeclareLaunchArgument(
        "vehicle_config", default_value=os.path.join(bringup_share, "config", "usv_params_sim.yaml"),
        description="Identified parameters shared by the Gazebo boat and controller")
    simulation_config_arg = DeclareLaunchArgument(
        "simulation_config", default_value=os.path.join(simulation_share, "config", "vrx_model.yaml"))
    model_output_arg = DeclareLaunchArgument(
        "model_output_dir", default_value="", description="Generated SDF, mesh and effective YAML; default /tmp/usv_vrx_*")
    control_enabled_arg = DeclareLaunchArgument(
        "control_enabled", default_value="true", description="False for open-loop model checks")
    waypoints_file_arg = DeclareLaunchArgument("waypoints_file", default_value="")
    visualize_arg = DeclareLaunchArgument(
        "visualize",
        default_value="false",
        description="Start the matplotlib runtime visualizer",
    )
    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="B", choices=["A", "B", "C"],
        description="A=运动学 MPC(cmd_vel→推力转换) B=动力学 NMPC(直接推力) C=RL 策略(ONNX 推理)")
    rl_model_arg = DeclareLaunchArgument(
        "rl_model", default_value="",
        description="方案C 的 ONNX 策略路径（usv_rl.export_policy 导出）")
    record_bag_arg = DeclareLaunchArgument("record_bag", default_value="false")
    bag_dir_arg = DeclareLaunchArgument(
        "bag_dir",
        default_value=PathJoinSubstitution([EnvironmentVariable("HOME"), "USV", "usv_vrx_logs"]),
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

    vrx = OpaqueFunction(function=launch_vrx)

    mpc_params = os.path.join(bringup_share, "config", "mpc_params.yaml")
    mpc_params_a = os.path.join(bringup_share, "config", "mpc_params_A.yaml")
    usv_params_sim = LaunchConfiguration("effective_vehicle")
    mpc_overlay = os.path.join(bringup_share, "config", "mpc_params_vrx.yaml")
    path_params = os.path.join(bringup_share, "config", "path_config.yaml")

    # ament_python does not automatically source arbitrary files installed in
    # share/<package>/environment. Make the acados runtime path explicit for
    # the Scheme B process so vrx.launch.py works in a clean sourced shell.
    acados_source = os.environ.get(
        "ACADOS_SOURCE_DIR", os.path.join(os.path.expanduser("~"), "acados")
    )
    current_library_path = os.environ.get("LD_LIBRARY_PATH", "")
    acados_library_path = os.path.join(acados_source, "lib")
    if current_library_path:
        acados_library_path += os.pathsep + current_library_path
    solver_environment = {
        "ACADOS_SOURCE_DIR": acados_source,
        "LD_LIBRARY_PATH": acados_library_path,
    }

    planner_node = TimerAction(
        period=8.0,
        actions=[Node(
            package="usv_planning_cpp",
            executable="path_planner_node",
            name="path_planner_node",
            output="screen",
            condition=IfCondition(LaunchConfiguration("control_enabled")),
            parameters=[path_params, {
                "use_sim_time": True,
                "odom_topic": odom_topic,
                "path_topic": path_topic,
                "profile_topic": profile_topic,
                "dynamic_waypoints_topic": dynamic_waypoints_topic,
                "waypoints_file": waypoints_file,
            }],
        )],
    )

    enabled = LaunchConfiguration("control_enabled")
    is_scheme_a = PythonExpression(["'", scheme, "' == 'A' and '", enabled, "'.lower() == 'true'"])
    is_scheme_b = PythonExpression(["'", scheme, "' == 'B' and '", enabled, "'.lower() == 'true'"])
    is_scheme_c = PythonExpression(["'", scheme, "' == 'C' and '", enabled, "'.lower() == 'true'"])

    def plant_parameter(name):
        return ParameterValue(LaunchConfiguration("plant_" + name), value_type=float)

    # 方案 B: 动力学 NMPC, 推力 1:1 直发 (现有路径)
    mpc_node_b = TimerAction(
        period=9.0,
        actions=[Node(
            package="usv_mpc_cpp",
            executable="mpc_node",
            name="mpc_controller_node",
            output="screen",
            condition=IfCondition(is_scheme_b),
            additional_env=solver_environment,
            parameters=[mpc_params, usv_params_sim, mpc_overlay, {
                "use_sim_time": True,
                "dynamic.T_max": plant_parameter("tmax"),
                "dynamic.T_min": plant_parameter("tmin"),
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
                "use_sim_time": True,
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
                "use_sim_time": True,
                "d_thruster": plant_parameter("d"),
                "mass": plant_parameter("mass"), "iz_eff": plant_parameter("iz_eff"),
                "xu": plant_parameter("xu"), "xuu": plant_parameter("xuu"),
                "nr": plant_parameter("nr"), "nrr": plant_parameter("nrr"),
                "t_max": plant_parameter("inner_tmax"),
            }],
        )],
    )

    # 方案 C: RL 策略 ONNX 推理（usv_rl_ros, 推力直发, 接口与方案 B 对齐）
    rl_node = TimerAction(
        period=9.0,
        actions=[Node(
            package="usv_rl_ros",
            executable="rl_policy_node",
            name="rl_policy_node",
            output="screen",
            condition=IfCondition(is_scheme_c),
            parameters=[{
                "use_sim_time": True,
                "model_path": LaunchConfiguration("rl_model"),
                "odom_topic": odom_topic,
                "imu_topic": imu_topic,
                "path_topic": path_topic,
                "profile_topic": profile_topic,
                "status_topic": mpc_status_topic,
                "left_thrust_topic": left_thrust_topic,
                "right_thrust_topic": right_thrust_topic,
                "control_rate_hz": 5.0,
                "t_max": plant_parameter("tmax"),
                "d_t_max": 80.0,
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
                "use_sim_time": True,
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
            "/clock",
        ],
        output="screen",
        condition=IfCondition(record_bag),
    )

    return LaunchDescription([
        world_arg,
        headless_arg,
        paused_arg,
        vehicle_config_arg,
        simulation_config_arg,
        model_output_arg,
        control_enabled_arg,
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
        rl_model_arg,
        planner_node,
        mpc_node_b,
        kin_node,
        rl_node,
        visualizer_node,
        bag_record,
    ])
