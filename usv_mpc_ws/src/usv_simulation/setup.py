from setuptools import setup

package_name = "usv_simulation"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
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
