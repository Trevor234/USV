import os
from glob import glob

from setuptools import setup

package_name = "usv_simulation"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        # Single-hull VRX model (usv_mono.urdf.xacro + usv_mono_dynamics.xacro)
        (os.path.join("share", package_name, "urdf"), glob("urdf/*.xacro")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description="VRX/WAM-V runtime visualization utilities for USV MPC validation.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "visualizer = usv_simulation.visualizer:main",
        ],
    },
)
