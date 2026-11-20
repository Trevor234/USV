"""使用 rosbag2 将实船控制闭环录制到外接存储设备。"""

from datetime import datetime
import os
from pathlib import Path
import re

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
import yaml

from usv_bringup.topic_contract import get_record_topics, write_derived_qos_file


_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _parse_nonnegative_int(name, value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got: {value!r}") from exc
    if parsed < 0:
        raise RuntimeError(f"{name} must be non-negative, got: {parsed}")
    return parsed


def _load_topics(path):
    try:
        with path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Failed to read rosbag topics file {path}: {exc}") from exc

    if not isinstance(config, dict):
        raise RuntimeError(f"Rosbag topics file must be a YAML mapping: {path}")

    if "topics" in config:
        topics = config["topics"]
    else:
        # 兼容直接传入 topic_contract.yaml (SSOT)
        topics = get_record_topics(path)

    if not isinstance(topics, list) or not topics:
        raise RuntimeError(f"Rosbag topics file must contain a non-empty 'topics' list: {path}")
    if any(not isinstance(topic, str) or not topic.startswith("/") for topic in topics):
        raise RuntimeError(f"All rosbag topics must be absolute ROS topic names: {path}")
    if len(topics) != len(set(topics)):
        raise RuntimeError(f"Rosbag topics file contains duplicate topics: {path}")
    return topics


def _start_recorder(context):
    bag_output_dir = Path(LaunchConfiguration("bag_output_dir").perform(context)).expanduser()
    bag_prefix = LaunchConfiguration("bag_prefix").perform(context)
    topics_file = Path(LaunchConfiguration("topics_file").perform(context)).expanduser()
    qos_raw = LaunchConfiguration("qos_overrides_path").perform(context).strip()
    contract_file = Path(LaunchConfiguration("contract_file").perform(context)).expanduser()

    if not _PREFIX_PATTERN.fullmatch(bag_prefix):
        raise RuntimeError(
            "bag_prefix must start with an alphanumeric character and contain only "
            "letters, digits, '.', '_', or '-'"
        )
    if not bag_output_dir.exists():
        raise RuntimeError(
            f"Bag output directory does not exist: {bag_output_dir}. "
            "Mount the external SSD before starting the system."
        )
    if not bag_output_dir.is_dir():
        raise RuntimeError(f"Bag output path is not a directory: {bag_output_dir}")
    if not os.access(bag_output_dir, os.R_OK | os.W_OK | os.X_OK):
        raise RuntimeError(f"Bag output directory is not accessible and writable: {bag_output_dir}")

    # 剩余空间预检。写满后 ros2 bag 会退出, 而 systemd Restart=always 会每
    # 10 秒重建一个空 bag 目录, 形成重启风暴, 且没有明确的"磁盘满"告警。
    # 宁可启动时 fail fast, 让人看到真实原因。
    min_free = _parse_nonnegative_int(
        "min_free_bytes", LaunchConfiguration("min_free_bytes").perform(context)
    )
    if min_free > 0:
        st = os.statvfs(bag_output_dir)
        free_bytes = st.f_bavail * st.f_frsize
        if free_bytes < min_free:
            raise RuntimeError(
                f"Bag output directory has only {free_bytes / 1e9:.1f} GB free, "
                f"below min_free_bytes={min_free / 1e9:.1f} GB. "
                "Free space on the recording drive before starting."
            )
        print(f"[record] free space {free_bytes / 1e9:.1f} GB "
              f"(min {min_free / 1e9:.1f} GB)", flush=True)
    if not topics_file.is_file() or not os.access(topics_file, os.R_OK):
        raise RuntimeError(f"Rosbag topics file is missing or unreadable: {topics_file}")

    topics = _load_topics(topics_file)
    max_bag_size = _parse_nonnegative_int(
        "max_bag_size", LaunchConfiguration("max_bag_size").perform(context)
    )
    max_bag_duration = _parse_nonnegative_int(
        "max_bag_duration", LaunchConfiguration("max_bag_duration").perform(context)
    )
    max_cache_size = _parse_nonnegative_int(
        "max_cache_size", LaunchConfiguration("max_cache_size").perform(context)
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_uri = bag_output_dir / f"{bag_prefix}_{timestamp}"
    if output_uri.exists():
        raise RuntimeError(f"Rosbag output already exists: {output_uri}")

    # QoS 覆盖配置: 显式传入有效路径则使用; 否则从 topic_contract.yaml 动态派生
    if qos_raw and qos_raw.lower() != "auto":
        qos_path = Path(qos_raw).expanduser()
        if not qos_path.is_file() or not os.access(qos_path, os.R_OK):
            raise RuntimeError(f"Rosbag QoS override file is missing or unreadable: {qos_path}")
    else:
        if not contract_file.is_file() or not os.access(contract_file, os.R_OK):
            raise RuntimeError(
                f"Topic contract file for QoS derivation is missing or unreadable: {contract_file}"
            )
        derived_qos_path = bag_output_dir / f"{bag_prefix}_{timestamp}_qos.yaml"
        try:
            write_derived_qos_file(contract_file, derived_qos_path, target_topics=topics)
            qos_path = derived_qos_path
        except Exception:
            fallback_path = Path(f"/tmp/usv_qos_{bag_prefix}_{timestamp}.yaml")
            write_derived_qos_file(contract_file, fallback_path, target_topics=topics)
            qos_path = fallback_path
        print(f"[record] dynamically derived QoS overrides from {contract_file} -> {qos_path}", flush=True)
    output_uri = bag_output_dir / f"{bag_prefix}_{timestamp}"
    if output_uri.exists():
        raise RuntimeError(f"Rosbag output already exists: {output_uri}")

    # storage_config_file: 给了就用 --storage-config-file(例如 noChunking 实时落盘),
    # 没给就回退到默认 zstd_fast 预设, 行为与改动前完全一致。
    # 注意: --storage-preset-profile 与 --storage-config-file 互斥, 只能二选一。
    storage_config_file = LaunchConfiguration("storage_config_file").perform(context)
    if storage_config_file:
        storage_args = ["--storage-config-file", storage_config_file]
    else:
        storage_args = ["--storage-preset-profile", "zstd_fast"]

    recorder = ExecuteProcess(
        cmd=[
            "ros2",
            "bag",
            "record",
            "-s",
            "mcap",
            *storage_args,
            "--max-bag-size",
            str(max_bag_size),
            "--max-bag-duration",
            str(max_bag_duration),
            "--max-cache-size",
            str(max_cache_size),
            "--qos-profile-overrides-path",
            str(qos_path),
            "-o",
            str(output_uri),
            "--topics",
            *topics,
        ],
        output="screen",
    )

    shutdown_on_exit = RegisterEventHandler(
        OnProcessExit(
            target_action=recorder,
            on_exit=[
                LogInfo(msg="Rosbag recorder exited; shutting down the launch graph."),
                EmitEvent(event=Shutdown(reason="rosbag recorder exited")),
            ],
        )
    )

    return [
        LogInfo(msg=f"Recording rosbag to {output_uri}"),
        shutdown_on_exit,
        recorder,
    ]


def generate_launch_description():
    bringup_dir = get_package_share_directory("usv_bringup")
    default_contract = os.path.join(bringup_dir, "config", "topic_contract.yaml")
    # 默认直接以 topic_contract.yaml 为录制清单与 QoS 的单一事实来源 (SSOT)
    default_topics = default_contract

    return LaunchDescription([
        DeclareLaunchArgument(
            "bag_output_dir",
            default_value="/mnt/usv_bags",
            description="Existing writable external-drive directory for rosbag output",
        ),
        DeclareLaunchArgument(
            "bag_prefix",
            default_value="usv_run",
            description="Prefix for the timestamped rosbag directory",
        ),
        DeclareLaunchArgument(
            "contract_file",
            default_value=default_contract,
            description="Topic contract YAML (SSOT) used for dynamic QoS derivation",
        ),
        DeclareLaunchArgument(
            "topics_file",
            default_value=default_topics,
            description="YAML file containing topics list or topic contract YAML (SSOT)",
        ),
        DeclareLaunchArgument(
            "qos_overrides_path",
            default_value="",
            description=(
                "Optional explicit rosbag2 QoS override YAML. When empty (default), "
                "QoS overrides are dynamically derived from contract_file."
            ),
        ),
        DeclareLaunchArgument(
            "max_bag_size",
            default_value="3221225472",
            description="Maximum MCAP file size in bytes before splitting (FAT32-safe default)",
        ),
        DeclareLaunchArgument(
            "max_bag_duration",
            default_value="900",
            description="Maximum MCAP file duration in seconds before splitting (0 disables)",
        ),
        DeclareLaunchArgument(
            "max_cache_size",
            default_value="104857600",
            description="rosbag2 write-cache size in bytes (0 disables caching)",
        ),
        DeclareLaunchArgument(
            "min_free_bytes",
            default_value="5368709120",
            description=(
                "Refuse to start if free space is below this many bytes "
                "(default 5 GB). Prevents the disk-full restart storm."
            ),
        ),
        DeclareLaunchArgument(
            "storage_config_file",
            default_value="",
            description=(
                "MCAP storage config YAML. When set, it replaces the default "
                "zstd_fast preset (e.g. noChunking for real-time flush)."
            ),
        ),
        OpaqueFunction(function=_start_recorder),
    ])
