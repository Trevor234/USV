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
        # Legacy Xacro plus inputs used by the native SDF generator in vrx.launch.py.
        (f"share/{package_name}/urdf", glob("urdf/*.xacro")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/worlds", glob("worlds/*.sdf")),
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
            "build_vrx_model = usv_simulation.vrx_model:main",
            "cmdvel_to_thrust = usv_simulation.cmdvel_to_thrust:main",
            "telemetry_bridge = usv_simulation.telemetry_bridge:main",
        ],
    },
)
