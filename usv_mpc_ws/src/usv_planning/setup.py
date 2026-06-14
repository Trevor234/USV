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
    install_requires=["setuptools", "numpy", "pyyaml"],
    extras_require={
        # casadi is only needed for the optional minimum-curvature path
        # refinement (enable_curvature_opt:=true). pip-only, no rosdep key.
        "curvature_opt": ["casadi"],
    },
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description="Path planning for USV",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "path_planner_node = usv_planning.path_planner_node:main",
            "mission_bridge_node = usv_planning.mission_bridge_node:main",
        ],
    },
)
