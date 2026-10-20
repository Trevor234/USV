from glob import glob
from setuptools import setup

package_name = "usv_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/config/waypoints", glob("config/waypoints/*.yaml")),
        # env-hook: 让 ros2 source 时自动导出 acados 环境变量
        (f"share/{package_name}/environment", ["env-hooks/usv_mpc.sh"]),
    ],
    install_requires=["setuptools"],
    entry_points={
        "console_scripts": [
            "fix_qos_relay = usv_bringup.fix_qos_relay:main",
        ],
    },
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description="Launch + config for USV MPC (Pi5 / NMPC real boat)",
    license="MIT",
    tests_require=["pytest"],
)
