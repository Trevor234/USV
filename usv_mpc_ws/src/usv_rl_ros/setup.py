from glob import glob
import os

from setuptools import setup

package_name = "usv_rl_ros"

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
    description="RL policy inference node (ONNX) for USV scheme C.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "rl_policy_node = usv_rl_ros.rl_policy_node:main",
        ],
    },
)
