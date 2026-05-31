from setuptools import setup

package_name = "usv_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=[],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (f"share/{package_name}/launch", [
            "launch/mavros.launch.py",
            "launch/sim.launch.py",
            "launch/sitl.launch.py",
            "launch/real.launch.py",
        ]),
        (f"share/{package_name}/config", [
            "config/mavros_config.yaml",
            "config/usv_params.yaml",
            "config/mpc_params.yaml",
            "config/path_config.yaml",
        ]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description="Launch files and configuration for USV MPC system",
    license="MIT",
)
