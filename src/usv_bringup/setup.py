import os
from glob import glob
from setuptools import setup

package_name = "usv_bringup"

_config_yaml = glob("config/*.yaml")
if os.environ.get("USV_BRINGUP_EXCLUDE_SECRETS") == "1":
    # 仅在研究隔离构建时排除凭据，防止 setuptools 解引用并复制进研究产物；
    # 常规生产构建默认保留 config/*.yaml，与 HEAD 行为一致。
    _config_yaml = [
        item for item in _config_yaml
        if os.path.basename(item) not in {"ntrip_params.yaml"}
    ]

setup(
    name=package_name,
    version="0.1.0",
    packages=["usv_bringup"],
    package_dir={"": "."},
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/config", _config_yaml),
        # env-hook: 让 ros2 source 时自动导出 acados 环境变量
        (f"share/{package_name}/environment", ["env-hooks/usv_mpc.sh"]),
    ],
    install_requires=["setuptools"],
    entry_points={
        "console_scripts": [
            "power_monitor_node = usv_bringup.power_monitor_node:main",
            "mavros_rate_configurator = usv_bringup.mavros_rate_configurator:main",
        ],
    },
    zip_safe=True,
    maintainer="USV Developer",
    maintainer_email="user@example.com",
    description="Launch + config for USV MPC (Pi5 / NMPC real boat)",
    license="MIT",
    tests_require=["pytest"],
)
