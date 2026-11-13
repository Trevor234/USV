"""实船全系统启动 — 配合 AET-H743-AIR-PRO 飞控运行完整控制栈。

启动全部核心节点：
  - MAVROS（与 AET-H743-AIR-PRO 的串口 UART 连接）
  - MPC 控制器
  - 路径规划器
  - 模式管理与安全监控节点
  - （可选）NTRIP RTK 差分注入与 rosbag2 数据录制

用法：
  ros2 launch usv_bringup real.launch.py
  ros2 launch usv_bringup real.launch.py use_ntrip:=true
  ros2 launch usv_bringup real.launch.py record:=true bag_output_dir:=/mnt/usv_bags
"""

import os
import subprocess

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch.actions import ExecuteProcess

def _ntrip_daemon_state(service="usv-rtk.service"):
    """判断 RTK 差分注入守护进程 usv-rtk.service 的状态。

    2026-11-11 拆分: 差分注入从本 launch 迁出, 由 usv-rtk.service 托管;
    但 use_ntrip 保持默认 true, 让本 launch 在守护进程缺席时仍自足。

    必须互斥的原因: ntrip_client 的两份实例会同时向
    /mavros/gps_rtk/send_rtcm 发 GPS_RTCM_DATA, 双份差分流会污染
    RTK 模块的解析。

    返回值:
      "active"  —— 守护进程正在跑, 本 launch 必须跳过
      "enabled" —— 已设开机自启但当前未运行
                   (可能正在启动中, 也可能被人为 stop)。本 launch 也跳过,
                   避免与服务抢注。此时日志会明确提示, 不会静默失效。
      "off"     —— 未启用也不在跑, 本 launch 用自己的 ntrip

    放行方式(手工调试): systemctl disable --now usv-rtk 后再启动本 launch。
    """
    def _probe(verb):
        try:
            res = subprocess.run(
                ["systemctl", verb, service],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return res.stdout.strip()

    if _probe("is-active") in ("active", "activating", "reloading"):
        return "active"
    if _probe("is-enabled") == "enabled":
        return "enabled"
    return "off"

def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")


    # scheme: 控制方案选择。A=运动学 MPC(kinematic), B=动力学 NMPC(dynamic)。
    # 切换时自动选择对应的 MPC 包和参数配置文件:
    #   A: usv_mpc  + mpc_params_A.yaml + usv_params_A.yaml
    #   B: usv_nmpc + mpc_params_B.yaml + usv_params_B.yaml
    scheme_arg = DeclareLaunchArgument(
        "scheme", default_value="B",
        description="控制方案: A=运动学MPC, B=动力学NMPC",
        choices=["A", "B"],
    )


    
 
    # fcu_url: 连接飞控的串口参数。默认 /dev/ttyAMA10:921600。    
    fcu_url_arg = DeclareLaunchArgument(
        "fcu_url", default_value="/dev/ttyAMA10:921600",
        description="FCU serial connection URL"
    )

    # 2026-11-11: TCP GCS 转发链路已删除（gcs_url 不再声明，也不再传给 mavros）。
    # 如需临时恢复，用 mavros.launch.py gcs_url:=... 单独启动，不要挂回常驻服务。
    # mavros_odom_topic: planner 和 MPC 用作主定位话题的名称。
    mavros_odom_topic_arg = DeclareLaunchArgument(
        "mavros_odom_topic", default_value="/mavros/local_position/odom",
        description="MAVROS odometry topic for planner and MPC"
    )

    # mavros_state_topic: mode_manager 和 MPC 用作飞控状态的话题名称。
    mavros_state_topic_arg = DeclareLaunchArgument(
        "mavros_state_topic", default_value="/mavros/state",
        description="MAVROS state topic for mode manager and MPC"
    )

    # mavros_imu_topic: MPC 用作 IMU 输入的话题名称 (方案 A/B 均订阅以读取 angular_velocity.z 作为横摆角速度 r)。
    mavros_imu_topic_arg = DeclareLaunchArgument(
        "mavros_imu_topic", default_value="/mavros/imu/data",
        description="MAVROS IMU topic used by the MPC node"
    )

       
    
    
    
    # mavros_rc_override_topic: NMPC 预留的 RC override 话题名称参数。
    mavros_rc_override_topic_arg = DeclareLaunchArgument(
        "mavros_rc_override_topic", default_value="/mavros/rc/override",
        description="MAVROS RC override topic used by the NMPC controller"
    )

    # profile_topic: MPC 用作输入参考速度/曲率/时间的 Profile 话题名称。
    profile_topic_arg = DeclareLaunchArgument(
        "profile_topic", default_value="/path/reference_profile",
        description="Reference speed/curvature/time profile topic used by MPC",
    )

    # use_ntrip: 是否启动 ntrip_client 差分定位。默认 true —— 本 launch 保持自足,
    # 即使 usv-rtk.service 没启用也能独立完成差分注入。
    # 2026-11-11 拆分: 差分注入另由 usv-rtk.service 守护进程托管, 两者互斥。
    # 互斥由 _ntrip_daemon_state() 自动判定: 守护进程 enabled/active 时本 launch
    # 自动跳过, 不会出现双份 RTCM 注入飞控。手工强制走本 launch 需先
    # systemctl disable --now usv-rtk。
    use_ntrip_arg = DeclareLaunchArgument(
        "use_ntrip", default_value="true",
        description="启动 ntrip_client 把 CORS 差分注入飞控做 RTK。默认开启;"
                    "若 usv-rtk.service 已 enabled/active 则自动跳过以避免双份 RTCM。",
        choices=["true", "false"],
    )

    # record: 是否随实机系统启动 rosbag2。启用时必须先挂载可写的外接存储。
    record_arg = DeclareLaunchArgument(
        "record", default_value="false",
        description="Record the core control loop to MCAP on an external drive",
        choices=["true", "false"],
    )
    bag_output_dir_arg = DeclareLaunchArgument(
        "bag_output_dir", default_value="/mnt/usv_bags",
        description="Existing writable external-drive directory for rosbag output",
    )
    bag_prefix_arg = DeclareLaunchArgument(
        "bag_prefix", default_value="usv_run",
        description="Prefix for timestamped rosbag directories",
    )
    bag_max_bag_size_arg = DeclareLaunchArgument(
        "bag_max_bag_size", default_value="3221225472",
        description="Maximum MCAP file size in bytes before splitting (FAT32-safe default)",
    )
    bag_max_bag_duration_arg = DeclareLaunchArgument(
        "bag_max_bag_duration", default_value="900",
        description="Maximum MCAP file duration in seconds before splitting",
    )
    bag_max_cache_size_arg = DeclareLaunchArgument(
        "bag_max_cache_size", default_value="104857600",
        description="rosbag2 write-cache size in bytes",
    )

    fcu_url = LaunchConfiguration("fcu_url")
    mavros_odom_topic = LaunchConfiguration("mavros_odom_topic")
    mavros_state_topic = LaunchConfiguration("mavros_state_topic")
    mavros_imu_topic = LaunchConfiguration("mavros_imu_topic")
    mavros_rc_override_topic = LaunchConfiguration("mavros_rc_override_topic")
    profile_topic = LaunchConfiguration("profile_topic")
    use_ntrip = LaunchConfiguration("use_ntrip")
    scheme = LaunchConfiguration("scheme")
    record = LaunchConfiguration("record")
    bag_output_dir = LaunchConfiguration("bag_output_dir")
    bag_prefix = LaunchConfiguration("bag_prefix")
    bag_max_bag_size = LaunchConfiguration("bag_max_bag_size")
    bag_max_bag_duration = LaunchConfiguration("bag_max_bag_duration")
    bag_max_cache_size = LaunchConfiguration("bag_max_cache_size")

    # 立即开始录制，确保捕获 MAVROS 建立连接与系统启动阶段状态。
    # 若外接存储不可用或不可写，record.launch.py 会立即失败退出。
    record_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, "launch", "record.launch.py")
        ),
        condition=IfCondition(record),
        launch_arguments={
            "bag_output_dir": bag_output_dir,
            "bag_prefix": bag_prefix,
            "max_bag_size": bag_max_bag_size,
            "max_bag_duration": bag_max_bag_duration,
            "max_cache_size": bag_max_cache_size,
        }.items(),
    )

    # 启动 MAVROS 节点
    mavros_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, "launch", "mavros.launch.py")
        ),
        launch_arguments={
            "fcu_url": fcu_url,
        }.items(),
    )

    

    # 安全节点 (usv_safety)
    safety_node = Node(
        package="usv_safety",
        executable="mode_manager_node",
        name="mode_manager_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "safety_params.yaml"),
            {
                "auto_arm": False,
                "auto_mode_switch": False,
                "state_topic": mavros_state_topic,
                "odom_topic": mavros_odom_topic,
                "battery_topic": "/mavros/battery",
                "path_topic": "/path/reference",
                "set_mode_service": "/mavros/set_mode",
                "arming_service": "/mavros/cmd/arming",
            },
        ],
    )

    # 规划节点 (usv_planning)
    planner_node = Node(
        package="usv_planning",
        executable="path_planner_node",
        name="path_planner_node",
        output="screen",
        parameters=[
            os.path.join(bringup_dir, "config", "path_config.yaml"),
            {
                "odom_topic": mavros_odom_topic,
                "path_topic": "/path/reference",
                "profile_topic": profile_topic,
            },
        ],
    )

    mission_bridge_node = Node(
        package="usv_planning",
        executable="mission_bridge_node",
        name="mission_bridge_node",
        output="screen",
        parameters=[{
            "waypoints_topic": "/mavros/mission/waypoints",
            "origin_topic": "/mavros/global_position/gp_origin",
            "output_topic": "/usv/mission/waypoints_local",
            "pull_service": "/mavros/mission/pull",
            "auto_pull": True,
            "pull_interval": 2.0,
            "skip_home": True,
        }],
    )

    # MPC 控制器: 根据 scheme 切换包和配置文件。
    #   scheme=A: usv_mpc  (运动学, acados SQP+MERIT_BACKTRACKING) + mpc_params_A.yaml
    #   scheme=B: usv_nmpc (动力学, acados SQP_RTI) + mpc_params_B.yaml
    # 两个方案共用 usv_acados::backend (libusv_acados_backend.so), 只是各自
    # 使用独立的生成模型/实例。

    # acados 运行时库路径: 非交互式启动 (SSH、systemd) 不 source .bashrc,
    # 故显式补 LD_LIBRARY_PATH:
    #   - acados 运行时库 (libacados/libhpipm/libblasfeo)
    #   - 共用后端库: 由 workspace setup.bash 的 overlay 给出 (launch 继承),
    #     此处只保留 overlay 已设置的 LD_LIBRARY_PATH 前缀 _ld_base。
    # 方案 A 不再需要 CasADi 运行时库 (不链接也不 import casadi)。
    _acados_lib = os.path.expanduser("~/acados/lib")
    _ld_base = os.environ.get("LD_LIBRARY_PATH", "")
    _mpc_ld_path = ":".join(p for p in [_ld_base, _acados_lib] if p)

    mpc_pkg = PythonExpression(
        expression=["'usv_mpc' if '", scheme, "' == 'A' else 'usv_nmpc'"]
    )
    mpc_params_file = PythonExpression(
        expression=["'", bringup_dir, "/config/mpc_params_A.yaml' if '", scheme, "' == 'A' else '", bringup_dir, "/config/mpc_params_B.yaml'"]
    )
    usv_params_file = PythonExpression(
        expression=["'", bringup_dir, "/config/usv_params_A.yaml' if '", scheme, "' == 'A' else '", bringup_dir, "/config/usv_params_B.yaml'"]
    )
    mpc_node = Node(
        package=mpc_pkg,
        executable="mpc_node",
        name="mpc_controller_node",
        output="screen",
        additional_env={"LD_LIBRARY_PATH": _mpc_ld_path},
        parameters=[
            mpc_params_file,
            usv_params_file,
            {
                "odom_topic": mavros_odom_topic,
                "imu_topic": mavros_imu_topic,
                "path_topic": "/path/reference",
                "profile_topic": profile_topic,
                "state_topic": mavros_state_topic,
                # 方案相关参数: 两边都显式传入, 各自节点只声明自己认识的那个。
                # ROS 2 对未声明参数静默忽略, 不会报错。
                #   A: velocity_topic  (/mavros/setpoint_velocity/cmd_vel)
                #   B: rc_override_topic (/mavros/rc/override)
                # 2026-10-21: 此前只传 rc_override_topic, 方案 A 的
                # velocity_topic 完全依赖代码默认值, 契约里也没有记录。
                "rc_override_topic": mavros_rc_override_topic,
                "velocity_topic": "/mavros/setpoint_velocity/cmd_vel",
            },
        ],
    )

    # 延迟启动 — 等待 MAVROS 先建立连接
    delayed_mpc = TimerAction(
        period=3.0,
        actions=[mpc_node],
    )

    # RTK 差分注入 (CORS → ntrip_client → MAVROS gps_rtk → 飞控 → GPS)。
    # 2026-11-11 起默认不在此启动, 改由独立守护进程 usv-rtk.service 托管;
    # 拆分理由: 差分链路依赖外部 CORS 网络, 曾每 6 秒重连一次, 与控制栈
    # 生命周期解耦后可单独重启/排障, 不影响录制与 MPC。
    _rtk_state = _ntrip_daemon_state()
    if _rtk_state == "active":
        # 守护进程正在跑: 绝不能再起第二份 ntrip。
        delayed_ntrip = LogInfo(msg=[
            "[real.launch] RTK 差分注入由 usv-rtk.service 托管(运行中), 本 launch 跳过 ntrip。",
            "  手动排查: journalctl -u usv-rtk -f",
            "  若要改由此 launch 启动: sudo systemctl disable --now usv-rtk",
        ])
    elif _rtk_state == "enabled":
        # 已启用但当前没跑: 大概率是开机时尚未轮到它, 或在被人为 stop。
        # 仍然跳过, 否则会与随后启动的服务抢注; 但必须把这事说清楚,
        # 不能让 "差分没注入" 变成静默故障。
        delayed_ntrip = LogInfo(msg=[
            "[real.launch] usv-rtk.service 已 enabled 但当前未运行, 本 launch 仍跳过 ntrip。",
            "  若差分确实需要: sudo systemctl start usv-rtk",
            "  若想改由此 launch 启动: sudo systemctl disable --now usv-rtk 后重启本服务",
        ])
    else:
        ntrip_launch = IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(bringup_dir, "launch", "ntrip.launch.py")
            ),
            condition=IfCondition(use_ntrip),
        )
        delayed_ntrip = TimerAction(
            period=5.0,
            actions=[ntrip_launch],
        )

    log_msg = ExecuteProcess(
        cmd=["echo", "Launching real USV system..."],
        shell=True,
        output="screen"
    )
    return LaunchDescription([
        log_msg,
        scheme_arg,
        fcu_url_arg,
        mavros_odom_topic_arg,
        mavros_state_topic_arg,
        mavros_imu_topic_arg,
        mavros_rc_override_topic_arg,
        profile_topic_arg,
        use_ntrip_arg,
        record_arg,
        bag_output_dir_arg,
        bag_prefix_arg,
        bag_max_bag_size_arg,
        bag_max_bag_duration_arg,
        bag_max_cache_size_arg,
        record_launch,
        mavros_launch,
        safety_node,
        planner_node,
        mission_bridge_node,
        delayed_mpc,
        delayed_ntrip,
    ])
