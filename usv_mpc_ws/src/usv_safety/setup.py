from setuptools import setup

package_name = "usv_safety"

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
    description="Safety monitoring and mode management for USV",
    license="MIT",
    entry_points={
        "console_scripts": [
            "mode_manager_node = usv_safety.mode_manager_node:main",
        ],
    },
)
