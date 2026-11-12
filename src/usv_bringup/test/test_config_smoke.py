from pathlib import Path

import yaml


def test_bringup_yaml_configs_parse():
    config_dir = Path(__file__).resolve().parents[1] / "config"
    yaml_files = sorted(config_dir.glob("*.yaml"))
    assert yaml_files
    for path in yaml_files:
        with path.open("r", encoding="utf-8") as f:
            assert yaml.safe_load(f) is not None, path


def test_topic_contract_has_profile_stamp_contract():
    contract_path = Path(__file__).resolve().parents[1] / "config" / "topic_contract.yaml"
    text = contract_path.read_text(encoding="utf-8")
    assert "stamp_sec" in text
    assert "stamp_nanosec" in text
    assert "/path/reference" in text
    assert "/path/reference_profile" in text


def test_bag_topics_are_valid_and_in_topic_contract():
    package_dir = Path(__file__).resolve().parents[1]
    with (package_dir / "config" / "bag_topics.yaml").open("r", encoding="utf-8") as f:
        topics = yaml.safe_load(f)["topics"]
    contract = (package_dir / "config" / "topic_contract.yaml").read_text(
        encoding="utf-8"
    )

    assert topics
    assert len(topics) == len(set(topics))
    assert all(isinstance(topic, str) and topic.startswith("/") for topic in topics)
    assert all(topic in contract for topic in topics)


def test_rosbag_qos_overrides_match_sensor_topics():
    package_dir = Path(__file__).resolve().parents[1]
    with (package_dir / "config" / "bag_topics.yaml").open("r", encoding="utf-8") as f:
        topics = set(yaml.safe_load(f)["topics"])
    with (package_dir / "config" / "rosbag_qos_overrides.yaml").open(
        "r", encoding="utf-8"
    ) as f:
        overrides = yaml.safe_load(f)

    # BEST_EFFORT 发布的 MAVROS 传感器话题 (录制器必须以 best_effort 订阅):
    # odom/imu 以及 2026-10-09 加入的 raw/fix (GPS 经纬度原值)。
    expected_topics = {
        "/mavros/local_position/odom",
        "/mavros/imu/data",
        "/mavros/global_position/raw/fix",
    }
    assert set(overrides) == expected_topics
    assert set(overrides).issubset(topics)
    for profile in overrides.values():
        assert profile["reliability"] == "best_effort"
        assert profile["durability"] == "volatile"
        assert profile["history"] == "keep_last"
        assert profile["depth"] > 0


def test_record_launch_uses_mcap_storage_compression_only():
    launch_path = Path(__file__).resolve().parents[1] / "launch" / "record.launch.py"
    text = launch_path.read_text(encoding="utf-8")

    assert '"mcap"' in text
    assert '"zstd_fast"' in text
    assert '"--storage-preset-profile"' in text
    assert "--compression-mode" not in text
    assert "--compression-format" not in text


def test_scheme_mode_contract_matches_output_backend():
    """方案 ↔ FCU 模式是一一对应的硬契约, 写错就是船不动。

    A 输出速度 setpoint, 只有 GUIDED 执行; B 输出 RC 覆写, 只有 MANUAL
    下才经 ArduRover pilot 输入链成为舵/油主控制。2026-11-12 实船方案 B
    因 launch 未传 allowed_fcu_modes、节点默认 GUIDED, 切到 GUIDED 后
    原地不动 —— 契约必须由参数文件本身声明, 不能依赖 launch 兜底。
    """
    config_dir = Path(__file__).resolve().parents[1] / "config"
    expected = {"mpc_params_A.yaml": ["GUIDED"], "mpc_params_B.yaml": ["MANUAL"]}
    for filename, modes in expected.items():
        with (config_dir / filename).open("r", encoding="utf-8") as f:
            params = yaml.safe_load(f)["/**"]["ros__parameters"]
        assert params["allowed_fcu_modes"] == modes, filename
