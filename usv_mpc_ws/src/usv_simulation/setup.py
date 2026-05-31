import os
from glob import glob

from setuptools import setup

package_name = "usv_simulation"


def _data_files(target_subdir, src_glob):
    """Helper: install all files matching src_glob into share/<pkg>/<target_subdir>."""
    files = [f for f in glob(src_glob) if os.path.isfile(f)]
    if not files:
        return []
    return [(os.path.join("share", package_name, target_subdir), files)]


setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        # Launch files
        *_data_files("launch", "launch/*.py"),
        # World files
        *_data_files("worlds", "worlds/*.world"),
        *_data_files("worlds", "worlds/*.sdf"),
        # URDF
        *_data_files("urdf", "urdf/*"),
        # Config
        *_data_files("config", "config/*.yaml"),
        *_data_files("config", "config/*.parm"),
        # Scripts
        *_data_files("scripts", "scripts/*.sh"),
        # Models — install the whole tree under models/usv_2m/
        *_data_files("models/usv_2m", "models/usv_2m/*"),
    ],
    install_requires=["setuptools", "numpy"],
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description=(
        "Gazebo Sim / ROS 2 Jazzy simulation environment for the 2m dual-thruster USV. "
        "Contains SDF models, lake worlds, ArduPilot SITL launch wiring, "
        "and ROS 2 launch files for end-to-end MPC validation."
    ),
    license="MIT",
    entry_points={
        "console_scripts": [
            "thrust_bridge = usv_simulation.thrust_bridge:main",
            "cmd_force_to_entity_wrench = usv_simulation.cmd_force_to_entity_wrench:main",
            "sim_node = usv_simulation.sim_node:main",
            "visualizer = usv_simulation.visualizer:main",
        ],
    },
)
