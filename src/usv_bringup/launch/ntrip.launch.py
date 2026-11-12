"""NTRIP 客户端 launch —— 把 CORS 差分(RTCM3)经 MAVROS 注入飞控做 RTK。

数据通路:
  CORS caster --NTRIP/RTCM3--> ntrip_client
    发布 rtcm(mavros_msgs/RTCM)      --重映射--> /mavros/gps_rtk/send_rtcm
    订阅 fix (sensor_msgs/NavSatFix) <--重映射-- /fix_for_ntrip (QoS中继, 见下)
  fix_qos_relay (本launch自带, 2026-10-09 引入):
    /mavros/global_position/raw/fix (BEST_EFFORT) --> /fix_for_ntrip (RELIABLE)
    原因: MAVROS raw/fix 是 BEST_EFFORT, 而 ntrip_client 的 fix 订阅是
    RELIABLE 且未启用 rclpy qos_overriding_options, 参数表无法覆盖,
    只能靠中继桥接。中继断了 GGA 就上不去, VRS 不发差分。
  MAVROS gps_rtk 插件 --GPS_RTCM_DATA(MAVLink)--> AET-H743-AIR-PRO --GPS串口--> RTK模块

前置: 先在 config/ntrip_params.yaml 填好 CORS 账号/挂载点。

用法(MAVROS 需已在运行, 如 real.launch.py 或 mavros.launch.py):
  ros2 launch usv_bringup ntrip.launch.py
  ros2 launch usv_bringup ntrip.launch.py fix_topic:=/mavros/global_position/global
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")

    params_file_arg = DeclareLaunchArgument(
        "ntrip_params_file",
        default_value=os.path.join(bringup_dir, "config", "ntrip_params.yaml"),
        description="CORS/NTRIP 连接参数 YAML (host/port/mountpoint/账号)",
    )
    rtcm_topic_arg = DeclareLaunchArgument(
        "rtcm_topic", default_value="/mavros/gps_rtk/send_rtcm",
        description="MAVROS gps_rtk 插件的 RTCM 输入话题 (mavros_msgs/RTCM)",
    )
    fix_topic_arg = DeclareLaunchArgument(
        "fix_topic", default_value="/fix_for_ntrip",
        description="用于生成上传给 CORS 的 GGA 的 NavSatFix 来源 (VRS 必需); "
                    "也可用 /mavros/global_position/global",
    )

    params_file = LaunchConfiguration("ntrip_params_file")
    rtcm_topic = LaunchConfiguration("rtcm_topic")
    fix_topic = LaunchConfiguration("fix_topic")

    # ntrip_client (LORD-MicroStrain): 可执行 ntrip_ros.py
    #   发布 'rtcm', 订阅 'nmea' 与 'fix' —— 这里只用 'fix' 上传 GGA。
    ntrip_node = Node(
        package="ntrip_client",
        executable="ntrip_ros.py",
        name="ntrip_client",
        output="screen",
        parameters=[params_file],
        remappings=[
            ("rtcm", rtcm_topic),
            ("fix", fix_topic),
        ],
    )

    # QoS 中继 (2026-10-09): raw/fix BEST_EFFORT -> /fix_for_ntrip RELIABLE。
    # ntrip_client 的 fix 订阅无法用参数覆盖 QoS, 只能经此桥接。
    fix_qos_relay = Node(
        package="usv_bringup",
        executable="fix_qos_relay",
        name="fix_qos_relay",
        output="screen",
    )

    return LaunchDescription([
        params_file_arg,
        rtcm_topic_arg,
        fix_topic_arg,
        fix_qos_relay,
        ntrip_node,
    ])
