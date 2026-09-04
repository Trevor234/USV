from setuptools import setup

package_name = "usv_mpc"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    # casadi/numpy: IPOPT 后端必需。acados 后端(可选, kinematic.backend:=acados)
    # 需源码安装 acados 并 `pip install -e interfaces/acados_template`，无 PyPI 包，
    # 故不列入此处；见 docs/acados_migration.md。
    install_requires=["setuptools", "casadi", "numpy"],
    zip_safe=True,
    maintainer="Trevor",
    maintainer_email="1572652994@qq.com",
    description="MPC controller for dual-thruster USV",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "mpc_node = usv_mpc.mpc_node:main",
        ],
    },
)
