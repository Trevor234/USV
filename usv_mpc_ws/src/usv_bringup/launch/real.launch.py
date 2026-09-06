"""Real USV launch — full system with MicoAir743.

Launches ALL nodes:
  - MAVROS (UART connection to MicoAir743)
  - MPC controller
  - Path planner
  - Mode manager & safety monitor
  - (optional) Visualizer + NTRIP RTK injection

Usage:
  ros2 launch usv_bringup real.launch.py
  ros2 launch usv_bringup real.launch.py gcs_url:=udp://@<gcs-ip>:14550
  ros2 launch usv_bringup real.launch.py visualize:=true use_ntrip:=true
  ros2 launch usv_bringup real.launch.py record:=true bag_output_dir:=/mnt/usv_bags
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch.actions import ExecuteProcess

def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")


    # use_cpp: 切换已重写为 C++ 的节点 (safety/planning/mpc 同进同退),与方案 A 一致。
    # True 用 *_cpp 包,False 用原 Python 包,便于 A/B 灰度对比与回退。
    use_cpp_arg = DeclareLaunchArgument(
        "use_cpp", default_value="false",
        description="Use C++ node implementations where available (A/B toggle)"
    )

    # scheme: 控制方案选择。A=运动学 MPC(kinematic), B=动力学 NMPC(dynamic)。
    # 切换时自动选择对应的 MPC 包和参数配置文件:
    #   A: usv_mpc_kinematic_cpp + mpc_params_A.yaml + usv_params_A.yaml
    #   B: usv_mpc_cpp          + mpc_params_B.yaml + usv_params_B.yaml
    # 注意: use_cpp=false 时 MPC 用 Python 包(usv_mpc),方案 A 才有 Python MPC。
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

    # gcs_url: MAVLink 链路，可用于转发到地面站或转发 CORS 数据。默认指向方案 A 的 GCS 地址。
    gcs_url_arg = DeclareLaunchArgument(
        "gcs_url", default_value="tcp-l://:14550",
        description="Optional MAVLink GCS forwarding URL"
    )

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

    # mavros_imu_topic: MPC 用作 IMU 输入的话题名称 (目前方案 A/B 逻辑未直接消费,但保留配置)。
    mavros_imu_topic_arg = DeclareLaunchArgument(
        "mavros_imu_topic", default_value="/mavros/imu/data",
        description="MAVROS IMU topic used by the MPC node"
    )

       
    
    
    
    # mavros_rc_override_topic: NMPC(Python 逻辑)读取摇杆 override 的话题名称(C++ 已切换,但保留参数)。
    mavros_rc_override_topic_arg = DeclareLaunchArgument(
        "mavros_rc_override_topic", default_value="/mavros/rc/override",
        description="MAVROS RC override topic used by the NMPC controller"
    )

    # profile_topic: MPC 用作输入参考速度/曲率/时间的 Profile 话题名称。
    profile_topic_arg = DeclareLaunchArgument(
        "profile_topic", default_value="/path/reference_profile",
        description="Reference speed/curvature/time profile topic used by MPC",
    )
    
    # visualize: 是否启动 matplotlib 实时可视化。
    visualize_arg = DeclareLaunchArgument(
        "visualize", default_value="false",
        description="启动 matplotlib 实时可视化。默认关闭(B 实机通常 headless);"
                    "无 DISPLAY 时该节点会自动优雅退出(不影响其他节点);需开启传 visualize:=true",
        choices=["true", "false"],
    )

    # telemetry: 是否启动遥测桥接,经 frp 向地面站转发状态。
    telemetry_arg = DeclareLaunchArgument(
        "telemetry", default_value="true",
        description="启动遥测桥接(usv_simulation/telemetry_bridge),5 Hz 打包 JSON 经裸 TCP 转发。默认开启",
        choices=["true", "false"],
    )

    # use_ntrip: 是否启动 ntrip_client 差分定位。
    # CORS 账号已配好(config/ntrip_params.yaml), 默认开启随服务自启;
    # 调试或暂不用 RTK 时传 use_ntrip:=false 关闭。
    use_ntrip_arg = DeclareLaunchArgument(
        "use_ntrip", default_value="true",
        description="启动 ntrip_client 把 CORS 差分注入飞控做 RTK。默认开启;"
                    "config/ntrip_params.yaml 已填好账号; 不用时传 use_ntrip:=false",
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
    gcs_url = LaunchConfiguration("gcs_url")
    mavros_odom_topic = LaunchConfiguration("mavros_odom_topic")
    mavros_state_topic = LaunchConfiguration("mavros_state_topic")
    mavros_imu_topic = LaunchConfiguration("mavros_imu_topic")
    mavros_rc_override_topic = LaunchConfiguration("mavros_rc_override_topic")
    profile_topic = LaunchConfiguration("profile_topic")
    visualize = LaunchConfiguration("visualize")
    telemetry = LaunchConfiguration("telemetry")
    use_ntrip = LaunchConfiguration("use_ntrip")
    use_cpp = LaunchConfiguration("use_cpp")
    scheme = LaunchConfiguration("scheme")
    record = LaunchConfiguration("record")
    bag_output_dir = LaunchConfiguration("bag_output_dir")
    bag_prefix = LaunchConfiguration("bag_prefix")
    bag_max_bag_size = LaunchConfiguration("bag_max_bag_size")
    bag_max_bag_duration = LaunchConfiguration("bag_max_bag_duration")
    bag_max_cache_size = LaunchConfiguration("bag_max_cache_size")

    # Start recording immediately so MAVROS connection and startup state are captured.
    # record.launch.py fails fast if the external drive is unavailable or unwritable.
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

    # MAVROS launch
    mavros_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, "launch", "mavros.launch.py")
        ),
        launch_arguments={
            "fcu_url": fcu_url,
            "gcs_url": gcs_url,
        }.items(),
    )

    

    # use_cpp=true 时用 C++ 实现 (usv_safety_cpp),否则用原 Python (usv_safety)。
    safety_pkg = PythonExpression(
        expression=["'usv_safety_cpp' if '", use_cpp, "' == 'true' else 'usv_safety'"]
    )
    safety_node = Node(
        package=safety_pkg,
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

    # use_cpp=true 时用 C++ 实现 (usv_planning_cpp),否则用原 Python (usv_planning)。
    planning_pkg = PythonExpression(
        expression=["'usv_planning_cpp' if '", use_cpp, "' == 'true' else 'usv_planning'"]
    )
    planner_node = Node(
        package=planning_pkg,
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
        package=planning_pkg,
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
    #   scheme=A: usv_mpc_kinematic_cpp (运动学, CasADi) + mpc_params_A.yaml + usv_params_A.yaml
    #   scheme=B: usv_mpc_cpp (动力学 NMPC, acados+CasADi) + mpc_params_B.yaml + usv_params_B.yaml
    # 2026-09-06: Python 方案 A 包 (usv_mpc) 已删除, 方案 A 恒为 C++
    # (usv_mpc_kinematic_cpp, CasADi/IPOPT); scheme=B 为 usv_mpc_cpp (acados)。

    # acados/CasADi 运行时库路径: 非交互式启动(如 SSH、systemd)不 source .bashrc,
    # 故在此显式设置 LD_LIBRARY_PATH, 确保 scheme=B 的 mpc_node 能找到 libhpipm.so 等。
    _acados_lib = os.path.expanduser("~/acados/lib")
    _casadi_lib = os.path.expanduser("~/.local/lib/python3.12/site-packages/casadi")
    _mpc_ld_path = ":".join(p for p in [
        os.environ.get("LD_LIBRARY_PATH", ""),
        _acados_lib,
        _casadi_lib,
    ] if p)

    mpc_pkg = PythonExpression(
        expression=["'usv_mpc_kinematic_cpp' if '", scheme, "' == 'A' else 'usv_mpc_cpp'"]
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
                "rc_override_topic": mavros_rc_override_topic,
            },
        ],
    )

    # Delayed start — let MAVROS connect first
    delayed_mpc = TimerAction(
        period=3.0,
        actions=[mpc_node],
    )

    # 可视化节点 (方案无关)。B 输出 rc/override 而非 cmd_vel,故 cmd_vel_topic 留空
    # (visualizer 优雅跳过);如需看推力,可把 left/right_thrust_topic 指向推力话题。
    visualizer_node = Node(
        package="usv_simulation",
        executable="visualizer",
        name="usv_visualizer",
        output="screen",
        condition=IfCondition(visualize),
        parameters=[{
            "odom_topic": mavros_odom_topic,
            "cmd_vel_topic": "",
            "left_thrust_topic": "",
            "right_thrust_topic": "",
            "rtcm_topic": "/mavros/gps_rtk/send_rtcm",
            "gps_fix_topic": "/mavros/global_position/raw/fix",
            "gps_raw_topic": "/mavros/gpsstatus/gps1/raw",
        }],
    )

    # 遥测桥接: 复用 USVVisualizer 采集类, 5 Hz 打包 JSON 经裸 TCP 转发。
    # 监听 127.0.0.1:8765, 配合 frpc 的 usv-telemetry 代理对外暴露给地面站。
    # host/port/rate 用 telemetry_bridge 的默认值(127.0.0.1:8765:5Hz),
    # 话题参数与 visualizer_node 一致(同一份采集逻辑)。
    telemetry_node = Node(
        package="usv_simulation",
        executable="telemetry_bridge",
        name="usv_telemetry_bridge",
        output="screen",
        condition=IfCondition(telemetry),
        parameters=[{
            "odom_topic": mavros_odom_topic,
            "cmd_vel_topic": "",
            "left_thrust_topic": "",
            "right_thrust_topic": "",
            "rtcm_topic": "/mavros/gps_rtk/send_rtcm",
            "gps_fix_topic": "/mavros/global_position/raw/fix",
            "gps_raw_topic": "/mavros/gpsstatus/gps1/raw",
        }],
    )

    # RTK 差分注入 (CORS → ntrip_client → MAVROS gps_rtk → 飞控 → GPS)。
    # 延迟启动让 MAVROS 先连上飞控,gps_rtk 插件就绪后再喂 RTCM。
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
        use_cpp_arg,
        scheme_arg,
        fcu_url_arg,
        gcs_url_arg,
        mavros_odom_topic_arg,
        mavros_state_topic_arg,
        mavros_imu_topic_arg,
        mavros_rc_override_topic_arg,
        profile_topic_arg,
        visualize_arg,
        telemetry_arg,
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
        visualizer_node,
        telemetry_node,
        delayed_ntrip,
    ])
