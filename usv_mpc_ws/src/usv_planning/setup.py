from setuptools import setup

package_name = "usv_planning"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description="Path planning for USV",
    license="MIT",
    entry_points={
        "console_scripts": [
            "path_planner_node = usv_planning.path_planner_node:main",
            "mission_bridge_node = usv_planning.mission_bridge_node:main",
        ],
    },
)
