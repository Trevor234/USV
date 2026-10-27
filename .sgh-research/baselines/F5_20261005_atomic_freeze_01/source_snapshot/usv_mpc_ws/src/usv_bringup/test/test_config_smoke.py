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

    expected_topics = {
        "/mavros/local_position/odom",
        "/mavros/imu/data",
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
