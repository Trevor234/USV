"""WeAct PowerMonitorMini V1 电池驱动节点 (Pi GPIO UART 直连)。

硬件接线与协议见 usv_bringup/power_monitor_node.py 模块 docstring。
要点: /boot/firmware/config.txt 加 `dtoverlay=uart4-pi5` (GPIO12/13 →
/dev/ttyAMA4), 与功率计 4 针口交叉接线并共地; GPIO14/15 (/dev/ttyAMA10)
已被 MAVROS 占用。设备波特率由其设置菜单决定 (出厂默认 9600)。

用法:
  ros2 launch usv_bringup power_monitor.launch.py
  ros2 launch usv_bringup power_monitor.launch.py port:=/dev/ttyAMA4 baudrate:=9600
  ros2 topic echo /usv/battery --once
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    port_arg = DeclareLaunchArgument(
        "port", default_value="/dev/ttyAMA4",
        description="功率计串口 (Pi5 需 dtoverlay=uart4-pi5 → /dev/ttyAMA4)",
    )
    baudrate_arg = DeclareLaunchArgument(
        "baudrate", default_value="9600",
        description="与设备设置菜单 Baudrate 一致 (出厂默认 9600)",
    )

    power_monitor_node = Node(
        package="usv_bringup",
        executable="power_monitor_node",
        name="power_monitor_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "power_monitor_params.yaml"),
            {
                "port": LaunchConfiguration("port"),
                "baudrate": LaunchConfiguration("baudrate"),
            },
        ],
    )

    return LaunchDescription([port_arg, baudrate_arg, power_monitor_node])
