"""ROS launch adapter for the generated native SDF and existing VRX topics."""

import os
from pathlib import Path
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch.actions import LogInfo, SetLaunchConfiguration
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from usv_simulation.vrx_model import build_model


def launch_vrx(context):
    import vrx_gz.launch

    def value(name):
        return LaunchConfiguration(name).perform(context)

    output = value("model_output_dir") or tempfile.mkdtemp(prefix="usv_vrx_")
    report = build_model(value("vehicle_config"), value("simulation_config"), output)
    output = Path(output).resolve()
    vehicle = report["effective_vehicle"]
    import yaml
    with (output / "effective_vehicle.yaml").open(encoding="utf-8") as stream:
        thruster = yaml.safe_load(stream)["/**"]["ros__parameters"]["thruster"]
    configs = {"effective_vehicle": str(output / "effective_vehicle.yaml"),
               "plant_d": vehicle["d_thruster"], "plant_xu": -vehicle["Xu"],
               "plant_mass": vehicle["mass"] - vehicle["Xu_dot"],
               "plant_iz_eff": vehicle["Iz"] - vehicle["Nr_dot"],
               "plant_xuu": -vehicle["Xuu"], "plant_nr": -vehicle["Nr"],
               "plant_nrr": -vehicle["Nrr"], "plant_tmax": thruster["T_max_forward"],
               "plant_inner_tmax": min(thruster["T_max_forward"], thruster["T_max_reverse"]),
               "plant_tmin": -thruster["T_max_reverse"]}
    actions = [SetLaunchConfiguration(key, str(val)) for key, val in configs.items()]
    actions.append(LogInfo(msg=f"USV SDF / effective parameters / report: {output}"))
    actions.extend(LogInfo(msg=warning) for warning in report["warnings"])
    world = value("world")
    if world == "usv_calm":
        world = os.path.join(get_package_share_directory("usv_simulation"), "worlds", world)
    world = os.path.splitext(world)[0]
    world_name = os.path.basename(world)
    actions.extend(vrx_gz.launch.simulation(
        world, value("headless").lower() == "true", value("paused").lower() == "true"))
    # Native SDF bypasses URDF conversion, which otherwise discards fluid_added_mass.
    position = [0, 0, 0, 0] if world_name == "usv_calm" else [-532, 162, 0, 1]
    actions.append(Node(
        package="ros_gz_sim", executable="create", output="screen",
        arguments=["-world", world_name, "-name", "wamv", "-file", report["sdf"],
                   "-x", str(position[0]), "-y", str(position[1]),
                   "-z", str(position[2]), "-Y", str(position[3])]))
    # Explicit absolute topics preserve the controller contract and sensor FLU frames.
    bridges = {
        "/clock": ("/clock", "rosgraph_msgs/msg/Clock", "gz.msgs.Clock", "["),
        value("odom_topic"):
            ("/model/wamv/odometry", "nav_msgs/msg/Odometry", "gz.msgs.Odometry", "["),
        value("imu_topic"):
            (f"/world/{world_name}/model/wamv/link/wamv/base_link/sensor/imu_sensor/imu",
             "sensor_msgs/msg/Imu", "gz.msgs.IMU", "["),
        "/wamv/joint_states":
            (f"/world/{world_name}/model/wamv/joint_state", "sensor_msgs/msg/JointState",
             "gz.msgs.Model", "["),
    }
    for side in ("left", "right"):
        topic = f"/wamv/thrusters/{side}/thrust"
        bridges[value(f"{side}_thrust_topic")] = (topic, "std_msgs/msg/Float64", "gz.msgs.Double", "]")
    actions.append(Node(
        package="ros_gz_bridge", executable="parameter_bridge", output="screen",
        arguments=[f"{gz_topic}@{ros_type}{direction}{gz_type}"
                   for gz_topic, ros_type, gz_type, direction in bridges.values()],
        remappings=[(spec[0], ros_topic) for ros_topic, spec in bridges.items()],
        parameters=[{"use_sim_time": True}]))
    actions.append(Node(
        package="robot_state_publisher", executable="robot_state_publisher", output="screen",
        parameters=[{"use_sim_time": True,
                     "robot_description": (output / "model.urdf").read_text(encoding="utf-8")}],
        remappings=[("/joint_states", "/wamv/joint_states")]))
    return actions
