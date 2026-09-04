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
        # VRX sim boat model (usv_mono.urdf.xacro + dynamics xacro), consumed by
        # usv_bringup/launch/vrx.launch.py via get_package_share_directory.
        (f"share/{package_name}/urdf", glob("urdf/*.xacro")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description="Matplotlib runtime visualization + TCP telemetry bridge for USV MPC.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "visualizer = usv_simulation.visualizer:main",
            "telemetry_bridge = usv_simulation.telemetry_bridge:main",
        ],
    },
)
